"""LineageTracker ユニットテスト.

DynamoDB への処理履歴レコード書き込み・検索ロジックを検証する。
"""

import os
import sys
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.lineage import LineageRecord, LineageTracker, VALID_STATUSES


@pytest.fixture
def lineage_table():
    """Create a mock DynamoDB table for lineage testing."""
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-1")
        table = dynamodb.create_table(
            TableName="fsxn-s3ap-data-lineage",
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
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        table.meta.client.get_waiter("table_exists").wait(
            TableName="fsxn-s3ap-data-lineage"
        )
        yield dynamodb


def _make_record(
    source_file_key: str = "/vol1/legal/contract.pdf",
    processing_timestamp: str = "2026-06-15T14:30:45.123Z",
    execution_arn: str = "arn:aws:states:us-east-1:123456789012:execution:test-exec",
    uc_id: str = "legal-compliance",
    status: str = "success",
    duration_ms: int = 4523,
) -> LineageRecord:
    """Helper to create a LineageRecord for testing."""
    return LineageRecord(
        source_file_key=source_file_key,
        processing_timestamp=processing_timestamp,
        step_functions_execution_arn=execution_arn,
        uc_id=uc_id,
        output_keys=["s3://output-bucket/legal/reports/analysis.json"],
        status=status,
        duration_ms=duration_ms,
    )


class TestLineageRecord:
    """LineageRecord dataclass のテスト."""

    def test_create_record(self):
        """レコードが正しく作成される."""
        record = _make_record()
        assert record.source_file_key == "/vol1/legal/contract.pdf"
        assert record.status == "success"
        assert record.duration_ms == 4523
        assert record.metadata is None

    def test_create_record_with_metadata(self):
        """メタデータ付きレコードが正しく作成される."""
        record = LineageRecord(
            source_file_key="/vol1/test.pdf",
            processing_timestamp="2026-01-01T00:00:00Z",
            step_functions_execution_arn="arn:test",
            uc_id="test-uc",
            output_keys=[],
            status="success",
            duration_ms=100,
            metadata={"extra": "info"},
        )
        assert record.metadata == {"extra": "info"}


class TestStatusValidation:
    """ステータスバリデーションのテスト."""

    def test_valid_statuses(self):
        """有効なステータスが受け入れられる."""
        tracker = LineageTracker(table_name="test")
        for status in ["success", "failed", "partial"]:
            tracker._validate_status(status)  # Should not raise

    def test_invalid_status_raises(self):
        """無効なステータスで ValueError が発生する."""
        tracker = LineageTracker(table_name="test")
        with pytest.raises(ValueError, match="Invalid status"):
            tracker._validate_status("invalid")

    def test_empty_status_raises(self):
        """空文字列ステータスで ValueError が発生する."""
        tracker = LineageTracker(table_name="test")
        with pytest.raises(ValueError, match="Invalid status"):
            tracker._validate_status("")


class TestLineageTrackerRecord:
    """LineageTracker.record() のテスト."""

    @mock_aws
    def test_record_success(self, lineage_table):
        """レコードが正常に書き込まれる."""
        tracker = LineageTracker(
            table_name="fsxn-s3ap-data-lineage",
            dynamodb_resource=lineage_table,
        )
        record = _make_record()
        lineage_id = tracker.record(record)

        assert lineage_id == "/vol1/legal/contract.pdf#2026-06-15T14:30:45.123Z"

    @mock_aws
    def test_record_with_metadata(self, lineage_table):
        """メタデータ付きレコードが正常に書き込まれる."""
        tracker = LineageTracker(
            table_name="fsxn-s3ap-data-lineage",
            dynamodb_resource=lineage_table,
        )
        record = LineageRecord(
            source_file_key="/vol1/test.pdf",
            processing_timestamp="2026-01-01T00:00:00Z",
            step_functions_execution_arn="arn:test",
            uc_id="test-uc",
            output_keys=["s3://bucket/out.json"],
            status="success",
            duration_ms=100,
            metadata={"pipeline_version": "2.0"},
        )
        lineage_id = tracker.record(record)
        assert lineage_id == "/vol1/test.pdf#2026-01-01T00:00:00Z"

    @mock_aws
    def test_record_invalid_status_raises(self, lineage_table):
        """無効なステータスで ValueError が発生する."""
        tracker = LineageTracker(
            table_name="fsxn-s3ap-data-lineage",
            dynamodb_resource=lineage_table,
        )
        record = _make_record(status="invalid")
        with pytest.raises(ValueError, match="Invalid status"):
            tracker.record(record)

    @mock_aws
    def test_record_write_failure_logs_warning(self, lineage_table, caplog):
        """DynamoDB 書き込み失敗時に警告ログが出力され、例外は発生しない."""
        import logging

        # Use a non-existent table to trigger an error
        tracker = LineageTracker(
            table_name="non-existent-table",
            dynamodb_resource=lineage_table,
        )
        record = _make_record()

        with caplog.at_level(logging.WARNING):
            lineage_id = tracker.record(record)

        # Should still return lineage_id (fail-open)
        assert lineage_id == "/vol1/legal/contract.pdf#2026-06-15T14:30:45.123Z"
        assert "Failed to write record" in caplog.text

    @mock_aws
    def test_record_sets_ttl(self, lineage_table):
        """TTL が正しく設定される."""
        import time

        tracker = LineageTracker(
            table_name="fsxn-s3ap-data-lineage",
            dynamodb_resource=lineage_table,
        )
        record = _make_record()
        before = int(time.time())
        tracker.record(record)
        after = int(time.time())

        # Read back the item
        table = lineage_table.Table("fsxn-s3ap-data-lineage")
        response = table.get_item(
            Key={
                "source_file_key": record.source_file_key,
                "processing_timestamp": record.processing_timestamp,
            }
        )
        item = response["Item"]
        ttl = int(item["ttl"])

        # TTL should be approximately 365 days from now
        expected_min = before + (365 * 86400)
        expected_max = after + (365 * 86400)
        assert expected_min <= ttl <= expected_max


class TestLineageTrackerGetHistory:
    """LineageTracker.get_history() のテスト."""

    @mock_aws
    def test_get_history_returns_records(self, lineage_table):
        """ソースファイルキーで履歴が取得できる."""
        tracker = LineageTracker(
            table_name="fsxn-s3ap-data-lineage",
            dynamodb_resource=lineage_table,
        )
        # Write multiple records for same source
        for i, ts in enumerate(
            ["2026-06-15T10:00:00Z", "2026-06-15T12:00:00Z", "2026-06-15T14:00:00Z"]
        ):
            record = _make_record(processing_timestamp=ts, duration_ms=100 * (i + 1))
            tracker.record(record)

        history = tracker.get_history("/vol1/legal/contract.pdf")
        assert len(history) == 3

    @mock_aws
    def test_get_history_descending_order(self, lineage_table):
        """履歴が processing_timestamp 降順でソートされる."""
        tracker = LineageTracker(
            table_name="fsxn-s3ap-data-lineage",
            dynamodb_resource=lineage_table,
        )
        timestamps = [
            "2026-06-15T10:00:00Z",
            "2026-06-15T14:00:00Z",
            "2026-06-15T12:00:00Z",
        ]
        for ts in timestamps:
            tracker.record(_make_record(processing_timestamp=ts))

        history = tracker.get_history("/vol1/legal/contract.pdf")
        assert len(history) == 3
        # Should be descending
        assert history[0].processing_timestamp == "2026-06-15T14:00:00Z"
        assert history[1].processing_timestamp == "2026-06-15T12:00:00Z"
        assert history[2].processing_timestamp == "2026-06-15T10:00:00Z"

    @mock_aws
    def test_get_history_respects_limit(self, lineage_table):
        """limit パラメータが正しく適用される."""
        tracker = LineageTracker(
            table_name="fsxn-s3ap-data-lineage",
            dynamodb_resource=lineage_table,
        )
        for i in range(5):
            tracker.record(
                _make_record(processing_timestamp=f"2026-06-15T{10+i:02d}:00:00Z")
            )

        history = tracker.get_history("/vol1/legal/contract.pdf", limit=2)
        assert len(history) == 2

    @mock_aws
    def test_get_history_empty_result(self, lineage_table):
        """存在しないキーで空リストが返る."""
        tracker = LineageTracker(
            table_name="fsxn-s3ap-data-lineage",
            dynamodb_resource=lineage_table,
        )
        history = tracker.get_history("/vol1/nonexistent.pdf")
        assert history == []


class TestLineageTrackerGetByUc:
    """LineageTracker.get_by_uc() のテスト."""

    @mock_aws
    def test_get_by_uc_returns_records(self, lineage_table):
        """UC ID で履歴が取得できる."""
        tracker = LineageTracker(
            table_name="fsxn-s3ap-data-lineage",
            dynamodb_resource=lineage_table,
        )
        # Write records for different UCs
        tracker.record(_make_record(uc_id="legal-compliance"))
        tracker.record(
            _make_record(
                source_file_key="/vol1/finance/report.xlsx",
                uc_id="finance-audit",
                processing_timestamp="2026-06-15T15:00:00Z",
            )
        )

        results = tracker.get_by_uc("legal-compliance")
        assert len(results) == 1
        assert results[0].uc_id == "legal-compliance"

    @mock_aws
    def test_get_by_uc_with_time_range(self, lineage_table):
        """時間範囲フィルタが正しく適用される."""
        tracker = LineageTracker(
            table_name="fsxn-s3ap-data-lineage",
            dynamodb_resource=lineage_table,
        )
        timestamps = [
            "2026-06-14T10:00:00Z",
            "2026-06-15T10:00:00Z",
            "2026-06-16T10:00:00Z",
        ]
        for i, ts in enumerate(timestamps):
            tracker.record(
                _make_record(
                    source_file_key=f"/vol1/legal/file{i}.pdf",
                    processing_timestamp=ts,
                )
            )

        results = tracker.get_by_uc(
            "legal-compliance",
            start_time="2026-06-15T00:00:00Z",
            end_time="2026-06-15T23:59:59Z",
        )
        assert len(results) == 1
        assert results[0].processing_timestamp == "2026-06-15T10:00:00Z"

    @mock_aws
    def test_get_by_uc_empty_result(self, lineage_table):
        """存在しない UC ID で空リストが返る."""
        tracker = LineageTracker(
            table_name="fsxn-s3ap-data-lineage",
            dynamodb_resource=lineage_table,
        )
        results = tracker.get_by_uc("nonexistent-uc")
        assert results == []


class TestLineageTrackerGetByExecution:
    """LineageTracker.get_by_execution() のテスト."""

    @mock_aws
    def test_get_by_execution_returns_records(self, lineage_table):
        """execution_arn で履歴が取得できる."""
        tracker = LineageTracker(
            table_name="fsxn-s3ap-data-lineage",
            dynamodb_resource=lineage_table,
        )
        target_arn = "arn:aws:states:us-east-1:123456789012:execution:target-exec"
        tracker.record(_make_record(execution_arn=target_arn))
        tracker.record(
            _make_record(
                source_file_key="/vol1/other.pdf",
                execution_arn="arn:aws:states:us-east-1:123456789012:execution:other",
                processing_timestamp="2026-06-15T15:00:00Z",
            )
        )

        results = tracker.get_by_execution(target_arn)
        assert len(results) == 1
        assert results[0].step_functions_execution_arn == target_arn

    @mock_aws
    def test_get_by_execution_empty_result(self, lineage_table):
        """存在しない execution_arn で空リストが返る."""
        tracker = LineageTracker(
            table_name="fsxn-s3ap-data-lineage",
            dynamodb_resource=lineage_table,
        )
        results = tracker.get_by_execution("arn:nonexistent")
        assert results == []
