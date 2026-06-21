"""Automotive CAE Discovery Lambda

S3 AP 経由で CAE シミュレーション結果ファイルを検出する。
対象: solver output, mesh files, telemetry data
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

# CAE 関連ファイル拡張子
CAE_EXTENSIONS = {
    ".d3plot",
    ".binout",
    ".k",
    ".key",  # LS-DYNA
    ".op2",
    ".f06",
    ".bdf",
    ".dat",  # Nastran
    ".odb",
    ".inp",  # Abaqus
    ".cas",
    ".dat",
    ".msh",  # Fluent
    ".sim",
    ".star",  # STAR-CCM+
    ".csv",
    ".json",
    ".log",
    ".txt",  # 汎用
    ".vtu",
    ".vtk",
    ".stl",  # メッシュ
}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Discovery Lambda ハンドラー"""
    logger.info("CAE Discovery started")

    s3ap_alias = os.environ.get("S3_ACCESS_POINT_ALIAS", "")
    prefix = event.get("prefix", "simulations/")
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
                if ext in CAE_EXTENSIONS:
                    objects.append(
                        {
                            "key": key,
                            "size": obj["Size"],
                            "last_modified": obj["LastModified"].isoformat(),
                            "extension": ext,
                            "category": _categorize_file(ext),
                        }
                    )

            if not response.get("IsTruncated"):
                break
            continuation_token = response.get("NextContinuationToken")

    except Exception as e:
        logger.error("CAE Discovery failed: %s", str(e))
        return {"status": "error", "error": str(e), "objects": []}

    logger.info("Discovered %d CAE files", len(objects))
    return {
        "status": "completed",
        "object_count": len(objects),
        "objects": objects,
        "timestamp": int(time.time()),
    }


def _categorize_file(ext: str) -> str:
    """ファイル拡張子からカテゴリを判定"""
    solver_output = {".d3plot", ".binout", ".op2", ".f06", ".odb", ".cas"}
    mesh = {".k", ".key", ".bdf", ".dat", ".inp", ".msh", ".vtu", ".vtk", ".stl"}
    telemetry = {".csv", ".json", ".log", ".txt"}

    if ext in solver_output:
        return "solver_output"
    elif ext in mesh:
        return "mesh"
    elif ext in telemetry:
        return "telemetry"
    return "other"
