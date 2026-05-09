"""UC17 Smart City Geospatial Discovery Lambda.

FSx ONTAP S3 Access Point から GIS データ（GeoTIFF/Shapefile/GeoJSON/LAS/GeoPackage）の
一覧を取得し、Manifest JSON を生成・S3 に書き出す。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN
    S3_ACCESS_POINT_OUTPUT: 出力用 S3 AP (default: S3_ACCESS_POINT)
    PREFIX_FILTER: プレフィックスフィルタ (default: "gis/")
    SUFFIX_FILTER: サフィックスフィルタ
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime

from shared.exceptions import lambda_error_handler
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = frozenset({
    ".tif", ".tiff", ".shp", ".geojson", ".json",
    ".las", ".laz", ".gpkg",
})


def _classify_geo_format(key: str) -> str:
    """ファイル拡張子からジオデータ形式を分類する。"""
    lower = key.lower()
    if lower.endswith((".tif", ".tiff")):
        return "raster"
    if lower.endswith(".shp"):
        return "vector_shapefile"
    if lower.endswith((".geojson", ".json")):
        return "vector_geojson"
    if lower.endswith((".las", ".laz")):
        return "pointcloud"
    if lower.endswith(".gpkg"):
        return "geopackage"
    return "unknown"


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """UC17 Discovery Lambda ハンドラ。"""
    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    s3ap_output = S3ApHelper(
        os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ["S3_ACCESS_POINT"])
    )
    prefix = os.environ.get("PREFIX_FILTER", "gis/")
    suffix_filter = os.environ.get(
        "SUFFIX_FILTER", ",".join(sorted(SUPPORTED_FORMATS))
    )

    logger.info(
        "UC17 Discovery started: ap=%s, prefix=%r",
        os.environ["S3_ACCESS_POINT"],
        prefix,
    )

    with xray_subsegment(
        name="s3ap_list_objects",
        annotations={
            "service_name": "s3",
            "operation": "ListObjectsV2",
            "use_case": "smart-city-geospatial",
        },
    ):
        all_objects = []
        for single_suffix in suffix_filter.split(","):
            single_suffix = single_suffix.strip()
            if single_suffix:
                all_objects.extend(
                    s3ap.list_objects(prefix=prefix, suffix=single_suffix)
                )

    seen_keys = set()
    objects = []
    geo_types = {
        "raster": 0, "vector_shapefile": 0, "vector_geojson": 0,
        "pointcloud": 0, "geopackage": 0, "unknown": 0,
    }
    for obj in all_objects:
        if obj["Key"] not in seen_keys:
            seen_keys.add(obj["Key"])
            obj["GeoFormat"] = _classify_geo_format(obj["Key"])
            geo_types[obj["GeoFormat"]] += 1
            objects.append(obj)

    manifest = {
        "execution_id": context.aws_request_id,
        "timestamp": datetime.utcnow().isoformat(),
        "total_objects": len(objects),
        "objects": objects,
        "geo_formats": geo_types,
    }

    manifest_key = (
        f"manifests/{datetime.utcnow().strftime('%Y/%m/%d')}"
        f"/{context.aws_request_id}.json"
    )
    s3ap_output.put_object(
        key=manifest_key,
        body=json.dumps(manifest, default=str),
        content_type="application/json",
    )

    logger.info(
        "UC17 Discovery completed: total=%d, raster=%d, vector=%d, pointcloud=%d",
        len(objects),
        geo_types["raster"],
        geo_types["vector_shapefile"] + geo_types["vector_geojson"],
        geo_types["pointcloud"],
    )

    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="discovery")
    metrics.set_dimension("UseCase", "smart-city-geospatial")
    metrics.put_metric("FilesProcessed", float(len(objects)), "Count")
    metrics.flush()

    return {
        "manifest_key": manifest_key,
        "total_objects": len(objects),
        "objects": objects,
        "geo_formats": geo_types,
    }
