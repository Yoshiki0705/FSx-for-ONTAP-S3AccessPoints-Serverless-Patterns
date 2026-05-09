"""UC16 Government Archives Classification Lambda

Amazon Comprehend で文書を分類し、機密レベル（public/sensitive/confidential）を判定する。

Environment Variables:
    OUTPUT_BUCKET: 出力先 S3 バケット
    COMPREHEND_LANGUAGE_CODE: 言語コード (default: "en", auto-detect 可)
    CLASSIFIER_ENDPOINT_ARN: Comprehend Custom Classifier Endpoint ARN (optional)
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


# 機密キーワード（Public = low, Sensitive = medium, Confidential = high）
# 注意: 「社外秘」のような部分一致を避けるため、SENSITIVE を先にチェックする
CONFIDENTIAL_KEYWORDS = frozenset({
    "top secret", "classified", "confidential", "national security",
    "極秘", "機密",
})

SENSITIVE_KEYWORDS = frozenset({
    "internal", "restricted", "proprietary", "sensitive",
    "社外秘", "限定", "内部",
})


def classify_by_keywords(text: str) -> tuple[str, float]:
    """キーワードベースのルール分類（Comprehend Custom Classifier が無い場合のフォールバック）。

    Args:
        text: 文書テキスト

    Returns:
        tuple: (クリアランスレベル, 信頼度)
    """
    text_lower = text.lower()

    # SENSITIVE を先にチェック（「社外秘」が「秘」で confidential に誤判定されないよう）
    for kw in SENSITIVE_KEYWORDS:
        if kw in text_lower:
            return "sensitive", 0.85

    for kw in CONFIDENTIAL_KEYWORDS:
        if kw in text_lower:
            return "confidential", 0.95

    return "public", 0.75


def detect_language(comprehend, text: str) -> str:
    """Comprehend で主要言語を検出する。"""
    if not text.strip():
        return "en"
    sample = text[:5000]  # Comprehend 制限対策
    try:
        response = comprehend.detect_dominant_language(Text=sample)
        languages = response.get("Languages", [])
        if languages:
            return languages[0].get("LanguageCode", "en")
    except Exception as e:
        logger.warning("Language detection failed: %s", e)
    return "en"


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """UC16 Classification Lambda ハンドラ。

    Input:
        {"document_key": "...", "text_key": "..."}

    Output:
        {"document_key": str, "clearance_level": str, "confidence": float, "language": str}
    """
    output_bucket = os.environ["OUTPUT_BUCKET"]
    classifier_endpoint = os.environ.get("CLASSIFIER_ENDPOINT_ARN", "")

    document_key = event.get("document_key", "")
    text_key = event.get("text_key", "")

    if not text_key:
        raise ValueError("Input must contain 'text_key'")

    # OCR テキストを S3 から取得
    s3_client = boto3.client("s3")
    response = s3_client.get_object(Bucket=output_bucket, Key=text_key)
    text = response["Body"].read().decode("utf-8")

    comprehend = boto3.client("comprehend")

    # 言語検出
    language = detect_language(comprehend, text)

    # 分類: Custom Classifier があれば使用、なければキーワードフォールバック
    if classifier_endpoint and text.strip():
        try:
            sample = text[:5000]
            cls_response = comprehend.classify_document(
                EndpointArn=classifier_endpoint,
                Text=sample,
            )
            classes = cls_response.get("Classes", [])
            if classes:
                top = max(classes, key=lambda c: c.get("Score", 0))
                clearance_level = top.get("Name", "public").lower()
                confidence = top.get("Score", 0.0)
            else:
                clearance_level, confidence = classify_by_keywords(text)
        except Exception as e:
            logger.warning("Custom classifier failed, using keyword fallback: %s", e)
            clearance_level, confidence = classify_by_keywords(text)
    else:
        clearance_level, confidence = classify_by_keywords(text)

    # 結果を S3 に書き出し
    classification_key = f"classifications/{document_key}.json"
    result = {
        "document_key": document_key,
        "text_key": text_key,
        "clearance_level": clearance_level,
        "confidence": float(confidence),
        "language": language,
    }
    s3_client.put_object(
        Bucket=output_bucket,
        Key=classification_key,
        Body=json.dumps(result, default=str),
        ContentType="application/json",
        ServerSideEncryption="aws:kms",
    )

    logger.info(
        "UC16 Classification: document=%s, level=%s, confidence=%.2f",
        document_key,
        clearance_level,
        confidence,
    )

    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="classification")
    metrics.set_dimension("UseCase", "government-archives")
    metrics.set_dimension("ClearanceLevel", clearance_level)
    metrics.put_metric("ClassifiedDocuments", 1.0, "Count")
    metrics.put_metric("Confidence", float(confidence), "None")
    metrics.flush()

    return result
