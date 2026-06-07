"""通信業界 (UC18) Discovery Lambda ハンドラ

S3 Access Point から CDR (Call Detail Record) ファイルおよびネットワーク機器ログを
検出し、Manifest JSON を生成して S3 AP に書き出す。

サフィックスフィルタは環境変数 CDR_SUFFIX_FILTER でカンマ区切りで設定可能。
デフォルトは ".csv,.asn1,.parquet" で、最大 20 パターンまで受け付ける。

S3 AP 接続性バリデーション (Requirement 13.5):
    処理開始前に S3 AP への接続を HeadBucket (GetBucketLocation) で検証し、
    到達不可の場合は構造化エラーレスポンスを返す。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用、省略時は S3_ACCESS_POINT を使用)
    PREFIX_FILTER: プレフィックスフィルタ (optional)
    CDR_SUFFIX_FILTER: CDR サフィックスフィルタ (default: ".csv,.asn1,.parquet", max 20)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from shared.exceptions import S3ApHelperError, lambda_error_handler
from shared.s3ap_helper import S3ApHelper
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)

# デフォルト CDR サフィックスフィルタ
DEFAULT_CDR_SUFFIX_FILTER = ".csv,.asn1,.parquet"

# サフィックスパターンの最大数
MAX_SUFFIX_PATTERNS = 20


def parse_suffix_filter(suffix_filter_str: str) -> list[str]:
    """サフィックスフィルタ文字列をパースし、有効なサフィックスリストを返す。

    カンマ区切りの文字列を分割し、空白を除去、空文字列を除外する。
    最大 MAX_SUFFIX_PATTERNS (20) パターンまで受け付け、超過分は切り捨てる。

    Args:
        suffix_filter_str: カンマ区切りのサフィックスフィルタ文字列
            (例: ".csv,.asn1,.parquet")

    Returns:
        list[str]: 有効なサフィックスのリスト (最大 20 エントリ)
    """
    if not suffix_filter_str or not suffix_filter_str.strip():
        return []

    suffixes = [s.strip() for s in suffix_filter_str.split(",") if s.strip()]
    if len(suffixes) > MAX_SUFFIX_PATTERNS:
        logger.warning(
            "Suffix filter exceeds maximum of %d patterns (%d provided). Truncating to first %d entries.",
            MAX_SUFFIX_PATTERNS,
            len(suffixes),
            MAX_SUFFIX_PATTERNS,
        )
        suffixes = suffixes[:MAX_SUFFIX_PATTERNS]

    return suffixes


def validate_s3ap_connectivity(s3ap: S3ApHelper) -> dict | None:
    """S3 Access Point への接続性を検証する。

    HeadBucket (GetBucketLocation 相当) を使用して S3 AP が到達可能か確認する。
    ListObjectsV2 で MaxKeys=1 を実行することで、最小限の権限で接続性を確認する。

    Args:
        s3ap: S3ApHelper インスタンス

    Returns:
        None: 接続成功時
        dict: 接続失敗時の構造化エラーレスポンス
    """
    try:
        # MaxKeys=1 で軽量な接続性テストを実行
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
    """Telecom Network Analytics Discovery Lambda

    S3 AP から CDR ファイルおよびネットワークログを検出し、
    Manifest JSON を生成・S3 に書き出す。

    Processing Flow:
        1. S3 AP 接続性バリデーション (Req 13.5)
        2. サフィックスフィルタのパース (max 20 patterns)
        3. 各サフィックスでオブジェクト一覧取得
        4. Manifest JSON 生成・書き出し
        5. EMF メトリクス出力

    Returns:
        dict: manifest_key, total_objects, objects, suffix_patterns_used
    """
    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    s3ap_output = S3ApHelper(os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ["S3_ACCESS_POINT"]))
    prefix = os.environ.get("PREFIX_FILTER", "")
    suffix_filter_str = os.environ.get("CDR_SUFFIX_FILTER", DEFAULT_CDR_SUFFIX_FILTER)

    logger.info(
        "Telecom Discovery started: access_point=%s, prefix=%r, suffix_filter=%r",
        os.environ["S3_ACCESS_POINT"],
        prefix,
        suffix_filter_str,
    )

    # Step 1: S3 AP 接続性バリデーション (Requirement 13.5)
    with xray_subsegment(
        name="s3ap_connectivity_validation",
        annotations={
            "service_name": "s3",
            "operation": "ConnectivityCheck",
            "use_case": "telecom-network-analytics",
        },
    ):
        connectivity_error = validate_s3ap_connectivity(s3ap)
        if connectivity_error is not None:
            return connectivity_error

    # Step 2: サフィックスフィルタのパース
    suffixes = parse_suffix_filter(suffix_filter_str)
    if not suffixes:
        logger.warning("No valid suffix patterns configured. Using default: %s", DEFAULT_CDR_SUFFIX_FILTER)
        suffixes = parse_suffix_filter(DEFAULT_CDR_SUFFIX_FILTER)

    logger.info("Using %d suffix patterns: %s", len(suffixes), suffixes)

    # Step 3: 各サフィックスでオブジェクト一覧取得
    all_objects: list[dict] = []
    for suffix in suffixes:
        with xray_subsegment(
            name="s3ap_list_objects",
            annotations={
                "service_name": "s3",
                "operation": "ListObjectsV2",
                "use_case": "telecom-network-analytics",
                "suffix": suffix,
            },
        ):
            objects = s3ap.list_objects(prefix=prefix, suffix=suffix)
        all_objects.extend(objects)

    # 重複排除（同一キーが複数サフィックスにマッチする可能性に備える）
    seen_keys: set[str] = set()
    unique_objects: list[dict] = []
    for obj in all_objects:
        if obj["Key"] not in seen_keys:
            seen_keys.add(obj["Key"])
            unique_objects.append(obj)

    # Step 4: Manifest 生成
    manifest = {
        "execution_id": context.aws_request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "use_case": "telecom-network-analytics",
        "total_objects": len(unique_objects),
        "total_size_bytes": sum(obj.get("Size", 0) for obj in unique_objects),
        "suffix_patterns_used": suffixes,
        "objects": unique_objects,
    }

    # Manifest を S3 AP に書き出し
    manifest_key = f"manifests/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{context.aws_request_id}.json"

    s3ap_output.put_object(
        key=manifest_key,
        body=json.dumps(manifest, default=str),
        content_type="application/json",
    )

    logger.info(
        "Telecom Discovery completed: total_objects=%d, manifest=%s",
        len(unique_objects),
        manifest_key,
    )

    # Step 5: EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="discovery")
    metrics.set_dimension("UseCase", "telecom-network-analytics")
    metrics.put_metric("FilesProcessed", float(len(unique_objects)), "Count")
    metrics.flush()

    return {
        "manifest_key": manifest_key,
        "total_objects": len(unique_objects),
        "objects": unique_objects,
        "suffix_patterns_used": suffixes,
    }
