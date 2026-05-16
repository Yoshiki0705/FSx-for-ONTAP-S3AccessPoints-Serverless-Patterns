"""shared.lambdas.capacity_forecast.handler — Capacity Forecast Lambda

CloudWatch メトリクスの FSx ストレージ使用量データから線形回帰で容量枯渇予測日を算出する。
EventBridge Scheduler により日次で自動実行される。

アルゴリズム:
- CloudWatch GetMetricData で過去 30 日間の FSx ストレージ使用量を取得
- 最小二乗法による線形回帰で増加傾向を算出（標準ライブラリ math のみ使用）
- 容量枯渇予測日（DaysUntilFull）を CloudWatch カスタムメトリクスとして発行
- 閾値以下（デフォルト 30 日）で SNS アラート送信

エッジケース:
- データポイント不足（2 点未満）: DaysUntilFull = -1
- slope <= 0（使用量減少/横ばい）: DaysUntilFull = -1

Usage:
    # EventBridge Scheduler が自動的に呼び出す
    # event = {"file_system_id": "fs-0123456789abcdef0"}
"""

from __future__ import annotations

import logging
import math
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Constants
SECONDS_PER_DAY = 86400
BYTES_PER_GB = 1024 * 1024 * 1024
DEFAULT_LOOKBACK_DAYS = 30
DEFAULT_THRESHOLD_DAYS = 30
METRIC_NAMESPACE = "FSxN-S3AP-Patterns"
METRIC_NAME_DAYS_UNTIL_FULL = "DaysUntilFull"


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Capacity forecast handler.

    Args:
        event: EventBridge イベント
            - file_system_id: FSx ファイルシステム ID（オプション、環境変数でも指定可）
        context: Lambda コンテキスト

    Returns:
        予測結果の辞書:
            - days_until_full: 容量枯渇までの日数（-1 = 予測不可）
            - current_usage_pct: 現在の使用率（%）
            - total_capacity_gb: 総容量（GB）
            - growth_rate_gb_per_day: 日次増加量（GB/日）
            - forecast_date: 予測枯渇日（ISO format）
    """
    # Resolve configuration from event or environment variables
    file_system_id = event.get("file_system_id") or os.environ.get(
        "FILE_SYSTEM_ID", ""
    )
    total_capacity_gb = float(
        event.get("total_capacity_gb")
        or os.environ.get("TOTAL_CAPACITY_GB", "1024")
    )
    threshold_days = int(
        event.get("threshold_days")
        or os.environ.get("THRESHOLD_DAYS", str(DEFAULT_THRESHOLD_DAYS))
    )
    lookback_days = int(
        event.get("lookback_days")
        or os.environ.get("LOOKBACK_DAYS", str(DEFAULT_LOOKBACK_DAYS))
    )
    sns_topic_arn = os.environ.get("SNS_TOPIC_ARN", "")

    if not file_system_id:
        logger.error("FILE_SYSTEM_ID is not configured.")
        raise ValueError("FILE_SYSTEM_ID must be provided via event or environment variable.")

    logger.info(
        "Starting capacity forecast for file_system_id=%s, "
        "total_capacity_gb=%.1f, threshold_days=%d, lookback_days=%d",
        file_system_id,
        total_capacity_gb,
        threshold_days,
        lookback_days,
    )

    # Fetch usage metrics from CloudWatch
    data_points = fetch_usage_metrics(file_system_id, days=lookback_days)
    current_time = time.time()

    # Handle insufficient data points
    if len(data_points) < 2:
        logger.warning(
            "Insufficient data points (%d) for regression. "
            "Publishing DaysUntilFull = -1.",
            len(data_points),
        )
        days_until_full = -1
        growth_rate_gb_per_day = 0.0
        current_usage_pct = 0.0
        forecast_date = ""

        _publish_metric(file_system_id, days_until_full)

        return {
            "days_until_full": days_until_full,
            "current_usage_pct": current_usage_pct,
            "total_capacity_gb": total_capacity_gb,
            "growth_rate_gb_per_day": growth_rate_gb_per_day,
            "forecast_date": forecast_date,
        }

    # Perform linear regression
    slope, intercept = linear_regression(data_points)

    # Predict days until full
    days_until_full = predict_days_until_full(
        slope, intercept, total_capacity_gb, current_time
    )

    # Calculate current usage and growth rate
    current_usage_gb = slope * current_time + intercept
    current_usage_pct = (
        (current_usage_gb / total_capacity_gb) * 100.0
        if total_capacity_gb > 0
        else 0.0
    )
    # Convert slope from GB/second to GB/day
    growth_rate_gb_per_day = slope * SECONDS_PER_DAY

    # Calculate forecast date
    if days_until_full > 0:
        forecast_dt = datetime.now(timezone.utc) + timedelta(days=days_until_full)
        forecast_date = forecast_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        forecast_date = ""

    logger.info(
        "Forecast result: days_until_full=%d, current_usage_pct=%.1f%%, "
        "growth_rate=%.4f GB/day, forecast_date=%s",
        days_until_full,
        current_usage_pct,
        growth_rate_gb_per_day,
        forecast_date or "N/A",
    )

    # Publish DaysUntilFull metric to CloudWatch
    _publish_metric(file_system_id, days_until_full)

    # Send SNS alert if days_until_full is within threshold
    if 0 <= days_until_full <= threshold_days and sns_topic_arn:
        _send_alert(
            sns_topic_arn=sns_topic_arn,
            file_system_id=file_system_id,
            days_until_full=days_until_full,
            current_usage_pct=current_usage_pct,
            total_capacity_gb=total_capacity_gb,
            growth_rate_gb_per_day=growth_rate_gb_per_day,
            forecast_date=forecast_date,
        )

    return {
        "days_until_full": days_until_full,
        "current_usage_pct": round(current_usage_pct, 2),
        "total_capacity_gb": total_capacity_gb,
        "growth_rate_gb_per_day": round(growth_rate_gb_per_day, 4),
        "forecast_date": forecast_date,
    }


def fetch_usage_metrics(
    file_system_id: str,
    days: int = 30,
) -> list[tuple[float, float]]:
    """CloudWatch から FSx ストレージ使用量メトリクスを取得する。

    CloudWatch GetMetricData API を使用して AWS/FSx namespace の
    StorageUsed メトリクスを取得する。

    Args:
        file_system_id: FSx ファイルシステム ID
        days: 取得する日数（デフォルト: 30 日）

    Returns:
        (timestamp_epoch, usage_gb) のタプルリスト（時系列順）
    """
    cw_client = boto3.client("cloudwatch")

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)

    # Use GetMetricData for efficient metric retrieval
    response = cw_client.get_metric_data(
        MetricDataQueries=[
            {
                "Id": "storage_used",
                "MetricStat": {
                    "Metric": {
                        "Namespace": "AWS/FSx",
                        "MetricName": "StorageUsed",
                        "Dimensions": [
                            {
                                "Name": "FileSystemId",
                                "Value": file_system_id,
                            }
                        ],
                    },
                    "Period": 3600,  # 1-hour granularity
                    "Stat": "Average",
                },
                "ReturnData": True,
            }
        ],
        StartTime=start_time,
        EndTime=end_time,
        ScanBy="TimestampAscending",
    )

    # Extract data points
    data_points: list[tuple[float, float]] = []
    results = response.get("MetricDataResults", [])

    if results:
        timestamps = results[0].get("Timestamps", [])
        values = results[0].get("Values", [])

        for ts, val in zip(timestamps, values):
            # Convert timestamp to epoch seconds
            epoch = ts.timestamp() if hasattr(ts, "timestamp") else float(ts)
            # Convert bytes to GB
            usage_gb = val / BYTES_PER_GB
            data_points.append((epoch, usage_gb))

    # Sort by timestamp (ascending) to ensure correct ordering
    data_points.sort(key=lambda p: p[0])

    logger.info(
        "Fetched %d data points for file_system_id=%s over %d days.",
        len(data_points),
        file_system_id,
        days,
    )

    return data_points


def linear_regression(
    data_points: list[tuple[float, float]],
) -> tuple[float, float]:
    """最小二乗法による線形回帰を実行する。

    標準ライブラリ（math モジュール）のみで実装。外部依存なし。
    y = slope * x + intercept の形式で回帰直線を算出する。

    Args:
        data_points: (x, y) のタプルリスト

    Returns:
        (slope, intercept) のタプル

    Raises:
        ValueError: データポイントが 2 点未満の場合
    """
    n = len(data_points)
    if n < 2:
        raise ValueError("Need at least 2 data points for regression")

    sum_x = 0.0
    sum_y = 0.0
    sum_xy = 0.0
    sum_x2 = 0.0

    for x, y in data_points:
        sum_x += x
        sum_y += y
        sum_xy += x * y
        sum_x2 += x * x

    denominator = n * sum_x2 - sum_x * sum_x

    # If all x values are identical (or nearly so), return flat line
    if abs(denominator) < 1e-10:
        return (0.0, sum_y / n)

    slope = (n * sum_xy - sum_x * sum_y) / denominator
    intercept = (sum_y - slope * sum_x) / n

    return (slope, intercept)


def predict_days_until_full(
    slope: float,
    intercept: float,
    total_capacity: float,
    current_time: float,
) -> int:
    """容量枯渇までの日数を予測する。

    Args:
        slope: 線形回帰の傾き（GB/秒）
        intercept: 線形回帰の切片（GB）
        total_capacity: 総容量（GB）
        current_time: 現在時刻（epoch 秒）

    Returns:
        容量枯渇までの日数。slope <= 0 の場合は -1。
        既に容量超過の場合は 0。
    """
    # Calculate current usage from regression line
    current_usage = slope * current_time + intercept

    # Already at or above capacity
    if current_usage >= total_capacity:
        return 0

    # No growth or shrinking — never fills up
    if slope <= 0:
        return -1

    # Time when usage reaches capacity: total_capacity = slope * t + intercept
    time_at_full = (total_capacity - intercept) / slope
    seconds_remaining = time_at_full - current_time

    # Guard against overflow for extremely large values
    if not math.isfinite(seconds_remaining) or seconds_remaining > 1e15:
        return -1

    days_remaining = int(seconds_remaining / SECONDS_PER_DAY)

    return max(0, days_remaining)


def _publish_metric(file_system_id: str, days_until_full: int) -> None:
    """CloudWatch カスタムメトリクス DaysUntilFull を発行する。

    Args:
        file_system_id: FSx ファイルシステム ID
        days_until_full: 容量枯渇までの日数
    """
    try:
        cw_client = boto3.client("cloudwatch")
        cw_client.put_metric_data(
            Namespace=METRIC_NAMESPACE,
            MetricData=[
                {
                    "MetricName": METRIC_NAME_DAYS_UNTIL_FULL,
                    "Dimensions": [
                        {
                            "Name": "FileSystemId",
                            "Value": file_system_id,
                        }
                    ],
                    "Value": float(days_until_full),
                    "Unit": "Count",
                }
            ],
        )
        logger.info(
            "Published metric %s=%d for FileSystemId=%s.",
            METRIC_NAME_DAYS_UNTIL_FULL,
            days_until_full,
            file_system_id,
        )
    except Exception as e:
        logger.error("Failed to publish CloudWatch metric: %s", str(e))


def _send_alert(
    sns_topic_arn: str,
    file_system_id: str,
    days_until_full: int,
    current_usage_pct: float,
    total_capacity_gb: float,
    growth_rate_gb_per_day: float,
    forecast_date: str,
) -> None:
    """容量枯渇予測が閾値以下の場合に SNS アラートを送信する。

    Args:
        sns_topic_arn: SNS トピック ARN
        file_system_id: FSx ファイルシステム ID
        days_until_full: 容量枯渇までの日数
        current_usage_pct: 現在の使用率（%）
        total_capacity_gb: 総容量（GB）
        growth_rate_gb_per_day: 日次増加量（GB/日）
        forecast_date: 予測枯渇日（ISO format）
    """
    try:
        sns_client = boto3.client("sns")
        sns_client.publish(
            TopicArn=sns_topic_arn,
            Subject=(
                f"[Capacity Forecast] Storage exhaustion in {days_until_full} days "
                f"- {file_system_id}"
            ),
            Message=(
                f"FSx Storage Capacity Forecast Alert\n"
                f"{'=' * 50}\n\n"
                f"File System ID: {file_system_id}\n"
                f"Days Until Full: {days_until_full}\n"
                f"Forecast Date: {forecast_date}\n"
                f"Current Usage: {current_usage_pct:.1f}%\n"
                f"Total Capacity: {total_capacity_gb:.1f} GB\n"
                f"Growth Rate: {growth_rate_gb_per_day:.4f} GB/day\n\n"
                f"Action Required: Please review storage capacity and consider "
                f"expanding the file system or cleaning up unused data."
            ),
        )
        logger.info(
            "Capacity alert sent to SNS topic %s for FileSystemId=%s.",
            sns_topic_arn,
            file_system_id,
        )
    except Exception as e:
        logger.error("Failed to send SNS alert: %s", str(e))
