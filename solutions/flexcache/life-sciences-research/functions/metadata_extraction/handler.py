"""Life Sciences Research Metadata Extraction Lambda

研究データからメタデータを抽出し、S3 に保存する。
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


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Metadata Extraction Lambda ハンドラー"""
    key = event.get("key", "")
    category = event.get("category", "")
    size = event.get("size", 0)
    s3ap_alias = os.environ.get("S3_ACCESS_POINT_ALIAS", "")
    output_bucket = os.environ.get("OUTPUT_BUCKET", "")

    logger.info("Extracting metadata: %s", key)

    try:
        metadata = {
            "source_key": key,
            "category": category,
            "file_size_bytes": size,
            "file_name": os.path.basename(key),
            "directory": os.path.dirname(key),
            "extension": os.path.splitext(key)[1].lower(),
            "extracted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        # カテゴリ別のメタデータ抽出
        if category == "sequence_data":
            metadata.update(_extract_sequence_metadata(key, s3ap_alias))
        elif category == "experiment_data":
            metadata.update(_extract_experiment_metadata(key, s3ap_alias))
        elif category == "document":
            metadata.update(_extract_document_metadata(key, size))
        elif category == "microscopy_image":
            metadata.update(_extract_image_metadata(key, size))

        # S3 に保存
        if output_bucket:
            output_key = f"research-metadata/{category}/{os.path.basename(key)}.json"
            s3_client.put_object(
                Bucket=output_bucket,
                Key=output_key,
                Body=json.dumps(metadata, indent=2, ensure_ascii=False),
                ContentType="application/json",
            )

        return {
            "key": key,
            "status": "completed",
            "metadata": metadata,
            "timestamp": int(time.time()),
        }

    except Exception as e:
        logger.error("Metadata extraction failed for %s: %s", key, str(e))
        return {
            "key": key,
            "status": "error",
            "error": str(e),
            "timestamp": int(time.time()),
        }


def _extract_sequence_metadata(key: str, s3ap_alias: str) -> dict[str, Any]:
    """シーケンスデータのメタデータ"""
    ext = os.path.splitext(key)[1].lower()
    metadata: dict[str, Any] = {"data_type": "genomics"}

    if ext in (".fastq", ".fq"):
        metadata["format"] = "FASTQ"
        metadata["sequencing_type"] = "unknown"
        # ファイル名からサンプル情報を推定
        basename = os.path.basename(key)
        if "_R1" in basename:
            metadata["read_direction"] = "forward"
        elif "_R2" in basename:
            metadata["read_direction"] = "reverse"
    elif ext == ".bam":
        metadata["format"] = "BAM"
        metadata["aligned"] = True
    elif ext == ".vcf":
        metadata["format"] = "VCF"
        metadata["variant_type"] = "unknown"

    return metadata


def _extract_experiment_metadata(key: str, s3ap_alias: str) -> dict[str, Any]:
    """実験データのメタデータ"""
    try:
        response = s3_client.get_object(
            Bucket=s3ap_alias,
            Key=key,
            Range="bytes=0-4095",
        )
        header = response["Body"].read().decode("utf-8", errors="replace")
        response["Body"].close()

        lines = header.split("\n")
        if lines:
            columns = lines[0].split(",")
            return {
                "column_count": len(columns),
                "columns_preview": columns[:10],
                "estimated_rows": len(lines) - 1,
            }
    except Exception:
        pass

    return {"data_type": "tabular"}


def _extract_document_metadata(key: str, size: int) -> dict[str, Any]:
    """ドキュメントのメタデータ"""
    return {
        "document_type": "research",
        "estimated_pages": max(1, size // 50000),  # 概算
    }


def _extract_image_metadata(key: str, size: int) -> dict[str, Any]:
    """画像のメタデータ"""
    return {
        "image_type": "microscopy",
        "estimated_resolution": "unknown",
        "file_size_mb": round(size / (1024 * 1024), 2),
    }
