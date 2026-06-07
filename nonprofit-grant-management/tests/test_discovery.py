"""UC24 Nonprofit Grant Management — Discovery Lambda unit tests."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Dynamic import for namespace isolation
_handler_path = Path(__file__).parent.parent / "functions" / "discovery" / "handler.py"
_spec = importlib.util.spec_from_file_location("npo_discovery_handler", _handler_path)
_module = importlib.util.module_from_spec(_spec)
sys.modules["npo_discovery_handler"] = _module
_spec.loader.exec_module(_module)

classify_file = _module.classify_file
extract_program_area = _module.extract_program_area
extract_submission_date = _module.extract_submission_date
validate_s3ap_connectivity = _module.validate_s3ap_connectivity
GRANT_DOC_EXTENSIONS = _module.GRANT_DOC_EXTENSIONS
DOC_TYPE_APPLICATION = _module.DOC_TYPE_APPLICATION
DOC_TYPE_REPORT = _module.DOC_TYPE_REPORT


class TestClassifyFile:
    """ファイル分類ロジックのテスト"""

    def test_grant_application_pdf(self):
        result = classify_file(
            "grant-applications/education/2025/proposal.pdf",
            "grant-applications/",
            "activity-reports/",
        )
        assert result == DOC_TYPE_APPLICATION

    def test_grant_application_docx(self):
        result = classify_file(
            "grant-applications/health/application.docx",
            "grant-applications/",
            "activity-reports/",
        )
        assert result == DOC_TYPE_APPLICATION

    def test_grant_application_doc(self):
        result = classify_file(
            "grant-applications/environment/project.doc",
            "grant-applications/",
            "activity-reports/",
        )
        assert result == DOC_TYPE_APPLICATION

    def test_activity_report_pdf(self):
        result = classify_file(
            "activity-reports/education/2025/annual-report.pdf",
            "grant-applications/",
            "activity-reports/",
        )
        assert result == DOC_TYPE_REPORT

    def test_activity_report_docx(self):
        result = classify_file(
            "activity-reports/health/outcomes.docx",
            "grant-applications/",
            "activity-reports/",
        )
        assert result == DOC_TYPE_REPORT

    def test_unsupported_extension(self):
        result = classify_file(
            "grant-applications/data.xlsx",
            "grant-applications/",
            "activity-reports/",
        )
        assert result is None

    def test_wrong_prefix(self):
        result = classify_file(
            "other/path/file.pdf",
            "grant-applications/",
            "activity-reports/",
        )
        assert result is None

    def test_empty_key(self):
        result = classify_file("", "grant-applications/", "activity-reports/")
        assert result is None

    def test_no_extension(self):
        result = classify_file(
            "grant-applications/noext",
            "grant-applications/",
            "activity-reports/",
        )
        assert result is None

    def test_case_insensitive_extension(self):
        result = classify_file(
            "grant-applications/report.PDF",
            "grant-applications/",
            "activity-reports/",
        )
        assert result == DOC_TYPE_APPLICATION

    def test_nested_path(self):
        result = classify_file(
            "grant-applications/education/2025/Q1/proposal.pdf",
            "grant-applications/",
            "activity-reports/",
        )
        assert result == DOC_TYPE_APPLICATION


class TestExtractProgramArea:
    """プログラムエリア抽出のテスト"""

    def test_standard_path(self):
        result = extract_program_area(
            "grant-applications/education/2025/proposal.pdf",
            "grant-applications/",
        )
        assert result == "education"

    def test_health_area(self):
        result = extract_program_area(
            "grant-applications/health/application.pdf",
            "grant-applications/",
        )
        assert result == "health"

    def test_no_subdirectory(self):
        result = extract_program_area(
            "grant-applications/proposal.pdf",
            "grant-applications/",
        )
        assert result == "general"

    def test_wrong_prefix(self):
        result = extract_program_area(
            "other/path/file.pdf",
            "grant-applications/",
        )
        assert result == "general"

    def test_empty_area(self):
        result = extract_program_area(
            "grant-applications//file.pdf",
            "grant-applications/",
        )
        assert result == "general"


class TestExtractSubmissionDate:
    """提出日抽出のテスト"""

    def test_hyphenated_date(self):
        result = extract_submission_date("grant-applications/education/2025-03-15/proposal.pdf")
        assert result == "2025-03-15"

    def test_slash_date(self):
        result = extract_submission_date("grant-applications/2025/03/15/proposal.pdf")
        assert result == "2025-03-15"

    def test_compact_date(self):
        result = extract_submission_date("grant-applications/education/20250315_proposal.pdf")
        assert result == "2025-03-15"

    def test_no_date(self):
        result = extract_submission_date("grant-applications/education/proposal.pdf")
        assert result is None

    def test_invalid_date(self):
        result = extract_submission_date("grant-applications/education/2025-13-45/proposal.pdf")
        assert result is None


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


class TestGrantDocExtensions:
    """対応拡張子の定義テスト"""

    def test_pdf_supported(self):
        assert ".pdf" in GRANT_DOC_EXTENSIONS

    def test_docx_supported(self):
        assert ".docx" in GRANT_DOC_EXTENSIONS

    def test_doc_supported(self):
        assert ".doc" in GRANT_DOC_EXTENSIONS

    def test_xlsx_not_supported(self):
        assert ".xlsx" not in GRANT_DOC_EXTENSIONS
