"""Build the approval manifest and ask a person to approve it.

Actions:

* ``prepare``  list the VERIFIED files, write ``manifests/<runId>.json`` (for the person) and
               ``manifests/<runId>-items.json`` (for the delete Map state)
* ``request``  store the task token in SSM Parameter Store (SecureString) and publish an SNS
               message that says how to approve or reject. The token is never in the message.
"""

from __future__ import annotations

import logging

import boto3

from shared.archive_verify import ledger as L
from shared.archive_verify.ledger import Ledger
from shared.archive_verify.runtime import MANIFEST_PREFIX, RuntimeConfig, put_json
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
    }


def approval_message(cfg: RuntimeConfig, run_id: str, prepared: dict, dry_run: bool, execution_arn: str) -> str:
    param = token_parameter(cfg.stack_name, run_id)
    return (
        f"Archive run {run_id}: {prepared['count']} files ({prepared['totalBytes']} bytes) verified.\n"
        f"Mode: {'DRY RUN (nothing will be deleted)' if dry_run else 'DELETE from the Access Point after approval'}\n"
        f"Manifest: s3://{cfg.archive_bucket}/{prepared['manifestKey']}\n"
        f"Execution: {execution_arn}\n\n"
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
            cfg, run_id, event["prepared"], bool(event.get("dryRun", True)), event.get("executionArn", "")
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
    raise InvalidInput(f"unknown action {action!r}")
