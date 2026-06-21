"""サステナビリティ・ESG (UC23) Framework Mapper Lambda ハンドラ

ESG メトリクスを GRI/TCFD/CDP フレームワーク識別子にマッピングする。

処理フロー:
    1. Metrics Extractor の出力を受け取る
    2. Bedrock で各メトリクスを報告フレームワーク識別子にマッピング
    3. マッピング結果を出力

対応フレームワーク (Requirement 7.3):
    - GRI (Global Reporting Initiative) — 開示番号
    - TCFD (Task Force on Climate-Related Financial Disclosures) — 推奨事項
    - CDP (Carbon Disclosure Project) — 質問参照

Environment Variables:
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
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

# フレームワークマッピングプロンプト
FRAMEWORK_MAPPING_PROMPT = """以下のESGメトリクスを国際的な報告フレームワークの識別子にマッピングしてください。

対象フレームワーク:
- GRI (Global Reporting Initiative): 開示番号 (例: GRI 305-1, GRI 302-1)
- TCFD (Task Force on Climate-Related Financial Disclosures): 推奨事項 (例: TCFD Metrics-a)
- CDP (Carbon Disclosure Project): 質問参照 (例: CDP C6.1, CDP C8.2a)

各メトリクスに対して最も適切なフレームワーク識別子をマッピングしてください。
複数のフレームワークにマッピング可能な場合は全て含めてください。

入力メトリクス:
{metrics_json}

以下のJSON配列形式で出力してください:
[
  {{
    "metric_name": "<メトリクス名>",
    "category": "<カテゴリ>",
    "framework_mappings": {{
      "GRI": ["<GRI識別子>"],
      "TCFD": ["<TCFD識別子>"],
      "CDP": ["<CDP識別子>"]
    }}
  }}
]
"""

# 既知のマッピングテーブル（Bedrock フォールバック用）
KNOWN_FRAMEWORK_MAPPINGS: dict[str, dict[str, list[str]]] = {
    "co2_emissions": {
        "GRI": ["GRI 305-1", "GRI 305-2", "GRI 305-3"],
        "TCFD": ["TCFD Metrics-a", "TCFD Metrics-b"],
        "CDP": ["CDP C6.1", "CDP C6.3", "CDP C6.5"],
    },
    "energy_usage": {
        "GRI": ["GRI 302-1", "GRI 302-3", "GRI 302-4"],
        "TCFD": ["TCFD Metrics-a"],
        "CDP": ["CDP C8.2a", "CDP C8.2b"],
    },
    "waste_volume": {
        "GRI": ["GRI 306-3", "GRI 306-4", "GRI 306-5"],
        "TCFD": [],
        "CDP": ["CDP C-CE6.6/C-CG6.6"],
    },
    "water_usage": {
        "GRI": ["GRI 303-3", "GRI 303-4", "GRI 303-5"],
        "TCFD": [],
        "CDP": ["CDP W1.2b", "CDP W1.2d"],
    },
}


def get_fallback_mapping(category: str) -> dict[str, list[str]]:
    """既知マッピングテーブルからフォールバックマッピングを取得する。

    Args:
        category: メトリクスカテゴリ

    Returns:
        dict: フレームワーク識別子マッピング
    """
    return KNOWN_FRAMEWORK_MAPPINGS.get(category, {"GRI": [], "TCFD": [], "CDP": []})


def map_metrics_with_bedrock(
    metrics: list[dict],
    bedrock_client,
    model_id: str,
) -> list[dict]:
    """Bedrock でメトリクスをフレームワーク識別子にマッピングする。

    Args:
        metrics: 正規化されたメトリクスリスト
        bedrock_client: Bedrock Runtime boto3 クライアント
        model_id: Bedrock モデル ID

    Returns:
        list[dict]: フレームワークマッピング結果
    """
    if not metrics:
        return []

    # メトリクスサマリを作成（Bedrock に送信するのは要約のみ）
    metrics_summary = [
        {
            "metric_name": m.get("metric_name", ""),
            "category": m.get("category", ""),
            "value": m.get("normalized_value"),
            "unit": m.get("normalized_unit", ""),
        }
        for m in metrics
        if m.get("status") == "success"
    ]

    if not metrics_summary:
        # 成功メトリクスがない場合はフォールバック
        return _apply_fallback_mappings(metrics)

    prompt = FRAMEWORK_MAPPING_PROMPT.format(metrics_json=json.dumps(metrics_summary, ensure_ascii=False))

    try:

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

        # JSON 配列を抽出
        mappings = _parse_mappings_json(content_text)
        if mappings:
            return _merge_mappings_with_metrics(metrics, mappings)

    except Exception as e:
        logger.warning("Bedrock framework mapping failed, using fallback: %s", str(e))

    # フォールバック
    return _apply_fallback_mappings(metrics)


def _parse_mappings_json(text: str) -> list[dict]:
    """Bedrock レスポンスから JSON 配列を抽出する。"""
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
        logger.warning("Failed to parse framework mapping JSON")

    return []


def _merge_mappings_with_metrics(metrics: list[dict], mappings: list[dict]) -> list[dict]:
    """Bedrock マッピング結果をメトリクスに統合する。"""
    # マッピングを名前でインデックス
    mapping_index: dict[str, dict] = {}
    for m in mappings:
        name = m.get("metric_name", "")
        if name:
            mapping_index[name] = m.get("framework_mappings", {})

    result: list[dict] = []
    for metric in metrics:
        name = metric.get("metric_name", "")
        category = metric.get("category", "")

        # Bedrock マッピングを探す
        fw_mappings = mapping_index.get(name)
        if not fw_mappings:
            # フォールバック
            fw_mappings = get_fallback_mapping(category)

        result.append(
            {
                **metric,
                "framework_mappings": fw_mappings,
            }
        )

    return result


def _apply_fallback_mappings(metrics: list[dict]) -> list[dict]:
    """フォールバックマッピングをメトリクスに適用する。"""
    result: list[dict] = []
    for metric in metrics:
        category = metric.get("category", "")
        fw_mappings = get_fallback_mapping(category)
        result.append(
            {
                **metric,
                "framework_mappings": fw_mappings,
            }
        )
    return result


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """ESG Framework Mapper Lambda

    メトリクス抽出結果を報告フレームワーク識別子にマッピングする。

    Input event:
        - key: S3 オブジェクトキー
        - category: ESG カテゴリ
        - metrics: 正規化されたメトリクスリスト
        - status: "success" | "error"

    Returns:
        dict: status, key, mapped_metrics, errors
    """
    key = event.get("key", event.get("Key", ""))
    esg_category = event.get("category", "environmental")
    input_metrics = event.get("metrics", [])
    input_status = event.get("status", "")

    logger.info(
        "Framework mapping started: key=%s, category=%s, metrics_count=%d",
        key,
        esg_category,
        len(input_metrics),
    )

    # 入力がエラーの場合はそのまま透過
    if input_status == "error":
        return event

    s3ap_output = S3ApHelper(os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ.get("S3_ACCESS_POINT", "")))
    model_id = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-haiku-4-5-20251001-v1:0")

    bedrock_client = boto3.client("bedrock-runtime")

    errors: list[dict] = []

    try:
        # Bedrock でフレームワークマッピング
        with xray_subsegment(
            name="bedrock_framework_mapping",
            annotations={
                "service_name": "bedrock",
                "operation": "InvokeModel",
                "use_case": "sustainability-esg-reporting",
            },
        ):
            mapped_metrics = map_metrics_with_bedrock(input_metrics, bedrock_client, model_id)

        logger.info(
            "Framework mapping completed: key=%s, mapped_count=%d",
            key,
            len(mapped_metrics),
        )

        # 結果を S3 に出力
        result_key = (
            f"results/framework-mapped/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{os.path.basename(key)}.json"
        )
        s3ap_output.put_object(
            key=result_key,
            body=json.dumps(
                {
                    "source_key": key,
                    "esg_category": esg_category,
                    "mapped_metrics": mapped_metrics,
                    "frameworks_used": ["GRI", "TCFD", "CDP"],
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
        metrics_emf.set_dimension("Stage", "framework-mapper")
        metrics_emf.put_metric("SuccessCount", 1.0, "Count")
        metrics_emf.put_metric("MetricsMapped", float(len(mapped_metrics)), "Count")
        metrics_emf.flush()

        return {
            "status": "success",
            "key": key,
            "category": esg_category,
            "result_key": result_key,
            "mapped_metrics": mapped_metrics,
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

        logger.error("Framework mapping failed: key=%s, error=%s", key, str(e))

        # EMF メトリクス
        metrics_emf = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="processing")
        metrics_emf.set_dimension("UseCase", "sustainability-esg-reporting")
        metrics_emf.set_dimension("Stage", "framework-mapper")
        metrics_emf.put_metric("ErrorCount", 1.0, "Count")
        metrics_emf.flush()

        # フォールバック: Bedrock 失敗でも既知マッピングを適用
        fallback_metrics = _apply_fallback_mappings(input_metrics)

        return {
            "status": "partial",
            "key": key,
            "category": esg_category,
            "mapped_metrics": fallback_metrics,
            "errors": errors,
        }
