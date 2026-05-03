"""OntapClient ユニットテスト

OntapClientConfig と OntapClient の動作を検証するユニットテスト。
unittest.mock を使用して外部依存（Secrets Manager, urllib3）をモックする。

Validates: Requirements 12.1, 13.1, 13.6
"""

from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock, patch

import pytest

from shared.ontap_client import OntapClient, OntapClientConfig, OntapClientError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def default_config() -> OntapClientConfig:
    """デフォルト設定の OntapClientConfig を返す"""
    return OntapClientConfig(
        management_ip="10.0.0.1",
        secret_name="fsxn/ontap-credentials",
    )


@pytest.fixture
def custom_config() -> OntapClientConfig:
    """カスタム設定の OntapClientConfig を返す"""
    return OntapClientConfig(
        management_ip="192.168.1.100",
        secret_name="custom/secret",
        verify_ssl=False,
        ca_cert_path="/path/to/ca.pem",
        connect_timeout=5.0,
        read_timeout=15.0,
        retry_total=5,
        backoff_factor=1.0,
    )


@pytest.fixture
def mock_session():
    """モック boto3.Session を返す"""
    session = MagicMock()
    sm_client = MagicMock()
    sm_client.get_secret_value.return_value = {
        "SecretString": json.dumps({"username": "admin", "password": "secret123"}),
    }
    session.client.return_value = sm_client
    return session


@pytest.fixture
def client(default_config, mock_session) -> OntapClient:
    """テスト用 OntapClient インスタンスを返す"""
    return OntapClient(config=default_config, session=mock_session)


# ---------------------------------------------------------------------------
# TestOntapClientConfig
# ---------------------------------------------------------------------------

class TestOntapClientConfig:
    """OntapClientConfig のテスト"""

    def test_default_values(self, default_config: OntapClientConfig):
        """デフォルト値が正しく設定されることを検証する"""
        assert default_config.management_ip == "10.0.0.1"
        assert default_config.secret_name == "fsxn/ontap-credentials"
        assert default_config.verify_ssl is True
        assert default_config.ca_cert_path is None
        assert default_config.connect_timeout == 10.0
        assert default_config.read_timeout == 30.0
        assert default_config.retry_total == 3
        assert default_config.backoff_factor == 0.5

    def test_to_dict_from_dict_roundtrip(self, default_config: OntapClientConfig):
        """to_dict → from_dict のラウンドトリップで等価な設定が復元されることを検証する"""
        d = default_config.to_dict()
        restored = OntapClientConfig.from_dict(d)
        assert restored.to_dict() == default_config.to_dict()

    def test_custom_values(self, custom_config: OntapClientConfig):
        """カスタム値がすべて保持されることを検証する"""
        assert custom_config.management_ip == "192.168.1.100"
        assert custom_config.secret_name == "custom/secret"
        assert custom_config.verify_ssl is False
        assert custom_config.ca_cert_path == "/path/to/ca.pem"
        assert custom_config.connect_timeout == 5.0
        assert custom_config.read_timeout == 15.0
        assert custom_config.retry_total == 5
        assert custom_config.backoff_factor == 1.0


# ---------------------------------------------------------------------------
# TestOntapClient
# ---------------------------------------------------------------------------

class TestOntapClient:
    """OntapClient のテスト"""

    def test_tls_verification_enabled_by_default(self, default_config: OntapClientConfig):
        """verify_ssl がデフォルトで True であることを検証する"""
        assert default_config.verify_ssl is True

    def test_warning_emitted_when_tls_disabled(self, mock_session, caplog):
        """verify_ssl=False の場合に警告ログが出力されることを検証する"""
        config = OntapClientConfig(
            management_ip="10.0.0.1",
            secret_name="fsxn/ontap-credentials",
            verify_ssl=False,
        )
        ontap_client = OntapClient(config=config, session=mock_session)

        with caplog.at_level(logging.WARNING, logger="shared.ontap_client"):
            ontap_client._get_pool()

        assert any(
            "TLS verification is disabled" in record.message
            for record in caplog.records
        ), "Expected warning about TLS verification being disabled"

    def test_secrets_manager_failure_raises_descriptive_error(self, default_config):
        """Secrets Manager 失敗時に secret 名を含む OntapClientError が発生することを検証する"""
        session = MagicMock()
        sm_client = MagicMock()
        sm_client.get_secret_value.side_effect = Exception("Access denied")
        session.client.return_value = sm_client

        ontap_client = OntapClient(config=default_config, session=session)

        with pytest.raises(OntapClientError, match="fsxn/ontap-credentials"):
            ontap_client._get_credentials()

    def test_non_2xx_response_raises_error(self, client: OntapClient):
        """非 2xx レスポンスで OntapClientError が発生し、status_code と response_body を含むことを検証する"""
        mock_response = MagicMock()
        mock_response.status = 404
        mock_response.data = b'{"error": "Not found"}'

        mock_pool = MagicMock()
        mock_pool.request.return_value = mock_response

        client._pool = mock_pool
        # Pre-cache credentials so _get_credentials is not called during _request
        client._credentials = {"username": "admin", "password": "secret123"}

        with pytest.raises(OntapClientError) as exc_info:
            client.get("/storage/volumes")

        assert exc_info.value.status_code == 404
        assert exc_info.value.response_body == '{"error": "Not found"}'

    def test_get_request(self, client: OntapClient):
        """GET リクエストが正しい URL とヘッダーで送信されることを検証する"""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.data = json.dumps({"records": []}).encode("utf-8")

        mock_pool = MagicMock()
        mock_pool.request.return_value = mock_response

        client._pool = mock_pool
        client._credentials = {"username": "admin", "password": "secret123"}

        result = client.get("/storage/volumes")

        assert result == {"records": []}
        call_kwargs = mock_pool.request.call_args
        assert call_kwargs.kwargs["method"] == "GET"
        assert "https://10.0.0.1/api/storage/volumes" == call_kwargs.kwargs["url"]
        assert "application/json" in call_kwargs.kwargs["headers"]["Content-Type"]

    def test_post_request(self, client: OntapClient):
        """POST リクエストがボディ付きで正しく送信されることを検証する"""
        mock_response = MagicMock()
        mock_response.status = 201
        mock_response.data = json.dumps({"uuid": "new-vol-uuid"}).encode("utf-8")

        mock_pool = MagicMock()
        mock_pool.request.return_value = mock_response

        client._pool = mock_pool
        client._credentials = {"username": "admin", "password": "secret123"}

        body = {"name": "test_vol", "size": 1073741824}
        result = client.post("/storage/volumes", body=body)

        assert result == {"uuid": "new-vol-uuid"}
        call_kwargs = mock_pool.request.call_args
        assert call_kwargs.kwargs["method"] == "POST"
        assert call_kwargs.kwargs["body"] == json.dumps(body).encode("utf-8")

    def test_list_volumes(self, client: OntapClient):
        """list_volumes が GET /storage/volumes を呼び出し records リストを返すことを検証する"""
        volumes_data = {
            "records": [
                {"uuid": "vol-1", "name": "vol1"},
                {"uuid": "vol-2", "name": "vol2"},
            ],
        }
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.data = json.dumps(volumes_data).encode("utf-8")

        mock_pool = MagicMock()
        mock_pool.request.return_value = mock_response

        client._pool = mock_pool
        client._credentials = {"username": "admin", "password": "secret123"}

        result = client.list_volumes()

        assert len(result) == 2
        assert result[0]["uuid"] == "vol-1"
        assert result[1]["name"] == "vol2"

    def test_get_volume(self, client: OntapClient):
        """get_volume が GET /storage/volumes/{uuid} を呼び出すことを検証する"""
        volume_data = {"uuid": "vol-123", "name": "test_vol", "state": "online"}
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.data = json.dumps(volume_data).encode("utf-8")

        mock_pool = MagicMock()
        mock_pool.request.return_value = mock_response

        client._pool = mock_pool
        client._credentials = {"username": "admin", "password": "secret123"}

        result = client.get_volume("vol-123")

        assert result["uuid"] == "vol-123"
        assert result["name"] == "test_vol"
        call_kwargs = mock_pool.request.call_args
        assert "/api/storage/volumes/vol-123" in call_kwargs.kwargs["url"]

    def test_list_cifs_shares(self, client: OntapClient):
        """list_cifs_shares が GET /protocols/cifs/shares を呼び出し records リストを返すことを検証する"""
        shares_data = {
            "records": [
                {"name": "share1", "path": "/vol1/share1"},
                {"name": "share2", "path": "/vol1/share2"},
            ],
        }
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.data = json.dumps(shares_data).encode("utf-8")

        mock_pool = MagicMock()
        mock_pool.request.return_value = mock_response

        client._pool = mock_pool
        client._credentials = {"username": "admin", "password": "secret123"}

        result = client.list_cifs_shares("svm-uuid-1")

        assert len(result) == 2
        assert result[0]["name"] == "share1"
        call_kwargs = mock_pool.request.call_args
        assert "/api/protocols/cifs/shares" in call_kwargs.kwargs["url"]

    def test_get_svm(self, client: OntapClient):
        """get_svm が GET /svm/svms/{uuid} を呼び出すことを検証する"""
        svm_data = {"uuid": "svm-123", "name": "svm1", "state": "running"}
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.data = json.dumps(svm_data).encode("utf-8")

        mock_pool = MagicMock()
        mock_pool.request.return_value = mock_response

        client._pool = mock_pool
        client._credentials = {"username": "admin", "password": "secret123"}

        result = client.get_svm("svm-123")

        assert result["uuid"] == "svm-123"
        assert result["name"] == "svm1"
        call_kwargs = mock_pool.request.call_args
        assert "/api/svm/svms/svm-123" in call_kwargs.kwargs["url"]
