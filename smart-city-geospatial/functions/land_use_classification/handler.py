"""UC17 Smart City Land Use Classification Lambda.

衛星画像・航空写真から土地利用分類（residential, commercial, industrial, agricultural,
forest, water, road 等）を推定する。

画像サイズにより Rekognition / SageMaker を切替。

Environment Variables:
    S3_ACCESS_POINT_ALIAS: 入力 S3 AP (optional)
    INFERENCE_TYPE: "none" | "provisioned" | "serverless" | "components"
    SAGEMAKER_ENDPOINT_NAME: SageMaker Endpoint 名
    REKOGNITION_MIN_CONFIDENCE: default 60.0
    OUTPUT_DESTINATION: `STANDARD_S3` or `FSXN_S3AP` (デフォルト: `STANDARD_S3`)
    OUTPUT_BUCKET: STANDARD_S3 モードの出力バケット
    OUTPUT_S3AP_ALIAS: FSXN_S3AP モードの S3AP Alias or ARN
    OUTPUT_S3AP_PREFIX: FSXN_S3AP モードの出力プレフィックス
"""

from __future__ import annotations

import json
import logging
import os

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler
from shared.output_writer import OutputWriter
from shared.routing import determine_inference_path, InferencePath
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)


# Rekognition label → 土地利用クラスマッピング
LABEL_TO_LANDUSE = {
    "Building": "residential",
    "House": "residential",
    "Office Building": "commercial",
    "Skyscraper": "commercial",
    "Factory": "industrial",
    "Warehouse": "industrial",
    "Farm": "agricultural",
    "Field": "agricultural",
    "Forest": "forest",
    "Tree": "forest",
    "Water": "water",
    "Lake": "water",
    "River": "water",
    "Road": "road",
    "Highway": "road",
    "Vehicle": "transport",
}


def map_labels_to_landuse(labels: list[dict]) -> dict[str, float]:
    """Rekognition label から土地利用分類分布を算出する。"""
    distribution: dict[str, float] = {}
    total_confidence = 0.0
    for label in labels:
        name = label.get("Name") or label.get("label", "")
        confidence = float(label.get("Confidence") or label.get("confidence", 0.0))
        landuse = LABEL_TO_LANDUSE.get(name)
        if landuse:
            distribution[landuse] = distribution.get(landuse, 0.0) + confidence
            total_confidence += confidence

    # 正規化
    if total_confidence > 0:
        distribution = {k: v / total_confidence for k, v in distribution.items()}
    return distribution


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """UC17 Land Use Classification Lambda ハンドラ。

    Input: {"source_key": "gis/area.tif", "Size": int}
    Output: {"source_key": str, "landuse_distribution": {...}, "inference_path": str}
    """
    output_writer = OutputWriter.from_env()
    s3_access_point = os.environ.get("S3_ACCESS_POINT_ALIAS")
    min_confidence = float(os.environ.get("REKOGNITION_MIN_CONFIDENCE", "60.0"))
    inference_type = os.environ.get("INFERENCE_TYPE", "none")
    endpoint_name = os.environ.get("SAGEMAKER_ENDPOINT_NAME", "")

    source_key = event.get("source_key") or event.get("Key")
    if not source_key:
        raise ValueError("Input must contain 'source_key' or 'Key'")

    # 画像ダウンロード
    if s3_access_point:
        s3ap = S3ApHelper(s3_access_point)
        response = s3ap.get_object(source_key)
    else:
        # Fallback: OUTPUT_BUCKET からの直接読み取り（テスト互換）
        fallback_bucket = os.environ.get("OUTPUT_BUCKET", "")
        s3_client = boto3.client("s3")
        response = s3_client.get_object(Bucket=fallback_bucket, Key=source_key)

    image_bytes = response["Body"].read()
    image_size = len(image_bytes)

    # ラスター画像のみ分類（ベクターデータはスキップ）
    is_raster = source_key.lower().endswith((".tif", ".tiff"))
    if not is_raster:
        logger.info("Skipping non-raster file: %s", source_key)
        return {
            "source_key": source_key,
            "landuse_distribution": {},
            "inference_path": "skipped",
            "skipped": True,
        }

    # ルーティング
    rekognition_limit = 5 * 1024 * 1024  # 5 MB
    if inference_type == "none" or image_size < rekognition_limit:
        inference_path = "rekognition"
        rekognition = boto3.client("rekognition")
        try:
            response = rekognition.detect_labels(
                Image={"Bytes": image_bytes},
                MaxLabels=50,
                MinConfidence=min_confidence,
            )
            labels = response.get("Labels", [])
        except rekognition.exceptions.InvalidImageFormatException as e:
            logger.warning("InvalidImageFormat (continuing with empty labels): %s", e)
            labels = []
        except rekognition.exceptions.ImageTooLargeException as e:
            logger.warning("ImageTooLarge (continuing with empty labels): %s", e)
            labels = []
        except Exception as e:
            logger.error("Rekognition failed: %s", e)
            labels = []
    else:
        # SageMaker ルート（Phase 6B routing 利用）
        file_count = event.get("file_count", 1)
        batch_threshold = int(os.environ.get("BATCH_THRESHOLD", "10"))
        try:
            decision = determine_inference_path(
                file_count=file_count,
                batch_threshold=batch_threshold,
                inference_type=inference_type,
            )
            if decision == InferencePath.REALTIME_ENDPOINT:
                inference_path = "sagemaker_realtime"
            elif decision == InferencePath.SERVERLESS_INFERENCE:
                inference_path = "sagemaker_serverless"
            elif decision == InferencePath.INFERENCE_COMPONENTS:
                inference_path = "sagemaker_components"
            else:
                inference_path = "sagemaker_batch"
        except ValueError:
            inference_path = "rekognition"
            labels = []

        # Actual SageMaker invocation
        if endpoint_name:
            runtime = boto3.client("sagemaker-runtime")
            try:
                sm_response = runtime.invoke_endpoint(
                    EndpointName=endpoint_name,
                    Body=image_bytes,
                    ContentType="image/tiff",
                    Accept="application/json",
                )
                labels = json.loads(sm_response["Body"].read())
            except Exception as e:
                logger.error("SageMaker failed: %s", e)
                labels = []
        else:
            labels = []

    landuse_distribution = map_labels_to_landuse(labels)

    # 結果を出力先に書き出し
    result_key = f"landuse/{source_key}.json"
    output_writer.put_json(
        key=result_key,
        data={
            "source_key": source_key,
            "inference_path": inference_path,
            "landuse_distribution": landuse_distribution,
            "label_count": len(labels),
        },
    )

    logger.info(
        "UC17 LandUse Classification: source=%s, path=%s, classes=%d",
        source_key,
        inference_path,
        len(landuse_distribution),
    )

    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="land_use_classification")
    metrics.set_dimension("UseCase", "smart-city-geospatial")
    metrics.set_dimension("InferencePath", inference_path)
    metrics.put_metric("ImagesClassified", 1.0, "Count")
    metrics.put_metric("LandUseClasses", float(len(landuse_distribution)), "Count")
    metrics.flush()

    return {
        "source_key": source_key,
        "result_key": result_key,
        "inference_path": inference_path,
        "landuse_distribution": landuse_distribution,
    }
