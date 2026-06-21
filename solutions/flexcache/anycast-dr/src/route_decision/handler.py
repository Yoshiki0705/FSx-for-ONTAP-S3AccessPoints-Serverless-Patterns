"""FlexCache Route Decision Lambda

クライアントリージョン、レイテンシ、重み、ヘルス状態に基づいて
最適な FlexCache エンドポイントを選択する。

BGP/VIP が利用できない FSx for ONTAP 環境での AnyCast シミュレーション。
"""

from __future__ import annotations

import json
import logging
import os
import random
import time
from typing import Any

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Route Decision Lambda ハンドラー

    Args:
        event: {
            "client_region": "ap-northeast-1",
            "strategy": "latency_based" | "weighted" | "region_affinity" | "failover",
            "exclude_caches": ["cache-id-to-exclude"]
        }

    Returns:
        dict: 選択されたキャッシュ情報
    """
    logger.info("Route decision requested: %s", json.dumps(event))

    client_region = event.get("client_region", os.environ.get("AWS_REGION", "ap-northeast-1"))
    strategy = event.get("strategy", "latency_based")
    exclude_caches = event.get("exclude_caches", [])

    # ルーティングテーブルから候補を取得
    candidates = _get_healthy_candidates(exclude_caches)

    if not candidates:
        logger.warning("No healthy cache candidates available")
        return {
            "status": "no_candidates",
            "error": "No healthy FlexCache endpoints available",
            "timestamp": int(time.time()),
        }

    # 戦略に基づいてキャッシュを選択
    selected = _select_cache(candidates, strategy, client_region)

    result = {
        "status": "selected",
        "selected_cache": selected["cache_id"],
        "endpoint": selected.get("endpoint", ""),
        "s3ap_alias": selected.get("s3ap_alias", ""),
        "region": selected.get("region", ""),
        "strategy": strategy,
        "candidates_count": len(candidates),
        "timestamp": int(time.time()),
    }

    logger.info("Route decision result: %s", json.dumps(result))
    return result


def _get_healthy_candidates(exclude_caches: list[str]) -> list[dict]:
    """DynamoDB からヘルシーなキャッシュ候補を取得"""
    table_name = os.environ.get("ROUTING_TABLE_NAME", "FlexCacheRoutingTable")

    try:
        table = dynamodb.Table(table_name)
        response = table.scan(
            FilterExpression="health = :h",
            ExpressionAttributeValues={":h": "healthy"},
        )
        candidates = response.get("Items", [])

        # 除外リストを適用
        if exclude_caches:
            candidates = [c for c in candidates if c["cache_id"] not in exclude_caches]

        return candidates

    except Exception as e:
        logger.error("Failed to get candidates from DynamoDB: %s", str(e))
        # フォールバック: 環境変数から静的候補を取得
        return _get_static_candidates()


def _get_static_candidates() -> list[dict]:
    """環境変数から静的キャッシュ候補を取得（DynamoDB 障害時のフォールバック）"""
    endpoints_str = os.environ.get("CACHE_ENDPOINTS", "")
    if not endpoints_str:
        return []

    candidates = []
    for i, endpoint in enumerate(endpoints_str.split(",")):
        endpoint = endpoint.strip()
        if endpoint:
            candidates.append(
                {
                    "cache_id": f"static-cache-{i}",
                    "endpoint": endpoint,
                    "region": os.environ.get("AWS_REGION", "ap-northeast-1"),
                    "weight": "50",
                    "latency_ms": "10",
                    "health": "healthy",
                }
            )
    return candidates


def _select_cache(
    candidates: list[dict],
    strategy: str,
    client_region: str,
) -> dict:
    """戦略に基づいてキャッシュを選択"""
    if strategy == "latency_based":
        return _select_by_latency(candidates)
    elif strategy == "weighted":
        return _select_by_weight(candidates)
    elif strategy == "region_affinity":
        return _select_by_region(candidates, client_region)
    elif strategy == "failover":
        return _select_failover(candidates)
    else:
        logger.warning("Unknown strategy '%s', falling back to latency_based", strategy)
        return _select_by_latency(candidates)


def _select_by_latency(candidates: list[dict]) -> dict:
    """レイテンシが最小のキャッシュを選択"""
    return min(candidates, key=lambda c: int(c.get("latency_ms", 9999)))


def _select_by_weight(candidates: list[dict]) -> dict:
    """重み付きランダム選択"""
    weights = [int(c.get("weight", 1)) for c in candidates]
    return random.choices(candidates, weights=weights, k=1)[0]


def _select_by_region(candidates: list[dict], client_region: str) -> dict:
    """同一リージョン優先、なければレイテンシベース"""
    same_region = [c for c in candidates if c.get("region") == client_region]
    if same_region:
        return _select_by_latency(same_region)
    return _select_by_latency(candidates)


def _select_failover(candidates: list[dict]) -> dict:
    """優先度順（priority フィールド）で選択"""
    return min(candidates, key=lambda c: int(c.get("priority", 100)))
