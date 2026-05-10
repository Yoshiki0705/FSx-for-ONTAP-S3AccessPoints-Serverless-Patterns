"""Unit tests for UC16 Redaction Lambda."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_redact_text_empty_entities(redaction_handler):
    text = "Hello World"
    redacted, metadata = redaction_handler.redact_text(text, [])
    assert redacted == text
    assert metadata == []


def test_redact_text_single_entity(redaction_handler):
    text = "Contact John Doe today"
    entities = [{"Type": "NAME", "BeginOffset": 8, "EndOffset": 16, "Score": 0.99}]
    redacted, metadata = redaction_handler.redact_text(text, entities)
    assert "[REDACTED]" in redacted
    assert "John Doe" not in redacted
    assert len(metadata) == 1
    assert metadata[0]["entity_type"] == "NAME"


def test_redact_text_multiple_entities(redaction_handler):
    text = "John Doe emailed jane@example.com yesterday"
    entities = [
        {"Type": "NAME", "BeginOffset": 0, "EndOffset": 8, "Score": 0.95},
        {"Type": "EMAIL", "BeginOffset": 17, "EndOffset": 33, "Score": 0.99},
    ]
    redacted, metadata = redaction_handler.redact_text(text, entities)
    # Two markers, no PII
    assert redacted.count("[REDACTED]") == 2
    assert "John Doe" not in redacted
    assert "jane@example.com" not in redacted


def test_redact_text_custom_marker(redaction_handler):
    text = "Name here"
    entities = [{"Type": "NAME", "BeginOffset": 0, "EndOffset": 4, "Score": 0.9}]
    redacted, _ = redaction_handler.redact_text(text, entities, marker="XXX")
    assert "XXX" in redacted
    assert "[REDACTED]" not in redacted


def test_redact_text_invalid_offsets_skipped(redaction_handler):
    text = "Hello"
    # Invalid: end < begin
    entities = [{"Type": "NAME", "BeginOffset": 10, "EndOffset": 5, "Score": 0.9}]
    redacted, metadata = redaction_handler.redact_text(text, entities)
    assert redacted == text
    assert len(metadata) == 0


def test_redact_text_metadata_contains_hash(redaction_handler):
    text = "John Doe"
    entities = [{"Type": "NAME", "BeginOffset": 0, "EndOffset": 8, "Score": 0.99}]
    _, metadata = redaction_handler.redact_text(text, entities)
    # Metadata keeps hash, not original PII
    assert "original_text_hash" in metadata[0]
    assert metadata[0]["original_text_hash"].startswith("sha256:")
    assert "John" not in metadata[0]["original_text_hash"]


def test_handler_writes_redacted_and_metadata(
    redaction_handler, lambda_context, monkeypatch
):
    monkeypatch.setenv("OUTPUT_BUCKET", "test-bucket")

    text = "Contact John Doe today"

    mock_writer = MagicMock()
    mock_writer.get_text.return_value = text

    with patch.object(
        redaction_handler, "OutputWriter"
    ) as mock_output_writer_cls:
        mock_output_writer_cls.from_env.return_value = mock_writer
        event = {
            "document_key": "doc.pdf",
            "text_key": "ocr-results/doc.pdf.txt",
            "entities": [
                {"Type": "NAME", "BeginOffset": 8, "EndOffset": 16, "Score": 0.99}
            ],
        }
        result = redaction_handler.handler(event, lambda_context)

    assert result["redaction_count"] == 1
    # 書き出しは put_text (redacted) + put_json (metadata) の 2 回
    assert mock_writer.put_text.call_count == 1
    assert mock_writer.put_json.call_count == 1
