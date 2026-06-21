"""UC28 Chemical SDS Management — Discovery Lambda unit tests."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_handler_path = Path(__file__).parent.parent / "functions" / "discovery" / "handler.py"
_spec = importlib.util.spec_from_file_location("chem_discovery_handler", _handler_path)
_module = importlib.util.module_from_spec(_spec)
sys.modules["chem_discovery_handler"] = _module
_spec.loader.exec_module(_module)

classify_file = _module.classify_file
extract_substance_id = _module.extract_substance_id
extract_revision_date = _module.extract_revision_date
validate_s3ap_connectivity = _module.validate_s3ap_connectivity
FILE_TYPE_SDS = _module.FILE_TYPE_SDS
FILE_TYPE_LABBOOK = _module.FILE_TYPE_LABBOOK


class TestClassifyFile:
    def test_sds_pdf(self):
        result = classify_file("sds/substance-123/sds_2024.pdf", "sds/", "labbooks/")
        assert result == FILE_TYPE_SDS

    def test_sds_xml(self):
        result = classify_file("sds/CAS-7732-18-5/ghs.xml", "sds/", "labbooks/")
        assert result == FILE_TYPE_SDS

    def test_labbook_jpeg(self):
        result = classify_file("labbooks/exp001/page1.jpg", "sds/", "labbooks/")
        assert result == FILE_TYPE_LABBOOK

    def test_labbook_png(self):
        result = classify_file("labbooks/exp002/notes.png", "sds/", "labbooks/")
        assert result == FILE_TYPE_LABBOOK

    def test_labbook_tiff(self):
        result = classify_file("labbooks/exp003/scan.tiff", "sds/", "labbooks/")
        assert result == FILE_TYPE_LABBOOK

    def test_unsupported_extension(self):
        result = classify_file("sds/data.doc", "sds/", "labbooks/")
        assert result is None

    def test_wrong_prefix(self):
        result = classify_file("other/file.pdf", "sds/", "labbooks/")
        assert result is None

    def test_empty_key(self):
        result = classify_file("", "sds/", "labbooks/")
        assert result is None


class TestExtractSubstanceId:
    def test_substance_hyphen(self):
        result = extract_substance_id("sds/substance-H2O/sds.pdf")
        assert result == "H2O"

    def test_cas_pattern(self):
        result = extract_substance_id("sds/CAS-7732-18-5/document.pdf")
        assert result == "7732-18-5"

    def test_substance_underscore(self):
        result = extract_substance_id("sds/substance_NaCl/data.xml")
        assert result == "NaCl"

    def test_no_substance_id(self):
        result = extract_substance_id("sds/unknown/file.pdf")
        assert result is None


class TestExtractRevisionDate:
    def test_hyphenated_date(self):
        result = extract_revision_date("sds/substance-A/2024-03-15/sds.pdf")
        assert result == "2024-03-15"

    def test_compact_date(self):
        result = extract_revision_date("sds/20240315_revision.pdf")
        assert result == "2024-03-15"

    def test_no_date(self):
        result = extract_revision_date("sds/substance-A/current.pdf")
        assert result is None

    def test_invalid_date(self):
        result = extract_revision_date("sds/2024-13-45/file.pdf")
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
