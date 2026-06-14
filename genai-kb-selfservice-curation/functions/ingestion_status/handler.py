"""UC29 Self-Service KB Curation — Ingestion Status Lambda

Step Functions の自動化ワークフローから呼び出され、Bedrock Knowledge Base の
Ingestion ジョブの状態をポーリングして返す。完了/失敗の判定に利用する。
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

bedrock_agent = boto3.client("bedrock-agent")


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Ingestion ジョブの状態を返す。

    event 例:
      {"knowledge_base_id": "...", "data_source_id": "...", "ingestion_job_id": "..."}
    戻り値の ingestion_status は STARTING / IN_PROGRESS / COMPLETE / FAILED など。
    """
    kb_id = event.get("knowledge_base_id") or os.environ.get("KNOWLEDGE_BASE_ID", "")
    ds_id = event.get("data_source_id") or os.environ.get("DATA_SOURCE_ID", "")
    job_id = event.get("ingestion_job_id", "")
    now = int(datetime.now(timezone.utc).timestamp())

    if not (kb_id and ds_id and job_id):
        return {
            "status": "error",
            "error": "knowledge_base_id / data_source_id / ingestion_job_id are required",
            "ingestion_status": "UNKNOWN",
            "timestamp": now,
        }

    try:
        resp = bedrock_agent.get_ingestion_job(
            knowledgeBaseId=kb_id,
            dataSourceId=ds_id,
            ingestionJobId=job_id,
        )
        job = resp["ingestionJob"]
        ingestion_status = job["status"]
        stats = job.get("statistics", {})

        result = {
            "status": "completed",
            "ingestion_status": ingestion_status,
            "knowledge_base_id": kb_id,
            "data_source_id": ds_id,
            "ingestion_job_id": job_id,
            "documents_scanned": stats.get("numberOfDocumentsScanned"),
            "documents_indexed": stats.get("numberOfNewDocumentsIndexed"),
            "documents_failed": stats.get("numberOfDocumentsFailed"),
            "timestamp": now,
        }
        logger.info("Ingestion job %s status=%s", job_id, ingestion_status)
        return result

    except Exception as e:  # noqa: BLE001 - 状態取得失敗を可視化
        logger.error("get_ingestion_job failed: %s", str(e))
        return {
            "status": "error",
            "error": str(e),
            "ingestion_status": "UNKNOWN",
            "ingestion_job_id": job_id,
            "timestamp": now,
        }
