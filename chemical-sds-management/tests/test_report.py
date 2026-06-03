"""UC28 Chemical SDS Management — Report Lambda unit tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_handler_path = Path(__file__).parent.parent / "functions" / "report" / "handler.py"
_spec = importlib.util.spec_from_file_location("chem_report_handler", _handler_path)
_module = importlib.util.module_from_spec(_spec)
sys.modules["chem_report_handler"] = _module
_spec.loader.exec_module(_module)

compute_compliance_summary = _module.compute_compliance_summary
GHS_MANDATORY_SECTIONS = _module.GHS_MANDATORY_SECTIONS


class TestComputeComplianceSummary:
    def test_all_compliant(self):
        sds_results = [
            {
                "status": "success",
                "key": "sds/A.pdf",
                "substance_id": "A",
                "revision_date": "2024-01-01",
                "expiry": {"is_expired": False, "days_since_revision": 100, "priority": None},
                "missing_ghs_sections": [],
            },
        ]
        result = compute_compliance_summary(sds_results, [], validity_days=365)
        assert result["compliant_count"] == 1
        assert result["expired_sds_count"] == 0
        assert result["missing_sections_count"] == 0
        assert result["compliance_rate"] == 100.0

    def test_expired_sds_critical(self):
        sds_results = [
            {
                "status": "success",
                "key": "sds/old.pdf",
                "substance_id": "B",
                "revision_date": "2022-01-01",
                "expiry": {"is_expired": True, "days_since_revision": 900, "priority": "critical"},
                "missing_ghs_sections": [],
            },
        ]
        result = compute_compliance_summary(sds_results, [], validity_days=365)
        assert result["expired_sds_count"] == 1
        assert result["expired_sds_alerts"][0]["priority"] == "critical"
        assert result["compliant_count"] == 0

    def test_missing_ghs_sections(self):
        sds_results = [
            {
                "status": "success",
                "key": "sds/incomplete.pdf",
                "substance_id": "C",
                "revision_date": "2024-06-01",
                "expiry": {"is_expired": False, "days_since_revision": 30, "priority": None},
                "missing_ghs_sections": ["first_aid", "fire_fighting"],
            },
        ]
        result = compute_compliance_summary(sds_results, [], validity_days=365)
        assert result["missing_sections_count"] == 1
        assert result["missing_sections_alerts"][0]["priority"] == "high"
        assert "first_aid" in result["missing_sections_alerts"][0]["missing_sections"]

    def test_research_data_index(self):
        labbook_results = [
            {
                "status": "success",
                "key": "labbooks/exp1.jpg",
                "substance_id": "D",
                "experiment_data": {
                    "parameters": ["温度: 25°C"],
                    "results": ["収率 90%"],
                    "observations": [],
                },
            },
        ]
        result = compute_compliance_summary([], labbook_results)
        assert result["research_entries_count"] == 1
        assert result["research_data_index"][0]["has_parameters"] is True
        assert result["research_data_index"][0]["has_results"] is True

    def test_empty_results(self):
        result = compute_compliance_summary([], [])
        assert result["total_sds_analyzed"] == 0
        assert result["compliance_rate"] == 0.0
        assert result["expired_sds_count"] == 0

    def test_error_results_excluded(self):
        sds_results = [
            {"status": "error", "error_type": "TRANSIENT"},
        ]
        result = compute_compliance_summary(sds_results, [])
        assert result["total_sds_analyzed"] == 0
