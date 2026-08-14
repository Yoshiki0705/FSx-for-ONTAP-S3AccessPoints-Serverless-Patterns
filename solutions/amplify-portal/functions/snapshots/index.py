import json
import logging
import os
from urllib.parse import quote

import boto3
import urllib3

from shared.ontap_diagnosis import diagnose_exception, diagnose_response, not_configured

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ONTAP_MGMT_IP = os.environ.get("ONTAP_MGMT_IP", "")
SECRET_NAME = os.environ.get("ONTAP_SECRET_NAME", "")
VOLUME_NAME = os.environ.get("VOLUME_NAME", "")
SVM_NAME = os.environ.get("SVM_NAME", "")


def _qval(value) -> str:
    """Percent-encode a value used as a query-string value.

    The volume name reaches this URL from the client now, and an unencoded `&` or `=`
    would add parameters to the request rather than being matched as part of a name.
    """
    return quote(str(value), safe="")


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

    # The volume this request is about. Every action here read VOLUME_NAME directly, so
    # the whole data-protection area could only ever describe one volume: the ARP page
    # showed a fixed badge, and a state changed on any other volume was invisible there
    # -- indistinguishable from a change that had not taken effect.
    #
    # The environment variable stays as the default, which is what a reader without the
    # storage-admin group sees; only that group is offered the choice.
    volume_name = event.get("volumeName") or VOLUME_NAME
    # And which SVM it belongs to. A volume name is unique within an SVM, not within a
    # file system, so a name resolved against the wrong SVM is either not found or -- if
    # the name happens to exist on both -- the wrong volume. The panels can now choose a
    # volume, so they have to be able to say where it lives.
    svm_name = event.get("svm") or SVM_NAME

    missing = [
        name
        for name, value in (
            ("ONTAP_MGMT_IP", ONTAP_MGMT_IP),
            ("ONTAP_SECRET_NAME", SECRET_NAME),
            ("VOLUME_NAME", volume_name),
        )
        if not value
    ]
    if missing:
        return {"snapshots": [], "volumeName": volume_name, **not_configured(missing).as_dict()}

    try:
        username, password = get_credentials()
        http = urllib3.PoolManager(cert_reqs="CERT_NONE")
        headers = urllib3.make_headers(basic_auth=f"{username}:{password}")
        headers["Accept"] = "application/json"

        # Get volume UUID (shared across all actions)
        vol_url = (
            f"https://{ONTAP_MGMT_IP}/api/storage/volumes"
            f"?name={_qval(volume_name)}&svm.name={_qval(svm_name)}"
            f"&fields=uuid,anti_ransomware,snaplock,snapshot_locking_enabled"
        )
        vol_resp = http.request("GET", vol_url, headers=headers)

        # The status was never read here. An ONTAP 401 body carries no `records`, so a
        # rejected password arrived as "Volume 'vol1' not found on SVM 'fsxsvm01'" and the
        # panel then advised checking the VPC subnet and the security group -- neither of
        # which had anything to do with it.
        diagnosis = diagnose_response(
            vol_resp.status,
            vol_resp.data,
            subject=f"volume '{volume_name}' on SVM '{svm_name}'",
        )
        if diagnosis is not None:
            logger.warning("ONTAP volume lookup failed: class=%s status=%s", diagnosis.failure.value, diagnosis.status)
            return {"snapshots": [], "volumeName": volume_name, **diagnosis.as_dict()}

        vol_data = json.loads(vol_resp.data)

        vol_record = vol_data["records"][0]
        vol_uuid = vol_record["uuid"]

        # --- Action: getArpStatus ---
        if action == "getArpStatus":
            arp = vol_record.get("anti_ransomware", {})
            return {
                "volumeName": volume_name,
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
                "volumeName": volume_name,
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

            # The portal shows a dialog stating the expiry date and that the lock
            # can only be extended, but that dialog is client-side. Requiring the
            # flag here means a direct call cannot set a lock without saying so.
            if event.get("acknowledgeIrreversible") is not True:
                return {
                    "success": False,
                    "error": (
                        "acknowledgeIrreversible=true is required for this operation. "
                        f"The snapshot cannot be deleted until {expiry_time}, and the "
                        "expiry can afterwards only be extended, never shortened or "
                        "released. See docs/tamperproof-snapshot-design.md before "
                        "setting it."
                    ),
                }

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
                    "volumeName": volume_name,
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

        # --- Action: getFilePermissions ---
        if action == "getFilePermissions":
            file_path = event.get("filePath", "")
            if not file_path:
                return {"error": "filePath is required", "permissions": None}

            # Ensure path starts with /vol/<volume_name>
            if not file_path.startswith("/"):
                file_path = f"/vol/{volume_name}/{file_path}"
            elif not file_path.startswith("/vol/"):
                file_path = f"/vol/{volume_name}{file_path}"

            # Get SVM UUID first
            svm_url = f"https://{ONTAP_MGMT_IP}/api/svm/svms?name={_qval(svm_name)}&fields=uuid"
            svm_resp = http.request("GET", svm_url, headers=headers)
            svm_data = json.loads(svm_resp.data)
            if not svm_data.get("records"):
                return {"error": f"SVM '{svm_name}' not found", "permissions": None}
            svm_uuid = svm_data["records"][0]["uuid"]

            # Query file-security effective permissions
            import urllib.parse

            encoded_path = urllib.parse.quote(file_path, safe="")
            perm_url = f"https://{ONTAP_MGMT_IP}/api/protocols/file-security/permissions/{svm_uuid}/{encoded_path}"
            perm_resp = http.request("GET", perm_url, headers=headers)

            if perm_resp.status >= 400:
                # Fallback: get basic file info from volume
                return {
                    "filePath": file_path,
                    "permissions": None,
                    "error": f"Cannot get permissions (HTTP {perm_resp.status}). File may not exist or API unavailable.",
                }

            perm_data = json.loads(perm_resp.data)
            acls = perm_data.get("acls", [])
            unix_perms = perm_data.get("unix_permissions", "")
            owner = perm_data.get("owner", "")
            group = perm_data.get("group", "")
            security_style = perm_data.get("security_style", "")

            return {
                "filePath": file_path,
                "permissions": {
                    "securityStyle": security_style,
                    "owner": owner,
                    "group": group,
                    "unixPermissions": unix_perms,
                    "acls": [
                        {
                            "user": a.get("user", ""),
                            "access": a.get("access", ""),
                            "accessControl": a.get("access_control", ""),
                            "applyTo": a.get("apply_to", {}),
                        }
                        for a in acls[:10]
                    ],
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
            "volumeName": volume_name,
            "snapshotLockingEnabled": vol_record.get("snapshot_locking_enabled", False),
            "error": None,
        }

    except urllib3.exceptions.HTTPError as e:
        # A request that never produced a response: routing, security group, or a LIF
        # that is not listening. Separated from the block below because it is the one
        # failure the panel's original network advice was actually written for.
        diagnosis = diagnose_exception(e, mgmt_ip=ONTAP_MGMT_IP)
        logger.warning("ONTAP unreachable: %s", diagnosis.message)
        return {"snapshots": [], "volumeName": volume_name, **diagnosis.as_dict()}
    except Exception as e:
        logger.exception("Error listing snapshots")
        return {
            "snapshots": [],
            "volumeName": volume_name,
            "error": str(e),
            "errorClass": "ONTAP_ERROR",
        }
