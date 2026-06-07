"""UC20 Travel Document Processing — Report Lambda unit tests."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Dynamic import — report handler
_rpt_path = Path(__file__).parent.parent / "functions" / "report" / "handler.py"
_rpt_spec = importlib.util.spec_from_file_location("travel_report_handler", _rpt_path)
_rpt_module = importlib.util.module_from_spec(_rpt_spec)
sys.modules["travel_report_handler"] = _rpt_module
_rpt_spec.loader.exec_module(_rpt_module)

aggregate_reservation_results = _rpt_module.aggregate_reservation_results
aggregate_facility_results = _rpt_module.aggregate_facility_results
generate_human_readable_report = _rpt_module.generate_human_readable_report


class TestAggregateReservationResults:
    """予約結果集約のテスト"""

    def test_all_success(self):
        results = [
            {
                "status": "success",
                "extracted_data": {
                    "guest_name": "田中太郎",
                    "check_in_date": "2026-01-15",
                    "check_out_date": "2026-01-18",
                    "room_type": "ツイン",
                    "amount": "¥50,000",
                    "language_detected": "ja",
                },
            },
            {
                "status": "success",
                "extracted_data": {
                    "guest_name": "John Smith",
                    "check_in_date": "2026-02-01",
                    "check_out_date": None,
                    "room_type": "double",
                    "amount": "$350",
                    "language_detected": "en",
                },
            },
        ]
        summary = aggregate_reservation_results(results)
        assert summary["total_processed"] == 2
        assert summary["success_count"] == 2
        assert summary["error_count"] == 0
        assert summary["extraction_completeness"]["guest_name"]["count"] == 2
        assert summary["languages_detected"]["ja"] == 1
        assert summary["languages_detected"]["en"] == 1

    def test_mixed_success_error(self):
        results = [
            {
                "status": "success",
                "extracted_data": {
                    "guest_name": "Test",
                    "check_in_date": "2026-01-01",
                    "check_out_date": None,
                    "room_type": None,
                    "amount": None,
                    "language_detected": "ja",
                },
            },
            {"status": "error", "errors": [{"details": "extraction failed"}]},
        ]
        summary = aggregate_reservation_results(results)
        assert summary["total_processed"] == 2
        assert summary["success_count"] == 1
        assert summary["error_count"] == 1

    def test_empty_results(self):
        summary = aggregate_reservation_results([])
        assert summary["total_processed"] == 0
        assert summary["success_count"] == 0
        assert summary["error_count"] == 0


class TestAggregateFacilityResults:
    """施設点検結果集約のテスト"""

    def test_all_success(self):
        results = [
            {
                "status": "success",
                "cleanliness_score": 85,
                "damages": [{"type": "Crack", "confidence": 90.0}],
            },
            {
                "status": "success",
                "cleanliness_score": 92,
                "damages": [],
            },
        ]
        summary = aggregate_facility_results(results)
        assert summary["total_inspected"] == 2
        assert summary["success_count"] == 2
        assert summary["error_count"] == 0
        assert summary["cleanliness_scores"]["average"] == 88.5
        assert summary["cleanliness_scores"]["minimum"] == 85
        assert summary["cleanliness_scores"]["maximum"] == 92
        assert summary["damage_summary"]["total_damage_instances"] == 1

    def test_condition_distribution(self):
        results = [
            {"status": "success", "cleanliness_score": 95, "damages": []},
            {"status": "success", "cleanliness_score": 75, "damages": []},
            {"status": "success", "cleanliness_score": 55, "damages": []},
            {"status": "success", "cleanliness_score": 30, "damages": []},
        ]
        summary = aggregate_facility_results(results)
        assert summary["condition_distribution"]["excellent"] == 1
        assert summary["condition_distribution"]["good"] == 1
        assert summary["condition_distribution"]["fair"] == 1
        assert summary["condition_distribution"]["poor"] == 1

    def test_empty_results(self):
        summary = aggregate_facility_results([])
        assert summary["total_inspected"] == 0
        assert summary["cleanliness_scores"]["average"] == 0.0


class TestGenerateHumanReadableReport:
    """人間可読レポート生成のテスト"""

    def test_report_contains_sections(self):
        reservation_summary = {
            "total_processed": 5,
            "success_count": 4,
            "error_count": 1,
            "extraction_completeness": {
                "guest_name": {"count": 4, "rate": 100.0},
                "check_in_date": {"count": 4, "rate": 100.0},
                "check_out_date": {"count": 3, "rate": 75.0},
                "room_type": {"count": 3, "rate": 75.0},
                "amount": {"count": 4, "rate": 100.0},
            },
            "languages_detected": {"ja": 3, "en": 1},
            "room_type_distribution": {"ツイン": 2, "double": 1},
        }
        facility_summary = {
            "total_inspected": 3,
            "success_count": 3,
            "error_count": 0,
            "cleanliness_scores": {"average": 80.0, "minimum": 65, "maximum": 95},
            "condition_distribution": {
                "excellent": 1,
                "good": 1,
                "fair": 1,
                "poor": 0,
            },
            "damage_summary": {
                "total_damage_instances": 2,
                "damage_types": {"Crack": 1, "Stain": 1},
            },
        }
        report = generate_human_readable_report(reservation_summary, facility_summary, "2026-06-15")
        assert "予約文書処理サマリ" in report
        assert "施設状態トレンド" in report
        assert "処理件数: 5" in report
        assert "点検件数: 3" in report
        assert "Excellent" in report
        assert "Crack: 1" in report
