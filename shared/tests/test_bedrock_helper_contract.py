"""shared.bedrock_helper — Converse API contract tests (offline, no network).

These complement test_bedrock_helper.py (which injects a MagicMock and therefore
cannot catch a wrong Converse *parameter name*). Here we drive a real
bedrock-runtime client through botocore's Stubber, which validates the request
parameters against the actual service model and shapes the response like the real
API. A typo such as ``modelId`` -> ``modelID`` or ``inferenceConfig`` -> a wrong
key would raise ParamValidationError.

This is the closest we can prove the Converse request/response contract without a
live AWS call. For a true end-to-end invoke against Bedrock, see the opt-in
scripts/bedrock_inference_profile_smoke.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

import boto3
import pytest
from botocore.stub import Stubber

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.bedrock_helper import converse_text  # noqa: E402

PROFILE_ID = "apac.amazon.nova-lite-v1:0"


@pytest.fixture
def bedrock_client():
    return boto3.client(
        "bedrock-runtime",
        region_name="ap-northeast-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )


def _converse_response(text: str) -> dict:
    return {
        "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
        "stopReason": "end_turn",
        "usage": {"inputTokens": 10, "outputTokens": 5, "totalTokens": 15},
        "metrics": {"latencyMs": 123},
    }


def test_converse_request_conforms_to_service_model(bedrock_client):
    """converse_text builds a request that passes botocore param validation."""
    stubber = Stubber(bedrock_client)
    expected_params = {
        "modelId": PROFILE_ID,
        "messages": [{"role": "user", "content": [{"text": "要約してください"}]}],
        "inferenceConfig": {"maxTokens": 2048, "temperature": 0.3},
    }
    stubber.add_response("converse", _converse_response("要約結果です"), expected_params)
    with stubber:
        result = converse_text(PROFILE_ID, prompt="要約してください", client=bedrock_client)
    assert result == "要約結果です"
    stubber.assert_no_pending_responses()


def test_converse_request_with_system_and_guardrail(bedrock_client):
    """system + guardrailConfig are valid Converse parameters."""
    stubber = Stubber(bedrock_client)
    expected_params = {
        "modelId": PROFILE_ID,
        "messages": [{"role": "user", "content": [{"text": "p"}]}],
        "inferenceConfig": {"maxTokens": 1024, "temperature": 0.1},
        "system": [{"text": "you are an analyst"}],
        "guardrailConfig": {"guardrailIdentifier": "gr-1", "guardrailVersion": "DRAFT"},
    }
    stubber.add_response("converse", _converse_response("ok"), expected_params)
    with stubber:
        result = converse_text(
            PROFILE_ID,
            prompt="p",
            system="you are an analyst",
            guardrail_id="gr-1",
            max_tokens=1024,
            temperature=0.1,
            client=bedrock_client,
        )
    assert result == "ok"
    stubber.assert_no_pending_responses()


def test_converse_parses_multiple_text_blocks(bedrock_client):
    """Multi-block Converse output is concatenated (real response shape)."""
    stubber = Stubber(bedrock_client)
    resp = {
        "output": {"message": {"role": "assistant", "content": [{"text": "a"}, {"text": "b"}]}},
        "stopReason": "max_tokens",
        "usage": {"inputTokens": 1, "outputTokens": 2, "totalTokens": 3},
        "metrics": {"latencyMs": 1},
    }
    stubber.add_response(
        "converse",
        resp,
        {
            "modelId": PROFILE_ID,
            "messages": [{"role": "user", "content": [{"text": "p"}]}],
            "inferenceConfig": {"maxTokens": 2048, "temperature": 0.3},
        },
    )
    with stubber:
        assert converse_text(PROFILE_ID, prompt="p", client=bedrock_client) == "a\nb"
