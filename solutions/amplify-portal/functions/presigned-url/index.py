"""Presigned URLs for FSx for ONTAP S3 Access Point objects.

A presigned URL executes as the ONTAP identity of the access point it was signed
against, not as the person who asked for it. Measured 2026-08-26 on ONTAP
9.18.1P3D1: a URL signed against an access point pinned to UNIX `root` returned the
contents of a directory at mode 0700 owned by an unrelated uid, fetched by a client
holding no AWS credentials, and a `PUT` signed the same way landed on the volume
owned by uid 0. The same key signed against an access point pinned to a read-only
identity answered 403.

This function used to read `S3_AP_ALIAS` alone. Where a deployment mapped groups to
per-identity access points, every download URL was therefore signed against the
default one -- so the boundary held for listing and writing through
`functions/list-files` and was bypassed for reading here. Both halves now apply: the
group decides the access point, and the key is checked against the caller's prefixes
before anything is signed.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from shared.exceptions import S3ApHelperError
from shared.portal_activity_ledger import ACTION_SHARE_LINK, record_activity
from shared.portal_external_policy import share_link_expiry_ceiling
from shared.portal_path_scope import allowed_prefixes, reject_key, resolve_ap_alias
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger()
logger.setLevel(logging.INFO)

AUDIT_TABLE = os.environ.get("URL_AUDIT_TABLE_NAME", "")
DEFAULT_AP_ALIAS = os.environ.get("S3_AP_ALIAS", "")
GROUP_AP_MAPPING = json.loads(os.environ.get("GROUP_AP_MAPPING", "{}"))
GROUP_PATH_PREFIXES = json.loads(os.environ.get("GROUP_PATH_PREFIXES", "{}"))
# Whether a caller from outside the organisation may mint a share link, by role.
# Absent means denied, so an unset variable does not hand out bearer URLs.
EXTERNAL_SHARE_LINKS_BY_ROLE = json.loads(os.environ.get("EXTERNAL_SHARE_LINKS_BY_ROLE", "{}"))

# One hour. Longer than a preview needs, and the URL is a bearer credential that no
# later authorization decision can withdraw.
MAX_EXPIRES_IN = 3600
DEFAULT_EXPIRES_IN = 300


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Generate a presigned URL for an object on FSx for ONTAP S3 AP.

    Args:
        event: `key`, optional `expiresIn`, plus `userId` and `groups` injected by the
            resolver from the Cognito identity.
        context: Lambda context, unused.

    Returns:
        `url` and `expiresIn`, or `error` naming why nothing was signed.
    """
    key = event.get("key", "")
    expires_in = min(event.get("expiresIn", DEFAULT_EXPIRES_IN), MAX_EXPIRES_IN)
    user_id = event.get("userId", "anonymous")
    groups = event.get("groups") if isinstance(event.get("groups"), list) else []

    # Clamped rather than refused. This one query backs the preview, the download button
    # and the share dialog, and the request does not say which -- the share dialog's
    # shortest lifetime is the preview's. Refusing would take away downloading, so what
    # the role controls is how long the URL stays redeemable.
    ceiling = share_link_expiry_ceiling(groups, share_links_by_role=EXTERNAL_SHARE_LINKS_BY_ROLE)
    if ceiling is not None and expires_in > ceiling:
        logger.info(
            "Clamping presigned URL lifetime from %ss to %ss: external caller whose role does not allow share links",
            expires_in,
            ceiling,
        )
        expires_in = ceiling

    # The group decides the access point, so the URL carries the identity that group
    # is meant to act as rather than the deployment's default one.
    ap_alias = resolve_ap_alias(groups, GROUP_AP_MAPPING, DEFAULT_AP_ALIAS)
    if not ap_alias:
        return {"url": None, "expiresIn": 0, "error": "S3_AP_ALIAS is not configured"}

    # Checked before signing. The URL outlives the request, so an unchecked key hands
    # out access that cannot be withdrawn afterwards.
    refused = reject_key(key, allowed_prefixes(groups, GROUP_PATH_PREFIXES), field="key")
    if refused:
        return {"url": None, "expiresIn": 0, **refused}

    try:
        url = S3ApHelper(ap_alias).generate_presigned_get_url(key, expires_in)
    except S3ApHelperError as e:
        logger.exception("Presign failed for key %s on %s", key, ap_alias)
        return {"url": None, "expiresIn": 0, "error": str(e)}

    # Recorded after signing, because the row describes a URL that exists. The write
    # cannot fail the request: the URL is already valid and cannot be withdrawn, so a
    # failure here would turn a gap in the record into a failed request.
    record_activity(
        table_name=AUDIT_TABLE,
        action=ACTION_SHARE_LINK,
        user_id=user_id,
        key=key,
        access_point=ap_alias,
        groups=groups,
        detail={
            "expires_in_seconds": expires_in,
            "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat(),
        },
    )
    return {"url": url, "expiresIn": expires_in, "error": None}
