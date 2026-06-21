"""Monitor Job Lambda

モックジョブの状態を監視する。数回ポーリング後に SUCCEEDED を返す。
simulate_failure パラメータで FAILED/TIMEOUT も再現可能。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Monitor Job Lambda ハンドラー

    Args:
        event: {
            "mock_job_id": "mock-render-001-1234567890",
            "job_id": "render-001",
            "submitted_at": 1234567890,
            "expected_completion_at": 1234567920,
            "simulate_failure": false,
            "poll_count": 0
        }

    Returns:
        dict: ジョブ状態
    """
    logger.info("Monitor job: %s", json.dumps(event))

    mock_job_id = event.get("mock_job_id", "")
    submitted_at = event.get("submitted_at", 0)
    expected_completion_at = event.get("expected_completion_at", 0)
    simulate_failure = event.get("simulate_failure", False)
    poll_count = event.get("poll_count", 0) + 1

    current_time = int(time.time())

    # シミュレーション: 期待完了時刻を過ぎたら完了
    if current_time >= expected_completion_at:
        if simulate_failure:
            status = "FAILED"
            message = "Simulated job failure for testing"
        else:
            status = "SUCCEEDED"
            message = "Job completed successfully"
    else:
        status = "RUNNING"
        elapsed = current_time - submitted_at
        total = expected_completion_at - submitted_at
        progress = min(95, int((elapsed / max(total, 1)) * 100))
        message = f"Job running... {progress}% complete"

    result = {
        "mock_job_id": mock_job_id,
        "job_id": event.get("job_id", ""),
        "status": status,
        "message": message,
        "poll_count": poll_count,
        "submitted_at": submitted_at,
        "expected_completion_at": expected_completion_at,
        "current_time": current_time,
        "simulate_failure": simulate_failure,
        # Step Functions の Choice State で使用
        "is_terminal": status in ("SUCCEEDED", "FAILED", "TIMEOUT"),
        "is_success": status == "SUCCEEDED",
        # 次のポーリングのために引き継ぐ
        "cache_name": event.get("cache_name", ""),
        "cache_uuid": event.get("cache_uuid", ""),
        "project": event.get("project", ""),
    }

    logger.info("Job %s status: %s (poll #%d)", mock_job_id, status, poll_count)

    return result
