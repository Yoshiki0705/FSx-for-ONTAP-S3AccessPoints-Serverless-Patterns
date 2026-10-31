"""Processing Lambda — Step Functions × AgentCore Gateway pattern.

S3 AP 経由で 1 ファイルを読み取り、Amazon Bedrock（Nova）で要約・分類する。
Step Functions の Map Iterator から 1 オブジェクトずつ呼ばれる。

要約結果の確信度を shared.human_review.evaluate_confidence で評価し、
AUTO_APPROVE / HUMAN_REVIEW / REJECT の判定を結果に含める。最終判断はこの Lambda では
行わず、判定を後続（Report / 人間レビュー）へ渡すだけにとどめる。

Environment Variables:
    S3_ACCESS_POINT_ALIAS: S3 AP Alias（DemoMode では通常バケット名）
    BEDROCK_MODEL_ID: Bedrock モデル ID / 推論プロファイル ID
    MAX_READ_BYTES: 読み取り上限バイト数（デフォルト: 51200）
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import boto3

from shared.exceptions import lambda_error_handler
from shared.human_review import evaluate_confidence
from shared.observability import EmfMetrics
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_bedrock = boto3.client("bedrock-runtime")

DEFAULT_MAX_READ_BYTES = 50 * 1024


@lambda_error_handler
def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Processing Lambda ハンドラー。

    Map Iterator の 1 要素（discovery が生成した manifest の 1 オブジェクト）を処理する。

    Args:
        event: {key, size, category, ...} を含むオブジェクト情報。
        context: Lambda コンテキスト。

    Returns:
        dict: {key, status, category, summary, confidence, human_review, ...}。

    Raises:
        S3ApHelperError: S3 AP 読み取りに失敗した場合（Retry/Catch を機能させるため再送出）。
    """
    key = event.get("key", "")
    category = event.get("category", "general")
    size = int(event.get("size", 0))
    alias = os.environ.get("S3_ACCESS_POINT_ALIAS", "")
    model_id = os.environ.get("BEDROCK_MODEL_ID", "apac.amazon.nova-pro-v1:0")
    max_bytes = int(os.environ.get("MAX_READ_BYTES", str(DEFAULT_MAX_READ_BYTES)))

    logger.info("Processing: key=%s category=%s size=%d", key, category, size)

    metrics = EmfMetrics(service="stepfunctions-agentcore-tools")

    helper = S3ApHelper(alias)
    raw = helper.get_object_bytes(key, max_bytes=max_bytes)
    content = raw.decode("utf-8", errors="replace")

    summary, confidence = _summarize(content, category, key, model_id)

    decision = evaluate_confidence(confidence)

    metrics.put_metric("FilesProcessed", 1, "Count")
    if decision.requires_review:
        metrics.put_metric("HumanReviewRequired", 1, "Count")
    metrics.flush()

    return {
        "key": key,
        "status": "completed",
        "category": category,
        "summary": summary,
        "confidence": round(confidence, 3),
        "human_review": decision.to_dict(),
        "content_preview": content[:200],
        "file_size": size,
    }


def _summarize(content: str, category: str, key: str, model_id: str) -> tuple[str, float]:
    """Bedrock Nova でファイル内容を要約し、要約と確信度を返す。

    Args:
        content: ファイル内容（先頭部分）。
        category: discovery が推定したカテゴリ。
        key: オブジェクトキー。
        model_id: Bedrock モデル ID / 推論プロファイル ID。

    Returns:
        tuple[str, float]: (要約テキスト, 確信度 0.0-1.0)。
            Bedrock 呼び出しに失敗した場合は要約にエラー文、確信度 0.0 を返す。
    """
    prompt = (
        f"以下は '{os.path.basename(key)}'（カテゴリ: {category}）の内容です。"
        "ドキュメントタイプ・主要フィールド・1-2 文の要約を日本語で述べてください。\n\n"
        f"--- 内容（先頭部分） ---\n{content[:3000]}\n--- ここまで ---"
    )

    try:
        response = _bedrock.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(
                {
                    "messages": [{"role": "user", "content": [{"text": prompt}]}],
                    "inferenceConfig": {"maxTokens": 1024, "temperature": 0.1},
                }
            ),
        )
        body = json.loads(response["body"].read())
        summary = body["output"]["message"]["content"][0]["text"]
        # 要約が得られたことを確信度の下限の目安にする。長さで粗く重み付けする。
        confidence = 0.9 if len(summary) >= 40 else 0.6
        return summary, confidence
    except Exception as e:  # noqa: BLE001 — Bedrock 失敗は致命ではなく低確信度で返す
        logger.warning("Bedrock invocation failed for %s: %s", key, str(e))
        return f"[summarization unavailable: {e}]", 0.0
