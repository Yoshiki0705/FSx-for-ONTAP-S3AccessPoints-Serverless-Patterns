"""Approval-gated AWS Backup restore handler for FSx for ONTAP volumes.

This Lambda starts an AWS Backup restore job that creates a NEW Amazon FSx for
NetApp ONTAP (thereafter FSx for ONTAP) volume in an EXISTING file system from a
selected recovery point. It is the portal's first write / irreversible AWS Backup
path, so every write is gated twice:

- a server-side acknowledgement guard (``acknowledgeIrreversible`` must be ``True``),
  mirroring ``functions/data-protection/handler.py``; and
- the chat-side ``request_action_approval`` advisory in ``functions/agent-chat``,
  which surfaces the restore for human approval before the agent proposes it.

An AWS Backup restore always creates a new resource; it never writes into an
existing file system's data, never overwrites an existing volume, and never
restores individual files or folders. FSx for ONTAP is the one FSx type whose new
volume can be placed into an existing file system via the chosen SVM. The handler
therefore offers no overwrite / no "restore in place" path, and constrains the
target SVM (and file system) to a configured allowlist.

Like ``functions/recovery-points`` this reaches a regional AWS control-plane API
over the Lambda service network, so it needs no VPC, no shared layer, and no
Secrets Manager credential — only a boto3 ``backup`` client.

Environment:
    BACKUP_RESTORE_ROLE_ARN: ARN of the restore role AWS Backup assumes to create
        the volume. Empty means restore is not configured; the handler answers
        "not configured" instead of calling StartRestoreJob (mirrors the
        ``stateMachineArn`` empty-guard in backend.ts).
    ALLOWED_SVM_IDS: JSON array of storage virtual machine ids a restore may target.
        Empty means no SVM is allowed, so a restore is refused until configured.
    ALLOWED_FILE_SYSTEM_IDS: JSON array of file system ids a restore may target.
        Empty means the file-system allowlist is not enforced (the SVM allowlist
        still applies; an SVM belongs to exactly one file system).

Reference:
    AWS Backup StartRestoreJob:
    https://docs.aws.amazon.com/aws-backup/latest/APIReference/API_StartRestoreJob.html
    Restore an FSx file system (FSx for ONTAP metadata keys, no-overwrite rule):
    https://docs.aws.amazon.com/aws-backup/latest/devguide/restoring-fsx.html
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# The restore role AWS Backup assumes to create the new volume. Empty disables the
# write path: the handler answers "not configured" rather than calling the API.
BACKUP_RESTORE_ROLE_ARN = os.environ.get("BACKUP_RESTORE_ROLE_ARN", "")

# SVM ids a restore may target, as a JSON array supplied by backend.ts from
# config.restoreAllowedSvmIds. A restore to an SVM outside this set is refused: the
# SVM names which existing file system receives the new volume, so an arbitrary SVM
# would place a volume anywhere the restore role can reach.
ALLOWED_SVM_IDS: list[str] = json.loads(os.environ.get("ALLOWED_SVM_IDS", "[]"))

# File system ids a restore may target. The ONTAP restore metadata has no separate
# file-system key (the target is implied by the SVM), so this is an optional second
# allowlist; when it is empty the file-system check is not enforced.
ALLOWED_FILE_SYSTEM_IDS: list[str] = json.loads(os.environ.get("ALLOWED_FILE_SYSTEM_IDS", "[]"))

# FSx for ONTAP restores set ResourceType "FSx"; the API uses it to disambiguate.
FSX_RESOURCE_TYPE = "FSx"

_IRREVERSIBLE_ACK_FIELD = "acknowledgeIrreversible"

# The one-sentence consequence a caller agrees to when it sets the ack flag. Stated
# as what the write does, not as a warning: the restore is additive (it creates a
# new volume) rather than destructive, which is why the UI gate is a checkbox and
# not a typed keyword.
_RESTORE_EFFECT = (
    "This creates a NEW FSx for ONTAP volume in an existing file system from the "
    "selected recovery point; it does not overwrite or restore into any existing "
    "volume, and cannot restore individual files or folders."
)


def _require_ack(event: dict[str, Any], effect: str) -> dict[str, Any] | None:
    """None when the caller acknowledged the write, or an error response.

    Mirrors the guard in ``functions/data-protection/handler.py``. The restore is
    the portal's first write AWS Backup path, so the same rule holds here: the
    mutation is refused unless ``acknowledgeIrreversible`` is ``True``. ``effect`` is
    the consequence in one sentence, interpolated into the error so a caller reading
    only the error learns what it is agreeing to.

    Args:
        event: The request payload.
        effect: One-sentence description of what the write does.

    Returns:
        ``None`` when the write may proceed, else an error dict.
    """
    if event.get(_IRREVERSIBLE_ACK_FIELD) is True:
        return None
    return {
        "error": (
            f"{_IRREVERSIBLE_ACK_FIELD}=true is required for this operation. {effect} "
            "See docs/data-protection-recovery-design.md before setting it."
        ),
    }


def _client():
    """Build the AWS Backup client.

    Kept in a function so the tests can patch ``boto3`` before the client is built,
    rather than at import time.
    """
    return boto3.client("backup")


def _build_metadata(event: dict[str, Any]) -> dict[str, str]:
    """Assemble the FSx for ONTAP restore ``Metadata`` map from the request.

    The required keys come from the console restore flow (Name, SVM, Junction path,
    Volume size); storage efficiency and tiering policy are optional. The whole map
    is passed to ``StartRestoreJob`` as the required ``Metadata`` argument. Every
    value is sent as a string, which is the shape StartRestoreJob's metadata map
    takes.

    Args:
        event: The request payload, already validated for required fields.

    Returns:
        The ``Metadata`` string→string map.
    """
    ontap: dict[str, str] = {
        "storageVirtualMachineId": str(event["storageVirtualMachineId"]),
        "junctionPath": str(event["junctionPath"]),
        "sizeInMegabytes": str(event["sizeInMegabytes"]),
    }
    # Optional, copied only when supplied so the API applies its own defaults
    # otherwise.
    if event.get("storageEfficiencyEnabled") is not None:
        ontap["storageEfficiencyEnabled"] = str(bool(event["storageEfficiencyEnabled"])).lower()
    if event.get("tieringPolicy"):
        ontap["tieringPolicy"] = str(event["tieringPolicy"])

    return {
        "Name": str(event["name"]),
        "OntapConfiguration": json.dumps(ontap),
    }


# Fields a restore is refused without. The SVM names which existing file system
# receives the new volume; the rest describe the volume to create.
_REQUIRED_FIELDS = ("recoveryPointArn", "name", "storageVirtualMachineId", "junctionPath", "sizeInMegabytes")


def _start_restore(event: dict[str, Any]) -> dict[str, Any]:
    """Start an AWS Backup restore job to a new FSx for ONTAP volume.

    Order of guards, each refusing before any API call:
      1. the acknowledgement guard (``acknowledgeIrreversible`` must be ``True``);
      2. the restore-role configuration guard (empty role → "not configured");
      3. required-field validation;
      4. the SVM / file-system allowlist.

    Args:
        event: The request payload.

    Returns:
        ``{"restoreJobId": ..., "error": None}`` on success, else ``{"error": ...}``.
    """
    refused = _require_ack(event, _RESTORE_EFFECT)
    if refused:
        return refused

    if not BACKUP_RESTORE_ROLE_ARN:
        return {"error": "Restore is not configured (set BACKUP_RESTORE_ROLE_ARN)."}

    missing = [field for field in _REQUIRED_FIELDS if not event.get(field)]
    if missing:
        return {"error": f"Missing required field(s): {', '.join(missing)}"}

    svm_id = str(event["storageVirtualMachineId"])
    if svm_id not in ALLOWED_SVM_IDS:
        return {"error": f"Storage virtual machine {svm_id} is not in the allowed set."}

    file_system_id = event.get("fileSystemId")
    if ALLOWED_FILE_SYSTEM_IDS and file_system_id and str(file_system_id) not in ALLOWED_FILE_SYSTEM_IDS:
        return {"error": f"File system {file_system_id} is not in the allowed set."}

    client = _client()
    # A fresh idempotency token per request makes a retry of the same request a
    # no-op success rather than a second volume. The caller may pass one to make a
    # client-side retry safe across invocations.
    idempotency_token = str(event.get("idempotencyToken") or uuid.uuid4())

    response = client.start_restore_job(
        RecoveryPointArn=str(event["recoveryPointArn"]),
        Metadata=_build_metadata(event),
        IamRoleArn=BACKUP_RESTORE_ROLE_ARN,
        ResourceType=FSX_RESOURCE_TYPE,
        IdempotencyToken=idempotency_token,
    )
    return {"restoreJobId": response.get("RestoreJobId", ""), "error": None}


def _describe_restore(event: dict[str, Any]) -> dict[str, Any]:
    """Describe one restore job.

    The portal surfaces the job id and state and links out; it does not poll this on
    a timer (that overlaps #133/#134). The ``Status`` enum here is the restore-JOB
    status (PENDING | RUNNING | COMPLETED | ABORTED | FAILED), distinct from the
    recovery-POINT ``Status`` enum used in #459.

    Args:
        event: The request payload; ``restoreJobId`` is required.

    Returns:
        The job's id, status, status message, progress and created-resource ARN.
    """
    restore_job_id = event.get("restoreJobId", "")
    if not restore_job_id:
        return {"restoreJob": None, "error": "restoreJobId is required"}

    client = _client()
    job = client.describe_restore_job(RestoreJobId=str(restore_job_id))
    return {
        "restoreJob": {
            "restoreJobId": job.get("RestoreJobId", ""),
            "status": job.get("Status", ""),
            "statusMessage": job.get("StatusMessage", ""),
            "percentDone": job.get("PercentDone", ""),
            "createdResourceArn": job.get("CreatedResourceArn", ""),
        },
        "error": None,
    }


def handler(event, context):
    """Dispatch an AWS Backup restore action.

    Actions:
      - ``startRestore`` (default): start a restore job to a new FSx for ONTAP
        volume. Gated by the acknowledgement guard and the SVM allowlist.
      - ``describeRestore``: describe one restore job (job id + state, no polling).

    Returns a plain dict on every path. A boto3 ``ClientError`` or any other
    exception is caught and returned as ``{"error": str(e)}`` so an error never
    raises to AppSync (mirrors ``functions/recovery-points/index.py``).
    """
    action = event.get("action", "startRestore")

    try:
        if action == "startRestore":
            return _start_restore(event)
        if action == "describeRestore":
            return _describe_restore(event)
        return {"error": f"Unknown action: {action}"}
    except ClientError as e:
        logger.warning("AWS Backup restore call failed: %s", e)
        return {"error": str(e)}
    except Exception as e:  # noqa: BLE001 - never raise to AppSync
        logger.exception("Error handling action %s", action)
        return {"error": str(e)}
