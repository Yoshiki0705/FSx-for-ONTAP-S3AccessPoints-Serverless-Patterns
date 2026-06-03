"""UC21 Agri-Food Traceability — Discovery Lambda unit tests."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Dynamic import for namespace isolation
_handler_path = Path(__file__).parent.parent / "functions" / "discovery" / "handler.py"
_spec = importlib.util.spec_from_file_location("agri_discovery_handler", _handler_path)
_module = importlib.util.module_from_spec(_spec)
sys.modules["agri_discovery_handler"] = _module
_spec.loader.exec_module(_module)

classify_file = _module.classify_file
validate_s3ap_connectivity = _module.validate_s3ap_connectivity
AERIAL_IMAGE_EXTENSIONS = _module.AERIAL_IMAGE_EXTENSIONS
TRACEABILITY_DOC_EXTENSIONS = _module.TRACEABILITY_DOC_EXTENSIONS
DEFAULT_MAX_IMAGE_SIZE_MB = _module.DEFAULT_MAX_IMAGE_SIZE_MB

MAX_SIZE_BYTES = DEFAULT_MAX_IMAGE_SIZE_MB * 1024 * 1024


class TestClassifyFile:
    """ファイル分類ロジックのテスト"""

    def test_geotiff_image(self):
        result = classify_file(
            "aerial-images/field-a/2026-06.tif", 100_000_000,
            "aerial-images/", "traceability/", MAX_SIZE_BYTES,
        )
        assert result == "aerial_image"

    def test_jpeg_image(self):
        result = classify_file(
            "aerial-images/field-b/drone_001.jpg", 50_000_000,
            "aerial-images/", "traceability/", MAX_SIZE_BYTES,
        )
        assert result == "aerial_image"

    def test_jpeg_extension_variant(self):
        result = classify_file(
            "aerial-images/field-c/capture.jpeg", 30_000_000,
            "aerial-images/", "traceability/", MAX_SIZE_BYTES,
        )
        assert result == "aerial_image"

    def test_geotiff_extension(self):
        result = classify_file(
            "aerial-images/field/scan.geotiff", 200_000_000,
            "aerial-images/", "traceability/", MAX_SIZE_BYTES,
        )
        assert result == "aerial_image"

    def test_image_exceeds_500mb(self):
        """500 MB を超える画像はフィルタされる (Req 5.1)"""
        over_limit = 501 * 1024 * 1024  # 501 MB
        result = classify_file(
            "aerial-images/large/huge.tif", over_limit,
            "aerial-images/", "traceability/", MAX_SIZE_BYTES,
        )
        assert result is None

    def test_image_exactly_500mb(self):
        """500 MB ちょうどは許可"""
        exactly = 500 * 1024 * 1024
        result = classify_file(
            "aerial-images/exact/limit.tif", exactly,
            "aerial-images/", "traceability/", MAX_SIZE_BYTES,
        )
        assert result == "aerial_image"

    def test_traceability_pdf(self):
        result = classify_file(
            "traceability/lot-001/harvest_record.pdf", 1_000_000,
            "aerial-images/", "traceability/", MAX_SIZE_BYTES,
        )
        assert result == "traceability_doc"

    def test_traceability_csv(self):
        result = classify_file(
            "traceability/manifests/shipping.csv", 500_000,
            "aerial-images/", "traceability/", MAX_SIZE_BYTES,
        )
        assert result == "traceability_doc"

    def test_traceability_xlsx(self):
        result = classify_file(
            "traceability/inspection/cert.xlsx", 2_000_000,
            "aerial-images/", "traceability/", MAX_SIZE_BYTES,
        )
        assert result == "traceability_doc"

    def test_wrong_prefix(self):
        result = classify_file(
            "other/path/image.tif", 100_000,
            "aerial-images/", "traceability/", MAX_SIZE_BYTES,
        )
        assert result is None

    def test_unsupported_extension_in_image_prefix(self):
        result = classify_file(
            "aerial-images/data.mp4", 100_000,
            "aerial-images/", "traceability/", MAX_SIZE_BYTES,
        )
        assert result is None

    def test_empty_key(self):
        result = classify_file(
            "", 0,
            "aerial-images/", "traceability/", MAX_SIZE_BYTES,
        )
        assert result is None

    def test_no_extension(self):
        result = classify_file(
            "aerial-images/noext", 100_000,
            "aerial-images/", "traceability/", MAX_SIZE_BYTES,
        )
        assert result is None

    def test_case_insensitive_extension(self):
        result = classify_file(
            "aerial-images/field/photo.TIFF", 100_000,
            "aerial-images/", "traceability/", MAX_SIZE_BYTES,
        )
        assert result == "aerial_image"


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
