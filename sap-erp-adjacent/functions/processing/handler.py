"""SAP/ERP Adjacent Processing Lambda

S3 AP 経由でファイルを読み取り、Amazon Bedrock で要約・分類を行う。
IDoc、EDI、CSV 等のフォーマットに応じた前処理を実施する。

Environment Variables:
    S3_ACCESS_POINT_ALIAS: S3 AP Alias (入力読み取り用)
    BEDROCK_MODEL_ID: Bedrock モデル ID (デフォルト: amazon.nova-pro-v1:0)
    OUTPUT_BUCKET: 出力先 S3 バケット名
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

s3_client = boto3.client("s3")
bedrock_client = boto3.client("bedrock-runtime")

# 読み取り上限（Lambda メモリ保護）
MAX_READ_BYTES = 50 * 1024  # 50 KB


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Processing Lambda ハンドラー

    ファイルを読み取り、Bedrock で要約・分類を行う。
    """
    key = event.get("key", "")
    category = event.get("category", "general_erp")
    size = event.get("size", 0)
    s3ap_alias = os.environ.get("S3_ACCESS_POINT_ALIAS", "")
    model_id = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-pro-v1:0")
    output_bucket = os.environ.get("OUTPUT_BUCKET", "")

    logger.info("Processing: %s (category: %s, size: %d)", key, category, size)

    # ファイル読み取り（先頭 50KB のみ）
    try:
        read_size = min(size, MAX_READ_BYTES) if size > 0 else MAX_READ_BYTES
        response = s3_client.get_object(
            Bucket=s3ap_alias,
            Key=key,
            Range=f"bytes=0-{read_size - 1}",
        )
        content = response["Body"].read().decode("utf-8", errors="replace")
        response["Body"].close()
    except Exception as e:
        logger.error("Failed to read file %s: %s", key, str(e))
        return {
            "key": key,
            "status": "error",
            "error": f"Read failed: {str(e)}",
            "timestamp": int(time.time()),
        }

    # Bedrock で要約・分類
    prompt = _build_prompt(content, category, key)

    try:
        bedrock_response = bedrock_client.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "messages": [{"role": "user", "content": [{"text": prompt}]}],
                "inferenceConfig": {"maxTokens": 1024, "temperature": 0.1},
            }),
        )
        response_body = json.loads(bedrock_response["body"].read())
        summary = response_body["output"]["message"]["content"][0]["text"]
    except Exception as e:
        logger.error("Bedrock invocation failed: %s", str(e))
        summary = f"[Bedrock error: {str(e)}]"

    # 結果を出力バケットに保存
    result = {
        "key": key,
        "status": "completed",
        "category": category,
        "summary": summary,
        "content_preview": content[:200],
        "file_size": size,
        "timestamp": int(time.time()),
    }

    if output_bucket:
        output_key = f"processed/{os.path.basename(key)}.json"
        try:
            s3_client.put_object(
                Bucket=output_bucket,
                Key=output_key,
                Body=json.dumps(result, ensure_ascii=False),
                ContentType="application/json",
            )
            result["output_key"] = output_key
        except Exception as e:
            logger.warning("Failed to write output: %s", str(e))

    return result


def _build_prompt(content: str, category: str, key: str) -> str:
    """カテゴリに応じたプロンプトを構築する"""
    category_instructions = {
        "sap_idoc": (
            "以下は SAP IDoc エクスポートファイルの内容です。"
            "IDoc タイプ（ORDERS, INVOIC, DESADV 等）を特定し、"
            "主要フィールド（取引先、金額、日付、品目）を抽出して要約してください。"
        ),
        "hulft_transfer": (
            "以下は HULFT/DataSpider で転送されたファイルの内容です。"
            "データ形式を特定し、レコード数、主要フィールド、データ品質を要約してください。"
        ),
        "edi_document": (
            "以下は EDI (X12/EDIFACT) ドキュメントの内容です。"
            "トランザクションセットタイプを特定し、取引内容を要約してください。"
        ),
        "batch_output": (
            "以下はバッチジョブ出力ファイルの内容です。"
            "処理結果（成功/失敗）、処理件数、エラー内容を要約してください。"
        ),
        "data_extract": (
            "以下は ERP データ抽出ファイルの内容です。"
            "データ構造、レコード数、主要フィールドを要約してください。"
        ),
    }

    instruction = category_instructions.get(
        category,
        "以下のファイル内容を要約し、データ形式と主要な情報を抽出してください。",
    )

    return f"""{instruction}

ファイル名: {os.path.basename(key)}
カテゴリ: {category}

--- ファイル内容（先頭部分） ---
{content[:3000]}
--- ここまで ---

JSON 形式で以下を出力してください:
- document_type: ドキュメントタイプ
- key_fields: 主要フィールドのリスト
- record_count: レコード数（推定）
- summary: 1-2 文の要約
- quality_issues: データ品質の問題点（あれば）
"""
