"""教育 / 研究 メタデータ生成 Lambda ハンドラ

各論文の構造化メタデータ（title, authors, classification, keywords, citation_count）
を JSON で S3 出力する。

Environment Variables:
    OUTPUT_BUCKET: S3 出力バケット名
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import PurePosixPath

import boto3

from shared.exceptions import lambda_error_handler

logger = logging.getLogger(__name__)


def _build_paper_metadata(
    file_key: str,
    classification: dict,
    entities: list[dict],
    key_phrases: list[str],
    citation_count: int,
) -> dict:
    """論文の構造化メタデータを構築する

    Args:
        file_key: ファイルキー
        classification: 分類結果
        entities: エンティティリスト
        key_phrases: キーフレーズリスト
        citation_count: 引用数

    Returns:
        dict: 構造化メタデータ
    """
    # 著者抽出（PERSON エンティティ）
    authors = [
        e["text"] for e in entities
        if e.get("type") == "PERSON" and e.get("score", 0) >= 0.7
    ]

    # 機関抽出（ORGANIZATION エンティティ）
    organizations = [
        e["text"] for e in entities
        if e.get("type") == "ORGANIZATION" and e.get("score", 0) >= 0.7
    ]

    # 日付抽出（DATE エンティティ）
    dates = [
        e["text"] for e in entities
        if e.get("type") == "DATE" and e.get("score", 0) >= 0.7
    ]

    return {
        "file_key": file_key,
        "title": classification.get("summary", PurePosixPath(file_key).stem),
        "authors": authors[:10],
        "organizations": organizations[:5],
        "publication_date": dates[0] if dates else "Unknown",
        "domain": classification.get("domain", "Other"),
        "domain_confidence": classification.get("confidence", 0.0),
        "keywords": classification.get("keywords", key_phrases[:10]),
        "key_phrases": key_phrases,
        "citation_count": citation_count,
    }


@lambda_error_handler
def handler(event, context):
    """論文メタデータ生成

    Input:
        {
            "file_key": "papers/research_2026.pdf",
            "classification": {...},
            "entities": [...],
            "key_phrases": [...],
            "citation_count": 5
        }

    Output:
        {
            "status": "SUCCESS",
            "file_key": "...",
            "metadata": {...},
            "output_key": "..."
        }
    """
    file_key = event.get("file_key", "")
    classification = event.get("classification", {})
    entities = event.get("entities", [])
    key_phrases = event.get("key_phrases", [])
    citation_count = event.get("citation_count", 0)

    output_bucket = os.environ["OUTPUT_BUCKET"]

    logger.info("Metadata generation started: file_key=%s", file_key)

    # 構造化メタデータ構築
    paper_metadata = _build_paper_metadata(
        file_key=file_key,
        classification=classification,
        entities=entities,
        key_phrases=key_phrases,
        citation_count=citation_count,
    )

    # 出力キー生成
    now = datetime.now(timezone.utc)
    file_stem = PurePosixPath(file_key).stem
    output_key = f"metadata/{now.strftime('%Y/%m/%d')}/{file_stem}_metadata.json"

    # 結果を S3 出力バケットに書き込み
    result = {
        "status": "SUCCESS",
        "file_key": file_key,
        "metadata": paper_metadata,
        "output_key": output_key,
        "generated_at": now.isoformat(),
    }

    s3_client = boto3.client("s3")
    s3_client.put_object(
        Bucket=output_bucket,
        Key=output_key,
        Body=json.dumps(result, default=str, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json; charset=utf-8",
    )

    logger.info(
        "Metadata generation completed: file_key=%s, domain=%s",
        file_key,
        paper_metadata.get("domain", "Unknown"),
    )

    return result
