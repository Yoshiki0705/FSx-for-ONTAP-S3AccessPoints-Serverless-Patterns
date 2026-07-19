"""OPS1 Collect Handler テスト."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestCollectHandlerDemoMode:
    """DemoMode=true での Collect Handler テスト."""

    def test_collect_demo_mode_returns_volumes(self, collect_handler):
        """DemoMode で volume_space.json のデータが返る."""
        result = collect_handler.handler({}, None)

        assert "file_systems" in result
        assert len(result["file_systems"]) == 1
        assert result["demo_mode"] is True

        fs_data = result["file_systems"][0]
        assert fs_data["fs_id"] == "fs-test01"
        assert len(fs_data["volumes"]) == 5
        assert len(fs_data["aggregates"]) == 1
        assert "cloudwatch" in fs_data

    def test_collect_demo_mode_volume_has_required_fields(self, collect_handler):
        """DemoMode のボリュームデータが必須フィールドを持つ."""
        result = collect_handler.handler({}, None)
        vol = result["file_systems"][0]["volumes"][0]

        required_fields = [
            "name",
            "uuid",
            "svm_name",
            "size_bytes",
            "used_bytes",
            "available_bytes",
            "utilization_percent",
            "autosize_enabled",
            "autosize_mode",
            "fs_id",
        ]
        for field in required_fields:
            assert field in vol, f"Missing field: {field}"

    def test_collect_demo_mode_cloudwatch_has_required_fields(self, collect_handler):
        """DemoMode の CloudWatch データが必須フィールドを持つ."""
        result = collect_handler.handler({}, None)
        cw = result["file_systems"][0]["cloudwatch"]

        required_fields = [
            "storage_capacity_utilization_percent",
            "cpu_utilization_percent",
            "network_sent_bytes_per_sec",
            "network_received_bytes_per_sec",
            "is_gen2",
            "throughput_capacity_mbps",
        ]
        for field in required_fields:
            assert field in cw, f"Missing field: {field}"

    def test_collect_single_fs_override(self, collect_handler):
        """event.fs_id で単一 FS を指定できる."""
        result = collect_handler.handler({"fs_id": "fs-override01"}, None)

        assert result["file_systems"][0]["fs_id"] == "fs-override01"

    def test_collect_collected_at_is_iso8601(self, collect_handler):
        """collected_at が ISO 8601 形式."""
        result = collect_handler.handler({}, None)

        assert "collected_at" in result
        assert "T" in result["collected_at"]
        assert result["file_systems"][0]["collected_at"]


class TestCollectHandlerMultiFs:
    """複数 FS 対応テスト."""

    def test_collect_multiple_fs_ids(self, collect_handler, monkeypatch):
        """複数 FS ID が指定された場合、それぞれにデータを返す."""
        monkeypatch.setenv("FILE_SYSTEM_IDS", "fs-test01,fs-test02")

        result = collect_handler.handler({}, None)

        assert len(result["file_systems"]) == 2
        assert result["file_systems"][0]["fs_id"] == "fs-test01"
        assert result["file_systems"][1]["fs_id"] == "fs-test02"

    def test_collect_empty_fs_ids_returns_empty(self, collect_handler, monkeypatch):
        """空の FS ID リストでは空結果."""
        monkeypatch.setenv("FILE_SYSTEM_IDS", "")

        result = collect_handler.handler({}, None)

        assert result["file_systems"] == []
