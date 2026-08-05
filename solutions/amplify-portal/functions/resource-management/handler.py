"""Resource Management Lambda — Volume, Export Policy, QoS, SnapLock operations.

Provides the backend for the portal's Admin > Resource Management section.
Modeled after ONTAP System Manager's storage management capabilities,
implemented via ONTAP REST API for programmatic access.

ONTAP REST API endpoints used:
- /storage/volumes — Volume CRUD + resize, FlexClone create/split
- /protocols/nfs/export-policies — Export policy management
- /protocols/nfs/export-policies/{id}/rules — Export policy rules
- /storage/qos/policies — QoS policy management
- /storage/volumes/{uuid} (snaplock fields) — SnapLock configuration
- /protocols/cifs/local-users — SMB local user management
- /protocols/cifs/local-groups — SMB local group management
- /protocols/cifs/local-groups/{svm}/{sid}/members — Local group membership
- /name-services/name-mappings — Windows <-> UNIX identity mapping
- /storage/flexcache/flexcaches — FlexCache create/list/delete
- /snapmirror/relationships — Replication status, transfer, quiesce/resume,
  break, resync, delete
- /snapmirror/relationships/{uuid}/transfers — On-demand transfer and abort
- /protocols/vscan/{svm.uuid} — Virus scanning enable/disable
- /protocols/vscan/{svm.uuid}/on-access-policies — On-access policy management
- /protocols/fpolicy/{svm.uuid}/events — File access event definitions
- /protocols/fpolicy/{svm.uuid}/policies — File access notification policies
- /cluster/peers — Cluster peering (create with passphrase, accept, delete)
- /svm/peers — SVM peering (create, accept, delete)
- /network/ip/interfaces — LIF inventory, intercluster LIF check, enable/disable
- /cluster, /cluster/nodes, /cluster/licensing/licenses — Cluster inventory
- /name-services/dns — DNS domains and servers
- /protocols/{nfs,cifs,s3}/services — Data protocol service state
- /cluster/jobs — Asynchronous job progress for the operations above

Environment:
    ONTAP_MGMT_IP: FSx for ONTAP management endpoint
    ONTAP_SECRET_NAME: Secrets Manager secret (username/password)
    SVM_NAME: Default SVM name
"""

from __future__ import annotations

import json
import logging
import os
import re
from urllib.parse import quote

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


# Caller-supplied names reach ONTAP request paths in many of the actions below.
# An unencoded value containing a traversal sequence would redirect the request
# to a different endpoint — a "delete this share" call could reach a cluster
# resource instead. Rather than trusting ~110 call sites to remember, the check
# lives in the one function they all go through.
_UNSAFE_PATH_CHARS = re.compile(r"[\x00-\x1f\x7f\\]")


def _is_unsafe_path(path: str) -> bool:
    """True if the assembled request path must not be sent."""
    if _UNSAFE_PATH_CHARS.search(path):
        return True
    # Split off the query string, then look for a traversal segment. `..` inside
    # a name (for example "my..share") is fine; a whole segment of ".." is not.
    route = path.split("?", 1)[0]
    return any(segment == ".." for segment in route.split("/"))


def _seg(value) -> str:
    """Percent-encode a value used as a single path segment."""
    return quote(str(value), safe="")


def _qval(value) -> str:
    """Percent-encode a value used as a query-string value.

    Without this, a name containing `&` or `=` adds parameters to the request
    instead of being matched as a name.
    """
    return quote(str(value), safe="")


def _shared_client():
    """Build an OntapClient from shared/, or raise ImportError if unavailable.

    `shared/` arrives at /opt/python through a Lambda layer; functionCode() in
    backend.ts bundles only this directory. The parent walk is the fallback for
    running the module from a checkout, where the layer does not exist.

    verify_ssl is False to match the request path the rest of this handler uses
    (`urllib3.PoolManager(cert_reqs="CERT_NONE")`). The FSx for ONTAP management
    LIF presents a self-signed certificate by default, so turning verification on
    is not a flag flip -- it needs a trusted CA reachable from the function and a
    ca_cert_path pointing at it.
    """
    import sys
    from pathlib import Path

    candidates = ["/opt/python"]
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "shared" / "ontap_client.py").exists():
            candidates.append(str(parent))
            break
    for candidate in candidates:
        if candidate not in sys.path:
            sys.path.insert(0, candidate)

    from shared.ontap_client import OntapClient, OntapClientConfig

    return OntapClient(
        OntapClientConfig(
            management_ip=MGMT_IP,
            secret_name=SECRET_NAME,
            verify_ssl=False,  # PoC — set True + ca_cert_path for production
        ),
        # Pass this module's session rather than letting the client build its own.
        # Every other action in this handler reads its credential through
        # `handler.boto3`, so a test patching that module controlled all AWS access.
        # A client with its own session breaks that: an unpatched test reaches real
        # Secrets Manager and hangs on credential discovery instead of failing.
        session=boto3.Session(),
    )


def _client_or_error():
    """(client, None) on success, (None, error_dict) on failure.

    Built on demand rather than alongside the urllib3 pool: only the SnapMirror
    actions take this path, and constructing the client reads the credential
    secret, which the other actions should not pay for.
    """
    try:
        return _shared_client(), None
    except ImportError as e:
        logger.error("shared/ is not importable: %s", e)
        return None, {
            "success": False,
            "error": f"shared modules are unavailable to this function ({type(e).__name__})",
        }
    except Exception as e:
        logger.error("Could not build the ONTAP client: %s: %s", type(e).__name__, e)
        return None, {
            "success": False,
            "error": f"Could not build the ONTAP client ({type(e).__name__})",
        }


def _client_error(exc) -> str:
    """The message to show for a failed client call.

    OntapClientError carries the response body; `ontap_message` pulls ONTAP's own
    error text out of it. Falling back to str(exc) keeps a transport failure --
    which has no ONTAP body -- readable.
    """
    return getattr(exc, "ontap_message", None) or str(exc)


def _ontap_request(http, headers, method, path, body=None):
    """Make an ONTAP REST API request."""
    if _is_unsafe_path(path):
        logger.warning("Refused ONTAP request with unsafe path: %r", path[:200])
        return {
            "_error": True,
            "_status": 400,
            "_message": "Invalid characters in request path",
        }
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

        # --- SMB Local Users and Groups ---
        elif action == "listLocalUsers":
            return _list_local_users(http, headers, event)
        elif action == "createLocalUser":
            return _create_local_user(http, headers, event, user_id)
        elif action == "deleteLocalUser":
            return _delete_local_user(http, headers, event, user_id)
        elif action == "listLocalGroups":
            return _list_local_groups(http, headers, event)
        elif action == "createLocalGroup":
            return _create_local_group(http, headers, event, user_id)
        elif action == "deleteLocalGroup":
            return _delete_local_group(http, headers, event, user_id)
        elif action == "listGroupMembers":
            return _list_group_members(http, headers, event)
        elif action == "addGroupMember":
            return _add_group_member(http, headers, event, user_id)
        elif action == "removeGroupMember":
            return _remove_group_member(http, headers, event, user_id)

        # --- Name Mapping (Windows <-> UNIX identity) ---
        elif action == "listNameMappings":
            return _list_name_mappings(http, headers, event)
        elif action == "createNameMapping":
            return _create_name_mapping(http, headers, event, user_id)
        elif action == "deleteNameMapping":
            return _delete_name_mapping(http, headers, event, user_id)

        # --- FlexCache ---
        elif action == "listFlexCaches":
            return _list_flexcaches(http, headers, event)
        elif action == "createFlexCache":
            return _create_flexcache(http, headers, event, user_id)
        elif action == "deleteFlexCache":
            return _delete_flexcache(http, headers, event, user_id)

        # --- FlexClone ---
        elif action == "listFlexClones":
            return _list_flexclones(http, headers, event)
        elif action == "createFlexClone":
            return _create_flexclone(http, headers, event, user_id)
        elif action == "splitFlexClone":
            return _split_flexclone(http, headers, event, user_id)

        # --- SnapMirror ---
        elif action == "listSnapmirrorRelationships":
            return _list_snapmirror_relationships(event)
        elif action == "getSnapmirrorTransfers":
            return _get_snapmirror_transfers(event)
        elif action == "updateSnapmirrorNow":
            return _update_snapmirror_now(event, user_id)
        elif action == "quiesceSnapmirror":
            return _set_snapmirror_state(event, user_id, "paused")
        elif action == "resumeSnapmirror":
            return _set_snapmirror_state(event, user_id, "snapmirrored")
        elif action == "breakSnapmirror":
            return _break_snapmirror(event, user_id)
        elif action == "resyncSnapmirror":
            return _resync_snapmirror(event, user_id)
        elif action == "abortSnapmirrorTransfer":
            return _abort_snapmirror_transfer(event, user_id)
        elif action == "deleteSnapmirror":
            return _delete_snapmirror(event, user_id)

        # --- Vscan ---
        elif action == "getVscanStatus":
            return _get_vscan_status(http, headers, event)
        elif action == "listVscanPolicies":
            return _list_vscan_policies(http, headers, event)
        elif action == "setVscanEnabled":
            return _set_vscan_enabled(http, headers, event, user_id)
        elif action == "createVscanPolicy":
            return _create_vscan_policy(http, headers, event, user_id)
        elif action == "setVscanPolicyEnabled":
            return _set_vscan_policy_enabled(http, headers, event, user_id)
        elif action == "deleteVscanPolicy":
            return _delete_vscan_policy(http, headers, event, user_id)

        # --- FPolicy ---
        elif action == "getFpolicyStatus":
            return _get_fpolicy_status(http, headers, event)
        elif action == "listFpolicyPolicies":
            return _list_fpolicy_policies(http, headers, event)
        elif action == "listFpolicyEvents":
            return _list_fpolicy_events(http, headers, event)
        elif action == "createFpolicyEvent":
            return _create_fpolicy_event(http, headers, event, user_id)
        elif action == "deleteFpolicyEvent":
            return _delete_fpolicy_event(http, headers, event, user_id)
        elif action == "createFpolicyPolicy":
            return _create_fpolicy_policy(http, headers, event, user_id)
        elif action == "setFpolicyPolicyEnabled":
            return _set_fpolicy_policy_enabled(http, headers, event, user_id)
        elif action == "deleteFpolicyPolicy":
            return _delete_fpolicy_policy(http, headers, event, user_id)

        # --- Peering (cluster and SVM) ---
        elif action == "listInterclusterLifs":
            return _list_intercluster_lifs(http, headers, event)
        elif action == "listClusterPeers":
            return _list_cluster_peers(http, headers, event)
        elif action == "createClusterPeer":
            return _create_cluster_peer(http, headers, event, user_id)
        elif action == "acceptClusterPeer":
            return _accept_cluster_peer(http, headers, event, user_id)
        elif action == "deleteClusterPeer":
            return _delete_cluster_peer(http, headers, event, user_id)
        elif action == "listSvmPeers":
            return _list_svm_peers(http, headers, event)
        elif action == "createSvmPeer":
            return _create_svm_peer(http, headers, event, user_id)
        elif action == "acceptSvmPeer":
            return _accept_svm_peer(http, headers, event, user_id)
        elif action == "deleteSvmPeer":
            return _delete_svm_peer(http, headers, event, user_id)

        # --- Cluster inventory and services ---
        elif action == "getClusterInfo":
            return _get_cluster_info(http, headers, event)
        elif action == "listNodes":
            return _list_nodes(http, headers, event)
        elif action == "listLicenses":
            return _list_licenses(http, headers, event)
        elif action == "listNetworkInterfaces":
            return _list_network_interfaces(http, headers, event)
        elif action == "setNetworkInterfaceEnabled":
            return _set_network_interface_enabled(http, headers, event, user_id)
        elif action == "getDnsConfig":
            return _get_dns_config(http, headers, event)
        elif action == "updateDnsConfig":
            return _update_dns_config(http, headers, event, user_id)
        elif action == "listProtocolServices":
            return _list_protocol_services(http, headers, event)
        elif action == "setProtocolServiceEnabled":
            return _set_protocol_service_enabled(http, headers, event, user_id)
        elif action == "listJobs":
            return _list_jobs(http, headers, event)
        elif action == "getJob":
            return _get_job(http, headers, event)

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
    allowed_keys = {
        "aiAgentEnabled",
        "aiSearchEnabled",
        "aiMultimodalEnabled",
        "aiSmartRoutingEnabled",
        "chatHistoryEnabled",
        "aiVoiceEnabled",
        "agentDirectoryEnabled",
    }
    if key not in allowed_keys:
        return {"error": f"Setting '{key}' is not allowed. Valid: {sorted(allowed_keys)}"}

    ddb = boto3.resource("dynamodb")
    table = ddb.Table(PORTAL_SETTINGS_TABLE)

    try:
        table.put_item(
            Item={
                "settingKey": key,
                "settingValue": str(value).lower(),
                "updatedBy": user_id,
            }
        )
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
        http,
        headers,
        "GET",
        f"/storage/volumes?svm.name={_qval(svm)}"
        f"&fields=name,uuid,size,state,type,style,nas,space,guarantee,snaplock"
        f"&max_records=50",
    )
    if data.get("_error"):
        return {"volumes": [], "error": data["_message"]}

    volumes = []
    for v in data.get("records", []):
        space = v.get("space", {})
        volumes.append(
            {
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
            }
        )

    return {"volumes": volumes, "count": len(volumes), "error": None}


def _list_volumes_filtered(http, headers, event):
    """List volumes with server-side name wildcard filtering.

    ONTAP REST: GET /api/storage/volumes?name=*keyword*&svm.name=<svm>&max_records=20
    Used by VolumeSelector search for large environments (thousands of volumes).
    """
    svm = event.get("svm", SVM_NAME)
    name_filter = event.get("nameFilter", "")
    max_records = min(event.get("maxRecords", 20), 50)

    query = f"/storage/volumes?svm.name={_qval(svm)}"
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
        http,
        headers,
        "GET",
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
        http,
        headers,
        "PATCH",
        f"/storage/volumes/{vol_uuid}",
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
        http,
        headers,
        "GET",
        f"/protocols/nfs/export-policies?svm.name={_qval(svm)}&fields=name,id,rules",
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
        http,
        headers,
        "GET",
        f"/protocols/nfs/export-policies/{policy_id}/rules?fields=clients,ro_rule,rw_rule,superuser,protocols,index",
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
        http,
        headers,
        "POST",
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
        http,
        headers,
        "DELETE",
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
        http,
        headers,
        "GET",
        f"/storage/qos/policies?svm.name={_qval(svm)}&fields=name,uuid,fixed,adaptive",
    )
    if data.get("_error"):
        return {"policies": [], "error": data["_message"]}

    policies = []
    for p in data.get("records", []):
        fixed = p.get("fixed", {})
        adaptive = p.get("adaptive", {})
        policies.append(
            {
                "name": p.get("name", ""),
                "uuid": p.get("uuid", ""),
                "type": "adaptive" if adaptive else "fixed",
                "maxThroughputIops": fixed.get("max_throughput_iops"),
                "maxThroughputMbps": fixed.get("max_throughput_mbps"),
                "expectedIops": adaptive.get("expected_iops"),
                "peakIops": adaptive.get("peak_iops"),
            }
        )

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
                http,
                headers,
                "GET",
                f"/storage/volumes?name={_qval(vol_name)}&svm.name={_qval(svm)}&fields=uuid",
            )
            records = resolve.get("records", [])
            if records:
                vol_uuid = records[0]["uuid"]
            else:
                return {"config": None, "error": f"Volume '{vol_name}' not found"}
        else:
            return {"config": None, "error": "volumeUuid or volumeName is required"}

    data = _ontap_request(
        http,
        headers,
        "GET",
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
    params = f"svm.name={_qval(svm)}&fields=type,qtree.name,users.name,group.name,space,files,volume.name"
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
        rules.append(
            {
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
            }
        )

    return {"rules": rules, "count": len(rules), "error": None}


def _get_quota_report(http, headers, event):
    """Get quota usage report (actual consumption vs limits).

    ONTAP REST: GET /api/storage/quota/reports
    """
    svm = event.get("svm", SVM_NAME)
    vol_name = event.get("volumeName", "")
    params = f"svm.name={_qval(svm)}&fields=space,files,users.name,group.name,qtree.name,type,volume.name"
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
        entries.append(
            {
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
                )
                if space.get("hard_limit")
                else 0,
                "filesUsed": files.get("used", {}).get("total", 0),
                "filesHardLimit": files.get("hard_limit", 0),
            }
        )

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
        http,
        headers,
        "GET",
        f"/protocols/cifs/shares?svm.name={_qval(svm)}"
        f"&fields=name,path,comment,acls,encryption,continuously_available"
        f"&max_records=50",
    )
    if data.get("_error"):
        return {"shares": [], "error": data["_message"]}

    shares = []
    for s in data.get("records", []):
        shares.append(
            {
                "name": s.get("name", ""),
                "path": s.get("path", ""),
                "comment": s.get("comment", ""),
                "encryption": s.get("encryption", False),
                "continuouslyAvailable": s.get("continuously_available", False),
                "aclCount": len(s.get("acls", [])),
            }
        )

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
    svm_data = _ontap_request(http, headers, "GET", f"/svm/svms?name={_qval(svm)}&fields=uuid")
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
        http,
        headers,
        "PATCH",
        f"/protocols/cifs/shares/{svm_uuid}/{_seg(share_name)}",
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
    svm_data = _ontap_request(http, headers, "GET", f"/svm/svms?name={_qval(svm)}&fields=uuid")
    svm_records = svm_data.get("records", [])
    if not svm_records:
        return {"success": False, "error": f"SVM '{svm}' not found"}
    svm_uuid = svm_records[0]["uuid"]

    data = _ontap_request(http, headers, "DELETE", f"/protocols/cifs/shares/{svm_uuid}/{_seg(share_name)}")
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
    params = f"svm.name={_qval(svm)}&fields=name,id,volume.name,security_style,export_policy.name,unix_permissions"
    if vol_name:
        params += f"&volume.name={vol_name}"
    params += "&max_records=100"

    data = _ontap_request(http, headers, "GET", f"/storage/qtrees?{params}")
    if data.get("_error"):
        return {"qtrees": [], "error": data["_message"]}

    qtrees = []
    for q in data.get("records", []):
        qtrees.append(
            {
                "id": q.get("id"),
                "name": q.get("name", ""),
                "volumeName": q.get("volume", {}).get("name", ""),
                "securityStyle": q.get("security_style", ""),
                "exportPolicy": q.get("export_policy", {}).get("name", ""),
                "unixPermissions": q.get("unix_permissions", ""),
            }
        )

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
        http,
        headers,
        "GET",
        f"/storage/volumes?name={_qval(vol_name)}&svm.name={_qval(svm)}&fields=uuid",
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
        http,
        headers,
        "GET",
        f"/storage/volumes?svm.name={_qval(svm)}&fields=name,efficiency,space&max_records=50",
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

        volumes.append(
            {
                "name": v.get("name", ""),
                "dedupe": eff.get("dedupe", "none"),
                "compression": eff.get("compression", "none"),
                "crossVolumeDeduplication": eff.get("cross_volume_dedupe", "none"),
                "compaction": eff.get("compaction", "none"),
                "logicalUsedBytes": logical,
                "physicalUsedBytes": physical,
                "savingsRatio": round(logical / max(physical, 1), 2),
                "savingsPercent": round((1 - physical / max(logical, 1)) * 100, 1) if logical > 0 else 0,
            }
        )

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
        http,
        headers,
        "GET",
        f"/storage/volumes?svm.name={_qval(svm)}&fields=name,uuid,anti_ransomware,type,nas,size&max_records=100",
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

        volumes.append(
            {
                "name": v.get("name", ""),
                "uuid": v.get("uuid", ""),
                "state": arp.get("state", "disabled"),
                "attackProbability": arp.get("attack_probability", "none"),
                "dryRunStartTime": arp.get("dry_run_start_time"),
                "surgeAsNormal": arp.get("surge_as_normal", False),
                "volumeType": "SAN" if is_san else "NAS",
                "sizeGiB": round(v.get("size", 0) / (1024**3), 1),
                "type": vol_type,
            }
        )

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
            http,
            headers,
            "GET",
            f"/security/anti-ransomware/suspects"
            f"?volume.uuid={vol_uuid}"
            f"&fields=file.path,file.type,suspect_time,file.entropy",
        )
        if data.get("_error"):
            return {"suspects": [], "error": data["_message"]}

        suspects = []
        for s in data.get("records", []):
            file_info = s.get("file", {})
            suspects.append(
                {
                    "filePath": file_info.get("path", ""),
                    "fileType": file_info.get("type", ""),
                    "entropy": file_info.get("entropy"),
                    "suspectTime": s.get("suspect_time", ""),
                }
            )

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
    logger.info(f"ARP bulk enable: {success_count}/{len(vol_uuids)} → '{target_state}' by {user_id}")

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
        http,
        headers,
        "GET",
        f"/storage/snapshot-policies?svm.name={_qval(svm)}&fields=name,uuid,enabled,copies,comment,scope&max_records=50",
    )
    if data.get("_error"):
        return {"policies": [], "error": data["_message"]}

    policies = []
    for p in data.get("records", []):
        copies = p.get("copies", [])
        policies.append(
            {
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
            }
        )

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
        http,
        headers,
        "PATCH",
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
        http,
        headers,
        "GET",
        f"/storage/volumes/{vol_uuid}?fields=name,snapshot_locking_enabled,snapshot_policy",
    )
    if data.get("_error"):
        return {"config": None, "error": data["_message"]}

    # Count locked snapshots
    snap_data = _ontap_request(
        http,
        headers,
        "GET",
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
            }
            if retention
            else None,
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

            buckets.append(
                {
                    "name": bucket_name,
                    "creationDate": b.get("CreationDate", "").isoformat()
                    if hasattr(b.get("CreationDate", ""), "isoformat")
                    else str(b.get("CreationDate", "")),
                }
            )

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


# ─── SMB Local Users and Groups ───────────────────────────────────────────────


def _get_svm_uuid(http, headers, svm_name):
    """Resolve an SVM name to its UUID.

    Several CIFS endpoints are keyed by SVM UUID rather than name, so callers
    that need a path segment resolve it here first.
    """
    data = _ontap_request(http, headers, "GET", f"/svm/svms?name={_qval(svm_name)}&fields=uuid")
    if data.get("_error"):
        return None, data["_message"]
    records = data.get("records", [])
    if not records:
        return None, f"SVM '{svm_name}' not found"
    return records[0]["uuid"], None


def _list_local_users(http, headers, event):
    """List SMB local users for the SVM.

    ONTAP REST: GET /api/protocols/cifs/local-users
    """
    svm = event.get("svm", SVM_NAME)
    params = f"svm.name={_qval(svm)}&fields=name,sid,full_name,description,account_disabled,membership&max_records=200"

    data = _ontap_request(http, headers, "GET", f"/protocols/cifs/local-users?{params}")
    if data.get("_error"):
        return {"users": [], "error": data["_message"]}

    users = []
    for u in data.get("records", []):
        # ONTAP strips the SVM prefix on display names ("SERVER\user" -> "user")
        raw_name = u.get("name", "")
        users.append(
            {
                "name": raw_name.split("\\")[-1] if "\\" in raw_name else raw_name,
                "sid": u.get("sid", ""),
                "fullName": u.get("full_name", ""),
                "description": u.get("description", ""),
                "disabled": bool(u.get("account_disabled", False)),
                "memberOf": [g.get("name", "") for g in u.get("membership", [])],
            }
        )

    return {"users": users, "count": len(users), "error": None}


def _create_local_user(http, headers, event, user_id):
    """Create an SMB local user.

    ONTAP REST: POST /api/protocols/cifs/local-users
    """
    svm = event.get("svm", SVM_NAME)
    name = event.get("name", "")
    password = event.get("password", "")

    if not name or not password:
        return {"success": False, "error": "name and password are required"}

    body = {"svm": {"name": svm}, "name": name, "password": password}
    if event.get("fullName"):
        body["full_name"] = event["fullName"]
    if event.get("description"):
        body["description"] = event["description"]

    data = _ontap_request(http, headers, "POST", "/protocols/cifs/local-users", body=body)
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    # Never log the password; the name is enough for the audit trail.
    logger.info(f"SMB local user created: {name} by {user_id}")
    return {"success": True, "name": name, "error": None}


def _delete_local_user(http, headers, event, user_id):
    """Delete an SMB local user.

    ONTAP REST: DELETE /api/protocols/cifs/local-users/{svm.uuid}/{sid}
    """
    svm = event.get("svm", SVM_NAME)
    sid = event.get("sid", "")
    name = event.get("name", "")

    if not sid:
        return {"success": False, "error": "sid is required"}

    svm_uuid, err = _get_svm_uuid(http, headers, svm)
    if err:
        return {"success": False, "error": err}

    data = _ontap_request(http, headers, "DELETE", f"/protocols/cifs/local-users/{svm_uuid}/{sid}")
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"SMB local user deleted: {name or sid} by {user_id}")
    return {"success": True, "error": None}


def _list_local_groups(http, headers, event):
    """List SMB local groups for the SVM.

    ONTAP REST: GET /api/protocols/cifs/local-groups
    """
    svm = event.get("svm", SVM_NAME)
    params = f"svm.name={_qval(svm)}&fields=name,sid,description&max_records=200"

    data = _ontap_request(http, headers, "GET", f"/protocols/cifs/local-groups?{params}")
    if data.get("_error"):
        return {"groups": [], "error": data["_message"]}

    groups = []
    for g in data.get("records", []):
        raw_name = g.get("name", "")
        groups.append(
            {
                "name": raw_name.split("\\")[-1] if "\\" in raw_name else raw_name,
                "sid": g.get("sid", ""),
                "description": g.get("description", ""),
            }
        )

    return {"groups": groups, "count": len(groups), "error": None}


def _create_local_group(http, headers, event, user_id):
    """Create an SMB local group.

    ONTAP REST: POST /api/protocols/cifs/local-groups
    """
    svm = event.get("svm", SVM_NAME)
    name = event.get("name", "")

    if not name:
        return {"success": False, "error": "name is required"}

    body = {"svm": {"name": svm}, "name": name}
    if event.get("description"):
        body["description"] = event["description"]

    data = _ontap_request(http, headers, "POST", "/protocols/cifs/local-groups", body=body)
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"SMB local group created: {name} by {user_id}")
    return {"success": True, "name": name, "error": None}


def _delete_local_group(http, headers, event, user_id):
    """Delete an SMB local group.

    ONTAP REST: DELETE /api/protocols/cifs/local-groups/{svm.uuid}/{sid}
    """
    svm = event.get("svm", SVM_NAME)
    sid = event.get("sid", "")
    name = event.get("name", "")

    if not sid:
        return {"success": False, "error": "sid is required"}

    svm_uuid, err = _get_svm_uuid(http, headers, svm)
    if err:
        return {"success": False, "error": err}

    data = _ontap_request(http, headers, "DELETE", f"/protocols/cifs/local-groups/{svm_uuid}/{sid}")
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"SMB local group deleted: {name or sid} by {user_id}")
    return {"success": True, "error": None}


def _list_group_members(http, headers, event):
    """List the members of an SMB local group.

    ONTAP REST: GET /api/protocols/cifs/local-groups/{svm.uuid}/{group_sid}/members
    """
    svm = event.get("svm", SVM_NAME)
    group_sid = event.get("groupSid", "")

    if not group_sid:
        return {"members": [], "error": "groupSid is required"}

    svm_uuid, err = _get_svm_uuid(http, headers, svm)
    if err:
        return {"members": [], "error": err}

    data = _ontap_request(
        http,
        headers,
        "GET",
        f"/protocols/cifs/local-groups/{svm_uuid}/{group_sid}/members?fields=name&max_records=200",
    )
    if data.get("_error"):
        return {"members": [], "error": data["_message"]}

    members = [{"name": m.get("name", "")} for m in data.get("records", [])]
    return {"members": members, "count": len(members), "error": None}


def _add_group_member(http, headers, event, user_id):
    """Add a local user, AD user or AD group to an SMB local group.

    ONTAP REST: POST /api/protocols/cifs/local-groups/{svm.uuid}/{group_sid}/members
    """
    svm = event.get("svm", SVM_NAME)
    group_sid = event.get("groupSid", "")
    group_name = event.get("groupName", "")
    member_name = event.get("memberName", "")

    if not group_sid or not member_name:
        return {"success": False, "error": "groupSid and memberName are required"}

    svm_uuid, err = _get_svm_uuid(http, headers, svm)
    if err:
        return {"success": False, "error": err}

    data = _ontap_request(
        http,
        headers,
        "POST",
        f"/protocols/cifs/local-groups/{svm_uuid}/{group_sid}/members",
        body={"name": member_name},
    )
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"SMB group member added: {member_name} -> {group_name or group_sid} by {user_id}")
    return {"success": True, "error": None}


def _remove_group_member(http, headers, event, user_id):
    """Remove a member from an SMB local group.

    ONTAP REST: DELETE /api/protocols/cifs/local-groups/{svm.uuid}/{group_sid}/members/{name}
    """
    svm = event.get("svm", SVM_NAME)
    group_sid = event.get("groupSid", "")
    group_name = event.get("groupName", "")
    member_name = event.get("memberName", "")

    if not group_sid or not member_name:
        return {"success": False, "error": "groupSid and memberName are required"}

    svm_uuid, err = _get_svm_uuid(http, headers, svm)
    if err:
        return {"success": False, "error": err}

    # Member names can contain a domain backslash, so percent-encode the segment.
    encoded = quote(member_name, safe="")
    data = _ontap_request(
        http,
        headers,
        "DELETE",
        f"/protocols/cifs/local-groups/{svm_uuid}/{group_sid}/members/{encoded}",
    )
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"SMB group member removed: {member_name} from {group_name or group_sid} by {user_id}")
    return {"success": True, "error": None}


# ─── Name Mapping (Windows <-> UNIX identity) ─────────────────────────────────


def _list_name_mappings(http, headers, event):
    """List name-mapping rules for the SVM.

    ONTAP REST: GET /api/name-services/name-mappings
    """
    svm = event.get("svm", SVM_NAME)
    params = f"svm.name={_qval(svm)}&fields=direction,index,pattern,replacement&max_records=200"

    data = _ontap_request(http, headers, "GET", f"/name-services/name-mappings?{params}")
    if data.get("_error"):
        return {"mappings": [], "error": data["_message"]}

    mappings = []
    for m in data.get("records", []):
        mappings.append(
            {
                "direction": m.get("direction", ""),
                "index": m.get("index", 0),
                "pattern": m.get("pattern", ""),
                "replacement": m.get("replacement", ""),
            }
        )
    mappings.sort(key=lambda m: (m["direction"], m["index"]))

    return {"mappings": mappings, "count": len(mappings), "error": None}


def _create_name_mapping(http, headers, event, user_id):
    """Create a name-mapping rule.

    ONTAP REST: POST /api/name-services/name-mappings

    Directions are win_unix, unix_win and s3_unix. Entries whose direction is
    s3_unix are created and removed by FSx for ONTAP when an S3 Access Point is
    attached, so they are not managed here.
    """
    svm = event.get("svm", SVM_NAME)
    direction = event.get("direction", "")
    index = event.get("index")
    pattern = event.get("pattern", "")
    replacement = event.get("replacement", "")

    if not direction or not pattern or not replacement:
        return {
            "success": False,
            "error": "direction, pattern and replacement are required",
        }
    if direction == "s3_unix":
        return {
            "success": False,
            "error": "s3_unix mappings are managed automatically by FSx for ONTAP",
        }
    if index is None:
        return {"success": False, "error": "index is required"}

    body = {
        "svm": {"name": svm},
        "direction": direction,
        "index": int(index),
        "pattern": pattern,
        "replacement": replacement,
    }

    data = _ontap_request(http, headers, "POST", "/name-services/name-mappings", body=body)
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"Name mapping created: {direction}[{index}] by {user_id}")
    return {"success": True, "error": None}


def _delete_name_mapping(http, headers, event, user_id):
    """Delete a name-mapping rule.

    ONTAP REST: DELETE /api/name-services/name-mappings/{svm.uuid}/{direction}/{index}
    """
    svm = event.get("svm", SVM_NAME)
    direction = event.get("direction", "")
    index = event.get("index")

    if not direction or index is None:
        return {"success": False, "error": "direction and index are required"}

    svm_uuid, err = _get_svm_uuid(http, headers, svm)
    if err:
        return {"success": False, "error": err}

    data = _ontap_request(
        http,
        headers,
        "DELETE",
        f"/name-services/name-mappings/{svm_uuid}/{direction}/{int(index)}",
    )
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"Name mapping deleted: {direction}[{index}] by {user_id}")
    return {"success": True, "error": None}


# ─── FlexCache ────────────────────────────────────────────────────────────────


def _list_flexcaches(http, headers, event):
    """List FlexCache volumes hosted on this cluster.

    ONTAP REST: GET /api/storage/flexcache/flexcaches
    """
    params = (
        "fields=name,uuid,svm.name,size,path,origins.cluster.name,"
        "origins.svm.name,origins.volume.name,origins.state,global_file_locking_enabled"
        "&max_records=100"
    )

    data = _ontap_request(http, headers, "GET", f"/storage/flexcache/flexcaches?{params}")
    if data.get("_error"):
        return {"caches": [], "error": data["_message"]}

    caches = []
    for c in data.get("records", []):
        origins = []
        for o in c.get("origins", []):
            origins.append(
                {
                    "clusterName": o.get("cluster", {}).get("name", ""),
                    "svmName": o.get("svm", {}).get("name", ""),
                    "volumeName": o.get("volume", {}).get("name", ""),
                    "state": o.get("state", ""),
                }
            )
        caches.append(
            {
                "name": c.get("name", ""),
                "uuid": c.get("uuid", ""),
                "svmName": c.get("svm", {}).get("name", ""),
                "sizeGiB": round(c.get("size", 0) / (1024**3), 2),
                "path": c.get("path", ""),
                "origins": origins,
                "globalFileLocking": bool(c.get("global_file_locking_enabled", False)),
            }
        )

    return {"caches": caches, "count": len(caches), "error": None}


def _create_flexcache(http, headers, event, user_id):
    """Create a FlexCache volume.

    ONTAP REST: POST /api/storage/flexcache/flexcaches

    NetApp's guidance is to size a cache at roughly 10% of the origin volume,
    with 1 GiB as the smallest usable constituent.
    """
    svm = event.get("svm", SVM_NAME)
    name = event.get("name", "")
    origin_volume = event.get("originVolume", "")
    origin_svm = event.get("originSvm") or svm
    size_gib = event.get("sizeGiB")
    path = event.get("path") or f"/{name}"
    prepopulate_paths = event.get("prepopulatePaths")

    if not name or not origin_volume:
        return {"success": False, "error": "name and originVolume are required"}
    if not size_gib:
        return {"success": False, "error": "sizeGiB is required"}
    if float(size_gib) < 1:
        return {"success": False, "error": "sizeGiB must be at least 1"}

    body = {
        "name": name,
        "svm": {"name": svm},
        "size": int(float(size_gib) * 1024**3),
        "path": path,
        "origins": [{"volume": {"name": origin_volume}, "svm": {"name": origin_svm}}],
    }
    if prepopulate_paths:
        body["prepopulate"] = {"dir_paths": prepopulate_paths}

    data = _ontap_request(http, headers, "POST", "/storage/flexcache/flexcaches", body=body)
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    # FlexCache creation is asynchronous; surface the job so the UI can report it.
    job_id = data.get("job", {}).get("uuid", "")
    logger.info(f"FlexCache created: {name} from {origin_svm}:{origin_volume} by {user_id}")
    return {"success": True, "jobId": job_id, "error": None}


def _delete_flexcache(http, headers, event, user_id):
    """Delete a FlexCache volume.

    ONTAP REST: DELETE /api/storage/flexcache/flexcaches/{uuid}
    """
    uuid = event.get("uuid", "")
    name = event.get("name", "")

    if not uuid:
        return {"success": False, "error": "uuid is required"}

    data = _ontap_request(http, headers, "DELETE", f"/storage/flexcache/flexcaches/{uuid}")
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"FlexCache deleted: {name or uuid} by {user_id}")
    return {"success": True, "error": None}


# ─── FlexClone ────────────────────────────────────────────────────────────────


def _list_flexclones(http, headers, event):
    """List FlexClone volumes in the SVM.

    ONTAP REST: GET /api/storage/volumes?clone.is_flexclone=true
    """
    svm = event.get("svm", SVM_NAME)
    params = (
        f"svm.name={_qval(svm)}&clone.is_flexclone=true"
        "&fields=name,uuid,size,state,space.used,clone.parent_volume.name,"
        "clone.parent_snapshot.name,clone.split_initiated,clone.split_complete_percent"
        "&max_records=100"
    )

    data = _ontap_request(http, headers, "GET", f"/storage/volumes?{params}")
    if data.get("_error"):
        return {"clones": [], "error": data["_message"]}

    clones = []
    for v in data.get("records", []):
        clone = v.get("clone", {})
        clones.append(
            {
                "name": v.get("name", ""),
                "uuid": v.get("uuid", ""),
                "sizeGiB": round(v.get("size", 0) / (1024**3), 2),
                "state": v.get("state", ""),
                "parentVolume": clone.get("parent_volume", {}).get("name", ""),
                "parentSnapshot": clone.get("parent_snapshot", {}).get("name", ""),
                "splitInitiated": bool(clone.get("split_initiated", False)),
                "splitCompletePercent": clone.get("split_complete_percent", 0),
                "usedGiB": round(v.get("space", {}).get("used", 0) / (1024**3), 2),
            }
        )

    return {"clones": clones, "count": len(clones), "error": None}


def _create_flexclone(http, headers, event, user_id):
    """Create a writable FlexClone from a snapshot.

    ONTAP REST: POST /api/storage/volumes with a clone block

    The clone's security style and export policy are inherited from the parent
    volume and cannot be set at creation time.
    """
    svm = event.get("svm", SVM_NAME)
    clone_name = event.get("cloneName", "")
    parent_volume = event.get("parentVolume", "")
    parent_snapshot = event.get("parentSnapshot", "")

    if not clone_name or not parent_volume:
        return {"success": False, "error": "cloneName and parentVolume are required"}

    clone = {"parent_volume": {"name": parent_volume}}
    if parent_snapshot:
        clone["parent_snapshot"] = {"name": parent_snapshot}

    body = {"name": clone_name, "svm": {"name": svm}, "clone": clone}

    data = _ontap_request(http, headers, "POST", "/storage/volumes", body=body)
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(
        f"FlexClone created: {clone_name} from {parent_volume}"
        f"{':' + parent_snapshot if parent_snapshot else ''} by {user_id}"
    )
    return {"success": True, "jobId": data.get("job", {}).get("uuid", ""), "error": None}


def _split_flexclone(http, headers, event, user_id):
    """Start splitting a FlexClone from its parent.

    ONTAP REST: PATCH /api/storage/volumes/{uuid} with clone.split_initiated

    Splitting makes the clone independent, so it stops sharing blocks with the
    parent and its space consumption grows to the full size of the data.
    """
    volume_uuid = event.get("volumeUuid", "")
    volume_name = event.get("volumeName", "")

    if not volume_uuid:
        return {"success": False, "error": "volumeUuid is required"}

    data = _ontap_request(
        http,
        headers,
        "PATCH",
        f"/storage/volumes/{volume_uuid}",
        body={"clone": {"split_initiated": True}},
    )
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"FlexClone split started: {volume_name or volume_uuid} by {user_id}")
    return {"success": True, "jobId": data.get("job", {}).get("uuid", ""), "error": None}


# ─── SnapMirror inventory ─────────────────────────────────────────────────────


def _list_snapmirror_relationships(event):
    """List SnapMirror relationships whose destination is on this cluster.

    ONTAP REST: GET /api/snapmirror/relationships

    Read-only by design: creating or breaking a replication relationship is a
    cross-cluster operation that belongs with a change-managed runbook rather
    than a portal button.
    """
    # The field selection lives in OntapClient.RELATIONSHIP_FIELDS, including the
    # note that `last_transfer_size` is not a field on this endpoint — ONTAP 9.17
    # rejects the whole request and the list comes back empty. Per-transfer byte
    # counts come from getSnapmirrorTransfers instead.
    client, error = _client_or_error()
    if error:
        return {"relationships": [], "error": error["error"]}

    try:
        records = client.list_snapmirror_relationships()
    except Exception as e:
        return {"relationships": [], "error": _client_error(e)}

    relationships = []
    for r in records:
        src = r.get("source", {})
        dst = r.get("destination", {})
        relationships.append(
            {
                "uuid": r.get("uuid", ""),
                "sourcePath": src.get("path", ""),
                "sourceSvm": src.get("svm", {}).get("name", ""),
                "destinationPath": dst.get("path", ""),
                "destinationSvm": dst.get("svm", {}).get("name", ""),
                "state": r.get("state", ""),
                "healthy": bool(r.get("healthy", False)),
                "policy": r.get("policy", {}).get("name", ""),
                "lagTime": r.get("lag_time", ""),
                "lastTransferType": r.get("last_transfer_type", ""),
            }
        )

    return {"relationships": relationships, "count": len(relationships), "error": None}


def _get_snapmirror_transfers(event):
    """List recent transfers for one SnapMirror relationship.

    ONTAP REST: GET /api/snapmirror/relationships/{uuid}/transfers
    """
    relationship_uuid = event.get("relationshipUuid", "")

    if not relationship_uuid:
        return {"transfers": [], "error": "relationshipUuid is required"}

    client, error = _client_or_error()
    if error:
        return {"transfers": [], "error": error["error"]}

    try:
        records = client.list_snapmirror_transfers(relationship_uuid)
    except Exception as e:
        return {"transfers": [], "error": _client_error(e)}

    transfers = []
    for tr in records:
        transfers.append(
            {
                "state": tr.get("state", ""),
                "bytesTransferred": tr.get("bytes_transferred", 0),
                "endTime": tr.get("end_time", ""),
                "duration": tr.get("total_duration", ""),
            }
        )

    return {"transfers": transfers, "count": len(transfers), "error": None}


# ─── Vscan inventory ──────────────────────────────────────────────────────────


def _get_vscan_status(http, headers, event):
    """Report whether Vscan is enabled on the SVM.

    ONTAP REST: GET /api/protocols/vscan

    Vscan requires an external scan engine and a Vscan connector, so the portal
    reports configuration state and leaves provisioning to the scanner vendor's
    own tooling.
    """
    svm = event.get("svm", SVM_NAME)

    data = _ontap_request(http, headers, "GET", f"/protocols/vscan?svm.name={_qval(svm)}&fields=enabled")
    if data.get("_error"):
        return {"enabled": False, "error": data["_message"]}

    records = data.get("records", [])
    if not records:
        return {"enabled": False, "error": None}

    return {"enabled": bool(records[0].get("enabled", False)), "error": None}


def _list_vscan_policies(http, headers, event):
    """List Vscan on-access policies for the SVM.

    ONTAP REST: GET /api/protocols/vscan (on_access_policies sub-object)
    """
    svm = event.get("svm", SVM_NAME)
    params = (
        f"svm.name={_qval(svm)}&fields=on_access_policies.name,on_access_policies.enabled,"
        "on_access_policies.mandatory,on_access_policies.scope.max_file_size,"
        "on_access_policies.scope.exclude_paths,on_access_policies.scope.exclude_extensions"
    )

    data = _ontap_request(http, headers, "GET", f"/protocols/vscan?{params}")
    if data.get("_error"):
        return {"policies": [], "error": data["_message"]}

    policies = []
    for record in data.get("records", []):
        for p in record.get("on_access_policies", []):
            scope = p.get("scope", {})
            policies.append(
                {
                    "name": p.get("name", ""),
                    "enabled": bool(p.get("enabled", False)),
                    "mandatory": bool(p.get("mandatory", False)),
                    "maxFileSize": scope.get("max_file_size", 0),
                    "excludedPaths": scope.get("exclude_paths", []) or [],
                    "excludedExtensions": scope.get("exclude_extensions", []) or [],
                }
            )

    return {"policies": policies, "count": len(policies), "error": None}


# ─── FPolicy inventory ────────────────────────────────────────────────────────


def _get_fpolicy_status(http, headers, event):
    """Report FPolicy external engine connection status.

    ONTAP REST: GET /api/protocols/fpolicy (connections sub-object)
    """
    svm = event.get("svm", SVM_NAME)
    params = f"svm.name={_qval(svm)}&fields=connections.node.name,connections.policy.name,connections.server,connections.state"

    data = _ontap_request(http, headers, "GET", f"/protocols/fpolicy?{params}")
    if data.get("_error"):
        return {"connections": [], "error": data["_message"]}

    connections = []
    for record in data.get("records", []):
        for c in record.get("connections", []):
            connections.append(
                {
                    "node": c.get("node", {}).get("name", ""),
                    "policy": c.get("policy", {}).get("name", ""),
                    "server": c.get("server", ""),
                    "state": c.get("state", ""),
                }
            )

    return {"connections": connections, "count": len(connections), "error": None}


def _list_fpolicy_policies(http, headers, event):
    """List FPolicy policies for the SVM.

    ONTAP REST: GET /api/protocols/fpolicy (policies sub-object)
    """
    svm = event.get("svm", SVM_NAME)
    params = f"svm.name={_qval(svm)}&fields=policies.name,policies.enabled,policies.priority,policies.engine.name,policies.events"

    data = _ontap_request(http, headers, "GET", f"/protocols/fpolicy?{params}")
    if data.get("_error"):
        return {"policies": [], "error": data["_message"]}

    policies = []
    for record in data.get("records", []):
        for p in record.get("policies", []):
            events = p.get("events", [])
            policies.append(
                {
                    "name": p.get("name", ""),
                    "enabled": bool(p.get("enabled", False)),
                    "priority": p.get("priority", 0),
                    "engineType": p.get("engine", {}).get("name", ""),
                    "events": [e.get("name", "") if isinstance(e, dict) else str(e) for e in events],
                }
            )

    return {"policies": policies, "count": len(policies), "error": None}


def _list_fpolicy_events(http, headers, event):
    """List FPolicy event definitions for the SVM.

    ONTAP REST: GET /api/protocols/fpolicy (events sub-object)

    These are the event definitions that policies subscribe to, not a live feed
    of file access records.
    """
    svm = event.get("svm", SVM_NAME)
    params = f"svm.name={_qval(svm)}&fields=events.name,events.protocol,events.file_operations"

    data = _ontap_request(http, headers, "GET", f"/protocols/fpolicy?{params}")
    if data.get("_error"):
        return {"events": [], "error": data["_message"]}

    events = []
    for record in data.get("records", []):
        for e in record.get("events", []):
            ops = e.get("file_operations", {}) or {}
            enabled_ops = [name for name, on in ops.items() if on is True]
            events.append(
                {
                    "name": e.get("name", ""),
                    "protocol": e.get("protocol", ""),
                    "fileOperations": sorted(enabled_ops),
                }
            )

    return {"events": events, "count": len(events), "error": None}


# ─── SnapMirror write operations ──────────────────────────────────────────────
#
# Replication state changes are consequential, so the operations that redirect
# or discard data (break, resync, delete) require an explicit confirm flag.


def _update_snapmirror_now(event, user_id):
    """Start an on-demand SnapMirror transfer.

    ONTAP REST: POST /api/snapmirror/relationships/{uuid}/transfers

    On an uninitialised relationship this performs the initialize; otherwise it
    performs an incremental update.
    """
    rel_uuid = event.get("relationshipUuid", "")
    if not rel_uuid:
        return {"success": False, "error": "relationshipUuid is required"}

    client, error = _client_or_error()
    if error:
        return error

    try:
        data = client.update_snapmirror_now(rel_uuid)
    except Exception as e:
        return {"success": False, "error": _client_error(e)}

    logger.info(f"SnapMirror transfer started: {rel_uuid} by {user_id}")
    return {"success": True, "jobId": data.get("job", {}).get("uuid", ""), "error": None}


def _set_snapmirror_state(event, user_id, state):
    """Pause (quiesce) or resume a SnapMirror relationship.

    ONTAP REST: PATCH /api/snapmirror/relationships/{uuid} with a state value
    """
    rel_uuid = event.get("relationshipUuid", "")
    if not rel_uuid:
        return {"success": False, "error": "relationshipUuid is required"}

    client, error = _client_or_error()
    if error:
        return error

    try:
        data = client.set_snapmirror_state(rel_uuid, state)
    except Exception as e:
        return {"success": False, "error": _client_error(e)}

    logger.info(f"SnapMirror state set to {state}: {rel_uuid} by {user_id}")
    return {
        "success": True,
        "state": state,
        "jobId": data.get("job", {}).get("uuid", ""),
        "error": None,
    }


def _break_snapmirror(event, user_id):
    """Break a SnapMirror relationship so the destination can serve data.

    ONTAP REST: PATCH /api/snapmirror/relationships/{uuid} state=broken_off

    After a break the destination becomes writable and diverges from the source,
    so this is gated behind an explicit confirmation.
    """
    rel_uuid = event.get("relationshipUuid", "")
    if not rel_uuid:
        return {"success": False, "error": "relationshipUuid is required"}
    if not event.get("confirm", False):
        return {"success": False, "error": "confirm=true is required"}

    client, error = _client_or_error()
    if error:
        return error

    try:
        data = client.break_snapmirror(rel_uuid)
    except Exception as e:
        return {"success": False, "error": _client_error(e)}

    logger.info(f"SnapMirror broken off: {rel_uuid} by {user_id}")
    return {
        "success": True,
        "state": "broken_off",
        "jobId": data.get("job", {}).get("uuid", ""),
        "error": None,
    }


def _resync_snapmirror(event, user_id):
    """Resynchronise a broken SnapMirror relationship.

    ONTAP REST: PATCH /api/snapmirror/relationships/{uuid} state=snapmirrored

    Resync discards changes written to the destination after the break, so it
    requires an explicit confirmation.
    """
    rel_uuid = event.get("relationshipUuid", "")
    if not rel_uuid:
        return {"success": False, "error": "relationshipUuid is required"}
    if not event.get("confirm", False):
        return {"success": False, "error": "confirm=true is required"}

    client, error = _client_or_error()
    if error:
        return error

    try:
        data = client.resync_snapmirror(rel_uuid)
    except Exception as e:
        return {"success": False, "error": _client_error(e)}

    logger.info(f"SnapMirror resync started: {rel_uuid} by {user_id}")
    return {
        "success": True,
        "state": "snapmirrored",
        "jobId": data.get("job", {}).get("uuid", ""),
        "error": None,
    }


def _abort_snapmirror_transfer(event, user_id):
    """Abort an in-progress SnapMirror transfer.

    ONTAP REST: PATCH /api/snapmirror/relationships/{uuid}/transfers/{transfer_uuid}
    with state=aborted
    """
    rel_uuid = event.get("relationshipUuid", "")
    transfer_uuid = event.get("transferUuid", "")
    if not rel_uuid or not transfer_uuid:
        return {
            "success": False,
            "error": "relationshipUuid and transferUuid are required",
        }

    client, error = _client_or_error()
    if error:
        return error

    try:
        client.abort_snapmirror_transfer(rel_uuid, transfer_uuid)
    except Exception as e:
        return {"success": False, "error": _client_error(e)}

    logger.info(f"SnapMirror transfer aborted: {transfer_uuid} by {user_id}")
    return {"success": True, "error": None}


def _delete_snapmirror(event, user_id):
    """Delete a SnapMirror relationship.

    ONTAP REST: DELETE /api/snapmirror/relationships/{uuid}

    The destination volume is left in place; only the relationship is removed.
    """
    rel_uuid = event.get("relationshipUuid", "")
    if not rel_uuid:
        return {"success": False, "error": "relationshipUuid is required"}
    if not event.get("confirm", False):
        return {"success": False, "error": "confirm=true is required"}

    client, error = _client_or_error()
    if error:
        return error

    try:
        data = client.delete_snapmirror(rel_uuid)
    except Exception as e:
        return {"success": False, "error": _client_error(e)}

    logger.info(f"SnapMirror relationship deleted: {rel_uuid} by {user_id}")
    return {"success": True, "jobId": data.get("job", {}).get("uuid", ""), "error": None}


# ─── Vscan write operations ───────────────────────────────────────────────────


def _set_vscan_enabled(http, headers, event, user_id):
    """Enable or disable Vscan on the SVM.

    ONTAP REST: PATCH /api/protocols/vscan/{svm.uuid}
    """
    svm = event.get("svm", SVM_NAME)
    enabled = event.get("enabled")
    if enabled is None:
        return {"success": False, "error": "enabled is required"}

    svm_uuid, err = _get_svm_uuid(http, headers, svm)
    if err:
        return {"success": False, "error": err}

    data = _ontap_request(http, headers, "PATCH", f"/protocols/vscan/{svm_uuid}", body={"enabled": bool(enabled)})
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"Vscan enabled={bool(enabled)} on {svm} by {user_id}")
    return {"success": True, "enabled": bool(enabled), "error": None}


def _create_vscan_policy(http, headers, event, user_id):
    """Create a Vscan on-access policy.

    ONTAP REST: POST /api/protocols/vscan/{svm.uuid}/on-access-policies

    ONTAP enables a policy on creation. Scanning still requires a scanner pool
    backed by an external scan engine.
    """
    svm = event.get("svm", SVM_NAME)
    name = event.get("name", "")
    if not name:
        return {"success": False, "error": "name is required"}

    svm_uuid, err = _get_svm_uuid(http, headers, svm)
    if err:
        return {"success": False, "error": err}

    scope = {}
    if event.get("maxFileSize"):
        scope["max_file_size"] = int(event["maxFileSize"])
    if event.get("excludedPaths"):
        scope["exclude_paths"] = event["excludedPaths"]
    if event.get("excludedExtensions"):
        scope["exclude_extensions"] = event["excludedExtensions"]

    body = {"name": name, "mandatory": bool(event.get("mandatory", False))}
    if scope:
        body["scope"] = scope

    data = _ontap_request(
        http,
        headers,
        "POST",
        f"/protocols/vscan/{svm_uuid}/on-access-policies",
        body=body,
    )
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"Vscan on-access policy created: {name} by {user_id}")
    return {"success": True, "name": name, "error": None}


def _set_vscan_policy_enabled(http, headers, event, user_id):
    """Enable or disable a Vscan on-access policy.

    ONTAP REST: PATCH /api/protocols/vscan/{svm.uuid}/on-access-policies/{name}
    """
    svm = event.get("svm", SVM_NAME)
    name = event.get("name", "")
    enabled = event.get("enabled")
    if not name or enabled is None:
        return {"success": False, "error": "name and enabled are required"}

    svm_uuid, err = _get_svm_uuid(http, headers, svm)
    if err:
        return {"success": False, "error": err}

    data = _ontap_request(
        http,
        headers,
        "PATCH",
        f"/protocols/vscan/{svm_uuid}/on-access-policies/{quote(name, safe='')}",
        body={"enabled": bool(enabled)},
    )
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"Vscan policy {name} enabled={bool(enabled)} by {user_id}")
    return {"success": True, "enabled": bool(enabled), "error": None}


def _delete_vscan_policy(http, headers, event, user_id):
    """Delete a Vscan on-access policy.

    ONTAP REST: DELETE /api/protocols/vscan/{svm.uuid}/on-access-policies/{name}

    Deleting the policy takes its scope out of scanning, so it is confirm-gated
    here as well as in the UI. A caller that bypasses the UI is refused too.
    """
    svm = event.get("svm", SVM_NAME)
    name = event.get("name", "")
    if not name:
        return {"success": False, "error": "name is required"}
    if not event.get("confirm", False):
        return {"success": False, "error": "confirm=true is required"}

    svm_uuid, err = _get_svm_uuid(http, headers, svm)
    if err:
        return {"success": False, "error": err}

    data = _ontap_request(
        http,
        headers,
        "DELETE",
        f"/protocols/vscan/{svm_uuid}/on-access-policies/{quote(name, safe='')}",
    )
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"Vscan policy deleted: {name} by {user_id}")
    return {"success": True, "error": None}


# ─── FPolicy write operations ─────────────────────────────────────────────────


def _create_fpolicy_event(http, headers, event, user_id):
    """Create an FPolicy event definition.

    ONTAP REST: POST /api/protocols/fpolicy/{svm.uuid}/events

    An event names the protocol and the file operations to watch. Policies then
    subscribe to events by name.
    """
    svm = event.get("svm", SVM_NAME)
    name = event.get("name", "")
    protocol = event.get("protocol", "")
    file_operations = event.get("fileOperations") or []

    if not name or not protocol:
        return {"success": False, "error": "name and protocol are required"}
    if not file_operations:
        return {"success": False, "error": "at least one file operation is required"}

    body = {
        "name": name,
        "protocol": protocol,
        "file_operations": {op: True for op in file_operations},
    }

    svm_uuid, err = _get_svm_uuid(http, headers, svm)
    if err:
        return {"success": False, "error": err}

    data = _ontap_request(http, headers, "POST", f"/protocols/fpolicy/{svm_uuid}/events", body=body)
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"FPolicy event created: {name} ({protocol}) by {user_id}")
    return {"success": True, "name": name, "error": None}


def _delete_fpolicy_event(http, headers, event, user_id):
    """Delete an FPolicy event definition.

    ONTAP REST: DELETE /api/protocols/fpolicy/{svm.uuid}/events/{name}

    An event still referenced by a policy cannot be removed; ONTAP rejects it.
    Removing it stops the policies that subscribe to it, so it is confirm-gated.
    """
    svm = event.get("svm", SVM_NAME)
    name = event.get("name", "")
    if not name:
        return {"success": False, "error": "name is required"}
    if not event.get("confirm", False):
        return {"success": False, "error": "confirm=true is required"}

    svm_uuid, err = _get_svm_uuid(http, headers, svm)
    if err:
        return {"success": False, "error": err}

    data = _ontap_request(
        http,
        headers,
        "DELETE",
        f"/protocols/fpolicy/{svm_uuid}/events/{quote(name, safe='')}",
    )
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"FPolicy event deleted: {name} by {user_id}")
    return {"success": True, "error": None}


def _create_fpolicy_policy(http, headers, event, user_id):
    """Create an FPolicy policy.

    ONTAP REST: POST /api/protocols/fpolicy/{svm.uuid}/policies

    A policy needs the events it monitors and an engine. The engine must already
    exist; the portal does not create external engine definitions.
    """
    svm = event.get("svm", SVM_NAME)
    name = event.get("name", "")
    events = event.get("events") or []
    engine_name = event.get("engineName", "native")
    priority = event.get("priority")

    if not name:
        return {"success": False, "error": "name is required"}
    if not events:
        return {"success": False, "error": "at least one event is required"}

    svm_uuid, err = _get_svm_uuid(http, headers, svm)
    if err:
        return {"success": False, "error": err}

    body = {
        "name": name,
        "events": [{"name": e} for e in events],
        "engine": {"name": engine_name},
    }
    # ONTAP treats a policy with a priority as enabled.
    if priority is not None:
        body["priority"] = int(priority)

    data = _ontap_request(http, headers, "POST", f"/protocols/fpolicy/{svm_uuid}/policies", body=body)
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"FPolicy policy created: {name} by {user_id}")
    return {"success": True, "name": name, "error": None}


def _set_fpolicy_policy_enabled(http, headers, event, user_id):
    """Enable or disable an FPolicy policy.

    ONTAP REST: PATCH /api/protocols/fpolicy/{svm.uuid}/policies/{name}

    ONTAP requires a priority when enabling a policy; it is not needed when
    disabling one.
    """
    svm = event.get("svm", SVM_NAME)
    name = event.get("name", "")
    enabled = event.get("enabled")
    priority = event.get("priority")

    if not name or enabled is None:
        return {"success": False, "error": "name and enabled are required"}
    if enabled and priority is None:
        return {"success": False, "error": "priority is required when enabling a policy"}

    svm_uuid, err = _get_svm_uuid(http, headers, svm)
    if err:
        return {"success": False, "error": err}

    body = {"enabled": bool(enabled)}
    if enabled:
        body["priority"] = int(priority)

    data = _ontap_request(
        http,
        headers,
        "PATCH",
        f"/protocols/fpolicy/{svm_uuid}/policies/{quote(name, safe='')}",
        body=body,
    )
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"FPolicy policy {name} enabled={bool(enabled)} by {user_id}")
    return {"success": True, "enabled": bool(enabled), "error": None}


def _delete_fpolicy_policy(http, headers, event, user_id):
    """Delete an FPolicy policy.

    ONTAP REST: DELETE /api/protocols/fpolicy/{svm.uuid}/policies/{name}

    A policy has to be disabled before it can be deleted. Deleting it stops the
    audit events it generates, so it is confirm-gated.
    """
    svm = event.get("svm", SVM_NAME)
    name = event.get("name", "")
    if not name:
        return {"success": False, "error": "name is required"}
    if not event.get("confirm", False):
        return {"success": False, "error": "confirm=true is required"}

    svm_uuid, err = _get_svm_uuid(http, headers, svm)
    if err:
        return {"success": False, "error": err}

    data = _ontap_request(
        http,
        headers,
        "DELETE",
        f"/protocols/fpolicy/{svm_uuid}/policies/{quote(name, safe='')}",
    )
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"FPolicy policy deleted: {name} by {user_id}")
    return {"success": True, "error": None}


# ─── Cluster and SVM peering ──────────────────────────────────────────────────
#
# Peering is the area that most often forces operators to the ONTAP CLI, because
# it is not exposed in the AWS console. Both halves of a peer relationship have
# to be configured, and the authentication passphrase has to travel between them.


def _list_intercluster_lifs(http, headers, event):
    """List intercluster LIFs, which peering depends on.

    ONTAP REST: GET /api/network/ip/interfaces

    Without an intercluster LIF on both sides, creating a cluster peer fails.
    Listing them first is the quickest way to see whether the prerequisite holds.
    """
    params = (
        "services=intercluster_core"
        "&fields=name,uuid,ip.address,enabled,state,location.node.name,svm.name"
        "&max_records=100"
    )

    data = _ontap_request(http, headers, "GET", f"/network/ip/interfaces?{params}")
    if data.get("_error"):
        return {"lifs": [], "error": data["_message"]}

    lifs = []
    for r in data.get("records", []):
        lifs.append(
            {
                "name": r.get("name", ""),
                "uuid": r.get("uuid", ""),
                "address": r.get("ip", {}).get("address", ""),
                "enabled": bool(r.get("enabled", False)),
                "state": r.get("state", ""),
                "node": r.get("location", {}).get("node", {}).get("name", ""),
            }
        )

    return {"lifs": lifs, "count": len(lifs), "error": None}


def _list_cluster_peers(http, headers, event):
    """List cluster peer relationships.

    ONTAP REST: GET /api/cluster/peers
    """
    params = (
        "fields=name,uuid,status.state,status.update_time,remote.name,"
        "remote.ip_addresses,authentication.state,encryption.state,ipspace.name"
        "&max_records=100"
    )

    data = _ontap_request(http, headers, "GET", f"/cluster/peers?{params}")
    if data.get("_error"):
        return {"peers": [], "error": data["_message"]}

    peers = []
    for r in data.get("records", []):
        remote = r.get("remote", {})
        peers.append(
            {
                "name": r.get("name", ""),
                "uuid": r.get("uuid", ""),
                "state": r.get("status", {}).get("state", ""),
                "updateTime": r.get("status", {}).get("update_time", ""),
                "remoteName": remote.get("name", ""),
                "remoteAddresses": remote.get("ip_addresses", []) or [],
                "authState": r.get("authentication", {}).get("state", ""),
                "encryptionState": r.get("encryption", {}).get("state", ""),
                "ipspace": r.get("ipspace", {}).get("name", ""),
            }
        )

    return {"peers": peers, "count": len(peers), "error": None}


def _create_cluster_peer(http, headers, event, user_id):
    """Create a cluster peer relationship.

    ONTAP REST: POST /api/cluster/peers

    Two ways to authenticate:
    - generatePassphrase=true asks ONTAP to produce a passphrase, which is
      returned once and must then be entered on the remote cluster.
    - Supplying a passphrase matches one already generated on the remote side.

    The remote addresses are the intercluster LIF addresses of the other cluster.
    """
    remote_addresses = event.get("remoteAddresses") or []
    passphrase = event.get("passphrase", "")
    generate = bool(event.get("generatePassphrase", False))

    if not remote_addresses:
        return {"success": False, "error": "remoteAddresses is required"}
    if not generate and not passphrase:
        return {
            "success": False,
            "error": "either passphrase or generatePassphrase=true is required",
        }

    body = {"remote": {"ip_addresses": remote_addresses}}
    if event.get("name"):
        body["name"] = event["name"]
    if event.get("ipspace"):
        body["ipspace"] = {"name": event["ipspace"]}
    if generate:
        body["generate_passphrase"] = True
    else:
        body["authentication"] = {"passphrase": passphrase}

    data = _ontap_request(http, headers, "POST", "/cluster/peers", body=body)
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    # ONTAP returns the generated passphrase in the creation response only.
    generated = ""
    records = data.get("records") or []
    if records:
        generated = records[0].get("authentication", {}).get("passphrase", "")
    if not generated:
        generated = data.get("authentication", {}).get("passphrase", "")

    logger.info(f"Cluster peer created for {remote_addresses} by {user_id}")
    return {
        "success": True,
        "passphrase": generated,
        "error": None,
    }


def _accept_cluster_peer(http, headers, event, user_id):
    """Complete a cluster peer relationship by supplying the passphrase.

    ONTAP REST: PATCH /api/cluster/peers/{uuid}
    """
    uuid = event.get("uuid", "")
    passphrase = event.get("passphrase", "")
    if not uuid or not passphrase:
        return {"success": False, "error": "uuid and passphrase are required"}

    data = _ontap_request(
        http,
        headers,
        "PATCH",
        f"/cluster/peers/{uuid}",
        body={"authentication": {"passphrase": passphrase}},
    )
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"Cluster peer accepted: {uuid} by {user_id}")
    return {"success": True, "error": None}


def _delete_cluster_peer(http, headers, event, user_id):
    """Delete a cluster peer relationship.

    ONTAP REST: DELETE /api/cluster/peers/{uuid}

    SVM peers and replication relationships that depend on it must be removed
    first; ONTAP rejects the delete otherwise.
    """
    uuid = event.get("uuid", "")
    if not uuid:
        return {"success": False, "error": "uuid is required"}
    if not event.get("confirm", False):
        return {"success": False, "error": "confirm=true is required"}

    data = _ontap_request(http, headers, "DELETE", f"/cluster/peers/{uuid}")
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"Cluster peer deleted: {uuid} by {user_id}")
    return {"success": True, "error": None}


def _list_svm_peers(http, headers, event):
    """List SVM peer relationships.

    ONTAP REST: GET /api/svm/peers
    """
    params = "fields=name,uuid,state,applications,svm.name,peer.svm.name,peer.cluster.name&max_records=100"

    data = _ontap_request(http, headers, "GET", f"/svm/peers?{params}")
    if data.get("_error"):
        return {"peers": [], "error": data["_message"]}

    peers = []
    for r in data.get("records", []):
        peer = r.get("peer", {})
        peers.append(
            {
                "name": r.get("name", ""),
                "uuid": r.get("uuid", ""),
                "state": r.get("state", ""),
                "applications": r.get("applications", []) or [],
                "localSvm": r.get("svm", {}).get("name", ""),
                "peerSvm": peer.get("svm", {}).get("name", ""),
                "peerCluster": peer.get("cluster", {}).get("name", ""),
            }
        )

    return {"peers": peers, "count": len(peers), "error": None}


def _create_svm_peer(http, headers, event, user_id):
    """Create an SVM peer relationship.

    ONTAP REST: POST /api/svm/peers

    The clusters must already be peered. The relationship starts in a pending
    state and the remote side accepts it.
    """
    local_svm = event.get("localSvm", SVM_NAME)
    peer_svm = event.get("peerSvm", "")
    peer_cluster = event.get("peerCluster", "")
    applications = event.get("applications") or ["snapmirror"]

    if not peer_svm:
        return {"success": False, "error": "peerSvm is required"}

    body = {
        "svm": {"name": local_svm},
        "peer": {"svm": {"name": peer_svm}},
        "applications": applications,
    }
    if peer_cluster:
        body["peer"]["cluster"] = {"name": peer_cluster}

    data = _ontap_request(http, headers, "POST", "/svm/peers", body=body)
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"SVM peer created: {local_svm} <-> {peer_svm} by {user_id}")
    return {"success": True, "error": None}


def _accept_svm_peer(http, headers, event, user_id):
    """Accept a pending SVM peer relationship.

    ONTAP REST: PATCH /api/svm/peers/{uuid} with state=peered
    """
    uuid = event.get("uuid", "")
    if not uuid:
        return {"success": False, "error": "uuid is required"}

    data = _ontap_request(http, headers, "PATCH", f"/svm/peers/{uuid}", body={"state": "peered"})
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"SVM peer accepted: {uuid} by {user_id}")
    return {"success": True, "error": None}


def _delete_svm_peer(http, headers, event, user_id):
    """Delete an SVM peer relationship.

    ONTAP REST: DELETE /api/svm/peers/{uuid}
    """
    uuid = event.get("uuid", "")
    if not uuid:
        return {"success": False, "error": "uuid is required"}
    if not event.get("confirm", False):
        return {"success": False, "error": "confirm=true is required"}

    data = _ontap_request(http, headers, "DELETE", f"/svm/peers/{uuid}")
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"SVM peer deleted: {uuid} by {user_id}")
    return {"success": True, "error": None}


# ─── Cluster inventory and services ───────────────────────────────────────────


def _get_cluster_info(http, headers, event):
    """Report cluster identity and version.

    ONTAP REST: GET /api/cluster
    """
    data = _ontap_request(http, headers, "GET", "/cluster?fields=name,version,management_interfaces")
    if data.get("_error"):
        return {"error": data["_message"]}

    version = data.get("version", {})
    return {
        "name": data.get("name", ""),
        "version": version.get("full", ""),
        "generation": version.get("generation"),
        "major": version.get("major"),
        "minor": version.get("minor"),
        "error": None,
    }


def _list_nodes(http, headers, event):
    """List cluster nodes and their health.

    ONTAP REST: GET /api/cluster/nodes
    """
    params = "fields=name,uuid,state,model,serial_number,version.full,uptime,ha.enabled,ha.partners.name&max_records=50"

    data = _ontap_request(http, headers, "GET", f"/cluster/nodes?{params}")
    if data.get("_error"):
        return {"nodes": [], "error": data["_message"]}

    nodes = []
    for r in data.get("records", []):
        ha = r.get("ha", {})
        nodes.append(
            {
                "name": r.get("name", ""),
                "uuid": r.get("uuid", ""),
                "state": r.get("state", ""),
                "model": r.get("model", ""),
                "serialNumber": r.get("serial_number", ""),
                "version": r.get("version", {}).get("full", ""),
                "uptimeSeconds": r.get("uptime", 0),
                "haEnabled": bool(ha.get("enabled", False)),
                "haPartners": [p.get("name", "") for p in ha.get("partners", [])],
            }
        )

    return {"nodes": nodes, "count": len(nodes), "error": None}


def _list_licenses(http, headers, event):
    """List installed licence packages.

    ONTAP REST: GET /api/cluster/licensing/licenses
    """
    data = _ontap_request(
        http,
        headers,
        "GET",
        "/cluster/licensing/licenses?fields=name,state,scope,licenses.expiry_time&max_records=100",
    )
    if data.get("_error"):
        return {"licenses": [], "error": data["_message"]}

    licenses = []
    for r in data.get("records", []):
        entries = r.get("licenses", []) or []
        licenses.append(
            {
                "name": r.get("name", ""),
                "state": r.get("state", ""),
                "scope": r.get("scope", ""),
                "expiryTime": entries[0].get("expiry_time", "") if entries else "",
            }
        )

    return {"licenses": licenses, "count": len(licenses), "error": None}


def _list_network_interfaces(http, headers, event):
    """List IP interfaces (LIFs) on the cluster.

    ONTAP REST: GET /api/network/ip/interfaces
    """
    params = (
        "fields=name,uuid,ip.address,ip.netmask,enabled,state,scope,svm.name,"
        "location.node.name,location.port.name,services&max_records=200"
    )

    data = _ontap_request(http, headers, "GET", f"/network/ip/interfaces?{params}")
    if data.get("_error"):
        return {"interfaces": [], "error": data["_message"]}

    interfaces = []
    for r in data.get("records", []):
        loc = r.get("location", {})
        interfaces.append(
            {
                "name": r.get("name", ""),
                "uuid": r.get("uuid", ""),
                "address": r.get("ip", {}).get("address", ""),
                "netmask": r.get("ip", {}).get("netmask", ""),
                "enabled": bool(r.get("enabled", False)),
                "state": r.get("state", ""),
                "scope": r.get("scope", ""),
                "svmName": r.get("svm", {}).get("name", ""),
                "node": loc.get("node", {}).get("name", ""),
                "port": loc.get("port", {}).get("name", ""),
                "services": r.get("services", []) or [],
            }
        )

    return {"interfaces": interfaces, "count": len(interfaces), "error": None}


def _set_network_interface_enabled(http, headers, event, user_id):
    """Bring an IP interface up or down.

    ONTAP REST: PATCH /api/network/ip/interfaces/{uuid}

    Disabling the interface that carries the management or data path will cut
    that path, so callers should confirm which LIF they are changing.
    """
    uuid = event.get("uuid", "")
    enabled = event.get("enabled")
    if not uuid or enabled is None:
        return {"success": False, "error": "uuid and enabled are required"}
    if not enabled and not event.get("confirm", False):
        return {"success": False, "error": "confirm=true is required to disable a LIF"}

    data = _ontap_request(
        http,
        headers,
        "PATCH",
        f"/network/ip/interfaces/{uuid}",
        body={"enabled": bool(enabled)},
    )
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"LIF {uuid} enabled={bool(enabled)} by {user_id}")
    return {"success": True, "enabled": bool(enabled), "error": None}


def _get_dns_config(http, headers, event):
    """Read the DNS configuration for the SVM.

    ONTAP REST: GET /api/name-services/dns
    """
    svm = event.get("svm", SVM_NAME)
    data = _ontap_request(
        http,
        headers,
        "GET",
        f"/name-services/dns?svm.name={_qval(svm)}&fields=domains,servers,dynamic_dns.enabled",
    )
    if data.get("_error"):
        return {"domains": [], "servers": [], "error": data["_message"]}

    records = data.get("records", [])
    if not records:
        return {"domains": [], "servers": [], "dynamicDns": False, "error": None}

    r = records[0]
    return {
        "domains": r.get("domains", []) or [],
        "servers": r.get("servers", []) or [],
        "dynamicDns": bool(r.get("dynamic_dns", {}).get("enabled", False)),
        "error": None,
    }


def _update_dns_config(http, headers, event, user_id):
    """Update DNS domains and servers for the SVM.

    ONTAP REST: PATCH /api/name-services/dns/{svm.uuid}

    An AD-joined SVM resolves domain controllers through these servers, so a
    wrong value here breaks SMB and, on AD-joined SVMs, S3 Access Point data
    operations as well.
    """
    svm = event.get("svm", SVM_NAME)
    domains = event.get("domains") or []
    servers = event.get("servers") or []

    if not domains or not servers:
        return {"success": False, "error": "domains and servers are required"}

    svm_uuid, err = _get_svm_uuid(http, headers, svm)
    if err:
        return {"success": False, "error": err}

    data = _ontap_request(
        http,
        headers,
        "PATCH",
        f"/name-services/dns/{svm_uuid}",
        body={"domains": domains, "servers": servers},
    )
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"DNS updated for {svm} by {user_id}")
    return {"success": True, "error": None}


def _list_protocol_services(http, headers, event):
    """Report which data protocols are enabled on the SVM.

    ONTAP REST: GET /api/protocols/nfs/services, /api/protocols/cifs/services,
    /api/protocols/s3/services
    """
    svm = event.get("svm", SVM_NAME)
    services = []

    nfs = _ontap_request(http, headers, "GET", f"/protocols/nfs/services?svm.name={_qval(svm)}&fields=enabled,state")
    if not nfs.get("_error"):
        rec = (nfs.get("records") or [{}])[0]
        services.append(
            {
                "protocol": "nfs",
                "enabled": bool(rec.get("enabled", False)),
                "state": rec.get("state", ""),
                "detail": "",
            }
        )

    cifs = _ontap_request(
        http,
        headers,
        "GET",
        f"/protocols/cifs/services?svm.name={_qval(svm)}&fields=enabled,name,ad_domain.fqdn",
    )
    if not cifs.get("_error"):
        recs = cifs.get("records") or []
        rec = recs[0] if recs else {}
        services.append(
            {
                "protocol": "cifs",
                "enabled": bool(rec.get("enabled", False)) if recs else False,
                "state": "",
                # An AD-joined SVM shows its domain here; empty means not joined.
                "detail": rec.get("ad_domain", {}).get("fqdn", "") if recs else "",
            }
        )

    s3 = _ontap_request(http, headers, "GET", f"/protocols/s3/services?svm.name={_qval(svm)}&fields=enabled,name")
    if not s3.get("_error"):
        recs = s3.get("records") or []
        rec = recs[0] if recs else {}
        services.append(
            {
                "protocol": "s3",
                "enabled": bool(rec.get("enabled", False)) if recs else False,
                "state": "",
                "detail": rec.get("name", "") if recs else "",
            }
        )

    return {"services": services, "count": len(services), "error": None}


def _set_protocol_service_enabled(http, headers, event, user_id):
    """Enable or disable a data protocol on the SVM.

    ONTAP REST: PATCH /api/protocols/{nfs|cifs|s3}/services/{svm.uuid}

    Disabling a protocol disconnects clients using it, so it is confirm-gated.
    """
    svm = event.get("svm", SVM_NAME)
    protocol = event.get("protocol", "")
    enabled = event.get("enabled")

    if protocol not in ("nfs", "cifs", "s3"):
        return {"success": False, "error": "protocol must be nfs, cifs or s3"}
    if enabled is None:
        return {"success": False, "error": "enabled is required"}
    if not enabled and not event.get("confirm", False):
        return {
            "success": False,
            "error": "confirm=true is required to disable a protocol",
        }

    svm_uuid, err = _get_svm_uuid(http, headers, svm)
    if err:
        return {"success": False, "error": err}

    data = _ontap_request(
        http,
        headers,
        "PATCH",
        f"/protocols/{protocol}/services/{svm_uuid}",
        body={"enabled": bool(enabled)},
    )
    if data.get("_error"):
        return {"success": False, "error": data["_message"]}

    logger.info(f"Protocol {protocol} enabled={bool(enabled)} on {svm} by {user_id}")
    return {"success": True, "enabled": bool(enabled), "error": None}


def _list_jobs(http, headers, event):
    """List recent asynchronous jobs.

    ONTAP REST: GET /api/cluster/jobs

    FlexCache creation, FlexClone split, SnapMirror transfers and peering all
    run as jobs, so this is where their progress and failure reasons appear.
    """
    params = "fields=uuid,description,state,message,code,start_time,end_time&max_records=50"

    data = _ontap_request(http, headers, "GET", f"/cluster/jobs?{params}")
    if data.get("_error"):
        return {"jobs": [], "error": data["_message"]}

    jobs = []
    for r in data.get("records", []):
        jobs.append(
            {
                "uuid": r.get("uuid", ""),
                "description": r.get("description", ""),
                "state": r.get("state", ""),
                "message": r.get("message", ""),
                "code": r.get("code", 0),
                "startTime": r.get("start_time", ""),
                "endTime": r.get("end_time", ""),
            }
        )

    return {"jobs": jobs, "count": len(jobs), "error": None}


def _get_job(http, headers, event):
    """Report the state of a single asynchronous job.

    ONTAP REST: GET /api/cluster/jobs/{uuid}
    """
    job_uuid = event.get("jobId", "")
    if not job_uuid:
        return {"error": "jobId is required"}

    data = _ontap_request(
        http,
        headers,
        "GET",
        f"/cluster/jobs/{job_uuid}?fields=uuid,description,state,message,code,start_time,end_time",
    )
    if data.get("_error"):
        return {"error": data["_message"]}

    return {
        "uuid": data.get("uuid", ""),
        "description": data.get("description", ""),
        "state": data.get("state", ""),
        "message": data.get("message", ""),
        "code": data.get("code", 0),
        "startTime": data.get("start_time", ""),
        "endTime": data.get("end_time", ""),
        "error": None,
    }
