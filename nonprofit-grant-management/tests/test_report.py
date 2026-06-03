"""UC24 Nonprofit Grant Management — Report Lambda unit tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# Dynamic import for namespace isolation
_handler_path = Path(__file__).parent.parent / "functions" / "report" / "handler.py"
_spec = importlib.util.spec_from_file_location("npo_report_handler", _handler_path)
_module = importlib.util.module_from_spec(_spec)
sys.modules["npo_report_handler"] = _module
_spec.loader.exec_module(_module)

compute_compliance_status = _module.compute_compliance_status
compute_achievement_rates = _module.compute_achievement_rates
aggregate_by_program_area = _module.aggregate_by_program_area


class TestComputeComplianceStatus:
    """コンプライアンスステータス計算テスト"""

    def test_all_compliant(self):
        results = [
            {
                "status": "success",
                "extracted_info": {
                    "applicant_info": {"organization_name": "NPO A"},
                    "budget": {"total_amount": 100000},
                    "project_description": {"title": "Project A"},
                },
            },
            {
                "status": "success",
                "extracted_info": {
                    "applicant_info": {"organization_name": "NPO B"},
                    "budget": {"total_amount": 200000},
                    "project_description": {"title": "Project B"},
                },
            },
        ]

        status = compute_compliance_status(results)
        assert status["total"] == 2
        assert status["compliant"] == 2
        assert status["non_compliant"] == 0
        assert status["pending_review"] == 0
        assert status["compliance_rate"] == 100.0

    def test_mixed_results(self):
        results = [
            {
                "status": "success",
                "extracted_info": {
                    "applicant_info": {"organization_name": "NPO A"},
                    "budget": {"total_amount": 100000},
                    "project_description": {"title": "Project A"},
                },
            },
            {
                "status": "success",
                "extracted_info": {
                    "applicant_info": {"organization_name": ""},
                    "budget": {"total_amount": None},
                    "project_description": {"title": ""},
                },
            },
            {"status": "error", "errors": [{"path": "file.pdf"}]},
            {"status": "skipped", "reason": "unrecognized_format"},
        ]

        status = compute_compliance_status(results)
        assert status["total"] == 4
        assert status["compliant"] == 1
        assert status["non_compliant"] == 1
        assert status["pending_review"] == 2
        assert status["compliance_rate"] == 25.0

    def test_empty_results(self):
        status = compute_compliance_status([])
        assert status["total"] == 0
        assert status["compliant"] == 0
        assert status["compliance_rate"] == 0.0

    def test_all_errors(self):
        results = [
            {"status": "error", "errors": [{"path": "a.pdf"}]},
            {"status": "error", "errors": [{"path": "b.pdf"}]},
        ]

        status = compute_compliance_status(results)
        assert status["total"] == 2
        assert status["non_compliant"] == 2
        assert status["compliant"] == 0


class TestComputeAchievementRates:
    """達成率計算テスト"""

    def test_high_achievement(self):
        results = [
            {
                "status": "success",
                "outcome_data": {
                    "overall_achievement_rate": 95,
                    "objective_matching": [
                        {"achievement_status": "achieved"},
                        {"achievement_status": "achieved"},
                    ],
                },
            },
        ]

        rates = compute_achievement_rates(results)
        assert rates["total_reports"] == 1
        assert rates["average_achievement_rate"] == 95.0

    def test_mixed_achievement(self):
        results = [
            {
                "status": "success",
                "outcome_data": {
                    "overall_achievement_rate": 90,
                    "objective_matching": [
                        {"achievement_status": "achieved"},
                    ],
                },
            },
            {
                "status": "success",
                "outcome_data": {
                    "overall_achievement_rate": 40,
                    "objective_matching": [
                        {"achievement_status": "not_achieved"},
                    ],
                },
            },
        ]

        rates = compute_achievement_rates(results)
        assert rates["total_reports"] == 2
        assert rates["average_achievement_rate"] == 65.0

    def test_empty_results(self):
        rates = compute_achievement_rates([])
        assert rates["total_reports"] == 0
        assert rates["average_achievement_rate"] == 0.0

    def test_error_results_skipped(self):
        results = [
            {"status": "error", "errors": [{"path": "file.pdf"}]},
        ]

        rates = compute_achievement_rates(results)
        assert rates["total_reports"] == 1
        assert rates["average_achievement_rate"] == 0.0

    def test_no_overall_rate(self):
        results = [
            {
                "status": "success",
                "outcome_data": {
                    "objective_matching": [
                        {"achievement_status": "achieved"},
                        {"achievement_status": "partially_achieved"},
                    ],
                },
            },
        ]

        rates = compute_achievement_rates(results)
        assert rates["achieved"] == 1
        assert rates["partially_achieved"] == 1


class TestAggregateByProgramArea:
    """プログラムエリア別集約テスト"""

    def test_multiple_areas(self):
        grant_results = [
            {
                "status": "success",
                "extracted_info": {
                    "_metadata": {"program_area": "education"},
                    "applicant_info": {"organization_name": "NPO A"},
                    "budget": {"total_amount": 100000},
                    "project_description": {"title": "Education Project"},
                },
            },
            {
                "status": "success",
                "extracted_info": {
                    "_metadata": {"program_area": "health"},
                    "applicant_info": {"organization_name": "NPO B"},
                    "budget": {"total_amount": 200000},
                    "project_description": {"title": "Health Project"},
                },
            },
            {
                "status": "success",
                "extracted_info": {
                    "_metadata": {"program_area": "education"},
                    "applicant_info": {"organization_name": "NPO C"},
                    "budget": {"total_amount": 150000},
                    "project_description": {"title": "Education Project 2"},
                },
            },
        ]

        outcome_results = [
            {
                "status": "success",
                "outcome_data": {
                    "_metadata": {"program_area": "education"},
                    "overall_achievement_rate": 85,
                },
            },
        ]

        breakdown = aggregate_by_program_area(grant_results, outcome_results)

        assert "education" in breakdown
        assert "health" in breakdown
        assert breakdown["education"]["grant_applications"] == 2
        assert breakdown["education"]["activity_reports"] == 1
        assert breakdown["education"]["total_budget_requested"] == 250000.0
        assert breakdown["health"]["grant_applications"] == 1
        assert breakdown["health"]["total_budget_requested"] == 200000.0

    def test_empty_results(self):
        breakdown = aggregate_by_program_area([], [])
        assert breakdown == {}

    def test_error_results_skipped(self):
        grant_results = [
            {"status": "error", "errors": [{"path": "file.pdf"}]},
        ]
        breakdown = aggregate_by_program_area(grant_results, [])
        assert breakdown == {}
