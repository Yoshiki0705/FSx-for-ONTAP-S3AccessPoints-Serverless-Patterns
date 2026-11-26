"""Restore helpers, the ONTAP REST function, and the Fargate entrypoint."""

from __future__ import annotations

import json
import shlex

import pytest
from avd_support import AP, ARCHIVE, SECOND, load_fargate_entrypoint, load_handler
from hypothesis import given, settings
from hypothesis import strategies as st

from shared.archive_verify import ledger as L
from shared.archive_verify.checksums import CRC64NVME, hash_stream
from shared.exceptions import InvalidInput
from shared.s3ap_helper import S3ApHelper

restore = load_handler("restore")
ontap = load_handler("ontap_rest")
entry = load_fargate_entrypoint()


# ---------------------------------------------------------------- restore


def test_restore_input_needs_exactly_one_of_keys_or_prefix():
    ok = restore.validate_restore_input({"runId": "r1", "keys": ["a"]}, "e1")
    assert ok["tier"] == "Bulk" and ok["days"] == 7 and ok["restoreRunId"] == "e1"
    for bad in ({"runId": "r1"}, {"runId": "r1", "keys": ["a"], "prefix": "p"}):
        with pytest.raises(InvalidInput):
            restore.validate_restore_input(bad, "e1")


@pytest.mark.parametrize(
    "extra", [{"tier": "Fast"}, {"days": 0}, {"days": True}, {"days": 400}, {"keys": "a"}, {"keys": [1]}]
)
def test_restore_input_rejections(extra):
    with pytest.raises(InvalidInput):
        restore.validate_restore_input({"runId": "r1", "keys": ["a"], **extra}, "e1")


def _deleted(ledger, key, **extra):
    ledger.put(
        "r1",
        key,
        L.DELETED,
        size=3,
        isLarge=False,
        storageClass="DEEP_ARCHIVE",
        archiveBucket=ARCHIVE,
        archiveKey=f"data/{key}",
        **extra,
    )


def test_select_items_takes_only_deleted_files(ledger):
    _deleted(ledger, "docs/a")
    _deleted(ledger, "docs/b")
    _deleted(ledger, "img/c")
    ledger.put("r1", "docs/live", L.VERIFIED, size=1)
    by_prefix = restore.select_items(ledger, {"runId": "r1", "prefix": "docs/", "keys": []})
    assert sorted(i["key"] for i in by_prefix) == ["docs/a", "docs/b"]
    by_keys = restore.select_items(ledger, {"runId": "r1", "prefix": "", "keys": ["img/c", "docs/live"]})
    assert [i["key"] for i in by_keys] == ["img/c"]


def test_restore_state_from_the_head_header():
    ongoing = {"Restore": 'ongoing-request="true"'}
    done = {"Restore": 'ongoing-request="false", expiry-date="Fri, 21 Dec 2012 00:00:00 GMT"'}
    assert restore.restore_state(ongoing, "DEEP_ARCHIVE") == "WAITING"
    assert restore.restore_state(done, "GLACIER") == "READY"
    assert restore.restore_state({}, "DEEP_ARCHIVE") == "NOT_REQUESTED"
    assert restore.restore_state({}, "GLACIER_IR") == "READY"


def test_check_times_out_after_the_attempt_budget(lambda_context):
    waiting = {"Restore": 'ongoing-request="true"'}
    args = {"action": "check", "head": waiting, "storageClass": "GLACIER", "maxAttempts": 2}
    assert restore.handler({**args, "attempt": 0}, lambda_context) == {"state": "WAITING", "attempt": 1}
    assert restore.handler({**args, "attempt": 1}, lambda_context)["state"] == "WAITING"
    assert restore.handler({**args, "attempt": 2}, lambda_context)["state"] == "TIMEOUT"


def test_prepare_reports_existing_files_so_they_are_never_overwritten(aws, lambda_context):
    aws.put_object(Bucket=AP, Key="docs/a", Body=b"live")
    item = {"key": "docs/a", "storageClass": "DEEP_ARCHIVE", "archiveBucket": ARCHIVE, "archiveKey": "data/docs/a"}
    assert restore.handler({"action": "prepare", "item": item}, lambda_context) == {"exists": True}


def test_prepare_builds_the_copy_back(aws, lambda_context):
    item = {"key": "docs/ü", "storageClass": "GLACIER_IR", "archiveBucket": ARCHIVE, "archiveKey": "data/docs/ü"}
    out = restore.handler({"action": "prepare", "item": item}, lambda_context)
    assert out["exists"] is False and out["needsRestore"] is False
    assert out["copy"] == {"bucket": AP, "key": "docs/ü", "copySource": f"{ARCHIVE}/data/docs/%C3%BC"}
    assert (
        restore.handler({"action": "prepare", "item": {**item, "storageClass": "GLACIER"}}, lambda_context)[
            "needsRestore"
        ]
        is True
    )


def test_finalize_marks_restored_only_from_deleted(ledger, lambda_context):
    _deleted(ledger, "a")
    ledger.put("r1", "live", L.VERIFIED, size=1)
    args = {"action": "finalize", "runId": "r1", "restoreRunId": "rr1"}
    restore.handler({**args, "key": "a"}, lambda_context)
    restore.handler({**args, "key": "live"}, lambda_context)
    assert ledger.get("r1", "a")["status"] == L.RESTORED
    assert ledger.get("r1", "live")["status"] == L.VERIFIED


def test_reapply_script_restores_attributes():
    items = [
        {
            "key": "docs/a b.txt",
            "attrs": {"uid": 1234, "gid": 5678, "mode": "640", "mtime": "2020-01-02T03:04:05+00:00"},
        }
    ]
    script = restore.reapply_script("r1", items)
    assert script.startswith("#!/bin/sh")
    assert "chown 1234:5678 -- \"$MOUNT_ROOT\"/'docs/a b.txt'" in script
    assert "chmod 640 -- " in script
    assert "touch -d 2020-01-02T03:04:05+00:00 -- " in script or "touch -d '2020-01-02T03:04:05+00:00' -- " in script


def test_reapply_script_never_runs_a_value_from_the_ledger():
    hostile = [
        {"key": "x; rm -rf /", "attrs": {"uid": "1; reboot", "gid": 1, "mode": "644; id", "mtime": "$(id)"}},
        {"key": "../escape", "attrs": {"uid": 1, "gid": 1}},
        {"key": "/abs", "attrs": {"uid": 1, "gid": 1}},
    ]
    script = restore.reapply_script("r1", hostile)
    commands = [
        ln
        for ln in script.splitlines()
        if ln and not ln.startswith("#") and "MOUNT_ROOT:?" not in ln and ln != "set -eu"
    ]
    assert commands == []
    assert "skipped (unsafe key)" in script


@settings(max_examples=100, deadline=None)
@given(key=st.text(min_size=1, max_size=30))
def test_any_key_becomes_one_shell_word_and_never_a_command(key):
    """Parse the whole script as sh would: the only commands are chown/chmod/touch with one path word."""
    script = restore.reapply_script(
        "r1", [{"key": key, "attrs": {"uid": 1, "gid": 2, "mode": "644", "mtime": "2020-01-01T00:00:00+00:00"}}]
    )
    words = shlex.split(script, comments=True)
    # Header: set -eu, then the ': "${MOUNT_ROOT:?...}"' guard.
    assert words[:2] == ["set", "-eu"]
    commands = [w for w in words if w in ("chown", "chmod", "touch")]
    if ".." in key.split("/") or key.startswith("/"):
        assert commands == []
        return
    assert commands == ["chown", "chmod", "touch"]
    assert words.count("--") == 3
    assert [w for w in words if w == f"$MOUNT_ROOT/{key}"] == [f"$MOUNT_ROOT/{key}"] * 3


def test_a_newline_in_a_skipped_key_cannot_end_the_comment():
    script = restore.reapply_script("r1", [{"key": "../x\nrm -rf ~", "attrs": {"uid": 1, "gid": 2}}])
    assert "rm -rf" not in [ln.split()[0] for ln in script.splitlines() if ln.split()]


def test_reapply_action_writes_the_script_for_this_restore_only(aws, ledger, lambda_context):
    _deleted(ledger, "a", attrs={"uid": 1, "gid": 2, "mode": "600"})
    _deleted(ledger, "b", attrs={"uid": 1, "gid": 2, "mode": "600"})
    for k, rr in (("a", "rr1"), ("b", "other")):
        ledger.update("r1", k, L.RESTORED, restoreRunId=rr)
    out = restore.handler({"action": "reapply", "runId": "r1", "restoreRunId": "rr1"}, lambda_context)
    body = aws.get_object(Bucket=ARCHIVE, Key=out["scriptKey"])["Body"].read().decode()
    assert out["files"] == 1 and '"$MOUNT_ROOT"/a' in body and '"$MOUNT_ROOT"/b' not in body


def test_restore_select_writes_items(aws, ledger, lambda_context):
    _deleted(ledger, "docs/a")
    out = restore.handler(
        {"action": "select", "input": {"runId": "r1", "prefix": "docs/"}, "executionName": "rr1"}, lambda_context
    )
    assert out["count"] == 1 and out["restoreRunId"] == "rr1" and out["pollSeconds"] == 1800
    assert json.loads(aws.get_object(Bucket=ARCHIVE, Key=out["itemsKey"])["Body"].read())[0]["key"] == "docs/a"


# ---------------------------------------------------------------- ONTAP REST function


class FakeOntap:
    def __init__(self, tree):
        self.tree = tree

    def list_directory(self, volume_uuid, path, **kw):
        return self.tree.get(path, [])


def _entry(name, kind, atime="2019-01-01T00:00:00+00:00"):
    return {
        "name": name,
        "type": kind,
        "accessed_time": atime,
        "owner_id": 1,
        "group_id": 2,
        "unix_permissions": 644,
        "modified_time": "2018-01-01T00:00:00+00:00",
    }


def test_walk_finds_old_files_recursively_with_attributes():
    tree = {
        "": [
            _entry("a.txt", "file"),
            _entry("sub", "directory"),
            _entry("new.txt", "file", "2999-01-01T00:00:00+00:00"),
        ],
        "sub": [_entry("b.txt", "file"), _entry(".", "directory")],
    }
    found, truncated = ontap.walk_candidates(FakeOntap(tree), "vol", "", 30, 1000)
    assert sorted(f["path"] for f in found) == ["a.txt", "sub/b.txt"]
    assert not truncated and found[0]["attrs"]["uid"] == 1 and found[0]["attrs"]["mode"] == 644


def test_walk_stops_at_the_scan_limit_and_says_so():
    tree = {"": [_entry(f"f{i}", "file") for i in range(10)]}
    found, truncated = ontap.walk_candidates(FakeOntap(tree), "vol", "", 30, 5)
    assert truncated and len(found) == 5


def test_attrs_from_entry_names():
    assert ontap.attrs_from_entry(_entry("x", "file")) == {
        "uid": 1,
        "gid": 2,
        "mode": 644,
        "mtime": "2018-01-01T00:00:00+00:00",
        "atime": "2019-01-01T00:00:00+00:00",
    }


# ---------------------------------------------------------------- Fargate entrypoint


def _task(aws, key="big.bin", body=b"0123456789abcdef" * (1024 * 1024)):  # 16 MiB
    put = aws.put_object(Bucket=AP, Key=key, Body=body)
    item = {"key": key, "size": len(body), "etag": put["ETag"], "lastModified": "2020-01-01T00:00:00+00:00"}
    copy = {
        "bucket": ARCHIVE,
        "key": f"data/{key}",
        "ifMatch": put["ETag"],
        "storageClass": "STANDARD",
        "contentType": "application/octet-stream",
        "metadata": {"source-key": key},
    }
    return body, {"runId": "r1", "item": item, "copy": copy}


def test_entrypoint_archive_hashes_copies_and_updates_the_ledger(aws, ledger, monkeypatch):
    monkeypatch.setattr(entry, "PART_SIZE", 5 * 1024 * 1024)
    body, task = _task(aws)
    ledger.put("r1", "big.bin", L.RECORDED, size=len(body), etag=task["item"]["etag"], isLarge=True)
    assert entry.run_archive(task, S3ApHelper(AP), ledger) == entry.EXIT_OK
    stored = ledger.get("r1", "big.bin")
    expected = hash_stream([body])
    assert stored["status"] == L.COPIED and stored["crc64nvme"] == expected.crc64nvme_b64
    assert stored["sha256"] == expected.sha256_hex
    assert aws.get_object(Bucket=ARCHIVE, Key="data/big.bin")["Body"].read() == body


def test_entrypoint_exits_changed_when_the_source_moved(aws, ledger):
    body, task = _task(aws)
    aws.put_object(Bucket=AP, Key="big.bin", Body=b"rewritten")
    ledger.put("r1", "big.bin", L.RECORDED, size=len(body), etag=task["item"]["etag"], isLarge=True)
    assert entry.run_archive(task, S3ApHelper(AP), ledger) == entry.EXIT_CHANGED
    assert ledger.get("r1", "big.bin")["status"] == L.CHANGED
    assert "Contents" not in aws.list_objects_v2(Bucket=ARCHIVE)


def test_entrypoint_second_copy_goes_to_the_second_bucket(aws, ledger, monkeypatch):
    monkeypatch.setattr(entry, "PART_SIZE", 5 * 1024 * 1024)
    body, task = _task(aws)
    task["secondCopy"] = {**task["copy"], "bucket": SECOND}
    assert entry.run_second(task, S3ApHelper(AP), ledger) == entry.EXIT_OK
    assert aws.get_object(Bucket=SECOND, Key="data/big.bin")["Body"].read() == body


def test_entrypoint_restore_copies_back(aws, ledger, monkeypatch):
    monkeypatch.setattr(entry, "PART_SIZE", 5 * 1024 * 1024)
    body = b"z" * (11 * 1024 * 1024)
    aws.put_object(Bucket=ARCHIVE, Key="data/r.bin", Body=body)
    task = {"copy": {"copySource": f"{ARCHIVE}/data/r.bin", "key": "r.bin"}}
    assert entry.run_restore(task, S3ApHelper(AP), ledger) == entry.EXIT_OK
    assert aws.get_object(Bucket=AP, Key="r.bin")["Body"].read() == body


def test_entrypoint_main_bad_input(monkeypatch):
    monkeypatch.delenv("TASK_MODE", raising=False)
    assert entry.main() == entry.EXIT_BAD_INPUT
    monkeypatch.setenv("TASK_MODE", "archive")
    monkeypatch.setenv("TASK_INPUT", "{not json")
    assert entry.main() == entry.EXIT_BAD_INPUT


def test_entrypoint_uses_crc64nvme_for_multipart():
    assert (
        entry._extra_args(
            {"ifMatch": "e", "storageClass": "GLACIER", "contentType": "x", "metadata": {}}, with_checksum=True
        )["ChecksumAlgorithm"]
        == CRC64NVME
    )
