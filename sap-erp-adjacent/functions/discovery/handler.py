"""SAP/ERP Adjacent Discovery Lambda

FSx ONTAP S3 Access Point 経由で SAP IDoc、HULFT、EDI、バッチ出力ファイルを検出する。
ファイルプレフィックスとサフィックスでフィルタリングし、Manifest JSON を生成する。

Environment Variables:
    S3_ACCESS_POINT_ALIAS: S3 AP Alias (入力読み取り用)
    FILE_PREFIX: スキャン対象プレフィックス (例: "idoc-export/")
    MAX_FILES: 1 回の実行あたりの最大ファイル数 (デフォルト: 100)
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

# SAP/ERP 関連ファイル拡張子
SAP_EXTENSIONS = {
    ".txt", ".dat", ".csv", ".xml", ".json", ".edi", ".idoc",
    ".x12", ".edifact", ".flat", ".tsv", ".xlsx",
}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Discovery Lambda ハンドラー

    S3 AP からファイル一覧を取得し、SAP/ERP 関連ファイルをフィルタリングする。
    """
    s3ap_alias = os.environ.get("S3_ACCESS_POINT_ALIAS", "")
    prefix = os.environ.get("FILE_PREFIX", "idoc-export/")
    max_files = int(os.environ.get("MAX_FILES", "100"))

    logger.info("SAP/ERP Discovery: alias=%s, prefix=%s, max=%d", s3ap_alias, prefix, max_files)

    objects = []
    continuation_token = None

    try:
        while len(objects) < max_files:
            kwargs = {
                "Bucket": s3ap_alias,
                "Prefix": prefix,
                "MaxKeys": min(1000, max_files - len(objects)),
            }
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token

            response = s3_client.list_objects_v2(**kwargs)

            for obj in response.get("Contents", []):
                key = obj["Key"]
                ext = os.path.splitext(key)[1].lower()
                if ext in SAP_EXTENSIONS or not ext:
                    objects.append({
                        "key": key,
                        "size": obj["Size"],
                        "last_modified": obj["LastModified"].isoformat()
                        if hasattr(obj["LastModified"], "isoformat")
                        else str(obj["LastModified"]),
                        "category": _categorize_file(key),
                    })

                if len(objects) >= max_files:
                    break

            if not response.get("IsTruncated"):
                break
            continuation_token = response.get("NextContinuationToken")

    except Exception as e:
        logger.error("Discovery failed: %s", str(e))
        return {"status": "error", "error": str(e), "object_count": 0}

    logger.info("Discovery completed: %d files found", len(objects))

    return {
        "status": "completed",
        "object_count": len(objects),
        "objects": objects,
        "prefix": prefix,
        "timestamp": int(time.time()),
    }


def _categorize_file(key: str) -> str:
    """ファイルをカテゴリに分類する"""
    key_lower = key.lower()

    if "idoc" in key_lower or ".idoc" in key_lower:
        return "sap_idoc"
    elif "hulft" in key_lower:
        return "hulft_transfer"
    elif ".edi" in key_lower or ".x12" in key_lower or ".edifact" in key_lower:
        return "edi_document"
    elif "batch" in key_lower or "job" in key_lower:
        return "batch_output"
    elif ".xml" in key_lower and "sap" in key_lower:
        return "sap_xml"
    elif ".csv" in key_lower or ".tsv" in key_lower:
        return "data_extract"
    else:
        return "general_erp"
