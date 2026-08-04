import os
import json
import boto3

s3 = boto3.client("s3")

# Group → AP mapping (JSON from environment variable)
GROUP_AP_MAPPING = json.loads(os.environ.get("GROUP_AP_MAPPING", "{}"))
DEFAULT_AP_ALIAS = os.environ.get("S3_AP_ALIAS", "")


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

    # Determine which AP to use
    if action == "listFilesFromAp" and event.get("apAlias"):
        # Direct AP alias override (for FlexClone comparison)
        ap_alias = event["apAlias"]
    else:
        # Default: group-based routing
        ap_alias = resolve_ap_alias(user_groups)

    if not ap_alias:
        return {"files": [], "isTruncated": False, "nextContinuationToken": None, "resolvedAp": "", "scope": "none"}

    # UX-3: Trash file (Copy to .trash/, then delete original)
    if action == "trashFile":
        key = event.get("key", "")
        if not key:
            return {"success": False, "trashKey": "", "error": "No key specified"}
        trash_key = f".trash/{key}"
        try:
            s3.copy_object(Bucket=ap_alias, CopySource=f"{ap_alias}/{key}", Key=trash_key)
            s3.delete_object(Bucket=ap_alias, Key=key)
            return {"success": True, "trashKey": trash_key, "error": None}
        except Exception as e:
            return {"success": False, "trashKey": "", "error": str(e)}

    # UX-3: Restore from trash (Copy from .trash/ back, then delete trash copy)
    if action == "restoreFromTrash":
        trash_key = event.get("trashKey", "")
        if not trash_key or not trash_key.startswith(".trash/"):
            return {"success": False, "restoredKey": "", "error": "Invalid trash key"}
        original_key = trash_key.replace(".trash/", "", 1)
        try:
            s3.copy_object(Bucket=ap_alias, CopySource=f"{ap_alias}/{trash_key}", Key=original_key)
            s3.delete_object(Bucket=ap_alias, Key=trash_key)
            return {"success": True, "restoredKey": original_key, "error": None}
        except Exception as e:
            return {"success": False, "restoredKey": "", "error": str(e)}

    # UX-7: Create upload link (PutObject Presigned URL for external file request)
    if action == "createUploadLink":
        dest_prefix = event.get("destinationPrefix", "uploads/")
        file_name = event.get("fileName", "")
        expires_in = min(event.get("expiresIn", 3600), 86400)  # Max 24h
        import uuid as _uuid

        dest_key = f"{dest_prefix.rstrip('/')}/{file_name or _uuid.uuid4().hex[:8]}"
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
        if not src_key or not dst_key:
            return {"success": False, "newKey": "", "error": "sourceKey and destinationKey required"}
        try:
            s3.copy_object(Bucket=ap_alias, CopySource=f"{ap_alias}/{src_key}", Key=dst_key)
            s3.delete_object(Bucket=ap_alias, Key=src_key)
            return {"success": True, "newKey": dst_key, "error": None}
        except Exception as e:
            return {"success": False, "newKey": "", "error": str(e)}

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
        print(f"Error listing files: {e}")
        return {
            "files": [],
            "isTruncated": False,
            "nextContinuationToken": None,
            "resolvedAp": ap_alias,
            "scope": "error",
        }
