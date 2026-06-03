"""農業・食品業界 (UC21) Discovery Lambda ハンドラ

S3 Access Point から農地航空画像（GeoTIFF/JPEG with EXIF GPS）と
トレーサビリティ文書（収穫記録、出荷マニフェスト、検査証明書）を検出し、
Manifest JSON を生成する。

ファイル分類:
    - 航空画像: IMAGE_PREFIX 配下の GeoTIFF/JPEG (≤500 MB)
    - トレーサビリティ文書: TRACEABILITY_PREFIX 配下の PDF/Excel/CSV

S3 AP 接続性バリデーション (Requirement 13.5):
    処理開始前に S3 AP への接続を検証し、
    到達不可の場合は構造化エラーレスポンスを返す。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
    IMAGE_PREFIX: 航空画像プレフィックス (default: "aerial-images/")
    TRACEABILITY_PREFIX: トレーサビリティ文書プレフィックス (default: "traceability/")
    MAX_IMAGE_SIZE_MB: 画像最大サイズ MB (default: 500)
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

# 航空画像の対応拡張子 (GeoTIFF / JPEG with potential EXIF GPS)
AERIAL_IMAGE_EXTENSIONS: frozenset[str] = frozenset(
    {".tif", ".tiff", ".geotiff", ".jpg", ".jpeg"}
)

# トレーサビリティ文書の対応拡張子
TRACEABILITY_DOC_EXTENSIONS: frozenset[str] = frozenset(
    {".pdf", ".xlsx", ".xls", ".csv", ".docx"}
)

# デフォルト最大画像サイズ (バイト)
DEFAULT_MAX_IMAGE_SIZE_MB: int = 500


def classify_file(
    key: str,
    size: int,
    image_prefix: str,
    traceability_prefix: str,
    max_image_size_bytes: int,
) -> str | None:
    """ファイルキーをカテゴリに分類する。

    Args:
        key: S3 オブジェクトキー
        size: ファイルサイズ (bytes)
        image_prefix: 航空画像プレフィックス
        traceability_prefix: トレーサビリティ文書プレフィックス
        max_image_size_bytes: 画像最大サイズ (bytes)

    Returns:
        "aerial_image" | "traceability_doc" | None (対象外)
    """
    if not key:
        return None

    dot_index = key.rfind(".")
    if dot_index == -1:
        return None

    extension = key[dot_index:].lower()

    # 航空画像チェック
    if image_prefix and key.startswith(image_prefix):
        if extension in AERIAL_IMAGE_EXTENSIONS:
            if size <= max_image_size_bytes:
                return "aerial_image"
            else:
                logger.info(
                    "Image exceeds size limit: key=%s, size=%d, max=%d",
                    key,
                    size,
                    max_image_size_bytes,
                )
                return None

    # トレーサビリティ文書チェック
    if traceability_prefix and key.startswith(traceability_prefix):
        if extension in TRACEABILITY_DOC_EXTENSIONS:
            return "traceability_doc"

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
            "body": json.dumps({
                "error": "S3 Access Point unreachable",
                "error_type": "ConnectivityError",
                "error_code": e.error_code or "Unknown",
                "access_point": s3ap.bucket_param,
                "message": str(e),
            }),
        }
    except Exception as e:
        logger.error(
            "Unexpected error during S3 AP connectivity validation: %s",
            str(e),
        )
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
    """Agri-Food Traceability Discovery Lambda

    S3 AP から航空画像とトレーサビリティ文書を検出し、
    カテゴリ別に分類した Manifest JSON を生成・書き出す。

    Processing Flow:
        1. S3 AP 接続性バリデーション (Req 13.5)
        2. プレフィックス設定の取得
        3. 各プレフィックスでオブジェクト一覧取得
        4. ファイル分類フィルタ適用 (500 MB サイズフィルタ含む)
        5. Manifest JSON 生成・書き出し
        6. EMF メトリクス出力

    Returns:
        dict: manifest_key, total_objects, aerial_images, traceability_docs
    """
    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    s3ap_output = S3ApHelper(
        os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ["S3_ACCESS_POINT"])
    )
    image_prefix = os.environ.get("IMAGE_PREFIX", "aerial-images/")
    traceability_prefix = os.environ.get("TRACEABILITY_PREFIX", "traceability/")
    max_image_size_mb = int(os.environ.get("MAX_IMAGE_SIZE_MB", str(DEFAULT_MAX_IMAGE_SIZE_MB)))
    max_image_size_bytes = max_image_size_mb * 1024 * 1024

    logger.info(
        "Agri-Food Discovery started: access_point=%s, "
        "image_prefix=%r, traceability_prefix=%r, max_image_size_mb=%d",
        os.environ["S3_ACCESS_POINT"],
        image_prefix,
        traceability_prefix,
        max_image_size_mb,
    )

    # Step 1: S3 AP 接続性バリデーション
    with xray_subsegment(
        name="s3ap_connectivity_validation",
        annotations={
            "service_name": "s3",
            "operation": "ConnectivityCheck",
            "use_case": "agri-food-traceability",
        },
    ):
        connectivity_error = validate_s3ap_connectivity(s3ap)
        if connectivity_error is not None:
            return connectivity_error

    # Step 2-3: 各プレフィックスでオブジェクト一覧取得
    aerial_images: list[dict] = []
    traceability_docs: list[dict] = []

    # 航空画像の検出
    with xray_subsegment(
        name="s3ap_list_aerial_images",
        annotations={
            "service_name": "s3",
            "operation": "ListObjectsV2",
            "use_case": "agri-food-traceability",
            "prefix": image_prefix,
        },
    ):
        image_objects = s3ap.list_objects(prefix=image_prefix, suffix="")

    for obj in image_objects:
        category = classify_file(
            obj.get("Key", ""),
            obj.get("Size", 0),
            image_prefix,
            traceability_prefix,
            max_image_size_bytes,
        )
        if category == "aerial_image":
            obj["category"] = "aerial_image"
            aerial_images.append(obj)

    # トレーサビリティ文書の検出
    with xray_subsegment(
        name="s3ap_list_traceability_docs",
        annotations={
            "service_name": "s3",
            "operation": "ListObjectsV2",
            "use_case": "agri-food-traceability",
            "prefix": traceability_prefix,
        },
    ):
        traceability_objects = s3ap.list_objects(prefix=traceability_prefix, suffix="")

    for obj in traceability_objects:
        category = classify_file(
            obj.get("Key", ""),
            obj.get("Size", 0),
            image_prefix,
            traceability_prefix,
            max_image_size_bytes,
        )
        if category == "traceability_doc":
            obj["category"] = "traceability_doc"
            traceability_docs.append(obj)

    all_objects = aerial_images + traceability_docs

    logger.info(
        "File classification: aerial_images=%d, traceability_docs=%d, total=%d",
        len(aerial_images),
        len(traceability_docs),
        len(all_objects),
    )

    # Step 5: Manifest 生成
    manifest = {
        "execution_id": context.aws_request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "use_case": "agri-food-traceability",
        "total_objects": len(all_objects),
        "total_size_bytes": sum(obj.get("Size", 0) for obj in all_objects),
        "aerial_image_count": len(aerial_images),
        "traceability_doc_count": len(traceability_docs),
        "image_prefix": image_prefix,
        "traceability_prefix": traceability_prefix,
        "max_image_size_mb": max_image_size_mb,
        "objects": all_objects,
    }

    manifest_key = (
        f"manifests/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{context.aws_request_id}.json"
    )

    s3ap_output.put_object(
        key=manifest_key,
        body=json.dumps(manifest, default=str),
        content_type="application/json",
    )

    logger.info(
        "Agri-Food Discovery completed: total_objects=%d, manifest=%s",
        len(all_objects),
        manifest_key,
    )

    # Step 6: EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="discovery")
    metrics.set_dimension("UseCase", "agri-food-traceability")
    metrics.put_metric("FilesProcessed", float(len(all_objects)), "Count")
    metrics.put_metric("AerialImages", float(len(aerial_images)), "Count")
    metrics.put_metric("TraceabilityDocs", float(len(traceability_docs)), "Count")
    metrics.flush()

    return {
        "manifest_key": manifest_key,
        "total_objects": len(all_objects),
        "aerial_images": aerial_images,
        "traceability_docs": traceability_docs,
    }
