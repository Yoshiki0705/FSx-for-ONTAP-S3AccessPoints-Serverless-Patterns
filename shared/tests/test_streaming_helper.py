"""Unit Tests for shared/streaming/ module

StreamingHelper のバッチ分割ロジック、部分失敗リトライ、
StreamingError 発生、create_event_record シリアライゼーション、
describe_stream をテストする。
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from shared.exceptions import StreamingError
from shared.streaming import StreamingConfig, StreamingHelper


# ---------------------------------------------------------------------------
# Test: Batch splitting logic (500 record limit)
# ---------------------------------------------------------------------------


class TestBatchRecordsSplitting:
    """_batch_records のバッチ分割ロジックテスト"""

    def test_empty_records(self):
        """空リストは空のバッチリストを返す"""
        batches = StreamingHelper._batch_records([])
        assert batches == []

    def test_under_500_records_single_batch(self):
        """500 件未満は 1 バッチ"""
        records = [
            {"Data": b"data", "PartitionKey": f"pk-{i}"}
            for i in range(100)
        ]
        batches = StreamingHelper._batch_records(records)
        assert len(batches) == 1
        assert len(batches[0]) == 100

    def test_exactly_500_records_single_batch(self):
        """ちょうど 500 件は 1 バッチ"""
        records = [
            {"Data": b"data", "PartitionKey": f"pk-{i}"}
            for i in range(500)
        ]
        batches = StreamingHelper._batch_records(records)
        assert len(batches) == 1
        assert len(batches[0]) == 500

    def test_501_records_two_batches(self):
        """501 件は 2 バッチに分割"""
        records = [
            {"Data": b"data", "PartitionKey": f"pk-{i}"}
            for i in range(501)
        ]
        batches = StreamingHelper._batch_records(records)
        assert len(batches) == 2
        assert len(batches[0]) == 500
        assert len(batches[1]) == 1

    def test_1000_records_two_batches(self):
        """1000 件は 2 バッチに分割"""
        records = [
            {"Data": b"data", "PartitionKey": f"pk-{i}"}
            for i in range(1000)
        ]
        batches = StreamingHelper._batch_records(records)
        assert len(batches) == 2
        assert len(batches[0]) == 500
        assert len(batches[1]) == 500

    def test_5mb_limit_splits_batch(self):
        """5 MB 制限でバッチが分割される"""
        # 各レコード約 1 MB → 5 レコードで 5 MB 超
        large_data = b"x" * (1024 * 1024)  # 1 MB
        records = [
            {"Data": large_data, "PartitionKey": f"pk-{i}"}
            for i in range(6)
        ]
        batches = StreamingHelper._batch_records(records)
        # 5 MB 制限により 5 レコード以下でバッチが分割される
        assert len(batches) >= 2
        for batch in batches:
            total_size = sum(
                len(r["Data"]) + len(r["PartitionKey"].encode("utf-8"))
                for r in batch
            )
            assert total_size <= 5 * 1024 * 1024


# ---------------------------------------------------------------------------
# Test: Partial failure retry with mocked Kinesis
# ---------------------------------------------------------------------------


class TestPartialFailureRetry:
    """部分失敗リトライのテスト"""

    def _make_helper(self, max_retries: int = 3) -> tuple[StreamingHelper, MagicMock]:
        config = StreamingConfig(
            stream_name="test-stream",
            region="ap-northeast-1",
            max_retries=max_retries,
        )
        mock_session = MagicMock()
        mock_client = MagicMock()
        mock_session.client.return_value = mock_client
        helper = StreamingHelper(config, session=mock_session)
        return helper, mock_client

    @patch("shared.streaming.streaming_helper.time.sleep")
    def test_partial_failure_retries_only_failed_records(self, mock_sleep):
        """部分失敗時は失敗レコードのみリトライする"""
        helper, mock_client = self._make_helper(max_retries=3)

        records = [
            {"Data": b"data-0", "PartitionKey": "pk-0"},
            {"Data": b"data-1", "PartitionKey": "pk-1"},
            {"Data": b"data-2", "PartitionKey": "pk-2"},
        ]

        # 1st call: record 1 fails
        # 2nd call: all succeed
        mock_client.put_records.side_effect = [
            {
                "FailedRecordCount": 1,
                "Records": [
                    {"SequenceNumber": "seq-0", "ShardId": "shard-0"},
                    {"ErrorCode": "ProvisionedThroughputExceededException", "ErrorMessage": "Rate exceeded"},
                    {"SequenceNumber": "seq-2", "ShardId": "shard-0"},
                ],
            },
            {
                "FailedRecordCount": 0,
                "Records": [
                    {"SequenceNumber": "seq-1", "ShardId": "shard-0"},
                ],
            },
        ]

        result = helper.put_records(records)
        assert result["FailedRecordCount"] == 0

        # 2nd call should only contain the failed record
        second_call_records = mock_client.put_records.call_args_list[1][1]["Records"]
        assert len(second_call_records) == 1
        assert second_call_records[0]["Data"] == b"data-1"

    @patch("shared.streaming.streaming_helper.time.sleep")
    def test_all_succeed_no_retry(self, mock_sleep):
        """全レコード成功時はリトライなし"""
        helper, mock_client = self._make_helper()

        records = [
            {"Data": b"data-0", "PartitionKey": "pk-0"},
        ]

        mock_client.put_records.return_value = {
            "FailedRecordCount": 0,
            "Records": [
                {"SequenceNumber": "seq-0", "ShardId": "shard-0"},
            ],
        }

        result = helper.put_records(records)
        assert result["FailedRecordCount"] == 0
        assert mock_client.put_records.call_count == 1
        mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# Test: StreamingError raised after max retries exhausted
# ---------------------------------------------------------------------------


class TestStreamingErrorOnMaxRetries:
    """最大リトライ後の StreamingError テスト"""

    @patch("shared.streaming.streaming_helper.time.sleep")
    def test_raises_streaming_error_after_max_retries(self, mock_sleep):
        """全リトライ失敗後に StreamingError が raise される"""
        config = StreamingConfig(
            stream_name="test-stream",
            region="ap-northeast-1",
            max_retries=2,
        )
        mock_session = MagicMock()
        mock_client = MagicMock()
        mock_session.client.return_value = mock_client
        helper = StreamingHelper(config, session=mock_session)

        records = [
            {"Data": b"data-0", "PartitionKey": "pk-0"},
            {"Data": b"data-1", "PartitionKey": "pk-1"},
        ]

        # 1st call: record 1 fails (2 records sent)
        # 2nd call: record 1 still fails (1 record sent - only the failed one)
        # 3rd call: record 1 still fails (1 record sent - final attempt)
        mock_client.put_records.side_effect = [
            {
                "FailedRecordCount": 1,
                "Records": [
                    {"SequenceNumber": "seq-0", "ShardId": "shard-0"},
                    {"ErrorCode": "InternalFailure", "ErrorMessage": "Internal error"},
                ],
            },
            {
                "FailedRecordCount": 1,
                "Records": [
                    {"ErrorCode": "InternalFailure", "ErrorMessage": "Internal error"},
                ],
            },
            {
                "FailedRecordCount": 1,
                "Records": [
                    {"ErrorCode": "InternalFailure", "ErrorMessage": "Internal error"},
                ],
            },
        ]

        with pytest.raises(StreamingError) as exc_info:
            helper.put_records(records)

        assert len(exc_info.value.failed_records) == 1
        assert "InternalFailure" in exc_info.value.error_codes

    @patch("shared.streaming.streaming_helper.time.sleep")
    def test_streaming_error_contains_error_codes(self, mock_sleep):
        """StreamingError にエラーコードが含まれる"""
        config = StreamingConfig(
            stream_name="test-stream",
            region="ap-northeast-1",
            max_retries=1,
        )
        mock_session = MagicMock()
        mock_client = MagicMock()
        mock_session.client.return_value = mock_client
        helper = StreamingHelper(config, session=mock_session)

        records = [
            {"Data": b"data-0", "PartitionKey": "pk-0"},
        ]

        mock_client.put_records.return_value = {
            "FailedRecordCount": 1,
            "Records": [
                {"ErrorCode": "ProvisionedThroughputExceededException", "ErrorMessage": "Rate exceeded"},
            ],
        }

        with pytest.raises(StreamingError) as exc_info:
            helper.put_records(records)

        assert "ProvisionedThroughputExceededException" in exc_info.value.error_codes


# ---------------------------------------------------------------------------
# Test: create_event_record serialization format
# ---------------------------------------------------------------------------


class TestCreateEventRecord:
    """create_event_record のシリアライゼーションテスト"""

    def test_basic_event_record(self):
        """基本的なイベントレコードの生成"""
        record = StreamingHelper.create_event_record(
            key="images/product/001.jpg",
            event_type="created",
            timestamp="2026-01-15T10:00:00Z",
        )

        assert "Data" in record
        assert "PartitionKey" in record
        assert record["PartitionKey"] == "images"

        data = json.loads(record["Data"])
        assert data["key"] == "images/product/001.jpg"
        assert data["event_type"] == "created"
        assert data["timestamp"] == "2026-01-15T10:00:00Z"
        assert "metadata" not in data

    def test_event_record_with_metadata(self):
        """メタデータ付きイベントレコードの生成"""
        metadata = {"size": 1024, "content_type": "image/jpeg"}
        record = StreamingHelper.create_event_record(
            key="catalog/items/sku-123.json",
            event_type="modified",
            timestamp="2026-01-15T10:00:00Z",
            metadata=metadata,
        )

        data = json.loads(record["Data"])
        assert data["metadata"] == metadata
        assert record["PartitionKey"] == "catalog"

    def test_partition_key_from_root_file(self):
        """ルートレベルファイルのパーティションキー"""
        record = StreamingHelper.create_event_record(
            key="readme.txt",
            event_type="deleted",
            timestamp="2026-01-15T10:00:00Z",
        )
        # ルートレベルファイルはファイル名自体がパーティションキー
        assert record["PartitionKey"] == "readme.txt"

    def test_partition_key_from_nested_path(self):
        """ネストされたパスのパーティションキー（最初のセグメント）"""
        record = StreamingHelper.create_event_record(
            key="a/b/c/d/file.dat",
            event_type="created",
            timestamp="2026-01-15T10:00:00Z",
        )
        assert record["PartitionKey"] == "a"


# ---------------------------------------------------------------------------
# Test: describe_stream
# ---------------------------------------------------------------------------


class TestDescribeStream:
    """describe_stream のテスト"""

    def test_describe_stream_success(self):
        """正常系: describe_stream が Kinesis レスポンスを返す"""
        config = StreamingConfig(
            stream_name="test-stream",
            region="ap-northeast-1",
        )
        mock_session = MagicMock()
        mock_client = MagicMock()
        mock_session.client.return_value = mock_client
        helper = StreamingHelper(config, session=mock_session)

        expected_response = {
            "StreamDescription": {
                "StreamName": "test-stream",
                "StreamStatus": "ACTIVE",
                "Shards": [{"ShardId": "shard-000"}],
            }
        }
        mock_client.describe_stream.return_value = expected_response

        result = helper.describe_stream()
        assert result == expected_response
        mock_client.describe_stream.assert_called_once_with(
            StreamName="test-stream"
        )

    def test_describe_stream_raises_streaming_error(self):
        """異常系: API エラー時に StreamingError が raise される"""
        config = StreamingConfig(
            stream_name="nonexistent-stream",
            region="ap-northeast-1",
        )
        mock_session = MagicMock()
        mock_client = MagicMock()
        mock_session.client.return_value = mock_client
        helper = StreamingHelper(config, session=mock_session)

        mock_client.describe_stream.side_effect = Exception(
            "ResourceNotFoundException"
        )

        with pytest.raises(StreamingError) as exc_info:
            helper.describe_stream()

        assert "nonexistent-stream" in str(exc_info.value)
