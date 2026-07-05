"""shared.bedrock_helper ユニットテスト

Converse ラッパーのリクエスト組み立て、レスポンス抽出、JSON 抽出、
推論プロファイル判定を検証する。moto は converse 未対応のため、
bedrock-runtime クライアントは直接 MagicMock で注入する。
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.bedrock_helper import (
    converse_text,
    extract_json,
    is_inference_profile_id,
)


def _mock_client(text: str = "hello") -> MagicMock:
    client = MagicMock()
    client.converse.return_value = {"output": {"message": {"role": "assistant", "content": [{"text": text}]}}}
    return client


class TestConverseText:
    def test_prompt_builds_messages_and_returns_text(self):
        client = _mock_client("生成結果")
        result = converse_text("apac.amazon.nova-lite-v1:0", prompt="要約して", client=client)
        assert result == "生成結果"
        kwargs = client.converse.call_args.kwargs
        assert kwargs["modelId"] == "apac.amazon.nova-lite-v1:0"
        assert kwargs["messages"] == [{"role": "user", "content": [{"text": "要約して"}]}]
        assert kwargs["inferenceConfig"] == {"maxTokens": 2048, "temperature": 0.3}
        assert "system" not in kwargs
        assert "guardrailConfig" not in kwargs

    def test_system_and_guardrail_included_when_provided(self):
        client = _mock_client()
        converse_text(
            "apac.amazon.nova-pro-v1:0",
            prompt="p",
            system="あなたは物流アナリストです。",
            guardrail_id="gr-123",
            guardrail_version="1",
            max_tokens=1024,
            temperature=0.1,
            client=client,
        )
        kwargs = client.converse.call_args.kwargs
        assert kwargs["system"] == [{"text": "あなたは物流アナリストです。"}]
        assert kwargs["guardrailConfig"] == {
            "guardrailIdentifier": "gr-123",
            "guardrailVersion": "1",
        }
        assert kwargs["inferenceConfig"] == {"maxTokens": 1024, "temperature": 0.1}

    def test_explicit_messages_take_precedence(self):
        client = _mock_client()
        msgs = [{"role": "user", "content": [{"text": "a"}, {"text": "b"}]}]
        converse_text("apac.amazon.nova-lite-v1:0", messages=msgs, client=client)
        assert client.converse.call_args.kwargs["messages"] == msgs

    def test_missing_prompt_and_messages_raises(self):
        with pytest.raises(ValueError):
            converse_text("apac.amazon.nova-lite-v1:0", client=_mock_client())

    def test_multiple_text_blocks_concatenated(self):
        client = MagicMock()
        client.converse.return_value = {"output": {"message": {"content": [{"text": "part1"}, {"text": "part2"}]}}}
        assert converse_text("m", prompt="p", client=client) == "part1\npart2"

    def test_empty_content_returns_empty_string(self):
        client = MagicMock()
        client.converse.return_value = {"output": {"message": {"content": []}}}
        assert converse_text("m", prompt="p", client=client) == ""


class TestExtractJson:
    def test_plain_json(self):
        assert extract_json('{"a": 1}') == {"a": 1}

    def test_json_code_fence(self):
        assert extract_json('```json\n{"a": 2}\n```') == {"a": 2}

    def test_generic_code_fence(self):
        assert extract_json('```\n{"a": 3}\n```') == {"a": 3}

    def test_invalid_returns_empty(self):
        assert extract_json("This is not JSON") == {}

    def test_non_object_json_returns_empty(self):
        assert extract_json("[1, 2, 3]") == {}


class TestIsInferenceProfileId:
    @pytest.mark.parametrize(
        "model_id",
        [
            "apac.amazon.nova-lite-v1:0",
            "us.amazon.nova-pro-v1:0",
            "eu.anthropic.claude-haiku-4-5-20251001-v1:0",
            "jp.anthropic.claude-haiku-4-5-20251001-v1:0",
            "global.anthropic.claude-haiku-4-5-20251001-v1:0",
            "arn:aws:bedrock:ap-northeast-1:123456789012:inference-profile/apac.amazon.nova-lite-v1:0",
        ],
    )
    def test_profile_ids(self, model_id):
        assert is_inference_profile_id(model_id) is True

    @pytest.mark.parametrize(
        "model_id",
        [
            "amazon.nova-lite-v1:0",
            "anthropic.claude-haiku-4-5-20251001-v1:0",
            "amazon.titan-embed-text-v2:0",
        ],
    )
    def test_bare_ids(self, model_id):
        assert is_inference_profile_id(model_id) is False
