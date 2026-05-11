"""CloudFormation Custom Resource handler for VPC Endpoint SG management.

Automatically manages ingress rules on a shared VPC Endpoint Security Group
during stack lifecycle events (Create/Update/Delete).

This handler:
- On Create: Authorizes TCP 443 ingress from Lambda SG to VPC Endpoint SG
- On Update: Revokes old rule (if Lambda SG changed), authorizes new rule
- On Delete: Revokes the ingress rule

All operations are idempotent — duplicate rules and missing rules are handled gracefully.
"""
from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

ec2_client = boto3.client("ec2")


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------


def authorize_ingress(vpc_endpoint_sg_id: str, lambda_sg_id: str) -> None:
    """Add ingress rule allowing Lambda SG → VPC Endpoint SG on TCP 443.

    Idempotent: catches InvalidPermission.Duplicate.
    """
    try:
        ec2_client.authorize_security_group_ingress(
            GroupId=vpc_endpoint_sg_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 443,
                    "ToPort": 443,
                    "UserIdGroupPairs": [
                        {
                            "GroupId": lambda_sg_id,
                            "Description": "Allow HTTPS from Lambda SG (managed by fsxn-s3ap-patterns)",
                        }
                    ],
                }
            ],
        )
        logger.info(
            f"Authorized ingress: {vpc_endpoint_sg_id} ← {lambda_sg_id} (TCP 443)"
        )
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "InvalidPermission.Duplicate":
            logger.info(
                f"Rule already exists: {vpc_endpoint_sg_id} ← {lambda_sg_id} (idempotent)"
            )
        else:
            raise


def revoke_ingress(vpc_endpoint_sg_id: str, lambda_sg_id: str) -> None:
    """Remove ingress rule for Lambda SG from VPC Endpoint SG.

    Idempotent: catches InvalidPermission.NotFound.
    """
    try:
        ec2_client.revoke_security_group_ingress(
            GroupId=vpc_endpoint_sg_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 443,
                    "ToPort": 443,
                    "UserIdGroupPairs": [{"GroupId": lambda_sg_id}],
                }
            ],
        )
        logger.info(
            f"Revoked ingress: {vpc_endpoint_sg_id} ← {lambda_sg_id} (TCP 443)"
        )
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "InvalidPermission.NotFound":
            logger.info(
                f"Rule not found: {vpc_endpoint_sg_id} ← {lambda_sg_id} (already removed)"
            )
        else:
            raise


# ---------------------------------------------------------------------------
# CloudFormation Custom Resource handler
# ---------------------------------------------------------------------------


def handler(event: dict[str, Any], context: Any) -> None:
    """CloudFormation Custom Resource handler.

    ResourceProperties:
        VpcEndpointSecurityGroupId: str — Target VPC Endpoint SG
        LambdaSecurityGroupId: str — Source Lambda SG
    """
    logger.info(f"Event: {json.dumps(event)}")

    request_type = event["RequestType"]
    props = event["ResourceProperties"]
    physical_resource_id = event.get(
        "PhysicalResourceId", f"vpce-sg-rule-{props.get('LambdaSecurityGroupId', 'unknown')}"
    )

    try:
        vpc_endpoint_sg_id = props["VpcEndpointSecurityGroupId"]
        lambda_sg_id = props["LambdaSecurityGroupId"]

        if request_type == "Create":
            authorize_ingress(vpc_endpoint_sg_id, lambda_sg_id)
            physical_resource_id = f"vpce-sg-rule-{lambda_sg_id}"

        elif request_type == "Update":
            old_props = event.get("OldResourceProperties", {})
            old_lambda_sg = old_props.get("LambdaSecurityGroupId")
            if old_lambda_sg and old_lambda_sg != lambda_sg_id:
                revoke_ingress(vpc_endpoint_sg_id, old_lambda_sg)
            authorize_ingress(vpc_endpoint_sg_id, lambda_sg_id)
            physical_resource_id = f"vpce-sg-rule-{lambda_sg_id}"

        elif request_type == "Delete":
            revoke_ingress(vpc_endpoint_sg_id, lambda_sg_id)

        send_response(event, context, "SUCCESS", physical_resource_id)

    except Exception as e:
        logger.error(f"Error handling {request_type}: {e}")
        send_response(
            event, context, "FAILED", physical_resource_id, reason=str(e)
        )


# ---------------------------------------------------------------------------
# CloudFormation response helper
# ---------------------------------------------------------------------------


def send_response(
    event: dict[str, Any],
    context: Any,
    status: str,
    physical_resource_id: str,
    reason: str = "",
) -> None:
    """Send response to CloudFormation via pre-signed S3 URL."""
    response_body = {
        "Status": status,
        "Reason": reason or f"See CloudWatch Log Stream: {getattr(context, 'log_stream_name', 'N/A')}",
        "PhysicalResourceId": physical_resource_id,
        "StackId": event["StackId"],
        "RequestId": event["RequestId"],
        "LogicalResourceId": event["LogicalResourceId"],
        "Data": {},
    }

    response_url = event["ResponseURL"]
    body = json.dumps(response_body).encode("utf-8")

    req = urllib.request.Request(
        response_url,
        data=body,
        headers={"Content-Type": "", "Content-Length": str(len(body))},
        method="PUT",
    )

    try:
        urllib.request.urlopen(req)
        logger.info(f"Response sent: {status}")
    except Exception as e:
        logger.error(f"Failed to send response: {e}")
