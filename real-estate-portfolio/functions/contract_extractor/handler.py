"""不動産 (UC26) Contract Extractor Lambda ハンドラ

賃貸契約書から主要条件を抽出する。

抽出対象 (Requirement 10.3):
    - 賃料 (rent_amount)
    - 契約期間 (lease_period)
    - 特約条件 (special_conditions)
    - テナント情報 (tenant_info)

AI/ML サービス:
    - Amazon Textract: 文書テキスト抽出
    - Amazon Comprehend: エンティティ認識

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
    TEXTRACT_REGION: Textract リージョン (default: us-east-1)
"""

from __future__ import annotations

import logging
import os
import re
import time

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler
from shared.retry_handler import RetryConfig, categorize_error, retry_with_backoff

logger = logging.getLogger(__name__)

# 契約条件抽出パターン
RENT_PATTERNS: list[re.Pattern] = [
    re.compile(r"(?:賃料|家賃|月額)[\s:：]*([0-9,]+)\s*(?:円|万円)"),
    re.compile(r"(?:rent|monthly)\s*[:：]?\s*\$?([0-9,]+)"),
]

LEASE_PERIOD_PATTERNS: list[re.Pattern] = [
    re.compile(r"(?:契約期間|賃貸期間)[\s:：]*(\d+)\s*(?:年|ヶ月|か月)"),
    re.compile(r"(?:lease\s*(?:term|period))[\s:：]*(\d+)\s*(?:year|month)", re.IGNORECASE),
]


def extract_text_textract(
    s3ap_alias: str,
    object_key: str,
    textract_client=None,
) -> str:
    """Textract で契約書からテキストを抽出する。

    Args:
        s3ap_alias: S3 AP エイリアス
        object_key: 文書オブジェクトキー
        textract_client: Textract クライアント (テスト用)

    Returns:
        str: 抽出されたテキスト
    """
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


def extract_entities_comprehend(
    text: str,
    comprehend_client=None,
) -> list[dict]:
    """Comprehend でエンティティを抽出する。

    Args:
        text: 入力テキスト
        comprehend_client: Comprehend クライアント (テスト用)

    Returns:
        list[dict]: 検出されたエンティティ
    """
    if not text:
        return []

    if comprehend_client is None:
        comprehend_client = boto3.client("comprehend")

    # Comprehend の最大テキスト長
    max_length = 5000
    truncated_text = text[:max_length]

    @retry_with_backoff(config=RetryConfig(max_attempts=3))
    def _call_comprehend():
        return comprehend_client.detect_entities(
            Text=truncated_text,
            LanguageCode="ja",
        )

    response = _call_comprehend()
    entities = response.get("Entities", [])

    return [
        {
            "text": e.get("Text", ""),
            "type": e.get("Type", ""),
            "score": e.get("Score", 0.0),
        }
        for e in entities
        if e.get("Score", 0.0) >= 0.7
    ]


def extract_lease_terms(text: str, entities: list[dict]) -> dict:
    """テキストとエンティティから契約条件を抽出する。

    Args:
        text: Textract 抽出テキスト
        entities: Comprehend エンティティ

    Returns:
        dict: rent_amount, lease_period, special_conditions, tenant_info
    """
    result = {
        "rent_amount": None,
        "rent_currency": "JPY",
        "lease_period_months": None,
        "special_conditions": [],
        "tenant_name": None,
        "tenant_info": {},
    }

    # 賃料抽出
    for pattern in RENT_PATTERNS:
        match = pattern.search(text)
        if match:
            amount_str = match.group(1).replace(",", "")
            try:
                result["rent_amount"] = int(amount_str)
                if "万円" in text[match.start():match.end() + 5]:
                    result["rent_amount"] *= 10000
            except ValueError:
                pass
            break

    # 契約期間抽出
    for pattern in LEASE_PERIOD_PATTERNS:
        match = pattern.search(text)
        if match:
            period = int(match.group(1))
            # 「年」の場合は月に変換
            if "年" in text[match.start():match.end() + 3] or "year" in text[match.start():match.end() + 5].lower():
                period *= 12
            result["lease_period_months"] = period
            break

    # テナント情報 (PERSON エンティティ)
    person_entities = [e for e in entities if e["type"] == "PERSON"]
    if person_entities:
        result["tenant_name"] = person_entities[0]["text"]
        result["tenant_info"] = {
            "name": person_entities[0]["text"],
            "confidence": person_entities[0]["score"],
        }

    # 特約条件抽出（キーワードベース）
    special_keywords = ["特約", "条件", "禁止", "ペット", "改装", "解約", "更新"]
    lines = text.split("\n")
    for line in lines:
        for keyword in special_keywords:
            if keyword in line and len(line) > 5:
                result["special_conditions"].append(line.strip())
                break

    # 特約条件は最大10件に制限
    result["special_conditions"] = result["special_conditions"][:10]

    return result


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Contract Extractor Lambda

    契約書リストに対して条件抽出を行う。

    Input event:
        - objects: 契約書オブジェクトリスト (Discovery Lambda の出力)

    Returns:
        dict: results, success_count, error_count
    """
    start_time = time.time()

    s3ap_alias = os.environ.get("S3_ACCESS_POINT", "")

    objects = event.get("objects", [])
    logger.info("Contract extraction started: %d documents", len(objects))

    results: list[dict] = []
    success_count = 0
    error_count = 0

    for obj in objects:
        key = obj.get("Key", "")
        property_id = obj.get("property_id")

        try:
            # Textract でテキスト抽出
            text = extract_text_textract(s3ap_alias, key)

            # Comprehend でエンティティ抽出
            entities = extract_entities_comprehend(text)

            # 契約条件抽出
            lease_terms = extract_lease_terms(text, entities)

            results.append({
                "key": key,
                "property_id": property_id,
                "status": "success",
                "lease_terms": lease_terms,
                "text_length": len(text),
                "entity_count": len(entities),
            })
            success_count += 1

        except Exception as e:
            error_category = categorize_error(e)
            logger.warning(
                "Contract extraction failed for %s: %s [%s]",
                key,
                str(e),
                error_category.value,
            )
            results.append({
                "key": key,
                "property_id": property_id,
                "status": "error",
                "error_type": error_category.value,
                "error_message": str(e),
            })
            error_count += 1

    processing_duration_ms = int((time.time() - start_time) * 1000)

    logger.info(
        "Contract extraction completed: success=%d, errors=%d, duration=%dms",
        success_count,
        error_count,
        processing_duration_ms,
    )

    # EMF メトリクス
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="processing")
    metrics.set_dimension("UseCase", "real-estate-portfolio")
    metrics.set_dimension("Stage", "contract-extraction")
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
