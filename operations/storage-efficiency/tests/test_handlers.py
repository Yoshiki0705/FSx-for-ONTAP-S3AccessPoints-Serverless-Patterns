"""OPS2 Storage Efficiency テスト."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestCollect:
    def test_collect_demo(self, collect_handler):
        result = collect_handler.handler({}, None)
        assert len(result["file_systems"]) == 1
        vols = result["file_systems"][0]["volumes"]
        assert len(vols) == 5
        for v in vols:
            assert "dedupe_enabled" in v
            assert "overall_ratio" in v


class TestAnalyze:
    def test_no_efficiency_gets_recommendation(self, analyze_handler, collect_output):
        result = analyze_handler.handler(collect_output, None)
        recs = result["analyses"][0]["recommendations"]
        # vol_dev has neither dedupe nor compression
        dev_recs = [r for r in recs if r["volume_name"] == "vol_dev"]
        assert len(dev_recs) == 1
        assert "Enable" in dev_recs[0]["recommendation"]

    def test_high_efficiency_no_recommendation(self, analyze_handler, collect_output):
        result = analyze_handler.handler(collect_output, None)
        recs = result["analyses"][0]["recommendations"]
        # vol_archive (3.2:1) should not get recommendation
        archive_recs = [r for r in recs if r["volume_name"] == "vol_archive"]
        assert len(archive_recs) == 0

    def test_summary_stats(self, analyze_handler, collect_output):
        result = analyze_handler.handler(collect_output, None)
        summary = result["analyses"][0]["summary"]
        assert summary["total_volumes"] == 3
        assert summary["volumes_with_both_enabled"] == 2
        assert summary["volumes_with_none"] == 1
        assert summary["avg_efficiency_ratio"] > 1.0

    def test_savings_calculated(self, analyze_handler, collect_output):
        result = analyze_handler.handler(collect_output, None)
        recs = result["analyses"][0]["recommendations"]
        for r in recs:
            if "Enable" in r.get("recommendation", ""):
                assert r["estimated_monthly_savings_usd"] > 0


class TestReport:
    def test_report_uploaded(self, report_handler, collect_output, analyze_handler):
        analyze_out = analyze_handler.handler(collect_output, None)
        with patch.object(report_handler, "boto3") as mock_boto3:
            mock_s3 = MagicMock()
            mock_boto3.client.side_effect = lambda svc, **kw: {
                "s3": mock_s3,
                "cloudwatch": MagicMock(),
                "sns": MagicMock(),
            }.get(svc, MagicMock())
            report_handler.handler(analyze_out, None)
            assert mock_s3.put_object.called
            assert "efficiency-report.json" in mock_s3.put_object.call_args_list[0].kwargs["Key"]
