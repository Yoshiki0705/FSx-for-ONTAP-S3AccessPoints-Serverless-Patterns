"""Unit Tests for UC8: SEG-Y メタデータ抽出 Lambda

SEG-Y ヘッダーパース、テキストヘッダーデコード、調査名抽出、
ハンドラの正常系・異常系をテストする。

Requirements: 13.1, 13.2
"""

from __future__ import annotations

import os
import struct
import sys
from unittest.mock import MagicMock, patch

import pytest

# shared モジュールと UC8 関数のパスを追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from functions.seismic_metadata.handler import (
    _decode_textual_header,
    _extract_coordinate_system,
    _extract_survey_name,
    _parse_binary_header,
)


# ---------------------------------------------------------------------------
# _decode_textual_header tests
# ---------------------------------------------------------------------------


class TestDecodeTextualHeader:
    """テキストヘッダーデコードのテスト"""

    def test_ascii_header(self):
        """ASCII テキストヘッダーを正しくデコードする"""
        text = "C 1 CLIENT: North Sea Survey 2026" + " " * (3200 - 34)
        raw = text.encode("ascii")
        result = _decode_textual_header(raw)
        assert "CLIENT" in result
        assert "North Sea Survey 2026" in result

    def test_ebcdic_header(self):
        """EBCDIC テキストヘッダーを正しくデコードする"""
        text = "C 1 CLIENT: Test Survey"
        # EBCDIC エンコード (cp500)
        raw = text.encode("cp500")
        # パディング
        raw = raw + b"\x40" * (3200 - len(raw))  # 0x40 = EBCDIC space
        result = _decode_textual_header(raw)
        assert "CLIENT" in result
        assert "Test Survey" in result

    def test_empty_header(self):
        """空のヘッダーでもエラーにならない"""
        raw = b"\x00" * 3200
        result = _decode_textual_header(raw)
        assert isinstance(result, str)

    def test_short_header(self):
        """短いヘッダーでもエラーにならない"""
        raw = b"SHORT"
        result = _decode_textual_header(raw)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# _extract_survey_name tests
# ---------------------------------------------------------------------------


class TestExtractSurveyName:
    """調査名抽出のテスト"""

    def test_client_keyword(self):
        """CLIENT キーワードから調査名を抽出する"""
        header = "C 1 CLIENT: North Sea 2026\nC 2 AREA: Block 15"
        result = _extract_survey_name(header)
        assert result == "North Sea 2026"

    def test_survey_keyword(self):
        """SURVEY キーワードから調査名を抽出する"""
        header = "C 1 SURVEY: Gulf of Mexico 2025\nC 2 LINE: 001"
        result = _extract_survey_name(header)
        assert result == "Gulf of Mexico 2025"

    def test_project_keyword(self):
        """PROJECT キーワードから調査名を抽出する"""
        header = "C 1 PROJECT = Deep Water Exploration\nC 2 DATE: 2026"
        result = _extract_survey_name(header)
        assert result == "Deep Water Exploration"

    def test_no_keyword_found(self):
        """キーワードが見つからない場合は空文字列を返す"""
        header = "C 1 SOME RANDOM TEXT\nC 2 MORE TEXT"
        result = _extract_survey_name(header)
        assert result == ""

    def test_80_char_lines(self):
        """80 文字ごとに分割されたヘッダーを処理する"""
        # 改行なしの 80 文字行
        line1 = "C 1 CLIENT: Test Survey Name" + " " * 52
        line2 = "C 2 AREA: Block A" + " " * 62
        header = line1 + line2
        result = _extract_survey_name(header)
        assert result == "Test Survey Name"


# ---------------------------------------------------------------------------
# _extract_coordinate_system tests
# ---------------------------------------------------------------------------


class TestExtractCoordinateSystem:
    """座標系抽出のテスト"""

    def test_coordinate_keyword(self):
        """COORDINATE キーワードから座標系を抽出する"""
        header = "C 1 COORDINATE SYSTEM: WGS84\nC 2 OTHER"
        result = _extract_coordinate_system(header)
        assert result == "WGS84"

    def test_datum_keyword(self):
        """DATUM キーワードから座標系を抽出する"""
        header = "C 1 DATUM: NAD27\nC 2 OTHER"
        result = _extract_coordinate_system(header)
        assert result == "NAD27"

    def test_no_keyword_found(self):
        """キーワードが見つからない場合は 'unknown' を返す"""
        header = "C 1 SOME TEXT\nC 2 MORE TEXT"
        result = _extract_coordinate_system(header)
        assert result == "unknown"


# ---------------------------------------------------------------------------
# _parse_binary_header tests
# ---------------------------------------------------------------------------


class TestParseBinaryHeader:
    """バイナリヘッダーパースのテスト"""

    def test_valid_header(self):
        """有効なバイナリヘッダーを正しくパースする"""
        header = bytearray(400)
        # trace_count at offset 12-13
        struct.pack_into(">h", header, 12, 500)
        # sample_interval at offset 16-17
        struct.pack_into(">h", header, 16, 4000)
        # samples_per_trace at offset 20-21
        struct.pack_into(">h", header, 20, 1500)
        # data_format_code at offset 24-25
        struct.pack_into(">h", header, 24, 1)
        # measurement_system at offset 54-55
        struct.pack_into(">h", header, 54, 1)

        result = _parse_binary_header(bytes(header))

        assert result["trace_count"] == 500
        assert result["sample_interval"] == 4000
        assert result["samples_per_trace"] == 1500
        assert result["data_format_code"] == 1
        assert result["measurement_system"] == "meters"

    def test_feet_measurement_system(self):
        """測定系 feet を正しく識別する"""
        header = bytearray(400)
        struct.pack_into(">h", header, 12, 100)
        struct.pack_into(">h", header, 16, 2000)
        struct.pack_into(">h", header, 20, 500)
        struct.pack_into(">h", header, 24, 5)
        struct.pack_into(">h", header, 54, 2)

        result = _parse_binary_header(bytes(header))

        assert result["measurement_system"] == "feet"

    def test_unknown_measurement_system(self):
        """不明な測定系コードは 'unknown' を返す"""
        header = bytearray(400)
        struct.pack_into(">h", header, 12, 100)
        struct.pack_into(">h", header, 16, 2000)
        struct.pack_into(">h", header, 20, 500)
        struct.pack_into(">h", header, 24, 1)
        struct.pack_into(">h", header, 54, 99)

        result = _parse_binary_header(bytes(header))

        assert result["measurement_system"] == "unknown"

    def test_zero_trace_count(self):
        """トレース数が 0 の場合も正しく処理する"""
        header = bytearray(400)
        struct.pack_into(">h", header, 12, 0)
        struct.pack_into(">h", header, 16, 4000)
        struct.pack_into(">h", header, 20, 1000)
        struct.pack_into(">h", header, 24, 1)
        struct.pack_into(">h", header, 54, 1)

        result = _parse_binary_header(bytes(header))

        assert result["trace_count"] == 0

    def test_header_too_short(self):
        """ヘッダーが短すぎる場合は ValueError を raise する"""
        header = b"\x00" * 100  # 400 バイト未満

        with pytest.raises(ValueError, match="Binary header too short"):
            _parse_binary_header(header)

    def test_all_data_format_codes(self):
        """全データフォーマットコード (1-5) を正しく抽出する"""
        for code in range(1, 6):
            header = bytearray(400)
            struct.pack_into(">h", header, 12, 100)
            struct.pack_into(">h", header, 16, 2000)
            struct.pack_into(">h", header, 20, 500)
            struct.pack_into(">h", header, 24, code)
            struct.pack_into(">h", header, 54, 1)

            result = _parse_binary_header(bytes(header))
            assert result["data_format_code"] == code


# ---------------------------------------------------------------------------
# handler tests (mocked AWS calls)
# ---------------------------------------------------------------------------


class TestHandler:
    """ハンドラの正常系・異常系テスト"""

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT": "test-ap-ext-s3alias",
        "OUTPUT_BUCKET": "test-output-bucket",
    })
    @patch("functions.seismic_metadata.handler.boto3")
    @patch("functions.seismic_metadata.handler.S3ApHelper")
    def test_handler_success(self, mock_s3ap_class, mock_boto3):
        """正常系: SEG-Y ヘッダーを正しくパースしてメタデータを返す"""
        from functions.seismic_metadata.handler import handler

        # テキストヘッダー (3200 bytes) + バイナリヘッダー (400 bytes)
        textual = ("C 1 CLIENT: Test Survey" + " " * 57).encode("ascii")
        textual = textual + b" " * (3200 - len(textual))

        binary = bytearray(400)
        struct.pack_into(">h", binary, 12, 1000)
        struct.pack_into(">h", binary, 16, 4000)
        struct.pack_into(">h", binary, 20, 1500)
        struct.pack_into(">h", binary, 24, 1)
        struct.pack_into(">h", binary, 54, 1)

        header_data = textual + bytes(binary)

        mock_s3ap = MagicMock()
        mock_s3ap.streaming_download_range.return_value = header_data
        mock_s3ap_class.return_value = mock_s3ap

        mock_s3_client = MagicMock()
        mock_boto3.client.return_value = mock_s3_client

        event = {"Key": "surveys/test_survey.segy", "Size": 1073741824}
        context = MagicMock()
        context.aws_request_id = "test-request-id"

        result = handler(event, context)

        assert result["status"] == "SUCCESS"
        assert result["file_key"] == "surveys/test_survey.segy"
        assert result["metadata"]["sample_interval"] == 4000
        assert result["metadata"]["trace_count"] == 1000
        assert result["metadata"]["data_format_code"] == 1
        assert "output_key" in result

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT": "test-ap-ext-s3alias",
        "OUTPUT_BUCKET": "test-output-bucket",
    })
    def test_handler_file_too_small(self):
        """異常系: ファイルサイズがヘッダーサイズ未満の場合は INVALID を返す"""
        from functions.seismic_metadata.handler import handler

        event = {"Key": "surveys/tiny.segy", "Size": 100}
        context = MagicMock()
        context.aws_request_id = "test-request-id"

        result = handler(event, context)

        assert result["status"] == "INVALID"
        assert result["file_key"] == "surveys/tiny.segy"
        assert "error_type" in result
        assert result["error_type"] == "FileTooSmall"

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT": "test-ap-ext-s3alias",
        "OUTPUT_BUCKET": "test-output-bucket",
    })
    @patch("functions.seismic_metadata.handler.S3ApHelper")
    def test_handler_download_error(self, mock_s3ap_class):
        """異常系: ダウンロードエラー時は INVALID を返す"""
        from functions.seismic_metadata.handler import handler

        mock_s3ap = MagicMock()
        mock_s3ap.streaming_download_range.side_effect = Exception("Network error")
        mock_s3ap_class.return_value = mock_s3ap

        event = {"Key": "surveys/error.segy", "Size": 10000}
        context = MagicMock()
        context.aws_request_id = "test-request-id"

        result = handler(event, context)

        assert result["status"] == "INVALID"
        assert result["error_type"] == "DownloadError"
