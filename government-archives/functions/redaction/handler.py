"""UC16 Government Archives Redaction Lambda

PII を `[REDACTED]` マーカーに置換し、sidecar メタデータを生成する。

Invariants:
- N 個の PII エンティティがある場合、出力には正確に N 個の [REDACTED] マーカー
- 出力に PII 原文が残存してはならない

Environment Variables:
    OUTPUT_BUCKET: 出力先 S3 バケット
    REDACTION_MARKER: 墨消しマーカー文字列 (default: "[REDACTED]")
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)

DEFAULT_REDACTION_MARKER = "[REDACTED]"


def redact_text(
    text: str, entities: list[dict], marker: str = DEFAULT_REDACTION_MARKER
) -> tuple[str, list[dict]]:
    """テキスト中の PII エンティティを marker に置換する。

    Args:
        text: 元テキスト
        entities: PII エンティティリスト（BeginOffset, EndOffset 含む）
        marker: 置換マーカー文字列

    Returns:
        tuple: (redacted_text, redaction_metadata)
    """
    if not entities:
        return text, []

    # オフセット順にソート（末尾から置換すると前のオフセットが変わらない）
    sorted_entities = sorted(
        entities, key=lambda e: e.get("BeginOffset", 0), reverse=True
    )

    redacted = text
    metadata = []

    for ent in sorted_entities:
        begin = ent.get("BeginOffset", 0)
        end = ent.get("EndOffset", 0)
        if end <= begin or end > len(redacted):
            continue
        original = redacted[begin:end]
        redacted = redacted[:begin] + marker + redacted[end:]
        metadata.append({
            "entity_type": ent.get("Type", "UNKNOWN"),
            "original_offset": [begin, end],
            "original_text_hash": "sha256:" + hashlib.sha256(
                original.encode()
            ).hexdigest(),
            "confidence": float(ent.get("Score", 0.0)),
        })

    # メタデータを元の順序に戻す
    metadata.reverse()
    return redacted, metadata


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """UC16 Redaction Lambda ハンドラ。

    Input:
        {"document_key": "...", "text_key": "...", "entities": [...]}

    Output:
        {
            "document_key": str,
            "redacted_text_key": str,
            "redaction_metadata_key": str,
            "redaction_count": int
        }
    """
    output_bucket = os.environ["OUTPUT_BUCKET"]
    marker = os.environ.get("REDACTION_MARKER", DEFAULT_REDACTION_MARKER)

    document_key = event.get("document_key", "")
    text_key = event.get("text_key", "")
    entities = event.get("entities", [])

    if not text_key:
        raise ValueError("Input must contain 'text_key'")

    # OCR テキストを S3 から取得
    s3_client = boto3.client("s3")
    response = s3_client.get_object(Bucket=output_bucket, Key=text_key)
    text = response["Body"].read().decode("utf-8")

    redacted_text, redaction_metadata = redact_text(text, entities, marker)

    # 墨消しテキストを S3 に書き出し
    redacted_key = text_key.replace("ocr-results/", "redacted/")
    if redacted_key == text_key:
        redacted_key = f"redacted/{text_key}"
    s3_client.put_object(
        Bucket=output_bucket,
        Key=redacted_key,
        Body=redacted_text.encode("utf-8"),
        ContentType="text/plain",
        ServerSideEncryption="aws:kms",
    )

    # 墨消しメタデータ（sidecar JSON）
    metadata_key = f"redaction-metadata/{document_key}.json"
    sidecar = {
        "original_document": document_key,
        "redacted_document": redacted_key,
        "redactions": redaction_metadata,
        "redaction_count": len(redaction_metadata),
        "processed_at": context.aws_request_id,
    }
    s3_client.put_object(
        Bucket=output_bucket,
        Key=metadata_key,
        Body=json.dumps(sidecar, default=str),
        ContentType="application/json",
        ServerSideEncryption="aws:kms",
    )

    logger.info(
        "UC16 Redaction: document=%s, redactions=%d",
        document_key,
        len(redaction_metadata),
    )

    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="redaction")
    metrics.set_dimension("UseCase", "government-archives")
    metrics.put_metric("RedactionsApplied", float(len(redaction_metadata)), "Count")
    metrics.flush()

    return {
        "document_key": document_key,
        "redacted_text_key": redacted_key,
        "redaction_metadata_key": metadata_key,
        "redaction_count": len(redaction_metadata),
    }
