"""UC26 Real Estate Portfolio — Discovery Lambda unit tests."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Dynamic import for namespace isolation
_handler_path = Path(__file__).parent.parent / "functions" / "discovery" / "handler.py"
_spec = importlib.util.spec_from_file_location("realestate_discovery_handler", _handler_path)
_module = importlib.util.module_from_spec(_spec)
sys.modules["realestate_discovery_handler"] = _module
_spec.loader.exec_module(_module)

classify_file = _module.classify_file
extract_property_id = _module.extract_property_id
detect_image_type = _module.detect_image_type
validate_s3ap_connectivity = _module.validate_s3ap_connectivity
FILE_TYPE_PROPERTY_IMAGE = _module.FILE_TYPE_PROPERTY_IMAGE
FILE_TYPE_CONTRACT = _module.FILE_TYPE_CONTRACT


class TestClassifyFile:
    """ファイル分類ロジックのテスト"""

    def test_property_image_jpeg(self):
        result = classify_file(
            "properties/images/PROP-001/interior/room1.jpg",
            "properties/images/",
            "properties/contracts/",
        )
        assert result == FILE_TYPE_PROPERTY_IMAGE

    def test_property_image_png(self):
        result = classify_file(
            "properties/images/PROP-001/exterior.png",
            "properties/images/",
            "properties/contracts/",
        )
        assert result == FILE_TYPE_PROPERTY_IMAGE

    def test_property_image_tiff(self):
        result = classify_file(
            "properties/images/PROP-001/floorplan.tiff",
            "properties/images/",
            "properties/contracts/",
        )
        assert result == FILE_TYPE_PROPERTY_IMAGE

    def test_contract_pdf(self):
        result = classify_file(
            "properties/contracts/PROP-001/lease_2024.pdf",
            "properties/images/",
            "properties/contracts/",
        )
        assert result == FILE_TYPE_CONTRACT

    def test_unsupported_extension(self):
        result = classify_file(
            "properties/images/PROP-001/video.mp4",
            "properties/images/",
            "properties/contracts/",
        )
        assert result is None

    def test_wrong_prefix(self):
        result = classify_file(
            "other/path/photo.jpg",
            "properties/images/",
            "properties/contracts/",
        )
        assert result is None

    def test_empty_key(self):
        result = classify_file("", "properties/images/", "properties/contracts/")
        assert result is None

    def test_no_extension(self):
        result = classify_file(
            "properties/images/noext",
            "properties/images/",
            "properties/contracts/",
        )
        assert result is None


class TestExtractPropertyId:
    """物件 ID 抽出のテスト"""

    def test_prop_hyphen(self):
        result = extract_property_id("properties/images/PROP-12345/room.jpg")
        assert result == "12345"

    def test_prop_underscore(self):
        result = extract_property_id("properties/images/PROP_ABC123/room.jpg")
        assert result == "ABC123"

    def test_property_prefix(self):
        result = extract_property_id("properties/images/property-XYZ99/room.jpg")
        assert result == "XYZ99"

    def test_no_property_id(self):
        result = extract_property_id("properties/images/unknown/room.jpg")
        assert result is None

    def test_empty_key(self):
        result = extract_property_id("")
        assert result is None


class TestDetectImageType:
    """画像タイプ推定のテスト"""

    def test_interior_keyword(self):
        assert detect_image_type("PROP-001/interior/room.jpg") == "interior"

    def test_exterior_keyword(self):
        assert detect_image_type("PROP-001/exterior/front.jpg") == "exterior"

    def test_floor_plan_keyword(self):
        assert detect_image_type("PROP-001/floor_plan/1f.png") == "floor_plan"

    def test_japanese_interior(self):
        assert detect_image_type("PROP-001/内装/room.jpg") == "interior"

    def test_japanese_floor_plan(self):
        assert detect_image_type("PROP-001/間取り/plan.png") == "floor_plan"

    def test_unknown_type(self):
        assert detect_image_type("PROP-001/misc/photo.jpg") == "other"


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

    def test_connectivity_failure_unexpected(self):
        mock_s3ap = MagicMock()
        mock_s3ap.bucket_param = "test-ap"
        mock_s3ap.list_objects.side_effect = RuntimeError("Unexpected")
        result = validate_s3ap_connectivity(mock_s3ap)
        assert result is not None
        assert result["statusCode"] == 503
