"""SageMaker Batch Transform コールバック Lambda ハンドラ

EventBridge ルール（SageMaker Transform ジョブ状態変更）でトリガーされる。
ジョブタグから Task_Token を取得し、ジョブ結果に応じて
SendTaskSuccess または SendTaskFailure を呼び出す。

Environment Variables:
    USE_CASE: ユースケース名 (default: "autonomous-driving")
    REGION: AWS リージョン
"""

from __future__ import annotations

import json
import logging
import os

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import trace_lambda_handler

logger = logging.getLogger(__name__)


def extract_task_token_from_tags(sagemaker_client, job_name: str) -> str | None:
    """SageMaker ジョブタグから Task_Token を取得する

    Args:
        sagemaker_client: boto3 SageMaker クライアント
        job_name: Transform ジョブ名

    Returns:
        str | None: Task_Token（見つからない場合は None）
    """
    try:
        response = sagemaker_client.describe_transform_job(
            TransformJobName=job_name,
        )
        # タグはジョブ ARN から取得
        job_arn = response.get("TransformJobArn", "")
        if not job_arn:
            logger.warning("TransformJobArn not found for job: %s", job_name)
            return None

        tags_response = sagemaker_client.list_tags(ResourceArn=job_arn)
        tags = tags_response.get("Tags", [])

        for tag in tags:
            if tag.get("Key") == "TaskToken":
                return tag.get("Value")

        logger.warning("TaskToken tag not found for job: %s", job_name)
        return None
    except Exception as e:
        logger.error("Failed to extract TaskToken from job %s: %s", job_name, e)
        return None


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

    logger.info("SendTaskFailure called for job: %s, error: %s", job_name, error_message)
    return {"action": "SendTaskFailure", "job_name": job_name, "error": error_message}


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """SageMaker Callback Lambda ハンドラ

    EventBridge ルール（SageMaker Transform ジョブ状態変更）でトリガーされる。

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
        {"action": "SendTaskSuccess" | "SendTaskFailure", "job_name": "..."}
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

    # Task_Token をジョブタグから取得
    sagemaker_client = boto3.client("sagemaker", region_name=region)
    task_token = extract_task_token_from_tags(sagemaker_client, job_name)

    if not task_token:
        logger.error("TaskToken not found for job: %s", job_name)
        return {"action": "ERROR", "error": "TaskToken not found"}

    sfn_client = boto3.client("stepfunctions", region_name=region)

    if job_status == "Completed":
        return handle_job_success(sfn_client, task_token, job_name, output_s3_path)
    elif job_status in ("Failed", "Stopped"):
        error_msg = failure_reason or f"Job {job_status}: {job_name}"
        return handle_job_failure(sfn_client, task_token, job_name, error_msg)
    else:
        logger.warning("Unexpected job status: %s for job: %s", job_status, job_name)
        return {"action": "IGNORED", "job_name": job_name, "status": job_status}
