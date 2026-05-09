"""Unit tests for UC17 Discovery Lambda."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch


def test_classify_geo_format_raster(discovery_handler):
    assert discovery_handler._classify_geo_format("gis/area.tif") == "raster"
    assert discovery_handler._classify_geo_format("gis/area.TIFF") == "raster"


def test_classify_geo_format_vector(discovery_handler):
    assert discovery_handler._classify_geo_format("gis/parcels.shp") == "vector_shapefile"
    assert discovery_handler._classify_geo_format("gis/roads.geojson") == "vector_geojson"


def test_classify_geo_format_pointcloud(discovery_handler):
    assert discovery_handler._classify_geo_format("gis/city.las") == "pointcloud"
    assert discovery_handler._classify_geo_format("gis/city.LAZ") == "pointcloud"


def test_classify_geo_format_geopackage(discovery_handler):
    assert discovery_handler._classify_geo_format("gis/db.gpkg") == "geopackage"


def test_classify_geo_format_unknown(discovery_handler):
    assert discovery_handler._classify_geo_format("gis/random.pdf") == "unknown"


def test_handler_filters_and_counts(
    discovery_handler, lambda_context, monkeypatch
):
    monkeypatch.setenv("S3_ACCESS_POINT", "test-ap-ext-s3alias")
    monkeypatch.setenv("PREFIX_FILTER", "gis/")
    monkeypatch.setenv("SUFFIX_FILTER", ".tif,.las")

    tif_objs = [{"Key": "gis/a.tif", "Size": 100, "LastModified": datetime(2026, 5, 10), "ETag": '"e1"'}]
    las_objs = [{"Key": "gis/b.las", "Size": 200, "LastModified": datetime(2026, 5, 10), "ETag": '"e2"'}]

    mock_s3ap = MagicMock()
    mock_s3ap.list_objects.side_effect = [tif_objs, las_objs]

    with patch.object(discovery_handler, "S3ApHelper", side_effect=[mock_s3ap, mock_s3ap]):
        result = discovery_handler.handler({}, lambda_context)

    assert result["total_objects"] == 2
    assert result["geo_formats"]["raster"] == 1
    assert result["geo_formats"]["pointcloud"] == 1
