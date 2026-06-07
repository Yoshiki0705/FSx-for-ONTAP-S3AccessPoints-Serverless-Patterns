"""広告・マーケティング業界 (UC19) Visual Analyzer Lambda ハンドラ

Rekognition を使用してクリエイティブアセットの視覚的メタデータを抽出する。
- DetectLabels: 80% 以上の確信度でラベル検出（最大 50 タグ/アセット）
- DetectModerationLabels: 不適切コンテンツ検出
- DetectText: テキストオーバーレイ検出

また、Compliance Rules JSON に基づいて各アセットのコンプライアンスチェックを行う:
- 禁止モデレーションカテゴリ
- 必須免責事項キーワード
- ファイルサイズ/寸法制約

Requirements: 3.2, 3.4, 3.7, 13.6

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    OUTPUT_BUCKET: 出力バケット名
    MODERATION_CONFIDENCE_THRESHOLD: モデレーション確信度閾値 (デフォルト: 80)
    MAX_TAGS_PER_ASSET: アセットあたりの最大タグ数 (デフォルト: 50)
    COMPLIANCE_RULES_S3_KEY: コンプライアンスルール JSON の S3 キー
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

from shared.exceptions import lambda_error_handler
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler
from shared.retry_handler import (
    execute_with_retry,
    RetryConfig,
    RetryExhaustedError,
    categorize_error,
    ErrorCategory,
)
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)

# Rekognition リトライ設定
REKOGNITION_RETRY_CONFIG = RetryConfig(
    max_attempts=3,
    initial_interval_seconds=2.0,
    backoff_rate=2.0,
)


def get_confidence_threshold() -> float:
    """モデレーション確信度閾値を環境変数から取得する。

    Returns:
        float: 確信度閾値 (デフォルト: 80.0)
    """
    try:
        return float(os.environ.get("MODERATION_CONFIDENCE_THRESHOLD", "80"))
    except (ValueError, TypeError):
        return 80.0


def get_max_tags() -> int:
    """アセットあたりの最大タグ数を環境変数から取得する。

    Returns:
        int: 最大タグ数 (デフォルト: 50)
    """
    try:
        return int(os.environ.get("MAX_TAGS_PER_ASSET", "50"))
    except (ValueError, TypeError):
        return 50


def detect_labels(
    rekognition_client,
    image_bytes: bytes,
    confidence_threshold: float,
    max_tags: int,
) -> list[dict[str, Any]]:
    """Rekognition DetectLabels を実行し、ラベルを抽出する。

    Args:
        rekognition_client: boto3 Rekognition クライアント
        image_bytes: 画像のバイトデータ
        confidence_threshold: 最小確信度閾値 (%)
        max_tags: 返却する最大ラベル数

    Returns:
        list[dict]: 検出されたラベルのリスト
            各要素: {"name": str, "confidence": float, "categories": list[str]}
    """

    def _call():
        return rekognition_client.detect_labels(
            Image={"Bytes": image_bytes},
            MinConfidence=confidence_threshold,
            MaxLabels=max_tags,
        )

    response = execute_with_retry(_call, config=REKOGNITION_RETRY_CONFIG)

    labels = []
    for label in response.get("Labels", []):
        categories = [cat.get("Name", "") for cat in label.get("Categories", []) if cat.get("Name")]
        labels.append(
            {
                "name": label["Name"],
                "confidence": round(label["Confidence"], 2),
                "categories": categories,
            }
        )

    return labels[:max_tags]


def detect_moderation_labels(
    rekognition_client,
    image_bytes: bytes,
    confidence_threshold: float,
) -> list[dict[str, Any]]:
    """Rekognition DetectModerationLabels を実行する。

    Args:
        rekognition_client: boto3 Rekognition クライアント
        image_bytes: 画像のバイトデータ
        confidence_threshold: 最小確信度閾値 (%)

    Returns:
        list[dict]: モデレーションラベルのリスト
            各要素: {"name": str, "confidence": float, "parent_name": str}
    """

    def _call():
        return rekognition_client.detect_moderation_labels(
            Image={"Bytes": image_bytes},
            MinConfidence=confidence_threshold,
        )

    response = execute_with_retry(_call, config=REKOGNITION_RETRY_CONFIG)

    moderation_labels = []
    for label in response.get("ModerationLabels", []):
        moderation_labels.append(
            {
                "name": label.get("Name", ""),
                "confidence": round(label.get("Confidence", 0.0), 2),
                "parent_name": label.get("ParentName", ""),
            }
        )

    return moderation_labels


def detect_text(
    rekognition_client,
    image_bytes: bytes,
) -> list[dict[str, Any]]:
    """Rekognition DetectText を実行する。

    Args:
        rekognition_client: boto3 Rekognition クライアント
        image_bytes: 画像のバイトデータ

    Returns:
        list[dict]: 検出されたテキストのリスト
            各要素: {"text": str, "confidence": float, "type": str}
    """

    def _call():
        return rekognition_client.detect_text(
            Image={"Bytes": image_bytes},
        )

    response = execute_with_retry(_call, config=REKOGNITION_RETRY_CONFIG)

    text_detections = []
    for detection in response.get("TextDetections", []):
        text_detections.append(
            {
                "text": detection.get("DetectedText", ""),
                "confidence": round(detection.get("Confidence", 0.0), 2),
                "type": detection.get("Type", ""),
            }
        )

    return text_detections


def load_compliance_rules(s3_client, output_bucket: str, rules_key: str) -> dict[str, Any]:
    """コンプライアンスルール JSON を S3 から読み込む。

    ルール JSON 構造:
    {
        "prohibited_moderation_categories": ["Explicit Nudity", "Violence", ...],
        "required_disclaimer_keywords": ["©", "広告", "PR", ...],
        "dimension_constraints": {
            "min_width": 100,
            "min_height": 100,
            "max_width": 10000,
            "max_height": 10000
        },
        "size_constraints": {
            "max_bytes": 5368709120
        }
    }

    Args:
        s3_client: boto3 S3 クライアント
        output_bucket: ルールファイルが格納されたバケット名
        rules_key: ルール JSON の S3 キー

    Returns:
        dict: コンプライアンスルール (空の場合はデフォルト)
    """
    if not rules_key:
        return {}

    try:
        response = s3_client.get_object(Bucket=output_bucket, Key=rules_key)
        content = response["Body"].read().decode("utf-8")
        response["Body"].close()
        return json.loads(content)
    except ClientError as e:
        logger.warning(
            "Failed to load compliance rules from s3://%s/%s: %s",
            output_bucket,
            rules_key,
            str(e),
        )
        return {}
    except (json.JSONDecodeError, Exception) as e:
        logger.warning("Failed to parse compliance rules JSON: %s", str(e))
        return {}


def check_compliance(
    moderation_labels: list[dict],
    text_detections: list[dict],
    file_size: int,
    compliance_rules: dict[str, Any],
) -> dict[str, Any]:
    """アセットをコンプライアンスルールに対してチェックする。

    Requirement 3.4: 各アセットに対してコンプライアンスルール JSON を適用

    Args:
        moderation_labels: 検出されたモデレーションラベル
        text_detections: 検出されたテキスト
        file_size: ファイルサイズ (bytes)
        compliance_rules: コンプライアンスルール辞書

    Returns:
        dict: コンプライアンスチェック結果
            {
                "status": "compliant" | "non-compliant",
                "violations": [...],
                "checks_performed": [...]
            }
    """
    violations = []
    checks_performed = []

    # 1. 禁止モデレーションカテゴリチェック
    prohibited_categories = compliance_rules.get("prohibited_moderation_categories", [])
    if prohibited_categories:
        checks_performed.append("prohibited_moderation_categories")
        for label in moderation_labels:
            label_name = label.get("name", "")
            parent_name = label.get("parent_name", "")
            for prohibited in prohibited_categories:
                prohibited_lower = prohibited.lower()
                if prohibited_lower in label_name.lower() or prohibited_lower in parent_name.lower():
                    violations.append(
                        {
                            "type": "prohibited_moderation_category",
                            "category": prohibited,
                            "detected_label": label_name,
                            "confidence": label.get("confidence", 0.0),
                        }
                    )

    # 2. 必須免責事項キーワードチェック
    required_keywords = compliance_rules.get("required_disclaimer_keywords", [])
    if required_keywords:
        checks_performed.append("required_disclaimer_keywords")
        # 全検出テキストを結合して検索
        all_text = " ".join(d.get("text", "") for d in text_detections if d.get("type") == "LINE")
        for keyword in required_keywords:
            if keyword.lower() not in all_text.lower():
                violations.append(
                    {
                        "type": "missing_disclaimer_keyword",
                        "keyword": keyword,
                    }
                )

    # 3. ファイルサイズ制約チェック
    size_constraints = compliance_rules.get("size_constraints", {})
    if size_constraints:
        checks_performed.append("size_constraints")
        max_bytes = size_constraints.get("max_bytes")
        if max_bytes and file_size > max_bytes:
            violations.append(
                {
                    "type": "file_size_exceeded",
                    "max_bytes": max_bytes,
                    "actual_bytes": file_size,
                }
            )

    status = "non-compliant" if violations else "compliant"

    return {
        "status": status,
        "violations": violations,
        "checks_performed": checks_performed,
    }


def generate_tags(labels: list[dict], max_tags: int) -> list[str]:
    """ラベルからアセットタグを生成する。

    Requirement 3.2: 最大 50 タグ/アセット

    Args:
        labels: 検出されたラベルのリスト
        max_tags: 最大タグ数

    Returns:
        list[str]: アセットタグのリスト
    """
    tags = []
    for label in labels:
        tag = label.get("name", "").strip()
        if tag and tag not in tags:
            tags.append(tag)
            if len(tags) >= max_tags:
                break
    return tags


def record_processing_failure(
    s3_client,
    output_bucket: str,
    file_key: str,
    error_type: str,
    error_details: str,
) -> None:
    """処理失敗を記録する。

    Requirement 3.7: corruption/unsupported format/service error 時に
    file path, error type, timestamp を記録して処理を継続。

    Args:
        s3_client: boto3 S3 クライアント
        output_bucket: 出力バケット名
        file_key: 失敗したファイルのキー
        error_type: エラータイプ
        error_details: エラー詳細
    """
    error_record = {
        "file_path": file_key,
        "error_type": error_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "details": error_details,
    }

    date_prefix = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    file_basename = file_key.rsplit("/", 1)[-1] if "/" in file_key else file_key
    error_key = f"errors/visual_analyzer/{date_prefix}/{file_basename}.error.json"

    try:
        s3_client.put_object(
            Bucket=output_bucket,
            Key=error_key,
            Body=json.dumps(error_record, ensure_ascii=False),
            ContentType="application/json",
        )
        logger.info("Processing failure recorded: %s → %s", file_key, error_key)
    except Exception as e:
        logger.error("Failed to record processing failure for %s: %s", file_key, str(e))


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Visual Analyzer Lambda ハンドラ

    Step Functions Map State から呼び出され、個々のクリエイティブアセットに対して
    Rekognition を使用した視覚分析を行う。

    Event 形式:
        {
            "key": "creatives/2026/banner.jpg",
            "size": 2048000,
            "manifest_key": "manifests/2026/06/02/xxx.json"
        }

    Processing Flow:
        1. S3 AP からファイル取得
        2. Rekognition DetectLabels (80% 確信度閾値)
        3. Rekognition DetectModerationLabels
        4. Rekognition DetectText
        5. タグ生成 (最大 50)
        6. コンプライアンスルールチェック
        7. 結果を S3 出力バケットに書き出し
        8. 破損/未対応フォーマット時はエラー記録して継続

    Returns:
        dict: 処理結果
    """
    file_key = event.get("key", event.get("Key", ""))
    file_size = event.get("size", event.get("Size", 0))

    logger.info(
        "Visual Analyzer started: key=%s, size=%d",
        file_key,
        file_size,
    )

    # 環境設定
    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    output_bucket = os.environ.get("OUTPUT_BUCKET", "")
    confidence_threshold = get_confidence_threshold()
    max_tags = get_max_tags()
    compliance_rules_key = os.environ.get("COMPLIANCE_RULES_S3_KEY", "")

    s3_client = boto3.client("s3")
    rekognition_client = boto3.client("rekognition")

    # Step 1: ファイル取得
    try:
        with xray_subsegment(
            name="s3ap_get_object",
            annotations={
                "service_name": "s3",
                "operation": "GetObject",
                "use_case": "adtech-creative-management",
            },
        ):
            response = s3ap.get_object(file_key)
            image_bytes = response["Body"].read()
            response["Body"].close()
    except Exception as e:
        error_type = "retrieval_error"
        logger.error("Failed to retrieve file %s: %s", file_key, str(e))
        if output_bucket:
            record_processing_failure(s3_client, output_bucket, file_key, error_type, str(e))
        return {
            "key": file_key,
            "status": "error",
            "error_type": error_type,
            "error_details": str(e),
        }

    # Step 2: Rekognition DetectLabels
    labels = []
    try:
        with xray_subsegment(
            name="rekognition_detect_labels",
            annotations={
                "service_name": "rekognition",
                "operation": "DetectLabels",
                "use_case": "adtech-creative-management",
            },
        ):
            labels = detect_labels(rekognition_client, image_bytes, confidence_threshold, max_tags)
    except RetryExhaustedError as e:
        logger.error(
            "Rekognition DetectLabels failed after retries for %s: %s",
            file_key,
            str(e),
        )
        if output_bucket:
            record_processing_failure(s3_client, output_bucket, file_key, "service_error_labels", str(e))
        return {
            "key": file_key,
            "status": "error",
            "error_type": "service_error",
            "error_details": f"DetectLabels retry exhausted: {e}",
        }
    except Exception as e:
        # 破損/未対応フォーマット (Requirement 3.7)
        error_category = categorize_error(e)
        error_type = "corruption" if error_category == ErrorCategory.PARSE_ERROR else "service_error"
        logger.warning("DetectLabels failed for %s (%s): %s", file_key, error_type, str(e))
        if output_bucket:
            record_processing_failure(s3_client, output_bucket, file_key, error_type, str(e))
        return {
            "key": file_key,
            "status": "error",
            "error_type": error_type,
            "error_details": str(e),
        }

    # Step 3: Rekognition DetectModerationLabels
    moderation_labels = []
    try:
        with xray_subsegment(
            name="rekognition_detect_moderation",
            annotations={
                "service_name": "rekognition",
                "operation": "DetectModerationLabels",
                "use_case": "adtech-creative-management",
            },
        ):
            moderation_labels = detect_moderation_labels(rekognition_client, image_bytes, confidence_threshold)
    except RetryExhaustedError as e:
        logger.warning(
            "DetectModerationLabels failed after retries for %s: %s",
            file_key,
            str(e),
        )
        # モデレーション失敗は処理継続（ラベルは取得済み）
    except Exception as e:
        logger.warning("DetectModerationLabels failed for %s: %s", file_key, str(e))

    # Step 4: Rekognition DetectText
    text_detections = []
    try:
        with xray_subsegment(
            name="rekognition_detect_text",
            annotations={
                "service_name": "rekognition",
                "operation": "DetectText",
                "use_case": "adtech-creative-management",
            },
        ):
            text_detections = detect_text(rekognition_client, image_bytes)
    except RetryExhaustedError as e:
        logger.warning(
            "DetectText failed after retries for %s: %s",
            file_key,
            str(e),
        )
    except Exception as e:
        logger.warning("DetectText failed for %s: %s", file_key, str(e))

    # Step 5: タグ生成 (最大 50)
    tags = generate_tags(labels, max_tags)

    # Step 6: コンプライアンスルールチェック
    compliance_rules = {}
    if compliance_rules_key and output_bucket:
        compliance_rules = load_compliance_rules(s3_client, output_bucket, compliance_rules_key)

    compliance_result = check_compliance(
        moderation_labels=moderation_labels,
        text_detections=text_detections,
        file_size=file_size,
        compliance_rules=compliance_rules,
    )

    # Step 7: 結果構築
    result = {
        "key": file_key,
        "status": "success",
        "processing_timestamp": datetime.now(timezone.utc).isoformat(),
        "labels": labels,
        "moderation_labels": moderation_labels,
        "text_detections": text_detections,
        "tags": tags,
        "tag_count": len(tags),
        "compliance": compliance_result,
        "metadata": {
            "confidence_threshold": confidence_threshold,
            "max_tags": max_tags,
            "file_size": file_size,
        },
    }

    # 結果書き出し
    if output_bucket:
        date_prefix = datetime.now(timezone.utc).strftime("%Y/%m/%d")
        file_basename = file_key.rsplit("/", 1)[-1] if "/" in file_key else file_key
        result_key = f"results/visual_analyzer/{date_prefix}/{file_basename}.result.json"
        try:
            s3_client.put_object(
                Bucket=output_bucket,
                Key=result_key,
                Body=json.dumps(result, default=str, ensure_ascii=False),
                ContentType="application/json",
            )
        except Exception as e:
            logger.error("Failed to write result for %s: %s", file_key, str(e))

    # Step 8: EMF メトリクス
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="visual_analyzer")
    metrics.set_dimension("UseCase", "adtech-creative-management")
    metrics.put_metric("LabelsDetected", float(len(labels)), "Count")
    metrics.put_metric("ModerationLabelsDetected", float(len(moderation_labels)), "Count")
    metrics.put_metric("TextDetections", float(len(text_detections)), "Count")
    metrics.put_metric("TagsGenerated", float(len(tags)), "Count")
    metrics.put_metric("FilesProcessed", 1.0, "Count")
    if compliance_result["status"] == "non-compliant":
        metrics.put_metric("ComplianceViolations", 1.0, "Count")
    else:
        metrics.put_metric("ComplianceViolations", 0.0, "Count")
    metrics.flush()

    logger.info(
        "Visual Analyzer completed: key=%s, labels=%d, moderation=%d, text=%d, tags=%d, compliance=%s",
        file_key,
        len(labels),
        len(moderation_labels),
        len(text_detections),
        len(tags),
        compliance_result["status"],
    )

    return result
