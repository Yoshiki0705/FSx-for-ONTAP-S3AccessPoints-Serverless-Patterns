"""Monitor Job Lambda のユニットテスト"""

from __future__ import annotations

import importlib.util
import os
import time


_handler_path = os.path.join(
    os.path.dirname(__file__), "..", "src", "monitor_job", "handler.py"
)
_spec = importlib.util.spec_from_file_location("monitor_job_handler", _handler_path)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)


class TestMonitorJob:
    """Monitor Job Lambda のテスト"""

    def test_job_running(self):
        """ジョブ実行中の状態"""
        future_time = int(time.time()) + 3600
        event = {
            "mock_job_id": "mock-render-001",
            "job_id": "render-001",
            "submitted_at": int(time.time()),
            "expected_completion_at": future_time,
            "simulate_failure": False,
            "poll_count": 0,
            "cache_name": "dyn_cache_render_001",
            "cache_uuid": "uuid-123",
            "project": "movie-xyz",
        }
        result = _module.handler(event, None)

        assert result["status"] == "RUNNING"
        assert result["is_terminal"] is False
        assert result["is_success"] is False
        assert result["poll_count"] == 1

    def test_job_completed(self):
        """ジョブ完了の状態"""
        past_time = int(time.time()) - 100
        event = {
            "mock_job_id": "mock-render-001",
            "job_id": "render-001",
            "submitted_at": past_time - 100,
            "expected_completion_at": past_time,
            "simulate_failure": False,
            "poll_count": 5,
            "cache_name": "dyn_cache_render_001",
            "cache_uuid": "uuid-123",
            "project": "movie-xyz",
        }
        result = _module.handler(event, None)

        assert result["status"] == "SUCCEEDED"
        assert result["is_terminal"] is True
        assert result["is_success"] is True

    def test_job_failed(self):
        """ジョブ失敗のシミュレーション"""
        past_time = int(time.time()) - 100
        event = {
            "mock_job_id": "mock-render-001",
            "job_id": "render-001",
            "submitted_at": past_time - 100,
            "expected_completion_at": past_time,
            "simulate_failure": True,
            "poll_count": 5,
            "cache_name": "dyn_cache_render_001",
            "cache_uuid": "uuid-123",
            "project": "movie-xyz",
        }
        result = _module.handler(event, None)

        assert result["status"] == "FAILED"
        assert result["is_terminal"] is True
        assert result["is_success"] is False

    def test_poll_count_increments(self):
        """ポーリングカウントが増加する"""
        future_time = int(time.time()) + 3600
        event = {
            "mock_job_id": "mock-render-001",
            "job_id": "render-001",
            "submitted_at": int(time.time()),
            "expected_completion_at": future_time,
            "simulate_failure": False,
            "poll_count": 3,
        }
        result = _module.handler(event, None)

        assert result["poll_count"] == 4

    def test_preserves_cache_info(self):
        """キャッシュ情報が引き継がれる"""
        future_time = int(time.time()) + 3600
        event = {
            "mock_job_id": "mock-render-001",
            "job_id": "render-001",
            "submitted_at": int(time.time()),
            "expected_completion_at": future_time,
            "simulate_failure": False,
            "poll_count": 0,
            "cache_name": "my_cache",
            "cache_uuid": "my-uuid",
            "project": "my-project",
        }
        result = _module.handler(event, None)

        assert result["cache_name"] == "my_cache"
        assert result["cache_uuid"] == "my-uuid"
        assert result["project"] == "my-project"
