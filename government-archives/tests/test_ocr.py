"""Unit tests for UC16 OCR Lambda (Textract sync/async routing)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_select_textract_api_sync_for_small(ocr_handler):
    """<= threshold pages use sync API."""
    assert ocr_handler.select_textract_api(1, 10) == "sync"
    assert ocr_handler.select_textract_api(10, 10) == "sync"


def test_select_textract_api_async_for_large(ocr_handler):
    """> threshold pages use async API."""
    assert ocr_handler.select_textract_api(11, 10) == "async"
    assert ocr_handler.select_textract_api(100, 10) == "async"


def test_select_textract_api_boundary(ocr_handler):
    """Boundary condition at exactly threshold."""
    # Exactly threshold: sync
    assert ocr_handler.select_textract_api(10, 10) == "sync"
    # threshold + 1: async
    assert ocr_handler.select_textract_api(11, 10) == "async"


def test_extract_text_sync_returns_lines(ocr_handler):
    """Sync extraction returns joined text lines."""
    mock_textract = MagicMock()
    mock_textract.analyze_document.return_value = {
        "Blocks": [
            {"BlockType": "LINE", "Text": "Hello"},
            {"BlockType": "LINE", "Text": "World"},
            {"BlockType": "WORD", "Text": "ignored"},
        ]
    }
    text, blocks = ocr_handler._extract_text_sync(mock_textract, b"pdf-bytes")
    assert "Hello" in text
    assert "World" in text
    assert len(blocks) == 3


def test_handler_routes_to_sync_for_small_doc(
    ocr_handler, lambda_context, monkeypatch
):
    """Small document uses sync Textract."""
    monkeypatch.setenv("OUTPUT_BUCKET", "test-bucket")
    monkeypatch.setenv("SYNC_PAGE_THRESHOLD", "10")

    small_pdf = b"%PDF-1.4" + b"\x00" * 1000  # ~1KB, page_count=1

    mock_s3_client = MagicMock()
    mock_s3_client.get_object.return_value = {"Body": MagicMock(read=lambda: small_pdf)}

    mock_textract = MagicMock()
    mock_textract.analyze_document.return_value = {
        "Blocks": [{"BlockType": "LINE", "Text": "Test text"}]
    }
    mock_textract.exceptions = MagicMock()
    mock_textract.exceptions.InvalidParameterException = type(
        "InvalidParameterException", (Exception,), {}
    )

    def boto3_client(service):
        if service == "s3":
            return mock_s3_client
        if service == "textract":
            return mock_textract
        return MagicMock()

    with patch.object(ocr_handler, "boto3") as mock_boto3:
        mock_boto3.client.side_effect = boto3_client
        event = {"Key": "archives/small.pdf", "Size": 1000}
        result = ocr_handler.handler(event, lambda_context)

    assert result["api_used"] == "sync"
    assert result["text_length"] > 0
