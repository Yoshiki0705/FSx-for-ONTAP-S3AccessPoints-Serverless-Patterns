"""Tests for shared.lambdas.s3ap_external_monitor.handler

VPC-External S3AP Health Check Lambda のユニットテスト。
moto + botocore.stub でモック化し、以下をカバー:
- 正常系: ListObjectsV2 成功 → healthy=True, metric=1
- 異常系: AccessDenied → healthy=False, metric=0
- 異常系: タイムアウト → healthy=False, metric=0
- 異常系: S3AP_ALIAS 未設定 → healthy=False
- CloudWatch PutMetricData 呼び出し検証
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError, ConnectTimeoutError, ReadTimeoutError


@pytest.fixture(autouse=True)
def _env_setup(monkeypatch):
    """テスト用環境変数を設定する。"""
    monkeypatch.setenv("S3AP_ALIAS", "test-bucket-s3alias")
    monkeypatch.setenv("HEALTH_PREFIX", "_health/")
    monkeypatch.setenv("METRIC_NAMESPACE", "TestNamespace")
    monkeypatch.setenv("TIMEOUT_SECONDS", "5")


@pytest.fixture
def mock_context():
    """Lambda コンテキストのモック。"""
    ctx = MagicMock()
    ctx.function_name = "test-s3ap-health-check"
    ctx.aws_request_id = "test-request-123"
    return ctx


@pytest.fixture
def mock_s3():
    """S3 クライアントのモック。"""
    with patch("shared.lambdas.s3ap_external_monitor.handler.s3") as mock:
        yield mock


@pytest.fixture
def mock_cloudwatch():
    """CloudWatch クライアントのモック。"""
    with patch("shared.lambdas.s3ap_external_monitor.handler.cloudwatch") as mock:
        yield mock


def _import_handler():
    """ハンドラーモジュールを動的にインポートする。"""
    from shared.lambdas.s3ap_external_monitor.handler import handler

    return handler


class TestHealthCheckSuccess:
    """正常系テスト: S3AP が正常に応答する場合。"""

    def test_returns_healthy_true(self, mock_s3, mock_cloudwatch, mock_context):
        """ListObjectsV2 成功時に healthy=True を返す。"""
        mock_s3.list_objects_v2.return_value = {
            "KeyCount": 1,
            "Contents": [{"Key": "_health/marker.txt"}],
        }
        handler = _import_handler()
        result = handler({}, mock_context)

        assert result["healthy"] is True
        assert result["metric_value"] == 1
        assert result["s3ap_alias"] == "test-bucket-s3alias"
        assert "latency_ms" in result
        assert "error" not in result

    def test_calls_list_objects_with_correct_params(self, mock_s3, mock_cloudwatch, mock_context):
        """ListObjectsV2 が正しいパラメータで呼ばれることを確認。"""
        mock_s3.list_objects_v2.return_value = {"KeyCount": 0}
        handler = _import_handler()
        handler({}, mock_context)

        mock_s3.list_objects_v2.assert_called_once_with(
            Bucket="test-bucket-s3alias",
            Prefix="_health/",
            MaxKeys=1,
        )

    def test_publishes_metric_value_1(self, mock_s3, mock_cloudwatch, mock_context):
        """成功時に CloudWatch メトリクス値 1.0 を発行する。"""
        mock_s3.list_objects_v2.return_value = {"KeyCount": 1}
        handler = _import_handler()
        handler({}, mock_context)

        mock_cloudwatch.put_metric_data.assert_called_once()
        call_args = mock_cloudwatch.put_metric_data.call_args
        metric_data = call_args[1]["MetricData"][0]
        assert metric_data["MetricName"] == "S3APHealthCheck"
        assert metric_data["Value"] == 1.0


class TestHealthCheckAccessDenied:
    """異常系テスト: AccessDenied エラー。"""

    def test_returns_healthy_false_on_access_denied(self, mock_s3, mock_cloudwatch, mock_context):
        """AccessDenied エラー時に healthy=False を返す。"""
        mock_s3.list_objects_v2.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
            "ListObjectsV2",
        )
        handler = _import_handler()
        result = handler({}, mock_context)

        assert result["healthy"] is False
        assert result["metric_value"] == 0
        assert "AccessDenied" in result["error"]

    def test_publishes_metric_value_0_on_access_denied(self, mock_s3, mock_cloudwatch, mock_context):
        """AccessDenied エラー時にメトリクス値 0 を発行する。"""
        mock_s3.list_objects_v2.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
            "ListObjectsV2",
        )
        handler = _import_handler()
        handler({}, mock_context)

        call_args = mock_cloudwatch.put_metric_data.call_args
        metric_data = call_args[1]["MetricData"][0]
        assert metric_data["Value"] == 0.0


class TestHealthCheckTimeout:
    """異常系テスト: タイムアウト。"""

    def test_returns_healthy_false_on_read_timeout(self, mock_s3, mock_cloudwatch, mock_context):
        """ReadTimeoutError 時に healthy=False を返す。"""
        mock_s3.list_objects_v2.side_effect = ReadTimeoutError(endpoint_url="https://s3.amazonaws.com")
        handler = _import_handler()
        result = handler({}, mock_context)

        assert result["healthy"] is False
        assert result["metric_value"] == 0
        assert "ReadTimeoutError" in result["error"]

    def test_returns_healthy_false_on_connect_timeout(self, mock_s3, mock_cloudwatch, mock_context):
        """ConnectTimeoutError 時に healthy=False を返す。"""
        mock_s3.list_objects_v2.side_effect = ConnectTimeoutError(endpoint_url="https://s3.amazonaws.com")
        handler = _import_handler()
        result = handler({}, mock_context)

        assert result["healthy"] is False
        assert result["metric_value"] == 0
        assert "ConnectTimeoutError" in result["error"]


class TestHealthCheckMissingConfig:
    """異常系テスト: 設定不備。"""

    def test_returns_healthy_false_when_alias_not_set(self, mock_cloudwatch, mock_context, monkeypatch):
        """S3AP_ALIAS 未設定時に healthy=False を返す。"""
        monkeypatch.setenv("S3AP_ALIAS", "")
        handler = _import_handler()
        result = handler({}, mock_context)

        assert result["healthy"] is False
        assert "not configured" in result["error"]

    def test_publishes_metric_0_when_alias_not_set(self, mock_cloudwatch, mock_context, monkeypatch):
        """S3AP_ALIAS 未設定時にメトリクス値 0 を発行する。"""
        monkeypatch.setenv("S3AP_ALIAS", "")
        handler = _import_handler()
        handler({}, mock_context)

        mock_cloudwatch.put_metric_data.assert_called_once()
        call_args = mock_cloudwatch.put_metric_data.call_args
        metric_data = call_args[1]["MetricData"][0]
        assert metric_data["Value"] == 0.0


class TestHealthCheckMetricDimensions:
    """CloudWatch メトリクスのディメンション検証。"""

    def test_metric_has_correct_dimensions(self, mock_s3, mock_cloudwatch, mock_context):
        """発行されるメトリクスに正しいディメンションが含まれる。"""
        mock_s3.list_objects_v2.return_value = {"KeyCount": 0}
        handler = _import_handler()
        handler({}, mock_context)

        call_args = mock_cloudwatch.put_metric_data.call_args
        assert call_args[1]["Namespace"] == "TestNamespace"
        metric_data = call_args[1]["MetricData"][0]
        dimensions = {d["Name"]: d["Value"] for d in metric_data["Dimensions"]}
        assert dimensions["S3APAlias"] == "test-bucket-s3alias"
        assert dimensions["CheckType"] == "VPC-External"

    def test_metric_dimension_alias_unknown_when_empty(self, mock_cloudwatch, mock_context, monkeypatch):
        """S3AP_ALIAS 空文字列時にディメンション値が 'unknown' になる。"""
        monkeypatch.setenv("S3AP_ALIAS", "")
        handler = _import_handler()
        handler({}, mock_context)

        call_args = mock_cloudwatch.put_metric_data.call_args
        metric_data = call_args[1]["MetricData"][0]
        dimensions = {d["Name"]: d["Value"] for d in metric_data["Dimensions"]}
        assert dimensions["S3APAlias"] == "unknown"


class TestHealthCheckUnexpectedError:
    """異常系テスト: 想定外のエラー。"""

    def test_returns_healthy_false_on_unexpected_error(self, mock_s3, mock_cloudwatch, mock_context):
        """想定外の例外時に healthy=False を返す。"""
        mock_s3.list_objects_v2.side_effect = RuntimeError("Unexpected failure")
        handler = _import_handler()
        result = handler({}, mock_context)

        assert result["healthy"] is False
        assert result["metric_value"] == 0
        assert "RuntimeError" in result["error"]


class TestHealthCheckMetricPublishFailure:
    """CloudWatch メトリクス発行失敗のハンドリング。"""

    def test_does_not_raise_on_metric_publish_failure(self, mock_s3, mock_cloudwatch, mock_context):
        """メトリクス発行失敗時でも Lambda 自体は失敗しない。"""
        mock_s3.list_objects_v2.return_value = {"KeyCount": 1}
        mock_cloudwatch.put_metric_data.side_effect = Exception("CloudWatch unavailable")
        handler = _import_handler()

        # Should not raise
        result = handler({}, mock_context)
        assert result["healthy"] is True
