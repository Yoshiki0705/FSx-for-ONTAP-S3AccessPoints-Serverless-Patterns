"""UC21 Agri-Food Traceability — Report Lambda unit tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# Dynamic import for namespace isolation
_handler_path = Path(__file__).parent.parent / "functions" / "report" / "handler.py"
_spec = importlib.util.spec_from_file_location("agri_report_handler", _handler_path)
_module = importlib.util.module_from_spec(_spec)
sys.modules["agri_report_handler"] = _module
_spec.loader.exec_module(_module)

aggregate_crop_results = _module.aggregate_crop_results
aggregate_traceability_results = _module.aggregate_traceability_results


class TestAggregateCropResults:
    """作物分析結果集約のテスト"""

    def test_basic_aggregation(self):
        results = [
            {
                "status": "success",
                "key": "field-a/img1.tif",
                "location_status": "verified",
                "geolocation": {"latitude": 35.68, "longitude": 139.76},
                "anomalies": {
                    "confirmed": [
                        {"anomaly_type": "pest_damage", "confidence": 0.85},
                    ],
                    "review_required": [],
                },
            },
            {
                "status": "success",
                "key": "field-b/img2.jpg",
                "location_status": "location-unverified",
                "geolocation": None,
                "anomalies": {
                    "confirmed": [],
                    "review_required": [
                        {"anomaly_type": "irrigation_issue", "confidence": 0.65},
                    ],
                },
            },
        ]

        summary = aggregate_crop_results(results)

        assert summary["total_images_analyzed"] == 2
        assert summary["success_count"] == 2
        assert summary["error_count"] == 0
        assert summary["location_status"]["verified"] == 1
        assert summary["location_status"]["unverified"] == 1
        assert summary["anomaly_summary"]["total_confirmed"] == 1
        assert summary["anomaly_summary"]["total_review_required"] == 1
        assert summary["anomaly_summary"]["anomaly_type_distribution"]["pest_damage"] == 1

    def test_with_errors(self):
        results = [
            {"status": "success", "location_status": "verified", "geolocation": None, "anomalies": {"confirmed": [], "review_required": []}},
            {"status": "error", "error": {"type": "ServiceError", "message": "timeout"}},
        ]

        summary = aggregate_crop_results(results)

        assert summary["total_images_analyzed"] == 2
        assert summary["success_count"] == 1
        assert summary["error_count"] == 1

    def test_empty_results(self):
        summary = aggregate_crop_results([])

        assert summary["total_images_analyzed"] == 0
        assert summary["success_count"] == 0
        assert summary["anomaly_summary"]["total_confirmed"] == 0

    def test_affected_coordinates_collected(self):
        """Requirement 5.4: 座標付き異常レポート"""
        results = [
            {
                "status": "success",
                "key": "field/img.tif",
                "location_status": "verified",
                "geolocation": {"latitude": 35.5, "longitude": 139.7},
                "anomalies": {
                    "confirmed": [
                        {"anomaly_type": "pest_damage", "confidence": 0.90},
                    ],
                    "review_required": [],
                },
            },
        ]

        summary = aggregate_crop_results(results)

        assert len(summary["affected_areas"]) == 1
        assert summary["affected_areas"][0]["latitude"] == 35.5
        assert summary["affected_areas"][0]["anomaly_count"] == 1


class TestAggregateTraceabilityResults:
    """トレーサビリティ結果集約のテスト"""

    def test_basic_aggregation(self):
        results = [
            {
                "status": "success",
                "extracted_fields": {"lot_id": "LOT-001"},
                "classification": {"classification_confidence": 0.92, "status": "classified"},
            },
            {
                "status": "success",
                "extracted_fields": {"lot_id": "LOT-001"},
                "classification": {"classification_confidence": 0.88, "status": "classified"},
            },
            {
                "status": "success",
                "extracted_fields": {"lot_id": "LOT-002"},
                "classification": {"classification_confidence": 0.75, "status": "review-required"},
            },
        ]

        summary = aggregate_traceability_results(results)

        assert summary["total_documents_processed"] == 3
        assert summary["success_count"] == 3
        assert summary["lot_summary"]["unique_lots"] == 2
        assert summary["lot_summary"]["documents_per_lot"]["LOT-001"] == 2
        assert summary["lot_summary"]["documents_per_lot"]["LOT-002"] == 1
        assert summary["classification_summary"]["classified"] == 2
        assert summary["classification_summary"]["review_required"] == 1

    def test_confidence_distribution(self):
        """Requirement 5.4: 信頼度分布レポート"""
        results = [
            {
                "status": "success",
                "extracted_fields": {"lot_id": "LOT-A"},
                "classification": {"classification_confidence": 0.95, "status": "classified"},
            },
            {
                "status": "success",
                "extracted_fields": {"lot_id": "LOT-B"},
                "classification": {"classification_confidence": 0.60, "status": "review-required"},
            },
        ]

        summary = aggregate_traceability_results(results)
        dist = summary["classification_summary"]["confidence_distribution"]

        assert dist["min"] == pytest.approx(0.60, abs=0.01)
        assert dist["max"] == pytest.approx(0.95, abs=0.01)
        assert dist["mean"] == pytest.approx(0.775, abs=0.01)
        assert dist["above_threshold"] == 1
        assert dist["below_threshold"] == 1

    def test_empty_results(self):
        summary = aggregate_traceability_results([])

        assert summary["total_documents_processed"] == 0
        assert summary["lot_summary"]["unique_lots"] == 0
        assert summary["classification_summary"]["confidence_distribution"]["min"] == 0.0

    def test_with_errors(self):
        results = [
            {
                "status": "success",
                "extracted_fields": {"lot_id": "LOT-X"},
                "classification": {"classification_confidence": 0.85, "status": "classified"},
            },
            {
                "status": "error",
                "error": {"type": "TextractError", "message": "Failed"},
            },
        ]

        summary = aggregate_traceability_results(results)

        assert summary["total_documents_processed"] == 2
        assert summary["success_count"] == 1
        assert summary["error_count"] == 1

    def test_unknown_lot_id(self):
        """ロットID が抽出できない場合は 'unknown' にグループ化"""
        results = [
            {
                "status": "success",
                "extracted_fields": {"lot_id": None},
                "classification": {"classification_confidence": 0.82, "status": "classified"},
            },
        ]

        summary = aggregate_traceability_results(results)

        assert summary["lot_summary"]["documents_per_lot"]["unknown"] == 1
