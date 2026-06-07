"""旅行・ホスピタリティ業界 (UC20) Discovery Lambda ハンドラ

S3 Access Point から予約文書（PDF、スキャン画像）と施設点検画像を検出し、
Manifest JSON を生成して S3 AP に書き出す。

ファイル分類:
    - 予約文書: RESERVATION_DOC_PREFIX 配下の PDF/画像ファイル
    - 施設点検画像: FACILITY_IMAGE_PREFIX 配下の JPEG/PNG/TIFF ファイル

パスパターンは環境変数でカスタマイズ可能。

S3 AP 接続性バリデーション (Requirement 13.5):
    処理開始前に S3 AP への接続を検証し、
    到達不可の場合は構造化エラーレスポンスを返す。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
    RESERVATION_DOC_PREFIX: 予約文書プレフィックス (default: "reservations/")
    FACILITY_IMAGE_PREFIX: 施設点検画像プレフィックス (default: "facility-inspections/")
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

# 予約文書の対応拡張子
RESERVATION_DOC_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif"})

# 施設点検画像の対応拡張子
FACILITY_IMAGE_EXTENSIONS: frozenset[str] = frozenset({".jpg", ".jpeg", ".png", ".tiff", ".tif"})


def classify_file(key: str, reservation_prefix: str, facility_prefix: str) -> str | None:
    """ファイルキーをカテゴリに分類する。

    パスプレフィックスと拡張子に基づいてファイルを分類する。

    Args:
        key: S3 オブジェクトキー
        reservation_prefix: 予約文書プレフィックス
        facility_prefix: 施設点検画像プレフィックス

    Returns:
        "reservation_doc" | "facility_image" | None (対象外)
    """
    if not key:
        return None

    dot_index = key.rfind(".")
    if dot_index == -1:
        return None

    extension = key[dot_index:].lower()

    # プレフィックスに基づいて分類
    if reservation_prefix and key.startswith(reservation_prefix):
        if extension in RESERVATION_DOC_EXTENSIONS:
            return "reservation_doc"

    if facility_prefix and key.startswith(facility_prefix):
        if extension in FACILITY_IMAGE_EXTENSIONS:
            return "facility_image"

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
    """Travel Document Processing Discovery Lambda

    S3 AP から予約文書と施設点検画像を検出し、
    カテゴリ別に分類した Manifest JSON を生成・書き出す。

    Processing Flow:
        1. S3 AP 接続性バリデーション (Req 13.5)
        2. プレフィックス設定の取得
        3. 各プレフィックスでオブジェクト一覧取得
        4. ファイル分類フィルタ適用
        5. Manifest JSON 生成・書き出し
        6. EMF メトリクス出力

    Returns:
        dict: manifest_key, total_objects, reservation_docs, facility_images
    """
    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    s3ap_output = S3ApHelper(os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ["S3_ACCESS_POINT"]))
    reservation_prefix = os.environ.get("RESERVATION_DOC_PREFIX", "reservations/")
    facility_prefix = os.environ.get("FACILITY_IMAGE_PREFIX", "facility-inspections/")

    logger.info(
        "Travel Discovery started: access_point=%s, reservation_prefix=%r, facility_prefix=%r",
        os.environ["S3_ACCESS_POINT"],
        reservation_prefix,
        facility_prefix,
    )

    # Step 1: S3 AP 接続性バリデーション
    with xray_subsegment(
        name="s3ap_connectivity_validation",
        annotations={
            "service_name": "s3",
            "operation": "ConnectivityCheck",
            "use_case": "travel-document-processing",
        },
    ):
        connectivity_error = validate_s3ap_connectivity(s3ap)
        if connectivity_error is not None:
            return connectivity_error

    # Step 2-3: 各プレフィックスでオブジェクト一覧取得
    reservation_docs: list[dict] = []
    facility_images: list[dict] = []

    # 予約文書の検出
    with xray_subsegment(
        name="s3ap_list_reservation_docs",
        annotations={
            "service_name": "s3",
            "operation": "ListObjectsV2",
            "use_case": "travel-document-processing",
            "prefix": reservation_prefix,
        },
    ):
        reservation_objects = s3ap.list_objects(prefix=reservation_prefix, suffix="")

    for obj in reservation_objects:
        category = classify_file(obj.get("Key", ""), reservation_prefix, facility_prefix)
        if category == "reservation_doc":
            obj["category"] = "reservation_doc"
            reservation_docs.append(obj)

    # 施設点検画像の検出
    with xray_subsegment(
        name="s3ap_list_facility_images",
        annotations={
            "service_name": "s3",
            "operation": "ListObjectsV2",
            "use_case": "travel-document-processing",
            "prefix": facility_prefix,
        },
    ):
        facility_objects = s3ap.list_objects(prefix=facility_prefix, suffix="")

    for obj in facility_objects:
        category = classify_file(obj.get("Key", ""), reservation_prefix, facility_prefix)
        if category == "facility_image":
            obj["category"] = "facility_image"
            facility_images.append(obj)

    all_objects = reservation_docs + facility_images

    logger.info(
        "File classification: reservation_docs=%d, facility_images=%d, total=%d",
        len(reservation_docs),
        len(facility_images),
        len(all_objects),
    )

    # Step 5: Manifest 生成
    manifest = {
        "execution_id": context.aws_request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "use_case": "travel-document-processing",
        "total_objects": len(all_objects),
        "total_size_bytes": sum(obj.get("Size", 0) for obj in all_objects),
        "reservation_doc_count": len(reservation_docs),
        "facility_image_count": len(facility_images),
        "reservation_doc_prefix": reservation_prefix,
        "facility_image_prefix": facility_prefix,
        "objects": all_objects,
    }

    manifest_key = f"manifests/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{context.aws_request_id}.json"

    s3ap_output.put_object(
        key=manifest_key,
        body=json.dumps(manifest, default=str),
        content_type="application/json",
    )

    logger.info(
        "Travel Discovery completed: total_objects=%d, manifest=%s",
        len(all_objects),
        manifest_key,
    )

    # Step 6: EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="discovery")
    metrics.set_dimension("UseCase", "travel-document-processing")
    metrics.put_metric("FilesProcessed", float(len(all_objects)), "Count")
    metrics.put_metric("ReservationDocs", float(len(reservation_docs)), "Count")
    metrics.put_metric("FacilityImages", float(len(facility_images)), "Count")
    metrics.flush()

    return {
        "manifest_key": manifest_key,
        "total_objects": len(all_objects),
        "reservation_docs": reservation_docs,
        "facility_images": facility_images,
    }
