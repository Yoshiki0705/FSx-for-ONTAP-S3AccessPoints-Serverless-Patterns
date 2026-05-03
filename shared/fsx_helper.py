"""AWS FSx API ヘルパー

AWS FSx for NetApp ONTAP の API（describe_file_systems, describe_volumes,
describe_storage_virtual_machines）および CloudWatch メトリクス取得を行う共通モジュール。

既存リポジトリ FSx-for-ONTAP-Agentic-Access-Aware-RAG の検証済みパターンを
Python で再実装したもの。

Key patterns preserved:
- describe_file_systems, describe_volumes, describe_storage_virtual_machines
- CloudWatch metrics: StorageCapacity, StorageUsed, StorageCapacityUtilization
- boto3 ClientError → FsxHelperError wrapping (original_error attribute)
- Optional boto3 session parameter for cross-account/cross-region access
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class FsxHelperError(Exception):
    """FSx API エラー"""

    def __init__(self, message: str, original_error: Exception | None = None):
        super().__init__(message)
        self.original_error = original_error


class FsxHelper:
    """AWS FSx API ヘルパー

    FSx for NetApp ONTAP のファイルシステム、ボリューム、SVM の情報取得と
    CloudWatch メトリクスの取得を提供する。

    Usage:
        helper = FsxHelper()
        filesystems = helper.describe_file_systems(["fs-0123456789abcdef0"])
        metrics = helper.get_storage_metrics("fs-0123456789abcdef0")
    """

    def __init__(self, session: boto3.Session | None = None):
        """FsxHelper を初期化

        Args:
            session: boto3 セッション (オプション)。
                     クロスアカウント/クロスリージョンアクセス時に指定する。
        """
        self._session = session or boto3.Session()
        self._fsx_client = self._session.client("fsx")
        self._cw_client = self._session.client("cloudwatch")

    def describe_file_systems(
        self,
        filesystem_ids: list[str] | None = None,
    ) -> list[dict]:
        """ファイルシステム情報取得

        Args:
            filesystem_ids: ファイルシステム ID のリスト (オプション)。
                           省略時は全ファイルシステムを返す。

        Returns:
            list[dict]: ファイルシステム情報のリスト

        Raises:
            FsxHelperError: AWS FSx API 呼び出しに失敗した場合
        """
        try:
            kwargs = {}
            if filesystem_ids:
                kwargs["FileSystemIds"] = filesystem_ids

            filesystems = []
            paginator = self._fsx_client.get_paginator("describe_file_systems")
            for page in paginator.paginate(**kwargs):
                filesystems.extend(page.get("FileSystems", []))

            return filesystems
        except ClientError as e:
            raise FsxHelperError(
                f"Failed to describe file systems "
                f"(ids={filesystem_ids}): {e}",
                original_error=e,
            ) from e

    def describe_volumes(
        self,
        volume_ids: list[str] | None = None,
        filters: list[dict] | None = None,
    ) -> list[dict]:
        """ボリューム情報取得

        Args:
            volume_ids: ボリューム ID のリスト (オプション)
            filters: フィルタ条件のリスト (オプション)
                     例: [{"Name": "file-system-id", "Values": ["fs-xxx"]}]

        Returns:
            list[dict]: ボリューム情報のリスト

        Raises:
            FsxHelperError: AWS FSx API 呼び出しに失敗した場合
        """
        try:
            kwargs = {}
            if volume_ids:
                kwargs["VolumeIds"] = volume_ids
            if filters:
                kwargs["Filters"] = filters

            volumes = []
            paginator = self._fsx_client.get_paginator("describe_volumes")
            for page in paginator.paginate(**kwargs):
                volumes.extend(page.get("Volumes", []))

            return volumes
        except ClientError as e:
            raise FsxHelperError(
                f"Failed to describe volumes "
                f"(ids={volume_ids}, filters={filters}): {e}",
                original_error=e,
            ) from e

    def describe_storage_virtual_machines(
        self,
        svm_ids: list[str] | None = None,
    ) -> list[dict]:
        """SVM 情報取得

        Args:
            svm_ids: SVM ID のリスト (オプション)。
                    省略時は全 SVM を返す。

        Returns:
            list[dict]: SVM 情報のリスト

        Raises:
            FsxHelperError: AWS FSx API 呼び出しに失敗した場合
        """
        try:
            kwargs = {}
            if svm_ids:
                kwargs["StorageVirtualMachineIds"] = svm_ids

            svms = []
            paginator = self._fsx_client.get_paginator(
                "describe_storage_virtual_machines"
            )
            for page in paginator.paginate(**kwargs):
                svms.extend(page.get("StorageVirtualMachines", []))

            return svms
        except ClientError as e:
            raise FsxHelperError(
                f"Failed to describe storage virtual machines "
                f"(ids={svm_ids}): {e}",
                original_error=e,
            ) from e

    def get_storage_metrics(
        self,
        filesystem_id: str,
        period: int = 300,
        hours: int = 1,
    ) -> dict:
        """CloudWatch メトリクス取得

        FSx for ONTAP ファイルシステムの StorageCapacity, StorageUsed,
        StorageCapacityUtilization メトリクスを取得する。

        Args:
            filesystem_id: ファイルシステム ID
            period: メトリクス集計期間（秒）。デフォルト: 300 (5分)
            hours: 取得する過去の時間数。デフォルト: 1

        Returns:
            dict: {
                "StorageCapacity": list[dict],
                "StorageUsed": list[dict],
                "StorageCapacityUtilization": list[dict],
            }
            各リストは {"Timestamp": datetime, "Average": float} の辞書リスト

        Raises:
            FsxHelperError: CloudWatch API 呼び出しに失敗した場合
        """
        metric_names = [
            "StorageCapacity",
            "StorageUsed",
            "StorageCapacityUtilization",
        ]

        now = datetime.now(timezone.utc)
        start_time = now - timedelta(hours=hours)

        results = {}
        for metric_name in metric_names:
            try:
                response = self._cw_client.get_metric_statistics(
                    Namespace="AWS/FSx",
                    MetricName=metric_name,
                    Dimensions=[
                        {
                            "Name": "FileSystemId",
                            "Value": filesystem_id,
                        },
                    ],
                    StartTime=start_time,
                    EndTime=now,
                    Period=period,
                    Statistics=["Average"],
                )
                results[metric_name] = response.get("Datapoints", [])
            except ClientError as e:
                raise FsxHelperError(
                    f"Failed to get CloudWatch metric {metric_name} "
                    f"for filesystem {filesystem_id}: {e}",
                    original_error=e,
                ) from e

        return results
