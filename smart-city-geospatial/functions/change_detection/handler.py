"""UC17 Smart City Change Detection Lambda.

時系列で土地利用分布を比較し、大きな変化（緑地減少、建物新築等）を検出する。

DynamoDB Schema:
    PK: area_id (タイル ID または geohash)
    SK: timestamp (ISO 8601)
    Attributes: landuse_distribution, previous_distribution, change_magnitude

Environment Variables:
    LANDUSE_HISTORY_TABLE: DynamoDB テーブル名
    CHANGE_THRESHOLD: 変化閾値（0-1, 分布差分、default 0.15）
    TTL_SECONDS: DynamoDB TTL (default 1 year)
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


def _derive_area_id(source_key: str) -> str:
    """ソースキーから area_id を導出する（パスを正規化）。"""
    import hashlib
    return hashlib.sha256(source_key.encode()).hexdigest()[:16]


def compute_change_magnitude(
    current: dict[str, float], previous: dict[str, float]
) -> float:
    """土地利用分布の L1 差分（変化量 0-2）を計算する。"""
    all_keys = set(current.keys()) | set(previous.keys())
    if not all_keys:
        return 0.0
    return sum(
        abs(current.get(k, 0.0) - previous.get(k, 0.0)) for k in all_keys
    )


def detect_dominant_change(
    current: dict[str, float], previous: dict[str, float]
) -> dict[str, Any]:
    """どの分類が最も変化したかを返す。"""
    all_keys = set(current.keys()) | set(previous.keys())
    changes = []
    for k in all_keys:
        delta = current.get(k, 0.0) - previous.get(k, 0.0)
        changes.append({"class": k, "delta": round(delta, 4)})
    changes.sort(key=lambda c: abs(c["delta"]), reverse=True)
    return {
        "dominant_class_changes": changes[:3],
        "max_increase": max(
            (c for c in changes if c["delta"] > 0), key=lambda c: c["delta"], default=None
        ),
        "max_decrease": min(
            (c for c in changes if c["delta"] < 0), key=lambda c: c["delta"], default=None
        ),
    }


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """UC17 Change Detection Lambda ハンドラ。

    Input: {"source_key": "...", "landuse_distribution": {...}}
    Output: {"area_id": str, "change_detected": bool, "change_magnitude": float, ...}
    """
    table_name = os.environ["LANDUSE_HISTORY_TABLE"]
    threshold = float(os.environ.get("CHANGE_THRESHOLD", "0.15"))
    ttl_seconds = int(os.environ.get("TTL_SECONDS", str(365 * 24 * 3600)))

    source_key = event.get("source_key", "")
    current_dist = event.get("landuse_distribution", {})

    if not source_key:
        raise ValueError("Input must contain 'source_key'")

    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)

    area_id = _derive_area_id(source_key)
    now = datetime.utcnow()
    timestamp = now.isoformat() + "Z"

    # 過去の分布取得
    previous_dist: dict[str, float] = {}
    previous_timestamp = None
    try:
        response = table.query(
            KeyConditionExpression=Key("area_id").eq(area_id),
            ScanIndexForward=False,
            Limit=1,
        )
        items = response.get("Items", [])
        if items:
            previous_timestamp = items[0]["timestamp"]
            # DynamoDB stores Decimal; convert
            raw = items[0].get("landuse_distribution", {})
            previous_dist = {k: float(v) for k, v in raw.items()}
    except Exception as e:
        logger.warning("Failed to query previous: %s", e)

    # 変化量計算
    magnitude = compute_change_magnitude(current_dist, previous_dist)
    change_detected = magnitude >= threshold
    dominant_change = detect_dominant_change(current_dist, previous_dist)

    # DynamoDB に現在の分布を保存
    from decimal import Decimal
    ttl = int(time.time()) + ttl_seconds
    item = {
        "area_id": area_id,
        "timestamp": timestamp,
        "source_key": source_key,
        "landuse_distribution": {
            k: Decimal(str(round(v, 4))) for k, v in current_dist.items()
        },
        "change_magnitude": Decimal(str(round(magnitude, 4))),
        "ttl": ttl,
    }
    try:
        table.put_item(Item=item)
    except Exception as e:
        logger.error("Failed to write to DynamoDB: %s", e)

    logger.info(
        "UC17 ChangeDetection: area=%s, magnitude=%.4f, detected=%s",
        area_id,
        magnitude,
        change_detected,
    )

    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="change_detection")
    metrics.set_dimension("UseCase", "smart-city-geospatial")
    metrics.put_metric("ChangeDetected", 1.0 if change_detected else 0.0, "Count")
    metrics.put_metric("ChangeMagnitude", float(magnitude), "None")
    metrics.flush()

    return {
        "area_id": area_id,
        "timestamp": timestamp,
        "source_key": source_key,
        "landuse_distribution": current_dist,
        "change_magnitude": float(magnitude),
        "change_detected": change_detected,
        "previous_timestamp": previous_timestamp,
        "dominant_change": dominant_change,
    }
