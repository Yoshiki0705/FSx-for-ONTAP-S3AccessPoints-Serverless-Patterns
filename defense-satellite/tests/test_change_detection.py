"""Unit tests for UC15 Change Detection Lambda."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_compute_geohash_precision(change_detection_handler):
    """geohash length equals precision."""
    gh = change_detection_handler._compute_geohash(35.6895, 139.6917, precision=5)
    assert len(gh) == 5
    gh7 = change_detection_handler._compute_geohash(35.6895, 139.6917, precision=7)
    assert len(gh7) == 7


def test_compute_geohash_determinism(change_detection_handler):
    """Same coordinates produce same geohash."""
    a = change_detection_handler._compute_geohash(35.0, 139.0)
    b = change_detection_handler._compute_geohash(35.0, 139.0)
    assert a == b


def test_compute_geohash_different_locations(change_detection_handler):
    """Different coordinates produce different geohash."""
    tokyo = change_detection_handler._compute_geohash(35.6895, 139.6917)
    ny = change_detection_handler._compute_geohash(40.7128, -74.0060)
    assert tokyo != ny


def test_compute_diff_area_zero_for_identical(change_detection_handler):
    """Identical detection sets produce zero diff area."""
    detections = [
        {"label": "Vehicle", "bbox": {"Width": 0.1, "Height": 0.1}},
    ]
    diff = change_detection_handler._compute_diff_area_km2(detections, detections)
    assert diff == 0.0


def test_compute_diff_area_non_zero_for_different(change_detection_handler):
    """Different detection sets produce non-zero diff area."""
    current = [{"label": "Vehicle", "bbox": {"Width": 0.1, "Height": 0.1}}]
    previous = [{"label": "Vehicle", "bbox": {"Width": 0.2, "Height": 0.2}}]
    diff = change_detection_handler._compute_diff_area_km2(current, previous)
    assert diff > 0


def test_compute_diff_area_empty_bbox(change_detection_handler):
    """Detections without bbox contribute zero area."""
    detections = [{"label": "Unknown", "bbox": {}}]
    diff = change_detection_handler._compute_diff_area_km2(detections, detections)
    assert diff == 0.0


def test_handler_writes_to_dynamodb(
    change_detection_handler, lambda_context, monkeypatch
):
    """Handler writes current detection to DynamoDB."""
    monkeypatch.setenv("CHANGE_HISTORY_TABLE", "test-table")
    monkeypatch.setenv("OUTPUT_BUCKET", "test-bucket")
    monkeypatch.setenv("CHANGE_AREA_THRESHOLD_KM2", "0.5")

    mock_table = MagicMock()
    mock_table.query.return_value = {"Items": []}
    mock_resource = MagicMock()
    mock_resource.Table.return_value = mock_table

    with patch.object(change_detection_handler, "boto3") as mock_boto3:
        mock_boto3.resource.return_value = mock_resource
        event = {
            "tile_key": "tiles/test.tif",
            "detections": [
                {"label": "Vehicle", "bbox": {"Width": 0.1, "Height": 0.1}}
            ],
            "image_metadata": {"bounds": [139.0, 35.0, 140.0, 36.0]},
        }
        result = change_detection_handler.handler(event, lambda_context)

    assert "tile_id" in result
    assert result["timestamp"]
    mock_table.put_item.assert_called_once()


def test_handler_detects_no_change_for_first_detection(
    change_detection_handler, lambda_context, monkeypatch
):
    """First-time detection has no previous, so change_detected depends on threshold."""
    monkeypatch.setenv("CHANGE_HISTORY_TABLE", "test-table")
    monkeypatch.setenv("OUTPUT_BUCKET", "test-bucket")
    monkeypatch.setenv("CHANGE_AREA_THRESHOLD_KM2", "100.0")  # high threshold

    mock_table = MagicMock()
    mock_table.query.return_value = {"Items": []}
    mock_resource = MagicMock()
    mock_resource.Table.return_value = mock_table

    with patch.object(change_detection_handler, "boto3") as mock_boto3:
        mock_boto3.resource.return_value = mock_resource
        event = {
            "tile_key": "tiles/test.tif",
            "detections": [{"label": "X", "bbox": {"Width": 0.01, "Height": 0.01}}],
            "image_metadata": {"bounds": [139.0, 35.0, 140.0, 36.0]},
        }
        result = change_detection_handler.handler(event, lambda_context)

    # High threshold → no change alert
    assert result["change_detected"] is False
    assert result["previous_timestamp"] is None
