"""Unit tests for UC16 Classification Lambda."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_classify_by_keywords_confidential(classification_handler):
    level, conf = classification_handler.classify_by_keywords(
        "This document contains TOP SECRET information"
    )
    assert level == "confidential"
    assert conf >= 0.9


def test_classify_by_keywords_sensitive(classification_handler):
    level, conf = classification_handler.classify_by_keywords(
        "This is an internal memo, restricted to department members"
    )
    assert level == "sensitive"
    assert 0.8 <= conf < 0.95


def test_classify_by_keywords_public(classification_handler):
    level, conf = classification_handler.classify_by_keywords(
        "Annual budget report available to public"
    )
    assert level == "public"
    assert conf >= 0.7


def test_classify_by_keywords_japanese(classification_handler):
    """Japanese keyword classification."""
    level, _ = classification_handler.classify_by_keywords("極秘資料")
    assert level == "confidential"
    level, _ = classification_handler.classify_by_keywords("社外秘")
    assert level == "sensitive"


def test_detect_language_fallback(classification_handler):
    """Language detection falls back to 'en' on empty text."""
    mock_comprehend = MagicMock()
    lang = classification_handler.detect_language(mock_comprehend, "")
    assert lang == "en"


def test_handler_uses_keyword_fallback(
    classification_handler, lambda_context, monkeypatch
):
    monkeypatch.setenv("OUTPUT_BUCKET", "test-bucket")
    monkeypatch.delenv("CLASSIFIER_ENDPOINT_ARN", raising=False)

    mock_s3_client = MagicMock()
    mock_s3_client.get_object.return_value = {
        "Body": MagicMock(read=lambda: b"Top Secret government briefing")
    }

    mock_comprehend = MagicMock()
    mock_comprehend.detect_dominant_language.return_value = {
        "Languages": [{"LanguageCode": "en", "Score": 0.99}]
    }

    def boto3_client(service):
        if service == "s3":
            return mock_s3_client
        if service == "comprehend":
            return mock_comprehend
        return MagicMock()

    with patch.object(classification_handler, "boto3") as mock_boto3:
        mock_boto3.client.side_effect = boto3_client
        event = {"document_key": "d.pdf", "text_key": "ocr/d.pdf.txt"}
        result = classification_handler.handler(event, lambda_context)

    assert result["clearance_level"] == "confidential"
    assert result["language"] == "en"
