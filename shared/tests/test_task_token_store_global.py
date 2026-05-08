"""Unit Tests for TaskTokenStore Global Tables 拡張 — Phase 5

DynamoDB Global Tables 対応の TaskTokenStore 拡張機能をテストする。
moto を使用して DynamoDB をモックし、region パラメータ、
source_region 属性、後方互換性を検証する。

Validates: Requirements 19.1, 19.2
Coverage target: 80%+
"""

from __future__ import annotations

import os
import time
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

from shared.task_token_store import TaskTokenStore


# ---------------------------------------------------------------------------
# Fixtures / Helpers
# ---------------------------------------------------------------------------

TABLE_NAME = "test-global-task-token-store"
PRIMARY_REGION = "ap-northeast-1"
SECONDARY_REGION = "us-east-1"


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
def dynamodb_primary():
    """Fixture: moto DynamoDB テーブルを Primary リージョンに作成"""
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name=PRIMARY_REGION)
        _create_token_table(dynamodb)
        yield dynamodb


@pytest.fixture
def dynamodb_secondary():
    """Fixture: moto DynamoDB テーブルを Secondary リージョンに作成"""
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name=SECONDARY_REGION)
        _create_token_table(dynamodb)
        yield dynamodb


# ---------------------------------------------------------------------------
# Tests: region パラメータ
# ---------------------------------------------------------------------------


class TestRegionParameter:
    """region パラメータのテスト — Validates: Requirement 19.1"""

    def test_explicit_region_creates_regional_dynamodb_resource(self, dynamodb_secondary):
        """明示的な region パラメータで指定リージョンの DynamoDB リソースを作成する"""
        store = TaskTokenStore(
            table_name=TABLE_NAME,
            ttl_seconds=86400,
            region=SECONDARY_REGION,
        )

        assert store.region == SECONDARY_REGION

        # Token を保存して取得できることを確認
        cid = store.store_token(
            task_token="regional-token-value",
            transform_job_name="regional-job",
        )
        result = store.retrieve_token(cid)
        assert result == "regional-token-value"

    def test_explicit_region_sets_source_region(self, dynamodb_secondary):
        """明示的な region パラメータが source_region 属性に反映される"""
        store = TaskTokenStore(
            table_name=TABLE_NAME,
            ttl_seconds=86400,
            region=SECONDARY_REGION,
        )

        assert store.source_region == SECONDARY_REGION

    def test_primary_region_explicit(self, dynamodb_primary):
        """Primary リージョンを明示的に指定した場合の動作確認"""
        store = TaskTokenStore(
            table_name=TABLE_NAME,
            ttl_seconds=86400,
            region=PRIMARY_REGION,
        )

        assert store.region == PRIMARY_REGION
        assert store.source_region == PRIMARY_REGION

        cid = store.store_token(
            task_token="primary-token",
            transform_job_name="primary-job",
        )
        result = store.retrieve_token(cid)
        assert result == "primary-token"


# ---------------------------------------------------------------------------
# Tests: source_region 属性
# ---------------------------------------------------------------------------


class TestSourceRegionAttribute:
    """source_region 属性のテスト — Validates: Requirement 19.1"""

    def test_source_region_stored_in_dynamodb_record(self, dynamodb_primary):
        """DynamoDB レコードに source_region 属性が保存される"""
        store = TaskTokenStore(
            table_name=TABLE_NAME,
            ttl_seconds=86400,
            region=PRIMARY_REGION,
        )

        cid = store.store_token(
            task_token="source-region-test-token",
            transform_job_name="source-region-job",
        )

        # DynamoDB から直接読み取り
        table = dynamodb_primary.Table(TABLE_NAME)
        response = table.get_item(Key={"correlation_id": cid})
        item = response["Item"]

        assert "source_region" in item
        assert item["source_region"] == PRIMARY_REGION

    def test_source_region_matches_specified_region(self, dynamodb_secondary):
        """source_region が指定した region と一致する"""
        store = TaskTokenStore(
            table_name=TABLE_NAME,
            ttl_seconds=86400,
            region=SECONDARY_REGION,
        )

        cid = store.store_token(
            task_token="secondary-token",
            transform_job_name="secondary-job",
        )

        # DynamoDB から直接読み取り
        table = dynamodb_secondary.Table(TABLE_NAME)
        response = table.get_item(Key={"correlation_id": cid})
        item = response["Item"]

        assert item["source_region"] == SECONDARY_REGION

    def test_source_region_attribute_on_instance(self, dynamodb_primary):
        """TaskTokenStore インスタンスの source_region 属性が正しい"""
        store = TaskTokenStore(
            table_name=TABLE_NAME,
            ttl_seconds=86400,
            region=PRIMARY_REGION,
        )

        assert store.source_region == PRIMARY_REGION


# ---------------------------------------------------------------------------
# Tests: 後方互換性
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """後方互換性のテスト — Validates: Requirement 19.2"""

    def test_no_region_param_uses_aws_region_env_var(self, dynamodb_primary):
        """region パラメータなしの場合、AWS_REGION 環境変数を使用する"""
        with patch.dict("os.environ", {"AWS_REGION": PRIMARY_REGION}):
            store = TaskTokenStore(
                table_name=TABLE_NAME,
                ttl_seconds=86400,
            )

            assert store.region == PRIMARY_REGION
            assert store.source_region == PRIMARY_REGION

    def test_no_region_param_defaults_to_ap_northeast_1(self, dynamodb_primary):
        """region パラメータなし + AWS_REGION 未設定の場合、ap-northeast-1 をデフォルト使用"""
        with patch.dict("os.environ", {}, clear=True):
            # AWS_REGION を削除
            env_copy = os.environ.copy()
            if "AWS_REGION" in env_copy:
                del env_copy["AWS_REGION"]

            with patch.dict("os.environ", env_copy, clear=True):
                store = TaskTokenStore(
                    table_name=TABLE_NAME,
                    ttl_seconds=86400,
                )

                assert store.region == "ap-northeast-1"

    def test_existing_store_token_api_unchanged(self, dynamodb_primary):
        """既存の store_token API が変更なく動作する"""
        with patch.dict("os.environ", {"AWS_REGION": PRIMARY_REGION}):
            store = TaskTokenStore(
                table_name=TABLE_NAME,
                ttl_seconds=86400,
            )

            # 既存 API: region パラメータなしで動作
            cid = store.store_token(
                task_token="backward-compat-token",
                transform_job_name="backward-compat-job",
            )

            assert len(cid) == 8
            result = store.retrieve_token(cid)
            assert result == "backward-compat-token"

    def test_existing_retrieve_token_api_unchanged(self, dynamodb_primary):
        """既存の retrieve_token API が変更なく動作する"""
        with patch.dict("os.environ", {"AWS_REGION": PRIMARY_REGION}):
            store = TaskTokenStore(
                table_name=TABLE_NAME,
                ttl_seconds=86400,
            )

            cid = store.store_token(
                task_token="retrieve-compat-token",
                transform_job_name="retrieve-compat-job",
            )

            # 既存 API: correlation_id で取得
            result = store.retrieve_token(cid)
            assert result == "retrieve-compat-token"

    def test_existing_delete_token_api_unchanged(self, dynamodb_primary):
        """既存の delete_token API が変更なく動作する"""
        with patch.dict("os.environ", {"AWS_REGION": PRIMARY_REGION}):
            store = TaskTokenStore(
                table_name=TABLE_NAME,
                ttl_seconds=86400,
            )

            cid = store.store_token(
                task_token="delete-compat-token",
                transform_job_name="delete-compat-job",
            )

            # 既存 API: 削除
            store.delete_token(cid)
            result = store.retrieve_token(cid)
            assert result is None

    def test_existing_retrieve_by_job_name_api_unchanged(self, dynamodb_primary):
        """既存の retrieve_token_by_job_name API が変更なく動作する"""
        with patch.dict("os.environ", {"AWS_REGION": PRIMARY_REGION}):
            store = TaskTokenStore(
                table_name=TABLE_NAME,
                ttl_seconds=86400,
            )

            store.store_token(
                task_token="gsi-compat-token",
                transform_job_name="gsi-compat-job",
            )

            # 既存 API: GSI 経由で取得
            result = store.retrieve_token_by_job_name("gsi-compat-job")
            assert result == "gsi-compat-token"

    def test_ttl_still_works_without_region(self, dynamodb_primary):
        """region パラメータなしでも TTL が正しく設定される"""
        with patch.dict("os.environ", {"AWS_REGION": PRIMARY_REGION}):
            store = TaskTokenStore(
                table_name=TABLE_NAME,
                ttl_seconds=7200,  # 2 hours
            )

            before = int(time.time())
            cid = store.store_token(
                task_token="ttl-compat-token",
                transform_job_name="ttl-compat-job",
            )

            # DynamoDB から直接読み取り
            table = dynamodb_primary.Table(TABLE_NAME)
            response = table.get_item(Key={"correlation_id": cid})
            item = response["Item"]

            assert int(item["ttl"]) >= before + 7200
            assert int(item["ttl"]) <= before + 7200 + 2  # 2 秒の許容誤差
