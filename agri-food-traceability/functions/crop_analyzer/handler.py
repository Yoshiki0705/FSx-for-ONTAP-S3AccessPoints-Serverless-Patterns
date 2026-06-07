"""農業・食品業界 (UC21) Crop Analyzer Lambda ハンドラ

航空画像に対して植生指数分析と異常検出を実行する。
Rekognition でラベル検出し、Bedrock で植生異常を分類する。

機能:
    - Rekognition DetectLabels による植物/農地関連ラベル検出
    - Bedrock 推論による植生異常分類 (pest damage, irrigation issues)
    - 信頼度スコア 0.70 未満の結果はフィルタ ("review-required")
    - EXIF GPS 情報がない場合は "location-unverified" として処理続行

Confidence Threshold:
    - CropAnomalyConfidenceThreshold (default: 0.70)

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
    BEDROCK_MODEL_ID: Bedrock モデル ID
    CROP_ANOMALY_CONFIDENCE_THRESHOLD: 異常検出信頼度閾値 (default: 0.70)
    CROSS_REGION_TEXTRACT_REGION: Cross-Region (unused here, for consistency)
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import trace_lambda_handler
from shared.retry_handler import retry_with_backoff, RetryConfig

logger = logging.getLogger(__name__)

# 異常分類カテゴリ
ANOMALY_TYPES: list[str] = [
    "pest_damage",
    "irrigation_issue",
    "nutrient_deficiency",
    "disease",
    "weed_infestation",
    "drought_stress",
    "waterlogging",
]

# 植生関連の Rekognition ラベル
VEGETATION_LABELS: frozenset[str] = frozenset(
    {
        "Plant",
        "Vegetation",
        "Grass",
        "Tree",
        "Field",
        "Farm",
        "Crop",
        "Agriculture",
        "Nature",
        "Outdoors",
        "Land",
    }
)

DEFAULT_CONFIDENCE_THRESHOLD: float = 0.70


def extract_exif_geolocation(metadata: dict) -> dict | None:
    """EXIF メタデータから GPS 情報を抽出する。

    実際の実装では pillow/exifread で GPS タグを読む想定だが、
    ここでは S3 メタデータのカスタムヘッダからの取得をシミュレート。

    Args:
        metadata: S3 オブジェクトメタデータ

    Returns:
        GPS 情報 dict (lat, lon) or None
    """
    lat = metadata.get("x-amz-meta-gps-latitude") or metadata.get("gps_latitude")
    lon = metadata.get("x-amz-meta-gps-longitude") or metadata.get("gps_longitude")

    if lat is not None and lon is not None:
        try:
            return {"latitude": float(lat), "longitude": float(lon)}
        except (ValueError, TypeError):
            return None

    return None


def analyze_vegetation_with_rekognition(
    rekognition_client,
    s3_bucket: str,
    s3_key: str,
) -> dict:
    """Rekognition でラベル検出を行い植生関連の情報を返す。

    Args:
        rekognition_client: boto3 rekognition client
        s3_bucket: S3 バケット/AP エイリアス
        s3_key: オブジェクトキー

    Returns:
        dict: labels, vegetation_coverage, detected_issues
    """

    @retry_with_backoff(config=RetryConfig(max_attempts=3))
    def _detect_labels():
        return rekognition_client.detect_labels(
            Image={"S3Object": {"Bucket": s3_bucket, "Name": s3_key}},
            MaxLabels=50,
            MinConfidence=50.0,
        )

    response = _detect_labels()
    labels = response.get("Labels", [])

    vegetation_labels = []
    issue_labels = []

    for label in labels:
        label_name = label.get("Name", "")
        confidence = label.get("Confidence", 0) / 100.0  # 0-1 scale

        if label_name in VEGETATION_LABELS:
            vegetation_labels.append(
                {
                    "name": label_name,
                    "confidence": round(confidence, 4),
                }
            )
        else:
            issue_labels.append(
                {
                    "name": label_name,
                    "confidence": round(confidence, 4),
                }
            )

    return {
        "vegetation_labels": vegetation_labels,
        "other_labels": issue_labels,
        "total_labels": len(labels),
    }


def classify_anomalies_with_bedrock(
    bedrock_client,
    model_id: str,
    vegetation_data: dict,
    confidence_threshold: float,
) -> list[dict]:
    """Bedrock で植生異常を分類する。

    Args:
        bedrock_client: boto3 bedrock-runtime client
        model_id: Bedrock モデル ID
        vegetation_data: Rekognition 解析結果
        confidence_threshold: 信頼度閾値

    Returns:
        list[dict]: 検出された異常リスト
    """
    prompt = (
        "You are an agricultural image analysis expert. "
        "Based on the following Rekognition labels detected in a farmland aerial image, "
        "identify any crop anomalies. Classify each anomaly into one of these categories: "
        f"{', '.join(ANOMALY_TYPES)}. "
        "For each anomaly, provide a confidence score between 0.0 and 1.0.\n\n"
        f"Detected labels: {json.dumps(vegetation_data)}\n\n"
        "Respond in JSON format: "
        '[{"anomaly_type": "...", "confidence": 0.XX, "description": "..."}]'
    )

    @retry_with_backoff(config=RetryConfig(max_attempts=3))
    def _invoke_model():
        return bedrock_client.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": prompt}],
                }
            ),
        )

    response = _invoke_model()
    response_body = json.loads(response["body"].read())

    # Claude response parsing
    text_content = ""
    if "content" in response_body:
        for block in response_body["content"]:
            if block.get("type") == "text":
                text_content = block.get("text", "")
                break

    # Parse anomalies from response
    anomalies = []
    try:
        # Find JSON array in response
        start_idx = text_content.find("[")
        end_idx = text_content.rfind("]") + 1
        if start_idx >= 0 and end_idx > start_idx:
            parsed = json.loads(text_content[start_idx:end_idx])
            for item in parsed:
                confidence = float(item.get("confidence", 0))
                anomaly_type = item.get("anomaly_type", "unknown")
                if anomaly_type in ANOMALY_TYPES and confidence >= confidence_threshold:
                    anomalies.append(
                        {
                            "anomaly_type": anomaly_type,
                            "confidence": round(confidence, 4),
                            "description": item.get("description", ""),
                            "status": "confirmed",
                        }
                    )
                elif anomaly_type in ANOMALY_TYPES and confidence > 0:
                    anomalies.append(
                        {
                            "anomaly_type": anomaly_type,
                            "confidence": round(confidence, 4),
                            "description": item.get("description", ""),
                            "status": "review-required",
                            "reason": f"Confidence {confidence:.2f} below threshold {confidence_threshold}",
                        }
                    )
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.warning("Failed to parse Bedrock anomaly response: %s", str(e))

    return anomalies


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Agri-Food Crop Analyzer Lambda

    航空画像に対して植生指数分析と異常検出を実行する。

    Input event (single image object from Map state):
        - Key: S3 オブジェクトキー
        - Size: ファイルサイズ
        - category: "aerial_image"
        - (optional) metadata: S3 メタデータ

    Returns:
        dict: status, key, geolocation, anomalies, vegetation_data
    """
    start_time = time.time()

    s3_access_point = os.environ["S3_ACCESS_POINT"]
    bedrock_model_id = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-haiku-4-5-20251001-v1:0")
    confidence_threshold = float(os.environ.get("CROP_ANOMALY_CONFIDENCE_THRESHOLD", str(DEFAULT_CONFIDENCE_THRESHOLD)))

    object_key = event.get("Key", "")
    object_size = event.get("Size", 0)
    metadata = event.get("metadata", {})

    logger.info(
        "Crop analysis started: key=%s, size=%d, threshold=%.2f",
        object_key,
        object_size,
        confidence_threshold,
    )

    # GPS 位置情報の抽出
    geolocation = extract_exif_geolocation(metadata)
    location_status = "verified" if geolocation else "location-unverified"

    if not geolocation:
        logger.info(
            "Missing geolocation for %s — classifying as location-unverified",
            object_key,
        )

    # Rekognition による植生解析
    rekognition_client = boto3.client("rekognition")
    vegetation_data = analyze_vegetation_with_rekognition(rekognition_client, s3_access_point, object_key)

    # Bedrock による異常分類
    bedrock_client = boto3.client("bedrock-runtime")
    anomalies = classify_anomalies_with_bedrock(bedrock_client, bedrock_model_id, vegetation_data, confidence_threshold)

    confirmed_anomalies = [a for a in anomalies if a.get("status") == "confirmed"]
    review_required = [a for a in anomalies if a.get("status") == "review-required"]

    processing_duration_ms = int((time.time() - start_time) * 1000)

    result = {
        "status": "success",
        "key": object_key,
        "size": object_size,
        "location_status": location_status,
        "geolocation": geolocation,
        "exif_metadata": {
            "filename": object_key.split("/")[-1] if "/" in object_key else object_key,
            "capture_date": metadata.get("capture_date"),
            "camera_model": metadata.get("camera_model"),
        },
        "vegetation_analysis": vegetation_data,
        "anomalies": {
            "confirmed": confirmed_anomalies,
            "review_required": review_required,
            "total_detected": len(anomalies),
            "confirmed_count": len(confirmed_anomalies),
            "review_required_count": len(review_required),
        },
        "confidence_threshold": confidence_threshold,
        "processing_duration_ms": processing_duration_ms,
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }

    logger.info(
        "Crop analysis completed: key=%s, location=%s, anomalies=%d (confirmed=%d, review=%d)",
        object_key,
        location_status,
        len(anomalies),
        len(confirmed_anomalies),
        len(review_required),
    )

    return result
