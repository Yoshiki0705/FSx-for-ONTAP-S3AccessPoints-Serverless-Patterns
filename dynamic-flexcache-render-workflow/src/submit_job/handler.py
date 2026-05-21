"""Submit Job Lambda

モックジョブを投入する。実際の Deadline Cloud / AWS Batch / EDA scheduler
がない環境でもワークフローをデモ可能。

将来拡張:
- AWS Deadline Cloud
- AWS Batch
- IBM Spectrum LSF
- Slurm
"""

from __future__ import annotations

import json
import logging
import time
import uuid as uuid_mod
from typing import Any

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Submit Job Lambda ハンドラー

    Args:
        event: {
            "job_id": "render-001",
            "job_type": "render" | "eda" | "cae",
            "project": "movie-xyz",
            "cache_name": "dyn_cache_render_001",
            "junction_path": "/cache/dyn_cache_render_001",
            "parameters": {
                "frame_range": "1-100",
                "resolution": "4K",
                "simulate_failure": false,
                "simulate_duration_seconds": 30
            }
        }

    Returns:
        dict: ジョブ投入結果
    """
    logger.info("Submit job request: %s", json.dumps(event))

    job_id = event.get("job_id", str(uuid_mod.uuid4())[:8])
    job_type = event.get("job_type", "render")
    project = event.get("project", "default")
    parameters = event.get("parameters", {})

    # モックジョブ ID を生成
    mock_job_id = f"mock-{job_type}-{job_id}-{int(time.time())}"

    # ジョブ投入（モック）
    simulate_failure = parameters.get("simulate_failure", False)
    simulate_duration = parameters.get("simulate_duration_seconds", 30)

    result = {
        "status": "submitted",
        "mock_job_id": mock_job_id,
        "job_id": job_id,
        "job_type": job_type,
        "project": project,
        "cache_name": event.get("cache_name", ""),
        "junction_path": event.get("junction_path", ""),
        "simulate_failure": simulate_failure,
        "simulate_duration_seconds": simulate_duration,
        "submitted_at": int(time.time()),
        "expected_completion_at": int(time.time()) + simulate_duration,
        "poll_count": 0,
    }

    logger.info("Job submitted: %s (type: %s, duration: %ds)", mock_job_id, job_type, simulate_duration)

    return result
