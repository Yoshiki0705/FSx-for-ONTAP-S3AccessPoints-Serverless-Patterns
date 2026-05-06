"""SageMaker Batch Transform 起動 Lambda ハンドラ

Step Functions .waitForTaskToken から Task_Token を受け取り、
SageMaker Batch Transform ジョブを起動する。
MOCK_MODE=true の場合はモックセグメンテーション出力を生成し、
直接 SendTaskSuccess を呼び出す。

Environment Variables:
    MOCK_MODE: モックモード有効化 (default: "false")
    SAGEMAKER_MODEL_NAME: SageMaker モデル名
    SAGEMAKER_INSTANCE_TYPE: インスタンスタイプ (default: ml.m5.xlarge)
    OUTPUT_BUCKET: S3 出力バケット名
    USE_CASE: ユースケース名 (default: "autonomous-driving")
    REGION: AWS リージョン
"""

from __future__ import annotations

import json
import logging
import os
import random
from datetime import datetime, timezone

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)


def generate_mock_segmentation(point_count: int) -> list[int]:
    """モックセグメンテーションラベルを生成する

    入力 point_count と同数のランダムラベル（0-9）を生成する。

    Args:
        point_count: 入力点群のポイント数

    Returns:
        list[int]: セグメンテーションラベルのリスト（長さ == point_count）
    """
    return [random.randint(0, 9) for _ in range(point_count)]



def _handle_mock_mode(event: dict, task_token: str, output_bucket: str) -> dict:
    """MOCK_MODE=true 時の処理

    モックセグメンテーション出力を S3 に書き込み、
    直接 SendTaskSuccess を呼び出す。

    Args:
        event: Lambda イベント
        task_token: Step Functions Task Token
        output_bucket: S3 出力バケット名

    Returns:
        dict: 処理結果メタデータ
    """
    region = os.environ.get("REGION", os.environ.get("AWS_REGION", "ap-northeast-1"))
    point_count = event.get("point_count", 1000)
    input_s3_path = event.get("input_s3_path", "")

    # モックセグメンテーション出力生成
    labels = generate_mock_segmentation(point_count)

    # S3 に出力
    now = datetime.now(timezone.utc)
    output_key = f"sagemaker-output/{now.strftime('%Y/%m/%d')}/mock_segmentation.json"
    output_data = {
        "input_s3_path": input_s3_path,
        "point_count": point_count,
        "labels": labels,
        "model": "mock-segmentation-model",
        "timestamp": now.isoformat(),
    }

    s3_client = boto3.client("s3", region_name=region)
    s3_client.put_object(
        Bucket=output_bucket,
        Key=output_key,
        Body=json.dumps(output_data),
        ContentType="application/json",
    )

    # SendTaskSuccess を直接呼び出す
    sfn_client = boto3.client("stepfunctions", region_name=region)
    output_metadata = {
        "status": "COMPLETED",
        "output_s3_path": f"s3://{output_bucket}/{output_key}",
        "point_count": point_count,
        "labels_count": len(labels),
    }
    sfn_client.send_task_success(
        taskToken=task_token,
        output=json.dumps(output_metadata),
    )

    logger.info(
        "Mock mode: SendTaskSuccess called with task_token, point_count=%d",
        point_count,
    )

    return output_metadata


def _handle_real_mode(event: dict, task_token: str, output_bucket: str) -> dict:
    """MOCK_MODE=false 時の処理

    SageMaker CreateTransformJob API を呼び出す。
    Task_Token はジョブタグとして渡す。

    Args:
        event: Lambda イベント
        task_token: Step Functions Task Token
        output_bucket: S3 出力バケット名

    Returns:
        dict: Transform ジョブ情報
    """
    region = os.environ.get("REGION", os.environ.get("AWS_REGION", "ap-northeast-1"))
    model_name = os.environ.get("SAGEMAKER_MODEL_NAME", "point-cloud-segmentation")
    instance_type = os.environ.get("SAGEMAKER_INSTANCE_TYPE", "ml.m5.xlarge")

    input_s3_path = event.get("input_s3_path", "")

    now = datetime.now(timezone.utc)
    job_name = f"ad-segmentation-{now.strftime('%Y%m%d%H%M%S')}"
    output_s3_path = f"s3://{output_bucket}/sagemaker-output/{now.strftime('%Y/%m/%d')}/"

    sagemaker_client = boto3.client("sagemaker", region_name=region)
    sagemaker_client.create_transform_job(
        TransformJobName=job_name,
        ModelName=model_name,
        TransformInput={
            "DataSource": {
                "S3DataSource": {
                    "S3DataType": "S3Prefix",
                    "S3Uri": input_s3_path,
                }
            },
            "ContentType": "application/json",
        },
        TransformOutput={
            "S3OutputPath": output_s3_path,
        },
        TransformResources={
            "InstanceType": instance_type,
            "InstanceCount": 1,
        },
        Tags=[
            {"Key": "TaskToken", "Value": task_token},
            {"Key": "UseCase", "Value": "autonomous-driving"},
            {"Key": "Phase", "Value": "3"},
            {"Key": "Component", "Value": "sagemaker"},
        ],
    )

    logger.info(
        "SageMaker Transform job created: job_name=%s, model=%s, instance=%s",
        job_name,
        model_name,
        instance_type,
    )

    return {
        "status": "JOB_CREATED",
        "job_name": job_name,
        "output_s3_path": output_s3_path,
    }


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """SageMaker Invoke Lambda ハンドラ

    Step Functions .waitForTaskToken から呼び出される。
    MOCK_MODE に応じて実際の SageMaker ジョブ起動またはモック処理を行う。

    Input:
        {
            "task_token": "...",
            "input_s3_path": "s3://...",
            "point_count": N
        }

    Output:
        {
            "status": "COMPLETED" | "JOB_CREATED",
            ...
        }
    """
    mock_mode = os.environ.get("MOCK_MODE", "false").lower() == "true"
    output_bucket = os.environ["OUTPUT_BUCKET"]
    task_token = event.get("task_token", "")

    logger.info(
        "SageMaker Invoke started: mock_mode=%s, task_token_length=%d",
        mock_mode,
        len(task_token),
    )

    metrics = EmfMetrics(
        namespace="FSxN-S3AP-Patterns",
        service="sagemaker-invoke",
    )
    metrics.set_dimension("UseCase", "autonomous-driving")

    if mock_mode:
        result = _handle_mock_mode(event, task_token, output_bucket)
        metrics.put_metric("MockInvocations", 1.0, "Count")
    else:
        result = _handle_real_mode(event, task_token, output_bucket)
        metrics.put_metric("RealInvocations", 1.0, "Count")

    metrics.flush()
    return result
