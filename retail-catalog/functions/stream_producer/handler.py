"""UC11 Stream Producer Lambda ハンドラ

EventBridge Scheduler (rate(1 minute)) でトリガーされ、S3 Access Point の
現在のオブジェクト一覧と DynamoDB state テーブルを比較して、
新規・変更・削除ファイルを検出し、Kinesis Data Stream に変更イベントを書き込む。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN
    KINESIS_STREAM_NAME: Kinesis Data Stream 名
    STATE_TABLE_NAME: DynamoDB state テーブル名
    USE_CASE: ユースケース名 (default: "retail-catalog")
    REGION: AWS リージョン (default: "ap-northeast-1")
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import trace_lambda_handler, EmfMetrics, xray_subsegment
from shared.s3ap_helper import S3ApHelper
from shared.streaming import StreamingHelper, StreamingConfig

logger = logging.getLogger(__name__)


def _get_state_table_items(dynamodb_resource, table_name: str) -> dict[str, dict]:
    """DynamoDB state テーブルから全アイテムを取得する

    Args:
        dynamodb_resource: boto3 DynamoDB resource
        table_name: テーブル名

    Returns:
        dict: file_key をキーとするアイテム辞書
    """
    table = dynamodb_resource.Table(table_name)
    items: dict[str, dict] = {}
    response = table.scan()

    for item in response.get("Items", []):
        items[item["file_key"]] = item

    # ページネーション対応
    while "LastEvaluatedKey" in response:
        response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
        for item in response.get("Items", []):
            items[item["file_key"]] = item

    return items


def _detect_changes(
    s3_objects: list[dict],
    state_items: dict[str, dict],
) -> tuple[list[dict], list[dict], list[dict]]:
    """S3 AP オブジェクトと DynamoDB state を比較し変更を検出する

    Args:
        s3_objects: S3 AP から取得したオブジェクトリスト
        state_items: DynamoDB state テーブルのアイテム辞書

    Returns:
        tuple: (created, modified, deleted) の各変更リスト
    """
    created: list[dict] = []
    modified: list[dict] = []
    deleted: list[dict] = []

    # 現在の S3 AP キーセット
    current_keys: set[str] = set()

    for obj in s3_objects:
        key = obj["Key"]
        current_keys.add(key)
        etag = obj.get("ETag", "")
        last_modified = obj.get("LastModified", "")

        if key not in state_items:
            # 新規ファイル
            created.append({
                "key": key,
                "etag": etag,
                "last_modified": last_modified,
            })
        else:
            # 既存ファイル — ETag で変更検出
            state_etag = state_items[key].get("etag", "")
            if etag != state_etag:
                modified.append({
                    "key": key,
                    "etag": etag,
                    "last_modified": last_modified,
                })

    # 削除検出: state にあるが S3 AP にないファイル
    for key in state_items:
        if key not in current_keys:
            deleted.append({
                "key": key,
                "etag": state_items[key].get("etag", ""),
                "last_modified": state_items[key].get("last_modified", ""),
            })

    return created, modified, deleted


def _update_state_table(
    dynamodb_resource,
    table_name: str,
    created: list[dict],
    modified: list[dict],
    deleted: list[dict],
    timestamp: str,
) -> None:
    """DynamoDB state テーブルを更新する

    Args:
        dynamodb_resource: boto3 DynamoDB resource
        table_name: テーブル名
        created: 新規ファイルリスト
        modified: 変更ファイルリスト
        deleted: 削除ファイルリスト
        timestamp: 更新タイムスタンプ
    """
    table = dynamodb_resource.Table(table_name)

    # 新規・変更ファイルを upsert
    for item in created + modified:
        table.put_item(Item={
            "file_key": item["key"],
            "etag": item["etag"],
            "last_modified": item["last_modified"],
            "processing_status": "pending",
            "updated_at": timestamp,
        })

    # 削除ファイルを state テーブルから削除
    for item in deleted:
        table.delete_item(Key={"file_key": item["key"]})


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Stream Producer Lambda ハンドラ

    S3 AP の現在のオブジェクト一覧と DynamoDB state テーブルを比較し、
    変更イベントを Kinesis Data Stream に書き込む。

    Returns:
        dict: 処理結果サマリー
    """
    # 環境変数取得
    s3_access_point = os.environ["S3_ACCESS_POINT"]
    stream_name = os.environ["KINESIS_STREAM_NAME"]
    state_table_name = os.environ["STATE_TABLE_NAME"]
    region = os.environ.get("REGION", "ap-northeast-1")
    use_case = os.environ.get("USE_CASE", "retail-catalog")

    now = datetime.now(timezone.utc)
    timestamp = now.isoformat()

    # EMF メトリクス
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="stream-producer")
    metrics.set_dimension("UseCase", use_case)

    # S3 AP からオブジェクト一覧取得
    with xray_subsegment(
        name="s3ap_list_objects",
        annotations={"service_name": "s3", "operation": "ListObjectsV2", "use_case": use_case},
    ):
        s3ap = S3ApHelper(s3_access_point)
        s3_objects = s3ap.list_objects()

    logger.info("S3 AP objects found: %d", len(s3_objects))

    # DynamoDB state テーブルから現在の状態を取得
    dynamodb = boto3.resource("dynamodb", region_name=region)

    with xray_subsegment(
        name="dynamodb_scan_state",
        annotations={"service_name": "dynamodb", "operation": "Scan", "use_case": use_case},
    ):
        state_items = _get_state_table_items(dynamodb, state_table_name)

    logger.info("State table items: %d", len(state_items))

    # 変更検出
    created, modified, deleted = _detect_changes(s3_objects, state_items)

    total_changes = len(created) + len(modified) + len(deleted)
    logger.info(
        "Changes detected: created=%d, modified=%d, deleted=%d",
        len(created),
        len(modified),
        len(deleted),
    )

    # 変更がない場合は早期リターン
    if total_changes == 0:
        metrics.put_metric("ChangesDetected", 0, "Count")
        metrics.flush()
        return {
            "status": "no_changes",
            "timestamp": timestamp,
            "created": 0,
            "modified": 0,
            "deleted": 0,
        }

    # Kinesis レコード生成
    records: list[dict] = []
    for item in created:
        records.append(
            StreamingHelper.create_event_record(
                key=item["key"],
                event_type="created",
                timestamp=timestamp,
                metadata={"etag": item["etag"], "last_modified": item["last_modified"]},
            )
        )
    for item in modified:
        records.append(
            StreamingHelper.create_event_record(
                key=item["key"],
                event_type="modified",
                timestamp=timestamp,
                metadata={"etag": item["etag"], "last_modified": item["last_modified"]},
            )
        )
    for item in deleted:
        records.append(
            StreamingHelper.create_event_record(
                key=item["key"],
                event_type="deleted",
                timestamp=timestamp,
            )
        )

    # Kinesis Data Stream に書き込み
    streaming_config = StreamingConfig(stream_name=stream_name, region=region)
    streaming_helper = StreamingHelper(streaming_config)

    with xray_subsegment(
        name="kinesis_put_records",
        annotations={"service_name": "kinesis", "operation": "PutRecords", "use_case": use_case},
    ):
        streaming_helper.put_records(records)

    logger.info("Successfully wrote %d records to Kinesis stream", len(records))

    # DynamoDB state テーブル更新
    with xray_subsegment(
        name="dynamodb_update_state",
        annotations={"service_name": "dynamodb", "operation": "UpdateState", "use_case": use_case},
    ):
        _update_state_table(dynamodb, state_table_name, created, modified, deleted, timestamp)

    # EMF メトリクス出力
    metrics.put_metric("ChangesDetected", total_changes, "Count")
    metrics.put_metric("FilesCreated", len(created), "Count")
    metrics.put_metric("FilesModified", len(modified), "Count")
    metrics.put_metric("FilesDeleted", len(deleted), "Count")
    metrics.flush()

    return {
        "status": "changes_published",
        "timestamp": timestamp,
        "created": len(created),
        "modified": len(modified),
        "deleted": len(deleted),
        "total_records": len(records),
    }
