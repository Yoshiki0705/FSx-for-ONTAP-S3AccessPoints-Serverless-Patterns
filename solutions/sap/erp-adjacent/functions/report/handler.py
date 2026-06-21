"""SAP/ERP Adjacent Report Lambda

処理結果を集約し、実行サマリーレポートを生成して SNS 通知を送信する。

Environment Variables:
    OUTPUT_BUCKET: 出力先 S3 バケット名
    SNS_TOPIC_ARN: SNS トピック ARN
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

s3_client = boto3.client("s3")
sns_client = boto3.client("sns")


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Report Lambda ハンドラー

    処理結果を集約し、サマリーレポートを生成する。
    """
    processed_results = event.get("processed_results", [])
    output_bucket = os.environ.get("OUTPUT_BUCKET", "")
    sns_topic_arn = os.environ.get("SNS_TOPIC_ARN", "")

    logger.info("Generating report for %d processed files", len(processed_results))

    # 結果集約
    total = len(processed_results)
    succeeded = sum(1 for r in processed_results if r.get("status") == "completed")
    failed = sum(1 for r in processed_results if r.get("status") == "error")

    # カテゴリ別集計
    category_counts: dict[str, int] = {}
    for r in processed_results:
        cat = r.get("category", "unknown")
        category_counts[cat] = category_counts.get(cat, 0) + 1

    report = {
        "report_type": "sap_erp_processing_summary",
        "timestamp": int(time.time()),
        "summary": {
            "total_files": total,
            "succeeded": succeeded,
            "failed": failed,
            "success_rate_pct": round(succeeded / total * 100, 1) if total > 0 else 0,
        },
        "category_breakdown": category_counts,
        "errors": [
            {"key": r.get("key"), "error": r.get("error")} for r in processed_results if r.get("status") == "error"
        ],
    }

    # レポートを S3 に保存
    if output_bucket:
        report_key = f"reports/sap-erp-summary-{int(time.time())}.json"
        try:
            s3_client.put_object(
                Bucket=output_bucket,
                Key=report_key,
                Body=json.dumps(report, ensure_ascii=False, indent=2),
                ContentType="application/json",
            )
            report["report_key"] = report_key
            logger.info("Report saved: s3://%s/%s", output_bucket, report_key)
        except Exception as e:
            logger.warning("Failed to save report: %s", str(e))

    # SNS 通知
    if sns_topic_arn:
        subject = f"SAP/ERP Processing: {succeeded}/{total} succeeded"
        message = (
            f"SAP/ERP Adjacent File Processing Report\n"
            f"{'=' * 40}\n"
            f"Total files: {total}\n"
            f"Succeeded: {succeeded}\n"
            f"Failed: {failed}\n"
            f"Success rate: {report['summary']['success_rate_pct']}%\n\n"
            f"Category breakdown:\n"
        )
        for cat, count in category_counts.items():
            message += f"  - {cat}: {count}\n"

        if report["errors"]:
            message += f"\nErrors ({len(report['errors'])}):\n"
            for err in report["errors"][:5]:
                message += f"  - {err['key']}: {err['error']}\n"

        try:
            sns_client.publish(
                TopicArn=sns_topic_arn,
                Subject=subject[:100],
                Message=message,
            )
            logger.info("SNS notification sent")
        except Exception as e:
            logger.warning("Failed to send SNS notification: %s", str(e))

    return {
        "status": "completed",
        "report": report,
    }
