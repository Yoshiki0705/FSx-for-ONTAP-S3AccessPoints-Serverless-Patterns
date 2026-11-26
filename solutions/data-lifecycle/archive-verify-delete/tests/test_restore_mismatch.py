"""Re-restoring a file whose restored copy failed verification (RESTORE_MISMATCH).

The restore never overwrites a file that is already on the Access Point. A file in RESTORE_MISMATCH
is the exception: its existing copy is the one that is wrong. Overwriting is allowed only when the
start input says ``retryMismatched: true``, and only for a ledger item that is in RESTORE_MISMATCH
in the run the request names.
"""

from __future__ import annotations

import pytest
from avd_support import AP, ARCHIVE, load_handler

from shared.archive_verify import ledger as L
from shared.archive_verify.checksums import hash_stream
from shared.exceptions import InvalidInput
from shared.s3ap_helper import S3ApHelper

restore = load_handler("restore")

GOOD = b"the original bytes"


def _digest(body: bytes):
    return hash_stream(iter([body]))


def _mismatch(aws, ledger, key="docs/a", status=L.RESTORE_MISMATCH, on_ap=b"corrupted copy"):
    d = _digest(GOOD)
    aws.put_object(Bucket=ARCHIVE, Key=f"data/{key}", Body=GOOD)
    aws.put_object(Bucket=AP, Key=key, Body=on_ap)
    ledger.put(
        "r1",
        key,
        status,
        size=len(GOOD),
        sha256=d.sha256_hex,
        crc64nvme=d.crc64nvme_b64,
        isLarge=False,
        storageClass="GLACIER_IR",
        archiveBucket=ARCHIVE,
        archiveKey=f"data/{key}",
        restoreRunId="rr1",
    )


def _req(**over):
    return {"runId": "r1", "prefix": "", "keys": [], "retryMismatched": False, **over}


def test_the_flag_defaults_to_false():
    assert restore.validate_restore_input({"runId": "r1", "keys": ["a"]}, "e1")["retryMismatched"] is False


@pytest.mark.parametrize("value", ["true", "True", 1, 0, "", None, [], {}])
def test_the_flag_must_be_a_json_boolean(value):
    with pytest.raises(InvalidInput):
        restore.validate_restore_input({"runId": "r1", "keys": ["a"], "retryMismatched": value}, "e1")


def test_a_mismatched_item_is_not_selected_without_the_flag(aws, ledger):
    _mismatch(aws, ledger)
    assert restore.select_items(ledger, _req()) == []


def test_with_the_flag_a_mismatched_item_is_selected_and_marked_for_overwrite(aws, ledger):
    _mismatch(aws, ledger)
    selected = restore.select_items(ledger, _req(retryMismatched=True))
    assert [(i["key"], i.get("overwrite")) for i in selected] == [("docs/a", True)]


def test_with_the_flag_a_mismatched_item_without_its_archive_copy_is_not_selected(aws, ledger):
    _mismatch(aws, ledger)
    aws.delete_object(Bucket=ARCHIVE, Key="data/docs/a")
    assert restore.select_items(ledger, _req(retryMismatched=True)) == []


def test_the_flag_does_not_widen_the_selection_to_other_statuses(aws, ledger):
    _mismatch(aws, ledger, key="docs/ok", status=L.RESTORE_VERIFIED)
    _mismatch(aws, ledger, key="docs/live", status=L.VERIFIED)
    assert restore.select_items(ledger, _req(retryMismatched=True)) == []


def test_a_mismatch_of_another_run_is_not_selected(aws, ledger):
    _mismatch(aws, ledger)
    assert restore.select_items(ledger, _req(runId="other", retryMismatched=True)) == []


def _prepare(lambda_context, key="docs/a", run_id="r1", **item_over):
    item = {
        "key": key,
        "storageClass": "GLACIER_IR",
        "archiveBucket": ARCHIVE,
        "archiveKey": f"data/{key}",
        **item_over,
    }
    return restore.handler({"action": "prepare", "runId": run_id, "item": item}, lambda_context)


def test_prepare_lets_a_flagged_mismatch_overwrite_the_existing_copy(aws, ledger, lambda_context):
    _mismatch(aws, ledger)
    out = _prepare(lambda_context, overwrite=True)
    assert out["exists"] is False and out["copy"]["key"] == "docs/a"


def test_prepare_still_refuses_to_overwrite_without_the_flag(aws, ledger, lambda_context):
    _mismatch(aws, ledger)
    assert _prepare(lambda_context) == {"exists": True}


@pytest.mark.parametrize("status", [L.RESTORE_VERIFIED, L.VERIFIED, L.DELETED, L.RESTORED])
def test_a_forged_overwrite_flag_does_nothing_for_an_item_not_in_mismatch(aws, ledger, lambda_context, status):
    """The flag travels in the item list; the ledger decides."""
    _mismatch(aws, ledger, status=status)
    assert _prepare(lambda_context, overwrite=True) == {"exists": True}


def test_a_forged_overwrite_flag_does_nothing_for_another_run(aws, ledger, lambda_context):
    _mismatch(aws, ledger)
    assert _prepare(lambda_context, run_id="other", overwrite=True) == {"exists": True}


def test_the_whole_path_replaces_the_wrong_copy_and_verifies_it(aws, ledger, lambda_context):
    _mismatch(aws, ledger)
    [item] = restore.select_items(ledger, _req(retryMismatched=True))
    prep = _prepare(lambda_context, **{k: v for k, v in item.items() if k not in ("key",)})
    assert prep["exists"] is False
    aws.copy_object(Bucket=AP, Key="docs/a", CopySource={"Bucket": ARCHIVE, "Key": "data/docs/a"})
    args = {"runId": "r1", "key": "docs/a", "restoreRunId": "rr2"}
    restore.handler({"action": "finalize", **args}, lambda_context)
    assert ledger.get("r1", "docs/a")["status"] == L.RESTORED
    out = restore.handler({"action": "verify", **args}, lambda_context)
    assert out["status"] == L.RESTORE_VERIFIED
    assert ledger.get("r1", "docs/a")["restoreRunId"] == "rr2"
    assert S3ApHelper(AP).head_object("docs/a")["ContentLength"] == len(GOOD)


def test_a_second_mismatch_after_the_retry_is_recorded_again(aws, ledger, lambda_context):
    _mismatch(aws, ledger, on_ap=b"still wrong")
    args = {"runId": "r1", "key": "docs/a", "restoreRunId": "rr2"}
    restore.handler({"action": "finalize", **args}, lambda_context)
    assert restore.handler({"action": "verify", **args}, lambda_context)["status"] == L.RESTORE_MISMATCH
