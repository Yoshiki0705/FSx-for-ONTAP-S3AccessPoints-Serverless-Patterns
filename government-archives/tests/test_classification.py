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

    mock_comprehend = MagicMock()
    mock_comprehend.detect_dominant_language.return_value = {
        "Languages": [{"LanguageCode": "en", "Score": 0.99}]
    }

    def boto3_client(service):
        if service == "comprehend":
            return mock_comprehend
        return MagicMock()

    mock_writer = MagicMock()
    mock_writer.get_text.return_value = "Top Secret government briefing"

    with patch.object(classification_handler, "boto3") as mock_boto3, patch.object(
        classification_handler, "OutputWriter"
    ) as mock_output_writer_cls:
        mock_boto3.client.side_effect = boto3_client
        mock_output_writer_cls.from_env.return_value = mock_writer
        event = {"document_key": "d.pdf", "text_key": "ocr/d.pdf.txt"}
        result = classification_handler.handler(event, lambda_context)

    assert result["clearance_level"] == "confidential"
    assert result["language"] == "en"
    mock_writer.put_json.assert_called_once()
