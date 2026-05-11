"""UC11 Stream Consumer Lambda ハンドラ

Kinesis Event Source Mapping (batch size: 10, bisect-on-error: true) でトリガーされ、
ファイル変更イベントを処理する。有効な "created"/"modified" イベントに対して
既存の ImageTagging + CatalogMetadata パイプラインを呼び出す。

処理フロー:
1. レコードスキーマバリデーション（key, event_type, timestamp 必須）
2. 不正レコード: 破棄 + 警告ログ（シーケンス番号のみ記録、内容は記録しない）
3. DynamoDB conditional writes による冪等処理チェック
4. 有効な created/modified イベント: ImageTagging + CatalogMetadata Lambda を呼び出す
5. 処理エラー: DynamoDB dead-letter テーブルに書き込む

Environment Variables:
    STATE_TABLE_NAME: DynamoDB state テーブル名
    DEAD_LETTER_TABLE_NAME: DynamoDB dead-letter テーブル名
    IMAGE_TAGGING_FUNCTION: ImageTagging Lambda 関数名/ARN
    CATALOG_METADATA_FUNCTION: CatalogMetadata Lambda 関数名/ARN
    USE_CASE: ユースケース名 (default: "retail-catalog")
"""

from __future__ import annotations

import base64
import json
import logging
import os
import uuid
from datetime import datetime, timezone

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import trace_lambda_handler, EmfMetrics, xray_subsegment

logger = logging.getLogger(__name__)

# 必須フィールド
REQUIRED_FIELDS = {"key", "event_type", "timestamp"}

# 処理対象のイベントタイプ
PROCESSABLE_EVENT_TYPES = {"created", "modified"}


def _validate_record(record_data: dict) -> bool:
    """レコードスキーマをバリデーションする

    Args:
        record_data: デコードされたレコードデータ

    Returns:
        bool: バリデーション成功時 True
    """
    if not isinstance(record_data, dict):
        return False
    return REQUIRED_FIELDS.issubset(record_data.keys())


def _is_already_processed(
    dynamodb_resource,
    table_name: str,
    file_key: str,
) -> bool:
    """冪等処理チェック: 既に処理済みかどうかを確認する

    Args:
        dynamodb_resource: boto3 DynamoDB resource
        table_name: state テーブル名
        file_key: ファイルキー

    Returns:
        bool: 処理済みの場合 True
    """
    table = dynamodb_resource.Table(table_name)
    try:
        response = table.get_item(Key={"file_key": file_key})
        item = response.get("Item")
        if item and item.get("processing_status") == "completed":
            return True
    except Exception as e:
        logger.warning("Failed to check processing status for %s: %s", file_key, e)
    return False


def _mark_processing(
    dynamodb_resource,
    table_name: str,
    file_key: str,
) -> bool:
    """DynamoDB conditional write で処理中マークを設定する

    Args:
        dynamodb_resource: boto3 DynamoDB resource
        table_name: state テーブル名
        file_key: ファイルキー

    Returns:
        bool: マーク成功時 True（既に processing/completed の場合 False）
    """
    table = dynamodb_resource.Table(table_name)
    try:
        table.update_item(
            Key={"file_key": file_key},
            UpdateExpression="SET processing_status = :status, updated_at = :ts",
            ConditionExpression="attribute_not_exists(processing_status) OR processing_status <> :completed",
            ExpressionAttributeValues={
                ":status": "processing",
                ":completed": "completed",
                ":ts": datetime.now(timezone.utc).isoformat(),
            },
        )
        return True
    except dynamodb_resource.meta.client.exceptions.ConditionalCheckFailedException:
        return False
    except Exception as e:
        logger.warning("Failed to mark processing for %s: %s", file_key, e)
        return False


def _invoke_pipeline(
    lambda_client,
    file_key: str,
    image_tagging_function: str,
    catalog_metadata_function: str,
) -> dict:
    """ImageTagging + CatalogMetadata パイプラインを呼び出す

    Args:
        lambda_client: boto3 Lambda client
        file_key: 処理対象ファイルキー
        image_tagging_function: ImageTagging Lambda 関数名/ARN
        catalog_metadata_function: CatalogMetadata Lambda 関数名/ARN

    Returns:
        dict: パイプライン実行結果

    Raises:
        Exception: Lambda 呼び出しに失敗した場合
    """
    payload = json.dumps({"Key": file_key}).encode("utf-8")

    # ImageTagging 呼び出し
    tagging_response = lambda_client.invoke(
        FunctionName=image_tagging_function,
        InvocationType="RequestResponse",
        Payload=payload,
    )
    tagging_result = json.loads(tagging_response["Payload"].read())

    # CatalogMetadata 呼び出し
    metadata_payload = json.dumps({
        "Key": file_key,
        "tagging_result": tagging_result,
    }).encode("utf-8")

    metadata_response = lambda_client.invoke(
        FunctionName=catalog_metadata_function,
        InvocationType="RequestResponse",
        Payload=metadata_payload,
    )
    metadata_result = json.loads(metadata_response["Payload"].read())

    return {
        "tagging": tagging_result,
        "metadata": metadata_result,
    }


def _write_dead_letter(
    dynamodb_resource,
    table_name: str,
    file_key: str,
    error: str,
    retry_count: int = 0,
) -> None:
    """DynamoDB dead-letter テーブルに失敗レコードを書き込む

    Args:
        dynamodb_resource: boto3 DynamoDB resource
        table_name: dead-letter テーブル名
        file_key: ファイルキー
        error: エラーメッセージ
        retry_count: リトライ回数
    """
    table = dynamodb_resource.Table(table_name)
    record_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    table.put_item(Item={
        "record_id": record_id,
        "file_key": file_key,
        "error": error,
        "timestamp": timestamp,
        "retry_count": retry_count,
    })

    logger.error(
        "Dead-letter record written: record_id=%s, file_key=%s",
        record_id,
        file_key,
    )


def _mark_completed(
    dynamodb_resource,
    table_name: str,
    file_key: str,
) -> None:
    """処理完了マークを設定する

    Args:
        dynamodb_resource: boto3 DynamoDB resource
        table_name: state テーブル名
        file_key: ファイルキー
    """
    table = dynamodb_resource.Table(table_name)
    table.update_item(
        Key={"file_key": file_key},
        UpdateExpression="SET processing_status = :status, updated_at = :ts",
        ExpressionAttributeValues={
            ":status": "completed",
            ":ts": datetime.now(timezone.utc).isoformat(),
        },
    )


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Stream Consumer Lambda ハンドラ

    Kinesis Event Source Mapping からバッチレコードを受信し、
    各レコードを処理する。

    Args:
        event: Kinesis イベント (Records リスト)
        context: Lambda コンテキスト

    Returns:
        dict: 処理結果サマリー
    """
    # 環境変数取得
    state_table_name = os.environ["STATE_TABLE_NAME"]
    dead_letter_table_name = os.environ["DEAD_LETTER_TABLE_NAME"]
    image_tagging_function = os.environ["IMAGE_TAGGING_FUNCTION"]
    catalog_metadata_function = os.environ["CATALOG_METADATA_FUNCTION"]
    use_case = os.environ.get("USE_CASE", "retail-catalog")
    region = os.environ.get("REGION", "ap-northeast-1")

    # EMF メトリクス
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="stream-consumer")
    metrics.set_dimension("UseCase", use_case)

    dynamodb = boto3.resource("dynamodb", region_name=region)
    lambda_client = boto3.client("lambda", region_name=region)

    records = event.get("Records", [])
    total_records = len(records)
    processed = 0
    skipped = 0
    failed = 0
    invalid = 0

    logger.info("Processing batch of %d records", total_records)

    for record in records:
        sequence_number = record.get("kinesis", {}).get("sequenceNumber", "unknown")

        # レコードデータのデコード
        try:
            raw_data = base64.b64decode(record["kinesis"]["data"])
            record_data = json.loads(raw_data)
        except (KeyError, json.JSONDecodeError, Exception) as e:
            # Requirement 14.6: 不正レコードは破棄 + 警告ログ（シーケンス番号のみ）
            logger.warning(
                "Invalid record format at sequence_number=%s, discarding",
                sequence_number,
            )
            invalid += 1
            continue

        # スキーマバリデーション
        if not _validate_record(record_data):
            # Requirement 14.6: 不正レコードは破棄 + 警告ログ（シーケンス番号のみ）
            logger.warning(
                "Record schema validation failed at sequence_number=%s, discarding",
                sequence_number,
            )
            invalid += 1
            continue

        file_key = record_data["key"]
        event_type = record_data["event_type"]

        # 処理対象外のイベントタイプはスキップ
        if event_type not in PROCESSABLE_EVENT_TYPES:
            logger.debug(
                "Skipping non-processable event_type=%s for key=%s",
                event_type,
                file_key,
            )
            skipped += 1
            continue

        # 冪等処理チェック
        if _is_already_processed(dynamodb, state_table_name, file_key):
            logger.debug("Already processed: %s, skipping", file_key)
            skipped += 1
            continue

        # 処理中マーク（conditional write）
        if not _mark_processing(dynamodb, state_table_name, file_key):
            logger.debug("Could not acquire processing lock for: %s, skipping", file_key)
            skipped += 1
            continue

        # パイプライン呼び出し
        try:
            with xray_subsegment(
                name="invoke_pipeline",
                annotations={
                    "service_name": "lambda",
                    "operation": "InvokePipeline",
                    "use_case": use_case,
                },
            ):
                _invoke_pipeline(
                    lambda_client,
                    file_key,
                    image_tagging_function,
                    catalog_metadata_function,
                )

            # 処理完了マーク
            _mark_completed(dynamodb, state_table_name, file_key)
            processed += 1

        except Exception as e:
            logger.error("Processing failed for key=%s: %s", file_key, str(e))
            # Dead-letter テーブルに書き込み
            _write_dead_letter(
                dynamodb,
                dead_letter_table_name,
                file_key,
                str(e),
            )
            failed += 1

    # EMF メトリクス出力
    metrics.put_metric("RecordsProcessed", processed, "Count")
    metrics.put_metric("RecordsSkipped", skipped, "Count")
    metrics.put_metric("RecordsFailed", failed, "Count")
    metrics.put_metric("RecordsInvalid", invalid, "Count")
    metrics.flush()

    logger.info(
        "Batch processing complete: total=%d, processed=%d, skipped=%d, failed=%d, invalid=%d",
        total_records,
        processed,
        skipped,
        failed,
        invalid,
    )

    return {
        "status": "batch_processed",
        "total": total_records,
        "processed": processed,
        "skipped": skipped,
        "failed": failed,
        "invalid": invalid,
    }
