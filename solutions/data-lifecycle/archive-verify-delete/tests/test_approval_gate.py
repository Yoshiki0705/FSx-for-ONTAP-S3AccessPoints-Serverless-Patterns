"""The delete step deletes only what the approval step marked APPROVED for this run.

Before this gate, any non-empty ``approvedBy`` in the Lambda's input was enough to delete a
VERIFIED item, so a direct invoke (or a dry-run row left at VERIFIED) could delete a file
with no approval at all. The first test below is that case; it failed against the earlier code.
"""

from __future__ import annotations

import json

import pytest
from avd_support import AP, ARCHIVE, load_handler

from shared.archive_verify import ledger as L
from shared.archive_verify.plan import same_principal
from shared.archive_verify.runtime import RuntimeConfig
from shared.s3ap_helper import S3ApHelper

delete = load_handler("delete")
approval = load_handler("approval")

STARTER = "arn:aws:iam::123456789012:user/starter"
APPROVER = "arn:aws:iam::123456789012:user/approver"
CLAIM = "arn:aws:states:ap-northeast-1:123456789012:execution:avd-archive:exec-1"


def _put_verified(aws, ledger, key="docs/a.txt", body=b"hello", run="run1"):
    put = aws.put_object(Bucket=AP, Key=key, Body=body)
    ledger.put(
        run,
        key,
        L.VERIFIED,
        size=len(body),
        etag=put["ETag"],
        archiveBucket=ARCHIVE,
        archiveKey=f"data/{run}/{key}",
        secondCopyRequired=False,
    )


def _exists(aws, key="docs/a.txt"):
    return "Contents" in aws.list_objects_v2(Bucket=AP, Prefix=key)


def test_a_verified_item_is_not_deleted_whatever_the_caller_claims(aws, ledger):
    _put_verified(aws, ledger)
    result = delete.delete_one(
        run_id="run1", key="docs/a.txt", dry_run=False, claim=CLAIM, helper=S3ApHelper(AP), ledger=ledger
    )
    assert result["outcome"] == "NOT_APPROVED"
    assert _exists(aws)
    assert ledger.get("run1", "docs/a.txt")["status"] == L.VERIFIED


def test_the_delete_function_has_no_approved_by_input():
    import inspect

    assert "approved_by" not in inspect.signature(delete.delete_one).parameters


# ---- the approval step -------------------------------------------------------------------------


def _event(aws, run="run1", keys=("docs/a.txt",), approver=APPROVER, requested_by=STARTER, approved=True):
    aws.put_object(
        Bucket=ARCHIVE, Key=f"manifests/{run}-items.json", Body=json.dumps([{"key": k} for k in keys]).encode()
    )
    return {
        "runId": run,
        "approval": {"approved": approved, "approver": approver},
        "requestedBy": requested_by,
        "bucket": ARCHIVE,
        "itemsKey": f"manifests/{run}-items.json",
        "executionArn": CLAIM,
        "executionStartTime": "2026-01-01T00:00:00Z",
    }


def test_approval_marks_the_listed_items_approved_and_records_who(aws, ledger):
    _put_verified(aws, ledger)
    out = approval.approve(RuntimeConfig.from_env(), _event(aws), ledger=ledger)
    assert out["approved"] is True and out["marked"] == 1
    item = ledger.get("run1", "docs/a.txt")
    assert item["status"] == L.APPROVED
    assert item["approvedBy"] == APPROVER and item["requestedBy"] == STARTER
    assert item["approvalExecutionArn"] == CLAIM and item["approvedAt"]
    record = json.loads(aws.get_object(Bucket=ARCHIVE, Key="manifests/run1-approval.json")["Body"].read())
    assert record["approver"] == APPROVER and record["requestedBy"] == STARTER
    assert record["data_classification"] == "RESTRICTED"


def test_the_starter_cannot_approve_their_own_run(aws, ledger):
    _put_verified(aws, ledger)
    out = approval.approve(RuntimeConfig.from_env(), _event(aws, approver=STARTER), ledger=ledger)
    assert out == {"approved": False, "reason": "SELF_APPROVAL"}
    assert ledger.get("run1", "docs/a.txt")["status"] == L.VERIFIED


def test_a_session_of_the_starting_role_is_the_same_principal(aws, ledger):
    _put_verified(aws, ledger)
    starter = "arn:aws:iam::123456789012:role/ops"
    approver = "arn:aws:sts::123456789012:assumed-role/ops/alice"
    out = approval.approve(
        RuntimeConfig.from_env(), _event(aws, approver=approver, requested_by=starter), ledger=ledger
    )
    assert out["reason"] == "SELF_APPROVAL"


def test_a_run_without_a_requester_cannot_be_approved_when_separation_is_required(aws, ledger):
    _put_verified(aws, ledger)
    out = approval.approve(RuntimeConfig.from_env(), _event(aws, requested_by=""), ledger=ledger)
    assert out == {"approved": False, "reason": "NO_REQUESTER"}
    assert ledger.get("run1", "docs/a.txt")["status"] == L.VERIFIED


def test_separation_can_be_switched_off(aws, ledger, monkeypatch):
    monkeypatch.setenv("REQUIRE_SEPARATE_APPROVER", "false")
    _put_verified(aws, ledger)
    out = approval.approve(RuntimeConfig.from_env(), _event(aws, approver=STARTER), ledger=ledger)
    assert out["approved"] is True


@pytest.mark.parametrize("approver", [None, "", "  ", 7])
def test_an_approval_without_an_approver_is_refused(aws, ledger, approver):
    _put_verified(aws, ledger)
    out = approval.approve(RuntimeConfig.from_env(), _event(aws, approver=approver), ledger=ledger)
    assert out["approved"] is False
    assert ledger.get("run1", "docs/a.txt")["status"] == L.VERIFIED


def test_only_verified_items_become_approved(aws, ledger):
    _put_verified(aws, ledger)
    ledger.update("run1", "docs/a.txt", L.CHANGED)
    out = approval.approve(RuntimeConfig.from_env(), _event(aws), ledger=ledger)
    assert out["marked"] == 0 and out["notMarked"] == 1
    assert ledger.get("run1", "docs/a.txt")["status"] == L.CHANGED


def test_approving_then_deleting_end_to_end(aws, ledger):
    _put_verified(aws, ledger)
    approval.approve(RuntimeConfig.from_env(), _event(aws), ledger=ledger)
    result = delete.delete_one(
        run_id="run1", key="docs/a.txt", dry_run=False, claim=CLAIM, helper=S3ApHelper(AP), ledger=ledger
    )
    assert result["outcome"] == "DELETED" and not _exists(aws)
    assert ledger.get("run1", "docs/a.txt")["deletedBy"] == APPROVER


@pytest.mark.parametrize(
    ("a", "b", "same"),
    [
        (STARTER, STARTER, True),
        (STARTER, "ARN:AWS:IAM::123456789012:USER/Starter", True),
        (STARTER, APPROVER, False),
        ("arn:aws:iam::123456789012:role/ops", "arn:aws:sts::123456789012:assumed-role/ops/alice", True),
        ("arn:aws:sts::123456789012:assumed-role/ops/alice", "arn:aws:sts::123456789012:assumed-role/ops/bob", False),
        ("arn:aws:sts::123456789012:assumed-role/ops/alice", "arn:aws:sts::123456789012:assumed-role/ops/alice", True),
        ("arn:aws:iam::123456789012:role/ops", "arn:aws:iam::210987654321:role/ops", False),
        (
            "arn:aws:iam::123456789012:role/aws-reserved/sso.amazonaws.com/AWSReservedSSO_Admin_x",
            "arn:aws:sts::123456789012:assumed-role/AWSReservedSSO_Admin_x/alice",
            True,
        ),
        ("alice", "Alice", True),
        ("alice", "bob", False),
    ],
)
def test_same_principal(a, b, same):
    assert same_principal(a, b) is same


# ---- reconcile ---------------------------------------------------------------------------------


class _Sfn:
    def __init__(self, status="SUCCEEDED"):
        self.status = status

    def describe_execution(self, executionArn):
        return {"status": self.status}


def _reconcile(ledger, sfn=None):
    return delete.reconcile(run_id="run1", helper=S3ApHelper(AP), ledger=ledger, sfn=sfn or _Sfn())


def _stuck(aws, ledger, status, key="docs/a.txt"):
    _put_verified(aws, ledger, key=key)
    ledger.put(
        "run1",
        key,
        status,
        size=5,
        etag=aws.head_object(Bucket=AP, Key=key)["ETag"],
        approvedBy=APPROVER,
        approvedAt="x",
        claimedBy=CLAIM,
        approvalExecutionArn=CLAIM,
    )


def test_reconcile_records_a_delete_that_happened(aws, ledger):
    _stuck(aws, ledger, L.DELETING)
    aws.delete_object(Bucket=AP, Key="docs/a.txt")
    assert _reconcile(ledger)["deleted"] == 1
    item = ledger.get("run1", "docs/a.txt")
    assert item["status"] == L.DELETED and item["deletedBy"] == APPROVER and item["reconciled"] is True


@pytest.mark.parametrize("status", [L.DELETING, L.APPROVED])
def test_reconcile_sends_an_unchanged_file_back_for_a_new_approval(aws, ledger, status):
    _stuck(aws, ledger, status)
    assert _reconcile(ledger)["reverified"] == 1
    assert ledger.get("run1", "docs/a.txt")["status"] == L.VERIFIED
    assert _exists(aws)


def test_reconcile_marks_a_rewritten_file_changed(aws, ledger):
    _stuck(aws, ledger, L.DELETING)
    aws.put_object(Bucket=AP, Key="docs/a.txt", Body=b"a different, longer body")
    assert _reconcile(ledger)["changed"] == 1
    assert ledger.get("run1", "docs/a.txt")["status"] == L.CHANGED


def test_reconcile_leaves_items_of_a_running_execution_alone(aws, ledger):
    _stuck(aws, ledger, L.DELETING)
    aws.delete_object(Bucket=AP, Key="docs/a.txt")
    assert _reconcile(ledger, _Sfn("RUNNING"))["running"] == 1
    assert ledger.get("run1", "docs/a.txt")["status"] == L.DELETING


# ---- what the approver is told --------------------------------------------------------------------


def test_the_request_says_when_there_is_only_one_copy_and_when_files_cannot_be_restored(aws, monkeypatch):
    cfg = RuntimeConfig.from_env()
    text = approval.approval_message(
        cfg,
        "run1",
        {"count": 3, "totalBytes": 9, "manifestKey": "m", "oversizeFiles": 2},
        dry_run=False,
        execution_arn="arn:x",
        requested_by=STARTER,
    )
    assert "COPIES: ONE" in text and "only copy" in text
    assert "2 file(s) exceed the Access Point upload limit" in text
    assert f"Started by: {STARTER}" in text and "refused" in text
    monkeypatch.setenv("SECOND_COPY_BUCKET", "second")
    again = approval.approval_message(
        RuntimeConfig.from_env(),
        "run1",
        {"count": 1, "totalBytes": 1, "manifestKey": "m"},
        dry_run=True,
        execution_arn="arn:x",
    )
    assert "COPIES: ONE" not in again and "Second copy: s3://second/" in again and "Started by" not in again
