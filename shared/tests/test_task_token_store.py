"""Unit Tests for TaskTokenStore class — Phase 4

DynamoDB ベース Task Token ストレージの単体テスト。
moto を使用して DynamoDB をモックし、各メソッドの動作を検証する。

Coverage target: 80%+
"""

from __future__ import annotations

import re
import time
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

from shared.exceptions import TokenStorageError
from shared.task_token_store import TaskTokenStore


# ---------------------------------------------------------------------------
# Fixtures / Helpers
# ---------------------------------------------------------------------------

TABLE_NAME = "test-task-token-store"
REGION = "ap-northeast-1"


def _create_token_table(dynamodb_resource):
    """Create the Task Token Store DynamoDB table for testing.

    Schema:
    - PK: correlation_id (String)
    - GSI: TransformJobNameIndex on transform_job_name (String)
    - TTL: ttl attribute
    """
    table = dynamodb_resource.create_table(
        TableName=TABLE_NAME,
        KeySchema=[
            {"AttributeName": "correlation_id", "KeyType": "HASH"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "correlation_id", "AttributeType": "S"},
            {"AttributeName": "transform_job_name", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "TransformJobNameIndex",
                "KeySchema": [
                    {"AttributeName": "transform_job_name", "KeyType": "HASH"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    table.meta.client.update_time_to_live(
        TableName=TABLE_NAME,
        TimeToLiveSpecification={
            "Enabled": True,
            "AttributeName": "ttl",
        },
    )
    return table


@pytest.fixture
def dynamodb_table():
    """Fixture: moto DynamoDB テーブルを作成して返す"""
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name=REGION)
        _create_token_table(dynamodb)
        yield dynamodb


# ---------------------------------------------------------------------------
# Tests: generate_correlation_id
# ---------------------------------------------------------------------------


class TestGenerateCorrelationId:
    """generate_correlation_id() のテスト"""

    def test_returns_8_char_hex(self):
        """8 文字の hex 文字列を返す"""
        cid = TaskTokenStore.generate_correlation_id()
        assert len(cid) == 8
        assert re.match(r"^[0-9a-f]{8}$", cid)

    def test_returns_different_values(self):
        """複数回呼び出すと異なる値を返す（確率的）"""
        ids = {TaskTokenStore.generate_correlation_id() for _ in range(100)}
        # 100 回生成して少なくとも 90 個はユニークであるべき
        assert len(ids) >= 90


# ---------------------------------------------------------------------------
# Tests: store_token
# ---------------------------------------------------------------------------


class TestStoreToken:
    """store_token() のテスト"""

    def test_stores_and_returns_correlation_id(self, dynamodb_table):
        """Token を保存し、correlation_id を返す"""
        store = TaskTokenStore(table_name=TABLE_NAME, ttl_seconds=86400)

        cid = store.store_token(
            task_token="my-task-token-abc123",
            transform_job_name="test-job-001",
        )

        assert len(cid) == 8
        assert re.match(r"^[0-9a-f]{8}$", cid)

    def test_stores_correct_item_in_dynamodb(self, dynamodb_table):
        """DynamoDB に正しいアイテムが保存される"""
        store = TaskTokenStore(table_name=TABLE_NAME, ttl_seconds=3600)

        before = int(time.time())
        cid = store.store_token(
            task_token="token-value-xyz",
            transform_job_name="job-name-abc",
        )
        after = int(time.time())

        # DynamoDB から直接読み取り
        table = dynamodb_table.Table(TABLE_NAME)
        response = table.get_item(Key={"correlation_id": cid})
        item = response["Item"]

        assert item["correlation_id"] == cid
        assert item["task_token"] == "token-value-xyz"
        assert item["transform_job_name"] == "job-name-abc"
        assert before <= int(item["created_at"]) <= after
        assert int(item["ttl"]) == int(item["created_at"]) + 3600


# ---------------------------------------------------------------------------
# Tests: retrieve_token
# ---------------------------------------------------------------------------


class TestRetrieveToken:
    """retrieve_token() のテスト"""

    def test_retrieves_stored_token(self, dynamodb_table):
        """保存した Token を正しく取得する"""
        store = TaskTokenStore(table_name=TABLE_NAME, ttl_seconds=86400)

        cid = store.store_token(
            task_token="retrieve-me-token",
            transform_job_name="retrieve-job",
        )

        result = store.retrieve_token(cid)
        assert result == "retrieve-me-token"

    def test_returns_none_for_nonexistent_id(self, dynamodb_table):
        """存在しない correlation_id に対して None を返す"""
        store = TaskTokenStore(table_name=TABLE_NAME, ttl_seconds=86400)

        result = store.retrieve_token("deadbeef")
        assert result is None

    def test_returns_none_for_empty_id(self, dynamodb_table):
        """空の correlation_id に対して None を返す"""
        store = TaskTokenStore(table_name=TABLE_NAME, ttl_seconds=86400)

        result = store.retrieve_token("")
        assert result is None


# ---------------------------------------------------------------------------
# Tests: retrieve_token_by_job_name (GSI)
# ---------------------------------------------------------------------------


class TestRetrieveTokenByJobName:
    """retrieve_token_by_job_name() のテスト"""

    def test_retrieves_token_via_gsi(self, dynamodb_table):
        """GSI を使用してジョブ名から Token を取得する"""
        store = TaskTokenStore(table_name=TABLE_NAME, ttl_seconds=86400)

        store.store_token(
            task_token="gsi-token-value",
            transform_job_name="my-transform-job",
        )

        result = store.retrieve_token_by_job_name("my-transform-job")
        assert result == "gsi-token-value"

    def test_returns_none_for_nonexistent_job(self, dynamodb_table):
        """存在しないジョブ名に対して None を返す"""
        store = TaskTokenStore(table_name=TABLE_NAME, ttl_seconds=86400)

        result = store.retrieve_token_by_job_name("nonexistent-job")
        assert result is None


# ---------------------------------------------------------------------------
# Tests: delete_token
# ---------------------------------------------------------------------------


class TestDeleteToken:
    """delete_token() のテスト"""

    def test_deletes_existing_record(self, dynamodb_table):
        """保存済みレコードを削除する"""
        store = TaskTokenStore(table_name=TABLE_NAME, ttl_seconds=86400)

        cid = store.store_token(
            task_token="delete-me-token",
            transform_job_name="delete-job",
        )

        # 削除前は取得可能
        assert store.retrieve_token(cid) == "delete-me-token"

        # 削除
        store.delete_token(cid)

        # 削除後は None
        assert store.retrieve_token(cid) is None

    def test_delete_nonexistent_does_not_raise(self, dynamodb_table):
        """存在しないレコードの削除はエラーにならない"""
        store = TaskTokenStore(table_name=TABLE_NAME, ttl_seconds=86400)

        # Should not raise
        store.delete_token("nonexistent")


# ---------------------------------------------------------------------------
# Tests: Collision retry logic
# ---------------------------------------------------------------------------


class TestCollisionRetry:
    """衝突リトライロジックのテスト"""

    def test_retries_on_collision_and_succeeds(self, dynamodb_table):
        """衝突時にリトライして成功する"""
        store = TaskTokenStore(table_name=TABLE_NAME, ttl_seconds=86400)

        # Pre-insert a record with a known correlation_id
        table = dynamodb_table.Table(TABLE_NAME)
        table.put_item(
            Item={
                "correlation_id": "aaaaaaaa",
                "task_token": "existing-token",
                "transform_job_name": "existing-job",
                "created_at": int(time.time()),
                "ttl": int(time.time()) + 86400,
            }
        )

        # Patch generate_correlation_id to return colliding ID first, then unique
        with patch.object(
            TaskTokenStore, "generate_correlation_id",
            side_effect=["aaaaaaaa", "bbbbbbbb"],
        ):
            cid = store.store_token(
                task_token="new-token",
                transform_job_name="new-job",
            )

            assert cid == "bbbbbbbb"
            assert store.retrieve_token("bbbbbbbb") == "new-token"

    def test_raises_token_storage_error_after_max_retries(self, dynamodb_table):
        """最大リトライ回数超過で TokenStorageError を発生させる"""
        store = TaskTokenStore(table_name=TABLE_NAME, ttl_seconds=86400)

        # Pre-insert records for all collision IDs
        table = dynamodb_table.Table(TABLE_NAME)
        for hex_id in ["aaaaaaaa", "bbbbbbbb", "cccccccc"]:
            table.put_item(
                Item={
                    "correlation_id": hex_id,
                    "task_token": f"existing-{hex_id}",
                    "transform_job_name": f"job-{hex_id}",
                    "created_at": int(time.time()),
                    "ttl": int(time.time()) + 86400,
                }
            )

        # Patch generate_correlation_id to always return colliding IDs
        with patch.object(
            TaskTokenStore, "generate_correlation_id",
            side_effect=["aaaaaaaa", "bbbbbbbb", "cccccccc"],
        ):
            with pytest.raises(TokenStorageError) as exc_info:
                store.store_token(
                    task_token="will-fail-token",
                    transform_job_name="will-fail-job",
                )

            assert exc_info.value.retry_count == 3
            assert "retries" in str(exc_info.value)
