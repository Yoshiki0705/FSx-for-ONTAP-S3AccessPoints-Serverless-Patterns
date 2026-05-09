"""UC16 Government Archives Entity Extraction Lambda

Amazon Comprehend DetectPiiEntities で PII（個人情報）を検出する。
サポート PII タイプ:
- NAME, SSN, EMAIL, PHONE, ADDRESS, DATE_TIME,
- CREDIT_DEBIT_NUMBER, BANK_ACCOUNT_NUMBER など

Environment Variables:
    OUTPUT_BUCKET: 出力先 S3 バケット
    COMPREHEND_LANGUAGE_CODE: 言語コード (default: "en")
    COMPREHEND_MAX_BYTES: Comprehend API のテキスト最大バイト数 (default: 5000)
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)


# 正規表現ベースの PII フォールバック（Comprehend 未対応言語用）
PII_PATTERNS = {
    "EMAIL": re.compile(r"[\w\.-]+@[\w\.-]+\.\w+"),
    "PHONE_US": re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "PHONE_JP": re.compile(r"\b0\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{4}\b"),
    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "CREDIT_CARD": re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"),
}


def detect_pii_comprehend(comprehend, text: str, language: str = "en") -> list[dict]:
    """Comprehend DetectPiiEntities で PII 検出。"""
    if not text.strip():
        return []
    try:
        response = comprehend.detect_pii_entities(
            Text=text,
            LanguageCode=language,
        )
        return response.get("Entities", [])
    except Exception as e:
        logger.warning("Comprehend DetectPiiEntities failed: %s", e)
        return []


def detect_pii_regex(text: str) -> list[dict]:
    """正規表現ベース PII フォールバック検出。"""
    results = []
    for pii_type, pattern in PII_PATTERNS.items():
        for match in pattern.finditer(text):
            results.append({
                "Type": pii_type,
                "BeginOffset": match.start(),
                "EndOffset": match.end(),
                "Score": 0.80,  # fallback confidence
            })
    return results


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """UC16 Entity Extraction Lambda ハンドラ。

    Input:
        {"document_key": "...", "text_key": "...", "language": "en"}

    Output:
        {"document_key": str, "pii_count": int, "entities": [...]}
    """
    output_bucket = os.environ["OUTPUT_BUCKET"]
    max_bytes = int(os.environ.get("COMPREHEND_MAX_BYTES", "5000"))

    document_key = event.get("document_key", "")
    text_key = event.get("text_key", "")
    language = event.get("language", "en")

    if not text_key:
        raise ValueError("Input must contain 'text_key'")

    # OCR テキストを S3 から取得
    s3_client = boto3.client("s3")
    response = s3_client.get_object(Bucket=output_bucket, Key=text_key)
    text = response["Body"].read().decode("utf-8")

    comprehend = boto3.client("comprehend")

    all_entities = []

    # テキストを Comprehend 制限以内のチャンクに分割して処理
    for i in range(0, len(text), max_bytes):
        chunk = text[i:i + max_bytes]
        # Comprehend 対応言語なら API 使用、それ以外は regex
        if language in ("en", "es", "fr", "de", "it", "pt"):
            entities = detect_pii_comprehend(comprehend, chunk, language)
        else:
            entities = detect_pii_regex(chunk)

        # オフセットをチャンクオフセット分補正
        for ent in entities:
            ent["BeginOffset"] = ent.get("BeginOffset", 0) + i
            ent["EndOffset"] = ent.get("EndOffset", 0) + i
            # PII 原文は保存しないが、hash のみ保持
            all_entities.append(ent)

    # 結果を S3 に書き出し（hash のみ、原文保存しない）
    import hashlib
    pii_summary = []
    for ent in all_entities:
        begin = ent.get("BeginOffset", 0)
        end = ent.get("EndOffset", 0)
        original_text = text[begin:end] if end > begin else ""
        pii_summary.append({
            "Type": ent.get("Type", "UNKNOWN"),
            "BeginOffset": begin,
            "EndOffset": end,
            "Score": float(ent.get("Score", 0.0)),
            "TextHash": hashlib.sha256(original_text.encode()).hexdigest()[:16],
        })

    entities_key = f"pii-entities/{document_key}.json"
    s3_client.put_object(
        Bucket=output_bucket,
        Key=entities_key,
        Body=json.dumps({
            "document_key": document_key,
            "pii_count": len(pii_summary),
            "entities": pii_summary,
        }, default=str),
        ContentType="application/json",
        ServerSideEncryption="aws:kms",
    )

    logger.info(
        "UC16 Entity Extraction: document=%s, pii_count=%d",
        document_key,
        len(pii_summary),
    )

    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="entity_extraction")
    metrics.set_dimension("UseCase", "government-archives")
    metrics.put_metric("PiiEntitiesDetected", float(len(pii_summary)), "Count")
    metrics.flush()

    return {
        "document_key": document_key,
        "text_key": text_key,
        "entities_key": entities_key,
        "pii_count": len(pii_summary),
        "entities": pii_summary,
    }
