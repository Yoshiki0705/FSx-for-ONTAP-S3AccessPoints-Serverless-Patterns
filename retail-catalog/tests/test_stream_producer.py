"""UC11 Stream Producer ユニットテスト

DynamoDB (state table) と Kinesis を unittest.mock でモックし、
変更検出ロジック（新規・変更・削除）と Kinesis 書き込みをテストする。

テスト対象:
- 新規ファイル検出（S3 AP にあるが DynamoDB にない → "created" イベント）
- 変更ファイル検出（S3 AP の ETag が DynamoDB と異なる → "modified" イベント）
- 削除ファイル検出（DynamoDB にあるが S3 AP にない → "deleted" イベント）
- 変更なし → Kinesis 書き込みなし
- DynamoDB state テーブル更新（Kinesis 書き込み成功後）
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch, call
from datetime import datetime, timezone

import pytest


# テスト用環境変数を設定
@pytest.fixture(autouse=True)
def env_vars(monkeypatch):
    """テスト用環境変数"""
    monkeypatch.setenv("S3_ACCESS_POINT", "test-ap-ext-s3alias")
    monkeypatch.setenv("KINESIS_STREAM_NAME", "test-stream")
    monkeypatch.setenv("STATE_TABLE_NAME", "test-state-table")
    monkeypatch.setenv("USE_CASE", "retail-catalog")
    monkeypatch.setenv("REGION", "ap-northeast-1")
    monkeypatch.setenv("ENABLE_XRAY", "false")


@pytest.fixture
def mock_context():
    """Lambda コンテキストモック"""
    context = MagicMock()
    context.aws_request_id = "test-request-id-123"
    context.function_name = "test-stream-producer"
    return context


@pytest.fixture
def mock_dynamodb_table():
    """DynamoDB テーブルモック"""
    table = MagicMock()
    return table


class TestDetectChanges:
    """変更検出ロジックのテスト"""

    def test_new_file_detection(self):
        """S3 AP にあるが DynamoDB にないファイル → created イベント"""
        from retail_catalog_functions_stream_producer import _detect_changes

        s3_objects = [
            {"Key": "images/product/001.jpg", "ETag": '"abc123"', "LastModified": "2024-01-01T00:00:00Z"},
            {"Key": "images/product/002.jpg", "ETag": '"def456"', "LastModified": "2024-01-01T00:00:00Z"},
        ]
        state_items = {}  # 空の state テーブル

        created, modified, deleted = _detect_changes(s3_objects, state_items)

        assert len(created) == 2
        assert len(modified) == 0
        assert len(deleted) == 0
        assert created[0]["key"] == "images/product/001.jpg"
        assert created[1]["key"] == "images/product/002.jpg"

    def test_modified_file_detection(self):
        """S3 AP の ETag が DynamoDB と異なる → modified イベント"""
        from retail_catalog_functions_stream_producer import _detect_changes

        s3_objects = [
            {"Key": "images/product/001.jpg", "ETag": '"new-etag"', "LastModified": "2024-01-02T00:00:00Z"},
        ]
        state_items = {
            "images/product/001.jpg": {
                "file_key": "images/product/001.jpg",
                "etag": '"old-etag"',
                "last_modified": "2024-01-01T00:00:00Z",
                "processing_status": "completed",
            }
        }

        created, modified, deleted = _detect_changes(s3_objects, state_items)

        assert len(created) == 0
        assert len(modified) == 1
        assert len(deleted) == 0
        assert modified[0]["key"] == "images/product/001.jpg"
        assert modified[0]["etag"] == '"new-etag"'

    def test_deleted_file_detection(self):
        """DynamoDB にあるが S3 AP にないファイル → deleted イベント"""
        from retail_catalog_functions_stream_producer import _detect_changes

        s3_objects = []  # S3 AP は空
        state_items = {
            "images/product/001.jpg": {
                "file_key": "images/product/001.jpg",
                "etag": '"abc123"',
                "last_modified": "2024-01-01T00:00:00Z",
                "processing_status": "completed",
            }
        }

        created, modified, deleted = _detect_changes(s3_objects, state_items)

        assert len(created) == 0
        assert len(modified) == 0
        assert len(deleted) == 1
        assert deleted[0]["key"] == "images/product/001.jpg"

    def test_no_changes_detected(self):
        """変更なし → 全リスト空"""
        from retail_catalog_functions_stream_producer import _detect_changes

        s3_objects = [
            {"Key": "images/product/001.jpg", "ETag": '"abc123"', "LastModified": "2024-01-01T00:00:00Z"},
        ]
        state_items = {
            "images/product/001.jpg": {
                "file_key": "images/product/001.jpg",
                "etag": '"abc123"',
                "last_modified": "2024-01-01T00:00:00Z",
                "processing_status": "completed",
            }
        }

        created, modified, deleted = _detect_changes(s3_objects, state_items)

        assert len(created) == 0
        assert len(modified) == 0
        assert len(deleted) == 0


class TestHandlerIntegration:
    """ハンドラ統合テスト（モック使用）"""

    @patch("retail_catalog_functions_stream_producer.StreamingHelper")
    @patch("retail_catalog_functions_stream_producer.S3ApHelper")
    @patch("retail_catalog_functions_stream_producer.boto3")
    def test_no_changes_no_kinesis_write(self, mock_boto3, mock_s3ap_cls, mock_streaming_cls, mock_context):
        """変更なし → Kinesis 書き込みなし"""
        from retail_catalog_functions_stream_producer import handler

        # S3 AP モック: 1 ファイル
        mock_s3ap = MagicMock()
        mock_s3ap.list_objects.return_value = [
            {"Key": "images/001.jpg", "ETag": '"abc"', "LastModified": "2024-01-01T00:00:00Z"},
        ]
        mock_s3ap_cls.return_value = mock_s3ap

        # DynamoDB モック: 同じファイルが state テーブルにある
        mock_table = MagicMock()
        mock_table.scan.return_value = {
            "Items": [
                {"file_key": "images/001.jpg", "etag": '"abc"', "last_modified": "2024-01-01T00:00:00Z"}
            ]
        }
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb

        result = handler({}, mock_context)

        assert result["status"] == "no_changes"
        # StreamingHelper should not be instantiated for put_records
        mock_streaming_cls.return_value.put_records.assert_not_called()

    @patch("retail_catalog_functions_stream_producer.StreamingHelper")
    @patch("retail_catalog_functions_stream_producer.S3ApHelper")
    @patch("retail_catalog_functions_stream_producer.boto3")
    def test_new_file_triggers_kinesis_write(self, mock_boto3, mock_s3ap_cls, mock_streaming_cls, mock_context):
        """新規ファイル検出 → Kinesis 書き込み + state テーブル更新"""
        from retail_catalog_functions_stream_producer import handler

        # S3 AP モック: 新規ファイル
        mock_s3ap = MagicMock()
        mock_s3ap.list_objects.return_value = [
            {"Key": "images/new-product.jpg", "ETag": '"new-etag"', "LastModified": "2024-01-02T00:00:00Z"},
        ]
        mock_s3ap_cls.return_value = mock_s3ap

        # DynamoDB モック: 空の state テーブル
        mock_table = MagicMock()
        mock_table.scan.return_value = {"Items": []}
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb

        # StreamingHelper モック
        mock_streaming = MagicMock()
        mock_streaming.put_records.return_value = {"FailedRecordCount": 0, "Records": []}
        mock_streaming_cls.return_value = mock_streaming

        result = handler({}, mock_context)

        assert result["status"] == "changes_published"
        assert result["created"] == 1
        assert result["modified"] == 0
        assert result["deleted"] == 0
        mock_streaming.put_records.assert_called_once()

    @patch("retail_catalog_functions_stream_producer.StreamingHelper")
    @patch("retail_catalog_functions_stream_producer.S3ApHelper")
    @patch("retail_catalog_functions_stream_producer.boto3")
    def test_state_table_updated_after_kinesis_write(self, mock_boto3, mock_s3ap_cls, mock_streaming_cls, mock_context):
        """Kinesis 書き込み成功後に DynamoDB state テーブルが更新される"""
        from retail_catalog_functions_stream_producer import handler

        # S3 AP モック: 新規ファイル
        mock_s3ap = MagicMock()
        mock_s3ap.list_objects.return_value = [
            {"Key": "images/product/new.jpg", "ETag": '"etag1"', "LastModified": "2024-01-01T00:00:00Z"},
        ]
        mock_s3ap_cls.return_value = mock_s3ap

        # DynamoDB モック
        mock_table = MagicMock()
        mock_table.scan.return_value = {"Items": []}
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb

        # StreamingHelper モック
        mock_streaming = MagicMock()
        mock_streaming.put_records.return_value = {"FailedRecordCount": 0, "Records": []}
        mock_streaming_cls.return_value = mock_streaming

        handler({}, mock_context)

        # state テーブルに put_item が呼ばれたことを確認
        mock_table.put_item.assert_called()
        put_call_args = mock_table.put_item.call_args
        item = put_call_args[1]["Item"] if "Item" in put_call_args[1] else put_call_args[0][0]
        assert item["file_key"] == "images/product/new.jpg"
        assert item["processing_status"] == "pending"


# テスト用のインポートパスを設定するための conftest 的処理
import sys
from pathlib import Path

# stream_producer モジュールをインポート可能にする
_project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_project_root))

# handler.py を retail_catalog_functions_stream_producer としてインポート
import importlib.util

_handler_path = Path(__file__).resolve().parent.parent / "functions" / "stream_producer" / "handler.py"
_spec = importlib.util.spec_from_file_location("retail_catalog_functions_stream_producer", _handler_path)
_module = importlib.util.module_from_spec(_spec)
sys.modules["retail_catalog_functions_stream_producer"] = _module
_spec.loader.exec_module(_module)

# モジュールから関数をインポート
from retail_catalog_functions_stream_producer import _detect_changes  # noqa: E402, F401
