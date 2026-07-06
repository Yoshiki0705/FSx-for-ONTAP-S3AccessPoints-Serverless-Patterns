"""PoC Lambda handler: copy an IVS HLS recording package from S3 to FSx for ONTAP.

Status: PoC / sample only. NOT production-hardened.
    - No streaming of very large objects (loads object bodies into memory on the S3 AP path).
    - No idempotency/dedup (add shared/idempotency_checker.py before production).
    - No partial-failure reconciliation.
For large packages or many small segments, prefer AWS DataSync or an ECS/Batch worker that
mounts the FSx volume over NFS/SMB (see Placement B below).

Trigger input (from the Step Functions CopyPackageToFsx task):
    {
        "source_bucket": "<standard IVS recording bucket>",
        "recording_prefix": "ivs/v1/<account>/<channel>/.../<recording_id>",
        "recording_session_id": "<id>"
    }

Two placement strategies are shown and selected by the WRITE_METHOD env var:
    - "S3AP"  : write to FSx via an S3 Access Point alias (S3 API PutObject).
                Internet-origin AP -> run this Lambda OUTSIDE a VPC (or via NAT).
    - "MOUNT" : write to a locally mounted FSx NFS/SMB path. NOTE: Lambda cannot mount
                FSx for ONTAP NFS/SMB directly; use this branch from an ECS/Batch task
                (the code is shared for illustration).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# --- Configuration (environment variables) ---------------------------------
WRITE_METHOD = os.environ.get("WRITE_METHOD", "S3AP")  # "S3AP" | "MOUNT"
FSX_S3AP_ALIAS = os.environ.get("FSX_S3AP_ALIAS", "")  # required for S3AP
FSX_MOUNT_PATH = os.environ.get("FSX_MOUNT_PATH", "/mnt/fsxontap/vod")  # for MOUNT
MASTER_MANIFEST_NAME = os.environ.get("MASTER_MANIFEST_NAME", "master.m3u8")

s3 = boto3.client("s3")


def _list_keys(bucket: str, prefix: str) -> list[str]:
    """List all object keys under a prefix (handles pagination)."""
    keys: list[str] = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def _copy_via_s3ap(source_bucket: str, keys: list[str]) -> None:
    """Placement A: write objects to FSx through an S3 Access Point alias (PutObject).

    The AP alias is used in place of a bucket name for object operations. PutObject max is
    5 GB per object (use multipart for larger). HLS segments are typically small, but many
    segments mean many API calls — for large VODs prefer DataSync / mount-based copy.
    """
    if not FSX_S3AP_ALIAS:
        raise ValueError("FSX_S3AP_ALIAS is required when WRITE_METHOD=S3AP")
    for key in keys:
        obj = s3.get_object(Bucket=source_bucket, Key=key)
        body = obj["Body"].read()  # PoC: fine for small HLS segments; not for multi-GB files
        s3.put_object(Bucket=FSX_S3AP_ALIAS, Key=key, Body=body)
        logger.info("copied s3://%s/%s -> ap://%s/%s", source_bucket, key, FSX_S3AP_ALIAS, key)


def _copy_via_mount(source_bucket: str, keys: list[str]) -> None:
    """Placement B: write objects to a locally mounted FSx NFS/SMB path.

    Use from an ECS/Batch task with the FSx volume mounted at FSX_MOUNT_PATH.
    Lambda cannot mount FSx for ONTAP NFS/SMB directly; this branch is illustrative.
    """
    import pathlib

    for key in keys:
        obj = s3.get_object(Bucket=source_bucket, Key=key)
        dest = pathlib.Path(FSX_MOUNT_PATH) / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(obj["Body"].read())
        logger.info("copied s3://%s/%s -> %s", source_bucket, key, dest)


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    """Copy the HLS package and report whether a master manifest is present."""
    source_bucket = event["source_bucket"]
    recording_prefix = event["recording_prefix"].rstrip("/")

    keys = _list_keys(source_bucket, recording_prefix)
    if not keys:
        logger.warning("no objects under s3://%s/%s", source_bucket, recording_prefix)
        return {"copied": 0, "manifest_present": False, "master_manifest_key": ""}

    if WRITE_METHOD == "S3AP":
        _copy_via_s3ap(source_bucket, keys)
    elif WRITE_METHOD == "MOUNT":
        _copy_via_mount(source_bucket, keys)
    else:
        raise ValueError(f"unsupported WRITE_METHOD: {WRITE_METHOD}")

    master_keys = [k for k in keys if k.endswith(MASTER_MANIFEST_NAME)]
    master_manifest_key = master_keys[0] if master_keys else ""

    return {
        "copied": len(keys),
        "manifest_present": bool(master_manifest_key),
        "master_manifest_key": master_manifest_key,
        "recording_prefix": recording_prefix,
    }
