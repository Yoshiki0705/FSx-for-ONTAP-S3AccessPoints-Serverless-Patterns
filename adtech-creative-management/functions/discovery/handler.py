"""広告・マーケティング業界 (UC19) Discovery Lambda ハンドラ

S3 Access Point からクリエイティブアセット（画像・動画ファイル）を検出し、
Manifest JSON を生成して S3 AP に書き出す。

対応メディアフォーマット:
    JPEG (.jpg, .jpeg), PNG (.png), TIFF (.tiff, .tif),
    MP4 (.mp4), MOV (.mov), PSD (.psd)

ディレクトリプレフィックスフィルタは環境変数 CREATIVE_PREFIX_FILTER で設定可能。
5 GB を超えるファイルは処理対象から除外される。

S3 AP 接続性バリデーション (Requirement 13.5):
    処理開始前に S3 AP への接続を検証し、
    到達不可の場合は構造化エラーレスポンスを返す。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用、省略時は S3_ACCESS_POINT を使用)
    CREATIVE_PREFIX_FILTER: クリエイティブアセットディレクトリプレフィックスフィルタ (optional)
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

# 対応メディアフォーマット拡張子 (小文字)
SUPPORTED_MEDIA_EXTENSIONS: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".mp4", ".mov", ".psd"}
)

# ファイルサイズ上限: 5 GB (5,368,709,120 bytes)
MAX_FILE_SIZE_BYTES: int = 5_368_709_120


def is_supported_media(key: str) -> bool:
    """ファイルキーが対応メディアフォーマットかどうかを判定する。

    拡張子を小文字に正規化して SUPPORTED_MEDIA_EXTENSIONS と照合する。

    Args:
        key: S3 オブジェクトキー (例: "creatives/2026/banner.jpg")

    Returns:
        bool: 対応メディアフォーマットの場合 True
    """
    if not key:
        return False

    # ドットが含まれない場合は拡張子なし
    dot_index = key.rfind(".")
    if dot_index == -1:
        return False

    extension = key[dot_index:].lower()
    return extension in SUPPORTED_MEDIA_EXTENSIONS


def is_within_size_limit(size: int) -> bool:
    """ファイルサイズが 5 GB 以下かどうかを判定する。

    Args:
        size: ファイルサイズ（バイト）

    Returns:
        bool: 5 GB 以下の場合 True
    """
    return 0 <= size <= MAX_FILE_SIZE_BYTES


def validate_s3ap_connectivity(s3ap: S3ApHelper) -> dict | None:
    """S3 Access Point への接続性を検証する。

    ListObjectsV2 で MaxKeys=1 を実行し、S3 AP が到達可能か確認する。

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
    """Adtech Creative Management Discovery Lambda

    S3 AP からクリエイティブアセット（対応メディアフォーマット）を検出し、
    5 GB 超のファイルを除外した Manifest JSON を生成・書き出す。

    Processing Flow:
        1. S3 AP 接続性バリデーション (Req 13.5)
        2. プレフィックスフィルタの取得
        3. オブジェクト一覧取得
        4. メディアフォーマットフィルタ + サイズフィルタ適用
        5. Manifest JSON 生成・書き出し
        6. EMF メトリクス出力

    Returns:
        dict: manifest_key, total_objects, objects, excluded_oversize_count,
              excluded_unsupported_count
    """
    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    s3ap_output = S3ApHelper(os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ["S3_ACCESS_POINT"]))
    prefix = os.environ.get("CREATIVE_PREFIX_FILTER", "")

    logger.info(
        "Adtech Creative Discovery started: access_point=%s, prefix=%r",
        os.environ["S3_ACCESS_POINT"],
        prefix,
    )

    # Step 1: S3 AP 接続性バリデーション (Requirement 13.5)
    with xray_subsegment(
        name="s3ap_connectivity_validation",
        annotations={
            "service_name": "s3",
            "operation": "ConnectivityCheck",
            "use_case": "adtech-creative-management",
        },
    ):
        connectivity_error = validate_s3ap_connectivity(s3ap)
        if connectivity_error is not None:
            return connectivity_error

    # Step 2-3: オブジェクト一覧取得（サフィックスフィルタなし — クライアントサイドで判定）
    with xray_subsegment(
        name="s3ap_list_objects",
        annotations={
            "service_name": "s3",
            "operation": "ListObjectsV2",
            "use_case": "adtech-creative-management",
            "prefix": prefix,
        },
    ):
        all_objects = s3ap.list_objects(prefix=prefix, suffix="")

    # Step 4: メディアフォーマットフィルタ + サイズフィルタ適用
    filtered_objects: list[dict] = []
    excluded_oversize_count: int = 0
    excluded_unsupported_count: int = 0

    for obj in all_objects:
        key = obj.get("Key", "")
        size = obj.get("Size", 0)

        # メディアフォーマット判定
        if not is_supported_media(key):
            excluded_unsupported_count += 1
            continue

        # サイズ上限判定 (5 GB 超を除外)
        if not is_within_size_limit(size):
            excluded_oversize_count += 1
            logger.info(
                "Excluded oversize file: key=%s, size=%d bytes (max=%d)",
                key,
                size,
                MAX_FILE_SIZE_BYTES,
            )
            continue

        filtered_objects.append(obj)

    logger.info(
        "Media filter applied: total_scanned=%d, matched=%d, excluded_unsupported=%d, excluded_oversize=%d",
        len(all_objects),
        len(filtered_objects),
        excluded_unsupported_count,
        excluded_oversize_count,
    )

    # Step 5: Manifest 生成
    manifest = {
        "execution_id": context.aws_request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "use_case": "adtech-creative-management",
        "total_objects": len(filtered_objects),
        "total_size_bytes": sum(obj.get("Size", 0) for obj in filtered_objects),
        "prefix_filter": prefix,
        "supported_formats": sorted(SUPPORTED_MEDIA_EXTENSIONS),
        "max_file_size_bytes": MAX_FILE_SIZE_BYTES,
        "excluded_oversize_count": excluded_oversize_count,
        "excluded_unsupported_count": excluded_unsupported_count,
        "objects": filtered_objects,
    }

    # Manifest を S3 AP に書き出し
    manifest_key = f"manifests/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{context.aws_request_id}.json"

    s3ap_output.put_object(
        key=manifest_key,
        body=json.dumps(manifest, default=str),
        content_type="application/json",
    )

    logger.info(
        "Adtech Creative Discovery completed: total_objects=%d, manifest=%s",
        len(filtered_objects),
        manifest_key,
    )

    # Step 6: EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="discovery")
    metrics.set_dimension("UseCase", "adtech-creative-management")
    metrics.put_metric("FilesProcessed", float(len(filtered_objects)), "Count")
    metrics.put_metric("FilesExcludedOversize", float(excluded_oversize_count), "Count")
    metrics.put_metric("FilesExcludedUnsupported", float(excluded_unsupported_count), "Count")
    metrics.flush()

    return {
        "manifest_key": manifest_key,
        "total_objects": len(filtered_objects),
        "objects": filtered_objects,
        "excluded_oversize_count": excluded_oversize_count,
        "excluded_unsupported_count": excluded_unsupported_count,
    }
