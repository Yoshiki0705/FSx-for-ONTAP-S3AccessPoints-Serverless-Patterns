"""OPS3 Analyze Handler テスト."""

from __future__ import annotations

import pytest


class TestTieringAnalysis:
    def test_none_policy_gets_recommendation(self, analyze_handler, collect_output):
        """tiering_policy=none のボリュームに推奨が生成される."""
        result = analyze_handler.handler(collect_output, None)
        recs = result["analyses"][0]["recommendations"]
        none_recs = [r for r in recs if r["current_policy"] == "none"]
        assert len(none_recs) >= 2  # vol_dev_workspace + vol_backup_temp

    def test_recommendation_suggests_auto(self, analyze_handler, collect_output):
        """none → auto が推奨される."""
        result = analyze_handler.handler(collect_output, None)
        recs = result["analyses"][0]["recommendations"]
        for r in [rec for rec in recs if rec["current_policy"] == "none"]:
            assert r["recommended_policy"] == "auto"

    def test_snapshot_only_with_large_cloud_gets_upgrade(self, analyze_handler, collect_output):
        """snapshot-only で大量の Capacity Pool 使用時に auto 推奨."""
        result = analyze_handler.handler(collect_output, None)
        recs = result["analyses"][0]["recommendations"]
        archive_rec = [r for r in recs if r["volume_name"] == "vol_archive_2023"]
        assert len(archive_rec) == 1
        assert archive_rec[0]["recommended_policy"] == "auto"

    def test_savings_estimate_positive(self, analyze_handler, collect_output):
        """推奨に正の節約額が含まれる."""
        result = analyze_handler.handler(collect_output, None)
        recs = result["analyses"][0]["recommendations"]
        for r in recs:
            assert r["estimated_monthly_savings_usd"] > 0

    def test_summary_has_policy_distribution(self, analyze_handler, collect_output):
        """サマリにポリシー分布が含まれる."""
        result = analyze_handler.handler(collect_output, None)
        summary = result["analyses"][0]["summary"]
        assert "policy_distribution" in summary
        assert summary["policy_distribution"]["none"] == 2
        assert summary["policy_distribution"]["auto"] == 2

    def test_total_potential_savings(self, analyze_handler, collect_output):
        """合計削減見込が計算される."""
        result = analyze_handler.handler(collect_output, None)
        summary = result["analyses"][0]["summary"]
        assert summary["total_potential_savings_usd"] > 0

    def test_bedrock_disabled_no_summary(self, analyze_handler, collect_output):
        """Bedrock 無効で ai_summary が None."""
        result = analyze_handler.handler(collect_output, None)
        assert result["analyses"][0]["ai_summary"] is None


class TestCollectDemoMode:
    def test_collect_returns_tiering_data(self, collect_handler):
        """DemoMode でティアリングデータが返る."""
        result = collect_handler.handler({}, None)
        assert len(result["file_systems"]) == 1
        vols = result["file_systems"][0]["volumes"]
        assert len(vols) == 5
        for v in vols:
            assert "tiering_policy" in v
            assert "cooling_period_days" in v
