"""Route Decision Lambda のユニットテスト"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "route_decision"))


@pytest.fixture
def mock_dynamodb():
    """DynamoDB テーブルのモック"""
    with patch("handler.dynamodb") as mock_ddb:
        mock_table = MagicMock()
        mock_ddb.Table.return_value = mock_table
        yield mock_table


class TestRouteDecisionStrategies:
    """ルーティング戦略のテスト"""

    @patch.dict(os.environ, {
        "ROUTING_TABLE_NAME": "TestRoutingTable",
        "CACHE_ENDPOINTS": "a.example.com,b.example.com",
    })
    def test_latency_based_selects_lowest(self, mock_dynamodb):
        """レイテンシベースで最小レイテンシを選択"""
        mock_dynamodb.scan.return_value = {
            "Items": [
                {"cache_id": "cache-a", "endpoint": "a.example.com", "latency_ms": "50", "weight": "50", "health": "healthy", "region": "ap-northeast-1"},
                {"cache_id": "cache-b", "endpoint": "b.example.com", "latency_ms": "10", "weight": "50", "health": "healthy", "region": "us-west-2"},
            ]
        }

        from handler import handler

        event = {
            "client_region": "ap-northeast-1",
            "strategy": "latency_based",
        }
        result = handler(event, None)

        assert result["status"] == "selected"
        assert result["selected_cache"] == "cache-b"  # 低レイテンシ

    @patch.dict(os.environ, {
        "ROUTING_TABLE_NAME": "TestRoutingTable",
        "CACHE_ENDPOINTS": "",
    })
    def test_region_affinity_prefers_same_region(self, mock_dynamodb):
        """リージョンアフィニティで同一リージョンを優先"""
        mock_dynamodb.scan.return_value = {
            "Items": [
                {"cache_id": "cache-a", "endpoint": "a.example.com", "latency_ms": "50", "weight": "50", "health": "healthy", "region": "ap-northeast-1"},
                {"cache_id": "cache-b", "endpoint": "b.example.com", "latency_ms": "10", "weight": "50", "health": "healthy", "region": "us-west-2"},
            ]
        }

        from handler import handler

        event = {
            "client_region": "ap-northeast-1",
            "strategy": "region_affinity",
        }
        result = handler(event, None)

        assert result["selected_cache"] == "cache-a"  # 同一リージョン

    @patch.dict(os.environ, {
        "ROUTING_TABLE_NAME": "TestRoutingTable",
        "CACHE_ENDPOINTS": "",
    })
    def test_failover_selects_by_priority(self, mock_dynamodb):
        """フェイルオーバーで優先度順に選択"""
        mock_dynamodb.scan.return_value = {
            "Items": [
                {"cache_id": "cache-a", "endpoint": "a.example.com", "latency_ms": "50", "priority": "2", "health": "healthy"},
                {"cache_id": "cache-b", "endpoint": "b.example.com", "latency_ms": "10", "priority": "1", "health": "healthy"},
            ]
        }

        from handler import handler

        event = {
            "client_region": "ap-northeast-1",
            "strategy": "failover",
        }
        result = handler(event, None)

        assert result["selected_cache"] == "cache-b"  # 低 priority = 高優先度

    @patch.dict(os.environ, {
        "ROUTING_TABLE_NAME": "TestRoutingTable",
        "CACHE_ENDPOINTS": "",
    })
    def test_no_candidates_returns_error(self, mock_dynamodb):
        """候補なしの場合はエラー"""
        mock_dynamodb.scan.return_value = {"Items": []}

        from handler import handler

        event = {
            "client_region": "ap-northeast-1",
            "strategy": "latency_based",
        }
        result = handler(event, None)

        assert result["status"] == "no_candidates"
        assert "error" in result

    @patch.dict(os.environ, {
        "ROUTING_TABLE_NAME": "TestRoutingTable",
        "CACHE_ENDPOINTS": "",
    })
    def test_exclude_caches(self, mock_dynamodb):
        """除外リストが適用される"""
        mock_dynamodb.scan.return_value = {
            "Items": [
                {"cache_id": "cache-a", "endpoint": "a.example.com", "latency_ms": "5", "health": "healthy"},
                {"cache_id": "cache-b", "endpoint": "b.example.com", "latency_ms": "10", "health": "healthy"},
            ]
        }

        from handler import handler

        event = {
            "client_region": "ap-northeast-1",
            "strategy": "latency_based",
            "exclude_caches": ["cache-a"],
        }
        result = handler(event, None)

        assert result["selected_cache"] == "cache-b"  # cache-a は除外


class TestRouteDecisionFallback:
    """フォールバックのテスト"""

    @patch.dict(os.environ, {
        "ROUTING_TABLE_NAME": "TestRoutingTable",
        "CACHE_ENDPOINTS": "fallback-a.example.com,fallback-b.example.com",
    })
    def test_dynamodb_failure_uses_static_candidates(self, mock_dynamodb):
        """DynamoDB 障害時は静的候補を使用"""
        mock_dynamodb.scan.side_effect = Exception("DynamoDB unavailable")

        from handler import handler

        event = {
            "client_region": "ap-northeast-1",
            "strategy": "latency_based",
        }
        result = handler(event, None)

        assert result["status"] == "selected"
        assert "static-cache" in result["selected_cache"]
