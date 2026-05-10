"""UC15 Defense/Space Object Detection Lambda

衛星画像タイルから物体検出を実行する。

画像サイズによって推論経路を切替える:
- < 5 MB: Amazon Rekognition DetectLabels（同期、低レイテンシ）
- >= 5 MB: SageMaker Batch Transform（大容量対応）

Environment Variables:
    OUTPUT_BUCKET: 出力先 S3 バケット名
    S3_ACCESS_POINT_ALIAS: 入力 S3 AP Alias (optional)
    REKOGNITION_MIN_CONFIDENCE: Rekognition 検出最小信頼度 (default: 70.0)
    REKOGNITION_MAX_LABELS: Rekognition 最大検出ラベル数 (default: 100)
    REKOGNITION_PAYLOAD_LIMIT_BYTES: Rekognition ペイロード上限 (default: 5242880 = 5MB)
    INFERENCE_TYPE: "none" | "provisioned" | "serverless" | "components" (default: "none")
    SAGEMAKER_ENDPOINT_NAME: SageMaker Endpoint (INFERENCE_TYPE != none で必須)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler
from shared.routing import determine_inference_path, InferencePath
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)

REKOGNITION_PAYLOAD_LIMIT_BYTES = 5 * 1024 * 1024  # 5 MB


def _detect_with_rekognition(
    image_bytes: bytes, min_confidence: float, max_labels: int
) -> list[dict[str, Any]]:
    """Rekognition DetectLabels で物体検出する。

    Args:
        image_bytes: 画像バイト列（5MB 以下）
        min_confidence: 検出最小信頼度 (0.0-100.0)
        max_labels: 最大検出ラベル数

    Returns:
        list[dict]: 検出結果 [{"label": str, "confidence": float, "bbox": dict}]
        画像フォーマット不正等のエラー時は空リストを返す（ワークフロー継続優先）
    """
    rekognition = boto3.client("rekognition")
    try:
        response = rekognition.detect_labels(
            Image={"Bytes": image_bytes},
            MaxLabels=max_labels,
            MinConfidence=min_confidence,
        )
    except rekognition.exceptions.InvalidImageFormatException as e:
        logger.warning("Rekognition InvalidImageFormat, returning empty detections: %s", e)
        return []
    except rekognition.exceptions.ImageTooLargeException as e:
        logger.warning("Rekognition ImageTooLarge, returning empty detections: %s", e)
        return []
    except ClientError as e:
        # 他のクライアントエラーも空リストで継続（ワークフロー停止を避ける）
        logger.error("Rekognition DetectLabels failed: %s", e)
        return []

    results = []
    for label in response.get("Labels", []):
        # Instances があれば bbox を付与、なければ全体としてラベル化
        instances = label.get("Instances", [])
        if instances:
            for instance in instances:
                results.append({
                    "label": label["Name"],
                    "confidence": instance.get("Confidence", label["Confidence"]),
                    "bbox": instance.get("BoundingBox", {}),
                })
        else:
            results.append({
                "label": label["Name"],
                "confidence": label["Confidence"],
                "bbox": {},
            })
    return results


def _detect_with_sagemaker(
    endpoint_name: str, image_bytes: bytes
) -> list[dict[str, Any]]:
    """SageMaker Endpoint で物体検出する（大容量画像用）。

    Args:
        endpoint_name: SageMaker Endpoint 名
        image_bytes: 画像バイト列

    Returns:
        list[dict]: 検出結果
    """
    sagemaker_runtime = boto3.client("sagemaker-runtime")
    try:
        response = sagemaker_runtime.invoke_endpoint(
            EndpointName=endpoint_name,
            Body=image_bytes,
            ContentType="image/tiff",
            Accept="application/json",
        )
    except ClientError as e:
        logger.error("SageMaker InvokeEndpoint failed: %s", e)
        raise

    body = response["Body"].read()
    try:
        predictions = json.loads(body)
        return predictions if isinstance(predictions, list) else [predictions]
    except json.JSONDecodeError:
        logger.warning("SageMaker response is not JSON: %s", body[:200])
        return []


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """UC15 Object Detection Lambda ハンドラ。

    Input:
        {
            "tile_key": "tiles/YYYY/MM/DD/image/tile_001.tif",
            "source_key": "satellite/...",
            "file_count": int (optional)
        }

    Output:
        {
            "tile_key": "...",
            "inference_path": "rekognition" | "sagemaker_realtime" | "sagemaker_batch",
            "detections": [...],
            "detection_count": int
        }
    """
    output_bucket = os.environ["OUTPUT_BUCKET"]
    s3_access_point = os.environ.get("S3_ACCESS_POINT_ALIAS")
    min_confidence = float(os.environ.get("REKOGNITION_MIN_CONFIDENCE", "70.0"))
    max_labels = int(os.environ.get("REKOGNITION_MAX_LABELS", "100"))
    payload_limit = int(
        os.environ.get("REKOGNITION_PAYLOAD_LIMIT_BYTES", REKOGNITION_PAYLOAD_LIMIT_BYTES)
    )
    inference_type = os.environ.get("INFERENCE_TYPE", "none")
    endpoint_name = os.environ.get("SAGEMAKER_ENDPOINT_NAME", "")

    tile_key = event.get("tile_key") or event.get("Key")
    if not tile_key:
        raise ValueError("Input event must contain 'tile_key' or 'Key'")

    # 画像ダウンロード
    if s3_access_point:
        s3ap = S3ApHelper(s3_access_point)
        response = s3ap.get_object(tile_key)
    else:
        s3_client = boto3.client("s3")
        response = s3_client.get_object(Bucket=output_bucket, Key=tile_key)

    image_bytes = response["Body"].read()
    image_size = len(image_bytes)

    # ルーティング決定: サイズとINFERENCE_TYPE から
    if inference_type == "none" or image_size < payload_limit:
        # Rekognition パス
        inference_path = "rekognition"
        detections = _detect_with_rekognition(image_bytes, min_confidence, max_labels)
    else:
        # SageMaker パス（Phase 6B routing 利用）
        file_count = event.get("file_count", 1)
        batch_threshold = int(os.environ.get("BATCH_THRESHOLD", "10"))
        try:
            routing_decision = determine_inference_path(
                file_count=file_count,
                batch_threshold=batch_threshold,
                inference_type=inference_type,
            )
            if routing_decision == InferencePath.REALTIME_ENDPOINT:
                inference_path = "sagemaker_realtime"
            elif routing_decision == InferencePath.SERVERLESS_INFERENCE:
                inference_path = "sagemaker_serverless"
            elif routing_decision == InferencePath.INFERENCE_COMPONENTS:
                inference_path = "sagemaker_components"
            else:
                inference_path = "sagemaker_batch"
        except ValueError as e:
            logger.error("Invalid inference_type: %s", e)
            inference_path = "rekognition"
            detections = _detect_with_rekognition(
                image_bytes[:payload_limit], min_confidence, max_labels
            )
            detection_count = len(detections)
            return {
                "tile_key": tile_key,
                "inference_path": inference_path,
                "detections": detections,
                "detection_count": detection_count,
            }

        if not endpoint_name:
            raise ValueError(
                f"SAGEMAKER_ENDPOINT_NAME required for INFERENCE_TYPE={inference_type}"
            )
        detections = _detect_with_sagemaker(endpoint_name, image_bytes)

    detection_count = len(detections)

    logger.info(
        "UC15 Object Detection completed: tile=%s, path=%s, detections=%d",
        tile_key,
        inference_path,
        detection_count,
    )

    # 結果を S3 に書き出し
    result_key = tile_key.replace(".tif", "_detections.json").replace(
        "tiles/", "detections/"
    )
    s3_client = boto3.client("s3")
    s3_client.put_object(
        Bucket=output_bucket,
        Key=result_key,
        Body=json.dumps(
            {
                "tile_key": tile_key,
                "inference_path": inference_path,
                "detections": detections,
                "detection_count": detection_count,
            },
            default=str,
        ),
        ContentType="application/json",
        ServerSideEncryption="aws:kms",
    )

    # EMF メトリクス
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="object_detection")
    metrics.set_dimension("UseCase", "defense-satellite")
    metrics.set_dimension("InferencePath", inference_path)
    metrics.put_metric("DetectionCount", float(detection_count), "Count")
    metrics.put_metric("TileSizeBytes", float(image_size), "Bytes")
    metrics.flush()

    return {
        "tile_key": tile_key,
        "inference_path": inference_path,
        "detections": detections,
        "detection_count": detection_count,
    }
