"""A short-lived presigned URL for an object, encoded as a QR code.

The same bypass the download endpoint had, in a form that is easier to miss: this
returns a presigned URL as well as a picture of it. A presigned URL executes as the
ONTAP identity of the access point it was signed against, so signing against
`S3_AP_ALIAS` regardless of the caller handed out the default identity's reach --
measured 2026-08-26 as reading a directory at mode 0700 owned by an unrelated uid.

The QR code makes it worse in one respect: the URL leaves the browser as an image
meant to be scanned by another device, so the credential is expected to travel.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
from typing import Any

from shared.exceptions import S3ApHelperError
from shared.portal_external_policy import share_link_denial_reason
from shared.portal_path_scope import scope_for_caller
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DEFAULT_AP_ALIAS = os.environ.get("S3_AP_ALIAS", "")
GROUP_AP_MAPPING = json.loads(os.environ.get("GROUP_AP_MAPPING", "{}"))
GROUP_PATH_PREFIXES = json.loads(os.environ.get("GROUP_PATH_PREFIXES", "{}"))
MAX_EXPIRY = int(os.environ.get("MAX_QR_EXPIRY_SECONDS", "300"))
# Whether a caller from outside the organisation may mint a share link, by role.
# Absent means denied, so an unset variable does not hand out bearer URLs.
EXTERNAL_SHARE_LINKS_BY_ROLE = json.loads(os.environ.get("EXTERNAL_SHARE_LINKS_BY_ROLE", "{}"))


def generate_qr_png(data: str) -> bytes:
    """Render a QR code as PNG bytes.

    Args:
        data: The text to encode, here a presigned URL.

    Returns:
        PNG bytes, or empty when the `segno` layer is absent -- in which case the
        caller still receives the URL and the client can render the code itself.
    """
    try:
        import segno
    except ImportError:
        logger.warning("segno is not available; returning the URL without a QR image")
        return b""
    qr = segno.make(data)
    buffer = io.BytesIO()
    qr.save(buffer, kind="png", scale=6, border=2)
    return buffer.getvalue()


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Generate a short-expiry presigned URL and encode it as a QR code.

    Args:
        event: `key`, optional `expiresIn`, plus `groups` injected by the resolver
            from the Cognito identity.
        context: Lambda context, unused.

    Returns:
        `qrCodeBase64`, `presignedUrl` and `expiresIn`, or `error`.
    """
    key = event.get("key", "")
    expiry = min(event.get("expiresIn", 300), MAX_EXPIRY)
    groups = event.get("groups") if isinstance(event.get("groups"), list) else []

    empty = {"qrCodeBase64": "", "presignedUrl": "", "expiresIn": 0}

    # Before the boundary check, because the boundary's refusal names the key. Whether
    # this caller may mint a link at all does not depend on which key was asked for,
    # and answering in that order keeps the denial from confirming the key exists.
    denied = share_link_denial_reason(groups, share_links_by_role=EXTERNAL_SHARE_LINKS_BY_ROLE)
    if denied:
        logger.info("Share link refused for an external caller: %s", denied)
        return {**empty, "error": denied}

    alias, refused = scope_for_caller(
        groups,
        group_ap_mapping=GROUP_AP_MAPPING,
        group_path_prefixes=GROUP_PATH_PREFIXES,
        default_alias=DEFAULT_AP_ALIAS,
        key=key,
    )
    if refused:
        return {**empty, **refused}

    try:
        url = S3ApHelper(alias).generate_presigned_get_url(key, expiry)
    except S3ApHelperError as e:
        logger.exception("Presign failed for key %s on %s", key, alias)
        return {**empty, "error": str(e)}

    qr_bytes = generate_qr_png(url)
    return {
        "qrCodeBase64": base64.b64encode(qr_bytes).decode("utf-8") if qr_bytes else "",
        "presignedUrl": url,
        "expiresIn": expiry,
        "error": None,
    }
