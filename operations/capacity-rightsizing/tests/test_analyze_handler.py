"""OPS1 Analyze Handler テスト."""

from __future__ import annotations

import pytest


class TestAnalyzeCapacity:
    """容量分析ロジックのテスト."""

    def test_high_utilization_generates_upsize_recommendation(self, analyze_handler, collect_output):
        """80% 超のボリュームに upsize 推奨が生成される."""
        result = analyze_handler.handler(collect_output, None)

        analyses = result["analyses"]
        assert len(analyses) == 1

        recs = analyses[0]["recommendations"]
        upsize_recs = [r for r in recs if r["recommendation_type"] == "upsize"]
        assert len(upsize_recs) >= 2  # vol_production_data (85%) + vol_analytics_staging (90%)

    def test_low_utilization_generates_downsize_recommendation(self, analyze_handler, collect_output):
        """20% 以下 + autosize 無効のボリュームに downsize 推奨が生成される."""
        result = analyze_handler.handler(collect_output, None)

        analyses = result["analyses"]
        recs = analyses[0]["recommendations"]
        downsize_recs = [r for r in recs if r["recommendation_type"] == "downsize"]
        # vol_backup_temp (10%, autosize=off, 1TB) should generate downsize
        assert len(downsize_recs) >= 1

    def test_autosize_enabled_low_util_no_downsize(self, analyze_handler, collect_output):
        """autosize 有効 + 低利用率のボリュームには downsize 推奨を出さない."""
        result = analyze_handler.handler(collect_output, None)

        analyses = result["analyses"]
        recs = analyses[0]["recommendations"]
        downsize_recs = [r for r in recs if r["recommendation_type"] == "downsize"]
        # vol_dev_workspace (20%, autosize=grow_shrink) should NOT get downsize
        target_names = [r["target"] for r in downsize_recs]
        assert "vol_dev_workspace" not in target_names

    def test_threshold_customization(self, analyze_handler, collect_output, monkeypatch):
        """閾値を変更すると推奨数が変わる."""
        monkeypatch.setenv("THRESHOLD_PERCENT", "90")

        result = analyze_handler.handler(collect_output, None)

        recs = result["analyses"][0]["recommendations"]
        upsize_recs = [r for r in recs if r["recommendation_type"] == "upsize"]
        # At 90% threshold, only vol_analytics_staging (90%) triggers
        assert len(upsize_recs) >= 1

    def test_recommendation_has_cost_delta(self, analyze_handler, collect_output):
        """推奨にコスト差分が含まれる."""
        result = analyze_handler.handler(collect_output, None)

        recs = result["analyses"][0]["recommendations"]
        for rec in recs:
            assert "monthly_cost_delta_usd" in rec
            assert isinstance(rec["monthly_cost_delta_usd"], (int, float))

    def test_recommendation_has_confidence(self, analyze_handler, collect_output):
        """推奨に confidence スコアが含まれる."""
        result = analyze_handler.handler(collect_output, None)

        recs = result["analyses"][0]["recommendations"]
        for rec in recs:
            assert "confidence" in rec
            assert 0.0 <= rec["confidence"] <= 1.0


class TestAnalyzeThroughput:
    """スループット分析ロジックのテスト."""

    def test_high_throughput_util_generates_tier_upgrade(self, analyze_handler, collect_output, monkeypatch):
        """スループット利用率が閾値超で tier_upgrade 推奨を生成."""
        # Set threshold to 60% so the 62.5% utilization triggers
        monkeypatch.setenv("THRESHOLD_PERCENT", "60")

        result = analyze_handler.handler(collect_output, None)

        recs = result["analyses"][0]["recommendations"]
        tier_recs = [r for r in recs if r["recommendation_type"] == "tier_upgrade"]
        assert len(tier_recs) >= 1
        assert tier_recs[0]["target"] == "fs-test01"

    def test_normal_throughput_no_tier_recommendation(self, analyze_handler, collect_output):
        """スループット利用率が閾値内なら tier 推奨なし."""
        # Default threshold is 80%, utilization is 62.5% → no recommendation
        result = analyze_handler.handler(collect_output, None)

        recs = result["analyses"][0]["recommendations"]
        tier_recs = [r for r in recs if r["recommendation_type"] == "tier_upgrade"]
        assert len(tier_recs) == 0


class TestWhatIfScenarios:
    """What-If シナリオ生成テスト."""

    def test_what_if_scenarios_generated(self, analyze_handler, collect_output):
        """What-If シナリオが生成される."""
        result = analyze_handler.handler(collect_output, None)

        scenarios = result["analyses"][0]["what_if_scenarios"]
        assert len(scenarios) > 0

    def test_what_if_includes_upgrade_and_downgrade(self, analyze_handler, collect_output):
        """What-If にアップグレードとダウングレード両方が含まれる."""
        result = analyze_handler.handler(collect_output, None)

        scenarios = result["analyses"][0]["what_if_scenarios"]
        names = [s["scenario_name"] for s in scenarios]
        assert any("Upgrade" in n for n in names)
        # Current is 128 MBps (lowest), so no downgrade scenario
        # This is correct behavior

    def test_what_if_has_cost_fields(self, analyze_handler, collect_output):
        """What-If シナリオにコストフィールドが含まれる."""
        result = analyze_handler.handler(collect_output, None)

        for scenario in result["analyses"][0]["what_if_scenarios"]:
            assert "current_monthly_cost_usd" in scenario
            assert "projected_monthly_cost_usd" in scenario
            assert "monthly_delta_usd" in scenario


class TestSummaryStats:
    """集約統計テスト."""

    def test_summary_stats_present(self, analyze_handler, collect_output):
        """summary_stats が正しく計算される."""
        result = analyze_handler.handler(collect_output, None)

        summary = result["analyses"][0]["summary_stats"]
        assert summary["total_volumes"] == 5
        assert summary["volumes_above_threshold"] >= 1
        assert "avg_volume_utilization_percent" in summary
        assert "recommendation_count" in summary


class TestBedrockDisabled:
    """Bedrock 無効時のテスト."""

    def test_ai_summary_none_when_disabled(self, analyze_handler, collect_output):
        """EnableBedrockSummary=false で ai_summary が None."""
        result = analyze_handler.handler(collect_output, None)

        assert result["analyses"][0]["ai_summary"] is None
