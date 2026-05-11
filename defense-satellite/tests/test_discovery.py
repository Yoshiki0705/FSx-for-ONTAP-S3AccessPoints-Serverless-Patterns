"""Unit tests for UC15 Discovery Lambda."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch



def test_classify_image_type_optical(discovery_handler):
    """Optical image extensions map to 'optical'."""
    _classify = discovery_handler._classify_image_type
    assert _classify("satellite/2026/05/image.tif") == "optical"
    assert _classify("satellite/image.TIFF") == "optical"
    assert _classify("data/image.ntf") == "optical"
    assert _classify("data/image.NITF") == "optical"


def test_classify_image_type_sar(discovery_handler):
    """SAR image extensions map to 'sar'."""
    _classify = discovery_handler._classify_image_type
    assert _classify("satellite/sar.hdf") == "sar"
    assert _classify("satellite/sar.h5") == "sar"
    assert _classify("satellite/sar.HDF") == "sar"


def test_classify_image_type_unknown(discovery_handler):
    """Unknown extensions map to 'unknown'."""
    _classify = discovery_handler._classify_image_type
    assert _classify("data/file.jpg") == "unknown"
    assert _classify("data/file.txt") == "unknown"
    assert _classify("data/noext") == "unknown"


def test_handler_filters_and_classifies(
    discovery_handler, lambda_context, monkeypatch
):
    """Handler lists objects, classifies them, and writes manifest."""
    monkeypatch.setenv("S3_ACCESS_POINT", "test-ap-ext-s3alias")
    monkeypatch.setenv("PREFIX_FILTER", "satellite/")
    monkeypatch.setenv("SUFFIX_FILTER", ".tif,.h5")

    mock_objects_tif = [
        {
            "Key": "satellite/2026/05/image1.tif",
            "Size": 1024,
            "LastModified": datetime(2026, 5, 10),
            "ETag": '"etag1"',
        },
    ]
    mock_objects_h5 = [
        {
            "Key": "satellite/2026/05/sar1.h5",
            "Size": 2048,
            "LastModified": datetime(2026, 5, 10),
            "ETag": '"etag2"',
        },
    ]

    mock_s3ap = MagicMock()
    mock_s3ap.list_objects.side_effect = [mock_objects_tif, mock_objects_h5]
    mock_s3ap_output = MagicMock()

    with patch.object(discovery_handler, "S3ApHelper", side_effect=[mock_s3ap, mock_s3ap_output]):
        result = discovery_handler.handler({}, lambda_context)

    assert result["total_objects"] == 2
    assert result["image_types"]["optical"] == 1
    assert result["image_types"]["sar"] == 1
    mock_s3ap_output.put_object.assert_called_once()


def test_handler_deduplicates_keys(
    discovery_handler, lambda_context, monkeypatch
):
    """Handler deduplicates keys that match multiple suffixes."""
    monkeypatch.setenv("S3_ACCESS_POINT", "test-ap-ext-s3alias")
    monkeypatch.setenv("SUFFIX_FILTER", ".tif,.tiff")

    same_obj = {
        "Key": "satellite/same.tif",
        "Size": 1024,
        "LastModified": datetime(2026, 5, 10),
        "ETag": '"e1"',
    }
    mock_s3ap = MagicMock()
    mock_s3ap.list_objects.side_effect = [[same_obj], []]
    mock_s3ap_output = MagicMock()

    with patch.object(discovery_handler, "S3ApHelper", side_effect=[mock_s3ap, mock_s3ap_output]):
        result = discovery_handler.handler({}, lambda_context)

    # .tif と .tiff の両方でマッチしても重複排除される
    assert result["total_objects"] == 1


def test_handler_empty_results(
    discovery_handler, lambda_context, monkeypatch
):
    """Handler handles empty results gracefully."""
    monkeypatch.setenv("S3_ACCESS_POINT", "test-ap-ext-s3alias")
    monkeypatch.setenv("SUFFIX_FILTER", ".tif")

    mock_s3ap = MagicMock()
    mock_s3ap.list_objects.return_value = []
    mock_s3ap_output = MagicMock()

    with patch.object(discovery_handler, "S3ApHelper", side_effect=[mock_s3ap, mock_s3ap_output]):
        result = discovery_handler.handler({}, lambda_context)

    assert result["total_objects"] == 0
    assert sum(result["image_types"].values()) == 0
