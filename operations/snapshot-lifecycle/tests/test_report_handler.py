"""OPS4 Report Handler テスト."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestReportGeneration:
    """レポート生成テスト."""

    def test_json_report_uploaded(self, report_handler, analyze_output):
        """JSON レポートが S3 にアップロードされる."""
        with patch.object(report_handler, "boto3") as mock_boto3:
            mock_s3 = MagicMock()
            mock_cw = MagicMock()
            mock_boto3.client.side_effect = lambda service, **kw: {
                "s3": mock_s3,
                "cloudwatch": mock_cw,
                "sns": MagicMock(),
            }.get(service, MagicMock())

            report_handler.handler(analyze_output, None)

            assert mock_s3.put_object.called
            call_args = mock_s3.put_object.call_args_list[0]
            assert "snapshot-audit.json" in call_args.kwargs["Key"]

    def test_report_output_structure(self, report_handler, analyze_output):
        """レポート出力が正しい構造を持つ."""
        with patch.object(report_handler, "boto3") as mock_boto3:
            mock_boto3.client.return_value = MagicMock()

            result = report_handler.handler(analyze_output, None)

            assert "reports" in result
            assert result["total_expired_snapshots"] == 3
            report = result["reports"][0]
            assert report["fs_id"] == "fs-test01"
            assert report["expired_count"] == 3

    def test_no_alert_at_level_0(self, report_handler, analyze_output):
        """AutomationLevel=0 ではアラート送信しない."""
        with patch.object(report_handler, "boto3") as mock_boto3:
            mock_sns = MagicMock()
            mock_boto3.client.side_effect = lambda service, **kw: {
                "s3": MagicMock(),
                "cloudwatch": MagicMock(),
                "sns": mock_sns,
            }.get(service, MagicMock())

            result = report_handler.handler(analyze_output, None)

            mock_sns.publish.assert_not_called()
            assert result["reports"][0]["alert_required"] is False

    def test_alert_sent_at_level_1(self, report_handler, analyze_output, monkeypatch):
        """AutomationLevel=1 + expired snapshots でアラート送信."""
        monkeypatch.setenv("AUTOMATION_LEVEL", "1")
        monkeypatch.setenv("ALERT_TOPIC_ARN", "arn:aws:sns:ap-northeast-1:123456789012:topic")

        with patch.object(report_handler, "boto3") as mock_boto3:
            mock_sns = MagicMock()
            mock_boto3.client.side_effect = lambda service, **kw: {
                "s3": MagicMock(),
                "cloudwatch": mock_cw,
                "sns": mock_sns,
            }.get(service, MagicMock())
            mock_cw = MagicMock()

            result = report_handler.handler(analyze_output, None)

            mock_sns.publish.assert_called_once()
            assert result["reports"][0]["alert_required"] is True


class TestCloudWatchMetrics:
    """CloudWatch メトリクス テスト."""

    def test_snapshot_metrics_published(self, report_handler, analyze_output):
        """スナップショット固有メトリクスが publish される."""
        with patch.object(report_handler, "boto3") as mock_boto3:
            mock_cw = MagicMock()
            mock_boto3.client.side_effect = lambda service, **kw: {
                "s3": MagicMock(),
                "cloudwatch": mock_cw,
                "sns": MagicMock(),
            }.get(service, MagicMock())

            report_handler.handler(analyze_output, None)

            mock_cw.put_metric_data.assert_called_once()
            call_kwargs = mock_cw.put_metric_data.call_args.kwargs
            assert call_kwargs["Namespace"] == "FSxOps"
            metric_names = [m["MetricName"] for m in call_kwargs["MetricData"]]
            assert "ExpiredSnapshotCount" in metric_names
            assert "ExpiredSnapshotSizeGB" in metric_names
            assert "PolicyDriftVolumeCount" in metric_names
            assert "RetentionCompliancePercent" in metric_names
