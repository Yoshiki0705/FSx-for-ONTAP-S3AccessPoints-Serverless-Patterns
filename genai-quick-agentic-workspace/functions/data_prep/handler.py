"""UC30 Amazon Quick Agentic Workspace — Data Prep / Manifest

FSx ONTAP S3 Access Point 上の Quick ワークスペース領域（index / analytics / flows）を
走査し、Amazon Quick のデータソース準備状況をマニフェスト化する。

ボリューム構成（S3 AP プレフィックス）:
  quick-workspace/index/<role>/...      … Quick Index / Quick Research（非構造化）
  quick-workspace/analytics/<role>/...  … Quick Sight（構造化 CSV、Athena 経由）
  quick-workspace/flows/<role>/...      … Quick Flows（アクションサンプル）
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

s3_client = boto3.client("s3")

SERVICE_BUCKETS = {"index", "analytics", "flows"}


def _classify(key: str) -> tuple[str, str]:
    """key から (service_bucket, role) を推定する。"""
    parts = key.split("/")
    # 例: quick-workspace/index/sales/file.md
    if len(parts) >= 4 and parts[0] == "quick-workspace" and parts[1] in SERVICE_BUCKETS:
        return parts[1], parts[2]
    if len(parts) >= 3 and parts[0] in SERVICE_BUCKETS:
        return parts[0], parts[1]
    return "other", "unknown"


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """データソース準備状況のマニフェストを返す。"""
    s3ap_alias = os.environ.get("S3_ACCESS_POINT_ALIAS", "")
    workspace_prefix = os.environ.get("WORKSPACE_PREFIX", "quick-workspace/")
    requested_prefix = event.get("prefix", workspace_prefix)
    now = int(datetime.now(timezone.utc).timestamp())

    if not s3ap_alias:
        return {"status": "error", "error": "S3_ACCESS_POINT_ALIAS is required", "timestamp": now}

    # スコープ逸脱防止: 要求 prefix は設定済み WORKSPACE_PREFIX 配下に限定する
    if not requested_prefix.startswith(workspace_prefix):
        logger.warning(
            "Requested prefix '%s' escapes workspace '%s'; clamping", requested_prefix, workspace_prefix
        )
        prefix = workspace_prefix
    else:
        prefix = requested_prefix

    by_service: dict[str, int] = {"index": 0, "analytics": 0, "flows": 0, "other": 0}
    by_role: dict[str, int] = {}
    total = 0
    continuation_token = None

    try:
        while True:
            kwargs: dict[str, Any] = {"Bucket": s3ap_alias, "Prefix": prefix, "MaxKeys": 1000}
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token
            response = s3_client.list_objects_v2(**kwargs)

            for obj in response.get("Contents", []):
                key = obj["Key"]
                if key.endswith("/"):
                    continue
                service, role = _classify(key)
                by_service[service] = by_service.get(service, 0) + 1
                if service != "other":
                    by_role[role] = by_role.get(role, 0) + 1
                total += 1

            if not response.get("IsTruncated"):
                break
            continuation_token = response.get("NextContinuationToken")

    except Exception as e:  # noqa: BLE001 - 内部詳細は漏らさずサーバー側にのみ記録
        logger.error("data_prep failed: %s", str(e))
        return {"status": "error", "error": "internal error", "timestamp": now}

    logger.info("Data prep manifest: total=%d by_service=%s", total, by_service)
    return {
        "status": "completed",
        "total_objects": total,
        "by_service": by_service,
        "by_role": by_role,
        "scanned_prefix": prefix,
        "timestamp": now,
    }
