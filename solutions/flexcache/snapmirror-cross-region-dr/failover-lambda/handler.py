"""SnapMirror Cross-Region DR Failover Lambda.

Performs automated DR failover:
1. Breaks the SnapMirror relationship on the destination cluster
2. Sets junction path on destination volume (if unset after break)
3. Polls FSx API until volume shows junction path
4. Creates a new S3 Access Point on the destination volume
5. Publishes SNS notification with new S3 AP endpoint details

SM-VAL-009: DP volume MUST be created via FSx API for S3 AP attachment.
SM-VAL-008: FSx API VolumeType lag (>10min cross-region) — do NOT gate on VolumeType.
SM-VAL-010: Estimated RTO ~3 minutes (break + junction + AP creation + first API call).
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import boto3
import urllib3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Suppress urllib3 InsecureRequestWarning (ONTAP self-signed cert)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Environment variables
DEST_MGMT_IP = os.environ.get("DEST_MGMT_IP", "")
DEST_SECRET_ARN = os.environ.get("DEST_SECRET_ARN", "")
DEST_VOLUME_ID = os.environ.get("DEST_VOLUME_ID", "")
DEST_JUNCTION_PATH = os.environ.get("DEST_JUNCTION_PATH", "/dr_dest")
S3_AP_NAME = os.environ.get("S3_AP_NAME", "")
S3_AP_UNIX_USER = os.environ.get("S3_AP_UNIX_USER", "fsxadmin")
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")
DEST_REGION = os.environ.get("DEST_REGION", "")

# Timeouts and retries
JUNCTION_POLL_INTERVAL = 15
JUNCTION_POLL_MAX_ATTEMPTS = 12  # 3 minutes max
S3AP_POLL_INTERVAL = 10
S3AP_POLL_MAX_ATTEMPTS = 12  # 2 minutes max


def get_ontap_credentials(secret_arn: str) -> dict[str, str]:
    """Retrieve ONTAP credentials from Secrets Manager."""
    client = boto3.client("secretsmanager", region_name=DEST_REGION or None)
    response = client.get_secret_value(SecretId=secret_arn)
    return json.loads(response["SecretString"])


def ontap_request(
    method: str,
    path: str,
    mgmt_ip: str,
    username: str,
    password: str,
    body: dict | None = None,
) -> dict[str, Any]:
    """Make ONTAP REST API request."""
    http = urllib3.PoolManager(cert_reqs="CERT_NONE")
    url = f"https://{mgmt_ip}/api{path}"
    headers = urllib3.make_headers(basic_auth=f"{username}:{password}")
    headers["Content-Type"] = "application/json"
    headers["Accept"] = "application/json"

    kwargs: dict[str, Any] = {"method": method, "url": url, "headers": headers}
    if body:
        kwargs["body"] = json.dumps(body).encode("utf-8")

    response = http.request(**kwargs)

    if response.status >= 400:
        logger.error(
            "ONTAP API error: %s %s → %d: %s",
            method,
            path,
            response.status,
            response.data.decode("utf-8", errors="replace"),
        )
        raise RuntimeError(f"ONTAP API {method} {path} failed: HTTP {response.status}")

    if response.data:
        return json.loads(response.data.decode("utf-8"))
    return {}


def break_snapmirror(mgmt_ip: str, username: str, password: str) -> None:
    """Break SnapMirror relationship on destination.

    Finds the SnapMirror relationship targeting the destination volume
    and issues a break operation.
    """
    # Find SnapMirror relationships on this cluster (as destination)
    result = ontap_request(
        "GET",
        "/snapmirror/relationships?list_destinations_only=true&fields=uuid,state,destination.path",
        mgmt_ip,
        username,
        password,
    )

    relationships = result.get("records", [])
    if not relationships:
        logger.warning("No SnapMirror relationships found. Volume may already be RW.")
        return

    for rel in relationships:
        rel_uuid = rel["uuid"]
        state = rel.get("state", "")
        logger.info(
            "Found SnapMirror relationship %s (state=%s, dest=%s)",
            rel_uuid,
            state,
            rel.get("destination", {}).get("path", "unknown"),
        )

        if state == "broken_off":
            logger.info("Relationship already broken. Skipping break operation.")
            continue

        # Break the relationship
        logger.info("Breaking SnapMirror relationship %s...", rel_uuid)
        ontap_request(
            "PATCH",
            f"/snapmirror/relationships/{rel_uuid}",
            mgmt_ip,
            username,
            password,
            body={"state": "broken_off"},
        )
        logger.info("SnapMirror break initiated for %s", rel_uuid)


def set_junction_path(volume_id: str, junction_path: str, region: str) -> None:
    """Set junction path on the destination volume via FSx API.

    After SnapMirror break, junction path may be unset.
    This makes the volume accessible for NFS/SMB and S3 AP attachment.
    """
    fsx = boto3.client("fsx", region_name=region or None)

    # Check current state
    response = fsx.describe_volumes(VolumeIds=[volume_id])
    volumes = response.get("Volumes", [])
    if not volumes:
        raise RuntimeError(f"Volume {volume_id} not found in FSx API")

    current_jp = volumes[0].get("OntapConfiguration", {}).get("JunctionPath") or ""
    if current_jp:
        logger.info("Junction path already set: %s", current_jp)
        return

    # Set junction path
    logger.info("Setting junction path to %s on volume %s", junction_path, volume_id)
    fsx.update_volume(
        VolumeId=volume_id,
        OntapConfiguration={"JunctionPath": junction_path},
    )
    logger.info("Junction path update initiated")


def poll_junction_path(volume_id: str, region: str) -> bool:
    """Poll FSx API until junction path appears on the volume."""
    fsx = boto3.client("fsx", region_name=region or None)

    for attempt in range(1, JUNCTION_POLL_MAX_ATTEMPTS + 1):
        response = fsx.describe_volumes(VolumeIds=[volume_id])
        volumes = response.get("Volumes", [])
        if volumes:
            jp = volumes[0].get("OntapConfiguration", {}).get("JunctionPath") or ""
            if jp:
                logger.info("Junction path confirmed: %s (attempt %d)", jp, attempt)
                return True

        logger.info(
            "Waiting for junction path... (attempt %d/%d)",
            attempt,
            JUNCTION_POLL_MAX_ATTEMPTS,
        )
        time.sleep(JUNCTION_POLL_INTERVAL)

    logger.error("Junction path not set after %d attempts", JUNCTION_POLL_MAX_ATTEMPTS)
    return False


def create_s3_access_point(volume_id: str, ap_name: str, unix_user: str, region: str) -> dict[str, str]:
    """Create and attach an S3 Access Point on the destination volume.

    SM-VAL-008: Do NOT check FSx API VolumeType before creating AP.
    The S3 AP creation works as long as the ONTAP-level type is RW and
    junction path is set.
    """
    fsx = boto3.client("fsx", region_name=region or None)

    logger.info("Creating S3 AP '%s' on volume %s (user=%s)", ap_name, volume_id, unix_user)

    response = fsx.create_and_attach_s3_access_point(
        Name=ap_name,
        Type="ONTAP",
        OntapConfiguration={
            "VolumeId": volume_id,
            "FileSystemIdentity": {
                "Type": "UNIX",
                "UnixUser": {"Name": unix_user},
            },
        },
    )

    ap_arn = response.get("S3AccessPoint", {}).get("S3AccessPointArn", "")
    logger.info("S3 AP creation initiated. ARN: %s", ap_arn)
    return {"arn": ap_arn, "name": ap_name}


def poll_s3_ap_available(ap_name: str, region: str) -> str:
    """Poll until S3 AP status is AVAILABLE. Returns the AP alias."""
    fsx = boto3.client("fsx", region_name=region or None)
    account_id = boto3.client("sts").get_caller_identity()["Account"]

    for attempt in range(1, S3AP_POLL_MAX_ATTEMPTS + 1):
        # List data repository associations to find our AP
        try:
            response = fsx.describe_data_repository_associations()
            for assoc in response.get("Associations", []):
                # Match by name pattern in ARN
                arn = assoc.get("ResourceARN", "")
                if ap_name in arn and assoc.get("Lifecycle") == "AVAILABLE":
                    alias = f"{ap_name}-{account_id}-s3alias"
                    logger.info("S3 AP AVAILABLE (attempt %d)", attempt)
                    return alias
        except Exception as e:
            logger.warning("Error checking AP status: %s", e)

        logger.info(
            "Waiting for S3 AP AVAILABLE... (attempt %d/%d)",
            attempt,
            S3AP_POLL_MAX_ATTEMPTS,
        )
        time.sleep(S3AP_POLL_INTERVAL)

    logger.warning("S3 AP not confirmed AVAILABLE within timeout")
    return f"{ap_name}-{account_id}-s3alias"


def publish_notification(topic_arn: str, ap_info: dict[str, str], region: str) -> None:
    """Publish SNS notification with failover result."""
    if not topic_arn:
        logger.info("No SNS topic configured. Skipping notification.")
        return

    sns = boto3.client("sns", region_name=region or None)
    message = {
        "event": "SnapMirror DR Failover Complete",
        "s3_access_point_arn": ap_info.get("arn", ""),
        "s3_access_point_name": ap_info.get("name", ""),
        "s3_access_point_alias": ap_info.get("alias", ""),
        "destination_volume_id": DEST_VOLUME_ID,
        "destination_region": region,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "note": "Update client applications to use the new S3 AP endpoint.",
    }

    sns.publish(
        TopicArn=topic_arn,
        Subject="[DR Failover] S3 AP Re-Attached on Destination Volume",
        Message=json.dumps(message, indent=2),
    )
    logger.info("SNS notification published to %s", topic_arn)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler for SnapMirror DR failover.

    Input event (optional overrides):
    {
        "dest_mgmt_ip": "<override>",
        "dest_volume_id": "<override>",
        "dest_junction_path": "<override>",
        "s3_ap_name": "<override>",
        "dry_run": false
    }
    """
    # Allow event overrides for flexibility
    mgmt_ip = event.get("dest_mgmt_ip", DEST_MGMT_IP)
    volume_id = event.get("dest_volume_id", DEST_VOLUME_ID)
    junction_path = event.get("dest_junction_path", DEST_JUNCTION_PATH)
    ap_name = event.get("s3_ap_name", S3_AP_NAME)
    unix_user = event.get("s3_ap_unix_user", S3_AP_UNIX_USER)
    dry_run = event.get("dry_run", False)
    region = event.get("dest_region", DEST_REGION)

    logger.info("=== SnapMirror DR Failover Started ===")
    logger.info(
        "Volume=%s, JunctionPath=%s, S3AP=%s, DryRun=%s",
        volume_id,
        junction_path,
        ap_name,
        dry_run,
    )

    if dry_run:
        return {
            "statusCode": 200,
            "body": "DRY RUN — no changes made",
            "steps": [
                "break_snapmirror",
                "set_junction_path",
                "poll_junction_path",
                "create_s3_access_point",
                "publish_notification",
            ],
        }

    # Validate required parameters
    if not all([mgmt_ip, volume_id, ap_name]):
        raise ValueError("Missing required parameters: DEST_MGMT_IP, DEST_VOLUME_ID, S3_AP_NAME")

    # Step 1: Get ONTAP credentials
    logger.info("Step 1/5: Retrieving ONTAP credentials...")
    creds = get_ontap_credentials(DEST_SECRET_ARN)
    username = creds["username"]
    password = creds["password"]

    # Step 2: Break SnapMirror
    logger.info("Step 2/5: Breaking SnapMirror relationship...")
    break_snapmirror(mgmt_ip, username, password)

    # Step 3: Set junction path
    logger.info("Step 3/5: Setting junction path on destination volume...")
    set_junction_path(volume_id, junction_path, region)

    # Step 4: Poll for junction path propagation
    logger.info("Step 4/5: Waiting for junction path in FSx API...")
    if not poll_junction_path(volume_id, region):
        raise RuntimeError(f"Junction path not propagated within timeout for volume {volume_id}")

    # Step 5: Create S3 Access Point
    logger.info("Step 5/5: Creating S3 Access Point on destination volume...")
    ap_info = create_s3_access_point(volume_id, ap_name, unix_user, region)

    # Wait for AP availability and get alias
    alias = poll_s3_ap_available(ap_name, region)
    ap_info["alias"] = alias

    # Publish notification
    publish_notification(SNS_TOPIC_ARN, ap_info, region)

    logger.info("=== SnapMirror DR Failover Complete ===")
    logger.info("S3 AP ARN: %s", ap_info.get("arn", ""))
    logger.info("S3 AP Alias: %s", alias)

    return {
        "statusCode": 200,
        "body": "DR failover complete",
        "s3_access_point": ap_info,
        "destination_volume_id": volume_id,
        "destination_region": region,
    }
