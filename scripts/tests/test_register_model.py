"""Unit Tests for register_model.py (Phase 4 — Model Registry)

SageMaker Model Registry 操作スクリプトのユニットテスト。
- register_model: モデル登録
- approve_model: 承認ステータス更新
- list_model_versions: バージョン一覧取得
- メトリクス付き/なし登録
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# パス設定
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from register_model import (
    register_model,
    approve_model,
    list_model_versions,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MODEL_PACKAGE_GROUP = "test-point-cloud-segmentation"
MODEL_URL = "s3://test-bucket/models/model.tar.gz"
IMAGE_URI = "763104351884.dkr.ecr.ap-northeast-1.amazonaws.com/pytorch-inference:2.0-cpu-py310"
MODEL_PACKAGE_ARN = (
    "arn:aws:sagemaker:ap-northeast-1:123456789012:model-package/test-group/1"
)


# ---------------------------------------------------------------------------
# Tests: register_model
# ---------------------------------------------------------------------------


class TestRegisterModel:
    """register_model 関数のテスト"""

    def test_register_model_success(self):
        """正常なモデル登録が成功する"""
        mock_client = MagicMock()
        mock_client.create_model_package.return_value = {
            "ModelPackageArn": MODEL_PACKAGE_ARN,
        }

        result = register_model(
            sagemaker_client=mock_client,
            model_package_group_name=MODEL_PACKAGE_GROUP,
            model_url=MODEL_URL,
            image_uri=IMAGE_URI,
            description="Test model v1",
        )

        assert result["ModelPackageArn"] == MODEL_PACKAGE_ARN
        mock_client.create_model_package.assert_called_once()

        # API 呼び出しパラメータの検証
        call_kwargs = mock_client.create_model_package.call_args[1]
        assert call_kwargs["ModelPackageGroupName"] == MODEL_PACKAGE_GROUP
        assert call_kwargs["ModelApprovalStatus"] == "PendingManualApproval"
        assert call_kwargs["ModelPackageDescription"] == "Test model v1"

        # InferenceSpecification の検証
        inference_spec = call_kwargs["InferenceSpecification"]
        assert inference_spec["Containers"][0]["Image"] == IMAGE_URI
        assert inference_spec["Containers"][0]["ModelDataUrl"] == MODEL_URL
        assert "application/json" in inference_spec["SupportedContentTypes"]

    def test_register_with_accuracy_and_loss_metrics(self):
        """精度・損失メトリクス付きでモデルを登録する"""
        mock_client = MagicMock()
        mock_client.create_model_package.return_value = {
            "ModelPackageArn": MODEL_PACKAGE_ARN,
        }

        result = register_model(
            sagemaker_client=mock_client,
            model_package_group_name=MODEL_PACKAGE_GROUP,
            model_url=MODEL_URL,
            image_uri=IMAGE_URI,
            accuracy=0.95,
            loss=0.05,
        )

        assert result["ModelPackageArn"] == MODEL_PACKAGE_ARN

        call_kwargs = mock_client.create_model_package.call_args[1]
        # CustomerMetadataProperties にメトリクスが含まれる
        metadata = call_kwargs["CustomerMetadataProperties"]
        assert metadata["accuracy"] == "0.95"
        assert metadata["loss"] == "0.05"
        assert metadata["use_case"] == "autonomous-driving"
        assert metadata["phase"] == "4"

    def test_register_without_optional_metrics(self):
        """オプションメトリクスなしでモデルを登録する"""
        mock_client = MagicMock()
        mock_client.create_model_package.return_value = {
            "ModelPackageArn": MODEL_PACKAGE_ARN,
        }

        result = register_model(
            sagemaker_client=mock_client,
            model_package_group_name=MODEL_PACKAGE_GROUP,
            model_url=MODEL_URL,
            image_uri=IMAGE_URI,
            accuracy=None,
            loss=None,
        )

        assert result["ModelPackageArn"] == MODEL_PACKAGE_ARN

        call_kwargs = mock_client.create_model_package.call_args[1]
        metadata = call_kwargs["CustomerMetadataProperties"]
        # accuracy/loss キーが含まれない
        assert "accuracy" not in metadata
        assert "loss" not in metadata

    def test_register_with_custom_content_types(self):
        """カスタム Content-Type でモデルを登録する"""
        mock_client = MagicMock()
        mock_client.create_model_package.return_value = {
            "ModelPackageArn": MODEL_PACKAGE_ARN,
        }

        register_model(
            sagemaker_client=mock_client,
            model_package_group_name=MODEL_PACKAGE_GROUP,
            model_url=MODEL_URL,
            image_uri=IMAGE_URI,
            content_types=["application/x-npy"],
            response_types=["application/x-npy"],
        )

        call_kwargs = mock_client.create_model_package.call_args[1]
        inference_spec = call_kwargs["InferenceSpecification"]
        assert inference_spec["SupportedContentTypes"] == ["application/x-npy"]
        assert inference_spec["SupportedResponseMIMETypes"] == ["application/x-npy"]


# ---------------------------------------------------------------------------
# Tests: approve_model
# ---------------------------------------------------------------------------


class TestApproveModel:
    """approve_model 関数のテスト"""

    def test_approve_model_success(self):
        """モデル承認が成功する"""
        mock_client = MagicMock()
        mock_client.update_model_package.return_value = {
            "ModelPackageArn": MODEL_PACKAGE_ARN,
        }

        result = approve_model(
            sagemaker_client=mock_client,
            model_package_arn=MODEL_PACKAGE_ARN,
            approval_status="Approved",
            approval_description="Passed QA review",
        )

        assert result["ModelPackageArn"] == MODEL_PACKAGE_ARN
        mock_client.update_model_package.assert_called_once_with(
            ModelPackageArn=MODEL_PACKAGE_ARN,
            ModelApprovalStatus="Approved",
            ApprovalDescription="Passed QA review",
        )

    def test_reject_model(self):
        """モデル却下が成功する"""
        mock_client = MagicMock()
        mock_client.update_model_package.return_value = {
            "ModelPackageArn": MODEL_PACKAGE_ARN,
        }

        approve_model(
            sagemaker_client=mock_client,
            model_package_arn=MODEL_PACKAGE_ARN,
            approval_status="Rejected",
            approval_description="Failed accuracy threshold",
        )

        call_kwargs = mock_client.update_model_package.call_args[1]
        assert call_kwargs["ModelApprovalStatus"] == "Rejected"
        assert call_kwargs["ApprovalDescription"] == "Failed accuracy threshold"

    def test_approve_without_description(self):
        """説明なしで承認する"""
        mock_client = MagicMock()
        mock_client.update_model_package.return_value = {}

        approve_model(
            sagemaker_client=mock_client,
            model_package_arn=MODEL_PACKAGE_ARN,
        )

        call_kwargs = mock_client.update_model_package.call_args[1]
        assert call_kwargs["ModelPackageArn"] == MODEL_PACKAGE_ARN
        assert call_kwargs["ModelApprovalStatus"] == "Approved"
        # ApprovalDescription は空文字列の場合含まれない
        assert "ApprovalDescription" not in call_kwargs


# ---------------------------------------------------------------------------
# Tests: list_model_versions
# ---------------------------------------------------------------------------


class TestListModelVersions:
    """list_model_versions 関数のテスト"""

    def test_list_model_versions_success(self):
        """モデルバージョン一覧を取得する"""
        mock_client = MagicMock()
        mock_client.list_model_packages.return_value = {
            "ModelPackageSummaryList": [
                {
                    "ModelPackageArn": f"{MODEL_PACKAGE_ARN}/1",
                    "ModelApprovalStatus": "Approved",
                    "CreationTime": "2024-01-01T00:00:00Z",
                },
                {
                    "ModelPackageArn": f"{MODEL_PACKAGE_ARN}/2",
                    "ModelApprovalStatus": "PendingManualApproval",
                    "CreationTime": "2024-01-02T00:00:00Z",
                },
            ]
        }

        result = list_model_versions(
            sagemaker_client=mock_client,
            model_package_group_name=MODEL_PACKAGE_GROUP,
        )

        assert len(result) == 2
        assert result[0]["ModelApprovalStatus"] == "Approved"

        mock_client.list_model_packages.assert_called_once_with(
            ModelPackageGroupName=MODEL_PACKAGE_GROUP,
            MaxResults=10,
            SortBy="CreationTime",
            SortOrder="Descending",
        )

    def test_list_with_approval_status_filter(self):
        """承認ステータスでフィルタして一覧を取得する"""
        mock_client = MagicMock()
        mock_client.list_model_packages.return_value = {
            "ModelPackageSummaryList": [
                {
                    "ModelPackageArn": f"{MODEL_PACKAGE_ARN}/1",
                    "ModelApprovalStatus": "Approved",
                },
            ]
        }

        result = list_model_versions(
            sagemaker_client=mock_client,
            model_package_group_name=MODEL_PACKAGE_GROUP,
            approval_status="Approved",
            max_results=5,
        )

        assert len(result) == 1

        call_kwargs = mock_client.list_model_packages.call_args[1]
        assert call_kwargs["ModelApprovalStatus"] == "Approved"
        assert call_kwargs["MaxResults"] == 5

    def test_list_empty_results(self):
        """バージョンが存在しない場合は空リストを返す"""
        mock_client = MagicMock()
        mock_client.list_model_packages.return_value = {
            "ModelPackageSummaryList": []
        }

        result = list_model_versions(
            sagemaker_client=mock_client,
            model_package_group_name=MODEL_PACKAGE_GROUP,
        )

        assert result == []
