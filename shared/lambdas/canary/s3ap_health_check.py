"""shared.lambdas.canary.s3ap_health_check — S3AP + ONTAP ヘルスチェック Canary

CloudWatch Synthetics Canary として S3 Access Point と ONTAP の
エンドツーエンドヘルスチェックを実行する。5 分間隔で自動実行。

チェック項目:
1. S3 Access Point への ListObjectsV2 実行とレイテンシ計測
2. S3 Access Point への GetObject 実行（ヘルスマーカーファイル）
3. ONTAP REST API /api/cluster ヘルスチェック

設計方針:
- fail-independent: 1 つのチェック失敗が他のチェックを妨げない
- 各チェック結果を CloudWatch カスタムメトリクスとして発行
- ONTAP 認証情報は Secrets Manager から取得（環境変数に格納しない）
- 実行結果にファイル内容等の機密データを含めない

Usage:
    # CloudWatch Synthetics が自動的に呼び出す
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from typing import Any

import boto3
import urllib3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Disable InsecureRequestWarning for ONTAP self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Environment variables
_S3AP_ALIAS = "S3AP_ALIAS"
_HEALTH_PREFIX = "HEALTH_PREFIX"
_HEALTH_KEY = "HEALTH_KEY"
_ONTAP_MANAGEMENT_IP = "ONTAP_MANAGEMENT_IP"
_ONTAP_SECRET_ARN = "ONTAP_SECRET_ARN"
_METRIC_NAMESPACE = "FSxN-S3AP-Patterns"


@dataclass
class CheckResult:
    """個別チェックの結果。"""

    name: str
    passed: bool
    latency_ms: float
    error: str | None = None


def handler(event: dict[str, Any] | None = None, context: Any = None) -> dict[str, Any]:
    """Canary handler for S3AP + ONTAP health checks.

    fail-independent 設計: 各チェックは独立して実行され、
    1 つの失敗が他のチェックを妨げない。

    Args:
        event: Canary イベント（通常は空）
        context: Lambda コンテキスト

    Returns:
        チェック結果の辞書:
            - status: "PASSED" | "FAILED"
            - checks: CheckResult のリスト（辞書形式）
    """
    bucket_alias = os.environ.get(_S3AP_ALIAS, "")
    health_prefix = os.environ.get(_HEALTH_PREFIX, "health/")
    health_key = os.environ.get(_HEALTH_KEY, "health/marker.txt")
    management_ip = os.environ.get(_ONTAP_MANAGEMENT_IP, "")

    checks: list[CheckResult] = []
    all_passed = True

    # Check 1: S3AP ListObjectsV2 (fail-independent)
    list_result = check_s3ap_list(bucket_alias, health_prefix)
    checks.append(list_result)
    if not list_result.passed:
        all_passed = False

    # Check 2: S3AP GetObject (fail-independent)
    get_result = check_s3ap_get(bucket_alias, health_key)
    checks.append(get_result)
    if not get_result.passed:
        all_passed = False

    # Check 3: ONTAP Health (fail-independent)
    ontap_result = check_ontap_health(management_ip)
    checks.append(ontap_result)
    if not ontap_result.passed:
        all_passed = False

    # Emit CloudWatch custom metrics for each check
    _emit_metrics(checks)

    return {
        "status": "PASSED" if all_passed else "FAILED",
        "checks": [asdict(c) for c in checks],
    }


def check_s3ap_list(bucket_alias: str, prefix: str) -> CheckResult:
    """S3 Access Point への ListObjectsV2 を実行しレイテンシを計測する。

    Args:
        bucket_alias: S3 Access Point のバケットエイリアス
        prefix: リスト対象のプレフィックス

    Returns:
        CheckResult: チェック結果（レイテンシ含む）
    """
    name = "S3AP_List"
    start = time.time()
    try:
        s3_client = boto3.client("s3")
        s3_client.list_objects_v2(
            Bucket=bucket_alias,
            Prefix=prefix,
            MaxKeys=1,
        )
        latency_ms = (time.time() - start) * 1000
        logger.info("S3AP ListObjectsV2 succeeded: latency=%.1fms", latency_ms)
        return CheckResult(name=name, passed=True, latency_ms=latency_ms)
    except Exception as e:
        latency_ms = (time.time() - start) * 1000
        error_msg = f"{type(e).__name__}: {e}"
        logger.error("S3AP ListObjectsV2 failed: %s", error_msg)
        return CheckResult(
            name=name, passed=False, latency_ms=latency_ms, error=error_msg
        )


def check_s3ap_get(bucket_alias: str, key: str) -> CheckResult:
    """S3 Access Point への GetObject を実行しレイテンシを計測する。

    ヘルスマーカーファイルを取得し、レスポンスのレイテンシを計測する。
    ファイル内容は結果に含めない（機密データ保護）。

    Args:
        bucket_alias: S3 Access Point のバケットエイリアス
        key: ヘルスマーカーファイルのキー

    Returns:
        CheckResult: チェック結果（レイテンシ含む）
    """
    name = "S3AP_Get"
    start = time.time()
    try:
        s3_client = boto3.client("s3")
        response = s3_client.get_object(Bucket=bucket_alias, Key=key)
        # Read and discard body to complete the request — do NOT include content in results
        response["Body"].read()
        response["Body"].close()
        latency_ms = (time.time() - start) * 1000
        logger.info("S3AP GetObject succeeded: latency=%.1fms", latency_ms)
        return CheckResult(name=name, passed=True, latency_ms=latency_ms)
    except Exception as e:
        latency_ms = (time.time() - start) * 1000
        error_msg = f"{type(e).__name__}: {e}"
        logger.error("S3AP GetObject failed: %s", error_msg)
        return CheckResult(
            name=name, passed=False, latency_ms=latency_ms, error=error_msg
        )


def check_ontap_health(management_ip: str) -> CheckResult:
    """ONTAP REST API /api/cluster ヘルスチェックを実行する。

    Secrets Manager から認証情報を取得し、ONTAP クラスタの
    ヘルスステータスを確認する。

    Args:
        management_ip: ONTAP 管理 IP アドレス

    Returns:
        CheckResult: チェック結果（レイテンシ含む）
    """
    name = "ONTAP_Health"
    start = time.time()
    try:
        # Retrieve ONTAP credentials from Secrets Manager
        secret_arn = os.environ.get(_ONTAP_SECRET_ARN, "")
        credentials = _get_ontap_credentials(secret_arn)
        username = credentials.get("username", "fsxadmin")
        password = credentials.get("password", "")

        # Call ONTAP REST API /api/cluster
        http = urllib3.PoolManager(cert_reqs="CERT_NONE")
        url = f"https://{management_ip}/api/cluster"
        headers = urllib3.make_headers(basic_auth=f"{username}:{password}")
        headers["Accept"] = "application/json"

        response = http.request(
            "GET",
            url,
            headers=headers,
            timeout=urllib3.Timeout(connect=5.0, read=10.0),
        )

        latency_ms = (time.time() - start) * 1000

        if response.status == 200:
            logger.info("ONTAP health check succeeded: latency=%.1fms", latency_ms)
            return CheckResult(name=name, passed=True, latency_ms=latency_ms)
        else:
            error_msg = f"HTTP {response.status}"
            logger.error("ONTAP health check failed: %s", error_msg)
            return CheckResult(
                name=name, passed=False, latency_ms=latency_ms, error=error_msg
            )
    except Exception as e:
        latency_ms = (time.time() - start) * 1000
        error_msg = f"{type(e).__name__}: {e}"
        logger.error("ONTAP health check failed: %s", error_msg)
        return CheckResult(
            name=name, passed=False, latency_ms=latency_ms, error=error_msg
        )


def _get_ontap_credentials(secret_arn: str) -> dict[str, str]:
    """Secrets Manager から ONTAP 認証情報を取得する。

    Args:
        secret_arn: Secrets Manager シークレットの ARN

    Returns:
        認証情報の辞書 {"username": ..., "password": ...}

    Note:
        認証情報はログに出力しない。
    """
    sm_client = boto3.client("secretsmanager")
    response = sm_client.get_secret_value(SecretId=secret_arn)
    secret_string = response["SecretString"]
    return json.loads(secret_string)


def _emit_metrics(checks: list[CheckResult]) -> None:
    """CloudWatch カスタムメトリクスを発行する。

    各チェックのレイテンシと成功/失敗を CloudWatch に送信する。

    Args:
        checks: チェック結果のリスト
    """
    cw_client = boto3.client("cloudwatch")
    metric_data = []

    for check in checks:
        # Latency metric
        metric_data.append(
            {
                "MetricName": f"{check.name}_Latency_ms",
                "Value": check.latency_ms,
                "Unit": "Milliseconds",
                "Dimensions": [
                    {"Name": "Service", "Value": "synthetic-canary"},
                    {"Name": "CheckName", "Value": check.name},
                ],
            }
        )
        # Success/Failure metric
        metric_data.append(
            {
                "MetricName": f"{check.name}_Success",
                "Value": 1.0 if check.passed else 0.0,
                "Unit": "Count",
                "Dimensions": [
                    {"Name": "Service", "Value": "synthetic-canary"},
                    {"Name": "CheckName", "Value": check.name},
                ],
            }
        )

    try:
        cw_client.put_metric_data(
            Namespace=_METRIC_NAMESPACE,
            MetricData=metric_data,
        )
        logger.info("CloudWatch metrics emitted for %d checks", len(checks))
    except Exception as e:
        logger.error("Failed to emit CloudWatch metrics: %s", e)
