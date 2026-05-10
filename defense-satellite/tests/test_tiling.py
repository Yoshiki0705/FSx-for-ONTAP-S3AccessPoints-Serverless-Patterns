"""Unit tests for UC15 Tiling Lambda."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_compute_tile_count_exact(tiling_handler):
    """Tile count for image exactly divisible by tile size."""
    assert tiling_handler._compute_tile_count(256, 256, 256) == 1
    assert tiling_handler._compute_tile_count(512, 512, 256) == 4
    assert tiling_handler._compute_tile_count(1024, 512, 256) == 8


def test_compute_tile_count_with_remainder(tiling_handler):
    """Tile count includes partial tiles at edges."""
    assert tiling_handler._compute_tile_count(257, 257, 256) == 4
    assert tiling_handler._compute_tile_count(300, 200, 256) == 2


def test_compute_tile_count_zero_dimension(tiling_handler):
    """Zero dimension produces zero tiles."""
    assert tiling_handler._compute_tile_count(0, 100, 256) == 0
    assert tiling_handler._compute_tile_count(100, 0, 256) == 0


def test_extract_image_dimensions_fallback_tiff_magic(tiling_handler):
    """Fallback recognizes TIFF magic number (II / MM)."""
    # Little-endian TIFF header (II = Intel)
    ii_header = b"II*\x00" + b"\x00" * 100
    dims = tiling_handler._extract_image_dimensions_fallback(ii_header)
    assert dims["width"] > 0

    # Big-endian TIFF header (MM = Motorola)
    mm_header = b"MM\x00*" + b"\x00" * 100
    dims = tiling_handler._extract_image_dimensions_fallback(mm_header)
    assert dims["width"] > 0


def test_extract_image_dimensions_fallback_non_tiff(tiling_handler):
    """Fallback returns zero dimensions for non-TIFF data."""
    dims = tiling_handler._extract_image_dimensions_fallback(b"NOT A TIFF")
    assert dims["width"] == 0
    assert dims["height"] == 0


def test_handler_missing_key_raises(tiling_handler, lambda_context, monkeypatch):
    """Handler raises ValueError when 'Key' is missing in event."""
    monkeypatch.setenv("OUTPUT_BUCKET", "test-bucket")

    result = tiling_handler.handler({}, lambda_context)
    # lambda_error_handler wraps ValueError to a 5xx response
    assert result["statusCode"] >= 500


def test_handler_uses_fallback_when_rasterio_unavailable(
    tiling_handler, lambda_context, monkeypatch
):
    """Handler falls back to simple metadata when rasterio is unavailable."""
    monkeypatch.setenv("OUTPUT_BUCKET", "test-bucket")
    monkeypatch.setenv("TILE_SIZE", "256")

    mock_s3_client = MagicMock()
    mock_s3_client.get_object.return_value = {
        "Body": MagicMock(read=lambda: b"II*\x00" + b"\x00" * 100),
    }

    mock_writer = MagicMock()
    mock_writer.target_description = "Standard S3 bucket 'test-bucket'"
    mock_writer.build_s3_uri.return_value = "s3://test-bucket/out.json"

    with patch.object(tiling_handler, "boto3") as mock_boto3, patch.object(
        tiling_handler, "OutputWriter"
    ) as mock_output_writer_cls:
        mock_boto3.client.return_value = mock_s3_client
        mock_output_writer_cls.from_env.return_value = mock_writer
        with patch.object(tiling_handler, "RASTERIO_AVAILABLE", False):
            event = {"Key": "satellite/test.tif", "Size": 1000}
            result = tiling_handler.handler(event, lambda_context)

    assert result["source_key"] == "satellite/test.tif"
    assert "tile_count" in result
    assert "metadata" in result
    mock_writer.put_json.assert_called_once()
