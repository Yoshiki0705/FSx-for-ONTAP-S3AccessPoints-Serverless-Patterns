"""Unit tests for UC17 Report Generation Lambda."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_build_prompt_includes_sections(report_generation_handler):
    prompt = report_generation_handler.build_prompt(
        source_key="gis/area.tif",
        landuse={"residential": 0.5, "forest": 0.3},
        change_magnitude=0.2,
        dominant_change={
            "max_increase": {"class": "residential", "delta": 0.1},
            "max_decrease": {"class": "forest", "delta": -0.1},
        },
        risks={
            "flood": {"score": 0.5, "level": "MEDIUM"},
            "earthquake": {"score": 0.3, "level": "MEDIUM"},
            "landslide": {"score": 0.1, "level": "LOW"},
        },
    )
    assert "都市計画" in prompt
    assert "土地利用分布" in prompt
    assert "residential" in prompt
    assert "変化検出" in prompt
    assert "災害リスク" in prompt


def _converse_response(text: str) -> dict:
    """Bedrock Converse API レスポンス形式のモックを生成する。"""
    return {"output": {"message": {"content": [{"text": text}]}}}


def test_invoke_bedrock_nova_format(report_generation_handler):
    mock_bedrock = MagicMock()
    mock_bedrock.converse.return_value = _converse_response("Generated report text")
    result = report_generation_handler.invoke_bedrock(mock_bedrock, "apac.amazon.nova-lite-v1:0", "test prompt", 1024)
    assert result == "Generated report text"


def test_invoke_bedrock_claude_via_converse(report_generation_handler):
    # Converse is model-agnostic; a Claude inference-profile id returns the same shape.
    mock_bedrock = MagicMock()
    mock_bedrock.converse.return_value = _converse_response("Claude response")
    result = report_generation_handler.invoke_bedrock(
        mock_bedrock, "apac.anthropic.claude-haiku-4-5-20251001-v1:0", "test prompt", 1024
    )
    assert result == "Claude response"


def test_invoke_bedrock_error(report_generation_handler):
    mock_bedrock = MagicMock()
    mock_bedrock.converse.side_effect = Exception("Bedrock error")
    result = report_generation_handler.invoke_bedrock(mock_bedrock, "apac.amazon.nova-lite-v1:0", "test", 1024)
    assert "failed" in result.lower()


def test_handler_generates_report(report_generation_handler, lambda_context, monkeypatch):
    monkeypatch.setenv("OUTPUT_BUCKET", "test-bucket")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")

    mock_bedrock = MagicMock()
    mock_bedrock.converse.return_value = _converse_response("都市計画レポート")

    def boto3_client(service):
        if service == "bedrock-runtime":
            return mock_bedrock
        return MagicMock()

    mock_writer = MagicMock()

    with (
        patch.object(report_generation_handler, "boto3") as mock_boto3,
        patch.object(report_generation_handler, "OutputWriter") as mock_output_writer_cls,
    ):
        mock_boto3.client.side_effect = boto3_client
        mock_output_writer_cls.from_env.return_value = mock_writer
        event = {
            "source_key": "gis/area.tif",
            "landuse_distribution": {"residential": 0.5},
            "change_magnitude": 0.1,
            "risks": {"flood": {"score": 0.5, "level": "MEDIUM"}},
        }
        result = report_generation_handler.handler(event, lambda_context)

    assert "都市計画レポート" in result["report_text"]
    mock_writer.put_text.assert_called_once()
