"""Build the approval manifest and ask a person to approve it.

Actions:

* ``prepare``  list the VERIFIED files, write ``manifests/<runId>.json`` (for the person) and
               ``manifests/<runId>-items.json`` (for the delete Map state)
* ``request``  store the task token in SSM Parameter Store (SecureString) and publish an SNS
               message that says how to approve or reject. The token is never in the message.
* ``approve``  runs after a person sent ``SendTaskSuccess``. Checks the approver against the person
               who started the run (RequireSeparateApprover), then marks every listed item
               ``APPROVED`` in the ledger and writes ``manifests/<runId>-approval.json``. The delete
               step deletes only ``APPROVED`` items, so this is the one place approval is recorded.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

import boto3

from shared.archive_verify import ledger as L
from shared.archive_verify.ledger import Ledger
from shared.archive_verify.plan import ACCESS_POINT_UPLOAD_LIMIT_BYTES, same_principal
from shared.archive_verify.runtime import MANIFEST_PREFIX, RuntimeConfig, get_json, put_json
from shared.exceptions import InvalidInput, lambda_error_handler
from shared.observability import trace_lambda_handler

logger = logging.getLogger(__name__)


def token_parameter(stack_name: str, run_id: str) -> str:
    return f"/{stack_name}/approvals/{run_id}"


def eligible(item: dict) -> bool:
    """A file may be listed for deletion only when every required copy is verified."""
    if item.get("status") != L.VERIFIED:
        return False
    return not item.get("secondCopyRequired") or item.get("secondCopy") == L.VERIFIED


def prepare(cfg: RuntimeConfig, event: dict, ledger: Ledger | None = None) -> dict:
    run_id = event["runId"]
    ledger = ledger or Ledger(cfg.ledger_table)
    items = ledger.query_run(run_id)
    verified = [i for i in items if eligible(i)]
    excluded = [i for i in items if not eligible(i)]
    manifest = {
        "runId": run_id,
        "generatedAt": L.now_iso(),
        "dryRun": event.get("dryRun", True),
        "storageClass": event.get("storageClass"),
        **cfg.classification_fields(),
        "oversizeFiles": sum(1 for i in verified if int(i["size"]) > ACCESS_POINT_UPLOAD_LIMIT_BYTES),
        "archiveBucket": cfg.archive_bucket,
        "secondCopyBucket": cfg.second_copy_bucket or None,
        "totalBytes": sum(int(i["size"]) for i in verified),
        "files": [
            {
                "key": i["key"],
                "size": int(i["size"]),
                "etag": i["etag"],
                "sha256": i.get("sha256"),
                "crc64nvme": i.get("crc64nvme"),
                "archiveKey": i.get("archiveKey"),
            }
            for i in verified
        ],
        "notDeletable": [{"key": i["key"], "status": i.get("status")} for i in excluded],
    }
    items_key = f"{MANIFEST_PREFIX}{run_id}-items.json"
    manifest_key = f"{MANIFEST_PREFIX}{run_id}.json"
    put_json(cfg.archive_bucket, manifest_key, manifest)
    put_json(cfg.archive_bucket, items_key, [{"key": f["key"]} for f in manifest["files"]])
    return {
        "count": len(verified),
        "excluded": len(excluded),
        "totalBytes": manifest["totalBytes"],
        "bucket": cfg.archive_bucket,
        "manifestKey": manifest_key,
        "itemsKey": items_key,
        "oversizeFiles": manifest["oversizeFiles"],
    }


def approve(
    cfg: RuntimeConfig, event: dict, ledger: Ledger | None = None, session: boto3.Session | None = None
) -> dict:
    """Record the approval of a run: separation check, then ``VERIFIED`` -> ``APPROVED`` per item."""
    run_id = event["runId"]
    ledger = ledger or Ledger(cfg.ledger_table)
    approval = event.get("approval") or {}
    approver = approval.get("approver")
    if approval.get("approved") is not True or not isinstance(approver, str) or not approver.strip():
        return {"approved": False, "reason": "NO_APPROVER"}
    approver = approver.strip()
    requested_by = (event.get("requestedBy") or "").strip()
    if cfg.require_separate_approver:
        if not requested_by:
            return {"approved": False, "reason": "NO_REQUESTER"}
        if same_principal(requested_by, approver):
            logger.warning("refusing approval of %s: the approver is the principal that started the run", run_id)
            return {"approved": False, "reason": "SELF_APPROVAL"}
    items = get_json(event["bucket"], event["itemsKey"])
    stamp = {
        "approvedBy": approver,
        "approvedAt": L.now_iso(),
        "approvalExecutionArn": event.get("executionArn"),
        "requestedBy": requested_by or None,
    }

    def mark(entry: dict) -> bool:
        return ledger.update(run_id, entry["key"], L.APPROVED, only_if_status=L.VERIFIED, **stamp)

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(mark, items))
    marked = sum(results)
    put_json(
        cfg.archive_bucket,
        f"{MANIFEST_PREFIX}{run_id}-approval.json",
        {
            "runId": run_id,
            "approver": approver,
            "requestedBy": requested_by or None,
            "requireSeparateApprover": cfg.require_separate_approver,
            "executionArn": event.get("executionArn"),
            "executionStartTime": event.get("executionStartTime"),
            "approvedAt": stamp["approvedAt"],
            "itemsListed": len(items),
            "itemsApproved": marked,
            "note": "approver and requestedBy are values the callers declared; "
            "CloudTrail StartExecution and SendTaskSuccess events name the real principals",
            **cfg.classification_fields(),
        },
        session,
    )
    return {"approved": True, "approvedBy": approver, "marked": marked, "notMarked": len(items) - marked}


def approval_message(
    cfg: RuntimeConfig,
    run_id: str,
    prepared: dict,
    dry_run: bool,
    execution_arn: str,
    requested_by: str | None = None,
) -> str:
    param = token_parameter(cfg.stack_name, run_id)
    copies = (
        f"Second copy: s3://{cfg.second_copy_bucket}/ (verified before deletion)"
        if cfg.second_copy_bucket
        else "COPIES: ONE. No second copy is configured; after deletion the archive bucket holds the only copy"
    )
    oversize = prepared.get("oversizeFiles", 0)
    warn = (
        f"WARNING: {oversize} file(s) exceed the Access Point upload limit and cannot be restored to the "
        "Access Point; they can only be downloaded from the archive bucket.\n"
        if oversize
        else ""
    )
    separation = (
        f"Started by: {requested_by or '(not given)'}. The approver must be a different principal "
        "(RequireSeparateApprover is on); a self-approval is refused and nothing is deleted.\n"
        if cfg.require_separate_approver and not dry_run
        else ""
    )
    return (
        f"Archive run {run_id}: {prepared['count']} files ({prepared['totalBytes']} bytes) verified.\n"
        f"Mode: {'DRY RUN (nothing will be deleted)' if dry_run else 'DELETE from the Access Point after approval'}\n"
        f"Manifest: s3://{cfg.archive_bucket}/{prepared['manifestKey']}\n"
        f"Execution: {execution_arn}\n"
        f"{copies}\n{warn}{separation}\n"
        "Review the manifest first. To approve:\n"
        f"  TOKEN=$(aws ssm get-parameter --name {param} --with-decryption --query Parameter.Value --output text)\n"
        '  aws stepfunctions send-task-success --task-token "$TOKEN" \\\n'
        '    --task-output \'{"approved": true, "approver": "<your IAM principal ARN>"}\'\n'
        "To reject:\n"
        "  aws stepfunctions send-task-failure --task-token \"$TOKEN\" --error Rejected --cause '<reason>'\n"
    )


def request(cfg: RuntimeConfig, event: dict, session: boto3.Session | None = None) -> dict:
    session = session or boto3.Session()
    run_id = event["runId"]
    if not event.get("taskToken"):
        raise InvalidInput("taskToken is required")
    session.client("ssm").put_parameter(
        Name=token_parameter(cfg.stack_name, run_id),
        Value=event["taskToken"],
        Type="SecureString",
        Overwrite=True,
        Description=f"Task token for archive run {run_id}. Delete after the run.",
    )
    session.client("sns").publish(
        TopicArn=cfg.sns_topic_arn,
        Subject=f"Approval needed: archive run {run_id}"[:100],
        Message=approval_message(
            cfg,
            run_id,
            event["prepared"],
            bool(event.get("dryRun", True)),
            event.get("executionArn", ""),
            event.get("requestedBy"),
        ),
    )
    return {"requested": True}


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    cfg = RuntimeConfig.from_env()
    action = event.get("action")
    if action == "prepare":
        return prepare(cfg, event)
    if action == "request":
        return request(cfg, event)
    if action == "approve":
        return approve(cfg, event)
    raise InvalidInput(f"unknown action {action!r}")
