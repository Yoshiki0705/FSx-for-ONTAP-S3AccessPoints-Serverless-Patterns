"""UC20 Travel Document Processing — Discovery Lambda unit tests."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Dynamic import for namespace isolation
_handler_path = Path(__file__).parent.parent / "functions" / "discovery" / "handler.py"
_spec = importlib.util.spec_from_file_location("travel_discovery_handler", _handler_path)
_module = importlib.util.module_from_spec(_spec)
sys.modules["travel_discovery_handler"] = _module
_spec.loader.exec_module(_module)

classify_file = _module.classify_file
validate_s3ap_connectivity = _module.validate_s3ap_connectivity
RESERVATION_DOC_EXTENSIONS = _module.RESERVATION_DOC_EXTENSIONS
FACILITY_IMAGE_EXTENSIONS = _module.FACILITY_IMAGE_EXTENSIONS


class TestClassifyFile:
    """ファイル分類ロジックのテスト"""

    def test_reservation_pdf(self):
        result = classify_file(
            "reservations/2026/01/booking.pdf", "reservations/", "facility-inspections/"
        )
        assert result == "reservation_doc"

    def test_reservation_jpg(self):
        result = classify_file(
            "reservations/scan/receipt.jpg", "reservations/", "facility-inspections/"
        )
        assert result == "reservation_doc"

    def test_facility_image_jpeg(self):
        result = classify_file(
            "facility-inspections/lobby/photo.jpeg",
            "reservations/",
            "facility-inspections/",
        )
        assert result == "facility_image"

    def test_facility_image_png(self):
        result = classify_file(
            "facility-inspections/room101/wall.png",
            "reservations/",
            "facility-inspections/",
        )
        assert result == "facility_image"

    def test_facility_image_tiff(self):
        result = classify_file(
            "facility-inspections/pool/crack.tiff",
            "reservations/",
            "facility-inspections/",
        )
        assert result == "facility_image"

    def test_unsupported_extension(self):
        result = classify_file(
            "reservations/data.xlsx", "reservations/", "facility-inspections/"
        )
        assert result is None

    def test_wrong_prefix(self):
        result = classify_file(
            "other/path/file.pdf", "reservations/", "facility-inspections/"
        )
        assert result is None

    def test_empty_key(self):
        result = classify_file("", "reservations/", "facility-inspections/")
        assert result is None

    def test_no_extension(self):
        result = classify_file(
            "reservations/noext", "reservations/", "facility-inspections/"
        )
        assert result is None

    def test_case_insensitive_extension(self):
        result = classify_file(
            "reservations/doc.PDF", "reservations/", "facility-inspections/"
        )
        assert result == "reservation_doc"


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
        mock_s3ap.list_objects.side_effect = S3ApHelperError(
            "Connection failed", error_code="ServiceUnavailable"
        )
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
