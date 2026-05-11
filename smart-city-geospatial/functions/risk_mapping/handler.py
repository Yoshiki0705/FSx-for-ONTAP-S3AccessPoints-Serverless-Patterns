"""UC17 Smart City Risk Mapping Lambda.

土地利用、標高、水系データを元に、洪水・地震・土砂崩れの災害リスクスコアを計算する。

Environment Variables:
    OUTPUT_DESTINATION: `STANDARD_S3` or `FSXN_S3AP` (デフォルト: `STANDARD_S3`)
    OUTPUT_BUCKET: STANDARD_S3 モードの出力バケット
    OUTPUT_S3AP_ALIAS: FSXN_S3AP モードの S3AP Alias or ARN
    OUTPUT_S3AP_PREFIX: FSXN_S3AP モードの出力プレフィックス
"""

from __future__ import annotations

import logging
from datetime import datetime


from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler
from shared.output_writer import OutputWriter

logger = logging.getLogger(__name__)


def compute_flood_risk(
    landuse_distribution: dict[str, float],
    elevation_m: float,
    water_proximity_m: float,
) -> float:
    """洪水リスクスコア (0.0-1.0)。

    低標高 + 水辺近接 + 不透水率高（都市化）でリスク上昇。
    """
    # 標高スコア: 低いほどリスク高 (<10m で 1.0, >100m で 0.0)
    elevation_score = max(0.0, min(1.0, (100.0 - elevation_m) / 90.0))
    # 水系近接スコア: 近いほどリスク高 (<100m で 1.0, >2000m で 0.0)
    proximity_score = max(0.0, min(1.0, (2000.0 - water_proximity_m) / 1900.0))
    # 不透水率（建物 + 道路）
    impervious_rate = (
        landuse_distribution.get("residential", 0.0)
        + landuse_distribution.get("commercial", 0.0)
        + landuse_distribution.get("industrial", 0.0)
        + landuse_distribution.get("road", 0.0)
    )
    # 総合スコア（加重平均）
    return round(
        0.4 * elevation_score + 0.3 * proximity_score + 0.3 * impervious_rate,
        4,
    )


def compute_earthquake_risk(
    soil_type: str, building_density: float
) -> float:
    """地震リスクスコア (0.0-1.0)。"""
    soil_factors = {
        "rock": 0.2,
        "stiff_soil": 0.4,
        "soft_soil": 0.7,
        "unknown": 0.5,
    }
    soil_score = soil_factors.get(soil_type, 0.5)
    # 建物密度が高いほど被害ポテンシャル高
    density_score = min(1.0, building_density)
    return round(0.6 * soil_score + 0.4 * density_score, 4)


def compute_landslide_risk(
    slope_degrees: float,
    precipitation_annual_mm: float,
    landuse_distribution: dict[str, float],
) -> float:
    """土砂崩れリスクスコア (0.0-1.0)。"""
    # 斜度スコア: >45度で最大、<5度で0
    slope_score = max(0.0, min(1.0, (slope_degrees - 5.0) / 40.0))
    # 降雨スコア: 2000mm/年以上で最大
    rain_score = max(0.0, min(1.0, precipitation_annual_mm / 2000.0))
    # 植生スコア: 森林が少ないほどリスク高
    vegetation = landuse_distribution.get("forest", 0.0)
    veg_score = 1.0 - vegetation
    return round(0.5 * slope_score + 0.3 * rain_score + 0.2 * veg_score, 4)


def classify_risk_level(score: float) -> str:
    """リスクスコアから 4 段階レベル判定。"""
    if score >= 0.8:
        return "CRITICAL"
    if score >= 0.6:
        return "HIGH"
    if score >= 0.3:
        return "MEDIUM"
    return "LOW"


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """UC17 Risk Mapping Lambda ハンドラ。

    Input:
        {
            "source_key": "...",
            "landuse_distribution": {...},
            "elevation_m": float,
            "water_proximity_m": float,
            "soil_type": "rock" | "soft_soil" | ...,
            "slope_degrees": float,
            "precipitation_annual_mm": float,
            "building_density": float
        }

    Output: {"source_key": str, "risks": {"flood": {...}, "earthquake": {...}, "landslide": {...}}}
    """
    output_writer = OutputWriter.from_env()

    source_key = event.get("source_key", "")
    landuse = event.get("landuse_distribution", {})
    elevation_m = float(event.get("elevation_m", 50.0))
    water_proximity_m = float(event.get("water_proximity_m", 1000.0))
    soil_type = event.get("soil_type", "unknown")
    building_density = float(event.get("building_density", 0.0))
    slope_degrees = float(event.get("slope_degrees", 5.0))
    precip_mm = float(event.get("precipitation_annual_mm", 1500.0))

    flood_score = compute_flood_risk(landuse, elevation_m, water_proximity_m)
    quake_score = compute_earthquake_risk(soil_type, building_density)
    landslide_score = compute_landslide_risk(slope_degrees, precip_mm, landuse)

    risks = {
        "flood": {
            "score": flood_score,
            "level": classify_risk_level(flood_score),
            "factors": {
                "elevation_m": elevation_m,
                "water_proximity_m": water_proximity_m,
                "impervious_rate": round(
                    sum(
                        landuse.get(k, 0.0)
                        for k in ("residential", "commercial", "industrial", "road")
                    ),
                    4,
                ),
            },
        },
        "earthquake": {
            "score": quake_score,
            "level": classify_risk_level(quake_score),
            "factors": {
                "soil_type": soil_type,
                "building_density": building_density,
            },
        },
        "landslide": {
            "score": landslide_score,
            "level": classify_risk_level(landslide_score),
            "factors": {
                "slope_degrees": slope_degrees,
                "precipitation_annual_mm": precip_mm,
                "forest_coverage": landuse.get("forest", 0.0),
            },
        },
    }

    # 出力先に書き出し
    result_key = f"risk-maps/{source_key}.json"
    output_writer.put_json(
        key=result_key,
        data={
            "source_key": source_key,
            "risks": risks,
            "assessed_at": datetime.utcnow().isoformat(),
        },
    )

    logger.info(
        "UC17 RiskMapping: source=%s, flood=%.2f (%s), quake=%.2f (%s), landslide=%.2f (%s)",
        source_key,
        flood_score, risks["flood"]["level"],
        quake_score, risks["earthquake"]["level"],
        landslide_score, risks["landslide"]["level"],
    )

    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="risk_mapping")
    metrics.set_dimension("UseCase", "smart-city-geospatial")
    metrics.put_metric("FloodRiskScore", flood_score, "None")
    metrics.put_metric("EarthquakeRiskScore", quake_score, "None")
    metrics.put_metric("LandslideRiskScore", landslide_score, "None")
    metrics.flush()

    return {
        "source_key": source_key,
        "result_key": result_key,
        "risks": risks,
    }
