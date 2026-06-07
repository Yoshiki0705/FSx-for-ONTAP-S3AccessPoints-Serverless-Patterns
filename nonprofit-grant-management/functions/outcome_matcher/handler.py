"""NPO・非営利団体 (UC24) Outcome Matcher Lambda ハンドラ

活動報告書から成果メトリクスを抽出し、元の助成金目標とマッチングする。

処理フロー:
    1. S3 AP から活動報告書取得
    2. Comprehend で重要フレーズ・エンティティ抽出
    3. Bedrock で成果メトリクス抽出 + 目標マッチング
    4. 結果を S3 出力バケットに保存

抽出項目 (Requirement 8.3):
    - outcome_metrics: 達成指標 (数値, 定性的成果)
    - objective_matching: 元の助成金目標との対応付け
    - achievement_rate: 目標達成率

エラーハンドリング (Requirement 8.5):
    未認識フォーマットの場合はメタデータをログに記録し、
    バッチ処理を中断せずにスキップする。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
    CROSS_REGION_TEXTRACT_REGION: Textract リージョン (default: "us-east-1")
    BEDROCK_MODEL_ID: Bedrock モデル ID (default: "anthropic.claude-haiku-4-5-20251001-v1:0")
    COMPREHEND_LANGUAGE_CODE: Comprehend 言語コード (default: "ja")
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler
from shared.retry_handler import retry_with_backoff, RetryConfig
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)

# 対応するドキュメント拡張子
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".docx", ".doc"})

# Bedrock プロンプトテンプレート (成果マッチング用)
OUTCOME_MATCHING_PROMPT = """以下の活動報告書のテキストから、成果メトリクスを抽出し、
助成金の目標との対応関係を分析してください。

以下のJSON形式で出力してください:
{{
  "outcome_metrics": [
    {{
      "metric_name": "<指標名>",
      "achieved_value": "<達成した値 (数値または定性的記述)>",
      "target_value": "<目標値 (記載があれば)>",
      "unit": "<単位 (人, 件, % 等)>",
      "category": "<カテゴリ (参加者数/実施回数/成果物/その他)>"
    }}
  ],
  "objective_matching": [
    {{
      "original_objective": "<元の目標>",
      "achieved_outcome": "<対応する成果>",
      "match_confidence": <マッチング信頼度 0.0-1.0>,
      "achievement_status": "<achieved|partially_achieved|not_achieved>"
    }}
  ],
  "overall_achievement_rate": <全体達成率 0-100>,
  "summary": "<活動成果の要約 (200字以内)>"
}}

情報が見つからないフィールドは null としてください。

テキスト:
{text}

抽出されたキーフレーズ:
{key_phrases}
"""


def is_supported_format(key: str) -> bool:
    """ファイルが対応フォーマットかを判定する。

    Args:
        key: S3 オブジェクトキー

    Returns:
        bool: 対応フォーマットの場合 True
    """
    if not key:
        return False
    dot_index = key.rfind(".")
    if dot_index == -1:
        return False
    extension = key[dot_index:].lower()
    return extension in SUPPORTED_EXTENSIONS


def extract_text_with_textract(
    document_bytes: bytes,
    textract_client,
) -> str:
    """Textract でドキュメントからテキストを抽出する。

    Args:
        document_bytes: ドキュメントバイナリ
        textract_client: Textract boto3 クライアント

    Returns:
        str: 抽出されたテキスト
    """

    @retry_with_backoff(config=RetryConfig(max_attempts=3))
    def _call_textract():
        return textract_client.analyze_document(
            Document={"Bytes": document_bytes},
            FeatureTypes=["FORMS", "TABLES"],
        )

    response = _call_textract()

    lines: list[str] = []
    for block in response.get("Blocks", []):
        if block.get("BlockType") == "LINE":
            text = block.get("Text", "")
            if text:
                lines.append(text)

    return "\n".join(lines)


def extract_key_phrases_with_comprehend(
    text: str,
    comprehend_client,
    language_code: str,
) -> list[str]:
    """Comprehend でキーフレーズを抽出する。

    Args:
        text: 入力テキスト
        comprehend_client: Comprehend boto3 クライアント
        language_code: 言語コード

    Returns:
        list[str]: 抽出されたキーフレーズリスト
    """
    if not text or len(text.strip()) < 10:
        return []

    # Comprehend は最大 5000 バイト (UTF-8)
    truncated_text = text[:5000]

    @retry_with_backoff(config=RetryConfig(max_attempts=3))
    def _call_comprehend():
        return comprehend_client.detect_key_phrases(
            Text=truncated_text,
            LanguageCode=language_code,
        )

    response = _call_comprehend()

    key_phrases = []
    for phrase in response.get("KeyPhrases", []):
        if phrase.get("Score", 0) >= 0.7:
            key_phrases.append(phrase.get("Text", ""))

    return key_phrases[:30]  # 最大 30 フレーズ


def match_outcomes_with_bedrock(
    text: str,
    key_phrases: list[str],
    bedrock_client,
    model_id: str,
) -> dict:
    """Bedrock で成果メトリクス抽出と目標マッチングを行う。

    Args:
        text: 入力テキスト
        key_phrases: Comprehend で抽出されたキーフレーズ
        bedrock_client: Bedrock Runtime boto3 クライアント
        model_id: Bedrock モデル ID

    Returns:
        dict: 成果マッチング結果
    """
    if not text or len(text.strip()) < 20:
        return {}

    truncated_text = text[:10000]
    phrases_str = ", ".join(key_phrases) if key_phrases else "(なし)"

    prompt = OUTCOME_MATCHING_PROMPT.format(
        text=truncated_text,
        key_phrases=phrases_str,
    )

    @retry_with_backoff(config=RetryConfig(max_attempts=3))
    def _call_bedrock():
        return bedrock_client.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 4096,
                    "messages": [{"role": "user", "content": prompt}],
                }
            ),
        )

    response = _call_bedrock()
    response_body = json.loads(response["body"].read())

    content_text = ""
    for content_block in response_body.get("content", []):
        if content_block.get("type") == "text":
            content_text += content_block.get("text", "")

    return _parse_outcome_json(content_text)


def _parse_outcome_json(text: str) -> dict:
    """Bedrock レスポンスから JSON オブジェクトを抽出する。

    Args:
        text: Bedrock レスポンステキスト

    Returns:
        dict: パースされた成果マッチング結果
    """
    start_idx = text.find("{")
    end_idx = text.rfind("}")

    if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
        return {}

    json_str = text[start_idx : end_idx + 1]

    try:
        parsed = json.loads(json_str)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        logger.warning("Failed to parse outcome JSON from Bedrock response")

    return {}


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Outcome Matcher Lambda

    活動報告書から成果メトリクスを抽出し、目標とマッチングする。

    Input event:
        - Key: S3 オブジェクトキー
        - Size: ファイルサイズ
        - doc_type: "activity_report"
        - program_area: プログラムエリア
        - submission_date: 提出日

    Returns:
        dict: status, key, outcome_data, errors
    """
    key = event.get("Key", "")
    program_area = event.get("program_area", "general")
    submission_date = event.get("submission_date")

    logger.info(
        "Processing activity report: key=%s, program_area=%s, submission_date=%s",
        key,
        program_area,
        submission_date,
    )

    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    s3ap_output = S3ApHelper(os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ["S3_ACCESS_POINT"]))
    textract_region = os.environ.get("CROSS_REGION_TEXTRACT_REGION", "us-east-1")
    model_id = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-haiku-4-5-20251001-v1:0")
    language_code = os.environ.get("COMPREHEND_LANGUAGE_CODE", "ja")

    # Requirement 8.5: 未認識フォーマットのチェック
    if not is_supported_format(key):
        logger.warning(
            "Unrecognized document format, skipping: key=%s, program_area=%s",
            key,
            program_area,
        )
        return {
            "status": "skipped",
            "key": key,
            "reason": "unrecognized_format",
            "metadata": {
                "program_area": program_area,
                "submission_date": submission_date,
                "size": event.get("Size", 0),
            },
            "errors": [],
        }

    textract_client = boto3.client("textract", region_name=textract_region)
    comprehend_client = boto3.client("comprehend")
    bedrock_client = boto3.client("bedrock-runtime")

    try:
        # Step 1: ドキュメント取得
        with xray_subsegment(
            name="s3ap_get_document",
            annotations={
                "service_name": "s3",
                "operation": "GetObject",
                "use_case": "nonprofit-grant-management",
            },
        ):
            doc_bytes = s3ap.get_object_bytes(key=key)

        # Step 2: Textract でテキスト抽出
        with xray_subsegment(
            name="textract_extract_text",
            annotations={
                "service_name": "textract",
                "operation": "AnalyzeDocument",
                "use_case": "nonprofit-grant-management",
            },
        ):
            extracted_text = extract_text_with_textract(doc_bytes, textract_client)

        # Step 3: Comprehend でキーフレーズ抽出
        with xray_subsegment(
            name="comprehend_key_phrases",
            annotations={
                "service_name": "comprehend",
                "operation": "DetectKeyPhrases",
                "use_case": "nonprofit-grant-management",
            },
        ):
            key_phrases = extract_key_phrases_with_comprehend(extracted_text, comprehend_client, language_code)

        # Step 4: Bedrock で成果マッチング
        with xray_subsegment(
            name="bedrock_outcome_matching",
            annotations={
                "service_name": "bedrock",
                "operation": "InvokeModel",
                "use_case": "nonprofit-grant-management",
            },
        ):
            outcome_data = match_outcomes_with_bedrock(extracted_text, key_phrases, bedrock_client, model_id)

        # メタデータ追加
        outcome_data["_metadata"] = {
            "source_key": key,
            "program_area": program_area,
            "submission_date": submission_date,
            "extracted_text_length": len(extracted_text),
            "key_phrases_count": len(key_phrases),
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }

        # 結果を S3 に出力
        result_key = f"results/outcomes/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{os.path.basename(key)}.json"
        s3ap_output.put_object(
            key=result_key,
            body=json.dumps(outcome_data, ensure_ascii=False, default=str),
            content_type="application/json",
        )

        logger.info(
            "Outcome matching completed: key=%s, result_key=%s, metrics_count=%d, objectives_matched=%d",
            key,
            result_key,
            len(outcome_data.get("outcome_metrics", [])),
            len(outcome_data.get("objective_matching", [])),
        )

        # EMF メトリクス
        metrics_emf = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="processing")
        metrics_emf.set_dimension("UseCase", "nonprofit-grant-management")
        metrics_emf.set_dimension("Stage", "outcome-matcher")
        metrics_emf.put_metric("SuccessCount", 1.0, "Count")
        metrics_emf.put_metric(
            "OutcomeMetrics",
            float(len(outcome_data.get("outcome_metrics", []))),
            "Count",
        )
        metrics_emf.flush()

        return {
            "status": "success",
            "key": key,
            "result_key": result_key,
            "outcome_data": outcome_data,
            "errors": [],
        }

    except Exception as e:
        error_detail = {
            "path": key,
            "error_type": type(e).__name__,
            "details": str(e),
            "program_area": program_area,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        logger.error("Outcome matching failed: key=%s, error=%s", key, str(e))

        # エラーを出力バケットに記録
        error_key = f"errors/outcomes/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{os.path.basename(key)}.json"
        try:
            s3ap_output.put_object(
                key=error_key,
                body=json.dumps(error_detail, ensure_ascii=False, default=str),
                content_type="application/json",
            )
        except Exception as write_err:
            logger.error("Failed to write error record: %s", str(write_err))

        # EMF メトリクス
        metrics_emf = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="processing")
        metrics_emf.set_dimension("UseCase", "nonprofit-grant-management")
        metrics_emf.set_dimension("Stage", "outcome-matcher")
        metrics_emf.put_metric("ErrorCount", 1.0, "Count")
        metrics_emf.flush()

        return {
            "status": "error",
            "key": key,
            "errors": [error_detail],
        }
