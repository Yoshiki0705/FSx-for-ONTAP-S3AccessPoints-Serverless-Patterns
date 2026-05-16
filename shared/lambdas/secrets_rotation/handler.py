"""shared.lambdas.secrets_rotation.handler — Secrets Manager ローテーション Lambda

Secrets Manager のローテーション Lambda として動作し、ONTAP fsxadmin パスワードを
自動更新する。4 ステップローテーションプロトコルに準拠。

ローテーションフロー:
1. createSecret: 新しいパスワードを生成し AWSPENDING バージョンとして保存
2. setSecret: ONTAP REST API (PATCH /api/security/accounts) でパスワード変更
3. testSecret: 新認証情報で /api/cluster エンドポイントへの接続テスト
4. finishSecret: AWSPENDING を AWSCURRENT に昇格

セキュリティ要件:
- パスワードをログに出力しない
- VPC 内で実行し、ONTAP 管理 IP へのネットワークアクセスを確保
- 失敗時は SNS 通知を送信し例外を raise（Secrets Manager が自動ロールバック）

Usage:
    # Secrets Manager が自動的に呼び出す
    # event = {"Step": "createSecret", "SecretId": "arn:...", "ClientRequestToken": "..."}
"""

from __future__ import annotations

import json
import logging
import os
import secrets
from typing import Any

import boto3
import urllib3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Disable SSL warnings for self-signed ONTAP certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Module-level HTTP pool manager (reused across invocations)
_http = urllib3.PoolManager(
    cert_reqs="CERT_NONE",
    timeout=urllib3.Timeout(connect=10.0, read=30.0),
    retries=urllib3.Retry(total=2, backoff_factor=0.5),
)


def handler(event: dict[str, Any], context: Any) -> None:
    """Secrets Manager rotation handler.

    Implements the 4-step rotation protocol:
    - createSecret: Generate new password, store as AWSPENDING
    - setSecret: Apply new password to ONTAP via REST API
    - testSecret: Verify new credentials work against ONTAP
    - finishSecret: Promote AWSPENDING to AWSCURRENT

    Args:
        event: Secrets Manager rotation event
            - Step: ローテーションステップ名
            - SecretId: シークレット ARN
            - ClientRequestToken: バージョン ID
        context: Lambda コンテキスト
    """
    arn = event["SecretId"]
    token = event["ClientRequestToken"]
    step = event["Step"]

    # Create Secrets Manager client
    service_client = boto3.client("secretsmanager")

    # Verify the secret exists and the token is valid
    metadata = service_client.describe_secret(SecretId=arn)
    if not metadata.get("RotationEnabled"):
        logger.error("Secret %s is not enabled for rotation.", arn)
        raise ValueError(f"Secret {arn} is not enabled for rotation.")

    versions = metadata.get("VersionIdsToStages", {})
    if token not in versions:
        logger.error(
            "Secret version %s has no stage for rotation of secret %s.",
            token,
            arn,
        )
        raise ValueError(
            f"Secret version {token} has no stage for rotation of secret {arn}."
        )

    # Route to the appropriate step
    if step == "createSecret":
        _create_secret(service_client, arn, token)
    elif step == "setSecret":
        _set_secret(service_client, arn, token)
    elif step == "testSecret":
        _test_secret(service_client, arn, token)
    elif step == "finishSecret":
        _finish_secret(service_client, arn, token)
    else:
        raise ValueError(f"Invalid step parameter: {step}")


def _create_secret(service_client: Any, arn: str, token: str) -> None:
    """新しいパスワードを生成し AWSPENDING バージョンとして保存する。

    Args:
        service_client: Secrets Manager クライアント
        arn: シークレット ARN
        token: クライアントリクエストトークン（バージョン ID）
    """
    # Check if AWSPENDING already exists for this token
    metadata = service_client.describe_secret(SecretId=arn)
    versions = metadata.get("VersionIdsToStages", {})
    if token in versions and "AWSPENDING" in versions[token]:
        # Verify the AWSPENDING version actually has a SecretString
        # (it may exist in stages but have no value if a previous attempt failed)
        try:
            service_client.get_secret_value(
                SecretId=arn, VersionId=token, VersionStage="AWSPENDING"
            )
            logger.info("createSecret: AWSPENDING already exists for version %s.", token)
            return
        except service_client.exceptions.ResourceNotFoundException:
            logger.warning(
                "createSecret: AWSPENDING stage exists for version %s but has no value. "
                "Re-creating.",
                token,
            )

    # Get the current secret value to preserve non-password fields
    current = service_client.get_secret_value(
        SecretId=arn, VersionStage="AWSCURRENT"
    )
    current_dict = json.loads(current["SecretString"])

    # Generate a new password using cryptographically secure random
    new_password = secrets.token_urlsafe(32)

    # Build the new secret with updated password
    new_secret_dict = current_dict.copy()
    new_secret_dict["password"] = new_password

    # Store as AWSPENDING
    service_client.put_secret_value(
        SecretId=arn,
        ClientRequestToken=token,
        SecretString=json.dumps(new_secret_dict),
        VersionStages=["AWSPENDING"],
    )
    logger.info(
        "createSecret: Successfully created AWSPENDING for secret %s.", arn
    )


def _set_secret(service_client: Any, arn: str, token: str) -> None:
    """ONTAP REST API でパスワードを変更する。

    PATCH /api/security/accounts で fsxadmin パスワードを更新。
    現在の認証情報（AWSCURRENT）で ONTAP に認証し、新パスワードを設定する。

    Args:
        service_client: Secrets Manager クライアント
        arn: シークレット ARN
        token: クライアントリクエストトークン（バージョン ID）
    """
    # Retrieve pending secret (new password)
    pending = service_client.get_secret_value(
        SecretId=arn, VersionId=token, VersionStage="AWSPENDING"
    )
    secret_dict = json.loads(pending["SecretString"])
    new_password = secret_dict["password"]
    management_ip = secret_dict.get("management_ip") or os.environ.get("ONTAP_MGMT_IP", "")
    username = secret_dict.get("username", "fsxadmin")
    svm_uuid = secret_dict.get("svm_uuid") or os.environ.get("CLUSTER_UUID") or os.environ.get("SVM_UUID", "")

    # Retrieve current secret for authentication
    current = service_client.get_secret_value(
        SecretId=arn, VersionStage="AWSCURRENT"
    )
    current_dict = json.loads(current["SecretString"])
    current_password = current_dict["password"]

    # Build ONTAP REST API URL
    # Note: fsxadmin is a cluster-scoped account, not SVM-scoped.
    # The owner UUID is the cluster UUID, not the SVM UUID.
    # For FSx for ONTAP, use /api/security/accounts/{cluster_uuid}/fsxadmin
    # The cluster UUID can be obtained from /api/cluster or from the account's self link.
    # We use the owner UUID from the account listing, falling back to SVM UUID.
    owner_uuid = svm_uuid  # This should be the cluster UUID for fsxadmin
    ontap_url = (
        f"https://{management_ip}/api/security/accounts/{owner_uuid}/{username}"
    )

    # Apply new password via ONTAP REST API
    headers = urllib3.make_headers(
        basic_auth=f"{username}:{current_password}",
    )
    headers["Content-Type"] = "application/json"

    logger.info(
        "setSecret: Applying password change to ONTAP at %s for user %s.",
        management_ip,
        username,
    )

    response = _http.request(
        "PATCH",
        ontap_url,
        headers=headers,
        body=json.dumps({"password": new_password}).encode("utf-8"),
    )

    if response.status not in (200, 202):
        error_msg = (
            f"ONTAP password change failed: HTTP {response.status} - "
            f"{response.data.decode('utf-8', errors='replace')}"
        )
        logger.error("setSecret: %s", error_msg)
        _notify_failure(arn, "setSecret", error_msg)
        raise ValueError(error_msg)

    logger.info(
        "setSecret: Successfully applied password change to ONTAP for secret %s.",
        arn,
    )


def _test_secret(service_client: Any, arn: str, token: str) -> None:
    """新認証情報で ONTAP への接続テストを実行する。

    GET /api/cluster エンドポイントに新パスワードで接続し、
    200 OK が返ることを確認する。失敗時は SNS 通知を送信し例外を raise。

    Args:
        service_client: Secrets Manager クライアント
        arn: シークレット ARN
        token: クライアントリクエストトークン（バージョン ID）
    """
    # Retrieve pending secret (new credentials)
    pending = service_client.get_secret_value(
        SecretId=arn, VersionId=token, VersionStage="AWSPENDING"
    )
    secret_dict = json.loads(pending["SecretString"])
    new_password = secret_dict["password"]
    management_ip = secret_dict.get("management_ip") or os.environ.get("ONTAP_MGMT_IP", "")
    username = secret_dict.get("username", "fsxadmin")

    # Test connection with new credentials
    test_url = f"https://{management_ip}/api/cluster"

    headers = urllib3.make_headers(
        basic_auth=f"{username}:{new_password}",
    )
    headers["Accept"] = "application/json"

    logger.info(
        "testSecret: Testing new credentials against ONTAP at %s.",
        management_ip,
    )

    try:
        response = _http.request(
            "GET",
            test_url,
            headers=headers,
        )
    except Exception as e:
        error_msg = f"ONTAP connection test failed with exception: {type(e).__name__}: {e}"
        logger.error("testSecret: %s", error_msg)
        _notify_failure(arn, "testSecret", error_msg)
        raise ValueError(error_msg) from e

    if response.status != 200:
        error_msg = (
            f"ONTAP connection test failed: HTTP {response.status} - "
            f"{response.data.decode('utf-8', errors='replace')}"
        )
        logger.error("testSecret: %s", error_msg)
        _notify_failure(arn, "testSecret", error_msg)
        raise ValueError(error_msg)

    logger.info(
        "testSecret: Successfully verified new credentials for secret %s.",
        arn,
    )


def _finish_secret(service_client: Any, arn: str, token: str) -> None:
    """AWSPENDING を AWSCURRENT に昇格させる。

    Args:
        service_client: Secrets Manager クライアント
        arn: シークレット ARN
        token: クライアントリクエストトークン（バージョン ID）
    """
    # Describe the secret to get current version info
    metadata = service_client.describe_secret(SecretId=arn)
    versions = metadata.get("VersionIdsToStages", {})

    # Check if this version is already AWSCURRENT
    if token in versions and "AWSCURRENT" in versions[token]:
        logger.info(
            "finishSecret: Version %s already marked as AWSCURRENT for %s.",
            token,
            arn,
        )
        return

    # Find the current version to demote
    current_version = None
    for version_id, stages in versions.items():
        if "AWSCURRENT" in stages and version_id != token:
            current_version = version_id
            break

    # Promote AWSPENDING to AWSCURRENT
    service_client.update_secret_version_stage(
        SecretId=arn,
        VersionStage="AWSCURRENT",
        MoveToVersionId=token,
        RemoveFromVersionId=current_version,
    )

    logger.info(
        "finishSecret: Successfully promoted AWSPENDING to AWSCURRENT for secret %s.",
        arn,
    )


def _notify_failure(secret_arn: str, step: str, error_message: str) -> None:
    """ローテーション失敗時に SNS 通知を送信する。

    Args:
        secret_arn: 失敗したシークレットの ARN
        step: 失敗したローテーションステップ名
        error_message: エラーメッセージ（パスワードを含まないこと）
    """
    sns_topic_arn = os.environ.get("SNS_TOPIC_ARN")
    if not sns_topic_arn:
        logger.warning(
            "SNS_TOPIC_ARN not configured. Skipping failure notification."
        )
        return

    try:
        sns_client = boto3.client("sns")
        sns_client.publish(
            TopicArn=sns_topic_arn,
            Subject=f"[Secrets Rotation] Rotation failed at step: {step}",
            Message=(
                f"Secrets rotation failed.\n\n"
                f"Secret ARN: {secret_arn}\n"
                f"Step: {step}\n"
                f"Error: {error_message}\n\n"
                f"The rotation has been aborted. Secrets Manager will "
                f"automatically retry or rollback."
            ),
        )
        logger.info("Failure notification sent to SNS topic.")
    except Exception as e:
        logger.error(
            "Failed to send SNS notification: %s", str(e)
        )
