"""不動産 (UC26) Property Analyzer Lambda ハンドラ

物件画像から特徴を抽出し、リスティング説明文を生成する。

抽出対象 (Requirement 10.2):
    - 部屋数 (room_count)
    - 状態評価 (condition)
    - アメニティ検出 (amenities)

PII 検出 (Requirement 10.5):
    - 表札/文書が映り込んだ画像のフラグ付け

AI/ML サービス:
    - Amazon Rekognition: 画像ラベル + テキスト検出
    - Amazon Bedrock: リスティング説明文生成

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
    BEDROCK_MODEL_ID: Bedrock モデル ID
    CONFIDENCE_THRESHOLD: Rekognition 最小信頼度 (default: 80)
"""

from __future__ import annotations

import json
import logging
import os
import time

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler
from shared.retry_handler import RetryConfig, categorize_error, retry_with_backoff

logger = logging.getLogger(__name__)

# PII 関連テキストキーワード（表札・文書検出用）
PII_TEXT_KEYWORDS: frozenset[str] = frozenset(
    {
        "nameplate",
        "表札",
        "name plate",
        "mailbox",
        "ポスト",
        "document",
        "書類",
        "letter",
        "手紙",
        "certificate",
        "証明書",
    }
)

# 部屋タイプラベル
ROOM_LABELS: frozenset[str] = frozenset(
    {
        "bedroom",
        "bathroom",
        "kitchen",
        "living room",
        "dining room",
        "closet",
        "balcony",
        "office",
        "study",
        "laundry room",
    }
)

# アメニティラベル
AMENITY_LABELS: frozenset[str] = frozenset(
    {
        "pool",
        "swimming pool",
        "gym",
        "fitness",
        "parking",
        "elevator",
        "garden",
        "terrace",
        "air conditioning",
        "dishwasher",
        "washer",
        "dryer",
        "fireplace",
        "bathtub",
        "jacuzzi",
        "sauna",
        "solar panel",
    }
)

# 状態関連ラベル
CONDITION_NEGATIVE_LABELS: frozenset[str] = frozenset(
    {
        "mold",
        "crack",
        "stain",
        "damage",
        "rust",
        "leak",
        "broken",
    }
)


def analyze_image_rekognition(
    s3ap_alias: str,
    object_key: str,
    confidence_threshold: float,
    rekognition_client=None,
) -> dict:
    """Rekognition で物件画像を分析する。

    Args:
        s3ap_alias: S3 AP エイリアス
        object_key: 画像オブジェクトキー
        confidence_threshold: 最小信頼度閾値
        rekognition_client: Rekognition クライアント (テスト用)

    Returns:
        dict: labels, rooms, amenities, condition_issues, text_detections
    """
    if rekognition_client is None:
        rekognition_client = boto3.client("rekognition")

    @retry_with_backoff(config=RetryConfig(max_attempts=3))
    def _detect_labels():
        return rekognition_client.detect_labels(
            Image={"S3Object": {"Bucket": s3ap_alias, "Name": object_key}},
            MinConfidence=confidence_threshold,
            MaxLabels=100,
        )

    @retry_with_backoff(config=RetryConfig(max_attempts=3))
    def _detect_text():
        return rekognition_client.detect_text(
            Image={"S3Object": {"Bucket": s3ap_alias, "Name": object_key}},
        )

    # ラベル検出
    label_response = _detect_labels()
    labels = label_response.get("Labels", [])

    rooms: list[str] = []
    amenities: list[str] = []
    condition_issues: list[str] = []
    all_labels: list[dict] = []

    for label in labels:
        name = label.get("Name", "")
        confidence = label.get("Confidence", 0.0)
        name_lower = name.lower()

        all_labels.append({"name": name, "confidence": confidence})

        if name_lower in ROOM_LABELS:
            rooms.append(name_lower)
        if name_lower in AMENITY_LABELS:
            amenities.append(name_lower)
        if name_lower in CONDITION_NEGATIVE_LABELS:
            condition_issues.append(name_lower)

    # テキスト検出 (PII チェック用)
    text_response = _detect_text()
    text_detections = text_response.get("TextDetections", [])

    return {
        "labels": all_labels,
        "rooms": rooms,
        "amenities": amenities,
        "condition_issues": condition_issues,
        "text_detections": [
            {"text": t.get("DetectedText", ""), "confidence": t.get("Confidence", 0.0)}
            for t in text_detections
            if t.get("Type") == "LINE"
        ],
    }


def check_pii_in_image(text_detections: list[dict]) -> bool:
    """画像内のテキストから PII (表札/文書) の存在を判定する。

    Args:
        text_detections: Rekognition テキスト検出結果

    Returns:
        bool: PII が検出された場合 True
    """
    for detection in text_detections:
        text_lower = detection.get("text", "").lower()
        for keyword in PII_TEXT_KEYWORDS:
            if keyword in text_lower:
                return True
    # テキストが多い場合も文書映り込みの可能性
    if len(text_detections) > 10:
        return True
    return False


def generate_listing_description(
    property_id: str | None,
    analysis_results: list[dict],
    bedrock_client=None,
    model_id: str | None = None,
) -> str:
    """Bedrock で物件リスティング説明文を生成する。

    Args:
        property_id: 物件 ID
        analysis_results: 各画像の分析結果
        bedrock_client: Bedrock Runtime クライアント (テスト用)
        model_id: Bedrock モデル ID

    Returns:
        str: 生成されたリスティング説明文
    """
    if bedrock_client is None:
        bedrock_client = boto3.client("bedrock-runtime")

    if model_id is None:
        model_id = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-haiku-4-5-20251001-v1:0")

    # 分析結果を要約
    all_rooms: set[str] = set()
    all_amenities: set[str] = set()
    all_issues: list[str] = []

    for result in analysis_results:
        all_rooms.update(result.get("rooms", []))
        all_amenities.update(result.get("amenities", []))
        all_issues.extend(result.get("condition_issues", []))

    prompt = (
        f"以下の物件画像分析結果に基づき、不動産リスティング用の説明文を日本語で生成してください。\n"
        f"物件ID: {property_id or 'unknown'}\n"
        f"検出された部屋: {', '.join(sorted(all_rooms)) or 'N/A'}\n"
        f"アメニティ: {', '.join(sorted(all_amenities)) or 'N/A'}\n"
        f"状態懸念: {', '.join(all_issues) or 'なし'}\n\n"
        f"200文字以内で魅力的な説明文を生成してください。"
    )

    @retry_with_backoff(config=RetryConfig(max_attempts=3))
    def _call_bedrock():
        return bedrock_client.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 512,
                    "messages": [{"role": "user", "content": prompt}],
                }
            ),
        )

    try:
        response = _call_bedrock()
        response_body = json.loads(response["body"].read())
        return response_body.get("content", [{}])[0].get("text", "")
    except Exception as e:
        logger.warning("Listing description generation failed: %s", str(e))
        return ""


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Property Analyzer Lambda

    物件画像リストに対して特徴抽出 + PII 検出を行う。

    Input event:
        - objects: 物件画像オブジェクトリスト (Discovery Lambda の出力)

    Returns:
        dict: results, success_count, error_count
    """
    start_time = time.time()

    s3ap_alias = os.environ.get("S3_ACCESS_POINT", "")
    confidence_threshold = float(os.environ.get("CONFIDENCE_THRESHOLD", "80"))

    objects = event.get("objects", [])
    logger.info(
        "Property analysis started: %d objects, threshold=%.1f%%",
        len(objects),
        confidence_threshold,
    )

    results: list[dict] = []
    success_count = 0
    error_count = 0

    for obj in objects:
        key = obj.get("Key", "")
        property_id = obj.get("property_id")
        image_type = obj.get("image_type", "other")

        try:
            analysis = analyze_image_rekognition(s3ap_alias, key, confidence_threshold)

            # PII チェック (Requirement 10.5)
            pii_detected = check_pii_in_image(analysis["text_detections"])

            results.append(
                {
                    "key": key,
                    "property_id": property_id,
                    "image_type": image_type,
                    "status": "success",
                    "room_count": len(analysis["rooms"]),
                    "rooms": analysis["rooms"],
                    "amenities": analysis["amenities"],
                    "condition_issues": analysis["condition_issues"],
                    "condition": ("needs_repair" if analysis["condition_issues"] else "good"),
                    "pii_detected": pii_detected,
                    "requires_redaction": pii_detected,
                    "label_count": len(analysis["labels"]),
                }
            )
            success_count += 1

        except Exception as e:
            error_category = categorize_error(e)
            logger.warning(
                "Property analysis failed for %s: %s [%s]",
                key,
                str(e),
                error_category.value,
            )
            results.append(
                {
                    "key": key,
                    "property_id": property_id,
                    "image_type": image_type,
                    "status": "error",
                    "error_type": error_category.value,
                    "error_message": str(e),
                }
            )
            error_count += 1

    processing_duration_ms = int((time.time() - start_time) * 1000)

    logger.info(
        "Property analysis completed: success=%d, errors=%d, duration=%dms",
        success_count,
        error_count,
        processing_duration_ms,
    )

    # EMF メトリクス
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="processing")
    metrics.set_dimension("UseCase", "real-estate-portfolio")
    metrics.set_dimension("Stage", "property-analysis")
    metrics.put_metric("ProcessingDuration", float(processing_duration_ms), "Milliseconds")
    metrics.put_metric("SuccessCount", float(success_count), "Count")
    metrics.put_metric("ErrorCount", float(error_count), "Count")
    metrics.flush()

    return {
        "results": results,
        "success_count": success_count,
        "error_count": error_count,
        "processing_duration_ms": processing_duration_ms,
    }
