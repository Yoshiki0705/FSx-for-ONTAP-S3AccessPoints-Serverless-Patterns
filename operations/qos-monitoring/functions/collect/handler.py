"""OPS6 Collect Handler — QoS ポリシーデータ収集."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    demo_mode = os.environ.get("DEMO_MODE", "false") == "true"
    fs_ids = [f.strip() for f in os.environ.get("FILE_SYSTEM_IDS", "").split(",") if f.strip()]

    results = []
    for fs_id in fs_ids:
        if demo_mode:
            results.append(_demo_data(fs_id))
        else:
            results.append(_live_data(fs_id))

    return {"file_systems": results, "collected_at": datetime.now(UTC).isoformat(), "demo_mode": demo_mode}


def _demo_data(fs_id: str) -> dict[str, Any]:
    """DemoMode: QoS ポリシーモックデータ."""
    return {
        "fs_id": fs_id,
        "qos_policies": [
            {
                "name": "production-high",
                "uuid": "qp1",
                "max_throughput_iops": 10000,
                "max_throughput_mbps": 500,
                "min_throughput_iops": 1000,
                "assigned_volume_count": 3,
            },
            {
                "name": "dev-low",
                "uuid": "qp2",
                "max_throughput_iops": 2000,
                "max_throughput_mbps": 100,
                "min_throughput_iops": None,
                "assigned_volume_count": 5,
            },
            {
                "name": "default",
                "uuid": "qp3",
                "max_throughput_iops": None,
                "max_throughput_mbps": None,
                "min_throughput_iops": None,
                "assigned_volume_count": 2,
            },
        ],
        "volumes_without_qos": ["vol_backup_temp", "vol_test_data"],
        "collected_at": datetime.now(UTC).isoformat(),
    }


def _live_data(fs_id: str) -> dict[str, Any]:
    """Live: ONTAP REST API から QoS データ収集."""
    secret_arn = os.environ.get("ONTAP_SECRET_ARN", "")
    fsx = boto3.client("fsx")
    resp = fsx.describe_file_systems(FileSystemIds=[fs_id])
    fs_list = resp.get("FileSystems", [])
    if not fs_list:
        raise RuntimeError(f"FS not found: {fs_id}")
    ips = fs_list[0].get("OntapConfiguration", {}).get("Endpoints", {}).get("Management", {}).get("IpAddresses", [])
    if not ips:
        raise RuntimeError(f"Mgmt IP not found: {fs_id}")

    from shared.ontap_client import OntapClient, OntapClientConfig
    from shared.ontap_metrics import OntapMetricsCollector

    config = OntapClientConfig(management_ip=ips[0], secret_name=secret_arn, verify_ssl=False)
    collector = OntapMetricsCollector(OntapClient(config))
    policies = collector.collect_qos_policies()

    for p in policies:
        p["fs_id"] = fs_id

    return {
        "fs_id": fs_id,
        "qos_policies": policies,
        "volumes_without_qos": [],  # Would require cross-referencing volumes vs policies
        "collected_at": datetime.now(UTC).isoformat(),
    }
