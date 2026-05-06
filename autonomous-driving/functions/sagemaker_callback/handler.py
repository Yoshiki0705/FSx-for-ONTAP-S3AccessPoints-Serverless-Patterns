"""SageMaker Batch Transform コールバック Lambda ハンドラ

EventBridge ルール（SageMaker Transform ジョブ状態変更）でトリガーされる。
ジョブタグから Token 取得方式を自動検出し、ジョブ結果に応じて
SendTaskSuccess または SendTaskFailure を呼び出す。

Token 取得方式の検出ロジック:
- CorrelationId タグが存在 → DynamoDB モード（本番）
  - DynamoDB から task_token を取得し、コールバック後にレコード削除
- TaskToken タグが存在 → Direct モード（Phase 3 互換 / テスト用）
  - タグ値を直接 task_token として使用

Environment Variables:
    USE_CASE: ユースケース名 (default: "autonomous-driving")
    REGION: AWS リージョン
    TASK_TOKEN_TABLE_NAME: DynamoDB テーブル名 (DynamoDB モード時に使用)
"""

from __future__ import annotations

import json
import logging
import os

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler
from shared.task_token_store import TaskTokenStore

logger = logging.getLogger(__name__)


def _get_tags_from_job(sagemaker_client, job_name: str) -> list[dict[str, str]]:
    """SageMaker ジョブからタグ一覧を取得する。

    Args:
        sagemaker_client: boto3 SageMaker クライアント
        job_name: Transform ジョブ名

    Returns:
        list[dict]: タグのリスト [{"Key": "...", "Value": "..."}, ...]
    """
    try:
        response = sagemaker_client.describe_transform_job(
            TransformJobName=job_name,
        )
        job_arn = response.get("TransformJobArn", "")
        if not job_arn:
            logger.warning("TransformJobArn not found for job: %s", job_name)
            return []

        tags_response = sagemaker_client.list_tags(ResourceArn=job_arn)
        return tags_response.get("Tags", [])
    except Exception as e:
        logger.error("Failed to get tags from job %s: %s", job_name, e)
        return []


def _detect_token_mode(tags: list[dict[str, str]]) -> tuple[str, str | None]:
    """タグからトークン取得モードを検出する。

    CorrelationId タグが存在すれば DynamoDB モード、
    TaskToken タグが存在すれば Direct モードと判定する。

    Args:
        tags: ジョブタグのリスト

    Returns:
        tuple: (mode, value)
            - ("dynamodb", correlation_id) — DynamoDB モード
            - ("direct", task_token) — Direct モード
            - ("unknown", None) — どちらのタグも見つからない
    """
    correlation_id = None
    task_token_value = None

    for tag in tags:
        key = tag.get("Key", "")
        value = tag.get("Value", "")
        if key == "CorrelationId":
            correlation_id = value
        elif key == "TaskToken":
            task_token_value = value

    # CorrelationId タグ優先（DynamoDB モード）
    if correlation_id:
        return "dynamodb", correlation_id

    # TaskToken タグ（Direct モード / Phase 3 互換）
    if task_token_value:
        return "direct", task_token_value

    return "unknown", None


def _retrieve_token_from_dynamodb(correlation_id: str) -> str | None:
    """DynamoDB から Task Token を取得する。

    Args:
        correlation_id: 8 文字 hex の Correlation ID

    Returns:
        str | None: Task Token（見つからない場合は None）
    """
    table_name = os.environ.get("TASK_TOKEN_TABLE_NAME")
    if not table_name:
        logger.error(
            "TASK_TOKEN_TABLE_NAME not set; cannot retrieve token "
            "for correlation_id=%s",
            correlation_id,
        )
        return None

    store = TaskTokenStore(table_name=table_name)
    return store.retrieve_token(correlation_id)


def _delete_token_from_dynamodb(correlation_id: str) -> None:
    """DynamoDB から Token レコードを削除する。

    Args:
        correlation_id: 8 文字 hex の Correlation ID
    """
    table_name = os.environ.get("TASK_TOKEN_TABLE_NAME")
    if not table_name:
        logger.warning(
            "TASK_TOKEN_TABLE_NAME not set; cannot delete token "
            "for correlation_id=%s",
            correlation_id,
        )
        return

    store = TaskTokenStore(table_name=table_name)
    store.delete_token(correlation_id)


def _emit_orphaned_callback_metric(job_name: str, correlation_id: str) -> None:
    """OrphanedCallback EMF メトリクスを出力する。

    Token が DynamoDB に見つからない場合（TTL 期限切れ等）に呼び出される。

    Args:
        job_name: Transform ジョブ名
        correlation_id: 見つからなかった Correlation ID
    """
    metrics = EmfMetrics(
        namespace="FSxN-S3AP-Patterns",
        service="sagemaker-callback",
    )
    metrics.set_dimension("UseCase", "autonomous-driving")
    metrics.put_metric("OrphanedCallback", 1.0, "Count")
    metrics.set_property("TransformJobName", job_name)
    metrics.set_property("CorrelationId", correlation_id)
    metrics.flush()


def handle_job_success(
    sfn_client, task_token: str, job_name: str, output_s3_path: str
) -> dict:
    """ジョブ成功時の処理

    SendTaskSuccess を呼び出す。

    Args:
        sfn_client: boto3 Step Functions クライアント
        task_token: Step Functions Task Token
        job_name: Transform ジョブ名
        output_s3_path: 出力 S3 パス

    Returns:
        dict: 処理結果
    """
    output_metadata = {
        "status": "COMPLETED",
        "job_name": job_name,
        "output_s3_path": output_s3_path,
    }

    sfn_client.send_task_success(
        taskToken=task_token,
        output=json.dumps(output_metadata),
    )

    # セキュリティ: task_token の値はログに出力しない
    logger.info("SendTaskSuccess called for job: %s", job_name)
    return {"action": "SendTaskSuccess", "job_name": job_name}


def handle_job_failure(
    sfn_client, task_token: str, job_name: str, error_message: str
) -> dict:
    """ジョブ失敗/タイムアウト時の処理

    SendTaskFailure を呼び出す。

    Args:
        sfn_client: boto3 Step Functions クライアント
        task_token: Step Functions Task Token
        job_name: Transform ジョブ名
        error_message: エラーメッセージ

    Returns:
        dict: 処理結果
    """
    sfn_client.send_task_failure(
        taskToken=task_token,
        error="SageMakerTransformJobFailed",
        cause=error_message or f"Transform job {job_name} failed",
    )

    # セキュリティ: task_token の値はログに出力しない
    logger.info(
        "SendTaskFailure called for job: %s, error: %s",
        job_name,
        error_message,
    )
    return {"action": "SendTaskFailure", "job_name": job_name, "error": error_message}


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """SageMaker Callback Lambda ハンドラ

    EventBridge ルール（SageMaker Transform ジョブ状態変更）でトリガーされる。

    Detection logic:
      - If tag "CorrelationId" exists → DynamoDB mode
      - If tag "TaskToken" exists → Direct mode (Phase 3 compat)

    DynamoDB mode:
      1. Extract CorrelationId from job tags
      2. Query DynamoDB for task_token
      3. Call SendTaskSuccess/SendTaskFailure
      4. Delete DynamoDB record

    Direct mode:
      1. Extract TaskToken from job tags
      2. Call SendTaskSuccess/SendTaskFailure (Phase 3 behavior)

    Input (EventBridge event):
        {
            "detail": {
                "TransformJobName": "...",
                "TransformJobStatus": "Completed" | "Failed" | "Stopped",
                "FailureReason": "...",
                "TransformOutput": {"S3OutputPath": "..."}
            }
        }

    Output:
        {"action": "SendTaskSuccess" | "SendTaskFailure" | "ERROR", ...}
    """
    region = os.environ.get("REGION", os.environ.get("AWS_REGION", "ap-northeast-1"))

    detail = event.get("detail", {})
    job_name = detail.get("TransformJobName", "")
    job_status = detail.get("TransformJobStatus", "")
    failure_reason = detail.get("FailureReason", "")
    output_s3_path = detail.get("TransformOutput", {}).get("S3OutputPath", "")

    logger.info(
        "SageMaker Callback: job_name=%s, status=%s",
        job_name,
        job_status,
    )

    if not job_name:
        logger.error("TransformJobName not found in event")
        return {"action": "ERROR", "error": "Missing TransformJobName"}

    # ジョブタグを取得
    sagemaker_client = boto3.client("sagemaker", region_name=region)
    tags = _get_tags_from_job(sagemaker_client, job_name)

    # タグからトークン取得モードを検出
    mode, tag_value = _detect_token_mode(tags)

    logger.info(
        "Token mode detected: mode=%s, job_name=%s",
        mode,
        job_name,
    )

    # Task Token を取得
    task_token: str | None = None
    correlation_id: str | None = None

    if mode == "dynamodb":
        correlation_id = tag_value
        logger.info(
            "DynamoDB mode: retrieving token for correlation_id=%s",
            correlation_id,
        )
        task_token = _retrieve_token_from_dynamodb(correlation_id)

        if not task_token:
            # Token 未発見（TTL 期限切れ等）
            logger.error(
                "Token not found in DynamoDB: correlation_id=%s, "
                "job_name=%s (possibly TTL expired)",
                correlation_id,
                job_name,
            )
            _emit_orphaned_callback_metric(job_name, correlation_id)
            return {
                "action": "ERROR",
                "error": "Token not found (TTL expired)",
                "correlation_id": correlation_id,
                "job_name": job_name,
            }

    elif mode == "direct":
        # Direct モード: タグ値がそのまま task_token
        task_token = tag_value
        # セキュリティ: task_token の値はログに出力しない
        logger.info("Direct mode: task_token retrieved from tag")

    else:
        # どちらのタグも見つからない
        logger.error(
            "Neither CorrelationId nor TaskToken tag found for job: %s",
            job_name,
        )
        return {"action": "ERROR", "error": "No token tag found", "job_name": job_name}

    # Step Functions コールバック実行
    sfn_client = boto3.client("stepfunctions", region_name=region)

    if job_status == "Completed":
        result = handle_job_success(sfn_client, task_token, job_name, output_s3_path)
    elif job_status in ("Failed", "Stopped"):
        error_msg = failure_reason or f"Job {job_status}: {job_name}"
        result = handle_job_failure(sfn_client, task_token, job_name, error_msg)
    else:
        logger.warning(
            "Unexpected job status: %s for job: %s", job_status, job_name
        )
        return {"action": "IGNORED", "job_name": job_name, "status": job_status}

    # DynamoDB モード: コールバック成功後にレコード削除
    if mode == "dynamodb" and correlation_id:
        _delete_token_from_dynamodb(correlation_id)
        logger.info(
            "DynamoDB record deleted after callback: correlation_id=%s",
            correlation_id,
        )
        result["correlation_id"] = correlation_id
        result["token_mode"] = "dynamodb"
    else:
        result["token_mode"] = "direct"

    return result
