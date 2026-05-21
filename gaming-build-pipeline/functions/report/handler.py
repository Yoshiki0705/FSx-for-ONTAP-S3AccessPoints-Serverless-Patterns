"""Gaming Build Pipeline Report Lambda

ビルドパイプライン分析結果のレポートを生成する。
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
    timestamp = datetime.now(timezone.utc)

    discovery = event.get("discovery", {})
    processed = event.get("processed", [])

    total = discovery.get("object_count", 0)

    # 品質スコア集計
    quality_pass = 0
    quality_warn = 0
    quality_fail = 0
    log_errors = 0

    for p in processed:
        qc = p.get("quality", {})
        score = qc.get("quality_score", "")
        if score == "PASS":
            quality_pass += 1
        elif score == "WARNING":
            quality_warn += 1
        elif score == "FAIL":
            quality_fail += 1

        logs = p.get("logs", {})
        if logs.get("analysis", {}).get("error_count", 0) > 0:
            log_errors += 1

    report = {
        "report_type": "gaming_build_pipeline",
        "generated_at": timestamp.isoformat(),
        "summary": {
            "total_assets": total,
            "quality_pass": quality_pass,
            "quality_warning": quality_warn,
            "quality_fail": quality_fail,
            "logs_with_errors": log_errors,
        },
        "category_breakdown": _category_breakdown(processed),
    }

    # S3 保存
    output_bucket = os.environ.get("OUTPUT_BUCKET", "")
    report_key = ""
    if output_bucket:
        report_key = f"build-reports/{timestamp.strftime('%Y/%m/%d/%H%M%S')}.json"
        s3_client.put_object(
            Bucket=output_bucket,
            Key=report_key,
            Body=json.dumps(report, indent=2, ensure_ascii=False),
            ContentType="application/json",
        )

    # SNS 通知（エラーがある場合）
    topic_arn = os.environ.get("NOTIFICATION_TOPIC_ARN", "")
    if topic_arn and (quality_fail > 0 or log_errors > 0):
        sns_client.publish(
            TopicArn=topic_arn,
            Subject=f"Build Pipeline: {quality_fail} QC fails, {log_errors} log errors",
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
        cat = p.get("quality", {}).get("category", "unknown")
        breakdown[cat] = breakdown.get(cat, 0) + 1
    return breakdown
