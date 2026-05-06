"""Unit Tests for SageMaker Invoke Lambda (UC9 Phase 3 + Phase 4)

MOCK_MODE=true/false の動作、Task_Token 伝播をテストする。
Phase 4: TOKEN_STORAGE_MODE="dynamodb" / "direct" の分岐テストを追加。
"""

from __future__ import annotations

import json
import logging
import os
import sys
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

# shared モジュールと UC9 関数のパスを追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 環境変数設定
os.environ["OUTPUT_BUCKET"] = "test-output-bucket"
os.environ["MOCK_MODE"] = "true"
os.environ["SAGEMAKER_MODEL_NAME"] = "test-model"
os.environ["SAGEMAKER_INSTANCE_TYPE"] = "ml.m5.xlarge"
os.environ["USE_CASE"] = "autonomous-driving"
os.environ["REGION"] = "ap-northeast-1"
os.environ["ENABLE_XRAY"] = "false"

from shared.exceptions import TokenStorageError
from functions.sagemaker_invoke.handler import (
    generate_mock_segmentation,
    _handle_mock_mode,
    _handle_real_mode,
    _build_job_tags,
    handler,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TABLE_NAME = "test-task-token-store"
REGION = "ap-northeast-1"


def _create_token_table(dynamodb_resource):
    """Create the Task Token Store DynamoDB table for testing."""
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


# ---------------------------------------------------------------------------
# Phase 3 Tests (preserved)
# ---------------------------------------------------------------------------


class TestGenerateMockSegmentation:
    """generate_mock_segmentation のテスト"""

    def test_returns_correct_count(self):
        """指定した point_count と同数のラベルを返す"""
        labels = generate_mock_segmentation(100)
        assert len(labels) == 100

    def test_returns_empty_for_zero(self):
        """point_count=0 の場合は空リストを返す"""
        labels = generate_mock_segmentation(0)
        assert labels == []

    def test_labels_in_valid_range(self):
        """全ラベルが 0-9 の範囲内"""
        labels = generate_mock_segmentation(1000)
        for label in labels:
            assert 0 <= label <= 9


class TestHandleMockMode:
    """_handle_mock_mode のテスト"""

    def test_mock_mode_writes_to_s3_and_sends_task_success(self):
        """MOCK_MODE=true: S3 に出力を書き込み、SendTaskSuccess を呼ぶ"""
        event = {
            "task_token": "test-token-123",
            "input_s3_path": "s3://input-bucket/data/",
            "point_count": 500,
        }

        with patch("functions.sagemaker_invoke.handler.boto3") as mock_boto3:
            mock_s3 = MagicMock()
            mock_sfn = MagicMock()
            mock_boto3.client.side_effect = lambda service, **kwargs: {
                "s3": mock_s3,
                "stepfunctions": mock_sfn,
            }[service]

            result = _handle_mock_mode(event, "test-token-123", "test-output-bucket")

            # S3 に書き込まれたことを確認
            mock_s3.put_object.assert_called_once()
            s3_call = mock_s3.put_object.call_args[1]
            assert s3_call["Bucket"] == "test-output-bucket"
            assert "sagemaker-output/" in s3_call["Key"]

            # S3 に書き込まれたデータの検証
            body = json.loads(s3_call["Body"])
            assert body["point_count"] == 500
            assert len(body["labels"]) == 500

            # SendTaskSuccess が呼ばれたことを確認
            mock_sfn.send_task_success.assert_called_once()
            sfn_call = mock_sfn.send_task_success.call_args[1]
            assert sfn_call["taskToken"] == "test-token-123"

            output = json.loads(sfn_call["output"])
            assert output["status"] == "COMPLETED"
            assert output["point_count"] == 500

    def test_mock_mode_task_token_propagation(self):
        """MOCK_MODE=true: Task_Token が正確に伝播される"""
        token = "complex-token-with-special-chars_/+=abc123"
        event = {
            "task_token": token,
            "input_s3_path": "s3://bucket/path/",
            "point_count": 10,
        }

        with patch("functions.sagemaker_invoke.handler.boto3") as mock_boto3:
            mock_s3 = MagicMock()
            mock_sfn = MagicMock()
            mock_boto3.client.side_effect = lambda service, **kwargs: {
                "s3": mock_s3,
                "stepfunctions": mock_sfn,
            }[service]

            _handle_mock_mode(event, token, "bucket")

            sfn_call = mock_sfn.send_task_success.call_args[1]
            assert sfn_call["taskToken"] == token


class TestHandleRealModeDirectMode:
    """_handle_real_mode のテスト（Direct モード — Phase 3 互換）"""

    def test_real_mode_creates_transform_job(self):
        """MOCK_MODE=false, Direct モード: CreateTransformJob を呼ぶ"""
        event = {
            "task_token": "real-token-456",
            "input_s3_path": "s3://input-bucket/lidar-data/",
            "point_count": 1000,
        }

        with patch.dict(os.environ, {"TOKEN_STORAGE_MODE": "direct"}):
            with patch("functions.sagemaker_invoke.handler.boto3") as mock_boto3:
                mock_sagemaker = MagicMock()
                mock_boto3.client.return_value = mock_sagemaker

                result = _handle_real_mode(event, "real-token-456", "output-bucket")

                # CreateTransformJob が呼ばれたことを確認
                mock_sagemaker.create_transform_job.assert_called_once()
                call_kwargs = mock_sagemaker.create_transform_job.call_args[1]

                # ジョブパラメータの検証
                assert call_kwargs["ModelName"] == "test-model"
                assert call_kwargs["TransformResources"]["InstanceType"] == "ml.m5.xlarge"
                assert (
                    call_kwargs["TransformInput"]["DataSource"]["S3DataSource"]["S3Uri"]
                    == "s3://input-bucket/lidar-data/"
                )

                # Direct モード: TaskToken タグが設定されている
                tags = call_kwargs["Tags"]
                token_tag = next(t for t in tags if t["Key"] == "TaskToken")
                assert token_tag["Value"] == "real-token-456"

                # CorrelationId タグは存在しない
                correlation_tags = [t for t in tags if t["Key"] == "CorrelationId"]
                assert len(correlation_tags) == 0

                # 結果の検証
                assert result["status"] == "JOB_CREATED"
                assert result["token_storage_mode"] == "direct"
                assert "job_name" in result

    def test_real_mode_uses_env_vars(self):
        """MOCK_MODE=false: 環境変数からモデル名とインスタンスタイプを取得"""
        event = {
            "task_token": "token",
            "input_s3_path": "s3://bucket/data/",
        }

        with patch.dict(os.environ, {
            "SAGEMAKER_MODEL_NAME": "custom-model",
            "SAGEMAKER_INSTANCE_TYPE": "ml.p3.2xlarge",
            "TOKEN_STORAGE_MODE": "direct",
        }):
            with patch("functions.sagemaker_invoke.handler.boto3") as mock_boto3:
                mock_sagemaker = MagicMock()
                mock_boto3.client.return_value = mock_sagemaker

                _handle_real_mode(event, "token", "bucket")

                call_kwargs = mock_sagemaker.create_transform_job.call_args[1]
                assert call_kwargs["ModelName"] == "custom-model"
                assert call_kwargs["TransformResources"]["InstanceType"] == "ml.p3.2xlarge"


# ---------------------------------------------------------------------------
# Phase 4 Tests: DynamoDB Mode
# ---------------------------------------------------------------------------


class TestHandleRealModeDynamoDBMode:
    """_handle_real_mode のテスト（DynamoDB モード — Phase 4）"""

    @mock_aws
    def test_dynamodb_mode_creates_correlation_id_tag(self):
        """DynamoDB モード: CorrelationId タグを設定する（TaskToken タグではない）"""
        # DynamoDB テーブル作成
        dynamodb = boto3.resource("dynamodb", region_name=REGION)
        _create_token_table(dynamodb)

        event = {
            "task_token": "dynamodb-mode-token-very-long-value-" * 20,
            "input_s3_path": "s3://input-bucket/lidar-data/",
            "point_count": 1000,
        }

        with patch.dict(os.environ, {
            "TOKEN_STORAGE_MODE": "dynamodb",
            "TASK_TOKEN_TABLE_NAME": TABLE_NAME,
            "TOKEN_TTL_SECONDS": "86400",
        }):
            with patch("functions.sagemaker_invoke.handler.boto3") as mock_boto3:
                mock_sagemaker = MagicMock()
                mock_boto3.client.return_value = mock_sagemaker
                # boto3.resource should use real DynamoDB (moto)
                mock_boto3.resource.return_value = dynamodb

                # Patch TaskTokenStore to use moto DynamoDB
                with patch(
                    "functions.sagemaker_invoke.handler.TaskTokenStore"
                ) as MockStore:
                    mock_store_instance = MagicMock()
                    mock_store_instance.store_token.return_value = "abcd1234"
                    MockStore.return_value = mock_store_instance

                    result = _handle_real_mode(
                        event,
                        "dynamodb-mode-token-very-long-value-" * 20,
                        "output-bucket",
                    )

                    # CreateTransformJob が呼ばれたことを確認
                    mock_sagemaker.create_transform_job.assert_called_once()
                    call_kwargs = mock_sagemaker.create_transform_job.call_args[1]

                    # DynamoDB モード: CorrelationId タグが設定されている
                    tags = call_kwargs["Tags"]
                    correlation_tags = [t for t in tags if t["Key"] == "CorrelationId"]
                    assert len(correlation_tags) == 1
                    assert correlation_tags[0]["Value"] == "abcd1234"

                    # TaskToken タグは存在しない
                    token_tags = [t for t in tags if t["Key"] == "TaskToken"]
                    assert len(token_tags) == 0

                    # 結果の検証
                    assert result["status"] == "JOB_CREATED"
                    assert result["token_storage_mode"] == "dynamodb"
                    assert result["correlation_id"] == "abcd1234"

    def test_direct_mode_creates_task_token_tag(self):
        """Direct モード: TaskToken タグを設定する（CorrelationId タグではない）"""
        event = {
            "task_token": "direct-mode-token",
            "input_s3_path": "s3://input-bucket/data/",
        }

        with patch.dict(os.environ, {"TOKEN_STORAGE_MODE": "direct"}):
            with patch("functions.sagemaker_invoke.handler.boto3") as mock_boto3:
                mock_sagemaker = MagicMock()
                mock_boto3.client.return_value = mock_sagemaker

                result = _handle_real_mode(event, "direct-mode-token", "output-bucket")

                call_kwargs = mock_sagemaker.create_transform_job.call_args[1]
                tags = call_kwargs["Tags"]

                # Direct モード: TaskToken タグが設定されている
                token_tags = [t for t in tags if t["Key"] == "TaskToken"]
                assert len(token_tags) == 1
                assert token_tags[0]["Value"] == "direct-mode-token"

                # CorrelationId タグは存在しない
                correlation_tags = [t for t in tags if t["Key"] == "CorrelationId"]
                assert len(correlation_tags) == 0


class TestBuildJobTags:
    """_build_job_tags のテスト"""

    def test_direct_mode_returns_task_token_tag(self):
        """Direct モード: TaskToken タグを含むタグリストを返す"""
        tags, correlation_id = _build_job_tags("direct", "my-token", "job-1")

        assert correlation_id is None
        token_tags = [t for t in tags if t["Key"] == "TaskToken"]
        assert len(token_tags) == 1
        assert token_tags[0]["Value"] == "my-token"

    @mock_aws
    def test_dynamodb_mode_returns_correlation_id_tag(self):
        """DynamoDB モード: CorrelationId タグを含むタグリストを返す"""
        dynamodb = boto3.resource("dynamodb", region_name=REGION)
        _create_token_table(dynamodb)

        with patch.dict(os.environ, {
            "TASK_TOKEN_TABLE_NAME": TABLE_NAME,
            "TOKEN_TTL_SECONDS": "86400",
        }):
            tags, correlation_id = _build_job_tags(
                "dynamodb", "my-long-token", "job-1"
            )

            assert correlation_id is not None
            assert len(correlation_id) == 8
            correlation_tags = [t for t in tags if t["Key"] == "CorrelationId"]
            assert len(correlation_tags) == 1
            assert correlation_tags[0]["Value"] == correlation_id

    def test_dynamodb_mode_raises_without_table_name(self):
        """DynamoDB モード: TASK_TOKEN_TABLE_NAME 未設定で TokenStorageError"""
        with patch.dict(os.environ, {}, clear=False):
            # Remove TASK_TOKEN_TABLE_NAME if it exists
            os.environ.pop("TASK_TOKEN_TABLE_NAME", None)

            with pytest.raises(TokenStorageError):
                _build_job_tags("dynamodb", "token", "job")


class TestTaskTokenNotInLogs:
    """Task Token がログに出力されないことのテスト"""

    def test_task_token_never_appears_in_logs(self, caplog):
        """task_token の値がログ出力に含まれない"""
        secret_token = "SUPER_SECRET_TOKEN_VALUE_12345_MUST_NOT_APPEAR"
        event = {
            "task_token": secret_token,
            "input_s3_path": "s3://bucket/data/",
            "point_count": 10,
        }

        with caplog.at_level(logging.DEBUG):
            with patch.dict(os.environ, {
                "MOCK_MODE": "true",
                "TOKEN_STORAGE_MODE": "direct",
            }):
                with patch("functions.sagemaker_invoke.handler.boto3") as mock_boto3:
                    mock_s3 = MagicMock()
                    mock_sfn = MagicMock()
                    mock_boto3.client.side_effect = lambda service, **kwargs: {
                        "s3": mock_s3,
                        "stepfunctions": mock_sfn,
                    }[service]

                    _handle_mock_mode(event, secret_token, "bucket")

        # ログ出力に secret_token が含まれていないことを確認
        all_logs = " ".join(record.message for record in caplog.records)
        assert secret_token not in all_logs


# ---------------------------------------------------------------------------
# Handler Integration Tests
# ---------------------------------------------------------------------------


class TestHandler:
    """handler 関数の統合テスト"""

    def test_handler_mock_mode(self):
        """handler: MOCK_MODE=true で正常動作"""
        event = {
            "task_token": "handler-token",
            "input_s3_path": "s3://bucket/input/",
            "point_count": 50,
        }
        context = MagicMock()
        context.aws_request_id = "test-request-id"
        context.function_name = "test-function"

        with patch.dict(os.environ, {"MOCK_MODE": "true"}):
            with patch("functions.sagemaker_invoke.handler.boto3") as mock_boto3:
                mock_s3 = MagicMock()
                mock_sfn = MagicMock()
                mock_boto3.client.side_effect = lambda service, **kwargs: {
                    "s3": mock_s3,
                    "stepfunctions": mock_sfn,
                }[service]

                result = handler(event, context)

                assert result["status"] == "COMPLETED"
                mock_sfn.send_task_success.assert_called_once()

    def test_handler_dynamodb_mode(self):
        """handler: TOKEN_STORAGE_MODE=dynamodb で正常動作"""
        event = {
            "task_token": "handler-dynamodb-token",
            "input_s3_path": "s3://bucket/input/",
            "point_count": 50,
        }
        context = MagicMock()
        context.aws_request_id = "test-request-id"
        context.function_name = "test-function"

        with patch.dict(os.environ, {
            "MOCK_MODE": "false",
            "TOKEN_STORAGE_MODE": "dynamodb",
            "TASK_TOKEN_TABLE_NAME": TABLE_NAME,
            "TOKEN_TTL_SECONDS": "86400",
        }):
            with patch("functions.sagemaker_invoke.handler.boto3") as mock_boto3:
                mock_sagemaker = MagicMock()
                mock_boto3.client.return_value = mock_sagemaker

                with patch(
                    "functions.sagemaker_invoke.handler.TaskTokenStore"
                ) as MockStore:
                    mock_store_instance = MagicMock()
                    mock_store_instance.store_token.return_value = "ef012345"
                    MockStore.return_value = mock_store_instance

                    result = handler(event, context)

                    assert result["status"] == "JOB_CREATED"
                    assert result["token_storage_mode"] == "dynamodb"
                    assert result["correlation_id"] == "ef012345"

    def test_handler_direct_mode(self):
        """handler: TOKEN_STORAGE_MODE=direct で Phase 3 動作を維持"""
        event = {
            "task_token": "handler-direct-token",
            "input_s3_path": "s3://bucket/input/",
            "point_count": 50,
        }
        context = MagicMock()
        context.aws_request_id = "test-request-id"
        context.function_name = "test-function"

        with patch.dict(os.environ, {
            "MOCK_MODE": "false",
            "TOKEN_STORAGE_MODE": "direct",
        }):
            with patch("functions.sagemaker_invoke.handler.boto3") as mock_boto3:
                mock_sagemaker = MagicMock()
                mock_boto3.client.return_value = mock_sagemaker

                result = handler(event, context)

                assert result["status"] == "JOB_CREATED"
                assert result["token_storage_mode"] == "direct"
                assert "correlation_id" not in result
