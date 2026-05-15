"""FPolicy Engine IP Updater — ECS タスク IP 変更時に ONTAP external-engine を自動更新.

EventBridge ECS Task State Change イベントをトリガーとして、
新しい Fargate タスクの Private IP を ONTAP FPolicy external-engine に反映する。

Environment Variables:
    FSXN_MGMT_IP: FSxN SVM 管理 IP (e.g., 10.0.3.72)
    FSXN_SVM_UUID: FSxN SVM UUID
    FSXN_ENGINE_NAME: FPolicy external-engine 名 (default: fpolicy_aws_engine)
    FSXN_POLICY_NAME: FPolicy ポリシー名 (default: fpolicy_aws)
    FSXN_CREDENTIALS_SECRET: Secrets Manager シークレット名
    ECS_CLUSTER_NAME: 監視対象 ECS クラスター名
    ECS_SERVICE_NAME: 監視対象 ECS サービス名
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import boto3
import urllib3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Disable SSL warnings for ONTAP self-signed cert
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# --- Schema Validation (used by tests and SQS ingestion) ---

class SchemaValidationError(Exception):
    """Raised when an FPolicy event fails schema validation."""

    def __init__(self, message: str, errors: list | None = None):
        super().__init__(message)
        self.errors = errors or [message]


class SqsIngestionError(Exception):
    """Raised when SQS message send fails after retries."""
    pass


def validate_fpolicy_event(event: dict[str, Any], schema: dict | None = None) -> bool:
    """Validate an FPolicy event against the JSON schema.

    Args:
        event: FPolicy event dict to validate.
        schema: Optional JSON schema dict. If None, loads from default path.

    Returns:
        True if valid.

    Raises:
        SchemaValidationError: If validation fails.
    """
    import jsonschema

    if schema is None:
        schema_path = os.environ.get(
            "SCHEMA_PATH",
            str(Path(__file__).parent.parent.parent / "schemas" / "fpolicy-event-schema.json"),
        )
        with open(schema_path) as f:
            schema = json.load(f)

    try:
        jsonschema.validate(instance=event, schema=schema)
        return True
    except jsonschema.ValidationError as e:
        raise SchemaValidationError(
            f"Schema validation failed: {e.message}",
            errors=[e.message],
        ) from e


def send_to_sqs_with_retry(
    queue_url: str,
    message_body: str,
    max_retries: int = 3,
    region: str = "ap-northeast-1",
    base_delay: float = 1.0,
    sqs_client: Any = None,
) -> str:
    """Send a message to SQS with exponential backoff retry.

    Args:
        queue_url: SQS queue URL.
        message_body: JSON string to send.
        max_retries: Maximum retry attempts.
        region: AWS region.
        base_delay: Base delay between retries (seconds).
        sqs_client: Optional pre-configured SQS client.

    Returns:
        SQS MessageId string.

    Raises:
        SqsIngestionError: If all retries fail.
    """
    if sqs_client is None:
        sqs_client = boto3.client("sqs", region_name=region)
    last_error = None

    for attempt in range(max_retries):
        try:
            response = sqs_client.send_message(
                QueueUrl=queue_url,
                MessageBody=message_body,
            )
            return response["MessageId"]
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(base_delay * (2 ** attempt))

    raise SqsIngestionError(
        f"All {max_retries} SQS send attempts failed: {last_error}"
    )


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """ECS Task State Change イベントを処理し、ONTAP engine IP を更新する.

    トリガー条件:
    - ECS Task State Change (RUNNING)
    - 対象クラスター・サービスのタスクのみ

    拡張機能:
    - action: "ontap_api" — 汎用 ONTAP REST API 呼び出し
    - action: "get_status" — ステータス確認
    """
    logger.info("Event received: %s", json.dumps(event, default=str))

    # --- Extension: Generic ONTAP API access ---
    action = event.get("action", "")

    if action == "get_status":
        return {"statusCode": 200, "body": "IP Updater Lambda is running"}

    if action == "ontap_api":
        return _handle_ontap_api(event)

    # --- Original: ECS Task State Change handling ---
    # Extract task details from event
    detail = event.get("detail", {})
    last_status = detail.get("lastStatus", "")
    desired_status = detail.get("desiredStatus", "")
    cluster_arn = detail.get("clusterArn", "")
    group = detail.get("group", "")  # "service:<service-name>"

    # Only process RUNNING tasks
    if last_status != "RUNNING" or desired_status != "RUNNING":
        logger.info("Skipping: lastStatus=%s, desiredStatus=%s", last_status, desired_status)
        return {"statusCode": 200, "body": "Skipped: not a RUNNING task"}

    # Verify cluster and service match
    expected_cluster = os.environ.get("ECS_CLUSTER_NAME", "")
    expected_service = os.environ.get("ECS_SERVICE_NAME", "")

    if expected_cluster and expected_cluster not in cluster_arn:
        logger.info("Skipping: cluster %s doesn't match %s", cluster_arn, expected_cluster)
        return {"statusCode": 200, "body": "Skipped: wrong cluster"}

    if expected_service and f"service:{expected_service}" != group:
        logger.info("Skipping: group %s doesn't match service:%s", group, expected_service)
        return {"statusCode": 200, "body": "Skipped: wrong service"}

    # Extract task private IP from attachments
    attachments = detail.get("attachments", [])
    task_ip = None
    for attachment in attachments:
        if attachment.get("type") == "ElasticNetworkInterface":
            for kv in attachment.get("details", []):
                if kv.get("name") == "privateIPv4Address":
                    task_ip = kv.get("value")
                    break
        if task_ip:
            break

    if not task_ip:
        logger.error("Could not extract task IP from event")
        return {"statusCode": 500, "body": "Failed: no task IP found"}

    logger.info("New task IP: %s", task_ip)

    # Get ONTAP credentials from Secrets Manager
    secret_name = os.environ["FSXN_CREDENTIALS_SECRET"]
    sm_client = boto3.client("secretsmanager")
    secret_value = sm_client.get_secret_value(SecretId=secret_name)
    creds = json.loads(secret_value["SecretString"])
    username = creds["username"]
    password = creds["password"]

    # Update ONTAP FPolicy external-engine
    mgmt_ip = os.environ["FSXN_MGMT_IP"]
    svm_uuid = os.environ["FSXN_SVM_UUID"]
    engine_name = os.environ.get("FSXN_ENGINE_NAME", "fpolicy_aws_engine")
    policy_name = os.environ.get("FSXN_POLICY_NAME", "fpolicy_aws")

    http = urllib3.PoolManager(cert_reqs="CERT_NONE")
    base_url = f"https://{mgmt_ip}/api/protocols/fpolicy/{svm_uuid}"
    headers = urllib3.make_headers(basic_auth=f"{username}:{password}")
    headers["Content-Type"] = "application/json"

    # Step 1: Disable policy
    logger.info("Disabling FPolicy policy: %s", policy_name)
    resp = http.request(
        "PATCH",
        f"{base_url}/policies/{policy_name}",
        headers=headers,
        body=json.dumps({"enabled": False}).encode(),
    )
    if resp.status not in (200, 202):
        logger.warning("Policy disable response: %d %s", resp.status, resp.data.decode())

    # Brief wait for policy to fully disable
    time.sleep(2)

    # Step 2: Update engine primary_servers
    logger.info("Updating engine %s primary_servers to %s", engine_name, task_ip)
    resp = http.request(
        "PATCH",
        f"{base_url}/engines/{engine_name}",
        headers=headers,
        body=json.dumps({"primary_servers": [task_ip]}).encode(),
    )
    if resp.status not in (200, 202):
        error_msg = resp.data.decode()
        logger.error("Engine update failed: %d %s", resp.status, error_msg)
        return {"statusCode": 500, "body": f"Engine update failed: {error_msg}"}

    # Step 3: Re-enable policy
    logger.info("Re-enabling FPolicy policy: %s", policy_name)
    resp = http.request(
        "PATCH",
        f"{base_url}/policies/{policy_name}",
        headers=headers,
        body=json.dumps({"enabled": True, "priority": 1}).encode(),
    )
    if resp.status not in (200, 202):
        logger.warning("Policy enable response: %d %s", resp.status, resp.data.decode())

    logger.info("Successfully updated ONTAP engine IP to %s", task_ip)
    return {
        "statusCode": 200,
        "body": f"Updated engine {engine_name} to {task_ip}",
    }


def _handle_ontap_api(event: dict[str, Any]) -> dict[str, Any]:
    """汎用 ONTAP REST API 呼び出しハンドラ.

    Persistent Store 設定やステータス確認に使用する。

    Event format:
        {
            "action": "ontap_api",
            "method": "GET" | "POST" | "PATCH" | "DELETE",
            "path": "/api/protocols/fpolicy/{svm_uuid}/persistent-stores",
            "body": {...}  // optional
        }
    """
    method = event.get("method", "GET").upper()
    api_path = event.get("path", "")
    api_body = event.get("body")

    if not api_path:
        return {"statusCode": 400, "body": "Missing 'path' in event"}

    # Get ONTAP credentials
    secret_name = os.environ["FSXN_CREDENTIALS_SECRET"]
    sm_client = boto3.client("secretsmanager")
    secret_value = sm_client.get_secret_value(SecretId=secret_name)
    creds = json.loads(secret_value["SecretString"])
    username = creds["username"]
    password = creds["password"]

    mgmt_ip = os.environ["FSXN_MGMT_IP"]
    url = f"https://{mgmt_ip}{api_path}"

    http = urllib3.PoolManager(cert_reqs="CERT_NONE")
    headers = urllib3.make_headers(basic_auth=f"{username}:{password}")
    headers["Content-Type"] = "application/json"

    body = json.dumps(api_body).encode() if api_body else None

    logger.info("[ONTAP API] %s %s", method, api_path)
    resp = http.request(method, url, headers=headers, body=body)

    try:
        resp_body = json.loads(resp.data.decode()) if resp.data else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        resp_body = resp.data.decode(errors="replace")

    logger.info("[ONTAP API] Response: %d", resp.status)
    return {
        "statusCode": resp.status,
        "body": resp_body,
    }
