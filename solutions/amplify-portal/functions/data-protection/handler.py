"""Data Protection Lambda — Snapshots, ARP/AI, SnapLock status via ONTAP REST API.

Provides the backend for the portal's Data Protection section:
- Snapshot listing (including tamperproof/locked status)
- ARP/AI status and suspect file alerts
- SnapLock volume configuration

ONTAP REST API endpoints used:
- GET /api/storage/volumes/{uuid}/snapshots — list snapshots with lock status
- GET /api/storage/volumes/{uuid}?fields=anti_ransomware,snaplock — ARP + SnapLock config
- GET /api/security/anti-ransomware/suspects — suspect files from ARP

Reference:
- AWS Docs: https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/ARP.html
- ONTAP REST API: https://docs.netapp.com/us-en/ontap-restapi/
- ARP snapshot prefix: "Anti_ransomware_backup"
- Observability project: https://github.com/Yoshiki0705/fsxn-observability-integrations

Environment:
    ONTAP_MGMT_IP: FSx for ONTAP management endpoint
    ONTAP_SECRET_NAME: Secrets Manager secret (username/password)
    VOLUME_NAME: Target volume name
    SVM_NAME: SVM name
"""
from __future__ import annotations

import json
import logging
import os

import boto3
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

MGMT_IP = os.environ.get("ONTAP_MGMT_IP", "")
SECRET_NAME = os.environ.get("ONTAP_SECRET_NAME", "")
VOLUME_NAME = os.environ.get("VOLUME_NAME", "")
SVM_NAME = os.environ.get("SVM_NAME", "")


def _get_credentials():
    """Retrieve ONTAP credentials from Secrets Manager."""
    client = boto3.client("secretsmanager")
    secret = client.get_secret_value(SecretId=SECRET_NAME)
    data = json.loads(secret["SecretString"])
    return data.get("username", "fsxadmin"), data.get("password", "")


def _ontap_get(http, headers, path, params=""):
    """Make GET request to ONTAP REST API."""
    url = f"https://{MGMT_IP}/api{path}"
    if params:
        url += f"?{params}"
    resp = http.request("GET", url, headers=headers)
    return json.loads(resp.data)


def handler(event, context):
    """Route to appropriate handler based on action."""
    action = event.get("action", "")

    if not all([MGMT_IP, SECRET_NAME]):
        return {"error": "ONTAP connection not configured (set ONTAP_MGMT_IP, ONTAP_SECRET_NAME)"}

    try:
        username, password = _get_credentials()
        http = urllib3.PoolManager(cert_reqs="CERT_NONE")
        headers = urllib3.make_headers(basic_auth=f"{username}:{password}")
        headers["Accept"] = "application/json"

        if action == "getSnapshotsWithLockStatus":
            return _get_snapshots(http, headers, event)
        elif action == "getArpStatus":
            return _get_arp_status(http, headers, event)
        elif action == "getArpSuspects":
            return _get_arp_suspects(http, headers, event)
        elif action == "getSnapLockConfig":
            return _get_snaplock_config(http, headers, event)
        elif action == "getS3ObjectLockStatus":
            return _get_s3_object_lock_status(event)
        elif action == "getProtectionSummary":
            return _get_protection_summary(http, headers, event)
        # Write operations (storage-admin only — enforced at AppSync layer)
        elif action == "createSnapshot":
            return _create_snapshot(http, headers, event)
        elif action == "deleteSnapshot":
            return _delete_snapshot(http, headers, event)
        elif action == "updateArpState":
            return _update_arp_state(http, headers, event)
        elif action == "updateRetentionPolicy":
            return _update_retention_policy(http, headers, event)
        else:
            return {"error": f"Unknown action: {action}"}

    except Exception as e:
        logger.error(f"Data protection handler error: {e}")
        return {"error": str(e)}


def _get_volume_uuid(http, headers) -> str:
    """Resolve volume UUID from name."""
    data = _ontap_get(http, headers, "/storage/volumes",
                      f"name={VOLUME_NAME}&svm.name={SVM_NAME}&fields=uuid")
    if not data.get("records"):
        raise ValueError(f"Volume '{VOLUME_NAME}' not found")
    return data["records"][0]["uuid"]


def _get_snapshots(http, headers, event):
    """List snapshots with tamperproof/lock status.

    Returns snapshots with:
    - name, create_time, state
    - snaplock_expiry_time (if locked/tamperproof)
    - is_tamperproof: true if expiry_time is set
    - is_arp: true if name starts with Anti_ransomware_backup
    """
    vol_uuid = _get_volume_uuid(http, headers)
    max_results = event.get("maxResults", 20)

    data = _ontap_get(
        http, headers,
        f"/storage/volumes/{vol_uuid}/snapshots",
        f"order_by=create_time desc&max_records={max_results}"
        f"&fields=name,create_time,state,comment,snaplock_expiry_time,uuid"
    )

    snapshots = []
    for s in data.get("records", []):
        expiry = s.get("snaplock_expiry_time")
        name = s.get("name", "")
        snapshots.append({
            "name": name,
            "createTime": s.get("create_time", ""),
            "state": s.get("state", "valid"),
            "comment": s.get("comment", ""),
            "snapshotId": s.get("uuid", ""),
            "isTamperproof": expiry is not None,
            "snaplockExpiryTime": expiry,
            "isArp": name.startswith("Anti_ransomware_backup"),
            "type": _classify_snapshot(name),
        })

    return {
        "snapshots": snapshots,
        "volumeName": VOLUME_NAME,
        "totalCount": data.get("num_records", len(snapshots)),
        "error": None,
    }


def _classify_snapshot(name: str) -> str:
    """Classify snapshot by naming convention."""
    if name.startswith("Anti_ransomware_backup"):
        return "ARP"
    elif name.startswith("daily."):
        return "Daily"
    elif name.startswith("hourly."):
        return "Hourly"
    elif name.startswith("weekly."):
        return "Weekly"
    elif name.startswith("snapmirror."):
        return "SnapMirror"
    else:
        return "Manual"


def _get_arp_status(http, headers, event):
    """Get ARP/AI status for the volume.

    ONTAP REST: GET /api/storage/volumes/{uuid}?fields=anti_ransomware
    States: disabled, dry_run (learning), enabled (active), paused
    """
    vol_uuid = _get_volume_uuid(http, headers)
    data = _ontap_get(http, headers, f"/storage/volumes/{vol_uuid}",
                      "fields=anti_ransomware")

    arp = data.get("anti_ransomware", {})
    state = arp.get("state", "disabled")

    # Map states to user-friendly labels
    state_labels = {
        "disabled": {"label": "Disabled", "severity": "warning"},
        "dry_run": {"label": "Learning Mode", "severity": "info"},
        "enabled": {"label": "Active Protection", "severity": "success"},
        "paused": {"label": "Paused", "severity": "warning"},
        "dry_run_paused": {"label": "Learning Paused", "severity": "warning"},
        "enable_paused": {"label": "Active (Paused)", "severity": "warning"},
        "disable_in_progress": {"label": "Disabling...", "severity": "warning"},
    }

    info = state_labels.get(state, {"label": state, "severity": "info"})

    return {
        "state": state,
        "stateLabel": info["label"],
        "severity": info["severity"],
        "dryRunStartTime": arp.get("dry_run_start_time"),
        "volumeName": VOLUME_NAME,
        "error": None,
    }


def _get_arp_suspects(http, headers, event):
    """Get suspect files detected by ARP.

    ONTAP REST: GET /api/security/anti-ransomware/suspects
    """
    vol_uuid = _get_volume_uuid(http, headers)

    try:
        data = _ontap_get(http, headers, "/security/anti-ransomware/suspects",
                          f"volume.uuid={vol_uuid}&fields=file.path,suspect_time,file.type")
        suspects = [
            {
                "filePath": s.get("file", {}).get("path", ""),
                "fileType": s.get("file", {}).get("type", ""),
                "suspectTime": s.get("suspect_time", ""),
            }
            for s in data.get("records", [])
        ]
        return {
            "suspects": suspects,
            "count": len(suspects),
            "volumeName": VOLUME_NAME,
            "error": None,
        }
    except Exception as e:
        # API may not be available on older ONTAP versions
        return {"suspects": [], "count": 0, "volumeName": VOLUME_NAME, "error": str(e)}


def _get_snaplock_config(http, headers, event):
    """Get SnapLock configuration for the volume.

    ONTAP REST: GET /api/storage/volumes/{uuid}?fields=snaplock
    """
    vol_uuid = _get_volume_uuid(http, headers)
    data = _ontap_get(http, headers, f"/storage/volumes/{vol_uuid}",
                      "fields=snaplock")

    snaplock = data.get("snaplock", {})
    sl_type = snaplock.get("type", "non_snaplock")

    return {
        "type": sl_type,  # "compliance", "enterprise", "non_snaplock"
        "isEnabled": sl_type != "non_snaplock",
        "complianceClockTime": snaplock.get("compliance_clock_time"),
        "retentionPeriod": {
            "default": snaplock.get("retention", {}).get("default"),
            "minimum": snaplock.get("retention", {}).get("minimum"),
            "maximum": snaplock.get("retention", {}).get("maximum"),
        },
        "autocommitPeriod": snaplock.get("autocommit_period"),
        "volumeName": VOLUME_NAME,
        "error": None,
    }


def _get_protection_summary(http, headers, event):
    """Get consolidated protection summary for the dashboard cards.

    Combines ARP status + snapshot count + SnapLock status + S3 Object Lock in one call.
    """
    vol_uuid = _get_volume_uuid(http, headers)

    # Get volume with all protection fields
    data = _ontap_get(http, headers, f"/storage/volumes/{vol_uuid}",
                      "fields=anti_ransomware,snaplock")

    # Get snapshot count
    snap_data = _ontap_get(http, headers,
                           f"/storage/volumes/{vol_uuid}/snapshots",
                           "max_records=1&return_records=false")
    snap_count = snap_data.get("num_records", 0)

    # Count ARP snapshots
    arp_snap_data = _ontap_get(http, headers,
                               f"/storage/volumes/{vol_uuid}/snapshots",
                               "name=Anti_ransomware_backup*&return_records=false")
    arp_snap_count = arp_snap_data.get("num_records", 0)

    arp = data.get("anti_ransomware", {})
    snaplock = data.get("snaplock", {})

    # Get S3 Object Lock status for output buckets
    s3_lock = _get_s3_object_lock_status(event)

    return {
        "arp": {
            "state": arp.get("state", "disabled"),
            "isActive": arp.get("state") == "enabled",
        },
        "snapshots": {
            "totalCount": snap_count,
            "arpSnapshotCount": arp_snap_count,
        },
        "snaplock": {
            "type": snaplock.get("type", "non_snaplock"),
            "isEnabled": snaplock.get("type", "non_snaplock") != "non_snaplock",
        },
        "s3ObjectLock": s3_lock,
        "volumeName": VOLUME_NAME,
        "error": None,
    }


def _get_s3_object_lock_status(event):
    """Get S3 Object Lock configuration for managed buckets.

    Uses AWS S3 API:
    - GetObjectLockConfiguration: bucket-level lock config
    - GetBucketVersioning: required for Object Lock

    Checks both the S3 AP-associated bucket (FSx for ONTAP volume)
    and any output buckets configured for AI processing results.

    Environment:
        S3_AP_ALIAS: S3 AP alias (to identify the associated bucket)
        OUTPUT_BUCKET: Optional S3 bucket for AI outputs
    """
    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "ap-northeast-1"))
    output_bucket = os.environ.get("OUTPUT_BUCKET", "")
    ap_alias = os.environ.get("S3_AP_ALIAS", "")

    results = {
        "buckets": [],
        "error": None,
    }

    # Check output bucket (standard S3 bucket where Object Lock can be configured)
    buckets_to_check = []
    if output_bucket:
        buckets_to_check.append({"name": output_bucket, "purpose": "AI output archive"})

    for bucket_info in buckets_to_check:
        bucket_name = bucket_info["name"]
        try:
            # Get Object Lock configuration
            lock_config = s3.get_object_lock_configuration(Bucket=bucket_name)
            lock_rule = lock_config.get("ObjectLockConfiguration", {})
            rule = lock_rule.get("Rule", {}).get("DefaultRetention", {})

            results["buckets"].append({
                "bucketName": bucket_name,
                "purpose": bucket_info["purpose"],
                "objectLockEnabled": lock_rule.get("ObjectLockEnabled") == "Enabled",
                "defaultRetention": {
                    "mode": rule.get("Mode", "NONE"),  # GOVERNANCE or COMPLIANCE
                    "days": rule.get("Days"),
                    "years": rule.get("Years"),
                },
            })
        except s3.exceptions.ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "ObjectLockConfigurationNotFoundError":
                results["buckets"].append({
                    "bucketName": bucket_name,
                    "purpose": bucket_info["purpose"],
                    "objectLockEnabled": False,
                    "defaultRetention": None,
                })
            else:
                results["buckets"].append({
                    "bucketName": bucket_name,
                    "purpose": bucket_info["purpose"],
                    "objectLockEnabled": None,
                    "error": str(e),
                })

    # Note: FSx for ONTAP S3 AP does not support GetObjectLockConfiguration
    # (Object Lock is an S3-native feature, not available via S3 AP).
    # ONTAP-side immutability is managed via SnapLock (separate section).
    if ap_alias:
        results["s3ApNote"] = (
            "FSx for ONTAP S3 AP uses SnapLock for WORM protection "
            "(not S3 Object Lock). See the SnapLock section for volume-level immutability."
        )

    return results


# ─── Write Operations (Storage Admin) ────────────────────────────────────────


def _create_snapshot(http, headers, event):
    """Create a manual snapshot.

    ONTAP REST: POST /api/storage/volumes/{uuid}/snapshots
    Body: {"name": "manual_YYYY-MM-DD_HHMM", "comment": "..."}
    """
    vol_uuid = _get_volume_uuid(http, headers)
    name = event.get("name", "")
    comment = event.get("comment", "")
    user_id = event.get("userId", "unknown")

    if not name:
        return {"success": False, "snapshotName": "", "error": "Snapshot name is required"}

    url = f"https://{MGMT_IP}/api/storage/volumes/{vol_uuid}/snapshots"
    body = json.dumps({"name": name, "comment": comment or f"Created by {user_id} via portal"})
    headers_post = dict(headers)
    headers_post["Content-Type"] = "application/json"

    resp = http.request("POST", url, headers=headers_post, body=body)
    resp_data = json.loads(resp.data)

    if resp.status in (201, 202):
        logger.info(f"Snapshot created: {name} by {user_id}")
        return {"success": True, "snapshotName": name, "error": None}
    else:
        error_msg = resp_data.get("error", {}).get("message", f"HTTP {resp.status}")
        return {"success": False, "snapshotName": "", "error": error_msg}


def _delete_snapshot(http, headers, event):
    """Delete a snapshot.

    ONTAP REST: DELETE /api/storage/volumes/{vol_uuid}/snapshots/{snap_uuid}

    WARNING: Cannot delete tamperproof (locked) snapshots before expiry.
    The API will return an error if attempted.
    """
    vol_uuid = _get_volume_uuid(http, headers)
    snap_uuid = event.get("snapshotId", "")
    snap_name = event.get("snapshotName", "")
    user_id = event.get("userId", "unknown")

    if not snap_uuid:
        return {"success": False, "error": "snapshotId is required"}

    url = f"https://{MGMT_IP}/api/storage/volumes/{vol_uuid}/snapshots/{snap_uuid}"
    resp = http.request("DELETE", url, headers=headers)

    if resp.status in (200, 202):
        logger.info(f"Snapshot deleted: {snap_name} ({snap_uuid}) by {user_id}")
        return {"success": True, "error": None}
    else:
        resp_data = json.loads(resp.data)
        error_msg = resp_data.get("error", {}).get("message", f"HTTP {resp.status}")
        logger.warning(f"Snapshot delete failed: {snap_name} — {error_msg}")
        return {"success": False, "error": error_msg}


def _update_arp_state(http, headers, event):
    """Update ARP/AI state for the volume.

    ONTAP REST: PATCH /api/storage/volumes/{uuid}
    Body: {"anti_ransomware": {"state": "enabled|disabled|dry_run"}}

    Valid transitions:
    - disabled → dry_run (start learning)
    - dry_run → enabled (activate protection)
    - enabled → disabled (WARNING: removes protection)
    - any → paused (temporary pause)
    """
    vol_uuid = _get_volume_uuid(http, headers)
    new_state = event.get("state", "")
    user_id = event.get("userId", "unknown")

    valid_states = {"disabled", "dry_run", "enabled", "paused"}
    if new_state not in valid_states:
        return {"success": False, "newState": "", "error": f"Invalid state: {new_state}. Valid: {valid_states}"}

    url = f"https://{MGMT_IP}/api/storage/volumes/{vol_uuid}"
    body = json.dumps({"anti_ransomware": {"state": new_state}})
    headers_patch = dict(headers)
    headers_patch["Content-Type"] = "application/json"

    resp = http.request("PATCH", url, headers=headers_patch, body=body)

    if resp.status in (200, 202):
        logger.info(f"ARP state updated to '{new_state}' by {user_id}")
        return {"success": True, "newState": new_state, "error": None}
    else:
        resp_data = json.loads(resp.data)
        error_msg = resp_data.get("error", {}).get("message", f"HTTP {resp.status}")
        return {"success": False, "newState": "", "error": error_msg}


def _update_retention_policy(http, headers, event):
    """Update retention policy (SnapLock or S3 Object Lock).

    target: "snaplock" or "s3_object_lock"
    mode: "GOVERNANCE" or "COMPLIANCE" (S3) / retention period (SnapLock)
    days: retention days
    """
    target = event.get("target", "")
    mode = event.get("mode", "")
    days = event.get("days", 0)
    user_id = event.get("userId", "unknown")

    if target == "snaplock":
        return _update_snaplock_retention(http, headers, days, user_id)
    elif target == "s3_object_lock":
        return _update_s3_object_lock(mode, days, user_id)
    else:
        return {"success": False, "error": f"Invalid target: {target}. Use 'snaplock' or 's3_object_lock'"}


def _update_snaplock_retention(http, headers, days, user_id):
    """Update SnapLock default retention period.

    ONTAP REST: PATCH /api/storage/volumes/{uuid}
    Body: {"snaplock": {"retention": {"default": "P{days}D"}}}

    ISO 8601 duration format: P30D = 30 days, P1Y = 1 year
    """
    vol_uuid = _get_volume_uuid(http, headers)

    if days <= 0:
        return {"success": False, "error": "days must be > 0"}

    # Convert days to ISO 8601 duration
    duration = f"P{days}D"

    url = f"https://{MGMT_IP}/api/storage/volumes/{vol_uuid}"
    body = json.dumps({"snaplock": {"retention": {"default": duration}}})
    headers_patch = dict(headers)
    headers_patch["Content-Type"] = "application/json"

    resp = http.request("PATCH", url, headers=headers_patch, body=body)

    if resp.status in (200, 202):
        logger.info(f"SnapLock retention updated to {days} days by {user_id}")
        return {"success": True, "error": None}
    else:
        resp_data = json.loads(resp.data)
        error_msg = resp_data.get("error", {}).get("message", f"HTTP {resp.status}")
        return {"success": False, "error": error_msg}


def _update_s3_object_lock(mode, days, user_id):
    """Update S3 Object Lock default retention on the output bucket.

    AWS S3: PutObjectLockConfiguration
    """
    output_bucket = os.environ.get("OUTPUT_BUCKET", "")
    if not output_bucket:
        return {"success": False, "error": "OUTPUT_BUCKET not configured"}

    if mode not in ("GOVERNANCE", "COMPLIANCE"):
        return {"success": False, "error": f"Invalid mode: {mode}. Use GOVERNANCE or COMPLIANCE"}

    if days <= 0:
        return {"success": False, "error": "days must be > 0"}

    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "ap-northeast-1"))

    try:
        s3.put_object_lock_configuration(
            Bucket=output_bucket,
            ObjectLockConfiguration={
                "ObjectLockEnabled": "Enabled",
                "Rule": {
                    "DefaultRetention": {
                        "Mode": mode,
                        "Days": days,
                    }
                },
            },
        )
        logger.info(f"S3 Object Lock updated: {output_bucket} → {mode} {days}d by {user_id}")
        return {"success": True, "error": None}
    except Exception as e:
        return {"success": False, "error": str(e)}
