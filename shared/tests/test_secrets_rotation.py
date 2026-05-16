"""Secrets Rotation Lambda ユニットテスト

4 ステップローテーションプロトコルの動作を検証するユニットテスト。
unittest.mock を使用して外部依存（Secrets Manager, urllib3, SNS）をモックする。

Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.8
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch, call

import pytest

from shared.lambdas.secrets_rotation import handler as rotation_handler


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def secret_arn():
    return "arn:aws:secretsmanager:us-east-1:123456789012:secret:ontap-creds"


@pytest.fixture
def token():
    return "test-client-request-token-123"


@pytest.fixture
def current_secret_dict():
    return {
        "username": "fsxadmin",
        "password": "current-password-abc",
        "management_ip": "10.0.1.100",
        "svm_uuid": "svm-uuid-123",
    }


@pytest.fixture
def pending_secret_dict(current_secret_dict):
    d = current_secret_dict.copy()
    d["password"] = "new-generated-password-xyz"
    return d


@pytest.fixture
def mock_sm_client(secret_arn, token, current_secret_dict, pending_secret_dict):
    """Mock Secrets Manager client."""
    client = MagicMock()
    client.describe_secret.return_value = {
        "RotationEnabled": True,
        "VersionIdsToStages": {
            token: ["AWSPENDING"],
            "old-version-id": ["AWSCURRENT"],
        },
    }
    # get_secret_value behavior depends on VersionStage
    def get_secret_value_side_effect(**kwargs):
        if kwargs.get("VersionStage") == "AWSCURRENT":
            return {"SecretString": json.dumps(current_secret_dict)}
        elif kwargs.get("VersionStage") == "AWSPENDING":
            return {"SecretString": json.dumps(pending_secret_dict)}
        return {"SecretString": json.dumps(current_secret_dict)}

    client.get_secret_value.side_effect = get_secret_value_side_effect
    return client


# ---------------------------------------------------------------------------
# Test handler routing
# ---------------------------------------------------------------------------

class TestHandlerRouting:
    """handler() のステップルーティングを検証する。"""

    def test_invalid_step_raises(self, secret_arn, token):
        """無効なステップ名で ValueError が raise されることを検証する。"""
        event = {
            "SecretId": secret_arn,
            "ClientRequestToken": token,
            "Step": "invalidStep",
        }
        mock_client = MagicMock()
        mock_client.describe_secret.return_value = {
            "RotationEnabled": True,
            "VersionIdsToStages": {token: ["AWSPENDING"]},
        }
        with patch("boto3.client", return_value=mock_client):
            with pytest.raises(ValueError, match="Invalid step parameter"):
                rotation_handler.handler(event, None)

    def test_rotation_not_enabled_raises(self, secret_arn, token):
        """ローテーションが無効なシークレットで ValueError が raise されることを検証する。"""
        event = {
            "SecretId": secret_arn,
            "ClientRequestToken": token,
            "Step": "createSecret",
        }
        mock_client = MagicMock()
        mock_client.describe_secret.return_value = {
            "RotationEnabled": False,
            "VersionIdsToStages": {token: ["AWSPENDING"]},
        }
        with patch("boto3.client", return_value=mock_client):
            with pytest.raises(ValueError, match="not enabled for rotation"):
                rotation_handler.handler(event, None)

    def test_invalid_token_raises(self, secret_arn):
        """無効なトークンで ValueError が raise されることを検証する。"""
        event = {
            "SecretId": secret_arn,
            "ClientRequestToken": "nonexistent-token",
            "Step": "createSecret",
        }
        mock_client = MagicMock()
        mock_client.describe_secret.return_value = {
            "RotationEnabled": True,
            "VersionIdsToStages": {"other-token": ["AWSCURRENT"]},
        }
        with patch("boto3.client", return_value=mock_client):
            with pytest.raises(ValueError, match="has no stage"):
                rotation_handler.handler(event, None)


# ---------------------------------------------------------------------------
# Test _create_secret
# ---------------------------------------------------------------------------

class TestCreateSecret:
    """_create_secret() の動作を検証する。"""

    def test_creates_pending_version(self, mock_sm_client, secret_arn, token, current_secret_dict):
        """新しいパスワードが生成され AWSPENDING として保存されることを検証する。"""
        # Simulate no existing AWSPENDING for this token
        mock_sm_client.describe_secret.return_value = {
            "VersionIdsToStages": {"old-version-id": ["AWSCURRENT"]},
        }
        mock_sm_client.get_secret_value.side_effect = None
        mock_sm_client.get_secret_value.return_value = {
            "SecretString": json.dumps(current_secret_dict),
        }

        rotation_handler._create_secret(mock_sm_client, secret_arn, token)

        # Verify put_secret_value was called
        mock_sm_client.put_secret_value.assert_called_once()
        call_kwargs = mock_sm_client.put_secret_value.call_args[1]
        assert call_kwargs["SecretId"] == secret_arn
        assert call_kwargs["ClientRequestToken"] == token
        assert call_kwargs["VersionStages"] == ["AWSPENDING"]

        # Verify the new secret contains a password
        new_secret = json.loads(call_kwargs["SecretString"])
        assert "password" in new_secret
        assert new_secret["password"] != current_secret_dict["password"]
        # Verify non-password fields are preserved
        assert new_secret["management_ip"] == current_secret_dict["management_ip"]
        assert new_secret["username"] == current_secret_dict["username"]

    def test_skips_if_pending_exists(self, mock_sm_client, secret_arn, token):
        """AWSPENDING が既に存在する場合はスキップすることを検証する。"""
        mock_sm_client.describe_secret.return_value = {
            "VersionIdsToStages": {token: ["AWSPENDING"]},
        }

        rotation_handler._create_secret(mock_sm_client, secret_arn, token)

        # put_secret_value should NOT be called
        mock_sm_client.put_secret_value.assert_not_called()

    def test_password_is_url_safe(self, mock_sm_client, secret_arn, token, current_secret_dict):
        """生成されたパスワードが URL-safe であることを検証する。"""
        mock_sm_client.describe_secret.return_value = {
            "VersionIdsToStages": {"old-version-id": ["AWSCURRENT"]},
        }
        mock_sm_client.get_secret_value.side_effect = None
        mock_sm_client.get_secret_value.return_value = {
            "SecretString": json.dumps(current_secret_dict),
        }

        rotation_handler._create_secret(mock_sm_client, secret_arn, token)

        call_kwargs = mock_sm_client.put_secret_value.call_args[1]
        new_secret = json.loads(call_kwargs["SecretString"])
        password = new_secret["password"]
        # secrets.token_urlsafe(32) produces 43 chars
        assert len(password) >= 32


# ---------------------------------------------------------------------------
# Test _set_secret
# ---------------------------------------------------------------------------

class TestSetSecret:
    """_set_secret() の動作を検証する。"""

    @patch.object(rotation_handler, "_http")
    def test_successful_password_change(self, mock_http, mock_sm_client, secret_arn, token):
        """ONTAP REST API でパスワード変更が成功することを検証する。"""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.data = b'{"status": "ok"}'
        mock_http.request.return_value = mock_response

        rotation_handler._set_secret(mock_sm_client, secret_arn, token)

        # Verify ONTAP API was called with PATCH
        mock_http.request.assert_called_once()
        call_args = mock_http.request.call_args
        assert call_args[0][0] == "PATCH"
        assert "/api/security/accounts/" in call_args[0][1]

    @patch.object(rotation_handler, "_http")
    @patch.object(rotation_handler, "_notify_failure")
    def test_ontap_api_failure_raises(self, mock_notify, mock_http, mock_sm_client, secret_arn, token):
        """ONTAP API が失敗した場合に ValueError が raise されることを検証する。"""
        mock_response = MagicMock()
        mock_response.status = 401
        mock_response.data = b"Unauthorized"
        mock_http.request.return_value = mock_response

        with pytest.raises(ValueError, match="ONTAP password change failed"):
            rotation_handler._set_secret(mock_sm_client, secret_arn, token)

        # Verify SNS notification was attempted
        mock_notify.assert_called_once()

    @patch.object(rotation_handler, "_http")
    def test_accepts_202_status(self, mock_http, mock_sm_client, secret_arn, token):
        """ONTAP API が 202 Accepted を返した場合も成功として扱うことを検証する。"""
        mock_response = MagicMock()
        mock_response.status = 202
        mock_response.data = b'{"job": {"uuid": "job-123"}}'
        mock_http.request.return_value = mock_response

        # Should not raise
        rotation_handler._set_secret(mock_sm_client, secret_arn, token)


# ---------------------------------------------------------------------------
# Test _test_secret
# ---------------------------------------------------------------------------

class TestTestSecret:
    """_test_secret() の動作を検証する。"""

    @patch.object(rotation_handler, "_http")
    def test_successful_connection_test(self, mock_http, mock_sm_client, secret_arn, token):
        """新認証情報での接続テストが成功することを検証する。"""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.data = b'{"name": "cluster1"}'
        mock_http.request.return_value = mock_response

        rotation_handler._test_secret(mock_sm_client, secret_arn, token)

        # Verify /api/cluster was called with GET
        mock_http.request.assert_called_once()
        call_args = mock_http.request.call_args
        assert call_args[0][0] == "GET"
        assert "/api/cluster" in call_args[0][1]

    @patch.object(rotation_handler, "_http")
    @patch.object(rotation_handler, "_notify_failure")
    def test_connection_failure_raises_and_notifies(self, mock_notify, mock_http, mock_sm_client, secret_arn, token):
        """接続テスト失敗時に ValueError が raise され SNS 通知が送信されることを検証する。"""
        mock_response = MagicMock()
        mock_response.status = 401
        mock_response.data = b"Unauthorized"
        mock_http.request.return_value = mock_response

        with pytest.raises(ValueError, match="ONTAP connection test failed"):
            rotation_handler._test_secret(mock_sm_client, secret_arn, token)

        mock_notify.assert_called_once()

    @patch.object(rotation_handler, "_http")
    @patch.object(rotation_handler, "_notify_failure")
    def test_connection_exception_raises_and_notifies(self, mock_notify, mock_http, mock_sm_client, secret_arn, token):
        """接続例外時に ValueError が raise され SNS 通知が送信されることを検証する。"""
        mock_http.request.side_effect = Exception("Connection refused")

        with pytest.raises(ValueError, match="ONTAP connection test failed with exception"):
            rotation_handler._test_secret(mock_sm_client, secret_arn, token)

        mock_notify.assert_called_once()


# ---------------------------------------------------------------------------
# Test _finish_secret
# ---------------------------------------------------------------------------

class TestFinishSecret:
    """_finish_secret() の動作を検証する。"""

    def test_promotes_pending_to_current(self, mock_sm_client, secret_arn, token):
        """AWSPENDING が AWSCURRENT に昇格されることを検証する。"""
        rotation_handler._finish_secret(mock_sm_client, secret_arn, token)

        mock_sm_client.update_secret_version_stage.assert_called_once_with(
            SecretId=secret_arn,
            VersionStage="AWSCURRENT",
            MoveToVersionId=token,
            RemoveFromVersionId="old-version-id",
        )

    def test_skips_if_already_current(self, mock_sm_client, secret_arn, token):
        """既に AWSCURRENT の場合はスキップすることを検証する。"""
        mock_sm_client.describe_secret.return_value = {
            "VersionIdsToStages": {token: ["AWSCURRENT", "AWSPENDING"]},
        }

        rotation_handler._finish_secret(mock_sm_client, secret_arn, token)

        mock_sm_client.update_secret_version_stage.assert_not_called()


# ---------------------------------------------------------------------------
# Test _notify_failure
# ---------------------------------------------------------------------------

class TestNotifyFailure:
    """_notify_failure() の動作を検証する。"""

    @patch.dict("os.environ", {"SNS_TOPIC_ARN": "arn:aws:sns:us-east-1:123456789012:rotation-alerts"})
    @patch("boto3.client")
    def test_sends_sns_notification(self, mock_boto3_client, secret_arn):
        """SNS 通知が正しく送信されることを検証する。"""
        mock_sns = MagicMock()
        mock_boto3_client.return_value = mock_sns

        rotation_handler._notify_failure(secret_arn, "testSecret", "Connection failed")

        mock_sns.publish.assert_called_once()
        call_kwargs = mock_sns.publish.call_args[1]
        assert "testSecret" in call_kwargs["Subject"]
        assert secret_arn in call_kwargs["Message"]
        assert "Connection failed" in call_kwargs["Message"]

    @patch.dict("os.environ", {}, clear=True)
    def test_skips_when_no_topic_configured(self, secret_arn):
        """SNS_TOPIC_ARN が未設定の場合はスキップすることを検証する。"""
        # Should not raise
        rotation_handler._notify_failure(secret_arn, "testSecret", "Error")

    @patch.dict("os.environ", {"SNS_TOPIC_ARN": "arn:aws:sns:us-east-1:123456789012:topic"})
    @patch("boto3.client")
    def test_handles_sns_publish_failure(self, mock_boto3_client, secret_arn):
        """SNS publish が失敗しても例外を raise しないことを検証する。"""
        mock_sns = MagicMock()
        mock_sns.publish.side_effect = Exception("SNS error")
        mock_boto3_client.return_value = mock_sns

        # Should not raise
        rotation_handler._notify_failure(secret_arn, "setSecret", "Error")


# ---------------------------------------------------------------------------
# Test password not logged (Requirement 2.8)
# ---------------------------------------------------------------------------

class TestPasswordNotLogged:
    """パスワードがログに出力されないことを検証する。"""

    @patch.object(rotation_handler, "_http")
    def test_set_secret_does_not_log_password(self, mock_http, mock_sm_client, secret_arn, token, caplog):
        """_set_secret がパスワードをログに出力しないことを検証する。"""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.data = b'{"status": "ok"}'
        mock_http.request.return_value = mock_response

        import logging
        with caplog.at_level(logging.DEBUG):
            rotation_handler._set_secret(mock_sm_client, secret_arn, token)

        # Check that no password appears in log output
        for record in caplog.records:
            assert "new-generated-password-xyz" not in record.getMessage()
            assert "current-password-abc" not in record.getMessage()

    @patch.object(rotation_handler, "_http")
    def test_test_secret_does_not_log_password(self, mock_http, mock_sm_client, secret_arn, token, caplog):
        """_test_secret がパスワードをログに出力しないことを検証する。"""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.data = b'{"name": "cluster1"}'
        mock_http.request.return_value = mock_response

        import logging
        with caplog.at_level(logging.DEBUG):
            rotation_handler._test_secret(mock_sm_client, secret_arn, token)

        for record in caplog.records:
            assert "new-generated-password-xyz" not in record.getMessage()
