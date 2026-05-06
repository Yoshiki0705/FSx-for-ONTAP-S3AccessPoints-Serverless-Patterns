"""Inference Comparison Lambda ハンドラ — A/B テスト結果集計

EventBridge Schedule（5 分間隔）でトリガーされ、DynamoDB ABTestResults テーブルから
直近 5 分間の推論結果を集計する。バリアント別のメトリクス（平均レイテンシ、
エラーレート、リクエスト数）を計算し、CloudWatch EMF で出力する。

集計結果は DynamoDB に書き戻され、A/B テストの時系列比較に使用される。

Environment Variables:
    AB_TEST_TABLE_NAME: DynamoDB ABTestResults テーブル名
    ENDPOINT_NAME: SageMaker Endpoint 名（test_id として使用）
    AGGREGATION_WINDOW_SECONDS: 集計ウィンドウ秒数 (default: "300")
    RESULT_TTL_DAYS: 集計結果の TTL 日数 (default: "30")
    REGION: AWS リージョン
    USE_CASE: ユースケース名 (default: "autonomous-driving")
"""

from __future__ import annotations

import logging
import os
import time
from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)


def _query_recent_results(
    table,
    test_id: str,
    window_start: int,
    window_end: int,
) -> list[dict[str, Any]]:
    """DynamoDB ABTestResults テーブルから指定ウィンドウのレコードを取得する。

    Args:
        table: boto3 DynamoDB Table リソース
        test_id: A/B テスト識別子（endpoint_name）
        window_start: ウィンドウ開始 Unix タイムスタンプ
        window_end: ウィンドウ終了 Unix タイムスタンプ

    Returns:
        list[dict]: クエリ結果のアイテムリスト
    """
    items: list[dict[str, Any]] = []
    last_evaluated_key = None

    while True:
        query_params: dict[str, Any] = {
            "KeyConditionExpression": (
                Key("test_id").eq(test_id)
                & Key("timestamp").between(window_start, window_end)
            ),
        }
        if last_evaluated_key:
            query_params["ExclusiveStartKey"] = last_evaluated_key

        response = table.query(**query_params)
        items.extend(response.get("Items", []))

        last_evaluated_key = response.get("LastEvaluatedKey")
        if not last_evaluated_key:
            break

    return items


def aggregate_by_variant(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """推論結果をバリアント別に集計する。

    各レコードは以下の形式を想定:
    {
        "test_id": "endpoint-name",
        "timestamp": 1234567890,
        "variant_name": "model-v1",
        "latency_ms": 123.45,
        "is_error": False,
    }

    Args:
        items: DynamoDB クエリ結果のアイテムリスト

    Returns:
        dict: バリアント別集計結果
        {
            "model-v1": {
                "avg_latency_ms": 123.45,
                "error_rate": 0.05,
                "request_count": 100,
                "total_latency_ms": 12345.0,
                "error_count": 5,
            },
            ...
        }
    """
    variant_data: dict[str, dict[str, Any]] = {}

    for item in items:
        variant_name = str(item.get("variant_name", "unknown"))
        latency_ms = float(item.get("latency_ms", 0))
        is_error = bool(item.get("is_error", False))

        if variant_name not in variant_data:
            variant_data[variant_name] = {
                "total_latency_ms": 0.0,
                "error_count": 0,
                "request_count": 0,
            }

        data = variant_data[variant_name]
        data["request_count"] += 1
        data["total_latency_ms"] += latency_ms
        if is_error:
            data["error_count"] += 1

    # 平均値・レート計算
    result: dict[str, dict[str, Any]] = {}
    for variant_name, data in variant_data.items():
        request_count = data["request_count"]
        avg_latency = (
            data["total_latency_ms"] / request_count if request_count > 0 else 0.0
        )
        error_rate = (
            data["error_count"] / request_count if request_count > 0 else 0.0
        )

        result[variant_name] = {
            "avg_latency_ms": round(avg_latency, 2),
            "error_rate": round(error_rate, 4),
            "request_count": request_count,
            "total_latency_ms": round(data["total_latency_ms"], 2),
            "error_count": data["error_count"],
        }

    return result


def _emit_variant_metrics(
    variant_metrics: dict[str, dict[str, Any]],
    endpoint_name: str,
    use_case: str,
) -> None:
    """バリアント別メトリクスを CloudWatch EMF で出力する。

    各バリアントに対して個別の EMF ログ行を出力する。

    Args:
        variant_metrics: バリアント別集計結果
        endpoint_name: SageMaker Endpoint 名
        use_case: ユースケース名
    """
    for variant_name, metrics_data in variant_metrics.items():
        metrics = EmfMetrics(
            namespace="FSxN-S3AP-Patterns",
            service="inference-comparison",
        )
        metrics.set_dimension("UseCase", use_case)
        metrics.set_dimension("VariantName", variant_name)

        metrics.put_metric(
            "AvgLatency", metrics_data["avg_latency_ms"], "Milliseconds"
        )
        metrics.put_metric("ErrorRate", metrics_data["error_rate"], "None")
        metrics.put_metric(
            "RequestCount", float(metrics_data["request_count"]), "Count"
        )
        metrics.put_metric(
            "ErrorCount", float(metrics_data["error_count"]), "Count"
        )

        metrics.set_property("EndpointName", endpoint_name)
        metrics.set_property("VariantName", variant_name)
        metrics.flush()


def _write_aggregation_to_dynamodb(
    table,
    test_id: str,
    timestamp: int,
    variant_metrics: dict[str, dict[str, Any]],
    window_seconds: int,
    ttl_days: int,
) -> None:
    """集計結果を DynamoDB に書き戻す。

    Args:
        table: boto3 DynamoDB Table リソース
        test_id: A/B テスト識別子
        timestamp: 集計タイムスタンプ
        variant_metrics: バリアント別集計結果
        window_seconds: 集計ウィンドウ秒数
        ttl_days: TTL 日数
    """
    ttl_value = timestamp + (ttl_days * 86400)

    # Decimal 変換（DynamoDB は float を受け付けない）
    variant_metrics_decimal: dict[str, dict[str, Any]] = {}
    for variant_name, data in variant_metrics.items():
        variant_metrics_decimal[variant_name] = {
            "avg_latency_ms": Decimal(str(data["avg_latency_ms"])),
            "error_rate": Decimal(str(data["error_rate"])),
            "request_count": data["request_count"],
            "total_latency_ms": Decimal(str(data["total_latency_ms"])),
            "error_count": data["error_count"],
        }

    item = {
        "test_id": f"{test_id}-aggregation",
        "timestamp": timestamp,
        "variant_metrics": variant_metrics_decimal,
        "window_seconds": window_seconds,
        "record_type": "aggregation",
        "ttl": ttl_value,
    }

    table.put_item(Item=item)

    logger.info(
        "Aggregation written to DynamoDB: test_id=%s-aggregation, "
        "timestamp=%d, variants=%d",
        test_id,
        timestamp,
        len(variant_metrics),
    )


@trace_lambda_handler
@lambda_error_handler
def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Inference Comparison Lambda ハンドラ

    EventBridge Schedule（5 分間隔）でトリガーされる。
    DynamoDB ABTestResults テーブルから直近ウィンドウの推論結果を集計し、
    バリアント別メトリクスを CloudWatch EMF で出力する。

    Input:
        EventBridge Schedule イベント（内容は使用しない）

    Output:
        {
            "status": "completed",
            "test_id": "endpoint-name",
            "window_seconds": 300,
            "variants_compared": 2,
            "variant_metrics": {...}
        }
    """
    region = os.environ.get("REGION", os.environ.get("AWS_REGION", "ap-northeast-1"))
    table_name = os.environ.get("AB_TEST_TABLE_NAME", "")
    endpoint_name = os.environ.get("ENDPOINT_NAME", "")
    window_seconds = int(os.environ.get("AGGREGATION_WINDOW_SECONDS", "300"))
    ttl_days = int(os.environ.get("RESULT_TTL_DAYS", "30"))
    use_case = os.environ.get("USE_CASE", "autonomous-driving")

    if not table_name:
        raise ValueError("AB_TEST_TABLE_NAME environment variable is required")
    if not endpoint_name:
        raise ValueError("ENDPOINT_NAME environment variable is required")

    logger.info(
        "Inference comparison started: endpoint=%s, table=%s, "
        "window=%ds",
        endpoint_name,
        table_name,
        window_seconds,
    )

    # 集計ウィンドウ計算
    now = int(time.time())
    window_start = now - window_seconds
    test_id = endpoint_name

    # DynamoDB テーブルアクセス
    dynamodb = boto3.resource("dynamodb", region_name=region)
    table = dynamodb.Table(table_name)

    # Step 1: 直近ウィンドウのレコードを取得
    items = _query_recent_results(table, test_id, window_start, now)

    logger.info(
        "Queried %d records for test_id=%s, window=[%d, %d]",
        len(items),
        test_id,
        window_start,
        now,
    )

    if not items:
        logger.info("No records found in window, skipping aggregation")
        return {
            "status": "no_data",
            "test_id": test_id,
            "window_seconds": window_seconds,
            "variants_compared": 0,
            "variant_metrics": {},
        }

    # Step 2: バリアント別集計
    variant_metrics = aggregate_by_variant(items)

    logger.info(
        "Aggregation complete: %d variants, total_records=%d",
        len(variant_metrics),
        len(items),
    )

    # Step 3: CloudWatch EMF メトリクス出力
    _emit_variant_metrics(variant_metrics, endpoint_name, use_case)

    # Step 4: 集計結果を DynamoDB に書き戻し
    _write_aggregation_to_dynamodb(
        table=table,
        test_id=test_id,
        timestamp=now,
        variant_metrics=variant_metrics,
        window_seconds=window_seconds,
        ttl_days=ttl_days,
    )

    return {
        "status": "completed",
        "test_id": test_id,
        "window_seconds": window_seconds,
        "variants_compared": len(variant_metrics),
        "variant_metrics": variant_metrics,
    }
