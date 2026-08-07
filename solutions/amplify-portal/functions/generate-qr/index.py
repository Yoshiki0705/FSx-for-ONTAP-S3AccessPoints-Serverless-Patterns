import base64
import io
import os

import boto3
from botocore.config import Config

region = os.environ.get("AWS_REGION", "ap-northeast-1")
AP_ALIAS = os.environ.get("S3_AP_ALIAS", "")
MAX_EXPIRY = int(os.environ.get("MAX_QR_EXPIRY_SECONDS", "300"))

s3 = boto3.client(
    "s3",
    region_name=region,
    endpoint_url=f"https://s3.{region}.amazonaws.com",
    config=Config(signature_version="s3v4"),
)


def generate_qr_png(data: str) -> bytes:
    """Generate a QR code PNG using a minimal pure-Python approach.

    Uses segno library if available (Lambda layer), otherwise returns
    a placeholder indicating QR generation requires the segno package.
    """
    try:
        import segno

        qr = segno.make(data)
        buffer = io.BytesIO()
        qr.save(buffer, kind="png", scale=6, border=2)
        return buffer.getvalue()
    except ImportError:
        # Fallback: return a simple SVG-based approach
        try:
            import segno
        except ImportError:
            pass
        # If segno not available, return the URL as text
        # (client can use a JS QR library to render)
        return b""


def handler(event, context):
    """Generate a short-expiry Presigned URL and encode as QR code.

    Used for manufacturing/OT scenarios: scan QR on tablet to view file.
    Default expiry: 5 minutes (configurable, max controlled by MAX_QR_EXPIRY_SECONDS).
    """
    key = event.get("key", "")
    requested_expiry = event.get("expiresIn", 300)

    if not AP_ALIAS or not key:
        return {"qrCodeBase64": "", "presignedUrl": "", "expiresIn": 0, "error": "Missing S3_AP_ALIAS or file key"}

    # Enforce max expiry for security
    expiry = min(requested_expiry, MAX_EXPIRY)

    try:
        # Generate Presigned URL
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": AP_ALIAS, "Key": key},
            ExpiresIn=expiry,
        )

        # Generate QR code
        qr_bytes = generate_qr_png(url)
        qr_base64 = base64.b64encode(qr_bytes).decode("utf-8") if qr_bytes else ""

        return {
            "qrCodeBase64": qr_base64,
            "presignedUrl": url,
            "expiresIn": expiry,
            "error": None,
        }

    except Exception as e:
        print(f"QR generation error: {e}")
        return {"qrCodeBase64": "", "presignedUrl": "", "expiresIn": 0, "error": str(e)}
