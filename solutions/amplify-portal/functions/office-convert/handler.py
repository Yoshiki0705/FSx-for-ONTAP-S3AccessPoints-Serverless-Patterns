"""UX-5: Office file → PDF conversion Lambda (Container Image).

Converts docx/xlsx/pptx files from FSx for ONTAP S3 AP to PDF
using LibreOffice headless. The converted PDF is cached in the
same volume under .cache/previews/ for subsequent requests.

Flow:
  1. GetObject from S3 AP (source file)
  2. Write to /tmp/<uuid>.<ext>
  3. LibreOffice headless convert to PDF
  4. Upload PDF to S3 AP (.cache/previews/<hash>.pdf)
  5. Return Presigned URL for the cached PDF

Environment:
    S3_AP_ALIAS: S3 Access Point alias
    CACHE_PREFIX: Prefix for cached PDFs (default: .cache/previews/)
    PRESIGN_EXPIRY: Presigned URL expiry in seconds (default: 300)
"""
from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import tempfile
import uuid
from pathlib import Path

import boto3
from botocore.config import Config

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REGION = os.environ.get("AWS_REGION", "ap-northeast-1")
AP_ALIAS = os.environ.get("S3_AP_ALIAS", "")
CACHE_PREFIX = os.environ.get("CACHE_PREFIX", ".cache/previews/")
PRESIGN_EXPIRY = int(os.environ.get("PRESIGN_EXPIRY", "300"))

s3 = boto3.client(
    "s3", region_name=REGION,
    endpoint_url=f"https://s3.{REGION}.amazonaws.com",
    config=Config(signature_version="s3v4"),
)

SUPPORTED_EXTENSIONS = {".docx", ".xlsx", ".pptx", ".doc", ".xls", ".ppt", ".odt", ".ods", ".odp"}


def handler(event, context):
    """Convert Office file to PDF and return Presigned URL for preview."""
    key = event.get("key", "")
    if not AP_ALIAS or not key:
        return {"url": None, "error": "Missing S3_AP_ALIAS or key"}

    ext = Path(key).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return {"url": None, "error": f"Unsupported file type: {ext}"}

    # Check cache first
    file_hash = hashlib.md5(key.encode()).hexdigest()
    cache_key = f"{CACHE_PREFIX}{file_hash}.pdf"

    try:
        s3.head_object(Bucket=AP_ALIAS, Key=cache_key)
        # Cache hit — return presigned URL
        url = s3.generate_presigned_url(
            "get_object", Params={"Bucket": AP_ALIAS, "Key": cache_key},
            ExpiresIn=PRESIGN_EXPIRY,
        )
        logger.info(f"Cache hit: {key} → {cache_key}")
        return {"url": url, "cacheHit": True, "error": None}
    except s3.exceptions.ClientError:
        pass  # Cache miss — convert

    # Download source file
    work_dir = tempfile.mkdtemp()
    source_filename = f"{uuid.uuid4().hex}{ext}"
    source_path = Path(work_dir) / source_filename

    try:
        obj = s3.get_object(Bucket=AP_ALIAS, Key=key)
        source_path.write_bytes(obj["Body"].read())
        logger.info(f"Downloaded: {key} ({source_path.stat().st_size} bytes)")
    except Exception as e:
        return {"url": None, "error": f"Failed to download: {e}"}

    # Convert with LibreOffice
    try:
        result = subprocess.run(
            [
                "libreoffice", "--headless", "--convert-to", "pdf",
                "--outdir", work_dir, str(source_path),
            ],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            logger.error(f"LibreOffice error: {result.stderr}")
            return {"url": None, "error": f"Conversion failed: {result.stderr[:200]}"}
    except subprocess.TimeoutExpired:
        return {"url": None, "error": "Conversion timed out (60s)"}

    # Find output PDF
    pdf_path = source_path.with_suffix(".pdf")
    if not pdf_path.exists():
        return {"url": None, "error": "PDF output not found after conversion"}

    # Upload to cache
    try:
        s3.put_object(Bucket=AP_ALIAS, Key=cache_key, Body=pdf_path.read_bytes(),
                      ContentType="application/pdf")
        logger.info(f"Cached: {cache_key} ({pdf_path.stat().st_size} bytes)")
    except Exception as e:
        logger.warning(f"Cache upload failed (non-fatal): {e}")

    # Generate presigned URL
    url = s3.generate_presigned_url(
        "get_object", Params={"Bucket": AP_ALIAS, "Key": cache_key},
        ExpiresIn=PRESIGN_EXPIRY,
    )

    return {"url": url, "cacheHit": False, "error": None}
