"""ONTAP REST API メトリクス収集モジュール (Cluster スコープ)

operations/ パターン群で使用する、FSx for ONTAP のクラスタレベルメトリクスを
ONTAP REST API から収集する共通モジュール。

既存の shared/ontap_client.py (SVM スコープ) と異なり、fsxadmin 認証で
ファイルシステム管理 IP 経由でクラスタ全体のメトリクスを取得する。

Usage:
    from shared.ontap_metrics import OntapMetricsCollector
    from shared.ontap_client import OntapClient, OntapClientConfig

    config = OntapClientConfig(
        management_ip="<management-ip>",
        secret_name="fsxn/admin-credentials",
    )
    client = OntapClient(config)
    collector = OntapMetricsCollector(client)

    volumes = collector.collect_volume_space()
    efficiency = collector.collect_efficiency()

References:
    - ONTAP REST API: https://docs.netapp.com/us-en/ontap-restapi/ontap/storage_volumes_endpoint_overview.html
    - CloudWatch metrics: https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/monitoring-cloudwatch.html
    - Existing monitoring: https://github.com/NetApp/FSx-ONTAP-monitoring
    - Auto-resizing: https://github.com/NetApp/fsxn-monitoring-auto-resizing
"""

from __future__ import annotations

import logging
from typing import Any

from shared.ontap_client import OntapClient, OntapClientError

logger = logging.getLogger(__name__)


class OntapMetricsCollector:
    """ONTAP REST API からクラスタレベルメトリクスを収集する。

    fsxadmin 認証でファイルシステム管理 IP に接続し、
    ボリューム・アグリゲート・効率・ティアリング・スナップショット・QoS の
    メトリクスを取得する。

    Note:
        SVM スコープ操作 (CIFS/NFS/S3AP) は既存の ontap_client.py を使用。
        このクラスはクラスタスコープの読み取り専用操作に特化。
    """

    def __init__(self, client: OntapClient) -> None:
        """Initialize collector with an authenticated OntapClient.

        Args:
            client: 認証済み OntapClient インスタンス (fsxadmin 権限)
        """
        self._client = client

    def collect_volume_space(self) -> list[dict[str, Any]]:
        """全ボリュームの容量メトリクスを収集する。

        Returns:
            list[dict]: ボリュームごとの容量情報。各 dict は以下のキーを含む:
                - name (str): ボリューム名
                - uuid (str): ボリューム UUID
                - svm_name (str): 所属 SVM 名
                - size_bytes (int): ボリューム総容量
                - used_bytes (int): 使用済み容量
                - available_bytes (int): 利用可能容量
                - utilization_percent (float): 使用率 (%)
                - autosize_enabled (bool): autosize が有効か
                - autosize_mode (str): autosize モード ("off"|"grow"|"grow_shrink")
                - style (str): ボリュームスタイル ("flexvol"|"flexgroup")
                - state (str): ボリューム状態 ("online"|"offline"|"restricted")

        Raises:
            OntapClientError: ONTAP API 呼び出しに失敗した場合
        """
        logger.info("Collecting volume space metrics")
        params = {
            "fields": "name,uuid,svm.name,space,autosize,style,state,type",
            "type": "rw",  # データボリュームのみ (dp, ls を除外)
            "return_records": "true",
            "max_records": "500",
        }

        records = self._paginate("/storage/volumes", params)

        results = []
        for vol in records:
            space = vol.get("space", {})
            autosize = vol.get("autosize", {})
            size_bytes = space.get("size", 0)
            used_bytes = space.get("used", 0)
            available_bytes = space.get("available", 0)

            utilization = (used_bytes / size_bytes * 100) if size_bytes > 0 else 0.0

            results.append({
                "name": vol.get("name", ""),
                "uuid": vol.get("uuid", ""),
                "svm_name": vol.get("svm", {}).get("name", ""),
                "size_bytes": size_bytes,
                "used_bytes": used_bytes,
                "available_bytes": available_bytes,
                "utilization_percent": round(utilization, 2),
                "autosize_enabled": autosize.get("mode", "off") != "off",
                "autosize_mode": autosize.get("mode", "off"),
                "style": vol.get("style", "unknown"),
                "state": vol.get("state", "unknown"),
            })

        logger.info("Collected space metrics for %d volumes", len(results))
        return results

    def collect_aggregate_space(self) -> list[dict[str, Any]]:
        """アグリゲート (SSD + Capacity Pool) の容量メトリクスを収集する。

        Returns:
            list[dict]: アグリゲートごとの容量情報。各 dict は以下のキーを含む:
                - name (str): アグリゲート名
                - uuid (str): アグリゲート UUID
                - size_bytes (int): 総容量
                - used_bytes (int): 使用済み容量
                - available_bytes (int): 利用可能容量
                - utilization_percent (float): 使用率 (%)
                - state (str): 状態

        Raises:
            OntapClientError: ONTAP API 呼び出しに失敗した場合
        """
        logger.info("Collecting aggregate space metrics")
        params = {
            "fields": "name,uuid,space,state,block_storage",
            "return_records": "true",
            "max_records": "100",
        }

        result = self._client.get("/storage/aggregates", params=params)
        records = result.get("records", [])

        results = []
        for aggr in records:
            space = aggr.get("space", {})
            block = space.get("block_storage", {})
            size_bytes = block.get("size", 0)
            used_bytes = block.get("used", 0)
            available_bytes = block.get("available", 0)

            utilization = (used_bytes / size_bytes * 100) if size_bytes > 0 else 0.0

            results.append({
                "name": aggr.get("name", ""),
                "uuid": aggr.get("uuid", ""),
                "size_bytes": size_bytes,
                "used_bytes": used_bytes,
                "available_bytes": available_bytes,
                "utilization_percent": round(utilization, 2),
                "state": aggr.get("state", "unknown"),
            })

        logger.info("Collected space metrics for %d aggregates", len(results))
        return results

    def collect_efficiency(self) -> list[dict[str, Any]]:
        """全ボリュームの重複排除/圧縮効率メトリクスを収集する。

        Returns:
            list[dict]: ボリュームごとの効率情報。各 dict は以下のキーを含む:
                - name (str): ボリューム名
                - uuid (str): ボリューム UUID
                - svm_name (str): 所属 SVM 名
                - dedupe_enabled (bool): 重複排除が有効か
                - compression_enabled (bool): 圧縮が有効か
                - dedupe_savings_bytes (int): 重複排除による削減量
                - compression_savings_bytes (int): 圧縮による削減量
                - overall_ratio (float): 総合効率比率 (e.g., 2.5)
                - logical_used_bytes (int): 論理使用量
                - physical_used_bytes (int): 物理使用量

        Raises:
            OntapClientError: ONTAP API 呼び出しに失敗した場合
        """
        logger.info("Collecting storage efficiency metrics")
        params = {
            "fields": "name,uuid,svm.name,space,efficiency",
            "type": "rw",
            "return_records": "true",
            "max_records": "500",
        }

        records = self._paginate("/storage/volumes", params)

        results = []
        for vol in records:
            space = vol.get("space", {})
            efficiency = vol.get("efficiency", {})

            # efficiency_without_snapshots gives a cleaner picture
            logical_used = space.get("logical_space", {}).get("used", 0)
            physical_used = space.get("used", 0)

            # Calculate overall ratio
            ratio = (logical_used / physical_used) if physical_used > 0 else 1.0

            # Dedupe and compression savings from space fields
            dedupe_savings = space.get("dedupe_savings", 0)
            compression_savings = space.get("compression_savings", 0)

            results.append({
                "name": vol.get("name", ""),
                "uuid": vol.get("uuid", ""),
                "svm_name": vol.get("svm", {}).get("name", ""),
                "dedupe_enabled": efficiency.get("dedupe", "none") != "none",
                "compression_enabled": efficiency.get("compression", "none") != "none",
                "dedupe_savings_bytes": dedupe_savings,
                "compression_savings_bytes": compression_savings,
                "overall_ratio": round(ratio, 2),
                "logical_used_bytes": logical_used,
                "physical_used_bytes": physical_used,
            })

        logger.info("Collected efficiency metrics for %d volumes", len(results))
        return results

    def collect_tiering(self) -> list[dict[str, Any]]:
        """全ボリュームのティアリングポリシー + コールドデータ率を収集する。

        Returns:
            list[dict]: ボリュームごとのティアリング情報。各 dict は以下のキーを含む:
                - name (str): ボリューム名
                - uuid (str): ボリューム UUID
                - svm_name (str): 所属 SVM 名
                - tiering_policy (str): ティアリングポリシー
                    ("none"|"snapshot-only"|"auto"|"all")
                - cooling_period_days (int): クーリング期間 (日)
                - cloud_storage_used_bytes (int): Capacity Pool 使用量

        Raises:
            OntapClientError: ONTAP API 呼び出しに失敗した場合
        """
        logger.info("Collecting tiering metrics")
        params = {
            "fields": "name,uuid,svm.name,tiering,space",
            "type": "rw",
            "return_records": "true",
            "max_records": "500",
        }

        records = self._paginate("/storage/volumes", params)

        results = []
        for vol in records:
            tiering = vol.get("tiering", {})
            space = vol.get("space", {})

            # Cloud storage used (capacity pool tier)
            cloud_used = space.get("cloud_storage", {}).get("used", 0)

            results.append({
                "name": vol.get("name", ""),
                "uuid": vol.get("uuid", ""),
                "svm_name": vol.get("svm", {}).get("name", ""),
                "tiering_policy": tiering.get("policy", "none"),
                "cooling_period_days": tiering.get("min_cooling_days", 31),
                "cloud_storage_used_bytes": cloud_used,
            })

        logger.info("Collected tiering metrics for %d volumes", len(results))
        return results

    def collect_snapshots(self, volume_uuid: str) -> list[dict[str, Any]]:
        """指定ボリュームのスナップショット一覧を収集する。

        Args:
            volume_uuid: 対象ボリュームの UUID

        Returns:
            list[dict]: スナップショットごとの情報。各 dict は以下のキーを含む:
                - name (str): スナップショット名
                - uuid (str): スナップショット UUID
                - create_time (str): 作成日時 (ISO 8601)
                - size_bytes (int): スナップショットサイズ

        Raises:
            OntapClientError: ONTAP API 呼び出しに失敗した場合
        """
        logger.info("Collecting snapshots for volume %s", volume_uuid)
        params = {
            "fields": "name,uuid,create_time,size",
            "return_records": "true",
            "max_records": "500",
        }

        result = self._client.get(
            f"/storage/volumes/{volume_uuid}/snapshots",
            params=params,
        )
        records = result.get("records", [])

        results = []
        for snap in records:
            results.append({
                "name": snap.get("name", ""),
                "uuid": snap.get("uuid", ""),
                "create_time": snap.get("create_time", ""),
                "size_bytes": snap.get("size", 0),
            })

        logger.info("Collected %d snapshots for volume %s", len(results), volume_uuid)
        return results

    def collect_snapshot_policies(self) -> list[dict[str, Any]]:
        """Snapshot Policy 定義を収集する。

        Returns:
            list[dict]: ポリシーごとの情報。各 dict は以下のキーを含む:
                - name (str): ポリシー名
                - uuid (str): ポリシー UUID
                - enabled (bool): 有効か
                - schedules (list[dict]): スケジュール一覧

        Raises:
            OntapClientError: ONTAP API 呼び出しに失敗した場合
        """
        logger.info("Collecting snapshot policies")
        params = {
            "fields": "name,uuid,enabled,copies",
            "return_records": "true",
            "max_records": "100",
        }

        result = self._client.get("/storage/snapshot-policies", params=params)
        records = result.get("records", [])

        results = []
        for policy in records:
            results.append({
                "name": policy.get("name", ""),
                "uuid": policy.get("uuid", ""),
                "enabled": policy.get("enabled", False),
                "schedules": policy.get("copies", []),
            })

        logger.info("Collected %d snapshot policies", len(results))
        return results

    def collect_qos_policies(self) -> list[dict[str, Any]]:
        """QoS ポリシー定義を収集する。

        Returns:
            list[dict]: ポリシーごとの情報。各 dict は以下のキーを含む:
                - name (str): ポリシー名
                - uuid (str): ポリシー UUID
                - max_throughput_iops (int|None): 最大 IOPS
                - max_throughput_mbps (int|None): 最大スループット (MBps)
                - min_throughput_iops (int|None): 最小 IOPS (QoS adaptive)

        Raises:
            OntapClientError: ONTAP API 呼び出しに失敗した場合
        """
        logger.info("Collecting QoS policies")
        params = {
            "fields": "name,uuid,fixed,adaptive",
            "return_records": "true",
            "max_records": "100",
        }

        try:
            result = self._client.get("/storage/qos/policies", params=params)
        except OntapClientError as e:
            # QoS policies may not exist on all FSx for ONTAP configurations
            if e.status_code == 404:
                logger.warning("QoS policies endpoint not available")
                return []
            raise

        records = result.get("records", [])

        results = []
        for policy in records:
            fixed = policy.get("fixed", {})
            adaptive = policy.get("adaptive", {})

            results.append({
                "name": policy.get("name", ""),
                "uuid": policy.get("uuid", ""),
                "max_throughput_iops": fixed.get("max_throughput_iops"),
                "max_throughput_mbps": fixed.get("max_throughput_mbps"),
                "min_throughput_iops": adaptive.get("expected_iops"),
            })

        logger.info("Collected %d QoS policies", len(results))
        return results

    def _paginate(
        self,
        path: str,
        params: dict[str, str],
    ) -> list[dict[str, Any]]:
        """ONTAP REST API のページネーションを処理する。

        Args:
            path: API エンドポイントパス
            params: クエリパラメータ

        Returns:
            list[dict]: 全ページのレコードを結合したリスト

        Raises:
            OntapClientError: ONTAP API 呼び出しに失敗した場合
        """
        all_records: list[dict[str, Any]] = []
        next_link: str | None = None
        max_pages = 10  # Safety limit

        for page in range(max_pages):
            if next_link:
                # ONTAP REST API next link is a relative path with query params
                result = self._client.get(next_link)
            else:
                result = self._client.get(path, params=params)

            records = result.get("records", [])
            all_records.extend(records)

            # Check for next page
            links = result.get("_links", {})
            next_href = links.get("next", {}).get("href")
            if next_href:
                # Extract path from href (remove /api prefix if present)
                next_link = next_href.replace("/api", "", 1) if next_href.startswith("/api") else next_href
            else:
                break

        return all_records
