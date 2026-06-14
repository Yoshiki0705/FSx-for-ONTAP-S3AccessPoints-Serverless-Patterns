"""UC29 Self-Service KB Curation — Query Lambda

業務ユーザーが Windows ドラッグ&ドロップで維持しているナレッジに対して、
マネージド Amazon Bedrock Knowledge Base の RetrieveAndGenerate API で
自然言語の質問に回答する（デモ用 Q&A）。
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

bedrock_runtime = boto3.client("bedrock-agent-runtime")

# 推論プロファイル ID（apac. / us. / jp. / global. など地域プレフィックス）の判定
_INFERENCE_PROFILE_PREFIX = re.compile(r"^(apac|us|eu|jp|global|apne|au|ca|sa|me|af)\.")


def _build_model_arn(model_id: str, region: str, account_id: str) -> str:
    """モデル ID から InvokeModel 用 ARN を構築する。

    地域プレフィックス付き ID は推論プロファイル、それ以外は基盤モデルとして扱う。
    """
    if _INFERENCE_PROFILE_PREFIX.match(model_id):
        return f"arn:aws:bedrock:{region}:{account_id}:inference-profile/{model_id}"
    return f"arn:aws:bedrock:{region}::foundation-model/{model_id}"


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Query ハンドラー。

    event 例: {"query": "新製品Xの主な仕様を教えて"}
    """
    logger.info("Self-service KB query started")

    kb_id = os.environ.get("KNOWLEDGE_BASE_ID", "")
    model_id = os.environ.get("BEDROCK_LLM_MODEL_ID", "apac.amazon.nova-pro-v1:0")
    region = os.environ.get("AWS_REGION", "ap-northeast-1")
    query = (event.get("query") or "").strip()

    now = int(datetime.now(timezone.utc).timestamp())

    if not (kb_id and query):
        result = {
            "status": "error",
            "error": "KNOWLEDGE_BASE_ID and event.query are required",
            "timestamp": now,
        }
        logger.error(result["error"])
        return result

    account_id = ""
    if context is not None and getattr(context, "invoked_function_arn", ""):
        parts = context.invoked_function_arn.split(":")
        if len(parts) > 4:
            account_id = parts[4]
    model_arn = _build_model_arn(model_id, region, account_id)

    # 権限・ロール絞り込み用のメタデータフィルタ（任意）
    # event 例:
    #   {"query": "...", "role": "sales"}                      → role 単一一致
    #   {"query": "...", "filter": {"equals": {"key": "role", "value": "sales"}}}  → 任意フィルタ
    vector_search_config: dict[str, Any] = {}
    metadata_filter = event.get("filter")
    if not metadata_filter and event.get("role"):
        metadata_filter = {"equals": {"key": "role", "value": event["role"]}}
    if metadata_filter:
        vector_search_config["filter"] = metadata_filter

    kb_config: dict[str, Any] = {"knowledgeBaseId": kb_id, "modelArn": model_arn}
    if vector_search_config:
        kb_config["retrievalConfiguration"] = {
            "vectorSearchConfiguration": vector_search_config
        }
    # 任意: Bedrock Guardrails（GENSEC02 — 有害・不正確な応答の抑制）
    guardrail_id = os.environ.get("BEDROCK_GUARDRAIL_ID", "")
    if guardrail_id:
        kb_config["generationConfiguration"] = {
            "guardrailConfiguration": {
                "guardrailId": guardrail_id,
                "guardrailVersion": os.environ.get("BEDROCK_GUARDRAIL_VERSION", "DRAFT"),
            }
        }

    try:
        resp = bedrock_runtime.retrieve_and_generate(
            input={"text": query},
            retrieveAndGenerateConfiguration={
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": kb_config,
            },
        )

        answer = resp.get("output", {}).get("text", "")
        citations = []
        for citation in resp.get("citations", []):
            for ref in citation.get("retrievedReferences", []):
                location = ref.get("location", {})
                s3_loc = location.get("s3Location", {})
                citations.append({"source": s3_loc.get("uri", "")})

        result = {
            "status": "completed",
            "query": query,
            "answer": answer,
            "citations": citations,
            "timestamp": now,
        }
        logger.info("Query completed: %d citations", len(citations))
        return result

    except Exception as e:  # noqa: BLE001 - エラーを可視化
        result = {"status": "error", "error": str(e), "query": query, "timestamp": now}
        logger.error("Query failed: %s", str(e))
        return result
