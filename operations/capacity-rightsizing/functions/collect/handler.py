"""OPS1 Collect Handler — メトリクス収集

ONTAP REST API と CloudWatch から容量・スループットメトリクスを収集し、
後続の Analyze ステップに渡す。

DemoMode=true の場合は test-data/ops/ のモック JSON を使用。

References:
    - CloudWatch metrics: https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/monitoring-cloudwatch.html
    - Gen2 metrics: https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/so-file-system-metrics.html
    - ONTAP REST: https://docs.netapp.com/us-en/ontap-restapi/ontap/storage_volumes_endpoint_overview.html
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Collect metrics from ONTAP REST API and CloudWatch.

    Args:
        event: Step Functions input (may contain fs_id for single-FS mode)
        context: Lambda context

    Returns:
        dict: OpsCollectOutput-compatible structure per file system
    """
    demo_mode = os.environ.get("DEMO_MODE", "false") == "true"
    fs_ids = os.environ.get("FILE_SYSTEM_IDS", "").split(",")
    fs_ids = [fid.strip() for fid in fs_ids if fid.strip()]

    # Allow single-FS override from Step Functions input
    if event.get("fs_id"):
        fs_ids = [event["fs_id"]]

    logger.info("Collecting metrics for %d file systems (demo_mode=%s)", len(fs_ids), demo_mode)

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
    """DemoMode: モックデータから収集する."""
    from shared.demo_data_loader import DemoDataLoader

    loader = DemoDataLoader(source="local", base_path="test-data/ops")

    volumes = loader.load_volume_space(fs_id=fs_id)
    aggregates = loader.load_aggregate_space(fs_id=fs_id)
    cloudwatch = loader.load_cloudwatch_metrics(fs_id=fs_id)

    return {
        "fs_id": fs_id,
        "volumes": volumes,
        "aggregates": aggregates,
        "cloudwatch": cloudwatch,
        "collected_at": datetime.now(UTC).isoformat(),
    }


def _collect_live(fs_id: str) -> dict[str, Any]:
    """Live mode: ONTAP REST API + CloudWatch から収集する."""
    secret_arn = os.environ.get("ONTAP_SECRET_ARN", "")

    # Get management IP from FSx API
    mgmt_ip = _get_management_ip(fs_id)

    # Collect ONTAP metrics
    volumes, aggregates = _collect_ontap_metrics(mgmt_ip, secret_arn)

    # Collect CloudWatch metrics
    cloudwatch = _collect_cloudwatch_metrics(fs_id)

    # Tag volumes/aggregates with fs_id
    for vol in volumes:
        vol["fs_id"] = fs_id
    for aggr in aggregates:
        aggr["fs_id"] = fs_id

    return {
        "fs_id": fs_id,
        "volumes": volumes,
        "aggregates": aggregates,
        "cloudwatch": cloudwatch,
        "collected_at": datetime.now(UTC).isoformat(),
    }


def _get_management_ip(fs_id: str) -> str:
    """FSx API からファイルシステムの管理 IP を取得する."""
    fsx_client = boto3.client("fsx")
    response = fsx_client.describe_file_systems(FileSystemIds=[fs_id])

    file_systems = response.get("FileSystems", [])
    if not file_systems:
        raise RuntimeError(f"File system not found: {fs_id}")

    fs = file_systems[0]
    ontap_config = fs.get("OntapConfiguration", {})
    endpoints = ontap_config.get("Endpoints", {})
    mgmt_endpoint = endpoints.get("Management", {})
    ip_addresses = mgmt_endpoint.get("IpAddresses", [])

    if not ip_addresses:
        raise RuntimeError(f"Management IP not found for {fs_id}")

    return ip_addresses[0]


def _collect_ontap_metrics(
    mgmt_ip: str, secret_arn: str
) -> tuple[list[dict], list[dict]]:
    """ONTAP REST API からボリューム/アグリゲートメトリクスを収集する."""
    from shared.ontap_client import OntapClient, OntapClientConfig
    from shared.ontap_metrics import OntapMetricsCollector

    config = OntapClientConfig(
        management_ip=mgmt_ip,
        secret_name=secret_arn,
        verify_ssl=False,  # FSx for ONTAP uses self-signed certs
    )
    client = OntapClient(config)
    collector = OntapMetricsCollector(client)

    volumes = collector.collect_volume_space()
    aggregates = collector.collect_aggregate_space()

    return volumes, aggregates


def _collect_cloudwatch_metrics(fs_id: str) -> dict[str, Any]:
    """CloudWatch からファイルシステムレベルメトリクスを収集する."""
    cw_client = boto3.client("cloudwatch")
    fsx_client = boto3.client("fsx")

    # Determine Gen1 vs Gen2
    is_gen2 = _is_gen2_filesystem(fsx_client, fs_id)
    throughput_mbps = _get_throughput_capacity(fsx_client, fs_id)

    end_time = datetime.now(UTC)
    start_time = end_time - timedelta(hours=1)

    # Common metrics for both Gen1 and Gen2
    metric_queries = [
        _build_metric_query("StorageCapacityUtilization", fs_id, "m1"),
        _build_metric_query("CPUUtilization", fs_id, "m2"),
        _build_metric_query("NetworkSentBytes", fs_id, "m3", stat="Sum"),
        _build_metric_query("NetworkReceivedBytes", fs_id, "m4", stat="Sum"),
    ]

    # Gen2-specific metrics
    if is_gen2:
        metric_queries.extend([
            _build_metric_query("NetworkThroughputUtilization", fs_id, "m5"),
            _build_metric_query("DiskIOPSUtilization", fs_id, "m6"),
        ])

    response = cw_client.get_metric_data(
        MetricDataQueries=metric_queries,
        StartTime=start_time,
        EndTime=end_time,
    )

    # Extract latest values
    metrics_map = {}
    for result in response.get("MetricDataResults", []):
        metric_id = result["Id"]
        values = result.get("Values", [])
        metrics_map[metric_id] = values[0] if values else 0.0

    # Calculate network bytes per second (Sum over 1h → divide by 3600)
    network_sent_bps = metrics_map.get("m3", 0) / 3600
    network_received_bps = metrics_map.get("m4", 0) / 3600

    return {
        "fs_id": fs_id,
        "storage_capacity_utilization_percent": metrics_map.get("m1", 0.0),
        "network_throughput_utilization_percent": metrics_map.get("m5") if is_gen2 else None,
        "disk_iops_utilization_percent": metrics_map.get("m6") if is_gen2 else None,
        "cpu_utilization_percent": metrics_map.get("m2", 0.0),
        "network_sent_bytes_per_sec": network_sent_bps,
        "network_received_bytes_per_sec": network_received_bps,
        "is_gen2": is_gen2,
        "throughput_capacity_mbps": throughput_mbps,
    }


def _build_metric_query(
    metric_name: str,
    fs_id: str,
    query_id: str,
    stat: str = "Average",
) -> dict[str, Any]:
    """CloudWatch GetMetricData 用のクエリを構築する."""
    return {
        "Id": query_id,
        "MetricStat": {
            "Metric": {
                "Namespace": "AWS/FSx",
                "MetricName": metric_name,
                "Dimensions": [
                    {"Name": "FileSystemId", "Value": fs_id},
                ],
            },
            "Period": 3600,
            "Stat": stat,
        },
        "ReturnData": True,
    }


def _is_gen2_filesystem(fsx_client: Any, fs_id: str) -> bool:
    """ファイルシステムが Gen2 (MULTI_AZ_2/SINGLE_AZ_2) かを判定する."""
    response = fsx_client.describe_file_systems(FileSystemIds=[fs_id])
    file_systems = response.get("FileSystems", [])
    if not file_systems:
        return False

    deployment_type = (
        file_systems[0]
        .get("OntapConfiguration", {})
        .get("DeploymentType", "")
    )
    return deployment_type in ("MULTI_AZ_2", "SINGLE_AZ_2")


def _get_throughput_capacity(fsx_client: Any, fs_id: str) -> int:
    """ファイルシステムのスループットキャパシティ (MBps) を取得する."""
    response = fsx_client.describe_file_systems(FileSystemIds=[fs_id])
    file_systems = response.get("FileSystems", [])
    if not file_systems:
        return 0

    return (
        file_systems[0]
        .get("OntapConfiguration", {})
        .get("ThroughputCapacity", 0)
    )
