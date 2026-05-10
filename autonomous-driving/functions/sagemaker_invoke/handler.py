"""SageMaker Batch Transform 起動 Lambda ハンドラ

Step Functions .waitForTaskToken から Task_Token を受け取り、
SageMaker Batch Transform ジョブを起動する。
MOCK_MODE=true の場合はモックセグメンテーション出力を生成し、
直接 SendTaskSuccess を呼び出す。

TOKEN_STORAGE_MODE により Task Token の受け渡し方式を切り替える:
- "dynamodb": Correlation ID を生成し DynamoDB に Task Token を保存。
              ジョブタグには CorrelationId を設定（本番モード）。
- "direct":   Phase 3 互換。ジョブタグに TaskToken を直接設定（テスト用）。

Environment Variables:
    MOCK_MODE: モックモード有効化 (default: "false")
    TOKEN_STORAGE_MODE: "dynamodb" | "direct" (default: "direct")
    TASK_TOKEN_TABLE_NAME: DynamoDB テーブル名 (TOKEN_STORAGE_MODE="dynamodb" 時必須)
    TOKEN_TTL_SECONDS: Token TTL 秒数 (default: "86400")
    SAGEMAKER_MODEL_NAME: SageMaker モデル名
    SAGEMAKER_INSTANCE_TYPE: インスタンスタイプ (default: ml.m5.xlarge)
    OUTPUT_DESTINATION: `STANDARD_S3` or `FSXN_S3AP` (デフォルト: `STANDARD_S3`)
    OUTPUT_BUCKET: STANDARD_S3 モードの出力バケット名
    OUTPUT_S3AP_ALIAS: FSXN_S3AP モードの S3AP Alias or ARN
    OUTPUT_S3AP_PREFIX: FSXN_S3AP モードの出力プレフィックス (デフォルト: `ai-outputs/`)
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

from shared.exceptions import TokenStorageError, lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler
from shared.output_writer import OutputWriter
from shared.task_token_store import TaskTokenStore

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

    # セキュリティ: task_token の値はログに出力しない
    logger.info(
        "Mock mode: SendTaskSuccess called, point_count=%d",
        point_count,
    )

    return output_metadata


def _build_job_tags(
    token_storage_mode: str,
    task_token: str,
    job_name: str,
) -> tuple[list[dict[str, str]], str | None]:
    """TOKEN_STORAGE_MODE に応じてジョブタグを構築する。

    Args:
        token_storage_mode: "dynamodb" または "direct"
        task_token: Step Functions Task Token
        job_name: SageMaker Transform ジョブ名

    Returns:
        tuple: (タグリスト, correlation_id or None)

    Raises:
        TokenStorageError: DynamoDB モードで保存に失敗した場合
    """
    base_tags = [
        {"Key": "UseCase", "Value": "autonomous-driving"},
        {"Key": "Phase", "Value": "4"},
        {"Key": "Component", "Value": "sagemaker"},
    ]

    if token_storage_mode == "dynamodb":
        table_name = os.environ.get("TASK_TOKEN_TABLE_NAME")
        if not table_name:
            raise TokenStorageError(
                "TASK_TOKEN_TABLE_NAME environment variable is required "
                "when TOKEN_STORAGE_MODE is 'dynamodb'"
            )
        ttl_seconds = int(os.environ.get("TOKEN_TTL_SECONDS", "86400"))

        store = TaskTokenStore(table_name=table_name, ttl_seconds=ttl_seconds)
        correlation_id = store.store_token(
            task_token=task_token,
            transform_job_name=job_name,
        )

        # セキュリティ: task_token の値はログに出力しない
        logger.info(
            "DynamoDB mode: stored token with correlation_id=%s, "
            "transform_job_name=%s",
            correlation_id,
            job_name,
        )

        base_tags.append({"Key": "CorrelationId", "Value": correlation_id})
        return base_tags, correlation_id
    else:
        # Direct モード: Phase 3 互換（TaskToken タグに直接設定）
        base_tags.append({"Key": "TaskToken", "Value": task_token})
        return base_tags, None


def _handle_real_mode(event: dict, task_token: str, output_bucket: str) -> dict:
    """MOCK_MODE=false 時の処理

    SageMaker CreateTransformJob API を呼び出す。
    TOKEN_STORAGE_MODE に応じて Task Token の受け渡し方式を切り替える。

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
    token_storage_mode = os.environ.get("TOKEN_STORAGE_MODE", "direct")

    input_s3_path = event.get("input_s3_path", "")

    now = datetime.now(timezone.utc)
    job_name = f"ad-segmentation-{now.strftime('%Y%m%d%H%M%S')}"
    output_s3_path = f"s3://{output_bucket}/sagemaker-output/{now.strftime('%Y/%m/%d')}/"

    # TOKEN_STORAGE_MODE に応じたタグ構築
    tags, correlation_id = _build_job_tags(token_storage_mode, task_token, job_name)

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
        Tags=tags,
    )

    logger.info(
        "SageMaker Transform job created: job_name=%s, model=%s, "
        "instance=%s, token_storage_mode=%s",
        job_name,
        model_name,
        instance_type,
        token_storage_mode,
    )

    result = {
        "status": "JOB_CREATED",
        "job_name": job_name,
        "output_s3_path": output_s3_path,
        "token_storage_mode": token_storage_mode,
    }

    if correlation_id:
        result["correlation_id"] = correlation_id

    return result


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """SageMaker Invoke Lambda ハンドラ

    Step Functions .waitForTaskToken から呼び出される。
    MOCK_MODE に応じて実際の SageMaker ジョブ起動またはモック処理を行う。
    TOKEN_STORAGE_MODE に応じて Task Token の受け渡し方式を切り替える。

    Input:
        {
            "task_token": "...",
            "input_s3_path": "s3://...",
            "point_count": N
        }

    Output:
        {
            "status": "COMPLETED" | "JOB_CREATED",
            "token_storage_mode": "dynamodb" | "direct",
            ...
        }
    """
    mock_mode = os.environ.get("MOCK_MODE", "false").lower() == "true"
    output_writer = OutputWriter.from_env()
    output_bucket = os.environ.get("OUTPUT_BUCKET", "")
    task_token = event.get("task_token", "")
    token_storage_mode = os.environ.get("TOKEN_STORAGE_MODE", "direct")

    # セキュリティ: task_token の値はログに出力しない
    logger.info(
        "SageMaker Invoke started: mock_mode=%s, token_storage_mode=%s, "
        "task_token_present=%s",
        mock_mode,
        token_storage_mode,
        bool(task_token),
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
        # DynamoDB モード固有メトリクス
        if token_storage_mode == "dynamodb":
            metrics.put_metric("DynamoDBTokenStores", 1.0, "Count")

    metrics.flush()
    return result
