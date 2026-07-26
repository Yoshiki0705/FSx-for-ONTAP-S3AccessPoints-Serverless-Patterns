import os
import json
import urllib3
import boto3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ONTAP_MGMT_IP = os.environ.get("ONTAP_MGMT_IP", "")
SECRET_NAME = os.environ.get("ONTAP_SECRET_NAME", "")
VOLUME_NAME = os.environ.get("VOLUME_NAME", "")
SVM_NAME = os.environ.get("SVM_NAME", "")


def get_credentials():
    """Retrieve ONTAP credentials from Secrets Manager."""
    client = boto3.client("secretsmanager")
    secret = client.get_secret_value(SecretId=SECRET_NAME)
    data = json.loads(secret["SecretString"])
    return data.get("username", "fsxadmin"), data.get("password", "")


def handler(event, context):
    """List ONTAP snapshots for the configured volume.

    Returns snapshot names with creation timestamps, enabling the
    'Version History' feature in the portal UI. Users can select
    a snapshot to browse past file states via FlexClone + S3 AP.

    Supports multiple actions:
    - listSnapshots: List snapshots with lock status (default)
    - getArpStatus: Get ARP/AI ransomware protection status
    - getSnaplockStatus: Get SnapLock volume configuration
    - lockSnapshot: Set/extend expiry time on a snapshot (Tamperproof)
    - getProtectionSummary: Combined overview of all protection features
    """
    action = event.get("action", "listSnapshots")
    max_results = event.get("maxResults", 10)

    if not all([ONTAP_MGMT_IP, SECRET_NAME, VOLUME_NAME]):
        return {
            "snapshots": [],
            "volumeName": VOLUME_NAME,
            "error": "ONTAP connection not configured (set ONTAP_MGMT_IP, ONTAP_SECRET_NAME, VOLUME_NAME)",
        }

    try:
        username, password = get_credentials()
        http = urllib3.PoolManager(cert_reqs="CERT_NONE")
        headers = urllib3.make_headers(basic_auth=f"{username}:{password}")
        headers["Accept"] = "application/json"

        # Get volume UUID (shared across all actions)
        vol_url = (
            f"https://{ONTAP_MGMT_IP}/api/storage/volumes"
            f"?name={VOLUME_NAME}&svm.name={SVM_NAME}&fields=uuid,anti_ransomware,snaplock,snapshot_locking_enabled"
        )
        vol_resp = http.request("GET", vol_url, headers=headers)
        vol_data = json.loads(vol_resp.data)

        if not vol_data.get("records"):
            return {
                "snapshots": [],
                "volumeName": VOLUME_NAME,
                "error": f"Volume '{VOLUME_NAME}' not found on SVM '{SVM_NAME}'",
            }

        vol_record = vol_data["records"][0]
        vol_uuid = vol_record["uuid"]

        # --- Action: getArpStatus ---
        if action == "getArpStatus":
            arp = vol_record.get("anti_ransomware", {})
            return {
                "volumeName": VOLUME_NAME,
                "arp": {
                    "state": arp.get("state", "disabled"),
                    "attackProbability": arp.get("attack_probability", "none"),
                    "dryRunStartTime": arp.get("dry_run_start_time", ""),
                    "surgeAsNormal": arp.get("surge_as_normal", False),
                },
                "error": None,
            }

        # --- Action: getSnaplockStatus ---
        if action == "getSnaplockStatus":
            snaplock = vol_record.get("snaplock", {})
            return {
                "volumeName": VOLUME_NAME,
                "snaplock": {
                    "type": snaplock.get("type", "non_snaplock"),
                    "complianceClockTime": snaplock.get("compliance_clock_time", ""),
                    "expiryTime": snaplock.get("expiry_time", ""),
                    "isAuditLog": snaplock.get("is_audit_log", False),
                    "autocommitPeriod": snaplock.get("autocommit_period", ""),
                    "retentionPeriod": {
                        "defaultPeriod": str(snaplock.get("retention", {}).get("default", "")),
                        "minimumPeriod": str(snaplock.get("retention", {}).get("minimum", "")),
                        "maximumPeriod": str(snaplock.get("retention", {}).get("maximum", "")),
                    },
                },
                "snapshotLockingEnabled": vol_record.get("snapshot_locking_enabled", False),
                "error": None,
            }

        # --- Action: lockSnapshot (Tamperproof Snapshot) ---
        if action == "lockSnapshot":
            snap_uuid = event.get("snapshotId", "")
            expiry_time = event.get("expiryTime", "")
            if not snap_uuid or not expiry_time:
                return {"success": False, "error": "snapshotId and expiryTime required"}

            # Check if snapshot locking is enabled on volume
            if not vol_record.get("snapshot_locking_enabled", False):
                return {
                    "success": False,
                    "error": "Snapshot locking is not enabled on this volume. "
                             "Enable with: volume modify -volume <vol> -snapshot-locking-enabled true",
                }

            # PATCH snapshot to set expiry_time
            lock_url = f"https://{ONTAP_MGMT_IP}/api/storage/volumes/{vol_uuid}/snapshots/{snap_uuid}"
            body = json.dumps({"expiry_time": expiry_time}).encode("utf-8")
            lock_headers = dict(headers)
            lock_headers["Content-Type"] = "application/json"
            lock_resp = http.request("PATCH", lock_url, headers=lock_headers, body=body)

            if lock_resp.status in (200, 202):
                return {"success": True, "snapshotId": snap_uuid, "expiryTime": expiry_time, "error": None}
            else:
                err_data = json.loads(lock_resp.data) if lock_resp.data else {}
                err_msg = err_data.get("error", {}).get("message", f"HTTP {lock_resp.status}")
                return {"success": False, "error": err_msg}

        # --- Action: getProtectionSummary ---
        if action == "getProtectionSummary":
            arp = vol_record.get("anti_ransomware", {})
            snaplock = vol_record.get("snaplock", {})
            return {
                "data": {
                    "volumeName": VOLUME_NAME,
                    "arp": {
                        "state": arp.get("state", "disabled"),
                        "attackProbability": arp.get("attack_probability", "none"),
                    },
                    "snaplock": {
                        "type": snaplock.get("type", "non_snaplock"),
                    },
                    "snapshotLockingEnabled": vol_record.get("snapshot_locking_enabled", False),
                },
                "error": None,
            }

        # --- Default action: listSnapshots (with lock info) ---
        snap_url = (
            f"https://{ONTAP_MGMT_IP}/api/storage/volumes/{vol_uuid}/snapshots"
            f"?order_by=create_time desc&max_records={max_results}"
            f"&fields=name,create_time,state,comment,uuid,expiry_time,snaplock_expiry_time"
        )
        snap_resp = http.request("GET", snap_url, headers=headers)
        snap_data = json.loads(snap_resp.data)

        snapshots = [
            {
                "name": s["name"],
                "createTime": s.get("create_time", ""),
                "snapshotId": s.get("uuid", ""),
                "state": s.get("state", "valid"),
                "comment": s.get("comment", ""),
                "expiryTime": s.get("expiry_time", ""),
                "snaplockExpiryTime": s.get("snaplock_expiry_time", ""),
                "isLocked": bool(s.get("expiry_time") or s.get("snaplock_expiry_time")),
            }
            for s in snap_data.get("records", [])
        ]

        return {
            "snapshots": snapshots,
            "volumeName": VOLUME_NAME,
            "snapshotLockingEnabled": vol_record.get("snapshot_locking_enabled", False),
            "error": None,
        }

    except Exception as e:
        print(f"Error listing snapshots: {e}")
        return {
            "snapshots": [],
            "volumeName": VOLUME_NAME,
            "error": str(e),
        }
