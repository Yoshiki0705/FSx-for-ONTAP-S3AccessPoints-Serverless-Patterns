"""Unit Tests for SageMaker Callback Lambda (UC9 Phase 3 + Phase 4)

Success/Failure コールバック、Token 取得モード検出をテストする。
Phase 4: DynamoDB モード（CorrelationId タグ）と Direct モード（TaskToken タグ）の
自動検出・切り替えテストを追加。

Broken imports from Phase 3 → Phase 4 refactoring are fixed:
- extract_task_token_from_tags → _get_tags_from_job + _detect_token_mode
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
os.environ["USE_CASE"] = "autonomous-driving"
os.environ["REGION"] = "ap-northeast-1"
os.environ["ENABLE_XRAY"] = "false"

from functions.sagemaker_callback.handler import (
    _get_tags_from_job,
    _detect_token_mode,
    _retrieve_token_from_dynamodb,
    _delete_token_from_dynamodb,
    _emit_orphaned_callback_metric,
    handle_job_success,
    handle_job_failure,
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
# Tests: _detect_token_mode (replaces extract_task_token_from_tags)
# ---------------------------------------------------------------------------


class TestDetectTokenMode:
    """_detect_token_mode のテスト"""

    def test_detects_dynamodb_mode_with_correlation_id_tag(self):
        """CorrelationId タグ存在時は DynamoDB モードを返す"""
        tags = [
            {"Key": "UseCase", "Value": "autonomous-driving"},
            {"Key": "CorrelationId", "Value": "abcd1234"},
            {"Key": "Phase", "Value": "4"},
        ]

        mode, value = _detect_token_mode(tags)
        assert mode == "dynamodb"
        assert value == "abcd1234"

    def test_detects_direct_mode_with_task_token_tag(self):
        """TaskToken タグ存在時は Direct モードを返す"""
        tags = [
            {"Key": "UseCase", "Value": "autonomous-driving"},
            {"Key": "TaskToken", "Value": "my-task-token-123"},
            {"Key": "Phase", "Value": "3"},
        ]

        mode, value = _detect_token_mode(tags)
        assert mode == "direct"
        assert value == "my-task-token-123"

    def test_returns_unknown_when_no_token_tags(self):
        """どちらのタグも存在しない場合は unknown を返す"""
        tags = [
            {"Key": "UseCase", "Value": "autonomous-driving"},
        ]

        mode, value = _detect_token_mode(tags)
        assert mode == "unknown"
        assert value is None

    def test_correlation_id_takes_priority_over_task_token(self):
        """両方のタグが存在する場合は CorrelationId が優先"""
        tags = [
            {"Key": "CorrelationId", "Value": "abcd1234"},
            {"Key": "TaskToken", "Value": "some-token"},
        ]

        mode, value = _detect_token_mode(tags)
        assert mode == "dynamodb"
        assert value == "abcd1234"


class TestGetTagsFromJob:
    """_get_tags_from_job のテスト"""

    def test_returns_tags_from_job(self):
        """ジョブからタグを正しく取得する"""
        mock_sagemaker = MagicMock()
        mock_sagemaker.describe_transform_job.return_value = {
            "TransformJobArn": "arn:aws:sagemaker:ap-northeast-1:123:transform-job/test-job",
        }
        mock_sagemaker.list_tags.return_value = {
            "Tags": [
                {"Key": "CorrelationId", "Value": "abcd1234"},
                {"Key": "UseCase", "Value": "autonomous-driving"},
            ]
        }

        tags = _get_tags_from_job(mock_sagemaker, "test-job")
        assert len(tags) == 2
        assert {"Key": "CorrelationId", "Value": "abcd1234"} in tags

    def test_returns_empty_on_exception(self):
        """例外発生時は空リストを返す"""
        mock_sagemaker = MagicMock()
        mock_sagemaker.describe_transform_job.side_effect = Exception("API error")

        tags = _get_tags_from_job(mock_sagemaker, "test-job")
        assert tags == []

    def test_returns_empty_when_no_arn(self):
        """TransformJobArn が空の場合は空リストを返す"""
        mock_sagemaker = MagicMock()
        mock_sagemaker.describe_transform_job.return_value = {
            "TransformJobArn": "",
        }

        tags = _get_tags_from_job(mock_sagemaker, "test-job")
        assert tags == []


# ---------------------------------------------------------------------------
# Tests: handle_job_success / handle_job_failure (Phase 3 preserved)
# ---------------------------------------------------------------------------


class TestHandleJobSuccess:
    """handle_job_success のテスト"""

    def test_calls_send_task_success(self):
        """ジョブ成功時に SendTaskSuccess を呼ぶ"""
        mock_sfn = MagicMock()

        result = handle_job_success(
            mock_sfn,
            task_token="success-token",
            job_name="test-job-success",
            output_s3_path="s3://output-bucket/results/",
        )

        mock_sfn.send_task_success.assert_called_once()
        call_kwargs = mock_sfn.send_task_success.call_args[1]
        assert call_kwargs["taskToken"] == "success-token"

        output = json.loads(call_kwargs["output"])
        assert output["status"] == "COMPLETED"
        assert output["job_name"] == "test-job-success"
        assert output["output_s3_path"] == "s3://output-bucket/results/"

        assert result["action"] == "SendTaskSuccess"

    def test_task_token_propagation(self):
        """Task_Token が正確に伝播される"""
        mock_sfn = MagicMock()
        token = "long-token-with-special-chars/+=abc"

        handle_job_success(mock_sfn, token, "job", "s3://bucket/")

        call_kwargs = mock_sfn.send_task_success.call_args[1]
        assert call_kwargs["taskToken"] == token


class TestHandleJobFailure:
    """handle_job_failure のテスト"""

    def test_calls_send_task_failure(self):
        """ジョブ失敗時に SendTaskFailure を呼ぶ"""
        mock_sfn = MagicMock()

        result = handle_job_failure(
            mock_sfn,
            task_token="failure-token",
            job_name="test-job-failed",
            error_message="Out of memory",
        )

        mock_sfn.send_task_failure.assert_called_once()
        call_kwargs = mock_sfn.send_task_failure.call_args[1]
        assert call_kwargs["taskToken"] == "failure-token"
        assert call_kwargs["error"] == "SageMakerTransformJobFailed"
        assert call_kwargs["cause"] == "Out of memory"

        assert result["action"] == "SendTaskFailure"

    def test_task_token_propagation_on_failure(self):
        """失敗時も Task_Token が正確に伝播される"""
        mock_sfn = MagicMock()
        token = "failure-specific-token-xyz"

        handle_job_failure(mock_sfn, token, "job", "error msg")

        call_kwargs = mock_sfn.send_task_failure.call_args[1]
        assert call_kwargs["taskToken"] == token

    def test_non_empty_error_message(self):
        """空エラーメッセージの場合はフォールバックメッセージが使われる"""
        mock_sfn = MagicMock()

        handle_job_failure(mock_sfn, "token", "job-name", "")

        call_kwargs = mock_sfn.send_task_failure.call_args[1]
        # 空メッセージの場合もフォールバックで非空
        assert len(call_kwargs["cause"]) > 0


# ---------------------------------------------------------------------------
# Phase 4 Tests: DynamoDB Mode Handler Integration
# ---------------------------------------------------------------------------


class TestHandlerDynamoDBMode:
    """handler: DynamoDB モード（CorrelationId タグ）のテスト"""

    def test_dynamodb_mode_success_callback(self):
        """CorrelationId タグ → DynamoDB モード → SendTaskSuccess"""
        event = {
            "detail": {
                "TransformJobName": "test-job-dynamodb",
                "TransformJobStatus": "Completed",
                "TransformOutput": {"S3OutputPath": "s3://output/results/"},
            }
        }
        context = MagicMock()
        context.aws_request_id = "test-request-id"
        context.function_name = "test-function"

        with patch.dict(os.environ, {"TASK_TOKEN_TABLE_NAME": TABLE_NAME}):
            with patch("functions.sagemaker_callback.handler.boto3") as mock_boto3:
                mock_sagemaker = MagicMock()
                mock_sfn = MagicMock()

                mock_sagemaker.describe_transform_job.return_value = {
                    "TransformJobArn": "arn:aws:sagemaker:ap-northeast-1:123:transform-job/test-job",
                }
                mock_sagemaker.list_tags.return_value = {
                    "Tags": [
                        {"Key": "CorrelationId", "Value": "abcd1234"},
                        {"Key": "UseCase", "Value": "autonomous-driving"},
                    ]
                }

                mock_boto3.client.side_effect = lambda service, **kwargs: {
                    "sagemaker": mock_sagemaker,
                    "stepfunctions": mock_sfn,
                }[service]

                with patch(
                    "functions.sagemaker_callback.handler._retrieve_token_from_dynamodb"
                ) as mock_retrieve:
                    mock_retrieve.return_value = "retrieved-task-token-from-ddb"

                    with patch(
                        "functions.sagemaker_callback.handler._delete_token_from_dynamodb"
                    ) as mock_delete:
                        result = handler(event, context)

                        assert result["action"] == "SendTaskSuccess"
                        assert result["token_mode"] == "dynamodb"
                        assert result["correlation_id"] == "abcd1234"

                        # SendTaskSuccess が正しい token で呼ばれた
                        mock_sfn.send_task_success.assert_called_once()
                        call_kwargs = mock_sfn.send_task_success.call_args[1]
                        assert call_kwargs["taskToken"] == "retrieved-task-token-from-ddb"

                        # DynamoDB レコードが削除された
                        mock_delete.assert_called_once_with("abcd1234")

    def test_dynamodb_mode_failure_callback(self):
        """CorrelationId タグ → DynamoDB モード → SendTaskFailure"""
        event = {
            "detail": {
                "TransformJobName": "test-job-failed-ddb",
                "TransformJobStatus": "Failed",
                "FailureReason": "Model inference error",
                "TransformOutput": {},
            }
        }
        context = MagicMock()
        context.aws_request_id = "test-request-id"
        context.function_name = "test-function"

        with patch.dict(os.environ, {"TASK_TOKEN_TABLE_NAME": TABLE_NAME}):
            with patch("functions.sagemaker_callback.handler.boto3") as mock_boto3:
                mock_sagemaker = MagicMock()
                mock_sfn = MagicMock()

                mock_sagemaker.describe_transform_job.return_value = {
                    "TransformJobArn": "arn:aws:sagemaker:ap-northeast-1:123:transform-job/test-job",
                }
                mock_sagemaker.list_tags.return_value = {
                    "Tags": [{"Key": "CorrelationId", "Value": "ef567890"}]
                }

                mock_boto3.client.side_effect = lambda service, **kwargs: {
                    "sagemaker": mock_sagemaker,
                    "stepfunctions": mock_sfn,
                }[service]

                with patch(
                    "functions.sagemaker_callback.handler._retrieve_token_from_dynamodb"
                ) as mock_retrieve:
                    mock_retrieve.return_value = "failure-token-from-ddb"

                    with patch(
                        "functions.sagemaker_callback.handler._delete_token_from_dynamodb"
                    ) as mock_delete:
                        result = handler(event, context)

                        assert result["action"] == "SendTaskFailure"
                        assert result["token_mode"] == "dynamodb"

                        mock_sfn.send_task_failure.assert_called_once()
                        call_kwargs = mock_sfn.send_task_failure.call_args[1]
                        assert call_kwargs["taskToken"] == "failure-token-from-ddb"
                        assert "Model inference error" in call_kwargs["cause"]

                        # DynamoDB レコードが削除された
                        mock_delete.assert_called_once_with("ef567890")


class TestHandlerDirectMode:
    """handler: Direct モード（TaskToken タグ — Phase 3 互換）のテスト"""

    def test_direct_mode_completed_job(self):
        """TaskToken タグ → Direct モード → SendTaskSuccess"""
        event = {
            "detail": {
                "TransformJobName": "test-job-direct",
                "TransformJobStatus": "Completed",
                "TransformOutput": {"S3OutputPath": "s3://output/results/"},
            }
        }
        context = MagicMock()
        context.aws_request_id = "test-request-id"
        context.function_name = "test-function"

        with patch("functions.sagemaker_callback.handler.boto3") as mock_boto3:
            mock_sagemaker = MagicMock()
            mock_sfn = MagicMock()

            mock_sagemaker.describe_transform_job.return_value = {
                "TransformJobArn": "arn:aws:sagemaker:ap-northeast-1:123:transform-job/test-job",
            }
            mock_sagemaker.list_tags.return_value = {
                "Tags": [{"Key": "TaskToken", "Value": "direct-callback-token"}]
            }

            mock_boto3.client.side_effect = lambda service, **kwargs: {
                "sagemaker": mock_sagemaker,
                "stepfunctions": mock_sfn,
            }[service]

            result = handler(event, context)

            assert result["action"] == "SendTaskSuccess"
            assert result["token_mode"] == "direct"
            mock_sfn.send_task_success.assert_called_once()
            call_kwargs = mock_sfn.send_task_success.call_args[1]
            assert call_kwargs["taskToken"] == "direct-callback-token"

    def test_direct_mode_failed_job(self):
        """TaskToken タグ → Direct モード → SendTaskFailure"""
        event = {
            "detail": {
                "TransformJobName": "test-job-failed",
                "TransformJobStatus": "Failed",
                "FailureReason": "Model inference error",
                "TransformOutput": {},
            }
        }
        context = MagicMock()
        context.aws_request_id = "test-request-id"
        context.function_name = "test-function"

        with patch("functions.sagemaker_callback.handler.boto3") as mock_boto3:
            mock_sagemaker = MagicMock()
            mock_sfn = MagicMock()

            mock_sagemaker.describe_transform_job.return_value = {
                "TransformJobArn": "arn:aws:sagemaker:ap-northeast-1:123:transform-job/test-job",
            }
            mock_sagemaker.list_tags.return_value = {
                "Tags": [{"Key": "TaskToken", "Value": "fail-token"}]
            }

            mock_boto3.client.side_effect = lambda service, **kwargs: {
                "sagemaker": mock_sagemaker,
                "stepfunctions": mock_sfn,
            }[service]

            result = handler(event, context)

            assert result["action"] == "SendTaskFailure"
            assert result["token_mode"] == "direct"
            mock_sfn.send_task_failure.assert_called_once()
            call_kwargs = mock_sfn.send_task_failure.call_args[1]
            assert call_kwargs["taskToken"] == "fail-token"
            assert "Model inference error" in call_kwargs["cause"]


class TestHandlerOrphanedCallback:
    """handler: OrphanedCallback メトリクスのテスト"""

    def test_orphaned_callback_metric_emitted_when_token_not_found(self):
        """DynamoDB モードで Token 未発見時に OrphanedCallback メトリクスを出力"""
        event = {
            "detail": {
                "TransformJobName": "test-job-orphaned",
                "TransformJobStatus": "Completed",
                "TransformOutput": {"S3OutputPath": "s3://output/results/"},
            }
        }
        context = MagicMock()
        context.aws_request_id = "test-request-id"
        context.function_name = "test-function"

        with patch.dict(os.environ, {"TASK_TOKEN_TABLE_NAME": TABLE_NAME}):
            with patch("functions.sagemaker_callback.handler.boto3") as mock_boto3:
                mock_sagemaker = MagicMock()
                mock_sfn = MagicMock()

                mock_sagemaker.describe_transform_job.return_value = {
                    "TransformJobArn": "arn:aws:sagemaker:ap-northeast-1:123:transform-job/test-job",
                }
                mock_sagemaker.list_tags.return_value = {
                    "Tags": [{"Key": "CorrelationId", "Value": "expired01"}]
                }

                mock_boto3.client.side_effect = lambda service, **kwargs: {
                    "sagemaker": mock_sagemaker,
                    "stepfunctions": mock_sfn,
                }[service]

                with patch(
                    "functions.sagemaker_callback.handler._retrieve_token_from_dynamodb"
                ) as mock_retrieve:
                    mock_retrieve.return_value = None  # Token not found

                    with patch(
                        "functions.sagemaker_callback.handler._emit_orphaned_callback_metric"
                    ) as mock_metric:
                        result = handler(event, context)

                        assert result["action"] == "ERROR"
                        assert "Token not found" in result["error"]

                        # OrphanedCallback メトリクスが出力された
                        mock_metric.assert_called_once_with(
                            "test-job-orphaned", "expired01"
                        )


class TestHandlerDynamoDBRecordDeletion:
    """handler: DynamoDB レコード削除のテスト"""

    def test_dynamodb_record_deleted_after_successful_callback(self):
        """コールバック成功後に DynamoDB レコードが削除される"""
        event = {
            "detail": {
                "TransformJobName": "test-job-cleanup",
                "TransformJobStatus": "Completed",
                "TransformOutput": {"S3OutputPath": "s3://output/results/"},
            }
        }
        context = MagicMock()
        context.aws_request_id = "test-request-id"
        context.function_name = "test-function"

        with patch.dict(os.environ, {"TASK_TOKEN_TABLE_NAME": TABLE_NAME}):
            with patch("functions.sagemaker_callback.handler.boto3") as mock_boto3:
                mock_sagemaker = MagicMock()
                mock_sfn = MagicMock()

                mock_sagemaker.describe_transform_job.return_value = {
                    "TransformJobArn": "arn:aws:sagemaker:ap-northeast-1:123:transform-job/test-job",
                }
                mock_sagemaker.list_tags.return_value = {
                    "Tags": [{"Key": "CorrelationId", "Value": "cleanup1"}]
                }

                mock_boto3.client.side_effect = lambda service, **kwargs: {
                    "sagemaker": mock_sagemaker,
                    "stepfunctions": mock_sfn,
                }[service]

                with patch(
                    "functions.sagemaker_callback.handler._retrieve_token_from_dynamodb"
                ) as mock_retrieve:
                    mock_retrieve.return_value = "token-to-cleanup"

                    with patch(
                        "functions.sagemaker_callback.handler._delete_token_from_dynamodb"
                    ) as mock_delete:
                        result = handler(event, context)

                        assert result["action"] == "SendTaskSuccess"
                        mock_delete.assert_called_once_with("cleanup1")


class TestHandlerNoTokenTag:
    """handler: タグなしのテスト"""

    def test_handler_missing_both_tags(self):
        """CorrelationId も TaskToken も見つからない場合はエラーを返す"""
        event = {
            "detail": {
                "TransformJobName": "test-job-no-token",
                "TransformJobStatus": "Completed",
                "TransformOutput": {},
            }
        }
        context = MagicMock()
        context.aws_request_id = "test-request-id"
        context.function_name = "test-function"

        with patch("functions.sagemaker_callback.handler.boto3") as mock_boto3:
            mock_sagemaker = MagicMock()
            mock_sagemaker.describe_transform_job.return_value = {
                "TransformJobArn": "arn:aws:sagemaker:ap-northeast-1:123:transform-job/test-job",
            }
            mock_sagemaker.list_tags.return_value = {"Tags": []}

            mock_boto3.client.side_effect = lambda service, **kwargs: {
                "sagemaker": mock_sagemaker,
                "stepfunctions": MagicMock(),
            }[service]

            result = handler(event, context)

            assert result["action"] == "ERROR"
            assert "No token tag found" in result["error"]


class TestTaskTokenNotInLogs:
    """Task Token がログに出力されないことのテスト"""

    def test_task_token_never_appears_in_callback_logs(self, caplog):
        """task_token の値がコールバックログ出力に含まれない"""
        secret_token = "CALLBACK_SECRET_TOKEN_MUST_NOT_APPEAR_IN_LOGS"

        with caplog.at_level(logging.DEBUG):
            mock_sfn = MagicMock()
            handle_job_success(
                mock_sfn,
                task_token=secret_token,
                job_name="test-job",
                output_s3_path="s3://bucket/output/",
            )

        all_logs = " ".join(record.message for record in caplog.records)
        assert secret_token not in all_logs

    def test_task_token_never_appears_in_failure_logs(self, caplog):
        """task_token の値が失敗ログ出力に含まれない"""
        secret_token = "FAILURE_SECRET_TOKEN_MUST_NOT_APPEAR"

        with caplog.at_level(logging.DEBUG):
            mock_sfn = MagicMock()
            handle_job_failure(
                mock_sfn,
                task_token=secret_token,
                job_name="test-job",
                error_message="some error",
            )

        all_logs = " ".join(record.message for record in caplog.records)
        assert secret_token not in all_logs
