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
        volume_snapshots.append({
            "volume_name": vol_name,
            "volume_uuid": snaps[0].get("volume_uuid", ""),
            "snapshots": snaps,
            "snapshot_count": len(snaps),
        })

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
        for snap in snaps:
            create_time_str = snap.get("create_time", "")
            if create_time_str:
                try:
                    create_time = datetime.fromisoformat(create_time_str)
                    age_days = (now - create_time).days
                    snap["age_days"] = age_days
                except (ValueError, TypeError):
                    snap["age_days"] = 0
            else:
                snap["age_days"] = 0
            snap["volume_name"] = vol_name
            snap["volume_uuid"] = vol_uuid
            snap["fs_id"] = fs_id

        volume_snapshots.append({
            "volume_name": vol_name,
            "volume_uuid": vol_uuid,
            "snapshots": snaps,
            "snapshot_count": len(snaps),
        })

    return {
        "fs_id": fs_id,
        "volume_snapshots": volume_snapshots,
        "snapshot_policies": policies,
        "collected_at": datetime.now(UTC).isoformat(),
    }


def _get_management_ip(fs_id: str) -> str:
    """FSx API からファイルシステムの管理 IP を取得."""
    fsx_client = boto3.client("fsx")
    response = fsx_client.describe_file_systems(FileSystemIds=[fs_id])
    file_systems = response.get("FileSystems", [])
    if not file_systems:
        raise RuntimeError(f"File system not found: {fs_id}")

    endpoints = (
        file_systems[0]
        .get("OntapConfiguration", {})
        .get("Endpoints", {})
        .get("Management", {})
    )
    ip_addresses = endpoints.get("IpAddresses", [])
    if not ip_addresses:
        raise RuntimeError(f"Management IP not found for {fs_id}")
    return ip_addresses[0]
