"""OPS2 Report Handler — ストレージ効率レポート."""

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
    total_recs = event.get("total_recommendations", 0)
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
            json_key = f"reports/{date_prefix}/{fs_id}/efficiency-report.json"
            s3_client.put_object(
                Bucket=report_bucket,
                Key=json_key,
                Body=json.dumps(report_data, ensure_ascii=False, indent=2),
                ContentType="application/json",
            )

        html_key = None
        if report_format in ("HTML", "BOTH"):
            html_key = f"reports/{date_prefix}/{fs_id}/efficiency-report.html"
            s3_client.put_object(
                Bucket=report_bucket,
                Key=html_key,
                Body=f"<html><body><h1>OPS2 Efficiency Report - {fs_id}</h1><pre>{json.dumps(report_data, ensure_ascii=False, indent=2)}</pre></body></html>".encode(),
                ContentType="text/html; charset=utf-8",
            )

        cw_client.put_metric_data(
            Namespace=CW_NAMESPACE,
            MetricData=[
                {
                    "MetricName": "AvgEfficiencyRatio",
                    "Value": summary.get("avg_efficiency_ratio", 1.0),
                    "Unit": "None",
                    "Dimensions": [{"Name": "FileSystemId", "Value": fs_id}],
                },
                {
                    "MetricName": "EfficiencyRecommendationCount",
                    "Value": summary.get("recommendation_count", 0),
                    "Unit": "Count",
                    "Dimensions": [{"Name": "FileSystemId", "Value": fs_id}],
                },
                {
                    "MetricName": "TotalDedupSavingsGB",
                    "Value": summary.get("total_dedupe_savings_gb", 0),
                    "Unit": "Gigabytes",
                    "Dimensions": [{"Name": "FileSystemId", "Value": fs_id}],
                },
            ],
        )

        alert_required = automation_level >= 1 and len(recommendations) > 0
        if alert_required and alert_topic_arn:
            sns = boto3.client("sns")
            sns.publish(
                TopicArn=alert_topic_arn,
                Subject=f"[OPS2] Efficiency Alert - {fs_id}",
                Message=f"Recommendations: {len(recommendations)}\nPotential Savings: ${summary.get('total_potential_savings_usd', 0):.2f}/month",
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

    return {"reports": results, "total_recommendations": total_recs, "reported_at": now.isoformat()}
