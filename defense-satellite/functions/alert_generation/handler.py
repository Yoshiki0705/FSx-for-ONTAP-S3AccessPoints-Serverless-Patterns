"""UC15 Defense/Space Alert Generation Lambda

変化検出結果が閾値を超えた場合に SNS でアラートを発行する。

Environment Variables:
    SNS_TOPIC_ARN: 通知先 SNS Topic ARN
    CHANGE_AREA_THRESHOLD_KM2: 変化面積閾値 km² (default: 1.0)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)


def _build_alert_message(
    tile_id: str,
    timestamp: str,
    diff_area_km2: float,
    enrichment: dict[str, Any],
    detections: list[dict],
) -> dict[str, Any]:
    """アラートメッセージを構築する。

    Args:
        tile_id: geohash
        timestamp: 検出時刻
        diff_area_km2: 変化面積
        enrichment: geo enrichment 情報
        detections: 検出結果

    Returns:
        dict: SNS メッセージ
    """
    top_labels = sorted(
        {d.get("label", "unknown") for d in detections}
    )[:10]

    return {
        "alert_type": "SATELLITE_CHANGE_DETECTED",
        "severity": "HIGH" if diff_area_km2 >= 10.0 else "MEDIUM",
        "tile_id": tile_id,
        "timestamp": timestamp,
        "diff_area_km2": round(diff_area_km2, 3),
        "center_coordinates": enrichment.get("center_coordinates", {}),
        "sensor_type": enrichment.get("sensor_type", "unknown"),
        "acquisition_date": enrichment.get("acquisition_date"),
        "detected_labels": top_labels,
        "detection_count": len(detections),
    }


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """UC15 Alert Generation Lambda ハンドラ。

    Input:
        {
            "tile_id": geohash,
            "timestamp": ISO 8601,
            "change_detected": bool,
            "diff_area_km2": float,
            "enrichment": {...},
            "enriched_detections": [...]
        }

    Output:
        {
            "alert_sent": bool,
            "message_id": str | null,
            "alert_summary": {...} | null
        }
    """
    topic_arn = os.environ["SNS_TOPIC_ARN"]
    threshold = float(os.environ.get("CHANGE_AREA_THRESHOLD_KM2", "1.0"))

    change_detected = event.get("change_detected", False)
    diff_area_km2 = float(event.get("diff_area_km2", 0.0))

    if not change_detected or diff_area_km2 < threshold:
        logger.info(
            "No alert: change_detected=%s, diff_area=%.3fkm² < %.3fkm²",
            change_detected,
            diff_area_km2,
            threshold,
        )
        return {
            "alert_sent": False,
            "message_id": None,
            "alert_summary": None,
        }

    tile_id = event.get("tile_id", "unknown")
    timestamp = event.get("timestamp", "unknown")
    enrichment = event.get("enrichment", {})
    detections = event.get("enriched_detections", event.get("detections", []))

    alert_message = _build_alert_message(
        tile_id, timestamp, diff_area_km2, enrichment, detections
    )

    sns = boto3.client("sns")
    response = sns.publish(
        TopicArn=topic_arn,
        Subject=f"[UC15 Alert] Satellite Change Detected at {tile_id}",
        Message=json.dumps(alert_message, indent=2, default=str),
        MessageAttributes={
            "severity": {
                "DataType": "String",
                "StringValue": alert_message["severity"],
            },
            "alert_type": {
                "DataType": "String",
                "StringValue": alert_message["alert_type"],
            },
        },
    )

    message_id = response.get("MessageId", "")
    logger.info(
        "UC15 Alert sent: tile_id=%s, message_id=%s, severity=%s",
        tile_id,
        message_id,
        alert_message["severity"],
    )

    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="alert_generation")
    metrics.set_dimension("UseCase", "defense-satellite")
    metrics.set_dimension("Severity", alert_message["severity"])
    metrics.put_metric("AlertSent", 1.0, "Count")
    metrics.put_metric("DiffAreaKm2", diff_area_km2, "None")
    metrics.flush()

    return {
        "alert_sent": True,
        "message_id": message_id,
        "alert_summary": alert_message,
    }
