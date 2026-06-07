"""サステナビリティ・ESG (UC23) Metrics Extractor Lambda ハンドラ

ESG 文書から定量メトリクスを抽出し、単位正規化を行う。

処理フロー:
    1. S3 AP からドキュメント取得
    2. Textract でテキスト抽出
    3. Bedrock で定量メトリクス抽出 (CO2, エネルギー, 廃棄物, 水)
    4. shared/unit_normalizer.py で単位正規化
    5. 構造化レコード出力

出力レコード (Requirement 7.6):
    - metric_name: メトリクス名
    - value: 数値
    - unit: 正規化された単位
    - source_key: ソースドキュメントキー
    - period: レポート期間
    - category: ESG カテゴリ
    - confidence: 抽出信頼度 (0.0-1.0)

バリデーション (Requirement 7.5):
    - 単位なし → "requires-validation" (reason: "missing_unit")
    - 単位矛盾 → "requires-validation" (reason: "conflicting_units")
    - 範囲外値 → "requires-validation" (reason: "out_of_range")

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
    CROSS_REGION_TEXTRACT_REGION: Textract リージョン (default: "us-east-1")
    BEDROCK_MODEL_ID: Bedrock モデル ID (default: "anthropic.claude-3-haiku-20240307-v1:0")
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

# UC23 ローカル shared モジュール — 動的 import で namespace isolation
import importlib.util
import sys
from pathlib import Path

_uc_normalizer_path = Path(__file__).parent.parent.parent / "shared" / "unit_normalizer.py"
if _uc_normalizer_path.exists():
    _norm_spec = importlib.util.spec_from_file_location("uc23_unit_normalizer", _uc_normalizer_path)
    _norm_mod = importlib.util.module_from_spec(_norm_spec)
    sys.modules["uc23_unit_normalizer"] = _norm_mod
    _norm_spec.loader.exec_module(_norm_mod)
    normalize_value = _norm_mod.normalize_value
    get_supported_categories = _norm_mod.get_supported_categories
    UNIT_NORMALIZATION = _norm_mod.UNIT_NORMALIZATION
else:
    raise ImportError(f"unit_normalizer.py not found at {_uc_normalizer_path}")

logger = logging.getLogger(__name__)

# Bedrock プロンプトテンプレート (メトリクス抽出用)
METRICS_EXTRACTION_PROMPT = """以下のESGレポートのテキストから定量的なメトリクスを抽出してください。

対象メトリクスカテゴリ:
- co2_emissions: CO2排出量 (kg, t, Mt 等)
- energy_usage: エネルギー使用量 (kWh, MWh, GWh, GJ 等)
- waste_volume: 廃棄物量 (kg, t 等)
- water_usage: 水使用量 (L, kL, ML, m3 等)

各メトリクスについて以下のJSON配列形式で出力してください:
[
  {{
    "metric_name": "<具体的なメトリクス名>",
    "value": <数値>,
    "unit": "<単位>",
    "category": "<co2_emissions|energy_usage|waste_volume|water_usage>",
    "period": "<レポート期間 YYYY or YYYY-YYYY>",
    "confidence": <0.0-1.0の信頼度>
  }}
]

数値が見つからない場合は空の配列を返してください。
単位が不明確な場合は unit を null としてください。

テキスト:
{text}
"""


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


def extract_metrics_with_bedrock(
    text: str,
    bedrock_client,
    model_id: str,
) -> list[dict]:
    """Bedrock でテキストから ESG メトリクスを抽出する。

    Args:
        text: 入力テキスト
        bedrock_client: Bedrock Runtime boto3 クライアント
        model_id: Bedrock モデル ID

    Returns:
        list[dict]: 抽出されたメトリクスリスト
    """
    if not text or len(text.strip()) < 20:
        return []

    # テキストを最大 10000 文字に制限
    truncated_text = text[:10000]
    prompt = METRICS_EXTRACTION_PROMPT.format(text=truncated_text)

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

    # レスポンスからメトリクスを抽出
    content_text = ""
    for content_block in response_body.get("content", []):
        if content_block.get("type") == "text":
            content_text += content_block.get("text", "")

    # JSON 配列を抽出
    metrics = _parse_metrics_json(content_text)
    return metrics


def _parse_metrics_json(text: str) -> list[dict]:
    """Bedrock レスポンスから JSON 配列を抽出する。

    Args:
        text: Bedrock レスポンステキスト

    Returns:
        list[dict]: パースされたメトリクスリスト
    """
    # JSON 配列を探す
    start_idx = text.find("[")
    end_idx = text.rfind("]")

    if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
        return []

    json_str = text[start_idx : end_idx + 1]

    try:
        parsed = json.loads(json_str)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        logger.warning("Failed to parse metrics JSON from Bedrock response")

    return []


def normalize_metrics(
    raw_metrics: list[dict],
    source_key: str,
    esg_category: str,
) -> list[dict]:
    """抽出されたメトリクスを正規化する。

    Args:
        raw_metrics: Bedrock から抽出された生メトリクス
        source_key: ソースドキュメントの S3 キー
        esg_category: ESG カテゴリ (environmental/social/governance)

    Returns:
        list[dict]: 正規化された構造化レコードリスト
    """
    normalized_records: list[dict] = []
    valid_categories = get_supported_categories()

    for metric in raw_metrics:
        metric_name = metric.get("metric_name", "")
        value = metric.get("value")
        unit = metric.get("unit")
        category = metric.get("category", "")
        period = metric.get("period", "")
        confidence = metric.get("confidence", 0.0)

        # confidence を 0.0-1.0 に制限
        try:
            confidence = max(0.0, min(1.0, float(confidence)))
        except (ValueError, TypeError):
            confidence = 0.0

        # 値の数値変換
        try:
            numeric_value = float(value) if value is not None else None
        except (ValueError, TypeError):
            numeric_value = None

        # カテゴリが有効かチェック
        if category not in valid_categories:
            normalized_records.append(
                {
                    "metric_name": metric_name,
                    "value": numeric_value,
                    "unit": unit,
                    "normalized_value": None,
                    "normalized_unit": None,
                    "source_key": source_key,
                    "period": period,
                    "category": category,
                    "esg_category": esg_category,
                    "confidence": confidence,
                    "status": "requires-validation",
                    "validation_reason": "unknown_category",
                }
            )
            continue

        # 値がない場合
        if numeric_value is None:
            normalized_records.append(
                {
                    "metric_name": metric_name,
                    "value": None,
                    "unit": unit,
                    "normalized_value": None,
                    "normalized_unit": UNIT_NORMALIZATION[category]["target"],
                    "source_key": source_key,
                    "period": period,
                    "category": category,
                    "esg_category": esg_category,
                    "confidence": confidence,
                    "status": "requires-validation",
                    "validation_reason": "non_numeric_value",
                }
            )
            continue

        # 正規化実行
        result = normalize_value(numeric_value, unit, category)

        normalized_records.append(
            {
                "metric_name": metric_name,
                "value": numeric_value,
                "unit": unit,
                "normalized_value": result.value,
                "normalized_unit": result.unit,
                "source_key": source_key,
                "period": period,
                "category": category,
                "esg_category": esg_category,
                "confidence": confidence,
                "status": result.status,
                "validation_reason": result.reason,
            }
        )

    return normalized_records


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """ESG Metrics Extractor Lambda

    ESG 文書から定量メトリクスを抽出し正規化する。

    Input event:
        - Key: S3 オブジェクトキー
        - Size: ファイルサイズ
        - category: "environmental" | "social" | "governance"

    Returns:
        dict: status, key, metrics, errors
    """
    key = event.get("Key", "")
    esg_category = event.get("category", "environmental")

    logger.info("Processing ESG document: key=%s, category=%s", key, esg_category)

    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    s3ap_output = S3ApHelper(os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ["S3_ACCESS_POINT"]))
    textract_region = os.environ.get("CROSS_REGION_TEXTRACT_REGION", "us-east-1")
    model_id = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")

    # クライアント初期化
    textract_client = boto3.client("textract", region_name=textract_region)
    bedrock_client = boto3.client("bedrock-runtime")

    errors: list[dict] = []

    try:
        # Step 1: ドキュメント取得
        with xray_subsegment(
            name="s3ap_get_document",
            annotations={
                "service_name": "s3",
                "operation": "GetObject",
                "use_case": "sustainability-esg-reporting",
            },
        ):
            doc_bytes = s3ap.get_object_bytes(key=key)

        # Step 2: Textract でテキスト抽出
        with xray_subsegment(
            name="textract_extract_text",
            annotations={
                "service_name": "textract",
                "operation": "AnalyzeDocument",
                "use_case": "sustainability-esg-reporting",
            },
        ):
            extracted_text = extract_text_with_textract(doc_bytes, textract_client)

        # Step 3: Bedrock でメトリクス抽出
        with xray_subsegment(
            name="bedrock_extract_metrics",
            annotations={
                "service_name": "bedrock",
                "operation": "InvokeModel",
                "use_case": "sustainability-esg-reporting",
            },
        ):
            raw_metrics = extract_metrics_with_bedrock(extracted_text, bedrock_client, model_id)

        # Step 4: 単位正規化
        normalized_metrics = normalize_metrics(raw_metrics, key, esg_category)

        # 結果統計
        success_metrics = [m for m in normalized_metrics if m["status"] == "success"]
        validation_metrics = [m for m in normalized_metrics if m["status"] == "requires-validation"]

        logger.info(
            "Metrics extraction completed: key=%s, total=%d, success=%d, requires_validation=%d",
            key,
            len(normalized_metrics),
            len(success_metrics),
            len(validation_metrics),
        )

        # 結果を S3 に出力
        result_key = f"results/metrics/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{os.path.basename(key)}.json"
        s3ap_output.put_object(
            key=result_key,
            body=json.dumps(
                {
                    "source_key": key,
                    "esg_category": esg_category,
                    "metrics": normalized_metrics,
                    "summary": {
                        "total_metrics": len(normalized_metrics),
                        "success_count": len(success_metrics),
                        "validation_required_count": len(validation_metrics),
                    },
                    "extracted_text_length": len(extracted_text),
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                },
                ensure_ascii=False,
                default=str,
            ),
            content_type="application/json",
        )

        # EMF メトリクス
        metrics_emf = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="processing")
        metrics_emf.set_dimension("UseCase", "sustainability-esg-reporting")
        metrics_emf.set_dimension("Stage", "metrics-extractor")
        metrics_emf.put_metric("SuccessCount", 1.0, "Count")
        metrics_emf.put_metric("MetricsExtracted", float(len(normalized_metrics)), "Count")
        metrics_emf.flush()

        return {
            "status": "success",
            "key": key,
            "category": esg_category,
            "result_key": result_key,
            "metrics": normalized_metrics,
            "errors": [],
        }

    except Exception as e:
        error_detail = {
            "path": key,
            "category": esg_category,
            "error_type": type(e).__name__,
            "details": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        errors.append(error_detail)

        logger.error("Metrics extraction failed: key=%s, error=%s", key, str(e))

        # エラーを出力バケットに記録
        error_key = f"errors/metrics/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{os.path.basename(key)}.json"
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
        metrics_emf.set_dimension("UseCase", "sustainability-esg-reporting")
        metrics_emf.set_dimension("Stage", "metrics-extractor")
        metrics_emf.put_metric("ErrorCount", 1.0, "Count")
        metrics_emf.flush()

        return {
            "status": "error",
            "key": key,
            "category": esg_category,
            "errors": errors,
        }
