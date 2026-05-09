"""Unit tests for UC16 Discovery Lambda."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch


def test_classify_document_type_pdf(discovery_handler):
    assert discovery_handler._classify_document_type("archives/file.pdf") == "pdf"


def test_classify_document_type_scanned(discovery_handler):
    assert discovery_handler._classify_document_type("archives/file.tif") == "scanned_image"
    assert discovery_handler._classify_document_type("archives/file.TIFF") == "scanned_image"


def test_classify_document_type_email(discovery_handler):
    assert discovery_handler._classify_document_type("archives/msg.eml") == "email"
    assert discovery_handler._classify_document_type("archives/msg.msg") == "email"


def test_classify_document_type_office(discovery_handler):
    assert discovery_handler._classify_document_type("archives/doc.docx") == "word"
    assert discovery_handler._classify_document_type("archives/doc.xlsx") == "excel"


def test_classify_document_type_unknown(discovery_handler):
    assert discovery_handler._classify_document_type("archives/file.jpg") == "unknown"


def test_handler_filters_and_classifies(
    discovery_handler, lambda_context, monkeypatch
):
    monkeypatch.setenv("S3_ACCESS_POINT", "test-ap-ext-s3alias")
    monkeypatch.setenv("PREFIX_FILTER", "archives/")
    monkeypatch.setenv("SUFFIX_FILTER", ".pdf,.eml")

    mock_pdfs = [{"Key": "archives/x.pdf", "Size": 1024, "LastModified": datetime(2026, 5, 10), "ETag": '"e1"'}]
    mock_emls = [{"Key": "archives/x.eml", "Size": 500, "LastModified": datetime(2026, 5, 10), "ETag": '"e2"'}]

    mock_s3ap = MagicMock()
    mock_s3ap.list_objects.side_effect = [mock_pdfs, mock_emls]
    mock_output = MagicMock()

    with patch.object(discovery_handler, "S3ApHelper", side_effect=[mock_s3ap, mock_output]):
        result = discovery_handler.handler({}, lambda_context)

    assert result["total_objects"] == 2
    assert result["document_types"]["pdf"] == 1
    assert result["document_types"]["email"] == 1
    mock_output.put_object.assert_called_once()


def test_handler_empty_results(
    discovery_handler, lambda_context, monkeypatch
):
    monkeypatch.setenv("S3_ACCESS_POINT", "test-ap-ext-s3alias")
    monkeypatch.setenv("SUFFIX_FILTER", ".pdf")

    mock_s3ap = MagicMock()
    mock_s3ap.list_objects.return_value = []

    with patch.object(discovery_handler, "S3ApHelper", side_effect=[mock_s3ap, mock_s3ap]):
        result = discovery_handler.handler({}, lambda_context)

    assert result["total_objects"] == 0
