"""CrossRegionClient ユニットテスト

CrossRegionConfig と CrossRegionClient の動作を検証するユニットテスト。
unittest.mock を使用して外部依存（boto3）をモックする。

Validates: Requirements 13.7, 14.7, 14.4, 14.5, 14.6
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from shared.cross_region_client import CrossRegionClient, CrossRegionConfig
from shared.exceptions import CrossRegionClientError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def default_config() -> CrossRegionConfig:
    """デフォルト設定の CrossRegionConfig を返す"""
    return CrossRegionConfig()


@pytest.fixture
def custom_config() -> CrossRegionConfig:
    """カスタム設定の CrossRegionConfig を返す"""
    return CrossRegionConfig(
        target_region="eu-west-1",
        services=["textract", "comprehendmedical", "rekognition"],
        verify_ssl=False,
        connect_timeout=5,
        read_timeout=30,
    )


@pytest.fixture
def mock_session():
    """モック boto3.Session を返す"""
    session = MagicMock()
    mock_client = MagicMock()
    session.client.return_value = mock_client
    return session


@pytest.fixture
def client(default_config, mock_session) -> CrossRegionClient:
    """テスト用 CrossRegionClient インスタンスを返す"""
    return CrossRegionClient(config=default_config, session=mock_session)


# ---------------------------------------------------------------------------
# TestCrossRegionConfig
# ---------------------------------------------------------------------------


class TestCrossRegionConfig:
    """CrossRegionConfig のテスト"""

    def test_default_region_is_us_east_1(self, default_config: CrossRegionConfig):
        """デフォルトリージョンが us-east-1 であることを検証する"""
        assert default_config.target_region == "us-east-1"

    def test_default_services(self, default_config: CrossRegionConfig):
        """デフォルトの許可サービスリストが textract と comprehendmedical であることを検証する"""
        assert default_config.services == ["textract", "comprehendmedical"]

    def test_tls_verification_enabled_by_default(self, default_config: CrossRegionConfig):
        """TLS 検証がデフォルトで有効であることを検証する"""
        assert default_config.verify_ssl is True

    def test_default_timeouts(self, default_config: CrossRegionConfig):
        """デフォルトのタイムアウト値が正しいことを検証する"""
        assert default_config.connect_timeout == 10
        assert default_config.read_timeout == 60

    def test_custom_values(self, custom_config: CrossRegionConfig):
        """カスタム値がすべて保持されることを検証する"""
        assert custom_config.target_region == "eu-west-1"
        assert custom_config.services == ["textract", "comprehendmedical", "rekognition"]
        assert custom_config.verify_ssl is False
        assert custom_config.connect_timeout == 5
        assert custom_config.read_timeout == 30

    def test_to_dict(self, default_config: CrossRegionConfig):
        """to_dict が正しい辞書を返すことを検証する"""
        d = default_config.to_dict()
        assert d["target_region"] == "us-east-1"
        assert d["services"] == ["textract", "comprehendmedical"]
        assert d["verify_ssl"] is True
        assert d["connect_timeout"] == 10
        assert d["read_timeout"] == 60

    def test_to_dict_from_dict_roundtrip(self, default_config: CrossRegionConfig):
        """to_dict → from_dict のラウンドトリップで等価な設定が復元されることを検証する"""
        d = default_config.to_dict()
        restored = CrossRegionConfig.from_dict(d)
        assert restored.to_dict() == default_config.to_dict()

    def test_from_dict_ignores_unknown_keys(self):
        """from_dict が未知のキーを無視することを検証する"""
        data = {
            "target_region": "us-west-2",
            "services": ["textract"],
            "verify_ssl": True,
            "connect_timeout": 10,
            "read_timeout": 60,
            "unknown_key": "should_be_ignored",
        }
        config = CrossRegionConfig.from_dict(data)
        assert config.target_region == "us-west-2"
        assert config.services == ["textract"]
        assert not hasattr(config, "unknown_key")


# ---------------------------------------------------------------------------
# TestCrossRegionClient
# ---------------------------------------------------------------------------


class TestCrossRegionClient:
    """CrossRegionClient のテスト"""

    def test_get_client_for_allowed_service(self, client: CrossRegionClient, mock_session):
        """許可リスト内のサービスでクライアントが正常に作成されることを検証する"""
        boto_client = client.get_client("textract")

        assert boto_client is not None
        mock_session.client.assert_called_once()
        call_kwargs = mock_session.client.call_args
        assert call_kwargs.args[0] == "textract"
        assert call_kwargs.kwargs["region_name"] == "us-east-1"

    def test_get_client_caches_client(self, client: CrossRegionClient, mock_session):
        """同一サービスの2回目の呼び出しでキャッシュされたクライアントが返されることを検証する"""
        client1 = client.get_client("textract")
        client2 = client.get_client("textract")

        assert client1 is client2
        assert mock_session.client.call_count == 1

    def test_get_client_creates_separate_clients_per_service(
        self, client: CrossRegionClient, mock_session
    ):
        """異なるサービスで別々のクライアントが作成されることを検証する"""
        mock_session.client.side_effect = [MagicMock(), MagicMock()]

        textract_client = client.get_client("textract")
        comprehend_client = client.get_client("comprehendmedical")

        assert textract_client is not comprehend_client
        assert mock_session.client.call_count == 2

    def test_get_client_passes_verify_ssl(self, mock_session):
        """verify_ssl パラメータがクライアント作成時に渡されることを検証する"""
        config = CrossRegionConfig(verify_ssl=True)
        cr_client = CrossRegionClient(config=config, session=mock_session)
        cr_client.get_client("textract")

        call_kwargs = mock_session.client.call_args
        assert call_kwargs.kwargs["verify"] is True

    def test_get_client_passes_verify_ssl_false(self, mock_session):
        """verify_ssl=False がクライアント作成時に渡されることを検証する"""
        config = CrossRegionConfig(verify_ssl=False)
        cr_client = CrossRegionClient(config=config, session=mock_session)
        cr_client.get_client("textract")

        call_kwargs = mock_session.client.call_args
        assert call_kwargs.kwargs["verify"] is False

    def test_disallowed_service_raises_error(self, client: CrossRegionClient):
        """許可リスト外のサービスで CrossRegionClientError が発生することを検証する"""
        with pytest.raises(CrossRegionClientError) as exc_info:
            client.get_client("s3")

        assert "s3" in str(exc_info.value)
        assert "not in allowed services" in str(exc_info.value)

    def test_disallowed_service_error_contains_region(self, client: CrossRegionClient):
        """許可リスト外サービスのエラーにリージョン情報が含まれることを検証する"""
        with pytest.raises(CrossRegionClientError) as exc_info:
            client.get_client("s3")

        assert exc_info.value.target_region == "us-east-1"
        assert exc_info.value.service_name == "s3"

    def test_client_creation_failure_raises_error(self, mock_session):
        """boto3 クライアント作成失敗時に CrossRegionClientError が発生することを検証する"""
        mock_session.client.side_effect = Exception("Connection refused")
        config = CrossRegionConfig()
        cr_client = CrossRegionClient(config=config, session=mock_session)

        with pytest.raises(CrossRegionClientError) as exc_info:
            cr_client.get_client("textract")

        assert "Failed to create client" in str(exc_info.value)
        assert "us-east-1" in str(exc_info.value)
        assert exc_info.value.target_region == "us-east-1"
        assert exc_info.value.service_name == "textract"
        assert exc_info.value.original_error is not None

    def test_analyze_document_success(self, client: CrossRegionClient, mock_session):
        """analyze_document が正常に Textract API を呼び出すことを検証する"""
        mock_textract = mock_session.client.return_value
        mock_textract.analyze_document.return_value = {
            "Blocks": [{"BlockType": "PAGE", "Text": "Hello"}],
        }

        result = client.analyze_document(
            document_bytes=b"fake-pdf-bytes",
            feature_types=["TABLES", "FORMS"],
        )

        assert result["Blocks"][0]["BlockType"] == "PAGE"
        mock_textract.analyze_document.assert_called_once_with(
            Document={"Bytes": b"fake-pdf-bytes"},
            FeatureTypes=["TABLES", "FORMS"],
        )

    def test_analyze_document_default_feature_types(
        self, client: CrossRegionClient, mock_session
    ):
        """analyze_document が feature_types 未指定時にデフォルト値を使用することを検証する"""
        mock_textract = mock_session.client.return_value
        mock_textract.analyze_document.return_value = {"Blocks": []}

        client.analyze_document(document_bytes=b"fake-pdf-bytes")

        call_kwargs = mock_textract.analyze_document.call_args.kwargs
        assert call_kwargs["FeatureTypes"] == ["TABLES", "FORMS"]

    def test_analyze_document_api_failure_raises_error(
        self, client: CrossRegionClient, mock_session
    ):
        """analyze_document の API 呼び出し失敗時に CrossRegionClientError が発生することを検証する"""
        mock_textract = mock_session.client.return_value
        mock_textract.analyze_document.side_effect = Exception("Throttling")

        with pytest.raises(CrossRegionClientError) as exc_info:
            client.analyze_document(document_bytes=b"fake-pdf-bytes")

        assert "Textract AnalyzeDocument failed" in str(exc_info.value)
        assert "us-east-1" in str(exc_info.value)
        assert exc_info.value.target_region == "us-east-1"
        assert exc_info.value.service_name == "textract"
        assert exc_info.value.original_error is not None

    def test_detect_entities_v2_success(self, client: CrossRegionClient, mock_session):
        """detect_entities_v2 が正常に Comprehend Medical API を呼び出すことを検証する"""
        mock_comprehend = mock_session.client.return_value
        mock_comprehend.detect_entities_v2.return_value = {
            "Entities": [
                {"Text": "aspirin", "Category": "MEDICATION", "Score": 0.99},
            ],
        }

        result = client.detect_entities_v2(text="Patient takes aspirin daily.")

        assert result["Entities"][0]["Text"] == "aspirin"
        mock_comprehend.detect_entities_v2.assert_called_once_with(
            Text="Patient takes aspirin daily."
        )

    def test_detect_entities_v2_api_failure_raises_error(
        self, client: CrossRegionClient, mock_session
    ):
        """detect_entities_v2 の API 呼び出し失敗時に CrossRegionClientError が発生することを検証する"""
        mock_comprehend = mock_session.client.return_value
        mock_comprehend.detect_entities_v2.side_effect = Exception("Service unavailable")

        with pytest.raises(CrossRegionClientError) as exc_info:
            client.detect_entities_v2(text="Some medical text")

        assert "Comprehend Medical DetectEntitiesV2 failed" in str(exc_info.value)
        assert "us-east-1" in str(exc_info.value)
        assert exc_info.value.target_region == "us-east-1"
        assert exc_info.value.service_name == "comprehendmedical"
        assert exc_info.value.original_error is not None

    def test_custom_region_in_client_creation(self, mock_session):
        """カスタムリージョンがクライアント作成時に使用されることを検証する"""
        config = CrossRegionConfig(target_region="eu-west-1")
        cr_client = CrossRegionClient(config=config, session=mock_session)
        cr_client.get_client("textract")

        call_kwargs = mock_session.client.call_args
        assert call_kwargs.kwargs["region_name"] == "eu-west-1"

    def test_custom_region_in_error_message(self):
        """カスタムリージョンのエラーメッセージにリージョン情報が含まれることを検証する"""
        config = CrossRegionConfig(target_region="ap-southeast-1")
        session = MagicMock()
        session.client.side_effect = Exception("Endpoint not found")
        cr_client = CrossRegionClient(config=config, session=session)

        with pytest.raises(CrossRegionClientError) as exc_info:
            cr_client.get_client("textract")

        assert "ap-southeast-1" in str(exc_info.value)
        assert exc_info.value.target_region == "ap-southeast-1"

    def test_default_session_created_when_none_provided(self):
        """session 未指定時にデフォルトの boto3.Session が作成されることを検証する"""
        config = CrossRegionConfig()
        cr_client = CrossRegionClient(config=config)

        assert cr_client._session is not None

    def test_analyze_document_error_preserves_chain(
        self, client: CrossRegionClient, mock_session
    ):
        """analyze_document のエラーが元の例外を保持することを検証する"""
        original = ValueError("Invalid document format")
        mock_textract = mock_session.client.return_value
        mock_textract.analyze_document.side_effect = original

        with pytest.raises(CrossRegionClientError) as exc_info:
            client.analyze_document(document_bytes=b"bad-bytes")

        assert exc_info.value.original_error is original

    def test_detect_entities_v2_error_preserves_chain(
        self, client: CrossRegionClient, mock_session
    ):
        """detect_entities_v2 のエラーが元の例外を保持することを検証する"""
        original = RuntimeError("Network timeout")
        mock_comprehend = mock_session.client.return_value
        mock_comprehend.detect_entities_v2.side_effect = original

        with pytest.raises(CrossRegionClientError) as exc_info:
            client.detect_entities_v2(text="test")

        assert exc_info.value.original_error is original



# ---------------------------------------------------------------------------
# TestDiscoverRegionalEndpoints
# ---------------------------------------------------------------------------


class TestDiscoverRegionalEndpoints:
    """discover_regional_endpoints() のテスト — Validates: Requirement 14.4"""

    def test_discovers_from_env_vars(self, mock_session):
        """環境変数から S3 AP ARN を取得する"""
        config = CrossRegionConfig()
        cr_client = CrossRegionClient(
            config=config,
            session=mock_session,
            primary_region="ap-northeast-1",
            secondary_region="us-east-1",
        )

        with patch.dict(
            "os.environ",
            {
                "S3AP_ARN_AP_NORTHEAST_1": "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/primary",
                "S3AP_ARN_US_EAST_1": "arn:aws:s3:us-east-1:123456789012:accesspoint/secondary",
            },
        ):
            endpoints = cr_client.discover_regional_endpoints()

        assert "ap-northeast-1" in endpoints
        assert "us-east-1" in endpoints
        assert endpoints["ap-northeast-1"] == "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/primary"
        assert endpoints["us-east-1"] == "arn:aws:s3:us-east-1:123456789012:accesspoint/secondary"

    def test_falls_back_to_dynamodb_when_env_vars_empty(self, mock_session):
        """環境変数が空の場合に DynamoDB 設定テーブルにフォールバックする"""
        config = CrossRegionConfig()
        cr_client = CrossRegionClient(
            config=config,
            session=mock_session,
            primary_region="ap-northeast-1",
            secondary_region="us-east-1",
        )

        # DynamoDB テーブルのモック
        mock_dynamodb = MagicMock()
        mock_table = MagicMock()
        mock_table.scan.return_value = {
            "Items": [
                {"region": "ap-northeast-1", "s3ap_arn": "arn:aws:s3:ap-northeast-1:123:accesspoint/p"},
                {"region": "us-east-1", "s3ap_arn": "arn:aws:s3:us-east-1:123:accesspoint/s"},
            ]
        }
        mock_dynamodb.Table.return_value = mock_table
        mock_session.resource.return_value = mock_dynamodb

        with patch.dict("os.environ", {}, clear=True):
            # Ensure no S3AP_ARN env vars are set
            import os
            for key in list(os.environ.keys()):
                if key.startswith("S3AP_ARN_"):
                    del os.environ[key]

            endpoints = cr_client.discover_regional_endpoints()

        assert "ap-northeast-1" in endpoints
        assert "us-east-1" in endpoints

    def test_returns_empty_dict_when_no_source_available(self, mock_session):
        """環境変数も DynamoDB も利用不可の場合に空辞書を返す"""
        config = CrossRegionConfig()
        cr_client = CrossRegionClient(
            config=config,
            session=mock_session,
            primary_region="ap-northeast-1",
            secondary_region="us-east-1",
        )

        # DynamoDB アクセス失敗
        mock_dynamodb = MagicMock()
        mock_table = MagicMock()
        mock_table.scan.side_effect = Exception("Table not found")
        mock_dynamodb.Table.return_value = mock_table
        mock_session.resource.return_value = mock_dynamodb

        with patch.dict("os.environ", {}, clear=True):
            import os
            for key in list(os.environ.keys()):
                if key.startswith("S3AP_ARN_"):
                    del os.environ[key]

            endpoints = cr_client.discover_regional_endpoints()

        assert endpoints == {}


# ---------------------------------------------------------------------------
# TestAccessWithFailover
# ---------------------------------------------------------------------------


class TestAccessWithFailover:
    """access_with_failover() のテスト — Validates: Requirements 14.4, 14.5, 14.6"""

    def test_primary_success_returns_primary_region(self, mock_session):
        """Primary リージョン成功時に Primary の結果を返す"""
        config = CrossRegionConfig()
        cr_client = CrossRegionClient(
            config=config,
            session=mock_session,
            primary_region="ap-northeast-1",
            secondary_region="us-east-1",
        )

        # S3 クライアントのモック
        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = {"Body": b"data", "ContentLength": 4}
        mock_session.client.return_value = mock_s3

        with patch("shared.cross_region_client.EmfMetrics") as mock_emf_cls:
            mock_emf = MagicMock()
            mock_emf_cls.return_value = mock_emf

            result = cr_client.access_with_failover(
                "get_object", Bucket="test-bucket", Key="test-key"
            )

        assert result["region_served"] == "ap-northeast-1"
        assert result["is_failover"] is False
        assert "latency_ms" in result
        assert "response" in result

    def test_primary_timeout_triggers_failover_to_secondary(self, mock_session):
        """Primary タイムアウト時に Secondary にフェイルオーバーする"""
        from botocore.exceptions import ConnectTimeoutError

        config = CrossRegionConfig()
        cr_client = CrossRegionClient(
            config=config,
            session=mock_session,
            primary_region="ap-northeast-1",
            secondary_region="us-east-1",
        )

        # Primary は timeout、Secondary は成功
        mock_s3_primary = MagicMock()
        mock_s3_primary.get_object.side_effect = ConnectTimeoutError(endpoint_url="https://s3.ap-northeast-1.amazonaws.com")

        mock_s3_secondary = MagicMock()
        mock_s3_secondary.get_object.return_value = {"Body": b"data", "ContentLength": 4}

        # リージョン別に異なるクライアントを返す
        def client_factory(service, region_name=None, config=None):
            if region_name == "ap-northeast-1":
                return mock_s3_primary
            return mock_s3_secondary

        mock_session.client.side_effect = client_factory

        with patch("shared.cross_region_client.EmfMetrics") as mock_emf_cls:
            mock_emf = MagicMock()
            mock_emf_cls.return_value = mock_emf

            result = cr_client.access_with_failover(
                "get_object", Bucket="test-bucket", Key="test-key"
            )

        assert result["region_served"] == "us-east-1"
        assert result["is_failover"] is True

    def test_both_regions_fail_raises_error(self, mock_session):
        """両リージョン失敗時に CrossRegionClientError を発生させる"""
        from botocore.exceptions import ConnectTimeoutError, ReadTimeoutError

        config = CrossRegionConfig()
        cr_client = CrossRegionClient(
            config=config,
            session=mock_session,
            primary_region="ap-northeast-1",
            secondary_region="us-east-1",
        )

        # 両方 timeout
        mock_s3_primary = MagicMock()
        mock_s3_primary.get_object.side_effect = ConnectTimeoutError(endpoint_url="https://s3.ap-northeast-1.amazonaws.com")

        mock_s3_secondary = MagicMock()
        mock_s3_secondary.get_object.side_effect = ReadTimeoutError(endpoint_url="https://s3.us-east-1.amazonaws.com")

        def client_factory(service, region_name=None, config=None):
            if region_name == "ap-northeast-1":
                return mock_s3_primary
            return mock_s3_secondary

        mock_session.client.side_effect = client_factory

        with patch("shared.cross_region_client.EmfMetrics") as mock_emf_cls:
            mock_emf = MagicMock()
            mock_emf_cls.return_value = mock_emf

            with pytest.raises(CrossRegionClientError) as exc_info:
                cr_client.access_with_failover(
                    "get_object", Bucket="test-bucket", Key="test-key"
                )

            assert "failed in both" in str(exc_info.value)

    def test_4xx_error_does_not_trigger_failover(self, mock_session):
        """4xx エラー（クライアントエラー）はフェイルオーバー対象外"""
        from botocore.exceptions import ClientError

        config = CrossRegionConfig()
        cr_client = CrossRegionClient(
            config=config,
            session=mock_session,
            primary_region="ap-northeast-1",
            secondary_region="us-east-1",
        )

        # 403 Forbidden
        mock_s3 = MagicMock()
        error_response = {
            "Error": {"Code": "AccessDenied", "Message": "Access Denied"},
            "ResponseMetadata": {"HTTPStatusCode": 403},
        }
        mock_s3.get_object.side_effect = ClientError(error_response, "GetObject")
        mock_session.client.return_value = mock_s3

        with patch("shared.cross_region_client.EmfMetrics") as mock_emf_cls:
            mock_emf = MagicMock()
            mock_emf_cls.return_value = mock_emf

            with pytest.raises(CrossRegionClientError) as exc_info:
                cr_client.access_with_failover(
                    "get_object", Bucket="test-bucket", Key="test-key"
                )

            # Should NOT mention failover — it's a client error
            assert "HTTP 403" in str(exc_info.value)
            assert exc_info.value.target_region == "ap-northeast-1"

    def test_5xx_error_triggers_failover(self, mock_session):
        """5xx エラー（サーバーエラー）はフェイルオーバーをトリガーする"""
        from botocore.exceptions import ClientError

        config = CrossRegionConfig()
        cr_client = CrossRegionClient(
            config=config,
            session=mock_session,
            primary_region="ap-northeast-1",
            secondary_region="us-east-1",
        )

        # Primary: 503, Secondary: success
        mock_s3_primary = MagicMock()
        error_response = {
            "Error": {"Code": "ServiceUnavailable", "Message": "Service Unavailable"},
            "ResponseMetadata": {"HTTPStatusCode": 503},
        }
        mock_s3_primary.get_object.side_effect = ClientError(error_response, "GetObject")

        mock_s3_secondary = MagicMock()
        mock_s3_secondary.get_object.return_value = {"Body": b"data", "ContentLength": 4}

        def client_factory(service, region_name=None, config=None):
            if region_name == "ap-northeast-1":
                return mock_s3_primary
            return mock_s3_secondary

        mock_session.client.side_effect = client_factory

        with patch("shared.cross_region_client.EmfMetrics") as mock_emf_cls:
            mock_emf = MagicMock()
            mock_emf_cls.return_value = mock_emf

            result = cr_client.access_with_failover(
                "get_object", Bucket="test-bucket", Key="test-key"
            )

        assert result["region_served"] == "us-east-1"
        assert result["is_failover"] is True


# ---------------------------------------------------------------------------
# TestFailoverMetrics
# ---------------------------------------------------------------------------


class TestFailoverMetrics:
    """フェイルオーバーメトリクス出力のテスト — Validates: Requirement 14.5"""

    def test_emits_failover_count_metric_on_failover(self, mock_session):
        """フェイルオーバー発生時に CrossRegionFailoverCount メトリクスを出力する"""
        from botocore.exceptions import ConnectTimeoutError

        config = CrossRegionConfig()
        cr_client = CrossRegionClient(
            config=config,
            session=mock_session,
            primary_region="ap-northeast-1",
            secondary_region="us-east-1",
        )

        mock_s3_primary = MagicMock()
        mock_s3_primary.get_object.side_effect = ConnectTimeoutError(endpoint_url="https://s3.ap-northeast-1.amazonaws.com")

        mock_s3_secondary = MagicMock()
        mock_s3_secondary.get_object.return_value = {"Body": b"data"}

        def client_factory(service, region_name=None, config=None):
            if region_name == "ap-northeast-1":
                return mock_s3_primary
            return mock_s3_secondary

        mock_session.client.side_effect = client_factory

        with patch("shared.cross_region_client.EmfMetrics") as mock_emf_cls:
            mock_emf = MagicMock()
            mock_emf_cls.return_value = mock_emf

            cr_client.access_with_failover(
                "get_object", Bucket="test-bucket", Key="test-key"
            )

        # Verify CrossRegionFailoverCount was emitted
        failover_calls = [
            call for call in mock_emf.put_metric.call_args_list
            if call.args[0] == "CrossRegionFailoverCount"
        ]
        assert len(failover_calls) == 1
        assert failover_calls[0].args[1] == 1.0
        assert failover_calls[0].args[2] == "Count"

    def test_emits_latency_metric_on_success(self, mock_session):
        """成功時に CrossRegionLatency メトリクスを出力する"""
        config = CrossRegionConfig()
        cr_client = CrossRegionClient(
            config=config,
            session=mock_session,
            primary_region="ap-northeast-1",
            secondary_region="us-east-1",
        )

        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = {"Body": b"data"}
        mock_session.client.return_value = mock_s3

        with patch("shared.cross_region_client.EmfMetrics") as mock_emf_cls:
            mock_emf = MagicMock()
            mock_emf_cls.return_value = mock_emf

            cr_client.access_with_failover(
                "get_object", Bucket="test-bucket", Key="test-key"
            )

        # Verify CrossRegionLatency was emitted
        latency_calls = [
            call for call in mock_emf.put_metric.call_args_list
            if call.args[0] == "CrossRegionLatency"
        ]
        assert len(latency_calls) == 1
        assert latency_calls[0].args[2] == "Milliseconds"

    def test_emits_request_count_metric(self, mock_session):
        """リクエスト時に CrossRegionRequestCount メトリクスを出力する"""
        config = CrossRegionConfig()
        cr_client = CrossRegionClient(
            config=config,
            session=mock_session,
            primary_region="ap-northeast-1",
            secondary_region="us-east-1",
        )

        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = {"Body": b"data"}
        mock_session.client.return_value = mock_s3

        with patch("shared.cross_region_client.EmfMetrics") as mock_emf_cls:
            mock_emf = MagicMock()
            mock_emf_cls.return_value = mock_emf

            cr_client.access_with_failover(
                "get_object", Bucket="test-bucket", Key="test-key"
            )

        # Verify CrossRegionRequestCount was emitted
        request_calls = [
            call for call in mock_emf.put_metric.call_args_list
            if call.args[0] == "CrossRegionRequestCount"
        ]
        assert len(request_calls) == 1
        assert request_calls[0].args[1] == 1.0

    def test_flush_called_after_metrics(self, mock_session):
        """メトリクス出力後に flush が呼ばれることを検証する"""
        config = CrossRegionConfig()
        cr_client = CrossRegionClient(
            config=config,
            session=mock_session,
            primary_region="ap-northeast-1",
            secondary_region="us-east-1",
        )

        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = {"Body": b"data"}
        mock_session.client.return_value = mock_s3

        with patch("shared.cross_region_client.EmfMetrics") as mock_emf_cls:
            mock_emf = MagicMock()
            mock_emf_cls.return_value = mock_emf

            cr_client.access_with_failover(
                "get_object", Bucket="test-bucket", Key="test-key"
            )

        mock_emf.flush.assert_called_once()
