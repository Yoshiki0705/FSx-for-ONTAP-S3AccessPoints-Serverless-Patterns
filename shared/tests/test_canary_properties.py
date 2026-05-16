"""Synthetic Monitoring Canary プロパティベーステスト.

Property 11: Canary Fail-Independence
  - 任意のチェック失敗の組み合わせで全 3 チェックが常に実行・報告される
Property 16: Canary No Sensitive Data in Results
  - 任意の S3 オブジェクト内容が Canary 結果に含まれない（レイテンシとステータスのみ）

**Validates: Requirements 3.5, 3.9**
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from shared.lambdas.canary.s3ap_health_check import (
    CheckResult,
    handler,
)


# --- Hypothesis Strategies ---

# Strategy for which checks should fail (any combination of 3 booleans)
check_failure_strategy = st.tuples(st.booleans(), st.booleans(), st.booleans())

# Strategy for S3 object content (arbitrary text data, excluding surrogates)
s3_content_strategy = st.text(
    alphabet=st.characters(
        min_codepoint=1,
        max_codepoint=65535,
        exclude_categories=("Cs",),  # Exclude surrogates
    ),
    min_size=4,
    max_size=500,
)

# Strategy for latency values
latency_strategy = st.floats(min_value=0.1, max_value=5000.0, allow_nan=False, allow_infinity=False)


# --- Helpers ---


def _make_mock_s3_client(list_fails: bool, get_fails: bool, content: str = "health-ok"):
    """Create a mock S3 client with configurable failure behavior."""
    mock_client = MagicMock()

    if list_fails:
        mock_client.list_objects_v2.side_effect = Exception("S3 ListObjectsV2 timeout")
    else:
        mock_client.list_objects_v2.return_value = {"Contents": []}

    if get_fails:
        mock_client.get_object.side_effect = Exception("S3 GetObject access denied")
    else:
        body_mock = MagicMock()
        body_mock.read.return_value = content.encode("utf-8")
        body_mock.close.return_value = None
        mock_client.get_object.return_value = {"Body": body_mock}

    return mock_client


def _make_mock_secretsmanager_client():
    """Create a mock Secrets Manager client."""
    mock_client = MagicMock()
    mock_client.get_secret_value.return_value = {
        "SecretString": json.dumps({"username": "fsxadmin", "password": "test-pass"})
    }
    return mock_client


def _make_mock_cloudwatch_client():
    """Create a mock CloudWatch client."""
    mock_client = MagicMock()
    mock_client.put_metric_data.return_value = {}
    return mock_client


def _make_mock_http_pool(ontap_fails: bool):
    """Create a mock urllib3 PoolManager."""
    mock_pool = MagicMock()
    if ontap_fails:
        mock_pool.request.side_effect = Exception("ONTAP connection refused")
    else:
        mock_response = MagicMock()
        mock_response.status = 200
        mock_pool.request.return_value = mock_response
    return mock_pool


# --- Property 11: Canary Fail-Independence ---


class TestCanaryFailIndependence:
    """Property 11: Canary Fail-Independence.

    **Validates: Requirements 3.5**

    任意のチェック失敗の組み合わせ（S3AP List, S3AP Get, ONTAP Health）で、
    全 3 チェックが常に実行され、結果に独立して報告されることを検証する。
    """

    @pytest.mark.property
    @given(failures=check_failure_strategy)
    @settings(max_examples=50, deadline=None, suppress_health_check=[
        HealthCheck.function_scoped_fixture,
    ])
    def test_all_checks_always_executed(self, failures: tuple[bool, bool, bool]):
        """任意の失敗組み合わせで全 3 チェックが実行される."""
        list_fails, get_fails, ontap_fails = failures

        # Set up environment
        env_vars = {
            "S3AP_ALIAS": "test-bucket-alias",
            "HEALTH_PREFIX": "health/",
            "HEALTH_KEY": "health/marker.txt",
            "ONTAP_MANAGEMENT_IP": "10.0.0.1",
            "ONTAP_SECRET_ARN": "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:test",
        }

        mock_s3 = _make_mock_s3_client(list_fails, get_fails)
        mock_sm = _make_mock_secretsmanager_client()
        mock_cw = _make_mock_cloudwatch_client()
        mock_http = _make_mock_http_pool(ontap_fails)

        with patch.dict(os.environ, env_vars):
            with patch("shared.lambdas.canary.s3ap_health_check.boto3") as mock_boto3:
                mock_boto3.client.side_effect = lambda service, **kwargs: {
                    "s3": mock_s3,
                    "secretsmanager": mock_sm,
                    "cloudwatch": mock_cw,
                }.get(service, MagicMock())

                with patch("shared.lambdas.canary.s3ap_health_check.urllib3.PoolManager", return_value=mock_http):
                    result = handler()

        # Property: All 3 checks are always present in results
        checks = result["checks"]
        assert len(checks) == 3, (
            f"Expected 3 checks, got {len(checks)}. "
            f"Failures: list={list_fails}, get={get_fails}, ontap={ontap_fails}"
        )

        # Verify each check has the expected structure
        check_names = {c["name"] for c in checks}
        assert "S3AP_List" in check_names
        assert "S3AP_Get" in check_names
        assert "ONTAP_Health" in check_names

        # Verify each check reports independently
        for check in checks:
            assert "passed" in check
            assert "latency_ms" in check
            assert isinstance(check["passed"], bool)
            assert isinstance(check["latency_ms"], float)

    @pytest.mark.property
    @given(failures=check_failure_strategy)
    @settings(max_examples=50, deadline=None, suppress_health_check=[
        HealthCheck.function_scoped_fixture,
    ])
    def test_failure_isolation(self, failures: tuple[bool, bool, bool]):
        """1 つのチェック失敗が他のチェック結果に影響しない."""
        list_fails, get_fails, ontap_fails = failures

        env_vars = {
            "S3AP_ALIAS": "test-bucket-alias",
            "HEALTH_PREFIX": "health/",
            "HEALTH_KEY": "health/marker.txt",
            "ONTAP_MANAGEMENT_IP": "10.0.0.1",
            "ONTAP_SECRET_ARN": "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:test",
        }

        mock_s3 = _make_mock_s3_client(list_fails, get_fails)
        mock_sm = _make_mock_secretsmanager_client()
        mock_cw = _make_mock_cloudwatch_client()
        mock_http = _make_mock_http_pool(ontap_fails)

        with patch.dict(os.environ, env_vars):
            with patch("shared.lambdas.canary.s3ap_health_check.boto3") as mock_boto3:
                mock_boto3.client.side_effect = lambda service, **kwargs: {
                    "s3": mock_s3,
                    "secretsmanager": mock_sm,
                    "cloudwatch": mock_cw,
                }.get(service, MagicMock())

                with patch("shared.lambdas.canary.s3ap_health_check.urllib3.PoolManager", return_value=mock_http):
                    result = handler()

        checks = result["checks"]
        checks_by_name = {c["name"]: c for c in checks}

        # Each check's pass/fail should match its individual failure setting
        assert checks_by_name["S3AP_List"]["passed"] == (not list_fails)
        assert checks_by_name["S3AP_Get"]["passed"] == (not get_fails)
        assert checks_by_name["ONTAP_Health"]["passed"] == (not ontap_fails)

        # Overall status reflects any failure
        any_failure = list_fails or get_fails or ontap_fails
        expected_status = "FAILED" if any_failure else "PASSED"
        assert result["status"] == expected_status


# --- Property 16: Canary No Sensitive Data in Results ---


class TestCanaryNoSensitiveDataInResults:
    """Property 16: Canary No Sensitive Data in Results.

    **Validates: Requirements 3.9**

    任意の S3 オブジェクト内容が Canary 結果に含まれないことを検証する。
    結果にはレイテンシとステータスのみが含まれる。
    """

    @pytest.mark.property
    @given(content=s3_content_strategy)
    @settings(max_examples=100, deadline=None, suppress_health_check=[
        HealthCheck.function_scoped_fixture,
    ])
    def test_s3_content_not_in_result(self, content: str):
        """任意の S3 オブジェクト内容が結果に含まれない."""
        env_vars = {
            "S3AP_ALIAS": "test-bucket-alias",
            "HEALTH_PREFIX": "health/",
            "HEALTH_KEY": "health/marker.txt",
            "ONTAP_MANAGEMENT_IP": "10.0.0.1",
            "ONTAP_SECRET_ARN": "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:test",
        }

        # S3 GetObject returns the content but it should NOT appear in results
        mock_s3 = _make_mock_s3_client(list_fails=False, get_fails=False, content=content)
        mock_sm = _make_mock_secretsmanager_client()
        mock_cw = _make_mock_cloudwatch_client()
        mock_http = _make_mock_http_pool(ontap_fails=False)

        with patch.dict(os.environ, env_vars):
            with patch("shared.lambdas.canary.s3ap_health_check.boto3") as mock_boto3:
                mock_boto3.client.side_effect = lambda service, **kwargs: {
                    "s3": mock_s3,
                    "secretsmanager": mock_sm,
                    "cloudwatch": mock_cw,
                }.get(service, MagicMock())

                with patch("shared.lambdas.canary.s3ap_health_check.urllib3.PoolManager", return_value=mock_http):
                    result = handler()

        # Serialize the entire result to string for content check
        result_str = json.dumps(result)

        # The S3 object content must NOT appear in the result
        # (content is guaranteed to be > 3 chars due to min_size=4 in strategy)
        assert content not in result_str, (
            f"S3 object content leaked into canary result. "
            f"Content (first 50 chars): {content[:50]!r}"
        )

        # Verify result only contains expected fields (status, latency, error messages)
        for check in result["checks"]:
            allowed_keys = {"name", "passed", "latency_ms", "error"}
            assert set(check.keys()) <= allowed_keys, (
                f"Unexpected keys in check result: {set(check.keys()) - allowed_keys}"
            )

    @pytest.mark.property
    @given(content=st.binary(min_size=10, max_size=1000))
    @settings(max_examples=50, deadline=None, suppress_health_check=[
        HealthCheck.function_scoped_fixture,
    ])
    def test_binary_content_not_in_result(self, content: bytes):
        """任意のバイナリ S3 オブジェクト内容が結果に含まれない."""
        env_vars = {
            "S3AP_ALIAS": "test-bucket-alias",
            "HEALTH_PREFIX": "health/",
            "HEALTH_KEY": "health/marker.txt",
            "ONTAP_MANAGEMENT_IP": "10.0.0.1",
            "ONTAP_SECRET_ARN": "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:test",
        }

        # Create mock that returns binary content
        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.return_value = {"Contents": []}
        body_mock = MagicMock()
        body_mock.read.return_value = content
        body_mock.close.return_value = None
        mock_s3.get_object.return_value = {"Body": body_mock}

        mock_sm = _make_mock_secretsmanager_client()
        mock_cw = _make_mock_cloudwatch_client()
        mock_http = _make_mock_http_pool(ontap_fails=False)

        with patch.dict(os.environ, env_vars):
            with patch("shared.lambdas.canary.s3ap_health_check.boto3") as mock_boto3:
                mock_boto3.client.side_effect = lambda service, **kwargs: {
                    "s3": mock_s3,
                    "secretsmanager": mock_sm,
                    "cloudwatch": mock_cw,
                }.get(service, MagicMock())

                with patch("shared.lambdas.canary.s3ap_health_check.urllib3.PoolManager", return_value=mock_http):
                    result = handler()

        # Serialize result and check no binary content leaked
        result_str = json.dumps(result)
        content_hex = content.hex()

        # Binary content should not appear in result (neither raw nor hex-encoded)
        if len(content_hex) > 6:
            assert content_hex not in result_str, (
                f"Binary content (hex) leaked into canary result"
            )
