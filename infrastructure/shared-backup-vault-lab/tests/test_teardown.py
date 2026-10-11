"""10_teardown.sh: what it reads before it deletes, what it refuses, and what it keeps.

A test that expects a refusal checks the exit code, a message that belongs to the
refusal, that the script got as far as the read that caused it, and that no
state-changing call was recorded. The success scenario (``ops.teardown``) deletes a
share, one restored volume, the owner volume with its recovery point, three stacks
and finds an empty air-gapped vault managed by its stack.
"""

from __future__ import annotations

from typing import Any

import lab_scenarios as sc
import lab_scenarios_ops as ops
import pytest
from lab_testlib import Lab, assert_called

PRIMARY = sc.PRIMARY
SECOND = sc.SECOND
SCRIPT = "10_teardown.sh"
mutating = sc.mutating
calls_of = sc.calls_of
TWO_REGIONS = {"LAB_SECOND_REGION": SECOND}
OWNER_BASE = f"cloudformation describe-stacks --stack-name={sc.TAG}-owner-base"
LAG_STACK = f"cloudformation describe-stacks --stack-name={sc.TAG}-lag-{PRIMARY}"
RECIPIENT_STACK = f"cloudformation describe-stacks --stack-name={sc.TAG}-recipient-{PRIMARY}"
STD_LIST = f"backup list-recovery-points-by-backup-vault --backup-vault-name={sc.STD_VAULT}"
LAG_VAULTS = f"backup list-backup-vaults --by-vault-type --region={PRIMARY}"
TOKEN = ops.DELETE_KEY_TOKEN


def run10(
    lab: Lab, *updates: dict[str, Any], args: tuple[str, ...] = ("--apply",), env: dict[str, str | None] | None = None
):
    """Run 10 against the success scenario changed by ``updates``."""
    lab.write_scenario(sc.merged(ops.teardown(), *updates))
    return lab.run(SCRIPT, *args, env=env)


def only_deletes(calls: list[dict[str, Any]]) -> list[str]:
    """Names of the recorded calls that delete or schedule a deletion."""
    return [
        f"{c['service']} {c['subcommand']}"
        for c in calls
        if c["subcommand"].startswith("delete-") or c["subcommand"] == "schedule-key-deletion"
    ]


def absent_second_region() -> dict[str, Any]:
    """Nothing exists in the second Region (no recipient stack, no LAG stack, an empty vault list)."""
    return {
        f"cloudformation describe-stacks --stack-name={sc.TAG}-recipient-{SECOND}": sc.no_stack(),
        f"cloudformation describe-stacks --stack-name={sc.TAG}-lag-{SECOND}": sc.no_stack(),
        f"backup list-backup-vaults --by-vault-type --region={SECOND}": {"body": {"BackupVaultList": []}},
    }


# --------------------------------------------------------------------------
# Reading before deleting
# --------------------------------------------------------------------------


def test_10_tags_are_read_with_list_tags(lab: Lab) -> None:
    """The describe responses carry no tags; the Project tag comes from list-tags-for-resource."""
    result = run10(lab)
    assert result.rc == 0, result.out + result.err
    assert_called(result.calls, "fsx", "list-tags-for-resource", {"--resource-arn": ops.RECIPIENT_SVM_ARN}, times=1)
    assert_called(result.calls, "fsx", "list-tags-for-resource", {"--resource-arn": sc.VOLUME_ARN}, times=1)
    assert_called(result.calls, "fsx", "delete-volume", {"--volume-id": sc.SENTINEL.VOLUME}, times=1)


def test_10_foreign_tag_refuses_delete(lab: Lab) -> None:
    key = f"fsx list-tags-for-resource --resource-arn={ops.RECIPIENT_SVM_ARN}"
    result = run10(lab, {key: ops.FOREIGN_TAG})
    assert result.rc == 1
    assert "does not carry Project=shared-vault-lab" in result.err
    assert_called(result.calls, "fsx", "list-tags-for-resource", {"--resource-arn": ops.RECIPIENT_SVM_ARN})
    assert mutating(result.calls) == []


def test_10_foreign_tag_on_the_owner_volume_refuses_delete(lab: Lab) -> None:
    result = run10(lab, {f"fsx list-tags-for-resource --resource-arn={sc.VOLUME_ARN}": ops.NO_TAG})
    assert result.rc == 1
    assert f"volume {sc.SENTINEL.VOLUME} does not carry Project=shared-vault-lab" in result.err
    assert mutating(result.calls) == []


def test_10_revokes_share_before_anything_else(lab: Lab) -> None:
    result = run10(lab)
    assert result.rc == 0, result.out + result.err
    names = mutating(result.calls)
    assert names[0] == "ram delete-resource-share"
    assert names.count("ram delete-resource-share") == 1
    assert_called(result.calls, "ram", "delete-resource-share", {"--resource-share-arn": ops.SHARE_ARN}, times=1)


# --------------------------------------------------------------------------
# Step 0: running jobs
# --------------------------------------------------------------------------

JOB_CASES = {
    "backup": (
        "backup list-backup-jobs --by-state=RUNNING",
        {"body": {"BackupJobs": [{"BackupJobId": "bj-1111"}]}},
        "backup job(s) in ap-northeast-1, RUNNING: bj-1111",
    ),
    "copy": (
        "backup list-copy-jobs --by-state=RUNNING",
        {
            "body": {
                "CopyJobs": [
                    {
                        "CopyJobId": "cj-2222",
                        "DestinationBackupVaultArn": sc.lag_arn(PRIMARY),
                        "ResourceArn": sc.VOLUME_ARN,
                    }
                ]
            }
        },
        "copy job(s) in ap-northeast-1, RUNNING: cj-2222",
    ),
    "restore": (
        "backup list-restore-jobs --by-status=PENDING",
        {"body": {"RestoreJobs": [{"RestoreJobId": "rj-3333", "RecoveryPointArn": ops.SHARED_RP}]}},
        "restore job(s) in ap-northeast-1, PENDING: rj-3333",
    ),
}


@pytest.mark.parametrize("kind", sorted(JOB_CASES))
def test_10_running_jobs_abort_before_any_delete(lab: Lab, kind: str) -> None:
    key, body, text = JOB_CASES[kind]
    result = run10(lab, {key: body})
    assert result.rc == 1
    assert "jobs are running; nothing was changed" in result.err
    assert text in result.err
    assert mutating(result.calls) == []
    assert calls_of(result.calls, "list-backup-jobs"), "the job reads must have happened"


def test_10_other_owner_restore_job_is_ignored(lab: Lab) -> None:
    other = arn_of_other_owner()
    body = {"body": {"RestoreJobs": [{"RestoreJobId": "rj-4444", "RecoveryPointArn": other}]}}
    result = run10(lab, {"backup list-restore-jobs": body})
    assert result.rc == 0, result.out + result.err
    assert "rj-4444" not in result.err
    assert calls_of(result.calls, "delete-volume"), "the teardown must have continued"


def arn_of_other_owner() -> str:
    return "arn:aws:backup:ap-northeast-1:999988887777:recovery-point:eeeeeeee-4444-4444-8444-eeeeeeeeeeee"


COPY_CASES = {
    "primary-only": (
        {"backup list-copy-jobs --by-state=CREATED --region=ap-northeast-1": "job"},
        {},
    ),
    "second-only": (
        {"backup list-copy-jobs --by-state=RUNNING --region=ap-northeast-3": "job"},
        {},
    ),
    "no-volume-arn": (
        {"backup list-copy-jobs --by-state=RUNNING --region=ap-northeast-3": "job"},
        {OWNER_BASE: sc.no_stack()},
    ),
}


@pytest.mark.parametrize("name", sorted(COPY_CASES))
def test_10_running_cross_region_copy_job_aborts(lab: Lab, name: str) -> None:
    """The Region that lists a cross-Region copy job is not known, so both are read."""
    keys, extra = COPY_CASES[name]
    job = {
        "body": {
            "CopyJobs": [
                {
                    "CopyJobId": "cj-5555",
                    "DestinationBackupVaultArn": sc.lag_arn(SECOND),
                    "ResourceArn": "arn:aws:fsx:ap-northeast-1:111122223333:volume/fs-x/fsvol-x"
                    if name == "no-volume-arn"
                    else sc.VOLUME_ARN,
                }
            ]
        }
    }
    updates = [absent_second_region(), extra, {key: job for key in keys}]
    result = run10(lab, *updates, env=TWO_REGIONS)
    assert result.rc == 1
    assert "copy job(s)" in result.err and "cj-5555" in result.err
    assert mutating(result.calls) == []
    regions = {c["region"] for c in calls_of(result.calls, "list-copy-jobs")}
    assert regions >= {PRIMARY} if name == "primary-only" else regions >= {PRIMARY, SECOND}
    assert not [c for c in result.calls if "--by-destination-vault-arn" in c["args"]]


def test_10_copy_job_check_failure_is_unknown_and_aborts(lab: Lab) -> None:
    result = run10(lab, {"backup list-copy-jobs --by-state=RUNNING": sc.err("ThrottlingException", "slow down")})
    assert result.rc == 1
    assert "UNKNOWN: the RUNNING copy jobs in ap-northeast-1 could not be listed" in result.err
    assert "Nothing was changed" in result.err
    assert mutating(result.calls) == []


def test_10_copy_job_to_other_vault_is_ignored(lab: Lab) -> None:
    other_vault = sc.lag_arn(PRIMARY).replace(sc.LAG_VAULT, "someone-elses-vault")
    body = {
        "body": {
            "CopyJobs": [
                {
                    "CopyJobId": "cj-6666",
                    "DestinationBackupVaultArn": other_vault,
                    "ResourceArn": "arn:aws:fsx:ap-northeast-1:111122223333:volume/fs-x/fsvol-x",
                }
            ]
        }
    }
    result = run10(lab, {"backup list-copy-jobs --by-state=RUNNING": body})
    assert result.rc == 0, result.out + result.err
    assert "cj-6666" not in result.err
    assert calls_of(result.calls, "delete-volume")


def test_10_unreadable_owner_stack_is_unknown_and_aborts(lab: Lab) -> None:
    result = run10(lab, {OWNER_BASE: sc.err("ThrottlingException", "slow down")})
    assert result.rc == 1
    assert "UNKNOWN: stack shared-vault-lab-owner-base could not be read" in result.err
    assert mutating(result.calls) == []


def test_10_rejects_a_region_argument(lab: Lab) -> None:
    lab.write_scenario(ops.teardown())
    result = lab.run(SCRIPT, "--region", PRIMARY)
    assert result.rc == 2
    assert "no --region" in result.err
    assert result.calls == []


# --------------------------------------------------------------------------
# Recipient volumes are counted by membership in the lab SVM
# --------------------------------------------------------------------------


def test_10_untagged_restored_volume_in_lab_svm_is_deleted(lab: Lab) -> None:
    """08 may stop before it tags the volume: the volume is found through its SVM, not its tag."""
    result = run10(lab)
    assert result.rc == 0, result.out + result.err
    assert_called(
        result.calls,
        "fsx",
        "delete-volume",
        {"--volume-id": ops.RESTORED_VOLUME_ID, "--ontap-configuration": "SkipFinalBackup=true"},
        profile=sc.RECIPIENT_PROFILE,
        times=1,
    )
    assert not [
        c
        for c in calls_of(result.calls, "list-tags-for-resource")
        if c["args"]["--resource-arn"] == [ops.RESTORED_VOLUME_ARN]
    ]


def test_10_svm_without_lab_tag_refuses(lab: Lab) -> None:
    key = f"fsx list-tags-for-resource --resource-arn={ops.RECIPIENT_SVM_ARN}"
    result = run10(lab, {key: ops.NO_TAG})
    assert result.rc == 1
    assert "Nothing was deleted" in result.err
    assert only_deletes(result.calls) == []
    assert not calls_of(result.calls, "describe-volumes") or all(
        "--filters" not in c["args"] for c in calls_of(result.calls, "describe-volumes")
    )


def test_10_root_volume_is_not_deleted(lab: Lab) -> None:
    result = run10(lab)
    assert result.rc == 0, result.out + result.err
    deleted = [c["args"]["--volume-id"][0] for c in calls_of(result.calls, "delete-volume")]
    assert ops.ROOT_VOLUME_ID not in deleted
    assert ops.RESTORED_VOLUME_ID in deleted


def test_10_a_failed_volume_delete_keeps_the_stack(lab: Lab) -> None:
    key = f"fsx delete-volume --profile={sc.OWNER_PROFILE}"
    result = run10(lab, {key: sc.err("BadRequest", "volume in use")})
    assert result.rc == 1
    deleted_stacks = [c["args"]["--stack-name"][0] for c in calls_of(result.calls, "delete-stack")]
    assert f"{sc.TAG}-owner-base" not in deleted_stacks
    assert "is not deleted because an earlier step failed" in result.out


# --------------------------------------------------------------------------
# The standard vault (H4): only this volume's recovery points of this stack's vault
# --------------------------------------------------------------------------


def test_10_standard_vault_recovery_point_of_other_resource_is_kept(lab: Lab) -> None:
    own = {"RecoveryPointArn": sc.SRC_RP, "ResourceArn": sc.VOLUME_ARN}
    other = {"RecoveryPointArn": ops.OTHER_RP, "ResourceArn": ops.OTHER_VOLUME_ARN}
    updates = {STD_LIST: [{"body": {"RecoveryPoints": [own, other]}}, {"body": {"RecoveryPoints": [other]}}]}
    result = run10(lab, updates)
    deleted = calls_of(result.calls, "delete-recovery-point")
    assert [c["args"]["--recovery-point-arn"] for c in deleted] == [[sc.SRC_RP]]
    assert ops.OTHER_RP not in str(deleted)
    assert_called(result.calls, "backup", "list-recovery-points-by-backup-vault", {"--by-resource-arn": sc.VOLUME_ARN})


def test_10_standard_vault_recovery_point_of_another_resource_alone_is_never_deleted(lab: Lab) -> None:
    other = {"RecoveryPointArn": ops.OTHER_RP, "ResourceArn": ops.OTHER_VOLUME_ARN}
    result = run10(lab, {STD_LIST: {"body": {"RecoveryPoints": [other]}}})
    assert not calls_of(result.calls, "delete-recovery-point")


def test_10_standard_vault_without_stack_is_not_emptied(lab: Lab) -> None:
    """No owner-base stack but a vault of that name exists: nothing there is deleted."""
    vault_list = {
        "body": {"BackupVaultList": [{"BackupVaultName": sc.STD_VAULT, "NumberOfRecoveryPoints": 3}]},
    }
    result = run10(lab, {OWNER_BASE: sc.no_stack(), "backup list-backup-vaults !--by-vault-type": vault_list})
    assert result.rc == 1
    assert not calls_of(result.calls, "delete-recovery-point")
    assert not [
        c for c in calls_of(result.calls, "delete-stack") if c["args"]["--stack-name"] == [f"{sc.TAG}-owner-base"]
    ]
    assert not [
        c
        for c in calls_of(result.calls, "list-recovery-points-by-backup-vault")
        if c["args"].get("--backup-vault-name") == [sc.STD_VAULT]
    ], "the standard vault must not even be read without the stack"
    assert "=== REMAINING" in result.out
    assert f"standard vault {sc.STD_VAULT}" in result.out
    assert "steps 4 and 5 are not run" in result.err
    assert not calls_of(result.calls, "schedule-key-deletion")


def test_10_standard_vault_with_another_physical_name_is_not_emptied(lab: Lab) -> None:
    detail = {
        "body": {"StackResourceDetail": {"LogicalResourceId": "StandardVault", "PhysicalResourceId": "other-name"}}
    }
    result = run10(lab, {"cloudformation describe-stack-resource": detail})
    assert result.rc == 1
    assert not calls_of(result.calls, "delete-recovery-point")
    assert "is not named" in result.out
    assert not [
        c for c in calls_of(result.calls, "delete-stack") if c["args"]["--stack-name"] == [f"{sc.TAG}-owner-base"]
    ]


def test_10_without_stack_and_without_vault_there_is_nothing_to_empty(lab: Lab) -> None:
    """A rerun after the owner stack is gone must not be blocked by the standard-vault rule."""
    updates = {
        OWNER_BASE: sc.no_stack(),
        LAG_STACK: sc.no_stack(),
        RECIPIENT_STACK: sc.no_stack(),
        "ram get-resource-shares": {"body": {"resourceShares": []}},
        "backup list-backup-vaults !--by-vault-type": {"body": {"BackupVaultList": []}},
        LAG_VAULTS: {"body": {"BackupVaultList": []}},
    }
    result = run10(lab, updates)
    assert result.rc == 0, result.out + result.err
    assert "Nothing to delete." in result.out
    assert only_deletes(result.calls) == []


# --------------------------------------------------------------------------
# Air-gapped vaults and the key
# --------------------------------------------------------------------------


def test_10_lag_with_recovery_points_is_kept_and_listed(lab: Lab) -> None:
    result = run10(lab, ops.lag_listing(2))
    assert result.rc == 0, result.out + result.err
    lag_stack_deletes = [c for c in calls_of(result.calls, "delete-stack") if "-lag-" in c["args"]["--stack-name"][0]]
    assert lag_stack_deletes == []
    assert (
        f"air-gapped vault {sc.LAG_VAULT} in {PRIMARY} : recovery points=2, latest delete date={ops.DELETE_AT}"
        in result.out
    )
    assert "cost lag" in result.out


def test_10_empty_lag_without_stack_prints_the_delete_command_only(lab: Lab) -> None:
    result = run10(lab, {LAG_STACK: sc.no_stack()})
    assert result.rc == 0, result.out + result.err
    assert not [c for c in calls_of(result.calls, "delete-stack") if "-lag-" in c["args"]["--stack-name"][0]]
    assert f"aws backup delete-backup-vault --backup-vault-name {sc.LAG_VAULT} --region {PRIMARY}" in result.out
    assert not calls_of(result.calls, "delete-backup-vault")


def test_10_orphan_lag_vault_with_recovery_points_blocks_key_deletion(lab: Lab) -> None:
    """No LAG stack, no owner stack, but the vault holds recovery points (here: in the second Region)."""
    updates = [
        absent_second_region(),
        ops.lag_listing(1, SECOND),
        {
            OWNER_BASE: sc.no_stack(),
            LAG_STACK: sc.no_stack(),
            "backup list-backup-vaults !--by-vault-type": {"body": {"BackupVaultList": []}},
            f"cloudformation describe-stacks --stack-name={sc.TAG}-lag-{SECOND}": sc.no_stack(),
        },
    ]
    result = run10(lab, *updates, args=("--apply", "--delete-key", "--confirm", TOKEN), env=TWO_REGIONS)
    assert result.rc == 1
    assert not calls_of(result.calls, "schedule-key-deletion")
    assert "air-gapped vaults still hold 1 recovery point(s)" in result.out
    assert "key deletion refused" in result.out


KEY_CASES = {
    "recovery-points-remain": ([ops.lag_listing(1)], "still hold 1 recovery point(s)"),
    "listing-failed": (
        [{f"backup list-backup-vaults --by-vault-type --region={PRIMARY}": sc.err("ThrottlingException", "slow")}],
        "the state of an air-gapped vault is UNKNOWN",
    ),
    "file-system-uses-the-key": (
        [
            {
                "fsx describe-file-systems": {
                    "body": {"FileSystems": [{"FileSystemId": sc.SENTINEL.FS, "KmsKeyId": sc.KEY_ARN}]}
                }
            }
        ],
        "a file system still uses the key",
    ),
    "file-system-uses-the-key-by-id": (
        [
            {
                "fsx describe-file-systems": {
                    "body": {"FileSystems": [{"FileSystemId": sc.SENTINEL.FS, "KmsKeyId": ops.KEY_ID}]}
                }
            }
        ],
        "a file system still uses the key",
    ),
    "owner-stack-remains": (
        [{OWNER_BASE: {"body": sc.stack_body(f"{sc.TAG}-owner-base", "DELETE_FAILED", sc.OWNER_BASE_OUTPUTS)}}],
        "still exists",
    ),
}


@pytest.mark.parametrize("name", sorted(KEY_CASES))
def test_10_delete_key_requires_all_conditions(lab: Lab, name: str) -> None:
    updates, text = KEY_CASES[name]
    result = run10(lab, *updates, args=("--apply", "--delete-key", "--confirm", TOKEN))
    assert result.rc == 1, result.out + result.err
    assert text in result.out
    assert calls_of(result.calls, "describe-key"), "the key must have been read"
    assert not calls_of(result.calls, "schedule-key-deletion")
    assert not calls_of(result.calls, "delete-alias")


def test_10_delete_key_succeeds_once_when_all_hold(lab: Lab) -> None:
    result = run10(lab, args=("--apply", "--delete-key", "--confirm", TOKEN))
    assert result.rc == 0, result.out + result.err
    assert_called(
        result.calls,
        "kms",
        "schedule-key-deletion",
        {"--key-id": sc.KEY_ARN, "--pending-window-in-days": "7"},
        profile=sc.OWNER_PROFILE,
        times=1,
    )
    assert_called(result.calls, "kms", "delete-alias", {"--alias-name": "alias/shared-vault-lab-fs"}, times=1)
    names = [f"{c['service']} {c['subcommand']}" for c in result.calls]
    assert names.index("kms schedule-key-deletion") > max(
        i for i, n in enumerate(names) if n == "cloudformation delete-stack"
    )
    assert "deletion is scheduled (7-day pending window)" in result.out


def test_10_without_delete_key_the_key_is_kept(lab: Lab) -> None:
    result = run10(lab)
    assert result.rc == 0, result.out + result.err
    assert not calls_of(result.calls, "schedule-key-deletion")
    assert "customer managed key alias/shared-vault-lab-fs" in result.out


# --------------------------------------------------------------------------
# The remaining list
# --------------------------------------------------------------------------


def test_10_lists_portal_sandbox_when_outputs_exist(lab: Lab) -> None:
    portal = lab.repo / "solutions" / "amplify-portal"
    portal.mkdir(parents=True)
    portal = portal.resolve()
    (portal / "amplify_outputs.json").write_text("{}", encoding="utf-8")
    result = run10(lab)
    assert result.rc == 0, result.out + result.err
    assert f"make -C {portal} sandbox-delete" in result.out
    assert lab.external_calls() == [], "10 never runs the sandbox deletion"


def test_10_does_not_list_the_portal_sandbox_without_outputs(lab: Lab) -> None:
    result = run10(lab)
    assert result.rc == 0, result.out + result.err
    assert "sandbox-delete" not in result.out


def test_10_final_backups_left_behind_are_a_warning(lab: Lab) -> None:
    leftover = {"body": {"Backups": [{"BackupId": "backup-0aaaaaaaaaaaaaaaa"}]}}
    result = run10(lab, {"fsx describe-backups": leftover})
    assert result.rc == 0, result.out + result.err
    assert "1 backup(s) of the deleted file system" in result.out
    assert_called(
        result.calls, "fsx", "describe-backups", {"--filters": f"Name=file-system-id,Values={sc.SENTINEL.FS}"}
    )


def test_10_plan_mode_deletes_nothing_and_exits_10(lab: Lab) -> None:
    result = run10(lab, args=())
    assert result.rc == 10, result.out + result.err
    assert only_deletes(result.calls) == []
    assert "./scripts/10_teardown.sh --apply" in result.out


def test_10_two_regions_read_both_for_jobs_and_air_gapped_vaults(lab: Lab) -> None:
    updates = [absent_second_region(), ops.lag_listing(0, SECOND)]
    result = run10(lab, *updates, env=TWO_REGIONS)
    assert result.rc == 0, result.out + result.err
    for sub in ("list-copy-jobs", "list-backup-jobs"):
        assert {c["region"] for c in calls_of(result.calls, sub)} == {PRIMARY, SECOND}
    assert {c["region"] for c in calls_of(result.calls, "list-restore-jobs")} == {PRIMARY, SECOND}
    assert SECOND in {c["region"] for c in calls_of(result.calls, "list-backup-vaults")}
