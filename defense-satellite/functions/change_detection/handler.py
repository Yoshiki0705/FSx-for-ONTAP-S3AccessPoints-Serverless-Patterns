"""UC15 Defense/Space Change Detection Lambda

現在の検出結果を DynamoDB に保存し、過去の検出結果と比較して変化を検出する。

DynamoDB Schema:
    PK: tile_id (geohash)
    SK: timestamp (ISO 8601)
    Attributes: image_key, detected_objects, change_from_previous, ttl

Environment Variables:
    CHANGE_HISTORY_TABLE: DynamoDB テーブル名
    OUTPUT_BUCKET: 出力先 S3 バケット名
    TTL_SECONDS: DynamoDB TTL 秒数 (default: 31536000 = 1年)
    CHANGE_AREA_THRESHOLD_KM2: 変化面積閾値 km² (default: 1.0)
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)


def _compute_geohash(lat: float, lon: float, precision: int = 5) -> str:
    """簡易 geohash 実装（外部ライブラリなし）。

    Args:
        lat: 緯度
        lon: 経度
        precision: 精度（デフォルト 5 = 約 5km 四方）

    Returns:
        str: geohash
    """
    base32 = "0123456789bcdefghjkmnpqrstuvwxyz"
    lat_range = [-90.0, 90.0]
    lon_range = [-180.0, 180.0]
    geohash = []
    bits = []
    even = True
    while len(geohash) < precision:
        if even:
            mid = (lon_range[0] + lon_range[1]) / 2
            if lon >= mid:
                bits.append(1)
                lon_range[0] = mid
            else:
                bits.append(0)
                lon_range[1] = mid
        else:
            mid = (lat_range[0] + lat_range[1]) / 2
            if lat >= mid:
                bits.append(1)
                lat_range[0] = mid
            else:
                bits.append(0)
                lat_range[1] = mid
        even = not even
        if len(bits) == 5:
            idx = sum(b << (4 - i) for i, b in enumerate(bits))
            geohash.append(base32[idx])
            bits = []
    return "".join(geohash)


def _compute_diff_area_km2(
    current_detections: list[dict], previous_detections: list[dict]
) -> float:
    """現在と過去の検出結果から変化面積を概算する。

    簡易実装: bbox 面積の差分絶対値を km² で概算（1度 ≒ 111 km として）。

    Args:
        current_detections: 現在の検出結果
        previous_detections: 過去の検出結果

    Returns:
        float: 変化面積 km²
    """
    def total_area(detections: list[dict]) -> float:
        area = 0.0
        for d in detections:
            bbox = d.get("bbox", {})
            if bbox:
                # 正規化座標 (0-1) を想定。1度 ≒ 111 km として概算
                w = bbox.get("Width", 0.0)
                h = bbox.get("Height", 0.0)
                area += w * h * 111.0 * 111.0
        return area

    return abs(total_area(current_detections) - total_area(previous_detections))


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """UC15 Change Detection Lambda ハンドラ。

    Input:
        {
            "tile_key": "...",
            "detections": [...],
            "image_metadata": {"bounds": [lon_min, lat_min, lon_max, lat_max], ...}
        }

    Output:
        {
            "tile_id": geohash,
            "timestamp": ISO 8601,
            "change_detected": bool,
            "diff_area_km2": float,
            "previous_timestamp": ISO 8601 | null
        }
    """
    table_name = os.environ["CHANGE_HISTORY_TABLE"]
    output_bucket = os.environ["OUTPUT_BUCKET"]
    ttl_seconds = int(os.environ.get("TTL_SECONDS", str(365 * 24 * 3600)))
    threshold = float(os.environ.get("CHANGE_AREA_THRESHOLD_KM2", "1.0"))

    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)

    detections = event.get("detections", [])
    image_metadata = event.get("image_metadata", {})
    bounds = image_metadata.get("bounds", [0.0, 0.0, 0.0, 0.0])

    # 中心座標から geohash 算出
    if len(bounds) == 4:
        center_lon = (bounds[0] + bounds[2]) / 2
        center_lat = (bounds[1] + bounds[3]) / 2
    else:
        center_lon = 0.0
        center_lat = 0.0

    tile_id = _compute_geohash(center_lat, center_lon)
    now = datetime.utcnow()
    timestamp = now.isoformat() + "Z"

    # 過去の検出結果を DynamoDB から取得
    previous_detections = []
    previous_timestamp = None
    try:
        response = table.query(
            KeyConditionExpression=Key("tile_id").eq(tile_id),
            ScanIndexForward=False,  # 最新順
            Limit=1,
        )
        items = response.get("Items", [])
        if items:
            previous_timestamp = items[0]["timestamp"]
            previous_detections = items[0].get("detected_objects", [])
    except Exception as e:
        logger.warning("Failed to query previous detections: %s", e)

    # 変化面積計算
    diff_area_km2 = _compute_diff_area_km2(detections, previous_detections)
    change_detected = diff_area_km2 >= threshold

    # DynamoDB に現在の検出結果を保存
    from decimal import Decimal

    def _to_decimal(obj):
        """再帰的に float を Decimal に変換する（DynamoDB 互換）。"""
        if isinstance(obj, float):
            return Decimal(str(obj))
        if isinstance(obj, dict):
            return {k: _to_decimal(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_to_decimal(v) for v in obj]
        return obj

    ttl = int(time.time()) + ttl_seconds
    item = {
        "tile_id": tile_id,
        "timestamp": timestamp,
        "image_key": event.get("tile_key", ""),
        "detected_objects": _to_decimal(detections),
        "change_from_previous": {
            "previous_timestamp": previous_timestamp,
            "diff_area_km2": Decimal(str(round(diff_area_km2, 4))),
        },
        "ttl": ttl,
    }

    try:
        table.put_item(Item=item)
    except Exception as e:
        logger.error("Failed to write to DynamoDB: %s", e)
        raise

    logger.info(
        "UC15 Change Detection completed: tile_id=%s, change_detected=%s, diff_area=%.3fkm²",
        tile_id,
        change_detected,
        diff_area_km2,
    )

    # EMF メトリクス
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="change_detection")
    metrics.set_dimension("UseCase", "defense-satellite")
    metrics.put_metric("ChangeDetected", 1.0 if change_detected else 0.0, "Count")
    metrics.put_metric("DiffAreaKm2", float(diff_area_km2), "None")
    metrics.flush()

    return {
        "tile_id": tile_id,
        "timestamp": timestamp,
        "change_detected": change_detected,
        "diff_area_km2": float(diff_area_km2),
        "previous_timestamp": previous_timestamp,
        "detections": detections,
    }
