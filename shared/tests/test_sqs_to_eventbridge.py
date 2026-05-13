"""SQS → EventBridge Bridge プロパティテスト + ユニットテスト.

Property 7: SQS → EventBridge イベント変換の完全性
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.lambdas.sqs_to_eventbridge.handler import handler


# --- Hypothesis Strategies ---

uuid_strategy = st.from_regex(
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
    fullmatch=True,
)

operation_type_strategy = st.sampled_from(["create", "write", "delete", "rename"])

file_path_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), min_codepoint=65, max_codepoint=122),
    min_size=1,
    max_size=50,
).map(lambda s: f"/vol1/{s}")


@st.composite
def valid_fpolicy_event(draw: st.DrawFn) -> dict:
    """有効な FPolicy Event を生成."""
    op_type = draw(operation_type_strategy)
    event = {
        "event_id": draw(uuid_strategy),
        "operation_type": op_type,
        "file_path": draw(file_path_strategy),
        "volume_name": draw(st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz0123456789")),
        "svm_name": draw(st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz0123456789")),
        "timestamp": "2026-05-13T10:30:00+09:00",
        "file_size": draw(st.integers(min_value=0, max_value=1000000)),
    }
    if op_type == "rename":
        event["previous_path"] = draw(file_path_strategy)
    return event


def _make_sqs_event(fpolicy_events: list[dict]) -> dict:
    """SQS バッチイベントを構築."""
    records = []
    for i, evt in enumerate(fpolicy_events):
        records.append(
            {
                "messageId": f"msg-{i:04d}",
                "body": json.dumps(evt, ensure_ascii=False),
                "receiptHandle": f"handle-{i}",
                "attributes": {},
                "messageAttributes": {},
                "md5OfBody": "",
                "eventSource": "aws:sqs",
                "eventSourceARN": "arn:aws:sqs:ap-northeast-1:123456789012:test-queue",
                "awsRegion": "ap-northeast-1",
            }
        )
    return {"Records": records}


class TestSqsToEventBridgeProperty:
    """Property 7: SQS → EventBridge イベント変換の完全性."""

    @settings(max_examples=100)
    @given(event=valid_fpolicy_event())
    def test_event_detail_preserves_all_fields(self, event: dict) -> None:
        """Feature: fsxn-s3ap-serverless-patterns-phase10, Property 7: イベント変換完全性.

        有効な FPolicy Event を含む SQS メッセージの detail フィールドが
        全フィールドを保持することを検証。
        """
        sqs_event = _make_sqs_event([event])

        captured_entries: list[dict] = []

        mock_eb = MagicMock()
        mock_eb.put_events.return_value = {"Entries": [{"EventId": "evt-1"}]}

        mock_cw = MagicMock()

        with patch("shared.lambdas.sqs_to_eventbridge.handler.boto3") as mock_boto3:
            mock_boto3.client.side_effect = lambda service, **kwargs: (
                mock_eb if service == "events" else mock_cw
            )

            os.environ["EVENT_BUS_NAME"] = "test-bus"
            try:
                result = handler(sqs_event, None)
            finally:
                del os.environ["EVENT_BUS_NAME"]

        # Verify no failures
        assert result["batchItemFailures"] == []

        # Verify the detail field preserves all original fields
        call_args = mock_eb.put_events.call_args
        entries = call_args[1]["Entries"] if "Entries" in (call_args[1] or {}) else call_args[0][0] if call_args[0] else call_args[1].get("Entries", [])

        # Get entries from kwargs
        if call_args.kwargs:
            entries = call_args.kwargs.get("Entries", [])
        else:
            entries = call_args[1].get("Entries", []) if len(call_args) > 1 else []

        # Fallback: check the actual call
        actual_call = mock_eb.put_events.call_args_list[0]
        if actual_call.kwargs:
            entries = actual_call.kwargs.get("Entries", [])
        elif actual_call.args:
            entries = actual_call.args[0] if isinstance(actual_call.args[0], list) else []

        assert len(entries) == 1
        detail = json.loads(entries[0]["Detail"])

        # All original fields must be preserved
        for key, value in event.items():
            assert key in detail, f"Field '{key}' missing from EventBridge detail"
            assert detail[key] == value, f"Field '{key}' value mismatch"


class TestSqsToEventBridgeUnit:
    """SQS → EventBridge Bridge ユニットテスト."""

    def test_empty_records(self) -> None:
        """空の Records リストを処理."""
        mock_eb = MagicMock()
        mock_cw = MagicMock()

        with patch("shared.lambdas.sqs_to_eventbridge.handler.boto3") as mock_boto3:
            mock_boto3.client.side_effect = lambda service, **kwargs: (
                mock_eb if service == "events" else mock_cw
            )

            os.environ["EVENT_BUS_NAME"] = "test-bus"
            try:
                result = handler({"Records": []}, None)
            finally:
                del os.environ["EVENT_BUS_NAME"]

        assert result["batchItemFailures"] == []
        mock_eb.put_events.assert_not_called()

    def test_invalid_json_body_returns_failure(self) -> None:
        """不正な JSON ボディは batchItemFailures に含まれる."""
        sqs_event = {
            "Records": [
                {
                    "messageId": "msg-001",
                    "body": "not-valid-json{{{",
                    "receiptHandle": "handle-1",
                }
            ]
        }

        mock_eb = MagicMock()
        mock_cw = MagicMock()

        with patch("shared.lambdas.sqs_to_eventbridge.handler.boto3") as mock_boto3:
            mock_boto3.client.side_effect = lambda service, **kwargs: (
                mock_eb if service == "events" else mock_cw
            )

            os.environ["EVENT_BUS_NAME"] = "test-bus"
            try:
                result = handler(sqs_event, None)
            finally:
                del os.environ["EVENT_BUS_NAME"]

        assert len(result["batchItemFailures"]) == 1
        assert result["batchItemFailures"][0]["itemIdentifier"] == "msg-001"

    def test_eventbridge_put_events_failure(self) -> None:
        """EventBridge PutEvents 失敗時に batchItemFailures を返す."""
        event = {
            "event_id": "12345678-1234-4123-8123-123456789abc",
            "operation_type": "create",
            "file_path": "/vol1/test.txt",
        }
        sqs_event = _make_sqs_event([event])

        mock_eb = MagicMock()
        mock_eb.put_events.side_effect = Exception("Service unavailable")
        mock_cw = MagicMock()

        with patch("shared.lambdas.sqs_to_eventbridge.handler.boto3") as mock_boto3:
            mock_boto3.client.side_effect = lambda service, **kwargs: (
                mock_eb if service == "events" else mock_cw
            )

            os.environ["EVENT_BUS_NAME"] = "test-bus"
            try:
                result = handler(sqs_event, None)
            finally:
                del os.environ["EVENT_BUS_NAME"]

        assert len(result["batchItemFailures"]) == 1
