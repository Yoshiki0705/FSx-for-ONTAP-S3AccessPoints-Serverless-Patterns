"""UC29 Self-Service KB Curation — Auto-Sync Lambda

S3 Access Point 経由で AI 専用ボリュームのファイル投入（追加・更新）を検知し、
差分があればマネージド Amazon Bedrock Knowledge Base の取り込み（Ingestion）を
自動起動する。業務ユーザーは Windows ドラッグ&ドロップでファイルを置くだけでよい。

差分検知ロジック:
  直近の Ingestion ジョブ開始時刻を取得し、それ以降に LastModified された
  オブジェクトを「変更あり」とみなす。変更があれば新規 Ingestion を起動する。
  event に {"force": true} を渡すと差分の有無に関わらず起動する。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

s3_client = boto3.client("s3")
bedrock_agent = boto3.client("bedrock-agent")
sns_client = boto3.client("sns")

# サポートするファイル拡張子（Bedrock KB が取り込み可能な代表的形式）
SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".doc",
    ".txt",
    ".md",
    ".pptx",
    ".xlsx",
    ".csv",
    ".html",
    ".htm",
}


def _epoch_floor() -> datetime:
    """初回同期判定用の最小時刻（UTC aware）。"""
    return datetime(1970, 1, 1, tzinfo=timezone.utc)


def _last_ingestion_time(kb_id: str, ds_id: str) -> datetime:
    """直近の Ingestion ジョブ開始時刻を返す。履歴がなければ epoch。"""
    try:
        resp = bedrock_agent.list_ingestion_jobs(
            knowledgeBaseId=kb_id,
            dataSourceId=ds_id,
            sortBy={"attribute": "STARTED_AT", "order": "DESCENDING"},
            maxResults=1,
        )
        jobs = resp.get("ingestionJobSummaries", [])
        if jobs and jobs[0].get("startedAt"):
            started = jobs[0]["startedAt"]
            # boto3 は timezone-aware datetime を返す
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            return started
    except Exception as e:  # noqa: BLE001 - 履歴取得失敗時は全件を変更扱い
        logger.warning("list_ingestion_jobs failed, treating all as changed: %s", str(e))
    return _epoch_floor()


def _active_ingestion_job(kb_id: str, ds_id: str) -> str:
    """進行中（STARTING / IN_PROGRESS）の Ingestion ジョブ ID を返す。なければ空文字。

    多重起動を防ぐためのガード。
    """
    try:
        for state in ("STARTING", "IN_PROGRESS"):
            resp = bedrock_agent.list_ingestion_jobs(
                knowledgeBaseId=kb_id,
                dataSourceId=ds_id,
                filters=[{"attribute": "STATUS", "operator": "EQ", "values": [state]}],
                maxResults=1,
            )
            jobs = resp.get("ingestionJobSummaries", [])
            if jobs:
                return jobs[0].get("ingestionJobId", "active")
    except Exception as e:  # noqa: BLE001 - 取得失敗時はガードせず継続
        logger.warning("active ingestion check failed: %s", str(e))
    return ""


def _count_changed_files(s3ap_alias: str, prefix: str, since: datetime) -> int:
    """since 以降に LastModified された対象ファイル数を数える。"""
    changed = 0
    continuation_token = None
    while True:
        kwargs: dict[str, Any] = {"Bucket": s3ap_alias, "Prefix": prefix, "MaxKeys": 1000}
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token

        response = s3_client.list_objects_v2(**kwargs)
        for obj in response.get("Contents", []):
            ext = os.path.splitext(obj["Key"])[1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            last_modified = obj["LastModified"]
            if last_modified.tzinfo is None:
                last_modified = last_modified.replace(tzinfo=timezone.utc)
            if last_modified > since:
                changed += 1

        if not response.get("IsTruncated"):
            break
        continuation_token = response.get("NextContinuationToken")

    return changed


def _publish(topic_arn: str, subject: str, payload: dict[str, Any]) -> None:
    if not topic_arn:
        return
    try:
        sns_client.publish(
            TopicArn=topic_arn,
            Subject=subject[:100],
            Message=json.dumps(payload, ensure_ascii=False, default=str),
        )
    except Exception as e:  # noqa: BLE001 - 通知失敗は処理を止めない
        logger.warning("SNS publish failed: %s", str(e))


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Auto-Sync ハンドラー。"""
    logger.info("Self-service KB auto-sync started")

    s3ap_alias = os.environ.get("S3_ACCESS_POINT_ALIAS", "")
    kb_id = os.environ.get("KNOWLEDGE_BASE_ID", "")
    ds_id = os.environ.get("DATA_SOURCE_ID", "")
    prefix = os.environ.get("INGESTION_PREFIX", "")
    topic_arn = os.environ.get("NOTIFICATION_TOPIC_ARN", "")
    force = bool(event.get("force", False))

    now = int(datetime.now(timezone.utc).timestamp())

    if not (s3ap_alias and kb_id and ds_id):
        result = {
            "status": "error",
            "error": "S3_ACCESS_POINT_ALIAS / KNOWLEDGE_BASE_ID / DATA_SOURCE_ID is required",
            "timestamp": now,
        }
        logger.error(result["error"])
        return result

    try:
        # 多重起動防止: 進行中ジョブがあればスキップ
        active = _active_ingestion_job(kb_id, ds_id)
        if active:
            result = {
                "status": "ingestion_in_progress",
                "active_ingestion_job_id": active,
                "scanned_prefix": prefix,
                "timestamp": now,
            }
            logger.info("Active ingestion job %s exists; skipping new start", active)
            return result

        since = _epoch_floor() if force else _last_ingestion_time(kb_id, ds_id)
        changed = _count_changed_files(s3ap_alias, prefix, since)

        if changed == 0 and not force:
            result = {
                "status": "no_change",
                "changed_files_detected": 0,
                "scanned_prefix": prefix,
                "timestamp": now,
            }
            logger.info("No changed files detected; skipping ingestion")
            return result

        job = bedrock_agent.start_ingestion_job(
            knowledgeBaseId=kb_id,
            dataSourceId=ds_id,
            description=f"self-service auto-sync ({changed} changed files)",
        )
        job_id = job["ingestionJob"]["ingestionJobId"]

        result = {
            "status": "ingestion_started",
            "changed_files_detected": changed,
            "forced": force,
            "knowledge_base_id": kb_id,
            "data_source_id": ds_id,
            "ingestion_job_id": job_id,
            "scanned_prefix": prefix,
            "timestamp": now,
        }
        logger.info("Ingestion started: job=%s changed=%d", job_id, changed)
        _publish(topic_arn, "[UC29] KB auto-sync started", result)
        return result

    except Exception as e:  # noqa: BLE001 - 失敗は通知して可視化
        result = {"status": "error", "error": str(e), "timestamp": now}
        logger.error("Auto-sync failed: %s", str(e))
        _publish(topic_arn, "[UC29] KB auto-sync FAILED", result)
        return result
