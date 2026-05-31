"""Life Sciences Research Discovery Lambda

S3 AP 経由で研究データファイルを検出する。
対象: 顕微鏡画像、シーケンス結果、論文 PDF、実験ログ
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

RESEARCH_EXTENSIONS = {
    # 顕微鏡画像
    ".tiff",
    ".tif",
    ".nd2",
    ".czi",
    ".lif",
    ".oib",
    # シーケンス結果
    ".fastq",
    ".fq",
    ".bam",
    ".sam",
    ".vcf",
    ".bed",
    # 論文・ドキュメント
    ".pdf",
    ".docx",
    ".doc",
    ".md",
    ".txt",
    # 実験ログ・データ
    ".csv",
    ".xlsx",
    ".xls",
    ".json",
    ".tsv",
    # プロトコル
    ".html",
    ".htm",
}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Discovery Lambda ハンドラー"""
    logger.info("Life Sciences Research Discovery started")

    s3ap_alias = os.environ.get("S3_ACCESS_POINT_ALIAS", "")
    prefix = event.get("prefix", "")
    max_keys = event.get("max_keys", 500)

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
                if ext in RESEARCH_EXTENSIONS:
                    objects.append(
                        {
                            "key": key,
                            "size": obj["Size"],
                            "last_modified": obj["LastModified"].isoformat(),
                            "extension": ext,
                            "category": _categorize(ext),
                        }
                    )

            if not response.get("IsTruncated"):
                break
            continuation_token = response.get("NextContinuationToken")

    except Exception as e:
        logger.error("Discovery failed: %s", str(e))
        return {"status": "error", "error": str(e), "objects": []}

    logger.info("Discovered %d research files", len(objects))
    return {
        "status": "completed",
        "object_count": len(objects),
        "objects": objects,
        "timestamp": int(time.time()),
    }


def _categorize(ext: str) -> str:
    """拡張子からカテゴリを判定"""
    microscopy = {".tiff", ".tif", ".nd2", ".czi", ".lif", ".oib"}
    sequence = {".fastq", ".fq", ".bam", ".sam", ".vcf", ".bed"}
    document = {".pdf", ".docx", ".doc", ".md", ".txt", ".html", ".htm"}
    data = {".csv", ".xlsx", ".xls", ".json", ".tsv"}

    if ext in microscopy:
        return "microscopy_image"
    elif ext in sequence:
        return "sequence_data"
    elif ext in document:
        return "document"
    elif ext in data:
        return "experiment_data"
    return "other"
