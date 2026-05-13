"""FPolicy Log Query Lambda — Batch モード用ログ取得 + SQS Push.

FPolicy サーバーが FSxN S3AP に書き込んだ JSON Lines ログファイルを
S3AP 経由で読み取り、条件に一致するイベントを SQS に Push する。

動作モード:
- EventBridge Scheduler からの定期実行（Batch モード）
- API Gateway 経由のオンデマンド実行（Request モード）

Environment Variables:
    S3_ACCESS_POINT: FSxN S3AP エイリアスまたは ARN
    SQS_QUEUE_URL: 送信先 SQS キュー URL
    LOG_PREFIX: ログファイルプレフィックス (default: "fpolicy_events/")
    MAX_RESULTS: 最大結果数 (default: 10000)

Reference:
    - Shengyu Fang: lambda_fpolicy_log_query.py
      https://github.com/YhunerFSY/ontap-fpolicy-aws-integration
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Configuration
S3_ACCESS_POINT = os.environ.get("S3_ACCESS_POINT", "")
SQS_QUEUE_URL = os.environ.get("SQS_QUEUE_URL", "")
LOG_PREFIX = os.environ.get("LOG_PREFIX", "fpolicy_events/")
MAX_RESULTS = int(os.environ.get("MAX_RESULTS", "10000"))


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """ログファイルを読み取り、フィルタリング後に SQS に送信する.

    Args:
        event: EventBridge Scheduler イベントまたは API Gateway リクエスト
        context: Lambda コンテキスト

    Returns:
        dict: 処理結果
    """
    logger.info("Received event: %s", json.dumps(event, default=str))

    try:
        # Parse parameters (from Scheduler or API Gateway)
        params = _parse_parameters(event)

        # Query logs from S3AP
        records = query_fpolicy_logs(
            s3_access_point=S3_ACCESS_POINT,
            start_time=params["start_time"],
            end_time=params["end_time"],
            path_filter=params.get("path_filter"),
            operations=params.get("operations"),
            limit=params.get("limit", MAX_RESULTS),
        )

        # Send to SQS
        sent_count = _send_to_sqs(records)

        response_body = {
            "status": "success",
            "records_found": len(records),
            "records_sent": sent_count,
            "filters": {
                "time_range": {
                    "start": params["start_time"].isoformat(),
                    "end": params["end_time"].isoformat(),
                },
                "path_filter": params.get("path_filter"),
                "operations": params.get("operations"),
            },
        }

        logger.info(
            "Processed: found=%d, sent=%d", len(records), sent_count
        )

        # API Gateway response format
        if "httpMethod" in event or "requestContext" in event:
            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": json.dumps(response_body),
            }

        return response_body

    except ValueError as e:
        logger.error("Validation error: %s", str(e))
        if "httpMethod" in event or "requestContext" in event:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"status": "error", "message": str(e)}),
            }
        return {"status": "error", "message": str(e)}

    except Exception as e:
        logger.error("Internal error: %s", str(e))
        if "httpMethod" in event or "requestContext" in event:
            return {
                "statusCode": 500,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"status": "error", "message": str(e)}),
            }
        return {"status": "error", "message": str(e)}


def query_fpolicy_logs(
    s3_access_point: str,
    start_time: datetime,
    end_time: datetime,
    path_filter: str | None = None,
    operations: list[str] | None = None,
    limit: int = 10000,
) -> list[dict]:
    """S3AP からログファイルを読み取り、条件フィルタリングする.

    Args:
        s3_access_point: FSxN S3AP エイリアスまたは ARN
        start_time: 検索開始時刻
        end_time: 検索終了時刻
        path_filter: パスプレフィックスフィルタ
        operations: 操作種別フィルタ
        limit: 最大結果数

    Returns:
        list: フィルタに一致するイベントレコード
    """
    s3_client = boto3.client("s3")

    # Get log files for the date range
    log_files = _get_log_files_for_range(s3_client, s3_access_point, start_time, end_time)
    logger.info("Found %d log files to scan", len(log_files))

    matching_records: list[dict] = []

    for log_file_key in log_files:
        if len(matching_records) >= limit:
            break

        records = _scan_log_file(
            s3_client,
            s3_access_point,
            log_file_key,
            start_time,
            end_time,
            path_filter,
            operations,
        )
        matching_records.extend(records)

    # Trim to limit
    return matching_records[:limit]


def convert_ontap_path_to_s3_key(
    ontap_path: str, volume_prefix: str = ""
) -> str:
    """ONTAP パスを S3 キーに変換する.

    Args:
        ontap_path: ONTAP ファイルパス (e.g., /vol1/subdir/file.txt)
        volume_prefix: 除去するボリュームプレフィックス

    Returns:
        str: S3 キー (e.g., subdir/file.txt)
    """
    path = ontap_path.replace("\\", "/")

    if volume_prefix and path.startswith(volume_prefix):
        path = path[len(volume_prefix):]
    else:
        # Remove first path component (volume name)
        parts = path.strip("/").split("/", 1)
        if len(parts) > 1:
            path = parts[1]
        else:
            path = parts[0] if parts else ""

    return path.lstrip("/")


# --- Private helpers ---


def _parse_parameters(event: dict) -> dict:
    """イベントからパラメータを解析する."""
    # API Gateway request
    if "body" in event:
        body = event["body"]
        if isinstance(body, str):
            body = json.loads(body)
        elif body is None:
            body = {}
    else:
        body = event

    # Default: last 1 hour
    now = datetime.utcnow()
    start_time_str = body.get("start_time")
    end_time_str = body.get("end_time")

    if start_time_str and end_time_str:
        start_time = datetime.fromisoformat(start_time_str)
        end_time = datetime.fromisoformat(end_time_str)
    else:
        # Default for scheduled execution: last 1 hour
        end_time = now
        start_time = now - timedelta(hours=1)

    if start_time >= end_time:
        raise ValueError("start_time must be before end_time")

    if (end_time - start_time).days > 7:
        raise ValueError("Time range cannot exceed 7 days")

    return {
        "start_time": start_time,
        "end_time": end_time,
        "path_filter": body.get("path_filter"),
        "operations": body.get("operations"),
        "limit": body.get("limit", MAX_RESULTS),
    }


def _get_log_files_for_range(
    s3_client: Any,
    s3_access_point: str,
    start_time: datetime,
    end_time: datetime,
) -> list[str]:
    """日付範囲に対応するログファイルキーを取得する."""
    log_files: list[str] = []
    current_date = start_time.date()
    end_date = end_time.date()

    # Generate expected log file names
    expected_files: list[str] = []
    while current_date <= end_date:
        filename = f"{LOG_PREFIX}fpolicy_events_{current_date.isoformat()}.jsonl"
        expected_files.append(filename)
        current_date += timedelta(days=1)

    # Verify files exist
    try:
        response = s3_client.list_objects_v2(
            Bucket=s3_access_point,
            Prefix=LOG_PREFIX,
        )
        if "Contents" in response:
            existing_keys = {obj["Key"] for obj in response["Contents"]}
            log_files = [f for f in expected_files if f in existing_keys]
    except Exception as e:
        logger.error("Error listing S3 objects: %s", str(e))

    return log_files


def _scan_log_file(
    s3_client: Any,
    s3_access_point: str,
    log_file_key: str,
    start_time: datetime,
    end_time: datetime,
    path_filter: str | None,
    operations: list[str] | None,
) -> list[dict]:
    """ログファイルをスキャンしてフィルタに一致するレコードを返す."""
    try:
        response = s3_client.get_object(
            Bucket=s3_access_point,
            Key=log_file_key,
        )
        content = response["Body"].read().decode("utf-8")
    except Exception as e:
        logger.error("Error reading log file %s: %s", log_file_key, str(e))
        return []

    matches: list[dict] = []

    for line in content.strip().split("\n"):
        if not line:
            continue

        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue

        # Filter by timestamp
        record_time_str = record.get("timestamp", "")
        try:
            record_time = datetime.fromisoformat(record_time_str)
        except (ValueError, TypeError):
            continue

        # Remove timezone info for comparison if needed
        if record_time.tzinfo and not start_time.tzinfo:
            record_time = record_time.replace(tzinfo=None)

        if record_time < start_time or record_time > end_time:
            continue

        # Filter by operation
        if operations and record.get("operation_type") not in operations:
            continue

        # Filter by path
        if path_filter:
            file_path = record.get("file_path", "")
            if not file_path.startswith(path_filter):
                continue

        matches.append(record)

    return matches


def _send_to_sqs(records: list[dict]) -> int:
    """フィルタ結果を SQS に送信する."""
    if not SQS_QUEUE_URL or not records:
        return 0

    sqs_client = boto3.client("sqs")
    sent_count = 0

    for record in records:
        try:
            sqs_client.send_message(
                QueueUrl=SQS_QUEUE_URL,
                MessageBody=json.dumps(record, ensure_ascii=False),
            )
            sent_count += 1
        except Exception as e:
            logger.error("Error sending to SQS: %s", str(e))

    return sent_count
