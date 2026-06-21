"""GenAI RAG Report Lambda

インデックス処理の結果レポートを生成する。
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

    total_docs = discovery.get("object_count", 0)
    successful = sum(1 for p in processed if p.get("embeddings", {}).get("status") == "completed")
    failed = total_docs - successful

    report = {
        "report_type": "genai_rag_indexing",
        "generated_at": timestamp.isoformat(),
        "summary": {
            "total_documents": total_docs,
            "successfully_indexed": successful,
            "failed": failed,
            "success_rate": round(successful / max(total_docs, 1) * 100, 1),
        },
        "details": {
            "s3ap_alias": discovery.get("s3ap_alias", ""),
            "processed_documents": len(processed),
        },
    }

    # S3 に保存
    output_bucket = os.environ.get("OUTPUT_BUCKET", "")
    if output_bucket:
        report_key = f"rag-reports/{timestamp.strftime('%Y/%m/%d/%H%M%S')}.json"
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
            Subject=f"RAG Indexing: {successful}/{total_docs} documents indexed",
            Message=json.dumps(report, indent=2, ensure_ascii=False),
        )

    return {
        "status": "completed",
        "report": report["summary"],
        "timestamp": int(time.time()),
    }
