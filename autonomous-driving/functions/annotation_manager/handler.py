"""自動運転 / ADAS アノテーション管理 Lambda ハンドラ

Amazon Bedrock でアノテーション提案を生成し、Amazon SageMaker Batch Transform
で点群セグメンテーション推論を実行する。
COCO 互換 JSON 形式でアノテーションメタデータを出力する。

COCO フォーマット:
    {
        "images": [{"id": N, "file_name": "...", "width": W, "height": H}],
        "annotations": [{"id": N, "image_id": N, "category_id": N, "bbox": [...]}],
        "categories": [{"id": N, "name": "...", "supercategory": "..."}]
    }

Environment Variables:
    OUTPUT_BUCKET: S3 出力バケット名
    BEDROCK_MODEL_ID: Bedrock モデル ID
    SNS_TOPIC_ARN: SNS トピック ARN
    SAGEMAKER_TRANSFORM_JOB_NAME: SageMaker Transform ジョブ名プレフィックス
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)

# COCO カテゴリ定義（自動運転ドメイン）
COCO_CATEGORIES = [
    {"id": 1, "name": "vehicle", "supercategory": "transportation"},
    {"id": 2, "name": "pedestrian", "supercategory": "person"},
    {"id": 3, "name": "cyclist", "supercategory": "person"},
    {"id": 4, "name": "traffic_sign", "supercategory": "infrastructure"},
    {"id": 5, "name": "traffic_light", "supercategory": "infrastructure"},
    {"id": 6, "name": "lane_marking", "supercategory": "road"},
    {"id": 7, "name": "road", "supercategory": "road"},
    {"id": 8, "name": "building", "supercategory": "structure"},
    {"id": 9, "name": "vegetation", "supercategory": "nature"},
    {"id": 10, "name": "other", "supercategory": "misc"},
]


# ラベル名から COCO カテゴリ ID へのマッピング
LABEL_TO_CATEGORY = {
    "car": 1, "vehicle": 1, "automobile": 1, "truck": 1, "bus": 1,
    "motorcycle": 1,
    "pedestrian": 2, "person": 2, "human": 2,
    "cyclist": 3, "bicycle": 3,
    "traffic sign": 4, "stop sign": 4, "sign": 4,
    "traffic light": 5,
    "lane": 6, "lane marking": 6,
    "road": 7, "highway": 7,
    "building": 8,
    "tree": 9, "vegetation": 9,
}


def _map_label_to_category_id(label: str) -> int:
    """ラベル名を COCO カテゴリ ID にマッピングする

    Args:
        label: 検出ラベル名

    Returns:
        int: カテゴリ ID（マッピングなしの場合は 10 = other）
    """
    return LABEL_TO_CATEGORY.get(label.lower(), 10)


def _compute_label_distribution(labels: list[int]) -> dict[int, int]:
    """セグメンテーションラベルの分布を計算する

    Args:
        labels: セグメンテーションラベルのリスト

    Returns:
        dict[int, int]: ラベル ID → 出現回数のマッピング
    """
    distribution: dict[int, int] = {}
    for label in labels:
        distribution[label] = distribution.get(label, 0) + 1
    return distribution


def build_coco_annotations(
    detection_results: list[dict],
    qc_results: list[dict] | None = None,
    sagemaker_output: dict | None = None,
) -> dict:
    """検出結果から COCO 互換アノテーション JSON を構築する

    Args:
        detection_results: フレーム抽出 Lambda からの検出結果リスト
        qc_results: 点群 QC Lambda からの QC 結果リスト（オプション）
        sagemaker_output: SageMaker Batch Transform 出力（オプション）
            - s3_path: 出力 S3 パス
            - point_count: ポイント数
            - labels: セグメンテーションラベルリスト

    Returns:
        dict: COCO 互換 JSON 構造
            - images: 画像情報リスト
            - annotations: アノテーションリスト
            - categories: カテゴリリスト
            - point_cloud_segmentation: セグメンテーション情報（sagemaker_output 存在時）
    """
    images = []
    annotations = []
    annotation_id = 1
    image_id = 1

    for result in detection_results:
        file_key = result.get("file_key", f"unknown_{image_id}")
        frames_extracted = result.get("frames_extracted", 0)
        detections = result.get("detections", [])

        # 各フレームを画像として登録
        for frame_data in detections:
            frame_index = frame_data.get("frame_index", 0)
            timestamp_ms = frame_data.get("timestamp_ms", 0)

            image_entry = {
                "id": image_id,
                "file_name": f"{file_key}_frame_{frame_index}",
                "width": 1920,  # デフォルト解像度
                "height": 1080,
                "metadata": {
                    "source_video": file_key,
                    "frame_index": frame_index,
                    "timestamp_ms": timestamp_ms,
                },
            }
            images.append(image_entry)

            # 各検出をアノテーションとして登録
            for obj in frame_data.get("objects", []):
                label = obj.get("label", "unknown")
                confidence = obj.get("confidence", 0.0)
                bbox = obj.get("bounding_box")

                category_id = _map_label_to_category_id(label)

                annotation_entry = {
                    "id": annotation_id,
                    "image_id": image_id,
                    "category_id": category_id,
                    "bbox": _convert_bbox(bbox) if bbox else [0, 0, 0, 0],
                    "area": _calculate_area(bbox) if bbox else 0,
                    "iscrowd": 0,
                    "attributes": {
                        "confidence": confidence,
                        "original_label": label,
                    },
                }
                annotations.append(annotation_entry)
                annotation_id += 1

            image_id += 1

    # 画像がない場合でもカテゴリは含める
    result = {
        "images": images,
        "annotations": annotations,
        "categories": COCO_CATEGORIES,
    }

    # SageMaker Batch Transform 出力の統合
    if sagemaker_output:
        segmentation_labels = sagemaker_output.get("labels", [])
        point_count = sagemaker_output.get("point_count", 0)
        s3_path = sagemaker_output.get("s3_path", "")

        result["point_cloud_segmentation"] = {
            "source": "sagemaker_batch_transform",
            "s3_path": s3_path,
            "point_count": point_count,
            "labels_count": len(segmentation_labels),
            "labels": segmentation_labels,
            "category_distribution": _compute_label_distribution(segmentation_labels),
        }

    return result


def _convert_bbox(bbox: dict | None) -> list[float]:
    """バウンディングボックスを COCO 形式 [x, y, width, height] に変換する

    Args:
        bbox: {"left": float, "top": float, "width": float, "height": float}

    Returns:
        list[float]: [x, y, width, height] (ピクセル座標)
    """
    if not bbox:
        return [0, 0, 0, 0]

    # Rekognition の正規化座標をピクセル座標に変換（1920x1080 想定）
    img_width = 1920
    img_height = 1080

    x = bbox.get("left", 0.0) * img_width
    y = bbox.get("top", 0.0) * img_height
    w = bbox.get("width", 0.0) * img_width
    h = bbox.get("height", 0.0) * img_height

    return [round(x, 1), round(y, 1), round(w, 1), round(h, 1)]


def _calculate_area(bbox: dict | None) -> float:
    """バウンディングボックスの面積を計算する

    Args:
        bbox: {"left": float, "top": float, "width": float, "height": float}

    Returns:
        float: 面積（ピクセル^2）
    """
    if not bbox:
        return 0.0

    img_width = 1920
    img_height = 1080
    w = bbox.get("width", 0.0) * img_width
    h = bbox.get("height", 0.0) * img_height
    return round(w * h, 1)


def _invoke_bedrock_annotation_suggestions(
    bedrock_client, model_id: str, detection_results: list[dict]
) -> str:
    """Bedrock でアノテーション提案を生成する

    Args:
        bedrock_client: boto3 Bedrock Runtime クライアント
        model_id: Bedrock モデル ID
        detection_results: 検出結果リスト

    Returns:
        str: 生成されたアノテーション提案テキスト
    """
    prompt = (
        "以下の自動運転データの物体検出結果に基づいて、"
        "アノテーション品質改善の提案を生成してください。\n\n"
        f"検出結果サマリー:\n"
        f"- 処理ファイル数: {len(detection_results)}\n"
        f"- 総検出数: {sum(len(r.get('detections', [])) for r in detection_results)}\n\n"
        "提案事項を箇条書きで出力してください。"
    )

    try:
        with xray_subsegment(

            name="bedrock_invokemodel",

            annotations={"service_name": "bedrock", "operation": "InvokeModel", "use_case": "autonomous-driving"},

        ):

            response = bedrock_client.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "inputText": prompt,
                "textGenerationConfig": {
                    "maxTokenCount": 1024,
                    "temperature": 0.3,
                },
            }),
        )
        response_body = json.loads(response["body"].read())
        return response_body.get("results", [{}])[0].get(
            "outputText", "No suggestions generated"
        )
    except Exception as e:
        logger.warning("Bedrock annotation suggestion failed: %s", e)
        return f"Annotation suggestion generation failed: {e}"


def _start_sagemaker_transform(
    sagemaker_client, job_name_prefix: str, qc_results: list[dict]
) -> dict:
    """SageMaker Batch Transform ジョブを開始する（点群セグメンテーション）

    Args:
        sagemaker_client: boto3 SageMaker クライアント
        job_name_prefix: ジョブ名プレフィックス
        qc_results: 点群 QC 結果リスト

    Returns:
        dict: Transform ジョブ情報
    """
    # 注: 実際のジョブ開始はモデルエンドポイントが必要
    # ここではジョブ情報のみ返す（シミュレーション）
    passed_files = [r for r in qc_results if r.get("status") == "PASS"]

    return {
        "job_name": f"{job_name_prefix}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "input_files": len(passed_files),
        "status": "SIMULATED",
        "message": "SageMaker Batch Transform requires model endpoint configuration",
    }


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """アノテーション管理 Lambda

    Bedrock でアノテーション提案生成、SageMaker Batch Transform で
    点群セグメンテーション推論を実行し、COCO 互換 JSON を出力する。

    Input:
        {"detection_results": [...], "qc_results": [...]}

    Output:
        {
            "status": "SUCCESS",
            "annotations": {"images": [...], "annotations": [...], "categories": [...]},
            "output_key": "..."
        }
    """
    detection_results = event.get("detection_results", [])
    qc_results = event.get("qc_results", [])
    sagemaker_output = event.get("sagemaker_output", None)

    output_bucket = os.environ["OUTPUT_BUCKET"]
    model_id = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")
    sns_topic_arn = os.environ.get("SNS_TOPIC_ARN", "")
    transform_job_prefix = os.environ.get(
        "SAGEMAKER_TRANSFORM_JOB_NAME", "ad-segmentation"
    )

    logger.info(
        "Annotation Manager started: detection_results=%d, qc_results=%d",
        len(detection_results),
        len(qc_results),
    )

    # COCO 互換アノテーション構築
    coco_annotations = build_coco_annotations(
        detection_results, qc_results, sagemaker_output
    )

    # Bedrock でアノテーション提案生成
    bedrock_client = boto3.client("bedrock-runtime")
    suggestions = _invoke_bedrock_annotation_suggestions(
        bedrock_client, model_id, detection_results
    )

    # SageMaker Batch Transform（点群セグメンテーション）
    sagemaker_client = boto3.client("sagemaker")
    transform_info = _start_sagemaker_transform(
        sagemaker_client, transform_job_prefix, qc_results
    )

    # 出力キー生成
    now = datetime.now(timezone.utc)
    output_key = f"annotations/{now.strftime('%Y/%m/%d')}/coco_annotations.json"

    # 結果を S3 出力バケットに書き込み
    s3_client = boto3.client("s3")
    output_data = {
        "status": "SUCCESS",
        "annotations": coco_annotations,
        "annotation_suggestions": suggestions,
        "transform_job": transform_info,
        "output_key": output_key,
        "summary": {
            "total_images": len(coco_annotations["images"]),
            "total_annotations": len(coco_annotations["annotations"]),
            "total_categories": len(coco_annotations["categories"]),
            "qc_passed_files": len(
                [r for r in qc_results if r.get("status") == "PASS"]
            ),
            "qc_failed_files": len(
                [r for r in qc_results if r.get("status") == "FAIL"]
            ),
        },
    }

    s3_client.put_object(
        Bucket=output_bucket,
        Key=output_key,
        Body=json.dumps(output_data, default=str),
        ContentType="application/json",
    )

    # SNS 通知
    if sns_topic_arn:
        try:
            sns_client = boto3.client("sns")
            sns_client.publish(
                TopicArn=sns_topic_arn,
                Subject="Autonomous Driving Annotation Complete",
                Message=json.dumps({
                    "status": "SUCCESS",
                    "total_annotations": len(coco_annotations["annotations"]),
                    "output_key": output_key,
                }, indent=2),
            )
        except Exception as e:
            logger.warning("SNS notification failed: %s", e)

    logger.info(
        "Annotation Manager completed: images=%d, annotations=%d",
        len(coco_annotations["images"]),
        len(coco_annotations["annotations"]),
    )


    # EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="annotation_manager")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "autonomous-driving"))
    metrics.put_metric("FilesProcessed", 1.0, "Count")
    metrics.flush()

    return {
        "status": "SUCCESS",
        "annotations": coco_annotations,
        "output_key": output_key,
    }
