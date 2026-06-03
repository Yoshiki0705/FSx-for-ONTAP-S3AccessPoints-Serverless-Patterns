"""UC26 Real Estate Portfolio — Report Lambda unit tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# Dynamic import
_handler_path = Path(__file__).parent.parent / "functions" / "report" / "handler.py"
_spec = importlib.util.spec_from_file_location("realestate_report_handler", _handler_path)
_module = importlib.util.module_from_spec(_spec)
sys.modules["realestate_report_handler"] = _module
_spec.loader.exec_module(_module)

compute_portfolio_summary = _module.compute_portfolio_summary


class TestComputePortfolioSummary:
    """ポートフォリオサマリ計算のテスト"""

    def test_basic_summary(self):
        property_results = [
            {
                "status": "success",
                "property_id": "001",
                "condition": "good",
                "pii_detected": False,
                "amenities": ["pool"],
                "rooms": ["bedroom"],
            },
            {
                "status": "success",
                "property_id": "002",
                "condition": "needs_repair",
                "pii_detected": True,
                "amenities": [],
                "rooms": ["kitchen"],
            },
        ]
        contract_results = [
            {
                "status": "success",
                "property_id": "001",
                "lease_terms": {
                    "rent_amount": 100000,
                    "lease_period_months": 24,
                    "tenant_name": "Tanaka",
                },
            },
        ]

        result = compute_portfolio_summary(property_results, contract_results)

        assert result["total_properties"] == 2
        assert result["vacancy"]["occupied"] == 1
        assert result["vacancy"]["vacant"] == 1
        assert result["vacancy"]["vacancy_rate"] == 50.0
        assert result["condition"]["good"] == 1
        assert result["condition"]["needs_repair"] == 1
        assert "002" in result["pii_flagged_properties"]

    def test_empty_results(self):
        result = compute_portfolio_summary([], [])
        assert result["total_properties"] == 0
        assert result["vacancy"]["vacant"] == 0
        assert result["vacancy"]["occupied"] == 0
        assert result["vacancy"]["vacancy_rate"] == 0.0

    def test_all_occupied(self):
        property_results = [
            {
                "status": "success",
                "property_id": "A",
                "condition": "good",
                "pii_detected": False,
                "amenities": [],
                "rooms": [],
            },
        ]
        contract_results = [
            {
                "status": "success",
                "property_id": "A",
                "lease_terms": {
                    "rent_amount": 200000,
                    "lease_period_months": 12,
                    "tenant_name": "Test",
                },
            },
        ]

        result = compute_portfolio_summary(property_results, contract_results)
        assert result["vacancy"]["occupied"] == 1
        assert result["vacancy"]["vacant"] == 0
        assert result["vacancy"]["vacancy_rate"] == 0.0

    def test_error_results_excluded(self):
        property_results = [
            {"status": "error", "property_id": "X", "error_type": "PARSE_ERROR"},
        ]
        contract_results = [
            {"status": "error", "property_id": "Y", "error_type": "TRANSIENT"},
        ]

        result = compute_portfolio_summary(property_results, contract_results)
        assert result["total_properties"] == 0

    def test_average_rent_calculation(self):
        contract_results = [
            {
                "status": "success",
                "property_id": "A",
                "lease_terms": {"rent_amount": 100000, "lease_period_months": 12, "tenant_name": None},
            },
            {
                "status": "success",
                "property_id": "B",
                "lease_terms": {"rent_amount": 200000, "lease_period_months": 24, "tenant_name": None},
            },
        ]

        result = compute_portfolio_summary([], contract_results)
        assert result["contract_summary"]["average_rent"] == 150000
