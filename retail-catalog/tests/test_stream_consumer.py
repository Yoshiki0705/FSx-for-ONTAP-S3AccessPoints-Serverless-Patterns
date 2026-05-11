"""UC11 Stream Consumer ユニットテスト

DynamoDB と Lambda を unittest.mock でモックし、
レコード処理ロジックをテストする。

テスト対象:
- 有効なレコードスキーマ → 正常処理
- 不正なレコードスキーマ（key 欠落）→ 破棄 + 警告ログ
- 冪等処理（既に処理済みレコード）→ スキップ
- 処理エラー → dead-letter テーブルに書き込み
- バッチ処理（有効/無効レコード混在）
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# stream_consumer モジュールをインポート可能にする
_project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_project_root))

import importlib.util

_handler_path = Path(__file__).resolve().parent.parent / "functions" / "stream_consumer" / "handler.py"
_spec = importlib.util.spec_from_file_location("retail_catalog_functions_stream_consumer", _handler_path)
_module = importlib.util.module_from_spec(_spec)
sys.modules["retail_catalog_functions_stream_consumer"] = _module
_spec.loader.exec_module(_module)

from retail_catalog_functions_stream_consumer import (
    handler,
    _validate_record,
)


# テスト用環境変数を設定
@pytest.fixture(autouse=True)
def env_vars(monkeypatch):
    """テスト用環境変数"""
    monkeypatch.setenv("STATE_TABLE_NAME", "test-state-table")
    monkeypatch.setenv("DEAD_LETTER_TABLE_NAME", "test-dead-letter-table")
    monkeypatch.setenv("IMAGE_TAGGING_FUNCTION", "test-image-tagging")
    monkeypatch.setenv("CATALOG_METADATA_FUNCTION", "test-catalog-metadata")
    monkeypatch.setenv("USE_CASE", "retail-catalog")
    monkeypatch.setenv("REGION", "ap-northeast-1")
    monkeypatch.setenv("ENABLE_XRAY", "false")


@pytest.fixture
def mock_context():
    """Lambda コンテキストモック"""
    context = MagicMock()
    context.aws_request_id = "test-request-id-456"
    context.function_name = "test-stream-consumer"
    return context


def _make_kinesis_record(data: dict, sequence_number: str = "seq-001") -> dict:
    """テスト用 Kinesis レコードを生成する"""
    encoded_data = base64.b64encode(json.dumps(data).encode("utf-8")).decode("utf-8")
    return {
        "kinesis": {
            "data": encoded_data,
            "sequenceNumber": sequence_number,
            "partitionKey": "test-partition",
        },
        "eventSource": "aws:kinesis",
    }


def _make_invalid_kinesis_record(raw_data: str = "not-json", sequence_number: str = "seq-bad") -> dict:
    """不正な Kinesis レコードを生成する"""
    encoded_data = base64.b64encode(raw_data.encode("utf-8")).decode("utf-8")
    return {
        "kinesis": {
            "data": encoded_data,
            "sequenceNumber": sequence_number,
            "partitionKey": "test-partition",
        },
        "eventSource": "aws:kinesis",
    }


class TestValidateRecord:
    """レコードスキーマバリデーションのテスト"""

    def test_valid_record(self):
        """必須フィールドが全て存在 → True"""
        record = {"key": "images/001.jpg", "event_type": "created", "timestamp": "2024-01-01T00:00:00Z"}
        assert _validate_record(record) is True

    def test_missing_key_field(self):
        """key フィールド欠落 → False"""
        record = {"event_type": "created", "timestamp": "2024-01-01T00:00:00Z"}
        assert _validate_record(record) is False

    def test_missing_event_type_field(self):
        """event_type フィールド欠落 → False"""
        record = {"key": "images/001.jpg", "timestamp": "2024-01-01T00:00:00Z"}
        assert _validate_record(record) is False

    def test_missing_timestamp_field(self):
        """timestamp フィールド欠落 → False"""
        record = {"key": "images/001.jpg", "event_type": "created"}
        assert _validate_record(record) is False

    def test_non_dict_input(self):
        """dict 以外の入力 → False"""
        assert _validate_record("not a dict") is False
        assert _validate_record(None) is False
        assert _validate_record([]) is False


class TestHandlerIntegration:
    """ハンドラ統合テスト（モック使用）"""

    @patch("retail_catalog_functions_stream_consumer.boto3")
    def test_valid_record_processes_successfully(self, mock_boto3, mock_context):
        """有効なレコード → 正常処理"""
        # DynamoDB モック
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}  # 未処理
        mock_table.update_item.return_value = {}
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_dynamodb.meta.client.exceptions.ConditionalCheckFailedException = Exception
        mock_boto3.resource.return_value = mock_dynamodb

        # Lambda client モック
        mock_lambda = MagicMock()
        mock_lambda.invoke.return_value = {
            "Payload": MagicMock(read=MagicMock(return_value=json.dumps({"status": "ok"}).encode()))
        }
        mock_boto3.client.return_value = mock_lambda

        event = {
            "Records": [
                _make_kinesis_record({
                    "key": "images/product/001.jpg",
                    "event_type": "created",
                    "timestamp": "2024-01-01T00:00:00Z",
                })
            ]
        }

        result = handler(event, mock_context)

        assert result["processed"] == 1
        assert result["invalid"] == 0
        assert result["failed"] == 0

    @patch("retail_catalog_functions_stream_consumer.boto3")
    def test_invalid_record_schema_discards_with_warning(self, mock_boto3, mock_context):
        """不正なレコードスキーマ → 破棄"""
        mock_dynamodb = MagicMock()
        mock_boto3.resource.return_value = mock_dynamodb
        mock_boto3.client.return_value = MagicMock()

        event = {
            "Records": [
                _make_kinesis_record({
                    "event_type": "created",
                    "timestamp": "2024-01-01T00:00:00Z",
                    # "key" フィールドが欠落
                })
            ]
        }

        result = handler(event, mock_context)

        assert result["invalid"] == 1
        assert result["processed"] == 0

    @patch("retail_catalog_functions_stream_consumer.boto3")
    def test_already_processed_record_skipped(self, mock_boto3, mock_context):
        """既に処理済みレコード → スキップ"""
        mock_table = MagicMock()
        # get_item で processing_status=completed を返す
        mock_table.get_item.return_value = {
            "Item": {
                "file_key": "images/001.jpg",
                "processing_status": "completed",
            }
        }
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb
        mock_boto3.client.return_value = MagicMock()

        event = {
            "Records": [
                _make_kinesis_record({
                    "key": "images/001.jpg",
                    "event_type": "modified",
                    "timestamp": "2024-01-01T00:00:00Z",
                })
            ]
        }

        result = handler(event, mock_context)

        assert result["skipped"] == 1
        assert result["processed"] == 0

    @patch("retail_catalog_functions_stream_consumer.boto3")
    def test_processing_error_writes_dead_letter(self, mock_boto3, mock_context):
        """処理エラー → dead-letter テーブルに書き込み"""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}  # 未処理
        mock_table.update_item.return_value = {}
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_dynamodb.meta.client.exceptions.ConditionalCheckFailedException = Exception
        mock_boto3.resource.return_value = mock_dynamodb

        # Lambda invoke が例外を投げる
        mock_lambda = MagicMock()
        mock_lambda.invoke.side_effect = Exception("Lambda invocation failed")
        mock_boto3.client.return_value = mock_lambda

        event = {
            "Records": [
                _make_kinesis_record({
                    "key": "images/error-file.jpg",
                    "event_type": "created",
                    "timestamp": "2024-01-01T00:00:00Z",
                })
            ]
        }

        result = handler(event, mock_context)

        assert result["failed"] == 1
        assert result["processed"] == 0
        # dead-letter テーブルに put_item が呼ばれたことを確認
        # (state テーブルと dead-letter テーブルの両方で Table が呼ばれる)
        assert mock_table.put_item.called

    @patch("retail_catalog_functions_stream_consumer.boto3")
    def test_batch_mixed_valid_invalid_records(self, mock_boto3, mock_context):
        """バッチ処理: 有効/無効レコード混在"""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}  # 未処理
        mock_table.update_item.return_value = {}
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_dynamodb.meta.client.exceptions.ConditionalCheckFailedException = Exception
        mock_boto3.resource.return_value = mock_dynamodb

        # Lambda client モック
        mock_lambda = MagicMock()
        mock_lambda.invoke.return_value = {
            "Payload": MagicMock(read=MagicMock(return_value=json.dumps({"status": "ok"}).encode()))
        }
        mock_boto3.client.return_value = mock_lambda

        event = {
            "Records": [
                # 有効レコード
                _make_kinesis_record(
                    {"key": "images/valid.jpg", "event_type": "created", "timestamp": "2024-01-01T00:00:00Z"},
                    sequence_number="seq-001",
                ),
                # 無効レコード（key 欠落）
                _make_kinesis_record(
                    {"event_type": "created", "timestamp": "2024-01-01T00:00:00Z"},
                    sequence_number="seq-002",
                ),
                # 不正 JSON
                _make_invalid_kinesis_record("not-json", sequence_number="seq-003"),
                # deleted イベント（処理対象外）
                _make_kinesis_record(
                    {"key": "images/deleted.jpg", "event_type": "deleted", "timestamp": "2024-01-01T00:00:00Z"},
                    sequence_number="seq-004",
                ),
            ]
        }

        result = handler(event, mock_context)

        assert result["total"] == 4
        assert result["processed"] == 1  # valid.jpg のみ
        assert result["invalid"] == 2    # key 欠落 + 不正 JSON
        assert result["skipped"] == 1    # deleted イベント
        assert result["failed"] == 0
