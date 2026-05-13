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
from typing import Any

import boto3
import urllib3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Disable SSL warnings for ONTAP self-signed cert
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """ECS Task State Change イベントを処理し、ONTAP engine IP を更新する.

    トリガー条件:
    - ECS Task State Change (RUNNING)
    - 対象クラスター・サービスのタスクのみ
    """
    logger.info("Event received: %s", json.dumps(event, default=str))

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
