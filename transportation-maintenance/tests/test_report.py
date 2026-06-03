"""UC22 Transportation Maintenance — Report Lambda unit tests."""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

# Dynamic module loading — report handler
_report_handler_path = os.path.join(
    os.path.dirname(__file__),
    "..",
    "functions",
    "report",
    "handler.py",
)
_report_spec = importlib.util.spec_from_file_location(
    "uc22_report_handler", _report_handler_path
)
_report_module = importlib.util.module_from_spec(_report_spec)
sys.modules["uc22_report_handler"] = _report_module
_report_spec.loader.exec_module(_report_module)

aggregate_deterioration_results = _report_module.aggregate_deterioration_results
aggregate_maintenance_results = _report_module.aggregate_maintenance_results
SEVERITY_PRIORITY = _report_module.SEVERITY_PRIORITY


class TestAggregateDeteriorationResults:
    """劣化検出結果集約のテスト."""

    def test_empty_results(self):
        result = aggregate_deterioration_results([])
        assert result["total_images_analyzed"] == 0
        assert result["success_count"] == 0
        assert result["error_count"] == 0

    def test_single_success_result(self):
        results = [
            {
                "status": "success",
                "key": "inspections/route-1/img001.jpg",
                "is_safety_critical": False,
                "human_review_required": False,
                "severity_counts": {"critical": 0, "major": 1, "minor": 2, "observation": 0},
                "severity_classifications": [
                    {"severity": "major", "defect_type": "crack"},
                    {"severity": "minor", "defect_type": "rust"},
                    {"severity": "minor", "defect_type": "wear"},
                ],
                "detection_summary": {"deterioration_labels_count": 3},
            }
        ]
        result = aggregate_deterioration_results(results)
        assert result["total_images_analyzed"] == 1
        assert result["success_count"] == 1
        assert result["severity_summary"]["major"] == 1
        assert result["severity_summary"]["minor"] == 2

    def test_reinspection_results_counted(self):
        results = [
            {
                "status": "requires-reinspection",
                "key": "inspections/low-res.jpg",
                "is_safety_critical": True,
                "reason": "Low resolution",
            }
        ]
        result = aggregate_deterioration_results(results)
        assert result["reinspection_required_count"] == 1
        assert result["success_count"] == 1  # requires-reinspection counts as success

    def test_priority_ranking_sorted_by_severity(self):
        results = [
            {
                "status": "success",
                "key": "inspections/minor_issue.jpg",
                "is_safety_critical": False,
                "human_review_required": False,
                "severity_counts": {"critical": 0, "major": 0, "minor": 1, "observation": 0},
                "severity_classifications": [{"severity": "minor"}],
                "detection_summary": {"deterioration_labels_count": 1},
            },
            {
                "status": "success",
                "key": "inspections/critical_issue.jpg",
                "is_safety_critical": True,
                "human_review_required": True,
                "severity_counts": {"critical": 1, "major": 0, "minor": 0, "observation": 0},
                "severity_classifications": [{"severity": "critical"}],
                "detection_summary": {"deterioration_labels_count": 1},
            },
        ]
        result = aggregate_deterioration_results(results)
        ranking = result["priority_ranking"]
        assert len(ranking) == 2
        # Critical + safety_critical should be first
        assert ranking[0]["severity"] == "critical"
        assert ranking[0]["is_safety_critical"] is True
        assert ranking[1]["severity"] == "minor"

    def test_human_review_count(self):
        results = [
            {
                "status": "success",
                "key": "img1.jpg",
                "is_safety_critical": False,
                "human_review_required": True,
                "severity_counts": {"critical": 0, "major": 0, "minor": 0, "observation": 1},
                "severity_classifications": [],
                "detection_summary": {"deterioration_labels_count": 0},
            },
            {
                "status": "success",
                "key": "img2.jpg",
                "is_safety_critical": False,
                "human_review_required": False,
                "severity_counts": {"critical": 0, "major": 0, "minor": 0, "observation": 0},
                "severity_classifications": [],
                "detection_summary": {"deterioration_labels_count": 0},
            },
        ]
        result = aggregate_deterioration_results(results)
        assert result["human_review_required_count"] == 1


class TestAggregateMaintenanceResults:
    """保守抽出結果集約のテスト."""

    def test_empty_results(self):
        result = aggregate_maintenance_results([])
        assert result["total_documents_processed"] == 0
        assert result["equipment_count"] == 0

    def test_successful_extraction(self):
        results = [
            {
                "status": "success",
                "key": "maintenance-reports/report_001.pdf",
                "lifecycle_data": {
                    "equipment_id": "EQ-001",
                    "installation_date": "2015-04-01",
                    "last_repair_date": "2024-12-15",
                    "component_age_days": 3500,
                    "replacement_schedule": "2027年3月予定",
                    "repair_history": [
                        {"date": "2024-12-15", "description": "ボルト交換"},
                    ],
                },
            },
        ]
        result = aggregate_maintenance_results(results)
        assert result["total_documents_processed"] == 1
        assert result["success_count"] == 1
        assert result["equipment_count"] == 1
        assert result["equipment_records"][0]["equipment_id"] == "EQ-001"

    def test_error_results_counted(self):
        results = [
            {"status": "error", "key": "corrupt.pdf", "error_category": "PARSE_ERROR"},
            {
                "status": "success",
                "key": "good.pdf",
                "lifecycle_data": {
                    "equipment_id": "EQ-002",
                    "installation_date": None,
                    "last_repair_date": None,
                    "component_age_days": None,
                    "replacement_schedule": None,
                    "repair_history": [],
                },
            },
        ]
        result = aggregate_maintenance_results(results)
        assert result["total_documents_processed"] == 2
        assert result["success_count"] == 1
        assert result["error_count"] == 1


class TestSeverityPriority:
    """重大度優先度のテスト."""

    def test_critical_highest_priority(self):
        assert SEVERITY_PRIORITY["critical"] < SEVERITY_PRIORITY["major"]
        assert SEVERITY_PRIORITY["major"] < SEVERITY_PRIORITY["minor"]
        assert SEVERITY_PRIORITY["minor"] < SEVERITY_PRIORITY["observation"]

    def test_all_levels_defined(self):
        assert "critical" in SEVERITY_PRIORITY
        assert "major" in SEVERITY_PRIORITY
        assert "minor" in SEVERITY_PRIORITY
        assert "observation" in SEVERITY_PRIORITY
