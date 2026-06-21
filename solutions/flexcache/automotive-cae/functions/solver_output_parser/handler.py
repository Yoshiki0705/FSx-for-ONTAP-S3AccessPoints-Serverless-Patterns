"""Automotive CAE Solver Output Parser Lambda

CAE solver output ファイルを解析し、メタデータを抽出する。
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
    """Solver Output Parser ハンドラー"""
    key = event.get("key", "")
    extension = event.get("extension", "")
    category = event.get("category", "")

    s3ap_alias = os.environ.get("S3_ACCESS_POINT_ALIAS", "")
    output_bucket = os.environ.get("OUTPUT_BUCKET", "")

    logger.info("Parsing solver output: %s (category: %s)", key, category)

    try:
        # S3 AP 経由でファイルヘッダー/メタデータを読み取り
        # 大きなバイナリファイルは先頭部分のみ
        response = s3_client.get_object(
            Bucket=s3ap_alias,
            Key=key,
            Range="bytes=0-65535",  # 先頭 64KB
        )
        header_bytes = response["Body"].read()
        response["Body"].close()

        # メタデータ抽出
        metadata = _extract_metadata(header_bytes, extension, category)
        metadata["source_key"] = key
        metadata["file_size"] = event.get("size", 0)

        # 結果を S3 に保存
        if output_bucket:
            output_key = f"cae-metadata/{os.path.basename(key)}.json"
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
        logger.error("Parser failed for %s: %s", key, str(e))
        return {
            "key": key,
            "status": "error",
            "error": str(e),
            "timestamp": int(time.time()),
        }


def _extract_metadata(header: bytes, extension: str, category: str) -> dict[str, Any]:
    """ファイルヘッダーからメタデータを抽出"""
    metadata: dict[str, Any] = {
        "extension": extension,
        "category": category,
        "header_size_bytes": len(header),
    }

    if category == "solver_output":
        metadata["solver_type"] = _detect_solver(extension)
        metadata["analysis_type"] = "structural"  # 簡易判定

    elif category == "mesh":
        metadata["mesh_format"] = extension.lstrip(".")
        # テキストベースのメッシュファイルからノード数を推定
        if extension in (".k", ".key", ".bdf", ".inp"):
            text = header.decode("ascii", errors="replace")
            metadata["estimated_nodes"] = text.count("NODE") + text.count("*NODE")

    elif category == "telemetry":
        # CSV/JSON のカラム数を推定
        text = header.decode("utf-8", errors="replace")
        lines = text.split("\n")
        if lines:
            metadata["columns"] = len(lines[0].split(","))
            metadata["estimated_rows"] = len(lines) - 1

    return metadata


def _detect_solver(extension: str) -> str:
    """拡張子からソルバーを判定"""
    solver_map = {
        ".d3plot": "LS-DYNA",
        ".binout": "LS-DYNA",
        ".op2": "Nastran",
        ".f06": "Nastran",
        ".odb": "Abaqus",
        ".cas": "Fluent",
    }
    return solver_map.get(extension, "unknown")
