"""FlexCache Health Check Lambda

FlexCache ノードのヘルスチェックを実行し、結果を返す。
シミュレーションモードでは実際の ONTAP API を呼ばずにモックデータを返す。
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

SIMULATION_MODE = os.environ.get("SIMULATION_MODE", "true").lower() == "true"


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """FlexCache ヘルスチェック Lambda ハンドラー

    Args:
        event: {
            "cache_endpoints": ["endpoint1", "endpoint2"],
            "check_type": "basic" | "detailed"
        }

    Returns:
        dict: ヘルスチェック結果
    """
    logger.info("FlexCache health check started: %s", json.dumps(event))

    cache_endpoints = event.get("cache_endpoints", [])
    check_type = event.get("check_type", "basic")

    if not cache_endpoints:
        cache_endpoints = _get_cache_endpoints_from_env()

    results = []
    for endpoint in cache_endpoints:
        if SIMULATION_MODE:
            result = _simulate_health_check(endpoint, check_type)
        else:
            result = _real_health_check(endpoint, check_type)
        results.append(result)

    summary = _build_summary(results)

    logger.info("Health check completed: %s", json.dumps(summary))

    return {
        "status": "completed",
        "timestamp": int(time.time()),
        "check_type": check_type,
        "simulation_mode": SIMULATION_MODE,
        "results": results,
        "summary": summary,
    }


def _get_cache_endpoints_from_env() -> list[str]:
    """環境変数からキャッシュエンドポイントを取得"""
    endpoints_str = os.environ.get("CACHE_ENDPOINTS", "")
    if not endpoints_str:
        return []
    return [e.strip() for e in endpoints_str.split(",") if e.strip()]


def _simulate_health_check(endpoint: str, check_type: str) -> dict[str, Any]:
    """シミュレーションモードのヘルスチェック"""
    import hashlib
    import random

    # エンドポイント名からシード生成（再現性のため）
    seed = int(hashlib.md5(endpoint.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed + int(time.time() // 300))

    is_healthy = rng.random() > 0.1  # 90% の確率で healthy

    result = {
        "endpoint": endpoint,
        "healthy": is_healthy,
        "latency_ms": rng.randint(1, 50) if is_healthy else -1,
        "cache_hit_ratio": round(rng.uniform(0.7, 0.95), 3) if is_healthy else 0.0,
        "volume_state": "online" if is_healthy else "offline",
    }

    if check_type == "detailed":
        result.update(
            {
                "storage_used_percent": rng.randint(30, 85),
                "origin_reachable": rng.random() > 0.05,
                "peer_state": "available" if is_healthy else "unavailable",
                "last_data_fetch_seconds_ago": rng.randint(1, 3600),
            }
        )

    return result


def _real_health_check(endpoint: str, check_type: str) -> dict[str, Any]:
    """実環境のヘルスチェック（ONTAP REST API 経由）"""
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "shared"))

    try:
        from shared.ontap_client import OntapClient, OntapClientConfig

        config = OntapClientConfig(
            management_ip=endpoint,
            secret_name=os.environ["ONTAP_SECRET_NAME"],
            connect_timeout=5.0,
            read_timeout=10.0,
        )
        client = OntapClient(config)

        # FlexCache ボリューム一覧取得
        start = time.time()
        volumes = client.list_volumes()
        latency_ms = int((time.time() - start) * 1000)

        flexcache_volumes = [v for v in volumes if v.get("style") == "flexcache"]

        result = {
            "endpoint": endpoint,
            "healthy": True,
            "latency_ms": latency_ms,
            "volume_state": "online",
            "flexcache_count": len(flexcache_volumes),
        }

        if check_type == "detailed":
            # クラスタピア状態確認
            peers = client.get("/cluster/peers")
            peer_records = peers.get("records", [])
            all_peers_available = all(p.get("status", {}).get("state") == "available" for p in peer_records)
            result.update(
                {
                    "origin_reachable": all_peers_available,
                    "peer_state": "available" if all_peers_available else "degraded",
                    "peer_count": len(peer_records),
                }
            )

        return result

    except Exception as e:
        logger.error("Health check failed for %s: %s", endpoint, str(e))
        return {
            "endpoint": endpoint,
            "healthy": False,
            "latency_ms": -1,
            "volume_state": "unknown",
            "error": str(e),
        }


def _build_summary(results: list[dict]) -> dict[str, Any]:
    """ヘルスチェック結果のサマリーを生成"""
    total = len(results)
    healthy = sum(1 for r in results if r.get("healthy"))
    unhealthy = total - healthy

    healthy_latencies = [r["latency_ms"] for r in results if r.get("healthy") and r["latency_ms"] > 0]
    avg_latency = sum(healthy_latencies) / len(healthy_latencies) if healthy_latencies else 0

    return {
        "total_caches": total,
        "healthy": healthy,
        "unhealthy": unhealthy,
        "avg_latency_ms": round(avg_latency, 1),
        "all_healthy": unhealthy == 0,
    }
