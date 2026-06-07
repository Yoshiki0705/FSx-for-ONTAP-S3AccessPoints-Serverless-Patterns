"""広告・マーケティング業界 (UC19) Text Compliance Lambda ハンドラ

テキストオーバーレイからの抽出と、ブランド用語ガイドラインに対するコンプライアンス検証を行う。

処理フロー:
    1. S3 AP からファイル取得
    2. Textract (Cross-Region: us-east-1) によるテキスト抽出
    3. Bedrock によるブランド用語ガイドラインとの照合
    4. コンプライアンス結果割り当て ("compliant" / "non-compliant")
    5. コンプライアンスルール JSON に対する追加チェック

Requirements: 3.3, 3.4, 3.7, 13.6

Textract:
    Cross-Region クライアント (us-east-1) を使用。
    設計ドキュメントの指定に従い TEXTRACT_REGION 環境変数で制御。

Bedrock:
    ブランド用語ガイドライン JSON を S3 から読み込み、
    抽出テキストとガイドラインを Bedrock に渡してコンプライアンス判定を行う。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    OUTPUT_BUCKET: 出力バケット名
    BRAND_GUIDELINES_S3_KEY: ブランドガイドライン JSON の S3 キー
    COMPLIANCE_RULES_S3_KEY: コンプライアンスルール JSON の S3 キー
    BEDROCK_MODEL_ID: Bedrock モデル ID (デフォルト: anthropic.claude-3-haiku-20240307-v1:0)
    TEXTRACT_REGION: Textract クライアントリージョン (デフォルト: us-east-1)
    MODERATION_CONFIDENCE_THRESHOLD: モデレーション確信度閾値 (デフォルト: 80)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from shared.exceptions import lambda_error_handler
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler
from shared.retry_handler import (
    execute_with_retry,
    RetryConfig,
    RetryExhaustedError,
    categorize_error,
    ErrorCategory,
)
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)

# AI/ML サービスリトライ設定
AI_SERVICE_RETRY_CONFIG = RetryConfig(
    max_attempts=3,
    initial_interval_seconds=2.0,
    backoff_rate=2.0,
)


def get_textract_client():
    """Cross-Region Textract クライアントを作成する。

    設計ドキュメントの指定に従い、Textract は us-east-1 で実行する。
    TEXTRACT_REGION 環境変数で制御可能。

    Returns:
        boto3.client: Textract クライアント (Cross-Region)
    """
    textract_region = os.environ.get("TEXTRACT_REGION", "us-east-1")
    boto_config = Config(
        connect_timeout=10,
        read_timeout=60,
    )
    return boto3.client(
        "textract",
        region_name=textract_region,
        config=boto_config,
    )


def get_bedrock_client():
    """Bedrock Runtime クライアントを作成する。

    Returns:
        boto3.client: Bedrock Runtime クライアント
    """
    return boto3.client("bedrock-runtime")


def extract_text_with_textract(
    textract_client,
    image_bytes: bytes,
) -> list[dict[str, Any]]:
    """Textract でテキスト抽出を行う。

    DetectDocumentText API を使用して画像/文書からテキストを抽出する。

    Args:
        textract_client: boto3 Textract クライアント (Cross-Region)
        image_bytes: 画像/文書のバイトデータ

    Returns:
        list[dict]: 抽出されたテキストブロックのリスト
            各要素: {"text": str, "confidence": float, "block_type": str}

    Raises:
        RetryExhaustedError: リトライ上限到達時
        Exception: その他のエラー
    """

    def _call():
        return textract_client.detect_document_text(Document={"Bytes": image_bytes})

    response = execute_with_retry(_call, config=AI_SERVICE_RETRY_CONFIG)

    text_blocks = []
    for block in response.get("Blocks", []):
        if block.get("BlockType") in ("LINE", "WORD"):
            text_blocks.append(
                {
                    "text": block.get("Text", ""),
                    "confidence": round(block.get("Confidence", 0.0), 2),
                    "block_type": block.get("BlockType", ""),
                }
            )

    return text_blocks


def load_brand_guidelines(s3_client, output_bucket: str, guidelines_key: str) -> dict[str, Any]:
    """ブランド用語ガイドライン JSON を S3 から読み込む。

    ガイドライン JSON 構造例:
    {
        "brand_name": "ExampleBrand",
        "required_terms": ["ExampleBrand™", "公式"],
        "prohibited_terms": ["安い", "最安値", "No.1"],
        "tone_guidelines": "フォーマルかつプロフェッショナルなトーンで...",
        "disclaimer_rules": ["広告であることの明示が必要"]
    }

    Args:
        s3_client: boto3 S3 クライアント
        output_bucket: ガイドラインが格納されたバケット名
        guidelines_key: ガイドライン JSON の S3 キー

    Returns:
        dict: ブランドガイドライン (空の場合はデフォルト)
    """
    if not guidelines_key:
        return {}

    try:
        response = s3_client.get_object(Bucket=output_bucket, Key=guidelines_key)
        content = response["Body"].read().decode("utf-8")
        response["Body"].close()
        return json.loads(content)
    except ClientError as e:
        logger.warning(
            "Failed to load brand guidelines from s3://%s/%s: %s",
            output_bucket,
            guidelines_key,
            str(e),
        )
        return {}
    except (json.JSONDecodeError, Exception) as e:
        logger.warning("Failed to parse brand guidelines JSON: %s", str(e))
        return {}


def load_compliance_rules(s3_client, output_bucket: str, rules_key: str) -> dict[str, Any]:
    """コンプライアンスルール JSON を S3 から読み込む。

    Args:
        s3_client: boto3 S3 クライアント
        output_bucket: ルールファイルが格納されたバケット名
        rules_key: ルール JSON の S3 キー

    Returns:
        dict: コンプライアンスルール
    """
    if not rules_key:
        return {}

    try:
        response = s3_client.get_object(Bucket=output_bucket, Key=rules_key)
        content = response["Body"].read().decode("utf-8")
        response["Body"].close()
        return json.loads(content)
    except ClientError as e:
        logger.warning(
            "Failed to load compliance rules from s3://%s/%s: %s",
            output_bucket,
            rules_key,
            str(e),
        )
        return {}
    except (json.JSONDecodeError, Exception) as e:
        logger.warning("Failed to parse compliance rules JSON: %s", str(e))
        return {}


def validate_brand_terminology_with_bedrock(
    bedrock_client,
    extracted_text: str,
    brand_guidelines: dict[str, Any],
    model_id: str,
) -> dict[str, Any]:
    """Bedrock を使用してブランド用語ガイドラインに対する検証を行う。

    Requirement 3.3: 抽出テキストをブランド用語ガイドラインと照合し、
    "compliant" or "non-compliant" を判定。マッチした用語を一覧化する。

    Args:
        bedrock_client: boto3 Bedrock Runtime クライアント
        extracted_text: 抽出されたテキスト（連結文字列）
        brand_guidelines: ブランドガイドライン辞書
        model_id: Bedrock モデル ID

    Returns:
        dict: 検証結果
            {
                "compliance_result": "compliant" | "non-compliant",
                "matched_terms": [...],
                "violations": [...],
                "reasoning": str
            }
    """
    if not extracted_text.strip():
        return {
            "compliance_result": "compliant",
            "matched_terms": [],
            "violations": [],
            "reasoning": "No text detected in asset",
        }

    if not brand_guidelines:
        return {
            "compliance_result": "compliant",
            "matched_terms": [],
            "violations": [],
            "reasoning": "No brand guidelines configured",
        }

    # Bedrock プロンプト構築
    prompt = _build_brand_validation_prompt(extracted_text, brand_guidelines)

    def _call():
        body = json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1024,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            }
        )
        return bedrock_client.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=body,
        )

    try:
        response = execute_with_retry(_call, config=AI_SERVICE_RETRY_CONFIG)
        response_body = json.loads(response["body"].read())

        # レスポンスからコンプライアンス判定を抽出
        content_text = ""
        for content_block in response_body.get("content", []):
            if content_block.get("type") == "text":
                content_text += content_block.get("text", "")

        return _parse_bedrock_compliance_response(content_text, extracted_text, brand_guidelines)

    except RetryExhaustedError as e:
        logger.error("Bedrock brand validation failed after retries: %s", str(e))
        raise
    except Exception as e:
        logger.error("Bedrock brand validation failed: %s", str(e))
        raise


def _build_brand_validation_prompt(extracted_text: str, brand_guidelines: dict) -> str:
    """ブランド検証用の Bedrock プロンプトを構築する。

    Args:
        extracted_text: 抽出されたテキスト
        brand_guidelines: ブランドガイドライン辞書

    Returns:
        str: プロンプト文字列
    """
    guidelines_str = json.dumps(brand_guidelines, ensure_ascii=False, indent=2)

    return f"""あなたはブランドコンプライアンスの専門家です。
以下のクリエイティブアセットから抽出されたテキストを、ブランド用語ガイドラインに照らして検証してください。

## 抽出テキスト:
{extracted_text}

## ブランド用語ガイドライン:
{guidelines_str}

## 検証指示:
1. テキスト内にガイドラインの「prohibited_terms」(禁止用語) が含まれているか確認
2. テキスト内に「required_terms」(必須用語) が適切に使用されているか確認
3. 全体的なトーンが「tone_guidelines」に準拠しているか確認

## 出力形式 (必ず以下のJSON形式で回答):
```json
{{
    "compliance_result": "compliant" または "non-compliant",
    "matched_prohibited_terms": ["見つかった禁止用語のリスト"],
    "matched_required_terms": ["見つかった必須用語のリスト"],
    "missing_required_terms": ["不足している必須用語のリスト"],
    "reasoning": "判定理由の説明"
}}
```"""


def _parse_bedrock_compliance_response(
    response_text: str,
    extracted_text: str,
    brand_guidelines: dict,
) -> dict[str, Any]:
    """Bedrock レスポンスからコンプライアンス判定を解析する。

    JSON 形式のレスポンスを試行し、失敗した場合はルールベースのフォールバックを行う。

    Args:
        response_text: Bedrock のレスポンステキスト
        extracted_text: 元の抽出テキスト
        brand_guidelines: ブランドガイドライン辞書

    Returns:
        dict: コンプライアンス検証結果
    """
    # JSON 抽出を試行
    try:
        # ```json ... ``` ブロックを探す
        json_start = response_text.find("{")
        json_end = response_text.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            json_str = response_text[json_start:json_end]
            parsed = json.loads(json_str)

            compliance_result = parsed.get("compliance_result", "compliant")
            matched_terms = parsed.get("matched_prohibited_terms", []) + parsed.get("matched_required_terms", [])
            violations = []

            # 禁止用語が見つかった場合
            for term in parsed.get("matched_prohibited_terms", []):
                violations.append(
                    {
                        "type": "prohibited_term_found",
                        "term": term,
                    }
                )

            # 必須用語が不足している場合
            for term in parsed.get("missing_required_terms", []):
                violations.append(
                    {
                        "type": "required_term_missing",
                        "term": term,
                    }
                )

            return {
                "compliance_result": compliance_result,
                "matched_terms": matched_terms,
                "violations": violations,
                "reasoning": parsed.get("reasoning", ""),
            }
    except (json.JSONDecodeError, ValueError):
        pass

    # フォールバック: ルールベースの簡易チェック
    return _rule_based_brand_check(extracted_text, brand_guidelines)


def _rule_based_brand_check(
    extracted_text: str,
    brand_guidelines: dict,
) -> dict[str, Any]:
    """ルールベースのブランド用語チェック（Bedrock フォールバック）。

    Args:
        extracted_text: 抽出テキスト
        brand_guidelines: ブランドガイドライン

    Returns:
        dict: コンプライアンス検証結果
    """
    violations = []
    matched_terms = []
    text_lower = extracted_text.lower()

    # 禁止用語チェック
    for term in brand_guidelines.get("prohibited_terms", []):
        if term.lower() in text_lower:
            violations.append(
                {
                    "type": "prohibited_term_found",
                    "term": term,
                }
            )
            matched_terms.append(term)

    # 必須用語チェック
    for term in brand_guidelines.get("required_terms", []):
        if term.lower() in text_lower:
            matched_terms.append(term)
        else:
            violations.append(
                {
                    "type": "required_term_missing",
                    "term": term,
                }
            )

    compliance_result = "non-compliant" if violations else "compliant"

    return {
        "compliance_result": compliance_result,
        "matched_terms": matched_terms,
        "violations": violations,
        "reasoning": "Rule-based check (Bedrock response parse failed)",
    }


def check_compliance_rules(
    text_blocks: list[dict],
    file_size: int,
    compliance_rules: dict[str, Any],
) -> dict[str, Any]:
    """コンプライアンスルール JSON に対するテキスト固有チェック。

    Requirement 3.4: required disclaimer keywords チェック等。

    Args:
        text_blocks: 抽出されたテキストブロック
        file_size: ファイルサイズ (bytes)
        compliance_rules: コンプライアンスルール辞書

    Returns:
        dict: 追加チェック結果
    """
    violations = []
    checks_performed = []

    # 必須免責事項キーワードチェック
    required_keywords = compliance_rules.get("required_disclaimer_keywords", [])
    if required_keywords:
        checks_performed.append("required_disclaimer_keywords")
        all_text = " ".join(block.get("text", "") for block in text_blocks if block.get("block_type") == "LINE")
        for keyword in required_keywords:
            if keyword.lower() not in all_text.lower():
                violations.append(
                    {
                        "type": "missing_disclaimer_keyword",
                        "keyword": keyword,
                    }
                )

    # サイズ制約チェック
    size_constraints = compliance_rules.get("size_constraints", {})
    if size_constraints:
        checks_performed.append("size_constraints")
        max_bytes = size_constraints.get("max_bytes")
        if max_bytes and file_size > max_bytes:
            violations.append(
                {
                    "type": "file_size_exceeded",
                    "max_bytes": max_bytes,
                    "actual_bytes": file_size,
                }
            )

    return {
        "violations": violations,
        "checks_performed": checks_performed,
    }


def record_processing_failure(
    s3_client,
    output_bucket: str,
    file_key: str,
    error_type: str,
    error_details: str,
) -> None:
    """処理失敗を記録する。

    Requirement 3.7: corruption/unsupported format/service error 時に
    file path, error type, timestamp を記録して処理を継続。

    Args:
        s3_client: boto3 S3 クライアント
        output_bucket: 出力バケット名
        file_key: 失敗したファイルのキー
        error_type: エラータイプ
        error_details: エラー詳細
    """
    error_record = {
        "file_path": file_key,
        "error_type": error_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "details": error_details,
    }

    date_prefix = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    file_basename = file_key.rsplit("/", 1)[-1] if "/" in file_key else file_key
    error_key = f"errors/text_compliance/{date_prefix}/{file_basename}.error.json"

    try:
        s3_client.put_object(
            Bucket=output_bucket,
            Key=error_key,
            Body=json.dumps(error_record, ensure_ascii=False),
            ContentType="application/json",
        )
        logger.info("Processing failure recorded: %s → %s", file_key, error_key)
    except Exception as e:
        logger.error("Failed to record processing failure for %s: %s", file_key, str(e))


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Text Compliance Lambda ハンドラ

    Step Functions Map State から呼び出され、クリエイティブアセットの
    テキストオーバーレイを抽出し、ブランドガイドラインとの照合を行う。

    Event 形式:
        {
            "key": "creatives/2026/banner.jpg",
            "size": 2048000,
            "manifest_key": "manifests/2026/06/02/xxx.json"
        }

    Processing Flow:
        1. S3 AP からファイル取得
        2. Textract (Cross-Region: us-east-1) によるテキスト抽出
        3. ブランドガイドライン JSON 読み込み
        4. Bedrock によるブランド用語コンプライアンス検証
        5. コンプライアンスルール JSON に対する追加チェック
        6. 結果を S3 出力バケットに書き出し
        7. エラー時は記録して継続

    Returns:
        dict: 処理結果
    """
    file_key = event.get("key", event.get("Key", ""))
    file_size = event.get("size", event.get("Size", 0))

    logger.info(
        "Text Compliance started: key=%s, size=%d",
        file_key,
        file_size,
    )

    # 環境設定
    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    output_bucket = os.environ.get("OUTPUT_BUCKET", "")
    brand_guidelines_key = os.environ.get("BRAND_GUIDELINES_S3_KEY", "")
    compliance_rules_key = os.environ.get("COMPLIANCE_RULES_S3_KEY", "")
    model_id = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")

    s3_client = boto3.client("s3")

    # Step 1: ファイル取得
    try:
        with xray_subsegment(
            name="s3ap_get_object",
            annotations={
                "service_name": "s3",
                "operation": "GetObject",
                "use_case": "adtech-creative-management",
            },
        ):
            response = s3ap.get_object(file_key)
            file_bytes = response["Body"].read()
            response["Body"].close()
    except Exception as e:
        error_type = "retrieval_error"
        logger.error("Failed to retrieve file %s: %s", file_key, str(e))
        if output_bucket:
            record_processing_failure(s3_client, output_bucket, file_key, error_type, str(e))
        return {
            "key": file_key,
            "status": "error",
            "error_type": error_type,
            "error_details": str(e),
        }

    # Step 2: Textract テキスト抽出 (Cross-Region: us-east-1)
    text_blocks = []
    try:
        textract_client = get_textract_client()
        with xray_subsegment(
            name="textract_detect_text",
            annotations={
                "service_name": "textract",
                "operation": "DetectDocumentText",
                "use_case": "adtech-creative-management",
                "region": os.environ.get("TEXTRACT_REGION", "us-east-1"),
            },
        ):
            text_blocks = extract_text_with_textract(textract_client, file_bytes)
    except RetryExhaustedError as e:
        logger.error("Textract failed after retries for %s: %s", file_key, str(e))
        if output_bucket:
            record_processing_failure(s3_client, output_bucket, file_key, "service_error_textract", str(e))
        return {
            "key": file_key,
            "status": "error",
            "error_type": "service_error",
            "error_details": f"Textract retry exhausted: {e}",
        }
    except Exception as e:
        # 破損/未対応フォーマット (Requirement 3.7)
        error_category = categorize_error(e)
        if error_category == ErrorCategory.PARSE_ERROR:
            error_type = "corruption_or_unsupported_format"
        else:
            error_type = "service_error"

        logger.warning("Textract failed for %s (%s): %s", file_key, error_type, str(e))
        if output_bucket:
            record_processing_failure(s3_client, output_bucket, file_key, error_type, str(e))
        return {
            "key": file_key,
            "status": "error",
            "error_type": error_type,
            "error_details": str(e),
        }

    # 抽出テキストを連結
    extracted_text = " ".join(block["text"] for block in text_blocks if block.get("block_type") == "LINE")

    # Step 3: ブランドガイドライン読み込み
    brand_guidelines = {}
    if brand_guidelines_key and output_bucket:
        brand_guidelines = load_brand_guidelines(s3_client, output_bucket, brand_guidelines_key)

    # Step 4: Bedrock によるブランド用語コンプライアンス検証
    brand_compliance = {
        "compliance_result": "compliant",
        "matched_terms": [],
        "violations": [],
        "reasoning": "No brand guidelines configured or no text extracted",
    }

    if extracted_text.strip() and brand_guidelines:
        try:
            bedrock_client = get_bedrock_client()
            with xray_subsegment(
                name="bedrock_brand_validation",
                annotations={
                    "service_name": "bedrock",
                    "operation": "InvokeModel",
                    "use_case": "adtech-creative-management",
                    "model_id": model_id,
                },
            ):
                brand_compliance = validate_brand_terminology_with_bedrock(
                    bedrock_client=bedrock_client,
                    extracted_text=extracted_text,
                    brand_guidelines=brand_guidelines,
                    model_id=model_id,
                )
        except RetryExhaustedError as e:
            logger.error(
                "Bedrock brand validation failed after retries for %s: %s",
                file_key,
                str(e),
            )
            # Bedrock 失敗はルールベースフォールバックを使用
            brand_compliance = _rule_based_brand_check(extracted_text, brand_guidelines)
            brand_compliance["reasoning"] += " (Bedrock retry exhausted, using rule-based fallback)"
        except Exception as e:
            logger.warning("Bedrock brand validation failed for %s: %s", file_key, str(e))
            brand_compliance = _rule_based_brand_check(extracted_text, brand_guidelines)
            brand_compliance["reasoning"] += f" (Bedrock error: {e}, using rule-based fallback)"

    # Step 5: コンプライアンスルール JSON チェック
    compliance_rules = {}
    if compliance_rules_key and output_bucket:
        compliance_rules = load_compliance_rules(s3_client, output_bucket, compliance_rules_key)

    rules_check = check_compliance_rules(
        text_blocks=text_blocks,
        file_size=file_size,
        compliance_rules=compliance_rules,
    )

    # 最終コンプライアンスステータス判定
    all_violations = brand_compliance.get("violations", []) + rules_check.get("violations", [])
    final_compliance_status = (
        "non-compliant" if all_violations else brand_compliance.get("compliance_result", "compliant")
    )

    # Step 6: 結果構築
    result = {
        "key": file_key,
        "status": "success",
        "processing_timestamp": datetime.now(timezone.utc).isoformat(),
        "extracted_text": extracted_text,
        "text_block_count": len(text_blocks),
        "brand_compliance": brand_compliance,
        "rules_compliance": rules_check,
        "final_compliance_status": final_compliance_status,
        "all_violations": all_violations,
        "matched_terms": brand_compliance.get("matched_terms", []),
        "metadata": {
            "model_id": model_id,
            "textract_region": os.environ.get("TEXTRACT_REGION", "us-east-1"),
            "brand_guidelines_key": brand_guidelines_key,
            "compliance_rules_key": compliance_rules_key,
            "file_size": file_size,
        },
    }

    # 結果書き出し
    if output_bucket:
        date_prefix = datetime.now(timezone.utc).strftime("%Y/%m/%d")
        file_basename = file_key.rsplit("/", 1)[-1] if "/" in file_key else file_key
        result_key = f"results/text_compliance/{date_prefix}/{file_basename}.result.json"
        try:
            s3_client.put_object(
                Bucket=output_bucket,
                Key=result_key,
                Body=json.dumps(result, default=str, ensure_ascii=False),
                ContentType="application/json",
            )
        except Exception as e:
            logger.error("Failed to write result for %s: %s", file_key, str(e))

    # Step 7: EMF メトリクス
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="text_compliance")
    metrics.set_dimension("UseCase", "adtech-creative-management")
    metrics.put_metric("TextBlocksExtracted", float(len(text_blocks)), "Count")
    metrics.put_metric("FilesProcessed", 1.0, "Count")
    if final_compliance_status == "non-compliant":
        metrics.put_metric("NonCompliantAssets", 1.0, "Count")
    else:
        metrics.put_metric("NonCompliantAssets", 0.0, "Count")
    metrics.put_metric("ViolationCount", float(len(all_violations)), "Count")
    metrics.flush()

    logger.info(
        "Text Compliance completed: key=%s, text_blocks=%d, compliance=%s, violations=%d",
        file_key,
        len(text_blocks),
        final_compliance_status,
        len(all_violations),
    )

    return result
