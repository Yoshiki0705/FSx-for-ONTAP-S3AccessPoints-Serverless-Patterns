"""FsxHelper ユニットテスト

FsxHelper の動作を検証するユニットテスト。
unittest.mock を使用して boto3 クライアント（FSx, CloudWatch）をモックする。

Validates: Requirements 12.1
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from shared.fsx_helper import FsxHelper, FsxHelperError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session():
    """モック boto3.Session を返す"""
    session = MagicMock()
    fsx_client = MagicMock()
    cw_client = MagicMock()

    def client_factory(service_name, **kwargs):
        if service_name == "fsx":
            return fsx_client
        elif service_name == "cloudwatch":
            return cw_client
        return MagicMock()

    session.client.side_effect = client_factory
    session._fsx_client = fsx_client
    session._cw_client = cw_client
    return session


@pytest.fixture
def helper(mock_session) -> FsxHelper:
    """テスト用 FsxHelper インスタンスを返す"""
    return FsxHelper(session=mock_session)


def _make_client_error(code: str = "FileSystemNotFound", message: str = "Not found", operation: str = "DescribeFileSystems") -> ClientError:
    """テスト用 ClientError を生成する"""
    return ClientError(
        {"Error": {"Code": code, "Message": message}},
        operation,
    )


# ---------------------------------------------------------------------------
# TestFsxHelper
# ---------------------------------------------------------------------------


class TestFsxHelper:
    """FsxHelper のテスト"""

    def test_describe_file_systems(self, helper: FsxHelper):
        """describe_file_systems がファイルシステムのリストを返すことを検証する"""
        paginator = MagicMock()
        paginator.paginate.return_value = [
            {"FileSystems": [{"FileSystemId": "fs-001"}, {"FileSystemId": "fs-002"}]},
        ]
        helper._fsx_client.get_paginator.return_value = paginator

        result = helper.describe_file_systems()

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["FileSystemId"] == "fs-001"
        assert result[1]["FileSystemId"] == "fs-002"
        helper._fsx_client.get_paginator.assert_called_once_with("describe_file_systems")

    def test_describe_file_systems_with_ids(self, helper: FsxHelper):
        """filesystem_ids パラメータが正しく渡されることを検証する"""
        paginator = MagicMock()
        paginator.paginate.return_value = [
            {"FileSystems": [{"FileSystemId": "fs-001"}]},
        ]
        helper._fsx_client.get_paginator.return_value = paginator

        result = helper.describe_file_systems(filesystem_ids=["fs-001"])

        assert len(result) == 1
        paginator.paginate.assert_called_once_with(FileSystemIds=["fs-001"])

    def test_describe_volumes(self, helper: FsxHelper):
        """describe_volumes がボリュームのリストを返すことを検証する"""
        paginator = MagicMock()
        paginator.paginate.return_value = [
            {"Volumes": [{"VolumeId": "fsvol-001"}, {"VolumeId": "fsvol-002"}]},
        ]
        helper._fsx_client.get_paginator.return_value = paginator

        result = helper.describe_volumes()

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["VolumeId"] == "fsvol-001"
        assert result[1]["VolumeId"] == "fsvol-002"
        helper._fsx_client.get_paginator.assert_called_once_with("describe_volumes")

    def test_describe_volumes_with_filters(self, helper: FsxHelper):
        """filters パラメータが正しく渡されることを検証する"""
        paginator = MagicMock()
        paginator.paginate.return_value = [
            {"Volumes": [{"VolumeId": "fsvol-001"}]},
        ]
        helper._fsx_client.get_paginator.return_value = paginator

        filters = [{"Name": "file-system-id", "Values": ["fs-001"]}]
        result = helper.describe_volumes(filters=filters)

        assert len(result) == 1
        paginator.paginate.assert_called_once_with(Filters=filters)

    def test_describe_storage_virtual_machines(self, helper: FsxHelper):
        """describe_storage_virtual_machines が SVM のリストを返すことを検証する"""
        paginator = MagicMock()
        paginator.paginate.return_value = [
            {
                "StorageVirtualMachines": [
                    {"StorageVirtualMachineId": "svm-001"},
                    {"StorageVirtualMachineId": "svm-002"},
                ],
            },
        ]
        helper._fsx_client.get_paginator.return_value = paginator

        result = helper.describe_storage_virtual_machines()

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["StorageVirtualMachineId"] == "svm-001"
        assert result[1]["StorageVirtualMachineId"] == "svm-002"
        helper._fsx_client.get_paginator.assert_called_once_with(
            "describe_storage_virtual_machines"
        )

    def test_fsx_api_error_wraps_client_error(self, helper: FsxHelper):
        """FSx API の ClientError が FsxHelperError にラップされ、original_error 属性を持つことを検証する"""
        original_error = _make_client_error(
            code="FileSystemNotFound",
            message="File system fs-999 not found",
            operation="DescribeFileSystems",
        )
        paginator = MagicMock()
        paginator.paginate.side_effect = original_error
        helper._fsx_client.get_paginator.return_value = paginator

        with pytest.raises(FsxHelperError) as exc_info:
            helper.describe_file_systems(filesystem_ids=["fs-999"])

        assert exc_info.value.original_error is original_error
        assert "Failed to describe file systems" in str(exc_info.value)

    def test_get_storage_metrics(self, helper: FsxHelper):
        """get_storage_metrics が 3 つのメトリクスキーを含む dict を返すことを検証する"""
        helper._cw_client.get_metric_statistics.return_value = {
            "Datapoints": [
                {"Timestamp": "2026-01-15T10:00:00Z", "Average": 100.0},
            ],
        }

        result = helper.get_storage_metrics("fs-001")

        assert isinstance(result, dict)
        assert "StorageCapacity" in result
        assert "StorageUsed" in result
        assert "StorageCapacityUtilization" in result
        assert len(result) == 3
        # Each metric should have datapoints
        for metric_name in ["StorageCapacity", "StorageUsed", "StorageCapacityUtilization"]:
            assert len(result[metric_name]) == 1
            assert result[metric_name][0]["Average"] == 100.0

        # Verify get_metric_statistics was called 3 times (once per metric)
        assert helper._cw_client.get_metric_statistics.call_count == 3

    def test_cloudwatch_error_wraps_client_error(self, helper: FsxHelper):
        """CloudWatch API の ClientError が FsxHelperError にラップされることを検証する"""
        original_error = _make_client_error(
            code="InternalServiceError",
            message="CloudWatch internal error",
            operation="GetMetricStatistics",
        )
        helper._cw_client.get_metric_statistics.side_effect = original_error

        with pytest.raises(FsxHelperError) as exc_info:
            helper.get_storage_metrics("fs-001")

        assert exc_info.value.original_error is original_error
        assert "Failed to get CloudWatch metric" in str(exc_info.value)

    def test_custom_session(self):
        """カスタム boto3 セッションが使用されることを検証する"""
        custom_session = MagicMock()
        custom_fsx_client = MagicMock()
        custom_cw_client = MagicMock()

        def client_factory(service_name, **kwargs):
            if service_name == "fsx":
                return custom_fsx_client
            elif service_name == "cloudwatch":
                return custom_cw_client
            return MagicMock()

        custom_session.client.side_effect = client_factory

        helper = FsxHelper(session=custom_session)

        assert helper._fsx_client is custom_fsx_client
        assert helper._cw_client is custom_cw_client
        # Verify session.client was called for both fsx and cloudwatch
        assert custom_session.client.call_count == 2
