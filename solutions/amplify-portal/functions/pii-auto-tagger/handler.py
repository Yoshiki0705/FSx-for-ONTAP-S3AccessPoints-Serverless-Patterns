"""DLP Auto-Detection: Comprehend PII → automatic classification tagging.

Triggered by:
  - FPolicy EventBridge (new file created on NFS/SMB)
  - S3 AP PutObject EventBridge (new file via portal upload)
  - Manual invocation (batch scan)

Flow:
  1. GetObject from S3 AP (text content)
  2. Comprehend DetectPiiEntities
  3. If PII found → classify as RESTRICTED + tag in DynamoDB
  4. Emit metric for CloudWatch dashboard

Supported file types: .txt, .csv, .json, .md, .log, .xml, .html
(Binary files like .pdf require Textract pre-processing — not included here)

Environment:
    S3_AP_ALIAS: S3 Access Point alias
    CLASSIFICATION_TABLE_NAME: DynamoDB table for file classifications
    AI_METADATA_TABLE_NAME: DynamoDB table for AI results
    COMPREHEND_LANGUAGE: Language code (default: en)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.config import Config

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REGION = os.environ.get("AWS_REGION", "ap-northeast-1")
AP_ALIAS = os.environ.get("S3_AP_ALIAS", "")
CLASSIFICATION_TABLE = os.environ.get("CLASSIFICATION_TABLE_NAME", "")
METADATA_TABLE = os.environ.get("AI_METADATA_TABLE_NAME", "")
LANGUAGE = os.environ.get("COMPREHEND_LANGUAGE", "en")
MAX_FILE_SIZE = 100 * 1024  # 100KB limit for Comprehend

TEXT_EXTENSIONS = {".txt", ".csv", ".json", ".md", ".log", ".xml", ".html", ".yml", ".yaml"}

s3 = boto3.client("s3", region_name=REGION,
                  endpoint_url=f"https://s3.{REGION}.amazonaws.com",
                  config=Config(signature_version="s3v4"))
comprehend = boto3.client("comprehend", region_name=REGION)


def handler(event, context):
    """Scan file for PII and auto-classify if found.

    Returns:
        {
            "fileKey": "path/to/file.txt",
            "piiDetected": true,
            "piiTypes": ["EMAIL_ADDRESS", "PHONE_NUMBER"],
            "piiCount": 3,
            "classification": "RESTRICTED",
            "action": "tagged"
        }
    """
    # Support both direct invocation and EventBridge event
    if "detail" in event:
        # EventBridge format
        detail = event.get("detail", {})
        file_key = detail.get("file_path", detail.get("key", ""))
    else:
        # Direct invocation
        file_key = event.get("fileKey", event.get("key", ""))

    if not file_key or not AP_ALIAS:
        return {"fileKey": file_key, "error": "Missing fileKey or S3_AP_ALIAS"}

    # Check file type
    ext = Path(file_key).suffix.lower()
    if ext not in TEXT_EXTENSIONS:
        return {"fileKey": file_key, "piiDetected": False, "action": "skipped",
                "reason": f"Unsupported extension: {ext}"}

    # Download file content
    try:
        obj = s3.get_object(Bucket=AP_ALIAS, Key=file_key)
        content_length = obj.get("ContentLength", 0)
        if content_length > MAX_FILE_SIZE:
            content = obj["Body"].read(MAX_FILE_SIZE).decode("utf-8", errors="replace")
        else:
            content = obj["Body"].read().decode("utf-8", errors="replace")
    except Exception as e:
        return {"fileKey": file_key, "error": f"Failed to read file: {e}"}

    if not content.strip():
        return {"fileKey": file_key, "piiDetected": False, "action": "empty_file"}

    # Detect PII
    try:
        response = comprehend.detect_pii_entities(
            Text=content[:5000],  # Comprehend limit per call
            LanguageCode=LANGUAGE,
        )
        entities = response.get("Entities", [])
    except Exception as e:
        return {"fileKey": file_key, "error": f"Comprehend error: {e}"}

    pii_types = list(set(e["Type"] for e in entities))
    pii_count = len(entities)

    result = {
        "fileKey": file_key,
        "piiDetected": pii_count > 0,
        "piiTypes": pii_types,
        "piiCount": pii_count,
        "classification": "RESTRICTED" if pii_count > 0 else "INTERNAL",
        "action": "tagged" if pii_count > 0 else "no_pii",
    }

    # Auto-tag in DynamoDB if PII detected
    if pii_count > 0:
        now = datetime.now(timezone.utc).isoformat()
        dynamodb = boto3.resource("dynamodb")

        # Update classification table
        if CLASSIFICATION_TABLE:
            try:
                table = dynamodb.Table(CLASSIFICATION_TABLE)
                table.put_item(Item={
                    "file_key": file_key,
                    "classification": "RESTRICTED",
                    "classified_by": "pii-auto-tagger",
                    "classified_at": now,
                    "pii_types": pii_types,
                    "pii_count": pii_count,
                })
                logger.info(f"Classified {file_key} as RESTRICTED ({pii_count} PII entities)")
            except Exception as e:
                logger.warning(f"Classification table update failed: {e}")

        # Update AI metadata table
        if METADATA_TABLE:
            try:
                table = dynamodb.Table(METADATA_TABLE)
                table.put_item(Item={
                    "file_key": file_key,
                    "classification": "RESTRICTED",
                    "pii_types": pii_types,
                    "pii_count": pii_count,
                    "processed_at": now,
                    "processing_pattern": "DLP_AUTO_SCAN",
                })
            except Exception as e:
                logger.warning(f"Metadata table update failed: {e}")

    logger.info(f"PII scan: {file_key} → {pii_count} entities, types={pii_types}")
    return result
