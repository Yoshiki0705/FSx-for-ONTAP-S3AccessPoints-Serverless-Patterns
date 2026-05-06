"""Unit tests for shared/observability.py

EmfMetrics, xray_subsegment, trace_lambda_handler のユニットテスト。
"""

from __future__ import annotations

import json
import os
import sys
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from shared.observability import EmfMetrics, trace_lambda_handler, xray_subsegment


# ---------------------------------------------------------------------------
# EmfMetrics flush output conforms to EMF spec
# ---------------------------------------------------------------------------


class TestEmfMetricsFlush:
    """EmfMetrics flush 出力が EMF 仕様に準拠することを検証する。"""

    def test_flush_produces_valid_emf_json(self):
        """flush() が _aws ブロック、Timestamp、CloudWatchMetrics を含む JSON を出力する。"""
        metrics = EmfMetrics(namespace="TestNamespace", service="test-func")
        metrics.set_dimension("UseCase", "unit-test")
        metrics.put_metric("TestMetric", 42.0, "Count")

        with patch("builtins.print") as mock_print:
            metrics.flush()

        output = mock_print.call_args[0][0]
        parsed = json.loads(output)

        # _aws block
        assert "_aws" in parsed
        assert "Timestamp" in parsed["_aws"]
        assert isinstance(parsed["_aws"]["Timestamp"], int)
        assert parsed["_aws"]["Timestamp"] > 0

        # CloudWatchMetrics
        cw_metrics = parsed["_aws"]["CloudWatchMetrics"]
        assert len(cw_metrics) == 1
        assert cw_metrics[0]["Namespace"] == "TestNamespace"
        assert cw_metrics[0]["Dimensions"] == [["FunctionName", "Environment", "UseCase"]]
        assert cw_metrics[0]["Metrics"] == [{"Name": "TestMetric", "Unit": "Count"}]

        # Top-level metric value
        assert parsed["TestMetric"] == 42.0

        # Dimensions as top-level keys
        assert parsed["FunctionName"] == "test-func"
        assert parsed["UseCase"] == "unit-test"

    def test_flush_does_nothing_when_no_metrics(self):
        """メトリクスが追加されていない場合、flush() は何も出力しない。"""
        metrics = EmfMetrics()

        with patch("builtins.print") as mock_print:
            metrics.flush()

        mock_print.assert_not_called()

    def test_flush_resets_metrics_after_output(self):
        """flush() 後にメトリクスがリセットされる。"""
        metrics = EmfMetrics()
        metrics.put_metric("Metric1", 1.0, "Count")

        with patch("builtins.print"):
            metrics.flush()

        # Second flush should not output anything
        with patch("builtins.print") as mock_print:
            metrics.flush()

        mock_print.assert_not_called()

    def test_multiple_metrics_in_single_flush(self):
        """複数メトリクスが単一の flush で出力される。"""
        metrics = EmfMetrics(namespace="Multi")
        metrics.put_metric("MetricA", 10.0, "Count")
        metrics.put_metric("MetricB", 200.0, "Milliseconds")
        metrics.put_metric("MetricC", 1024.0, "Bytes")

        with patch("builtins.print") as mock_print:
            metrics.flush()

        parsed = json.loads(mock_print.call_args[0][0])
        assert parsed["MetricA"] == 10.0
        assert parsed["MetricB"] == 200.0
        assert parsed["MetricC"] == 1024.0

        metric_defs = parsed["_aws"]["CloudWatchMetrics"][0]["Metrics"]
        assert len(metric_defs) == 3


# ---------------------------------------------------------------------------
# Metric name validation
# ---------------------------------------------------------------------------


class TestMetricNameValidation:
    """メトリクス名バリデーションのテスト。"""

    def test_rejects_name_exceeding_256_chars(self):
        """256 文字を超えるメトリクス名を拒否する。"""
        metrics = EmfMetrics()
        long_name = "a" * 257

        with pytest.raises(ValueError, match="exceeds 256 characters"):
            metrics.put_metric(long_name, 1.0, "Count")

    def test_rejects_special_characters(self):
        """特殊文字を含むメトリクス名を拒否する。"""
        metrics = EmfMetrics()

        invalid_names = [
            "metric-name",  # hyphen
            "metric.name",  # dot
            "metric name",  # space
            "metric@name",  # at sign
            "metric!name",  # exclamation
            "metric/name",  # slash
        ]

        for name in invalid_names:
            with pytest.raises(ValueError, match="invalid characters"):
                metrics.put_metric(name, 1.0, "Count")

    def test_rejects_empty_name(self):
        """空のメトリクス名を拒否する。"""
        metrics = EmfMetrics()

        with pytest.raises(ValueError, match="must not be empty"):
            metrics.put_metric("", 1.0, "Count")

    def test_accepts_valid_names(self):
        """有効なメトリクス名を受け入れる。"""
        metrics = EmfMetrics()

        valid_names = [
            "simple",
            "CamelCase",
            "with_underscore",
            "UPPER_CASE",
            "metric123",
            "a" * 256,  # exactly 256 chars
        ]

        for name in valid_names:
            metrics.put_metric(name, 1.0, "Count")  # Should not raise

    def test_rejects_invalid_unit(self):
        """無効な unit を拒否する。"""
        metrics = EmfMetrics()

        with pytest.raises(ValueError, match="Invalid unit"):
            metrics.put_metric("ValidName", 1.0, "InvalidUnit")


# ---------------------------------------------------------------------------
# EmfMetrics dimensions and properties
# ---------------------------------------------------------------------------


class TestEmfMetricsDimensionsAndProperties:
    """ディメンションとプロパティのテスト。"""

    def test_default_environment_dimension(self):
        """デフォルトで Environment ディメンションが設定される。"""
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            metrics = EmfMetrics()
            metrics.put_metric("Test", 1.0, "Count")

            with patch("builtins.print") as mock_print:
                metrics.flush()

            parsed = json.loads(mock_print.call_args[0][0])
            assert parsed["Environment"] == "production"

    def test_custom_dimensions(self):
        """カスタムディメンションが正しく設定される。"""
        metrics = EmfMetrics()
        metrics.set_dimension("UseCase", "retail-catalog")
        metrics.set_dimension("FunctionName", "my-function")
        metrics.put_metric("Test", 1.0, "Count")

        with patch("builtins.print") as mock_print:
            metrics.flush()

        parsed = json.loads(mock_print.call_args[0][0])
        assert parsed["UseCase"] == "retail-catalog"
        assert parsed["FunctionName"] == "my-function"

    def test_properties_included_in_output(self):
        """プロパティが出力に含まれる（メトリクスではない）。"""
        metrics = EmfMetrics()
        metrics.set_property("request_id", "abc-123")
        metrics.set_property("file_count", 5)
        metrics.put_metric("Test", 1.0, "Count")

        with patch("builtins.print") as mock_print:
            metrics.flush()

        parsed = json.loads(mock_print.call_args[0][0])
        assert parsed["request_id"] == "abc-123"
        assert parsed["file_count"] == 5

        # Properties should NOT be in Metrics definitions
        metric_defs = parsed["_aws"]["CloudWatchMetrics"][0]["Metrics"]
        metric_names = [m["Name"] for m in metric_defs]
        assert "request_id" not in metric_names
        assert "file_count" not in metric_names


# ---------------------------------------------------------------------------
# trace_lambda_handler decorator
# ---------------------------------------------------------------------------


class TestTraceLambdaHandler:
    """trace_lambda_handler デコレータのテスト。"""

    def test_measures_duration_on_success(self):
        """成功時に ProcessingDuration メトリクスを出力する。"""

        @trace_lambda_handler
        def handler(event, context):
            return {"statusCode": 200}

        context = MagicMock()
        context.function_name = "test-handler"

        with patch.dict(os.environ, {"ENABLE_XRAY": "false", "USE_CASE": "test-uc"}):
            with patch("builtins.print") as mock_print:
                result = handler({}, context)

        assert result == {"statusCode": 200}

        parsed = json.loads(mock_print.call_args[0][0])
        assert parsed["ProcessingDuration"] >= 0
        assert parsed["ProcessingSuccess"] == 1.0
        assert parsed["ProcessingErrors"] == 0.0
        assert parsed["UseCase"] == "test-uc"

    def test_counts_errors_on_exception(self):
        """例外発生時に ProcessingErrors メトリクスを出力する。"""

        @trace_lambda_handler
        def handler(event, context):
            raise RuntimeError("test error")

        context = MagicMock()
        context.function_name = "error-handler"

        with patch.dict(os.environ, {"ENABLE_XRAY": "false", "USE_CASE": "error-uc"}):
            with patch("builtins.print") as mock_print:
                with pytest.raises(RuntimeError, match="test error"):
                    handler({}, context)

        parsed = json.loads(mock_print.call_args[0][0])
        assert parsed["ProcessingSuccess"] == 0.0
        assert parsed["ProcessingErrors"] == 1.0
        assert parsed["ProcessingDuration"] >= 0

    def test_emf_metrics_emitted_even_when_xray_disabled(self):
        """X-Ray 無効時でも EMF メトリクスは出力される。"""

        @trace_lambda_handler
        def handler(event, context):
            return {"statusCode": 200}

        context = MagicMock()
        context.function_name = "no-xray-handler"

        with patch.dict(os.environ, {"ENABLE_XRAY": "false"}):
            with patch("builtins.print") as mock_print:
                handler({}, context)

        # EMF output should still be produced
        assert mock_print.called
        parsed = json.loads(mock_print.call_args[0][0])
        assert "_aws" in parsed
        assert "ProcessingDuration" in parsed


# ---------------------------------------------------------------------------
# xray_subsegment no-op tests
# ---------------------------------------------------------------------------


class TestXraySubsegmentNoop:
    """xray_subsegment の no-op 動作テスト。"""

    def test_noop_when_xray_sdk_not_available(self):
        """aws_xray_sdk が未インストール時に no-op として動作する。"""
        with patch.dict(os.environ, {"ENABLE_XRAY": "true"}):
            # Simulate aws_xray_sdk not being available
            with patch.dict(sys.modules, {"aws_xray_sdk": None, "aws_xray_sdk.core": None}):
                # Remove cached import if any
                import importlib
                import shared.observability
                importlib.reload(shared.observability)
                from shared.observability import xray_subsegment as xray_sub_reloaded

                result = None
                with xray_sub_reloaded(name="test", annotations={"key": "val"}):
                    result = 42

                assert result == 42

    def test_noop_when_enable_xray_false(self):
        """ENABLE_XRAY=false 時に no-op として動作する。"""
        with patch.dict(os.environ, {"ENABLE_XRAY": "false"}):
            result = None
            with xray_subsegment(name="test", annotations={"key": "val"}, metadata={"m": "v"}):
                result = "executed"

            assert result == "executed"

    def test_noop_does_not_raise_with_none_annotations(self):
        """annotations=None でもエラーなし。"""
        with patch.dict(os.environ, {"ENABLE_XRAY": "false"}):
            with xray_subsegment(name="test", annotations=None, metadata=None):
                pass  # Should not raise

    def test_wrapped_code_executes_normally(self):
        """no-op 時にラップされたコードが正常に実行される。"""
        with patch.dict(os.environ, {"ENABLE_XRAY": "false"}):
            values = []
            with xray_subsegment(name="accumulate"):
                for i in range(5):
                    values.append(i)

            assert values == [0, 1, 2, 3, 4]
