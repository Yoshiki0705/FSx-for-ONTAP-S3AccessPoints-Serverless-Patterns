"""Latency Reporter Lambda ユニットテスト

レイテンシ計測ロジックのテスト:
- レイテンシメトリクス計算
- EMF メトリクス出力
- エラー情報の記録
- 各種入力パターンの処理

カバレッジ目標: 80%以上
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path for shared module imports
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Import handler module
_handler_path = Path(__file__).resolve().parent.parent / "lambdas" / "latency_reporter" / "handler.py"
_spec = importlib.util.spec_from_file_location("latency_reporter_handler", _handler_path)
_module = importlib.util.module_from_spec(_spec)
sys.modules["latency_reporter_handler"] = _module
_spec.loader.exec_module(_module)

from latency_reporter_handler import (
    calculate_latency_metrics,
    emit_latency_metrics,
    handler,
)


class TestCalculateLatencyMetrics:
    """calculate_latency_metrics 関数のテスト"""

    def test_all_metrics_provided(self):
        """全メトリクスが提供された場合"""
        result = calculate_latency_metrics(
            event_time="2024-01-15T10:30:00Z",
            processing_duration_ms=150.5,
            event_to_processing_ms=50.0,
        )

        assert result["event_to_processing_latency_ms"] == 50.0
        assert result["processing_duration_ms"] == 150.5
        assert result["end_to_end_duration_ms"] > 0
        assert "reported_at" in result

    def test_no_event_time(self):
        """event_time が None の場合"""
        result = calculate_latency_metrics(
            event_time=None,
            processing_duration_ms=200.0,
            event_to_processing_ms=None,
        )

        assert result["event_to_processing_latency_ms"] == 0.0
        assert result["end_to_end_duration_ms"] == 200.0
        assert result["processing_duration_ms"] == 200.0

    def test_no_processing_duration(self):
        """processing_duration_ms が None の場合"""
        result = calculate_latency_metrics(
            event_time=None,
            processing_duration_ms=None,
            event_to_processing_ms=None,
        )

        assert result["processing_duration_ms"] == 0.0
        assert result["end_to_end_duration_ms"] == 0.0

    def test_invalid_event_time_format(self):
        """不正な event_time 形式の場合"""
        result = calculate_latency_metrics(
            event_time="not-a-valid-timestamp",
            processing_duration_ms=100.0,
            event_to_processing_ms=None,
        )

        # Falls back to processing_duration
        assert result["end_to_end_duration_ms"] == 100.0

    def test_event_time_in_past_gives_positive_e2e(self):
        """過去の event_time は正の end-to-end duration を生成する"""
        result = calculate_latency_metrics(
            event_time="2020-01-01T00:00:00Z",
            processing_duration_ms=100.0,
            event_to_processing_ms=50.0,
        )

        assert result["end_to_end_duration_ms"] > 0
        assert result["event_to_processing_latency_ms"] == 50.0


class TestEmitLatencyMetrics:
    """emit_latency_metrics 関数のテスト"""

    @patch("builtins.print")
    def test_emits_emf_json(self, mock_print):
        """EMF 形式の JSON が stdout に出力される"""
        metrics = {
            "event_to_processing_latency_ms": 50.0,
            "end_to_end_duration_ms": 200.0,
            "processing_duration_ms": 150.0,
        }

        emit_latency_metrics(metrics, "event-driven-prototype")

        # Verify print was called (EMF output)
        assert mock_print.called
        emf_output = mock_print.call_args[0][0]
        emf_data = json.loads(emf_output)

        # Verify EMF structure
        assert "_aws" in emf_data
        assert "CloudWatchMetrics" in emf_data["_aws"]
        cw_metrics = emf_data["_aws"]["CloudWatchMetrics"][0]
        assert cw_metrics["Namespace"] == "FSxN-S3AP-Patterns"

        # Verify metric values
        assert emf_data["EventToProcessingLatency"] == 50.0
        assert emf_data["EndToEndDuration"] == 200.0
        assert emf_data["ProcessingDuration"] == 150.0
        assert emf_data["EventVolumePerMinute"] == 1.0

    @patch("builtins.print")
    def test_emits_correct_dimensions(self, mock_print):
        """正しいディメンションが設定される"""
        metrics = {
            "event_to_processing_latency_ms": 0.0,
            "end_to_end_duration_ms": 0.0,
            "processing_duration_ms": 0.0,
        }

        emit_latency_metrics(metrics, "event-driven-prototype")

        emf_output = mock_print.call_args[0][0]
        emf_data = json.loads(emf_output)

        assert emf_data["UseCase"] == "event-driven-prototype"
        assert emf_data["TriggerMode"] == "event-driven"


class TestHandler:
    """handler 関数のテスト"""

    @patch.dict(os.environ, {"USE_CASE": "event-driven-prototype"})
    @patch("builtins.print")
    def test_normal_processing_result(self, mock_print):
        """正常な処理結果を受け取った場合"""
        event = {
            "time": "2024-01-15T10:30:00Z",
            "processing_result": {
                "event_time": "2024-01-15T10:30:00Z",
                "processing_duration_ms": 150.0,
                "event_to_processing_ms": 50.0,
                "status": "SUCCESS",
            },
        }
        context = MagicMock()
        context.function_name = "test-latency-reporter"

        result = handler(event, context)

        assert result["event_to_processing_latency_ms"] == 50.0
        assert result["processing_duration_ms"] == 150.0
        assert "reported_at" in result

    @patch.dict(os.environ, {"USE_CASE": "event-driven-prototype"})
    @patch("builtins.print")
    def test_error_in_processing_result(self, mock_print):
        """処理エラーが含まれる場合"""
        event = {
            "time": "2024-01-15T10:30:00Z",
            "processing_result": {},
            "error": {"Error": "States.TaskFailed", "Cause": "Lambda timeout"},
        }
        context = MagicMock()
        context.function_name = "test-latency-reporter"

        result = handler(event, context)

        assert "processing_error" in result

    @patch.dict(os.environ, {"USE_CASE": "event-driven-prototype"})
    @patch("builtins.print")
    def test_empty_processing_result(self, mock_print):
        """processing_result が空の場合"""
        event = {"time": "2024-01-15T10:30:00Z"}
        context = MagicMock()
        context.function_name = "test-latency-reporter"

        result = handler(event, context)

        assert result["processing_duration_ms"] == 0.0
        assert "reported_at" in result

    @patch.dict(os.environ, {"USE_CASE": "event-driven-prototype"})
    @patch("builtins.print")
    def test_event_time_from_processing_result(self, mock_print):
        """event_time が processing_result から取得される"""
        event = {
            "time": "2024-01-15T10:00:00Z",
            "processing_result": {
                "event_time": "2024-01-15T10:30:00Z",
                "processing_duration_ms": 100.0,
                "event_to_processing_ms": 25.0,
            },
        }
        context = MagicMock()
        context.function_name = "test-latency-reporter"

        result = handler(event, context)

        # event_time from processing_result takes priority
        assert result["event_to_processing_latency_ms"] == 25.0

    @patch.dict(os.environ, {"USE_CASE": "event-driven-prototype"})
    @patch("builtins.print")
    def test_fallback_to_event_time_field(self, mock_print):
        """processing_result に event_time がない場合は event.time を使用"""
        event = {
            "time": "2020-01-01T00:00:00Z",
            "processing_result": {
                "processing_duration_ms": 100.0,
            },
        }
        context = MagicMock()
        context.function_name = "test-latency-reporter"

        result = handler(event, context)

        # end_to_end should be calculated from event.time
        assert result["end_to_end_duration_ms"] > 0
