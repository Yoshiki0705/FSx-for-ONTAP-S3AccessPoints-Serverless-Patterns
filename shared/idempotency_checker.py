"""Idempotency Checker — HYBRID モード重複排除ヘルパー.

Step Functions の最初のステップで呼び出し、
同一ファイル操作の重複実行を防止する。

Usage in Step Functions:
    {
      "StartAt": "IdempotencyCheck",
      "States": {
        "IdempotencyCheck": {
          "Type": "Task",
          "Resource": "${IdempotencyCheckerFunction.Arn}",
          "ResultPath": "$.idempotency",
          "Next": "CheckDuplicate"
        },
        "CheckDuplicate": {
          "Type": "Choice",
          "Choices": [
            {
              "Variable": "$.idempotency.is_duplicate",
              "BooleanEquals": true,
              "Next": "SkipDuplicate"
            }
          ],
          "Default": "ProcessEvent"
        },
        "SkipDuplicate": {
          "Type": "Succeed",
          "Comment": "Duplicate event — skip processing"
        },
        "ProcessEvent": { ... }
      }
    }

Environment Variables:
    IDEMPOTENCY_TABLE: DynamoDB テーブル名
    DEDUP_WINDOW_MINUTES: 重複判定ウィンドウ（分、デフォルト: 5）
    USE_CASE: UC 名（パーティションキーのプレフィックス）
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

IDEMPOTENCY_TABLE = os.environ.get("IDEMPOTENCY_TABLE", "fsxn-s3ap-idempotency-store")
DEDUP_WINDOW_MINUTES = int(os.environ.get("DEDUP_WINDOW_MINUTES", "5"))
USE_CASE = os.environ.get("USE_CASE", "unknown")
TTL_DAYS = int(os.environ.get("TTL_DAYS", "7"))


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Idempotency check handler.

    Input event (from Step Functions):
        {
            "file_path": "/vol1/legal/contract.pdf",
            "operation_type": "create",
            "timestamp": "2026-05-14T10:30:00Z",
            ...
        }

    Returns:
        {
            "is_duplicate": true/false,
            "idempotency_key": "legal-compliance#/vol1/legal/contract.pdf",
            "sort_key": "create#2026-05-14T10:30"
        }
    """
    file_path = event.get("file_path", "")
    operation_type = event.get("operation_type", "create")
    timestamp = event.get("timestamp", "")

    if not file_path:
        logger.warning("No file_path in event, skipping idempotency check")
        return {"is_duplicate": False, "idempotency_key": "", "sort_key": ""}

    # Build keys
    pk = f"{USE_CASE}#{file_path}"
    # Bucket timestamp to DEDUP_WINDOW_MINUTES granularity
    ts_bucket = _bucket_timestamp(timestamp, DEDUP_WINDOW_MINUTES)
    sk = f"{operation_type}#{ts_bucket}"

    # Check if already processed
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(IDEMPOTENCY_TABLE)

    try:
        response = table.get_item(Key={"pk": pk, "sk": sk})
        if "Item" in response:
            logger.info(
                "[Idempotency] DUPLICATE: pk=%s sk=%s (processed at %s)",
                pk, sk, response["Item"].get("processed_at", "unknown"),
            )
            return {
                "is_duplicate": True,
                "idempotency_key": pk,
                "sort_key": sk,
            }
    except Exception as e:
        logger.warning("[Idempotency] GetItem failed: %s (proceeding as non-duplicate)", e)

    # Not a duplicate — record this event
    ttl = int(time.time()) + (TTL_DAYS * 86400)
    try:
        table.put_item(
            Item={
                "pk": pk,
                "sk": sk,
                "processed_at": timestamp or str(int(time.time())),
                "operation_type": operation_type,
                "ttl": ttl,
            },
            ConditionExpression="attribute_not_exists(pk)",
        )
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        # Race condition: another execution already recorded this
        logger.info("[Idempotency] RACE DUPLICATE: pk=%s sk=%s", pk, sk)
        return {
            "is_duplicate": True,
            "idempotency_key": pk,
            "sort_key": sk,
        }
    except Exception as e:
        logger.warning("[Idempotency] PutItem failed: %s (proceeding as non-duplicate)", e)

    logger.info("[Idempotency] NEW: pk=%s sk=%s", pk, sk)
    return {
        "is_duplicate": False,
        "idempotency_key": pk,
        "sort_key": sk,
    }


def _bucket_timestamp(timestamp: str, window_minutes: int) -> str:
    """Bucket a timestamp to the nearest window.

    Example: "2026-05-14T10:33:45Z" with 5-min window → "2026-05-14T10:30"
    """
    if not timestamp:
        # Use current time
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)
        minute_bucket = (now.minute // window_minutes) * window_minutes
        return now.strftime(f"%Y-%m-%dT%H:{minute_bucket:02d}")

    # Parse ISO timestamp and bucket
    try:
        # Handle various ISO formats
        ts = timestamp.replace("Z", "+00:00")
        if "T" in ts:
            date_part, time_part = ts.split("T")
            time_components = time_part.split(":")
            hour = int(time_components[0])
            minute = int(time_components[1]) if len(time_components) > 1 else 0
            minute_bucket = (minute // window_minutes) * window_minutes
            return f"{date_part}T{hour:02d}:{minute_bucket:02d}"
    except (ValueError, IndexError):
        pass

    return timestamp[:16]  # Fallback: truncate to minute
