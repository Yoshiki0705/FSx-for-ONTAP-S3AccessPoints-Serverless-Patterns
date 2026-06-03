"""UC22 Transportation Maintenance — Processing Lambda unit tests.

Tests for deterioration_detector and maintenance_extractor handlers.
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

# Dynamic module loading — deterioration_detector
_det_handler_path = os.path.join(
    os.path.dirname(__file__),
    "..",
    "functions",
    "deterioration_detector",
    "handler.py",
)
_det_spec = importlib.util.spec_from_file_location(
    "uc22_deterioration_handler", _det_handler_path
)
_det_module = importlib.util.module_from_spec(_det_spec)
sys.modules["uc22_deterioration_handler"] = _det_module
_det_spec.loader.exec_module(_det_module)

is_safety_critical = _det_module.is_safety_critical
parse_safety_critical_categories = _det_module.parse_safety_critical_categories
check_image_resolution = _det_module.check_image_resolution
SEVERITY_LEVELS = _det_module.SEVERITY_LEVELS

# Dynamic module loading — maintenance_extractor
_maint_handler_path = os.path.join(
    os.path.dirname(__file__),
    "..",
    "functions",
    "maintenance_extractor",
    "handler.py",
)
_maint_spec = importlib.util.spec_from_file_location(
    "uc22_maintenance_handler", _maint_handler_path
)
_maint_module = importlib.util.module_from_spec(_maint_spec)
sys.modules["uc22_maintenance_handler"] = _maint_module
_maint_spec.loader.exec_module(_maint_module)

extract_lifecycle_data = _maint_module.extract_lifecycle_data


class TestSafetyCriticalClassification:
    """安全重要インフラの分類ロジックテスト."""

    def test_bridges_is_safety_critical(self):
        categories = parse_safety_critical_categories("bridges,signaling,rail-joints")
        result = is_safety_critical(
            "inspections/bridges/route-1/2026-01-15/img001.jpg",
            categories,
        )
        assert result is True

    def test_signaling_is_safety_critical(self):
        categories = parse_safety_critical_categories("bridges,signaling,rail-joints")
        result = is_safety_critical(
            "inspections/signaling/station-a/2026-02-01/sig_005.png",
            categories,
        )
        assert result is True

    def test_rail_joints_is_safety_critical(self):
        categories = parse_safety_critical_categories("bridges,signaling,rail-joints")
        result = is_safety_critical(
            "inspections/rail-joints/segment-12/joint_003.tiff",
            categories,
        )
        assert result is True

    def test_standard_track_not_safety_critical(self):
        categories = parse_safety_critical_categories("bridges,signaling,rail-joints")
        result = is_safety_critical(
            "inspections/tracks/mainline/km-150/track_001.jpg",
            categories,
        )
        assert result is False

    def test_platform_not_safety_critical(self):
        categories = parse_safety_critical_categories("bridges,signaling,rail-joints")
        result = is_safety_critical(
            "inspections/platforms/station-b/platform_floor.jpg",
            categories,
        )
        assert result is False

    def test_case_insensitive_matching(self):
        categories = parse_safety_critical_categories("bridges,signaling,rail-joints")
        result = is_safety_critical(
            "inspections/BRIDGES/route-1/2026-01-15/img001.jpg",
            categories,
        )
        assert result is True

    def test_custom_categories(self):
        categories = parse_safety_critical_categories("tunnels,crossings")
        result = is_safety_critical(
            "inspections/tunnels/tunnel-A/entrance.jpg",
            categories,
        )
        assert result is True


class TestImageResolutionCheck:
    """画像解像度チェックのテスト."""

    def test_adequate_resolution(self):
        result = check_image_resolution(
            {"width": 1920, "height": 1080, "file_size": 2048000},
            1024,
            768,
        )
        assert result["adequate"] is True
        assert "status" not in result

    def test_minimum_resolution_passes(self):
        result = check_image_resolution(
            {"width": 1024, "height": 768, "file_size": 1024000},
            1024,
            768,
        )
        assert result["adequate"] is True

    def test_low_width_fails(self):
        result = check_image_resolution(
            {"width": 800, "height": 1080, "file_size": 500000},
            1024,
            768,
        )
        assert result["adequate"] is False
        assert result["status"] == "requires-reinspection"

    def test_low_height_fails(self):
        result = check_image_resolution(
            {"width": 1920, "height": 600, "file_size": 500000},
            1024,
            768,
        )
        assert result["adequate"] is False
        assert result["status"] == "requires-reinspection"

    def test_both_dimensions_low(self):
        result = check_image_resolution(
            {"width": 640, "height": 480, "file_size": 200000},
            1024,
            768,
        )
        assert result["adequate"] is False
        assert result["min_required_width"] == 1024
        assert result["min_required_height"] == 768

    def test_zero_dimensions(self):
        result = check_image_resolution(
            {"width": 0, "height": 0, "file_size": 0},
            1024,
            768,
        )
        assert result["adequate"] is False


class TestSeverityLevels:
    """重大度レベルの定義テスト."""

    def test_severity_levels_defined(self):
        assert SEVERITY_LEVELS == ["critical", "major", "minor", "observation"]

    def test_severity_has_four_levels(self):
        assert len(SEVERITY_LEVELS) == 4


class TestLifecycleDataExtraction:
    """ライフサイクルデータ抽出のテスト."""

    def test_extract_installation_date(self):
        text = "設備番号: EQ-001\n設置日: 2015-04-01\n最終修理: 2024-12-15"
        entities = [
            {"text": "2015-04-01", "type": "DATE", "score": 0.95, "begin_offset": 0, "end_offset": 0},
            {"text": "2024-12-15", "type": "DATE", "score": 0.92, "begin_offset": 0, "end_offset": 0},
            {"text": "EQ-001", "type": "OTHER", "score": 0.88, "begin_offset": 0, "end_offset": 0},
        ]
        key_phrases = []

        result = extract_lifecycle_data(text, entities, key_phrases)
        assert result["installation_date"] == "2015-04-01"
        assert result["last_repair_date"] == "2024-12-15"
        assert result["equipment_id"] == "EQ-001"

    def test_empty_text_returns_none_fields(self):
        result = extract_lifecycle_data("", [], [])
        assert result["installation_date"] is None
        assert result["last_repair_date"] is None
        assert result["component_age_days"] is None
        assert result["replacement_schedule"] is None

    def test_repair_history_extraction(self):
        text = "修理履歴:\n2023-06-01 — レール研磨修理を実施\n2024-01-15 — ボルト交換"
        entities = [
            {"text": "2023-06-01", "type": "DATE", "score": 0.9, "begin_offset": 0, "end_offset": 0},
            {"text": "2024-01-15", "type": "DATE", "score": 0.9, "begin_offset": 0, "end_offset": 0},
        ]
        key_phrases = []

        result = extract_lifecycle_data(text, entities, key_phrases)
        assert len(result["repair_history"]) >= 1
