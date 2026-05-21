"""Dynamic FlexCache Workflow Report Lambda

ワークフロー全体の結果レポートを生成し、S3 に保存・SNS 通知する。
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
    """Report Lambda ハンドラー"""
    logger.info("Generating workflow report")

    timestamp = datetime.now(timezone.utc)
    job_id = event.get("job_id", "unknown")
    project = event.get("project", "unknown")

    report = {
        "report_type": "dynamic_flexcache_workflow",
        "generated_at": timestamp.isoformat(),
        "job_id": job_id,
        "project": project,
        "workflow_summary": {
            "flexcache_created": event.get("flexcache_status", {}).get("status") == "created",
            "job_submitted": event.get("job_status", {}).get("status") == "submitted",
            "job_completed": event.get("monitor_result", {}).get("is_success", False),
            "flexcache_cleaned": event.get("cleanup_status", {}).get("status") in ("deleted", "already_deleted"),
        },
        "timing": {
            "workflow_start": event.get("workflow_start_time", 0),
            "workflow_end": int(time.time()),
        },
        "details": {
            "flexcache": event.get("flexcache_status", {}),
            "job": event.get("monitor_result", {}),
            "cleanup": event.get("cleanup_status", {}),
        },
    }

    # S3 に保存
    report_key = _save_report(report, job_id, timestamp)

    # 通知
    _send_notification(report)

    return {
        "status": "completed",
        "report_key": report_key,
        "job_id": job_id,
        "timestamp": int(time.time()),
    }


def _save_report(report: dict, job_id: str, timestamp: datetime) -> str:
    """レポートを S3 に保存"""
    output_bucket = os.environ.get("OUTPUT_BUCKET", "")
    if not output_bucket:
        return ""

    date_prefix = timestamp.strftime("%Y/%m/%d")
    report_key = f"workflow-reports/{date_prefix}/{job_id}.json"

    try:
        s3_client.put_object(
            Bucket=output_bucket,
            Key=report_key,
            Body=json.dumps(report, indent=2, ensure_ascii=False),
            ContentType="application/json",
        )
        return report_key
    except Exception as e:
        logger.error("Failed to save report: %s", str(e))
        return ""


def _send_notification(report: dict) -> None:
    """SNS 通知"""
    topic_arn = os.environ.get("NOTIFICATION_TOPIC_ARN", "")
    if not topic_arn:
        return

    job_id = report.get("job_id", "unknown")
    success = report.get("workflow_summary", {}).get("job_completed", False)
    status_emoji = "✅" if success else "❌"

    subject = f"{status_emoji} FlexCache Workflow: {job_id}"
    message = json.dumps(report, indent=2, ensure_ascii=False)

    try:
        sns_client.publish(
            TopicArn=topic_arn,
            Subject=subject[:100],
            Message=message[:262144],
        )
    except Exception as e:
        logger.error("Failed to send notification: %s", str(e))
