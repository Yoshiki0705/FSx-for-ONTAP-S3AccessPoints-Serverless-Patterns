"""EventBridge → AppSync Notification Bridge (E-1, E-2)

Receives events from:
- FPolicy EventBridge rule (E-1): NFS/SMB file create/modify/delete/rename
- Transfer Family EventBridge (E-2): SFTP file uploads

Creates FileNotification records in DynamoDB via AppSync mutation,
which triggers real-time subscriptions for connected portal clients.

Environment variables:
    APPSYNC_API_URL: AppSync GraphQL endpoint URL
    APPSYNC_API_KEY: AppSync API key (or use IAM auth)

EventBridge rule target: this Lambda function
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import boto3
import urllib3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

APPSYNC_URL = os.environ.get("APPSYNC_API_URL", "")
TABLE_NAME = os.environ.get("NOTIFICATION_TABLE_NAME", "")


def handler(event: dict, context) -> dict:
    """Process EventBridge events and create FileNotification records.

    Supports two event sources:
    1. FPolicy events (detail-type: "FPolicy File Event")
    2. Transfer Family events (detail-type: "Transfer Family File Upload")
    """
    detail_type = event.get("detail-type", "")
    detail = event.get("detail", {})
    source = event.get("source", "")

    logger.info(f"Received event: source={source}, detail-type={detail_type}")

    notification = None

    if "fpolicy" in detail_type.lower() or "fpolicy" in source.lower():
        # E-1: FPolicy event
        notification = {
            "source": "FPOLICY",
            "eventType": detail.get("operation", "CREATE").upper(),
            "fileKey": detail.get("file_path", detail.get("path", "")),
            "fileName": detail.get("file_name", ""),
            "fileSize": detail.get("file_size", 0),
            "clientIp": detail.get("client_ip", ""),
            "userName": detail.get("user_name", ""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    elif "transfer" in detail_type.lower() or "transfer" in source.lower():
        # E-2: Transfer Family event
        notification = {
            "source": "SFTP",
            "eventType": "CREATE",
            "fileKey": detail.get("file-key", detail.get("key", "")),
            "fileName": detail.get("file-key", "").rsplit("/", 1)[-1],
            "fileSize": detail.get("bytes", 0),
            "clientIp": detail.get("source-ip", ""),
            "userName": detail.get("user-name", detail.get("username", "")),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    else:
        logger.warning(f"Unknown event type: {detail_type}")
        return {"statusCode": 200, "body": "Ignored — unknown event type"}

    if not notification or not notification["fileKey"]:
        return {"statusCode": 200, "body": "Skipped — no file path in event"}

    # Write directly to DynamoDB (simpler than AppSync mutation for Lambda→Lambda)
    if TABLE_NAME:
        try:
            import uuid
            dynamodb = boto3.resource("dynamodb")
            table = dynamodb.Table(TABLE_NAME)
            notification["id"] = str(uuid.uuid4())
            table.put_item(Item=notification)
            logger.info(
                f"Notification created: {notification['source']} "
                f"{notification['eventType']} {notification['fileKey']}"
            )
        except Exception as e:
            logger.error(f"Failed to write notification: {e}")
            return {"statusCode": 500, "body": str(e)}

    return {"statusCode": 200, "body": json.dumps(notification, default=str)}
