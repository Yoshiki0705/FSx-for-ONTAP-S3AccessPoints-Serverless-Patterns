"""OPS6 Report Handler — QoS モニタリングレポート."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

CW_NAMESPACE = "FSxOps"


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    report_bucket = os.environ.get("REPORT_BUCKET", "")
    report_format = os.environ.get("REPORT_FORMAT", "BOTH")
    automation_level = int(os.environ.get("AUTOMATION_LEVEL", "0"))
    alert_topic_arn = os.environ.get("ALERT_TOPIC_ARN", "")

    analyses = event.get("analyses", [])
    s3_client = boto3.client("s3")
    cw_client = boto3.client("cloudwatch")
    now = datetime.now(UTC)
    date_prefix = now.strftime("%Y/%m/%d")

    results = []
    for analysis in analyses:
        fs_id = analysis.get("fs_id", "unknown")
        summary = analysis.get("summary", {})
        recommendations = analysis.get("recommendations", [])

        report_data = {
            "fs_id": fs_id,
            "generated_at": now.isoformat(),
            "summary": summary,
            "recommendations": recommendations,
            "ai_summary": analysis.get("ai_summary"),
        }

        json_key = None
        if report_format in ("JSON", "BOTH"):
            json_key = f"reports/{date_prefix}/{fs_id}/qos-report.json"
            s3_client.put_object(
                Bucket=report_bucket,
                Key=json_key,
                Body=json.dumps(report_data, ensure_ascii=False, indent=2),
                ContentType="application/json",
            )

        cw_client.put_metric_data(
            Namespace=CW_NAMESPACE,
            MetricData=[
                {
                    "MetricName": "QoSPoliciesWithLimits",
                    "Value": summary.get("policies_with_limits", 0),
                    "Unit": "Count",
                    "Dimensions": [{"Name": "FileSystemId", "Value": fs_id}],
                },
                {
                    "MetricName": "VolumesWithoutQoS",
                    "Value": summary.get("volumes_without_qos", 0),
                    "Unit": "Count",
                    "Dimensions": [{"Name": "FileSystemId", "Value": fs_id}],
                },
                {
                    "MetricName": "QoSRecommendationCount",
                    "Value": summary.get("recommendation_count", 0),
                    "Unit": "Count",
                    "Dimensions": [{"Name": "FileSystemId", "Value": fs_id}],
                },
            ],
        )

        alert_required = automation_level >= 1 and len(recommendations) > 0
        if alert_required and alert_topic_arn:
            sns = boto3.client("sns")
            sns.publish(
                TopicArn=alert_topic_arn,
                Subject=f"[OPS6] QoS Alert - {fs_id}",
                Message=f"QoS recommendations: {len(recommendations)}",
            )

        results.append(
            {
                "fs_id": fs_id,
                "report_s3_key": json_key,
                "recommendation_count": len(recommendations),
                "alert_required": alert_required,
                "reported_at": now.isoformat(),
            }
        )

    return {
        "reports": results,
        "total_recommendations": event.get("total_recommendations", 0),
        "reported_at": now.isoformat(),
    }
