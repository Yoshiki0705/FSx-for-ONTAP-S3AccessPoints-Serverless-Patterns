"""OPS4 Collect Handler — スナップショット + ポリシー収集

全対象ボリュームのスナップショット一覧と Snapshot Policy 定義を収集し、
後続の Analyze ステップに渡す。

DemoMode=true の場合は test-data/ops/snapshots.json のモックデータを使用。
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Collect snapshots and snapshot policies from ONTAP REST API.

    Returns:
        dict with keys: file_systems (list of per-FS snapshot data), collected_at
    """
    demo_mode = os.environ.get("DEMO_MODE", "false") == "true"
    fs_ids = os.environ.get("FILE_SYSTEM_IDS", "").split(",")
    fs_ids = [fid.strip() for fid in fs_ids if fid.strip()]

    if event.get("fs_id"):
        fs_ids = [event["fs_id"]]

    logger.info("Collecting snapshots for %d file systems (demo_mode=%s)", len(fs_ids), demo_mode)

    results = []
    for fs_id in fs_ids:
        if demo_mode:
            result = _collect_demo(fs_id)
        else:
            result = _collect_live(fs_id)
        results.append(result)

    return {
        "file_systems": results,
        "collected_at": datetime.now(UTC).isoformat(),
        "demo_mode": demo_mode,
    }


def _collect_demo(fs_id: str) -> dict[str, Any]:
    """DemoMode: モックデータからスナップショット情報を収集."""
    from shared.demo_data_loader import DemoDataLoader

    loader = DemoDataLoader(source="local", base_path="test-data/ops")
    snapshots = loader.load_snapshots(fs_id=fs_id)

    # Group snapshots by volume
    volumes_map: dict[str, list[dict]] = {}
    for snap in snapshots:
        vol_name = snap.get("volume_name", "unknown")
        if vol_name not in volumes_map:
            volumes_map[vol_name] = []
        volumes_map[vol_name].append(snap)

    volume_snapshots = []
    for vol_name, snaps in volumes_map.items():
        volume_snapshots.append(
            {
                "volume_name": vol_name,
                "volume_uuid": snaps[0].get("volume_uuid", ""),
                "snapshots": snaps,
                "snapshot_count": len(snaps),
            }
        )

    return {
        "fs_id": fs_id,
        "volume_snapshots": volume_snapshots,
        "snapshot_policies": [
            {
                "name": "default",
                "uuid": "policy-001",
                "enabled": True,
                "schedules": [
                    {"schedule": "daily", "count": 7},
                    {"schedule": "weekly", "count": 4},
                ],
            },
        ],
        "collected_at": datetime.now(UTC).isoformat(),
    }


def _collect_live(fs_id: str) -> dict[str, Any]:
    """Live mode: ONTAP REST API からスナップショットとポリシーを収集."""
    secret_arn = os.environ.get("ONTAP_SECRET_ARN", "")
    mgmt_ip = _get_management_ip(fs_id)

    from shared.ontap_client import OntapClient, OntapClientConfig
    from shared.ontap_metrics import OntapMetricsCollector

    config = OntapClientConfig(
        management_ip=mgmt_ip,
        secret_name=secret_arn,
        verify_ssl=False,
    )
    client = OntapClient(config)
    collector = OntapMetricsCollector(client)

    # Collect snapshot policies
    policies = collector.collect_snapshot_policies()

    # Collect volumes first, then snapshots for each
    volumes = collector.collect_volume_space()

    volume_snapshots = []
    for vol in volumes:
        vol_uuid = vol.get("uuid", "")
        vol_name = vol.get("name", "")
        if not vol_uuid:
            continue

        snaps = collector.collect_snapshots(vol_uuid)
        now = datetime.now(UTC)

        # Enrich with age calculation
        #
        # 経過日数が分からない場合の扱いに注意が必要。以前はいずれの失敗でも
        # age_days = 0 にしていた。0 は min_retention_days 未満なので analyze 側で
        # 「保護対象（削除禁止）」に分類され、期限切れ判定から外れる。つまり
        # タイムスタンプが読めないスナップショットは、実際には保持期限を超えていても
        # 「新しくて健全」として集計され、RetentionCompliancePercent が 100% に
        # 見えてしまう。保持コンプライアンスを見るパターンで最も避けたい種類の
        # 静かな誤りである。
        #
        # そこで age_days は None のままにし、解析できなかった事実を
        # age_unknown フラグとして残す。件数はボリューム単位で集計して
        # レポートまで運ぶ。
        unknown_age_count = 0
        for snap in snaps:
            create_time_str = snap.get("create_time", "")
            age_days = None
            if create_time_str:
                try:
                    create_time = datetime.fromisoformat(create_time_str)
                    if create_time.tzinfo is None:
                        # ONTAP はタイムゾーン付きで返すが、構成によっては naive の
                        # 可能性がある。aware な now との減算は TypeError になるため、
                        # UTC とみなして扱う。
                        create_time = create_time.replace(tzinfo=UTC)
                    age_days = (now - create_time).days
                except (ValueError, TypeError) as e:
                    logger.warning(
                        "Could not parse create_time %r for snapshot %r on volume %r: %s",
                        create_time_str,
                        snap.get("name"),
                        vol_name,
                        e,
                    )
            else:
                logger.warning("Snapshot %r on volume %r has no create_time", snap.get("name"), vol_name)

            snap["age_days"] = age_days
            snap["age_unknown"] = age_days is None
            if age_days is None:
                unknown_age_count += 1
            snap["volume_name"] = vol_name
            snap["volume_uuid"] = vol_uuid
            snap["fs_id"] = fs_id

        volume_snapshots.append(
            {
                "volume_name": vol_name,
                "volume_uuid": vol_uuid,
                "snapshots": snaps,
                "snapshot_count": len(snaps),
                "unknown_age_count": unknown_age_count,
            }
        )

    return {
        "fs_id": fs_id,
        "volume_snapshots": volume_snapshots,
        "snapshot_policies": policies,
        # 経過日数が判定できなかった総数。0 でない場合、コンプライアンス率は
        # その分だけ判定不能な対象を含んでいることになる。
        "unknown_age_count": sum(v["unknown_age_count"] for v in volume_snapshots),
        "collected_at": datetime.now(UTC).isoformat(),
    }


def _get_management_ip(fs_id: str) -> str:
    """FSx API からファイルシステムの管理 IP を取得."""
    fsx_client = boto3.client("fsx")
    response = fsx_client.describe_file_systems(FileSystemIds=[fs_id])
    file_systems = response.get("FileSystems", [])
    if not file_systems:
        raise RuntimeError(f"File system not found: {fs_id}")

    endpoints = file_systems[0].get("OntapConfiguration", {}).get("Endpoints", {}).get("Management", {})
    ip_addresses = endpoints.get("IpAddresses", [])
    if not ip_addresses:
        raise RuntimeError(f"Management IP not found for {fs_id}")
    return ip_addresses[0]
