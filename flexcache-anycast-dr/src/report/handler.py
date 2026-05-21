"""FlexCache Report Lambda

ヘルスチェック結果、ルーティング判定結果、Discovery 結果を
統合レポートとして生成し、S3 に保存・SNS 通知する。
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

s3_client = boto3.client("s3")
sns_client = boto3.client("sns")


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """FlexCache Report Lambda ハンドラー

    Args:
        event: {
            "health_check_result": {...},
            "route_decision_result": {...},
            "discovery_result": {...},
            "report_type": "health" | "failover" | "summary"
        }

    Returns:
        dict: レポート生成結果
    """
    logger.info("Report generation started")

    report_type = event.get("report_type", "summary")
    timestamp = datetime.now(timezone.utc)

    # レポート生成
    report = _generate_report(event, report_type, timestamp)

    # S3 に保存
    report_key = _save_report(report, report_type, timestamp)

    # 異常検出時は SNS 通知
    notification_sent = False
    if _should_notify(event, report_type):
        _send_notification(report, report_type)
        notification_sent = True

    result = {
        "status": "completed",
        "report_type": report_type,
        "report_key": report_key,
        "notification_sent": notification_sent,
        "timestamp": int(time.time()),
    }

    logger.info("Report generation completed: %s", report_key)
    return result


def _generate_report(
    event: dict[str, Any],
    report_type: str,
    timestamp: datetime,
) -> dict[str, Any]:
    """レポートを生成"""
    report = {
        "report_type": report_type,
        "generated_at": timestamp.isoformat(),
        "generated_by": "flexcache-anycast-report-lambda",
    }

    if report_type == "health":
        health_result = event.get("health_check_result", {})
        report["health_summary"] = health_result.get("summary", {})
        report["cache_details"] = health_result.get("results", [])
        report["recommendation"] = _generate_health_recommendation(health_result)

    elif report_type == "failover":
        report["failover_event"] = event.get("failover_event", {})
        report["route_decision"] = event.get("route_decision_result", {})
        report["impact_assessment"] = _assess_failover_impact(event)

    elif report_type == "summary":
        report["health"] = event.get("health_check_result", {}).get("summary", {})
        report["routing"] = event.get("route_decision_result", {})
        report["discovery"] = {
            "object_count": event.get("discovery_result", {}).get("object_count", 0),
            "s3ap_alias": event.get("discovery_result", {}).get("s3ap_alias", ""),
        }

    return report


def _generate_health_recommendation(health_result: dict) -> str:
    """ヘルスチェック結果に基づく推奨事項を生成"""
    summary = health_result.get("summary", {})
    unhealthy = summary.get("unhealthy", 0)
    total = summary.get("total_caches", 0)

    if unhealthy == 0:
        return "All caches healthy. No action required."
    elif unhealthy < total:
        return (
            f"{unhealthy}/{total} caches unhealthy. "
            "Investigate unhealthy nodes. Traffic automatically routed to healthy caches."
        )
    else:
        return (
            "ALL caches unhealthy. CRITICAL: Immediate investigation required. "
            "Consider failover to origin or DR site."
        )


def _assess_failover_impact(event: dict) -> dict[str, Any]:
    """フェイルオーバーの影響評価"""
    return {
        "affected_caches": event.get("failover_event", {}).get("affected_caches", []),
        "estimated_rto_seconds": 60,
        "data_at_risk": "None (read cache only)",
        "client_impact": "Temporary latency increase during failover",
    }


def _save_report(report: dict, report_type: str, timestamp: datetime) -> str:
    """レポートを S3 に保存"""
    output_bucket = os.environ.get("OUTPUT_BUCKET", "")
    if not output_bucket:
        logger.warning("OUTPUT_BUCKET not set, skipping S3 save")
        return ""

    date_prefix = timestamp.strftime("%Y/%m/%d")
    time_suffix = timestamp.strftime("%H%M%S")
    report_key = f"flexcache-reports/{report_type}/{date_prefix}/{time_suffix}.json"

    try:
        s3_client.put_object(
            Bucket=output_bucket,
            Key=report_key,
            Body=json.dumps(report, indent=2, ensure_ascii=False),
            ContentType="application/json",
        )
        logger.info("Report saved to s3://%s/%s", output_bucket, report_key)
        return report_key
    except Exception as e:
        logger.error("Failed to save report: %s", str(e))
        return ""


def _should_notify(event: dict, report_type: str) -> bool:
    """SNS 通知が必要か判定"""
    if report_type == "failover":
        return True

    if report_type == "health":
        summary = event.get("health_check_result", {}).get("summary", {})
        return summary.get("unhealthy", 0) > 0

    return False


def _send_notification(report: dict, report_type: str) -> None:
    """SNS 通知を送信"""
    topic_arn = os.environ.get("NOTIFICATION_TOPIC_ARN", "")
    if not topic_arn:
        logger.warning("NOTIFICATION_TOPIC_ARN not set, skipping notification")
        return

    subject = f"[FlexCache AnyCast] {report_type.upper()} Alert"
    message = json.dumps(report, indent=2, ensure_ascii=False)

    try:
        sns_client.publish(
            TopicArn=topic_arn,
            Subject=subject[:100],
            Message=message[:262144],  # SNS message size limit
        )
        logger.info("Notification sent to %s", topic_arn)
    except Exception as e:
        logger.error("Failed to send notification: %s", str(e))
