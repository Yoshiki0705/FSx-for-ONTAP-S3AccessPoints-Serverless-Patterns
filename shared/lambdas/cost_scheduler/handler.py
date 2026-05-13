"""Cost Scheduler — 営業時間ベースのスケジュール動的変更.

EventBridge Scheduler の ScheduleExpression を営業時間帯と非営業時間帯で
切り替えることで、不要な Lambda 実行コストを削減する。

動作:
- 営業時間開始時（平日 09:00 JST）: rate(1 hour) に変更
- 営業時間終了時（平日 18:00 JST）: rate(6 hours) に変更

Environment Variables:
    SCHEDULER_GROUP_NAME: EventBridge Scheduler グループ名
    BUSINESS_HOURS_RATE: 営業時間帯のレート (default: "rate(1 hour)")
    OFF_HOURS_RATE: 非営業時間帯のレート (default: "rate(6 hours)")
"""

from __future__ import annotations

import logging
import os
from typing import Any

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """スケジュール式を切り替える.

    Args:
        event: EventBridge Scheduler からのイベント
            {"action": "business_hours_start" | "business_hours_end"}
        context: Lambda コンテキスト

    Returns:
        dict: 更新結果 (updated_schedules, new_rate)
    """
    scheduler_group = os.environ["SCHEDULER_GROUP_NAME"]
    business_rate = os.environ.get("BUSINESS_HOURS_RATE", "rate(1 hour)")
    off_hours_rate = os.environ.get("OFF_HOURS_RATE", "rate(6 hours)")

    action = event.get("action", "business_hours_end")

    if action == "business_hours_start":
        new_rate = business_rate
    else:
        new_rate = off_hours_rate

    scheduler_client = boto3.client("scheduler")
    updated_schedules: list[str] = []

    try:
        # List all schedules in the group
        paginator = scheduler_client.get_paginator("list_schedules")
        for page in paginator.paginate(GroupName=scheduler_group):
            for schedule in page.get("Schedules", []):
                schedule_name = schedule["Name"]

                try:
                    # Get current schedule details
                    current = scheduler_client.get_schedule(
                        Name=schedule_name,
                        GroupName=scheduler_group,
                    )

                    # Update schedule expression
                    scheduler_client.update_schedule(
                        Name=schedule_name,
                        GroupName=scheduler_group,
                        ScheduleExpression=new_rate,
                        FlexibleTimeWindow=current["FlexibleTimeWindow"],
                        Target=current["Target"],
                        State=current.get("State", "ENABLED"),
                    )

                    updated_schedules.append(schedule_name)
                    logger.info(
                        "Updated schedule %s to %s", schedule_name, new_rate
                    )

                except Exception as e:
                    logger.error(
                        "Failed to update schedule %s: %s",
                        schedule_name,
                        str(e),
                    )

    except Exception as e:
        logger.error("Failed to list schedules: %s", str(e))
        return {
            "statusCode": 500,
            "error": str(e),
            "updated_schedules": [],
            "new_rate": new_rate,
        }

    # Emit cost savings metric
    savings = estimate_monthly_savings(
        business_hours_rate_minutes=_rate_to_minutes(business_rate),
        off_hours_rate_minutes=_rate_to_minutes(off_hours_rate),
    )
    _emit_savings_metric(savings)

    logger.info(
        "Updated %d schedules to %s (estimated savings: $%.4f/month)",
        len(updated_schedules),
        new_rate,
        savings,
    )

    return {
        "statusCode": 200,
        "updated_schedules": updated_schedules,
        "new_rate": new_rate,
        "estimated_monthly_savings_usd": round(savings, 4),
    }


def estimate_monthly_savings(
    business_hours_rate_minutes: int = 60,
    off_hours_rate_minutes: int = 360,
    lambda_cost_per_invocation: float = 0.0000002,
    lambda_duration_ms: int = 5000,
    lambda_memory_mb: int = 512,
) -> float:
    """月間コスト削減見積もりを算出する.

    Args:
        business_hours_rate_minutes: 営業時間帯の実行間隔（分）
        off_hours_rate_minutes: 非営業時間帯の実行間隔（分）
        lambda_cost_per_invocation: Lambda 1 回あたりのリクエスト料金
        lambda_duration_ms: Lambda 平均実行時間（ミリ秒）
        lambda_memory_mb: Lambda メモリサイズ（MB）

    Returns:
        float: 月間推定削減額（USD）
    """
    # Business hours: 9 hours/day × 5 days/week × 4.33 weeks/month
    business_hours_per_month = 9 * 5 * 4.33  # ~195 hours
    # Off hours: 15 hours/day × 5 days + 24 hours × 2 days × 4.33 weeks
    off_hours_per_month = (15 * 5 + 24 * 2) * 4.33  # ~533 hours

    # Invocations without cost scheduling (always business rate)
    total_hours_per_month = business_hours_per_month + off_hours_per_month
    invocations_without = total_hours_per_month * 60 / business_hours_rate_minutes

    # Invocations with cost scheduling
    invocations_business = (
        business_hours_per_month * 60 / business_hours_rate_minutes
    )
    invocations_off = off_hours_per_month * 60 / off_hours_rate_minutes
    invocations_with = invocations_business + invocations_off

    # Cost per invocation (request + duration)
    # Duration cost: $0.0000166667 per GB-second
    duration_cost = (
        (lambda_duration_ms / 1000)
        * (lambda_memory_mb / 1024)
        * 0.0000166667
    )
    cost_per_invocation = lambda_cost_per_invocation + duration_cost

    # Savings
    saved_invocations = invocations_without - invocations_with
    savings = saved_invocations * cost_per_invocation

    return max(savings, 0.0)


def _rate_to_minutes(rate_expression: str) -> int:
    """rate() 式を分に変換する."""
    # "rate(1 hour)" → 60, "rate(6 hours)" → 360
    parts = rate_expression.replace("rate(", "").replace(")", "").split()
    value = int(parts[0])
    unit = parts[1].rstrip("s")  # Remove plural 's'

    if unit == "minute":
        return value
    elif unit == "hour":
        return value * 60
    elif unit == "day":
        return value * 60 * 24
    else:
        return 60  # Default fallback


def _emit_savings_metric(savings: float) -> None:
    """月間コスト削減見積もりメトリクスを出力する."""
    try:
        cw_client = boto3.client("cloudwatch")
        cw_client.put_metric_data(
            Namespace="FSxN-S3AP-Patterns",
            MetricData=[
                {
                    "MetricName": "EstimatedMonthlySavings",
                    "Value": savings,
                    "Unit": "None",
                }
            ],
        )
    except Exception as e:
        logger.warning("Failed to emit savings metric: %s", str(e))
