"""OPS3 Report Handler テスト."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def analyze_output():
    return {
        "analyses": [
            {
                "fs_id": "fs-test01",
                "recommendations": [
                    {
                        "fs_id": "fs-test01",
                        "volume_name": "vol_dev",
                        "current_policy": "none",
                        "recommended_policy": "auto",
                        "current_cooling_days": 31,
                        "recommended_cooling_days": 31,
                        "estimated_monthly_savings_usd": 1.04,
                        "reason": "test",
                        "confidence": 0.7,
                    },
                ],
                "summary": {
                    "total_volumes": 5,
                    "volumes_with_recommendations": 1,
                    "total_potential_savings_usd": 1.04,
                    "policy_distribution": {"none": 2, "auto": 2, "snapshot-only": 1},
                },
                "ai_summary": None,
                "analyzed_at": "2026-07-13T00:01:00+00:00",
            }
        ],
        "total_recommendations": 1,
        "analyzed_at": "2026-07-13T00:01:00+00:00",
    }


class TestReportGeneration:
    def test_report_uploaded(self, report_handler, analyze_output):
        with patch.object(report_handler, "boto3") as mock_boto3:
            mock_s3 = MagicMock()
            mock_boto3.client.side_effect = lambda svc, **kw: {
                "s3": mock_s3,
                "cloudwatch": MagicMock(),
                "sns": MagicMock(),
            }.get(svc, MagicMock())
            report_handler.handler(analyze_output, None)
            assert mock_s3.put_object.called
            assert "tiering-report.json" in mock_s3.put_object.call_args_list[0].kwargs["Key"]

    def test_metrics_published(self, report_handler, analyze_output):
        with patch.object(report_handler, "boto3") as mock_boto3:
            mock_cw = MagicMock()
            mock_boto3.client.side_effect = lambda svc, **kw: {
                "s3": MagicMock(),
                "cloudwatch": mock_cw,
                "sns": MagicMock(),
            }.get(svc, MagicMock())
            report_handler.handler(analyze_output, None)
            mock_cw.put_metric_data.assert_called_once()
            names = [m["MetricName"] for m in mock_cw.put_metric_data.call_args.kwargs["MetricData"]]
            assert "TieringRecommendationCount" in names
            assert "TieringPotentialSavingsUSD" in names

    def test_no_alert_level_0(self, report_handler, analyze_output):
        with patch.object(report_handler, "boto3") as mock_boto3:
            mock_sns = MagicMock()
            mock_boto3.client.side_effect = lambda svc, **kw: {
                "s3": MagicMock(),
                "cloudwatch": MagicMock(),
                "sns": mock_sns,
            }.get(svc, MagicMock())
            result = report_handler.handler(analyze_output, None)
            mock_sns.publish.assert_not_called()
            assert result["reports"][0]["alert_required"] is False
