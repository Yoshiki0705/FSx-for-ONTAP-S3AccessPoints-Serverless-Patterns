"""Publish how long the oldest approval request has been waiting.

An execution that waits for approval holds its task token in an SSM parameter under
``/<stack>/approvals/``; ``summarize`` deletes it when the run ends. CloudWatch has no metric for
"an execution has been waiting for a person for N hours", so this function, run on a schedule,
reads the parameters' last-modified times and publishes the age of the oldest, in hours, as
``ApprovalPendingHours`` (0 when none), in hours. An alarm on that metric tells someone that the approval
mail was missed, before the approval timeout ends the run without a decision.

A token left behind by an execution that failed before ``summarize`` also keeps the metric
above zero, which is the intended signal: something needs a person to look at it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import boto3

from shared.archive_verify.runtime import RuntimeConfig
from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)


def oldest_pending_hours(ssm, path: str, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    oldest = 0.0
    token = None
    while True:
        kwargs = {"Path": path, "Recursive": True, "WithDecryption": False}
        if token:
            kwargs["NextToken"] = token
        resp = ssm.get_parameters_by_path(**kwargs)
        for p in resp.get("Parameters", []):
            oldest = max(oldest, (now - p["LastModifiedDate"]).total_seconds() / 3600)
        token = resp.get("NextToken")
        if not token:
            return round(oldest, 2)


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    cfg = RuntimeConfig.from_env()
    hours = oldest_pending_hours(boto3.client("ssm"), f"/{cfg.stack_name}/approvals")
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="archive-verify-delete")
    metrics.set_dimension("UseCase", "archive-verify-delete")
    metrics.put_metric("ApprovalPendingHours", hours, "None")
    metrics.flush()
    return {"approvalPendingHours": hours}
