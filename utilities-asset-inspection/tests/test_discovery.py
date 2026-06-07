"""UC25 Utilities Asset Inspection — Discovery Lambda unit tests."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Dynamic import for namespace isolation
_handler_path = Path(__file__).parent.parent / "functions" / "discovery" / "handler.py"
_spec = importlib.util.spec_from_file_location("utilities_discovery_handler", _handler_path)
_module = importlib.util.module_from_spec(_spec)
sys.modules["utilities_discovery_handler"] = _module
_spec.loader.exec_module(_module)

classify_file = _module.classify_file
extract_equipment_id = _module.extract_equipment_id
extract_inspection_date = _module.extract_inspection_date
get_file_format = _module.get_file_format
validate_s3ap_connectivity = _module.validate_s3ap_connectivity
DRONE_IMAGE_EXTENSIONS = _module.DRONE_IMAGE_EXTENSIONS
SCADA_LOG_EXTENSIONS = _module.SCADA_LOG_EXTENSIONS
FILE_TYPE_DRONE_IMAGE = _module.FILE_TYPE_DRONE_IMAGE
FILE_TYPE_THERMAL_IMAGE = _module.FILE_TYPE_THERMAL_IMAGE
FILE_TYPE_SCADA_LOG = _module.FILE_TYPE_SCADA_LOG


class TestClassifyFile:
    """ファイル分類ロジックのテスト"""

    def test_drone_image_jpeg(self):
        result = classify_file(
            "drone-images/EQ-12345/2025-06-01/img001.jpg",
            "drone-images/",
            "scada-logs/",
        )
        assert result == FILE_TYPE_DRONE_IMAGE

    def test_drone_image_png(self):
        result = classify_file(
            "drone-images/EQ-001/inspection.png",
            "drone-images/",
            "scada-logs/",
        )
        assert result == FILE_TYPE_DRONE_IMAGE

    def test_drone_image_tiff(self):
        result = classify_file(
            "drone-images/EQ-001/photo.tiff",
            "drone-images/",
            "scada-logs/",
        )
        assert result == FILE_TYPE_DRONE_IMAGE

    def test_thermal_image_fff(self):
        result = classify_file(
            "drone-images/EQ-001/thermal.fff",
            "drone-images/",
            "scada-logs/",
        )
        assert result == FILE_TYPE_THERMAL_IMAGE

    def test_thermal_image_seq(self):
        result = classify_file(
            "drone-images/EQ-001/thermal.seq",
            "drone-images/",
            "scada-logs/",
        )
        assert result == FILE_TYPE_THERMAL_IMAGE

    def test_scada_log_csv(self):
        result = classify_file(
            "scada-logs/EQ-001/2025-06-01/readings.csv",
            "drone-images/",
            "scada-logs/",
        )
        assert result == FILE_TYPE_SCADA_LOG

    def test_scada_log_parquet(self):
        result = classify_file(
            "scada-logs/EQ-001/data.parquet",
            "drone-images/",
            "scada-logs/",
        )
        assert result == FILE_TYPE_SCADA_LOG

    def test_scada_log_json(self):
        result = classify_file(
            "scada-logs/readings.json",
            "drone-images/",
            "scada-logs/",
        )
        assert result == FILE_TYPE_SCADA_LOG

    def test_unsupported_extension_in_drone(self):
        result = classify_file(
            "drone-images/EQ-001/video.mp4",
            "drone-images/",
            "scada-logs/",
        )
        assert result is None

    def test_wrong_prefix(self):
        result = classify_file(
            "other/path/file.jpg",
            "drone-images/",
            "scada-logs/",
        )
        assert result is None

    def test_empty_key(self):
        result = classify_file("", "drone-images/", "scada-logs/")
        assert result is None

    def test_no_extension(self):
        result = classify_file(
            "drone-images/noext",
            "drone-images/",
            "scada-logs/",
        )
        assert result is None


class TestExtractEquipmentId:
    """設備 ID 抽出のテスト"""

    def test_eq_hyphen_pattern(self):
        result = extract_equipment_id("drone-images/EQ-12345/2025-06-01/img.jpg")
        assert result == "12345"

    def test_eq_underscore_pattern(self):
        result = extract_equipment_id("drone-images/EQ_ABC123/img.jpg")
        assert result == "ABC123"

    def test_equipment_prefix(self):
        result = extract_equipment_id("drone-images/equipment_XYZ99/img.jpg")
        assert result == "XYZ99"

    def test_case_insensitive(self):
        result = extract_equipment_id("drone-images/eq-lower01/img.jpg")
        assert result == "lower01"

    def test_no_equipment_id(self):
        result = extract_equipment_id("drone-images/unknown/img.jpg")
        assert result is None

    def test_empty_key(self):
        result = extract_equipment_id("")
        assert result is None


class TestExtractInspectionDate:
    """点検日抽出のテスト"""

    def test_hyphenated_date(self):
        result = extract_inspection_date("drone-images/EQ-001/2025-06-15/img.jpg")
        assert result == "2025-06-15"

    def test_slash_date(self):
        result = extract_inspection_date("drone-images/2025/06/15/img.jpg")
        assert result == "2025-06-15"

    def test_compact_date(self):
        result = extract_inspection_date("drone-images/EQ-001/20250615_inspection.jpg")
        assert result == "2025-06-15"

    def test_no_date(self):
        result = extract_inspection_date("drone-images/EQ-001/img.jpg")
        assert result is None

    def test_invalid_date(self):
        result = extract_inspection_date("drone-images/EQ-001/2025-13-45/img.jpg")
        assert result is None


class TestGetFileFormat:
    """ファイルフォーマット取得のテスト"""

    def test_jpeg(self):
        assert get_file_format("img.jpg") == "jpeg"

    def test_jpeg_full(self):
        assert get_file_format("img.jpeg") == "jpeg"

    def test_png(self):
        assert get_file_format("img.png") == "png"

    def test_tiff(self):
        assert get_file_format("img.tiff") == "tiff"

    def test_tif(self):
        assert get_file_format("img.tif") == "tiff"

    def test_flir_fff(self):
        assert get_file_format("thermal.fff") == "flir_fff"

    def test_flir_seq(self):
        assert get_file_format("thermal.seq") == "flir_seq"

    def test_csv(self):
        assert get_file_format("data.csv") == "csv"

    def test_parquet(self):
        assert get_file_format("data.parquet") == "parquet"

    def test_no_extension(self):
        assert get_file_format("noext") == "unknown"


class TestValidateS3ApConnectivity:
    """S3 AP 接続性バリデーションのテスト"""

    def test_connectivity_success(self):
        mock_s3ap = MagicMock()
        mock_s3ap.list_objects.return_value = []
        result = validate_s3ap_connectivity(mock_s3ap)
        assert result is None

    def test_connectivity_failure_s3ap_error(self):
        from shared.exceptions import S3ApHelperError

        mock_s3ap = MagicMock()
        mock_s3ap.bucket_param = "test-ap"
        mock_s3ap.list_objects.side_effect = S3ApHelperError("Connection failed", error_code="ServiceUnavailable")
        result = validate_s3ap_connectivity(mock_s3ap)
        assert result is not None
        assert result["statusCode"] == 503
        body = json.loads(result["body"])
        assert body["error_type"] == "ConnectivityError"

    def test_connectivity_failure_unexpected_error(self):
        mock_s3ap = MagicMock()
        mock_s3ap.bucket_param = "test-ap"
        mock_s3ap.list_objects.side_effect = RuntimeError("Unexpected")
        result = validate_s3ap_connectivity(mock_s3ap)
        assert result is not None
        assert result["statusCode"] == 503
