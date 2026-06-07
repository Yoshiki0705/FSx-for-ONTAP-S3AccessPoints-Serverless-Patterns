"""運輸・鉄道業界 (UC22) Deterioration Detector Lambda ハンドラ

点検画像に対して劣化指標（ひび割れ、さび、変位）を検出し、
重大度を4段階（critical/major/minor/observation）に分類する。

安全重要インフラ設計 (Requirement 6.5):
    - 安全重要カテゴリ（橋梁、信号、レール接合部）:
      Rekognition 信頼度閾値 60%
    - 標準インフラ: Rekognition 信頼度閾値 80%
    - 90% 未満の検出はすべて human_review_required: true

低解像度画像対応 (Requirement 6.6):
    - 解像度 < 1024×768: "requires-reinspection" マーク
    - 品質メトリクス: 実解像度、ファイルサイズ、必要最低解像度

Confidence Thresholds:
    - STANDARD_CONFIDENCE_THRESHOLD (default: 80)
    - SAFETY_CRITICAL_CONFIDENCE_THRESHOLD (default: 60)
    - HUMAN_REVIEW_THRESHOLD (default: 90)

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    BEDROCK_MODEL_ID: Bedrock モデル ID
    STANDARD_CONFIDENCE_THRESHOLD: 標準信頼度閾値 (default: 80)
    SAFETY_CRITICAL_CONFIDENCE_THRESHOLD: 安全重要信頼度閾値 (default: 60)
    HUMAN_REVIEW_THRESHOLD: 人間レビュー閾値 (default: 90)
    MIN_IMAGE_WIDTH: 最低画像幅 (default: 1024)
    MIN_IMAGE_HEIGHT: 最低画像高さ (default: 768)
    SAFETY_CRITICAL_CATEGORIES: 安全重要カテゴリ (default: "bridges,signaling,rail-joints")
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

# 劣化指標タイプ
DETERIORATION_TYPES: list[str] = [
    "crack",
    "rust",
    "displacement",
    "corrosion",
    "deformation",
    "wear",
    "spalling",
    "erosion",
]

# 重大度レベル
SEVERITY_LEVELS: list[str] = ["critical", "major", "minor", "observation"]

# デフォルト閾値
DEFAULT_STANDARD_THRESHOLD: int = 80
DEFAULT_SAFETY_CRITICAL_THRESHOLD: int = 60
DEFAULT_HUMAN_REVIEW_THRESHOLD: int = 90
DEFAULT_MIN_WIDTH: int = 1024
DEFAULT_MIN_HEIGHT: int = 768

# デフォルト安全重要カテゴリ
DEFAULT_SAFETY_CRITICAL_CATEGORIES: str = "bridges,signaling,rail-joints"


def parse_safety_critical_categories(categories_str: str) -> frozenset[str]:
    """安全重要カテゴリ文字列をパースする。

    Args:
        categories_str: カンマ区切りのカテゴリ文字列

    Returns:
        frozenset[str]: 安全重要カテゴリ集合
    """
    return frozenset(c.strip().lower() for c in categories_str.split(",") if c.strip())


def is_safety_critical(object_key: str, categories: frozenset[str]) -> bool:
    """オブジェクトキーが安全重要カテゴリに属するか判定する。

    パスに安全重要カテゴリ名が含まれるかをチェック。
    例: "inspections/bridges/route-1/2026-01-15/img_001.jpg" → True

    Args:
        object_key: S3 オブジェクトキー
        categories: 安全重要カテゴリ集合

    Returns:
        bool: 安全重要カテゴリに属する場合 True
    """
    key_lower = object_key.lower()
    return any(cat in key_lower for cat in categories)


def check_image_resolution(image_metadata: dict, min_width: int, min_height: int) -> dict:
    """画像解像度が最低要件を満たしているか検証する。

    Requirement 6.6: 解像度 < 1024×768 は "requires-reinspection"

    Args:
        image_metadata: 画像メタデータ (width, height, file_size)
        min_width: 最低画像幅
        min_height: 最低画像高さ

    Returns:
        dict: resolution_check 結果
    """
    width = image_metadata.get("width", 0)
    height = image_metadata.get("height", 0)
    file_size = image_metadata.get("file_size", 0)

    is_adequate = width >= min_width and height >= min_height

    result = {
        "adequate": is_adequate,
        "actual_width": width,
        "actual_height": height,
        "file_size_bytes": file_size,
        "min_required_width": min_width,
        "min_required_height": min_height,
    }

    if not is_adequate:
        result["status"] = "requires-reinspection"
        result["reason"] = f"Image resolution {width}x{height} is below minimum required {min_width}x{min_height}"

    return result


def detect_deterioration_with_rekognition(
    rekognition_client,
    s3_bucket: str,
    s3_key: str,
    confidence_threshold: float,
) -> dict:
    """Rekognition で劣化指標を検出する。

    Args:
        rekognition_client: boto3 rekognition client
        s3_bucket: S3 バケット/AP エイリアス
        s3_key: オブジェクトキー
        confidence_threshold: 信頼度閾値 (0-100)

    Returns:
        dict: detected_labels, image_properties
    """

    @retry_with_backoff(config=RetryConfig(max_attempts=3))
    def _detect_labels():
        return rekognition_client.detect_labels(
            Image={"S3Object": {"Bucket": s3_bucket, "Name": s3_key}},
            MaxLabels=100,
            MinConfidence=confidence_threshold,
            Features=["GENERAL_LABELS", "IMAGE_PROPERTIES"],
        )

    response = _detect_labels()
    labels = response.get("Labels", [])

    # 画像プロパティから解像度を取得
    image_properties = response.get("ImageProperties", {})
    quality = image_properties.get("Quality", {})

    # 劣化関連ラベルをフィルタ
    deterioration_labels = []
    all_labels = []

    for label in labels:
        label_name = label.get("Name", "")
        confidence = label.get("Confidence", 0)

        all_labels.append(
            {
                "name": label_name,
                "confidence": round(confidence, 2),
            }
        )

        # 劣化関連キーワードのマッチング
        label_lower = label_name.lower()
        for det_type in DETERIORATION_TYPES:
            if det_type in label_lower or label_lower in det_type:
                deterioration_labels.append(
                    {
                        "name": label_name,
                        "confidence": round(confidence, 2),
                        "deterioration_type": det_type,
                    }
                )
                break

    return {
        "deterioration_labels": deterioration_labels,
        "all_labels": all_labels,
        "total_labels_detected": len(labels),
        "image_quality": {
            "brightness": quality.get("Brightness", 0),
            "sharpness": quality.get("Sharpness", 0),
            "contrast": quality.get("Contrast", 0),
        },
    }


def classify_severity_with_bedrock(
    bedrock_client,
    model_id: str,
    detection_data: dict,
    is_safety_critical_asset: bool,
) -> list[dict]:
    """Bedrock で劣化の重大度を分類する。

    Requirement 6.2: severity = critical/major/minor/observation

    Args:
        bedrock_client: boto3 bedrock-runtime client
        model_id: Bedrock モデル ID
        detection_data: Rekognition 検出結果
        is_safety_critical_asset: 安全重要インフラかどうか

    Returns:
        list[dict]: 重大度分類結果
    """
    safety_context = (
        "This is SAFETY-CRITICAL railway infrastructure (bridges, signaling, or rail joints). "
        "Apply conservative severity classification — err on the side of higher severity."
        if is_safety_critical_asset
        else "This is standard railway infrastructure."
    )

    prompt = (
        "You are a railway infrastructure deterioration assessment expert. "
        f"{safety_context}\n\n"
        "Based on the following defect detections from a railway inspection image, "
        "classify each defect into one of four severity levels:\n"
        "- critical: Immediate safety risk, requires urgent repair\n"
        "- major: Significant deterioration, schedule repair within 30 days\n"
        "- minor: Early-stage deterioration, monitor and plan maintenance\n"
        "- observation: Minimal finding, record for trending\n\n"
        f"Detected labels: {json.dumps(detection_data['deterioration_labels'])}\n"
        f"All labels: {json.dumps(detection_data['all_labels'][:20])}\n\n"
        "Respond in JSON format: "
        '[{"defect_type": "...", "severity": "critical|major|minor|observation", '
        '"confidence": 0.XX, "description": "..."}]'
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

    # Parse severity classifications from response
    classifications = []
    try:
        start_idx = text_content.find("[")
        end_idx = text_content.rfind("]") + 1
        if start_idx >= 0 and end_idx > start_idx:
            parsed = json.loads(text_content[start_idx:end_idx])
            for item in parsed:
                severity = item.get("severity", "observation").lower()
                if severity not in SEVERITY_LEVELS:
                    severity = "observation"
                classifications.append(
                    {
                        "defect_type": item.get("defect_type", "unknown"),
                        "severity": severity,
                        "confidence": round(float(item.get("confidence", 0)), 4),
                        "description": item.get("description", ""),
                    }
                )
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.warning("Failed to parse Bedrock severity response: %s", str(e))

    return classifications


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Transportation Deterioration Detector Lambda

    点検画像の劣化指標を検出し、重大度を分類する。

    Safety-critical design:
        - 安全重要インフラ: 60% 閾値
        - 標準インフラ: 80% 閾値
        - 90% 未満の検出: human_review_required = true
        - 低解像度画像: requires-reinspection マーク

    Input event (single image object from Map state):
        - Key: S3 オブジェクトキー
        - Size: ファイルサイズ
        - LastModified: 最終更新日時
        - category: "inspection_image"

    Returns:
        dict: status, key, severity_classifications, resolution_check, human_review_required
    """
    start_time = time.time()

    s3_access_point = os.environ["S3_ACCESS_POINT"]
    bedrock_model_id = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")

    # 閾値パラメータ
    standard_threshold = int(os.environ.get("STANDARD_CONFIDENCE_THRESHOLD", str(DEFAULT_STANDARD_THRESHOLD)))
    safety_critical_threshold = int(
        os.environ.get(
            "SAFETY_CRITICAL_CONFIDENCE_THRESHOLD",
            str(DEFAULT_SAFETY_CRITICAL_THRESHOLD),
        )
    )
    human_review_threshold = int(os.environ.get("HUMAN_REVIEW_THRESHOLD", str(DEFAULT_HUMAN_REVIEW_THRESHOLD)))
    min_width = int(os.environ.get("MIN_IMAGE_WIDTH", str(DEFAULT_MIN_WIDTH)))
    min_height = int(os.environ.get("MIN_IMAGE_HEIGHT", str(DEFAULT_MIN_HEIGHT)))

    # 安全重要カテゴリ
    safety_categories_str = os.environ.get("SAFETY_CRITICAL_CATEGORIES", DEFAULT_SAFETY_CRITICAL_CATEGORIES)
    safety_categories = parse_safety_critical_categories(safety_categories_str)

    object_key = event.get("Key", "")
    object_size = event.get("Size", 0)
    last_modified = event.get("LastModified", "")

    logger.info(
        "Deterioration detection started: key=%s, size=%d",
        object_key,
        object_size,
    )

    # 安全重要インフラ判定
    is_safety_critical_asset = is_safety_critical(object_key, safety_categories)
    effective_threshold = safety_critical_threshold if is_safety_critical_asset else standard_threshold

    logger.info(
        "Safety classification: key=%s, is_safety_critical=%s, threshold=%d%%",
        object_key,
        is_safety_critical_asset,
        effective_threshold,
    )

    # 画像解像度メタデータ取得 (S3 HEAD からメタデータ取得をシミュレート)
    # 実運用では Rekognition の ImageProperties や Pillow で取得
    image_metadata = event.get("image_metadata", {})
    if not image_metadata:
        # デフォルト: メタデータ未提供の場合はファイルサイズから推定
        image_metadata = {
            "width": event.get("width", 0),
            "height": event.get("height", 0),
            "file_size": object_size,
        }

    # 解像度チェック (Requirement 6.6)
    resolution_check = check_image_resolution(image_metadata, min_width, min_height)

    if not resolution_check["adequate"]:
        logger.warning(
            "Low resolution image: key=%s, %dx%d < %dx%d — marking requires-reinspection",
            object_key,
            image_metadata.get("width", 0),
            image_metadata.get("height", 0),
            min_width,
            min_height,
        )
        processing_duration_ms = int((time.time() - start_time) * 1000)
        return {
            "status": "requires-reinspection",
            "key": object_key,
            "size": object_size,
            "last_modified": last_modified,
            "is_safety_critical": is_safety_critical_asset,
            "resolution_check": resolution_check,
            "quality_metrics": {
                "actual_resolution": f"{image_metadata.get('width', 0)}x{image_metadata.get('height', 0)}",
                "file_size_bytes": object_size,
                "min_required_resolution": f"{min_width}x{min_height}",
            },
            "human_review_required": True,
            "reason": "Image resolution below minimum threshold for reliable analysis",
            "processing_duration_ms": processing_duration_ms,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }

    # Rekognition による劣化検出
    rekognition_client = boto3.client("rekognition")
    detection_data = detect_deterioration_with_rekognition(
        rekognition_client,
        s3_access_point,
        object_key,
        float(effective_threshold),
    )

    # Bedrock による重大度分類
    severity_classifications: list[dict] = []
    if detection_data["deterioration_labels"]:
        bedrock_client = boto3.client("bedrock-runtime")
        severity_classifications = classify_severity_with_bedrock(
            bedrock_client,
            bedrock_model_id,
            detection_data,
            is_safety_critical_asset,
        )

    # Human review フラグ (Requirement 6.5)
    # 90% 未満の検出はすべて human_review_required
    human_review_required = False
    flagged_for_review: list[dict] = []

    for label in detection_data["deterioration_labels"]:
        confidence = label.get("confidence", 0)
        if confidence < human_review_threshold:
            human_review_required = True
            flagged_for_review.append(
                {
                    "label": label.get("name"),
                    "confidence": confidence,
                    "reason": f"Confidence {confidence}% < {human_review_threshold}% threshold",
                }
            )

    # 重大度サマリ
    severity_counts = {"critical": 0, "major": 0, "minor": 0, "observation": 0}
    for classification in severity_classifications:
        severity = classification.get("severity", "observation")
        if severity in severity_counts:
            severity_counts[severity] += 1

    processing_duration_ms = int((time.time() - start_time) * 1000)

    result = {
        "status": "success",
        "key": object_key,
        "size": object_size,
        "last_modified": last_modified,
        "is_safety_critical": is_safety_critical_asset,
        "effective_threshold": effective_threshold,
        "resolution_check": resolution_check,
        "detection_summary": {
            "total_labels": detection_data["total_labels_detected"],
            "deterioration_labels_count": len(detection_data["deterioration_labels"]),
            "deterioration_labels": detection_data["deterioration_labels"],
        },
        "severity_classifications": severity_classifications,
        "severity_counts": severity_counts,
        "human_review_required": human_review_required,
        "flagged_for_review": flagged_for_review,
        "image_quality": detection_data["image_quality"],
        "processing_duration_ms": processing_duration_ms,
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }

    logger.info(
        "Deterioration detection completed: key=%s, safety_critical=%s, "
        "deterioration_count=%d, severity=%s, human_review=%s",
        object_key,
        is_safety_critical_asset,
        len(detection_data["deterioration_labels"]),
        severity_counts,
        human_review_required,
    )

    return result
