"""OntapClient ユニットテスト

OntapClientConfig と OntapClient の動作を検証するユニットテスト。
unittest.mock を使用して外部依存（Secrets Manager, urllib3）をモックする。

Validates: Requirements 12.1, 13.1, 13.6
"""

from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock

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

        assert any("TLS verification is disabled" in record.message for record in caplog.records), (
            "Expected warning about TLS verification being disabled"
        )

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


# ---------------------------------------------------------------------------
# Request path safety
# ---------------------------------------------------------------------------


def _client_with_pool(config: OntapClientConfig, response_body: dict | None = None):
    """A client wired to a MagicMock pool, with credentials pre-cached."""
    response = MagicMock()
    response.status = 200
    response.data = json.dumps(response_body if response_body is not None else {}).encode()
    pool = MagicMock()
    pool.request.return_value = response
    client = OntapClient(config)
    client._pool = pool
    client._credentials = {"username": "admin", "password": "secret123"}
    return client, pool


class TestPathSafety:
    """A caller-supplied name must not be able to redirect the request.

    Volume names, share names and relationship UUIDs all reach request paths. A
    value carrying a `..` segment addresses a different endpoint, so a "delete
    this share" call can arrive at a cluster resource. Callers are expected to
    percent-encode each segment; this is the check that does not depend on all of
    them remembering.
    """

    @pytest.mark.parametrize(
        "path",
        [
            "/storage/volumes/../../cluster",
            "/protocols/cifs/shares/..",
            "/storage/volumes/a/../../../cluster/nodes",
            "/storage/volumes/\x00null",
            "/storage/volumes/back\\slash",
            "/storage/volumes/bell\x07",
        ],
    )
    def test_refuses_unsafe_paths(self, default_config, path):
        client, pool = _client_with_pool(default_config)
        with pytest.raises(OntapClientError) as excinfo:
            client.get(path)
        assert excinfo.value.status_code == 400
        pool.request.assert_not_called(), "an unsafe path must not reach the network"

    @pytest.mark.parametrize(
        "path",
        [
            "/storage/volumes",
            "/storage/volumes/my..volume",
            "/protocols/cifs/shares/share.with.dots",
            "/snapmirror/relationships/8b3f-uuid/transfers",
            "/storage/volumes?name=has..dots&fields=uuid",
        ],
    )
    def test_allows_safe_paths(self, default_config, path):
        """`..` inside a name is a legitimate name, not traversal."""
        client, pool = _client_with_pool(default_config)
        client.get(path)
        assert pool.request.called


class TestOntapMessage:
    """Surface ONTAP's own error text, not the HTTP status line."""

    def test_extracts_the_ontap_message(self):
        error = OntapClientError(
            "ONTAP API error: PATCH /snapmirror/relationships/r1 returned 409",
            status_code=409,
            response_body=json.dumps({"error": {"message": "relationship is busy", "code": "13303842"}}),
        )
        assert error.ontap_message == "relationship is busy"

    @pytest.mark.parametrize(
        "body",
        [None, "", "not json at all", json.dumps({"error": "a string, not an object"}), json.dumps([1, 2])],
    )
    def test_falls_back_to_its_own_message(self, body):
        """A transport failure has no ONTAP body; the message must still read."""
        error = OntapClientError("Request timeout for GET /cluster", response_body=body)
        assert error.ontap_message == "Request timeout for GET /cluster"


# ---------------------------------------------------------------------------
# SnapMirror
# ---------------------------------------------------------------------------


class TestSnapMirror:
    """Paths and payloads verified against a live cluster before being lifted here."""

    def test_list_relationships_requests_the_supported_fields_only(self, default_config):
        """`last_transfer_size` is not a field on this endpoint.

        ONTAP 9.17 rejects the whole request when one field name is unknown, and
        the relationship list comes back empty rather than erroring visibly. That
        cost a live debugging session, so the field list is pinned here.
        """
        client, pool = _client_with_pool(default_config, {"records": [{"uuid": "r1"}]})
        records = client.list_snapmirror_relationships()

        assert records == [{"uuid": "r1"}]
        fields = pool.request.call_args.kwargs["fields"]
        assert "last_transfer_size" not in fields["fields"]
        for expected in ("uuid", "source.path", "destination.svm.name", "state", "healthy", "lag_time"):
            assert expected in fields["fields"]
        assert "/api/snapmirror/relationships" in pool.request.call_args.kwargs["url"]

    def test_list_transfers_targets_the_relationship(self, default_config):
        client, pool = _client_with_pool(default_config, {"records": [{"state": "success"}]})
        records = client.list_snapmirror_transfers("r1")

        assert records == [{"state": "success"}]
        assert pool.request.call_args.kwargs["url"].endswith("/snapmirror/relationships/r1/transfers")
        assert pool.request.call_args.kwargs["fields"]["fields"] == client.TRANSFER_FIELDS

    def test_empty_records_gives_an_empty_list(self, default_config):
        client, _pool = _client_with_pool(default_config, {})
        assert client.list_snapmirror_relationships() == []
        assert client.list_snapmirror_transfers("r1") == []

    @pytest.mark.parametrize(
        "method_name,expected_state",
        [
            ("quiesce_snapmirror", "paused"),
            ("resume_snapmirror", "snapmirrored"),
            ("break_snapmirror", "broken_off"),
            ("resync_snapmirror", "snapmirrored"),
        ],
    )
    def test_state_changes_patch_the_relationship(self, default_config, method_name, expected_state):
        client, pool = _client_with_pool(default_config, {"job": {"uuid": "j1"}})
        getattr(client, method_name)("r1")

        kwargs = pool.request.call_args.kwargs
        assert kwargs["method"] == "PATCH"
        assert kwargs["url"].endswith("/snapmirror/relationships/r1")
        assert json.loads(kwargs["body"]) == {"state": expected_state}

    def test_update_now_posts_a_transfer(self, default_config):
        client, pool = _client_with_pool(default_config, {"job": {"uuid": "j1"}})
        result = client.update_snapmirror_now("r1")

        assert result == {"job": {"uuid": "j1"}}
        kwargs = pool.request.call_args.kwargs
        assert kwargs["method"] == "POST"
        assert kwargs["url"].endswith("/snapmirror/relationships/r1/transfers")
        # An on-demand transfer takes no payload; sending one would be a change in
        # what ONTAP is asked to do.
        assert "body" not in kwargs

    def test_abort_patches_the_named_transfer(self, default_config):
        client, pool = _client_with_pool(default_config)
        client.abort_snapmirror_transfer("r1", "t1")

        kwargs = pool.request.call_args.kwargs
        assert kwargs["method"] == "PATCH"
        assert kwargs["url"].endswith("/snapmirror/relationships/r1/transfers/t1")
        assert json.loads(kwargs["body"]) == {"state": "aborted"}

    def test_delete_removes_the_relationship(self, default_config):
        client, pool = _client_with_pool(default_config, {"job": {"uuid": "j1"}})
        client.delete_snapmirror("r1")

        kwargs = pool.request.call_args.kwargs
        assert kwargs["method"] == "DELETE"
        assert kwargs["url"].endswith("/snapmirror/relationships/r1")

    def test_a_traversal_uuid_is_refused_before_the_request(self, default_config):
        """The SnapMirror paths interpolate the UUID directly, so this is the guard."""
        client, pool = _client_with_pool(default_config)
        with pytest.raises(OntapClientError):
            client.break_snapmirror("../../cluster")
        pool.request.assert_not_called()
