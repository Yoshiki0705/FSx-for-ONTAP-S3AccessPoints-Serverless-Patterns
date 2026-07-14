"""Operations パターン用 TypedDict 定義

operations/ パターン群の Lambda 関数間でやり取りされるイベント/レスポンスの
型定義。Step Functions のステート間データ受け渡しに使用。

Usage:
    from shared.schemas.ops_events import (
        VolumeSpaceMetric,
        CapacityRecommendation,
        OpsCollectOutput,
    )
"""

from __future__ import annotations

from typing import TypedDict


# --- Volume Space (OPS1: capacity-rightsizing) ---


class VolumeSpaceMetric(TypedDict):
    """ボリューム容量メトリクス."""

    fs_id: str
    name: str
    uuid: str
    svm_name: str
    size_bytes: int
    used_bytes: int
    available_bytes: int
    utilization_percent: float
    autosize_enabled: bool
    autosize_mode: str  # "off" | "grow" | "grow_shrink"
    style: str  # "flexvol" | "flexgroup"
    state: str  # "online" | "offline" | "restricted"


class AggregateSpaceMetric(TypedDict):
    """アグリゲート容量メトリクス."""

    fs_id: str
    name: str
    uuid: str
    size_bytes: int
    used_bytes: int
    available_bytes: int
    utilization_percent: float
    state: str


class CloudWatchFsMetric(TypedDict):
    """CloudWatch ファイルシステムレベルメトリクス."""

    fs_id: str
    storage_capacity_utilization_percent: float
    network_throughput_utilization_percent: float | None  # Gen2 only
    disk_iops_utilization_percent: float | None  # Gen2 only
    cpu_utilization_percent: float
    network_sent_bytes_per_sec: float
    network_received_bytes_per_sec: float
    is_gen2: bool
    throughput_capacity_mbps: int


# --- Efficiency (OPS2: storage-efficiency) ---


class EfficiencyMetric(TypedDict):
    """ストレージ効率メトリクス."""

    fs_id: str
    name: str
    uuid: str
    svm_name: str
    dedupe_enabled: bool
    compression_enabled: bool
    dedupe_savings_bytes: int
    compression_savings_bytes: int
    overall_ratio: float  # e.g., 2.5 means 2.5:1
    logical_used_bytes: int
    physical_used_bytes: int


# --- Tiering (OPS3: tiering-optimizer) ---


class TieringMetric(TypedDict):
    """ティアリングメトリクス."""

    fs_id: str
    name: str
    uuid: str
    svm_name: str
    tiering_policy: str  # "none" | "snapshot-only" | "auto" | "all"
    cooling_period_days: int
    cloud_storage_used_bytes: int


class TieringRecommendation(TypedDict):
    """ティアリング推奨."""

    fs_id: str
    volume_name: str
    current_policy: str
    recommended_policy: str
    current_cooling_days: int
    recommended_cooling_days: int
    estimated_monthly_savings_usd: float
    reason: str
    confidence: float


# --- Snapshot (OPS4: snapshot-lifecycle) ---


class SnapshotMetric(TypedDict):
    """スナップショットメトリクス."""

    fs_id: str
    volume_name: str
    volume_uuid: str
    snapshot_name: str
    snapshot_uuid: str
    create_time: str  # ISO 8601
    size_bytes: int
    age_days: int


class SnapshotPolicyMetric(TypedDict):
    """Snapshot Policy メトリクス."""

    fs_id: str
    policy_name: str
    policy_uuid: str
    enabled: bool
    schedules: list[dict]


class SnapshotAuditResult(TypedDict):
    """スナップショット監査結果."""

    fs_id: str
    volume_name: str
    total_snapshots: int
    total_size_bytes: int
    oldest_snapshot_age_days: int
    retention_compliant: bool
    expired_snapshots: list[SnapshotMetric]
    policy_drift_detected: bool
    policy_drift_details: str


# --- Cost (OPS5: cost-optimization) ---


class CostProjection(TypedDict):
    """コスト予測."""

    fs_id: str
    current_monthly_cost_usd: float
    projected_monthly_cost_usd: float  # 3 months ahead
    growth_rate_percent: float
    cost_per_gb_usd: float
    top_cost_drivers: list[str]
    ai_summary: str


class CostAllocation(TypedDict):
    """コスト配賦."""

    fs_id: str
    volume_name: str
    team: str
    cost_usd: float
    usage_gb: float


# --- QoS (OPS6: qos-monitoring) ---


class QosPolicyMetric(TypedDict):
    """QoS ポリシーメトリクス."""

    fs_id: str
    policy_name: str
    policy_uuid: str
    max_throughput_iops: int | None
    max_throughput_mbps: int | None
    min_throughput_iops: int | None
    assigned_volume_count: int


# --- Recommendations (共通) ---


class CapacityRecommendation(TypedDict):
    """容量/スループット推奨."""

    fs_id: str
    recommendation_type: str  # "upsize" | "downsize" | "tier_upgrade" | "tier_downgrade"
    target: str  # volume name or fs_id
    current_value: str  # e.g., "128 MBps" or "85% utilization"
    recommended_value: str  # e.g., "256 MBps" or "expand 20%"
    reason: str
    monthly_cost_delta_usd: float  # positive = cost increase, negative = savings
    confidence: float  # 0.0 - 1.0
    automation_action: str | None  # FSx API call or ONTAP REST path for Level 2/3


class WhatIfScenario(TypedDict):
    """What-If シミュレーション結果."""

    fs_id: str
    scenario_name: str  # e.g., "Upgrade to 256 MBps"
    current_monthly_cost_usd: float
    projected_monthly_cost_usd: float
    monthly_delta_usd: float
    description: str


# --- Step Functions ステート間データ ---


class OpsCollectOutput(TypedDict):
    """Collect Lambda の出力 (Step Functions)."""

    fs_id: str
    volumes: list[VolumeSpaceMetric]
    aggregates: list[AggregateSpaceMetric]
    cloudwatch: CloudWatchFsMetric
    collected_at: str  # ISO 8601


class OpsAnalyzeOutput(TypedDict):
    """Analyze Lambda の出力 (Step Functions)."""

    fs_id: str
    recommendations: list[CapacityRecommendation]
    what_if_scenarios: list[WhatIfScenario]
    summary_stats: dict  # Aggregated statistics
    analyzed_at: str  # ISO 8601


class OpsReportOutput(TypedDict):
    """Report Lambda の出力 (Step Functions)."""

    fs_id: str
    report_s3_key: str  # S3 path to JSON report
    html_report_s3_key: str | None  # S3 path to HTML report (if enabled)
    ai_summary: str | None  # Bedrock-generated summary (if enabled)
    recommendation_count: int
    alert_required: bool
    reported_at: str  # ISO 8601


# --- DemoMode ---


class DemoModeConfig(TypedDict):
    """DemoMode 設定."""

    enabled: bool
    data_source: str  # "mock_json" | "generated"
    mock_data_path: str  # S3 key or local path to fixture JSON
