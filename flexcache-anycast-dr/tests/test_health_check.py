"""Health Check Lambda のユニットテスト"""

from __future__ import annotations

import importlib.util
import os
from unittest.mock import patch


_handler_path = os.path.join(os.path.dirname(__file__), "..", "src", "health_check", "handler.py")
_spec = importlib.util.spec_from_file_location("health_check_handler", _handler_path)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)


class TestHealthCheckSimulation:
    """シミュレーションモードのテスト"""

    @patch.dict(
        os.environ,
        {
            "SIMULATION_MODE": "true",
            "CACHE_ENDPOINTS": "cache-a.example.com,cache-b.example.com",
        },
    )
    def test_basic_health_check(self):
        """基本的なヘルスチェック"""
        _spec.loader.exec_module(_module)

        event = {
            "cache_endpoints": ["cache-a.example.com", "cache-b.example.com"],
            "check_type": "basic",
        }
        result = _module.handler(event, None)

        assert result["status"] == "completed"
        assert result["simulation_mode"] is True
        assert len(result["results"]) == 2
        assert result["summary"]["total_caches"] == 2

    @patch.dict(
        os.environ,
        {
            "SIMULATION_MODE": "true",
            "CACHE_ENDPOINTS": "cache-a.example.com",
        },
    )
    def test_detailed_health_check(self):
        """詳細ヘルスチェック"""
        _spec.loader.exec_module(_module)

        event = {
            "cache_endpoints": ["cache-a.example.com"],
            "check_type": "detailed",
        }
        result = _module.handler(event, None)

        assert result["check_type"] == "detailed"
        cache_result = result["results"][0]
        assert "endpoint" in cache_result
        assert "healthy" in cache_result

    @patch.dict(
        os.environ,
        {
            "SIMULATION_MODE": "true",
            "CACHE_ENDPOINTS": "",
        },
    )
    def test_empty_endpoints(self):
        """エンドポイントなしの場合"""
        _spec.loader.exec_module(_module)

        event = {
            "cache_endpoints": [],
            "check_type": "basic",
        }
        result = _module.handler(event, None)

        assert result["status"] == "completed"
        assert len(result["results"]) == 0
        assert result["summary"]["total_caches"] == 0

    @patch.dict(
        os.environ,
        {
            "SIMULATION_MODE": "true",
            "CACHE_ENDPOINTS": "a.example.com,b.example.com,c.example.com",
        },
    )
    def test_uses_env_endpoints_when_not_in_event(self):
        """イベントにエンドポイントがない場合は環境変数を使用"""
        _spec.loader.exec_module(_module)

        event = {"check_type": "basic"}
        result = _module.handler(event, None)

        assert result["summary"]["total_caches"] == 3


class TestHealthCheckSummary:
    """サマリー生成のテスト"""

    @patch.dict(os.environ, {"SIMULATION_MODE": "true", "CACHE_ENDPOINTS": ""})
    def test_summary_fields(self):
        """サマリーに必要なフィールドが含まれる"""
        _spec.loader.exec_module(_module)

        event = {
            "cache_endpoints": ["a.example.com"],
            "check_type": "basic",
        }
        result = _module.handler(event, None)

        summary = result["summary"]
        assert "total_caches" in summary
        assert "healthy" in summary
        assert "unhealthy" in summary
        assert "avg_latency_ms" in summary
        assert "all_healthy" in summary
