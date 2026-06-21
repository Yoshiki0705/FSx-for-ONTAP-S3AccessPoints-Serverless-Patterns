"""Cleanup FlexCache Lambda のユニットテスト"""

from __future__ import annotations

import importlib.util
import os
from unittest.mock import patch


_handler_path = os.path.join(os.path.dirname(__file__), "..", "src", "cleanup_flexcache", "handler.py")
_spec = importlib.util.spec_from_file_location("cleanup_flexcache_handler", _handler_path)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)


class TestCleanupFlexCacheSimulation:
    """シミュレーションモードのテスト"""

    @patch.dict(os.environ, {"SIMULATION_MODE": "true"})
    def test_cleanup_simulation_basic(self):
        """シミュレーションモードで FlexCache 削除"""
        _spec.loader.exec_module(_module)

        event = {
            "cache_name": "dyn_cache_render_001",
            "cache_uuid": "uuid-123",
            "job_id": "render-001",
        }
        result = _module.handler(event, None)

        assert result["status"] == "deleted"
        assert result["cache_name"] == "dyn_cache_render_001"
        assert result["simulation"] is True

    @patch.dict(os.environ, {"SIMULATION_MODE": "true"})
    def test_cleanup_simulation_no_cache_info(self):
        """キャッシュ情報なしの場合はスキップ"""
        _spec.loader.exec_module(_module)

        event = {
            "cache_name": "",
            "cache_uuid": "",
            "job_id": "render-001",
        }
        result = _module.handler(event, None)

        assert result["status"] == "skipped"

    @patch.dict(os.environ, {"SIMULATION_MODE": "true"})
    def test_cleanup_idempotent(self):
        """複数回の cleanup 呼び出しが全て成功"""
        _spec.loader.exec_module(_module)

        event = {
            "cache_name": "dyn_cache_render_001",
            "cache_uuid": "uuid-123",
            "job_id": "render-001",
        }

        result1 = _module.handler(event, None)
        result2 = _module.handler(event, None)

        assert result1["status"] == "deleted"
        assert result2["status"] == "deleted"
