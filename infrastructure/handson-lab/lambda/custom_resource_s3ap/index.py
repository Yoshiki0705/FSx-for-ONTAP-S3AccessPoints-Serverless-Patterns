"""CloudFormation Custom Resource — FSx for ONTAP S3 Access Point.

Creates/deletes an S3 Access Point on an FSx for ONTAP volume using the
FSx CreateDataRepositoryAssociation API.

IMPORTANT:
- The SVM must be AD-joined before creating WINDOWS-type S3 APs
- WindowsUser.Name must be username only (no domain prefix!)
- Same user cannot have multiple S3 APs on the same file system
- S3 AP alias is auto-generated and immutable

Environment Variables:
    LOG_LEVEL: Logging level (default: INFO)
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

fsx_client = boto3.client("fsx")


def handler(event: dict[str, Any], context: Any) -> None:
    """CloudFormation Custom Resource handler."""
    logger.info("Event: %s", json.dumps(event, default=str))

    request_type = event["RequestType"]
    properties = event["ResourceProperties"]

    try:
        if request_type == "Create":
            physical_id, data = create_s3_access_point(properties)
        elif request_type == "Update":
            # S3 APs are immutable — replacement required
            physical_id, data = create_s3_access_point(properties)
        elif request_type == "Delete":
            physical_id, data = delete_s3_access_point(event)
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


def create_s3_access_point(properties: dict[str, Any]) -> tuple[str, dict[str, str]]:
    """Create S3 Access Point via FSx Data Repository Association."""
    volume_id = properties["VolumeId"]
    ap_name = properties["AccessPointName"]
    user_type = properties.get("FileSystemUserType", "WINDOWS")

    # Build S3 configuration for FSx S3 Access Point
    s3_config: dict[str, Any] = {
        "AutoImportPolicy": {"Events": ["NEW", "CHANGED", "DELETED"]},
        "AutoExportPolicy": {"Events": ["NEW", "CHANGED", "DELETED"]},
    }

    # Build NFS configuration with file system identity
    nfs_config: dict[str, Any] = {}

    # Determine file system user identity
    if user_type == "WINDOWS":
        windows_username = properties.get("WindowsUserName", "user01")
        # CRITICAL: No domain prefix! "user01" not "DOMAIN\\user01"
        logger.info(
            "Creating WINDOWS-type S3 AP: %s for user: %s",
            ap_name, windows_username,
        )
        nfs_config["FileSystemUserType"] = "WINDOWS"
        nfs_config["WindowsUser"] = {"Name": windows_username}
    else:
        unix_uid = properties.get("UnixUserId", "1001")
        unix_gid = properties.get("UnixGroupId", "1001")
        logger.info(
            "Creating UNIX-type S3 AP: %s for UID: %s GID: %s",
            ap_name, unix_uid, unix_gid,
        )
        nfs_config["FileSystemUserType"] = "UNIX"
        nfs_config["UnixUser"] = {
            "Id": int(unix_uid),
            "GroupId": int(unix_gid),
        }

    # Create Data Repository Association (S3 Access Point)
    try:
        response = fsx_client.create_data_repository_association(
            FileSystemId=get_filesystem_id_from_volume(volume_id),
            FileSystemPath="/",
            DataRepositoryPath=f"s3://{ap_name}",
            S3=s3_config,
            Tags=[
                {"Key": "Name", "Value": ap_name},
                {"Key": "Purpose", "Value": "handson-lab"},
            ],
        )
        association = response["Association"]
        association_id = association["AssociationId"]
        logger.info("DRA created: %s", association_id)
    except ClientError as e:
        # If DRA approach fails, try direct S3 AP creation via volume
        logger.warning("DRA approach failed: %s, trying volume-based S3 AP", str(e))
        return create_s3ap_via_volume(volume_id, ap_name, nfs_config)

    # Wait for association to become available
    data = wait_for_association(association_id)
    physical_id = association_id

    return physical_id, data


def create_s3ap_via_volume(
    volume_id: str,
    ap_name: str,
    nfs_config: dict[str, Any],
) -> tuple[str, dict[str, str]]:
    """Create S3 Access Point directly on FSx for ONTAP volume.

    Uses the FSx create-volume-from-backup or update-volume approach
    when DRA is not the correct mechanism.
    """
    # For FSx for ONTAP S3 Access Points, the correct API is different
    # from DRA (which is for Lustre). We need to use the S3 AP-specific
    # mechanism via the AWS S3 control API.
    s3control = boto3.client("s3control")
    sts = boto3.client("sts")

    account_id = sts.get_caller_identity()["Account"]
    region = os.environ.get("AWS_REGION", "ap-northeast-1")

    # Get volume details to find the file system
    volume_resp = fsx_client.describe_volumes(VolumeIds=[volume_id])
    volume = volume_resp["Volumes"][0]
    fs_id = volume["FileSystemId"]

    # Build the S3 Access Point configuration
    # FSx for ONTAP S3 APs use a specialized bucket format
    bucket_name = f"fsx-{fs_id}"

    logger.info(
        "Creating S3 AP '%s' on volume %s (fs: %s)",
        ap_name, volume_id, fs_id,
    )

    try:
        # Create S3 Access Point
        response = s3control.create_access_point(
            AccountId=account_id,
            Name=ap_name,
            Bucket=bucket_name,
            VpcConfiguration={
                "VpcId": get_vpc_id_from_filesystem(fs_id),
            } if False else {},  # Internet origin for hands-on simplicity
        )
        ap_arn = response.get("AccessPointArn", f"arn:aws:s3:{region}:{account_id}:accesspoint/{ap_name}")
        logger.info("S3 AP created: %s", ap_arn)
    except ClientError as e:
        if "AccessPointAlreadyOwnedByYou" in str(e) or "already exists" in str(e).lower():
            logger.info("S3 AP %s already exists", ap_name)
            ap_arn = f"arn:aws:s3:{region}:{account_id}:accesspoint/{ap_name}"
        else:
            raise

    # Get the AP alias
    try:
        ap_info = s3control.get_access_point(
            AccountId=account_id,
            Name=ap_name,
        )
        ap_alias = ap_info.get("Alias", f"{ap_name}-{account_id[:12]}-s3alias")
    except Exception:
        ap_alias = f"{ap_name}-s3alias"

    physical_id = f"{account_id}:{ap_name}"
    return physical_id, {
        "AccessPointArn": ap_arn,
        "AccessPointAlias": ap_alias,
        "AccessPointName": ap_name,
        "DataRepositoryAssociationId": "N/A (direct S3 AP)",
    }


def delete_s3_access_point(event: dict[str, Any]) -> tuple[str, dict[str, str]]:
    """Delete S3 Access Point."""
    physical_id = event["PhysicalResourceId"]
    properties = event["ResourceProperties"]
    ap_name = properties.get("AccessPointName", "")

    logger.info("Deleting S3 AP: physical_id=%s, name=%s", physical_id, ap_name)

    # Try DRA deletion first
    if physical_id.startswith("dra-"):
        try:
            fsx_client.delete_data_repository_association(
                AssociationId=physical_id,
                DeleteDataInFileSystem=False,
            )
            logger.info("DRA %s deletion initiated", physical_id)
        except ClientError as e:
            if "not found" in str(e).lower() or "NotFound" in str(e):
                logger.info("DRA %s not found, skipping", physical_id)
            else:
                logger.warning("DRA deletion failed: %s", str(e))

    # Try S3 AP deletion
    if ap_name:
        try:
            sts = boto3.client("sts")
            account_id = sts.get_caller_identity()["Account"]
            s3control = boto3.client("s3control")
            s3control.delete_access_point(
                AccountId=account_id,
                Name=ap_name,
            )
            logger.info("S3 AP %s deleted", ap_name)
        except ClientError as e:
            if "NoSuchAccessPoint" in str(e) or "not found" in str(e).lower():
                logger.info("S3 AP %s not found, skipping", ap_name)
            else:
                logger.warning("S3 AP deletion failed: %s", str(e))

    return physical_id, {"Deleted": "true"}


def get_filesystem_id_from_volume(volume_id: str) -> str:
    """Get file system ID from volume ID."""
    response = fsx_client.describe_volumes(VolumeIds=[volume_id])
    if not response["Volumes"]:
        raise ValueError(f"Volume {volume_id} not found")
    return response["Volumes"][0]["FileSystemId"]


def get_vpc_id_from_filesystem(fs_id: str) -> str:
    """Get VPC ID from file system."""
    response = fsx_client.describe_file_systems(FileSystemIds=[fs_id])
    if not response["FileSystems"]:
        raise ValueError(f"File system {fs_id} not found")
    return response["FileSystems"][0]["SubnetIds"][0]  # Simplified


def wait_for_association(association_id: str, timeout: int = 300) -> dict[str, str]:
    """Wait for DRA to become available."""
    start = time.time()
    while time.time() - start < timeout:
        response = fsx_client.describe_data_repository_associations(
            AssociationIds=[association_id]
        )
        assoc = response["Associations"][0]
        status = assoc.get("Lifecycle", "UNKNOWN")

        if status == "AVAILABLE":
            logger.info("DRA %s is AVAILABLE", association_id)
            return {
                "DataRepositoryAssociationId": association_id,
                "AccessPointArn": assoc.get("ResourceARN", ""),
                "AccessPointAlias": assoc.get("DataRepositoryPath", "").replace("s3://", ""),
                "AccessPointName": assoc.get("DataRepositoryPath", "").replace("s3://", ""),
            }
        elif status in ("FAILED", "MISCONFIGURED"):
            failure_details = assoc.get("FailureDetails", {})
            raise RuntimeError(
                f"DRA {association_id} failed: {status} - {failure_details}"
            )

        logger.info("DRA %s status: %s, waiting...", association_id, status)
        time.sleep(10)

    raise TimeoutError(f"DRA {association_id} did not become available within {timeout}s")


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

    logger.info("Response status: %s, physical_id: %s", status, physical_resource_id)

    request = urllib.request.Request(
        event["ResponseURL"],
        data=response_body.encode("utf-8"),
        headers={"Content-Type": ""},
        method="PUT",
    )

    with urllib.request.urlopen(request) as response:
        logger.info("CFn response sent: %s", response.status)
