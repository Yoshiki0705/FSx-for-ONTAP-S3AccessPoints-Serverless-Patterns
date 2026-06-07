"""UC23 Sustainability ESG Reporting — Processing Lambda unit tests.

Tests for metrics_extractor and framework_mapper handlers.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Dynamic import: unit_normalizer
_normalizer_path = Path(__file__).parent.parent / "shared" / "unit_normalizer.py"
_normalizer_spec = importlib.util.spec_from_file_location("esg_unit_normalizer", _normalizer_path)
_normalizer_module = importlib.util.module_from_spec(_normalizer_spec)
sys.modules["esg_unit_normalizer"] = _normalizer_module
_normalizer_spec.loader.exec_module(_normalizer_module)
normalize_value = _normalizer_module.normalize_value
normalize_metric_record = _normalizer_module.normalize_metric_record
get_supported_categories = _normalizer_module.get_supported_categories
get_target_unit = _normalizer_module.get_target_unit
get_supported_units = _normalizer_module.get_supported_units
UNIT_NORMALIZATION = _normalizer_module.UNIT_NORMALIZATION
NormalizationResult = _normalizer_module.NormalizationResult

# Dynamic import: metrics_extractor
_extractor_path = Path(__file__).parent.parent / "functions" / "metrics_extractor" / "handler.py"
_extractor_spec = importlib.util.spec_from_file_location("esg_metrics_extractor", _extractor_path)
_extractor_module = importlib.util.module_from_spec(_extractor_spec)
sys.modules["esg_metrics_extractor"] = _extractor_module
_extractor_spec.loader.exec_module(_extractor_module)
normalize_metrics = _extractor_module.normalize_metrics
_parse_metrics_json = _extractor_module._parse_metrics_json

# Dynamic import: framework_mapper
_mapper_path = Path(__file__).parent.parent / "functions" / "framework_mapper" / "handler.py"
_mapper_spec = importlib.util.spec_from_file_location("esg_framework_mapper", _mapper_path)
_mapper_module = importlib.util.module_from_spec(_mapper_spec)
sys.modules["esg_framework_mapper"] = _mapper_module
_mapper_spec.loader.exec_module(_mapper_module)
get_fallback_mapping = _mapper_module.get_fallback_mapping
_apply_fallback_mappings = _mapper_module._apply_fallback_mappings
KNOWN_FRAMEWORK_MAPPINGS = _mapper_module.KNOWN_FRAMEWORK_MAPPINGS


# ─────────────────────────────────────────────────────────────────────────────
# Unit Normalizer Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestUnitNormalization:
    """単位正規化ロジックのテスト"""

    def test_co2_kg_to_tco2e(self):
        result = normalize_value(1000.0, "kg", "co2_emissions")
        assert result.status == "success"
        assert result.value == pytest.approx(1.0)
        assert result.unit == "tCO2e"

    def test_co2_t_to_tco2e(self):
        result = normalize_value(5.0, "t", "co2_emissions")
        assert result.status == "success"
        assert result.value == pytest.approx(5.0)
        assert result.unit == "tCO2e"

    def test_co2_mt_to_tco2e(self):
        result = normalize_value(2.0, "Mt", "co2_emissions")
        assert result.status == "success"
        assert result.value == pytest.approx(2_000_000.0)
        assert result.unit == "tCO2e"

    def test_energy_kwh_to_mwh(self):
        result = normalize_value(5000.0, "kWh", "energy_usage")
        assert result.status == "success"
        assert result.value == pytest.approx(5.0)
        assert result.unit == "MWh"

    def test_energy_gwh_to_mwh(self):
        result = normalize_value(1.5, "GWh", "energy_usage")
        assert result.status == "success"
        assert result.value == pytest.approx(1500.0)
        assert result.unit == "MWh"

    def test_energy_gj_to_mwh(self):
        result = normalize_value(100.0, "GJ", "energy_usage")
        assert result.status == "success"
        assert result.value == pytest.approx(27.78)
        assert result.unit == "MWh"

    def test_waste_kg_to_t(self):
        result = normalize_value(5000.0, "kg", "waste_volume")
        assert result.status == "success"
        assert result.value == pytest.approx(5.0)
        assert result.unit == "t"

    def test_water_l_to_m3(self):
        result = normalize_value(10000.0, "L", "water_usage")
        assert result.status == "success"
        assert result.value == pytest.approx(10.0)
        assert result.unit == "m3"

    def test_water_kl_to_m3(self):
        result = normalize_value(50.0, "kL", "water_usage")
        assert result.status == "success"
        assert result.value == pytest.approx(50.0)
        assert result.unit == "m3"

    def test_water_ml_to_m3(self):
        result = normalize_value(2.0, "ML", "water_usage")
        assert result.status == "success"
        assert result.value == pytest.approx(2000.0)
        assert result.unit == "m3"

    def test_missing_unit(self):
        result = normalize_value(100.0, None, "co2_emissions")
        assert result.status == "requires-validation"
        assert result.reason == "missing_unit"

    def test_empty_unit(self):
        result = normalize_value(100.0, "", "co2_emissions")
        assert result.status == "requires-validation"
        assert result.reason == "missing_unit"

    def test_conflicting_unit(self):
        result = normalize_value(100.0, "gallons", "water_usage")
        assert result.status == "requires-validation"
        assert result.reason == "conflicting_units"

    def test_out_of_range_negative(self):
        result = normalize_value(-100.0, "t", "co2_emissions")
        assert result.status == "requires-validation"
        assert result.reason == "out_of_range"

    def test_unknown_category(self):
        result = normalize_value(100.0, "kg", "unknown_category")
        assert result.status == "requires-validation"
        assert result.reason == "unknown_category"

    def test_already_target_unit(self):
        result = normalize_value(42.0, "tCO2e", "co2_emissions")
        assert result.status == "success"
        assert result.value == pytest.approx(42.0)
        assert result.unit == "tCO2e"


class TestGetSupportedCategories:
    """カテゴリ一覧取得テスト"""

    def test_returns_all_categories(self):
        categories = get_supported_categories()
        assert "co2_emissions" in categories
        assert "energy_usage" in categories
        assert "waste_volume" in categories
        assert "water_usage" in categories

    def test_returns_four_categories(self):
        assert len(get_supported_categories()) == 4


class TestGetTargetUnit:
    """ターゲット単位取得テスト"""

    def test_co2_target(self):
        assert get_target_unit("co2_emissions") == "tCO2e"

    def test_energy_target(self):
        assert get_target_unit("energy_usage") == "MWh"

    def test_waste_target(self):
        assert get_target_unit("waste_volume") == "t"

    def test_water_target(self):
        assert get_target_unit("water_usage") == "m3"

    def test_unknown_category(self):
        assert get_target_unit("unknown") is None


class TestNormalizeMetricRecord:
    """レコード正規化テスト"""

    def test_valid_record(self):
        record = {"value": 1000, "unit": "kg", "category": "co2_emissions"}
        result = normalize_metric_record(record)
        assert result["normalization_status"] == "success"
        assert result["normalized_value"] == pytest.approx(1.0)
        assert result["normalized_unit"] == "tCO2e"

    def test_missing_value(self):
        record = {"value": None, "unit": "kg", "category": "co2_emissions"}
        result = normalize_metric_record(record)
        assert result["normalization_status"] == "requires-validation"

    def test_non_numeric_value(self):
        record = {"value": "abc", "unit": "kg", "category": "co2_emissions"}
        result = normalize_metric_record(record)
        assert result["normalization_status"] == "requires-validation"
        assert result["normalization_reason"] == "non_numeric_value"


# ─────────────────────────────────────────────────────────────────────────────
# Metrics Extractor Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestNormalizeMetrics:
    """メトリクス正規化統合テスト"""

    def test_normalizes_valid_metrics(self):
        raw_metrics = [
            {
                "metric_name": "CO2 emissions",
                "value": 1000,
                "unit": "t",
                "category": "co2_emissions",
                "period": "2024",
                "confidence": 0.9,
            }
        ]
        results = normalize_metrics(raw_metrics, "test.pdf", "environmental")
        assert len(results) == 1
        assert results[0]["status"] == "success"
        assert results[0]["normalized_value"] == pytest.approx(1000.0)
        assert results[0]["source_key"] == "test.pdf"
        assert results[0]["esg_category"] == "environmental"

    def test_handles_missing_unit(self):
        raw_metrics = [
            {
                "metric_name": "Energy",
                "value": 500,
                "unit": None,
                "category": "energy_usage",
                "period": "2024",
                "confidence": 0.7,
            }
        ]
        results = normalize_metrics(raw_metrics, "test.pdf", "environmental")
        assert results[0]["status"] == "requires-validation"
        assert results[0]["validation_reason"] == "missing_unit"

    def test_handles_unknown_category(self):
        raw_metrics = [
            {
                "metric_name": "Unknown",
                "value": 100,
                "unit": "kg",
                "category": "biodiversity",
                "period": "2024",
                "confidence": 0.5,
            }
        ]
        results = normalize_metrics(raw_metrics, "test.pdf", "environmental")
        assert results[0]["status"] == "requires-validation"
        assert results[0]["validation_reason"] == "unknown_category"

    def test_confidence_clamped(self):
        raw_metrics = [
            {
                "metric_name": "CO2",
                "value": 100,
                "unit": "t",
                "category": "co2_emissions",
                "period": "2024",
                "confidence": 1.5,  # over max
            }
        ]
        results = normalize_metrics(raw_metrics, "test.pdf", "environmental")
        assert results[0]["confidence"] == 1.0


class TestParseMetricsJson:
    """Bedrock レスポンス JSON パーステスト"""

    def test_parse_valid_json(self):
        text = 'Here are the results: [{"metric_name": "CO2", "value": 100}]'
        result = _parse_metrics_json(text)
        assert len(result) == 1
        assert result[0]["metric_name"] == "CO2"

    def test_parse_empty_array(self):
        text = "No metrics found: []"
        result = _parse_metrics_json(text)
        assert result == []

    def test_parse_no_json(self):
        text = "I could not find any metrics in this document."
        result = _parse_metrics_json(text)
        assert result == []

    def test_parse_invalid_json(self):
        text = "[{invalid json}]"
        result = _parse_metrics_json(text)
        assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# Framework Mapper Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestFrameworkMapper:
    """フレームワークマッパーテスト"""

    def test_fallback_mapping_co2(self):
        mapping = get_fallback_mapping("co2_emissions")
        assert "GRI" in mapping
        assert "TCFD" in mapping
        assert "CDP" in mapping
        assert len(mapping["GRI"]) > 0

    def test_fallback_mapping_energy(self):
        mapping = get_fallback_mapping("energy_usage")
        assert "GRI 302-1" in mapping["GRI"]

    def test_fallback_mapping_unknown(self):
        mapping = get_fallback_mapping("unknown_category")
        assert mapping == {"GRI": [], "TCFD": [], "CDP": []}

    def test_apply_fallback_mappings(self):
        metrics = [
            {"metric_name": "CO2", "category": "co2_emissions", "status": "success"},
            {"metric_name": "Energy", "category": "energy_usage", "status": "success"},
        ]
        results = _apply_fallback_mappings(metrics)
        assert len(results) == 2
        assert "framework_mappings" in results[0]
        assert "GRI" in results[0]["framework_mappings"]
        assert "framework_mappings" in results[1]
