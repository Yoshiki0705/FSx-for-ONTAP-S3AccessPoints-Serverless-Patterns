"""Publish how long the oldest approval request has been waiting.

An execution that waits for approval holds its task token in an SSM parameter under
``/<stack>/approvals/``; ``summarize`` deletes it when the run ends. CloudWatch has no metric for
"an execution has been waiting for a person for N hours", so this function, run on a schedule,
reads the parameters' last-modified times and publishes the age of the oldest, in hours, as
``ApprovalPendingHours`` (0 when none), in hours. An alarm on that metric tells someone that the approval
mail was missed, before the approval timeout ends the run without a decision.

A token left behind by an execution that failed before ``summarize`` also keeps the metric
above zero, which is the intended signal: something needs a person to look at it.

A task token cannot be used after the approval timeout, so a parameter older than the timeout plus one
hour belongs to an execution that has ended without reaching ``summarize``. The watchdog deletes it,
after publishing the metric, so the token does not stay readable for a run that cannot use it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import boto3

from shared.archive_verify.runtime import RuntimeConfig
from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)


GRACE_HOURS = 1.0


def oldest_pending_hours(ssm, path: str, now: datetime | None = None, expire_after_hours: float | None = None) -> float:
    """Age in hours of the oldest token. With ``expire_after_hours``, tokens older than that are deleted."""
    now = now or datetime.now(timezone.utc)
    oldest = 0.0
    token = None
    expired: list[str] = []
    while True:
        kwargs = {"Path": path, "Recursive": True, "WithDecryption": False}
        if token:
            kwargs["NextToken"] = token
        resp = ssm.get_parameters_by_path(**kwargs)
        for p in resp.get("Parameters", []):
            age = (now - p["LastModifiedDate"]).total_seconds() / 3600
            oldest = max(oldest, age)
            if expire_after_hours is not None and age > expire_after_hours:
                expired.append(p["Name"])
        token = resp.get("NextToken")
        if not token:
            break
    for name in expired:
        ssm.delete_parameter(Name=name)
    return round(oldest, 2)


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    cfg = RuntimeConfig.from_env()
    hours = oldest_pending_hours(
        boto3.client("ssm"),
        f"/{cfg.stack_name}/approvals",
        expire_after_hours=cfg.approval_timeout_seconds / 3600 + GRACE_HOURS,
    )
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="archive-verify-delete")
    metrics.set_dimension("UseCase", "archive-verify-delete")
    metrics.put_metric("ApprovalPendingHours", hours, "None")
    metrics.flush()
    return {"approvalPendingHours": hours}
