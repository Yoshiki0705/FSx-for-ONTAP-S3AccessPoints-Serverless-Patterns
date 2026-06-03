"""UC18 通信業界 Report Lambda ユニットテスト

Report Lambda のレポート生成ロジック、結果集約、
クリティカル判定、EMF メトリクス出力をテストする。
AWS サービス呼び出し (S3, SNS) は unittest.mock でモック化。
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# shared モジュールのパスを追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Report handler
_report_path = os.path.join(os.path.dirname(__file__), "..", "functions", "report", "handler.py")
_report_spec = importlib.util.spec_from_file_location("report_handler", _report_path)
_report_module = importlib.util.module_from_spec(_report_spec)
_report_spec.loader.exec_module(_report_module)

aggregate_results = _report_module.aggregate_results
build_network_health_report = _report_module.build_network_health_report
is_critical_anomaly = _report_module.is_critical_anomaly
publish_critical_alert = _report_module.publish_critical_alert
generate_report_id = _report_module.generate_report_id
handler = _report_module.handler


# =========================================================================
# aggregate_results テスト
# =========================================================================


class TestAggregateResults:
    """結果集約のテスト"""

    def test_basic_aggregation(self):
        """CDR/Log 結果が正しく集約される"""
        event = {
            "anomaly_result": {
                "anomalies": [{"metric_name": "call_volume", "z_score": 4.5}],
                "anomaly_count": 1,
                "classification": {"classification": "traffic_surge"},
                "current_metrics": {"call_volume": 500.0},
                "baseline_summary": {},
                "total_cdr_files": 5,
                "total_log_files": 3,
                "status": "success",
            },
            "cdr_results": [
                {"status": "success"},
                {"status": "success"},
                {"status": "parse_error"},
            ],
            "log_results": [
                {"status": "success"},
                {"status": "success"},
            ],
        }
        result = aggregate_results(event)
        assert result["anomaly_count"] == 1
        assert result["success_count"] == 4
        assert result["error_count"] == 1
        assert result["total_processed"] == 5

    def test_all_success(self):
        """全件成功のケース"""
        event = {
            "anomaly_result": {
                "anomalies": [],
                "anomaly_count": 0,
                "classification": {"classification": "normal"},
                "current_metrics": {},
                "baseline_summary": {},
                "total_cdr_files": 10,
                "total_log_files": 5,
                "status": "success",
            },
            "cdr_results": [{"status": "success"}] * 10,
            "log_results": [{"status": "success"}] * 5,
        }
        result = aggregate_results(event)
        assert result["success_count"] == 15
        assert result["error_count"] == 0
        assert result["total_processed"] == 15

    def test_no_results_uses_anomaly_result(self):
        """cdr_results/log_results が空の場合は anomaly_result から推定"""
        event = {
            "anomaly_result": {
                "anomalies": [],
                "anomaly_count": 0,
                "classification": {},
                "current_metrics": {},
                "baseline_summary": {},
                "total_cdr_files": 3,
                "total_log_files": 2,
                "status": "success",
            },
        }
        result = aggregate_results(event)
        assert result["total_cdr_files"] == 3
        assert result["total_log_files"] == 2

    def test_direct_event_format(self):
        """anomaly_result ではなく直接イベント形式"""
        event = {
            "anomalies": [{"metric_name": "x"}],
            "anomaly_count": 1,
            "classification": {"classification": "unknown"},
            "current_metrics": {},
            "baseline_summary": {},
            "total_cdr_files": 2,
            "total_log_files": 1,
            "status": "success",
        }
        result = aggregate_results(event)
        assert result["anomaly_count"] == 1


# =========================================================================
# build_network_health_report テスト
# =========================================================================


class TestBuildNetworkHealthReport:
    """レポート生成のテスト"""

    def test_healthy_report(self):
        """異常なしの健全なレポート"""
        aggregated = {
            "anomalies": [],
            "anomaly_count": 0,
            "classification": {"classification": "normal", "explanation": "", "recommendations": []},
            "current_metrics": {"call_volume": 100.0},
            "baseline_summary": {},
            "total_cdr_files": 10,
            "total_log_files": 5,
            "total_processed": 15,
            "success_count": 15,
            "error_count": 0,
        }
        report = build_network_health_report("test-id", aggregated, "2026-06-02")
        assert report["severity"] == "normal"
        assert report["summary"]["network_status"] == "healthy"
        assert report["report_id"] == "test-id"
        assert report["report_date"] == "2026-06-02"
        assert report["metrics"]["total_processed"] == 15
        assert report["metrics"]["success_count"] == 15
        assert report["metrics"]["error_count"] == 0

    def test_critical_report_equipment_degradation(self):
        """equipment_degradation 分類でクリティカルレポート"""
        aggregated = {
            "anomalies": [{"metric_name": "failures", "z_score": 4.0}],
            "anomaly_count": 1,
            "classification": {"classification": "equipment_degradation", "explanation": "Hardware failing", "recommendations": ["Replace"]},
            "current_metrics": {},
            "baseline_summary": {},
            "total_cdr_files": 5,
            "total_log_files": 3,
            "total_processed": 8,
            "success_count": 7,
            "error_count": 1,
        }
        report = build_network_health_report("crit-id", aggregated, "2026-06-02")
        assert report["severity"] == "critical"
        assert report["summary"]["network_status"] == "degraded"

    def test_warning_report_high_z_score(self):
        """高 z_score (>4, <=5) で warning レポート"""
        aggregated = {
            "anomalies": [{"metric_name": "volume", "z_score": 4.5}],
            "anomaly_count": 1,
            "classification": {"classification": "traffic_surge", "explanation": "Spike", "recommendations": []},
            "current_metrics": {},
            "baseline_summary": {},
            "total_cdr_files": 5,
            "total_log_files": 0,
            "total_processed": 5,
            "success_count": 5,
            "error_count": 0,
        }
        report = build_network_health_report("warn-id", aggregated, "2026-06-02")
        assert report["severity"] == "warning"
        assert report["summary"]["network_status"] == "attention_required"

    def test_report_contains_use_case(self):
        """レポートに use_case が含まれる"""
        aggregated = {
            "anomalies": [],
            "anomaly_count": 0,
            "classification": {},
            "current_metrics": {},
            "baseline_summary": {},
            "total_cdr_files": 0,
            "total_log_files": 0,
            "total_processed": 0,
            "success_count": 0,
            "error_count": 0,
        }
        report = build_network_health_report("id", aggregated, "2026-06-02")
        assert report["use_case"] == "telecom-network-analytics"
        assert report["report_type"] == "daily_network_health"


# =========================================================================
# is_critical_anomaly テスト
# =========================================================================


class TestIsCriticalAnomaly:
    """クリティカル判定のテスト"""

    def test_critical_severity(self):
        """severity=critical で True"""
        assert is_critical_anomaly({"severity": "critical"}) is True

    def test_warning_severity(self):
        """severity=warning で False"""
        assert is_critical_anomaly({"severity": "warning"}) is False

    def test_normal_severity(self):
        """severity=normal で False"""
        assert is_critical_anomaly({"severity": "normal"}) is False

    def test_missing_severity(self):
        """severity キーなしで False"""
        assert is_critical_anomaly({}) is False


# =========================================================================
# publish_critical_alert テスト
# =========================================================================


class TestPublishCriticalAlert:
    """クリティカルアラート発行のテスト"""

    def test_publishes_to_sns(self):
        """SNS に正しくパブリッシュされる"""
        mock_sns = MagicMock()
        report = {
            "report_id": "test-id",
            "report_date": "2026-06-02",
            "severity": "critical",
            "summary": {
                "anomaly_count": 3,
                "classification": "capacity_exhaustion",
                "explanation": "All links saturated",
                "recommendations": ["Add capacity"],
            },
            "details": {
                "top_anomalies": [{"metric": "load", "z_score": 6.0}],
            },
            "generated_at": "2026-06-02T10:00:00Z",
        }
        publish_critical_alert(mock_sns, "arn:aws:sns:ap-northeast-1:123:topic", report)
        mock_sns.publish.assert_called_once()
        call_kwargs = mock_sns.publish.call_args[1]
        assert "[CRITICAL]" in call_kwargs["Subject"]
        message = json.loads(call_kwargs["Message"])
        assert message["anomaly_count"] == 3
        assert message["classification"] == "capacity_exhaustion"

    def test_sns_publish_failure_handled(self):
        """SNS パブリッシュ失敗時も例外を発生させない"""
        mock_sns = MagicMock()
        mock_sns.publish.side_effect = Exception("SNS error")
        report = {
            "summary": {"anomaly_count": 1, "classification": "unknown", "explanation": "", "recommendations": []},
            "details": {"top_anomalies": []},
            "generated_at": "2026-06-02T10:00:00Z",
            "report_id": "id",
            "report_date": "2026-06-02",
        }
        # Should not raise
        publish_critical_alert(mock_sns, "arn:aws:sns:ap-northeast-1:123:topic", report)


# =========================================================================
# generate_report_id テスト
# =========================================================================


class TestGenerateReportId:
    """レポート ID 生成のテスト"""

    def test_returns_uuid_string(self):
        """UUID 形式の文字列を返す"""
        report_id = generate_report_id()
        assert isinstance(report_id, str)
        assert len(report_id) == 36  # UUID format: 8-4-4-4-12
        assert report_id.count("-") == 4

    def test_unique_ids(self):
        """複数呼び出しで一意の ID を返す"""
        ids = {generate_report_id() for _ in range(10)}
        assert len(ids) == 10


# =========================================================================
# handler 統合テスト (モック)
# =========================================================================


class TestReportHandler:
    """Report Lambda ハンドラーの統合テスト"""

    def _make_context(self):
        ctx = MagicMock()
        ctx.aws_request_id = "report-test-request-id"
        ctx.function_name = "telecom-report"
        return ctx

    @patch.dict(os.environ, {
        "OUTPUT_BUCKET": "test-output-bucket",
        "SNS_TOPIC_ARN": "",
    })
    @patch("boto3.client")
    def test_handler_success_normal(self, mock_boto_client):
        """正常系: 異常なしレポート生成"""
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        event = {
            "anomaly_result": {
                "anomalies": [],
                "anomaly_count": 0,
                "classification": {"classification": "normal"},
                "current_metrics": {"call_volume": 100.0},
                "baseline_summary": {},
                "total_cdr_files": 5,
                "total_log_files": 3,
                "status": "success",
            },
            "cdr_results": [{"status": "success"}] * 5,
            "log_results": [{"status": "success"}] * 3,
        }

        with patch.object(_report_module, "EmfMetrics") as mock_emf_cls:
            mock_emf = MagicMock()
            mock_emf_cls.return_value = mock_emf
            result = handler(event, self._make_context())

        assert result["status"] == "success"
        assert result["severity"] == "normal"
        assert result["anomaly_count"] == 0
        assert result["success_count"] == 8
        assert result["error_count"] == 0
        assert "report_key" in result
        assert result["report_key"].startswith("reports/daily/")

    @patch.dict(os.environ, {
        "OUTPUT_BUCKET": "test-output-bucket",
        "SNS_TOPIC_ARN": "arn:aws:sns:ap-northeast-1:123:alert-topic",
    })
    @patch("boto3.client")
    def test_handler_critical_sends_sns(self, mock_boto_client):
        """異常系: クリティカルレポートで SNS 通知が発行される"""
        mock_s3 = MagicMock()
        mock_sns = MagicMock()
        mock_boto_client.side_effect = lambda service, **kwargs: mock_sns if service == "sns" else mock_s3

        event = {
            "anomaly_result": {
                "anomalies": [{"metric_name": "failures", "z_score": 6.0}],
                "anomaly_count": 1,
                "classification": {"classification": "equipment_degradation", "explanation": "Failing", "recommendations": ["Fix"]},
                "current_metrics": {},
                "baseline_summary": {},
                "total_cdr_files": 5,
                "total_log_files": 3,
                "status": "success",
            },
            "cdr_results": [{"status": "success"}] * 5,
            "log_results": [{"status": "success"}] * 3,
        }

        with patch.object(_report_module, "EmfMetrics") as mock_emf_cls:
            mock_emf = MagicMock()
            mock_emf_cls.return_value = mock_emf
            result = handler(event, self._make_context())

        assert result["severity"] == "critical"
        mock_sns.publish.assert_called_once()

    @patch.dict(os.environ, {
        "OUTPUT_BUCKET": "test-output-bucket",
        "SNS_TOPIC_ARN": "",
    })
    @patch("boto3.client")
    def test_handler_emf_metrics_emitted(self, mock_boto_client):
        """EMF メトリクス (ProcessingDuration, SuccessCount, ErrorCount) が出力される"""
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        event = {
            "anomaly_result": {
                "anomalies": [],
                "anomaly_count": 0,
                "classification": {},
                "current_metrics": {},
                "baseline_summary": {},
                "total_cdr_files": 2,
                "total_log_files": 1,
                "status": "success",
            },
            "cdr_results": [{"status": "success"}, {"status": "error"}],
            "log_results": [{"status": "success"}],
        }

        with patch.object(_report_module, "EmfMetrics") as mock_emf_cls:
            mock_emf = MagicMock()
            mock_emf_cls.return_value = mock_emf
            result = handler(event, self._make_context())

        # EMF メトリクスの呼び出し確認
        mock_emf.put_metric.assert_any_call("ProcessingDuration", pytest.approx(result["processing_duration_ms"], abs=100), "Milliseconds")
        mock_emf.put_metric.assert_any_call("SuccessCount", 2.0, "Count")
        mock_emf.put_metric.assert_any_call("ErrorCount", 1.0, "Count")
        mock_emf.flush.assert_called_once()
