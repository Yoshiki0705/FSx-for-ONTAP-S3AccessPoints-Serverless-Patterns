"""GenAI RAG Embedding Lambda

チャンクテキストを Amazon Bedrock Titan Embeddings でベクトル化する。
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

bedrock_client = boto3.client("bedrock-runtime")


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Embedding Lambda ハンドラー"""
    key = event.get("key", "")
    chunks = event.get("chunks", {}).get("chunks", [])
    model_id = os.environ.get("BEDROCK_MODEL_ID", "amazon.titan-embed-text-v2:0")

    logger.info("Embedding %d chunks for %s", len(chunks), key)

    embeddings = []
    errors = 0

    for chunk in chunks[:50]:  # 最大50チャンク
        try:
            embedding = _get_embedding(chunk["text"], model_id)
            embeddings.append(
                {
                    "chunk_id": chunk["chunk_id"],
                    "embedding_dim": len(embedding),
                    "text_preview": chunk["text"][:100],
                }
            )
        except Exception as e:
            logger.warning("Embedding failed for chunk %d: %s", chunk["chunk_id"], str(e))
            errors += 1

    return {
        "key": key,
        "status": "completed",
        "embedding_count": len(embeddings),
        "error_count": errors,
        "model_id": model_id,
        "timestamp": int(time.time()),
    }


def _get_embedding(text: str, model_id: str) -> list[float]:
    """Bedrock Titan Embeddings でベクトル化"""
    body = json.dumps(
        {
            "inputText": text[:8000],  # Titan の入力制限
        }
    )

    response = bedrock_client.invoke_model(
        modelId=model_id,
        body=body,
        contentType="application/json",
        accept="application/json",
    )

    result = json.loads(response["body"].read())
    return result.get("embedding", [])
