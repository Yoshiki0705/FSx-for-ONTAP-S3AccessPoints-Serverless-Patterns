from __future__ import annotations

import json
import logging
import os

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")

# Group → AP mapping (JSON from environment variable)
GROUP_AP_MAPPING = json.loads(os.environ.get("GROUP_AP_MAPPING", "{}"))
DEFAULT_AP_ALIAS = os.environ.get("S3_AP_ALIAS", "")
# Where the notification bridge writes FPolicy / Transfer Family events. Empty
# when folder watch is not deployed, which the inbox reports as "not configured"
# rather than as an empty list.
NOTIFICATION_TABLE = os.environ.get("NOTIFICATION_TABLE_NAME", "")
# Cognito group -> allowed path prefixes, the same multi-tenancy boundary the
# agent applies to file access.
GROUP_PATH_PREFIXES = json.loads(os.environ.get("GROUP_PATH_PREFIXES", "{}"))


def resolve_ap_alias(groups: list[str]) -> str:
    """Resolve S3 AP alias based on user's Cognito groups.

    Returns the first matching group's AP alias, or the default.
    This enables per-team file visibility (My Files).
    """
    if GROUP_AP_MAPPING and groups:
        for group_name, ap_alias in GROUP_AP_MAPPING.items():
            if group_name in groups:
                return ap_alias
    return DEFAULT_AP_ALIAS


def _allowed_prefixes(user_groups: list[str]) -> list[str]:
    """Path prefixes this caller may see, or [] for no restriction.

    Mirrors `_get_allowed_prefixes` in functions/agent-chat: same environment
    variable, same storage-admin bypass, same "no configured prefixes means no
    restriction" reading. Two copies of a boundary can disagree, so if a third
    consumer appears this belongs in a shared module.
    """
    if not GROUP_PATH_PREFIXES or not user_groups:
        return []
    if "storage-admin" in user_groups:
        return []
    prefixes: list[str] = []
    for group in user_groups:
        prefixes.extend(GROUP_PATH_PREFIXES.get(group, []))
    return sorted(set(prefixes))


# The trash lives under this prefix in the same bucket. Permanent deletion is
# confined to it: to destroy an object you first move it here, which turns one
# careless click into two deliberate ones.
TRASH_PREFIX = ".trash/"

# S3's own limit. A longer key is rejected here so the failure names the key rather
# than arriving as an opaque ClientError.
MAX_KEY_BYTES = 1024


def _reject_key(key: str, allowed: list[str], *, field: str) -> dict | None:
    """Why this key may not be used, or None if it may.

    Every action that names an object runs its keys through here. Three classes of
    problem, and the order matters only in what the caller is told first.

    Shape. An empty key, a leading separator, a doubled separator, a control
    character, or anything over S3's length limit. None of these can be produced by
    the UI, so a request carrying one is not a mistake worth guessing at.

    A `..` segment. S3 keys are literal — `a/../b` is a key, not a path, and no
    resolution happens. That is exactly why it is refused: it means one thing to
    the prefix comparison below and another to a person, and a key that reads as an
    escape has no legitimate use in this portal.

    Scope. `GROUP_PATH_PREFIXES` is the multi-tenancy boundary. It was applied to
    the notification inbox alone, so where per-team prefixes were configured, a
    caller could rename, trash or restore an object under another team's prefix by
    naming it directly, and mint a presigned PUT into it. The endpoint is
    authenticated but the key was never checked against the caller.

    Args:
        key: The object key from the request.
        allowed: Prefixes this caller may touch; empty means unrestricted.
        field: Request field the key arrived in, named in the message.

    Returns:
        A failure payload fragment, or None when the key is acceptable.
    """
    if not key:
        return {"error": f"{field} is required"}
    if len(key.encode("utf-8")) > MAX_KEY_BYTES:
        return {"error": f"{field} exceeds the {MAX_KEY_BYTES}-byte key limit"}
    if key.startswith("/") or "//" in key:
        return {"error": f"{field} must not start with or contain an empty path segment"}
    if any(segment == ".." for segment in key.split("/")):
        return {"error": f"{field} must not contain a '..' segment"}
    if any(character < " " or character == "\x7f" for character in key):
        return {"error": f"{field} must not contain control characters"}
    if allowed and not any(key.startswith(prefix) for prefix in allowed):
        # Names the boundary without listing every other tenant's prefixes.
        return {"error": f"{field} is outside the prefixes your groups may access"}
    return None


def _scoped_trash_key(key: str) -> str:
    """Where `key` goes when trashed."""
    return f"{TRASH_PREFIX}{key}"


def _object_exists(bucket: str, key: str) -> bool:
    """Whether the object is there, used to refuse a silent overwrite.

    A missing object and a denied HeadObject are both reported as "not there" by
    the API, so this cannot distinguish them. That is acceptable for its one
    purpose: if the head is denied, the copy that follows is denied too, and the
    caller sees that error instead of a wrong answer from here.
    """
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except Exception:
        return False


def _list_notifications(event, user_groups):
    """Recent file events, newest first, scoped to what the caller may see.

    Returns `configured: False` when no notification table is wired, so the UI
    can say the feature is not deployed rather than showing an empty inbox that
    looks like "nothing has happened".
    """
    if not NOTIFICATION_TABLE:
        return {
            "notifications": [],
            "configured": False,
            "error": None,
        }

    limit = min(int(event.get("maxResults") or 50), 200)
    watched = [p for p in (event.get("watchedPrefixes") or "").split(",") if p]
    scope = _allowed_prefixes(user_groups if isinstance(user_groups, list) else [])

    try:
        ddb = boto3.resource("dynamodb")
        table = ddb.Table(NOTIFICATION_TABLE)
        # A scan rather than a query: the table is keyed by the notification id,
        # so there is no partition to query by time. It is bounded by the page
        # limit below, and the table is short-lived by design (see the TTL note
        # in backend.ts). A time-ordered access pattern would need a GSI.
        records = table.scan(Limit=1000).get("Items", [])
    except Exception as e:
        return {"notifications": [], "configured": True, "error": str(e)}

    def visible(item) -> bool:
        key = item.get("fileKey", "")
        # The tenancy boundary comes first: a caller must not learn that a path
        # exists outside their scope by watching a prefix that covers it.
        if scope and not any(key.startswith(p) for p in scope):
            return False
        if watched and not any(key.startswith(p) for p in watched):
            return False
        return True

    visible_records = [r for r in records if visible(r)]
    visible_records.sort(key=lambda r: str(r.get("timestamp", "")), reverse=True)

    notifications = [
        {
            "id": str(r.get("id", "")),
            "source": r.get("source", ""),
            "eventType": r.get("eventType", ""),
            "fileKey": r.get("fileKey", ""),
            "fileName": r.get("fileName", ""),
            "fileSize": int(r.get("fileSize", 0) or 0),
            "clientIp": r.get("clientIp", ""),
            "userName": r.get("userName", ""),
            "timestamp": r.get("timestamp", ""),
        }
        for r in visible_records[:limit]
    ]
    return {
        "notifications": notifications,
        "configured": True,
        "count": len(notifications),
        "error": None,
    }


def handler(event, context):
    """List files in S3 AP with pagination and directory navigation.

    Supports group-based AP routing: if the user belongs to a Cognito group
    that has a mapped S3 AP, that AP is used instead of the default.
    This provides per-team file isolation (My Files view).

    Also supports listFilesFromAp action: directly specify an AP alias
    (used by SnapshotCompare to list files from a FlexClone volume).
    """
    action = event.get("action", "listFiles")
    prefix = event.get("prefix", "")
    max_keys = event.get("maxKeys", 100)
    continuation_token = event.get("continuationToken")
    user_groups = event.get("groups", [])

    # E-1/E-2: Folder watch inbox. Reads the FileNotification records the
    # notification bridge writes from FPolicy and Transfer Family events.
    #
    # Read here rather than through the generated model client because the model
    # is `allow.authenticated()`: the bridge writes rows with no owner, so
    # per-owner authorization cannot express who may read one. Filtering in a
    # Lambda lets the same GROUP_PATH_PREFIXES boundary the rest of the portal
    # uses apply to the notifications too.
    #
    # Placed ahead of the Access Point resolution: the inbox reads DynamoDB and
    # needs no alias, so the "no alias configured" early return below would
    # otherwise swallow it and answer with an empty file listing.
    if action == "listNotifications":
        return _list_notifications(event, user_groups)

    # Determine which AP to use
    if action == "listFilesFromAp" and event.get("apAlias"):
        # Direct AP alias override (for FlexClone comparison)
        ap_alias = event["apAlias"]
    else:
        # Default: group-based routing
        ap_alias = resolve_ap_alias(user_groups)

    if not ap_alias:
        return {"files": [], "isTruncated": False, "nextContinuationToken": None, "resolvedAp": "", "scope": "none"}

    # The caller's boundary, resolved once and applied to every key below. Reading it
    # per action is how the notification inbox came to be the only place it applied.
    allowed = _allowed_prefixes(user_groups if isinstance(user_groups, list) else [])

    # UX-3: Trash file (Copy to .trash/, then delete original)
    if action == "trashFile":
        key = event.get("key", "")
        refused = _reject_key(key, allowed, field="key")
        if refused:
            return {"success": False, "trashKey": "", **refused}
        if key.endswith("/"):
            return {
                "success": False,
                "trashKey": "",
                "error": "key names a folder. Trashing a folder would copy the marker and leave its contents behind",
            }
        trash_key = _scoped_trash_key(key)
        try:
            s3.copy_object(Bucket=ap_alias, CopySource=f"{ap_alias}/{key}", Key=trash_key)
            s3.delete_object(Bucket=ap_alias, Key=key)
            return {"success": True, "trashKey": trash_key, "error": None}
        except Exception as e:
            return {"success": False, "trashKey": "", "error": str(e)}

    # UX-3: Restore from trash (Copy from .trash/ back, then delete trash copy)
    if action == "restoreFromTrash":
        trash_key = event.get("trashKey", "")
        if not trash_key.startswith(TRASH_PREFIX):
            return {"success": False, "restoredKey": "", "error": f"trashKey must start with {TRASH_PREFIX}"}
        original_key = trash_key[len(TRASH_PREFIX) :]
        # The original key is what is checked, not the trash key: the boundary is
        # about where the object lands. `.trash/` prefixes everything, so comparing
        # the trash key against a tenant prefix would never match.
        refused = _reject_key(original_key, allowed, field="trashKey")
        if refused:
            return {"success": False, "restoredKey": "", **refused}
        if _object_exists(ap_alias, original_key):
            return {
                "success": False,
                "restoredKey": "",
                "error": f"{original_key} already exists. Rename or move it before restoring",
            }
        try:
            s3.copy_object(Bucket=ap_alias, CopySource=f"{ap_alias}/{trash_key}", Key=original_key)
            s3.delete_object(Bucket=ap_alias, Key=trash_key)
            return {"success": True, "restoredKey": original_key, "error": None}
        except Exception as e:
            return {"success": False, "restoredKey": "", "error": str(e)}

    # Create a folder. S3 has no directories: a folder is a zero-byte object whose
    # key ends in "/", which is what makes it visible as a CommonPrefix before
    # anything has been put in it.
    if action == "createFolder":
        key = event.get("key", "")
        if key and not key.endswith("/"):
            key = f"{key}/"
        refused = _reject_key(key, allowed, field="key")
        if refused:
            return {"success": False, "key": "", **refused}
        if _object_exists(ap_alias, key):
            return {"success": False, "key": "", "error": f"{key} already exists"}
        try:
            s3.put_object(Bucket=ap_alias, Key=key, Body=b"")
            return {"success": True, "key": key, "error": None}
        except Exception as e:
            return {"success": False, "key": "", "error": str(e)}

    # Copy and move share their checks and differ by one delete, so they are one
    # branch. A move is a copy the source does not survive.
    if action in ("copyFile", "moveFile"):
        src_key = event.get("sourceKey", "")
        dst_key = event.get("destinationKey", "")
        for candidate, field in ((src_key, "sourceKey"), (dst_key, "destinationKey")):
            refused = _reject_key(candidate, allowed, field=field)
            if refused:
                return {"success": False, "newKey": "", **refused}
        if src_key.endswith("/") or dst_key.endswith("/"):
            return {
                "success": False,
                "newKey": "",
                "error": (
                    "folders are not supported. Copying a prefix means copying every object "
                    "under it, which can fail halfway and leave two partial folders"
                ),
            }
        if src_key == dst_key:
            return {"success": False, "newKey": "", "error": "sourceKey and destinationKey are the same"}
        # Overwriting is possible but never implicit: the destination holding
        # something is the one case where a copy destroys data.
        if not event.get("overwrite") and _object_exists(ap_alias, dst_key):
            return {
                "success": False,
                "newKey": "",
                "error": f"{dst_key} already exists. Pass overwrite to replace it",
            }
        try:
            s3.copy_object(Bucket=ap_alias, CopySource=f"{ap_alias}/{src_key}", Key=dst_key)
            if action == "moveFile":
                # Deleted only after the copy returns. The other order loses the
                # object when the copy fails.
                s3.delete_object(Bucket=ap_alias, Key=src_key)
            return {"success": True, "newKey": dst_key, "error": None}
        except Exception as e:
            return {"success": False, "newKey": "", "error": str(e)}

    # Permanent deletion. Confined to the trash and gated on an explicit
    # acknowledgement, because nothing here can undo it: the object is not
    # versioned, so there is no previous version to roll back to.
    if action == "deleteFileForever":
        key = event.get("key", "")
        if not key.startswith(TRASH_PREFIX):
            return {
                "success": False,
                "error": (
                    f"only objects under {TRASH_PREFIX} can be deleted permanently. Move the file to the trash first"
                ),
            }
        refused = _reject_key(key[len(TRASH_PREFIX) :], allowed, field="key")
        if refused:
            return {"success": False, **refused}
        if event.get("acknowledgeIrreversible") is not True:
            return {
                "success": False,
                "error": (
                    f"deleting {key} cannot be undone — the object is not versioned, so no "
                    "earlier copy remains. Set acknowledgeIrreversible to proceed"
                ),
            }
        try:
            s3.delete_object(Bucket=ap_alias, Key=key)
            return {"success": True, "deletedKey": key, "error": None}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # UX-7: Create upload link (PutObject Presigned URL for external file request)
    if action == "createUploadLink":
        dest_prefix = event.get("destinationPrefix", "uploads/")
        file_name = event.get("fileName", "")
        expires_in = min(event.get("expiresIn", 3600), 86400)  # Max 24h
        import uuid as _uuid

        dest_key = f"{dest_prefix.rstrip('/')}/{file_name or _uuid.uuid4().hex[:8]}"
        # Checked like any other write. The URL this returns is a credential for
        # exactly one key, so an unchecked destination hands out write access to
        # somewhere the caller cannot otherwise reach.
        refused = _reject_key(dest_key, allowed, field="destinationPrefix")
        if refused:
            return {"uploadUrl": "", "destinationKey": "", "expiresIn": 0, **refused}
        try:
            url = s3.generate_presigned_url(
                "put_object",
                Params={"Bucket": ap_alias, "Key": dest_key},
                ExpiresIn=expires_in,
            )
            return {"uploadUrl": url, "destinationKey": dest_key, "expiresIn": expires_in, "error": None}
        except Exception as e:
            return {"uploadUrl": "", "destinationKey": "", "expiresIn": 0, "error": str(e)}

    # UX-9: Rename file (CopyObject + DeleteObject)
    if action == "renameFile":
        src_key = event.get("sourceKey", "")
        dst_key = event.get("destinationKey", "")
        for candidate, field in ((src_key, "sourceKey"), (dst_key, "destinationKey")):
            refused = _reject_key(candidate, allowed, field=field)
            if refused:
                return {"success": False, "newKey": "", **refused}
        if not event.get("overwrite") and _object_exists(ap_alias, dst_key):
            return {
                "success": False,
                "newKey": "",
                "error": f"{dst_key} already exists. Pass overwrite to replace it",
            }
        try:
            s3.copy_object(Bucket=ap_alias, CopySource=f"{ap_alias}/{src_key}", Key=dst_key)
            s3.delete_object(Bucket=ap_alias, Key=src_key)
            return {"success": True, "newKey": dst_key, "error": None}
        except Exception as e:
            return {"success": False, "newKey": "", "error": str(e)}

    # Listing is bounded by the same prefixes as every write. Without this, a caller
    # restricted to `team-a/` could read `team-b/` by asking for it: the endpoint
    # requires a session but the prefix arrived unchecked. Browsing the root is still
    # allowed and shows only what the caller may see, which is what makes the
    # restriction navigable rather than a dead end.
    if allowed and prefix:
        if not any(prefix.startswith(p) or p.startswith(prefix) for p in allowed):
            return {
                "files": [],
                "isTruncated": False,
                "nextContinuationToken": None,
                "resolvedAp": ap_alias,
                "scope": "denied",
            }

    params = {
        "Bucket": ap_alias,
        "Prefix": prefix,
        "Delimiter": "/",
        "MaxKeys": min(max_keys, 1000),
    }
    if continuation_token:
        params["ContinuationToken"] = continuation_token

    try:
        response = s3.list_objects_v2(**params)
        folders = [
            {"key": cp["Prefix"], "size": 0, "lastModified": None, "storageClass": "DIRECTORY"}
            for cp in response.get("CommonPrefixes", [])
        ]
        files = [
            {
                "key": obj["Key"],
                "size": obj["Size"],
                "lastModified": obj["LastModified"].isoformat(),
                "storageClass": obj.get("StorageClass", "STANDARD"),
            }
            for obj in response.get("Contents", [])
            if not obj["Key"].endswith("/")
        ]
        # Determine scope label for UI
        scope = "default"
        if GROUP_AP_MAPPING and user_groups:
            for g in user_groups:
                if g in GROUP_AP_MAPPING:
                    scope = g
                    break

        return {
            "files": folders + files,
            "isTruncated": response.get("IsTruncated", False),
            "nextContinuationToken": response.get("NextContinuationToken"),
            "resolvedAp": ap_alias,
            "scope": scope,
        }
    except Exception as e:
        # logger, not print: a print goes to the log stream without a level, so it
        # cannot be filtered out of an alarm or found by one.
        logger.exception("listFiles failed for prefix %s", prefix)
        return {
            "files": [],
            "isTruncated": False,
            "nextContinuationToken": None,
            "resolvedAp": ap_alias,
            "scope": "error",
            "error": str(e),
        }
