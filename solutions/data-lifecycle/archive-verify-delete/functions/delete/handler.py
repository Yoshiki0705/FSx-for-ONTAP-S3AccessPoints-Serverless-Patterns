"""Delete one file from the Access Point, only if everything still matches.

The Access Point does not support conditional deletes (``If-Match`` on ``DeleteObject``
returns ``NotImplemented``; ``DeleteObjects`` with an ETag returns ``MalformedXML``).
The check is therefore a ``HeadObject`` immediately before the delete. A write between
the two calls is not detected; the window is the length of one API round trip.

A file is deleted only when all of these hold:

1. ``dryRun`` is the JSON boolean ``false``
2. the ledger status is ``VERIFIED`` (and the second copy is ``VERIFIED`` when one was required)
3. the Access Point's current ETag and size equal the ledger's
4. an approver is named in the input
"""

from __future__ import annotations

import logging

from shared.archive_verify import ledger as L
from shared.archive_verify.ledger import Ledger
from shared.archive_verify.plan import etag_equal, parse_dry_run
from shared.archive_verify.runtime import RuntimeConfig
from shared.exceptions import InvalidInput, S3ApHelperError, lambda_error_handler
from shared.observability import trace_lambda_handler
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)

DELETING = "DELETING"


def delete_one(
    *,
    run_id: str,
    key: str,
    dry_run,
    approved_by: str | None,
    helper: S3ApHelper,
    ledger: Ledger,
) -> dict:
    """Return ``{"key", "outcome", ...}`` where outcome is DELETED, DRY_RUN, CHANGED or NOT_VERIFIED."""
    if parse_dry_run(dry_run):
        return {"key": key, "outcome": "DRY_RUN"}
    if not approved_by or not isinstance(approved_by, str):
        raise InvalidInput("approvedBy is required to delete")

    item = ledger.get(run_id, key)
    if (
        item is None
        or item.get("status") != L.VERIFIED
        or (item.get("secondCopyRequired") and item.get("secondCopy") != L.VERIFIED)
    ):
        return {"key": key, "outcome": "NOT_VERIFIED", "status": item.get("status") if item else None}

    try:
        head = helper.head_object(key)
    except S3ApHelperError as e:
        if e.error_code in ("404", "NoSuchKey", "NotFound"):
            ledger.update(run_id, key, L.CHANGED, only_if_status=L.VERIFIED, reason="source no longer present")
            return {"key": key, "outcome": "CHANGED", "reason": "source no longer present"}
        raise
    if not etag_equal(head["ETag"], item["etag"]) or int(head["ContentLength"]) != int(item["size"]):
        ledger.update(
            run_id,
            key,
            L.CHANGED,
            only_if_status=L.VERIFIED,
            reason="ETag or size differs from the ledger at delete time",
        )
        return {"key": key, "outcome": "CHANGED", "reason": "ETag or size differs from the ledger"}

    # Claim the transition first so two executions cannot both delete.
    if not ledger.update(run_id, key, DELETING, only_if_status=L.VERIFIED):
        return {"key": key, "outcome": "NOT_VERIFIED", "status": "claimed elsewhere"}
    try:
        helper.delete_object(key)
    except Exception:
        ledger.update(run_id, key, L.VERIFIED, only_if_status=DELETING)
        raise
    ledger.update(run_id, key, L.DELETED, only_if_status=DELETING, deletedAt=L.now_iso(), deletedBy=approved_by)
    return {"key": key, "outcome": "DELETED", "size": int(item["size"])}


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    cfg = RuntimeConfig.from_env()
    return delete_one(
        run_id=event["runId"],
        key=event["key"],
        dry_run=event.get("dryRun"),
        approved_by=event.get("approvedBy"),
        helper=S3ApHelper(cfg.access_point),
        ledger=Ledger(cfg.ledger_table),
    )
