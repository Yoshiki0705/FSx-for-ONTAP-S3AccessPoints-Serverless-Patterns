"""GenAI RAG Discovery Lambda

S3 AP 経由でエンタープライズファイルの一覧を取得し、
新規/更新ファイルを検出する。
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

s3_client = boto3.client("s3")


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Discovery Lambda ハンドラー"""
    logger.info("GenAI RAG Discovery started")

    s3ap_alias = os.environ.get("S3_ACCESS_POINT_ALIAS", "")
    prefix = event.get("prefix", "")
    max_keys = event.get("max_keys", 500)

    # サポートするファイル拡張子
    supported_extensions = {
        ".pdf", ".docx", ".doc", ".txt", ".md",
        ".pptx", ".xlsx", ".csv", ".json",
        ".html", ".htm", ".rtf",
    }

    objects = []
    continuation_token = None

    try:
        while len(objects) < max_keys:
            kwargs = {
                "Bucket": s3ap_alias,
                "Prefix": prefix,
                "MaxKeys": min(1000, max_keys - len(objects)),
            }
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token

            response = s3_client.list_objects_v2(**kwargs)

            for obj in response.get("Contents", []):
                key = obj["Key"]
                ext = os.path.splitext(key)[1].lower()
                if ext in supported_extensions:
                    objects.append({
                        "key": key,
                        "size": obj["Size"],
                        "last_modified": obj["LastModified"].isoformat(),
                        "extension": ext,
                    })

            if not response.get("IsTruncated"):
                break
            continuation_token = response.get("NextContinuationToken")

    except Exception as e:
        logger.error("Discovery failed: %s", str(e))
        return {
            "status": "error",
            "error": str(e),
            "objects": [],
            "timestamp": int(time.time()),
        }

    logger.info("Discovered %d documents for RAG indexing", len(objects))

    return {
        "status": "completed",
        "object_count": len(objects),
        "objects": objects,
        "s3ap_alias": s3ap_alias,
        "timestamp": int(time.time()),
    }
