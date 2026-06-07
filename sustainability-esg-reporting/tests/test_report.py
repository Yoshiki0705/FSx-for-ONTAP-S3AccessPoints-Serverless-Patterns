"""UC23 Sustainability ESG Reporting — Report Lambda unit tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# Dynamic import for namespace isolation
_handler_path = Path(__file__).parent.parent / "functions" / "report" / "handler.py"
_spec = importlib.util.spec_from_file_location("esg_report_handler", _handler_path)
_module = importlib.util.module_from_spec(_spec)
sys.modules["esg_report_handler"] = _module
_spec.loader.exec_module(_module)

aggregate_by_category = _module.aggregate_by_category
aggregate_by_period = _module.aggregate_by_period
compute_yoy_trend = _module.compute_yoy_trend
generate_esg_summary = _module.generate_esg_summary


class TestAggregateByCategory:
    """カテゴリ別集約テスト"""

    def test_empty_results(self):
        result = aggregate_by_category([])
        assert result == {}

    def test_single_category(self):
        results = [
            {
                "status": "success",
                "mapped_metrics": [
                    {"esg_category": "environmental", "metric_name": "CO2"},
                    {"esg_category": "environmental", "metric_name": "Energy"},
                ],
            }
        ]
        categorized = aggregate_by_category(results)
        assert "environmental" in categorized
        assert len(categorized["environmental"]) == 2

    def test_multiple_categories(self):
        results = [
            {
                "status": "success",
                "mapped_metrics": [
                    {"esg_category": "environmental", "metric_name": "CO2"},
                    {"esg_category": "social", "metric_name": "Diversity"},
                    {"esg_category": "governance", "metric_name": "Board"},
                ],
            }
        ]
        categorized = aggregate_by_category(results)
        assert len(categorized) == 3
        assert "environmental" in categorized
        assert "social" in categorized
        assert "governance" in categorized

    def test_skips_error_results(self):
        results = [
            {"status": "error", "mapped_metrics": [{"esg_category": "environmental"}]},
            {
                "status": "success",
                "mapped_metrics": [
                    {"esg_category": "social", "metric_name": "Test"},
                ],
            },
        ]
        categorized = aggregate_by_category(results)
        assert "environmental" not in categorized
        assert "social" in categorized


class TestAggregateByPeriod:
    """期間別集約テスト"""

    def test_empty_metrics(self):
        result = aggregate_by_period([])
        assert result == {}

    def test_single_period(self):
        metrics = [
            {"period": "2024", "metric_name": "CO2"},
            {"period": "2024", "metric_name": "Energy"},
        ]
        result = aggregate_by_period(metrics)
        assert "2024" in result
        assert len(result["2024"]) == 2

    def test_multiple_periods(self):
        metrics = [
            {"period": "2023", "metric_name": "CO2"},
            {"period": "2024", "metric_name": "CO2"},
            {"period": "2024", "metric_name": "Energy"},
        ]
        result = aggregate_by_period(metrics)
        assert len(result) == 2
        assert len(result["2023"]) == 1
        assert len(result["2024"]) == 2


class TestComputeYoyTrend:
    """YoY トレンド計算テスト"""

    def test_single_period_returns_none(self):
        """1 期間のみの場合はトレンドなし"""
        period_data = {"2024": [{"category": "co2_emissions", "normalized_value": 100, "status": "success"}]}
        result = compute_yoy_trend(period_data)
        assert result is None

    def test_two_periods_calculates_trend(self):
        """2 期間あればトレンドを計算"""
        period_data = {
            "2023": [{"category": "co2_emissions", "normalized_value": 100, "status": "success"}],
            "2024": [{"category": "co2_emissions", "normalized_value": 90, "status": "success"}],
        }
        result = compute_yoy_trend(period_data)
        assert result is not None
        assert len(result) == 1
        assert result[0]["category"] == "co2_emissions"
        assert result[0]["change_percent"] == -10.0
        assert result[0]["direction"] == "decrease"

    def test_increase_trend(self):
        period_data = {
            "2023": [{"category": "energy_usage", "normalized_value": 500, "status": "success"}],
            "2024": [{"category": "energy_usage", "normalized_value": 600, "status": "success"}],
        }
        result = compute_yoy_trend(period_data)
        assert result is not None
        assert result[0]["direction"] == "increase"
        assert result[0]["change_percent"] == 20.0

    def test_unchanged_trend(self):
        period_data = {
            "2023": [{"category": "waste_volume", "normalized_value": 50, "status": "success"}],
            "2024": [{"category": "waste_volume", "normalized_value": 50, "status": "success"}],
        }
        result = compute_yoy_trend(period_data)
        assert result is not None
        assert result[0]["direction"] == "unchanged"
        assert result[0]["change_percent"] == 0.0

    def test_three_periods(self):
        period_data = {
            "2022": [{"category": "co2_emissions", "normalized_value": 200, "status": "success"}],
            "2023": [{"category": "co2_emissions", "normalized_value": 150, "status": "success"}],
            "2024": [{"category": "co2_emissions", "normalized_value": 120, "status": "success"}],
        }
        result = compute_yoy_trend(period_data)
        assert result is not None
        assert len(result) == 2  # 2022→2023, 2023→2024

    def test_skips_non_success_metrics(self):
        period_data = {
            "2023": [
                {"category": "co2_emissions", "normalized_value": 100, "status": "success"},
                {"category": "co2_emissions", "normalized_value": 50, "status": "requires-validation"},
            ],
            "2024": [{"category": "co2_emissions", "normalized_value": 80, "status": "success"}],
        }
        result = compute_yoy_trend(period_data)
        assert result is not None
        # 2023 success: 100, 2024 success: 80 → -20%
        assert result[0]["change_percent"] == -20.0


class TestGenerateEsgSummary:
    """ESG サマリ生成テスト"""

    def test_empty_categorized(self):
        result = generate_esg_summary({})
        assert result == {}

    def test_summary_with_metrics(self):
        categorized = {
            "environmental": [
                {
                    "status": "success",
                    "category": "co2_emissions",
                    "normalized_value": 100,
                    "normalized_unit": "tCO2e",
                    "framework_mappings": {"GRI": ["GRI 305-1"], "TCFD": [], "CDP": []},
                },
                {
                    "status": "requires-validation",
                    "category": "energy_usage",
                    "normalized_value": None,
                    "normalized_unit": "MWh",
                    "framework_mappings": {},
                },
            ]
        }
        result = generate_esg_summary(categorized)
        assert "environmental" in result
        env = result["environmental"]
        assert env["total_metrics"] == 2
        assert env["success_count"] == 1
        assert env["requires_validation_count"] == 1
        assert "co2_emissions" in env["metric_categories"]
