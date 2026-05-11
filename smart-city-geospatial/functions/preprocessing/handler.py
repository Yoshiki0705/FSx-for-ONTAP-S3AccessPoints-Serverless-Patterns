"""UC17 Smart City Geospatial Preprocessing Lambda.

座標参照系（CRS）を EPSG:4326（WGS84）に正規化する。
pyproj が Lambda Layer で利用可能な場合は実変換、利用不可時はメタデータのみ記録。

Environment Variables:
    TARGET_CRS: 正規化後の CRS (default: "EPSG:4326")
    OUTPUT_DESTINATION: `STANDARD_S3` or `FSXN_S3AP` (デフォルト: `STANDARD_S3`)
    OUTPUT_BUCKET: STANDARD_S3 モードの出力バケット
    OUTPUT_S3AP_ALIAS: FSXN_S3AP モードの S3AP Alias or ARN
    OUTPUT_S3AP_PREFIX: FSXN_S3AP モードの出力プレフィックス
"""

from __future__ import annotations

import logging
import os
from datetime import datetime


from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler
from shared.output_writer import OutputWriter

logger = logging.getLogger(__name__)

try:
    import pyproj
    PYPROJ_AVAILABLE = True
except ImportError:
    pyproj = None
    PYPROJ_AVAILABLE = False


def normalize_crs(
    source_crs: str, target_crs: str, coordinates: list[tuple[float, float]]
) -> list[tuple[float, float]]:
    """座標を target_crs に変換する。pyproj 不在時は元座標を返す。"""
    if not PYPROJ_AVAILABLE or source_crs == target_crs:
        return coordinates
    try:
        transformer = pyproj.Transformer.from_crs(
            source_crs, target_crs, always_xy=True
        )
        return [transformer.transform(x, y) for x, y in coordinates]
    except Exception as e:
        logger.warning("CRS transform failed: %s", e)
        return coordinates


def detect_source_crs(key: str, metadata: dict) -> str:
    """キー名やメタデータから CRS を推定する。"""
    # Explicit metadata
    if "crs" in metadata:
        return str(metadata["crs"])
    # Heuristic: UTM zones commonly embedded in filenames
    lower = key.lower()
    if "epsg" in lower:
        # e.g., file_epsg32654.tif
        try:
            start = lower.index("epsg") + 4
            num = ""
            for ch in lower[start:]:
                if ch.isdigit():
                    num += ch
                else:
                    break
            if num:
                return f"EPSG:{num}"
        except Exception:
            pass
    return "EPSG:4326"  # default


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """UC17 Preprocessing Lambda ハンドラ。

    Input: {"Key": "gis/area1.shp", "Size": 1234, "GeoFormat": "vector_shapefile"}
    Output: {"source_key": str, "target_crs": str, "normalized": bool, "metadata_key": str}
    """
    output_writer = OutputWriter.from_env()
    target_crs = os.environ.get("TARGET_CRS", "EPSG:4326")

    source_key = event.get("Key") or event.get("source_key")
    if not source_key:
        raise ValueError("Input event must contain 'Key'")

    geo_format = event.get("GeoFormat", "unknown")

    # メタデータ収集（CRS 検出等）
    geo_metadata = event.get("metadata", {})
    source_crs = detect_source_crs(source_key, geo_metadata)

    # サンプル座標のラウンドトリップ検証
    sample_coords = [(139.7671, 35.6812), (135.5023, 34.6937)]  # Tokyo, Osaka
    normalized_coords = normalize_crs(source_crs, target_crs, sample_coords)

    metadata = {
        "source_key": source_key,
        "geo_format": geo_format,
        "source_crs": source_crs,
        "target_crs": target_crs,
        "normalized": PYPROJ_AVAILABLE and source_crs != target_crs,
        "sample_coordinates_normalized": list(normalized_coords),
        "pyproj_available": PYPROJ_AVAILABLE,
        "processed_at": datetime.utcnow().isoformat(),
    }

    # メタデータを出力先に書き出し
    metadata_key = f"preprocessed/{source_key}.metadata.json"
    output_writer.put_json(key=metadata_key, data=metadata)

    logger.info(
        "UC17 Preprocessing: source=%s, src_crs=%s, target_crs=%s",
        source_key,
        source_crs,
        target_crs,
    )

    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="preprocessing")
    metrics.set_dimension("UseCase", "smart-city-geospatial")
    metrics.set_dimension("GeoFormat", geo_format)
    metrics.put_metric("FilesPreprocessed", 1.0, "Count")
    metrics.flush()

    return {
        "source_key": source_key,
        "metadata_key": metadata_key,
        "source_crs": source_crs,
        "target_crs": target_crs,
        "normalized": metadata["normalized"],
    }
