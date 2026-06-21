"""UC27 HR Document Screening — Discovery Lambda unit tests."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_handler_path = Path(__file__).parent.parent / "functions" / "discovery" / "handler.py"
_spec = importlib.util.spec_from_file_location("hr_discovery_handler", _handler_path)
_module = importlib.util.module_from_spec(_spec)
sys.modules["hr_discovery_handler"] = _module
_spec.loader.exec_module(_module)

classify_file = _module.classify_file
detect_position_type = _module.detect_position_type
extract_submission_date = _module.extract_submission_date
validate_s3ap_connectivity = _module.validate_s3ap_connectivity
FILE_TYPE_RESUME = _module.FILE_TYPE_RESUME


class TestClassifyFile:
    def test_pdf_resume(self):
        result = classify_file("hr/resumes/engineer/tanaka.pdf", "hr/resumes/")
        assert result == FILE_TYPE_RESUME

    def test_docx_resume(self):
        result = classify_file("hr/resumes/sales/resume.docx", "hr/resumes/")
        assert result == FILE_TYPE_RESUME

    def test_xlsx_resume(self):
        result = classify_file("hr/resumes/admin/data.xlsx", "hr/resumes/")
        assert result == FILE_TYPE_RESUME

    def test_unsupported_format(self):
        result = classify_file("hr/resumes/photo.jpg", "hr/resumes/")
        assert result is None

    def test_wrong_prefix(self):
        result = classify_file("other/resume.pdf", "hr/resumes/")
        assert result is None

    def test_empty_key(self):
        result = classify_file("", "hr/resumes/")
        assert result is None


class TestDetectPositionType:
    def test_engineer(self):
        assert detect_position_type("hr/resumes/engineer/file.pdf") == "engineering"

    def test_japanese_engineer(self):
        assert detect_position_type("hr/resumes/エンジニア/file.pdf") == "engineering"

    def test_sales(self):
        assert detect_position_type("hr/resumes/sales/file.pdf") == "sales"

    def test_japanese_sales(self):
        assert detect_position_type("hr/resumes/営業/file.pdf") == "sales"

    def test_general(self):
        assert detect_position_type("hr/resumes/misc/file.pdf") == "general"


class TestExtractSubmissionDate:
    def test_hyphenated_date(self):
        result = extract_submission_date("hr/resumes/2025-06-15/resume.pdf")
        assert result == "2025-06-15"

    def test_compact_date(self):
        result = extract_submission_date("hr/resumes/20250615_tanaka.pdf")
        assert result == "2025-06-15"

    def test_no_date(self):
        result = extract_submission_date("hr/resumes/resume.pdf")
        assert result is None

    def test_invalid_date(self):
        result = extract_submission_date("hr/resumes/2025-13-45/file.pdf")
        assert result is None


class TestValidateS3ApConnectivity:
    def test_success(self):
        mock_s3ap = MagicMock()
        mock_s3ap.list_objects.return_value = []
        assert validate_s3ap_connectivity(mock_s3ap) is None

    def test_failure(self):
        from shared.exceptions import S3ApHelperError

        mock_s3ap = MagicMock()
        mock_s3ap.bucket_param = "test-ap"
        mock_s3ap.list_objects.side_effect = S3ApHelperError("Fail", error_code="ServiceUnavailable")
        result = validate_s3ap_connectivity(mock_s3ap)
        assert result is not None
        assert result["statusCode"] == 503
