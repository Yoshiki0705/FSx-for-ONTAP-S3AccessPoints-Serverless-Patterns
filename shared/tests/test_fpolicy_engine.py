"""FPolicy Engine ユニットテスト.

正常系 + 異常系のテストケース。moto で SQS/CloudWatch をモック。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.lambdas.fpolicy_engine.handler import (
    SchemaValidationError,
    SqsIngestionError,
    handler,
    send_to_sqs_with_retry,
    validate_fpolicy_event,
)


SCHEMA_PATH = str(
    Path(__file__).parent.parent / "schemas" / "fpolicy-event-schema.json"
)


def _valid_event() -> dict:
    """テスト用の有効な FPolicy イベントを生成."""
    return {
        "event_id": "12345678-1234-4123-8123-123456789abc",
        "operation_type": "create",
        "file_path": "/vol1/products/image001.jpg",
        "volume_name": "vol1",
        "svm_name": "svm-prod",
        "timestamp": "2026-05-13T10:30:00+09:00",
        "file_size": 2048576,
    }


class TestValidateFpolicyEvent:
    """validate_fpolicy_event のテスト."""

    def test_valid_event_passes(self) -> None:
        """有効なイベントはバリデーション通過."""
        event = _valid_event()
        assert validate_fpolicy_event(event) is True

    def test_valid_rename_event_passes(self) -> None:
        """rename イベント（previous_path 付き）はバリデーション通過."""
        event = _valid_event()
        event["operation_type"] = "rename"
        event["previous_path"] = "/vol1/products/old_name.jpg"
        assert validate_fpolicy_event(event) is True

    def test_missing_event_id_fails(self) -> None:
        """event_id 欠落でバリデーション失敗."""
        event = _valid_event()
        del event["event_id"]
        with pytest.raises(SchemaValidationError) as exc_info:
            validate_fpolicy_event(event)
        assert len(exc_info.value.errors) > 0

    def test_invalid_operation_type_fails(self) -> None:
        """無効な operation_type でバリデーション失敗."""
        event = _valid_event()
        event["operation_type"] = "copy"
        with pytest.raises(SchemaValidationError):
            validate_fpolicy_event(event)

    def test_empty_file_path_fails(self) -> None:
        """空の file_path でバリデーション失敗."""
        event = _valid_event()
        event["file_path"] = ""
        with pytest.raises(SchemaValidationError):
            validate_fpolicy_event(event)


class TestSendToSqsWithRetry:
    """send_to_sqs_with_retry のテスト."""

    @mock_aws
    def test_successful_send(self) -> None:
        """正常送信成功."""
        sqs = boto3.client("sqs", region_name="ap-northeast-1")
        queue = sqs.create_queue(QueueName="test-queue")
        queue_url = queue["QueueUrl"]

        message_id = send_to_sqs_with_retry(
            queue_url=queue_url,
            message_body='{"test": "data"}',
            sqs_client=sqs,
        )
        assert message_id is not None
        assert len(message_id) > 0

    def test_all_retries_fail(self) -> None:
        """全リトライ失敗で SqsIngestionError."""
        mock_sqs = MagicMock()
        mock_sqs.send_message.side_effect = Exception("Connection error")

        with pytest.raises(SqsIngestionError) as exc_info:
            send_to_sqs_with_retry(
                queue_url="https://sqs.ap-northeast-1.amazonaws.com/123/test",
                message_body='{"test": "data"}',
                max_retries=3,
                base_delay=0.01,  # Fast retries for test
                sqs_client=mock_sqs,
            )

        assert "All 3 SQS send attempts failed" in str(exc_info.value)
        assert mock_sqs.send_message.call_count == 3

    def test_retry_succeeds_on_second_attempt(self) -> None:
        """2 回目のリトライで成功."""
        mock_sqs = MagicMock()
        mock_sqs.send_message.side_effect = [
            Exception("Temporary error"),
            {"MessageId": "msg-123"},
        ]

        message_id = send_to_sqs_with_retry(
            queue_url="https://sqs.ap-northeast-1.amazonaws.com/123/test",
            message_body='{"test": "data"}',
            max_retries=3,
            base_delay=0.01,
            sqs_client=mock_sqs,
        )

        assert message_id == "msg-123"
        assert mock_sqs.send_message.call_count == 2


class TestHandler:
    """handler 関数の統合テスト."""

    @mock_aws
    def test_handler_success(self) -> None:
        """正常系: 有効イベント → SQS 送信成功."""
        sqs = boto3.client("sqs", region_name="ap-northeast-1")
        queue = sqs.create_queue(QueueName="ingestion-queue")
        queue_url = queue["QueueUrl"]

        os.environ["SQS_QUEUE_URL"] = queue_url
        os.environ["SCHEMA_PATH"] = SCHEMA_PATH

        try:
            event = _valid_event()
            result = handler(event, None)

            assert result["statusCode"] == 200
            assert result["body"]["processed"] == 1
            assert result["body"]["results"][0]["status"] == "success"
        finally:
            del os.environ["SQS_QUEUE_URL"]
            if "SCHEMA_PATH" in os.environ:
                del os.environ["SCHEMA_PATH"]

    @mock_aws
    def test_handler_validation_failure(self) -> None:
        """異常系: バリデーション失敗."""
        sqs = boto3.client("sqs", region_name="ap-northeast-1")
        queue = sqs.create_queue(QueueName="ingestion-queue")
        dlq = sqs.create_queue(QueueName="ingestion-dlq")
        queue_url = queue["QueueUrl"]
        dlq_url = dlq["QueueUrl"]

        os.environ["SQS_QUEUE_URL"] = queue_url
        os.environ["DLQ_URL"] = dlq_url
        os.environ["SCHEMA_PATH"] = SCHEMA_PATH

        try:
            event = {"invalid": "event"}
            result = handler(event, None)

            assert result["statusCode"] == 200
            assert result["body"]["results"][0]["status"] == "validation_failed"
        finally:
            del os.environ["SQS_QUEUE_URL"]
            del os.environ["DLQ_URL"]
            if "SCHEMA_PATH" in os.environ:
                del os.environ["SCHEMA_PATH"]

    @mock_aws
    def test_handler_batch_events(self) -> None:
        """バッチイベント処理."""
        sqs = boto3.client("sqs", region_name="ap-northeast-1")
        queue = sqs.create_queue(QueueName="ingestion-queue")
        queue_url = queue["QueueUrl"]

        os.environ["SQS_QUEUE_URL"] = queue_url
        os.environ["SCHEMA_PATH"] = SCHEMA_PATH

        try:
            event1 = _valid_event()
            event2 = _valid_event()
            event2["event_id"] = "22345678-1234-4123-8123-123456789abc"
            event2["file_path"] = "/vol1/products/image002.jpg"

            batch_event = {"events": [event1, event2]}
            result = handler(batch_event, None)

            assert result["statusCode"] == 200
            assert result["body"]["processed"] == 2
            assert all(
                r["status"] == "success" for r in result["body"]["results"]
            )
        finally:
            del os.environ["SQS_QUEUE_URL"]
            if "SCHEMA_PATH" in os.environ:
                del os.environ["SCHEMA_PATH"]
