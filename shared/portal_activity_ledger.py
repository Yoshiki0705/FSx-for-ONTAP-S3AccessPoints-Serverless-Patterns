"""A per-user record of what the portal did, written where the action happened.

Distinct from the CloudTrail data-event trail the audit tab already queries, and not a
replacement for it. The two answer different questions and neither substitutes:

  CloudTrail records what reached S3, attributed to the access point's IAM role. Every
  portal user's activity arrives under the same principal, so it establishes that an
  object was read and not who asked for it.

  This ledger records the portal request, attributed to the Cognito user. It knows who,
  and it knows the things that never reach S3 as a distinguishable event at all -- a
  presigned URL is minted without touching the object, and the download that follows is
  attributed to whoever redeemed the URL rather than to whoever asked for it.

Writes never fail the caller. The action has already happened by the time the ledger is
written, so raising here would turn a gap in the record into a failed request. The write
is logged at warning instead, which makes the gap visible rather than silent -- and a
gap that nobody can see is worse than one that shows up in the log.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3

logger = logging.getLogger(__name__)

__all__ = [
    "ACTION_DELETE",
    "ACTION_DOWNLOAD",
    "ACTION_SHARE_LINK",
    "ACTION_UPLOAD_LINK",
    "DEFAULT_RETENTION_DAYS",
    "record_activity",
]

# What happened. Kept as constants rather than free strings because the audit tab groups
# by them, and a second spelling of the same action reads as two kinds of activity.
ACTION_DOWNLOAD = "DOWNLOAD"
ACTION_UPLOAD_LINK = "UPLOAD_LINK"
ACTION_DELETE = "DELETE"
ACTION_SHARE_LINK = "SHARE_LINK"

# How long a row survives.
#
# 90 days rather than the URL's own lifetime, which is what the previous inline version
# used: it deleted each row a day after the URL expired, so the record of who was given
# access disappeared days after the access did. An audit trail that outlives only the
# thing it describes cannot answer a question asked later, which is when audit questions
# are asked.
DEFAULT_RETENTION_DAYS = 90


def record_activity(
    *,
    table_name: str,
    action: str,
    user_id: str,
    key: str,
    access_point: str,
    groups: list[str] | None = None,
    detail: dict[str, Any] | None = None,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> bool:
    """Append one row to the activity ledger.

    Args:
        table_name: The DynamoDB table. An empty string means no ledger is configured,
            and the call returns without writing.
        action: One of the `ACTION_*` constants.
        user_id: The Cognito user the resolver attributed the call to.
        key: The object key, or the prefix for a folder-wide action.
        access_point: The access point the action went through. Recorded because the
            ONTAP identity follows from it, so two rows naming the same key are
            otherwise indistinguishable even when one carried far wider access.
        groups: The caller's Cognito groups, recorded as they were at the time. Group
            membership changes, and a row that only names the user cannot later show
            what they held when they acted.
        detail: Action-specific fields, such as a URL's lifetime.
        retention_days: How long the row survives.

    Returns:
        True when a row was written. False when no ledger is configured or the write
        failed -- both are reported rather than raised, because the action being
        recorded has already succeeded.
    """
    if not table_name:
        return False
    now = datetime.now(timezone.utc)
    item: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "action": action,
        "file_key": key,
        # Kept as the field name the previous inline version wrote, so rows from before
        # this module remain readable by the same query.
        "generated_by": user_id,
        "access_point": access_point,
        "generated_at": now.isoformat(),
        "groups": sorted(groups) if groups else [],
        "ttl": int((now + timedelta(days=retention_days)).timestamp()),
    }
    if detail:
        item.update(detail)
    try:
        boto3.resource("dynamodb").Table(table_name).put_item(Item=item)
        return True
    except Exception:
        logger.warning(
            "Activity ledger write failed: %s on %s by %s",
            action,
            key,
            user_id,
            exc_info=True,
        )
        return False
