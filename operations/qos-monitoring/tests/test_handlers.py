"""OPS6 QoS Monitoring テスト."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestCollect:
    def test_collect_demo(self, collect_handler):
        result = collect_handler.handler({}, None)
        assert len(result["file_systems"]) == 1
        fs = result["file_systems"][0]
        assert "qos_policies" in fs
        assert len(fs["qos_policies"]) == 3
        assert "volumes_without_qos" in fs


class TestAnalyze:
    def test_unassigned_volumes_recommendation(self, analyze_handler, collect_handler):
        collect_out = collect_handler.handler({}, None)
        result = analyze_handler.handler(collect_out, None)
        recs = result["analyses"][0]["recommendations"]
        assign_recs = [r for r in recs if r["type"] == "assign_qos_policy"]
        assert len(assign_recs) == 1

    def test_unlimited_policy_recommendation(self, analyze_handler, collect_handler):
        collect_out = collect_handler.handler({}, None)
        result = analyze_handler.handler(collect_out, None)
        recs = result["analyses"][0]["recommendations"]
        limit_recs = [r for r in recs if r["type"] == "set_limits"]
        # "default" policy has no limits and 2 volumes
        assert len(limit_recs) == 1

    def test_summary_stats(self, analyze_handler, collect_handler):
        collect_out = collect_handler.handler({}, None)
        result = analyze_handler.handler(collect_out, None)
        summary = result["analyses"][0]["summary"]
        assert summary["total_policies"] == 3
        assert summary["policies_with_limits"] == 2
        assert summary["policies_unlimited"] == 1
        assert summary["volumes_without_qos"] == 2


class TestReport:
    def test_report_uploaded(self, report_handler, analyze_handler, collect_handler):
        collect_out = collect_handler.handler({}, None)
        analyze_out = analyze_handler.handler(collect_out, None)
        with patch.object(report_handler, "boto3") as mock_boto3:
            mock_s3 = MagicMock()
            mock_boto3.client.side_effect = lambda svc, **kw: {
                "s3": mock_s3,
                "cloudwatch": MagicMock(),
                "sns": MagicMock(),
            }.get(svc, MagicMock())
            report_handler.handler(analyze_out, None)
            assert mock_s3.put_object.called
            assert "qos-report.json" in mock_s3.put_object.call_args_list[0].kwargs["Key"]
