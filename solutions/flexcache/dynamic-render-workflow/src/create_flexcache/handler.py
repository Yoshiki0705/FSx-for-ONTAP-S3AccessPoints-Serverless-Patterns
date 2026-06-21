"""Create FlexCache Lambda

ONTAP REST API を使用して FlexCache ボリュームを動的に作成する。
冪等性を確保し、既存の同名 FlexCache がある場合はスキップする。
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any


# shared モジュールのパスを追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "shared"))

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

SIMULATION_MODE = os.environ.get("SIMULATION_MODE", "true").lower() == "true"


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Create FlexCache Lambda ハンドラー

    Args:
        event: {
            "job_id": "render-001",
            "project": "movie-xyz",
            "origin_volume": "render_assets",
            "origin_svm": "svm1",
            "cache_svm": "svm1",
            "size_gb": 200,
            "prepopulate_dirs": ["/scene01/", "/textures/"],
            "aggregate_name": "aggr1"
        }

    Returns:
        dict: FlexCache 作成結果
    """
    logger.info("Create FlexCache request: %s", json.dumps(event))

    job_id = event["job_id"]
    project = event.get("project", "default")
    origin_volume = event.get("origin_volume", os.environ.get("ORIGIN_VOLUME_NAME", ""))
    origin_svm = event.get("origin_svm", os.environ.get("ORIGIN_SVM_NAME", ""))
    cache_svm = event.get("cache_svm", os.environ.get("CACHE_SVM_NAME", ""))
    size_gb = event.get("size_gb", 100)
    aggregate_name = event.get("aggregate_name", os.environ.get("CACHE_AGGREGATE_NAME"))
    prepopulate_dirs = event.get("prepopulate_dirs", [])

    # FlexCache 名を job_id から決定（冪等性）
    cache_prefix = os.environ.get("CACHE_VOLUME_PREFIX", "dyn_cache")
    cache_name = f"{cache_prefix}_{job_id.replace('-', '_')}"
    junction_path_prefix = os.environ.get("JUNCTION_PATH_PREFIX", "/cache")
    junction_path = f"{junction_path_prefix}/{cache_name}"

    if SIMULATION_MODE:
        return _simulate_create(cache_name, junction_path, size_gb, job_id, project)

    return _real_create(
        cache_name=cache_name,
        junction_path=junction_path,
        origin_volume=origin_volume,
        origin_svm=origin_svm,
        cache_svm=cache_svm,
        size_gb=size_gb,
        aggregate_name=aggregate_name,
        prepopulate_dirs=prepopulate_dirs,
        job_id=job_id,
        project=project,
    )


def _simulate_create(
    cache_name: str,
    junction_path: str,
    size_gb: int,
    job_id: str,
    project: str,
) -> dict[str, Any]:
    """シミュレーションモードの FlexCache 作成"""
    import uuid as uuid_mod

    fake_uuid = str(uuid_mod.uuid4())
    logger.info("[SIMULATION] Created FlexCache: %s (uuid: %s)", cache_name, fake_uuid)

    return {
        "status": "created",
        "cache_name": cache_name,
        "cache_uuid": fake_uuid,
        "junction_path": junction_path,
        "size_gb": size_gb,
        "job_id": job_id,
        "project": project,
        "simulation": True,
        "timestamp": int(time.time()),
    }


def _real_create(
    cache_name: str,
    junction_path: str,
    origin_volume: str,
    origin_svm: str,
    cache_svm: str,
    size_gb: int,
    aggregate_name: str | None,
    prepopulate_dirs: list[str],
    job_id: str,
    project: str,
) -> dict[str, Any]:
    """実環境の FlexCache 作成"""
    from shared.ontap_client import OntapClient, OntapClientConfig, OntapClientError

    config = OntapClientConfig(
        management_ip=os.environ["ONTAP_MANAGEMENT_IP"],
        secret_name=os.environ["ONTAP_SECRET_NAME"],
    )
    client = OntapClient(config)

    # 冪等性チェック: 同名の FlexCache が既に存在するか
    existing = client.list_flexcaches(name=cache_name, svm_name=cache_svm)
    if existing:
        logger.info("FlexCache already exists: %s (uuid: %s)", cache_name, existing[0]["uuid"])
        return {
            "status": "already_exists",
            "cache_name": cache_name,
            "cache_uuid": existing[0]["uuid"],
            "junction_path": existing[0].get("path", junction_path),
            "job_id": job_id,
            "project": project,
            "simulation": False,
            "timestamp": int(time.time()),
        }

    # FlexCache 作成
    try:
        enable_prepopulate = os.environ.get("ENABLE_PREPOPULATE", "true").lower() == "true"
        result = client.create_flexcache(
            name=cache_name,
            svm_name=cache_svm,
            origin_volume=origin_volume,
            origin_svm=origin_svm,
            size_gb=size_gb,
            junction_path=junction_path,
            aggregate_name=aggregate_name,
            prepopulate_dir_paths=prepopulate_dirs if enable_prepopulate and prepopulate_dirs else None,
        )

        # 非同期ジョブの完了を待機
        job_link = result.get("job", {}).get("uuid")
        if job_link:
            client.wait_ontap_job(job_link, timeout_seconds=180)

        # 作成された FlexCache の UUID を取得
        created = client.list_flexcaches(name=cache_name, svm_name=cache_svm)
        cache_uuid = created[0]["uuid"] if created else "unknown"

        logger.info("FlexCache created successfully: %s (uuid: %s)", cache_name, cache_uuid)

        return {
            "status": "created",
            "cache_name": cache_name,
            "cache_uuid": cache_uuid,
            "junction_path": junction_path,
            "size_gb": size_gb,
            "job_id": job_id,
            "project": project,
            "simulation": False,
            "timestamp": int(time.time()),
        }

    except OntapClientError as e:
        logger.error("FlexCache creation failed: %s", str(e))
        return {
            "status": "failed",
            "cache_name": cache_name,
            "error": str(e),
            "job_id": job_id,
            "project": project,
            "simulation": False,
            "timestamp": int(time.time()),
        }
