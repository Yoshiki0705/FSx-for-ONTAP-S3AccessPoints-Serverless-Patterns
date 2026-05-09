"""Unit tests for UC15 Object Detection Lambda."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_detect_with_rekognition_returns_labels(object_detection_handler):
    """Rekognition detection returns structured label list."""
    mock_rekognition = MagicMock()
    mock_rekognition.detect_labels.return_value = {
        "Labels": [
            {
                "Name": "Vehicle",
                "Confidence": 95.5,
                "Instances": [
                    {
                        "Confidence": 92.0,
                        "BoundingBox": {
                            "Width": 0.1,
                            "Height": 0.15,
                            "Left": 0.5,
                            "Top": 0.3,
                        },
                    }
                ],
            },
            {
                "Name": "Building",
                "Confidence": 88.0,
                "Instances": [],
            },
        ]
    }

    with patch.object(object_detection_handler, "boto3") as mock_boto3:
        mock_boto3.client.return_value = mock_rekognition
        results = object_detection_handler._detect_with_rekognition(
            b"image-bytes", min_confidence=70.0, max_labels=100
        )

    assert len(results) == 2
    assert any(r["label"] == "Vehicle" for r in results)
    assert any(r["label"] == "Building" for r in results)
    vehicle = next(r for r in results if r["label"] == "Vehicle")
    assert "bbox" in vehicle
    assert vehicle["bbox"]["Width"] == 0.1


def test_detect_with_sagemaker_parses_json(object_detection_handler):
    """SageMaker detection parses JSON response."""
    mock_runtime = MagicMock()
    mock_runtime.invoke_endpoint.return_value = {
        "Body": MagicMock(
            read=lambda: b'[{"label": "airplane", "confidence": 0.9}]'
        ),
    }

    with patch.object(object_detection_handler, "boto3") as mock_boto3:
        mock_boto3.client.return_value = mock_runtime
        results = object_detection_handler._detect_with_sagemaker(
            "test-endpoint", b"image-bytes"
        )

    assert len(results) == 1
    assert results[0]["label"] == "airplane"


def test_detect_with_sagemaker_handles_invalid_json(object_detection_handler):
    """SageMaker detection handles non-JSON response gracefully."""
    mock_runtime = MagicMock()
    mock_runtime.invoke_endpoint.return_value = {
        "Body": MagicMock(read=lambda: b"not-json"),
    }

    with patch.object(object_detection_handler, "boto3") as mock_boto3:
        mock_boto3.client.return_value = mock_runtime
        results = object_detection_handler._detect_with_sagemaker(
            "test-endpoint", b"image-bytes"
        )

    assert results == []


def test_handler_routes_to_rekognition_for_small_images(
    object_detection_handler, lambda_context, monkeypatch
):
    """Handler uses Rekognition for images below payload limit."""
    monkeypatch.setenv("OUTPUT_BUCKET", "test-bucket")
    monkeypatch.setenv("INFERENCE_TYPE", "none")

    small_image = b"II*\x00" + b"\x00" * 100  # < 5 MB

    mock_s3_client = MagicMock()
    mock_s3_client.get_object.return_value = {
        "Body": MagicMock(read=lambda: small_image),
    }
    mock_rekognition = MagicMock()
    mock_rekognition.detect_labels.return_value = {
        "Labels": [{"Name": "Ship", "Confidence": 85.0, "Instances": []}]
    }

    def boto3_client(service):
        if service == "s3":
            return mock_s3_client
        if service == "rekognition":
            return mock_rekognition
        return MagicMock()

    with patch.object(object_detection_handler, "boto3") as mock_boto3:
        mock_boto3.client.side_effect = boto3_client
        event = {"tile_key": "tiles/test.tif"}
        result = object_detection_handler.handler(event, lambda_context)

    assert result["inference_path"] == "rekognition"
    assert result["detection_count"] >= 1


def test_handler_requires_tile_key(
    object_detection_handler, lambda_context, monkeypatch
):
    """Handler raises ValueError when tile_key missing."""
    monkeypatch.setenv("OUTPUT_BUCKET", "test-bucket")

    result = object_detection_handler.handler({}, lambda_context)
    assert result["statusCode"] >= 500
