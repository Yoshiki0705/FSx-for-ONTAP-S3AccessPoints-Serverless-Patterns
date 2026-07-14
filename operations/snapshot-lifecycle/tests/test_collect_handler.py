"""OPS4 Collect Handler テスト."""

from __future__ import annotations

import pytest


class TestCollectDemoMode:
    """DemoMode でのスナップショット収集テスト."""

    def test_collect_returns_volume_snapshots(self, collect_handler):
        """DemoMode でスナップショットデータが返る."""
        result = collect_handler.handler({}, None)

        assert "file_systems" in result
        assert len(result["file_systems"]) == 1
        fs_data = result["file_systems"][0]
        assert fs_data["fs_id"] == "fs-test01"
        assert "volume_snapshots" in fs_data
        assert len(fs_data["volume_snapshots"]) > 0

    def test_collect_groups_snapshots_by_volume(self, collect_handler):
        """スナップショットがボリューム別にグループ化される."""
        result = collect_handler.handler({}, None)

        fs_data = result["file_systems"][0]
        for vol_snap in fs_data["volume_snapshots"]:
            assert "volume_name" in vol_snap
            assert "volume_uuid" in vol_snap
            assert "snapshots" in vol_snap
            assert "snapshot_count" in vol_snap
            assert vol_snap["snapshot_count"] == len(vol_snap["snapshots"])

    def test_collect_includes_snapshot_policies(self, collect_handler):
        """Snapshot Policy 定義が含まれる."""
        result = collect_handler.handler({}, None)

        fs_data = result["file_systems"][0]
        assert "snapshot_policies" in fs_data
        assert len(fs_data["snapshot_policies"]) > 0
        policy = fs_data["snapshot_policies"][0]
        assert "name" in policy
        assert "schedules" in policy

    def test_collect_snapshot_has_age_days(self, collect_handler):
        """スナップショットに age_days フィールドが含まれる."""
        result = collect_handler.handler({}, None)

        fs_data = result["file_systems"][0]
        for vol_snap in fs_data["volume_snapshots"]:
            for snap in vol_snap["snapshots"]:
                assert "age_days" in snap
                assert isinstance(snap["age_days"], int)
