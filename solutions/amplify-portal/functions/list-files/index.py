from __future__ import annotations

import json
import logging
import os

import boto3
from botocore.config import Config

from shared.portal_path_scope import MAX_KEY_BYTES  # noqa: F401  (kept for callers/tests)
from shared.portal_path_scope import allowed_prefixes as _shared_allowed_prefixes
from shared.portal_path_scope import reject_key as _reject_key

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# SigV4 is named rather than left to the default, because the default is not v4 for
# presigning: `generate_presigned_url` produced a v2 URL (`AWSAccessKeyId`, `Signature`,
# `Expires`) against the global endpoint, and S3 answered the upload with
# 301 PermanentRedirect naming the regional one. The upload link the portal handed out
# had never worked. Measured 2026-08-15.
#
# FSx for ONTAP's S3 support requires v4 as well; v2 arrives only in ONTAP 9.16.1, so a
# v2 URL is not something to rely on even where it is accepted.
#
# `addressing_style` is named for the same reason. Under the default (`auto`) botocore
# presigns against the global `s3.amazonaws.com` even with a region set, and S3 answers
# 301 with the regional host -- which the signature cannot follow, because it covers
# `host`. Asking for virtual addressing puts the region in the host that gets signed:
#   auto    -> <alias>.s3.amazonaws.com               (301, unusable)
#   virtual -> <alias>.s3.ap-northeast-1.amazonaws.com
s3 = boto3.client("s3", config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}))

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

    Binds this function's environment to the shared boundary. The third consumer
    arrived -- the thumbnail path -- which is the condition this docstring used to
    name as the point to extract, so the rule now lives in
    `shared.portal_path_scope` and there is one definition of it.
    """
    return _shared_allowed_prefixes(user_groups, GROUP_PATH_PREFIXES)


# The trash lives under this prefix in the same bucket. Permanent deletion is
# confined to it: to destroy an object you first move it here, which turns one
# careless click into two deliberate ones.
TRASH_PREFIX = ".trash/"


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


# The largest object a single CopyObject can handle. Every rename, move, copy, trash and
# restore in this handler is a CopyObject, so this is the ceiling on all of them.
#
# Past it the documented route is multipart copy (UploadPartCopy), and on FSx for ONTAP
# S3 Access Points that call is listed as supported and answers `NoSuchKey` when measured.
# So there is no route past this limit from here, and the honest thing is to say so before
# copying rather than to surface whichever error S3 returns partway through.
COPY_LIMIT_BYTES = 5 * 1024 * 1024 * 1024


def _too_large_to_copy(bucket: str, key: str) -> str:
    """The reason `key` cannot be copied, or "" when it can.

    Args:
        bucket: The Access Point alias.
        key: The object about to be copied.

    Returns:
        A message naming the size and the limit, or "" when the object is within it
        or its size cannot be read. An unreadable head is not treated as a refusal:
        the copy that follows reports the real reason.
    """
    try:
        size = int(s3.head_object(Bucket=bucket, Key=key)["ContentLength"])
    except Exception:
        return ""
    if size <= COPY_LIMIT_BYTES:
        return ""
    return (
        f"{key} is {size / 1024**3:.1f} GiB. A single copy is limited to 5 GiB, and the "
        "multipart copy that would lift the limit is not usable on this Access Point, so "
        "this operation cannot be completed from the portal. Move the file over NFS or SMB "
        "instead."
    )


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
        oversize = _too_large_to_copy(ap_alias, key)
        if oversize:
            return {"success": False, "trashKey": "", "error": oversize}
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
        oversize = _too_large_to_copy(ap_alias, trash_key)
        if oversize:
            return {"success": False, "restoredKey": "", "error": oversize}
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
        oversize = _too_large_to_copy(ap_alias, src_key)
        if oversize:
            return {"success": False, "newKey": "", "error": oversize}
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
        oversize = _too_large_to_copy(ap_alias, src_key)
        if oversize:
            return {"success": False, "newKey": "", "error": oversize}
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
