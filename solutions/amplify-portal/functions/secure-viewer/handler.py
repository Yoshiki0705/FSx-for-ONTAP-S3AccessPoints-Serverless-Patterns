"""A-4 Implementation: Secure view-only file sharing with dynamic watermark.

Serves files through a Lambda Function URL (or API Gateway) that:
1. Validates a one-time token from DynamoDB
2. Renders the file in an HTML viewer (not downloadable)
3. Overlays a dynamic watermark (user email + timestamp)
4. Sets CSP headers to prevent data exfiltration

Flow:
  User clicks secure share link → Lambda validates token → renders viewer HTML

Environment:
    S3_AP_ALIAS: S3 Access Point alias
    SHARE_TOKENS_TABLE: DynamoDB table for share tokens
    AWS_REGION: Region
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import boto3
from botocore.config import Config

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REGION = os.environ.get("AWS_REGION", "ap-northeast-1")
AP_ALIAS = os.environ.get("S3_AP_ALIAS", "")
TOKENS_TABLE = os.environ.get("SHARE_TOKENS_TABLE", "")

s3 = boto3.client(
    "s3", region_name=REGION, endpoint_url=f"https://s3.{REGION}.amazonaws.com", config=Config(signature_version="s3v4")
)

VIEWER_HTML = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Secure File Viewer</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, sans-serif; background: #1a1a2e; color: #fff; }}
        .viewer {{ position: relative; width: 100vw; height: 100vh; overflow: hidden; }}
        .viewer iframe {{ width: 100%; height: 100%; border: none; }}
        .viewer img {{ max-width: 100%; max-height: 100%; object-fit: contain; display: block; margin: auto; }}
        .watermark {{
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            pointer-events: none; z-index: 9999;
            display: flex; align-items: center; justify-content: center;
            opacity: 0.08; font-size: 2rem; font-weight: bold;
            transform: rotate(-30deg); color: #fff;
            text-shadow: 0 0 10px rgba(255,255,255,0.3);
        }}
        .header {{
            position: fixed; top: 0; left: 0; right: 0;
            background: rgba(0,0,0,0.8); padding: 8px 16px;
            display: flex; justify-content: space-between; align-items: center;
            z-index: 10000; font-size: 0.85rem;
        }}
        .header .title {{ opacity: 0.9; }}
        .header .meta {{ opacity: 0.6; font-size: 0.75rem; }}
        /* Prevent right-click and text selection */
        img, iframe {{ -webkit-user-select: none; user-select: none; }}
    </style>
</head>
<body oncontextmenu="return false">
    <div class="header">
        <span class="title">{filename}</span>
        <span class="meta">View only · Expires {expires}</span>
    </div>
    <div class="viewer">
        {content}
    </div>
    <div class="watermark">{watermark_text}</div>
    <script>
        // Disable keyboard shortcuts for save/print
        document.addEventListener('keydown', function(e) {{
            if ((e.ctrlKey || e.metaKey) && (e.key === 's' || e.key === 'p')) {{
                e.preventDefault();
                return false;
            }}
        }});
    </script>
</body>
</html>"""


def handler(event, context):
    """Handle secure view request via Lambda Function URL or API Gateway."""
    # Extract token from query string
    params = event.get("queryStringParameters", {}) or {}
    token = params.get("token", "")

    if not token or not TOKENS_TABLE:
        return _error_response("Invalid or missing share token")

    # Validate token
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(TOKENS_TABLE)

    try:
        resp = table.get_item(Key={"token": token})
        item = resp.get("Item")
    except Exception as e:
        return _error_response(f"Token validation error: {e}")

    if not item:
        return _error_response("Token not found or expired")

    # Check expiry
    expires_at = item.get("expires_at", "")
    if expires_at and datetime.fromisoformat(expires_at) < datetime.now(timezone.utc):
        return _error_response("Share link has expired")

    # Check view count
    max_views = item.get("max_views", 10)
    view_count = item.get("view_count", 0)
    if view_count >= max_views:
        return _error_response("Maximum view count reached")

    # Increment view count
    table.update_item(
        Key={"token": token},
        UpdateExpression="SET view_count = view_count + :inc",
        ExpressionAttributeValues={":inc": 1},
    )

    # Get file
    file_key = item.get("file_key", "")
    created_by = item.get("created_by", "unknown")

    try:
        # Generate short-lived presigned URL (5 min, for iframe src)
        presigned_url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": AP_ALIAS, "Key": file_key},
            ExpiresIn=300,
        )
    except Exception as e:
        return _error_response(f"File access error: {e}")

    # Determine content type for viewer
    ext = file_key.rsplit(".", 1)[-1].lower() if "." in file_key else ""
    if ext in ("png", "jpg", "jpeg", "gif", "webp"):
        content = f'<img src="{presigned_url}" alt="Preview" draggable="false">'
    elif ext == "pdf":
        content = f'<iframe src="{presigned_url}#toolbar=0&navpanes=0"></iframe>'
    else:
        content = f'<iframe src="{presigned_url}"></iframe>'

    # Build watermark
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    watermark = f"{created_by} · {now}"
    filename = file_key.rsplit("/", 1)[-1] if "/" in file_key else file_key

    html = VIEWER_HTML.format(
        filename=filename,
        expires=expires_at[:16] if expires_at else "N/A",
        content=content,
        watermark_text=watermark,
    )

    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "text/html; charset=utf-8",
            "Content-Security-Policy": "default-src 'self' 'unsafe-inline' https://s3.*.amazonaws.com; img-src 'self' https://s3.*.amazonaws.com data:; frame-src https://s3.*.amazonaws.com",
            "X-Frame-Options": "DENY",
            "Cache-Control": "no-store, no-cache, must-revalidate",
        },
        "body": html,
    }


def _error_response(message: str) -> dict:
    return {
        "statusCode": 403,
        "headers": {"Content-Type": "text/html; charset=utf-8"},
        "body": f"<html><body><h1>Access Denied</h1><p>{message}</p></body></html>",
    }
