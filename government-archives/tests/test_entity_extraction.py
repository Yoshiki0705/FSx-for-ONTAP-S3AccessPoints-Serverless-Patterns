"""Unit tests for UC16 Entity Extraction Lambda."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_detect_pii_regex_email(entity_extraction_handler):
    entities = entity_extraction_handler.detect_pii_regex(
        "Contact john.doe@example.com for details"
    )
    assert any(e["Type"] == "EMAIL" for e in entities)


def test_detect_pii_regex_ssn(entity_extraction_handler):
    entities = entity_extraction_handler.detect_pii_regex("SSN: 123-45-6789")
    assert any(e["Type"] == "SSN" for e in entities)


def test_detect_pii_regex_credit_card(entity_extraction_handler):
    entities = entity_extraction_handler.detect_pii_regex(
        "Card: 1234-5678-9012-3456"
    )
    assert any(e["Type"] == "CREDIT_CARD" for e in entities)


def test_detect_pii_regex_phone_us(entity_extraction_handler):
    entities = entity_extraction_handler.detect_pii_regex(
        "Call 202-555-1234 for info"
    )
    assert any(e["Type"] == "PHONE_US" for e in entities)


def test_detect_pii_regex_no_match(entity_extraction_handler):
    entities = entity_extraction_handler.detect_pii_regex("No PII here")
    assert len(entities) == 0


def test_detect_pii_comprehend_success(entity_extraction_handler):
    mock_comp = MagicMock()
    mock_comp.detect_pii_entities.return_value = {
        "Entities": [
            {"Type": "NAME", "BeginOffset": 0, "EndOffset": 8, "Score": 0.99}
        ]
    }
    entities = entity_extraction_handler.detect_pii_comprehend(
        mock_comp, "John Doe works here", "en"
    )
    assert len(entities) == 1
    assert entities[0]["Type"] == "NAME"


def test_detect_pii_comprehend_empty_text(entity_extraction_handler):
    mock_comp = MagicMock()
    entities = entity_extraction_handler.detect_pii_comprehend(
        mock_comp, "", "en"
    )
    assert entities == []


def test_handler_extracts_pii(
    entity_extraction_handler, lambda_context, monkeypatch
):
    monkeypatch.setenv("OUTPUT_BUCKET", "test-bucket")

    text = "Contact John Doe at john@example.com or 202-555-1234"

    mock_comp = MagicMock()
    mock_comp.detect_pii_entities.return_value = {
        "Entities": [
            {"Type": "NAME", "BeginOffset": 8, "EndOffset": 16, "Score": 0.99}
        ]
    }

    def boto3_client(service):
        if service == "comprehend":
            return mock_comp
        return MagicMock()

    mock_writer = MagicMock()
    mock_writer.get_text.return_value = text

    with patch.object(entity_extraction_handler, "boto3") as mock_boto3, patch.object(
        entity_extraction_handler, "OutputWriter"
    ) as mock_output_writer_cls:
        mock_boto3.client.side_effect = boto3_client
        mock_output_writer_cls.from_env.return_value = mock_writer
        event = {
            "document_key": "d.pdf",
            "text_key": "ocr/d.txt",
            "language": "en",
        }
        result = entity_extraction_handler.handler(event, lambda_context)

    assert result["pii_count"] >= 1
    # PII text hashed, not raw
    for entity in result["entities"]:
        assert "TextHash" in entity
    mock_writer.put_json.assert_called_once()
