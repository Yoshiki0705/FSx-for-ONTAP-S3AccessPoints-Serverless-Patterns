"""UC22 Transportation Maintenance — Discovery Lambda unit tests."""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

# Dynamic module loading for namespace isolation
_handler_path = os.path.join(
    os.path.dirname(__file__),
    "..",
    "functions",
    "discovery",
    "handler.py",
)
_spec = importlib.util.spec_from_file_location("uc22_discovery_handler", _handler_path)
_module = importlib.util.module_from_spec(_spec)
sys.modules["uc22_discovery_handler"] = _module
_spec.loader.exec_module(_module)

classify_file = _module.classify_file


class TestClassifyFile:
    """Discovery ファイル分類ロジックのテスト."""

    def test_inspection_image_jpeg(self):
        result = classify_file(
            "inspections/route-1/2026-01-15/img001.jpg",
            "inspections/",
            "maintenance-reports/",
        )
        assert result == "inspection_image"

    def test_inspection_image_png(self):
        result = classify_file(
            "inspections/bridges/route-3/2026-02-20/bridge_001.png",
            "inspections/",
            "maintenance-reports/",
        )
        assert result == "inspection_image"

    def test_inspection_image_tiff(self):
        result = classify_file(
            "inspections/signaling/2026-03-01/signal_042.tiff",
            "inspections/",
            "maintenance-reports/",
        )
        assert result == "inspection_image"

    def test_maintenance_report_pdf(self):
        result = classify_file(
            "maintenance-reports/2026/01/bridge_repair_report.pdf",
            "inspections/",
            "maintenance-reports/",
        )
        assert result == "maintenance_report"

    def test_maintenance_report_excel(self):
        result = classify_file(
            "maintenance-reports/quarterly/lifecycle_data.xlsx",
            "inspections/",
            "maintenance-reports/",
        )
        assert result == "maintenance_report"

    def test_non_matching_prefix(self):
        result = classify_file(
            "other/random_file.jpg",
            "inspections/",
            "maintenance-reports/",
        )
        assert result is None

    def test_unsupported_extension(self):
        result = classify_file(
            "inspections/route-1/2026-01-15/data.csv",
            "inspections/",
            "maintenance-reports/",
        )
        assert result is None

    def test_empty_key(self):
        result = classify_file("", "inspections/", "maintenance-reports/")
        assert result is None

    def test_no_extension(self):
        result = classify_file(
            "inspections/route-1/README",
            "inspections/",
            "maintenance-reports/",
        )
        assert result is None

    def test_case_insensitive_extension(self):
        result = classify_file(
            "inspections/route-1/photo.JPEG",
            "inspections/",
            "maintenance-reports/",
        )
        assert result == "inspection_image"

    def test_tif_extension(self):
        result = classify_file(
            "inspections/rail-joints/scan.tif",
            "inspections/",
            "maintenance-reports/",
        )
        assert result == "inspection_image"

    def test_xls_extension(self):
        result = classify_file(
            "maintenance-reports/old/legacy_data.xls",
            "inspections/",
            "maintenance-reports/",
        )
        assert result == "maintenance_report"
