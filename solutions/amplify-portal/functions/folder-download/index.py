"""Folder Download Lambda — ZIP generation for folder sharing.

Creates a ZIP archive of all files in a given S3 AP prefix, uploads it to
a temporary S3 bucket, and returns a Presigned URL for download.

Architecture:
  AppSync Mutation → This Lambda → S3 AP (ListObjects + GetObject) → ZIP → S3 temp → Presigned URL

Limitations:
  - Max folder size: ~500MB (Lambda /tmp = 10GB, timeout 15min)
  - ZIP file is stored in a temp bucket with 1-day lifecycle expiration
  - Presigned URL expires in 1 hour (configurable)
"""
from __future__ import annotations

import io
import os
import zipfile
import logging
from datetime import datetime, timezone

import boto3
from botocore.config import Config

logger = logging.getLogger()
logger.setLevel(logging.INFO)

region = os.environ.get("AWS_REGION", "ap-northeast-1")
S3_AP_ALIAS = os.environ.get("S3_AP_ALIAS", "")
ZIP_BUCKET = os.environ.get("ZIP_TEMP_BUCKET", "")
MAX_FILES = int(os.environ.get("MAX_ZIP_FILES", "500"))
MAX_TOTAL_BYTES = int(os.environ.get("MAX_ZIP_BYTES", str(500 * 1024 * 1024)))  # 500MB
PRESIGN_EXPIRES = int(os.environ.get("PRESIGN_EXPIRES_SECONDS", "3600"))

s3 = boto3.client(
    "s3",
    region_name=region,
    endpoint_url=f"https://s3.{region}.amazonaws.com",
    config=Config(signature_version="s3v4"),
)


def handler(event, context):
    """Generate a ZIP of all files under a given prefix.

    Expected event:
      {
        "prefix": "claims/photos/2026/05/",
        "userId": "admin@demo.local"
      }

    Returns:
      {
        "success": true,
        "downloadUrl": "https://...",
        "fileName": "claims_photos_2026_05.zip",
        "fileCount": 12,
        "totalBytes": 1234567,
        "error": null
      }
    """
    prefix = event.get("prefix", "")
    user_id = event.get("userId", "unknown")

    if not prefix:
        return {"success": False, "error": "prefix is required", "downloadUrl": None}

    if not S3_AP_ALIAS:
        # DemoMode: return a mock response
        return {
            "success": True,
            "downloadUrl": f"https://s3.{region}.amazonaws.com/{ZIP_BUCKET or 'demo-bucket'}/demo-folder.zip",
            "fileName": _prefix_to_filename(prefix),
            "fileCount": 5,
            "totalBytes": 102400,
            "error": None,
            "demoMode": True,
        }

    if not ZIP_BUCKET:
        return {"success": False, "error": "ZIP_TEMP_BUCKET not configured", "downloadUrl": None}

    try:
        # Step 1: List all objects under the prefix
        objects = _list_all_objects(prefix)

        if not objects:
            return {"success": False, "error": f"No files found under prefix: {prefix}", "downloadUrl": None}

        if len(objects) > MAX_FILES:
            return {
                "success": False,
                "error": f"Too many files ({len(objects)}). Maximum is {MAX_FILES}.",
                "downloadUrl": None,
            }

        total_size = sum(obj["Size"] for obj in objects)
        if total_size > MAX_TOTAL_BYTES:
            return {
                "success": False,
                "error": f"Total size ({total_size // (1024*1024)} MB) exceeds maximum ({MAX_TOTAL_BYTES // (1024*1024)} MB).",
                "downloadUrl": None,
            }

        # Step 2: Create ZIP in memory (stream to /tmp for large files)
        zip_key = _generate_zip_key(prefix, user_id)
        zip_filename = _prefix_to_filename(prefix)

        logger.info(f"Creating ZIP: {zip_filename} with {len(objects)} files ({total_size} bytes) for {user_id}")

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for obj in objects:
                key = obj["Key"]
                # Strip the prefix for relative paths in ZIP
                relative_path = key[len(prefix):] if key.startswith(prefix) else key
                if not relative_path:
                    continue

                # Get object content from S3 AP
                response = s3.get_object(Bucket=S3_AP_ALIAS, Key=key)
                content = response["Body"].read()
                zf.writestr(relative_path, content)

        # Step 3: Upload ZIP to temp bucket
        zip_buffer.seek(0)
        s3.put_object(
            Bucket=ZIP_BUCKET,
            Key=zip_key,
            Body=zip_buffer.getvalue(),
            ContentType="application/zip",
            ContentDisposition=f'attachment; filename="{zip_filename}"',
            Metadata={
                "generated-by": user_id,
                "source-prefix": prefix,
                "file-count": str(len(objects)),
            },
        )

        # Step 4: Generate Presigned URL
        download_url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": ZIP_BUCKET, "Key": zip_key},
            ExpiresIn=PRESIGN_EXPIRES,
        )

        logger.info(f"ZIP generated: {zip_key}, {len(objects)} files, {total_size} bytes")

        return {
            "success": True,
            "downloadUrl": download_url,
            "fileName": zip_filename,
            "fileCount": len(objects),
            "totalBytes": total_size,
            "error": None,
        }

    except Exception as e:
        logger.error(f"ZIP generation failed: {e}")
        return {"success": False, "error": str(e), "downloadUrl": None}


def _list_all_objects(prefix: str) -> list:
    """List all objects under a prefix using pagination."""
    objects = []
    continuation_token = None

    while True:
        params = {
            "Bucket": S3_AP_ALIAS,
            "Prefix": prefix,
            "MaxKeys": 1000,
        }
        if continuation_token:
            params["ContinuationToken"] = continuation_token

        response = s3.list_objects_v2(**params)
        contents = response.get("Contents", [])
        objects.extend([{"Key": obj["Key"], "Size": obj["Size"]} for obj in contents])

        if response.get("IsTruncated"):
            continuation_token = response["NextContinuationToken"]
        else:
            break

        # Safety limit
        if len(objects) > MAX_FILES:
            break

    return objects


def _prefix_to_filename(prefix: str) -> str:
    """Convert a prefix like 'claims/photos/2026/05/' to 'claims_photos_2026_05.zip'."""
    clean = prefix.strip("/").replace("/", "_")
    if not clean:
        clean = "folder"
    return f"{clean}.zip"


def _generate_zip_key(prefix: str, user_id: str) -> str:
    """Generate a unique S3 key for the ZIP file."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    clean_prefix = prefix.strip("/").replace("/", "_")[:50]
    return f"zip-downloads/{clean_prefix}_{timestamp}.zip"
