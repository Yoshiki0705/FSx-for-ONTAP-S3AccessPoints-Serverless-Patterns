"""Auto-Stop Lambda — アイドル SageMaker エンドポイントの自動スケールダウン

EventBridge Schedule（1 時間ごと）でトリガーされ、プロジェクトプレフィックスタグを持つ
SageMaker エンドポイントのアイドル状態を検出し、ゼロスケール（削除ではない）する。

環境変数:
- PROJECT_PREFIX: エンドポイントフィルタリング用タグプレフィックス (default: "fsxn-s3ap")
- IDLE_THRESHOLD_MINUTES: ゼロ呼び出しでアイドルと判定する分数 (default: 60)
- DRY_RUN: "true" の場合、アクションをログ出力のみで実行しない (default: "false")

設計方針:
- エンドポイントの削除は行わない（DesiredInstanceCount=0 によるスケールダウンのみ）
- DoNotAutoStop タグが "true" のエンドポイントはスキップ
- EMF メトリクス出力: EndpointsChecked, EndpointsStoppedCount, EstimatedSavingsPerHour
- DRY_RUN モード: 全アクションをログ出力するが実行しない

参照: Requirements 8.1–8.8
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Environment variables
PROJECT_PREFIX = os.environ.get("PROJECT_PREFIX", "fsxn-s3ap")
IDLE_THRESHOLD_MINUTES = int(os.environ.get("IDLE_THRESHOLD_MINUTES", "60"))
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"

# AWS clients
sagemaker_client = boto3.client("sagemaker")
cloudwatch_client = boto3.client("cloudwatch")

# Instance type hourly costs (approximate, us-east-1 pricing for reference)
INSTANCE_HOURLY_COSTS: dict[str, float] = {
    "ml.t2.medium": 0.065,
    "ml.t2.large": 0.130,
    "ml.m5.large": 0.134,
    "ml.m5.xlarge": 0.269,
    "ml.m5.2xlarge": 0.538,
    "ml.c5.large": 0.119,
    "ml.c5.xlarge": 0.238,
    "ml.c5.2xlarge": 0.476,
    "ml.g4dn.xlarge": 0.736,
    "ml.g4dn.2xlarge": 1.053,
    "ml.g5.xlarge": 1.408,
    "ml.g5.2xlarge": 1.672,
    "ml.p3.2xlarge": 4.284,
    "ml.inf1.xlarge": 0.362,
    "ml.inf2.xlarge": 0.758,
}


def handler(event: dict, context) -> dict:
    """Auto-Stop Lambda ハンドラー。

    EventBridge Schedule でトリガーされ、アイドルエンドポイントを検出・停止する。

    Args:
        event: EventBridge イベント
        context: Lambda コンテキスト

    Returns:
        dict: 処理結果サマリー
    """
    logger.info(
        "Auto-Stop Lambda started. PROJECT_PREFIX=%s, IDLE_THRESHOLD_MINUTES=%d, DRY_RUN=%s",
        PROJECT_PREFIX,
        IDLE_THRESHOLD_MINUTES,
        DRY_RUN,
    )

    endpoints = _list_project_endpoints()
    endpoints_checked = len(endpoints)
    endpoints_stopped = 0
    estimated_savings_per_hour = 0.0
    stop_actions: list[dict] = []

    for endpoint in endpoints:
        endpoint_name = endpoint["EndpointName"]

        # Check DoNotAutoStop tag
        if _has_do_not_auto_stop_tag(endpoint_name):
            logger.info("Skipping endpoint %s (DoNotAutoStop=true)", endpoint_name)
            continue

        # Check if endpoint is idle
        is_idle = _is_endpoint_idle(endpoint_name)
        if not is_idle:
            logger.info("Endpoint %s is active, skipping", endpoint_name)
            continue

        # Get endpoint details for cost estimation
        endpoint_details = _get_endpoint_details(endpoint_name)
        instance_type = endpoint_details.get("instance_type", "unknown")
        instance_count = endpoint_details.get("instance_count", 0)

        # Skip if already at minimum
        if instance_count == 0:
            logger.info("Endpoint %s already at zero instances, skipping", endpoint_name)
            continue

        # Calculate savings
        hourly_cost = INSTANCE_HOURLY_COSTS.get(instance_type, 0.0) * instance_count
        estimated_savings_per_hour += hourly_cost

        action_record = {
            "endpoint_name": endpoint_name,
            "idle_duration_minutes": IDLE_THRESHOLD_MINUTES,
            "instance_type": instance_type,
            "instance_count": instance_count,
            "estimated_hourly_savings": hourly_cost,
        }

        if DRY_RUN:
            logger.info(
                "[DRY_RUN] Would apply cost-saving action: endpoint=%s, instance_type=%s, "
                "instance_count=%d, estimated_hourly_savings=%.3f USD",
                endpoint_name,
                instance_type,
                instance_count,
                hourly_cost,
            )
        else:
            _scale_to_zero(endpoint_name)
            logger.info(
                "Applied cost-saving action: endpoint=%s, instance_type=%s, "
                "instance_count=%d, estimated_hourly_savings=%.3f USD",
                endpoint_name,
                instance_type,
                instance_count,
                hourly_cost,
            )
            endpoints_stopped += 1

        stop_actions.append(action_record)

    # Emit EMF metrics
    _emit_metrics(endpoints_checked, endpoints_stopped, estimated_savings_per_hour)

    result = {
        "endpoints_checked": endpoints_checked,
        "endpoints_stopped": endpoints_stopped,
        "estimated_savings_per_hour": estimated_savings_per_hour,
        "dry_run": DRY_RUN,
        "stop_actions": stop_actions,
    }

    logger.info("Auto-Stop Lambda completed: %s", result)
    return result


def _list_project_endpoints() -> list[dict]:
    """プロジェクトプレフィックスタグを持つ SageMaker エンドポイントを一覧取得する。

    Returns:
        list[dict]: エンドポイント情報のリスト
    """
    endpoints: list[dict] = []
    paginator = sagemaker_client.get_paginator("list_endpoints")

    for page in paginator.paginate(StatusEquals="InService"):
        for endpoint in page.get("Endpoints", []):
            endpoint_name = endpoint["EndpointName"]
            # Check if endpoint has project prefix tag
            try:
                tags_response = sagemaker_client.list_tags(
                    ResourceArn=_get_endpoint_arn(endpoint_name)
                )
                tags = {t["Key"]: t["Value"] for t in tags_response.get("Tags", [])}
                if tags.get("Project", "").startswith(PROJECT_PREFIX):
                    endpoints.append(endpoint)
            except Exception as e:
                logger.warning(
                    "Failed to get tags for endpoint %s: %s", endpoint_name, str(e)
                )

    return endpoints


def _has_do_not_auto_stop_tag(endpoint_name: str) -> bool:
    """DoNotAutoStop タグが "true" かどうかを確認する。

    Args:
        endpoint_name: エンドポイント名

    Returns:
        bool: DoNotAutoStop=true の場合 True
    """
    try:
        tags_response = sagemaker_client.list_tags(
            ResourceArn=_get_endpoint_arn(endpoint_name)
        )
        tags = {t["Key"]: t["Value"] for t in tags_response.get("Tags", [])}
        return tags.get("DoNotAutoStop", "false").lower() == "true"
    except Exception as e:
        logger.warning(
            "Failed to check DoNotAutoStop tag for %s: %s", endpoint_name, str(e)
        )
        return False


def _is_endpoint_idle(endpoint_name: str) -> bool:
    """エンドポイントがアイドル状態かどうかを CloudWatch メトリクスで判定する。

    InvocationsPerInstance メトリクスが IDLE_THRESHOLD_MINUTES 間ゼロの場合、
    アイドルと判定する。

    Args:
        endpoint_name: エンドポイント名

    Returns:
        bool: アイドルの場合 True
    """
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=IDLE_THRESHOLD_MINUTES)

    try:
        response = cloudwatch_client.get_metric_data(
            MetricDataQueries=[
                {
                    "Id": "invocations",
                    "MetricStat": {
                        "Metric": {
                            "Namespace": "AWS/SageMaker",
                            "MetricName": "InvocationsPerInstance",
                            "Dimensions": [
                                {
                                    "Name": "EndpointName",
                                    "Value": endpoint_name,
                                },
                                {
                                    "Name": "VariantName",
                                    "Value": "AllTraffic",
                                },
                            ],
                        },
                        "Period": 300,
                        "Stat": "Sum",
                    },
                    "ReturnData": True,
                }
            ],
            StartTime=start_time,
            EndTime=end_time,
        )

        # Check if all data points are zero or no data points exist
        results = response.get("MetricDataResults", [])
        if not results:
            return True

        values = results[0].get("Values", [])
        if not values:
            return True

        total_invocations = sum(values)
        return total_invocations == 0

    except Exception as e:
        logger.warning(
            "Failed to get metrics for endpoint %s: %s", endpoint_name, str(e)
        )
        # If we can't determine, don't stop the endpoint
        return False


def _get_endpoint_details(endpoint_name: str) -> dict:
    """エンドポイントの詳細情報（インスタンスタイプ、インスタンス数）を取得する。

    Args:
        endpoint_name: エンドポイント名

    Returns:
        dict: {"instance_type": str, "instance_count": int}
    """
    try:
        response = sagemaker_client.describe_endpoint(EndpointName=endpoint_name)
        endpoint_config_name = response.get("EndpointConfigName", "")

        config_response = sagemaker_client.describe_endpoint_config(
            EndpointConfigName=endpoint_config_name
        )
        variants = config_response.get("ProductionVariants", [])
        if variants:
            variant = variants[0]
            return {
                "instance_type": variant.get("InstanceType", "unknown"),
                "instance_count": variant.get("InitialInstanceCount", 0),
            }
    except Exception as e:
        logger.warning(
            "Failed to get endpoint details for %s: %s", endpoint_name, str(e)
        )

    return {"instance_type": "unknown", "instance_count": 0}


def _scale_to_zero(endpoint_name: str) -> None:
    """エンドポイントのコスト削減アクションを実行する。

    Inference Components を使用するエンドポイントの場合は DesiredInstanceCount=0 に
    スケールダウンする。標準エンドポイントの場合は MinCapacity=1 に設定するか、
    非本番環境ではエンドポイントを削除する。

    Note:
        SageMaker Real-time Endpoints (standard ProductionVariant) は
        DesiredInstanceCount=0 をサポートしない。Scale to zero は
        Inference Components を使用するエンドポイントでのみ可能。
        https://docs.aws.amazon.com/sagemaker/latest/dg/endpoint-auto-scaling-zero-instances.html

    Args:
        endpoint_name: エンドポイント名
    """
    auto_stop_action = os.environ.get("AUTO_STOP_ACTION", "scale_down")

    try:
        if auto_stop_action == "delete":
            # 非本番環境: エンドポイント削除（コスト完全停止）
            sagemaker_client.delete_endpoint(EndpointName=endpoint_name)
            logger.info("Deleted endpoint: %s", endpoint_name)
        else:
            # 本番環境: DesiredInstanceCount を最小値に設定
            # Note: DesiredInstanceCount=0 は Inference Components 使用時のみ有効
            # 標準エンドポイントでは MinCapacity=1 が最小値
            min_instance_count = int(os.environ.get("MIN_INSTANCE_COUNT", "1"))
            sagemaker_client.update_endpoint_weights_and_capacities(
                EndpointName=endpoint_name,
                DesiredWeightsAndCapacities=[
                    {
                        "VariantName": "AllTraffic",
                        "DesiredInstanceCount": min_instance_count,
                    }
                ],
            )
            logger.info(
                "Scaled endpoint %s to %d instance(s)",
                endpoint_name,
                min_instance_count,
            )
    except Exception as e:
        logger.error(
            "Failed to apply cost-saving action to endpoint %s: %s",
            endpoint_name,
            str(e),
        )
        raise


def _get_endpoint_arn(endpoint_name: str) -> str:
    """エンドポイント名から ARN を構築する。

    Args:
        endpoint_name: エンドポイント名

    Returns:
        str: エンドポイント ARN
    """
    region = os.environ.get("AWS_REGION", "ap-northeast-1")
    account_id = boto3.client("sts").get_caller_identity()["Account"]
    return f"arn:aws:sagemaker:{region}:{account_id}:endpoint/{endpoint_name}"


def _emit_metrics(
    endpoints_checked: int,
    endpoints_stopped: int,
    estimated_savings_per_hour: float,
) -> None:
    """EMF メトリクスを出力する。

    Args:
        endpoints_checked: チェックしたエンドポイント数
        endpoints_stopped: 停止したエンドポイント数
        estimated_savings_per_hour: 推定時間あたりコスト削減額 (USD)
    """
    import json

    timestamp_ms = int(time.time() * 1000)

    emf_dict = {
        "_aws": {
            "Timestamp": timestamp_ms,
            "CloudWatchMetrics": [
                {
                    "Namespace": "FSxN-S3AP-Patterns/AutoStop",
                    "Dimensions": [["FunctionName", "Environment"]],
                    "Metrics": [
                        {"Name": "EndpointsChecked", "Unit": "Count"},
                        {"Name": "EndpointsStoppedCount", "Unit": "Count"},
                        {"Name": "EstimatedSavingsPerHour", "Unit": "None"},
                    ],
                }
            ],
        },
        "FunctionName": os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "auto-stop"),
        "Environment": os.environ.get("ENVIRONMENT", "dev"),
        "EndpointsChecked": endpoints_checked,
        "EndpointsStoppedCount": endpoints_stopped,
        "EstimatedSavingsPerHour": estimated_savings_per_hour,
        "DryRun": DRY_RUN,
    }

    print(json.dumps(emf_dict))
