"""NPO・非営利団体 (UC24) Grant Extractor Lambda ハンドラ

助成金申請書から申請者情報、予算要求、プロジェクト説明を抽出する。

処理フロー:
    1. S3 AP からドキュメント取得
    2. Textract でテキスト・フォーム抽出
    3. Bedrock で構造化データ抽出 (申請者情報, 予算, プロジェクト説明)
    4. 結果を S3 出力バケットに保存

抽出項目 (Requirement 8.2):
    - applicant_info: 申請者名, 団体名, 連絡先
    - budget: 予算総額, 費目別内訳
    - project_description: プロジェクト概要, 目標, 期間

エラーハンドリング (Requirement 8.5):
    未認識フォーマットの場合はメタデータをログに記録し、
    バッチ処理を中断せずにスキップする。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
    CROSS_REGION_TEXTRACT_REGION: Textract リージョン (default: "us-east-1")
    BEDROCK_MODEL_ID: Bedrock モデル ID (default: "anthropic.claude-haiku-4-5-20251001-v1:0")
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

# Bedrock プロンプトテンプレート (助成金申請書情報抽出用)
GRANT_EXTRACTION_PROMPT = """以下の助成金申請書のテキストから、構造化された情報を抽出してください。

以下のJSON形式で出力してください:
{{
  "applicant_info": {{
    "applicant_name": "<申請者名 (個人名)>",
    "organization_name": "<団体名/法人名>",
    "contact_email": "<連絡先メール (見つかれば)>",
    "contact_phone": "<連絡先電話番号 (見つかれば)>",
    "representative": "<代表者名 (見つかれば)>"
  }},
  "budget": {{
    "total_amount": <予算総額 (数値)>,
    "currency": "<通貨 (JPY/USD等)>",
    "breakdown": [
      {{"item": "<費目名>", "amount": <金額>}}
    ]
  }},
  "project_description": {{
    "title": "<プロジェクト名>",
    "summary": "<プロジェクト概要 (200字以内)>",
    "objectives": ["<目標1>", "<目標2>"],
    "duration": "<実施期間>",
    "target_beneficiaries": "<対象受益者>"
  }}
}}

情報が見つからないフィールドは null としてください。

テキスト:
{text}
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


def extract_grant_info_with_bedrock(
    text: str,
    bedrock_client,
    model_id: str,
) -> dict:
    """Bedrock でテキストから助成金申請書情報を抽出する。

    Args:
        text: 入力テキスト
        bedrock_client: Bedrock Runtime boto3 クライアント
        model_id: Bedrock モデル ID

    Returns:
        dict: 抽出された構造化情報
    """
    if not text or len(text.strip()) < 20:
        return {}

    # テキストを最大 10000 文字に制限
    truncated_text = text[:10000]
    prompt = GRANT_EXTRACTION_PROMPT.format(text=truncated_text)

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

    return _parse_grant_json(content_text)


def _parse_grant_json(text: str) -> dict:
    """Bedrock レスポンスから JSON オブジェクトを抽出する。

    Args:
        text: Bedrock レスポンステキスト

    Returns:
        dict: パースされた助成金情報
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
        logger.warning("Failed to parse grant info JSON from Bedrock response")

    return {}


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Grant Extractor Lambda

    助成金申請書から構造化情報を抽出する。

    Input event:
        - Key: S3 オブジェクトキー
        - Size: ファイルサイズ
        - doc_type: "grant_application"
        - program_area: プログラムエリア
        - submission_date: 提出日

    Returns:
        dict: status, key, extracted_info, errors
    """
    key = event.get("Key", "")
    program_area = event.get("program_area", "general")
    submission_date = event.get("submission_date")

    logger.info(
        "Processing grant application: key=%s, program_area=%s, submission_date=%s",
        key,
        program_area,
        submission_date,
    )

    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    s3ap_output = S3ApHelper(os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ["S3_ACCESS_POINT"]))
    textract_region = os.environ.get("CROSS_REGION_TEXTRACT_REGION", "us-east-1")
    model_id = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-haiku-4-5-20251001-v1:0")

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

        # Step 3: Bedrock で構造化情報抽出
        with xray_subsegment(
            name="bedrock_extract_grant_info",
            annotations={
                "service_name": "bedrock",
                "operation": "InvokeModel",
                "use_case": "nonprofit-grant-management",
            },
        ):
            grant_info = extract_grant_info_with_bedrock(extracted_text, bedrock_client, model_id)

        # メタデータ追加
        grant_info["_metadata"] = {
            "source_key": key,
            "program_area": program_area,
            "submission_date": submission_date,
            "extracted_text_length": len(extracted_text),
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }

        # 結果を S3 に出力
        result_key = f"results/grants/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{os.path.basename(key)}.json"
        s3ap_output.put_object(
            key=result_key,
            body=json.dumps(grant_info, ensure_ascii=False, default=str),
            content_type="application/json",
        )

        logger.info(
            "Grant extraction completed: key=%s, result_key=%s",
            key,
            result_key,
        )

        # EMF メトリクス
        metrics_emf = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="processing")
        metrics_emf.set_dimension("UseCase", "nonprofit-grant-management")
        metrics_emf.set_dimension("Stage", "grant-extractor")
        metrics_emf.put_metric("SuccessCount", 1.0, "Count")
        metrics_emf.flush()

        return {
            "status": "success",
            "key": key,
            "result_key": result_key,
            "extracted_info": grant_info,
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

        logger.error("Grant extraction failed: key=%s, error=%s", key, str(e))

        # エラーを出力バケットに記録
        error_key = f"errors/grants/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{os.path.basename(key)}.json"
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
        metrics_emf.set_dimension("Stage", "grant-extractor")
        metrics_emf.put_metric("ErrorCount", 1.0, "Count")
        metrics_emf.flush()

        return {
            "status": "error",
            "key": key,
            "errors": [error_detail],
        }
