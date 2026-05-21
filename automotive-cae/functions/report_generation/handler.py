"""Automotive CAE Report Generation Lambda

CAE 分析結果のレポートを生成し、S3 に保存・SNS 通知する。
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
    """Report Generation ハンドラー"""
    timestamp = datetime.now(timezone.utc)

    discovery = event.get("discovery", {})
    processed = event.get("processed", [])

    total = discovery.get("object_count", 0)
    passed = sum(1 for p in processed if p.get("quality", {}).get("quality_score") == "PASS")
    warnings = sum(1 for p in processed if p.get("quality", {}).get("quality_score") == "WARNING")
    failed = sum(1 for p in processed if p.get("quality", {}).get("quality_score") == "FAIL")

    report = {
        "report_type": "automotive_cae_analytics",
        "generated_at": timestamp.isoformat(),
        "summary": {
            "total_files": total,
            "quality_pass": passed,
            "quality_warning": warnings,
            "quality_fail": failed,
        },
        "category_breakdown": _category_breakdown(processed),
        "solver_breakdown": _solver_breakdown(processed),
    }

    # S3 保存
    output_bucket = os.environ.get("OUTPUT_BUCKET", "")
    report_key = ""
    if output_bucket:
        report_key = f"cae-reports/{timestamp.strftime('%Y/%m/%d/%H%M%S')}.json"
        s3_client.put_object(
            Bucket=output_bucket,
            Key=report_key,
            Body=json.dumps(report, indent=2, ensure_ascii=False),
            ContentType="application/json",
        )

    # SNS 通知
    topic_arn = os.environ.get("NOTIFICATION_TOPIC_ARN", "")
    if topic_arn and (failed > 0 or warnings > 0):
        sns_client.publish(
            TopicArn=topic_arn,
            Subject=f"CAE Analytics: {passed} pass, {warnings} warn, {failed} fail",
            Message=json.dumps(report, indent=2, ensure_ascii=False),
        )

    return {
        "status": "completed",
        "report_key": report_key,
        "summary": report["summary"],
        "timestamp": int(time.time()),
    }


def _category_breakdown(processed: list) -> dict[str, int]:
    """カテゴリ別集計"""
    breakdown: dict[str, int] = {}
    for p in processed:
        cat = p.get("parsed", {}).get("metadata", {}).get("category", "unknown")
        breakdown[cat] = breakdown.get(cat, 0) + 1
    return breakdown


def _solver_breakdown(processed: list) -> dict[str, int]:
    """ソルバー別集計"""
    breakdown: dict[str, int] = {}
    for p in processed:
        solver = p.get("parsed", {}).get("metadata", {}).get("solver_type", "")
        if solver:
            breakdown[solver] = breakdown.get(solver, 0) + 1
    return breakdown
