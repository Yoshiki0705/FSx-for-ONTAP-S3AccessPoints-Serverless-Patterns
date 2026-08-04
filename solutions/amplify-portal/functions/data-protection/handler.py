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

Containment blocks and expiry:
    ONTAP name-mapping and export-policy rules carry no timestamp, so a block
    read back from the cluster cannot say when it was created or when it should
    end. Expiry therefore needs a ledger of the portal's own blocks, which is
    what CONTAINMENT_BLOCKS_TABLE holds. A scheduled sweep lifts the rows whose
    expiry has passed.

    The sweep only ever lifts blocks recorded in that ledger. Blocks placed by
    other means — an operator at the ONTAP CLI, another automation — are left
    alone, because this component cannot know the intent behind them and an
    unexpected unblock is a silent loss of containment.

Environment:
    ONTAP_MGMT_IP: FSx for ONTAP management endpoint
    ONTAP_SECRET_NAME: Secrets Manager secret (username/password)
    VOLUME_NAME: Target volume name
    SVM_NAME: SVM name
    CONTAINMENT_BLOCKS_TABLE: DynamoDB ledger of portal-created blocks (optional;
        without it blocking still works but nothing expires automatically)
    DEFAULT_BLOCK_TTL_HOURS: Fallback expiry when a caller does not pass one
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import boto3
import urllib3
from botocore.config import Config as BotoConfig

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

MGMT_IP = os.environ.get("ONTAP_MGMT_IP", "")
SECRET_NAME = os.environ.get("ONTAP_SECRET_NAME", "")
VOLUME_NAME = os.environ.get("VOLUME_NAME", "")
SVM_NAME = os.environ.get("SVM_NAME", "")
BLOCKS_TABLE = os.environ.get("CONTAINMENT_BLOCKS_TABLE", "")

# Applied when a caller does not pass ttlHours. A bounded default matters more
# than a long one: an expiry that has to be requested is an expiry that gets
# forgotten, and a block nobody remembers is indistinguishable from an outage.
DEFAULT_BLOCK_TTL_HOURS = int(os.environ.get("DEFAULT_BLOCK_TTL_HOURS", "24"))

# Ceiling on a single request, so a typo cannot park a block for years.
MAX_BLOCK_TTL_HOURS = 24 * 90

# Actions that change who can reach the filer, and so are worth noticing when
# they arrive without a portal identity behind them.
#
# `sweepExpiredBlocks` is deliberately absent: EventBridge invokes it directly
# and it carries no user by design. Including it would put the alarm in breach
# every quarter of an hour and teach everyone to ignore it.
#
# The unblocks are present even though they restore access. A forged unblock ends
# containment early, which is as much an incident as a forged block starting one.
STATE_CHANGING_ACTIONS = frozenset(
    {
        "blockSmbUser",
        "unblockSmbUser",
        "blockNfsIp",
        "unblockNfsIp",
        "containThreat",
        "disconnectSessions",
        "createSnapshot",
        "deleteSnapshot",
        "updateArpState",
        "updateRetentionPolicy",
    }
)

# How long a lifted or expired row is kept after its expiry, for audit. The
# native DynamoDB TTL is set from this, deliberately later than expiresAt, so
# the record of a containment action outlives the containment itself.
LEDGER_RETENTION_DAYS = int(os.environ.get("CONTAINMENT_LEDGER_RETENTION_DAYS", "400"))


def _get_credentials():
    """Retrieve ONTAP credentials from Secrets Manager."""
    client = boto3.client("secretsmanager")
    secret = client.get_secret_value(SecretId=SECRET_NAME)
    data = json.loads(secret["SecretString"])
    return data.get("username", "fsxadmin"), data.get("password", "")


# Identifiers supplied by the caller (a snapshot id, for example) end up in the
# request path. Unencoded, a value containing a traversal segment sends the
# request somewhere the action never advertised.
_UNSAFE_PATH_CHARS = re.compile(r"[\x00-\x1f\x7f\\]")


def _is_unsafe_path(path: str) -> bool:
    """True if the assembled request path must not be sent."""
    if _UNSAFE_PATH_CHARS.search(path):
        return True
    route = path.split("?", 1)[0]
    return any(segment == ".." for segment in route.split("/"))


def _seg(value) -> str:
    """Percent-encode a value used as a single path segment."""
    return quote(str(value), safe="")


def _ontap_get(http, headers, path, params=""):
    """Make GET request to ONTAP REST API."""
    if _is_unsafe_path(path):
        logger.warning("Refused ONTAP request with unsafe path: %r", path[:200])
        return {"error": {"message": "Invalid characters in request path"}}
    url = f"https://{MGMT_IP}/api{path}"
    if params:
        url += f"?{params}"
    resp = http.request("GET", url, headers=headers)
    return json.loads(resp.data)


def handler(event, context):
    """Route to appropriate handler based on action."""
    action = event.get("action", "")

    # Before the configuration check, so an unattributed attempt is recorded even
    # when it could not have done anything. Someone probing for a way in is worth
    # seeing whether or not the attempt would have worked.
    _note_attribution(action, event)

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
        # ARP/AI Response Actions (isolation/containment)
        #
        # Wrapped in _fan_out so an action can target several SVMs in one call. A
        # compromised account is usually reachable on every SVM that trusts the
        # same directory, and doing those one at a time leaves the others open
        # for as long as it takes. Fan-out only happens when the caller passes
        # `svms` or `allSvms`.
        elif action == "blockSmbUser":
            return _fan_out(event, _arp_block_smb_user, http, headers, gated=True)
        elif action == "unblockSmbUser":
            return _fan_out(event, _arp_unblock_smb_user, http, headers)
        elif action == "blockNfsIp":
            return _fan_out(event, _arp_block_nfs_ip, http, headers, gated=True)
        elif action == "unblockNfsIp":
            return _fan_out(event, _arp_unblock_nfs_ip, http, headers)
        elif action == "containThreat":
            return _fan_out(event, _arp_contain_threat, http, headers, gated=True)
        elif action == "listSvms":
            return _list_svms(http, headers, event)
        elif action == "listActiveBlocks":
            return _list_active_blocks_across(event, http, headers)
        elif action == "sweepExpiredBlocks":
            return _sweep_expired_blocks(event)
        elif action == "disconnectSessions":
            return _fan_out(event, _arp_disconnect_sessions, http, headers, gated=True)
        else:
            return {"error": f"Unknown action: {action}"}

    except Exception as e:
        logger.error(f"Data protection handler error: {e}")
        return {"error": str(e)}


def _get_volume_uuid(http, headers) -> str:
    """Resolve volume UUID from name."""
    data = _ontap_get(http, headers, "/storage/volumes", f"name={VOLUME_NAME}&svm.name={SVM_NAME}&fields=uuid")
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
        http,
        headers,
        f"/storage/volumes/{vol_uuid}/snapshots",
        f"order_by=create_time desc&max_records={max_results}"
        f"&fields=name,create_time,state,comment,snaplock_expiry_time,uuid",
    )

    snapshots = []
    for s in data.get("records", []):
        expiry = s.get("snaplock_expiry_time")
        name = s.get("name", "")
        snapshots.append(
            {
                "name": name,
                "createTime": s.get("create_time", ""),
                "state": s.get("state", "valid"),
                "comment": s.get("comment", ""),
                "snapshotId": s.get("uuid", ""),
                "isTamperproof": expiry is not None,
                "snaplockExpiryTime": expiry,
                "isArp": name.startswith("Anti_ransomware_backup"),
                "type": _classify_snapshot(name),
            }
        )

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
    data = _ontap_get(http, headers, f"/storage/volumes/{vol_uuid}", "fields=anti_ransomware")

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
        data = _ontap_get(
            http,
            headers,
            "/security/anti-ransomware/suspects",
            f"volume.uuid={vol_uuid}&fields=file.path,suspect_time,file.type",
        )
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
    data = _ontap_get(http, headers, f"/storage/volumes/{vol_uuid}", "fields=snaplock")

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
    data = _ontap_get(http, headers, f"/storage/volumes/{vol_uuid}", "fields=anti_ransomware,snaplock")

    # Get snapshot count
    snap_data = _ontap_get(
        http, headers, f"/storage/volumes/{vol_uuid}/snapshots", "max_records=1&return_records=false"
    )
    snap_count = snap_data.get("num_records", 0)

    # Count ARP snapshots
    arp_snap_data = _ontap_get(
        http, headers, f"/storage/volumes/{vol_uuid}/snapshots", "name=Anti_ransomware_backup*&return_records=false"
    )
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

            results["buckets"].append(
                {
                    "bucketName": bucket_name,
                    "purpose": bucket_info["purpose"],
                    "objectLockEnabled": lock_rule.get("ObjectLockEnabled") == "Enabled",
                    "defaultRetention": {
                        "mode": rule.get("Mode", "NONE"),  # GOVERNANCE or COMPLIANCE
                        "days": rule.get("Days"),
                        "years": rule.get("Years"),
                    },
                }
            )
        except s3.exceptions.ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "ObjectLockConfigurationNotFoundError":
                results["buckets"].append(
                    {
                        "bucketName": bucket_name,
                        "purpose": bucket_info["purpose"],
                        "objectLockEnabled": False,
                        "defaultRetention": None,
                    }
                )
            else:
                results["buckets"].append(
                    {
                        "bucketName": bucket_name,
                        "purpose": bucket_info["purpose"],
                        "objectLockEnabled": None,
                        "error": str(e),
                    }
                )

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

    url = f"https://{MGMT_IP}/api/storage/volumes/{vol_uuid}/snapshots/{_seg(snap_uuid)}"
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


# ─── ARP/AI Response Actions (Isolation/Containment) ─────────────────────────
#
# These use shared/ontap_response.ArpResponseActions which wraps OntapClient.
# Provides the same containment capabilities as DII Storage Workload Security
# but executed from the portal UI without external tools.


def _get_arp_response_client():
    """Initialize ArpResponseActions using project's shared modules.

    Uses the same Secrets Manager credentials as the rest of this Lambda.
    Imports are deferred to avoid import errors when shared/ is not in path
    (e.g., during local testing without the layer).
    """
    import sys
    from pathlib import Path

    # `/opt/python` is where the shared-modules Lambda layer mounts. The repo
    # root is only useful when running locally from a checkout.
    #
    # This previously used `Path(__file__).parents[4]`, which has three parents
    # in the Lambda runtime (`/var/task/handler.py`) and therefore raised
    # `IndexError: 4` before any import was attempted. Because `str(IndexError(4))`
    # is the string "4", it read like an HTTP status and was mistaken for one —
    # the containment actions were failing for a packaging reason while
    # reporting something else entirely. Walk the parents defensively instead.
    candidates = ["/opt/python"]
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "shared" / "ontap_response.py").exists():
            candidates.append(str(parent))
            break

    for p in candidates:
        if p not in sys.path:
            sys.path.insert(0, p)

    from shared.ontap_client import OntapClient, OntapClientConfig
    from shared.ontap_response import ArpResponseActions

    config = OntapClientConfig(
        management_ip=MGMT_IP,
        secret_name=SECRET_NAME,
        verify_ssl=False,  # PoC — set True + ca_cert_path for production
    )
    client = OntapClient(config)
    return ArpResponseActions(client)


def _arp_client_or_error():
    """Build the ARP client, converting a construction failure into a readable error.

    Returns (client, None) or (None, error_dict).

    Without this, a failure here escapes to the generic handler except clause
    and the UI shows whatever `str(e)` produced.

    Do not pattern-match on the text of the exception to guess a cause. An
    earlier version treated a short numeric message as an HTTP 404 and reported
    "the SVM may not have a CIFS service configured". The actual exception was
    `IndexError: 4` from a path calculation, so the message was confidently
    wrong about a packaging problem. Report the exception type and let the
    operator see the real detail.
    """
    try:
        return _get_arp_response_client(), None
    except ImportError as e:
        return None, {
            "success": False,
            "error": (
                "Containment is unavailable: the shared ONTAP modules are not on the "
                f"Python path ({e}). The function needs the shared-modules layer attached."
            ),
        }
    except Exception as e:
        return None, {
            "success": False,
            "error": f"Failed to initialise the ONTAP client: {type(e).__name__}: {e}",
        }


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _blocks_table():
    """Return the ledger table, or None when no table is configured.

    Returning None rather than raising keeps blocking usable in a deployment
    without the ledger: containment is the urgent half, expiry is the tidy-up.
    Callers surface this as `expiryTracked: false` so the difference is visible
    instead of looking like a block that will expire on its own.

    The timeouts are deliberately short and retries are off. This function runs
    in a VPC, and if the subnet has no route to DynamoDB the default client
    settings hang until the Lambda is killed. That turned a block ONTAP had
    already accepted into a timeout at the caller — an operator would read that
    as "containment failed" when the principal was in fact blocked. Failing in
    seconds keeps the ledger a side effect of the block rather than a gate on it.
    """
    if not BLOCKS_TABLE:
        return None
    return boto3.resource(
        "dynamodb",
        config=BotoConfig(
            connect_timeout=3,
            read_timeout=5,
            retries={"max_attempts": 1, "mode": "standard"},
        ),
    ).Table(BLOCKS_TABLE)


def _block_id(block_type: str, svm: str, *parts: str) -> str:
    """Stable identity for a block, so re-blocking updates one row.

    Without this, repeatedly blocking the same principal would leave several
    rows with different expiries and the earliest one would lift a block the
    operator had just extended.
    """
    return "#".join([block_type, svm, *parts])


def _validated_ttl_hours(event) -> tuple[int | None, dict | None]:
    """Resolve the requested expiry.

    Returns (hours, error). hours of 0 means the caller explicitly asked for an
    indefinite block, which is allowed but recorded as such — an unbounded block
    should be a deliberate statement, not the effect of omitting a field.
    """
    if "ttlHours" not in event or event.get("ttlHours") is None:
        return DEFAULT_BLOCK_TTL_HOURS, None

    raw = event.get("ttlHours")
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        return None, {"success": False, "error": "ttlHours must be a number"}
    try:
        hours = int(raw)
    except (TypeError, ValueError):
        return None, {"success": False, "error": "ttlHours must be a number"}

    if hours < 0:
        return None, {"success": False, "error": "ttlHours cannot be negative"}
    if hours > MAX_BLOCK_TTL_HOURS:
        return None, {
            "success": False,
            "error": f"ttlHours cannot exceed {MAX_BLOCK_TTL_HOURS} ({MAX_BLOCK_TTL_HOURS // 24} days)",
        }
    return hours, None


def _actor(event) -> dict:
    """Who took this action, and how that was established.

    `userId` is set by the AppSync resolver from the Cognito identity, and the
    resolver strips any the caller supplied, so it can be trusted on that path.
    A direct invocation of this function carries no identity at all, and the two
    cases must not look the same in the ledger: "unknown" alone reads like a
    lookup that failed rather than an action nobody is accountable for.

    There is deliberately no fallback to a caller-supplied field. An earlier
    version fell back to `actor`, which no resolver set or cleared, so a caller
    could name anyone they liked as long as `userId` happened to be absent.

    What this does not defend against: anyone holding lambda:InvokeFunction on
    this function can send both fields and be attributed as whoever they name.
    There is no way to tell from inside the handler, and it is a smaller problem
    than the one that permission already grants — the holder can block any
    principal outright. The IAM policy on the function is the real boundary; this
    keeps the AppSync path honest and makes an unattributed action look like one.
    """
    via = event.get("invokedVia")
    if via == "appsync" and event.get("userId"):
        return {"createdBy": event["userId"], "createdVia": "appsync"}

    # Reaching here means the call did not come through the portal. Record that
    # plainly instead of attributing it to someone.
    return {"createdBy": "unattributed", "createdVia": "direct-invoke"}


def _record_block(block_type: str, block_id: str, svm: str, params: dict, ttl_hours: int, event) -> dict:
    """Write the ledger row for a block that ONTAP has just accepted.

    Recorded after the cluster call succeeds, never before: a row for a block
    that does not exist would make the sweep try to lift nothing, and worse,
    would tell an operator a principal is contained when it is not.
    """
    table = _blocks_table()
    if table is None:
        return {"expiryTracked": False, "expiresAt": None}

    created = _now()
    expires = created + timedelta(hours=ttl_hours) if ttl_hours > 0 else None
    item = {
        "blockId": block_id,
        "blockType": block_type,
        "svm": svm,
        "status": "active",
        "createdAt": _iso(created),
        **_actor(event),
        "expiresAt": _iso(expires) if expires else None,
        # Kept past expiry on purpose, so the audit trail of a containment
        # action outlives the block.
        "ttl": int(((expires or created) + timedelta(days=LEDGER_RETENTION_DAYS)).timestamp()),
        **params,
    }

    try:
        table.put_item(Item=item)
        return {"expiryTracked": True, "expiresAt": item["expiresAt"]}
    except Exception as e:
        # The block itself is in place, so this is not a failure of containment.
        # It does mean nothing will expire it, which the caller must be told.
        logger.error(f"ledger write failed for {block_id}: {type(e).__name__}: {e}")
        return {
            "expiryTracked": False,
            "expiresAt": None,
            "ledgerError": type(e).__name__,
        }


def _mark_lifted(block_id: str, reason: str) -> None:
    """Close out a ledger row once the block is gone from the cluster."""
    table = _blocks_table()
    if table is None:
        return
    try:
        table.update_item(
            Key={"blockId": block_id},
            UpdateExpression="SET #s = :s, liftedAt = :t, liftReason = :r",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":s": "lifted",
                ":t": _iso(_now()),
                ":r": reason,
            },
        )
    except Exception as e:
        # A stale 'active' row is the safe direction to fail: the next sweep
        # retries the unblock, and unblocking something already unblocked is
        # harmless. Losing the row would be worse.
        logger.error(f"ledger update failed for {block_id}: {type(e).__name__}: {e}")


def _list_svms(http, headers, event):
    """List the SVMs on the cluster, for choosing containment targets.

    A compromised account is usually reachable on every SVM that trusts the same
    directory, so containing it on one SVM is often only part of the job. The
    portal cannot decide that on the operator's behalf, but it can show them the
    choice.
    """
    try:
        data = _ontap_get(http, headers, "/svm/svms", "fields=name,state&max_records=200")
        svms = [{"name": r.get("name"), "state": r.get("state")} for r in data.get("records", []) if r.get("name")]
        return {"success": True, "svms": svms, "total": len(svms), "error": None}
    except Exception as e:
        logger.error(f"list_svms failed: {type(e).__name__}: {e}")
        return {
            "success": False,
            "svms": [],
            "total": 0,
            "error": f"Failed to list SVMs: {type(e).__name__}",
        }


def _svm_targets(event, http, headers) -> tuple[list[str] | None, dict | None]:
    """Resolve which SVMs an action should act on.

    Returns (targets, error). Fan-out is never implicit: an operator who names
    one SVM gets one SVM. `svms` names them explicitly, `allSvms` asks the
    cluster. Widening the blast radius has to be something the caller asked for.
    """
    if event.get("allSvms"):
        listing = _list_svms(http, headers, event)
        if not listing["success"]:
            return None, {"success": False, "error": listing["error"]}
        # Only SVMs that are actually serving data. Blocking on a stopped SVM
        # would report a containment that is not protecting anything.
        names = [s["name"] for s in listing["svms"] if s.get("state") == "running"]
        if not names:
            return None, {"success": False, "error": "No running SVMs found on the cluster"}
        return names, None

    requested = event.get("svms")
    if requested is not None:
        if not isinstance(requested, list) or not requested:
            return None, {"success": False, "error": "svms must be a non-empty list of SVM names"}
        names = []
        for entry in requested:
            if not isinstance(entry, str) or not entry.strip():
                return None, {"success": False, "error": "svms must contain non-empty strings"}
            names.append(entry.strip())
        # Preserve order but drop duplicates, so a repeated name does not turn
        # into a second block attempt reported as "already blocked".
        return list(dict.fromkeys(names)), None

    return [event.get("svm", SVM_NAME)], None


def _fan_out(event, single, http, headers, gated: bool = False):
    """Run a single-SVM containment action across the resolved targets.

    Partial results are reported as such. Claiming overall success would hide a
    gap in containment; claiming overall failure would hide the SVMs where the
    block did land and now needs lifting. Both readings lead an operator to the
    wrong next action, so the response names each SVM and its outcome.

    Gated actions are checked once here rather than once per SVM, so a missing
    confirmation returns the reason instead of a list of identical refusals.
    """
    if gated:
        gate = _require_confirm(event)
        if gate:
            return gate

    targets, error = _svm_targets(event, http, headers)
    if error:
        return error

    if len(targets) == 1:
        return single({**event, "svm": targets[0]})

    results = {}
    for svm in targets:
        try:
            results[svm] = single({**event, "svm": svm})
        except Exception as e:
            # A raise here would abandon the SVMs not yet visited and lose the
            # record of the ones already done.
            logger.error(f"fan-out to {svm} raised: {type(e).__name__}: {e}")
            results[svm] = {"success": False, "error": f"{type(e).__name__}: {e}"}

    succeeded = sorted(s for s, r in results.items() if r.get("success"))
    failed = sorted(s for s, r in results.items() if not r.get("success"))

    return {
        "success": not failed,
        "action": next((r.get("action") for r in results.values() if r.get("action")), event.get("action")),
        "fannedOut": True,
        "targets": targets,
        "succeededOn": succeeded,
        "failedOn": failed,
        "perSvm": results,
        "error": None
        if not failed
        else f"Succeeded on {len(succeeded)} of {len(targets)} SVMs; failed on: {', '.join(failed)}",
    }


def _require_confirm(event):
    """Return an error dict unless the caller passed confirm=true.

    Blocking a user or a client IP cuts data access for that principal across
    the whole SVM. A UI dialog alone is a suggestion, not a control — anything
    calling AppSync directly bypasses it — so the gate lives here as well.

    Unblock actions are deliberately NOT gated: they restore access, and a
    confirmation step on the way back out of a mistaken block only slows the
    recovery down.
    """
    if not event.get("confirm", False):
        return {"success": False, "error": "confirm=true is required for containment operations"}
    return None


def _arp_block_smb_user(event):
    """Block an SMB user (name-mapping deny rule).

    Event params:
        domain: Windows domain (e.g., "CORP")
        username: Username to block (e.g., "jdoe")
        confirm: Must be true — this cuts the user's access SVM-wide
        svm: Optional SVM name override (default: SVM_NAME env var)
    """
    svm = event.get("svm", SVM_NAME)
    domain = event.get("domain", "")
    username = event.get("username", "")

    if not domain or not username:
        return {"success": False, "error": "domain and username are required"}
    gate = _require_confirm(event)
    if gate:
        return gate
    ttl_hours, ttl_error = _validated_ttl_hours(event)
    if ttl_error:
        return ttl_error

    arp, client_error = _arp_client_or_error()
    if client_error:
        return client_error

    try:
        result = arp.block_smb_user(svm_name=svm, domain=domain, username=username)
        ledger = _record_block(
            "smb",
            _block_id("smb", svm, domain, username),
            svm,
            {"domain": domain, "username": username},
            ttl_hours,
            event,
        )
        return {"success": True, **result, **ledger}
    except Exception as e:
        logger.error(f"block_smb_user failed: {e}")
        return {"success": False, "error": str(e)}


def _arp_unblock_smb_user(event):
    """Unblock a previously blocked SMB user.

    Event params:
        domain: Windows domain
        username: Username to unblock
        svm: Optional SVM name override
    """
    arp, client_error = _arp_client_or_error()
    if client_error:
        return client_error
    svm = event.get("svm", SVM_NAME)
    domain = event.get("domain", "")
    username = event.get("username", "")

    if not domain or not username:
        return {"success": False, "error": "domain and username are required"}

    try:
        result = arp.unblock_smb_user(svm_name=svm, domain=domain, username=username)
        _mark_lifted(_block_id("smb", svm, domain, username), event.get("reason", "manual"))
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"unblock_smb_user failed: {e}")
        return {"success": False, "error": str(e)}


def _arp_block_nfs_ip(event):
    """Block an IP address from NFS access (export-policy deny rule).

    Event params:
        clientIp: IP to block (e.g., "10.0.5.99")
        policyName: Export policy name (default: "default")
        confirm: Must be true — this cuts the client's NFS access
        svm: Optional SVM name override
    """
    svm = event.get("svm", SVM_NAME)
    client_ip = event.get("clientIp", "")
    policy_name = event.get("policyName", "default")

    if not client_ip:
        return {"success": False, "error": "clientIp is required"}
    gate = _require_confirm(event)
    if gate:
        return gate
    ttl_hours, ttl_error = _validated_ttl_hours(event)
    if ttl_error:
        return ttl_error

    arp, client_error = _arp_client_or_error()
    if client_error:
        return client_error

    try:
        result = arp.block_nfs_ip(svm_name=svm, policy_name=policy_name, client_ip=client_ip)
        ledger = _record_block(
            "nfs",
            _block_id("nfs", svm, policy_name, client_ip),
            svm,
            {"policyName": policy_name, "clientIp": client_ip},
            ttl_hours,
            event,
        )
        return {"success": True, **result, **ledger}
    except Exception as e:
        logger.error(f"block_nfs_ip failed: {e}")
        return {"success": False, "error": str(e)}


def _arp_unblock_nfs_ip(event):
    """Unblock a previously blocked NFS IP.

    Event params:
        clientIp: IP to unblock
        policyName: Export policy name (default: "default")
        svm: Optional SVM name override
    """
    arp, client_error = _arp_client_or_error()
    if client_error:
        return client_error
    svm = event.get("svm", SVM_NAME)
    client_ip = event.get("clientIp", "")
    policy_name = event.get("policyName", "default")

    if not client_ip:
        return {"success": False, "error": "clientIp is required"}

    try:
        result = arp.unblock_nfs_ip(svm_name=svm, policy_name=policy_name, client_ip=client_ip)
        _mark_lifted(_block_id("nfs", svm, policy_name, client_ip), event.get("reason", "manual"))
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"unblock_nfs_ip failed: {e}")
        return {"success": False, "error": str(e)}


def _arp_contain_threat(event):
    """Execute full threat containment (snapshot + block + disconnect).

    Event params:
        domain: Windows domain (optional, for SMB blocking)
        username: Username (optional, for SMB blocking)
        clientIp: IP address (optional, for NFS blocking)
        volumeName: Volume to snapshot (optional, default: VOLUME_NAME)
        policyName: Export policy (default: "default")
        reason: Reason string for audit
        confirm: Must be true — this blocks and disconnects in one call
        svm: Optional SVM name override
    """
    svm = event.get("svm", SVM_NAME)
    domain = event.get("domain")
    username = event.get("username")
    client_ip = event.get("clientIp")
    volume_name = event.get("volumeName", VOLUME_NAME)
    policy_name = event.get("policyName", "default")
    reason = event.get("reason", "portal-initiated")

    if not domain and not username and not client_ip:
        return {
            "success": False,
            "error": "At least one of (domain+username) or clientIp is required",
        }
    gate = _require_confirm(event)
    if gate:
        return gate
    ttl_hours, ttl_error = _validated_ttl_hours(event)
    if ttl_error:
        return ttl_error

    arp, client_error = _arp_client_or_error()
    if client_error:
        return client_error

    try:
        result = arp.contain_threat(
            svm_name=svm,
            domain=domain,
            username=username,
            client_ip=client_ip,
            volume_name=volume_name if volume_name else None,
            policy_name=policy_name,
            reason=reason,
        )
        contained = result["status"] == "contained"

        # This path places the same blocks as the individual actions, so it has
        # to record them the same way. Leaving them out of the ledger would make
        # the most urgent route the only one that never expires.
        expiries = []
        if contained:
            if domain and username:
                expiries.append(
                    _record_block(
                        "smb",
                        _block_id("smb", svm, domain, username),
                        svm,
                        {"domain": domain, "username": username, "viaContainThreat": True},
                        ttl_hours,
                        event,
                    )
                )
            if client_ip:
                expiries.append(
                    _record_block(
                        "nfs",
                        _block_id("nfs", svm, policy_name, client_ip),
                        svm,
                        {"policyName": policy_name, "clientIp": client_ip, "viaContainThreat": True},
                        ttl_hours,
                        event,
                    )
                )

        return {
            "success": contained,
            **result,
            "expiryTracked": bool(expiries) and all(e["expiryTracked"] for e in expiries),
            "expiresAt": next((e["expiresAt"] for e in expiries if e["expiresAt"]), None),
        }
    except Exception as e:
        logger.error(f"contain_threat failed: {e}")
        return {"success": False, "error": str(e)}


def _arp_list_active_blocks(event):
    """List all active isolation blocks on the SVM.

    Event params:
        svm: Optional SVM name override

    Returns name-mapping deny entries (SMB blocks) and export-policy deny rules (NFS blocks).
    Falls back to empty lists if the shared module is unavailable or errors.
    """
    svm = event.get("svm", SVM_NAME)

    arp, client_error = _arp_client_or_error()
    if client_error:
        # Surface it rather than reporting an empty list. "No blocks" and "could
        # not ask" look identical to an operator otherwise, and this listing is
        # the only way to find and lift a block that was set by mistake.
        return {
            "success": False,
            "smbBlocks": [],
            "nfsBlocks": [],
            "total": 0,
            "error": client_error["error"],
        }

    try:
        result = arp.list_active_blocks(svm_name=svm)
        # The shared module returns snake_case keys; the UI reads camelCase, and
        # the error branches below already used camelCase. Spreading the raw
        # result therefore produced a response the Active Blocks tab could not
        # read: real blocks existed on the SVM and the panel showed none of them.
        # Since that tab is the only way to lift a block from the portal, the
        # mismatch made a mistaken block unliftable through the UI.
        smb_blocks = _annotate_expiry(result.get("smb_blocks", []), "smb", svm)
        nfs_blocks = _annotate_expiry(result.get("nfs_blocks", []), "nfs", svm)
        return {
            "success": True,
            "action": result.get("action", "list_active_blocks"),
            "svm": result.get("svm", svm),
            "smbBlocks": smb_blocks,
            "nfsBlocks": nfs_blocks,
            "total": result.get("total", 0),
            "error": None,
        }
    except Exception as e:
        logger.error(f"list_active_blocks failed: {type(e).__name__}: {e}")
        return {
            "success": False,
            "smbBlocks": [],
            "nfsBlocks": [],
            "total": 0,
            "error": f"Failed to retrieve active blocks: {type(e).__name__}: {e}",
        }


def _list_active_blocks_across(event, http, headers):
    """List active blocks on one SVM or across several.

    Blocking can fan out, so the listing has to as well. A block placed on an SVM
    the listing does not cover is invisible, and an invisible block cannot be
    lifted from the portal — the same trap as reporting an empty list when the
    query failed.

    Each entry carries its own `svm`, because the unblock call needs to know
    where the block actually is.
    """
    targets, error = _svm_targets(event, http, headers)
    if error:
        return {"success": False, "smbBlocks": [], "nfsBlocks": [], "total": 0, **error}

    if len(targets) == 1:
        return _arp_list_active_blocks({**event, "svm": targets[0]})

    smb, nfs, failures = [], [], []
    for svm in targets:
        result = _arp_list_active_blocks({**event, "svm": svm})
        if not result.get("success"):
            failures.append(f"{svm}: {result.get('error')}")
            continue
        for entry in result.get("smbBlocks", []):
            smb.append({**entry, "svm": svm})
        for entry in result.get("nfsBlocks", []):
            nfs.append({**entry, "svm": svm})

    return {
        # A listing that silently skipped an SVM would let a block hide there.
        "success": not failures,
        "action": "list_active_blocks",
        "svm": ", ".join(targets),
        "svms": targets,
        "smbBlocks": smb,
        "nfsBlocks": nfs,
        "total": len(smb) + len(nfs),
        "error": None if not failures else "; ".join(failures),
    }


def _ledger_rows(status: str = "active") -> list[dict]:
    """Read ledger rows with the given status.

    A scan is adequate here and a GSI would be premature: the table only ever
    holds one row per contained principal, and a deployment with enough
    simultaneous blocks to make this expensive has a much bigger problem.
    """
    table = _blocks_table()
    if table is None:
        return []

    rows: list[dict] = []
    kwargs: dict = {
        "FilterExpression": "#s = :s",
        "ExpressionAttributeNames": {"#s": "status"},
        "ExpressionAttributeValues": {":s": status},
    }
    while True:
        page = table.scan(**kwargs)
        rows.extend(page.get("Items", []))
        cursor = page.get("LastEvaluatedKey")
        if not cursor:
            return rows
        kwargs["ExclusiveStartKey"] = cursor


def _annotate_expiry(blocks: list, block_type: str, svm: str) -> list:
    """Attach expiry to the blocks the cluster reported.

    ONTAP has no timestamp for these rules, so expiry can only come from the
    ledger. Blocks with no matching row get `expiresAt: None` and
    `managedByPortal: False` — that is the honest answer for a block placed
    outside the portal, and it tells the operator the sweep will not lift it.
    """
    try:
        rows = {row["blockId"]: row for row in _ledger_rows("active")}
    except Exception as e:
        logger.error(f"ledger read failed while annotating: {type(e).__name__}: {e}")
        rows = {}

    annotated = []
    for block in blocks:
        entry = dict(block) if isinstance(block, dict) else {"value": block}
        match = None
        for row in rows.values():
            if row.get("blockType") != block_type or row.get("svm") != svm:
                continue
            if block_type == "smb":
                needle = f"{row.get('domain', '')}\\{row.get('username', '')}"
                if needle and needle.replace("\\", "") in str(entry.get("pattern", "")).replace("\\", ""):
                    match = row
                    break
            else:
                if str(row.get("clientIp", "")) and str(row.get("clientIp")) in str(entry.get("client_match", "")):
                    match = row
                    break
        entry["expiresAt"] = match.get("expiresAt") if match else None
        entry["managedByPortal"] = match is not None
        annotated.append(entry)
    return annotated


METRIC_NAMESPACE = "FsxOntapPortal/Containment"


def _emit_sweep_metrics(swept: int, failed: int, examined: int) -> None:
    """Publish the sweep outcome as CloudWatch metrics, via an embedded-format log.

    EMF is written to stdout and picked up by the log group, so this needs no
    cloudwatch:PutMetricData permission and cannot fail on a throttle.

    `SweepRuns` is emitted on every run, including clean ones, so an alarm can
    treat missing data as a breach. Alarming only on failures would leave the
    worst case invisible: a sweep that has stopped running altogether reports no
    failures at all, and blocks quietly outlive their expiry.

    Wrapped so a metrics problem can never take down the sweep. The sweep exists
    to restore access; losing telemetry is the lesser harm.
    """
    try:
        print(
            json.dumps(
                {
                    "_aws": {
                        "Timestamp": int(_now().timestamp() * 1000),
                        "CloudWatchMetrics": [
                            {
                                "Namespace": METRIC_NAMESPACE,
                                "Dimensions": [[]],
                                "Metrics": [
                                    {"Name": "SweepRuns", "Unit": "Count"},
                                    {"Name": "SweepFailures", "Unit": "Count"},
                                    {"Name": "BlocksLifted", "Unit": "Count"},
                                    {"Name": "ActiveBlocksExamined", "Unit": "Count"},
                                ],
                            }
                        ],
                    },
                    "SweepRuns": 1,
                    "SweepFailures": failed,
                    "BlocksLifted": swept,
                    "ActiveBlocksExamined": examined,
                }
            )
        )
    except Exception as e:
        logger.error(f"could not emit sweep metrics: {type(e).__name__}: {e}")


def _note_attribution(action: str, event) -> None:
    """Record whether a state-changing action came with a portal identity.

    This is detection, not prevention, and the distinction is worth being clear
    about. Within one account a principal may invoke a function if *either* its
    own identity policy or the function's resource policy allows it, and the
    Lambda permission API only writes Allow statements. So no resource policy
    added here can take invoke rights away from a principal that already has
    them; it can only hand them to more. Prevention lives in the identity
    policies and any service control policy or permissions boundary above them —
    outside this stack. See docs/portal-authorization-model.md.

    What is achievable from inside the function is making the case visible. A
    direct invocation is already recorded as `unattributed` / `direct-invoke` in
    the ledger, but only somebody reading that row would ever see it. Emitting a
    metric turns it into something that can raise an alarm while the containment
    is still in force.

    Expected to fire during operational work: scripts/portal-probes/ invokes this
    function directly on purpose. That is the same event the alarm is for, so the
    probes are documented as tripping it rather than exempted — an exemption would
    be a hole shaped exactly like the thing being watched for.
    """
    if action not in STATE_CHANGING_ACTIONS:
        return

    attributed = _actor(event)["createdVia"] == "appsync"
    if not attributed:
        logger.warning(f"state-changing action '{action}' invoked without a portal identity; recorded as unattributed")

    try:
        print(
            json.dumps(
                {
                    "_aws": {
                        "Timestamp": int(_now().timestamp() * 1000),
                        "CloudWatchMetrics": [
                            {
                                "Namespace": METRIC_NAMESPACE,
                                "Dimensions": [[]],
                                "Metrics": [
                                    {"Name": "UnattributedContainmentActions", "Unit": "Count"},
                                    {"Name": "AttributedContainmentActions", "Unit": "Count"},
                                ],
                            }
                        ],
                    },
                    "UnattributedContainmentActions": 0 if attributed else 1,
                    "AttributedContainmentActions": 1 if attributed else 0,
                    # Not a metric dimension: the action name would multiply the
                    # metric by cardinality for no gain, since the alarm is on
                    # "any of them". Kept as a log field so the log tells you
                    # which one without the metric paying for it.
                    "action": action,
                }
            )
        )
    except Exception as e:
        # Losing telemetry must never stop a containment action from running.
        logger.error(f"could not emit attribution metric: {type(e).__name__}: {e}")


def _sweep_expired_blocks(event):
    """Lift the blocks whose expiry has passed.

    Invoked on a schedule. Only ledger rows are considered, so a block placed
    outside the portal is never touched — see the module docstring.

    A row whose unblock fails stays `active` deliberately, so the next run tries
    again. Unblocking something already unblocked is harmless; leaving a
    principal cut off because one sweep failed is not.
    """
    arp, client_error = _arp_client_or_error()
    if client_error:
        # Counted as a failure, not just logged. A sweep that cannot reach ONTAP
        # lifts nothing, which is indistinguishable from having nothing to lift
        # unless it says so.
        _emit_sweep_metrics(swept=0, failed=1, examined=0)
        return {"success": False, "swept": 0, "failed": 0, "error": client_error["error"]}

    try:
        rows = _ledger_rows("active")
    except Exception as e:
        logger.error(f"sweep could not read the ledger: {type(e).__name__}: {e}")
        _emit_sweep_metrics(swept=0, failed=1, examined=0)
        return {
            "success": False,
            "swept": 0,
            "failed": 0,
            "error": f"Ledger read failed: {type(e).__name__}",
        }

    now = _now()
    swept, failed, details = 0, 0, []

    for row in rows:
        expires_at = row.get("expiresAt")
        if not expires_at:
            continue  # explicitly indefinite
        try:
            due = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        except ValueError:
            logger.error(f"unparseable expiresAt on {row.get('blockId')}: {expires_at!r}")
            failed += 1
            continue
        if due > now:
            continue

        block_id = row["blockId"]
        try:
            if row.get("blockType") == "smb":
                arp.unblock_smb_user(
                    svm_name=row.get("svm", SVM_NAME),
                    domain=row.get("domain", ""),
                    username=row.get("username", ""),
                )
            else:
                arp.unblock_nfs_ip(
                    svm_name=row.get("svm", SVM_NAME),
                    policy_name=row.get("policyName", "default"),
                    client_ip=row.get("clientIp", ""),
                )
            _mark_lifted(block_id, "expired")
            swept += 1
            details.append({"blockId": block_id, "result": "lifted"})
        except Exception as e:
            failed += 1
            logger.error(f"sweep failed to lift {block_id}: {type(e).__name__}: {e}")
            details.append({"blockId": block_id, "result": f"failed: {type(e).__name__}"})

    logger.info(f"sweep complete: {swept} lifted, {failed} failed, {len(rows)} active rows examined")
    _emit_sweep_metrics(swept=swept, failed=failed, examined=len(rows))
    return {
        "success": failed == 0,
        "action": "sweep_expired_blocks",
        "swept": swept,
        "failed": failed,
        "examined": len(rows),
        "details": details,
        "error": None if failed == 0 else f"{failed} block(s) could not be lifted",
    }


def _arp_disconnect_sessions(event):
    """Disconnect active CIFS sessions for a user or IP.

    Event params:
        user: Windows user (e.g., "CORP\\jdoe")
        clientIp: Client IP (at least one required)
        confirm: Must be true — this drops the user's open sessions
        svm: Optional SVM name override
    """
    svm = event.get("svm", SVM_NAME)
    user = event.get("user")
    client_ip = event.get("clientIp")

    if not user and not client_ip:
        return {"success": False, "error": "At least one of user or clientIp is required"}
    gate = _require_confirm(event)
    if gate:
        return gate

    arp, client_error = _arp_client_or_error()
    if client_error:
        return client_error

    try:
        result = arp.disconnect_smb_sessions(svm_name=svm, user=user, client_ip=client_ip)
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"disconnect_sessions failed: {e}")
        return {"success": False, "error": str(e)}
