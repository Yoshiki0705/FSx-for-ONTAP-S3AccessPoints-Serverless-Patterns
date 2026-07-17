"""OPS5 Collect Handler — コストデータ収集.

FSx for ONTAP の構成情報 (容量, スループットティア) から月額コストを算出。
DemoMode 時はモック値を返す。
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# Pricing (ap-northeast-1 approximate)
SSD_PER_GB = 0.125
CAPACITY_POOL_PER_GB = 0.021
THROUGHPUT_PER_MBPS = 0.370
BACKUP_PER_GB = 0.025


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    demo_mode = os.environ.get("DEMO_MODE", "false") == "true"
    fs_ids = [f.strip() for f in os.environ.get("FILE_SYSTEM_IDS", "").split(",") if f.strip()]

    results = []
    for fs_id in fs_ids:
        if demo_mode:
            results.append(_demo_cost(fs_id))
        else:
            results.append(_live_cost(fs_id))

    return {"file_systems": results, "collected_at": datetime.now(UTC).isoformat(), "demo_mode": demo_mode}


def _demo_cost(fs_id: str) -> dict[str, Any]:
    return {
        "fs_id": fs_id,
        "ssd_capacity_gb": 1024,
        "capacity_pool_gb": 512,
        "throughput_mbps": 128,
        "backup_gb": 200,
        "monthly_cost_breakdown": {
            "ssd": round(1024 * SSD_PER_GB, 2),
            "capacity_pool": round(512 * CAPACITY_POOL_PER_GB, 2),
            "throughput": round(128 * THROUGHPUT_PER_MBPS, 2),
            "backup": round(200 * BACKUP_PER_GB, 2),
        },
        "total_monthly_cost_usd": round(
            1024 * SSD_PER_GB + 512 * CAPACITY_POOL_PER_GB + 128 * THROUGHPUT_PER_MBPS + 200 * BACKUP_PER_GB, 2
        ),
        "cost_per_gb_usd": round((1024 * SSD_PER_GB + 512 * CAPACITY_POOL_PER_GB) / (1024 + 512), 4),
        "collected_at": datetime.now(UTC).isoformat(),
    }


def _live_cost(fs_id: str) -> dict[str, Any]:
    fsx = boto3.client("fsx")
    resp = fsx.describe_file_systems(FileSystemIds=[fs_id])
    fs_list = resp.get("FileSystems", [])
    if not fs_list:
        raise RuntimeError(f"FS not found: {fs_id}")

    fs = fs_list[0]
    ontap = fs.get("OntapConfiguration", {})
    ssd_gb = fs.get("StorageCapacity", 0)
    throughput = ontap.get("ThroughputCapacity", 0)

    # Capacity pool and backup sizes require CloudWatch or ONTAP API
    # Simplified: estimate from StorageCapacity
    pool_gb = ssd_gb * 0.5  # rough estimate
    backup_gb = ssd_gb * 0.2

    breakdown = {
        "ssd": round(ssd_gb * SSD_PER_GB, 2),
        "capacity_pool": round(pool_gb * CAPACITY_POOL_PER_GB, 2),
        "throughput": round(throughput * THROUGHPUT_PER_MBPS, 2),
        "backup": round(backup_gb * BACKUP_PER_GB, 2),
    }
    total = sum(breakdown.values())

    return {
        "fs_id": fs_id,
        "ssd_capacity_gb": ssd_gb,
        "capacity_pool_gb": pool_gb,
        "throughput_mbps": throughput,
        "backup_gb": backup_gb,
        "monthly_cost_breakdown": breakdown,
        "total_monthly_cost_usd": round(total, 2),
        "cost_per_gb_usd": round(total / max(ssd_gb + pool_gb, 1), 4),
        "collected_at": datetime.now(UTC).isoformat(),
    }
