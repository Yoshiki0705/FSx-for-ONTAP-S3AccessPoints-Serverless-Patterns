"""UC17 Smart City Infrastructure Assessment Lambda.

LAS/LAZ 点群データからインフラ（道路、橋梁、建物）の状態を評価する。
laspy Layer が利用可能な場合は実データ解析、利用不可時はメタデータのみ。

Environment Variables:
    OUTPUT_BUCKET: 出力先 S3 バケット
    S3_ACCESS_POINT_ALIAS: 入力 S3 AP (optional)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)

try:
    import laspy
    LASPY_AVAILABLE = True
except ImportError:
    laspy = None
    LASPY_AVAILABLE = False


def assess_condition_score(
    point_density: float, std_elevation: float
) -> str:
    """点群統計から状態スコアを判定する。

    - GOOD: 高密度、低分散（均一な表面）
    - FAIR: 中密度
    - POOR: 低密度、高分散（損傷の可能性）
    """
    if point_density >= 10.0 and std_elevation < 0.5:
        return "GOOD"
    if point_density >= 5.0:
        return "FAIR"
    return "POOR"


def analyze_pointcloud_fallback(data_size: int) -> dict[str, Any]:
    """laspy 非利用時のフォールバック分析（サイズベースの概算）。"""
    # 点密度の概算: 1 MB あたり ~40,000 点と仮定
    estimated_points = (data_size // (1024 * 1024)) * 40000
    estimated_density = max(1.0, estimated_points / 10000)  # 仮想面積
    return {
        "estimated_points": estimated_points,
        "point_density": estimated_density,
        "std_elevation": 1.0,  # unknown
        "fallback_used": True,
    }


def analyze_pointcloud_laspy(data: bytes) -> dict[str, Any]:
    """laspy を使った点群解析。"""
    import io
    with laspy.open(io.BytesIO(data)) as f:
        header = f.header
        point_count = header.point_count
        xyz_array = []
        for points in f.chunk_iterator(10000):
            xyz_array.extend(points.z[:100].tolist())
        import statistics
        std_elev = statistics.stdev(xyz_array) if len(xyz_array) > 1 else 0.0

        # 面積 (m²) = (x_max - x_min) * (y_max - y_min)
        area = max(
            1.0,
            (header.maxs[0] - header.mins[0]) * (header.maxs[1] - header.mins[1]),
        )
        point_density = point_count / area

        return {
            "point_count": int(point_count),
            "point_density": float(point_density),
            "std_elevation": float(std_elev),
            "x_range": [float(header.mins[0]), float(header.maxs[0])],
            "y_range": [float(header.mins[1]), float(header.maxs[1])],
            "z_range": [float(header.mins[2]), float(header.maxs[2])],
            "fallback_used": False,
        }


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """UC17 Infrastructure Assessment Lambda ハンドラ。

    Input: {"source_key": "gis/bridge.las", "GeoFormat": "pointcloud"}
    Output: {"source_key": str, "condition_score": str, "statistics": {...}}
    """
    output_bucket = os.environ["OUTPUT_BUCKET"]
    s3_access_point = os.environ.get("S3_ACCESS_POINT_ALIAS")

    source_key = event.get("source_key") or event.get("Key")
    if not source_key:
        raise ValueError("Input must contain 'source_key' or 'Key'")

    # 点群データのみ処理
    is_pointcloud = source_key.lower().endswith((".las", ".laz"))
    if not is_pointcloud:
        return {
            "source_key": source_key,
            "condition_score": "N/A",
            "skipped": True,
            "reason": "Not a point cloud file",
        }

    # ダウンロード
    if s3_access_point:
        s3ap = S3ApHelper(s3_access_point)
        response = s3ap.get_object(source_key)
    else:
        s3_client = boto3.client("s3")
        response = s3_client.get_object(Bucket=output_bucket, Key=source_key)

    data = response["Body"].read()

    # 解析
    if LASPY_AVAILABLE:
        try:
            stats = analyze_pointcloud_laspy(data)
        except Exception as e:
            logger.warning("laspy analysis failed, falling back: %s", e)
            stats = analyze_pointcloud_fallback(len(data))
    else:
        stats = analyze_pointcloud_fallback(len(data))

    condition = assess_condition_score(
        stats.get("point_density", 0.0),
        stats.get("std_elevation", 1.0),
    )

    # 結果を S3 に書き出し
    result_key = f"infra-assessment/{source_key}.json"
    result = {
        "source_key": source_key,
        "condition_score": condition,
        "statistics": stats,
        "assessed_at": datetime.utcnow().isoformat(),
    }
    s3_client = boto3.client("s3")
    s3_client.put_object(
        Bucket=output_bucket,
        Key=result_key,
        Body=json.dumps(result, default=str),
        ContentType="application/json",
        ServerSideEncryption="aws:kms",
    )

    logger.info(
        "UC17 InfraAssessment: source=%s, condition=%s",
        source_key,
        condition,
    )

    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="infra_assessment")
    metrics.set_dimension("UseCase", "smart-city-geospatial")
    metrics.set_dimension("ConditionScore", condition)
    metrics.put_metric("InfrastructureAssessed", 1.0, "Count")
    metrics.flush()

    return {
        "source_key": source_key,
        "result_key": result_key,
        "condition_score": condition,
        "statistics": stats,
    }
