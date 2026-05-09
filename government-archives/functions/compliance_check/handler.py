"""UC16 Government Archives Compliance Check Lambda

NARA GRS (General Records Schedule) に基づき保存期間と廃棄スケジュールを
DynamoDB に記録する。

Environment Variables:
    RETENTION_TABLE: DynamoDB Retention Schedule テーブル名
    DEFAULT_RETENTION_YEARS: デフォルト保存年数 (default: 7)
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)


# NARA GRS 保存期間マッピング（簡略化）
GRS_RETENTION_MAP = {
    "public": {"grs_code": "GRS 2.1", "retention_years": 3},
    "sensitive": {"grs_code": "GRS 2.2", "retention_years": 7},
    "confidential": {"grs_code": "GRS 1.1", "retention_years": 30},
}


def compute_disposal_date(
    creation_date: str, retention_years: int
) -> str:
    """廃棄予定日を計算する（ISO 8601 形式）。"""
    try:
        created = datetime.fromisoformat(creation_date.replace("Z", ""))
    except ValueError:
        created = datetime.utcnow()
    disposal = created + timedelta(days=365 * retention_years)
    return disposal.isoformat()


def get_retention_schedule(clearance_level: str) -> dict[str, Any]:
    """機密レベルから保存スケジュールを取得する。"""
    default = {"grs_code": "GRS 2.1", "retention_years": 7}
    return GRS_RETENTION_MAP.get(clearance_level, default)


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """UC16 Compliance Check Lambda ハンドラ。

    Input:
        {
            "document_key": "...",
            "clearance_level": "...",
            "creation_date": "2026-05-10T..."
        }

    Output:
        {
            "document_key": str,
            "grs_code": str,
            "retention_years": int,
            "disposal_date": str
        }
    """
    table_name = os.environ.get("RETENTION_TABLE", "")
    default_years = int(os.environ.get("DEFAULT_RETENTION_YEARS", "7"))

    document_key = event.get("document_key", "")
    clearance_level = event.get("clearance_level", "public")
    creation_date = event.get("creation_date", datetime.utcnow().isoformat())

    schedule = get_retention_schedule(clearance_level)
    retention_years = schedule.get("retention_years", default_years)
    grs_code = schedule.get("grs_code", "GRS 2.1")
    disposal_date = compute_disposal_date(creation_date, retention_years)

    # DynamoDB に保存
    if table_name:
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table(table_name)
        # 廃棄予定日 + 90日を TTL に（自動削除通知用）
        ttl = int(time.time()) + int(
            (datetime.fromisoformat(disposal_date) - datetime.utcnow()).total_seconds()
        ) + 90 * 24 * 3600

        table.put_item(Item={
            "document_key": document_key,
            "clearance_level": clearance_level,
            "grs_code": grs_code,
            "retention_years": retention_years,
            "creation_date": creation_date,
            "disposal_date": disposal_date,
            "ttl": ttl,
        })

    logger.info(
        "UC16 ComplianceCheck: document=%s, grs=%s, retention=%dy, disposal=%s",
        document_key,
        grs_code,
        retention_years,
        disposal_date,
    )

    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="compliance_check")
    metrics.set_dimension("UseCase", "government-archives")
    metrics.set_dimension("GrsCode", grs_code)
    metrics.put_metric("DocumentsScheduled", 1.0, "Count")
    metrics.flush()

    return {
        "document_key": document_key,
        "clearance_level": clearance_level,
        "grs_code": grs_code,
        "retention_years": retention_years,
        "creation_date": creation_date,
        "disposal_date": disposal_date,
    }
