"""化学・素材 (UC28) Discovery Lambda ハンドラ

S3 Access Point から SDS (PDF/XML) + ラボノート画像を検出し、
物質名 + 改訂日で分類した Manifest を生成する。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
    SDS_PREFIX: SDS ファイルプレフィックス (default: "sds/")
    LABBOOK_PREFIX: ラボノートプレフィックス (default: "labbooks/")
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone

from shared.exceptions import S3ApHelperError, lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler, xray_subsegment
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)

# SDS の対応拡張子
SDS_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".xml"})

# ラボノートの対応拡張子
LABBOOK_EXTENSIONS: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".tiff", ".tif"}
)

# ファイルタイプ定数
FILE_TYPE_SDS = "sds"
FILE_TYPE_LABBOOK = "labbook"

# 日付パターン
DATE_PATTERN = re.compile(r"(\d{4})[-/]?(\d{2})[-/]?(\d{2})")

# 物質名パターン (CAS 番号含む)
SUBSTANCE_PATTERN = re.compile(
    r"(?:substance[-_]|CAS[-_]?)([A-Za-z0-9-]+)", re.IGNORECASE
)


def classify_file(key: str, sds_prefix: str, labbook_prefix: str) -> str | None:
    """ファイルキーを分類する。

    Args:
        key: S3 オブジェクトキー
        sds_prefix: SDS プレフィックス
        labbook_prefix: ラボノートプレフィックス

    Returns:
        "sds" | "labbook" | None
    """
    if not key:
        return None

    dot_index = key.rfind(".")
    if dot_index == -1:
        return None

    extension = key[dot_index:].lower()

    if sds_prefix and key.startswith(sds_prefix):
        if extension in SDS_EXTENSIONS:
            return FILE_TYPE_SDS
        return None

    if labbook_prefix and key.startswith(labbook_prefix):
        if extension in LABBOOK_EXTENSIONS:
            return FILE_TYPE_LABBOOK
        return None

    return None


def extract_substance_id(key: str) -> str | None:
    """ファイルパスから物質名/CAS 番号を抽出する。

    Args:
        key: S3 オブジェクトキー

    Returns:
        str | None: 物質 ID or None
    """
    match = SUBSTANCE_PATTERN.search(key)
    if match:
        return match.group(1)
    return None


def extract_revision_date(key: str) -> str | None:
    """ファイルパスから改訂日を抽出する。

    Args:
        key: S3 オブジェクトキー

    Returns:
        str | None: ISO 日付文字列 or None
    """
    match = DATE_PATTERN.search(key)
    if match:
        year, month, day = match.group(1), match.group(2), match.group(3)
        try:
            datetime(int(year), int(month), int(day))
            return f"{year}-{month}-{day}"
        except ValueError:
            pass
    return None


def validate_s3ap_connectivity(s3ap: S3ApHelper) -> dict | None:
    """S3 Access Point への接続性を検証する。"""
    try:
        s3ap.list_objects(prefix="", suffix="", max_keys=1)
        return None
    except S3ApHelperError as e:
        logger.error("S3 AP connectivity failed: %s", str(e))
        return {
            "statusCode": 503,
            "body": json.dumps({
                "error": "S3 Access Point unreachable",
                "error_type": "ConnectivityError",
                "error_code": e.error_code or "Unknown",
                "access_point": s3ap.bucket_param,
                "message": str(e),
            }),
        }
    except Exception as e:
        logger.error("Unexpected S3 AP error: %s", str(e))
        return {
            "statusCode": 503,
            "body": json.dumps({
                "error": "S3 Access Point unreachable",
                "error_type": "ConnectivityError",
                "error_code": "UnexpectedError",
                "access_point": s3ap.bucket_param,
                "message": str(e),
            }),
        }


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Chemical SDS Management Discovery Lambda

    Returns:
        dict: manifest_key, total_objects, sds_files, labbook_images
    """
    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    s3ap_output = S3ApHelper(
        os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ["S3_ACCESS_POINT"])
    )
    sds_prefix = os.environ.get("SDS_PREFIX", "sds/")
    labbook_prefix = os.environ.get("LABBOOK_PREFIX", "labbooks/")

    logger.info(
        "Chemical SDS Discovery started: sds_prefix=%r, labbook_prefix=%r",
        sds_prefix,
        labbook_prefix,
    )

    # S3 AP 接続性バリデーション
    with xray_subsegment(
        name="s3ap_connectivity_validation",
        annotations={"use_case": "chemical-sds-management"},
    ):
        connectivity_error = validate_s3ap_connectivity(s3ap)
        if connectivity_error is not None:
            return connectivity_error

    # SDS ファイル検出
    sds_files: list[dict] = []
    with xray_subsegment(name="s3ap_list_sds", annotations={"prefix": sds_prefix}):
        sds_objects = s3ap.list_objects(prefix=sds_prefix, suffix="")

    for obj in sds_objects:
        key = obj.get("Key", "")
        file_type = classify_file(key, sds_prefix, labbook_prefix)
        if file_type == FILE_TYPE_SDS:
            obj["file_type"] = file_type
            obj["substance_id"] = extract_substance_id(key)
            obj["revision_date"] = extract_revision_date(key)
            sds_files.append(obj)

    # ラボノート検出
    labbook_images: list[dict] = []
    with xray_subsegment(name="s3ap_list_labbooks", annotations={"prefix": labbook_prefix}):
        labbook_objects = s3ap.list_objects(prefix=labbook_prefix, suffix="")

    for obj in labbook_objects:
        key = obj.get("Key", "")
        file_type = classify_file(key, sds_prefix, labbook_prefix)
        if file_type == FILE_TYPE_LABBOOK:
            obj["file_type"] = file_type
            obj["substance_id"] = extract_substance_id(key)
            labbook_images.append(obj)

    all_objects = sds_files + labbook_images

    logger.info(
        "Chemical SDS Discovery: sds=%d, labbooks=%d, total=%d",
        len(sds_files),
        len(labbook_images),
        len(all_objects),
    )

    # JSON Manifest 出力 (Requirement 12.1)
    manifest = {
        "execution_id": context.aws_request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "use_case": "chemical-sds-management",
        "total_objects": len(all_objects),
        "total_size_bytes": sum(obj.get("Size", 0) for obj in all_objects),
        "sds_count": len(sds_files),
        "labbook_count": len(labbook_images),
        "sds_prefix": sds_prefix,
        "labbook_prefix": labbook_prefix,
        "objects": all_objects,
    }

    manifest_key = (
        f"manifests/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/"
        f"{context.aws_request_id}.json"
    )

    s3ap_output.put_object(
        key=manifest_key,
        body=json.dumps(manifest, default=str),
        content_type="application/json",
    )

    # EMF メトリクス
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="discovery")
    metrics.set_dimension("UseCase", "chemical-sds-management")
    metrics.put_metric("FilesProcessed", float(len(all_objects)), "Count")
    metrics.put_metric("SdsFiles", float(len(sds_files)), "Count")
    metrics.put_metric("LabbookImages", float(len(labbook_images)), "Count")
    metrics.flush()

    return {
        "manifest_key": manifest_key,
        "total_objects": len(all_objects),
        "sds_files": sds_files,
        "labbook_images": labbook_images,
    }
