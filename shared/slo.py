"""shared.slo — SLO (Service Level Objectives) 定義モジュール

イベント駆動パイプラインの SLO ターゲットを定義し、
CloudWatch ダッシュボードと SLO アラームで可視化するための設定を提供する。

SLO ターゲット:
- EventIngestionLatency: FPolicy event → SQS delivery P99 < 5s
- ProcessingSuccessRate: Step Functions 実行成功率 > 99.5%
- ReconnectTime: FPolicy server 再接続時間 < 30s
- ReplayCompletionTime: Persistent Store リプレイ完了 < 5min

Feature 3（Synthetic Monitoring）統合:
- S3AP_ListLatency_ms / S3AP_GetLatency_ms / ONTAP_HealthCheck メトリクスを
  ダッシュボードウィジェットに含め、SLO 評価と合わせて可視化する。

Usage:
    from shared.slo import SLO_TARGETS, SLOTarget, evaluate_slos, generate_dashboard_widgets

    # SLO 評価
    import boto3
    cw = boto3.client("cloudwatch")
    results = evaluate_slos(cw)
    for r in results:
        print(f"{r.slo_name}: {'MET' if r.met else 'VIOLATED'} (value={r.value})")

    # ダッシュボードウィジェット JSON 生成
    widgets = generate_dashboard_widgets(region="ap-northeast-1")
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SLOTarget:
    """SLO ターゲット定義。

    Attributes:
        name: SLO 名称
        metric_namespace: CloudWatch メトリクス名前空間
        metric_name: CloudWatch メトリクス名
        threshold: 閾値
        comparison: 比較演算子（"LessThanThreshold" | "GreaterThanThreshold"）
        period_sec: 評価期間（秒）
        evaluation_periods: 連続違反回数
        description: SLO の説明
    """

    name: str
    metric_namespace: str
    metric_name: str
    threshold: float
    comparison: str  # "LessThanThreshold" | "GreaterThanThreshold"
    period_sec: int = 300
    evaluation_periods: int = 3
    description: str = ""


# SLO ターゲット定義
SLO_TARGETS: list[SLOTarget] = [
    SLOTarget(
        name="EventIngestionLatency",
        metric_namespace="FSxN-S3AP-Patterns",
        metric_name="EventIngestionLatency_ms",
        threshold=5000.0,  # P99 < 5 seconds
        comparison="LessThanThreshold",
        description="FPolicy event → SQS delivery latency P99 < 5s",
    ),
    SLOTarget(
        name="ProcessingSuccessRate",
        metric_namespace="FSxN-S3AP-Patterns",
        metric_name="ProcessingSuccessRate_pct",
        threshold=99.5,  # > 99.5% success
        comparison="GreaterThanThreshold",
        description="Step Functions execution success rate > 99.5%",
    ),
    SLOTarget(
        name="ReconnectTime",
        metric_namespace="FSxN-S3AP-Patterns",
        metric_name="FPolicyReconnectTime_sec",
        threshold=30.0,  # < 30 seconds
        comparison="LessThanThreshold",
        description="FPolicy server reconnection time < 30s",
    ),
    SLOTarget(
        name="ReplayCompletionTime",
        metric_namespace="FSxN-S3AP-Patterns",
        metric_name="ReplayCompletionTime_sec",
        threshold=300.0,  # < 5 minutes
        comparison="LessThanThreshold",
        description="Persistent Store replay completion < 5 minutes",
    ),
]

# Feature 3 (Synthetic Monitoring) メトリクス定義
SYNTHETIC_MONITORING_METRICS: list[dict[str, str]] = [
    {
        "namespace": "FSxN-S3AP-Patterns/Canary",
        "metric_name": "S3AP_ListLatency_ms",
        "label": "S3AP List Latency (ms)",
    },
    {
        "namespace": "FSxN-S3AP-Patterns/Canary",
        "metric_name": "S3AP_GetLatency_ms",
        "label": "S3AP Get Latency (ms)",
    },
    {
        "namespace": "FSxN-S3AP-Patterns/Canary",
        "metric_name": "ONTAP_HealthCheck",
        "label": "ONTAP Health (1=OK, 0=Fail)",
    },
]


@dataclass
class SLOEvaluationResult:
    """個別 SLO の評価結果。

    Attributes:
        slo_name: SLO 名称
        met: SLO が達成されているか
        value: 現在のメトリクス値（データなしの場合は None）
        threshold: SLO 閾値
        comparison: 比較演算子
        evaluated_at: 評価時刻（ISO 形式）
        description: SLO の説明
        data_available: メトリクスデータが取得できたか
    """

    slo_name: str
    met: bool
    value: float | None
    threshold: float
    comparison: str
    evaluated_at: str
    description: str = ""
    data_available: bool = True


def evaluate_slos(
    cloudwatch_client: Any,
    targets: list[SLOTarget] | None = None,
    period_sec: int | None = None,
) -> list[SLOEvaluationResult]:
    """全 SLO ターゲットを評価し、結果を返す。

    CloudWatch から各 SLO のメトリクスを取得し、閾値と比較して
    met/violated を判定する。

    Args:
        cloudwatch_client: boto3 CloudWatch クライアント
        targets: 評価対象の SLO リスト（None の場合は SLO_TARGETS を使用）
        period_sec: メトリクス取得期間（秒）。None の場合は各 SLO の period_sec を使用

    Returns:
        各 SLO の評価結果リスト
    """
    if targets is None:
        targets = SLO_TARGETS

    now = datetime.now(timezone.utc)
    results: list[SLOEvaluationResult] = []

    for target in targets:
        eval_period = period_sec if period_sec is not None else target.period_sec
        result = _evaluate_single_slo(cloudwatch_client, target, now, eval_period)
        results.append(result)

    logger.info(
        "SLO evaluation complete: %d targets, %d met, %d violated",
        len(results),
        sum(1 for r in results if r.met),
        sum(1 for r in results if not r.met),
    )

    return results


def _evaluate_single_slo(
    cloudwatch_client: Any,
    target: SLOTarget,
    now: datetime,
    period_sec: int,
) -> SLOEvaluationResult:
    """単一の SLO ターゲットを評価する。

    Args:
        cloudwatch_client: boto3 CloudWatch クライアント
        target: 評価対象の SLO ターゲット
        now: 現在時刻
        period_sec: メトリクス取得期間（秒）

    Returns:
        SLO 評価結果
    """
    from datetime import timedelta

    start_time = now - timedelta(seconds=period_sec)
    evaluated_at = now.isoformat()

    try:
        # CloudWatch GetMetricStatistics で最新値を取得
        # LessThanThreshold の場合は Maximum（最悪値）を使用
        # GreaterThanThreshold の場合は Minimum（最悪値）を使用
        stat = "Maximum" if target.comparison == "LessThanThreshold" else "Minimum"

        response = cloudwatch_client.get_metric_statistics(
            Namespace=target.metric_namespace,
            MetricName=target.metric_name,
            StartTime=start_time,
            EndTime=now,
            Period=period_sec,
            Statistics=[stat],
        )

        datapoints = response.get("Datapoints", [])

        if not datapoints:
            # データなし — SLO 判定不可（met=True として扱う）
            logger.warning(
                "No datapoints for SLO %s (%s/%s) in last %d seconds",
                target.name,
                target.metric_namespace,
                target.metric_name,
                period_sec,
            )
            return SLOEvaluationResult(
                slo_name=target.name,
                met=True,
                value=None,
                threshold=target.threshold,
                comparison=target.comparison,
                evaluated_at=evaluated_at,
                description=target.description,
                data_available=False,
            )

        # 最新のデータポイントを使用
        latest = max(datapoints, key=lambda dp: dp["Timestamp"])
        value = latest[stat]

        # 閾値比較
        met = _compare_threshold(value, target.threshold, target.comparison)

        return SLOEvaluationResult(
            slo_name=target.name,
            met=met,
            value=value,
            threshold=target.threshold,
            comparison=target.comparison,
            evaluated_at=evaluated_at,
            description=target.description,
            data_available=True,
        )

    except Exception as e:
        logger.error("Failed to evaluate SLO %s: %s", target.name, str(e))
        # エラー時はデータなしとして扱う
        return SLOEvaluationResult(
            slo_name=target.name,
            met=True,
            value=None,
            threshold=target.threshold,
            comparison=target.comparison,
            evaluated_at=evaluated_at,
            description=target.description,
            data_available=False,
        )


def _compare_threshold(value: float, threshold: float, comparison: str) -> bool:
    """メトリクス値と閾値を比較する。

    Args:
        value: メトリクス値
        threshold: 閾値
        comparison: 比較演算子

    Returns:
        SLO が達成されているか（True = met）
    """
    if comparison == "LessThanThreshold":
        return value < threshold
    elif comparison == "GreaterThanThreshold":
        return value > threshold
    else:
        raise ValueError(f"Unknown comparison operator: {comparison}")


def generate_dashboard_widgets(
    region: str = "ap-northeast-1",
    targets: list[SLOTarget] | None = None,
    include_synthetic_monitoring: bool = True,
) -> list[dict[str, Any]]:
    """CloudWatch ダッシュボード用のウィジェット JSON を生成する。

    SLO メトリクスと Feature 3（Synthetic Monitoring）メトリクスを
    統合したダッシュボードウィジェット定義を返す。

    Args:
        region: AWS リージョン
        targets: SLO ターゲットリスト（None の場合は SLO_TARGETS を使用）
        include_synthetic_monitoring: Feature 3 メトリクスを含めるか

    Returns:
        CloudWatch ダッシュボードウィジェット定義のリスト
    """
    if targets is None:
        targets = SLO_TARGETS

    widgets: list[dict[str, Any]] = []
    y_offset = 0

    # SLO サマリーウィジェット（テキスト）
    widgets.append(
        {
            "type": "text",
            "x": 0,
            "y": y_offset,
            "width": 24,
            "height": 2,
            "properties": {
                "markdown": "# SLO Dashboard — FSxN S3AP Serverless Patterns\n"
                "Service Level Objectives for the event-driven pipeline."
            },
        }
    )
    y_offset += 2

    # 各 SLO のメトリクスウィジェット
    for i, target in enumerate(targets):
        col = (i % 2) * 12
        if i % 2 == 0 and i > 0:
            y_offset += 6

        widget = _create_slo_metric_widget(target, region, col, y_offset)
        widgets.append(widget)

    y_offset += 6

    # Feature 3 (Synthetic Monitoring) 統合ウィジェット
    if include_synthetic_monitoring:
        widgets.append(
            {
                "type": "text",
                "x": 0,
                "y": y_offset,
                "width": 24,
                "height": 1,
                "properties": {
                    "markdown": "## Synthetic Monitoring — S3AP & ONTAP Health"
                },
            }
        )
        y_offset += 1

        sm_widget = _create_synthetic_monitoring_widget(region, y_offset)
        widgets.append(sm_widget)
        y_offset += 6

    return widgets


def _create_slo_metric_widget(
    target: SLOTarget,
    region: str,
    x: int,
    y: int,
) -> dict[str, Any]:
    """個別 SLO のメトリクスウィジェットを生成する。

    閾値ラインを含むグラフウィジェットを返す。

    Args:
        target: SLO ターゲット
        region: AWS リージョン
        x: ウィジェットの X 座標
        y: ウィジェットの Y 座標

    Returns:
        ウィジェット定義辞書
    """
    return {
        "type": "metric",
        "x": x,
        "y": y,
        "width": 12,
        "height": 6,
        "properties": {
            "metrics": [
                [
                    target.metric_namespace,
                    target.metric_name,
                    {"label": target.name, "stat": "p99" if "Latency" in target.metric_name else "Average"},
                ],
            ],
            "title": f"{target.name} (threshold: {target.threshold})",
            "region": region,
            "period": target.period_sec,
            "annotations": {
                "horizontal": [
                    {
                        "label": f"SLO Threshold ({target.threshold})",
                        "value": target.threshold,
                        "color": "#d13212",
                    }
                ]
            },
            "view": "timeSeries",
            "stacked": False,
        },
    }


def _create_synthetic_monitoring_widget(
    region: str,
    y: int,
) -> dict[str, Any]:
    """Feature 3 (Synthetic Monitoring) 統合ウィジェットを生成する。

    S3AP レイテンシと ONTAP ヘルスチェックのメトリクスを
    1 つのグラフにまとめて表示する。

    Args:
        region: AWS リージョン
        y: ウィジェットの Y 座標

    Returns:
        ウィジェット定義辞書
    """
    metrics = []
    for sm_metric in SYNTHETIC_MONITORING_METRICS:
        metrics.append(
            [
                sm_metric["namespace"],
                sm_metric["metric_name"],
                {"label": sm_metric["label"]},
            ]
        )

    return {
        "type": "metric",
        "x": 0,
        "y": y,
        "width": 24,
        "height": 6,
        "properties": {
            "metrics": metrics,
            "title": "Synthetic Monitoring — S3AP & ONTAP Health Checks",
            "region": region,
            "period": 300,
            "view": "timeSeries",
            "stacked": False,
        },
    }
