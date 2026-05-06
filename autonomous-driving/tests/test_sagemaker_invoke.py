"""Unit Tests for SageMaker Invoke Lambda (UC9 Phase 3)

MOCK_MODE=true/false の動作、Task_Token 伝播をテストする。
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
os.environ["OUTPUT_BUCKET"] = "test-output-bucket"
os.environ["MOCK_MODE"] = "true"
os.environ["SAGEMAKER_MODEL_NAME"] = "test-model"
os.environ["SAGEMAKER_INSTANCE_TYPE"] = "ml.m5.xlarge"
os.environ["USE_CASE"] = "autonomous-driving"
os.environ["REGION"] = "ap-northeast-1"
os.environ["ENABLE_XRAY"] = "false"

from functions.sagemaker_invoke.handler import (
    generate_mock_segmentation,
    _handle_mock_mode,
    _handle_real_mode,
    handler,
)


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


class TestHandleRealMode:
    """_handle_real_mode のテスト"""

    def test_real_mode_creates_transform_job(self):
        """MOCK_MODE=false: CreateTransformJob を呼ぶ"""
        event = {
            "task_token": "real-token-456",
            "input_s3_path": "s3://input-bucket/lidar-data/",
            "point_count": 1000,
        }

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
            assert call_kwargs["TransformInput"]["DataSource"]["S3DataSource"]["S3Uri"] == "s3://input-bucket/lidar-data/"

            # Task_Token がタグとして渡されていることを確認
            tags = call_kwargs["Tags"]
            token_tag = next(t for t in tags if t["Key"] == "TaskToken")
            assert token_tag["Value"] == "real-token-456"

            # 結果の検証
            assert result["status"] == "JOB_CREATED"
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
        }):
            with patch("functions.sagemaker_invoke.handler.boto3") as mock_boto3:
                mock_sagemaker = MagicMock()
                mock_boto3.client.return_value = mock_sagemaker

                _handle_real_mode(event, "token", "bucket")

                call_kwargs = mock_sagemaker.create_transform_job.call_args[1]
                assert call_kwargs["ModelName"] == "custom-model"
                assert call_kwargs["TransformResources"]["InstanceType"] == "ml.p3.2xlarge"


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
