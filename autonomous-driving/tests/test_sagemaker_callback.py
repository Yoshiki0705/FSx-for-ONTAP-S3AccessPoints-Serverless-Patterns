"""Unit Tests for SageMaker Callback Lambda (UC9 Phase 3)

Success/Failure コールバック、Task_Token 抽出をテストする。
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# shared モジュールと UC9 関数のパスを追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 環境変数設定
os.environ["USE_CASE"] = "autonomous-driving"
os.environ["REGION"] = "ap-northeast-1"
os.environ["ENABLE_XRAY"] = "false"

from functions.sagemaker_callback.handler import (
    extract_task_token_from_tags,
    handle_job_success,
    handle_job_failure,
    handler,
)


class TestExtractTaskTokenFromTags:
    """extract_task_token_from_tags のテスト"""

    def test_extracts_token_from_tags(self):
        """ジョブタグから TaskToken を正しく取得する"""
        mock_sagemaker = MagicMock()
        mock_sagemaker.describe_transform_job.return_value = {
            "TransformJobArn": "arn:aws:sagemaker:ap-northeast-1:123456789012:transform-job/test-job",
        }
        mock_sagemaker.list_tags.return_value = {
            "Tags": [
                {"Key": "UseCase", "Value": "autonomous-driving"},
                {"Key": "TaskToken", "Value": "my-task-token-123"},
                {"Key": "Phase", "Value": "3"},
            ]
        }

        token = extract_task_token_from_tags(mock_sagemaker, "test-job")
        assert token == "my-task-token-123"

    def test_returns_none_when_no_token_tag(self):
        """TaskToken タグが存在しない場合は None を返す"""
        mock_sagemaker = MagicMock()
        mock_sagemaker.describe_transform_job.return_value = {
            "TransformJobArn": "arn:aws:sagemaker:ap-northeast-1:123456789012:transform-job/test-job",
        }
        mock_sagemaker.list_tags.return_value = {
            "Tags": [
                {"Key": "UseCase", "Value": "autonomous-driving"},
            ]
        }

        token = extract_task_token_from_tags(mock_sagemaker, "test-job")
        assert token is None

    def test_returns_none_on_exception(self):
        """例外発生時は None を返す"""
        mock_sagemaker = MagicMock()
        mock_sagemaker.describe_transform_job.side_effect = Exception("API error")

        token = extract_task_token_from_tags(mock_sagemaker, "test-job")
        assert token is None



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
        """エラーメッセージが非空であることを確認"""
        mock_sfn = MagicMock()

        handle_job_failure(mock_sfn, "token", "job-name", "")

        call_kwargs = mock_sfn.send_task_failure.call_args[1]
        # 空メッセージの場合はフォールバックメッセージが使われる
        assert len(call_kwargs["cause"]) > 0


class TestHandler:
    """handler 関数の統合テスト"""

    def test_handler_completed_job(self):
        """handler: Completed ジョブで SendTaskSuccess を呼ぶ"""
        event = {
            "detail": {
                "TransformJobName": "test-job-completed",
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
                "Tags": [{"Key": "TaskToken", "Value": "callback-token"}]
            }

            mock_boto3.client.side_effect = lambda service, **kwargs: {
                "sagemaker": mock_sagemaker,
                "stepfunctions": mock_sfn,
            }[service]

            result = handler(event, context)

            assert result["action"] == "SendTaskSuccess"
            mock_sfn.send_task_success.assert_called_once()

    def test_handler_failed_job(self):
        """handler: Failed ジョブで SendTaskFailure を呼ぶ"""
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
            mock_sfn.send_task_failure.assert_called_once()
            call_kwargs = mock_sfn.send_task_failure.call_args[1]
            assert call_kwargs["taskToken"] == "fail-token"
            assert "Model inference error" in call_kwargs["cause"]

    def test_handler_missing_task_token(self):
        """handler: TaskToken が見つからない場合はエラーを返す"""
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
            assert "TaskToken not found" in result["error"]
