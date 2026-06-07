"""化学・素材 (UC28) SDS Extractor Lambda ハンドラ

SDS 文書から危険分類、取扱注意、緊急時手順を抽出する。

Requirement 12.2:
    - Textract + Bedrock で構造化抽出
    - GHS 必須セクションの存在チェック

GHS 必須セクション:
    identification, hazard_classification, composition, first_aid,
    fire_fighting, accidental_release, handling_storage, exposure_controls

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN
    TEXTRACT_REGION: Textract リージョン (default: us-east-1)
    BEDROCK_MODEL_ID: Bedrock モデル ID
    SDS_VALIDITY_DAYS: SDS 有効期間日数 (default: 365)
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler
from shared.retry_handler import RetryConfig, categorize_error, retry_with_backoff

logger = logging.getLogger(__name__)

# GHS 必須セクション (Requirement 12.4)
GHS_MANDATORY_SECTIONS: list[str] = [
    "identification",
    "hazard_classification",
    "composition",
    "first_aid",
    "fire_fighting",
    "accidental_release",
    "handling_storage",
    "exposure_controls",
]

# GHS セクション検出キーワード（日本語/英語）
GHS_SECTION_KEYWORDS: dict[str, list[str]] = {
    "identification": ["化学品の名称", "identification", "製品名", "product name"],
    "hazard_classification": ["危険有害性の要約", "hazard", "ghs分類", "ghs classification"],
    "composition": ["組成", "composition", "成分", "ingredients"],
    "first_aid": ["応急措置", "first aid", "first-aid"],
    "fire_fighting": ["火災時の措置", "fire fighting", "fire-fighting", "消火"],
    "accidental_release": ["漏出時の措置", "accidental release", "漏洩"],
    "handling_storage": ["取扱い及び保管", "handling", "storage", "保管"],
    "exposure_controls": ["ばく露防止", "exposure control", "保護具", "protective"],
}


def extract_text_textract(
    s3ap_alias: str,
    object_key: str,
    textract_client=None,
) -> str:
    """Textract で SDS からテキストを抽出する。"""
    if textract_client is None:
        textract_region = os.environ.get("TEXTRACT_REGION", "us-east-1")
        textract_client = boto3.client("textract", region_name=textract_region)

    @retry_with_backoff(config=RetryConfig(max_attempts=3))
    def _call_textract():
        return textract_client.detect_document_text(
            Document={"S3Object": {"Bucket": s3ap_alias, "Name": object_key}},
        )

    response = _call_textract()
    blocks = response.get("Blocks", [])

    lines: list[str] = []
    for block in blocks:
        if block.get("BlockType") == "LINE":
            text = block.get("Text", "")
            if text:
                lines.append(text)

    return "\n".join(lines)


def check_ghs_sections(text: str) -> dict[str, bool]:
    """GHS 必須セクションの存在をチェックする。

    Args:
        text: SDS テキスト

    Returns:
        dict: セクション名 → 存在フラグ
    """
    text_lower = text.lower()
    results: dict[str, bool] = {}

    for section in GHS_MANDATORY_SECTIONS:
        keywords = GHS_SECTION_KEYWORDS.get(section, [])
        found = any(kw.lower() in text_lower for kw in keywords)
        results[section] = found

    return results


def get_missing_ghs_sections(ghs_check: dict[str, bool]) -> list[str]:
    """不足している GHS セクションのリストを返す。

    Args:
        ghs_check: check_ghs_sections の結果

    Returns:
        list[str]: 不足セクション名のリスト
    """
    return [section for section, found in ghs_check.items() if not found]


def extract_hazard_info_bedrock(
    text: str,
    substance_id: str | None,
    bedrock_client=None,
    model_id: str | None = None,
) -> dict:
    """Bedrock で危険分類・取扱注意・緊急時手順を抽出する。

    Args:
        text: SDS テキスト
        substance_id: 物質 ID
        bedrock_client: Bedrock クライアント (テスト用)
        model_id: Bedrock モデル ID

    Returns:
        dict: hazard_classification, handling_precautions, emergency_procedures
    """
    if bedrock_client is None:
        bedrock_client = boto3.client("bedrock-runtime")

    if model_id is None:
        model_id = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")

    # テキストを制限
    truncated_text = text[:4000]

    prompt = (
        f"以下の SDS (安全データシート) テキストから構造化情報を抽出してください。\n"
        f"物質ID: {substance_id or 'unknown'}\n\n"
        f"テキスト:\n{truncated_text}\n\n"
        f"以下の JSON 形式で回答してください:\n"
        f'{{"hazard_classification": "GHS分類", '
        f'"signal_word": "危険/警告/なし", '
        f'"hazard_statements": ["危険有害性情報"], '
        f'"handling_precautions": ["取扱注意事項"], '
        f'"emergency_procedures": ["緊急時手順"]}}'
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
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": prompt}],
                }
            ),
        )

    try:
        response = _call_bedrock()
        response_body = json.loads(response["body"].read())
        content_text = response_body.get("content", [{}])[0].get("text", "")
        return _parse_hazard_response(content_text)
    except Exception as e:
        logger.warning("Bedrock hazard extraction failed: %s", str(e))
        return {
            "hazard_classification": "",
            "signal_word": "",
            "hazard_statements": [],
            "handling_precautions": [],
            "emergency_procedures": [],
        }


def _parse_hazard_response(text: str) -> dict:
    """Bedrock レスポンスからJSON を抽出する。"""
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    return {
        "hazard_classification": "",
        "signal_word": "",
        "hazard_statements": [],
        "handling_precautions": [],
        "emergency_procedures": [],
    }


def check_sds_expiry(revision_date: str | None, validity_days: int = 365) -> dict:
    """SDS の有効期限をチェックする。

    Args:
        revision_date: 改訂日 (YYYY-MM-DD)
        validity_days: 有効期間日数

    Returns:
        dict: is_expired, days_since_revision, priority
    """
    if not revision_date:
        return {"is_expired": False, "days_since_revision": None, "priority": None}

    try:
        rev_date = datetime.strptime(revision_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        days_since = (now - rev_date).days

        is_expired = days_since > validity_days
        priority = "critical" if is_expired else None

        return {
            "is_expired": is_expired,
            "days_since_revision": days_since,
            "priority": priority,
        }
    except ValueError:
        return {"is_expired": False, "days_since_revision": None, "priority": None}


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """SDS Extractor Lambda

    Input event:
        - objects: SDS オブジェクトリスト

    Returns:
        dict: results, success_count, error_count
    """
    start_time = time.time()

    s3ap_alias = os.environ.get("S3_ACCESS_POINT", "")
    validity_days = int(os.environ.get("SDS_VALIDITY_DAYS", "365"))

    objects = event.get("objects", [])
    logger.info("SDS extraction started: %d documents", len(objects))

    results: list[dict] = []
    success_count = 0
    error_count = 0

    for obj in objects:
        key = obj.get("Key", "")
        substance_id = obj.get("substance_id")
        revision_date = obj.get("revision_date")

        try:
            text = extract_text_textract(s3ap_alias, key)

            # GHS セクションチェック
            ghs_check = check_ghs_sections(text)
            missing_sections = get_missing_ghs_sections(ghs_check)

            # Bedrock で危険情報抽出
            hazard_info = extract_hazard_info_bedrock(text, substance_id)

            # 有効期限チェック
            expiry_info = check_sds_expiry(revision_date, validity_days)

            results.append(
                {
                    "key": key,
                    "substance_id": substance_id,
                    "revision_date": revision_date,
                    "status": "success",
                    "ghs_sections": ghs_check,
                    "missing_ghs_sections": missing_sections,
                    "hazard_info": hazard_info,
                    "expiry": expiry_info,
                }
            )
            success_count += 1

        except Exception as e:
            error_category = categorize_error(e)
            logger.warning(
                "SDS extraction failed for %s: %s [%s]",
                key,
                str(e),
                error_category.value,
            )
            results.append(
                {
                    "key": key,
                    "substance_id": substance_id,
                    "revision_date": revision_date,
                    "status": "error",
                    "error_type": error_category.value,
                    "error_message": str(e),
                }
            )
            error_count += 1

    processing_duration_ms = int((time.time() - start_time) * 1000)

    logger.info(
        "SDS extraction completed: success=%d, errors=%d",
        success_count,
        error_count,
    )

    # EMF メトリクス
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="processing")
    metrics.set_dimension("UseCase", "chemical-sds-management")
    metrics.set_dimension("Stage", "sds-extraction")
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
