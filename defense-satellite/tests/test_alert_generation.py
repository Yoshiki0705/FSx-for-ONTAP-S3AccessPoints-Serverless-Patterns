"""Unit tests for UC15 Alert Generation Lambda."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_build_alert_message_high_severity(alert_generation_handler):
    """Large diff area produces HIGH severity alert."""
    msg = alert_generation_handler._build_alert_message(
        tile_id="xyz12",
        timestamp="2026-05-10T12:00:00Z",
        diff_area_km2=25.0,
        enrichment={
            "center_coordinates": {"lat": 35.0, "lon": 139.0},
            "sensor_type": "optical",
            "acquisition_date": "2026-05-10T00:00:00",
        },
        detections=[{"label": "Vehicle"}, {"label": "Ship"}],
    )
    assert msg["severity"] == "HIGH"
    assert msg["alert_type"] == "SATELLITE_CHANGE_DETECTED"
    assert msg["tile_id"] == "xyz12"


def test_build_alert_message_medium_severity(alert_generation_handler):
    """Medium diff area produces MEDIUM severity alert."""
    msg = alert_generation_handler._build_alert_message(
        tile_id="abc12",
        timestamp="2026-05-10T12:00:00Z",
        diff_area_km2=2.0,
        enrichment={"center_coordinates": {}, "sensor_type": "sar"},
        detections=[{"label": "Building"}],
    )
    assert msg["severity"] == "MEDIUM"


def test_build_alert_message_deduplicates_labels(alert_generation_handler):
    """Duplicate labels are collected as unique set."""
    msg = alert_generation_handler._build_alert_message(
        tile_id="x",
        timestamp="t",
        diff_area_km2=1.0,
        enrichment={},
        detections=[
            {"label": "Vehicle"},
            {"label": "Vehicle"},
            {"label": "Ship"},
        ],
    )
    labels = msg["detected_labels"]
    assert set(labels) == {"Vehicle", "Ship"}


def test_handler_skips_alert_below_threshold(
    alert_generation_handler, lambda_context, monkeypatch
):
    """Handler does not send alert when change_detected is False."""
    monkeypatch.setenv("SNS_TOPIC_ARN", "arn:aws:sns:us-east-1:123:test")

    event = {
        "change_detected": False,
        "diff_area_km2": 0.1,
    }
    result = alert_generation_handler.handler(event, lambda_context)

    assert result["alert_sent"] is False
    assert result["message_id"] is None


def test_handler_sends_alert_above_threshold(
    alert_generation_handler, lambda_context, monkeypatch
):
    """Handler sends SNS alert when threshold exceeded."""
    monkeypatch.setenv("SNS_TOPIC_ARN", "arn:aws:sns:us-east-1:123:test")
    monkeypatch.setenv("CHANGE_AREA_THRESHOLD_KM2", "1.0")

    mock_sns = MagicMock()
    mock_sns.publish.return_value = {"MessageId": "msg-abc-123"}

    with patch.object(alert_generation_handler, "boto3") as mock_boto3:
        mock_boto3.client.return_value = mock_sns
        event = {
            "change_detected": True,
            "diff_area_km2": 2.5,
            "tile_id": "xyz12",
            "timestamp": "2026-05-10T12:00:00Z",
            "enrichment": {
                "center_coordinates": {"lat": 35.0, "lon": 139.0},
                "sensor_type": "optical",
            },
            "enriched_detections": [{"label": "Vehicle"}],
        }
        result = alert_generation_handler.handler(event, lambda_context)

    assert result["alert_sent"] is True
    assert result["message_id"] == "msg-abc-123"
    mock_sns.publish.assert_called_once()
