"""shared.lambdas.s3ap_external_monitor.handler — VPC-External S3AP Health Check

VPC 外で実行し、Internet-origin S3 Access Point の可用性を監視する Lambda ハンドラー。
Phase 12 で発見された VPC 内タイムアウト問題を回避するため、VpcConfig なしで実行する。

動作:
- S3 AP エイリアスに対して ListObjectsV2 を実行
- 成功時: CloudWatch メトリクス S3APHealthCheck = 1
- 失敗時: CloudWatch メトリクス S3APHealthCheck = 0 + エラーログ

ネットワーク制約:
- Internet-origin S3AP は VPC 内 Lambda (S3 Gateway Endpoint 経由) からタイムアウトする
- このため VpcConfig なし（VPC 外実行）が必須

参考:
- Phase 12 発見: VPC-internal Canary → S3AP timeout
- AWS Docs: https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/configuring-network-access-for-s3-access-points.html
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, ConnectTimeoutError, ReadTimeoutError

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# S3 クライアント（タイムアウト設定付き）
TIMEOUT_SECONDS = int(os.environ.get("TIMEOUT_SECONDS", "10"))
s3_config = Config(
    connect_timeout=TIMEOUT_SECONDS,
    read_timeout=TIMEOUT_SECONDS,
    retries={"max_attempts": 1},
)
s3 = boto3.client("s3", config=s3_config)
cloudwatch = boto3.client("cloudwatch")


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """S3 Access Point ヘルスチェックを実行する。

    Args:
        event: Lambda イベント（未使用、EventBridge Schedule から呼び出し）
        context: Lambda コンテキスト

    Returns:
        ヘルスチェック結果
    """
    s3ap_alias = os.environ.get("S3AP_ALIAS", "")
    health_prefix = os.environ.get("HEALTH_PREFIX", "_health/")
    metric_namespace = os.environ.get("METRIC_NAMESPACE", "FSxN-S3AP-Patterns/Canary")

    if not s3ap_alias:
        logger.error("S3AP_ALIAS environment variable is not set")
        _publish_metric(metric_namespace, s3ap_alias, 0)
        return {"healthy": False, "error": "S3AP_ALIAS not configured"}

    start_time = time.time()
    metric_value = 0
    error_message = ""

    try:
        response = s3.list_objects_v2(
            Bucket=s3ap_alias,
            Prefix=health_prefix,
            MaxKeys=1,
        )
        metric_value = 1
        latency_ms = int((time.time() - start_time) * 1000)
        logger.info(
            "S3AP health check passed: alias=%s, latency=%dms, objects=%d",
            s3ap_alias,
            latency_ms,
            response.get("KeyCount", 0),
        )

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_message = f"ClientError: {error_code} - {e.response['Error']['Message']}"
        logger.error("S3AP health check failed: %s", error_message)

    except ReadTimeoutError as e:
        error_message = f"ReadTimeoutError: {e}"
        logger.error("S3AP health check timed out (read): %s", error_message)

    except ConnectTimeoutError as e:
        error_message = f"ConnectTimeoutError: {e}"
        logger.error("S3AP health check timed out (connect): %s", error_message)

    except Exception as e:
        error_message = f"UnexpectedError: {type(e).__name__}: {e}"
        logger.error("S3AP health check unexpected error: %s", error_message)

    # Publish metric
    _publish_metric(metric_namespace, s3ap_alias, metric_value)

    result = {
        "healthy": metric_value == 1,
        "s3ap_alias": s3ap_alias,
        "metric_value": metric_value,
        "latency_ms": int((time.time() - start_time) * 1000),
    }
    if error_message:
        result["error"] = error_message

    return result


def _publish_metric(namespace: str, s3ap_alias: str, value: int) -> None:
    """CloudWatch カスタムメトリクスを発行する。

    Args:
        namespace: メトリクス名前空間
        s3ap_alias: S3AP エイリアス（Dimension 値）
        value: メトリクス値（1=healthy, 0=unhealthy）
    """
    try:
        cloudwatch.put_metric_data(
            Namespace=namespace,
            MetricData=[
                {
                    "MetricName": "S3APHealthCheck",
                    "Value": float(value),
                    "Unit": "None",
                    "Dimensions": [
                        {"Name": "S3APAlias", "Value": s3ap_alias or "unknown"},
                        {"Name": "CheckType", "Value": "VPC-External"},
                    ],
                }
            ],
        )
    except Exception as e:
        # メトリクス発行失敗は Lambda 自体の失敗にしない
        logger.warning("Failed to publish CloudWatch metric: %s", e)
