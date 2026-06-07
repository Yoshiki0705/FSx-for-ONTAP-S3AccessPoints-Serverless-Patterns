"""UC19 Discovery Lambda — Unit Tests

クリエイティブアセット検出ロジックのテスト:
- メディアフォーマット判定 (JPEG, PNG, TIFF, MP4, MOV, PSD)
- ファイルサイズ上限 (5 GB) フィルタリング
- S3 AP 接続性バリデーション
- Manifest 生成
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
_spec = importlib.util.spec_from_file_location("adtech_discovery_handler", _handler_path)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

is_supported_media = _module.is_supported_media
is_within_size_limit = _module.is_within_size_limit
validate_s3ap_connectivity = _module.validate_s3ap_connectivity
handler = _module.handler
SUPPORTED_MEDIA_EXTENSIONS = _module.SUPPORTED_MEDIA_EXTENSIONS
MAX_FILE_SIZE_BYTES = _module.MAX_FILE_SIZE_BYTES


# ============================================================
# is_supported_media() テスト
# ============================================================


class TestIsSupportedMedia:
    """メディアフォーマット判定のテスト"""

    @pytest.mark.parametrize(
        "key",
        [
            "creatives/banner.jpg",
            "ads/campaign/hero.jpeg",
            "assets/logo.png",
            "print/cover.tiff",
            "print/layout.tif",
            "video/spot_30s.mp4",
            "video/master.mov",
            "design/template.psd",
        ],
    )
    def test_supported_formats_accepted(self, key: str):
        """対応フォーマットのファイルは True を返す"""
        assert is_supported_media(key) is True

    @pytest.mark.parametrize(
        "key",
        [
            "creatives/BANNER.JPG",
            "ads/HERO.JPEG",
            "assets/LOGO.PNG",
            "print/COVER.TIFF",
            "video/SPOT.MP4",
            "video/MASTER.MOV",
            "design/TEMPLATE.PSD",
        ],
    )
    def test_case_insensitive(self, key: str):
        """拡張子は大文字小文字を区別しない"""
        assert is_supported_media(key) is True

    @pytest.mark.parametrize(
        "key",
        [
            "docs/report.pdf",
            "data/metrics.csv",
            "scripts/deploy.sh",
            "config/settings.json",
            "readme.md",
            "archive/backup.zip",
            "video/subtitle.srt",
            "audio/track.wav",
        ],
    )
    def test_unsupported_formats_rejected(self, key: str):
        """非対応フォーマットのファイルは False を返す"""
        assert is_supported_media(key) is False

    def test_empty_key(self):
        """空文字列は False を返す"""
        assert is_supported_media("") is False

    def test_no_extension(self):
        """拡張子なしのファイルは False を返す"""
        assert is_supported_media("creatives/noext") is False

    def test_dot_only(self):
        """ドットのみのファイルは False を返す"""
        assert is_supported_media(".") is False

    def test_hidden_file_with_extension(self):
        """隠しファイルでも拡張子が対応していれば True"""
        assert is_supported_media(".hidden.jpg") is True

    def test_multiple_dots(self):
        """複数ドットの場合、最後の拡張子で判定"""
        assert is_supported_media("archive/v2.backup.png") is True
        assert is_supported_media("archive/v2.backup.txt") is False


# ============================================================
# is_within_size_limit() テスト
# ============================================================


class TestIsWithinSizeLimit:
    """ファイルサイズ上限フィルタのテスト"""

    def test_zero_size(self):
        """0 バイトは許可"""
        assert is_within_size_limit(0) is True

    def test_normal_size(self):
        """通常サイズ (1 MB) は許可"""
        assert is_within_size_limit(1_048_576) is True

    def test_exactly_5gb(self):
        """ちょうど 5 GB (5,368,709,120 bytes) は許可"""
        assert is_within_size_limit(5_368_709_120) is True

    def test_over_5gb(self):
        """5 GB + 1 byte は除外"""
        assert is_within_size_limit(5_368_709_121) is False

    def test_large_file(self):
        """10 GB は除外"""
        assert is_within_size_limit(10_737_418_240) is False

    def test_negative_size(self):
        """負の値は除外"""
        assert is_within_size_limit(-1) is False


# ============================================================
# validate_s3ap_connectivity() テスト
# ============================================================


class TestValidateS3apConnectivity:
    """S3 AP 接続性バリデーションのテスト"""

    def test_connectivity_success(self):
        """接続成功時は None を返す"""
        mock_s3ap = MagicMock()
        mock_s3ap.list_objects.return_value = []

        result = validate_s3ap_connectivity(mock_s3ap)
        assert result is None
        mock_s3ap.list_objects.assert_called_once_with(prefix="", suffix="", max_keys=1)

    def test_connectivity_s3ap_error(self):
        """S3ApHelperError 発生時は 503 レスポンスを返す"""
        from shared.exceptions import S3ApHelperError

        mock_s3ap = MagicMock()
        mock_s3ap.list_objects.side_effect = S3ApHelperError("Access denied", error_code="AccessDenied")
        mock_s3ap.bucket_param = "test-ap-alias"

        result = validate_s3ap_connectivity(mock_s3ap)
        assert result is not None
        assert result["statusCode"] == 503
        body = json.loads(result["body"])
        assert body["error_type"] == "ConnectivityError"
        assert body["error_code"] == "AccessDenied"
        assert body["access_point"] == "test-ap-alias"

    def test_connectivity_unexpected_error(self):
        """予期しない例外発生時は 503 レスポンスを返す"""
        mock_s3ap = MagicMock()
        mock_s3ap.list_objects.side_effect = RuntimeError("Network timeout")
        mock_s3ap.bucket_param = "test-ap-alias"

        result = validate_s3ap_connectivity(mock_s3ap)
        assert result is not None
        assert result["statusCode"] == 503
        body = json.loads(result["body"])
        assert body["error_code"] == "UnexpectedError"


# ============================================================
# handler() 統合テスト
# ============================================================


class TestHandler:
    """Discovery Lambda ハンドラーの統合テスト"""

    def _make_context(self):
        ctx = MagicMock()
        ctx.aws_request_id = "test-request-id-12345"
        ctx.function_name = "adtech-creative-discovery"
        return ctx

    @patch.dict(
        os.environ,
        {
            "S3_ACCESS_POINT": "test-ap-alias",
            "CREATIVE_PREFIX_FILTER": "creatives/",
        },
    )
    def test_handler_filters_media_formats(self):
        """対応メディアフォーマットのみ Manifest に含まれる"""
        with patch.object(_module, "S3ApHelper") as mock_s3ap_class:
            mock_instance = MagicMock()
            mock_s3ap_class.return_value = mock_instance

            # connectivity check returns empty, then full list
            mock_instance.list_objects.side_effect = [
                [],  # connectivity check
                [
                    {
                        "Key": "creatives/banner.jpg",
                        "Size": 1_000_000,
                        "LastModified": "2026-06-01T00:00:00Z",
                        "ETag": '"abc"',
                    },
                    {
                        "Key": "creatives/logo.png",
                        "Size": 500_000,
                        "LastModified": "2026-06-01T00:00:00Z",
                        "ETag": '"def"',
                    },
                    {
                        "Key": "creatives/readme.txt",
                        "Size": 1_000,
                        "LastModified": "2026-06-01T00:00:00Z",
                        "ETag": '"ghi"',
                    },
                    {
                        "Key": "creatives/video.mp4",
                        "Size": 50_000_000,
                        "LastModified": "2026-06-01T00:00:00Z",
                        "ETag": '"jkl"',
                    },
                    {
                        "Key": "creatives/data.csv",
                        "Size": 2_000,
                        "LastModified": "2026-06-01T00:00:00Z",
                        "ETag": '"mno"',
                    },
                ],
            ]
            mock_instance.bucket_param = "test-ap-alias"

            result = handler({}, self._make_context())

            assert result["total_objects"] == 3  # jpg, png, mp4
            assert result["excluded_unsupported_count"] == 2  # txt, csv
            assert result["excluded_oversize_count"] == 0
            assert len(result["objects"]) == 3

    @patch.dict(
        os.environ,
        {
            "S3_ACCESS_POINT": "test-ap-alias",
            "CREATIVE_PREFIX_FILTER": "",
        },
    )
    def test_handler_excludes_oversize_files(self):
        """5 GB 超のファイルは除外される"""
        with patch.object(_module, "S3ApHelper") as mock_s3ap_class:
            mock_instance = MagicMock()
            mock_s3ap_class.return_value = mock_instance

            mock_instance.list_objects.side_effect = [
                [],  # connectivity check
                [
                    {
                        "Key": "creatives/small.jpg",
                        "Size": 1_000_000,
                        "LastModified": "2026-06-01T00:00:00Z",
                        "ETag": '"a"',
                    },
                    {
                        "Key": "creatives/huge.tiff",
                        "Size": 6_000_000_000,
                        "LastModified": "2026-06-01T00:00:00Z",
                        "ETag": '"b"',
                    },
                    {
                        "Key": "creatives/medium.psd",
                        "Size": 4_000_000_000,
                        "LastModified": "2026-06-01T00:00:00Z",
                        "ETag": '"c"',
                    },
                ],
            ]
            mock_instance.bucket_param = "test-ap-alias"

            result = handler({}, self._make_context())

            assert result["total_objects"] == 2  # small.jpg + medium.psd
            assert result["excluded_oversize_count"] == 1  # huge.tiff
            assert result["excluded_unsupported_count"] == 0

    @patch.dict(
        os.environ,
        {
            "S3_ACCESS_POINT": "test-ap-alias",
        },
    )
    def test_handler_connectivity_failure(self):
        """S3 AP 接続失敗時は 503 エラーを返す"""
        from shared.exceptions import S3ApHelperError

        with patch.object(_module, "S3ApHelper") as mock_s3ap_class:
            mock_instance = MagicMock()
            mock_s3ap_class.return_value = mock_instance
            mock_instance.list_objects.side_effect = S3ApHelperError("Access denied", error_code="AccessDenied")
            mock_instance.bucket_param = "test-ap-alias"

            result = handler({}, self._make_context())

            assert result["statusCode"] == 503
            body = json.loads(result["body"])
            assert body["error_type"] == "ConnectivityError"

    @patch.dict(
        os.environ,
        {
            "S3_ACCESS_POINT": "test-ap-alias",
            "CREATIVE_PREFIX_FILTER": "assets/campaigns/",
        },
    )
    def test_handler_uses_prefix_filter(self):
        """CREATIVE_PREFIX_FILTER 環境変数が正しく使用される"""
        with patch.object(_module, "S3ApHelper") as mock_s3ap_class:
            mock_instance = MagicMock()
            mock_s3ap_class.return_value = mock_instance
            mock_instance.list_objects.side_effect = [
                [],  # connectivity check
                [],  # main listing
            ]
            mock_instance.bucket_param = "test-ap-alias"

            handler({}, self._make_context())

            # 2回目の list_objects 呼び出し (1回目は接続バリデーション)
            calls = mock_instance.list_objects.call_args_list
            # 最初のコール: connectivity check (prefix="", suffix="", max_keys=1)
            assert calls[0].kwargs == {"prefix": "", "suffix": "", "max_keys": 1}
            # 2回目のコール: 本体リスト (prefix="assets/campaigns/", suffix="")
            assert calls[1].kwargs == {"prefix": "assets/campaigns/", "suffix": ""}

    @patch.dict(
        os.environ,
        {
            "S3_ACCESS_POINT": "test-ap-alias",
        },
    )
    def test_handler_empty_prefix_default(self):
        """CREATIVE_PREFIX_FILTER 未設定時は空文字列がデフォルト"""
        with patch.object(_module, "S3ApHelper") as mock_s3ap_class:
            mock_instance = MagicMock()
            mock_s3ap_class.return_value = mock_instance
            mock_instance.list_objects.side_effect = [
                [],  # connectivity check
                [],  # main listing
            ]
            mock_instance.bucket_param = "test-ap-alias"

            handler({}, self._make_context())

            calls = mock_instance.list_objects.call_args_list
            # 2回目のコール: 空プレフィックス
            assert calls[1].kwargs["prefix"] == ""

    @patch.dict(
        os.environ,
        {
            "S3_ACCESS_POINT": "test-ap-alias",
            "CREATIVE_PREFIX_FILTER": "creatives/",
        },
    )
    def test_handler_writes_manifest(self):
        """Manifest JSON が S3 AP に書き出される"""
        with patch.object(_module, "S3ApHelper") as mock_s3ap_class:
            mock_instance = MagicMock()
            mock_s3ap_class.return_value = mock_instance
            mock_instance.list_objects.side_effect = [
                [],  # connectivity check
                [{"Key": "creatives/img.png", "Size": 100, "LastModified": "2026-06-01T00:00:00Z", "ETag": '"x"'}],
            ]
            mock_instance.bucket_param = "test-ap-alias"

            handler({}, self._make_context())

            # put_object が呼ばれたことを確認
            mock_instance.put_object.assert_called_once()
            call_kwargs = mock_instance.put_object.call_args.kwargs
            assert call_kwargs["content_type"] == "application/json"
            assert "manifest" in call_kwargs["key"]

            # Manifest の内容を検証
            manifest = json.loads(call_kwargs["body"])
            assert manifest["use_case"] == "adtech-creative-management"
            assert manifest["total_objects"] == 1
            assert manifest["max_file_size_bytes"] == MAX_FILE_SIZE_BYTES
            assert ".jpg" in manifest["supported_formats"]
