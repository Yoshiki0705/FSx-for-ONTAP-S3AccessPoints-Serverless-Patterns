"""物流 / サプライチェーン データ構造化 Lambda ハンドラ

Bedrock で OCR 抽出フィールドを正規化し、構造化配送レコード
（JSON 形式、標準化フィールド名）を生成する。

Environment Variables:
    OUTPUT_BUCKET: S3 出力バケット名
    BEDROCK_MODEL_ID: Bedrock モデル ID (デフォルト: amazon.nova-lite-v1:0)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import PurePosixPath

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)

# 構造化配送レコードの必須フィールド
REQUIRED_FIELDS = [
    "sender_name",
    "sender_address",
    "recipient_name",
    "recipient_address",
    "tracking_number",
    "items",
    "total_quantity",
]


def _build_prompt(extracted_text: str, forms: list[dict]) -> str:
    """Bedrock 用プロンプトを構築する

    Args:
        extracted_text: OCR で抽出されたテキスト
        forms: OCR で抽出されたフォームフィールド

    Returns:
        str: Bedrock プロンプト
    """
    forms_text = "\n".join(
        f"  {f['key']}: {f['value']}" for f in forms
    )

    return f"""以下の配送伝票 OCR 結果から、構造化された配送レコードを JSON 形式で生成してください。

## OCR テキスト:
{extracted_text}

## フォームフィールド:
{forms_text}

## 出力 JSON フォーマット:
{{
    "sender_name": "送り主名",
    "sender_address": "送り主住所",
    "recipient_name": "届け先名",
    "recipient_address": "届け先住所",
    "tracking_number": "追跡番号",
    "items": [
        {{"description": "品名", "quantity": 数量}}
    ],
    "total_quantity": 合計数量,
    "shipping_date": "発送日 (YYYY-MM-DD)",
    "delivery_date": "配達予定日 (YYYY-MM-DD)"
}}

JSON のみを出力してください。"""


def _parse_bedrock_response(response_body: bytes) -> dict:
    """Bedrock レスポンスから JSON を解析する

    Args:
        response_body: Bedrock レスポンスボディ

    Returns:
        dict: 解析された構造化データ
    """
    response_json = json.loads(response_body)

    # Nova モデルのレスポンス形式
    if "results" in response_json:
        output_text = response_json["results"][0].get("outputText", "")
    elif "content" in response_json:
        output_text = response_json["content"][0].get("text", "")
    else:
        output_text = json.dumps(response_json)

    # JSON 部分を抽出
    try:
        # コードブロック内の JSON を探す
        if "```json" in output_text:
            json_str = output_text.split("```json")[1].split("```")[0].strip()
        elif "```" in output_text:
            json_str = output_text.split("```")[1].split("```")[0].strip()
        else:
            json_str = output_text.strip()

        return json.loads(json_str)
    except (json.JSONDecodeError, IndexError):
        return {}


def _ensure_required_fields(data: dict) -> dict:
    """必須フィールドが存在することを保証する

    Args:
        data: 構造化データ

    Returns:
        dict: 必須フィールドが補完されたデータ
    """
    defaults = {
        "sender_name": "Unknown",
        "sender_address": "Unknown",
        "recipient_name": "Unknown",
        "recipient_address": "Unknown",
        "tracking_number": "Unknown",
        "items": [],
        "total_quantity": 0,
    }

    for field, default_value in defaults.items():
        if not data.get(field):
            data[field] = default_value

    return data


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """配送伝票データ構造化（Bedrock）

    Input:
        {
            "file_key": "slips/delivery_20260115.pdf",
            "extracted_text": "...",
            "forms": [...]
        }

    Output:
        {
            "status": "SUCCESS",
            "file_key": "...",
            "structured_record": {...},
            "output_key": "..."
        }
    """
    file_key = event.get("file_key", "")
    extracted_text = event.get("extracted_text", "")
    forms = event.get("forms", [])

    output_bucket = os.environ["OUTPUT_BUCKET"]
    model_id = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")

    logger.info(
        "Data structuring started: file_key=%s, text_length=%d, forms=%d",
        file_key,
        len(extracted_text),
        len(forms),
    )

    # Bedrock でデータ構造化
    bedrock_client = boto3.client("bedrock-runtime")
    prompt = _build_prompt(extracted_text, forms)

    try:
        bedrock_response = bedrock_client.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "inputText": prompt,
                "textGenerationConfig": {
                    "maxTokenCount": 2048,
                    "temperature": 0.1,
                },
            }),
        )
        structured_record = _parse_bedrock_response(
            bedrock_response["body"].read()
        )
    except Exception as e:
        logger.warning("Bedrock invocation failed: %s, using fallback", e)
        structured_record = {}

    # 必須フィールド補完
    structured_record = _ensure_required_fields(structured_record)

    # 出力キー生成
    now = datetime.now(timezone.utc)
    file_stem = PurePosixPath(file_key).stem
    output_key = f"structured/{now.strftime('%Y/%m/%d')}/{file_stem}_record.json"

    # 結果を S3 出力バケットに書き込み
    result = {
        "status": "SUCCESS",
        "file_key": file_key,
        "structured_record": structured_record,
        "output_key": output_key,
        "structured_at": now.isoformat(),
    }

    s3_client = boto3.client("s3")
    s3_client.put_object(
        Bucket=output_bucket,
        Key=output_key,
        Body=json.dumps(result, default=str, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json; charset=utf-8",
    )

    logger.info(
        "Data structuring completed: file_key=%s, output_key=%s",
        file_key,
        output_key,
    )


    # EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="data_structuring")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "logistics-ocr"))
    metrics.put_metric("FilesProcessed", 1.0, "Count")
    metrics.flush()

    return result
