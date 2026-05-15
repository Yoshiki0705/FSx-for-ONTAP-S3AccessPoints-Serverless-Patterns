"""Idempotency Checker テスト.

HYBRID モードの重複排除ロジックを検証する。
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import boto3
import pytest
from moto import mock_aws

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.idempotency_checker import handler, _bucket_timestamp


@pytest.fixture
def dynamodb_table():
    """Create a mock DynamoDB table for testing."""
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-1")
        table = dynamodb.create_table(
            TableName="fsxn-s3ap-idempotency-store",
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        table.meta.client.get_waiter("table_exists").wait(
            TableName="fsxn-s3ap-idempotency-store"
        )
        yield table


class TestBucketTimestamp:
    """_bucket_timestamp のテスト."""

    def test_5min_bucket(self):
        assert _bucket_timestamp("2026-05-14T10:33:45Z", 5) == "2026-05-14T10:30"

    def test_5min_bucket_exact(self):
        assert _bucket_timestamp("2026-05-14T10:30:00Z", 5) == "2026-05-14T10:30"

    def test_5min_bucket_end(self):
        assert _bucket_timestamp("2026-05-14T10:34:59Z", 5) == "2026-05-14T10:30"

    def test_10min_bucket(self):
        assert _bucket_timestamp("2026-05-14T10:47:00Z", 10) == "2026-05-14T10:40"

    def test_empty_timestamp(self):
        result = _bucket_timestamp("", 5)
        assert "T" in result  # Should return current time bucket

    def test_no_timezone(self):
        assert _bucket_timestamp("2026-05-14T10:33:45", 5) == "2026-05-14T10:30"


class TestIdempotencyHandler:
    """handler 関数のテスト."""

    @mock_aws
    def test_new_event_not_duplicate(self):
        """新規イベントは重複ではない."""
        # Setup
        dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-1")
        dynamodb.create_table(
            TableName="fsxn-s3ap-idempotency-store",
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        os.environ["USE_CASE"] = "legal-compliance"
        os.environ["IDEMPOTENCY_TABLE"] = "fsxn-s3ap-idempotency-store"
        os.environ["AWS_DEFAULT_REGION"] = "ap-northeast-1"

        try:
            # Patch module-level USE_CASE
            import shared.idempotency_checker as ic
            ic.USE_CASE = "legal-compliance"

            event = {
                "file_path": "/vol1/legal/contract.pdf",
                "operation_type": "create",
                "timestamp": "2026-05-14T10:30:00Z",
            }
            result = handler(event, None)

            assert result["is_duplicate"] is False
            assert "legal-compliance#/vol1/legal/contract.pdf" in result["idempotency_key"]
        finally:
            del os.environ["USE_CASE"]
            del os.environ["IDEMPOTENCY_TABLE"]

    @mock_aws
    def test_duplicate_event_detected(self):
        """同一イベントの 2 回目は重複として検出される."""
        dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-1")
        dynamodb.create_table(
            TableName="fsxn-s3ap-idempotency-store",
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        os.environ["USE_CASE"] = "legal-compliance"
        os.environ["IDEMPOTENCY_TABLE"] = "fsxn-s3ap-idempotency-store"
        os.environ["AWS_DEFAULT_REGION"] = "ap-northeast-1"

        try:
            event = {
                "file_path": "/vol1/legal/contract.pdf",
                "operation_type": "create",
                "timestamp": "2026-05-14T10:30:00Z",
            }

            # First call — not duplicate
            result1 = handler(event, None)
            assert result1["is_duplicate"] is False

            # Second call — duplicate
            result2 = handler(event, None)
            assert result2["is_duplicate"] is True
        finally:
            del os.environ["USE_CASE"]
            del os.environ["IDEMPOTENCY_TABLE"]

    @mock_aws
    def test_different_operations_not_duplicate(self):
        """同一ファイルでも異なる操作は重複ではない."""
        dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-1")
        dynamodb.create_table(
            TableName="fsxn-s3ap-idempotency-store",
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        os.environ["USE_CASE"] = "legal-compliance"
        os.environ["IDEMPOTENCY_TABLE"] = "fsxn-s3ap-idempotency-store"
        os.environ["AWS_DEFAULT_REGION"] = "ap-northeast-1"

        try:
            event_create = {
                "file_path": "/vol1/legal/contract.pdf",
                "operation_type": "create",
                "timestamp": "2026-05-14T10:30:00Z",
            }
            event_delete = {
                "file_path": "/vol1/legal/contract.pdf",
                "operation_type": "delete",
                "timestamp": "2026-05-14T10:30:00Z",
            }

            result1 = handler(event_create, None)
            assert result1["is_duplicate"] is False

            result2 = handler(event_delete, None)
            assert result2["is_duplicate"] is False
        finally:
            del os.environ["USE_CASE"]
            del os.environ["IDEMPOTENCY_TABLE"]

    def test_empty_file_path(self):
        """file_path が空の場合は重複チェックをスキップ."""
        event = {"file_path": "", "operation_type": "create"}
        result = handler(event, None)
        assert result["is_duplicate"] is False
