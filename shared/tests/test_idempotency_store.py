"""Idempotency Store ユニットテスト.

Property 4: 冪等性ストアの重複検出
DynamoDB ベースの冪等性ストアの動作を検証する。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

TABLE_NAME = "fsxn-fpolicy-idempotency-test"


def _create_table(dynamodb_client):
    """テスト用 DynamoDB テーブルを作成."""
    dynamodb_client.create_table(
        TableName=TABLE_NAME,
        KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    # Enable TTL
    dynamodb_client.update_time_to_live(
        TableName=TABLE_NAME,
        TimeToLiveSpecification={"Enabled": True, "AttributeName": "ttl"},
    )


def _check_duplicate(dynamodb_client, file_path: str, event_id: str) -> bool:
    """重複チェック: 既に処理済みなら True を返す."""
    pk = f"{file_path}#{event_id}"
    response = dynamodb_client.get_item(
        TableName=TABLE_NAME,
        Key={"pk": {"S": pk}},
    )
    return "Item" in response


def _record_processed(
    dynamodb_client,
    file_path: str,
    event_id: str,
    operation_type: str,
    execution_arn: str = "",
    ttl_seconds: int = 86400,
) -> None:
    """処理済みイベントを記録する."""
    pk = f"{file_path}#{event_id}"
    ttl_value = int(time.time()) + ttl_seconds

    dynamodb_client.put_item(
        TableName=TABLE_NAME,
        Item={
            "pk": {"S": pk},
            "ttl": {"N": str(ttl_value)},
            "operation_type": {"S": operation_type},
            "processed_at": {"S": time.strftime("%Y-%m-%dT%H:%M:%S+00:00")},
            "execution_arn": {"S": execution_arn},
        },
    )


class TestIdempotencyStoreUnit:
    """Idempotency Store ユニットテスト."""

    @mock_aws
    def test_new_event_not_duplicate(self) -> None:
        """新規イベントは重複ではない."""
        client = boto3.client("dynamodb", region_name="ap-northeast-1")
        _create_table(client)

        is_dup = _check_duplicate(
            client, "/vol1/test.txt", "event-001"
        )
        assert is_dup is False

    @mock_aws
    def test_recorded_event_is_duplicate(self) -> None:
        """記録済みイベントは重複として検出される."""
        client = boto3.client("dynamodb", region_name="ap-northeast-1")
        _create_table(client)

        # Record the event
        _record_processed(
            client,
            "/vol1/test.txt",
            "event-001",
            "create",
            "arn:aws:states:ap-northeast-1:123:execution:test:run1",
        )

        # Check duplicate
        is_dup = _check_duplicate(
            client, "/vol1/test.txt", "event-001"
        )
        assert is_dup is True

    @mock_aws
    def test_different_event_id_not_duplicate(self) -> None:
        """同一ファイルでも異なる event_id は重複ではない."""
        client = boto3.client("dynamodb", region_name="ap-northeast-1")
        _create_table(client)

        _record_processed(
            client, "/vol1/test.txt", "event-001", "create"
        )

        is_dup = _check_duplicate(
            client, "/vol1/test.txt", "event-002"
        )
        assert is_dup is False

    @mock_aws
    def test_different_file_path_not_duplicate(self) -> None:
        """異なるファイルパスは重複ではない."""
        client = boto3.client("dynamodb", region_name="ap-northeast-1")
        _create_table(client)

        _record_processed(
            client, "/vol1/file-a.txt", "event-001", "create"
        )

        is_dup = _check_duplicate(
            client, "/vol1/file-b.txt", "event-001"
        )
        assert is_dup is False

    @mock_aws
    def test_ttl_attribute_set_correctly(self) -> None:
        """TTL 属性が正しく設定される."""
        client = boto3.client("dynamodb", region_name="ap-northeast-1")
        _create_table(client)

        before = int(time.time())
        _record_processed(
            client, "/vol1/test.txt", "event-001", "write", ttl_seconds=86400
        )
        after = int(time.time())

        # Retrieve and check TTL
        response = client.get_item(
            TableName=TABLE_NAME,
            Key={"pk": {"S": "/vol1/test.txt#event-001"}},
        )
        ttl_value = int(response["Item"]["ttl"]["N"])

        # TTL should be ~24 hours from now
        assert ttl_value >= before + 86400
        assert ttl_value <= after + 86400

    @mock_aws
    def test_operation_type_stored(self) -> None:
        """operation_type が正しく保存される."""
        client = boto3.client("dynamodb", region_name="ap-northeast-1")
        _create_table(client)

        _record_processed(
            client, "/vol1/test.txt", "event-001", "rename"
        )

        response = client.get_item(
            TableName=TABLE_NAME,
            Key={"pk": {"S": "/vol1/test.txt#event-001"}},
        )
        assert response["Item"]["operation_type"]["S"] == "rename"

    @mock_aws
    def test_multiple_events_independent(self) -> None:
        """複数イベントが独立して管理される."""
        client = boto3.client("dynamodb", region_name="ap-northeast-1")
        _create_table(client)

        # Record 3 events
        events = [
            ("/vol1/a.txt", "ev-1", "create"),
            ("/vol1/b.txt", "ev-2", "write"),
            ("/vol1/c.txt", "ev-3", "delete"),
        ]
        for fp, eid, op in events:
            _record_processed(client, fp, eid, op)

        # All should be detected as duplicates
        for fp, eid, _ in events:
            assert _check_duplicate(client, fp, eid) is True

        # New event should not be duplicate
        assert _check_duplicate(client, "/vol1/d.txt", "ev-4") is False
