"""運輸・鉄道業界 (UC22) Discovery Lambda ハンドラ

S3 Access Point から鉄道インフラ点検画像（JPEG/PNG/TIFF）と
保守報告書（PDF/Excel）を検出し、Manifest JSON を生成する。

ファイル分類:
    - 点検画像: INSPECTION_PREFIX 配下の JPEG/PNG/TIFF ファイル
      ルート + 日付でオーガナイズ想定
    - 保守報告書: MAINTENANCE_PREFIX 配下の PDF/Excel ファイル

S3 AP 接続性バリデーション (Requirement 13.5):
    処理開始前に S3 AP への接続を検証し、
    到達不可の場合は構造化エラーレスポンスを返す。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
    INSPECTION_PREFIX: 点検画像プレフィックス (default: "inspections/")
    MAINTENANCE_PREFIX: 保守報告書プレフィックス (default: "maintenance-reports/")
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from shared.exceptions import S3ApHelperError, lambda_error_handler
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)

# 点検画像の対応拡張子 (JPEG/PNG/TIFF)
INSPECTION_IMAGE_EXTENSIONS: frozenset[str] = frozenset({".jpg", ".jpeg", ".png", ".tiff", ".tif"})

# 保守報告書の対応拡張子 (PDF/Excel)
MAINTENANCE_DOC_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".xlsx", ".xls"})


def classify_file(
    key: str,
    inspection_prefix: str,
    maintenance_prefix: str,
) -> str | None:
    """ファイルキーをカテゴリに分類する。

    Args:
        key: S3 オブジェクトキー
        inspection_prefix: 点検画像プレフィックス
        maintenance_prefix: 保守報告書プレフィックス

    Returns:
        "inspection_image" | "maintenance_report" | None (対象外)
    """
    if not key:
        return None

    dot_index = key.rfind(".")
    if dot_index == -1:
        return None

    extension = key[dot_index:].lower()

    # 点検画像チェック
    if inspection_prefix and key.startswith(inspection_prefix):
        if extension in INSPECTION_IMAGE_EXTENSIONS:
            return "inspection_image"

    # 保守報告書チェック
    if maintenance_prefix and key.startswith(maintenance_prefix):
        if extension in MAINTENANCE_DOC_EXTENSIONS:
            return "maintenance_report"

    return None


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
    """Transportation Maintenance Discovery Lambda

    S3 AP から点検画像と保守報告書を検出し、
    カテゴリ別に分類した Manifest JSON を生成・書き出す。

    Manifest に含まれる情報 (Requirement 6.1):
        - object keys
        - sizes
        - last-modified timestamps

    Processing Flow:
        1. S3 AP 接続性バリデーション (Req 13.5)
        2. プレフィックス設定の取得
        3. 各プレフィックスでオブジェクト一覧取得
        4. ファイル分類フィルタ適用
        5. Manifest JSON 生成・書き出し
        6. EMF メトリクス出力

    Returns:
        dict: manifest_key, total_objects, inspection_images, maintenance_reports
    """
    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    s3ap_output = S3ApHelper(os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ["S3_ACCESS_POINT"]))
    inspection_prefix = os.environ.get("INSPECTION_PREFIX", "inspections/")
    maintenance_prefix = os.environ.get("MAINTENANCE_PREFIX", "maintenance-reports/")

    logger.info(
        "Transportation Discovery started: access_point=%s, inspection_prefix=%r, maintenance_prefix=%r",
        os.environ["S3_ACCESS_POINT"],
        inspection_prefix,
        maintenance_prefix,
    )

    # Step 1: S3 AP 接続性バリデーション
    with xray_subsegment(
        name="s3ap_connectivity_validation",
        annotations={
            "service_name": "s3",
            "operation": "ConnectivityCheck",
            "use_case": "transportation-maintenance",
        },
    ):
        connectivity_error = validate_s3ap_connectivity(s3ap)
        if connectivity_error is not None:
            return connectivity_error

    # Step 2-3: 各プレフィックスでオブジェクト一覧取得
    inspection_images: list[dict] = []
    maintenance_reports: list[dict] = []

    # 点検画像の検出
    with xray_subsegment(
        name="s3ap_list_inspection_images",
        annotations={
            "service_name": "s3",
            "operation": "ListObjectsV2",
            "use_case": "transportation-maintenance",
            "prefix": inspection_prefix,
        },
    ):
        image_objects = s3ap.list_objects(prefix=inspection_prefix, suffix="")

    for obj in image_objects:
        category = classify_file(
            obj.get("Key", ""),
            inspection_prefix,
            maintenance_prefix,
        )
        if category == "inspection_image":
            obj["category"] = "inspection_image"
            inspection_images.append(obj)

    # 保守報告書の検出
    with xray_subsegment(
        name="s3ap_list_maintenance_reports",
        annotations={
            "service_name": "s3",
            "operation": "ListObjectsV2",
            "use_case": "transportation-maintenance",
            "prefix": maintenance_prefix,
        },
    ):
        maintenance_objects = s3ap.list_objects(prefix=maintenance_prefix, suffix="")

    for obj in maintenance_objects:
        category = classify_file(
            obj.get("Key", ""),
            inspection_prefix,
            maintenance_prefix,
        )
        if category == "maintenance_report":
            obj["category"] = "maintenance_report"
            maintenance_reports.append(obj)

    all_objects = inspection_images + maintenance_reports

    logger.info(
        "File classification: inspection_images=%d, maintenance_reports=%d, total=%d",
        len(inspection_images),
        len(maintenance_reports),
        len(all_objects),
    )

    # Step 5: Manifest 生成 (Req 6.1: keys, sizes, last-modified timestamps)
    # Note: image width/height not available from S3 ListObjects.
    # The Deterioration Detector handler checks resolution via Rekognition ImageProperties
    # or falls back to event-provided metadata from the caller.
    manifest = {
        "execution_id": context.aws_request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "use_case": "transportation-maintenance",
        "total_objects": len(all_objects),
        "total_size_bytes": sum(obj.get("Size", 0) for obj in all_objects),
        "inspection_image_count": len(inspection_images),
        "maintenance_report_count": len(maintenance_reports),
        "inspection_prefix": inspection_prefix,
        "maintenance_prefix": maintenance_prefix,
        "objects": all_objects,
    }

    manifest_key = f"manifests/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{context.aws_request_id}.json"

    s3ap_output.put_object(
        key=manifest_key,
        body=json.dumps(manifest, default=str),
        content_type="application/json",
    )

    logger.info(
        "Transportation Discovery completed: total_objects=%d, manifest=%s",
        len(all_objects),
        manifest_key,
    )

    # Step 6: EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="discovery")
    metrics.set_dimension("UseCase", "transportation-maintenance")
    metrics.put_metric("FilesProcessed", float(len(all_objects)), "Count")
    metrics.put_metric("InspectionImages", float(len(inspection_images)), "Count")
    metrics.put_metric("MaintenanceReports", float(len(maintenance_reports)), "Count")
    metrics.flush()

    return {
        "manifest_key": manifest_key,
        "total_objects": len(all_objects),
        "objects": all_objects,
        "inspection_images": inspection_images,
        "maintenance_reports": maintenance_reports,
    }
