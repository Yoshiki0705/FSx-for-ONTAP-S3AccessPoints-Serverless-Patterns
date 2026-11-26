"""Write the run summary, emit metrics, notify, and remove the approval token."""

from __future__ import annotations

import logging
from collections import Counter

import boto3
from botocore.exceptions import ClientError

from shared.archive_verify import ledger as L
from shared.archive_verify.ledger import Ledger
from shared.archive_verify.runtime import MANIFEST_PREFIX, RuntimeConfig, put_json
from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)


def build_summary(run_id: str, outcome: str, items: list[dict], extra: dict) -> dict:
    by_status = Counter(i.get("status", "UNKNOWN") for i in items)
    return {
        "runId": run_id,
        "outcome": outcome,
        "finishedAt": L.now_iso(),
        "filesByStatus": dict(by_status),
        "bytesVerified": sum(int(i["size"]) for i in items if i.get("status") in (L.VERIFIED, L.DELETED)),
        "bytesDeleted": sum(int(i["size"]) for i in items if i.get("status") == L.DELETED),
        "mismatches": [i["key"] for i in items if i.get("status") == L.MISMATCH],
        "changed": [i["key"] for i in items if i.get("status") == L.CHANGED],
        "failed": [i["key"] for i in items if i.get("status") == L.FAILED],
        "dataClassification": "operational-metadata",
        **extra,
    }


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    cfg = RuntimeConfig.from_env()
    run_id, outcome = event["runId"], event["outcome"]
    items = Ledger(cfg.ledger_table).query_run(run_id)
    summary = build_summary(
        run_id,
        outcome,
        items,
        {
            "storageClass": event.get("storageClass"),
            "dryRun": event.get("dryRun"),
            "skippedLarge": event.get("skippedLarge", 0),
        },
    )
    key = f"{MANIFEST_PREFIX}{run_id}-result.json"
    put_json(cfg.archive_bucket, key, summary)

    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="archive-verify-delete")
    metrics.set_dimension("UseCase", "archive-verify-delete")
    counts = summary["filesByStatus"]
    metrics.put_metric("FilesVerified", counts.get(L.VERIFIED, 0) + counts.get(L.DELETED, 0), "Count")
    metrics.put_metric("FilesDeleted", counts.get(L.DELETED, 0), "Count")
    metrics.put_metric("FilesMismatch", counts.get(L.MISMATCH, 0), "Count")
    metrics.put_metric("FilesChanged", counts.get(L.CHANGED, 0), "Count")
    metrics.put_metric("FilesFailed", counts.get(L.FAILED, 0), "Count")
    metrics.put_metric("BytesVerified", summary["bytesVerified"], "Bytes")
    metrics.put_metric("BytesDeleted", summary["bytesDeleted"], "Bytes")
    metrics.flush()

    session = boto3.Session()
    if cfg.sns_topic_arn:
        session.client("sns").publish(
            TopicArn=cfg.sns_topic_arn,
            Subject=f"Archive run {run_id}: {outcome}"[:100],
            Message=f"Result: s3://{cfg.archive_bucket}/{key}\nFiles by status: {summary['filesByStatus']}",
        )
    try:
        session.client("ssm").delete_parameter(Name=f"/{cfg.stack_name}/approvals/{run_id}")
    except ClientError as e:
        if e.response["Error"]["Code"] != "ParameterNotFound":
            raise
    return {"resultKey": key, "filesByStatus": summary["filesByStatus"], "outcome": outcome}
