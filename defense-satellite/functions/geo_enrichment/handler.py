"""UC15 Defense/Space Geo Enrichment Lambda

衛星画像のヘッダから地理メタデータ（座標、取得時刻、解像度、センサータイプ）を
抽出して、検出結果を補強する。

Environment Variables:
    OUTPUT_BUCKET: 出力先 S3 バケット名
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)


def _build_enrichment(
    tile_metadata: dict[str, Any], source_key: str
) -> dict[str, Any]:
    """タイルメタデータから geo enrichment 情報を構築する。

    Args:
        tile_metadata: タイリング時に抽出したメタデータ
        source_key: 元ファイルの S3 キー

    Returns:
        dict: enrichment 情報
    """
    bounds = tile_metadata.get("bounds", [])
    if len(bounds) == 4:
        center_lon = (bounds[0] + bounds[2]) / 2
        center_lat = (bounds[1] + bounds[3]) / 2
    else:
        center_lon = 0.0
        center_lat = 0.0

    # ファイル名から取得時刻を推定（簡易実装）
    # 例: satellite/2026/05/10/image.tif → 2026-05-10
    acquisition_date = None
    parts = source_key.split("/")
    if len(parts) >= 4 and parts[0] == "satellite":
        try:
            year = int(parts[1])
            month = int(parts[2])
            day = int(parts[3]) if parts[3].isdigit() else 1
            acquisition_date = datetime(year, month, day).isoformat()
        except (ValueError, IndexError):
            pass

    # センサータイプ判定
    source_lower = source_key.lower()
    if source_lower.endswith((".tif", ".tiff")):
        sensor_type = "optical"
    elif source_lower.endswith((".ntf", ".nitf")):
        sensor_type = "optical-nitf"
    elif source_lower.endswith((".hdf", ".h5")):
        sensor_type = "sar"
    else:
        sensor_type = "unknown"

    return {
        "center_coordinates": {"lat": center_lat, "lon": center_lon},
        "bounds": bounds,
        "acquisition_date": acquisition_date,
        "sensor_type": sensor_type,
        "crs": tile_metadata.get("crs", "unknown"),
        "resolution": {
            "width": tile_metadata.get("width", 0),
            "height": tile_metadata.get("height", 0),
            "bands": tile_metadata.get("bands", 0),
        },
    }


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """UC15 Geo Enrichment Lambda ハンドラ。

    Input:
        {
            "tile_id": geohash,
            "detections": [...],
            "image_metadata": {...},
            "source_key": "satellite/..."
        }

    Output:
        {
            "tile_id": geohash,
            "enrichment": {...},
            "enriched_detections": [...]
        }
    """
    output_bucket = os.environ["OUTPUT_BUCKET"]

    tile_id = event.get("tile_id", "unknown")
    detections = event.get("detections", [])
    tile_metadata = event.get("image_metadata", {})
    source_key = event.get("source_key", "")

    enrichment = _build_enrichment(tile_metadata, source_key)

    # 検出結果に enrichment を付与
    enriched_detections = []
    for det in detections:
        enriched_detections.append({
            **det,
            "geo_context": enrichment,
        })

    # S3 に書き出し
    result_key = f"enriched/{datetime.utcnow().strftime('%Y/%m/%d')}/{tile_id}.json"
    s3_client = boto3.client("s3")
    s3_client.put_object(
        Bucket=output_bucket,
        Key=result_key,
        Body=json.dumps({
            "tile_id": tile_id,
            "enrichment": enrichment,
            "enriched_detections": enriched_detections,
        }, default=str),
        ContentType="application/json",
        ServerSideEncryption="aws:kms",
    )

    logger.info(
        "UC15 Geo Enrichment completed: tile_id=%s, sensor=%s, detections=%d",
        tile_id,
        enrichment["sensor_type"],
        len(enriched_detections),
    )

    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="geo_enrichment")
    metrics.set_dimension("UseCase", "defense-satellite")
    metrics.set_dimension("SensorType", enrichment["sensor_type"])
    metrics.put_metric("EnrichedDetections", float(len(enriched_detections)), "Count")
    metrics.flush()

    return {
        "tile_id": tile_id,
        "enrichment": enrichment,
        "enriched_detections": enriched_detections,
        "result_key": result_key,
    }
