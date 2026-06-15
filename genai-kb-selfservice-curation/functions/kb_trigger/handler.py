"""UC29 Scenario C — FPolicy イベント駆動 KB 同期トリガー.

FPolicy ファイル操作イベント（EventBridge カスタムバス経由）を受信し、
Bedrock Knowledge Base の Ingestion をリアルタイムで起動する。

シナリオ B（EventBridge Scheduler の定期ポーリング）と異なり、
ファイルが SMB/NFS で配置された瞬間に同期を開始する。

デバウンス: 進行中の Ingestion ジョブがある場合は新規起動をスキップする
（Bedrock KB はデータソースあたり同時に 1 ジョブのみ。実行中ジョブが
完了後の残りファイルは次イベントまたは定期同期で取り込まれる）。

Environment Variables:
    KNOWLEDGE_BASE_ID: 対象 Bedrock Knowledge Base ID
    DATA_SOURCE_ID: S3 AP データソース ID
    FPOLICY_PATH_FILTER: FPolicy ファイルパスに対する任意の二次フィルタ
        （ONTAP ボリュームパス名前空間。例 "ai_knowledge/"、空でフィルタなし）。
        一次フィルタは EventBridge ルールで行う。
    NOTIFICATION_TOPIC_ARN: 同期結果通知 SNS Topic ARN（任意）
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

bedrock_agent = boto3.client("bedrock-agent")
sns_client = boto3.client("sns")
cloudwatch = boto3.client("cloudwatch")

# 進行中とみなす Ingestion ジョブステータス
_ACTIVE_STATUSES = ("STARTING", "IN_PROGRESS")


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """FPolicy イベントを受けて KB Ingestion をトリガーする.

    Args:
        event: EventBridge イベント（detail に FPolicy イベント本体）
        context: Lambda コンテキスト

    Returns:
        dict: トリガー結果（status, ingestion_job_id 等）
    """
    kb_id = os.environ.get("KNOWLEDGE_BASE_ID", "")
    ds_id = os.environ.get("DATA_SOURCE_ID", "")
    # FPolicy のファイルパス（ONTAP ボリュームパス名前空間）に対する任意の二次フィルタ。
    # 一次フィルタは EventBridge ルール側で行う。空ならフィルタなし。
    # 注意: これは KB の S3 取り込みプレフィックス（INGESTION_PREFIX）とは別名前空間
    # （FPolicy は /<volume>/... を報告、S3 AP は別プレフィックス）。
    path_filter = os.environ.get("FPOLICY_PATH_FILTER", "")
    topic_arn = os.environ.get("NOTIFICATION_TOPIC_ARN", "")

    if not kb_id or not ds_id:
        logger.error("KNOWLEDGE_BASE_ID / DATA_SOURCE_ID is not configured")
        return {"status": "error", "reason": "missing_configuration"}

    detail = event.get("detail", {})
    operation = detail.get("operation_type", "unknown")
    file_path = detail.get("file_path", "")

    # 二次パスフィルタ（FPolicy ボリュームパス名前空間。EventBridge ルールが一次フィルタ）
    if path_filter and path_filter not in file_path:
        logger.info(
            "Skip: file_path '%s' does not match path filter '%s'", file_path, path_filter
        )
        return {"status": "skipped", "reason": "path_filter_mismatch", "file_path": file_path}

    correlation_id = detail.get("event_id", context.aws_request_id if context else "n/a")
    logger.info(
        json.dumps(
            {
                "event": "kb_trigger_received",
                "correlation_id": correlation_id,
                "operation": operation,
                "file_path": file_path,
            }
        )
    )

    # デバウンス: 進行中ジョブがあればスキップ
    active_job_id = _find_active_ingestion_job(kb_id, ds_id)
    if active_job_id:
        logger.info("Ingestion already in progress (job=%s), skipping", active_job_id)
        _emit_metric("KbTriggerSkipped", 1)
        return {
            "status": "ingestion_in_progress",
            "active_ingestion_job_id": active_job_id,
            "correlation_id": correlation_id,
        }

    # Ingestion 起動
    try:
        resp = bedrock_agent.start_ingestion_job(
            knowledgeBaseId=kb_id,
            dataSourceId=ds_id,
            description=f"Scenario C trigger: {operation} {file_path}"[:200],
        )
        job_id = resp["ingestionJob"]["ingestionJobId"]
    except Exception as e:  # noqa: BLE001
        logger.error("StartIngestionJob failed: %s", str(e))
        _emit_metric("KbTriggerError", 1)
        return {"status": "error", "reason": str(e), "correlation_id": correlation_id}

    logger.info("Ingestion started (job=%s) via FPolicy event", job_id)
    _emit_metric("KbTriggerStarted", 1)

    if topic_arn:
        _notify(
            topic_arn,
            subject="[UC29 Scenario C] KB ingestion triggered",
            message={
                "status": "ingestion_started",
                "trigger": "fpolicy_event",
                "operation": operation,
                "file_path": file_path,
                "ingestion_job_id": job_id,
                "correlation_id": correlation_id,
            },
        )

    return {
        "status": "ingestion_started",
        "trigger": "fpolicy_event",
        "operation": operation,
        "file_path": file_path,
        "knowledge_base_id": kb_id,
        "data_source_id": ds_id,
        "ingestion_job_id": job_id,
        "correlation_id": correlation_id,
    }


def _find_active_ingestion_job(kb_id: str, ds_id: str) -> str | None:
    """進行中（STARTING / IN_PROGRESS）の Ingestion ジョブ ID を返す（なければ None）."""
    try:
        resp = bedrock_agent.list_ingestion_jobs(
            knowledgeBaseId=kb_id,
            dataSourceId=ds_id,
            filters=[{"attribute": "STATUS", "operator": "EQ", "values": list(_ACTIVE_STATUSES)}],
            maxResults=5,
        )
        summaries = resp.get("ingestionJobSummaries", [])
        if summaries:
            return summaries[0].get("ingestionJobId")
    except Exception as e:  # noqa: BLE001
        # filters 非対応や一時エラー時は安全側で「進行中なし」とせず、フォールバック取得
        logger.warning("list_ingestion_jobs with filter failed: %s; falling back", str(e))
        try:
            resp = bedrock_agent.list_ingestion_jobs(
                knowledgeBaseId=kb_id, dataSourceId=ds_id, maxResults=10
            )
            for s in resp.get("ingestionJobSummaries", []):
                if s.get("status") in _ACTIVE_STATUSES:
                    return s.get("ingestionJobId")
        except Exception as e2:  # noqa: BLE001
            logger.warning("Fallback list_ingestion_jobs failed: %s", str(e2))
    return None


def _emit_metric(name: str, value: float) -> None:
    """CloudWatch カスタムメトリクスを出力する."""
    try:
        cloudwatch.put_metric_data(
            Namespace="FSxN-S3AP-Patterns",
            MetricData=[{"MetricName": name, "Value": value, "Unit": "Count"}],
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to emit metric %s: %s", name, str(e))


def _notify(topic_arn: str, subject: str, message: dict[str, Any]) -> None:
    """SNS 通知を送信する."""
    try:
        sns_client.publish(
            TopicArn=topic_arn,
            Subject=subject[:100],
            Message=json.dumps(message, ensure_ascii=False),
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("SNS publish failed: %s", str(e))
