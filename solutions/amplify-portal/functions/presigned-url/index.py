import os
from datetime import datetime, timezone

import boto3
from botocore.config import Config

# Use SigV4 signing with explicit regional endpoint (required for FSx for ONTAP S3 AP)
region = os.environ.get("AWS_REGION", "ap-northeast-1")
s3 = boto3.client(
    "s3",
    region_name=region,
    endpoint_url=f"https://s3.{region}.amazonaws.com",
    config=Config(signature_version="s3v4"),
)

AUDIT_TABLE = os.environ.get("URL_AUDIT_TABLE_NAME", "")


def log_url_generation(user_id: str, key: str, expires_in: int):
    """F-3: Log Presigned URL generation for audit purposes."""
    if not AUDIT_TABLE:
        return
    try:
        import uuid

        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table(AUDIT_TABLE)
        table.put_item(
            Item={
                "id": str(uuid.uuid4()),
                "file_key": key,
                "generated_by": user_id,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "expires_in_seconds": expires_in,
                "expires_at": datetime.fromtimestamp(
                    datetime.now(timezone.utc).timestamp() + expires_in, tz=timezone.utc
                ).isoformat(),
                "ttl": int(datetime.now(timezone.utc).timestamp())
                + expires_in
                + 86400,  # Auto-delete 1 day after expiry
            }
        )
    except Exception as e:
        print(f"Audit log warning: {e}")


def handler(event, context):
    """Generate a presigned URL for an object on FSx for ONTAP S3 AP.

    Presigned URLs on FSx for ONTAP S3 AP are client-side SigV4 calculations
    that execute as standard GetObject requests. Verified working (2026-07-19).

    F-3: Logs URL generation to DynamoDB for audit (if URL_AUDIT_TABLE_NAME set).
    Records auto-expire via DynamoDB TTL (1 day after URL expiry).

    Args:
        event: { "key": "path/to/file.jpg", "expiresIn": 300, "userId": "..." }
    Returns:
        { "url": "https://...", "expiresIn": 300 }
    """
    ap_alias = os.environ.get("S3_AP_ALIAS", "")
    key = event.get("key", "")
    expires_in = min(event.get("expiresIn", 300), 3600)  # Max 1 hour
    user_id = event.get("userId", "anonymous")

    if not ap_alias or not key:
        return {"url": None, "expiresIn": 0, "error": "Missing S3_AP_ALIAS or key"}

    try:
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": ap_alias, "Key": key},
            ExpiresIn=expires_in,
        )

        # F-3: Audit log
        log_url_generation(user_id, key, expires_in)

        return {"url": url, "expiresIn": expires_in, "error": None}
    except Exception as e:
        print(f"Error generating presigned URL: {e}")
        return {"url": None, "expiresIn": 0, "error": str(e)}
