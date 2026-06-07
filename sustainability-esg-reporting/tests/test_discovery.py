"""UC23 Sustainability ESG Reporting — Discovery Lambda unit tests."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Dynamic import for namespace isolation
_handler_path = Path(__file__).parent.parent / "functions" / "discovery" / "handler.py"
_spec = importlib.util.spec_from_file_location("esg_discovery_handler", _handler_path)
_module = importlib.util.module_from_spec(_spec)
sys.modules["esg_discovery_handler"] = _module
_spec.loader.exec_module(_module)

classify_file = _module.classify_file
validate_s3ap_connectivity = _module.validate_s3ap_connectivity
ESG_DOC_EXTENSIONS = _module.ESG_DOC_EXTENSIONS
ESG_CATEGORIES = _module.ESG_CATEGORIES


class TestClassifyFile:
    """ESG ファイル分類ロジックのテスト"""

    def test_environmental_pdf(self):
        result = classify_file(
            "environmental/2025/report.pdf",
            "environmental/",
            "social/",
            "governance/",
        )
        assert result == "environmental"

    def test_environmental_xlsx(self):
        result = classify_file(
            "environmental/energy/consumption.xlsx",
            "environmental/",
            "social/",
            "governance/",
        )
        assert result == "environmental"

    def test_social_pdf(self):
        result = classify_file(
            "social/diversity/report.pdf",
            "environmental/",
            "social/",
            "governance/",
        )
        assert result == "social"

    def test_governance_csv(self):
        result = classify_file(
            "governance/compliance/audit.csv",
            "environmental/",
            "social/",
            "governance/",
        )
        assert result == "governance"

    def test_governance_docx(self):
        result = classify_file(
            "governance/board/minutes.docx",
            "environmental/",
            "social/",
            "governance/",
        )
        assert result == "governance"

    def test_unsupported_extension(self):
        result = classify_file(
            "environmental/data.zip",
            "environmental/",
            "social/",
            "governance/",
        )
        assert result is None

    def test_wrong_prefix(self):
        result = classify_file(
            "other/path/file.pdf",
            "environmental/",
            "social/",
            "governance/",
        )
        assert result is None

    def test_empty_key(self):
        result = classify_file("", "environmental/", "social/", "governance/")
        assert result is None

    def test_no_extension(self):
        result = classify_file(
            "environmental/noext",
            "environmental/",
            "social/",
            "governance/",
        )
        assert result is None

    def test_case_insensitive_extension(self):
        result = classify_file(
            "environmental/report.PDF",
            "environmental/",
            "social/",
            "governance/",
        )
        assert result == "environmental"

    def test_nested_path(self):
        result = classify_file(
            "environmental/co2/2025/Q1/emissions.csv",
            "environmental/",
            "social/",
            "governance/",
        )
        assert result == "environmental"


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


class TestESGCategories:
    """ESG カテゴリ定義のテスト"""

    def test_three_categories_defined(self):
        assert len(ESG_CATEGORIES) == 3

    def test_all_esg_categories_present(self):
        assert "environmental" in ESG_CATEGORIES
        assert "social" in ESG_CATEGORIES
        assert "governance" in ESG_CATEGORIES
