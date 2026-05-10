"""Unit tests for UC17 Preprocessing Lambda (CRS normalization)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from hypothesis import HealthCheck, given, settings, strategies as st


def test_detect_source_crs_from_filename(preprocessing_handler):
    assert preprocessing_handler.detect_source_crs(
        "gis/tokyo_epsg32654.tif", {}
    ) == "EPSG:32654"


def test_detect_source_crs_from_metadata(preprocessing_handler):
    assert preprocessing_handler.detect_source_crs(
        "gis/file.tif", {"crs": "EPSG:3857"}
    ) == "EPSG:3857"


def test_detect_source_crs_default(preprocessing_handler):
    assert preprocessing_handler.detect_source_crs("gis/file.tif", {}) == "EPSG:4326"


def test_normalize_crs_identity(preprocessing_handler):
    """Same CRS returns coords unchanged."""
    coords = [(139.0, 35.0), (140.0, 36.0)]
    result = preprocessing_handler.normalize_crs("EPSG:4326", "EPSG:4326", coords)
    assert result == coords


def test_normalize_crs_no_pyproj_fallback(preprocessing_handler):
    """Without pyproj, coords returned unchanged."""
    coords = [(139.0, 35.0)]
    with patch.object(preprocessing_handler, "PYPROJ_AVAILABLE", False):
        result = preprocessing_handler.normalize_crs("EPSG:32654", "EPSG:4326", coords)
    assert result == coords


@given(
    lon=st.floats(min_value=-180.0, max_value=180.0, allow_nan=False),
    lat=st.floats(min_value=-85.0, max_value=85.0, allow_nan=False),
)
@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_normalize_crs_roundtrip_identity(preprocessing_handler, lon, lat):
    """Identity CRS transform is stable (Property test)."""
    result = preprocessing_handler.normalize_crs(
        "EPSG:4326", "EPSG:4326", [(lon, lat)]
    )
    assert result == [(lon, lat)]


def test_handler_records_metadata(preprocessing_handler, lambda_context, monkeypatch):
    monkeypatch.setenv("OUTPUT_BUCKET", "test-bucket")
    monkeypatch.setenv("TARGET_CRS", "EPSG:4326")

    mock_writer = MagicMock()

    with patch.object(
        preprocessing_handler, "OutputWriter"
    ) as mock_output_writer_cls:
        mock_output_writer_cls.from_env.return_value = mock_writer
        event = {
            "Key": "gis/area_epsg32654.tif",
            "GeoFormat": "raster",
        }
        result = preprocessing_handler.handler(event, lambda_context)

    assert result["source_key"] == "gis/area_epsg32654.tif"
    assert result["source_crs"] == "EPSG:32654"
    assert result["target_crs"] == "EPSG:4326"
    mock_writer.put_json.assert_called_once()
