"""UC25 Utilities Asset Inspection — Report Lambda unit tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# Dynamic import for namespace isolation
_handler_path = Path(__file__).parent.parent / "functions" / "report" / "handler.py"
_spec = importlib.util.spec_from_file_location("utilities_report_handler", _handler_path)
_module = importlib.util.module_from_spec(_spec)
sys.modules["utilities_report_handler"] = _module
_spec.loader.exec_module(_module)

compute_equipment_condition = _module.compute_equipment_condition
generate_maintenance_schedule = _module.generate_maintenance_schedule


class TestComputeEquipmentCondition:
    """設備状態評価のテスト"""

    def test_critical_condition(self):
        defect_results = [
            {
                "status": "success",
                "equipment_id": "EQ-001",
                "defects": [
                    {"severity": "critical", "defect_type": "insulator_damage"},
                ],
            }
        ]
        result = compute_equipment_condition(defect_results, [], [])
        assert "EQ-001" in result
        assert result["EQ-001"]["overall_condition"] == "critical"
        assert result["EQ-001"]["critical_defects"] == 1

    def test_degraded_condition_major_defects(self):
        defect_results = [
            {
                "status": "success",
                "equipment_id": "EQ-002",
                "defects": [
                    {"severity": "major", "defect_type": "conductor_sag"},
                ],
            }
        ]
        result = compute_equipment_condition(defect_results, [], [])
        assert result["EQ-002"]["overall_condition"] == "degraded"

    def test_degraded_condition_hot_spots(self):
        thermal_results = [
            {
                "status": "success",
                "equipment_id": "EQ-003",
                "hot_spots": [
                    {"component_id": "a"},
                    {"component_id": "b"},
                    {"component_id": "c"},
                ],
            }
        ]
        result = compute_equipment_condition([], [], thermal_results)
        assert result["EQ-003"]["overall_condition"] == "degraded"
        assert result["EQ-003"]["hot_spot_count"] == 3

    def test_fair_condition_minor_defects(self):
        defect_results = [
            {
                "status": "success",
                "equipment_id": "EQ-004",
                "defects": [
                    {"severity": "minor", "defect_type": "vegetation_encroachment"},
                    {"severity": "minor", "defect_type": "vegetation_encroachment"},
                    {"severity": "minor", "defect_type": "vegetation_encroachment"},
                ],
            }
        ]
        result = compute_equipment_condition(defect_results, [], [])
        assert result["EQ-004"]["overall_condition"] == "fair"

    def test_good_condition(self):
        defect_results = [
            {
                "status": "success",
                "equipment_id": "EQ-005",
                "defects": [
                    {"severity": "minor", "defect_type": "vegetation_encroachment"},
                ],
            }
        ]
        result = compute_equipment_condition(defect_results, [], [])
        assert result["EQ-005"]["overall_condition"] == "good"

    def test_skips_error_results(self):
        defect_results = [
            {
                "status": "error",
                "equipment_id": "EQ-ERR",
                "error_message": "failed",
            }
        ]
        result = compute_equipment_condition(defect_results, [], [])
        assert "EQ-ERR" not in result

    def test_empty_inputs(self):
        result = compute_equipment_condition([], [], [])
        assert result == {}

    def test_multiple_equipment(self):
        defect_results = [
            {
                "status": "success",
                "equipment_id": "EQ-A",
                "defects": [{"severity": "critical", "defect_type": "damage"}],
            },
            {
                "status": "success",
                "equipment_id": "EQ-B",
                "defects": [{"severity": "minor", "defect_type": "veg"}],
            },
        ]
        result = compute_equipment_condition(defect_results, [], [])
        assert result["EQ-A"]["overall_condition"] == "critical"
        assert result["EQ-B"]["overall_condition"] == "good"


class TestGenerateMaintenanceSchedule:
    """予測保全スケジュール生成のテスト"""

    def test_critical_equipment(self):
        conditions = {
            "EQ-001": {
                "defect_count": 2,
                "critical_defects": 1,
                "major_defects": 0,
                "minor_defects": 1,
                "anomaly_count": 0,
                "hot_spot_count": 0,
                "overall_condition": "critical",
            }
        }
        schedule = generate_maintenance_schedule(conditions)
        assert len(schedule) == 1
        assert schedule[0]["days_until_maintenance"] == 1
        assert schedule[0]["priority"] == "immediate"
        assert schedule[0]["recommended_action"] == "emergency_inspection"

    def test_degraded_equipment(self):
        conditions = {
            "EQ-002": {
                "defect_count": 1,
                "critical_defects": 0,
                "major_defects": 1,
                "minor_defects": 0,
                "anomaly_count": 0,
                "hot_spot_count": 0,
                "overall_condition": "degraded",
            }
        }
        schedule = generate_maintenance_schedule(conditions)
        assert schedule[0]["days_until_maintenance"] == 14
        assert schedule[0]["priority"] == "high"

    def test_good_equipment(self):
        conditions = {
            "EQ-003": {
                "defect_count": 0,
                "critical_defects": 0,
                "major_defects": 0,
                "minor_defects": 0,
                "anomaly_count": 0,
                "hot_spot_count": 0,
                "overall_condition": "good",
            }
        }
        schedule = generate_maintenance_schedule(conditions)
        assert schedule[0]["days_until_maintenance"] == 180
        assert schedule[0]["priority"] == "low"
        assert schedule[0]["recommended_action"] == "routine_inspection"

    def test_schedule_sorted_by_priority(self):
        conditions = {
            "EQ-LOW": {
                "defect_count": 0,
                "critical_defects": 0,
                "major_defects": 0,
                "minor_defects": 0,
                "anomaly_count": 0,
                "hot_spot_count": 0,
                "overall_condition": "good",
            },
            "EQ-HIGH": {
                "defect_count": 1,
                "critical_defects": 1,
                "major_defects": 0,
                "minor_defects": 0,
                "anomaly_count": 0,
                "hot_spot_count": 0,
                "overall_condition": "critical",
            },
        }
        schedule = generate_maintenance_schedule(conditions)
        assert schedule[0]["equipment_id"] == "EQ-HIGH"
        assert schedule[1]["equipment_id"] == "EQ-LOW"

    def test_days_within_1_365_range(self):
        conditions = {
            "EQ-001": {
                "defect_count": 0,
                "critical_defects": 0,
                "major_defects": 0,
                "minor_defects": 0,
                "anomaly_count": 0,
                "hot_spot_count": 0,
                "overall_condition": "good",
            },
            "EQ-002": {
                "defect_count": 5,
                "critical_defects": 3,
                "major_defects": 0,
                "minor_defects": 2,
                "anomaly_count": 0,
                "hot_spot_count": 0,
                "overall_condition": "critical",
            },
        }
        schedule = generate_maintenance_schedule(conditions)
        for entry in schedule:
            assert 1 <= entry["days_until_maintenance"] <= 365

    def test_empty_conditions(self):
        schedule = generate_maintenance_schedule({})
        assert schedule == []
