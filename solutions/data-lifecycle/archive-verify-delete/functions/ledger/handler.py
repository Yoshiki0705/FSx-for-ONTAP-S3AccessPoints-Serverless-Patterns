"""Ledger transitions that depend on what S3 reported.

Actions:

* ``compare``  compare a ``HeadObject`` response from the archive (or second copy) bucket with
               the ledger, and set ``VERIFIED`` or ``MISMATCH``
* ``mark``     record a failure for a file whose processing raised
"""

from __future__ import annotations

import logging

from shared.archive_verify import ledger as L
from shared.archive_verify.checksums import expected_algorithm, verify_head
from shared.archive_verify.ledger import Ledger
from shared.archive_verify.runtime import RuntimeConfig
from shared.exceptions import InvalidInput, lambda_error_handler
from shared.observability import trace_lambda_handler

logger = logging.getLogger(__name__)

PRECONDITION_MARKERS = ("PreconditionFailed", "pre-conditions you specified", "Status Code: 412")


def compare(ledger: Ledger, event: dict) -> dict:
    run_id, key, target = event["runId"], event["key"], event.get("target", "archive")
    item = ledger.get(run_id, key)
    if item is None:
        raise InvalidInput(f"no ledger item for {key}")
    # A large file is hashed by the Fargate task, which writes crc64nvme before copying.
    algorithm = expected_algorithm(bool(item.get("isLarge")))
    ok, reason = verify_head(
        event["head"],
        size=int(item["size"]),
        sha256_b64=item.get("sha256B64", ""),
        crc64nvme_b64=item.get("crc64nvme", ""),
        algorithm=algorithm,
    )
    if target == "archive":
        ledger.update(
            run_id,
            key,
            L.VERIFIED if ok else L.MISMATCH,
            only_if_status=(L.RECORDED, L.COPIED),
            verifiedAt=L.now_iso() if ok else None,
            verifyAlgorithm=algorithm,
            verifyReason=reason,
        )
    else:
        # A bad second copy withdraws the file from deletion.
        if ok:
            ledger.update(run_id, key, L.VERIFIED, only_if_status=L.VERIFIED, secondCopy=L.VERIFIED)
        else:
            ledger.update(
                run_id,
                key,
                L.MISMATCH,
                only_if_status=L.VERIFIED,
                secondCopy=L.MISMATCH,
                verifyReason=f"second copy: {reason}",
            )
    return {"key": key, "target": target, "verified": ok, "reason": reason, "algorithm": algorithm}


def mark(ledger: Ledger, event: dict) -> dict:
    run_id, key = event["runId"], event["key"]
    error = str(event.get("error", ""))[:1000]
    # A failed precondition on the copy means the source changed after it was recorded.
    status = L.CHANGED if any(m in error for m in PRECONDITION_MARKERS) else L.FAILED
    live = (L.SELECTED, L.RECORDED, L.COPIED, L.VERIFIED)
    if not ledger.update(run_id, key, status, only_if_status=live, reason=error):
        if ledger.get(run_id, key) is None:
            ledger.put(run_id, key, status, reason=error)
    return {"key": key, "status": status}


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    cfg = RuntimeConfig.from_env()
    ledger = Ledger(cfg.ledger_table)
    action = event.get("action")
    if action == "compare":
        return compare(ledger, event)
    if action == "mark":
        return mark(ledger, event)
    raise InvalidInput(f"unknown action {action!r}")
