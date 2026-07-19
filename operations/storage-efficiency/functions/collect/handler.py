"""OPS2 Collect Handler — ストレージ効率メトリクス収集."""

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
    fs_ids = [fid.strip() for fid in os.environ.get("FILE_SYSTEM_IDS", "").split(",") if fid.strip()]
    if event.get("fs_id"):
        fs_ids = [event["fs_id"]]

    results = []
    for fs_id in fs_ids:
        if demo_mode:
            from shared.demo_data_loader import DemoDataLoader

            loader = DemoDataLoader(source="local", base_path="test-data/ops")
            volumes = loader.load_efficiency(fs_id=fs_id)
        else:
            volumes = _collect_live(fs_id)
        results.append({"fs_id": fs_id, "volumes": volumes, "collected_at": datetime.now(UTC).isoformat()})

    return {"file_systems": results, "collected_at": datetime.now(UTC).isoformat(), "demo_mode": demo_mode}


def _collect_live(fs_id: str) -> list[dict]:
    secret_arn = os.environ.get("ONTAP_SECRET_ARN", "")
    fsx_client = boto3.client("fsx")
    resp = fsx_client.describe_file_systems(FileSystemIds=[fs_id])
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
    volumes = collector.collect_efficiency()
    for v in volumes:
        v["fs_id"] = fs_id
    return volumes
