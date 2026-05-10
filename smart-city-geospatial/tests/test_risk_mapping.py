"""Unit tests for UC17 Risk Mapping Lambda."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_compute_flood_risk_high_low_elevation(risk_mapping_handler):
    landuse = {"residential": 0.7, "road": 0.2}
    score = risk_mapping_handler.compute_flood_risk(
        landuse, elevation_m=5.0, water_proximity_m=50.0
    )
    assert score > 0.6


def test_compute_flood_risk_low_high_elevation(risk_mapping_handler):
    landuse = {"forest": 0.8}
    score = risk_mapping_handler.compute_flood_risk(
        landuse, elevation_m=500.0, water_proximity_m=3000.0
    )
    assert score < 0.3


def test_compute_earthquake_risk_soft_soil(risk_mapping_handler):
    score = risk_mapping_handler.compute_earthquake_risk(
        soil_type="soft_soil", building_density=0.9
    )
    # soft_soil ~ 0.7, high building density → high score
    assert score > 0.5


def test_compute_earthquake_risk_rock(risk_mapping_handler):
    score = risk_mapping_handler.compute_earthquake_risk(
        soil_type="rock", building_density=0.1
    )
    # rock ~ 0.2, low density → low score
    assert score < 0.3


def test_compute_landslide_risk_steep_wet_barren(risk_mapping_handler):
    landuse = {"residential": 0.6}  # no forest
    score = risk_mapping_handler.compute_landslide_risk(
        slope_degrees=40.0, precipitation_annual_mm=2500.0,
        landuse_distribution=landuse,
    )
    assert score > 0.7


def test_compute_landslide_risk_flat_dry_forested(risk_mapping_handler):
    landuse = {"forest": 0.9}
    score = risk_mapping_handler.compute_landslide_risk(
        slope_degrees=2.0, precipitation_annual_mm=500.0,
        landuse_distribution=landuse,
    )
    assert score < 0.2


def test_classify_risk_level(risk_mapping_handler):
    assert risk_mapping_handler.classify_risk_level(0.9) == "CRITICAL"
    assert risk_mapping_handler.classify_risk_level(0.65) == "HIGH"
    assert risk_mapping_handler.classify_risk_level(0.4) == "MEDIUM"
    assert risk_mapping_handler.classify_risk_level(0.1) == "LOW"


def test_handler_computes_all_risks(risk_mapping_handler, lambda_context, monkeypatch):
    monkeypatch.setenv("OUTPUT_BUCKET", "test-bucket")

    mock_writer = MagicMock()

    with patch.object(
        risk_mapping_handler, "OutputWriter"
    ) as mock_output_writer_cls:
        mock_output_writer_cls.from_env.return_value = mock_writer
        event = {
            "source_key": "gis/area.tif",
            "landuse_distribution": {"residential": 0.5, "road": 0.2},
            "elevation_m": 30.0,
            "water_proximity_m": 500.0,
            "soil_type": "stiff_soil",
            "building_density": 0.6,
            "slope_degrees": 10.0,
            "precipitation_annual_mm": 1500.0,
        }
        result = risk_mapping_handler.handler(event, lambda_context)

    assert "risks" in result
    assert "flood" in result["risks"]
    assert "earthquake" in result["risks"]
    assert "landslide" in result["risks"]
    for hazard, info in result["risks"].items():
        assert "score" in info
        assert "level" in info
        assert info["level"] in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    mock_writer.put_json.assert_called_once()
