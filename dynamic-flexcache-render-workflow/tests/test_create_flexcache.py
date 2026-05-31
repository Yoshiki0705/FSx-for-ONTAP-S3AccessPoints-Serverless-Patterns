"""Create FlexCache Lambda のユニットテスト"""

from __future__ import annotations

import importlib.util
import os
from unittest.mock import patch


# 正しいハンドラーモジュールをロード
_handler_path = os.path.join(os.path.dirname(__file__), "..", "src", "create_flexcache", "handler.py")
_spec = importlib.util.spec_from_file_location("create_flexcache_handler", _handler_path)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
create_handler = _module.handler


class TestCreateFlexCacheSimulation:
    """シミュレーションモードのテスト"""

    @patch.dict(
        os.environ,
        {
            "SIMULATION_MODE": "true",
            "CACHE_VOLUME_PREFIX": "dyn_cache",
            "JUNCTION_PATH_PREFIX": "/cache",
        },
    )
    def test_create_simulation_basic(self):
        """シミュレーションモードで FlexCache 作成"""
        # Reload module with new env
        _spec.loader.exec_module(_module)

        event = {
            "job_id": "render-001",
            "project": "movie-xyz",
            "origin_volume": "render_assets",
            "origin_svm": "svm1",
            "cache_svm": "svm1",
            "size_gb": 200,
        }
        result = _module.handler(event, None)

        assert result["status"] == "created"
        assert result["cache_name"] == "dyn_cache_render_001"
        assert result["junction_path"] == "/cache/dyn_cache_render_001"
        assert result["size_gb"] == 200
        assert result["job_id"] == "render-001"
        assert result["project"] == "movie-xyz"
        assert result["simulation"] is True

    @patch.dict(
        os.environ,
        {
            "SIMULATION_MODE": "true",
            "CACHE_VOLUME_PREFIX": "fc",
            "JUNCTION_PATH_PREFIX": "/mnt",
        },
    )
    def test_create_simulation_custom_prefix(self):
        """カスタムプレフィックスでの作成"""
        _spec.loader.exec_module(_module)

        event = {
            "job_id": "eda-042",
            "project": "chip-alpha",
            "origin_volume": "tools",
            "origin_svm": "svm1",
            "cache_svm": "svm1",
            "size_gb": 500,
        }
        result = _module.handler(event, None)

        assert result["cache_name"] == "fc_eda_042"
        assert result["junction_path"] == "/mnt/fc_eda_042"

    @patch.dict(
        os.environ,
        {
            "SIMULATION_MODE": "true",
            "CACHE_VOLUME_PREFIX": "dyn_cache",
            "JUNCTION_PATH_PREFIX": "/cache",
        },
    )
    def test_create_idempotent_same_job_id(self):
        """同じ job_id は同じ cache_name を生成"""
        _spec.loader.exec_module(_module)

        event = {
            "job_id": "render-001",
            "project": "movie-xyz",
            "origin_volume": "assets",
            "origin_svm": "svm1",
            "cache_svm": "svm1",
            "size_gb": 100,
        }

        result1 = _module.handler(event, None)
        result2 = _module.handler(event, None)

        assert result1["cache_name"] == result2["cache_name"]

    @patch.dict(
        os.environ,
        {
            "SIMULATION_MODE": "true",
            "CACHE_VOLUME_PREFIX": "dyn_cache",
            "JUNCTION_PATH_PREFIX": "/cache",
        },
    )
    def test_create_different_job_ids(self):
        """異なる job_id は異なる cache_name を生成"""
        _spec.loader.exec_module(_module)

        event1 = {
            "job_id": "render-001",
            "project": "movie-xyz",
            "origin_volume": "assets",
            "origin_svm": "svm1",
            "cache_svm": "svm1",
            "size_gb": 100,
        }
        event2 = {**event1, "job_id": "render-002"}

        result1 = _module.handler(event1, None)
        result2 = _module.handler(event2, None)

        assert result1["cache_name"] != result2["cache_name"]
