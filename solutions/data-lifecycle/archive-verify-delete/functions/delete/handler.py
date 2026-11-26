"""Delete one file from the Access Point, only if the approval step approved it and nothing changed.

The Access Point does not support conditional deletes (``If-Match`` on ``DeleteObject``
returns ``NotImplemented``; ``DeleteObjects`` with an ETag returns ``MalformedXML``).
The check is therefore a ``HeadObject`` immediately before the delete. A write between
the two calls is not detected; the window is the length of one API round trip.

A file is deleted only when all of these hold:

1. ``dryRun`` is the JSON boolean ``false``
2. the ledger status is ``APPROVED``: the approval step wrote it, for this run, after a person
   approved the run (and, with RequireSeparateApprover, after checking the approver is not the
   person who started it). Nothing in this function's input can stand in for that: the former
   ``approvedBy`` input is gone, because any non-empty string in it was enough to delete.
   The approval is also bound to the execution that recorded it (``approvalExecutionArn`` must
   equal ``claim``) and to time (``approvedAt`` is at most ``ApprovalValidityHours`` old). An
   execution stopped after the approval leaves ``APPROVED`` items behind; a direct call with any
   other ``claim``, or a call made after the window, finds them ``NOT_APPROVED``. The ``claim`` must
   also name an execution that is ``RUNNING`` now, so the stopped execution's own ARN, which the
   ledger shows, does not work either; when the state cannot be read the call is refused
3. the second copy is ``VERIFIED`` when one was required
4. the Access Point's current ETag and size equal the ledger's

The delete is idempotent. The function holds a claim (``DELETING`` plus ``claimedBy``, the
execution that runs it). When a call fails after the file was deleted (a client timeout, a
failed ledger write), the Step Functions retry finds the claim, sees the file is gone, and
records ``DELETED`` instead of reporting the file as changed.

``reconcile`` handles what a retry cannot: items left in ``DELETING`` or ``APPROVED`` after the
execution ended.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import boto3

from shared.archive_verify import ledger as L
from shared.archive_verify.ledger import Ledger
from shared.archive_verify.plan import etag_equal, parse_dry_run
from shared.archive_verify.runtime import RuntimeConfig
from shared.exceptions import InvalidInput, S3ApHelperError, lambda_error_handler
from shared.observability import trace_lambda_handler
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)

NOT_FOUND = ("404", "NoSuchKey", "NotFound")
DEFAULT_APPROVAL_VALIDITY_HOURS = 24


def approval_is_current(item: dict, claim: str, validity_hours: float, now: datetime | None = None) -> bool:
    """True when the approval was recorded by execution ``claim`` and is not older than the window.

    An unreadable or missing ``approvedAt`` counts as expired: the approval cannot be shown to be recent.
    """
    if not item.get("approvalExecutionArn") or item["approvalExecutionArn"] != claim:
        return False
    try:
        approved_at = datetime.fromisoformat(str(item.get("approvedAt")))
    except ValueError:
        return False
    if approved_at.tzinfo is None:
        approved_at = approved_at.replace(tzinfo=timezone.utc)
    return (now or datetime.now(timezone.utc)) - approved_at <= timedelta(hours=validity_hours)


def delete_one(
    *,
    run_id: str,
    key: str,
    dry_run,
    claim: str | None,
    helper: S3ApHelper,
    ledger: Ledger,
    approval_validity_hours: float = DEFAULT_APPROVAL_VALIDITY_HOURS,
    execution_state=None,
) -> dict:
    """Return ``{"key", "outcome", ...}``: DELETED, DRY_RUN, CHANGED, NOT_APPROVED or NOT_VERIFIED."""
    if parse_dry_run(dry_run):
        return {"key": key, "outcome": "DRY_RUN"}
    if not claim or not isinstance(claim, str):
        raise InvalidInput("claim (the execution id) is required to delete")
    item = ledger.get(run_id, key)
    resuming = bool(item) and item.get("status") == L.DELETING and item.get("claimedBy") == claim
    if (
        item is None
        or not (item.get("status") == L.APPROVED or resuming)
        or not item.get("approvedBy")
        or not item.get("approvedAt")
    ):
        return {"key": key, "outcome": "NOT_APPROVED", "status": item.get("status") if item else None}
    if not resuming and not approval_is_current(item, claim, approval_validity_hours):
        # An APPROVED item from a stopped execution, or one approved longer ago than the window.
        # reconcile returns it to VERIFIED once its execution is no longer running.
        return {"key": key, "outcome": "NOT_APPROVED", "status": "approval not current"}
    if execution_state is not None and execution_state(claim) != "RUNNING":
        # The claim is only as good as the execution behind it. An execution that was stopped after the
        # approval left APPROVED items whose claim is public (it is in the ledger); it must not delete.
        return {"key": key, "outcome": "NOT_APPROVED", "status": "claiming execution is not running"}
    if item.get("secondCopyRequired") and item.get("secondCopy") != L.VERIFIED:
        return {"key": key, "outcome": "NOT_VERIFIED", "status": "second copy not verified"}
    before = (L.DELETING,) if resuming else (L.APPROVED,)
    try:
        head = helper.head_object(key)
    except S3ApHelperError as e:
        if e.error_code in NOT_FOUND:
            if resuming:
                # The earlier attempt deleted the file and failed afterwards. Finish the record.
                _mark_deleted(ledger, run_id, key, item, claim)
                return {"key": key, "outcome": "DELETED", "size": int(item["size"]), "note": "already gone on retry"}
            ledger.update(run_id, key, L.CHANGED, only_if_status=before, reason="source no longer present")
            return {"key": key, "outcome": "CHANGED", "reason": "source no longer present"}
        raise
    if not etag_equal(head["ETag"], item["etag"]) or int(head["ContentLength"]) != int(item["size"]):
        ledger.update(
            run_id,
            key,
            L.CHANGED,
            only_if_status=before,
            reason="ETag or size differs from the ledger at delete time",
        )
        return {"key": key, "outcome": "CHANGED", "reason": "ETag or size differs from the ledger"}
    # Claim the transition first so two executions cannot both delete.
    claimed = ledger.update(
        run_id,
        key,
        L.DELETING,
        only_if_status=before,
        also_if={"claimedBy": claim} if resuming else None,
        claimedBy=claim,
    )
    if not claimed:
        return {"key": key, "outcome": "NOT_APPROVED", "status": "claimed elsewhere"}
    # No rollback if this raises: whether the file is gone is unknown, so the item stays
    # DELETING with this claim and the retry decides from what the Access Point says.
    helper.delete_object(key)
    _mark_deleted(ledger, run_id, key, item, claim)
    return {"key": key, "outcome": "DELETED", "size": int(item["size"])}


def _mark_deleted(ledger: Ledger, run_id: str, key: str, item: dict, claim: str) -> None:
    ledger.update(
        run_id,
        key,
        L.DELETED,
        only_if_status=L.DELETING,
        also_if={"claimedBy": claim},
        deletedAt=L.now_iso(),
        deletedBy=item["approvedBy"],
    )


def execution_status(sfn, arn: str) -> str:
    """Status of an execution, or ``UNKNOWN`` when it cannot be read (the caller then refuses)."""
    try:
        return sfn.describe_execution(executionArn=arn)["status"]
    except Exception:  # noqa: BLE001 - fail closed: an unreadable execution is not shown to be running
        logger.warning("could not read execution %s; refusing to delete under it", arn)
        return "UNKNOWN"


def _execution_running(sfn, arn: str | None) -> bool:
    if not arn:
        return False
    try:
        return sfn.describe_execution(executionArn=arn)["status"] == "RUNNING"
    except Exception:  # noqa: BLE001 - when the state is unknown, treat the execution as running
        logger.warning("could not read execution %s; leaving its items alone", arn)
        return True


def reconcile(*, run_id: str, helper: S3ApHelper, ledger: Ledger, sfn=None) -> dict:
    """Settle items an ended execution left in ``DELETING`` or ``APPROVED``.

    * ``DELETING`` and the file is gone from the Access Point: ``DELETED`` (the delete happened)
    * ``DELETING`` or ``APPROVED`` and the file is there, unchanged: back to ``VERIFIED``, so a new
      approval is needed before it can be deleted. An approval belongs to one execution
    * the file is there but differs from the ledger: ``CHANGED``
    * the execution that holds the item is still running: left alone
    """
    sfn = sfn or boto3.client("stepfunctions")
    counts = {"deleted": 0, "reverified": 0, "changed": 0, "running": 0}
    for item in ledger.query_run(run_id):
        if item.get("status") not in (L.DELETING, L.APPROVED):
            continue
        key = item["key"]
        if _execution_running(sfn, item.get("claimedBy") or item.get("approvalExecutionArn")):
            counts["running"] += 1
            continue
        try:
            head = helper.head_object(key)
        except S3ApHelperError as e:
            if e.error_code not in NOT_FOUND:
                raise
            if item["status"] == L.DELETING:
                ledger.update(
                    run_id,
                    key,
                    L.DELETED,
                    only_if_status=L.DELETING,
                    deletedAt=L.now_iso(),
                    deletedBy=item.get("approvedBy"),
                    reconciled=True,
                )
                counts["deleted"] += 1
            else:
                ledger.update(run_id, key, L.CHANGED, only_if_status=L.APPROVED, reason="source no longer present")
                counts["changed"] += 1
            continue
        if etag_equal(head["ETag"], item["etag"]) and int(head["ContentLength"]) == int(item["size"]):
            ledger.update(run_id, key, L.VERIFIED, only_if_status=(L.DELETING, L.APPROVED), reconciled=True)
            counts["reverified"] += 1
        else:
            ledger.update(
                run_id,
                key,
                L.CHANGED,
                only_if_status=(L.DELETING, L.APPROVED),
                reason="ETag or size differs from the ledger at reconcile time",
            )
            counts["changed"] += 1
    return counts


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    cfg = RuntimeConfig.from_env()
    helper, ledger = S3ApHelper(cfg.access_point), Ledger(cfg.ledger_table)
    if event.get("action") == "reconcile":
        return reconcile(run_id=event["runId"], helper=helper, ledger=ledger)
    sfn = boto3.client("stepfunctions")
    return delete_one(
        run_id=event["runId"],
        key=event["key"],
        dry_run=event.get("dryRun"),
        claim=event.get("claim"),
        helper=helper,
        ledger=ledger,
        approval_validity_hours=cfg.approval_validity_hours,
        execution_state=lambda arn: execution_status(sfn, arn),
    )
