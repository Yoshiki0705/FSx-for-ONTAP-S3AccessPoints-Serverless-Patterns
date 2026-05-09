"""Unit Tests for shared.lambdas.auto_stop.handler module

Auto-Stop Lambda ハンドラーの単体テスト。
boto3 クライアントをモックし、アイドル検出・タグ保護・DRY_RUN・スケールゼロ・EMF 出力を検証する。

Coverage target: 90% for auto_stop/handler.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def env_setup(monkeypatch):
    """Set up environment variables for Auto-Stop Lambda."""
    monkeypatch.setenv("PROJECT_PREFIX", "fsxn-s3ap")
    monkeypatch.setenv("IDLE_THRESHOLD_MINUTES", "60")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("AWS_REGION", "ap-northeast-1")
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "auto-stop-test")
    monkeypatch.setenv("ENVIRONMENT", "test")


@pytest.fixture
def mock_boto3_clients():
    """Mock boto3 clients used by the Auto-Stop Lambda."""
    mock_sm = MagicMock()
    mock_cw = MagicMock()
    mock_sts = MagicMock()
    mock_sts.get_caller_identity.return_value = {"Account": "123456789012"}

    def fake_client(service_name, **kwargs):
        if service_name == "sagemaker":
            return mock_sm
        elif service_name == "cloudwatch":
            return mock_cw
        elif service_name == "sts":
            return mock_sts
        return MagicMock()

    with patch("shared.lambdas.auto_stop.handler.sagemaker_client", mock_sm), \
         patch("shared.lambdas.auto_stop.handler.cloudwatch_client", mock_cw), \
         patch("shared.lambdas.auto_stop.handler.boto3") as mock_boto3:

        mock_boto3.client.side_effect = fake_client

        yield {
            "sagemaker": mock_sm,
            "cloudwatch": mock_cw,
            "boto3": mock_boto3,
        }


def _make_endpoint(name: str) -> dict:
    """Create a mock endpoint dict."""
    return {
        "EndpointName": name,
        "EndpointStatus": "InService",
        "CreationTime": datetime(2024, 1, 1, tzinfo=timezone.utc),
    }


def _make_tags(tags_dict: dict) -> list[dict]:
    """Convert a dict to SageMaker tag format."""
    return [{"Key": k, "Value": v} for k, v in tags_dict.items()]


# ---------------------------------------------------------------------------
# Tests: Idle Detection Logic
# ---------------------------------------------------------------------------


class TestIdleDetection:
    """Tests for idle endpoint detection (zero invocations → idle)."""

    def test_endpoint_with_zero_invocations_is_idle(self, mock_boto3_clients):
        """Endpoint with zero invocations in monitoring period is idle."""
        from shared.lambdas.auto_stop.handler import _is_endpoint_idle

        mock_cw = mock_boto3_clients["cloudwatch"]
        mock_cw.get_metric_data.return_value = {
            "MetricDataResults": [
                {"Id": "invocations", "Values": [0.0, 0.0, 0.0]}
            ]
        }

        result = _is_endpoint_idle("test-endpoint")
        assert result is True

    def test_endpoint_with_invocations_is_not_idle(self, mock_boto3_clients):
        """Endpoint with non-zero invocations is not idle."""
        from shared.lambdas.auto_stop.handler import _is_endpoint_idle

        mock_cw = mock_boto3_clients["cloudwatch"]
        mock_cw.get_metric_data.return_value = {
            "MetricDataResults": [
                {"Id": "invocations", "Values": [5.0, 3.0, 2.0]}
            ]
        }

        result = _is_endpoint_idle("test-endpoint")
        assert result is False

    def test_endpoint_with_no_metric_data_is_idle(self, mock_boto3_clients):
        """Endpoint with no metric data points is considered idle."""
        from shared.lambdas.auto_stop.handler import _is_endpoint_idle

        mock_cw = mock_boto3_clients["cloudwatch"]
        mock_cw.get_metric_data.return_value = {
            "MetricDataResults": [
                {"Id": "invocations", "Values": []}
            ]
        }

        result = _is_endpoint_idle("test-endpoint")
        assert result is True

    def test_endpoint_with_empty_results_is_idle(self, mock_boto3_clients):
        """Endpoint with empty MetricDataResults is considered idle."""
        from shared.lambdas.auto_stop.handler import _is_endpoint_idle

        mock_cw = mock_boto3_clients["cloudwatch"]
        mock_cw.get_metric_data.return_value = {
            "MetricDataResults": []
        }

        result = _is_endpoint_idle("test-endpoint")
        assert result is True

    def test_endpoint_metric_error_returns_not_idle(self, mock_boto3_clients):
        """If CloudWatch query fails, endpoint is NOT considered idle (safe default)."""
        from shared.lambdas.auto_stop.handler import _is_endpoint_idle

        mock_cw = mock_boto3_clients["cloudwatch"]
        mock_cw.get_metric_data.side_effect = Exception("CloudWatch error")

        result = _is_endpoint_idle("test-endpoint")
        assert result is False


# ---------------------------------------------------------------------------
# Tests: DoNotAutoStop Tag Protection
# ---------------------------------------------------------------------------


class TestDoNotAutoStopTagProtection:
    """Tests for DoNotAutoStop tag protection."""

    def test_endpoint_with_do_not_auto_stop_true_is_protected(self, mock_boto3_clients):
        """Endpoint with DoNotAutoStop=true tag is protected."""
        from shared.lambdas.auto_stop.handler import _has_do_not_auto_stop_tag

        mock_sm = mock_boto3_clients["sagemaker"]
        mock_sm.list_tags.return_value = {
            "Tags": _make_tags({"DoNotAutoStop": "true", "Project": "fsxn-s3ap"})
        }

        result = _has_do_not_auto_stop_tag("protected-endpoint")
        assert result is True

    def test_endpoint_with_do_not_auto_stop_false_is_not_protected(self, mock_boto3_clients):
        """Endpoint with DoNotAutoStop=false tag is not protected."""
        from shared.lambdas.auto_stop.handler import _has_do_not_auto_stop_tag

        mock_sm = mock_boto3_clients["sagemaker"]
        mock_sm.list_tags.return_value = {
            "Tags": _make_tags({"DoNotAutoStop": "false", "Project": "fsxn-s3ap"})
        }

        result = _has_do_not_auto_stop_tag("unprotected-endpoint")
        assert result is False

    def test_endpoint_without_do_not_auto_stop_tag_is_not_protected(self, mock_boto3_clients):
        """Endpoint without DoNotAutoStop tag is not protected."""
        from shared.lambdas.auto_stop.handler import _has_do_not_auto_stop_tag

        mock_sm = mock_boto3_clients["sagemaker"]
        mock_sm.list_tags.return_value = {
            "Tags": _make_tags({"Project": "fsxn-s3ap"})
        }

        result = _has_do_not_auto_stop_tag("no-tag-endpoint")
        assert result is False

    def test_endpoint_tag_check_error_returns_not_protected(self, mock_boto3_clients):
        """If tag check fails, endpoint is NOT protected (safe default: don't stop)."""
        from shared.lambdas.auto_stop.handler import _has_do_not_auto_stop_tag

        mock_sm = mock_boto3_clients["sagemaker"]
        mock_sm.list_tags.side_effect = Exception("Tag check error")

        result = _has_do_not_auto_stop_tag("error-endpoint")
        assert result is False

    def test_endpoint_with_do_not_auto_stop_case_insensitive(self, mock_boto3_clients):
        """DoNotAutoStop tag check is case-insensitive for value."""
        from shared.lambdas.auto_stop.handler import _has_do_not_auto_stop_tag

        mock_sm = mock_boto3_clients["sagemaker"]
        mock_sm.list_tags.return_value = {
            "Tags": _make_tags({"DoNotAutoStop": "TRUE"})
        }

        result = _has_do_not_auto_stop_tag("case-endpoint")
        assert result is True


# ---------------------------------------------------------------------------
# Tests: DRY_RUN Mode
# ---------------------------------------------------------------------------


class TestDryRunMode:
    """Tests for DRY_RUN mode (no actual scaling)."""

    def test_dry_run_does_not_call_scale_to_zero(self, mock_boto3_clients, monkeypatch):
        """In DRY_RUN mode, no actual scaling operations are performed."""
        import shared.lambdas.auto_stop.handler as handler_module

        # Patch DRY_RUN at module level
        monkeypatch.setattr(handler_module, "DRY_RUN", True)

        mock_sm = mock_boto3_clients["sagemaker"]

        # Setup: one idle endpoint
        paginator_mock = MagicMock()
        paginator_mock.paginate.return_value = [
            {"Endpoints": [_make_endpoint("idle-ep")]}
        ]
        mock_sm.get_paginator.return_value = paginator_mock
        mock_sm.list_tags.return_value = {
            "Tags": _make_tags({"Project": "fsxn-s3ap"})
        }
        mock_sm.describe_endpoint.return_value = {
            "EndpointConfigName": "config-1"
        }
        mock_sm.describe_endpoint_config.return_value = {
            "ProductionVariants": [
                {"InstanceType": "ml.m5.large", "InitialInstanceCount": 1}
            ]
        }

        mock_cw = mock_boto3_clients["cloudwatch"]
        mock_cw.get_metric_data.return_value = {
            "MetricDataResults": [{"Id": "invocations", "Values": [0.0]}]
        }

        result = handler_module.handler({}, None)

        # DRY_RUN: no actual scaling call
        mock_sm.update_endpoint_weights_and_capacities.assert_not_called()
        assert result["dry_run"] is True
        assert result["endpoints_stopped"] == 0

    def test_non_dry_run_calls_scale_to_zero(self, mock_boto3_clients, monkeypatch):
        """When DRY_RUN is false, actual scaling operations are performed."""
        import shared.lambdas.auto_stop.handler as handler_module

        # Patch DRY_RUN at module level
        monkeypatch.setattr(handler_module, "DRY_RUN", False)

        mock_sm = mock_boto3_clients["sagemaker"]

        # Setup: one idle endpoint
        paginator_mock = MagicMock()
        paginator_mock.paginate.return_value = [
            {"Endpoints": [_make_endpoint("idle-ep")]}
        ]
        mock_sm.get_paginator.return_value = paginator_mock
        mock_sm.list_tags.return_value = {
            "Tags": _make_tags({"Project": "fsxn-s3ap"})
        }
        mock_sm.describe_endpoint.return_value = {
            "EndpointConfigName": "config-1"
        }
        mock_sm.describe_endpoint_config.return_value = {
            "ProductionVariants": [
                {"InstanceType": "ml.m5.large", "InitialInstanceCount": 1}
            ]
        }

        mock_cw = mock_boto3_clients["cloudwatch"]
        mock_cw.get_metric_data.return_value = {
            "MetricDataResults": [{"Id": "invocations", "Values": [0.0]}]
        }

        result = handler_module.handler({}, None)

        # Non-DRY_RUN: scaling call should be made
        mock_sm.update_endpoint_weights_and_capacities.assert_called_once()
        assert result["dry_run"] is False
        assert result["endpoints_stopped"] == 1


# ---------------------------------------------------------------------------
# Tests: Scale-to-Zero Action
# ---------------------------------------------------------------------------


class TestScaleToZeroAction:
    """Tests for scale-to-zero action (DesiredInstanceCount=0)."""

    def test_scale_to_zero_calls_update_with_zero_instances(self, mock_boto3_clients, monkeypatch):
        """Scale-to-zero sets DesiredInstanceCount=0 when MIN_INSTANCE_COUNT=0."""
        monkeypatch.setenv("MIN_INSTANCE_COUNT", "0")
        monkeypatch.setenv("AUTO_STOP_ACTION", "scale_down")
        from shared.lambdas.auto_stop.handler import _scale_to_zero

        mock_sm = mock_boto3_clients["sagemaker"]

        _scale_to_zero("test-endpoint")

        mock_sm.update_endpoint_weights_and_capacities.assert_called_once_with(
            EndpointName="test-endpoint",
            DesiredWeightsAndCapacities=[
                {
                    "VariantName": "AllTraffic",
                    "DesiredInstanceCount": 0,
                }
            ],
        )

    def test_scale_to_zero_raises_on_error(self, mock_boto3_clients):
        """Scale-to-zero raises exception if API call fails."""
        from shared.lambdas.auto_stop.handler import _scale_to_zero

        mock_sm = mock_boto3_clients["sagemaker"]
        mock_sm.update_endpoint_weights_and_capacities.side_effect = Exception(
            "API error"
        )

        with pytest.raises(Exception, match="API error"):
            _scale_to_zero("failing-endpoint")


# ---------------------------------------------------------------------------
# Tests: EMF Metrics Output
# ---------------------------------------------------------------------------


class TestEmfMetricsOutput:
    """Tests for EMF metrics output."""

    def test_emit_metrics_outputs_valid_emf_json(self, mock_boto3_clients, capsys):
        """EMF metrics output is valid JSON with correct structure."""
        from shared.lambdas.auto_stop.handler import _emit_metrics

        _emit_metrics(
            endpoints_checked=5,
            endpoints_stopped=2,
            estimated_savings_per_hour=1.5,
        )

        captured = capsys.readouterr()
        emf_data = json.loads(captured.out.strip())

        # Verify EMF structure
        assert "_aws" in emf_data
        assert "CloudWatchMetrics" in emf_data["_aws"]
        assert "Timestamp" in emf_data["_aws"]

        # Verify metric values
        assert emf_data["EndpointsChecked"] == 5
        assert emf_data["EndpointsStoppedCount"] == 2
        assert emf_data["EstimatedSavingsPerHour"] == 1.5

    def test_emit_metrics_includes_namespace(self, mock_boto3_clients, capsys):
        """EMF metrics include correct namespace."""
        from shared.lambdas.auto_stop.handler import _emit_metrics

        _emit_metrics(endpoints_checked=0, endpoints_stopped=0, estimated_savings_per_hour=0.0)

        captured = capsys.readouterr()
        emf_data = json.loads(captured.out.strip())

        metrics_def = emf_data["_aws"]["CloudWatchMetrics"][0]
        assert metrics_def["Namespace"] == "FSxN-S3AP-Patterns/AutoStop"

    def test_emit_metrics_includes_dimensions(self, mock_boto3_clients, capsys):
        """EMF metrics include FunctionName and Environment dimensions."""
        from shared.lambdas.auto_stop.handler import _emit_metrics

        _emit_metrics(endpoints_checked=3, endpoints_stopped=1, estimated_savings_per_hour=0.5)

        captured = capsys.readouterr()
        emf_data = json.loads(captured.out.strip())

        assert "FunctionName" in emf_data
        assert "Environment" in emf_data


# ---------------------------------------------------------------------------
# Tests: Handler Integration
# ---------------------------------------------------------------------------


class TestHandlerIntegration:
    """Integration tests for the handler function."""

    def test_handler_skips_protected_endpoint(self, mock_boto3_clients, monkeypatch):
        """Handler skips endpoints with DoNotAutoStop=true."""
        import shared.lambdas.auto_stop.handler as handler_module

        monkeypatch.setattr(handler_module, "DRY_RUN", False)

        mock_sm = mock_boto3_clients["sagemaker"]

        # Setup: one protected endpoint
        paginator_mock = MagicMock()
        paginator_mock.paginate.return_value = [
            {"Endpoints": [_make_endpoint("protected-ep")]}
        ]
        mock_sm.get_paginator.return_value = paginator_mock

        # First list_tags call for project prefix check, second for DoNotAutoStop check
        mock_sm.list_tags.return_value = {
            "Tags": _make_tags({"Project": "fsxn-s3ap", "DoNotAutoStop": "true"})
        }

        result = handler_module.handler({}, None)

        # Protected endpoint should not be scaled
        mock_sm.update_endpoint_weights_and_capacities.assert_not_called()
        assert result["endpoints_stopped"] == 0

    def test_handler_skips_active_endpoint(self, mock_boto3_clients, monkeypatch):
        """Handler skips endpoints that are actively receiving invocations."""
        import shared.lambdas.auto_stop.handler as handler_module

        monkeypatch.setattr(handler_module, "DRY_RUN", False)

        mock_sm = mock_boto3_clients["sagemaker"]

        # Setup: one active endpoint
        paginator_mock = MagicMock()
        paginator_mock.paginate.return_value = [
            {"Endpoints": [_make_endpoint("active-ep")]}
        ]
        mock_sm.get_paginator.return_value = paginator_mock
        mock_sm.list_tags.return_value = {
            "Tags": _make_tags({"Project": "fsxn-s3ap"})
        }

        mock_cw = mock_boto3_clients["cloudwatch"]
        mock_cw.get_metric_data.return_value = {
            "MetricDataResults": [{"Id": "invocations", "Values": [10.0, 5.0]}]
        }

        result = handler_module.handler({}, None)

        # Active endpoint should not be scaled
        mock_sm.update_endpoint_weights_and_capacities.assert_not_called()
        assert result["endpoints_stopped"] == 0

    def test_handler_returns_correct_summary(self, mock_boto3_clients, monkeypatch):
        """Handler returns correct summary with endpoints_checked and estimated savings."""
        import shared.lambdas.auto_stop.handler as handler_module

        monkeypatch.setattr(handler_module, "DRY_RUN", False)

        mock_sm = mock_boto3_clients["sagemaker"]

        # Setup: two endpoints
        paginator_mock = MagicMock()
        paginator_mock.paginate.return_value = [
            {"Endpoints": [_make_endpoint("ep-1"), _make_endpoint("ep-2")]}
        ]
        mock_sm.get_paginator.return_value = paginator_mock
        mock_sm.list_tags.return_value = {
            "Tags": _make_tags({"Project": "fsxn-s3ap"})
        }
        mock_sm.describe_endpoint.return_value = {
            "EndpointConfigName": "config-1"
        }
        mock_sm.describe_endpoint_config.return_value = {
            "ProductionVariants": [
                {"InstanceType": "ml.m5.large", "InitialInstanceCount": 1}
            ]
        }

        mock_cw = mock_boto3_clients["cloudwatch"]
        mock_cw.get_metric_data.return_value = {
            "MetricDataResults": [{"Id": "invocations", "Values": [0.0]}]
        }

        result = handler_module.handler({}, None)

        assert result["endpoints_checked"] == 2
        assert result["endpoints_stopped"] == 2
        assert result["estimated_savings_per_hour"] > 0
        assert "stop_actions" in result
        assert len(result["stop_actions"]) == 2
