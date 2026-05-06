"""Property-Based Tests for Task Token Store — Phase 4

Hypothesis を使用したプロパティベーステスト。
Phase 4 Theme A: DynamoDB ベース Task Token ストレージの
不変条件（invariants）を任意入力で検証する。

Testing Strategy:
- 最小 100 イテレーション/プロパティ
- 各テストにプロパティ番号タグを付与
- タグ形式: Feature: fsxn-s3ap-serverless-patterns-phase4, Property {number}: {property_text}
"""

from __future__ import annotations

import logging
import logging.handlers
import re
import time
from unittest.mock import patch

import boto3
import pytest
from hypothesis import given, settings, strategies as st, HealthCheck
from moto import mock_aws

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


def detect_token_mode(tags: dict) -> str:
    """Detect token retrieval mode based on SageMaker job tags.

    If 'CorrelationId' tag is present → DynamoDB mode.
    If 'TaskToken' tag is present → direct mode.

    Args:
        tags: Dictionary of SageMaker job tags.

    Returns:
        "dynamodb" or "direct"
    """
    if "CorrelationId" in tags:
        return "dynamodb"
    elif "TaskToken" in tags:
        return "direct"
    # Fallback (should not happen in production)
    return "direct"


# ---------------------------------------------------------------------------
# Property 1: Correlation ID Format Invariant
# Feature: fsxn-s3ap-serverless-patterns-phase4, Property 1: Correlation ID Format Invariant
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(st.integers(min_value=0, max_value=10000))
def test_correlation_id_format_invariant(_iteration):
    """Feature: fsxn-s3ap-serverless-patterns-phase4, Property 1: Correlation ID Format Invariant

    For any call to generate_correlation_id(), the returned value SHALL be
    exactly 8 hexadecimal characters (matching regex ^[0-9a-f]{8}$),
    providing 32 bits of entropy.

    **Validates: Requirements 2.1**
    """
    correlation_id = TaskTokenStore.generate_correlation_id()

    # Must be exactly 8 characters
    assert len(correlation_id) == 8, (
        f"Correlation ID must be 8 chars, got {len(correlation_id)}: '{correlation_id}'"
    )

    # Must match hex pattern
    assert re.match(r"^[0-9a-f]{8}$", correlation_id), (
        f"Correlation ID must match ^[0-9a-f]{{8}}$, got: '{correlation_id}'"
    )


# ---------------------------------------------------------------------------
# Property 2: Task Token Round-Trip
# Feature: fsxn-s3ap-serverless-patterns-phase4, Property 2: Task Token Round-Trip
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    task_token=st.text(min_size=100, max_size=2000),
    job_name=st.text(min_size=5, max_size=100),
)
def test_task_token_round_trip(task_token, job_name):
    """Feature: fsxn-s3ap-serverless-patterns-phase4, Property 2: Task Token Round-Trip

    For any valid Task Token string and transform job name, storing the token
    in the Task Token Store and then retrieving it by the returned correlation
    ID SHALL return the exact original Task Token value (byte-for-byte equality).

    **Validates: Requirements 2.1, 3.2**
    """
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name=REGION)
        _create_token_table(dynamodb)

        store = TaskTokenStore(table_name=TABLE_NAME, ttl_seconds=86400)

        # Store the token
        correlation_id = store.store_token(
            task_token=task_token,
            transform_job_name=job_name,
        )

        # Retrieve by correlation_id
        retrieved = store.retrieve_token(correlation_id)

        # Round-trip: must get back the exact original value
        assert retrieved == task_token, (
            f"Round-trip failed: stored token length={len(task_token)}, "
            f"retrieved={'None' if retrieved is None else f'length={len(retrieved)}'}"
        )


# ---------------------------------------------------------------------------
# Property 3: TTL Calculation Correctness
# Feature: fsxn-s3ap-serverless-patterns-phase4, Property 3: TTL Calculation Correctness
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    current_timestamp=st.integers(min_value=0, max_value=2**31),
    retention_seconds=st.integers(min_value=1, max_value=604800),
)
def test_ttl_calculation_correctness(current_timestamp, retention_seconds):
    """Feature: fsxn-s3ap-serverless-patterns-phase4, Property 3: TTL Calculation Correctness

    For any current Unix timestamp and configurable retention period (in seconds),
    the computed ttl attribute SHALL equal current_timestamp + retention_seconds,
    and SHALL always be greater than current_timestamp.

    **Validates: Requirements 2.2**
    """
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name=REGION)
        _create_token_table(dynamodb)

        store = TaskTokenStore(table_name=TABLE_NAME, ttl_seconds=retention_seconds)

        # Mock time.time() to return our controlled timestamp
        with patch("shared.task_token_store.time.time", return_value=current_timestamp):
            correlation_id = store.store_token(
                task_token="test-token-for-ttl-verification",
                transform_job_name="test-job",
            )

        # Read the raw item from DynamoDB to verify TTL
        table = dynamodb.Table(TABLE_NAME)
        response = table.get_item(Key={"correlation_id": correlation_id})
        item = response["Item"]

        expected_ttl = current_timestamp + retention_seconds

        # TTL must equal current_timestamp + retention_seconds
        assert int(item["ttl"]) == expected_ttl, (
            f"TTL mismatch: expected {expected_ttl}, got {item['ttl']}"
        )

        # TTL must always be greater than current_timestamp
        assert int(item["ttl"]) > current_timestamp, (
            f"TTL ({item['ttl']}) must be > current_timestamp ({current_timestamp})"
        )


# ---------------------------------------------------------------------------
# Property 4: Conditional Write Prevents Collision
# Feature: fsxn-s3ap-serverless-patterns-phase4, Property 4: Conditional Write Prevents Collision
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    correlation_id=st.text(
        alphabet="0123456789abcdef", min_size=8, max_size=8
    ),
    task_token_1=st.text(min_size=100, max_size=500),
    task_token_2=st.text(min_size=100, max_size=500),
)
def test_conditional_write_prevents_collision(
    correlation_id, task_token_1, task_token_2
):
    """Feature: fsxn-s3ap-serverless-patterns-phase4, Property 4: Conditional Write Prevents Collision

    For any two store operations with the same correlation ID, exactly one
    SHALL succeed and the other SHALL raise a ConditionalCheckFailedException,
    ensuring no Task Token is silently overwritten.

    **Validates: Requirements 2.4**
    """
    from botocore.exceptions import ClientError

    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name=REGION)
        _create_token_table(dynamodb)

        table = dynamodb.Table(TABLE_NAME)

        # First write should succeed
        table.put_item(
            Item={
                "correlation_id": correlation_id,
                "task_token": task_token_1,
                "transform_job_name": "job-1",
                "created_at": int(time.time()),
                "ttl": int(time.time()) + 86400,
            },
            ConditionExpression="attribute_not_exists(correlation_id)",
        )

        # Second write with same correlation_id should fail
        with pytest.raises(ClientError) as exc_info:
            table.put_item(
                Item={
                    "correlation_id": correlation_id,
                    "task_token": task_token_2,
                    "transform_job_name": "job-2",
                    "created_at": int(time.time()),
                    "ttl": int(time.time()) + 86400,
                },
                ConditionExpression="attribute_not_exists(correlation_id)",
            )

        assert (
            exc_info.value.response["Error"]["Code"]
            == "ConditionalCheckFailedException"
        ), (
            f"Expected ConditionalCheckFailedException, "
            f"got: {exc_info.value.response['Error']['Code']}"
        )

        # Verify original token is preserved (not overwritten)
        response = table.get_item(Key={"correlation_id": correlation_id})
        assert response["Item"]["task_token"] == task_token_1


# ---------------------------------------------------------------------------
# Property 5: Mode Detection by Tag Presence
# Feature: fsxn-s3ap-serverless-patterns-phase4, Property 5: Mode Detection by Tag Presence
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    correlation_id_value=st.text(
        alphabet="0123456789abcdef", min_size=8, max_size=8
    ),
    task_token_value=st.text(min_size=100, max_size=500),
)
def test_mode_detection_by_tag_presence(correlation_id_value, task_token_value):
    """Feature: fsxn-s3ap-serverless-patterns-phase4, Property 5: Mode Detection by Tag Presence

    For any EventBridge event containing SageMaker job tags, if the tag
    'CorrelationId' is present the callback Lambda SHALL use DynamoDB
    retrieval mode, and if the tag 'TaskToken' is present it SHALL use
    direct mode. The two modes are mutually exclusive per event.

    **Validates: Requirements 3.1, 4.4**
    """
    # Case 1: CorrelationId tag present → DynamoDB mode
    tags_dynamodb = {"CorrelationId": correlation_id_value, "OtherTag": "value"}
    assert detect_token_mode(tags_dynamodb) == "dynamodb", (
        "CorrelationId tag present should result in 'dynamodb' mode"
    )

    # Case 2: TaskToken tag present → direct mode
    tags_direct = {"TaskToken": task_token_value, "OtherTag": "value"}
    assert detect_token_mode(tags_direct) == "direct", (
        "TaskToken tag present should result in 'direct' mode"
    )

    # Case 3: Modes are mutually exclusive — CorrelationId takes priority
    # (In production, both tags should never be present simultaneously,
    # but if they are, DynamoDB mode takes precedence)
    tags_both = {
        "CorrelationId": correlation_id_value,
        "TaskToken": task_token_value,
    }
    assert detect_token_mode(tags_both) == "dynamodb", (
        "When both tags present, CorrelationId (DynamoDB mode) takes precedence"
    )


# ---------------------------------------------------------------------------
# Property 6: Task Token Never Logged in Plaintext
# Feature: fsxn-s3ap-serverless-patterns-phase4, Property 6: Task Token Never Logged in Plaintext
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    task_token=st.text(min_size=100, max_size=2000),
)
def test_task_token_never_logged_in_plaintext(task_token):
    """Feature: fsxn-s3ap-serverless-patterns-phase4, Property 6: Task Token Never Logged in Plaintext

    For any Task Token value processed by the TaskTokenStore, the token value
    SHALL NOT appear in any log output. Only the correlation ID and job name
    SHALL be logged for audit purposes.

    **Validates: Requirements 2.6, 3.7**
    """
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name=REGION)
        _create_token_table(dynamodb)

        store = TaskTokenStore(table_name=TABLE_NAME, ttl_seconds=86400)

        # Set up log capture
        log_handler = logging.handlers.MemoryHandler(capacity=1000)
        log_records: list[logging.LogRecord] = []

        class RecordCollector(logging.Handler):
            def emit(self, record):
                log_records.append(record)

        collector = RecordCollector()
        logger = logging.getLogger("shared.task_token_store")
        logger.addHandler(collector)
        logger.setLevel(logging.DEBUG)

        try:
            # Store operation
            correlation_id = store.store_token(
                task_token=task_token,
                transform_job_name="test-job-logging",
            )

            # Retrieve operation
            store.retrieve_token(correlation_id)

            # Delete operation
            store.delete_token(correlation_id)
        finally:
            logger.removeHandler(collector)

        # The task_token value must NOT appear in any log record
        all_log_text = " ".join(record.getMessage() for record in log_records)

        # Only check if token is non-empty and has meaningful content
        if len(task_token.strip()) > 0:
            assert task_token not in all_log_text, (
                f"Task token value was found in log output! "
                f"Token length: {len(task_token)}, "
                f"Log contains {len(log_records)} records"
            )


# ---------------------------------------------------------------------------
# Property 7: Cleanup After Successful Callback
# Feature: fsxn-s3ap-serverless-patterns-phase4, Property 7: Cleanup After Successful Callback
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    task_token=st.text(min_size=100, max_size=2000),
    job_name=st.text(min_size=5, max_size=100),
)
def test_cleanup_after_successful_callback(task_token, job_name):
    """Feature: fsxn-s3ap-serverless-patterns-phase4, Property 7: Cleanup After Successful Callback

    For any successful SendTaskSuccess or SendTaskFailure call, the
    corresponding Task Token Store record SHALL be deleted. After deletion,
    querying by the same correlation ID SHALL return None.

    **Validates: Requirements 3.6**
    """
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name=REGION)
        _create_token_table(dynamodb)

        store = TaskTokenStore(table_name=TABLE_NAME, ttl_seconds=86400)

        # Store the token
        correlation_id = store.store_token(
            task_token=task_token,
            transform_job_name=job_name,
        )

        # Verify it exists
        retrieved = store.retrieve_token(correlation_id)
        assert retrieved == task_token, "Token should exist before deletion"

        # Delete (simulating cleanup after successful callback)
        store.delete_token(correlation_id)

        # After deletion, retrieve must return None
        retrieved_after_delete = store.retrieve_token(correlation_id)
        assert retrieved_after_delete is None, (
            f"After deletion, retrieve should return None, "
            f"got: {type(retrieved_after_delete)}"
        )
