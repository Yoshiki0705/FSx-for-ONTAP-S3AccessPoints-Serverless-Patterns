"""FPolicy Engine — ONTAP FPolicy イベント受信 + SQS 転送.

ONTAP FPolicy の外部サーバーとして動作し、ファイル操作イベントを
SQS Ingestion Queue に転送する。

Environment Variables:
    SQS_QUEUE_URL: Ingestion Queue の URL
    DLQ_URL: Dead Letter Queue の URL（バリデーション失敗時）
    MAX_RETRIES: SQS 送信リトライ回数 (default: 3)
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import boto3
import jsonschema

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Lazy-loaded schema
_schema: dict | None = None

SCHEMA_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fpolicy-event-schema.json",
)

# Fallback: try shared/schemas/ path for local development/testing
_SCHEMA_PATH_FALLBACK = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "schemas",
    "fpolicy-event-schema.json",
)


class SchemaValidationError(Exception):
    """FPolicy イベントの JSON Schema バリデーション失敗."""

    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.errors = errors or []


class SqsIngestionError(Exception):
    """SQS 送信の全リトライ失敗."""

    def __init__(self, message: str, last_error: Exception | None = None):
        super().__init__(message)
        self.last_error = last_error


def _load_schema() -> dict:
    """JSON Schema をファイルから読み込む（キャッシュ付き）."""
    global _schema
    if _schema is None:
        schema_path = os.environ.get("SCHEMA_PATH", SCHEMA_PATH)
        # Try primary path first, then fallback for local dev/testing
        if not os.path.exists(schema_path):
            schema_path = _SCHEMA_PATH_FALLBACK
        with open(schema_path) as f:
            _schema = json.load(f)
    return _schema


def validate_fpolicy_event(event: dict[str, Any], schema: dict | None = None) -> bool:
    """FPolicy イベントを JSON Schema に対してバリデーションする.

    Args:
        event: バリデーション対象のイベント
        schema: JSON Schema 定義（None の場合はデフォルトスキーマを使用）

    Returns:
        bool: バリデーション成功時 True

    Raises:
        SchemaValidationError: バリデーション失敗時
    """
    if schema is None:
        schema = _load_schema()

    validator = jsonschema.Draft7Validator(schema)
    errors = list(validator.iter_errors(event))

    if errors:
        error_messages = [f"{e.json_path}: {e.message}" for e in errors]
        raise SchemaValidationError(
            f"FPolicy event validation failed with {len(errors)} error(s)",
            errors=error_messages,
        )

    return True


def send_to_sqs_with_retry(
    queue_url: str,
    message_body: str,
    max_retries: int = 3,
    base_delay: float = 1.0,
    sqs_client: Any | None = None,
) -> str:
    """エクスポネンシャルバックオフリトライ付き SQS 送信.

    Args:
        queue_url: SQS キュー URL
        message_body: メッセージ本文（JSON 文字列）
        max_retries: 最大リトライ回数
        base_delay: 初回リトライ待機秒数
        sqs_client: SQS クライアント（テスト用 DI）

    Returns:
        str: SQS MessageId

    Raises:
        SqsIngestionError: 全リトライ失敗時
    """
    if sqs_client is None:
        sqs_client = boto3.client("sqs")

    last_error: Exception | None = None

    for attempt in range(max_retries):
        try:
            response = sqs_client.send_message(
                QueueUrl=queue_url,
                MessageBody=message_body,
            )
            return response["MessageId"]
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                delay = base_delay * (2**attempt)
                logger.warning(
                    "SQS send failed (attempt %d/%d), retrying in %.1fs: %s",
                    attempt + 1,
                    max_retries,
                    delay,
                    str(e),
                )
                time.sleep(delay)

    raise SqsIngestionError(
        f"All {max_retries} SQS send attempts failed",
        last_error=last_error,
    )


def _emit_metric(metric_name: str, value: float = 1.0) -> None:
    """CloudWatch メトリクスを出力する."""
    try:
        cw_client = boto3.client("cloudwatch")
        cw_client.put_metric_data(
            Namespace="FSxN-S3AP-Patterns",
            MetricData=[
                {
                    "MetricName": metric_name,
                    "Value": value,
                    "Unit": "Count",
                }
            ],
        )
    except Exception as e:
        logger.error("Failed to emit metric %s: %s", metric_name, str(e))


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """FPolicy イベントを受信し、バリデーション後に SQS に送信する.

    Args:
        event: FPolicy イベント（ONTAP から HTTP POST で受信）
        context: Lambda コンテキスト

    Returns:
        dict: 処理結果 (status, event_id, queue_message_id)
    """
    queue_url = os.environ["SQS_QUEUE_URL"]
    dlq_url = os.environ.get("DLQ_URL", "")
    max_retries = int(os.environ.get("MAX_RETRIES", "3"))

    # Handle batch events (multiple FPolicy events in one invocation)
    events = event.get("events", [event]) if "events" in event else [event]
    results = []

    for fpolicy_event in events:
        event_id = fpolicy_event.get("event_id", "unknown")

        try:
            # Step 1: Validate against JSON Schema
            validate_fpolicy_event(fpolicy_event)
            logger.info("Event %s validated successfully", event_id)

            # Step 2: Send to SQS with retry
            message_body = json.dumps(fpolicy_event, ensure_ascii=False)
            message_id = send_to_sqs_with_retry(
                queue_url=queue_url,
                message_body=message_body,
                max_retries=max_retries,
            )

            logger.info(
                "Event %s sent to SQS (MessageId: %s)", event_id, message_id
            )
            results.append(
                {
                    "status": "success",
                    "event_id": event_id,
                    "queue_message_id": message_id,
                }
            )

        except SchemaValidationError as e:
            logger.error(
                "Schema validation failed for event %s: %s", event_id, str(e)
            )
            _emit_metric("SchemaValidationFailures")

            # Send to DLQ if available
            if dlq_url:
                try:
                    sqs_client = boto3.client("sqs")
                    sqs_client.send_message(
                        QueueUrl=dlq_url,
                        MessageBody=json.dumps(
                            {
                                "original_event": fpolicy_event,
                                "error": str(e),
                                "validation_errors": e.errors,
                            },
                            ensure_ascii=False,
                        ),
                    )
                except Exception as dlq_err:
                    logger.error("Failed to send to DLQ: %s", str(dlq_err))

            results.append(
                {
                    "status": "validation_failed",
                    "event_id": event_id,
                    "error": str(e),
                }
            )

        except SqsIngestionError as e:
            logger.error(
                "SQS ingestion failed for event %s: %s", event_id, str(e)
            )
            _emit_metric("FPolicyIngestionFailures")
            results.append(
                {
                    "status": "ingestion_failed",
                    "event_id": event_id,
                    "error": str(e),
                }
            )

    return {
        "statusCode": 200,
        "body": {"processed": len(results), "results": results},
    }
