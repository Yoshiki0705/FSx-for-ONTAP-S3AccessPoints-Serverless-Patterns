"""shared.lambdas.lineage_export.handler — Lineage DynamoDB → S3 Export

DynamoDB の LineageRecord を S3 に日次エクスポートする Lambda ハンドラー。
Object Lock (Compliance mode) で 7 年間の不変保存を実現する。

動作:
1. DynamoDB Scan で前日のレコードを取得
2. JSON Lines 形式でフォーマット
3. S3 に日付パーティションキーで書き込み
4. CloudWatch メトリクス LineageExportRecordCount を発行

リトライ:
- DynamoDB Scan / S3 PutObject 失敗時は最大 3 回リトライ（指数バックオフ）
- 3 回失敗後は CloudWatch Alarm で通知

出力キー形式:
  s3://{bucket}/lineage/year={YYYY}/month={MM}/day={DD}/export-{timestamp}.jsonl
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")
cloudwatch = boto3.client("cloudwatch")

MAX_RETRIES = 3
BACKOFF_BASE = 2.0


class DecimalEncoder(json.JSONEncoder):
    """DynamoDB Decimal 型を JSON シリアライズ可能にする。"""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            if obj % 1 == 0:
                return int(obj)
            return float(obj)
        return super().default(obj)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lineage レコードを S3 にエクスポートする。

    Args:
        event: Lambda イベント（EventBridge Schedule から呼び出し）
        context: Lambda コンテキスト

    Returns:
        エクスポート結果
    """
    table_name = os.environ.get("LINEAGE_TABLE_NAME", "fsxn-s3ap-data-lineage")
    bucket_name = os.environ.get("RETENTION_BUCKET", "")
    metric_namespace = os.environ.get("METRIC_NAMESPACE", "FSxN-S3AP-Patterns")

    if not bucket_name:
        raise ValueError("RETENTION_BUCKET environment variable is required")

    # 前日の日付範囲を計算
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)
    date_prefix = yesterday.strftime("%Y-%m-%d")
    year = yesterday.strftime("%Y")
    month = yesterday.strftime("%m")
    day = yesterday.strftime("%d")

    logger.info("Exporting lineage records for date: %s", date_prefix)

    # DynamoDB Scan（前日のレコードをフィルタ）
    records = _scan_records_with_retry(table_name, date_prefix)

    if not records:
        logger.info("No records found for %s", date_prefix)
        _publish_metric(metric_namespace, 0)
        return {"record_count": 0, "date": date_prefix, "status": "empty"}

    # JSON Lines 形式でフォーマット
    jsonl_content = "\n".join(
        json.dumps(record, cls=DecimalEncoder, ensure_ascii=False)
        for record in records
    )

    # S3 に書き込み
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    s3_key = f"lineage/year={year}/month={month}/day={day}/export-{timestamp}.jsonl"

    _put_object_with_retry(bucket_name, s3_key, jsonl_content)

    # メトリクス発行
    _publish_metric(metric_namespace, len(records))

    logger.info(
        "Export complete: %d records → s3://%s/%s",
        len(records),
        bucket_name,
        s3_key,
    )

    return {
        "record_count": len(records),
        "date": date_prefix,
        "s3_key": s3_key,
        "status": "success",
    }


def _scan_records_with_retry(table_name: str, date_prefix: str) -> list[dict]:
    """DynamoDB Scan をリトライ付きで実行する。"""
    table = dynamodb.Table(table_name)

    for attempt in range(MAX_RETRIES):
        try:
            items: list[dict] = []
            scan_kwargs: dict[str, Any] = {
                "FilterExpression": boto3.dynamodb.conditions.Attr(
                    "processing_timestamp"
                ).begins_with(date_prefix),
            }

            while True:
                response = table.scan(**scan_kwargs)
                items.extend(response.get("Items", []))

                last_key = response.get("LastEvaluatedKey")
                if not last_key:
                    break
                scan_kwargs["ExclusiveStartKey"] = last_key

            return items

        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                wait = BACKOFF_BASE ** attempt
                logger.warning(
                    "DynamoDB scan failed (attempt %d/%d): %s. Retrying in %.1fs",
                    attempt + 1,
                    MAX_RETRIES,
                    e,
                    wait,
                )
                time.sleep(wait)
            else:
                logger.error("DynamoDB scan failed after %d attempts: %s", MAX_RETRIES, e)
                raise


def _put_object_with_retry(bucket: str, key: str, content: str) -> None:
    """S3 PutObject をリトライ付きで実行する。"""
    for attempt in range(MAX_RETRIES):
        try:
            s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=content.encode("utf-8"),
                ContentType="application/x-ndjson",
            )
            return

        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                wait = BACKOFF_BASE ** attempt
                logger.warning(
                    "S3 PutObject failed (attempt %d/%d): %s. Retrying in %.1fs",
                    attempt + 1,
                    MAX_RETRIES,
                    e,
                    wait,
                )
                time.sleep(wait)
            else:
                logger.error("S3 PutObject failed after %d attempts: %s", MAX_RETRIES, e)
                raise


def _publish_metric(namespace: str, record_count: int) -> None:
    """CloudWatch メトリクスを発行する。"""
    try:
        cloudwatch.put_metric_data(
            Namespace=namespace,
            MetricData=[
                {
                    "MetricName": "LineageExportRecordCount",
                    "Value": float(record_count),
                    "Unit": "Count",
                }
            ],
        )
    except Exception as e:
        logger.warning("Failed to publish metric: %s", e)
