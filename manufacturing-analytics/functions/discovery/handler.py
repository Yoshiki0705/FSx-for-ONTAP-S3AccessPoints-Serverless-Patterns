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
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime

from shared.exceptions import lambda_error_handler
from shared.s3ap_helper import S3ApHelper
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler

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
    s3ap_output = S3ApHelper(
        os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ["S3_ACCESS_POINT"])
    )
    prefix = os.environ.get("PREFIX_FILTER", "")

    logger.info(
        "Manufacturing Analytics Discovery started: access_point=%s, prefix=%r",
        os.environ["S3_ACCESS_POINT"],
        prefix,
    )

    # 対象ファイルを各サフィックスで検出
    all_objects: list[dict] = []
    for suffix in ALL_SUFFIXES:
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
        if any(key_lower.endswith(s) for s in SENSOR_LOG_SUFFIXES):
            csv_files.append(obj)
        elif any(key_lower.endswith(s) for s in INSPECTION_IMAGE_SUFFIXES):
            image_files.append(obj)

    # Manifest 生成
    manifest = {
        "execution_id": context.aws_request_id,
        "timestamp": datetime.utcnow().isoformat(),
        "total_objects": len(unique_objects),
        "objects": unique_objects,
        "csv_files": csv_files,
        "image_files": image_files,
    }

    # Manifest を S3 AP に書き出し
    manifest_key = (
        f"manifests/{datetime.utcnow().strftime('%Y/%m/%d')}"
        f"/{context.aws_request_id}.json"
    )

    s3ap_output.put_object(
        key=manifest_key,
        body=json.dumps(manifest, default=str),
        content_type="application/json",
    )

    logger.info(
        "Manufacturing Analytics Discovery completed: "
        "total=%d, csv=%d, images=%d, manifest=%s",
        len(unique_objects),
        len(csv_files),
        len(image_files),
        manifest_key,
    )


    # EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="discovery")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "manufacturing-analytics"))
    metrics.put_metric("FilesProcessed", float(len(objects)), "Count")
    metrics.flush()

    return {
        "manifest_key": manifest_key,
        "total_objects": len(unique_objects),
        "csv_files": csv_files,
        "image_files": image_files,
    }
