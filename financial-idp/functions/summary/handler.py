"""金融・保険 Summary Lambda ハンドラ

Entity Extraction Lambda から抽出テキストとエンティティを受け取り、
Amazon Bedrock で構造化サマリーを生成し、JSON 出力を S3 AP に書き出す。

出力 JSON スキーマ:
    {
        "extracted_text": str,
        "entities": dict,
        "summary": str,
        "document_key": str,
        "processed_at": str  # ISO 8601
    }

Environment Variables:
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
    BEDROCK_MODEL_ID: Bedrock モデル ID (デフォルト: amazon.nova-lite-v1:0)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime

import boto3

from shared.exceptions import lambda_error_handler
from shared.s3ap_helper import S3ApHelper
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)


def build_summary_output(
    extracted_text: str,
    entities: dict,
    summary_text: str,
    document_key: str,
) -> dict:
    """構造化サマリー出力を生成する

    プロパティテストで直接テスト可能なヘルパー関数。

    Args:
        extracted_text: OCR で抽出されたテキスト
        entities: Entity Extraction で抽出されたエンティティ
        summary_text: Bedrock で生成されたサマリーテキスト
        document_key: 元ドキュメントの S3 キー

    Returns:
        dict: 構造化出力 JSON。以下のキーを含む:
            - extracted_text (str)
            - entities (dict)
            - summary (str)
            - document_key (str)
            - processed_at (str): ISO 8601 形式のタイムスタンプ
    """
    return {
        "extracted_text": extracted_text,
        "entities": entities,
        "summary": summary_text,
        "document_key": document_key,
        "processed_at": datetime.utcnow().isoformat(),
    }


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Summary Lambda: Bedrock でサマリー生成 → JSON 出力 → S3 書き出し

    Entity Extraction Lambda から以下の形式でデータを受け取る:
        {"document_key": str, "extracted_text": str, "entities": dict}

    Returns:
        dict: document_key, output_bucket, output_key
    """
    document_key = event["document_key"]
    extracted_text = event.get("extracted_text", "")
    entities = event.get("entities", {})

    logger.info(
        "Summary generation started: key=%s, text_length=%d",
        document_key,
        len(extracted_text),
    )

    # Bedrock でサマリー生成
    bedrock_client = boto3.client("bedrock-runtime")
    model_id = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")

    prompt = (
        "以下のドキュメントから抽出されたテキストとエンティティに基づき、"
        "構造化されたサマリーを日本語で生成してください。\n\n"
        f"## 抽出テキスト\n{extracted_text[:5000]}\n\n"
        f"## 抽出エンティティ\n{json.dumps(entities, ensure_ascii=False)}\n\n"
        "## 出力形式\n"
        "- 文書種別（契約書/請求書/その他）\n"
        "- 主要当事者\n"
        "- 重要日付\n"
        "- 金額情報\n"
        "- 要約（3-5文）"
    )

    try:
        bedrock_response = bedrock_client.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "messages": [
                    {
                        "role": "user",
                        "content": [{"text": prompt}],
                    }
                ],
                "inferenceConfig": {
                    "maxTokens": 2048,
                    "temperature": 0.3,
                },
            }),
        )

        response_body = json.loads(bedrock_response["body"].read())
        summary_text = (
            response_body.get("output", {})
            .get("message", {})
            .get("content", [{}])[0]
            .get("text", "")
        )
    except Exception as e:
        logger.error("Bedrock InvokeModel failed: %s", e)
        summary_text = f"サマリー生成に失敗しました: {str(e)[:200]}"

    # 構造化出力を生成
    output = build_summary_output(
        extracted_text=extracted_text,
        entities=entities,
        summary_text=summary_text,
        document_key=document_key,
    )

    # S3 AP に書き出し
    s3ap_output = S3ApHelper(os.environ["S3_ACCESS_POINT_OUTPUT"])
    output_key = (
        f"summaries/{datetime.utcnow().strftime('%Y/%m/%d')}"
        f"/{document_key.replace('/', '_')}.json"
    )

    s3ap_output.put_object(
        key=output_key,
        body=json.dumps(output, ensure_ascii=False, default=str),
        content_type="application/json",
    )

    logger.info(
        "Summary generation completed: key=%s, output=%s",
        document_key,
        output_key,
    )


    # EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="summary")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "financial-idp"))
    metrics.put_metric("FilesProcessed", 1.0, "Count")
    metrics.flush()

    return {
        "document_key": document_key,
        "output_key": output_key,
    }
