"""UC18 通信業界 Discovery Lambda ユニットテスト

Discovery Lambda のファイルフィルタリングロジック、
S3 AP 接続性バリデーション、サフィックスフィルタ処理をテストする。
AWS サービス呼び出しは unittest.mock でモック化。
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# shared モジュールのパスを追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# handler モジュールを動的にインポート
_handler_path = os.path.join(os.path.dirname(__file__), "..", "functions", "discovery", "handler.py")
_spec = importlib.util.spec_from_file_location("telecom_discovery_handler", _handler_path)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

parse_suffix_filter = _module.parse_suffix_filter
validate_s3ap_connectivity = _module.validate_s3ap_connectivity
DEFAULT_CDR_SUFFIX_FILTER = _module.DEFAULT_CDR_SUFFIX_FILTER
MAX_SUFFIX_PATTERNS = _module.MAX_SUFFIX_PATTERNS
handler = _module.handler


# =========================================================================
# parse_suffix_filter テスト
# =========================================================================


class TestParseSuffixFilter:
    """サフィックスフィルタパース関数のテスト"""

    def test_default_filter_parses_correctly(self):
        """デフォルトフィルタ '.csv,.asn1,.parquet' が正しくパースされる"""
        result = parse_suffix_filter(".csv,.asn1,.parquet")
        assert result == [".csv", ".asn1", ".parquet"]

    def test_empty_string_returns_empty_list(self):
        """空文字列で空リストを返す"""
        assert parse_suffix_filter("") == []

    def test_whitespace_only_returns_empty_list(self):
        """空白のみの文字列で空リストを返す"""
        assert parse_suffix_filter("   ") == []

    def test_strips_whitespace_from_entries(self):
        """各エントリの前後空白が除去される"""
        result = parse_suffix_filter(" .csv , .asn1 , .parquet ")
        assert result == [".csv", ".asn1", ".parquet"]

    def test_filters_empty_entries(self):
        """カンマ区切りで空エントリが除外される"""
        result = parse_suffix_filter(".csv,,,.asn1,")
        assert result == [".csv", ".asn1"]

    def test_single_suffix(self):
        """単一サフィックスが正しくパースされる"""
        result = parse_suffix_filter(".csv")
        assert result == [".csv"]

    def test_max_20_patterns_enforced(self):
        """21 以上のパターンが 20 に切り捨てられる"""
        suffixes = ",".join([f".ext{i}" for i in range(25)])
        result = parse_suffix_filter(suffixes)
        assert len(result) == MAX_SUFFIX_PATTERNS
        assert result[0] == ".ext0"
        assert result[19] == ".ext19"

    def test_exactly_20_patterns_accepted(self):
        """20 パターンがそのまま受け入れられる"""
        suffixes = ",".join([f".ext{i}" for i in range(20)])
        result = parse_suffix_filter(suffixes)
        assert len(result) == 20

    def test_none_like_empty_returns_empty(self):
        """None 相当のケース（空文字列）で空リストを返す"""
        result = parse_suffix_filter("")
        assert result == []


# =========================================================================
# validate_s3ap_connectivity テスト
# =========================================================================


class TestValidateS3apConnectivity:
    """S3 AP 接続性バリデーションのテスト"""

    def test_successful_connectivity_returns_none(self):
        """接続成功時に None を返す"""
        mock_s3ap = MagicMock()
        mock_s3ap.list_objects.return_value = []

        result = validate_s3ap_connectivity(mock_s3ap)
        assert result is None
        mock_s3ap.list_objects.assert_called_once_with(prefix="", suffix="", max_keys=1)

    def test_s3ap_error_returns_structured_error(self):
        """S3ApHelperError で構造化エラーレスポンスを返す"""
        from shared.exceptions import S3ApHelperError

        mock_s3ap = MagicMock()
        mock_s3ap.bucket_param = "test-ap-alias-ext-s3alias"
        mock_s3ap.list_objects.side_effect = S3ApHelperError("Access denied", error_code="AccessDenied")

        result = validate_s3ap_connectivity(mock_s3ap)
        assert result is not None
        assert result["statusCode"] == 503
        body = json.loads(result["body"])
        assert body["error"] == "S3 Access Point unreachable"
        assert body["error_type"] == "ConnectivityError"
        assert body["error_code"] == "AccessDenied"
        assert body["access_point"] == "test-ap-alias-ext-s3alias"

    def test_unexpected_error_returns_structured_error(self):
        """予期しないエラーで構造化エラーレスポンスを返す"""
        mock_s3ap = MagicMock()
        mock_s3ap.bucket_param = "test-ap-alias-ext-s3alias"
        mock_s3ap.list_objects.side_effect = TimeoutError("Connection timed out")

        result = validate_s3ap_connectivity(mock_s3ap)
        assert result is not None
        assert result["statusCode"] == 503
        body = json.loads(result["body"])
        assert body["error_code"] == "UnexpectedError"
        assert "Connection timed out" in body["message"]

    def test_service_unavailable_error(self):
        """ServiceUnavailable エラーで構造化エラーレスポンスを返す"""
        from shared.exceptions import S3ApHelperError

        mock_s3ap = MagicMock()
        mock_s3ap.bucket_param = "test-ap-alias-ext-s3alias"
        mock_s3ap.list_objects.side_effect = S3ApHelperError("Service unavailable", error_code="ServiceUnavailable")

        result = validate_s3ap_connectivity(mock_s3ap)
        assert result is not None
        assert result["statusCode"] == 503
        body = json.loads(result["body"])
        assert body["error_code"] == "ServiceUnavailable"


# =========================================================================
# handler 統合テスト (モック)
# =========================================================================


class TestDiscoveryHandler:
    """Discovery Lambda ハンドラーの統合テスト"""

    def _make_context(self):
        """テスト用の Lambda context を生成"""
        ctx = MagicMock()
        ctx.aws_request_id = "test-request-id-12345"
        ctx.function_name = "telecom-discovery"
        return ctx

    @patch.dict(
        os.environ,
        {
            "S3_ACCESS_POINT": "test-ap-alias-ext-s3alias",
            "CDR_SUFFIX_FILTER": ".csv,.asn1,.parquet",
            "PREFIX_FILTER": "cdr/",
        },
    )
    def test_handler_success(self):
        """正常系: CDR ファイルを検出してマニフェストを返す"""
        with patch.object(_module, "S3ApHelper") as mock_s3ap_cls, patch.object(_module, "EmfMetrics") as mock_emf_cls:
            mock_s3ap = MagicMock()
            mock_s3ap_cls.return_value = mock_s3ap
            mock_s3ap.list_objects.side_effect = [
                [],  # connectivity check (max_keys=1)
                [
                    {
                        "Key": "cdr/2026/06/02/morning.csv",
                        "Size": 1048576,
                        "LastModified": "2026-06-02T00:15:00Z",
                        "ETag": '"abc"',
                    }
                ],
                [
                    {
                        "Key": "cdr/2026/06/02/data.asn1",
                        "Size": 524288,
                        "LastModified": "2026-06-02T01:00:00Z",
                        "ETag": '"def"',
                    }
                ],
                [
                    {
                        "Key": "cdr/2026/06/02/summary.parquet",
                        "Size": 2097152,
                        "LastModified": "2026-06-02T02:00:00Z",
                        "ETag": '"ghi"',
                    }
                ],
            ]

            mock_emf = MagicMock()
            mock_emf_cls.return_value = mock_emf

            result = handler({}, self._make_context())

            assert result["total_objects"] == 3
            assert result["manifest_key"].startswith("manifests/")
            assert len(result["objects"]) == 3
            assert result["suffix_patterns_used"] == [".csv", ".asn1", ".parquet"]

    @patch.dict(
        os.environ,
        {
            "S3_ACCESS_POINT": "test-ap-alias-ext-s3alias",
            "CDR_SUFFIX_FILTER": ".csv,.asn1,.parquet",
        },
    )
    def test_handler_connectivity_failure(self):
        """異常系: S3 AP 接続失敗で 503 エラーを返す"""
        from shared.exceptions import S3ApHelperError

        with patch.object(_module, "S3ApHelper") as mock_s3ap_cls:
            mock_s3ap = MagicMock()
            mock_s3ap_cls.return_value = mock_s3ap
            mock_s3ap.bucket_param = "test-ap-alias-ext-s3alias"
            mock_s3ap.list_objects.side_effect = S3ApHelperError("Access denied to S3 AP", error_code="AccessDenied")

            result = handler({}, self._make_context())

            assert result["statusCode"] == 503
            body = json.loads(result["body"])
            assert body["error"] == "S3 Access Point unreachable"

    @patch.dict(
        os.environ,
        {
            "S3_ACCESS_POINT": "test-ap-alias-ext-s3alias",
            "CDR_SUFFIX_FILTER": ".csv",
            "PREFIX_FILTER": "data/",
        },
    )
    def test_handler_deduplication(self):
        """重複キーが排除されることを確認"""
        with patch.object(_module, "S3ApHelper") as mock_s3ap_cls, patch.object(_module, "EmfMetrics") as mock_emf_cls:
            mock_s3ap = MagicMock()
            mock_s3ap_cls.return_value = mock_s3ap
            # Connectivity check succeeds, then same key returned by suffix filter
            mock_s3ap.list_objects.side_effect = [
                [],  # connectivity check
                [
                    {"Key": "data/file1.csv", "Size": 100, "LastModified": "2026-01-01T00:00:00Z", "ETag": '"aaa"'},
                    {"Key": "data/file1.csv", "Size": 100, "LastModified": "2026-01-01T00:00:00Z", "ETag": '"aaa"'},
                ],
            ]

            mock_emf = MagicMock()
            mock_emf_cls.return_value = mock_emf

            result = handler({}, self._make_context())

            assert result["total_objects"] == 1

    @patch.dict(
        os.environ,
        {
            "S3_ACCESS_POINT": "test-ap-alias-ext-s3alias",
        },
    )
    def test_handler_uses_default_suffix_when_env_not_set(self):
        """CDR_SUFFIX_FILTER 未設定時にデフォルトが使用される"""
        with patch.object(_module, "S3ApHelper") as mock_s3ap_cls, patch.object(_module, "EmfMetrics") as mock_emf_cls:
            mock_s3ap = MagicMock()
            mock_s3ap_cls.return_value = mock_s3ap
            mock_s3ap.list_objects.return_value = []

            mock_emf = MagicMock()
            mock_emf_cls.return_value = mock_emf

            result = handler({}, self._make_context())

            assert result["suffix_patterns_used"] == [".csv", ".asn1", ".parquet"]


# =========================================================================
# ハンドラーファイル構造テスト
# =========================================================================


class TestHandlerStructure:
    """ハンドラーファイルの構造テスト"""

    def test_handler_file_exists(self):
        """handler.py が存在する"""
        handler_path = os.path.join(os.path.dirname(__file__), "..", "functions", "discovery", "handler.py")
        assert os.path.exists(handler_path)

    def test_handler_has_entry_point(self):
        """handler 関数が定義されている"""
        handler_path = os.path.join(os.path.dirname(__file__), "..", "functions", "discovery", "handler.py")
        with open(handler_path) as f:
            content = f.read()
        assert "def handler(event, context):" in content

    def test_handler_uses_s3ap_helper(self):
        """S3ApHelper を使用している"""
        handler_path = os.path.join(os.path.dirname(__file__), "..", "functions", "discovery", "handler.py")
        with open(handler_path) as f:
            content = f.read()
        assert "from shared.s3ap_helper import S3ApHelper" in content

    def test_handler_uses_lambda_error_handler(self):
        """lambda_error_handler デコレータを使用している"""
        handler_path = os.path.join(os.path.dirname(__file__), "..", "functions", "discovery", "handler.py")
        with open(handler_path) as f:
            content = f.read()
        assert "@lambda_error_handler" in content

    def test_handler_has_connectivity_validation(self):
        """S3 AP 接続性バリデーション関数が定義されている"""
        handler_path = os.path.join(os.path.dirname(__file__), "..", "functions", "discovery", "handler.py")
        with open(handler_path) as f:
            content = f.read()
        assert "def validate_s3ap_connectivity(" in content

    def test_handler_has_configurable_suffix(self):
        """CDR_SUFFIX_FILTER 環境変数を使用している"""
        handler_path = os.path.join(os.path.dirname(__file__), "..", "functions", "discovery", "handler.py")
        with open(handler_path) as f:
            content = f.read()
        assert "CDR_SUFFIX_FILTER" in content

    def test_handler_default_suffix_value(self):
        """デフォルトサフィックスが .csv,.asn1,.parquet である"""
        handler_path = os.path.join(os.path.dirname(__file__), "..", "functions", "discovery", "handler.py")
        with open(handler_path) as f:
            content = f.read()
        assert ".csv,.asn1,.parquet" in content

    def test_handler_max_patterns_enforced(self):
        """最大 20 パターン制限が実装されている"""
        handler_path = os.path.join(os.path.dirname(__file__), "..", "functions", "discovery", "handler.py")
        with open(handler_path) as f:
            content = f.read()
        assert "MAX_SUFFIX_PATTERNS" in content
        assert "20" in content

    def test_handler_generates_manifest_key(self):
        """manifests/ プレフィックスのキーを生成する"""
        handler_path = os.path.join(os.path.dirname(__file__), "..", "functions", "discovery", "handler.py")
        with open(handler_path) as f:
            content = f.read()
        assert "manifests/" in content

    def test_init_files_exist(self):
        """__init__.py ファイルが存在する"""
        functions_init = os.path.join(os.path.dirname(__file__), "..", "functions", "__init__.py")
        discovery_init = os.path.join(os.path.dirname(__file__), "..", "functions", "discovery", "__init__.py")
        assert os.path.exists(functions_init)
        assert os.path.exists(discovery_init)
