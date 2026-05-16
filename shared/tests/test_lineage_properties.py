"""Data Lineage Tracking プロパティベーステスト.

Property 5: Lineage Record Round-Trip
  - record() で書き込んだレコードが get_history() / get_by_uc() で取得可能
Property 6: Lineage History Ordering
  - get_history() が processing_timestamp 降順でソートされたリストを返す

**Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**
"""

from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta

import boto3
import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st
from moto import mock_aws

from shared.lineage import LineageRecord, LineageTracker


# --- Hypothesis Strategies ---

TABLE_NAME = "test-lineage-pbt"

uc_id_strategy = st.sampled_from([
    "legal-compliance",
    "financial-reporting",
    "media-transcoding",
    "data-archival",
    "log-analysis",
])

status_strategy = st.sampled_from(["success", "failed", "partial"])

source_file_key_strategy = st.from_regex(
    r"/vol[1-9]/[a-z]{3,10}/[a-z0-9_-]{5,20}\.(pdf|csv|json|txt)",
    fullmatch=True,
)

output_keys_strategy = st.lists(
    st.from_regex(r"s3://[a-z-]{5,15}/[a-z0-9/_-]{5,30}\.(json|csv|parquet)", fullmatch=True),
    min_size=0,
    max_size=5,
)

duration_ms_strategy = st.integers(min_value=100, max_value=300000)

execution_arn_strategy = st.from_regex(
    r"arn:aws:states:ap-northeast-1:123456789012:execution:uc-[a-z]{3,8}:[a-f0-9]{8}",
    fullmatch=True,
)

# Strategy for generating sorted timestamps (for ordering tests)
num_records_strategy = st.integers(min_value=2, max_value=10)


# --- Helpers ---


def _ensure_lineage_table(region: str = "ap-northeast-1") -> None:
    """Create the DynamoDB lineage table with GSI."""
    dynamodb = boto3.resource("dynamodb", region_name=region)
    existing_tables = boto3.client("dynamodb", region_name=region).list_tables()["TableNames"]
    if TABLE_NAME not in existing_tables:
        dynamodb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[
                {"AttributeName": "source_file_key", "KeyType": "HASH"},
                {"AttributeName": "processing_timestamp", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "source_file_key", "AttributeType": "S"},
                {"AttributeName": "processing_timestamp", "AttributeType": "S"},
                {"AttributeName": "uc_id", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "uc_id-timestamp-index",
                    "KeySchema": [
                        {"AttributeName": "uc_id", "KeyType": "HASH"},
                        {"AttributeName": "processing_timestamp", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )


def _make_timestamp(base: datetime, offset_seconds: int) -> str:
    """Generate an ISO 8601 timestamp with offset."""
    ts = base + timedelta(seconds=offset_seconds)
    return ts.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# --- Property 5: Lineage Record Round-Trip ---


class TestLineageRecordRoundTrip:
    """Property 5: Lineage Record Round-Trip.

    **Validates: Requirements 5.1, 5.2, 5.4, 5.5**

    record() で書き込んだレコードが get_history() および get_by_uc() で
    取得可能であることを検証する。
    """

    @pytest.mark.property
    @given(
        source_file_key=source_file_key_strategy,
        uc_id=uc_id_strategy,
        status=status_strategy,
        output_keys=output_keys_strategy,
        duration_ms=duration_ms_strategy,
        execution_arn=execution_arn_strategy,
    )
    @settings(max_examples=50, deadline=None, suppress_health_check=[
        HealthCheck.function_scoped_fixture,
        HealthCheck.too_slow,
    ])
    def test_record_retrievable_via_get_history(
        self,
        source_file_key: str,
        uc_id: str,
        status: str,
        output_keys: list[str],
        duration_ms: int,
        execution_arn: str,
    ):
        """書き込んだレコードが get_history() で取得可能."""
        os.environ["AWS_DEFAULT_REGION"] = "ap-northeast-1"

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        record = LineageRecord(
            source_file_key=source_file_key,
            processing_timestamp=timestamp,
            step_functions_execution_arn=execution_arn,
            uc_id=uc_id,
            output_keys=output_keys,
            status=status,
            duration_ms=duration_ms,
        )

        with mock_aws():
            _ensure_lineage_table()

            tracker = LineageTracker(table_name=TABLE_NAME)
            lineage_id = tracker.record(record)

            # Verify via get_history
            history = tracker.get_history(source_file_key)

            assert len(history) >= 1, (
                f"Expected at least 1 record in history, got {len(history)}"
            )

            # Find our record
            found = False
            for r in history:
                if r.processing_timestamp == timestamp:
                    assert r.source_file_key == source_file_key
                    assert r.uc_id == uc_id
                    assert r.status == status
                    assert r.duration_ms == duration_ms
                    assert r.step_functions_execution_arn == execution_arn
                    assert r.output_keys == output_keys
                    found = True
                    break

            assert found, (
                f"Record with timestamp {timestamp} not found in history"
            )

    @pytest.mark.property
    @given(
        source_file_key=source_file_key_strategy,
        uc_id=uc_id_strategy,
        status=status_strategy,
        duration_ms=duration_ms_strategy,
        execution_arn=execution_arn_strategy,
    )
    @settings(max_examples=50, deadline=None, suppress_health_check=[
        HealthCheck.function_scoped_fixture,
        HealthCheck.too_slow,
    ])
    def test_record_retrievable_via_get_by_uc(
        self,
        source_file_key: str,
        uc_id: str,
        status: str,
        duration_ms: int,
        execution_arn: str,
    ):
        """書き込んだレコードが get_by_uc() で取得可能."""
        os.environ["AWS_DEFAULT_REGION"] = "ap-northeast-1"

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        record = LineageRecord(
            source_file_key=source_file_key,
            processing_timestamp=timestamp,
            step_functions_execution_arn=execution_arn,
            uc_id=uc_id,
            output_keys=[],
            status=status,
            duration_ms=duration_ms,
        )

        with mock_aws():
            _ensure_lineage_table()

            tracker = LineageTracker(table_name=TABLE_NAME)
            tracker.record(record)

            # Verify via get_by_uc
            results = tracker.get_by_uc(uc_id)

            assert len(results) >= 1, (
                f"Expected at least 1 record for uc_id={uc_id}, got {len(results)}"
            )

            # Find our record
            found = any(
                r.source_file_key == source_file_key
                and r.processing_timestamp == timestamp
                for r in results
            )
            assert found, (
                f"Record not found via get_by_uc('{uc_id}')"
            )


# --- Property 6: Lineage History Ordering ---


class TestLineageHistoryOrdering:
    """Property 6: Lineage History Ordering.

    **Validates: Requirements 5.3**

    get_history() が processing_timestamp 降順でソートされたリストを返すことを検証する。
    """

    @pytest.mark.property
    @given(
        uc_id=uc_id_strategy,
        num_records=num_records_strategy,
        status=status_strategy,
    )
    @settings(max_examples=30, deadline=None, suppress_health_check=[
        HealthCheck.function_scoped_fixture,
        HealthCheck.too_slow,
    ])
    def test_history_sorted_descending(
        self,
        uc_id: str,
        num_records: int,
        status: str,
    ):
        """get_history() が processing_timestamp 降順でソートされる."""
        os.environ["AWS_DEFAULT_REGION"] = "ap-northeast-1"

        # Use a fixed source_file_key for all records
        source_file_key = "/vol1/test/ordering-test.pdf"
        base_time = datetime(2026, 6, 15, 10, 0, 0, tzinfo=timezone.utc)

        # Generate records with distinct timestamps (ascending order)
        records = []
        for i in range(num_records):
            timestamp = _make_timestamp(base_time, i * 60)  # 1 minute apart
            records.append(
                LineageRecord(
                    source_file_key=source_file_key,
                    processing_timestamp=timestamp,
                    step_functions_execution_arn=f"arn:aws:states:ap-northeast-1:123456789012:execution:uc-test:{i:08d}",
                    uc_id=uc_id,
                    output_keys=[],
                    status=status,
                    duration_ms=1000 + i * 100,
                )
            )

        with mock_aws():
            _ensure_lineage_table()

            tracker = LineageTracker(table_name=TABLE_NAME)

            # Write records in random-ish order (ascending, which is NOT the expected output order)
            for record in records:
                tracker.record(record)

            # Retrieve history
            history = tracker.get_history(source_file_key, limit=num_records + 10)

            assert len(history) == num_records, (
                f"Expected {num_records} records, got {len(history)}"
            )

            # Verify descending order
            timestamps = [r.processing_timestamp for r in history]
            for i in range(len(timestamps) - 1):
                assert timestamps[i] >= timestamps[i + 1], (
                    f"History not in descending order: "
                    f"timestamps[{i}]={timestamps[i]} < timestamps[{i+1}]={timestamps[i+1]}"
                )

    @pytest.mark.property
    @given(
        num_records=st.integers(min_value=3, max_value=8),
        time_gaps=st.lists(
            st.integers(min_value=1, max_value=3600),
            min_size=2,
            max_size=7,
        ),
    )
    @settings(max_examples=30, deadline=None, suppress_health_check=[
        HealthCheck.function_scoped_fixture,
        HealthCheck.too_slow,
    ])
    def test_history_ordering_with_variable_gaps(
        self,
        num_records: int,
        time_gaps: list[int],
    ):
        """不均等な時間間隔でも降順ソートが保持される."""
        os.environ["AWS_DEFAULT_REGION"] = "ap-northeast-1"

        # Adjust num_records to match available gaps
        actual_records = min(num_records, len(time_gaps) + 1)
        assume(actual_records >= 2)

        source_file_key = "/vol2/data/variable-gap-test.csv"
        base_time = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        # Generate timestamps with variable gaps
        timestamps = []
        cumulative_offset = 0
        for i in range(actual_records):
            timestamps.append(_make_timestamp(base_time, cumulative_offset))
            if i < len(time_gaps):
                cumulative_offset += time_gaps[i]

        with mock_aws():
            _ensure_lineage_table()

            tracker = LineageTracker(table_name=TABLE_NAME)

            # Write records
            for i, ts in enumerate(timestamps):
                record = LineageRecord(
                    source_file_key=source_file_key,
                    processing_timestamp=ts,
                    step_functions_execution_arn=f"arn:aws:states:ap-northeast-1:123456789012:execution:uc-gap:{i:08d}",
                    uc_id="log-analysis",
                    output_keys=[],
                    status="success",
                    duration_ms=500,
                )
                tracker.record(record)

            # Retrieve and verify ordering
            history = tracker.get_history(source_file_key, limit=50)

            assert len(history) == actual_records

            # Verify strictly descending (or equal) timestamps
            result_timestamps = [r.processing_timestamp for r in history]
            for i in range(len(result_timestamps) - 1):
                assert result_timestamps[i] >= result_timestamps[i + 1], (
                    f"Not descending at index {i}: "
                    f"{result_timestamps[i]} vs {result_timestamps[i+1]}"
                )
