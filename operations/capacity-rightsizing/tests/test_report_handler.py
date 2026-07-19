"""OPS1 Report Handler テスト."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestReportGeneration:
    """レポート生成テスト."""

    def test_json_report_uploaded_to_s3(self, report_handler, analyze_output):
        """JSON レポートが S3 にアップロードされる."""
        with patch.object(report_handler, "boto3") as mock_boto3:
            mock_s3 = MagicMock()
            mock_cw = MagicMock()
            mock_boto3.client.side_effect = lambda service, **kwargs: {
                "s3": mock_s3,
                "cloudwatch": mock_cw,
                "sns": MagicMock(),
            }.get(service, MagicMock())

            report_handler.handler(analyze_output, None)

            # Verify S3 put_object was called
            assert mock_s3.put_object.called
            call_args = mock_s3.put_object.call_args_list[0]
            assert call_args.kwargs["Bucket"] == "test-report-bucket"
            assert "capacity-report.json" in call_args.kwargs["Key"]
            assert call_args.kwargs["ContentType"] == "application/json"

    def test_report_output_structure(self, report_handler, analyze_output):
        """レポート出力が正しい構造を持つ."""
        with patch.object(report_handler, "boto3") as mock_boto3:
            mock_boto3.client.return_value = MagicMock()

            result = report_handler.handler(analyze_output, None)

            assert "reports" in result
            assert "total_recommendations" in result
            assert result["total_recommendations"] == 2

            report = result["reports"][0]
            assert report["fs_id"] == "fs-test01"
            assert report["recommendation_count"] == 2
            assert "reported_at" in report

    def test_no_alert_at_level_0(self, report_handler, analyze_output):
        """AutomationLevel=0 ではアラートを送信しない."""
        with patch.object(report_handler, "boto3") as mock_boto3:
            mock_sns = MagicMock()
            mock_boto3.client.side_effect = lambda service, **kwargs: {
                "s3": MagicMock(),
                "cloudwatch": MagicMock(),
                "sns": mock_sns,
            }.get(service, MagicMock())

            result = report_handler.handler(analyze_output, None)

            # SNS publish should NOT be called at level 0
            mock_sns.publish.assert_not_called()
            assert result["reports"][0]["alert_required"] is False

    def test_alert_sent_at_level_1(self, report_handler, analyze_output, monkeypatch):
        """AutomationLevel=1 でアラートが送信される."""
        monkeypatch.setenv("AUTOMATION_LEVEL", "1")
        monkeypatch.setenv("ALERT_TOPIC_ARN", "arn:aws:sns:ap-northeast-1:123456789012:test-topic")

        with patch.object(report_handler, "boto3") as mock_boto3:
            mock_sns = MagicMock()
            mock_boto3.client.side_effect = lambda service, **kwargs: {
                "s3": MagicMock(),
                "cloudwatch": MagicMock(),
                "sns": mock_sns,
            }.get(service, MagicMock())

            result = report_handler.handler(analyze_output, None)

            mock_sns.publish.assert_called_once()
            assert result["reports"][0]["alert_required"] is True


class TestCloudWatchMetrics:
    """CloudWatch カスタムメトリクス publish テスト."""

    def test_custom_metrics_published(self, report_handler, analyze_output):
        """カスタムメトリクスが publish される."""
        with patch.object(report_handler, "boto3") as mock_boto3:
            mock_cw = MagicMock()
            mock_boto3.client.side_effect = lambda service, **kwargs: {
                "s3": MagicMock(),
                "cloudwatch": mock_cw,
                "sns": MagicMock(),
            }.get(service, MagicMock())

            report_handler.handler(analyze_output, None)

            mock_cw.put_metric_data.assert_called_once()
            call_kwargs = mock_cw.put_metric_data.call_args.kwargs
            assert call_kwargs["Namespace"] == "FSxOps"
            metric_names = [m["MetricName"] for m in call_kwargs["MetricData"]]
            assert "AvgVolumeUtilizationPercent" in metric_names
            assert "RecommendationCount" in metric_names
            assert "MonthlyCostDeltaUSD" in metric_names


class TestHtmlReport:
    """HTML レポート生成テスト."""

    def test_html_report_generated_in_both_mode(self, report_handler, analyze_output, monkeypatch):
        """ReportFormat=BOTH で HTML レポートも生成される."""
        monkeypatch.setenv("REPORT_FORMAT", "BOTH")

        with patch.object(report_handler, "boto3") as mock_boto3:
            mock_s3 = MagicMock()
            mock_boto3.client.side_effect = lambda service, **kwargs: {
                "s3": mock_s3,
                "cloudwatch": MagicMock(),
                "sns": MagicMock(),
            }.get(service, MagicMock())

            report_handler.handler(analyze_output, None)

            # Should have 2 S3 uploads (JSON + HTML)
            assert mock_s3.put_object.call_count == 2
            content_types = [call.kwargs["ContentType"] for call in mock_s3.put_object.call_args_list]
            assert "application/json" in content_types
            assert "text/html; charset=utf-8" in content_types

    def test_html_report_contains_recommendations(self, report_handler, analyze_output, monkeypatch):
        """HTML レポートに推奨内容が含まれる."""
        monkeypatch.setenv("REPORT_FORMAT", "HTML")

        with patch.object(report_handler, "boto3") as mock_boto3:
            mock_s3 = MagicMock()
            mock_boto3.client.side_effect = lambda service, **kwargs: {
                "s3": mock_s3,
                "cloudwatch": MagicMock(),
                "sns": MagicMock(),
            }.get(service, MagicMock())

            report_handler.handler(analyze_output, None)

            html_call = mock_s3.put_object.call_args_list[0]
            html_body = html_call.kwargs["Body"].decode("utf-8")
            assert "vol_production_data" in html_body
            assert "OPS1" in html_body
            assert "Governance Note" in html_body
