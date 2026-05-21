"""Life Sciences Research Report Lambda

研究データ分析結果のレポートを生成する。
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
    categories = {}
    for p in processed:
        cat = p.get("classification", {}).get("category", "unknown")
        categories[cat] = categories.get(cat, 0) + 1

    report = {
        "report_type": "life_sciences_research",
        "generated_at": timestamp.isoformat(),
        "summary": {
            "total_files": total,
            "processed": len(processed),
            "categories": categories,
        },
    }

    # S3 保存
    output_bucket = os.environ.get("OUTPUT_BUCKET", "")
    if output_bucket:
        report_key = f"research-reports/{timestamp.strftime('%Y/%m/%d/%H%M%S')}.json"
        s3_client.put_object(
            Bucket=output_bucket,
            Key=report_key,
            Body=json.dumps(report, indent=2, ensure_ascii=False),
            ContentType="application/json",
        )

    # SNS 通知
    topic_arn = os.environ.get("NOTIFICATION_TOPIC_ARN", "")
    if topic_arn:
        sns_client.publish(
            TopicArn=topic_arn,
            Subject=f"Research Analytics: {total} files processed",
            Message=json.dumps(report, indent=2, ensure_ascii=False),
        )

    return {
        "status": "completed",
        "summary": report["summary"],
        "timestamp": int(time.time()),
    }
