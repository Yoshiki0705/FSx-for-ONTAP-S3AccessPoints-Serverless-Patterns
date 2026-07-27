"""Resource Management Lambda — Volume, Export Policy, QoS, SnapLock operations.

Provides the backend for the portal's Admin > Resource Management section.
Modeled after ONTAP System Manager's storage management capabilities,
implemented via ONTAP REST API for programmatic access.

ONTAP REST API endpoints used:
- /storage/volumes — Volume CRUD + resize
- /protocols/nfs/export-policies — Export policy management
- /protocols/nfs/export-policies/{id}/rules — Export policy rules
- /storage/qos/policies — QoS policy management
- /storage/volumes/{uuid} (snaplock fields) — SnapLock configuration

Environment:
    ONTAP_MGMT_IP: FSx for ONTAP management endpoint
    ONTAP_SECRET_NAME: Secrets Manager secret (username/password)
    SVM_NAME: Default SVM name
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
SVM_NAME = os.environ.get("SVM_NAME", "")
PORTAL_SETTINGS_TABLE = os.environ.get("PORTAL_SETTINGS_TABLE", "")


def _get_credentials():
    """Retrieve ONTAP credentials from Secrets Manager."""
    client = boto3.client("secretsmanager")
    secret = client.get_secret_value(SecretId=SECRET_NAME)
    data = json.loads(secret["SecretString"])
    return data.get("username", "fsxadmin"), data.get("password", "")


def _ontap_request(http, headers, method, path, body=None):
    """Make an ONTAP REST API request."""
    url = f"https://{MGMT_IP}/api{path}"
    kwargs = {"headers": headers}
    if body:
        headers_with_ct = dict(headers)
        headers_with_ct["Content-Type"] = "application/json"
        kwargs["headers"] = headers_with_ct
        kwargs["body"] = json.dumps(body)
    resp = http.request(method, url, **kwargs)
    data = json.loads(resp.data) if resp.data else {}
    if resp.status >= 400:
        error_msg = data.get("error", {}).get("message", f"HTTP {resp.status}")
        return {"_error": True, "_status": resp.status, "_message": error_msg}
    return data


def handler(event, context):
    """Route to appropriate handler based on action."""
    action = event.get("action", "")
    user_id = event.get("userId", "unknown")

    # --- Portal Settings (DynamoDB only, no ONTAP needed) ---
    if action == "getPortalSettings":
        return _get_portal_settings(event)
    elif action == "updatePortalSettings":
        return _update_portal_settings(event, user_id)

    if not all([MGMT_IP, SECRET_NAME]):
        return {"error": "ONTAP connection not configured"}

    try:
        username, password = _get_credentials()
        http = urllib3.PoolManager(cert_reqs="CERT_NONE")
        headers = urllib3.make_headers(basic_auth=f"{username}:{password}")
        headers["Accept"] = "application/json"

        # --- Volume Management ---
        if action == "listVolumes":
            return _list_volumes(http, headers, event)
        elif action == "listVolumesFiltered":
            return _list_volumes_filtered(http, headers, event)
        elif action == "getVolume":
            return _get_volume(http, headers, event)
        elif action == "createVolume":
            return _create_volume(http, headers, event, user_id)
        elif action == "resizeVolume":
            return _resize_volume(http, headers, event, user_id)
        elif action == "deleteVolume":
            return _delete_volume(http, headers, event, user_id)

        # --- Export Policy Management ---
        elif action == "listExportPolicies":
            return _list_export_policies(http, headers, event)
        elif action == "getExportPolicyRules":
            return _get_export_policy_rules(http, headers, event)
        elif action == "createExportPolicy":
            return _create_export_policy(http, headers, event, user_id)
        elif action == "deleteExportPolicy":
            return _delete_export_policy(http, headers, event, user_id)
        elif action == "createExportPolicyRule":
            return _create_export_policy_rule(http, headers, event, user_id)
        elif action == "deleteExportPolicyRule":
            return _delete_export_policy_rule(http, headers, event, user_id)

        # --- QoS Policy Management ---
        elif action == "listQosPolicies":
            return _list_qos_policies(http, headers, event)
        elif action == "createQosPolicy":
            return _create_qos_policy(http, headers, event, user_id)
        elif action == "updateQosPolicy":
            return _update_qos_policy(http, headers, event, user_id)
        elif action == "deleteQosPolicy":
            return _delete_qos_policy(http, headers, event, user_id)
        elif action == "assignQosToVolume":
            return _assign_qos_to_volume(http, headers, event, user_id)

        # --- SnapLock Management ---
        elif action == "getSnaplockConfig":
            return _get_snaplock_config(http, headers, event)
        elif action == "updateSnaplockRetention":
            return _update_snaplock_retention(http, headers, event, user_id)

        # --- Quota Management ---
        elif action == "listQuotaRules":
            return _list_quota_rules(http, headers, event)
        elif action == "getQuotaReport":
            return _get_quota_report(http, headers, event)
        elif action == "createQuotaRule":
            return _create_quota_rule(http, headers, event, user_id)
        elif action == "deleteQuotaRule":
            return _delete_quota_rule(http, headers, event, user_id)

        # --- CIFS/SMB Share Management ---
        elif action == "listCifsShares":
            return _list_cifs_shares(http, headers, event)
        elif action == "createCifsShare":
            return _create_cifs_share(http, headers, event, user_id)
        elif action == "updateCifsShare":
            return _update_cifs_share(http, headers, event, user_id)
        elif action == "deleteCifsShare":
            return _delete_cifs_share(http, headers, event, user_id)

        # --- Qtree Management ---
        elif action == "listQtrees":
            return _list_qtrees(http, headers, event)
        elif action == "createQtree":
            return _create_qtree(http, headers, event, user_id)
        elif action == "deleteQtree":
            return _delete_qtree(http, headers, event, user_id)

        # --- Storage Efficiency ---
        elif action == "getEfficiencyStats":
            return _get_efficiency_stats(http, headers, event)

        # --- ARP/AI Administration ---
        elif action == "listArpVolumes":
            return _list_arp_volumes(http, headers, event)
        elif action == "updateArpStateAdmin":
            return _update_arp_state_admin(http, headers, event, user_id)
        elif action == "getArpSuspectsAdmin":
            return _get_arp_suspects_admin(http, headers, event)
        elif action == "clearArpSuspects":
            return _clear_arp_suspects(http, headers, event, user_id)
        elif action == "updateArpSurgeParams":
            return _update_arp_surge_params(http, headers, event, user_id)
        elif action == "enableArpBulk":
            return _enable_arp_bulk(http, headers, event, user_id)

        # --- Snapshot Administration ---
        elif action == "listSnapshotPolicies":
            return _list_snapshot_policies(http, headers, event)
        elif action == "createSnapshotPolicy":
            return _create_snapshot_policy(http, headers, event, user_id)
        elif action == "enableSnapshotLocking":
            return _enable_snapshot_locking(http, headers, event, user_id)
        elif action == "lockSnapshot":
            return _lock_snapshot(http, headers, event, user_id)
        elif action == "assignSnapshotPolicy":
            return _assign_snapshot_policy(http, headers, event, user_id)
        elif action == "getSnapshotLockingStatus":
            return _get_snapshot_locking_status(http, headers, event)

        # --- EMS Events ---
        elif action == "getEmsEvents":
            return _get_ems_events(http, headers, event)

        # --- S3 Object Lock ---
        elif action == "getS3ObjectLockStatus":
            return _get_s3_object_lock_status(event)
        elif action == "listS3Buckets":
            return _list_s3_buckets(event)
        elif action == "putS3ObjectLockRetention":
            return _put_s3_object_lock_retention(event, user_id)

        else:
            return {"error": f"Unknown action: {action}"}

    except Exception as e:
        logger.error(f"Resource management error: {e}")
        return {"error": str(e)}


# ─── Portal Settings (DynamoDB) ───────────────────────────────────────────────


def _get_portal_settings(event):
    """Read all portal settings from DynamoDB.

    Returns: { settings: { aiAgentEnabled: bool, ... } }
    """
    if not PORTAL_SETTINGS_TABLE:
        return {"settings": {"aiAgentEnabled": False}}

    ddb = boto3.resource("dynamodb")
    table = ddb.Table(PORTAL_SETTINGS_TABLE)

    try:
        response = table.scan()
        settings = {}
        for item in response.get("Items", []):
            key = item.get("settingKey", "")
            value = item.get("settingValue", "")
            # Parse boolean strings
            if value in ("true", "True", "1"):
                settings[key] = True
            elif value in ("false", "False", "0"):
                settings[key] = False
            else:
                settings[key] = value
        return {"settings": settings}
    except Exception as e:
        logger.error(f"Failed to read portal settings: {e}")
        return {"settings": {"aiAgentEnabled": False}, "error": str(e)}


def _update_portal_settings(event, user_id):
    """Update a portal setting in DynamoDB.

    Params: { key: str, value: str }
    Only specific keys are allowed (whitelist).
    """
    if not PORTAL_SETTINGS_TABLE:
        return {"error": "Portal settings table not configured"}

    # Params are spread into event by the AppSync resolver (rm-dispatch.js)
    key = event.get("key", "")
    value = event.get("value", "")

    # Whitelist of allowed settings keys
    allowed_keys = {"aiAgentEnabled", "aiSearchEnabled"}
    if key not in allowed_keys:
        return {"error": f"Setting '{key}' is not allowed. Valid: {sorted(allowed_keys)}"}

    ddb = boto3.resource("dynamodb")
    table = ddb.Table(PORTAL_SETTINGS_TABLE)

    try:
        table.put_item(Item={
            "settingKey": key,
            "settingValue": str(value).lower(),
            "updatedBy": user_id,
        })
        logger.info(f"Portal setting updated: {key}={value} by {user_id}")
        return {"success": True, "key": key, "value": value}
    except Exception as e:
        logger.error(f"Failed to update portal setting: {e}")
        return {"error": str(e)}


# ─── Volume Management ────────────────────────────────────────────────────────


def _list_volumes(http, headers, event):
    """List volumes in the SVM.

    ONTAP REST: GET /api/storage/volumes?svm.name=<svm>&fields=...
    """
    svm = event.get("svm", SVM_NAME)
    data = _ontap_request(
        http, headers, "GET",
        f"/storage/volumes?svm.name={svm}"
        f"&fields=name,uuid,size,state,type,style,nas,space,guarantee,snaplock"
        f"&max_records=50",
    )
    if data.get("_error"):
        return {"volumes": [], "error": data["_message"]}

    volumes = []
    for v in data.get("records", []):
        space = v.get("space", {})
        volumes.append({
            "name": v.get("name", ""),
            "uuid": v.get("uuid", ""),
            "sizeBytes": v.get("size", 0),
            "sizeGiB": round(v.get("size", 0) / (1024**3), 1),
            "usedBytes": space.get("used", 0),
            "usedPercent": round(space.get("used", 0) / max(v.get("size", 1), 1) * 100, 1),
            "state": v.get("state", ""),
            "type": v.get("type", ""),
            "style": v.get("style", ""),
            "securityStyle": v.get("nas", {}).get("security_style", ""),
            "snaplockType": v.get("snaplock", {}).get("type", "non_snaplock"),
        })

    return {"volumes": volumes, "count": len(volumes), "error": None}


def _list_volumes_filtered(http, headers, event):
    """List volumes with server-side name wildcard filtering.

    ONTAP REST: GET /api/storage/volumes?name=*keyword*&svm.name=<svm>&max_records=20
    Used by VolumeSelector search for large environments (thousands of volumes).
    """
    svm = event.get("svm", SVM_NAME)
    name_filter = event.get("nameFilter", "")
    max_records = min(event.get("maxRecords", 20), 50)

    query = f"/storage/volumes?svm.name={svm}"
    query += "&fields=name,uuid,size,state,nas,snaplock"
    query += f"&max_records={max_records}"

    if name_filter:
        # ONTAP REST supports wildcard: *keyword* matches anywhere in name
        query += f"&name=*{name_filter}*"

    data = _ontap_request(http, headers, "GET", query)
    if data.get("_error"):
        return {"volumes": [], "error": data["_message"]}

    # ONTAP REST pagination: _links.next.href contains the next page URL
    next_token = None
    links = data.get("_links", {})
    if "next" in links:
        next_href = links["next"].get("href", "")
        # Extract the cursor from the next URL for client-side pagination
        next_token = next_href

    volumes = [
        {
            "name": v.get("name", ""),
            "uuid": v.get("uuid", ""),
            "sizeGiB": round(v.get("size", 0) / (1024**3), 1),
            "state": v.get("state", ""),
            "securityStyle": v.get("nas", {}).get("security_style", ""),
            "snaplockType": v.get("snaplock", {}).get("type", "non_snaplock"),
        }
        for v in data.get("records", [])
    ]
    return {"volumes": volumes, "count": len(volumes), "hasMore": next_token is not None, "error": None}


def _get_volume(http, headers, event):
    """Get detailed volume info."""
    vol_uuid = event.get("volumeUuid", "")
    if not vol_uuid:
        return {"error": "volumeUuid is required"}

    data = _ontap_request(
        http, headers, "GET",
        f"/storage/volumes/{vol_uuid}"
        f"?fields=name,uuid,size,state,type,style,nas,space,guarantee,"
        f"snapshot_policy,qos,tiering,efficiency,autosize,snaplock,anti_ransomware",
    )
    if data.get("_error"):
        return {"volume": None, "error": data["_message"]}

    return {"volume": data, "error": None}


def _create_volume(http, headers, event, user_id):
    """Create a new volume.

    ONTAP REST: POST /api/storage/volumes
    """
    svm = event.get("svm", SVM_NAME)
    name = event.get("name", "")
    size_gib = event.get("sizeGiB", 0)
    security_style = event.get("securityStyle", "unix")
    export_policy = event.get("exportPolicy", "default")

    if not name:
        return {"success": False, "error": "Volume name is required"}
    if size_gib <= 0:
        return {"success": False, "error": "Size must be > 0 GiB"}

    # ONTAP volume names: alphanumeric + underscore only
    if not all(c.isalnum() or c == "_" for c in name):
        return {"success": False, "error": "Volume name allows only alphanumeric and underscore"}

    body = {
        "name": name,
        "svm": {"name": svm},
        "size": size_gib * 1024 * 1024 * 1024,  # Convert GiB to bytes
        "nas": {
            "security_style": security_style,
            "export_policy": {"name": export_policy},
            "path": f"/{name}",
        },
    }

    # SnapLock configuration (optional — only at creation time)
    snaplock_type = event.get("snaplockType")
    if snaplock_type and snaplock_type in ("compliance", "enterprise"):
        body["snaplock"] = {
            "type": snaplock_type,
        }
        retention = {}
        if event.get("retentionDefault"):
            retention["default"] = event["retentionDefault"]
        if event.get("retentionMin"):
            retention["minimum"] = event["retentionMin"]
        if event.get("retentionMax"):
            retention["maximum"] = event["retentionMax"]
        if retention:
            body["snaplock"]["retention"] = retention

    data = _ontap_request(http, headers, "POST", "/storage/volumes", body=body)
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"Volume created: {name} ({size_gib} GiB) by {user_id}")
    return {"success": True, "volumeName": name, "error": None}


def _resize_volume(http, headers, event, user_id):
    """Resize a volume.

    ONTAP REST: PATCH /api/storage/volumes/{uuid}
    """
    vol_uuid = event.get("volumeUuid", "")
    new_size_gib = event.get("newSizeGiB", 0)

    if not vol_uuid:
        return {"success": False, "error": "volumeUuid is required"}
    if new_size_gib <= 0:
        return {"success": False, "error": "newSizeGiB must be > 0"}

    body = {"size": new_size_gib * 1024 * 1024 * 1024}
    data = _ontap_request(http, headers, "PATCH", f"/storage/volumes/{vol_uuid}", body=body)
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"Volume resized: {vol_uuid} → {new_size_gib} GiB by {user_id}")
    return {"success": True, "error": None}


def _delete_volume(http, headers, event, user_id):
    """Delete a volume (offline first, then delete).

    ONTAP REST: PATCH (offline) + DELETE /api/storage/volumes/{uuid}
    """
    vol_uuid = event.get("volumeUuid", "")
    vol_name = event.get("volumeName", "")
    confirm = event.get("confirm", False)

    if not vol_uuid:
        return {"success": False, "error": "volumeUuid is required"}
    if not confirm:
        return {"success": False, "error": "confirm=true is required for delete operations"}

    # Offline first
    offline_data = _ontap_request(
        http, headers, "PATCH", f"/storage/volumes/{vol_uuid}",
        body={"state": "offline"},
    )
    if offline_data.get("_error"):
        return {"success": False, "error": f"Failed to offline: {offline_data['_message']}"}

    # Delete
    data = _ontap_request(http, headers, "DELETE", f"/storage/volumes/{vol_uuid}")
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"Volume deleted: {vol_name} ({vol_uuid}) by {user_id}")
    return {"success": True, "error": None}


# ─── Export Policy Management ─────────────────────────────────────────────────


def _list_export_policies(http, headers, event):
    """List export policies for the SVM."""
    svm = event.get("svm", SVM_NAME)
    data = _ontap_request(
        http, headers, "GET",
        f"/protocols/nfs/export-policies?svm.name={svm}&fields=name,id,rules",
    )
    if data.get("_error"):
        return {"policies": [], "error": data["_message"]}

    policies = [
        {
            "id": p.get("id"),
            "name": p.get("name", ""),
            "ruleCount": len(p.get("rules", [])),
        }
        for p in data.get("records", [])
    ]
    return {"policies": policies, "error": None}


def _get_export_policy_rules(http, headers, event):
    """Get rules for a specific export policy."""
    policy_id = event.get("policyId", "")
    if not policy_id:
        return {"rules": [], "error": "policyId is required"}

    data = _ontap_request(
        http, headers, "GET",
        f"/protocols/nfs/export-policies/{policy_id}/rules"
        f"?fields=clients,ro_rule,rw_rule,superuser,protocols,index",
    )
    if data.get("_error"):
        return {"rules": [], "error": data["_message"]}

    rules = [
        {
            "index": r.get("index"),
            "clients": [c.get("match", "") for c in r.get("clients", [])],
            "roRule": r.get("ro_rule", []),
            "rwRule": r.get("rw_rule", []),
            "superuser": r.get("superuser", []),
            "protocols": r.get("protocols", []),
        }
        for r in data.get("records", [])
    ]
    return {"rules": rules, "policyId": policy_id, "error": None}


def _create_export_policy_rule(http, headers, event, user_id):
    """Create a new export policy rule."""
    policy_id = event.get("policyId", "")
    client_match = event.get("clientMatch", "")
    ro_rule = event.get("roRule", ["sys"])
    rw_rule = event.get("rwRule", ["sys"])
    superuser = event.get("superuser", ["sys"])
    protocols = event.get("protocols", ["any"])

    if not policy_id or not client_match:
        return {"success": False, "error": "policyId and clientMatch are required"}

    body = {
        "clients": [{"match": client_match}],
        "ro_rule": ro_rule,
        "rw_rule": rw_rule,
        "superuser": superuser,
        "protocols": protocols,
    }

    data = _ontap_request(
        http, headers, "POST",
        f"/protocols/nfs/export-policies/{policy_id}/rules",
        body=body,
    )
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"Export policy rule created: policy {policy_id}, client {client_match} by {user_id}")
    return {"success": True, "error": None}


def _delete_export_policy_rule(http, headers, event, user_id):
    """Delete an export policy rule."""
    policy_id = event.get("policyId", "")
    rule_index = event.get("ruleIndex", 0)

    if not policy_id or not rule_index:
        return {"success": False, "error": "policyId and ruleIndex are required"}

    data = _ontap_request(
        http, headers, "DELETE",
        f"/protocols/nfs/export-policies/{policy_id}/rules/{rule_index}",
    )
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"Export policy rule deleted: policy {policy_id}, index {rule_index} by {user_id}")
    return {"success": True, "error": None}


def _create_export_policy(http, headers, event, user_id):
    """Create a new export policy.

    ONTAP REST: POST /api/protocols/nfs/export-policies
    """
    svm = event.get("svm", SVM_NAME)
    name = event.get("name", "")

    if not name:
        return {"success": False, "error": "Policy name is required"}

    body = {
        "name": name,
        "svm": {"name": svm},
    }

    data = _ontap_request(http, headers, "POST", "/protocols/nfs/export-policies", body=body)
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"Export policy created: {name} by {user_id}")
    return {"success": True, "policyName": name, "error": None}


def _delete_export_policy(http, headers, event, user_id):
    """Delete an export policy.

    ONTAP REST: DELETE /api/protocols/nfs/export-policies/{id}
    Note: Cannot delete if policy is in use by a volume. ONTAP returns error.
    """
    policy_id = event.get("policyId", "")
    confirm = event.get("confirm", False)

    if not policy_id:
        return {"success": False, "error": "policyId is required"}
    if not confirm:
        return {"success": False, "error": "confirm=true is required for delete operations"}

    data = _ontap_request(http, headers, "DELETE", f"/protocols/nfs/export-policies/{policy_id}")
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"Export policy deleted: {policy_id} by {user_id}")
    return {"success": True, "error": None}


# ─── QoS Policy Management ───────────────────────────────────────────────────


def _list_qos_policies(http, headers, event):
    """List QoS policies for the SVM."""
    svm = event.get("svm", SVM_NAME)
    data = _ontap_request(
        http, headers, "GET",
        f"/storage/qos/policies?svm.name={svm}"
        f"&fields=name,uuid,fixed,adaptive",
    )
    if data.get("_error"):
        return {"policies": [], "error": data["_message"]}

    policies = []
    for p in data.get("records", []):
        fixed = p.get("fixed", {})
        adaptive = p.get("adaptive", {})
        policies.append({
            "name": p.get("name", ""),
            "uuid": p.get("uuid", ""),
            "type": "adaptive" if adaptive else "fixed",
            "maxThroughputIops": fixed.get("max_throughput_iops"),
            "maxThroughputMbps": fixed.get("max_throughput_mbps"),
            "expectedIops": adaptive.get("expected_iops"),
            "peakIops": adaptive.get("peak_iops"),
        })

    return {"policies": policies, "error": None}


def _create_qos_policy(http, headers, event, user_id):
    """Create a new QoS policy."""
    svm = event.get("svm", SVM_NAME)
    name = event.get("name", "")
    policy_type = event.get("policyType", "fixed")  # "fixed" or "adaptive"
    max_iops = event.get("maxIops")
    max_mbps = event.get("maxMbps")
    expected_iops = event.get("expectedIops")
    peak_iops = event.get("peakIops")

    if not name:
        return {"success": False, "error": "Policy name is required"}

    body: dict = {
        "name": name,
        "svm": {"name": svm},
    }

    if policy_type == "fixed":
        fixed: dict = {}
        if max_iops:
            fixed["max_throughput_iops"] = max_iops
        if max_mbps:
            fixed["max_throughput_mbps"] = max_mbps
        if not fixed:
            return {"success": False, "error": "At least one of maxIops or maxMbps is required for fixed policy"}
        body["fixed"] = fixed
    elif policy_type == "adaptive":
        if not expected_iops or not peak_iops:
            return {"success": False, "error": "expectedIops and peakIops are required for adaptive policy"}
        body["adaptive"] = {
            "expected_iops": expected_iops,
            "peak_iops": peak_iops,
        }

    data = _ontap_request(http, headers, "POST", "/storage/qos/policies", body=body)
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"QoS policy created: {name} by {user_id}")
    return {"success": True, "policyName": name, "error": None}


def _update_qos_policy(http, headers, event, user_id):
    """Update an existing QoS policy."""
    policy_uuid = event.get("policyUuid", "")
    max_iops = event.get("maxIops")
    max_mbps = event.get("maxMbps")
    expected_iops = event.get("expectedIops")
    peak_iops = event.get("peakIops")

    if not policy_uuid:
        return {"success": False, "error": "policyUuid is required"}

    body: dict = {}
    if max_iops is not None or max_mbps is not None:
        fixed: dict = {}
        if max_iops is not None:
            fixed["max_throughput_iops"] = max_iops
        if max_mbps is not None:
            fixed["max_throughput_mbps"] = max_mbps
        body["fixed"] = fixed
    elif expected_iops is not None or peak_iops is not None:
        adaptive: dict = {}
        if expected_iops is not None:
            adaptive["expected_iops"] = expected_iops
        if peak_iops is not None:
            adaptive["peak_iops"] = peak_iops
        body["adaptive"] = adaptive

    if not body:
        return {"success": False, "error": "No changes specified"}

    data = _ontap_request(http, headers, "PATCH", f"/storage/qos/policies/{policy_uuid}", body=body)
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"QoS policy updated: {policy_uuid} by {user_id}")
    return {"success": True, "error": None}


def _delete_qos_policy(http, headers, event, user_id):
    """Delete a QoS policy."""
    policy_uuid = event.get("policyUuid", "")
    if not policy_uuid:
        return {"success": False, "error": "policyUuid is required"}

    data = _ontap_request(http, headers, "DELETE", f"/storage/qos/policies/{policy_uuid}")
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"QoS policy deleted: {policy_uuid} by {user_id}")
    return {"success": True, "error": None}


def _assign_qos_to_volume(http, headers, event, user_id):
    """Assign a QoS policy to a volume."""
    vol_uuid = event.get("volumeUuid", "")
    policy_name = event.get("policyName", "")

    if not vol_uuid or not policy_name:
        return {"success": False, "error": "volumeUuid and policyName are required"}

    body = {"qos": {"policy": {"name": policy_name}}}
    data = _ontap_request(http, headers, "PATCH", f"/storage/volumes/{vol_uuid}", body=body)
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"QoS policy '{policy_name}' assigned to volume {vol_uuid} by {user_id}")
    return {"success": True, "error": None}


# ─── SnapLock Management ─────────────────────────────────────────────────────


def _get_snaplock_config(http, headers, event):
    """Get SnapLock configuration for a volume."""
    vol_uuid = event.get("volumeUuid", "")
    if not vol_uuid:
        # Try resolving by name
        vol_name = event.get("volumeName", "")
        svm = event.get("svm", SVM_NAME)
        if vol_name:
            resolve = _ontap_request(
                http, headers, "GET",
                f"/storage/volumes?name={vol_name}&svm.name={svm}&fields=uuid",
            )
            records = resolve.get("records", [])
            if records:
                vol_uuid = records[0]["uuid"]
            else:
                return {"config": None, "error": f"Volume '{vol_name}' not found"}
        else:
            return {"config": None, "error": "volumeUuid or volumeName is required"}

    data = _ontap_request(
        http, headers, "GET",
        f"/storage/volumes/{vol_uuid}?fields=snaplock,name",
    )
    if data.get("_error"):
        return {"config": None, "error": data["_message"]}

    snaplock = data.get("snaplock", {})
    return {
        "config": {
            "volumeName": data.get("name", ""),
            "type": snaplock.get("type", "non_snaplock"),
            "isEnabled": snaplock.get("type", "non_snaplock") != "non_snaplock",
            "complianceClockTime": snaplock.get("compliance_clock_time"),
            "retentionDefault": snaplock.get("retention", {}).get("default"),
            "retentionMinimum": snaplock.get("retention", {}).get("minimum"),
            "retentionMaximum": snaplock.get("retention", {}).get("maximum"),
            "autocommitPeriod": snaplock.get("autocommit_period"),
        },
        "error": None,
    }


def _update_snaplock_retention(http, headers, event, user_id):
    """Update SnapLock default retention period.

    ONTAP REST: PATCH /api/storage/volumes/{uuid}
    Body: {"snaplock": {"retention": {"default": "P{days}D"}}}
    """
    vol_uuid = event.get("volumeUuid", "")
    days = event.get("days", 0)

    if not vol_uuid:
        return {"success": False, "error": "volumeUuid is required"}
    if days <= 0:
        return {"success": False, "error": "days must be > 0"}

    duration = f"P{days}D"
    body = {"snaplock": {"retention": {"default": duration}}}

    data = _ontap_request(http, headers, "PATCH", f"/storage/volumes/{vol_uuid}", body=body)
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"SnapLock retention updated to {days} days for {vol_uuid} by {user_id}")
    return {"success": True, "error": None}


# ─── Quota Management ─────────────────────────────────────────────────────────


def _list_quota_rules(http, headers, event):
    """List quota rules for volumes in the SVM.

    ONTAP REST: GET /api/storage/quota/rules
    """
    svm = event.get("svm", SVM_NAME)
    vol_name = event.get("volumeName", "")
    params = f"svm.name={svm}&fields=type,qtree.name,users.name,group.name,space,files,volume.name"
    if vol_name:
        params += f"&volume.name={vol_name}"
    params += "&max_records=50"

    data = _ontap_request(http, headers, "GET", f"/storage/quota/rules?{params}")
    if data.get("_error"):
        return {"rules": [], "error": data["_message"]}

    rules = []
    for r in data.get("records", []):
        space = r.get("space", {})
        files = r.get("files", {})
        rules.append({
            "uuid": r.get("uuid", ""),
            "type": r.get("type", ""),  # "tree", "user", "group"
            "volumeName": r.get("volume", {}).get("name", ""),
            "qtreeName": r.get("qtree", {}).get("name", ""),
            "users": [u.get("name", "") for u in r.get("users", [])],
            "groupName": r.get("group", {}).get("name", ""),
            "spaceHardLimit": space.get("hard_limit"),
            "spaceSoftLimit": space.get("soft_limit"),
            "filesHardLimit": files.get("hard_limit"),
            "filesSoftLimit": files.get("soft_limit"),
        })

    return {"rules": rules, "count": len(rules), "error": None}


def _get_quota_report(http, headers, event):
    """Get quota usage report (actual consumption vs limits).

    ONTAP REST: GET /api/storage/quota/reports
    """
    svm = event.get("svm", SVM_NAME)
    vol_name = event.get("volumeName", "")
    params = f"svm.name={svm}&fields=space,files,users.name,group.name,qtree.name,type,volume.name"
    if vol_name:
        params += f"&volume.name={vol_name}"
    params += "&max_records=50"

    data = _ontap_request(http, headers, "GET", f"/storage/quota/reports?{params}")
    if data.get("_error"):
        return {"entries": [], "error": data["_message"]}

    entries = []
    for r in data.get("records", []):
        space = r.get("space", {})
        files = r.get("files", {})
        entries.append({
            "type": r.get("type", ""),
            "volumeName": r.get("volume", {}).get("name", ""),
            "qtreeName": r.get("qtree", {}).get("name", ""),
            "users": [u.get("name", "") for u in r.get("users", [])],
            "groupName": r.get("group", {}).get("name", ""),
            "spaceUsed": space.get("used", {}).get("total", 0),
            "spaceHardLimit": space.get("hard_limit", 0),
            "spaceSoftLimit": space.get("soft_limit", 0),
            "spaceUsedPercent": round(
                space.get("used", {}).get("total", 0) / max(space.get("hard_limit", 1), 1) * 100, 1
            ) if space.get("hard_limit") else 0,
            "filesUsed": files.get("used", {}).get("total", 0),
            "filesHardLimit": files.get("hard_limit", 0),
        })

    return {"entries": entries, "count": len(entries), "error": None}


def _create_quota_rule(http, headers, event, user_id):
    """Create a quota rule.

    ONTAP REST: POST /api/storage/quota/rules
    Types: "tree" (per qtree), "user" (per user), "group" (per group)
    """
    svm = event.get("svm", SVM_NAME)
    vol_name = event.get("volumeName", "")
    rule_type = event.get("type", "tree")  # "tree", "user", "group"
    qtree_name = event.get("qtreeName", "")
    user_name = event.get("userName", "")
    group_name = event.get("groupName", "")
    space_hard = event.get("spaceHardLimitGiB", 0)
    space_soft = event.get("spaceSoftLimitGiB", 0)
    files_hard = event.get("filesHardLimit", 0)

    if not vol_name:
        return {"success": False, "error": "volumeName is required"}

    body: dict = {
        "svm": {"name": svm},
        "volume": {"name": vol_name},
        "type": rule_type,
    }

    if rule_type == "tree" and qtree_name:
        body["qtree"] = {"name": qtree_name}
    elif rule_type == "user" and user_name:
        body["users"] = [{"name": user_name}]
    elif rule_type == "group" and group_name:
        body["group"] = {"name": group_name}

    space: dict = {}
    if space_hard > 0:
        space["hard_limit"] = space_hard * 1024 * 1024 * 1024
    if space_soft > 0:
        space["soft_limit"] = space_soft * 1024 * 1024 * 1024
    if space:
        body["space"] = space

    files: dict = {}
    if files_hard > 0:
        files["hard_limit"] = files_hard
    if files:
        body["files"] = files

    data = _ontap_request(http, headers, "POST", "/storage/quota/rules", body=body)
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"Quota rule created: {rule_type} on {vol_name} by {user_id}")
    return {"success": True, "error": None}


def _delete_quota_rule(http, headers, event, user_id):
    """Delete a quota rule."""
    rule_uuid = event.get("ruleUuid", "")
    if not rule_uuid:
        return {"success": False, "error": "ruleUuid is required"}

    data = _ontap_request(http, headers, "DELETE", f"/storage/quota/rules/{rule_uuid}")
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"Quota rule deleted: {rule_uuid} by {user_id}")
    return {"success": True, "error": None}


# ─── CIFS/SMB Share Management ────────────────────────────────────────────────


def _list_cifs_shares(http, headers, event):
    """List CIFS/SMB shares for the SVM.

    ONTAP REST: GET /api/protocols/cifs/shares
    """
    svm = event.get("svm", SVM_NAME)
    data = _ontap_request(
        http, headers, "GET",
        f"/protocols/cifs/shares?svm.name={svm}"
        f"&fields=name,path,comment,acls,encryption,continuously_available"
        f"&max_records=50",
    )
    if data.get("_error"):
        return {"shares": [], "error": data["_message"]}

    shares = []
    for s in data.get("records", []):
        shares.append({
            "name": s.get("name", ""),
            "path": s.get("path", ""),
            "comment": s.get("comment", ""),
            "encryption": s.get("encryption", False),
            "continuouslyAvailable": s.get("continuously_available", False),
            "aclCount": len(s.get("acls", [])),
        })

    return {"shares": shares, "count": len(shares), "error": None}


def _create_cifs_share(http, headers, event, user_id):
    """Create a CIFS/SMB share.

    ONTAP REST: POST /api/protocols/cifs/shares
    """
    svm = event.get("svm", SVM_NAME)
    name = event.get("name", "")
    path = event.get("path", "")
    comment = event.get("comment", "")

    if not name or not path:
        return {"success": False, "error": "name and path are required"}

    body: dict = {
        "svm": {"name": svm},
        "name": name,
        "path": path,
    }
    if comment:
        body["comment"] = comment

    data = _ontap_request(http, headers, "POST", "/protocols/cifs/shares", body=body)
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"CIFS share created: {name} → {path} by {user_id}")
    return {"success": True, "shareName": name, "error": None}


def _update_cifs_share(http, headers, event, user_id):
    """Update CIFS share properties (encryption, continuously_available).

    ONTAP REST: PATCH /api/protocols/cifs/shares/{svm.uuid}/{share_name}
    Used for toggling SMB 3.0 in-transit encryption.
    Note: FSx for ONTAP always encrypts data at rest via KMS — this controls SMB protocol-level encryption.
    """
    svm = event.get("svm", SVM_NAME)
    share_name = event.get("name", "")
    encryption = event.get("encryption")
    continuously_available = event.get("continuouslyAvailable")

    if not share_name:
        return {"success": False, "error": "name is required"}

    # Get SVM UUID
    svm_data = _ontap_request(http, headers, "GET", f"/svm/svms?name={svm}&fields=uuid")
    svm_records = svm_data.get("records", [])
    if not svm_records:
        return {"success": False, "error": f"SVM '{svm}' not found"}
    svm_uuid = svm_records[0]["uuid"]

    body: dict = {}
    if encryption is not None:
        body["encryption"] = bool(encryption)
    if continuously_available is not None:
        body["continuously_available"] = bool(continuously_available)

    if not body:
        return {"success": False, "error": "No changes specified"}

    data = _ontap_request(
        http, headers, "PATCH",
        f"/protocols/cifs/shares/{svm_uuid}/{share_name}",
        body=body,
    )
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"CIFS share updated: {share_name} ({body}) by {user_id}")
    return {"success": True, "error": None}


def _delete_cifs_share(http, headers, event, user_id):
    """Delete a CIFS/SMB share.

    ONTAP REST: DELETE /api/protocols/cifs/shares/{svm.uuid}/{share_name}
    """
    svm = event.get("svm", SVM_NAME)
    share_name = event.get("name", "")
    confirm = event.get("confirm", False)

    if not share_name:
        return {"success": False, "error": "name is required"}
    if not confirm:
        return {"success": False, "error": "confirm=true is required"}

    # Get SVM UUID
    svm_data = _ontap_request(http, headers, "GET", f"/svm/svms?name={svm}&fields=uuid")
    svm_records = svm_data.get("records", [])
    if not svm_records:
        return {"success": False, "error": f"SVM '{svm}' not found"}
    svm_uuid = svm_records[0]["uuid"]

    data = _ontap_request(http, headers, "DELETE", f"/protocols/cifs/shares/{svm_uuid}/{share_name}")
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"CIFS share deleted: {share_name} by {user_id}")
    return {"success": True, "error": None}


# ─── Qtree Management ─────────────────────────────────────────────────────────


def _list_qtrees(http, headers, event):
    """List qtrees for volumes in the SVM.

    ONTAP REST: GET /api/storage/qtrees
    """
    svm = event.get("svm", SVM_NAME)
    vol_name = event.get("volumeName", "")
    params = f"svm.name={svm}&fields=name,id,volume.name,security_style,export_policy.name,unix_permissions"
    if vol_name:
        params += f"&volume.name={vol_name}"
    params += "&max_records=100"

    data = _ontap_request(http, headers, "GET", f"/storage/qtrees?{params}")
    if data.get("_error"):
        return {"qtrees": [], "error": data["_message"]}

    qtrees = []
    for q in data.get("records", []):
        qtrees.append({
            "id": q.get("id"),
            "name": q.get("name", ""),
            "volumeName": q.get("volume", {}).get("name", ""),
            "securityStyle": q.get("security_style", ""),
            "exportPolicy": q.get("export_policy", {}).get("name", ""),
            "unixPermissions": q.get("unix_permissions", ""),
        })

    return {"qtrees": qtrees, "count": len(qtrees), "error": None}


def _create_qtree(http, headers, event, user_id):
    """Create a qtree in a volume.

    ONTAP REST: POST /api/storage/qtrees
    """
    svm = event.get("svm", SVM_NAME)
    vol_name = event.get("volumeName", "")
    qtree_name = event.get("name", "")
    security_style = event.get("securityStyle", "unix")
    export_policy = event.get("exportPolicy", "default")

    if not vol_name or not qtree_name:
        return {"success": False, "error": "volumeName and name are required"}

    body = {
        "svm": {"name": svm},
        "volume": {"name": vol_name},
        "name": qtree_name,
        "security_style": security_style,
        "export_policy": {"name": export_policy},
    }

    data = _ontap_request(http, headers, "POST", "/storage/qtrees", body=body)
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"Qtree created: {vol_name}/{qtree_name} by {user_id}")
    return {"success": True, "qtreeName": qtree_name, "error": None}


def _delete_qtree(http, headers, event, user_id):
    """Delete a qtree.

    ONTAP REST: DELETE /api/storage/qtrees/{volume.uuid}/{qtree.id}
    """
    vol_name = event.get("volumeName", "")
    qtree_id = event.get("qtreeId", "")
    confirm = event.get("confirm", False)
    svm = event.get("svm", SVM_NAME)

    if not vol_name or not qtree_id:
        return {"success": False, "error": "volumeName and qtreeId are required"}
    if not confirm:
        return {"success": False, "error": "confirm=true is required"}

    # Get volume UUID
    vol_data = _ontap_request(
        http, headers, "GET",
        f"/storage/volumes?name={vol_name}&svm.name={svm}&fields=uuid",
    )
    vol_records = vol_data.get("records", [])
    if not vol_records:
        return {"success": False, "error": f"Volume '{vol_name}' not found"}
    vol_uuid = vol_records[0]["uuid"]

    data = _ontap_request(http, headers, "DELETE", f"/storage/qtrees/{vol_uuid}/{qtree_id}")
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"Qtree deleted: {vol_name}/{qtree_id} by {user_id}")
    return {"success": True, "error": None}


# ─── Storage Efficiency ───────────────────────────────────────────────────────


def _get_efficiency_stats(http, headers, event):
    """Get storage efficiency stats (dedup, compression, savings).

    ONTAP REST: GET /api/storage/volumes?fields=efficiency,space
    """
    svm = event.get("svm", SVM_NAME)
    data = _ontap_request(
        http, headers, "GET",
        f"/storage/volumes?svm.name={svm}"
        f"&fields=name,efficiency,space"
        f"&max_records=50",
    )
    if data.get("_error"):
        return {"volumes": [], "error": data["_message"]}

    volumes = []
    total_logical = 0
    total_physical = 0

    for v in data.get("records", []):
        eff = v.get("efficiency", {})
        space = v.get("space", {})
        logical = space.get("logical_space", {}).get("used", 0)
        physical = space.get("used", 0)
        total_logical += logical
        total_physical += physical

        volumes.append({
            "name": v.get("name", ""),
            "dedupe": eff.get("dedupe", "none"),
            "compression": eff.get("compression", "none"),
            "crossVolumeDeduplication": eff.get("cross_volume_dedupe", "none"),
            "compaction": eff.get("compaction", "none"),
            "logicalUsedBytes": logical,
            "physicalUsedBytes": physical,
            "savingsRatio": round(logical / max(physical, 1), 2),
            "savingsPercent": round((1 - physical / max(logical, 1)) * 100, 1) if logical > 0 else 0,
        })

    overall_ratio = round(total_logical / max(total_physical, 1), 2) if total_physical > 0 else 1.0
    overall_savings = round((1 - total_physical / max(total_logical, 1)) * 100, 1) if total_logical > 0 else 0

    return {
        "volumes": volumes,
        "summary": {
            "totalLogicalBytes": total_logical,
            "totalPhysicalBytes": total_physical,
            "overallRatio": overall_ratio,
            "overallSavingsPercent": overall_savings,
        },
        "error": None,
    }


# ─── ARP/AI Administration ────────────────────────────────────────────────────


def _list_arp_volumes(http, headers, event):
    """List all volumes with their ARP/AI status.

    Returns per-volume ARP state to give administrators an overview of
    which volumes are protected, learning, or unprotected.

    ONTAP REST: GET /api/storage/volumes?fields=anti_ransomware,nas,san
    """
    svm = event.get("svm", SVM_NAME)
    data = _ontap_request(
        http, headers, "GET",
        f"/storage/volumes?svm.name={svm}"
        f"&fields=name,uuid,anti_ransomware,type,nas,size"
        f"&max_records=100",
    )
    if data.get("_error"):
        return {"volumes": [], "error": data["_message"]}

    volumes = []
    for v in data.get("records", []):
        arp = v.get("anti_ransomware", {})
        nas = v.get("nas", {})
        vol_type = v.get("type", "rw")
        # Determine if this is a NAS or SAN volume
        is_san = not bool(nas.get("path"))  # No junction path = likely SAN

        volumes.append({
            "name": v.get("name", ""),
            "uuid": v.get("uuid", ""),
            "state": arp.get("state", "disabled"),
            "attackProbability": arp.get("attack_probability", "none"),
            "dryRunStartTime": arp.get("dry_run_start_time"),
            "surgeAsNormal": arp.get("surge_as_normal", False),
            "volumeType": "SAN" if is_san else "NAS",
            "sizeGiB": round(v.get("size", 0) / (1024**3), 1),
            "type": vol_type,
        })

    # Summary counts
    enabled_count = sum(1 for v in volumes if v["state"] == "enabled")
    learning_count = sum(1 for v in volumes if v["state"] == "dry_run")
    disabled_count = sum(1 for v in volumes if v["state"] == "disabled")

    return {
        "volumes": volumes,
        "summary": {
            "total": len(volumes),
            "enabled": enabled_count,
            "learning": learning_count,
            "disabled": disabled_count,
        },
        "error": None,
    }


def _update_arp_state_admin(http, headers, event, user_id):
    """Update ARP/AI state for a volume (admin version with all transitions).

    Valid states:
    - disabled: ARP monitoring off
    - dry_run: Learning mode (classic ARP — 30 day recommended learning period)
    - enabled: Active protection (ARP/AI skips learning; classic ARP requires prior dry_run)
    - paused: Temporarily suspend monitoring without losing learned patterns

    For ARP/AI (ONTAP 9.16+):
    - Can go directly disabled → enabled (no learning period needed)
    - AI model is pre-trained on known ransomware patterns

    For classic ARP (pre-9.16):
    - Must go disabled → dry_run → enabled (30-day learning recommended)
    - Learning period establishes baseline file activity patterns

    For SAN volumes (ONTAP 9.17.1+):
    - Same state transitions as NAS
    - Detection is entropy-based only (no file-level analysis)

    ONTAP REST: PATCH /api/storage/volumes/{uuid}
    Body: {"anti_ransomware": {"state": "<new_state>"}}
    """
    vol_uuid = event.get("volumeUuid", "")
    new_state = event.get("state", "")

    if not vol_uuid:
        return {"success": False, "error": "volumeUuid is required"}

    valid_states = {"disabled", "dry_run", "enabled", "paused"}
    if new_state not in valid_states:
        return {
            "success": False,
            "error": f"Invalid state: '{new_state}'. Valid states: {', '.join(sorted(valid_states))}",
        }

    body = {"anti_ransomware": {"state": new_state}}
    data = _ontap_request(http, headers, "PATCH", f"/storage/volumes/{vol_uuid}", body=body)
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"ARP state updated: volume {vol_uuid} → '{new_state}' by {user_id}")
    return {"success": True, "newState": new_state, "error": None}


def _get_arp_suspects_admin(http, headers, event):
    """Get ARP suspect files for a volume (admin view with full details).

    ONTAP REST: GET /api/security/anti-ransomware/suspects

    For NAS volumes: Returns file paths, types, and suspect time.
    For SAN volumes: Returns volume-level entropy spikes only
    (individual files inside LUNs/NVMe namespaces are not visible to ARP).
    """
    vol_uuid = event.get("volumeUuid", "")
    if not vol_uuid:
        return {"suspects": [], "error": "volumeUuid is required"}

    try:
        data = _ontap_request(
            http, headers, "GET",
            f"/security/anti-ransomware/suspects"
            f"?volume.uuid={vol_uuid}"
            f"&fields=file.path,file.type,suspect_time,file.entropy",
        )
        if data.get("_error"):
            return {"suspects": [], "error": data["_message"]}

        suspects = []
        for s in data.get("records", []):
            file_info = s.get("file", {})
            suspects.append({
                "filePath": file_info.get("path", ""),
                "fileType": file_info.get("type", ""),
                "entropy": file_info.get("entropy"),
                "suspectTime": s.get("suspect_time", ""),
            })

        return {
            "suspects": suspects,
            "count": len(suspects),
            "error": None,
        }
    except Exception as e:
        return {"suspects": [], "count": 0, "error": str(e)}


def _clear_arp_suspects(http, headers, event, user_id):
    """Clear ARP suspect files (mark as false positive).

    After investigation, admin can clear suspects to acknowledge them as
    normal activity. This removes the suspect status and returns the
    volume to normal monitoring.

    ONTAP REST: POST /api/security/anti-ransomware/suspects/{volume.uuid}/clear
    (or via volume PATCH with acknowledge)
    """
    vol_uuid = event.get("volumeUuid", "")
    if not vol_uuid:
        return {"success": False, "error": "volumeUuid is required"}

    # Clear suspects by acknowledging the attack report as false positive
    # This is done via PATCH on the volume's anti_ransomware state
    body = {"anti_ransomware": {"state": "enabled"}}
    data = _ontap_request(http, headers, "PATCH", f"/storage/volumes/{vol_uuid}", body=body)
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"ARP suspects cleared for volume {vol_uuid} by {user_id}")
    return {"success": True, "error": None}


def _update_arp_surge_params(http, headers, event, user_id):
    """Mark current activity surge as normal (tune false positives).

    When ARP detects a surge that is actually normal activity (e.g., a
    quarterly report generation), the admin can tell ARP to treat this
    pattern as baseline.

    ONTAP REST: PATCH /api/storage/volumes/{uuid}
    Body: {"anti_ransomware": {"surge_as_normal": true}}

    Available since ONTAP 9.11.1.
    """
    vol_uuid = event.get("volumeUuid", "")
    surge_as_normal = event.get("surgeAsNormal", True)

    if not vol_uuid:
        return {"success": False, "error": "volumeUuid is required"}

    body = {"anti_ransomware": {"surge_as_normal": surge_as_normal}}
    data = _ontap_request(http, headers, "PATCH", f"/storage/volumes/{vol_uuid}", body=body)
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"ARP surge_as_normal={surge_as_normal} for volume {vol_uuid} by {user_id}")
    return {"success": True, "error": None}


def _enable_arp_bulk(http, headers, event, user_id):
    """Enable ARP on multiple volumes at once.

    Useful for initial rollout: enable ARP/AI on all unprotected volumes,
    or start learning mode on all volumes simultaneously.

    Processes volumes sequentially. Returns per-volume results.
    """
    vol_uuids = event.get("volumeUuids", [])
    target_state = event.get("state", "enabled")

    if not vol_uuids:
        return {"success": False, "results": [], "error": "volumeUuids list is required"}

    valid_states = {"dry_run", "enabled"}
    if target_state not in valid_states:
        return {"success": False, "results": [], "error": f"Bulk enable only supports: {valid_states}"}

    results = []
    for vol_uuid in vol_uuids:
        body = {"anti_ransomware": {"state": target_state}}
        data = _ontap_request(http, headers, "PATCH", f"/storage/volumes/{vol_uuid}", body=body)
        if data.get("_error"):
            results.append({"uuid": vol_uuid, "success": False, "error": data["_message"]})
        else:
            results.append({"uuid": vol_uuid, "success": True})

    success_count = sum(1 for r in results if r["success"])
    logger.info(
        f"ARP bulk enable: {success_count}/{len(vol_uuids)} → '{target_state}' by {user_id}"
    )

    return {
        "success": success_count == len(vol_uuids),
        "results": results,
        "successCount": success_count,
        "totalCount": len(vol_uuids),
        "error": None if success_count == len(vol_uuids) else "Some volumes failed",
    }


# ─── Snapshot Administration ──────────────────────────────────────────────────


def _list_snapshot_policies(http, headers, event):
    """List snapshot policies.

    ONTAP REST: GET /api/storage/snapshot-policies
    """
    svm = event.get("svm", SVM_NAME)
    data = _ontap_request(
        http, headers, "GET",
        f"/storage/snapshot-policies?svm.name={svm}"
        f"&fields=name,uuid,enabled,copies,comment,scope"
        f"&max_records=50",
    )
    if data.get("_error"):
        return {"policies": [], "error": data["_message"]}

    policies = []
    for p in data.get("records", []):
        copies = p.get("copies", [])
        policies.append({
            "name": p.get("name", ""),
            "uuid": p.get("uuid", ""),
            "enabled": p.get("enabled", True),
            "comment": p.get("comment", ""),
            "scope": p.get("scope", ""),
            "scheduleCount": len(copies),
            "schedules": [
                {
                    "schedule": c.get("schedule", {}).get("name", ""),
                    "count": c.get("count", 0),
                    "prefix": c.get("prefix", ""),
                    "retentionPeriod": c.get("retention_period", ""),
                }
                for c in copies
            ],
        })

    return {"policies": policies, "count": len(policies), "error": None}


def _create_snapshot_policy(http, headers, event, user_id):
    """Create a snapshot policy with schedules.

    ONTAP REST: POST /api/storage/snapshot-policies
    """
    svm = event.get("svm", SVM_NAME)
    name = event.get("name", "")
    comment = event.get("comment", "")
    schedules = event.get("schedules", [])

    if not name:
        return {"success": False, "error": "Policy name is required"}
    if not schedules:
        return {"success": False, "error": "At least one schedule is required"}

    copies = []
    for s in schedules:
        copy: dict = {
            "schedule": {"name": s.get("schedule", "daily")},
            "count": s.get("count", 7),
        }
        if s.get("prefix"):
            copy["prefix"] = s["prefix"]
        if s.get("retentionPeriod"):
            copy["retention_period"] = s["retentionPeriod"]
        copies.append(copy)

    body: dict = {
        "name": name,
        "svm": {"name": svm},
        "enabled": True,
        "copies": copies,
    }
    if comment:
        body["comment"] = comment

    data = _ontap_request(http, headers, "POST", "/storage/snapshot-policies", body=body)
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"Snapshot policy created: {name} with {len(copies)} schedules by {user_id}")
    return {"success": True, "policyName": name, "error": None}


def _enable_snapshot_locking(http, headers, event, user_id):
    """Enable tamperproof snapshot locking on a volume.

    Once enabled, snapshots on this volume can be locked with a retention
    period. Locked snapshots cannot be deleted until the retention expires.

    ONTAP REST: PATCH /api/storage/volumes/{uuid}
    Body: {"snapshot_locking_enabled": true}

    Note: This is a one-way operation on Compliance volumes — cannot be disabled.
    On Enterprise volumes, it can be toggled.
    """
    vol_uuid = event.get("volumeUuid", "")
    enabled = event.get("enabled", True)

    if not vol_uuid:
        return {"success": False, "error": "volumeUuid is required"}

    body = {"snapshot_locking_enabled": enabled}
    data = _ontap_request(http, headers, "PATCH", f"/storage/volumes/{vol_uuid}", body=body)
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"Snapshot locking {'enabled' if enabled else 'disabled'} for volume {vol_uuid} by {user_id}")
    return {"success": True, "error": None}


def _lock_snapshot(http, headers, event, user_id):
    """Lock a snapshot with a retention period (tamperproof).

    ONTAP REST: PATCH /api/storage/volumes/{vol_uuid}/snapshots/{snap_uuid}
    Body: {"expiry_time": "2026-12-31T23:59:59Z"}

    The expiry_time must be in the future. Once set, the snapshot cannot be
    deleted until the expiry time passes.
    """
    vol_uuid = event.get("volumeUuid", "")
    snap_uuid = event.get("snapshotUuid", "")
    retention_days = event.get("retentionDays", 30)

    if not vol_uuid or not snap_uuid:
        return {"success": False, "error": "volumeUuid and snapshotUuid are required"}
    if retention_days <= 0:
        return {"success": False, "error": "retentionDays must be > 0"}

    from datetime import datetime, timezone, timedelta
    expiry = (datetime.now(timezone.utc) + timedelta(days=retention_days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    body = {"expiry_time": expiry}
    data = _ontap_request(
        http, headers, "PATCH",
        f"/storage/volumes/{vol_uuid}/snapshots/{snap_uuid}",
        body=body,
    )
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"Snapshot locked: {snap_uuid} for {retention_days} days (expires {expiry}) by {user_id}")
    return {"success": True, "expiryTime": expiry, "retentionDays": retention_days, "error": None}


def _assign_snapshot_policy(http, headers, event, user_id):
    """Assign a snapshot policy to a volume.

    ONTAP REST: PATCH /api/storage/volumes/{uuid}
    Body: {"snapshot_policy": {"name": "<policy_name>"}}
    """
    vol_uuid = event.get("volumeUuid", "")
    policy_name = event.get("policyName", "")

    if not vol_uuid or not policy_name:
        return {"success": False, "error": "volumeUuid and policyName are required"}

    body = {"snapshot_policy": {"name": policy_name}}
    data = _ontap_request(http, headers, "PATCH", f"/storage/volumes/{vol_uuid}", body=body)
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"Snapshot policy '{policy_name}' assigned to volume {vol_uuid} by {user_id}")
    return {"success": True, "error": None}


def _get_snapshot_locking_status(http, headers, event):
    """Get snapshot locking configuration for a volume.

    Returns whether tamperproof locking is enabled and the current
    locked snapshot count.
    """
    vol_uuid = event.get("volumeUuid", "")
    if not vol_uuid:
        return {"config": None, "error": "volumeUuid is required"}

    data = _ontap_request(
        http, headers, "GET",
        f"/storage/volumes/{vol_uuid}?fields=name,snapshot_locking_enabled,snapshot_policy",
    )
    if data.get("_error"):
        return {"config": None, "error": data["_message"]}

    # Count locked snapshots
    snap_data = _ontap_request(
        http, headers, "GET",
        f"/storage/volumes/{vol_uuid}/snapshots?fields=expiry_time,snaplock_expiry_time&max_records=100",
    )
    locked_count = 0
    for s in snap_data.get("records", []):
        if s.get("expiry_time") or s.get("snaplock_expiry_time"):
            locked_count += 1

    return {
        "config": {
            "volumeName": data.get("name", ""),
            "snapshotLockingEnabled": data.get("snapshot_locking_enabled", False),
            "snapshotPolicy": data.get("snapshot_policy", {}).get("name", ""),
            "lockedSnapshotCount": locked_count,
            "totalSnapshotCount": snap_data.get("num_records", 0),
        },
        "error": None,
    }


# ─── S3 Object Lock ──────────────────────────────────────────────────────────

S3_OBJECT_LOCK_BUCKET = os.environ.get("S3_OBJECT_LOCK_BUCKET", "")


def _get_s3_object_lock_status(event):
    """Get S3 Object Lock configuration for the configured output bucket.

    AWS API: s3:GetObjectLockConfiguration
    This does NOT require ONTAP connectivity — it's a pure S3 API call.
    """
    bucket = event.get("bucket") or S3_OBJECT_LOCK_BUCKET

    if not bucket:
        return {
            "configured": False,
            "bucket": None,
            "objectLockEnabled": False,
            "defaultRetention": None,
            "error": None,
            "message": "No S3 Object Lock bucket configured. Set S3_OBJECT_LOCK_BUCKET to enable.",
        }

    try:
        s3 = boto3.client("s3")
        response = s3.get_object_lock_configuration(Bucket=bucket)
        config = response.get("ObjectLockConfiguration", {})
        rule = config.get("Rule", {})
        retention = rule.get("DefaultRetention", {})

        return {
            "configured": True,
            "bucket": bucket,
            "objectLockEnabled": config.get("ObjectLockEnabled") == "Enabled",
            "defaultRetention": {
                "mode": retention.get("Mode", ""),
                "days": retention.get("Days"),
                "years": retention.get("Years"),
            } if retention else None,
            "error": None,
        }
    except s3.exceptions.ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        if error_code == "ObjectLockConfigurationNotFoundError":
            return {
                "configured": True,
                "bucket": bucket,
                "objectLockEnabled": False,
                "defaultRetention": None,
                "error": None,
                "message": "Bucket exists but Object Lock is not enabled.",
            }
        return {
            "configured": False,
            "bucket": bucket,
            "objectLockEnabled": False,
            "defaultRetention": None,
            "error": str(e),
        }
    except Exception as e:
        return {
            "configured": False,
            "bucket": bucket,
            "objectLockEnabled": False,
            "defaultRetention": None,
            "error": str(e),
        }


def _list_s3_buckets(event):
    """List S3 buckets (name only, fast).

    Filters by name if provided. Does NOT check Object Lock status per bucket
    (that would timeout with many buckets). Lock status is checked individually
    via getS3ObjectLockStatus when a bucket is selected.
    """
    name_filter = event.get("nameFilter", "")

    try:
        s3 = boto3.client("s3")
        response = s3.list_buckets()
        buckets = []

        for b in response.get("Buckets", []):
            bucket_name = b.get("Name", "")

            # Client-side name filter
            if name_filter and name_filter.lower() not in bucket_name.lower():
                continue

            buckets.append({
                "name": bucket_name,
                "creationDate": b.get("CreationDate", "").isoformat() if hasattr(b.get("CreationDate", ""), "isoformat") else str(b.get("CreationDate", "")),
            })

        # Limit to 30 results
        return {"buckets": buckets[:30], "count": min(len(buckets), 30), "error": None}

    except Exception as e:
        return {"buckets": [], "error": str(e)}


def _put_s3_object_lock_retention(event, user_id):
    """Update S3 Object Lock default retention configuration.

    AWS API: s3:PutObjectLockConfiguration
    Note: Bucket must already have Object Lock enabled at creation time.
    This only updates the default retention rule (mode + days/years).
    """
    bucket = event.get("bucket", "")
    mode = event.get("mode", "GOVERNANCE")  # GOVERNANCE or COMPLIANCE
    days = event.get("days")
    years = event.get("years")

    if not bucket:
        return {"success": False, "error": "Bucket name is required"}
    if mode not in ("GOVERNANCE", "COMPLIANCE"):
        return {"success": False, "error": "Mode must be GOVERNANCE or COMPLIANCE"}
    if not days and not years:
        return {"success": False, "error": "Either days or years is required"}

    retention = {"Mode": mode}
    if days:
        retention["Days"] = int(days)
    elif years:
        retention["Years"] = int(years)

    try:
        s3 = boto3.client("s3")
        s3.put_object_lock_configuration(
            Bucket=bucket,
            ObjectLockConfiguration={
                "ObjectLockEnabled": "Enabled",
                "Rule": {"DefaultRetention": retention},
            },
        )
        logger.info(f"S3 Object Lock retention updated: {bucket} ({mode}, {days or years}) by {user_id}")
        return {"success": True, "error": None}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── EMS Events ──────────────────────────────────────────────────────────────


def _get_ems_events(http, headers, event):
    """Get recent EMS (Event Management System) events from ONTAP.

    ONTAP REST: GET /api/support/ems/events
    Retrieves alert and error severity events for operational awareness.
    """
    max_records = min(event.get("maxRecords", 20), 50)
    severity_filter = event.get("severity", "alert,error,emergency")

    query = f"/support/ems/events?max_records={max_records}"
    query += f"&severity={severity_filter}"
    query += "&order_by=time desc"
    query += "&fields=time,severity,message.name,message.text,node.name"

    data = _ontap_request(http, headers, "GET", query)
    if data.get("_error"):
        return {"events": [], "error": data["_message"]}

    events = [
        {
            "time": e.get("time", ""),
            "severity": e.get("severity", ""),
            "messageName": e.get("message", {}).get("name", ""),
            "messageText": e.get("message", {}).get("text", ""),
            "node": e.get("node", {}).get("name", ""),
        }
        for e in data.get("records", [])
    ]
    return {"events": events, "count": len(events), "error": None}
