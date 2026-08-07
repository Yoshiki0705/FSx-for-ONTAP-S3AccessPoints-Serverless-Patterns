"""製造業 Discovery Lambda ハンドラ

S3 Access Point から CSV センサーログと JPEG/PNG 検査画像を検出し、
Manifest JSON を生成して S3 AP に書き出す。

対象ファイル:
- CSV センサーログ (.csv)
- JPEG 検査画像 (.jpeg, .jpg)
- PNG 検査画像 (.png)

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用、省略時は S3_ACCESS_POINT を使用)
    PREFIX_FILTER: プレフィックスフィルタ (optional)
    SENSOR_LOG_SUFFIX_FILTER: センサーログの拡張子。カンマ区切り (optional)
    INSPECTION_IMAGE_SUFFIX_FILTER: 検査画像の拡張子。カンマ区切り (optional)
        いずれも未設定または実質空の場合はモジュール定数を使用する。
        検出結果はカテゴリごとに後続処理が分かれるため、単一の SUFFIX_FILTER では
        設定できない（片方にしか属さない拡張子を足すと分類で落ちる）。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler, xray_subsegment
from shared.s3ap_helper import S3ApHelper
from shared.suffix_filter import allowed_suffixes

logger = logging.getLogger(__name__)

# 製造業ユースケースで対象とするファイル拡張子
SENSOR_LOG_SUFFIXES = (".csv",)
INSPECTION_IMAGE_SUFFIXES = (".jpeg", ".jpg", ".png")
ALL_SUFFIXES = SENSOR_LOG_SUFFIXES + INSPECTION_IMAGE_SUFFIXES


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Manufacturing Analytics Discovery Lambda

    S3 AP から CSV センサーログと JPEG/PNG 検査画像を検出し、
    Manifest JSON を生成・S3 に書き出す。

    Returns:
        dict: manifest_bucket, manifest_key, total_objects,
              csv_files (CSV ファイルリスト), image_files (画像ファイルリスト)
    """
    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    s3ap_output = S3ApHelper(os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ["S3_ACCESS_POINT"]))
    prefix = os.environ.get("PREFIX_FILTER", "")

    logger.info(
        "Manufacturing Analytics Discovery started: access_point=%s, prefix=%r",
        os.environ["S3_ACCESS_POINT"],
        prefix,
    )

    # 検出対象のサフィックスをカテゴリごとに決める。
    #
    # このパターンは検出結果をセンサーログと検査画像に分類し、後続の処理が別なので、
    # 単一の平坦な SUFFIX_FILTER では設定できない。1 つのノブに拡張子を足しても、
    # 下の分類（if/elif）でどちらにも該当せず落ちる。カテゴリごとに環境変数を
    # 分けることで、リスト対象と分類対象が構造的に一致する。
    sensor_log_suffixes = allowed_suffixes(SENSOR_LOG_SUFFIXES, env_var="SENSOR_LOG_SUFFIX_FILTER")
    inspection_image_suffixes = allowed_suffixes(INSPECTION_IMAGE_SUFFIXES, env_var="INSPECTION_IMAGE_SUFFIX_FILTER")

    # 両カテゴリの合併を走査対象にする（重複はここで除く）
    scan_suffixes = tuple(dict.fromkeys(sensor_log_suffixes + inspection_image_suffixes))

    logger.info(
        "Discovery suffixes: sensor_logs=%s, inspection_images=%s",
        ",".join(sensor_log_suffixes),
        ",".join(inspection_image_suffixes),
    )

    # 対象ファイルを各サフィックスで検出
    all_objects: list[dict] = []
    for suffix in scan_suffixes:
        with xray_subsegment(
            name="s3ap_list_objects",
            annotations={"service_name": "s3", "operation": "ListObjectsV2", "use_case": "manufacturing-analytics"},
        ):
            objects = s3ap.list_objects(prefix=prefix, suffix=suffix)
        all_objects.extend(objects)

    # 重複排除
    seen_keys: set[str] = set()
    unique_objects: list[dict] = []
    for obj in all_objects:
        if obj["Key"] not in seen_keys:
            seen_keys.add(obj["Key"])
            unique_objects.append(obj)

    # CSV ファイルと画像ファイルを分類
    csv_files: list[dict] = []
    image_files: list[dict] = []
    for obj in unique_objects:
        key_lower = obj["Key"].lower()
        # 走査に使ったものと同じタプルで分類する。定数を直接参照すると、
        # 環境変数で広げた拡張子がどちらにも該当せず無言で落ちる。
        if any(key_lower.endswith(s) for s in sensor_log_suffixes):
            csv_files.append(obj)
        elif any(key_lower.endswith(s) for s in inspection_image_suffixes):
            image_files.append(obj)

    # Manifest 生成
    manifest = {
        "execution_id": context.aws_request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_objects": len(unique_objects),
        "objects": unique_objects,
        "csv_files": csv_files,
        "image_files": image_files,
    }

    # Manifest を S3 AP に書き出し
    manifest_key = f"manifests/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{context.aws_request_id}.json"

    s3ap_output.put_object(
        key=manifest_key,
        body=json.dumps(manifest, default=str),
        content_type="application/json",
    )

    logger.info(
        "Manufacturing Analytics Discovery completed: total=%d, csv=%d, images=%d, manifest=%s",
        len(unique_objects),
        len(csv_files),
        len(image_files),
        manifest_key,
    )

    # EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="discovery")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "manufacturing-analytics"))
    metrics.put_metric("FilesProcessed", float(len(unique_objects)), "Count")
    metrics.flush()

    return {
        "manifest_key": manifest_key,
        "total_objects": len(unique_objects),
        "csv_files": csv_files,
        "image_files": image_files,
    }
