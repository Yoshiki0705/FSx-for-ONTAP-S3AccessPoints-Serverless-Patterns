"""The delete gate. These are the tests that matter most in this pattern."""

from __future__ import annotations

import pytest
from avd_support import AP, load_handler
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from shared.archive_verify import ledger as L
from shared.exceptions import InvalidInput
from shared.s3ap_helper import S3ApHelper

delete = load_handler("delete")


def _seed(aws, ledger, key="docs/a.txt", body=b"hello", **over):
    """Put a file on the 'Access Point' and a VERIFIED ledger item matching it."""
    put = aws.put_object(Bucket=AP, Key=key, Body=body)
    item = {
        "size": len(body),
        "etag": put["ETag"],
        "archiveBucket": "archive-bucket",
        "archiveKey": f"data/{key}",
        "secondCopyRequired": False,
    }
    item.update(over)
    ledger.put("run1", key, L.VERIFIED, **item)
    return put["ETag"]


def _delete(ledger, key="docs/a.txt", dry_run=False, approved_by="arn:aws:iam::123456789012:user/approver"):
    return delete.delete_one(
        run_id="run1",
        key=key,
        dry_run=dry_run,
        approved_by=approved_by,
        helper=S3ApHelper(AP),
        ledger=ledger,
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
    assert item["deletedBy"] == "arn:aws:iam::123456789012:user/approver"


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
    assert ledger.get("run1", "docs/a.txt")["status"] == L.VERIFIED


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


@pytest.mark.parametrize("status", [L.RECORDED, L.COPIED, L.MISMATCH, L.CHANGED, L.FAILED, L.DELETED])
def test_only_verified_items_are_deleted(aws, ledger, status):
    etag = _seed(aws, ledger)
    ledger.put("run1", "docs/a.txt", status, size=5, etag=etag)
    assert _delete(ledger)["outcome"] == "NOT_VERIFIED"
    assert _exists(aws)


def test_unknown_item_is_not_deleted(aws, ledger):
    aws.put_object(Bucket=AP, Key="docs/a.txt", Body=b"hello")
    assert _delete(ledger)["outcome"] == "NOT_VERIFIED"
    assert _exists(aws)


def test_second_copy_required_but_unverified_blocks_delete(aws, ledger):
    _seed(aws, ledger, secondCopyRequired=True)
    assert _delete(ledger)["outcome"] == "NOT_VERIFIED"
    assert _exists(aws)


def test_second_copy_verified_allows_delete(aws, ledger):
    _seed(aws, ledger, secondCopyRequired=True, secondCopy=L.VERIFIED)
    assert _delete(ledger)["outcome"] == "DELETED"


@pytest.mark.parametrize("approver", [None, "", 5])
def test_no_approver_no_delete(aws, ledger, approver):
    _seed(aws, ledger)
    with pytest.raises(InvalidInput):
        _delete(ledger, approved_by=approver)
    assert _exists(aws)


def test_file_already_gone_is_reported_changed(aws, ledger):
    _seed(aws, ledger)
    aws.delete_object(Bucket=AP, Key="docs/a.txt")
    assert _delete(ledger)["outcome"] == "CHANGED"


def test_second_delete_of_same_item_is_a_no_op(aws, ledger):
    _seed(aws, ledger)
    assert _delete(ledger)["outcome"] == "DELETED"
    assert _delete(ledger)["outcome"] == "NOT_VERIFIED"


def test_failed_delete_returns_item_to_verified(aws, ledger):
    _seed(aws, ledger)

    class Boom(S3ApHelper):
        def delete_object(self, key):
            raise RuntimeError("transient")

    with pytest.raises(RuntimeError):
        delete.delete_one(
            run_id="run1",
            key="docs/a.txt",
            dry_run=False,
            approved_by="arn:aws:iam::123456789012:user/a",
            helper=Boom(AP),
            ledger=ledger,
        )
    assert ledger.get("run1", "docs/a.txt")["status"] == L.VERIFIED
    assert _delete(ledger)["outcome"] == "DELETED"  # a Step Functions retry succeeds


def test_handler_wiring(aws, ledger, lambda_context):
    _seed(aws, ledger)
    out = delete.handler({"runId": "run1", "key": "docs/a.txt", "dryRun": True, "approvedBy": "x"}, lambda_context)
    assert out["outcome"] == "DRY_RUN"
