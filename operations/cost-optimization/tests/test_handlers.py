"""OPS5 Cost Optimization テスト."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestCollect:
    def test_collect_demo(self, collect_handler):
        result = collect_handler.handler({}, None)
        assert len(result["file_systems"]) == 1
        fs = result["file_systems"][0]
        assert fs["fs_id"] == "fs-test01"
        assert fs["total_monthly_cost_usd"] > 0
        assert "monthly_cost_breakdown" in fs
        assert "ssd" in fs["monthly_cost_breakdown"]
        assert "throughput" in fs["monthly_cost_breakdown"]

    def test_cost_per_gb(self, collect_handler):
        result = collect_handler.handler({}, None)
        fs = result["file_systems"][0]
        assert fs["cost_per_gb_usd"] > 0


class TestAnalyze:
    def test_projection_calculated(self, analyze_handler, collect_handler):
        collect_out = collect_handler.handler({}, None)
        result = analyze_handler.handler(collect_out, None)
        summary = result["analyses"][0]["summary"]
        assert summary["projected_3month_cost_usd"] > summary["total_monthly_cost_usd"]
        assert summary["growth_rate_percent"] > 0

    def test_top_cost_driver_identified(self, analyze_handler, collect_handler):
        collect_out = collect_handler.handler({}, None)
        result = analyze_handler.handler(collect_out, None)
        summary = result["analyses"][0]["summary"]
        assert summary["top_cost_driver"] in ("ssd", "capacity_pool", "throughput", "backup")

    def test_bedrock_disabled(self, analyze_handler, collect_handler):
        collect_out = collect_handler.handler({}, None)
        result = analyze_handler.handler(collect_out, None)
        assert result["analyses"][0]["ai_summary"] is None


class TestReport:
    def test_report_uploaded(self, report_handler, analyze_handler, collect_handler):
        collect_out = collect_handler.handler({}, None)
        analyze_out = analyze_handler.handler(collect_out, None)
        with patch.object(report_handler, "boto3") as mock_boto3:
            mock_s3 = MagicMock()
            mock_boto3.client.side_effect = lambda svc, **kw: {"s3": mock_s3, "cloudwatch": MagicMock(), "sns": MagicMock()}.get(svc, MagicMock())
            report_handler.handler(analyze_out, None)
            assert mock_s3.put_object.called
            assert "cost-report.json" in mock_s3.put_object.call_args_list[0].kwargs["Key"]
