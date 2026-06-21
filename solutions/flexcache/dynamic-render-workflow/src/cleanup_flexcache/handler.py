"""Cleanup FlexCache Lambda

ジョブ完了後に FlexCache ボリュームを削除する。
冪等性を確保し、既に削除済みの場合はスキップする。
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "shared"))

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

SIMULATION_MODE = os.environ.get("SIMULATION_MODE", "true").lower() == "true"


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Cleanup FlexCache Lambda ハンドラー

    Args:
        event: {
            "cache_name": "dyn_cache_render_001",
            "cache_uuid": "uuid-xxx",
            "job_id": "render-001",
            "force": false
        }

    Returns:
        dict: 削除結果
    """
    logger.info("Cleanup FlexCache request: %s", json.dumps(event))

    cache_name = event.get("cache_name", "")
    cache_uuid = event.get("cache_uuid", "")
    job_id = event.get("job_id", "")
    force = event.get("force", False)

    if not cache_name and not cache_uuid:
        return {
            "status": "skipped",
            "reason": "No cache_name or cache_uuid provided",
            "job_id": job_id,
            "timestamp": int(time.time()),
        }

    if SIMULATION_MODE:
        return _simulate_cleanup(cache_name, cache_uuid, job_id)

    return _real_cleanup(cache_name, cache_uuid, job_id, force)


def _simulate_cleanup(
    cache_name: str,
    cache_uuid: str,
    job_id: str,
) -> dict[str, Any]:
    """シミュレーションモードの FlexCache 削除"""
    logger.info("[SIMULATION] Deleted FlexCache: %s (uuid: %s)", cache_name, cache_uuid)
    return {
        "status": "deleted",
        "cache_name": cache_name,
        "cache_uuid": cache_uuid,
        "job_id": job_id,
        "simulation": True,
        "timestamp": int(time.time()),
    }


def _real_cleanup(
    cache_name: str,
    cache_uuid: str,
    job_id: str,
    force: bool,
) -> dict[str, Any]:
    """実環境の FlexCache 削除"""
    from shared.ontap_client import OntapClient, OntapClientConfig, OntapClientError

    config = OntapClientConfig(
        management_ip=os.environ["ONTAP_MANAGEMENT_IP"],
        secret_name=os.environ["ONTAP_SECRET_NAME"],
    )
    client = OntapClient(config)

    # UUID が不明な場合は名前で検索
    if not cache_uuid and cache_name:
        svm_name = os.environ.get("CACHE_SVM_NAME", "")
        existing = client.list_flexcaches(name=cache_name, svm_name=svm_name)
        if not existing:
            logger.info("FlexCache not found (already deleted?): %s", cache_name)
            return {
                "status": "not_found",
                "cache_name": cache_name,
                "reason": "FlexCache not found (already deleted or never created)",
                "job_id": job_id,
                "simulation": False,
                "timestamp": int(time.time()),
            }
        cache_uuid = existing[0]["uuid"]

    # FlexCache 削除
    try:
        result = client.delete_flexcache(uuid=cache_uuid)

        # 非同期ジョブの完了を待機
        job_link = result.get("job", {}).get("uuid")
        if job_link:
            client.wait_ontap_job(job_link, timeout_seconds=120)

        logger.info("FlexCache deleted successfully: %s (uuid: %s)", cache_name, cache_uuid)

        return {
            "status": "deleted",
            "cache_name": cache_name,
            "cache_uuid": cache_uuid,
            "job_id": job_id,
            "simulation": False,
            "timestamp": int(time.time()),
        }

    except OntapClientError as e:
        error_msg = str(e)
        # 既に削除済みの場合は成功扱い（冪等性）
        if e.status_code == 404 or "not found" in error_msg.lower():
            logger.info("FlexCache already deleted: %s", cache_name)
            return {
                "status": "already_deleted",
                "cache_name": cache_name,
                "cache_uuid": cache_uuid,
                "job_id": job_id,
                "simulation": False,
                "timestamp": int(time.time()),
            }

        logger.error("FlexCache deletion failed: %s", error_msg)
        return {
            "status": "failed",
            "cache_name": cache_name,
            "cache_uuid": cache_uuid,
            "error": error_msg,
            "job_id": job_id,
            "simulation": False,
            "timestamp": int(time.time()),
        }
