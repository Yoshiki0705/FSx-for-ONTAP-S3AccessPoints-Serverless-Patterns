"""Unit tests for shared/vpc_endpoint_sg_manager/handler.py.

Uses moto to mock EC2 security group operations.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

# Add shared directory to path
shared_dir = Path(__file__).parent.parent
sys.path.insert(0, str(shared_dir))

from vpc_endpoint_sg_manager.handler import (  # noqa: E402
    authorize_ingress,
    handler,
    revoke_ingress,
)

REGION = "ap-northeast-1"


@pytest.fixture
def aws_env(monkeypatch):
    """Set environment variables for tests."""
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")


@pytest.fixture
def vpc_and_sgs(aws_env):
    """Create a VPC with two security groups for testing."""
    with mock_aws():
        ec2 = boto3.client("ec2", region_name=REGION)
        vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")
        vpc_id = vpc["Vpc"]["VpcId"]

        vpce_sg = ec2.create_security_group(
            GroupName="vpce-sg", Description="VPC Endpoint SG", VpcId=vpc_id
        )
        lambda_sg = ec2.create_security_group(
            GroupName="lambda-sg", Description="Lambda SG", VpcId=vpc_id
        )

        yield {
            "ec2": ec2,
            "vpc_id": vpc_id,
            "vpce_sg_id": vpce_sg["GroupId"],
            "lambda_sg_id": lambda_sg["GroupId"],
        }


# ---------------------------------------------------------------------------
# Test: authorize_ingress
# ---------------------------------------------------------------------------


@mock_aws
def test_authorize_ingress_success(aws_env):
    """Successfully adds ingress rule."""
    ec2 = boto3.client("ec2", region_name=REGION)
    vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")
    vpc_id = vpc["Vpc"]["VpcId"]

    vpce_sg = ec2.create_security_group(
        GroupName="vpce-sg", Description="VPC Endpoint SG", VpcId=vpc_id
    )
    lambda_sg = ec2.create_security_group(
        GroupName="lambda-sg", Description="Lambda SG", VpcId=vpc_id
    )

    with patch("shared.vpc_endpoint_sg_manager.handler.ec2_client", ec2):
        authorize_ingress(vpce_sg["GroupId"], lambda_sg["GroupId"])

    # Verify rule was added
    sg_info = ec2.describe_security_groups(GroupIds=[vpce_sg["GroupId"]])
    ingress_rules = sg_info["SecurityGroups"][0]["IpPermissions"]
    assert len(ingress_rules) == 1
    assert ingress_rules[0]["FromPort"] == 443
    assert ingress_rules[0]["ToPort"] == 443
    assert ingress_rules[0]["UserIdGroupPairs"][0]["GroupId"] == lambda_sg["GroupId"]


@mock_aws
def test_authorize_ingress_duplicate_idempotent(aws_env):
    """Duplicate rule does not raise an error."""
    ec2 = boto3.client("ec2", region_name=REGION)
    vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")
    vpc_id = vpc["Vpc"]["VpcId"]

    vpce_sg = ec2.create_security_group(
        GroupName="vpce-sg", Description="VPC Endpoint SG", VpcId=vpc_id
    )
    lambda_sg = ec2.create_security_group(
        GroupName="lambda-sg", Description="Lambda SG", VpcId=vpc_id
    )

    with patch("shared.vpc_endpoint_sg_manager.handler.ec2_client", ec2):
        authorize_ingress(vpce_sg["GroupId"], lambda_sg["GroupId"])
        # Second call should not raise
        authorize_ingress(vpce_sg["GroupId"], lambda_sg["GroupId"])


# ---------------------------------------------------------------------------
# Test: revoke_ingress
# ---------------------------------------------------------------------------


@mock_aws
def test_revoke_ingress_success(aws_env):
    """Successfully removes ingress rule."""
    ec2 = boto3.client("ec2", region_name=REGION)
    vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")
    vpc_id = vpc["Vpc"]["VpcId"]

    vpce_sg = ec2.create_security_group(
        GroupName="vpce-sg", Description="VPC Endpoint SG", VpcId=vpc_id
    )
    lambda_sg = ec2.create_security_group(
        GroupName="lambda-sg", Description="Lambda SG", VpcId=vpc_id
    )

    # Add rule first
    ec2.authorize_security_group_ingress(
        GroupId=vpce_sg["GroupId"],
        IpPermissions=[
            {
                "IpProtocol": "tcp",
                "FromPort": 443,
                "ToPort": 443,
                "UserIdGroupPairs": [{"GroupId": lambda_sg["GroupId"]}],
            }
        ],
    )

    with patch("shared.vpc_endpoint_sg_manager.handler.ec2_client", ec2):
        revoke_ingress(vpce_sg["GroupId"], lambda_sg["GroupId"])

    # Verify rule was removed
    sg_info = ec2.describe_security_groups(GroupIds=[vpce_sg["GroupId"]])
    ingress_rules = sg_info["SecurityGroups"][0]["IpPermissions"]
    assert len(ingress_rules) == 0


@mock_aws
def test_revoke_ingress_not_found_idempotent(aws_env):
    """Revoking non-existent rule does not raise an error."""
    ec2 = boto3.client("ec2", region_name=REGION)
    vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")
    vpc_id = vpc["Vpc"]["VpcId"]

    vpce_sg = ec2.create_security_group(
        GroupName="vpce-sg", Description="VPC Endpoint SG", VpcId=vpc_id
    )
    lambda_sg = ec2.create_security_group(
        GroupName="lambda-sg", Description="Lambda SG", VpcId=vpc_id
    )

    with patch("shared.vpc_endpoint_sg_manager.handler.ec2_client", ec2):
        # Should not raise even though rule doesn't exist
        revoke_ingress(vpce_sg["GroupId"], lambda_sg["GroupId"])


# ---------------------------------------------------------------------------
# Test: handler (CloudFormation Custom Resource)
# ---------------------------------------------------------------------------


def _make_cfn_event(request_type: str, vpce_sg_id: str, lambda_sg_id: str, old_lambda_sg_id: str = "") -> dict:
    """Create a mock CloudFormation Custom Resource event."""
    event = {
        "RequestType": request_type,
        "ResponseURL": "https://cloudformation-custom-resource-response.s3.amazonaws.com/test",
        "StackId": "arn:aws:cloudformation:ap-northeast-1:123456789012:stack/test/guid",
        "RequestId": "unique-id-1234",
        "LogicalResourceId": "VpcEndpointSgRule",
        "ResourceProperties": {
            "VpcEndpointSecurityGroupId": vpce_sg_id,
            "LambdaSecurityGroupId": lambda_sg_id,
        },
    }
    if request_type == "Update" and old_lambda_sg_id:
        event["OldResourceProperties"] = {
            "VpcEndpointSecurityGroupId": vpce_sg_id,
            "LambdaSecurityGroupId": old_lambda_sg_id,
        }
    if request_type in ("Update", "Delete"):
        event["PhysicalResourceId"] = f"vpce-sg-rule-{old_lambda_sg_id or lambda_sg_id}"
    return event


@mock_aws
def test_handler_create(aws_env):
    """Handler Create event authorizes ingress."""
    ec2 = boto3.client("ec2", region_name=REGION)
    vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")
    vpc_id = vpc["Vpc"]["VpcId"]

    vpce_sg = ec2.create_security_group(
        GroupName="vpce-sg", Description="VPC Endpoint SG", VpcId=vpc_id
    )
    lambda_sg = ec2.create_security_group(
        GroupName="lambda-sg", Description="Lambda SG", VpcId=vpc_id
    )

    event = _make_cfn_event("Create", vpce_sg["GroupId"], lambda_sg["GroupId"])
    context = MagicMock()
    context.log_stream_name = "test-log-stream"

    with patch("shared.vpc_endpoint_sg_manager.handler.ec2_client", ec2):
        with patch("shared.vpc_endpoint_sg_manager.handler.urllib.request.urlopen") as mock_urlopen:
            handler(event, context)

    # Verify send_response was called with SUCCESS
    mock_urlopen.assert_called_once()
    sent_body = json.loads(mock_urlopen.call_args[0][0].data.decode())
    assert sent_body["Status"] == "SUCCESS"
    assert f"vpce-sg-rule-{lambda_sg['GroupId']}" == sent_body["PhysicalResourceId"]


@mock_aws
def test_handler_delete(aws_env):
    """Handler Delete event revokes ingress."""
    ec2 = boto3.client("ec2", region_name=REGION)
    vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")
    vpc_id = vpc["Vpc"]["VpcId"]

    vpce_sg = ec2.create_security_group(
        GroupName="vpce-sg", Description="VPC Endpoint SG", VpcId=vpc_id
    )
    lambda_sg = ec2.create_security_group(
        GroupName="lambda-sg", Description="Lambda SG", VpcId=vpc_id
    )

    # Add rule first
    ec2.authorize_security_group_ingress(
        GroupId=vpce_sg["GroupId"],
        IpPermissions=[
            {
                "IpProtocol": "tcp",
                "FromPort": 443,
                "ToPort": 443,
                "UserIdGroupPairs": [{"GroupId": lambda_sg["GroupId"]}],
            }
        ],
    )

    event = _make_cfn_event("Delete", vpce_sg["GroupId"], lambda_sg["GroupId"])
    context = MagicMock()
    context.log_stream_name = "test-log-stream"

    with patch("shared.vpc_endpoint_sg_manager.handler.ec2_client", ec2):
        with patch("shared.vpc_endpoint_sg_manager.handler.urllib.request.urlopen") as mock_urlopen:
            handler(event, context)

    mock_urlopen.assert_called_once()
    sent_body = json.loads(mock_urlopen.call_args[0][0].data.decode())
    assert sent_body["Status"] == "SUCCESS"

    # Verify rule was removed
    sg_info = ec2.describe_security_groups(GroupIds=[vpce_sg["GroupId"]])
    assert len(sg_info["SecurityGroups"][0]["IpPermissions"]) == 0


@mock_aws
def test_handler_update_sg_changed(aws_env):
    """Handler Update event revokes old rule and authorizes new one."""
    ec2 = boto3.client("ec2", region_name=REGION)
    vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")
    vpc_id = vpc["Vpc"]["VpcId"]

    vpce_sg = ec2.create_security_group(
        GroupName="vpce-sg", Description="VPC Endpoint SG", VpcId=vpc_id
    )
    old_lambda_sg = ec2.create_security_group(
        GroupName="old-lambda-sg", Description="Old Lambda SG", VpcId=vpc_id
    )
    new_lambda_sg = ec2.create_security_group(
        GroupName="new-lambda-sg", Description="New Lambda SG", VpcId=vpc_id
    )

    # Add old rule
    ec2.authorize_security_group_ingress(
        GroupId=vpce_sg["GroupId"],
        IpPermissions=[
            {
                "IpProtocol": "tcp",
                "FromPort": 443,
                "ToPort": 443,
                "UserIdGroupPairs": [{"GroupId": old_lambda_sg["GroupId"]}],
            }
        ],
    )

    event = _make_cfn_event(
        "Update",
        vpce_sg["GroupId"],
        new_lambda_sg["GroupId"],
        old_lambda_sg_id=old_lambda_sg["GroupId"],
    )
    context = MagicMock()
    context.log_stream_name = "test-log-stream"

    with patch("shared.vpc_endpoint_sg_manager.handler.ec2_client", ec2):
        with patch("shared.vpc_endpoint_sg_manager.handler.urllib.request.urlopen") as mock_urlopen:
            handler(event, context)

    mock_urlopen.assert_called_once()
    sent_body = json.loads(mock_urlopen.call_args[0][0].data.decode())
    assert sent_body["Status"] == "SUCCESS"

    # Verify old rule removed, new rule added
    sg_info = ec2.describe_security_groups(GroupIds=[vpce_sg["GroupId"]])
    ingress = sg_info["SecurityGroups"][0]["IpPermissions"]
    assert len(ingress) == 1
    assert ingress[0]["UserIdGroupPairs"][0]["GroupId"] == new_lambda_sg["GroupId"]


@mock_aws
def test_handler_error_sends_failed(aws_env):
    """Handler sends FAILED on unexpected error."""
    event = _make_cfn_event("Create", "sg-nonexistent", "sg-also-nonexistent")
    context = MagicMock()
    context.log_stream_name = "test-log-stream"

    # Use a mock ec2 that raises an unexpected error
    mock_ec2 = MagicMock()
    mock_ec2.authorize_security_group_ingress.side_effect = ClientError(
        {"Error": {"Code": "InvalidGroup.NotFound", "Message": "SG not found"}},
        "AuthorizeSecurityGroupIngress",
    )

    with patch("shared.vpc_endpoint_sg_manager.handler.ec2_client", mock_ec2):
        with patch("shared.vpc_endpoint_sg_manager.handler.urllib.request.urlopen") as mock_urlopen:
            handler(event, context)

    mock_urlopen.assert_called_once()
    sent_body = json.loads(mock_urlopen.call_args[0][0].data.decode())
    assert sent_body["Status"] == "FAILED"
