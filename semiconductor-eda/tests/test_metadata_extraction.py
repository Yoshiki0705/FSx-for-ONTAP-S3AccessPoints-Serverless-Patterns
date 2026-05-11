"""UC6 半導体 / EDA メタデータ抽出 ユニットテスト

moto を使用した AWS API モック、正常系・異常系のメタデータ抽出をテストする。
Lambda ハンドラーの入出力形式、エラーハンドリング、
ヘルパー関数のロジックを検証する。

Requirements: 13.1, 13.2
"""

from __future__ import annotations

import json
import os
import struct
import sys
from unittest.mock import MagicMock, patch

import pytest

# shared モジュールと UC6 関数のパスを追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from functions.metadata_extraction.handler import (
    GdsiiParseError,
    OasisParseError,
    _detect_file_format,
    _extract_metadata,
    _gdsii_real8_to_float,
    _parse_gdsii_header,
    _parse_oasis_header,
    _read_gdsii_record,
)

# テスト用ヘルパーを property テストから再利用
from tests.test_properties import build_gds_header, _make_gdsii_record


# =========================================================================
# _read_gdsii_record テスト
# =========================================================================


class TestReadGdsiiRecord:
    """GDSII レコード読み取りのテスト"""

    def test_valid_record(self):
        """有効なレコードを正しく読み取れること"""
        # HEADER record: length=6, type=0x0002, data=0x0258 (version 600)
        data = struct.pack(">HH", 6, 0x0002) + struct.pack(">H", 600)
        record_type, next_offset, record_data = _read_gdsii_record(data, 0)
        assert record_type == 0x0002
        assert next_offset == 6
        assert len(record_data) == 2
        assert struct.unpack(">H", record_data)[0] == 600

    def test_insufficient_data_for_header(self):
        """データが不足している場合に GdsiiParseError が発生すること"""
        data = b"\x00\x06"  # Only 2 bytes, need 4
        with pytest.raises(GdsiiParseError, match="Insufficient data"):
            _read_gdsii_record(data, 0)

    def test_invalid_record_length(self):
        """レコード長が 4 未満の場合に GdsiiParseError が発生すること"""
        data = struct.pack(">HH", 2, 0x0002)  # length=2, too short
        with pytest.raises(GdsiiParseError, match="Invalid record length"):
            _read_gdsii_record(data, 0)

    def test_record_extends_beyond_buffer(self):
        """レコードデータがバッファを超える場合に GdsiiParseError が発生すること"""
        # Record says length=100 but we only have 6 bytes
        data = struct.pack(">HH", 100, 0x0002) + struct.pack(">H", 600)
        with pytest.raises(GdsiiParseError, match="Record data extends beyond"):
            _read_gdsii_record(data, 0)

    def test_empty_record_data(self):
        """データなしレコード (length=4) を正しく読み取れること"""
        data = struct.pack(">HH", 4, 0x0400)  # ENDLIB, no data
        record_type, next_offset, record_data = _read_gdsii_record(data, 0)
        assert record_type == 0x0400
        assert next_offset == 4
        assert record_data == b""


# =========================================================================
# _gdsii_real8_to_float テスト
# =========================================================================


class TestGdsiiReal8ToFloat:
    """GDSII 8 バイト実数変換のテスト"""

    def test_zero_value(self):
        """ゼロ値が正しく変換されること"""
        assert _gdsii_real8_to_float(b"\x00" * 8) == 0.0

    def test_wrong_length(self):
        """8 バイト以外のデータで 0.0 が返ること"""
        assert _gdsii_real8_to_float(b"\x00" * 4) == 0.0
        assert _gdsii_real8_to_float(b"") == 0.0

    def test_positive_value(self):
        """正の値が正しく変換されること"""
        # Construct a known GDSII real8 for 0.001
        # exponent = 64 - 2 = 62 (since 0.001 = 0.001 * 16^0, need normalization)
        # This is a round-trip test using the helper
        from tests.test_properties import _float_to_gdsii_real8

        encoded = _float_to_gdsii_real8(0.001)
        decoded = _gdsii_real8_to_float(encoded)
        assert abs(decoded - 0.001) < 1e-10

    def test_small_value(self):
        """非常に小さい値 (1e-9) が正しく変換されること"""
        from tests.test_properties import _float_to_gdsii_real8

        encoded = _float_to_gdsii_real8(1e-9)
        decoded = _gdsii_real8_to_float(encoded)
        assert abs(decoded - 1e-9) < 1e-15


# =========================================================================
# _parse_gdsii_header テスト
# =========================================================================


class TestParseGdsiiHeader:
    """GDSII ヘッダーパースのテスト"""

    def test_valid_header_basic(self):
        """基本的な有効ヘッダーが正しくパースされること"""
        header = build_gds_header(
            library_name="TEST_LIB",
            cell_count=5,
        )
        result = _parse_gdsii_header(header)

        assert result["file_format"] == "GDSII"
        assert result["library_name"] == "TEST_LIB"
        assert result["cell_count"] == 5
        assert result["file_version"] == "6.0"
        assert result["creation_date"] is not None

    def test_valid_header_zero_cells(self):
        """セル数 0 のヘッダーが正しくパースされること"""
        header = build_gds_header(library_name="EMPTY_LIB", cell_count=0)
        result = _parse_gdsii_header(header)

        assert result["library_name"] == "EMPTY_LIB"
        assert result["cell_count"] == 0

    def test_valid_header_many_cells(self):
        """多数のセルを持つヘッダーが正しくパースされること"""
        header = build_gds_header(library_name="BIG_LIB", cell_count=50)
        result = _parse_gdsii_header(header)

        assert result["library_name"] == "BIG_LIB"
        assert result["cell_count"] == 50

    def test_creation_date_parsed(self):
        """作成日時が正しくパースされること"""
        header = build_gds_header(
            library_name="DATE_TEST",
            cell_count=1,
            creation_year=2026,
            creation_month=3,
            creation_day=20,
            creation_hour=14,
            creation_minute=30,
            creation_second=45,
        )
        result = _parse_gdsii_header(header)

        assert result["creation_date"] is not None
        assert "2026-03-20" in result["creation_date"]
        assert "14:30:45" in result["creation_date"]

    def test_units_extracted(self):
        """ユニット情報が抽出されること"""
        header = build_gds_header(library_name="UNITS_TEST", cell_count=1)
        result = _parse_gdsii_header(header)

        assert "user_unit" in result["units"]
        assert "db_unit" in result["units"]
        assert result["units"]["user_unit"] != 0.0
        assert result["units"]["db_unit"] != 0.0

    def test_invalid_first_record_not_header(self):
        """最初のレコードが HEADER でない場合に GdsiiParseError が発生すること"""
        # Create a record with BGNLIB type instead of HEADER
        data = _make_gdsii_record(0x0102, struct.pack(">H", 600))
        with pytest.raises(GdsiiParseError, match="Expected HEADER"):
            _parse_gdsii_header(data)

    def test_unsupported_version(self):
        """サポート外バージョンで GdsiiParseError が発生すること"""
        # Version 800 is unsupported (max is 700)
        data = _make_gdsii_record(0x0002, struct.pack(">H", 800))
        with pytest.raises(GdsiiParseError, match="Unsupported GDS version"):
            _parse_gdsii_header(data)

    def test_empty_data(self):
        """空データで GdsiiParseError が発生すること"""
        with pytest.raises(GdsiiParseError):
            _parse_gdsii_header(b"")

    def test_truncated_header(self):
        """切り詰められたデータで GdsiiParseError が発生すること"""
        with pytest.raises(GdsiiParseError):
            _parse_gdsii_header(b"\x00\x06")


# =========================================================================
# _parse_oasis_header テスト
# =========================================================================


class TestParseOasisHeader:
    """OASIS ヘッダーパースのテスト"""

    def test_valid_oasis_header(self):
        """有効な OASIS ヘッダーが正しくパースされること"""
        # Magic + START record (id=1) + version string "1.0"
        version_str = b"1.0"
        data = b"%SEMI-OASIS\r\n" + bytes([1, len(version_str)]) + version_str
        result = _parse_oasis_header(data)

        assert result["file_format"] == "OASIS"
        assert result["file_version"] == "1.0"

    def test_invalid_magic_bytes(self):
        """不正なマジックバイトで OasisParseError が発生すること"""
        with pytest.raises(OasisParseError, match="Invalid OASIS magic"):
            _parse_oasis_header(b"INVALID_MAGIC")

    def test_oasis_header_minimal(self):
        """マジックバイトのみの最小ヘッダーがパースされること"""
        data = b"%SEMI-OASIS\r\n"
        result = _parse_oasis_header(data)
        assert result["file_format"] == "OASIS"

    def test_oasis_default_units(self):
        """OASIS のデフォルトユニットが設定されること"""
        data = b"%SEMI-OASIS\r\n"
        result = _parse_oasis_header(data)
        assert result["units"]["user_unit"] == 0.001
        assert result["units"]["db_unit"] == 1e-09


# =========================================================================
# _detect_file_format テスト
# =========================================================================


class TestDetectFileFormat:
    """ファイルフォーマット検出のテスト"""

    def test_gds_extension(self):
        assert _detect_file_format("designs/chip.gds") == "GDSII"

    def test_gds2_extension(self):
        assert _detect_file_format("designs/chip.gds2") == "GDSII"

    def test_oas_extension(self):
        assert _detect_file_format("designs/chip.oas") == "OASIS"

    def test_oasis_extension(self):
        assert _detect_file_format("designs/chip.oasis") == "OASIS"

    def test_unknown_extension(self):
        assert _detect_file_format("designs/chip.txt") == "UNKNOWN"

    def test_case_insensitive(self):
        assert _detect_file_format("designs/CHIP.GDS") == "GDSII"
        assert _detect_file_format("designs/CHIP.OAS") == "OASIS"


# =========================================================================
# _extract_metadata テスト
# =========================================================================


class TestExtractMetadata:
    """メタデータ抽出の統合テスト"""

    def test_gdsii_extraction(self):
        """GDSII ファイルのメタデータ抽出が正しく動作すること"""
        header = build_gds_header(library_name="EXTRACT_TEST", cell_count=3)
        result = _extract_metadata(header, "test/chip.gds")

        assert result["file_format"] == "GDSII"
        assert result["library_name"] == "EXTRACT_TEST"
        assert result["cell_count"] == 3

    def test_oasis_extraction(self):
        """OASIS ファイルのメタデータ抽出が正しく動作すること"""
        version_str = b"1.0"
        data = b"%SEMI-OASIS\r\n" + bytes([1, len(version_str)]) + version_str
        result = _extract_metadata(data, "test/chip.oas")

        assert result["file_format"] == "OASIS"
        assert result["file_version"] == "1.0"

    def test_unknown_format_raises_error(self):
        """不明なフォーマットで ValueError が発生すること"""
        with pytest.raises(ValueError, match="Unknown file format"):
            _extract_metadata(b"some data", "test/chip.txt")

    def test_corrupted_gds_raises_parse_error(self):
        """破損した GDS データで GdsiiParseError が発生すること"""
        with pytest.raises(GdsiiParseError):
            _extract_metadata(b"\xff\xff\xff\xff", "test/chip.gds")

    def test_corrupted_oasis_raises_parse_error(self):
        """破損した OASIS データで OasisParseError が発生すること"""
        with pytest.raises(OasisParseError):
            _extract_metadata(b"NOT_OASIS_DATA", "test/chip.oas")


# =========================================================================
# Lambda ハンドラーテスト (moto / mock)
# =========================================================================


class TestMetadataExtractionHandler:
    """メタデータ抽出 Lambda ハンドラーのテスト"""

    def _make_handler_env(self):
        """テスト用環境変数を設定"""
        return {
            "S3_ACCESS_POINT": "test-ap-ext-s3alias",
            "OUTPUT_BUCKET": "test-output-bucket",
        }

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT": "test-ap-ext-s3alias",
        "OUTPUT_BUCKET": "test-output-bucket",
    })
    @patch("functions.metadata_extraction.handler.boto3")
    @patch("functions.metadata_extraction.handler.S3ApHelper")
    def test_handler_success_gdsii(self, mock_s3ap_cls, mock_boto3):
        """正常系: GDSII ファイルのメタデータ抽出が成功すること"""
        from functions.metadata_extraction.handler import handler

        # Setup mocks
        mock_s3ap = MagicMock()
        mock_s3ap_cls.return_value = mock_s3ap

        header = build_gds_header(library_name="HANDLER_TEST", cell_count=10)
        mock_s3ap.streaming_download_range.return_value = header

        mock_s3_client = MagicMock()
        mock_boto3.client.return_value = mock_s3_client

        event = {"Key": "designs/chip_v2.gds", "Size": 1073741824}
        context = MagicMock()

        result = handler(event, context)

        assert result["status"] == "SUCCESS"
        assert result["file_key"] == "designs/chip_v2.gds"
        assert result["metadata"]["library_name"] == "HANDLER_TEST"
        assert result["metadata"]["cell_count"] == 10
        assert result["metadata"]["file_format"] == "GDSII"
        assert "output_key" in result
        assert "metadata/" in result["output_key"]
        assert result["output_key"].endswith(".json")

        # Verify S3 put_object was called
        mock_s3_client.put_object.assert_called_once()

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT": "test-ap-ext-s3alias",
        "OUTPUT_BUCKET": "test-output-bucket",
    })
    @patch("functions.metadata_extraction.handler.boto3")
    @patch("functions.metadata_extraction.handler.S3ApHelper")
    def test_handler_invalid_gdsii(self, mock_s3ap_cls, mock_boto3):
        """異常系: 破損 GDSII ファイルで INVALID ステータスが返ること"""
        from functions.metadata_extraction.handler import handler

        mock_s3ap = MagicMock()
        mock_s3ap_cls.return_value = mock_s3ap
        mock_s3ap.streaming_download_range.return_value = b"\xff\xff\xff\xff"

        event = {"Key": "designs/corrupted.gds", "Size": 100}
        context = MagicMock()

        result = handler(event, context)

        assert result["status"] == "INVALID"
        assert result["file_key"] == "designs/corrupted.gds"
        assert "error" in result
        assert "error_type" in result

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT": "test-ap-ext-s3alias",
        "OUTPUT_BUCKET": "test-output-bucket",
    })
    @patch("functions.metadata_extraction.handler.boto3")
    @patch("functions.metadata_extraction.handler.S3ApHelper")
    def test_handler_oasis_success(self, mock_s3ap_cls, mock_boto3):
        """正常系: OASIS ファイルのメタデータ抽出が成功すること"""
        from functions.metadata_extraction.handler import handler

        mock_s3ap = MagicMock()
        mock_s3ap_cls.return_value = mock_s3ap

        version_str = b"1.0"
        oasis_data = b"%SEMI-OASIS\r\n" + bytes([1, len(version_str)]) + version_str
        mock_s3ap.streaming_download_range.return_value = oasis_data

        mock_s3_client = MagicMock()
        mock_boto3.client.return_value = mock_s3_client

        event = {"Key": "designs/layout.oas", "Size": 5000}
        context = MagicMock()

        result = handler(event, context)

        assert result["status"] == "SUCCESS"
        assert result["file_key"] == "designs/layout.oas"
        assert result["metadata"]["file_format"] == "OASIS"
        assert result["metadata"]["file_version"] == "1.0"

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT": "test-ap-ext-s3alias",
        "OUTPUT_BUCKET": "test-output-bucket",
    })
    @patch("functions.metadata_extraction.handler.boto3")
    @patch("functions.metadata_extraction.handler.S3ApHelper")
    def test_handler_unknown_format(self, mock_s3ap_cls, mock_boto3):
        """異常系: 不明なファイル形式で INVALID ステータスが返ること"""
        from functions.metadata_extraction.handler import handler

        mock_s3ap = MagicMock()
        mock_s3ap_cls.return_value = mock_s3ap
        mock_s3ap.streaming_download_range.return_value = b"some data"

        event = {"Key": "designs/unknown.txt", "Size": 100}
        context = MagicMock()

        result = handler(event, context)

        assert result["status"] == "INVALID"
        assert result["file_key"] == "designs/unknown.txt"
        assert "Unknown file format" in result["error"]

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT": "test-ap-ext-s3alias",
        "OUTPUT_BUCKET": "test-output-bucket",
    })
    @patch("functions.metadata_extraction.handler.boto3")
    @patch("functions.metadata_extraction.handler.S3ApHelper")
    def test_handler_s3_download_error(self, mock_s3ap_cls, mock_boto3):
        """異常系: S3 ダウンロードエラーで INVALID ステータスが返ること"""
        from functions.metadata_extraction.handler import handler

        mock_s3ap = MagicMock()
        mock_s3ap_cls.return_value = mock_s3ap
        mock_s3ap.streaming_download_range.side_effect = Exception("S3 error")

        event = {"Key": "designs/chip.gds", "Size": 100}
        context = MagicMock()

        result = handler(event, context)

        assert result["status"] == "INVALID"
        assert result["file_key"] == "designs/chip.gds"
        assert "S3 error" in result["error"]

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT": "test-ap-ext-s3alias",
        "OUTPUT_BUCKET": "test-output-bucket",
    })
    @patch("functions.metadata_extraction.handler.boto3")
    @patch("functions.metadata_extraction.handler.S3ApHelper")
    def test_handler_output_key_has_date_partition(self, mock_s3ap_cls, mock_boto3):
        """出力キーに日付パーティションが含まれること"""
        from functions.metadata_extraction.handler import handler

        mock_s3ap = MagicMock()
        mock_s3ap_cls.return_value = mock_s3ap

        header = build_gds_header(library_name="DATE_TEST", cell_count=1)
        mock_s3ap.streaming_download_range.return_value = header

        mock_s3_client = MagicMock()
        mock_boto3.client.return_value = mock_s3_client

        event = {"Key": "designs/chip.gds", "Size": 100}
        context = MagicMock()

        result = handler(event, context)

        assert result["status"] == "SUCCESS"
        # Verify date partition format YYYY/MM/DD
        import re
        assert re.search(r"\d{4}/\d{2}/\d{2}", result["output_key"])

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT": "test-ap-ext-s3alias",
        "OUTPUT_BUCKET": "test-output-bucket",
    })
    @patch("functions.metadata_extraction.handler.boto3")
    @patch("functions.metadata_extraction.handler.S3ApHelper")
    def test_handler_output_json_written_to_s3(self, mock_s3ap_cls, mock_boto3):
        """メタデータ JSON が S3 に書き込まれること"""
        from functions.metadata_extraction.handler import handler

        mock_s3ap = MagicMock()
        mock_s3ap_cls.return_value = mock_s3ap

        header = build_gds_header(library_name="S3_WRITE_TEST", cell_count=2)
        mock_s3ap.streaming_download_range.return_value = header

        mock_s3_client = MagicMock()
        mock_boto3.client.return_value = mock_s3_client

        event = {"Key": "designs/chip.gds", "Size": 100}
        context = MagicMock()

        result = handler(event, context)

        assert result["status"] == "SUCCESS"

        # Verify put_object was called with correct parameters
        call_kwargs = mock_s3_client.put_object.call_args[1]
        assert call_kwargs["Bucket"] == "test-output-bucket"
        assert call_kwargs["ContentType"] == "application/json"

        # Verify the body is valid JSON
        body_json = json.loads(call_kwargs["Body"].decode("utf-8"))
        assert body_json["file_key"] == "designs/chip.gds"
        assert body_json["library_name"] == "S3_WRITE_TEST"
        assert "extracted_at" in body_json
