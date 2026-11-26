"""Selection and recording: what is read, hashed and written to the ledger."""

from __future__ import annotations

import hashlib
import json

import pytest
from avd_support import AP, ARCHIVE, load_handler

from shared.archive_verify import ledger as L
from shared.archive_verify.checksums import crc64_to_b64, crc64nvme_update_pure
from shared.archive_verify.runtime import RuntimeConfig
from shared.exceptions import InvalidConfiguration, InvalidInput
from shared.s3ap_helper import S3ApHelper

select = load_handler("select")
record = load_handler("record")


def _plan(lambda_context, **event):
    return select.handler(
        {"action": "plan", "input": {"olderThanDays": 0, **event}, "executionName": "exec-1"}, lambda_context
    )


def test_plan_returns_safe_defaults_and_config(lambda_context):
    out = _plan(lambda_context)
    assert out["dryRun"] is True and out["storageClass"] == "DEEP_ARCHIVE" and out["runId"] == "exec-1"
    assert out["config"]["archiveBucket"] == ARCHIVE
    assert out["config"]["approvalTimeoutSeconds"] == 72 * 3600
    assert out["config"]["fargateEnabled"] is False


def test_plan_rejects_atime_when_ontap_is_not_deployed(lambda_context):
    with pytest.raises(InvalidConfiguration):
        _plan(lambda_context, selection="ATIME")


def test_unknown_action_is_rejected(lambda_context):
    with pytest.raises(InvalidInput):
        select.handler({"action": "nope"}, lambda_context)


def _list(lambda_context, days, **extra):
    return select.handler(
        {"action": "list", "runId": "r1", "prefix": "docs/", "olderThanDays": days, "maxFiles": 10, **extra},
        lambda_context,
    )


def test_list_selects_old_files_in_prefix_and_writes_the_selection(aws, lambda_context):
    aws.put_object(Bucket=AP, Key="docs/a.txt", Body=b"aaa")
    aws.put_object(Bucket=AP, Key="docs/sub/b.txt", Body=b"bb")
    aws.put_object(Bucket=AP, Key="docs/dir/", Body=b"")
    aws.put_object(Bucket=AP, Key="other/c.txt", Body=b"c")
    out = _list(lambda_context, 0)
    assert out["count"] == 2 and out["totalBytes"] == 5 and out["skippedLarge"] == 0
    items = json.loads(aws.get_object(Bucket=ARCHIVE, Key=out["key"])["Body"].read())
    assert sorted(i["key"] for i in items) == ["docs/a.txt", "docs/sub/b.txt"]
    assert all(i["isLarge"] is False and i["etag"] for i in items)


def test_list_leaves_out_files_newer_than_the_threshold(aws, lambda_context):
    aws.put_object(Bucket=AP, Key="docs/a.txt", Body=b"aaa")
    assert _list(lambda_context, 365)["count"] == 0


def test_list_respects_max_files(aws, lambda_context):
    for i in range(5):
        aws.put_object(Bucket=AP, Key=f"docs/{i}", Body=b"x")
    assert _list(lambda_context, 0, maxFiles=3)["count"] == 3


def test_large_files_are_skipped_and_counted_without_fargate(aws, lambda_context, monkeypatch):
    monkeypatch.setenv("LARGE_FILE_THRESHOLD_BYTES", "4")
    aws.put_object(Bucket=AP, Key="docs/small", Body=b"abc")
    aws.put_object(Bucket=AP, Key="docs/big", Body=b"abcdefgh")
    out = _list(lambda_context, 0)
    assert (out["count"], out["skippedLarge"]) == (1, 1)


def test_large_files_are_kept_when_fargate_is_enabled(aws, lambda_context, monkeypatch):
    monkeypatch.setenv("LARGE_FILE_THRESHOLD_BYTES", "4")
    monkeypatch.setenv("FARGATE_ENABLED", "true")
    aws.put_object(Bucket=AP, Key="docs/big", Body=b"abcdefgh")
    out = _list(lambda_context, 0)
    items = json.loads(aws.get_object(Bucket=ARCHIVE, Key=out["key"])["Body"].read())
    assert items[0]["isLarge"] is True


def test_from_candidates_confirms_each_file_through_the_access_point(aws, lambda_context):
    aws.put_object(Bucket=AP, Key="docs/a.txt", Body=b"aaa")
    candidates = [
        {"key": "docs/a.txt", "attrs": {"uid": 1234, "gid": 5678, "mode": "640", "atime": "2020-01-01T00:00:00+00:00"}},
        {"key": "docs/gone.txt", "attrs": {"uid": 1}},
    ]
    aws.put_object(Bucket=ARCHIVE, Key="manifests/r1-candidates.json", Body=json.dumps(candidates).encode())
    out = select.handler({"action": "from_candidates", "runId": "r1", "maxFiles": 10}, lambda_context)
    assert out["count"] == 1
    items = json.loads(aws.get_object(Bucket=ARCHIVE, Key=out["key"])["Body"].read())
    assert items[0]["key"] == "docs/a.txt" and items[0]["attrs"]["uid"] == 1234


# ---------------------------------------------------------------- record


def _item(aws, key="docs/a.txt", body=b"hello world", large=False):
    put = aws.put_object(Bucket=AP, Key=key, Body=body)
    return {
        "key": key,
        "size": len(body),
        "etag": put["ETag"],
        "lastModified": "2020-01-01T00:00:00+00:00",
        "isLarge": large,
    }


def _record(item, ledger, attrs=None, **cfg_env):
    return record.record_file(
        RuntimeConfig.from_env(),
        run_id="r1",
        item=item,
        attrs=attrs,
        storage_class="DEEP_ARCHIVE",
        helper=S3ApHelper(AP),
        ledger=ledger,
    )


def test_record_hashes_the_file_and_writes_the_ledger(aws, ledger):
    body = b"hello world" * 1000
    out = _record(_item(aws, body=body), ledger, attrs={"uid": 1234, "mode": "640"})
    stored = ledger.get("r1", "docs/a.txt")
    assert out["status"] == L.RECORDED == stored["status"]
    assert stored["sha256"] == hashlib.sha256(body).hexdigest()
    assert stored["crc64nvme"] == crc64_to_b64(crc64nvme_update_pure(0, body))
    assert stored["archiveKey"] == "data/docs/a.txt" and stored["size"] == len(body)
    assert stored["attrs"]["uid"] == 1234 and stored["secondCopyRequired"] is False


def test_record_builds_copy_parameters(aws, ledger):
    item = _item(aws, key="docs/ü file.txt")
    out = _record(item, ledger, attrs={"uid": 7})
    copy = out["copy"]
    assert copy["bucket"] == ARCHIVE and copy["key"] == "data/docs/ü file.txt"
    assert copy["copySource"] == f"{AP}/docs/%C3%BC%20file.txt"
    assert copy["ifMatch"] == item["etag"] and copy["storageClass"] == "DEEP_ARCHIVE"
    assert copy["metadata"]["source-uid"] == "7" and copy["contentType"] == "text/plain"
    assert "secondCopy" not in out


def test_record_adds_second_copy_parameters_when_configured(aws, ledger, monkeypatch):
    monkeypatch.setenv("SECOND_COPY_BUCKET", "second-copy-bucket")
    out = _record(_item(aws), ledger)
    assert out["secondCopy"]["bucket"] == "second-copy-bucket"
    assert ledger.get("r1", "docs/a.txt")["secondCopyRequired"] is True


def test_record_large_file_is_not_hashed_here(aws, ledger):
    out = _record(_item(aws, large=True), ledger)
    stored = ledger.get("r1", "docs/a.txt")
    assert out["isLarge"] is True and "sha256" not in stored and stored["isLarge"] is True


def test_record_sets_a_changed_file_aside(aws, ledger):
    item = _item(aws, body=b"first")
    aws.put_object(Bucket=AP, Key="docs/a.txt", Body=b"second version")
    out = _record(item, ledger)
    assert out["status"] == L.CHANGED and "copy" not in out
    assert ledger.get("r1", "docs/a.txt")["status"] == L.CHANGED


def test_record_detects_a_change_during_the_read(aws, ledger):
    item = _item(aws, body=b"x" * 100)

    class Mutating(S3ApHelper):
        def streaming_download(self, key, chunk_size=0):
            yield from super().streaming_download(key)
            aws.put_object(Bucket=AP, Key=key, Body=b"y" * 100)

    out = record.record_file(
        RuntimeConfig.from_env(),
        run_id="r1",
        item=item,
        attrs=None,
        storage_class="GLACIER",
        helper=Mutating(AP),
        ledger=ledger,
    )
    assert out["status"] == L.CHANGED
