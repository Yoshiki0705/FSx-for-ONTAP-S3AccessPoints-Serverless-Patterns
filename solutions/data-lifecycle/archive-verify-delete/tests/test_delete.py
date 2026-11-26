"""The delete gate. These are the tests that matter most in this pattern."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from avd_support import AP, load_handler
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from shared.archive_verify import ledger as L
from shared.exceptions import InvalidInput
from shared.s3ap_helper import S3ApHelper

delete = load_handler("delete")


APPROVER = "arn:aws:iam::123456789012:user/approver"
CLAIM = "arn:aws:states:ap-northeast-1:123456789012:execution:avd-archive:exec-1"


def _seed(aws, ledger, key="docs/a.txt", body=b"hello", **over):
    """Put a file on the 'Access Point' and a VERIFIED ledger item matching it."""
    put = aws.put_object(Bucket=AP, Key=key, Body=body)
    item = {
        "size": len(body),
        "etag": put["ETag"],
        "archiveBucket": "archive-bucket",
        "archiveKey": f"data/run1/{key}",
        "secondCopyRequired": False,
        "approvedBy": APPROVER,
        "approvedAt": L.now_iso(),
        "approvalExecutionArn": CLAIM,
    }
    item.update(over)
    ledger.put("run1", key, L.APPROVED, **item)
    return put["ETag"]


def _delete(ledger, key="docs/a.txt", dry_run=False, claim=CLAIM, helper=None, **extra):
    return delete.delete_one(
        run_id="run1",
        key=key,
        dry_run=dry_run,
        claim=claim,
        helper=helper or S3ApHelper(AP),
        ledger=ledger,
        **extra,
    )


def _exists(aws, key="docs/a.txt"):
    return "Contents" in aws.list_objects_v2(Bucket=AP, Prefix=key)


def test_deletes_a_verified_unchanged_file(aws, ledger):
    _seed(aws, ledger)
    result = _delete(ledger)
    assert result["outcome"] == "DELETED"
    assert not _exists(aws)
    item = ledger.get("run1", "docs/a.txt")
    assert item["status"] == L.DELETED
    assert item["deletedBy"] == APPROVER  # taken from the ledger, not from the call


def test_does_not_delete_when_etag_changed(aws, ledger):
    """The file was rewritten after the ledger recorded it: the copy no longer represents it."""
    _seed(aws, ledger, body=b"original")
    aws.put_object(Bucket=AP, Key="docs/a.txt", Body=b"rewritten after verification")
    result = _delete(ledger)
    assert result["outcome"] == "CHANGED"
    assert _exists(aws), "a changed file must stay on the Access Point"
    assert ledger.get("run1", "docs/a.txt")["status"] == L.CHANGED


def test_does_not_delete_when_size_differs_but_etag_equal(aws, ledger):
    _seed(aws, ledger, size=999)  # ledger says 999 bytes, the file has 5
    assert _delete(ledger)["outcome"] == "CHANGED"
    assert _exists(aws)


def test_dry_run_true_never_deletes(aws, ledger):
    _seed(aws, ledger)
    assert _delete(ledger, dry_run=True)["outcome"] == "DRY_RUN"
    assert _exists(aws)
    assert ledger.get("run1", "docs/a.txt")["status"] == L.APPROVED


@pytest.mark.parametrize("value", ["false", "False", "no", 0, 1, "", [], {}])
def test_dry_run_that_is_not_a_boolean_is_rejected_not_interpreted(aws, ledger, value):
    _seed(aws, ledger)
    with pytest.raises(InvalidInput):
        _delete(ledger, dry_run=value)
    assert _exists(aws)


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(value=st.one_of(st.none(), st.just(True), st.text(), st.integers(), st.lists(st.integers())))
def test_only_the_boolean_false_can_reach_a_delete(aws, ledger, value):
    _seed(aws, ledger)
    try:
        result = _delete(ledger, dry_run=value)
    except InvalidInput:
        pass
    else:
        assert result["outcome"] == "DRY_RUN"
    assert _exists(aws)
    aws.put_object(Bucket=AP, Key="docs/a.txt", Body=b"hello")  # reset for the next example


@pytest.mark.parametrize(
    "status", [L.SELECTED, L.RECORDED, L.COPIED, L.VERIFIED, L.MISMATCH, L.CHANGED, L.FAILED, L.DELETED]
)
def test_only_approved_items_are_deleted(aws, ledger, status):
    etag = _seed(aws, ledger)
    ledger.put("run1", "docs/a.txt", status, size=5, etag=etag, approvedBy=APPROVER, approvedAt="x")
    assert _delete(ledger)["outcome"] == "NOT_APPROVED"
    assert _exists(aws)


def test_unknown_item_is_not_deleted(aws, ledger):
    aws.put_object(Bucket=AP, Key="docs/a.txt", Body=b"hello")
    assert _delete(ledger)["outcome"] == "NOT_APPROVED"
    assert _exists(aws)


def test_an_approved_row_without_an_approver_record_is_not_deleted(aws, ledger):
    _seed(aws, ledger, approvedBy="")
    assert _delete(ledger)["outcome"] == "NOT_APPROVED"
    assert _exists(aws)


def test_second_copy_required_but_unverified_blocks_delete(aws, ledger):
    _seed(aws, ledger, secondCopyRequired=True)
    assert _delete(ledger)["outcome"] == "NOT_VERIFIED"
    assert _exists(aws)


def test_second_copy_verified_allows_delete(aws, ledger):
    _seed(aws, ledger, secondCopyRequired=True, secondCopy=L.VERIFIED)
    assert _delete(ledger)["outcome"] == "DELETED"


@pytest.mark.parametrize("claim", [None, "", 5])
def test_no_claim_no_delete(aws, ledger, claim):
    _seed(aws, ledger)
    with pytest.raises(InvalidInput):
        _delete(ledger, claim=claim)
    assert _exists(aws)


def test_file_already_gone_is_reported_changed(aws, ledger):
    _seed(aws, ledger)
    aws.delete_object(Bucket=AP, Key="docs/a.txt")
    assert _delete(ledger)["outcome"] == "CHANGED"


def test_second_delete_of_same_item_is_a_no_op(aws, ledger):
    _seed(aws, ledger)
    assert _delete(ledger)["outcome"] == "DELETED"
    assert _delete(ledger)["outcome"] == "NOT_APPROVED"


def test_failed_delete_leaves_the_claim_and_the_retry_finishes(aws, ledger):
    """Whether the file is gone is unknown after an error, so the item keeps its claim."""
    _seed(aws, ledger)

    class Boom(S3ApHelper):
        def delete_object(self, key):
            raise RuntimeError("transient")

    with pytest.raises(RuntimeError):
        _delete(ledger, helper=Boom(AP))
    item = ledger.get("run1", "docs/a.txt")
    assert item["status"] == L.DELETING and item["claimedBy"] == CLAIM
    assert _delete(ledger)["outcome"] == "DELETED"  # the same execution's retry succeeds


def test_retry_after_the_file_was_deleted_but_the_ledger_write_failed_records_deleted(aws, ledger):
    """The case where DeleteObject succeeded and the client saw an error: not CHANGED, but DELETED."""
    _seed(aws, ledger)

    class DeletesThenFails(S3ApHelper):
        def delete_object(self, key):
            super().delete_object(key)
            raise TimeoutError("read timed out after the server deleted the object")

    with pytest.raises(TimeoutError):
        _delete(ledger, helper=DeletesThenFails(AP))
    assert not _exists(aws)
    assert ledger.get("run1", "docs/a.txt")["status"] == L.DELETING
    result = _delete(ledger)
    assert result["outcome"] == "DELETED" and result["note"] == "already gone on retry"
    assert ledger.get("run1", "docs/a.txt")["status"] == L.DELETED


def test_another_execution_cannot_finish_someone_elses_claim(aws, ledger):
    _seed(aws, ledger, claimedBy=CLAIM)
    ledger.update("run1", "docs/a.txt", L.DELETING, only_if_status=L.APPROVED)
    assert (
        _delete(ledger, claim="arn:aws:states:ap-northeast-1:123456789012:execution:avd-archive:other")["outcome"]
        == "NOT_APPROVED"
    )
    assert _exists(aws)


def test_handler_wiring(aws, ledger, lambda_context):
    _seed(aws, ledger)
    out = delete.handler({"runId": "run1", "key": "docs/a.txt", "dryRun": True, "claim": CLAIM}, lambda_context)
    assert out["outcome"] == "DRY_RUN"


OTHER = "arn:aws:states:ap-northeast-1:123456789012:execution:avd-archive:stopped-earlier"


def test_an_approval_belongs_to_the_execution_that_recorded_it(aws, ledger):
    """An APPROVED item left by a stopped execution must not be consumed by a call that names another one."""
    _seed(aws, ledger, approvalExecutionArn=OTHER)
    result = _delete(ledger)  # claim is CLAIM, the approval was recorded by OTHER
    assert result["outcome"] == "NOT_APPROVED"
    assert _exists(aws)
    assert ledger.get("run1", "docs/a.txt")["status"] == L.APPROVED


def test_an_approval_without_an_execution_is_not_consumed(aws, ledger):
    _seed(aws, ledger, approvalExecutionArn="")
    assert _delete(ledger)["outcome"] == "NOT_APPROVED"
    assert _exists(aws)


def test_an_approval_older_than_the_validity_window_is_not_consumed(aws, ledger):
    old = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    _seed(aws, ledger, approvedAt=old)
    result = _delete(ledger)  # default validity is 24 hours
    assert result["outcome"] == "NOT_APPROVED"
    assert _exists(aws)


def test_an_approval_inside_the_validity_window_is_consumed(aws, ledger):
    recent = (datetime.now(timezone.utc) - timedelta(hours=23)).isoformat()
    _seed(aws, ledger, approvedAt=recent)
    assert _delete(ledger)["outcome"] == "DELETED"


def test_the_validity_window_is_a_parameter(aws, ledger):
    two_hours = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    _seed(aws, ledger, approvedAt=two_hours)
    assert _delete(ledger, approval_validity_hours=1)["outcome"] == "NOT_APPROVED"
    assert _delete(ledger, approval_validity_hours=3)["outcome"] == "DELETED"


@pytest.mark.parametrize("stamp", ["x", "", "2026-13-45", None])
def test_an_unreadable_approval_time_is_not_consumed(aws, ledger, stamp):
    _seed(aws, ledger, approvedAt=stamp or "x")
    if stamp is None:
        ledger.update("run1", "docs/a.txt", L.APPROVED, only_if_status=L.APPROVED, approvedAt="")
    assert _delete(ledger)["outcome"] == "NOT_APPROVED"
    assert _exists(aws)


def test_handler_reads_the_validity_from_the_environment(aws, ledger, lambda_context, monkeypatch):
    monkeypatch.setenv("APPROVAL_VALIDITY_HOURS", "1")
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    _seed(aws, ledger, approvedAt=old)
    out = delete.handler({"runId": "run1", "key": "docs/a.txt", "dryRun": False, "claim": CLAIM}, lambda_context)
    assert out["outcome"] == "NOT_APPROVED"
    assert _exists(aws)
