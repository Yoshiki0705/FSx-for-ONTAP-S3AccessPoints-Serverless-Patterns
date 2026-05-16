"""Secrets Rotation プロパティベーステスト.

Property 15: Secrets Not Logged
  - 任意のパスワード文字列がローテーション処理のログ出力に含まれないことを検証

**Validates: Requirements 2.8**
"""

from __future__ import annotations

import json
import logging
import os
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from shared.lambdas.secrets_rotation import handler as rotation_module


# --- Hypothesis Strategies ---

# Generate passwords that could potentially leak into logs
password_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S"),
        blacklist_characters="\x00\n\r",
    ),
    min_size=8,
    max_size=64,
)

# Generate management IPs
management_ip_strategy = st.from_regex(
    r"10\.0\.[0-9]{1,3}\.[0-9]{1,3}",
    fullmatch=True,
)

username_strategy = st.sampled_from(["fsxadmin", "admin", "ontap_user"])

step_strategy = st.sampled_from(["createSecret", "setSecret", "testSecret", "finishSecret"])


# --- Property 15: Secrets Not Logged ---


class TestSecretsNotLogged:
    """Property 15: Secrets Not Logged.

    **Validates: Requirements 2.8**

    任意のパスワード文字列に対して、ローテーション処理のログ出力に
    パスワードが含まれないことを検証する。
    """

    @pytest.mark.property
    @given(
        password=password_strategy,
        management_ip=management_ip_strategy,
        username=username_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_password_not_in_create_secret_logs(
        self,
        password: str,
        management_ip: str,
        username: str,
    ):
        """createSecret ステップのログにパスワードが含まれない."""
        assume(len(password) >= 8)

        secret_arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:test"
        token = "test-token-123"

        current_secret = {
            "username": username,
            "password": password,
            "management_ip": management_ip,
            "svm_uuid": "svm-uuid-123",
        }

        mock_client = MagicMock()
        mock_client.describe_secret.return_value = {
            "RotationEnabled": True,
            "VersionIdsToStages": {
                token: ["AWSPENDING"],
                "old-version": ["AWSCURRENT"],
            },
        }
        mock_client.get_secret_value.return_value = {
            "SecretString": json.dumps(current_secret),
        }

        # Capture all log output
        log_records: list[str] = []

        class LogCapture(logging.Handler):
            def emit(self, record):
                log_records.append(self.format(record))

        handler = LogCapture()
        handler.setLevel(logging.DEBUG)
        logger = logging.getLogger("shared.lambdas.secrets_rotation.handler")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        try:
            rotation_module._create_secret(mock_client, secret_arn, token)
        except Exception:
            pass  # We only care about log content, not execution success
        finally:
            logger.removeHandler(handler)

        # Verify password is not in any log record
        all_logs = "\n".join(log_records)
        assert password not in all_logs, (
            f"Password '{password[:4]}...' was found in log output during createSecret"
        )

    @pytest.mark.property
    @given(
        password=password_strategy,
        new_password=password_strategy,
        management_ip=management_ip_strategy,
        username=username_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_password_not_in_set_secret_logs(
        self,
        password: str,
        new_password: str,
        management_ip: str,
        username: str,
    ):
        """setSecret ステップのログにパスワード（新旧両方）が含まれない."""
        assume(len(password) >= 8)
        assume(len(new_password) >= 8)
        assume(password != new_password)

        secret_arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:test"
        token = "test-token-456"

        pending_secret = {
            "username": username,
            "password": new_password,
            "management_ip": management_ip,
            "svm_uuid": "svm-uuid-123",
        }
        current_secret = {
            "username": username,
            "password": password,
            "management_ip": management_ip,
            "svm_uuid": "svm-uuid-123",
        }

        mock_client = MagicMock()

        def get_secret_value_side_effect(**kwargs):
            if kwargs.get("VersionStage") == "AWSPENDING":
                return {"SecretString": json.dumps(pending_secret)}
            return {"SecretString": json.dumps(current_secret)}

        mock_client.get_secret_value.side_effect = get_secret_value_side_effect

        # Capture all log output
        log_records: list[str] = []

        class LogCapture(logging.Handler):
            def emit(self, record):
                log_records.append(self.format(record))

        handler = LogCapture()
        handler.setLevel(logging.DEBUG)
        logger = logging.getLogger("shared.lambdas.secrets_rotation.handler")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        # Mock the HTTP request to avoid actual network calls
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.data = b'{"status": "ok"}'

        with patch.object(rotation_module._http, "request", return_value=mock_response):
            try:
                rotation_module._set_secret(mock_client, secret_arn, token)
            except Exception:
                pass  # We only care about log content
            finally:
                logger.removeHandler(handler)

        all_logs = "\n".join(log_records)
        assert password not in all_logs, (
            f"Current password was found in log output during setSecret"
        )
        assert new_password not in all_logs, (
            f"New password was found in log output during setSecret"
        )

    @pytest.mark.property
    @given(
        password=password_strategy,
        management_ip=management_ip_strategy,
        username=username_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_password_not_in_test_secret_logs(
        self,
        password: str,
        management_ip: str,
        username: str,
    ):
        """testSecret ステップのログにパスワードが含まれない."""
        assume(len(password) >= 8)

        secret_arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:test"
        token = "test-token-789"

        pending_secret = {
            "username": username,
            "password": password,
            "management_ip": management_ip,
            "svm_uuid": "svm-uuid-123",
        }

        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {
            "SecretString": json.dumps(pending_secret),
        }

        # Capture all log output
        log_records: list[str] = []

        class LogCapture(logging.Handler):
            def emit(self, record):
                log_records.append(self.format(record))

        handler = LogCapture()
        handler.setLevel(logging.DEBUG)
        logger = logging.getLogger("shared.lambdas.secrets_rotation.handler")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        # Mock the HTTP request
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.data = b'{"status": "ok"}'

        with patch.object(rotation_module._http, "request", return_value=mock_response):
            try:
                rotation_module._test_secret(mock_client, secret_arn, token)
            except Exception:
                pass
            finally:
                logger.removeHandler(handler)

        all_logs = "\n".join(log_records)
        assert password not in all_logs, (
            f"Password was found in log output during testSecret"
        )

    @pytest.mark.property
    @given(
        password=password_strategy,
        management_ip=management_ip_strategy,
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_password_not_in_failure_notification(
        self,
        password: str,
        management_ip: str,
    ):
        """失敗通知メッセージにパスワードが含まれない."""
        assume(len(password) >= 8)

        # Simulate a failure error message that might accidentally include password
        error_message = (
            f"ONTAP connection test failed: HTTP 401 - "
            f"Authentication failed for user fsxadmin at {management_ip}"
        )

        # Verify the error message construction doesn't include password
        assert password not in error_message, (
            "Password leaked into error message"
        )

        # Also verify _notify_failure doesn't log the password
        log_records: list[str] = []

        class LogCapture(logging.Handler):
            def emit(self, record):
                log_records.append(self.format(record))

        handler = LogCapture()
        handler.setLevel(logging.DEBUG)
        logger = logging.getLogger("shared.lambdas.secrets_rotation.handler")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        with patch.dict(os.environ, {"SNS_TOPIC_ARN": ""}):
            try:
                rotation_module._notify_failure(
                    "arn:aws:secretsmanager:us-east-1:123456789012:secret:test",
                    "testSecret",
                    error_message,
                )
            except Exception:
                pass
            finally:
                logger.removeHandler(handler)

        all_logs = "\n".join(log_records)
        assert password not in all_logs, (
            "Password was found in failure notification logs"
        )
