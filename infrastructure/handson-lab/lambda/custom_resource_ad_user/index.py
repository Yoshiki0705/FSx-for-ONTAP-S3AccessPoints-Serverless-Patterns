"""CloudFormation Custom Resource — AD User Creation.

Creates a user in AWS Managed Microsoft AD using the Directory Service API.
Handles Create, Update, and Delete lifecycle events.

Environment Variables:
    DIRECTORY_ID: AWS Managed AD Directory ID
    DOMAIN_NAME: AD domain FQDN (for logging)
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ds_client = boto3.client("ds")
sm_client = boto3.client("secretsmanager")


def handler(event: dict[str, Any], context: Any) -> None:
    """CloudFormation Custom Resource handler."""
    logger.info("Event: %s", json.dumps(event, default=str))

    request_type = event["RequestType"]
    properties = event["ResourceProperties"]

    try:
        if request_type == "Create":
            physical_id, data = create_user(properties)
        elif request_type == "Update":
            physical_id, data = update_user(event, properties)
        elif request_type == "Delete":
            physical_id, data = delete_user(event, properties)
        else:
            raise ValueError(f"Unknown RequestType: {request_type}")

        send_response(event, context, "SUCCESS", data, physical_id)

    except Exception as e:
        logger.exception("Failed to handle %s", request_type)
        physical_id = event.get("PhysicalResourceId", "NONE")
        send_response(
            event, context, "FAILED",
            {"Error": str(e)},
            physical_id,
        )


def create_user(properties: dict[str, Any]) -> tuple[str, dict[str, str]]:
    """Create an AD user in AWS Managed AD."""
    directory_id = properties["DirectoryId"]
    username = properties["UserName"]
    password_secret_arn = properties["UserPasswordSecretArn"]
    domain_name = properties.get("DomainName", os.environ.get("DOMAIN_NAME", ""))

    # Retrieve password from Secrets Manager
    password = get_secret_value(password_secret_arn)

    logger.info(
        "Creating AD user: %s in directory %s (domain: %s)",
        username, directory_id, domain_name,
    )

    try:
        ds_client.create_user(
            DirectoryId=directory_id,
            UserName=username,
            Password=password,
            DisplayName=f"Hands-on User {username}",
            Description="Hands-on lab participant user",
        )
        logger.info("User %s created successfully", username)
    except ClientError as e:
        if e.response["Error"]["Code"] == "EntityAlreadyExistsException":
            logger.info("User %s already exists, resetting password", username)
            ds_client.reset_user_password(
                DirectoryId=directory_id,
                UserName=username,
                NewPassword=password,
            )
        else:
            raise

    physical_id = f"{directory_id}/{username}"
    return physical_id, {
        "UserName": username,
        "DirectoryId": directory_id,
        "DomainUser": f"{domain_name}\\{username}" if domain_name else username,
    }


def update_user(
    event: dict[str, Any], properties: dict[str, Any]
) -> tuple[str, dict[str, str]]:
    """Update AD user (reset password if changed)."""
    directory_id = properties["DirectoryId"]
    username = properties["UserName"]
    password_secret_arn = properties["UserPasswordSecretArn"]
    domain_name = properties.get("DomainName", os.environ.get("DOMAIN_NAME", ""))

    old_properties = event.get("OldResourceProperties", {})
    old_username = old_properties.get("UserName", "")

    # If username changed, create new user (CloudFormation replacement)
    if old_username and old_username != username:
        logger.info("Username changed from %s to %s, creating new user", old_username, username)
        return create_user(properties)

    # Otherwise, reset password
    password = get_secret_value(password_secret_arn)
    logger.info("Resetting password for user %s", username)

    try:
        ds_client.reset_user_password(
            DirectoryId=directory_id,
            UserName=username,
            NewPassword=password,
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "EntityDoesNotExistException":
            logger.info("User %s does not exist, creating", username)
            return create_user(properties)
        raise

    physical_id = event["PhysicalResourceId"]
    return physical_id, {
        "UserName": username,
        "DirectoryId": directory_id,
        "DomainUser": f"{domain_name}\\{username}" if domain_name else username,
    }


def delete_user(
    event: dict[str, Any], properties: dict[str, Any]
) -> tuple[str, dict[str, str]]:
    """Delete AD user from AWS Managed AD."""
    directory_id = properties["DirectoryId"]
    username = properties["UserName"]

    logger.info("Deleting AD user: %s from directory %s", username, directory_id)

    try:
        ds_client.delete_user(
            DirectoryId=directory_id,
            UserName=username,
        )
        logger.info("User %s deleted successfully", username)
    except ClientError as e:
        if e.response["Error"]["Code"] == "EntityDoesNotExistException":
            logger.info("User %s does not exist, nothing to delete", username)
        else:
            # Log but don't fail on delete — allow stack deletion to proceed
            logger.warning("Failed to delete user %s: %s", username, str(e))

    physical_id = event["PhysicalResourceId"]
    return physical_id, {"UserName": username, "DirectoryId": directory_id}


def get_secret_value(secret_arn: str) -> str:
    """Retrieve plain-text secret value from Secrets Manager."""
    response = sm_client.get_secret_value(SecretId=secret_arn)
    return response["SecretString"]


def send_response(
    event: dict[str, Any],
    context: Any,
    status: str,
    data: dict[str, str],
    physical_resource_id: str,
) -> None:
    """Send response to CloudFormation pre-signed URL."""
    response_body = json.dumps({
        "Status": status,
        "Reason": f"See CloudWatch Log Stream: {context.log_stream_name}",
        "PhysicalResourceId": physical_resource_id,
        "StackId": event["StackId"],
        "RequestId": event["RequestId"],
        "LogicalResourceId": event["LogicalResourceId"],
        "Data": data,
    })

    logger.info("Response: %s", response_body)

    request = urllib.request.Request(
        event["ResponseURL"],
        data=response_body.encode("utf-8"),
        headers={"Content-Type": ""},
        method="PUT",
    )

    with urllib.request.urlopen(request) as response:
        logger.info("Response status: %s", response.status)
