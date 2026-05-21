"""GenAI RAG Chunking Lambda

S3 AP 経由でドキュメントを取得し、テキスト抽出・チャンク分割を行う。
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

s3_client = boto3.client("s3")


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Chunking Lambda ハンドラー"""
    key = event.get("key", "")
    size = event.get("size", 0)
    extension = event.get("extension", "")

    s3ap_alias = os.environ.get("S3_ACCESS_POINT_ALIAS", "")
    chunk_size = int(os.environ.get("CHUNK_SIZE", "1000"))
    chunk_overlap = int(os.environ.get("CHUNK_OVERLAP", "200"))

    logger.info("Chunking document: %s (%d bytes)", key, size)

    try:
        # S3 AP 経由でファイル取得
        response = s3_client.get_object(Bucket=s3ap_alias, Key=key)
        content_bytes = response["Body"].read()
        response["Body"].close()

        # テキスト抽出（簡易実装）
        text = _extract_text(content_bytes, extension)

        # チャンク分割
        chunks = _split_into_chunks(text, chunk_size, chunk_overlap)

        return {
            "key": key,
            "status": "completed",
            "chunk_count": len(chunks),
            "chunks": chunks[:50],  # 最大50チャンクを返す
            "total_chars": len(text),
            "timestamp": int(time.time()),
        }

    except Exception as e:
        logger.error("Chunking failed for %s: %s", key, str(e))
        return {
            "key": key,
            "status": "error",
            "error": str(e),
            "chunks": [],
            "timestamp": int(time.time()),
        }


def _extract_text(content: bytes, extension: str) -> str:
    """ファイルからテキストを抽出（簡易実装）"""
    if extension in (".txt", ".md", ".csv", ".json", ".html", ".htm"):
        return content.decode("utf-8", errors="replace")
    elif extension == ".pdf":
        # PDF テキスト抽出（簡易: バイナリからテキスト部分を抽出）
        # 本番では PyPDF2 や pdfplumber を使用
        return content.decode("latin-1", errors="replace")
    else:
        # その他のフォーマットはバイナリとして扱う
        return content.decode("utf-8", errors="replace")


def _split_into_chunks(text: str, chunk_size: int, overlap: int) -> list[dict]:
    """テキストをチャンクに分割"""
    chunks = []
    start = 0
    chunk_id = 0

    while start < len(text):
        end = start + chunk_size
        chunk_text = text[start:end]

        if chunk_text.strip():
            chunks.append({
                "chunk_id": chunk_id,
                "text": chunk_text,
                "start_char": start,
                "end_char": min(end, len(text)),
            })
            chunk_id += 1

        start += chunk_size - overlap

    return chunks
