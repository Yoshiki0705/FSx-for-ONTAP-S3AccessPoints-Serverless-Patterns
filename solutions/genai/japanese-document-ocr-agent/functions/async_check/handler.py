"""OCR (async check) Lambda — 日本語文書 OCR × AgentCore Gateway パターン。

非同期ジョブの状態を 1 回だけ確認する。ステートマシンの Wait → Check → Choice ループの
中身。結果は取得しない（`MaxResults=1` で状態だけ見る）。

待機間隔は段階的に伸ばす（5 → 10 → 15 → 20 → 30 秒、以降 30 秒）。固定間隔にすると、
長いジョブで Standard の実行履歴（25,000 イベント）を消費する。`AsyncJobMaxSeconds` を超えたら
`TIMED_OUT` を返してループを終える。Textract のジョブには取り消し手段がなく、タイムアウト後も
ジョブは走り続けて課金されうる。

Environment Variables:
    ASYNC_JOB_MAX_SECONDS: ジョブの待機上限（秒）
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from shared.exceptions import TextractRejected, lambda_error_handler
from shared.textract_helper import FEATURE_PROFILES, build_client, classify_client_error

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_textract = build_client()

#: 待機間隔の段階（秒）。最後の値を以降も使う。
WAIT_SCHEDULE = (5, 10, 15, 20, 30)


def next_wait_seconds(poll_index: int) -> int:
    """次の待機秒数を返す。

    Args:
        poll_index: これまでの確認回数（0 始まり）。

    Returns:
        `WAIT_SCHEDULE` の対応する値。範囲を超えたら最後の値。
    """
    return WAIT_SCHEDULE[min(max(poll_index, 0), len(WAIT_SCHEDULE) - 1)]


@lambda_error_handler
def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """OCR (async check) Lambda ハンドラー。

    Args:
        event: Map の項目。`job`（`async_start` の戻り値）と `profile` を持つ。
        context: Lambda コンテキスト。

    Returns:
        更新した `job`。`status` は `IN_PROGRESS`、`SUCCEEDED`、`PARTIAL_SUCCESS`、`FAILED`、
        `TIMED_OUT` のいずれか。`IN_PROGRESS` のときは `wait_seconds` に次の待機秒数を入れる。

    Raises:
        TextractThrottled: スロットリング（Step Functions が再試行する）。
        TextractTransient: 一時的な失敗（Step Functions が再試行する）。
        TextractRejected: ジョブ ID が不正など（再試行しない）。
    """
    job = dict(event["job"])
    features = FEATURE_PROFILES[event["profile"]]
    max_seconds = int(os.environ.get("ASYNC_JOB_MAX_SECONDS", "600"))
    elapsed = int(time.time()) - int(job.get("started_at", time.time()))

    try:
        if features:
            response = _textract.get_document_analysis(JobId=job["job_id"], MaxResults=1)
        else:
            response = _textract.get_document_text_detection(JobId=job["job_id"], MaxResults=1)
    except Exception as e:  # noqa: BLE001 — 分類してから再送出する
        error = classify_client_error(e)
        if isinstance(error, TextractRejected):
            logger.warning("Job %s cannot be checked: %s", job["job_id"], error)
        raise error from e

    status = response["JobStatus"]
    poll_index = int(job.get("poll_index", 0)) + 1
    if status == "IN_PROGRESS" and elapsed >= max_seconds:
        status = "TIMED_OUT"
    job.update(
        {
            "status": status,
            "poll_index": poll_index,
            "elapsed_seconds": elapsed,
            "wait_seconds": next_wait_seconds(poll_index),
        }
    )
    if response.get("StatusMessage"):
        job["status_message"] = str(response["StatusMessage"])[:200]
    logger.info("Job %s: status=%s polls=%d elapsed=%ds", job["job_id"], status, poll_index, elapsed)
    return job
