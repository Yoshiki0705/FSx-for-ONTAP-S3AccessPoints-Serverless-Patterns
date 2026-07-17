"""OPS3 Collect Handler — ティアリングメトリクス収集."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Collect tiering policy and cold data metrics."""
    demo_mode = os.environ.get("DEMO_MODE", "false") == "true"
    fs_ids = [fid.strip() for fid in os.environ.get("FILE_SYSTEM_IDS", "").split(",") if fid.strip()]

    if event.get("fs_id"):
        fs_ids = [event["fs_id"]]

    logger.info("Collecting tiering data for %d file systems", len(fs_ids))

    results = []
    for fs_id in fs_ids:
        if demo_mode:
            results.append(_collect_demo(fs_id))
        else:
            results.append(_collect_live(fs_id))

    return {"file_systems": results, "collected_at": datetime.now(UTC).isoformat(), "demo_mode": demo_mode}


def _collect_demo(fs_id: str) -> dict[str, Any]:
    from shared.demo_data_loader import DemoDataLoader

    loader = DemoDataLoader(source="local", base_path="test-data/ops")
    tiering = loader.load_tiering(fs_id=fs_id)
    return {"fs_id": fs_id, "volumes": tiering, "collected_at": datetime.now(UTC).isoformat()}


def _collect_live(fs_id: str) -> dict[str, Any]:
    secret_arn = os.environ.get("ONTAP_SECRET_ARN", "")
    mgmt_ip = _get_management_ip(fs_id)

    from shared.ontap_client import OntapClient, OntapClientConfig
    from shared.ontap_metrics import OntapMetricsCollector

    config = OntapClientConfig(management_ip=mgmt_ip, secret_name=secret_arn, verify_ssl=False)
    client = OntapClient(config)
    collector = OntapMetricsCollector(client)
    tiering = collector.collect_tiering()

    for vol in tiering:
        vol["fs_id"] = fs_id

    return {"fs_id": fs_id, "volumes": tiering, "collected_at": datetime.now(UTC).isoformat()}


def _get_management_ip(fs_id: str) -> str:
    fsx_client = boto3.client("fsx")
    response = fsx_client.describe_file_systems(FileSystemIds=[fs_id])
    fs_list = response.get("FileSystems", [])
    if not fs_list:
        raise RuntimeError(f"File system not found: {fs_id}")
    ips = fs_list[0].get("OntapConfiguration", {}).get("Endpoints", {}).get("Management", {}).get("IpAddresses", [])
    if not ips:
        raise RuntimeError(f"Management IP not found for {fs_id}")
    return ips[0]
