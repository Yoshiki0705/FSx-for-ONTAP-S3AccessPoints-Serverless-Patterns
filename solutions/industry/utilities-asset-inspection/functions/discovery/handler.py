"""電力・ユーティリティ (UC25) Discovery Lambda ハンドラ

S3 Access Point からドローン画像（設備 ID + 点検日で整理）および
SCADA ログファイルを検出し、Manifest JSON を生成する。

ファイル分類:
    - ドローン画像: DRONE_IMAGE_PREFIX 配下の画像ファイル (JPEG/PNG/TIFF/FLIR)
    - SCADA ログ: SCADA_LOG_PREFIX 配下のログファイル (CSV/Parquet/JSON)

Manifest 出力:
    各オブジェクトに S3 AP object key, equipment ID, inspection date, format を含む。

S3 AP 接続性バリデーション (Requirement 13.5):
    処理開始前に S3 AP への接続を検証し、
    到達不可の場合は構造化エラーレスポンスを返す。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
    DRONE_IMAGE_PREFIX: ドローン画像プレフィックス (default: "drone-images/")
    SCADA_LOG_PREFIX: SCADA ログプレフィックス (default: "scada-logs/")
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone

from shared.exceptions import S3ApHelperError, lambda_error_handler
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)

# ドローン画像の対応拡張子 (FLIR thermal = .fff, .seq)
DRONE_IMAGE_EXTENSIONS: frozenset[str] = frozenset({".jpg", ".jpeg", ".png", ".tiff", ".tif", ".fff", ".seq"})

# SCADA ログの対応拡張子
SCADA_LOG_EXTENSIONS: frozenset[str] = frozenset({".csv", ".parquet", ".json", ".log"})

# ファイルタイプ定数
FILE_TYPE_DRONE_IMAGE = "drone_image"
FILE_TYPE_THERMAL_IMAGE = "thermal_image"
FILE_TYPE_SCADA_LOG = "scada_log"

# FLIR thermal 拡張子
THERMAL_EXTENSIONS: frozenset[str] = frozenset({".fff", ".seq"})

# 設備 ID パターン: パス中の EQ-XXXX or EQ_XXXX or equipment-XXX or equipment_XXX 形式
EQUIPMENT_ID_PATTERN = re.compile(r"(?:equipment[-_]|EQ[-_])([A-Za-z0-9]+)", re.IGNORECASE)

# 日付パターン (YYYY-MM-DD or YYYY/MM/DD or YYYYMMDD in path)
DATE_PATTERN = re.compile(r"(\d{4})[-/]?(\d{2})[-/]?(\d{2})")


def classify_file(
    key: str,
    drone_image_prefix: str,
    scada_log_prefix: str,
) -> str | None:
    """ファイルキーをタイプに分類する。

    Args:
        key: S3 オブジェクトキー
        drone_image_prefix: ドローン画像プレフィックス
        scada_log_prefix: SCADA ログプレフィックス

    Returns:
        "drone_image" | "thermal_image" | "scada_log" | None
    """
    if not key:
        return None

    dot_index = key.rfind(".")
    if dot_index == -1:
        return None

    extension = key[dot_index:].lower()

    if drone_image_prefix and key.startswith(drone_image_prefix):
        if extension in THERMAL_EXTENSIONS:
            return FILE_TYPE_THERMAL_IMAGE
        if extension in DRONE_IMAGE_EXTENSIONS:
            return FILE_TYPE_DRONE_IMAGE
        return None

    if scada_log_prefix and key.startswith(scada_log_prefix):
        if extension in SCADA_LOG_EXTENSIONS:
            return FILE_TYPE_SCADA_LOG
        return None

    return None


def extract_equipment_id(key: str) -> str | None:
    """ファイルパスから設備 ID を抽出する。

    パス内の設備 ID パターンを検索する。
    例: "drone-images/EQ-12345/2025-06-01/img001.jpg" → "12345"
        "drone-images/equipment_ABC123/inspection.tiff" → "ABC123"

    Args:
        key: S3 オブジェクトキー

    Returns:
        str | None: 設備 ID or None
    """
    match = EQUIPMENT_ID_PATTERN.search(key)
    if match:
        return match.group(1)
    return None


def extract_inspection_date(key: str) -> str | None:
    """ファイルパスから点検日を抽出する。

    パス内の日付パターン (YYYY-MM-DD, YYYY/MM/DD, YYYYMMDD) を探す。

    Args:
        key: S3 オブジェクトキー

    Returns:
        str | None: ISO 日付文字列 (YYYY-MM-DD) or None
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


def get_file_format(key: str) -> str:
    """ファイルの拡張子からフォーマットを返す。

    Args:
        key: S3 オブジェクトキー

    Returns:
        str: ファイルフォーマット (例: "jpeg", "csv", "flir_fff")
    """
    dot_index = key.rfind(".")
    if dot_index == -1:
        return "unknown"

    ext = key[dot_index + 1 :].lower()
    # FLIR フォーマット
    if ext in ("fff", "seq"):
        return f"flir_{ext}"
    # 標準的なマッピング
    format_map = {
        "jpg": "jpeg",
        "jpeg": "jpeg",
        "png": "png",
        "tiff": "tiff",
        "tif": "tiff",
        "csv": "csv",
        "parquet": "parquet",
        "json": "json",
        "log": "log",
    }
    return format_map.get(ext, ext)


def validate_s3ap_connectivity(s3ap: S3ApHelper) -> dict | None:
    """S3 Access Point への接続性を検証する。

    Args:
        s3ap: S3ApHelper インスタンス

    Returns:
        None: 接続成功時
        dict: 接続失敗時の構造化エラーレスポンス
    """
    try:
        s3ap.list_objects(prefix="", suffix="", max_keys=1)
        return None
    except S3ApHelperError as e:
        logger.error(
            "S3 Access Point connectivity validation failed: %s (error_code=%s)",
            str(e),
            e.error_code,
        )
        return {
            "statusCode": 503,
            "body": json.dumps(
                {
                    "error": "S3 Access Point unreachable",
                    "error_type": "ConnectivityError",
                    "error_code": e.error_code or "Unknown",
                    "access_point": s3ap.bucket_param,
                    "message": str(e),
                }
            ),
        }
    except Exception as e:
        logger.error(
            "Unexpected error during S3 AP connectivity validation: %s",
            str(e),
        )
        return {
            "statusCode": 503,
            "body": json.dumps(
                {
                    "error": "S3 Access Point unreachable",
                    "error_type": "ConnectivityError",
                    "error_code": "UnexpectedError",
                    "access_point": s3ap.bucket_param,
                    "message": str(e),
                }
            ),
        }


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Utilities Asset Inspection Discovery Lambda

    S3 AP からドローン画像 + SCADA ログを検出し、
    設備 ID・点検日・フォーマットで分類した Manifest JSON を生成する。

    Returns:
        dict: manifest_key, total_objects, drone_images, thermal_images, scada_logs
    """
    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    s3ap_output = S3ApHelper(os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ["S3_ACCESS_POINT"]))
    drone_image_prefix = os.environ.get("DRONE_IMAGE_PREFIX", "drone-images/")
    scada_log_prefix = os.environ.get("SCADA_LOG_PREFIX", "scada-logs/")

    logger.info(
        "Utilities Asset Discovery started: access_point=%s, drone_prefix=%r, scada_prefix=%r",
        os.environ["S3_ACCESS_POINT"],
        drone_image_prefix,
        scada_log_prefix,
    )

    # Step 1: S3 AP 接続性バリデーション
    with xray_subsegment(
        name="s3ap_connectivity_validation",
        annotations={
            "service_name": "s3",
            "operation": "ConnectivityCheck",
            "use_case": "utilities-asset-inspection",
        },
    ):
        connectivity_error = validate_s3ap_connectivity(s3ap)
        if connectivity_error is not None:
            return connectivity_error

    # Step 2: 各プレフィックスでオブジェクト一覧取得
    drone_images: list[dict] = []
    thermal_images: list[dict] = []
    scada_logs: list[dict] = []

    # ドローン画像検出
    with xray_subsegment(
        name="s3ap_list_drone_images",
        annotations={
            "service_name": "s3",
            "operation": "ListObjectsV2",
            "use_case": "utilities-asset-inspection",
            "prefix": drone_image_prefix,
        },
    ):
        drone_objects = s3ap.list_objects(prefix=drone_image_prefix, suffix="")

    for obj in drone_objects:
        key = obj.get("Key", "")
        file_type = classify_file(key, drone_image_prefix, scada_log_prefix)
        if file_type in (FILE_TYPE_DRONE_IMAGE, FILE_TYPE_THERMAL_IMAGE):
            obj["file_type"] = file_type
            obj["equipment_id"] = extract_equipment_id(key)
            obj["inspection_date"] = extract_inspection_date(key)
            obj["format"] = get_file_format(key)
            if file_type == FILE_TYPE_THERMAL_IMAGE:
                thermal_images.append(obj)
            else:
                drone_images.append(obj)

    # SCADA ログ検出
    with xray_subsegment(
        name="s3ap_list_scada_logs",
        annotations={
            "service_name": "s3",
            "operation": "ListObjectsV2",
            "use_case": "utilities-asset-inspection",
            "prefix": scada_log_prefix,
        },
    ):
        scada_objects = s3ap.list_objects(prefix=scada_log_prefix, suffix="")

    for obj in scada_objects:
        key = obj.get("Key", "")
        file_type = classify_file(key, drone_image_prefix, scada_log_prefix)
        if file_type == FILE_TYPE_SCADA_LOG:
            obj["file_type"] = file_type
            obj["equipment_id"] = extract_equipment_id(key)
            obj["inspection_date"] = extract_inspection_date(key)
            obj["format"] = get_file_format(key)
            scada_logs.append(obj)

    all_objects = drone_images + thermal_images + scada_logs

    # 設備 ID 統計
    equipment_ids: dict[str, int] = {}
    for obj in all_objects:
        eq_id = obj.get("equipment_id")
        if eq_id:
            equipment_ids[eq_id] = equipment_ids.get(eq_id, 0) + 1

    logger.info(
        "File classification: drone_images=%d, thermal_images=%d, scada_logs=%d, total=%d, unique_equipment=%d",
        len(drone_images),
        len(thermal_images),
        len(scada_logs),
        len(all_objects),
        len(equipment_ids),
    )

    # Manifest 生成
    manifest = {
        "execution_id": context.aws_request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "use_case": "utilities-asset-inspection",
        "total_objects": len(all_objects),
        "total_size_bytes": sum(obj.get("Size", 0) for obj in all_objects),
        "drone_image_count": len(drone_images),
        "thermal_image_count": len(thermal_images),
        "scada_log_count": len(scada_logs),
        "unique_equipment_count": len(equipment_ids),
        "equipment_ids": equipment_ids,
        "drone_image_prefix": drone_image_prefix,
        "scada_log_prefix": scada_log_prefix,
        "objects": all_objects,
    }

    manifest_key = f"manifests/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{context.aws_request_id}.json"

    s3ap_output.put_object(
        key=manifest_key,
        body=json.dumps(manifest, default=str),
        content_type="application/json",
    )

    logger.info(
        "Utilities Asset Discovery completed: total_objects=%d, manifest=%s",
        len(all_objects),
        manifest_key,
    )

    # EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="discovery")
    metrics.set_dimension("UseCase", "utilities-asset-inspection")
    metrics.put_metric("FilesProcessed", float(len(all_objects)), "Count")
    metrics.put_metric("DroneImages", float(len(drone_images)), "Count")
    metrics.put_metric("ThermalImages", float(len(thermal_images)), "Count")
    metrics.put_metric("ScadaLogs", float(len(scada_logs)), "Count")
    metrics.flush()

    return {
        "manifest_key": manifest_key,
        "total_objects": len(all_objects),
        "objects": all_objects,
        "drone_images": drone_images,
        "thermal_images": thermal_images,
        "scada_logs": scada_logs,
    }
