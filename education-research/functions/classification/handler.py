"""教育 / 研究 分類 Lambda ハンドラ

Comprehend でトピック検出・エンティティ抽出（著者、機関、キーワード、出版日）を実行する。
Bedrock で研究ドメイン分類と構造化アブストラクトサマリーを生成する。

Environment Variables:
    OUTPUT_DESTINATION: `STANDARD_S3` or `FSXN_S3AP` (デフォルト: `STANDARD_S3`)
    OUTPUT_BUCKET: STANDARD_S3 モードの出力バケット名
    OUTPUT_S3AP_ALIAS: FSXN_S3AP モードの S3AP Alias or ARN
    OUTPUT_S3AP_PREFIX: FSXN_S3AP モードの出力プレフィックス (デフォルト: `ai-outputs/`)
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
from shared.output_writer import OutputWriter

logger = logging.getLogger(__name__)

# 研究ドメインカテゴリ
RESEARCH_DOMAINS = [
    "Computer Science",
    "Biology",
    "Physics",
    "Chemistry",
    "Mathematics",
    "Medicine",
    "Engineering",
    "Social Sciences",
    "Environmental Science",
    "Other",
]


def extract_entities_with_comprehend(
    comprehend_client, text: str, language_code: str = "en"
) -> list[dict]:
    """Comprehend でエンティティ抽出を実行する

    Args:
        comprehend_client: boto3 Comprehend クライアント
        text: 入力テキスト
        language_code: 言語コード

    Returns:
        list[dict]: 抽出されたエンティティのリスト
    """
    # テキストが長すぎる場合は切り詰め（Comprehend の制限: 100KB）
    truncated_text = text[:99000] if len(text) > 99000 else text

    response = comprehend_client.detect_entities(
        Text=truncated_text,
        LanguageCode=language_code,
    )

    entities = []
    for entity in response.get("Entities", []):
        entities.append({
            "text": entity["Text"],
            "type": entity["Type"],
            "score": round(entity["Score"], 3),
        })

    return entities


def detect_key_phrases(
    comprehend_client, text: str, language_code: str = "en"
) -> list[str]:
    """Comprehend でキーフレーズ検出を実行する

    Args:
        comprehend_client: boto3 Comprehend クライアント
        text: 入力テキスト
        language_code: 言語コード

    Returns:
        list[str]: 検出されたキーフレーズのリスト
    """
    truncated_text = text[:99000] if len(text) > 99000 else text

    response = comprehend_client.detect_key_phrases(
        Text=truncated_text,
        LanguageCode=language_code,
    )

    phrases = []
    for phrase in response.get("KeyPhrases", []):
        if phrase.get("Score", 0) >= 0.7:
            phrases.append(phrase["Text"])

    return phrases[:20]  # 上位20件


def _classify_domain_with_bedrock(
    bedrock_client, text: str, model_id: str
) -> dict:
    """Bedrock で研究ドメイン分類を実行する

    Args:
        bedrock_client: boto3 Bedrock Runtime クライアント
        text: 論文テキスト（先頭部分）
        model_id: Bedrock モデル ID

    Returns:
        dict: 分類結果 {"domain": str, "confidence": float, "summary": str}
    """
    prompt = f"""以下の論文テキストを分析し、研究ドメインを分類してください。

## テキスト（先頭2000文字）:
{text[:2000]}

## 分類カテゴリ:
{', '.join(RESEARCH_DOMAINS)}

## 出力 JSON フォーマット:
{{
    "domain": "分類されたドメイン",
    "confidence": 0.0-1.0の信頼度,
    "summary": "論文の要約（100文字以内）",
    "keywords": ["キーワード1", "キーワード2", ...]
}}

JSON のみを出力してください。"""

    try:
        with xray_subsegment(

            name="bedrock_invokemodel",

            annotations={"service_name": "bedrock", "operation": "InvokeModel", "use_case": "education-research"},

        ):

            response = bedrock_client.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "inputText": prompt,
                "textGenerationConfig": {
                    "maxTokenCount": 1024,
                    "temperature": 0.1,
                },
            }),
        )
        response_json = json.loads(response["body"].read())

        if "results" in response_json:
            output_text = response_json["results"][0].get("outputText", "")
        elif "content" in response_json:
            output_text = response_json["content"][0].get("text", "")
        else:
            output_text = ""

        # JSON 解析
        if "```json" in output_text:
            json_str = output_text.split("```json")[1].split("```")[0].strip()
        elif "```" in output_text:
            json_str = output_text.split("```")[1].split("```")[0].strip()
        else:
            json_str = output_text.strip()

        return json.loads(json_str)
    except Exception as e:
        logger.warning("Bedrock classification failed: %s", e)
        return {
            "domain": "Other",
            "confidence": 0.0,
            "summary": "",
            "keywords": [],
        }


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """論文分類（Comprehend + Bedrock）

    Input:
        {
            "file_key": "papers/research_2026.pdf",
            "extracted_text": "..."
        }

    Output:
        {
            "status": "SUCCESS",
            "file_key": "...",
            "classification": {
                "domain": "Computer Science",
                "confidence": 0.92,
                "summary": "...",
                "keywords": [...]
            },
            "entities": [...],
            "key_phrases": [...],
            "output_key": "..."
        }
    """
    file_key = event.get("file_key", "")
    extracted_text = event.get("extracted_text", "")

    model_id = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")

    logger.info(
        "Classification started: file_key=%s, text_length=%d",
        file_key,
        len(extracted_text),
    )

    # Comprehend でエンティティ抽出
    comprehend_client = boto3.client("comprehend")
    entities = extract_entities_with_comprehend(comprehend_client, extracted_text)
    key_phrases = detect_key_phrases(comprehend_client, extracted_text)

    # Bedrock で研究ドメイン分類
    bedrock_client = boto3.client("bedrock-runtime")
    classification = _classify_domain_with_bedrock(
        bedrock_client, extracted_text, model_id
    )

    # 出力キー生成
    now = datetime.now(timezone.utc)
    file_stem = PurePosixPath(file_key).stem
    output_key = f"classification/{now.strftime('%Y/%m/%d')}/{file_stem}_class.json"

    # 結果を S3 出力バケットに書き込み
    result = {
        "status": "SUCCESS",
        "file_key": file_key,
        "classification": classification,
        "entities": entities,
        "key_phrases": key_phrases,
        "output_key": output_key,
        "classified_at": now.isoformat(),
    }

    output_writer = OutputWriter.from_env()
    output_writer.put_json(key=output_key, data=result)

    logger.info(
        "Classification completed: file_key=%s, domain=%s, entities=%d",
        file_key,
        classification.get("domain", "Unknown"),
        len(entities),
    )


    # EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="classification")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "education-research"))
    metrics.put_metric("FilesProcessed", 1.0, "Count")
    metrics.flush()

    return result
