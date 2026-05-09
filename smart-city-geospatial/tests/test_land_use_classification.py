"""Unit tests for UC17 Land Use Classification Lambda."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_map_labels_to_landuse_empty(land_use_classification_handler):
    result = land_use_classification_handler.map_labels_to_landuse([])
    assert result == {}


def test_map_labels_to_landuse_buildings(land_use_classification_handler):
    labels = [
        {"Name": "Building", "Confidence": 90.0},
        {"Name": "House", "Confidence": 80.0},
    ]
    result = land_use_classification_handler.map_labels_to_landuse(labels)
    assert "residential" in result
    # Normalized to sum ~1.0
    total = sum(result.values())
    assert abs(total - 1.0) < 0.001


def test_map_labels_to_landuse_mixed(land_use_classification_handler):
    labels = [
        {"Name": "Building", "Confidence": 80.0},
        {"Name": "Forest", "Confidence": 60.0},
        {"Name": "Road", "Confidence": 40.0},
    ]
    result = land_use_classification_handler.map_labels_to_landuse(labels)
    assert "residential" in result
    assert "forest" in result
    assert "road" in result
    assert abs(sum(result.values()) - 1.0) < 0.001


def test_map_labels_to_landuse_unknown_labels_ignored(land_use_classification_handler):
    labels = [
        {"Name": "Sky", "Confidence": 90.0},  # no mapping
        {"Name": "Building", "Confidence": 80.0},
    ]
    result = land_use_classification_handler.map_labels_to_landuse(labels)
    assert "residential" in result
    # Only mapped labels contribute
    assert len(result) == 1


def test_handler_skips_non_raster(
    land_use_classification_handler, lambda_context, monkeypatch
):
    monkeypatch.setenv("OUTPUT_BUCKET", "test-bucket")
    monkeypatch.setenv("INFERENCE_TYPE", "none")

    mock_s3_client = MagicMock()
    mock_s3_client.get_object.return_value = {"Body": MagicMock(read=lambda: b"data")}
    with patch.object(land_use_classification_handler, "boto3") as mock_boto3:
        mock_boto3.client.return_value = mock_s3_client
        event = {"source_key": "gis/roads.shp"}
        result = land_use_classification_handler.handler(event, lambda_context)

    assert result["skipped"] is True
    assert result["inference_path"] == "skipped"


def test_handler_uses_rekognition_for_raster(
    land_use_classification_handler, lambda_context, monkeypatch
):
    monkeypatch.setenv("OUTPUT_BUCKET", "test-bucket")
    monkeypatch.setenv("INFERENCE_TYPE", "none")

    mock_s3_client = MagicMock()
    mock_s3_client.get_object.return_value = {
        "Body": MagicMock(read=lambda: b"II*\x00" + b"\x00" * 100)
    }
    mock_rekognition = MagicMock()
    mock_rekognition.detect_labels.return_value = {
        "Labels": [{"Name": "Building", "Confidence": 85.0}]
    }

    def boto3_client(service):
        if service == "s3":
            return mock_s3_client
        if service == "rekognition":
            return mock_rekognition
        return MagicMock()

    with patch.object(land_use_classification_handler, "boto3") as mock_boto3:
        mock_boto3.client.side_effect = boto3_client
        event = {"source_key": "gis/area.tif"}
        result = land_use_classification_handler.handler(event, lambda_context)

    assert result["inference_path"] == "rekognition"
    assert "residential" in result["landuse_distribution"]
