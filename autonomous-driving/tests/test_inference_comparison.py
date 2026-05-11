"""Unit Tests for Inference Comparison Lambda (Phase 4 — A/B Testing)

Inference Comparison Lambda のユニットテスト。
- aggregate_by_variant 集計ロジック
- DynamoDB クエリ + 書き戻し
- CloudWatch EMF メトリクス出力
- ハンドラ統合テスト
"""

from __future__ import annotations

import json
import os
import sys
import time
from decimal import Decimal
from unittest.mock import MagicMock, patch

import boto3
from moto import mock_aws

# パス設定
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 環境変数設定（インポート前に必要）
os.environ.setdefault("AB_TEST_TABLE_NAME", "test-ab-results")
os.environ.setdefault("ENDPOINT_NAME", "test-endpoint")
os.environ.setdefault("AGGREGATION_WINDOW_SECONDS", "300")
os.environ.setdefault("RESULT_TTL_DAYS", "30")
os.environ.setdefault("REGION", "ap-northeast-1")
os.environ.setdefault("USE_CASE", "autonomous-driving")
os.environ.setdefault("ENABLE_XRAY", "false")

from functions.inference_comparison.handler import (
    aggregate_by_variant,
    _emit_variant_metrics,
    _write_aggregation_to_dynamodb,
    handler,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TABLE_NAME = "test-ab-results"
REGION = "ap-northeast-1"


def _create_ab_test_table(dynamodb_resource):
    """ABTestResults DynamoDB テーブルを作成する。"""
    table = dynamodb_resource.create_table(
        TableName=TABLE_NAME,
        KeySchema=[
            {"AttributeName": "test_id", "KeyType": "HASH"},
            {"AttributeName": "timestamp", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "test_id", "AttributeType": "S"},
            {"AttributeName": "timestamp", "AttributeType": "N"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    return table


# ---------------------------------------------------------------------------
# Tests: aggregate_by_variant
# ---------------------------------------------------------------------------


class TestAggregateByVariant:
    """aggregate_by_variant のテスト"""

    def test_single_variant(self):
        """単一バリアントの集計"""
        items = [
            {"variant_name": "model-v1", "latency_ms": 100, "is_error": False},
            {"variant_name": "model-v1", "latency_ms": 200, "is_error": False},
            {"variant_name": "model-v1", "latency_ms": 300, "is_error": True},
        ]

        result = aggregate_by_variant(items)

        assert "model-v1" in result
        v1 = result["model-v1"]
        assert v1["request_count"] == 3
        assert v1["avg_latency_ms"] == 200.0  # (100+200+300)/3
        assert v1["error_count"] == 1
        assert v1["error_rate"] == round(1 / 3, 4)
        assert v1["total_latency_ms"] == 600.0

    def test_multiple_variants(self):
        """複数バリアントの集計"""
        items = [
            {"variant_name": "model-v1", "latency_ms": 100, "is_error": False},
            {"variant_name": "model-v2", "latency_ms": 50, "is_error": False},
            {"variant_name": "model-v1", "latency_ms": 200, "is_error": False},
            {"variant_name": "model-v2", "latency_ms": 150, "is_error": True},
        ]

        result = aggregate_by_variant(items)

        assert len(result) == 2

        v1 = result["model-v1"]
        assert v1["request_count"] == 2
        assert v1["avg_latency_ms"] == 150.0  # (100+200)/2
        assert v1["error_count"] == 0
        assert v1["error_rate"] == 0.0

        v2 = result["model-v2"]
        assert v2["request_count"] == 2
        assert v2["avg_latency_ms"] == 100.0  # (50+150)/2
        assert v2["error_count"] == 1
        assert v2["error_rate"] == 0.5

    def test_empty_list(self):
        """空リストの集計は空辞書を返す"""
        result = aggregate_by_variant([])
        assert result == {}

    def test_all_errors(self):
        """全リクエストがエラーの場合"""
        items = [
            {"variant_name": "model-v1", "latency_ms": 500, "is_error": True},
            {"variant_name": "model-v1", "latency_ms": 600, "is_error": True},
        ]

        result = aggregate_by_variant(items)

        v1 = result["model-v1"]
        assert v1["error_rate"] == 1.0
        assert v1["error_count"] == 2
        assert v1["request_count"] == 2
        assert v1["avg_latency_ms"] == 550.0

    def test_missing_variant_name_defaults_to_unknown(self):
        """variant_name がないレコードは 'unknown' に集計される"""
        items = [
            {"latency_ms": 100, "is_error": False},
        ]

        result = aggregate_by_variant(items)
        assert "unknown" in result
        assert result["unknown"]["request_count"] == 1


# ---------------------------------------------------------------------------
# Tests: _emit_variant_metrics
# ---------------------------------------------------------------------------


class TestEmitVariantMetrics:
    """_emit_variant_metrics のテスト"""

    def test_emf_metrics_emission(self, capsys):
        """バリアント別 EMF メトリクスが stdout に出力される"""
        variant_metrics = {
            "model-v1": {
                "avg_latency_ms": 150.0,
                "error_rate": 0.05,
                "request_count": 100,
                "error_count": 5,
            },
        }

        _emit_variant_metrics(variant_metrics, "test-endpoint", "autonomous-driving")

        captured = capsys.readouterr()
        output = captured.out.strip()
        emf_data = json.loads(output)

        # EMF 構造の検証
        assert "_aws" in emf_data
        assert emf_data["_aws"]["CloudWatchMetrics"][0]["Namespace"] == "FSxN-S3AP-Patterns"
        assert emf_data["AvgLatency"] == 150.0
        assert emf_data["ErrorRate"] == 0.05
        assert emf_data["RequestCount"] == 100.0
        assert emf_data["ErrorCount"] == 5.0
        assert emf_data["VariantName"] == "model-v1"
        assert emf_data["EndpointName"] == "test-endpoint"


# ---------------------------------------------------------------------------
# Tests: _write_aggregation_to_dynamodb
# ---------------------------------------------------------------------------


class TestWriteAggregationToDynamoDB:
    """_write_aggregation_to_dynamodb のテスト"""

    @mock_aws
    def test_write_aggregation_results(self):
        """集計結果が DynamoDB に正しく書き込まれる"""
        dynamodb = boto3.resource("dynamodb", region_name=REGION)
        table = _create_ab_test_table(dynamodb)

        variant_metrics = {
            "model-v1": {
                "avg_latency_ms": 120.5,
                "error_rate": 0.02,
                "request_count": 50,
                "total_latency_ms": 6025.0,
                "error_count": 1,
            },
        }

        now = int(time.time())
        _write_aggregation_to_dynamodb(
            table=table,
            test_id="test-endpoint",
            timestamp=now,
            variant_metrics=variant_metrics,
            window_seconds=300,
            ttl_days=30,
        )

        # 書き込まれたアイテムを確認
        response = table.get_item(
            Key={"test_id": "test-endpoint-aggregation", "timestamp": now}
        )
        item = response["Item"]

        assert item["record_type"] == "aggregation"
        assert item["window_seconds"] == 300
        assert item["ttl"] == now + (30 * 86400)
        assert "model-v1" in item["variant_metrics"]
        # Decimal 変換の確認
        assert item["variant_metrics"]["model-v1"]["avg_latency_ms"] == Decimal("120.5")


# ---------------------------------------------------------------------------
# Tests: handler integration
# ---------------------------------------------------------------------------


class TestHandlerIntegration:
    """handler 関数の統合テスト"""

    @mock_aws
    def test_handler_with_data(self):
        """handler: DynamoDB にデータがある場合の正常フロー"""
        dynamodb = boto3.resource("dynamodb", region_name=REGION)
        table = _create_ab_test_table(dynamodb)

        # テストデータ投入
        now = int(time.time())
        for i in range(5):
            table.put_item(
                Item={
                    "test_id": "test-endpoint",
                    "timestamp": now - 60 + i,
                    "variant_name": "model-v1",
                    "latency_ms": Decimal("100"),
                    "is_error": False,
                }
            )

        context = MagicMock()
        context.aws_request_id = "req-123"
        context.function_name = "inference-comparison"

        with patch.dict(os.environ, {
            "AB_TEST_TABLE_NAME": TABLE_NAME,
            "ENDPOINT_NAME": "test-endpoint",
            "AGGREGATION_WINDOW_SECONDS": "300",
            "RESULT_TTL_DAYS": "30",
            "REGION": REGION,
        }):
            with patch("functions.inference_comparison.handler.boto3") as mock_boto3:
                mock_boto3.resource.return_value = dynamodb

                result = handler({}, context)

        assert result["status"] == "completed"
        assert result["test_id"] == "test-endpoint"
        assert result["variants_compared"] == 1
        assert "model-v1" in result["variant_metrics"]
        assert result["variant_metrics"]["model-v1"]["request_count"] == 5

    @mock_aws
    def test_handler_no_data_in_window(self):
        """handler: ウィンドウ内にデータがない場合"""
        dynamodb = boto3.resource("dynamodb", region_name=REGION)
        _create_ab_test_table(dynamodb)

        context = MagicMock()
        context.aws_request_id = "req-456"
        context.function_name = "inference-comparison"

        with patch.dict(os.environ, {
            "AB_TEST_TABLE_NAME": TABLE_NAME,
            "ENDPOINT_NAME": "test-endpoint",
            "AGGREGATION_WINDOW_SECONDS": "300",
            "REGION": REGION,
        }):
            with patch("functions.inference_comparison.handler.boto3") as mock_boto3:
                mock_boto3.resource.return_value = dynamodb

                result = handler({}, context)

        assert result["status"] == "no_data"
        assert result["variants_compared"] == 0
        assert result["variant_metrics"] == {}

    def test_handler_missing_table_name_raises_value_error(self):
        """handler: AB_TEST_TABLE_NAME 未設定で ValueError"""
        context = MagicMock()
        context.aws_request_id = "req-789"
        context.function_name = "inference-comparison"

        with patch.dict(os.environ, {"AB_TEST_TABLE_NAME": "", "ENDPOINT_NAME": "ep"}):
            result = handler({}, context)

        assert result["statusCode"] == 500
        assert "AB_TEST_TABLE_NAME" in result["body"]

    def test_handler_missing_endpoint_name_raises_value_error(self):
        """handler: ENDPOINT_NAME 未設定で ValueError"""
        context = MagicMock()
        context.aws_request_id = "req-000"
        context.function_name = "inference-comparison"

        with patch.dict(os.environ, {"AB_TEST_TABLE_NAME": "table", "ENDPOINT_NAME": ""}):
            result = handler({}, context)

        assert result["statusCode"] == 500
        assert "ENDPOINT_NAME" in result["body"]
