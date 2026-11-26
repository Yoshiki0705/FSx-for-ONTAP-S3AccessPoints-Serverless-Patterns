"""Restore verification, restore selection of interrupted deletes, the watchdog and the policy renderer."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest
from avd_support import AP, ARCHIVE, PATTERN_DIR, load_fargate_entrypoint, load_handler

from shared.archive_verify import ledger as L
from shared.archive_verify.checksums import hash_stream
from shared.archive_verify.restore_verify import verify_restored
from shared.s3ap_helper import S3ApHelper

restore = load_handler("restore")
watchdog = load_handler("watchdog")
entry = load_fargate_entrypoint()

BODY = b"restore me" * 50


def _archived(ledger, key, status, with_copy=True, aws=None, **extra):
    d = hash_stream([BODY])
    ledger.put(
        "r1",
        key,
        status,
        size=len(BODY),
        isLarge=False,
        storageClass="DEEP_ARCHIVE",
        archiveBucket=ARCHIVE,
        archiveKey=f"data/r1/{key}",
        **d.as_ledger(),
        **extra,
    )
    if with_copy:
        aws.put_object(Bucket=ARCHIVE, Key=f"data/r1/{key}", Body=BODY)


def _select(ledger, **req):
    return restore.select_items(ledger, {"runId": "r1", "prefix": "", "keys": [], **req})


# ---- restore selection ---------------------------------------------------------------------------


def test_restore_selects_interrupted_and_changed_items_only_when_the_archive_copy_exists(aws, ledger):
    _archived(ledger, "deleted", L.DELETED, with_copy=False, aws=aws)  # the ledger says deleted: trusted
    _archived(ledger, "deleting-with-copy", L.DELETING, aws=aws)
    _archived(ledger, "deleting-no-copy", L.DELETING, with_copy=False, aws=aws)
    _archived(ledger, "changed-with-copy", L.CHANGED, aws=aws)
    ledger.put("r1", "changed-never-copied", L.CHANGED, size=1, etag="e")
    _archived(ledger, "verified", L.VERIFIED, aws=aws)
    assert sorted(i["key"] for i in _select(ledger)) == ["changed-with-copy", "deleted", "deleting-with-copy"]


def test_finalize_accepts_an_item_whose_delete_was_interrupted(aws, ledger, lambda_context):
    _archived(ledger, "k", L.DELETING, aws=aws)
    restore.handler({"action": "finalize", "runId": "r1", "key": "k", "restoreRunId": "rr1"}, lambda_context)
    assert ledger.get("r1", "k")["status"] == L.RESTORED


# ---- restore verification ------------------------------------------------------------------------


def _restored(ledger, aws, put_body=BODY, key="k"):
    _archived(ledger, key, L.RESTORED, aws=aws, restoreRunId="rr1")
    aws.put_object(Bucket=AP, Key=key, Body=put_body)


def test_restore_verified_when_the_restored_file_matches_the_ledger(aws, ledger):
    _restored(ledger, aws)
    out = verify_restored(S3ApHelper(AP), ledger, "r1", "k", "rr1")
    assert out["status"] == L.RESTORE_VERIFIED
    assert ledger.get("r1", "k")["status"] == L.RESTORE_VERIFIED


@pytest.mark.parametrize("body", [b"x" * len(BODY), BODY + b"!", b""])
def test_restore_mismatch_when_content_or_size_differ(aws, ledger, body):
    _restored(ledger, aws, put_body=body)
    out = verify_restored(S3ApHelper(AP), ledger, "r1", "k", "rr1")
    assert out["status"] == L.RESTORE_MISMATCH
    assert ledger.get("r1", "k")["status"] == L.RESTORE_MISMATCH


def test_restore_mismatch_when_the_ledger_has_no_digest(aws, ledger):
    ledger.put("r1", "k", L.RESTORED, size=3, restoreRunId="rr1")
    aws.put_object(Bucket=AP, Key="k", Body=b"abc")
    assert verify_restored(S3ApHelper(AP), ledger, "r1", "k", "rr1")["status"] == L.RESTORE_MISMATCH


def test_another_restore_runs_row_is_not_overwritten(aws, ledger):
    _restored(ledger, aws)
    verify_restored(S3ApHelper(AP), ledger, "r1", "k", "some-other-restore")
    assert ledger.get("r1", "k")["status"] == L.RESTORED


def test_the_handler_verify_action(aws, ledger, lambda_context):
    _restored(ledger, aws)
    out = restore.handler({"action": "verify", "runId": "r1", "key": "k", "restoreRunId": "rr1"}, lambda_context)
    assert out["status"] == L.RESTORE_VERIFIED


def test_the_fargate_verify_mode_exits_nonzero_on_a_mismatch(aws, ledger):
    _restored(ledger, aws, put_body=b"corrupt")
    task = {"runId": "r1", "key": "k", "restoreRunId": "rr1"}
    assert entry.run_verify_restore(task, S3ApHelper(AP), ledger) == entry.EXIT_MISMATCH
    _restored(ledger, aws)
    assert entry.run_verify_restore(task, S3ApHelper(AP), ledger) == entry.EXIT_OK


def test_reapply_lists_only_verified_files_and_reports_the_rest(aws, ledger, lambda_context):
    for k, st in (("good", L.RESTORE_VERIFIED), ("bad", L.RESTORE_MISMATCH), ("unchecked", L.RESTORED)):
        _archived(ledger, k, st, aws=aws, restoreRunId="rr1", attrs={"uid": 1, "gid": 2, "mode": "600"})
    out = restore.handler({"action": "reapply", "runId": "r1", "restoreRunId": "rr1"}, lambda_context)
    script = aws.get_object(Bucket=ARCHIVE, Key=out["scriptKey"])["Body"].read().decode()
    assert out["files"] == 1 and "good" in script and "bad" not in script and "unchecked" not in script
    assert out["restoreMismatch"] == ["bad"] and out["restoredNotVerified"] == ["unchecked"]
    assert out["outcome"] == "COMPLETED_WITH_ERRORS"


# ---- watchdog ------------------------------------------------------------------------------------


class _Ssm:
    def __init__(self, ages_hours):
        now = datetime.now(timezone.utc)
        self.params = [{"LastModifiedDate": now - timedelta(hours=h)} for h in ages_hours]

    def get_parameters_by_path(self, **kw):
        return {"Parameters": self.params}


def test_watchdog_reports_the_age_of_the_oldest_pending_approval():
    assert watchdog.oldest_pending_hours(_Ssm([1, 30, 5]), "/s/approvals") == pytest.approx(30, abs=0.1)
    assert watchdog.oldest_pending_hours(_Ssm([]), "/s/approvals") == 0


# ---- access point policy renderer ----------------------------------------------------------------

OUTPUTS = {
    "SelectRoleArn": "arn:aws:iam::123456789012:role/s-select",
    "RecordRoleArn": "arn:aws:iam::123456789012:role/s-record",
    "DeleteRoleArn": "arn:aws:iam::123456789012:role/s-delete",
    "RestoreFunctionRoleArn": "arn:aws:iam::123456789012:role/s-restorefn",
    "ArchiveStateMachineRoleArn": "arn:aws:iam::123456789012:role/s-archivesm",
    "RestoreStateMachineRoleArn": "arn:aws:iam::123456789012:role/s-restoresm",
    "FargateTaskRoleArn": "arn:aws:iam::123456789012:role/s-task",
    "FargateRestoreTaskRoleArn": "arn:aws:iam::123456789012:role/s-resttask",
}
AP_ARN = "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-ap"


def _renderer():
    sys.path.insert(0, str(PATTERN_DIR / "tools"))
    import render_access_point_policy as r

    return r


def _principals(policy, action):
    out = set()
    for s in policy["Statement"]:
        if action in s["Action"]:
            out |= set(s["Principal"]["AWS"])
    return out


def test_the_policy_gives_delete_to_the_delete_role_only_and_put_to_the_restore_roles_only():
    policy = _renderer().render(OUTPUTS, AP_ARN)
    assert _principals(policy, "s3:DeleteObject") == {OUTPUTS["DeleteRoleArn"]}
    assert _principals(policy, "s3:PutObject") == {
        OUTPUTS["RestoreStateMachineRoleArn"],
        OUTPUTS["FargateRestoreTaskRoleArn"],
    }
    assert OUTPUTS["FargateTaskRoleArn"] in _principals(policy, "s3:GetObject")
    # a role that reads 404 as "gone" must be able to list, or S3 answers 403 for a missing key
    assert {OUTPUTS["DeleteRoleArn"], OUTPUTS["RestoreFunctionRoleArn"], OUTPUTS["SelectRoleArn"]} <= _principals(
        policy, "s3:ListBucket"
    )
    assert all(s["Effect"] == "Allow" for s in policy["Statement"])
    assert AP_ARN + "/object/*" in policy["Statement"][0]["Resource"]


def test_the_renderer_works_without_fargate_and_rejects_missing_roles_and_bad_arns():
    r = _renderer()
    no_fargate = {k: v for k, v in OUTPUTS.items() if "Fargate" not in k}
    policy = r.render(no_fargate, AP_ARN)
    assert _principals(policy, "s3:PutObject") == {OUTPUTS["RestoreStateMachineRoleArn"]}
    with pytest.raises(ValueError, match="DeleteRoleArn"):
        r.render({k: v for k, v in OUTPUTS.items() if k != "DeleteRoleArn"}, AP_ARN)
    with pytest.raises(ValueError):
        r.render(OUTPUTS, "arn:aws:s3:::bucket")


def test_the_renderer_reads_describe_stacks_output(tmp_path):
    f = tmp_path / "o.json"
    f.write_text(json.dumps([{"OutputKey": k, "OutputValue": v} for k, v in OUTPUTS.items()]))
    done = subprocess.run(
        [
            sys.executable,
            str(PATTERN_DIR / "tools" / "render_access_point_policy.py"),
            "--outputs",
            str(f),
            "--access-point-arn",
            AP_ARN,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(done.stdout)["Version"] == "2012-10-17"
    assert hashlib.sha256(done.stdout.encode()).hexdigest()  # deterministic output is a string
