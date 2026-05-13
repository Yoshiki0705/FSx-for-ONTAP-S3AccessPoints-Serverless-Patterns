"""SQS → EventBridge Bridge — SQS メッセージをカスタムイベントバスに転送.

SQS Ingestion Queue をイベントソースとして起動され、
FPolicy イベントを EventBridge カスタムバスに PutEvents する。

Environment Variables:
    EVENT_BUS_NAME: EventBridge カスタムイベントバス名
    DETAIL_TYPE: イベント detail-type (default: "FPolicy File Operation")
    SOURCE: イベントソース名 (default: "fsxn.fpolicy")
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """SQS バッチイベントを EventBridge に転送する.

    Args:
        event: SQS バッチイベント (Records[])
        context: Lambda コンテキスト

    Returns:
        dict: batchItemFailures (部分失敗対応)
    """
    event_bus_name = os.environ["EVENT_BUS_NAME"]
    detail_type = os.environ.get("DETAIL_TYPE", "FPolicy File Operation")
    source = os.environ.get("SOURCE", "fsxn.fpolicy")

    eb_client = boto3.client("events")
    cw_client = boto3.client("cloudwatch")

    records = event.get("Records", [])
    batch_item_failures: list[dict[str, str]] = []

    # Process records in batches of 10 (EventBridge PutEvents limit)
    entries: list[dict[str, Any]] = []
    record_map: dict[int, str] = {}  # entry index → messageId

    for record in records:
        message_id = record["messageId"]
        start_time = time.time()

        try:
            body = json.loads(record["body"])

            entry = {
                "Source": source,
                "DetailType": detail_type,
                "Detail": json.dumps(body, ensure_ascii=False),
                "EventBusName": event_bus_name,
            }

            record_map[len(entries)] = message_id
            entries.append(entry)

            # Emit latency metric
            latency_ms = (time.time() - start_time) * 1000
            _emit_latency_metric(cw_client, latency_ms)

        except (json.JSONDecodeError, KeyError) as e:
            logger.error(
                "Failed to parse SQS message %s: %s", message_id, str(e)
            )
            batch_item_failures.append({"itemIdentifier": message_id})

    # Send entries in batches of 10
    if entries:
        for batch_start in range(0, len(entries), 10):
            batch = entries[batch_start : batch_start + 10]
            try:
                response = eb_client.put_events(Entries=batch)

                # Check for individual entry failures
                for i, result_entry in enumerate(
                    response.get("Entries", [])
                ):
                    if "ErrorCode" in result_entry:
                        entry_idx = batch_start + i
                        failed_message_id = record_map.get(entry_idx)
                        if failed_message_id:
                            logger.error(
                                "EventBridge PutEvents failed for message %s: %s - %s",
                                failed_message_id,
                                result_entry.get("ErrorCode"),
                                result_entry.get("ErrorMessage"),
                            )
                            batch_item_failures.append(
                                {"itemIdentifier": failed_message_id}
                            )

            except Exception as e:
                logger.error(
                    "EventBridge PutEvents batch failed: %s", str(e)
                )
                # Mark all entries in this batch as failed
                for i in range(len(batch)):
                    entry_idx = batch_start + i
                    failed_message_id = record_map.get(entry_idx)
                    if failed_message_id:
                        batch_item_failures.append(
                            {"itemIdentifier": failed_message_id}
                        )

    logger.info(
        "Processed %d records, %d failures",
        len(records),
        len(batch_item_failures),
    )

    return {"batchItemFailures": batch_item_failures}


def _emit_latency_metric(cw_client: Any, latency_ms: float) -> None:
    """EventBridge ルーティングレイテンシメトリクスを出力する."""
    try:
        cw_client.put_metric_data(
            Namespace="FSxN-S3AP-Patterns",
            MetricData=[
                {
                    "MetricName": "EventBridgeRoutingLatency",
                    "Value": latency_ms,
                    "Unit": "Milliseconds",
                }
            ],
        )
    except Exception as e:
        logger.warning("Failed to emit latency metric: %s", str(e))
