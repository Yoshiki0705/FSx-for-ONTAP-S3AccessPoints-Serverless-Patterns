"""SLO モジュール ユニットテスト.

SLOTarget 定義、evaluate_slos 評価ロジック、
generate_dashboard_widgets ダッシュボードウィジェット生成を検証する。
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.slo import (
    SLO_TARGETS,
    SYNTHETIC_MONITORING_METRICS,
    SLOEvaluationResult,
    SLOTarget,
    _compare_threshold,
    evaluate_slos,
    generate_dashboard_widgets,
)


class TestSLOTargetDefinitions:
    """SLO_TARGETS リストの定義を検証する。"""

    def test_slo_targets_has_four_entries(self):
        assert len(SLO_TARGETS) == 4

    def test_slo_target_names(self):
        names = [t.name for t in SLO_TARGETS]
        assert "EventIngestionLatency" in names
        assert "ProcessingSuccessRate" in names
        assert "ReconnectTime" in names
        assert "ReplayCompletionTime" in names

    def test_event_ingestion_latency_target(self):
        target = next(t for t in SLO_TARGETS if t.name == "EventIngestionLatency")
        assert target.metric_namespace == "FSxN-S3AP-Patterns"
        assert target.metric_name == "EventIngestionLatency_ms"
        assert target.threshold == 5000.0
        assert target.comparison == "LessThanThreshold"
        assert target.period_sec == 300
        assert target.evaluation_periods == 3

    def test_processing_success_rate_target(self):
        target = next(t for t in SLO_TARGETS if t.name == "ProcessingSuccessRate")
        assert target.metric_namespace == "FSxN-S3AP-Patterns"
        assert target.metric_name == "ProcessingSuccessRate_pct"
        assert target.threshold == 99.5
        assert target.comparison == "GreaterThanThreshold"

    def test_reconnect_time_target(self):
        target = next(t for t in SLO_TARGETS if t.name == "ReconnectTime")
        assert target.threshold == 30.0
        assert target.comparison == "LessThanThreshold"

    def test_replay_completion_time_target(self):
        target = next(t for t in SLO_TARGETS if t.name == "ReplayCompletionTime")
        assert target.threshold == 300.0
        assert target.comparison == "LessThanThreshold"


class TestCompareThreshold:
    """_compare_threshold 関数を検証する。"""

    def test_less_than_threshold_met(self):
        assert _compare_threshold(4000.0, 5000.0, "LessThanThreshold") is True

    def test_less_than_threshold_violated(self):
        assert _compare_threshold(6000.0, 5000.0, "LessThanThreshold") is False

    def test_less_than_threshold_equal_is_violated(self):
        assert _compare_threshold(5000.0, 5000.0, "LessThanThreshold") is False

    def test_greater_than_threshold_met(self):
        assert _compare_threshold(99.9, 99.5, "GreaterThanThreshold") is True

    def test_greater_than_threshold_violated(self):
        assert _compare_threshold(99.0, 99.5, "GreaterThanThreshold") is False

    def test_greater_than_threshold_equal_is_violated(self):
        assert _compare_threshold(99.5, 99.5, "GreaterThanThreshold") is False

    def test_unknown_comparison_raises(self):
        with pytest.raises(ValueError, match="Unknown comparison operator"):
            _compare_threshold(100.0, 50.0, "EqualToThreshold")


class TestEvaluateSLOs:
    """evaluate_slos 関数を検証する。"""

    def _make_cw_client(self, datapoints_map: dict[str, list[dict]]):
        """CloudWatch クライアントのモックを作成する。

        Args:
            datapoints_map: metric_name → datapoints のマッピング
        """
        client = MagicMock()

        def get_metric_statistics(**kwargs):
            metric_name = kwargs["MetricName"]
            dps = datapoints_map.get(metric_name, [])
            return {"Datapoints": dps}

        client.get_metric_statistics.side_effect = get_metric_statistics
        return client

    def test_all_slos_met(self):
        """全 SLO が達成されている場合。"""
        now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        datapoints = {
            "EventIngestionLatency_ms": [
                {"Timestamp": now, "Maximum": 3000.0}
            ],
            "ProcessingSuccessRate_pct": [
                {"Timestamp": now, "Minimum": 99.8}
            ],
            "FPolicyReconnectTime_sec": [
                {"Timestamp": now, "Maximum": 15.0}
            ],
            "ReplayCompletionTime_sec": [
                {"Timestamp": now, "Maximum": 120.0}
            ],
        }
        cw = self._make_cw_client(datapoints)

        results = evaluate_slos(cw)

        assert len(results) == 4
        assert all(r.met for r in results)
        assert all(r.data_available for r in results)

    def test_slo_violated(self):
        """SLO が違反されている場合。"""
        now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        datapoints = {
            "EventIngestionLatency_ms": [
                {"Timestamp": now, "Maximum": 8000.0}  # > 5000 → violated
            ],
            "ProcessingSuccessRate_pct": [
                {"Timestamp": now, "Minimum": 99.8}
            ],
            "FPolicyReconnectTime_sec": [
                {"Timestamp": now, "Maximum": 15.0}
            ],
            "ReplayCompletionTime_sec": [
                {"Timestamp": now, "Maximum": 120.0}
            ],
        }
        cw = self._make_cw_client(datapoints)

        results = evaluate_slos(cw)

        latency_result = next(r for r in results if r.slo_name == "EventIngestionLatency")
        assert latency_result.met is False
        assert latency_result.value == 8000.0
        assert latency_result.data_available is True

    def test_no_datapoints_returns_met_with_no_data(self):
        """データポイントがない場合は met=True, data_available=False。"""
        cw = self._make_cw_client({})

        results = evaluate_slos(cw)

        assert len(results) == 4
        assert all(r.met for r in results)
        assert all(not r.data_available for r in results)
        assert all(r.value is None for r in results)

    def test_cloudwatch_error_returns_met_with_no_data(self):
        """CloudWatch エラー時は met=True, data_available=False。"""
        cw = MagicMock()
        cw.get_metric_statistics.side_effect = Exception("Throttled")

        results = evaluate_slos(cw)

        assert len(results) == 4
        assert all(r.met for r in results)
        assert all(not r.data_available for r in results)

    def test_custom_targets(self):
        """カスタムターゲットリストで評価する。"""
        now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        custom_target = SLOTarget(
            name="CustomSLO",
            metric_namespace="Custom",
            metric_name="CustomMetric",
            threshold=100.0,
            comparison="LessThanThreshold",
        )
        cw = self._make_cw_client(
            {"CustomMetric": [{"Timestamp": now, "Maximum": 50.0}]}
        )

        results = evaluate_slos(cw, targets=[custom_target])

        assert len(results) == 1
        assert results[0].slo_name == "CustomSLO"
        assert results[0].met is True
        assert results[0].value == 50.0

    def test_custom_period(self):
        """カスタム期間で評価する。"""
        now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        cw = self._make_cw_client(
            {"EventIngestionLatency_ms": [{"Timestamp": now, "Maximum": 3000.0}]}
        )

        results = evaluate_slos(cw, period_sec=600)

        # 呼び出し時に Period=600 が使われていることを確認
        call_kwargs = cw.get_metric_statistics.call_args_list[0][1]
        assert call_kwargs["Period"] == 600

    def test_evaluation_result_has_evaluated_at(self):
        """評価結果に evaluated_at が含まれる。"""
        now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        cw = self._make_cw_client(
            {"EventIngestionLatency_ms": [{"Timestamp": now, "Maximum": 3000.0}]}
        )

        results = evaluate_slos(cw, targets=[SLO_TARGETS[0]])

        assert results[0].evaluated_at is not None
        # ISO format の日時文字列であること
        assert "T" in results[0].evaluated_at


class TestGenerateDashboardWidgets:
    """generate_dashboard_widgets 関数を検証する。"""

    def test_returns_list_of_widgets(self):
        widgets = generate_dashboard_widgets()
        assert isinstance(widgets, list)
        assert len(widgets) > 0

    def test_includes_header_text_widget(self):
        widgets = generate_dashboard_widgets()
        text_widgets = [w for w in widgets if w["type"] == "text"]
        assert len(text_widgets) >= 1
        assert "SLO Dashboard" in text_widgets[0]["properties"]["markdown"]

    def test_includes_metric_widgets_for_each_slo(self):
        widgets = generate_dashboard_widgets()
        metric_widgets = [w for w in widgets if w["type"] == "metric"]
        # 4 SLO + 1 Synthetic Monitoring = 5 metric widgets
        assert len(metric_widgets) >= 4

    def test_slo_widget_has_threshold_annotation(self):
        widgets = generate_dashboard_widgets()
        metric_widgets = [w for w in widgets if w["type"] == "metric"]
        # First metric widget should have threshold annotation
        slo_widget = metric_widgets[0]
        annotations = slo_widget["properties"].get("annotations", {})
        assert "horizontal" in annotations
        assert len(annotations["horizontal"]) == 1

    def test_includes_synthetic_monitoring_widget(self):
        widgets = generate_dashboard_widgets(include_synthetic_monitoring=True)
        # Find the Synthetic Monitoring text header
        text_widgets = [w for w in widgets if w["type"] == "text"]
        sm_headers = [
            w for w in text_widgets
            if "Synthetic Monitoring" in w["properties"]["markdown"]
        ]
        assert len(sm_headers) == 1

    def test_excludes_synthetic_monitoring_when_disabled(self):
        widgets = generate_dashboard_widgets(include_synthetic_monitoring=False)
        text_widgets = [w for w in widgets if w["type"] == "text"]
        sm_headers = [
            w for w in text_widgets
            if "Synthetic Monitoring" in w["properties"]["markdown"]
        ]
        assert len(sm_headers) == 0

    def test_widget_region_is_set(self):
        widgets = generate_dashboard_widgets(region="us-east-1")
        metric_widgets = [w for w in widgets if w["type"] == "metric"]
        for w in metric_widgets:
            assert w["properties"]["region"] == "us-east-1"

    def test_widget_positions_are_valid(self):
        widgets = generate_dashboard_widgets()
        for w in widgets:
            assert "x" in w
            assert "y" in w
            assert "width" in w
            assert "height" in w
            assert 0 <= w["x"] < 24
            assert w["width"] > 0
            assert w["height"] > 0


class TestSyntheticMonitoringMetrics:
    """SYNTHETIC_MONITORING_METRICS 定義を検証する。"""

    def test_has_three_metrics(self):
        assert len(SYNTHETIC_MONITORING_METRICS) == 3

    def test_metric_names(self):
        names = [m["metric_name"] for m in SYNTHETIC_MONITORING_METRICS]
        assert "S3AP_ListLatency_ms" in names
        assert "S3AP_GetLatency_ms" in names
        assert "ONTAP_HealthCheck" in names

    def test_all_metrics_have_required_fields(self):
        for m in SYNTHETIC_MONITORING_METRICS:
            assert "namespace" in m
            assert "metric_name" in m
            assert "label" in m
