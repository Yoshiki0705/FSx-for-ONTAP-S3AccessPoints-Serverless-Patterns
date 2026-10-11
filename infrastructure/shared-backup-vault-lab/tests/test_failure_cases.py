"""Failure cases of scripts 01-05.

A test that expects an abort checks four things: the exit code, a message that
belongs to that abort, that the script got as far as the read that caused it, and
that no state-changing call was recorded. An abort that merely crashes early would
satisfy the first condition alone.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import lab_scenarios as sc
import pytest
from lab_testlib import LAB_SRC, SENTINEL, Lab, assert_called

PRIMARY = sc.PRIMARY
SECOND = sc.SECOND
OWNER_PROFILE = sc.OWNER_PROFILE
RECIPIENT_PROFILE = sc.RECIPIENT_PROFILE
SCRIPT = "01_preflight.sh"
run01 = sc.run_preflight
mutating = sc.mutating
calls_of = sc.calls_of
NOW = {"LAB_NOW": "2026-10-11T00:00:00Z"}
TOKEN_03 = f"lock-7d-{sc.LAG_VAULT}@{PRIMARY}"
TOKEN_04 = f"copy-7d-{sc.LAG_VAULT}@{PRIMARY}"

# Scenario keys of sc.backup_copy() that tests override.
K_BASE_STACK = f"cloudformation describe-stacks --stack-name={sc.TAG}-owner-base"
K_LAG_STACK = f"cloudformation describe-stacks --stack-name={sc.TAG}-lag-{PRIMARY}"
K_LAG_VAULT = f"backup describe-backup-vault --region={PRIMARY}"
K_STD_LIST = f"backup list-recovery-points-by-backup-vault --backup-vault-name={sc.STD_VAULT}"
K_LAG_LIST = f"backup list-recovery-points-by-backup-vault --backup-vault-name={sc.LAG_VAULT}"
K_STD_DESCRIBE = f"backup describe-recovery-point --backup-vault-name={sc.STD_VAULT}"


def run04(lab: Lab, scenario: dict[str, Any], *args: str, env: dict[str, str] | None = None, token: str = TOKEN_04):
    """Run 04 --phase all with the right token unless ``args`` say otherwise."""
    lab.write_scenario(scenario)
    argv = list(args) or ["--retention-days", "7", "--apply", "--confirm", token]
    return lab.run("04_backup_and_copy.sh", *argv, env={**NOW, **(env or {})})


def run03(lab: Lab, scenario: dict[str, Any], *args: str, env: dict[str, str] | None = None):
    lab.write_scenario(scenario)
    argv = list(args) or ["--retention-days", "7", "--apply", "--confirm", TOKEN_03]
    return lab.run("03_deploy_lag_share.sh", *argv, env=env)


# --------------------------------------------------------------------------
# 01 (H10 and the organization / tag commands)
# --------------------------------------------------------------------------


def test_01_required_variable_empty_exits_78(lab: Lab) -> None:
    lab.write_scenario(sc.preflight())
    result = lab.run(SCRIPT, env={"LAB_OWNER_SUBNET_ID": ""})
    assert result.rc == 78
    assert "LAB_OWNER_SUBNET_ID" in result.err
    assert lab.calls() == []


def test_01_security_group_in_other_vpc_fails(lab: Lab) -> None:
    scenario = sc.merged(
        sc.preflight(),
        {
            f"ec2 describe-security-groups --profile={OWNER_PROFILE}": {
                "body": {"SecurityGroups": [{"GroupId": SENTINEL.SG, "VpcId": "vpc-0ccccccccccccccc"}]}
            }
        },
    )
    result = run01(lab, scenario, env={"LAB_OWNER_SECURITY_GROUP_ID": SENTINEL.SG})
    assert result.rc == 78
    assert "owner security group is in VPC vpc-0ccccccccccccccc" in result.out
    assert_called(result.calls, "ec2", "describe-security-groups", {"--group-ids": SENTINEL.SG}, profile=OWNER_PROFILE)
    assert mutating(result.calls) == []


def test_01_cli_without_by_shared_fails(lab: Lab) -> None:
    scenario = sc.merged(
        sc.preflight(), {"backup list-backup-vaults --by-shared": sc.err("", "Unknown options: --by-shared", rc=252)}
    )
    result = run01(lab, scenario)
    assert result.rc == 78
    assert "does not know --by-shared" in result.out
    assert_called(result.calls, "backup", "list-backup-vaults", {"--by-shared": []}, profile=RECIPIENT_PROFILE)


def test_01_never_calls_org_or_tag_mutations(lab: Lab) -> None:
    """The enabling commands are printed as text; they are never run."""
    org = {"body": {"Organization": {"Id": "o-aaaaaaaaaa", "MasterAccountId": sc.OWNER}}}
    scenario = sc.merged(
        sc.preflight(),
        sc.preflight_estimate(),
        {
            "organizations describe-organization": org,
            "organizations list-aws-service-access-for-organization": {"body": {"EnabledServicePrincipals": []}},
            "ce list-cost-allocation-tags": {"body": {"CostAllocationTags": []}},
        },
    )
    result = run01(lab, scenario, "--estimate-cost", env={"LAB_ALLOW_EXTERNAL_PRINCIPALS": "false"})
    forbidden = {("ram", "enable-sharing-with-aws-organization"), ("ce", "update-cost-allocation-tags-status")}
    assert not [c for c in result.calls if (c["service"], c["subcommand"]) in forbidden]
    assert "aws ram enable-sharing-with-aws-organization" in result.out
    assert "aws ce update-cost-allocation-tags-status" in result.out
    text = (LAB_SRC / "scripts" / SCRIPT).read_text(encoding="utf-8")
    assert not re.search(r"aws_(owner|recipient)\s+(ram enable-sharing|ce update-cost)", text)


# --------------------------------------------------------------------------
# Account and SSO guards (every state-changing script)
# --------------------------------------------------------------------------

GUARDED = {
    "02-owner": (sc.deploy_owner, ("02_deploy.sh", "--side", "owner", "--apply"), OWNER_PROFILE, {}),
    "02-recipient": (
        sc.deploy_recipient,
        ("02_deploy.sh", "--side", "recipient", "--apply"),
        RECIPIENT_PROFILE,
        {"LAB_RECIPIENT_EXISTING_FS_ID": sc.EXISTING_RECIPIENT_FS},
    ),
    "03": (
        sc.deploy_lag,
        ("03_deploy_lag_share.sh", "--retention-days", "7", "--apply", "--confirm", TOKEN_03),
        OWNER_PROFILE,
        {},
    ),
    "04": (
        sc.backup_copy,
        ("04_backup_and_copy.sh", "--retention-days", "7", "--apply", "--confirm", TOKEN_04),
        OWNER_PROFILE,
        NOW,
    ),
    "05": (sc.accept, ("05_accept_share.sh", "--apply"), RECIPIENT_PROFILE, NOW),
}


@pytest.mark.parametrize("name", sorted(GUARDED))
def test_assert_account_mismatch_blocks_all_mutations(lab: Lab, name: str) -> None:
    builder, argv, profile, env = GUARDED[name]
    other = {"body": {"Account": "999988887777", "Arn": "arn:aws:sts::999988887777:assumed-role/X/s", "UserId": "X"}}
    lab.write_scenario(sc.merged(builder(), {f"sts get-caller-identity --profile={profile}": other}))
    result = lab.run(*argv, env=env)
    assert result.rc == 1
    assert "resolves to account 999988887777" in result.err
    assert mutating(result.calls) == []
    assert [c["subcommand"] for c in result.calls] == ["get-caller-identity"]


def _write_sso(lab: Lab, profile: str, form: str, expires_at: str | None) -> None:
    config = lab.home / ".aws" / "config"
    cache = lab.home / ".aws" / "sso" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    if form == "session":
        config.write_text(
            f"[profile {profile}]\nsso_session = lab\n[sso-session lab]\nsso_start_url = https://example.invalid/start\n",
            encoding="utf-8",
        )
        key = "lab"
    elif form == "legacy":
        config.write_text(f"[profile {profile}]\nsso_start_url = https://example.invalid/start\n", encoding="utf-8")
        key = "https://example.invalid/start"
    else:
        config.write_text(f"[profile {profile}]\nregion = ap-northeast-1\n", encoding="utf-8")
        return
    name = hashlib.sha1(key.encode()).hexdigest()  # noqa: S324 - the cache key botocore uses
    if expires_at is not None:
        (cache / f"{name}.json").write_text(json.dumps({"expiresAt": expires_at}), encoding="utf-8")


@pytest.mark.parametrize("name", sorted(GUARDED))
@pytest.mark.parametrize("form", ["session", "legacy"])
def test_sso_minutes_low_blocks_every_mutation(lab: Lab, name: str, form: str) -> None:
    builder, argv, profile, env = GUARDED[name]
    _write_sso(lab, profile, form, "2026-10-11T00:10:00Z")
    lab.write_scenario(builder())
    result = lab.run(*argv, env={**env, "LAB_NOW": "2026-10-11T00:00:00Z"})
    assert result.rc == 1, result.out + result.err
    assert "10 minutes left (need 30)" in result.out
    assert mutating(result.calls) == []


def test_sso_minutes_enough_continues_and_other_profiles_are_skipped(lab: Lab) -> None:
    _write_sso(lab, OWNER_PROFILE, "session", "2026-10-11T02:00:00Z")
    lab.write_scenario(sc.deploy_lag())
    ok = lab.run("03_deploy_lag_share.sh", "--retention-days", "7", "--apply", "--confirm", TOKEN_03, env=NOW)
    assert ok.rc == 0, ok.out + ok.err
    assert "120 minutes left" in ok.out
    for form, text in (("static", "is not an SSO profile"), ("session", "could not be checked")):
        local = Lab(lab.tmp / f"sso-{form}")
        _write_sso(local, OWNER_PROFILE, form, None)
        local.write_scenario(sc.deploy_lag())
        result = local.run("03_deploy_lag_share.sh", "--retention-days", "7", "--apply", "--confirm", TOKEN_03, env=NOW)
        assert result.rc == 0, result.out + result.err
        assert text in result.out


# --------------------------------------------------------------------------
# Empty or ambiguous reads
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("missing", "stack"),
    [("VolumeArn", "base"), ("BackupRoleArn", "base"), ("KeyArn", "base"), ("LagVaultArn", "lag")],
)
def test_04_empty_prerequisite_aborts(lab: Lab, missing: str, stack: str) -> None:
    base_outputs = {k: v for k, v in sc.OWNER_BASE_OUTPUTS.items() if k != missing}
    lag = sc.lag_stack(PRIMARY)
    lag["Stacks"][0]["Outputs"] = [o for o in lag["Stacks"][0]["Outputs"] if o["OutputKey"] != missing]
    scenario = sc.merged(
        sc.backup_copy(),
        {
            K_BASE_STACK: {"body": sc.stack_body(f"{sc.TAG}-owner-base", "CREATE_COMPLETE", base_outputs)},
            K_LAG_STACK: {"body": lag},
        },
    )
    result = run04(lab, scenario)
    assert result.rc == 1, result.out + result.err
    assert "expected exactly one value (rows=0)" in result.err
    assert_called(result.calls, "cloudformation", "describe-stacks", {"--stack-name": f"{sc.TAG}-owner-base"})
    assert mutating(result.calls) == []


def test_04_null_output_value_aborts(lab: Lab) -> None:
    body = sc.stack_body(f"{sc.TAG}-owner-base", "CREATE_COMPLETE", sc.OWNER_BASE_OUTPUTS)
    body["Stacks"][0]["Outputs"][4]["OutputValue"] = None
    result = run04(lab, sc.merged(sc.backup_copy(), {K_BASE_STACK: {"body": body}}))
    assert result.rc == 1
    assert "rows=0" in result.err
    assert mutating(result.calls) == []


def test_04_two_source_recovery_points_abort(lab: Lab) -> None:
    other = sc.recovery_point(arn_value=sc.SRC_RP + "2", created="2026-10-10T10:00:00+09:00")
    scenario = sc.merged(sc.backup_copy(), {K_STD_LIST: {"body": {"RecoveryPoints": [sc.recovery_point(), other]}}})
    result = run04(lab, scenario)
    assert result.rc == 1
    assert "rows=2" in result.err
    assert "--source-recovery-point-arn" in result.err
    assert sc.SRC_RP in result.err and sc.SRC_RP + "2" in result.err
    assert_called(result.calls, "backup", "list-recovery-points-by-backup-vault", {"--backup-vault-name": sc.STD_VAULT})
    assert mutating(result.calls) == []
    # Naming one of them resolves the ambiguity.
    picked = run04(
        lab,
        scenario,
        "--retention-days",
        "7",
        "--source-recovery-point-arn",
        sc.SRC_RP,
        "--apply",
        "--confirm",
        TOKEN_04,
    )
    assert picked.rc == 0, picked.out + picked.err
    assert_called(picked.calls, "backup", "start-copy-job", {"--recovery-point-arn": sc.SRC_RP}, times=1)


def test_04_unlisted_source_recovery_point_aborts(lab: Lab) -> None:
    result = run04(
        lab,
        sc.backup_copy(source_exists=True),
        "--retention-days",
        "7",
        "--source-recovery-point-arn",
        sc.SRC_RP + "9",
        "--apply",
        "--confirm",
        TOKEN_04,
    )
    assert result.rc == 1
    assert "is not a COMPLETED recovery point" in result.err
    assert mutating(result.calls) == []


def test_04_source_listing_failure_aborts(lab: Lab) -> None:
    result = run04(lab, sc.merged(sc.backup_copy(), {K_STD_LIST: sc.err("AccessDeniedException", "denied")}))
    assert result.rc == 1
    assert "source state is unknown" in result.err
    assert mutating(result.calls) == []


def test_04_copy_phase_without_a_source_aborts(lab: Lab) -> None:
    result = run04(lab, sc.backup_copy(), "--phase", "copy", "--retention-days", "7", "--apply", "--confirm", TOKEN_04)
    assert result.rc == 1
    assert "run --phase backup --apply first" in result.err
    assert mutating(result.calls) == []


def test_05_two_pending_invitations_abort(lab: Lab) -> None:
    second = sc.invitation(PRIMARY)
    second["resourceShareInvitationArn"] += "2"
    scenario = sc.merged(
        sc.accept(),
        {
            "ram get-resource-share-invitations": {
                "body": {"resourceShareInvitations": [sc.invitation(PRIMARY), second]}
            }
        },
    )
    lab.write_scenario(scenario)
    result = lab.run("05_accept_share.sh", "--apply", env=NOW)
    assert result.rc == 1
    assert "rows=2" in result.err
    assert_called(result.calls, "ram", "get-resource-share-invitations")
    assert mutating(result.calls) == []


def test_03_two_active_shares_abort(lab: Lab) -> None:
    result = run03(lab, sc.merged(sc.deploy_lag(), {"ram get-resource-shares": sc.share_list(PRIMARY, count=2)}))
    assert result.rc == 1
    assert "duplicate shares" in result.out
    assert_called(result.calls, "ram", "get-resource-shares", times=1)


def test_03_repair_share_aborts_when_vault_list_has_no_lag(lab: Lab) -> None:
    scenario = sc.merged(sc.deploy_lag(), {"cloudformation describe-stacks": {"body": sc.lag_stack(PRIMARY)}})
    result = run03(lab, scenario, "--repair-share", "--apply")
    assert result.rc == 1
    assert "needs the vault" in result.err
    assert_called(result.calls, "backup", "list-backup-vaults")
    assert mutating(result.calls) == []


def test_03_repair_share_refuses_without_the_stack(lab: Lab) -> None:
    result = run03(lab, sc.deploy_lag(), "--repair-share", "--apply")
    assert result.rc == 1
    assert "needs the stack" in result.err
    assert mutating(result.calls) == []


def test_03_create_proceeds_when_vault_list_is_empty(lab: Lab) -> None:
    """The control of the two tests above: for a create, an empty list is the normal starting point."""
    result = run03(lab, sc.deploy_lag())
    assert result.rc == 0, result.out + result.err
    assert len(calls_of(result.calls, "deploy")) == 1


def test_03_vault_list_failure_aborts_before_deploy(lab: Lab) -> None:
    result = run03(
        lab, sc.merged(sc.deploy_lag(), {"backup list-backup-vaults": sc.err("AccessDeniedException", "denied")})
    )
    assert result.rc == 1
    assert "the vault state is unknown, nothing was changed" in result.err
    assert mutating(result.calls) == []


def test_03_orphan_vault_without_stack_aborts(lab: Lab) -> None:
    scenario = sc.merged(
        sc.deploy_lag(),
        {"backup list-backup-vaults": {"body": {"BackupVaultList": [{"BackupVaultName": sc.LAG_VAULT}]}}},
    )
    result = run03(lab, scenario)
    assert result.rc == 1
    assert "retained air-gapped vault" in result.err
    assert "shared-vault-lab-2" in result.err
    assert mutating(result.calls) == []


# --------------------------------------------------------------------------
# 02: stack states, deploy failures, tags
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status", ["ROLLBACK_COMPLETE", "CREATE_FAILED", "UPDATE_ROLLBACK_FAILED", "DELETE_FAILED", "REVIEW_IN_PROGRESS"]
)
def test_02_failed_stack_state_aborts(lab: Lab, status: str) -> None:
    body = sc.stack_body(f"{sc.TAG}-owner-base", status)
    lab.write_scenario(sc.merged(sc.deploy_owner(), {"cloudformation describe-stacks": {"body": body}}))
    result = lab.run("02_deploy.sh", "--side", "owner", "--apply")
    assert result.rc == 1
    assert f"is in {status}" in result.err
    expected = "continue-update-rollback" if status == "UPDATE_ROLLBACK_FAILED" else "delete-stack"
    assert f"aws cloudformation {expected} --stack-name {sc.TAG}-owner-base" in result.err
    assert_called(result.calls, "cloudformation", "describe-stacks")
    assert calls_of(result.calls, "deploy") == []


def test_02_a_stack_in_progress_is_not_deployed_over(lab: Lab) -> None:
    body = sc.stack_body(f"{sc.TAG}-owner-base", "UPDATE_IN_PROGRESS")
    lab.write_scenario(sc.merged(sc.deploy_owner(), {"cloudformation describe-stacks": {"body": body}}))
    result = lab.run("02_deploy.sh", "--side", "owner", "--apply")
    assert result.rc == 1
    assert "wait for the operation to finish" in result.err
    assert calls_of(result.calls, "deploy") == []


def test_02_unreadable_stack_state_aborts(lab: Lab) -> None:
    lab.write_scenario(
        sc.merged(sc.deploy_owner(), {"cloudformation describe-stacks": sc.err("AccessDenied", "denied")})
    )
    result = lab.run("02_deploy.sh", "--side", "owner", "--apply")
    assert result.rc == 1
    assert "could not be read" in result.err
    assert calls_of(result.calls, "deploy") == []


def test_02_deploy_failure_prints_events(lab: Lab) -> None:
    events = [
        {"LogicalResourceId": f"Res{i}", "ResourceStatus": "CREATE_FAILED", "ResourceStatusReason": f"reason {i}"}
        for i in range(12)
    ] + [{"LogicalResourceId": "Fine", "ResourceStatus": "CREATE_COMPLETE"}]
    scenario = sc.merged(
        sc.deploy_owner(),
        {
            "cloudformation describe-stacks": sc.no_stack(),
            "cloudformation deploy": sc.err("ChangeSetCreation", "Failed to create the changeset", rc=255),
            "cloudformation describe-stack-events": {"body": {"StackEvents": events}},
        },
    )
    lab.write_scenario(scenario)
    result = lab.run("02_deploy.sh", "--side", "owner", "--apply")
    assert result.rc == 1
    assert len(re.findall(r"^  FAILED ", result.err, re.M)) == 10
    assert "FAILED Res0: reason 0" in result.err
    assert "Fine" not in result.err
    assert_called(result.calls, "cloudformation", "describe-stack-events", {"--stack-name": f"{sc.TAG}-owner-base"})
    assert not [c for c in result.calls if c["subcommand"].startswith("delete")]


def test_02_postcheck_reads_tags_with_list_tags(lab: Lab) -> None:
    """The describe responses carry no tags; the check must use fsx list-tags-for-resource."""
    lab.write_scenario(sc.deploy_owner())
    result = lab.run("02_deploy.sh", "--side", "owner", "--apply")
    assert result.rc == 0, result.out + result.err
    assert len(calls_of(result.calls, "list-tags-for-resource")) == 3
    assert "[E3]" in result.out
    assert all("Tags" not in json.dumps(v) for k, v in sc.deploy_owner().items() if k.startswith("fsx describe"))


def test_02_foreign_or_missing_tag_fails_the_postcheck(lab: Lab) -> None:
    for tags in ({"Tags": [{"Key": "Project", "Value": "someone-else"}]}, {"Tags": []}):
        local = Lab(lab.tmp / f"tags-{len(tags['Tags'])}")
        local.write_scenario(sc.merged(sc.deploy_owner(), {"fsx list-tags-for-resource": {"body": tags}}))
        result = local.run("02_deploy.sh", "--side", "owner", "--apply")
        assert result.rc == 1
        assert "does not carry the Project=shared-vault-lab tag" in result.out


def test_02_missing_output_aborts_the_postcheck(lab: Lab) -> None:
    outputs = {k: v for k, v in sc.OWNER_BASE_OUTPUTS.items() if k != "SvmId"}
    body = sc.stack_body(f"{sc.TAG}-owner-base", "CREATE_COMPLETE", outputs)
    lab.write_scenario(
        sc.merged(sc.deploy_owner(), {"cloudformation describe-stacks": [sc.no_stack(), {"body": body}]})
    )
    result = lab.run("02_deploy.sh", "--side", "owner", "--apply")
    assert result.rc == 1
    assert "expected exactly one value (rows=0)" in result.err


def test_02_resource_that_never_becomes_available_fails_without_waiting_on_the_wall_clock(lab: Lab) -> None:
    creating = {
        "body": {"FileSystems": [{"FileSystemId": SENTINEL.FS, "Lifecycle": "CREATING", "ResourceARN": sc.FS_ARN}]}
    }
    lab.write_scenario(sc.merged(sc.deploy_owner(), {"fsx describe-file-systems": creating}))
    result = lab.run("02_deploy.sh", "--side", "owner", "--apply")
    assert result.rc == 1
    assert "did not reach AVAILABLE" in result.out
    assert len(lab.sleeps()) == 3600 // 30


def test_02_recipient_exhausted_svm_budget_refuses(lab: Lab) -> None:
    full = {"body": {"StorageVirtualMachines": [{"Name": f"svm_{i}"} for i in range(6)]}}
    lab.write_scenario(sc.merged(sc.deploy_recipient(), {"fsx describe-storage-virtual-machines --filters": full}))
    result = lab.run(
        "02_deploy.sh",
        "--side",
        "recipient",
        "--apply",
        env={"LAB_RECIPIENT_EXISTING_FS_ID": sc.EXISTING_RECIPIENT_FS},
    )
    assert result.rc == 1
    assert "already holds 6 of 6 SVMs" in result.err
    assert calls_of(result.calls, "deploy") == []


def test_02_requires_a_side_and_rejects_unknown_arguments(lab: Lab) -> None:
    assert lab.run("02_deploy.sh").rc == 2
    assert lab.run("02_deploy.sh", "--side", "both").rc == 2
    assert lab.run("02_deploy.sh", "--side", "owner", "--bogus").rc == 2
    assert lab.calls() == []


# --------------------------------------------------------------------------
# 03: retention change, vault state, share
# --------------------------------------------------------------------------


def test_03_changed_retention_on_existing_stack_aborts(lab: Lab) -> None:
    scenario = sc.merged(
        sc.deploy_lag(), {"cloudformation describe-stacks": {"body": sc.lag_stack(PRIMARY, retention="14")}}
    )
    result = run03(lab, scenario)
    assert result.rc == 1
    assert "RetentionDays=14" in result.err
    assert "--retention-days 7 would replace the vault" in result.err
    assert_called(result.calls, "cloudformation", "describe-stacks", {"--stack-name": f"{sc.TAG}-lag-{PRIMARY}"})
    assert calls_of(result.calls, "deploy") == []


def test_03_same_retention_on_existing_stack_redeploys(lab: Lab) -> None:
    scenario = sc.merged(
        sc.deploy_lag(), {"cloudformation describe-stacks": {"body": sc.lag_stack(PRIMARY, retention="7")}}
    )
    result = run03(lab, scenario)
    assert result.rc == 0, result.out + result.err
    assert len(calls_of(result.calls, "deploy")) == 1


def test_03_vault_not_available_in_15_minutes_fails(lab: Lab) -> None:
    creating = {"body": {**sc.lag_vault(state="CREATING")["body"]}}
    result = run03(lab, sc.merged(sc.deploy_lag(), {"backup describe-backup-vault": creating}))
    assert result.rc == 1
    assert "did not become AVAILABLE in ap-northeast-1 within 15 minutes (nothing was deleted)" in result.out
    assert len(lab.sleeps()) == 900 // 15
    assert not [c for c in result.calls if c["subcommand"].startswith("delete")]


def test_03_retention_mismatch_after_deploy_fails(lab: Lab) -> None:
    result = run03(lab, sc.merged(sc.deploy_lag(), {"backup describe-backup-vault": sc.lag_vault(retention=14)}))
    assert result.rc == 1
    assert "vault retention is 14 to 14 days, expected 7 to 7" in result.out


def test_03_empty_share_list_fails_with_repair_hint(lab: Lab) -> None:
    result = run03(lab, sc.merged(sc.deploy_lag(), {"ram get-resource-shares": sc.share_list(PRIMARY, count=0)}))
    assert result.rc == 1
    assert "03_deploy_lag_share.sh --repair-share --apply" in result.out
    assert "deleted outside the stack" in result.out


def test_03_repair_share_sequence(lab: Lab) -> None:
    scenario = sc.merged(
        sc.deploy_lag(),
        {
            "cloudformation describe-stacks": {"body": sc.lag_stack(PRIMARY, retention="21")},
            "backup list-backup-vaults": {"body": {"BackupVaultList": [{"BackupVaultName": sc.LAG_VAULT}]}},
        },
    )
    result = run03(lab, scenario, "--repair-share", "--apply")
    assert result.rc == 0, result.out + result.err
    deploys = [c["args"]["--parameter-overrides"] for c in calls_of(result.calls, "deploy")]
    assert len(deploys) == 2
    assert "ShareEnabled=false" in deploys[0] and "ShareEnabled=true" in deploys[1]
    # The existing retention is passed through unchanged.
    assert all("RetentionDays=21" in d and "AcknowledgeRetentionDays=21" in d for d in deploys)
    assert not [c for c in result.calls if "vault" in c["subcommand"] and c["subcommand"].startswith("create")]
    assert_called(result.calls, "ram", "get-resource-shares", times=1)


def test_03_failed_stack_state_aborts(lab: Lab) -> None:
    body = sc.lag_stack(PRIMARY, status="ROLLBACK_COMPLETE")
    result = run03(lab, sc.merged(sc.deploy_lag(), {"cloudformation describe-stacks": {"body": body}}))
    assert result.rc == 1
    assert "ROLLBACK_COMPLETE" in result.err
    assert calls_of(result.calls, "deploy") == []


def test_03_not_permitted_share_points_to_external_principals(lab: Lab) -> None:
    events = {
        "body": {
            "StackEvents": [
                {
                    "LogicalResourceId": "VaultShare",
                    "ResourceStatus": "CREATE_FAILED",
                    "ResourceStatusReason": "OperationNotPermittedException: external principals not allowed",
                }
            ]
        }
    }
    scenario = sc.merged(
        sc.deploy_lag(),
        {
            "cloudformation deploy": sc.err("Failed", "stack failed", rc=255),
            "cloudformation describe-stack-events": events,
        },
    )
    result = run03(lab, scenario, env={"LAB_ALLOW_EXTERNAL_PRINCIPALS": "false"})
    assert result.rc == 1
    assert "LAB_ALLOW_EXTERNAL_PRINCIPALS=false needs organization sharing" in result.out


def test_03_allow_external_false_is_passed_and_recorded(lab: Lab) -> None:
    result = run03(lab, sc.deploy_lag(), env={"LAB_ALLOW_EXTERNAL_PRINCIPALS": "false"})
    assert result.rc == 0, result.out + result.err
    assert "AllowExternalPrincipals=false" in calls_of(result.calls, "deploy")[0]["args"]["--parameter-overrides"]
    assert "[E13]" in result.out


# --------------------------------------------------------------------------
# 04: existing work, job results, mismatches
# --------------------------------------------------------------------------


def test_04_existing_source_skips_start_backup_job(lab: Lab) -> None:
    result = run04(lab, sc.backup_copy(source_exists=True))
    assert result.rc == 0, result.out + result.err
    assert calls_of(result.calls, "start-backup-job") == []
    assert len(calls_of(result.calls, "start-copy-job")) == 1
    assert "no new backup is started" in result.out


def test_04_existing_copy_in_lag_skips_start_copy_job(lab: Lab) -> None:
    """The only defence against a second, irreversible copy of the same volume."""
    scenario = sc.merged(
        sc.backup_copy(source_exists=True),
        {K_LAG_LIST: {"body": {"RecoveryPoints": [{"RecoveryPointArn": sc.dest_rp(PRIMARY)}]}}},
    )
    result = run04(lab, scenario)
    assert result.rc == 0, result.out + result.err
    assert calls_of(result.calls, "start-copy-job") == []
    assert "already holds a recovery point of this volume" in result.out
    assert_called(
        result.calls,
        "backup",
        "list-recovery-points-by-backup-vault",
        {"--backup-vault-name": sc.LAG_VAULT, "--by-resource-arn": sc.VOLUME_ARN},
    )


@pytest.mark.parametrize("state", ["FAILED", "ABORTED", "EXPIRED"])
def test_04_failed_copy_job_is_reported(lab: Lab, state: str) -> None:
    done = {"body": {"CopyJob": {"CopyJobId": sc.COPY_JOB_ID, "State": state, "StatusMessage": "key is not usable"}}}
    result = run04(lab, sc.merged(sc.backup_copy(source_exists=True), {"backup describe-copy-job": done}))
    assert result.rc == 1
    assert f"ended in {state}: key is not usable" in result.out
    assert "[E4]" in result.out


def test_04_completed_with_message_warns(lab: Lab) -> None:
    done = {
        "body": {
            "CopyJob": {"CopyJobId": sc.COPY_JOB_ID, "State": "COMPLETED", "StatusMessage": "completed with issues"}
        }
    }
    result = run04(lab, sc.merged(sc.backup_copy(source_exists=True), {"backup describe-copy-job": done}))
    assert result.rc == 0, result.out + result.err
    assert "completed with a status message" in result.out
    assert "completed with issues" in result.out


def test_04_copy_job_that_never_finishes_times_out_on_the_sleep_count(lab: Lab) -> None:
    running = {"body": {"CopyJob": {"CopyJobId": sc.COPY_JOB_ID, "State": "RUNNING"}}}
    result = run04(lab, sc.merged(sc.backup_copy(source_exists=True), {"backup describe-copy-job": running}))
    assert result.rc == 1
    assert "did not finish within 60 minutes" in result.err
    assert len(lab.sleeps()) == 3600 // 60


def test_04_failed_backup_job_is_reported(lab: Lab) -> None:
    failed = {"body": {"BackupJobId": sc.BACKUP_JOB_ID, "State": "FAILED", "StatusMessage": "volume busy"}}
    result = run04(lab, sc.merged(sc.backup_copy(), {"backup describe-backup-job": failed}))
    assert result.rc == 1
    assert "ended in FAILED: volume busy" in result.out
    assert calls_of(result.calls, "start-copy-job") == []


def test_04_backup_job_that_never_finishes_stops_before_the_copy(lab: Lab) -> None:
    running = {"body": {"BackupJobId": sc.BACKUP_JOB_ID, "State": "RUNNING"}}
    result = run04(lab, sc.merged(sc.backup_copy(), {"backup describe-backup-job": running}))
    assert result.rc == 1
    assert "did not finish within 30 minutes (nothing was copied)" in result.err
    assert calls_of(result.calls, "start-copy-job") == []
    assert len(lab.sleeps()) == 1800 // 30


def test_04_retention_differs_from_vault_min_max_aborts(lab: Lab) -> None:
    result = run04(lab, sc.merged(sc.backup_copy(source_exists=True), {K_LAG_VAULT: sc.lag_vault(retention=14)}))
    assert result.rc == 1
    assert "differs from the vault's retention in ap-northeast-1 (minimum 14, maximum 14)" in result.err
    assert_called(result.calls, "backup", "describe-backup-vault", {"--backup-vault-name": sc.LAG_VAULT})
    assert mutating(result.calls) == []


def test_04_vault_not_available_aborts(lab: Lab) -> None:
    result = run04(lab, sc.merged(sc.backup_copy(source_exists=True), {K_LAG_VAULT: sc.lag_vault(state="CREATING")}))
    assert result.rc == 1
    assert "is not AVAILABLE" in result.err
    assert mutating(result.calls) == []


@pytest.mark.parametrize(
    "key", ["arn:aws:kms:ap-northeast-1:111122223333:key/22222222-2222-4222-8222-222222222222", None]
)
def test_04_source_key_mismatch_aborts(lab: Lab, key: str | None) -> None:
    body = {"RecoveryPointArn": sc.SRC_RP, "Status": "COMPLETED"}
    if key:
        body["EncryptionKeyArn"] = key
    result = run04(lab, sc.merged(sc.backup_copy(source_exists=True), {K_STD_DESCRIBE: {"body": body}}))
    assert result.rc == 1
    assert "not the lab key" in result.err
    assert calls_of(result.calls, "start-copy-job") == []
    assert_called(result.calls, "backup", "describe-recovery-point", {"--recovery-point-arn": sc.SRC_RP})


def test_04_key_mismatch_after_a_fresh_backup_stops_before_the_copy(lab: Lab) -> None:
    other = "arn:aws:kms:ap-northeast-1:111122223333:key/22222222-2222-4222-8222-222222222222"
    body = {"body": {"RecoveryPointArn": sc.SRC_RP, "EncryptionKeyArn": other, "Status": "COMPLETED"}}
    result = run04(lab, sc.merged(sc.backup_copy(), {K_STD_DESCRIBE: body}))
    assert result.rc == 1
    assert len(calls_of(result.calls, "start-backup-job")) == 1
    assert calls_of(result.calls, "start-copy-job") == []


def test_04_token_gets_retry_suffix_after_failed_copy(lab: Lab) -> None:
    lag = sc.lag_arn(PRIMARY)
    earlier = {
        "body": {
            "CopyJobs": [
                {"CopyJobId": "j1", "DestinationBackupVaultArn": lag, "State": "FAILED"},
                {"CopyJobId": "j2", "DestinationBackupVaultArn": lag, "State": "PARTIAL"},
                {"CopyJobId": "j3", "DestinationBackupVaultArn": lag, "State": "COMPLETED"},
                {"CopyJobId": "j4", "DestinationBackupVaultArn": lag.replace("lag", "other"), "State": "FAILED"},
            ]
        }
    }
    result = run04(
        lab,
        sc.merged(
            sc.backup_copy(source_exists=True), {"backup list-copy-jobs --by-source-recovery-point-arn": earlier}
        ),
    )
    assert result.rc == 0, result.out + result.err
    token = calls_of(result.calls, "start-copy-job")[0]["args"]["--idempotency-token"][0]
    assert token == sc.helpers.text_digest([sc.SRC_RP, lag, "7"]) + "-r2"
    clean = run04(Lab(lab.tmp / "clean"), sc.backup_copy(source_exists=True))
    assert not calls_of(clean.calls, "start-copy-job")[0]["args"]["--idempotency-token"][0].endswith("-r1")


def test_04_the_same_inputs_give_the_same_tokens(lab: Lab) -> None:
    first = run04(lab, sc.backup_copy(source_exists=True))
    second = run04(Lab(lab.tmp / "again"), sc.backup_copy(source_exists=True))
    token = lambda r: calls_of(r.calls, "start-copy-job")[0]["args"]["--idempotency-token"]  # noqa: E731
    assert token(first) == token(second)


# H3: copy jobs and recovery points are looked up in both Regions, and any unreadable read is UNKNOWN


def test_04_running_copy_job_blocks_second_copy(lab: Lab) -> None:
    lag = sc.lag_arn(PRIMARY)
    job = {"body": {"CopyJobs": [{"CopyJobId": "job-x", "DestinationBackupVaultArn": lag, "State": "RUNNING"}]}}
    for state in ("RUNNING", "CREATED"):
        local = Lab(lab.tmp / f"primary-{state}")
        result = run04(
            local, sc.merged(sc.backup_copy(source_exists=True), {f"backup list-copy-jobs --by-state={state}": job})
        )
        assert result.rc == 1, result.out + result.err
        assert "already in progress (job-x)" in result.err
        assert calls_of(result.calls, "start-copy-job") == []


def test_04_running_copy_job_listed_only_in_the_destination_region_blocks_the_copy(lab: Lab) -> None:
    lag = sc.lag_arn(SECOND)
    job = {"body": {"CopyJobs": [{"CopyJobId": "job-y", "DestinationBackupVaultArn": lag, "State": "RUNNING"}]}}
    scenario = sc.merged(
        sc.backup_copy(source_exists=True, second_region=True),
        {f"backup list-copy-jobs --by-state=RUNNING --region={SECOND}": job},
    )
    result = run04(
        lab,
        scenario,
        "--retention-days",
        "7",
        "--region",
        SECOND,
        "--apply",
        "--confirm",
        f"copy-7d-{sc.LAG_VAULT}@{SECOND}",
        env={"LAB_SECOND_REGION": SECOND},
    )
    assert result.rc == 1, result.out + result.err
    assert "job-y" in result.err
    assert calls_of(result.calls, "start-copy-job") == []
    regions = [
        c["region"]
        for c in result.calls
        if c["subcommand"] == "list-copy-jobs" and c["args"].get("--by-state") == ["RUNNING"]
    ]
    assert regions == [PRIMARY, SECOND]


def test_04_a_running_job_to_another_vault_does_not_block(lab: Lab) -> None:
    job = {
        "body": {
            "CopyJobs": [
                {
                    "CopyJobId": "job-z",
                    "DestinationBackupVaultArn": sc.lag_arn(PRIMARY).replace("lag", "other"),
                    "State": "RUNNING",
                }
            ]
        }
    }
    result = run04(
        lab, sc.merged(sc.backup_copy(source_exists=True), {"backup list-copy-jobs --by-state=RUNNING": job})
    )
    assert result.rc == 0, result.out + result.err
    assert len(calls_of(result.calls, "start-copy-job")) == 1


@pytest.mark.parametrize(
    ("key", "second"),
    [
        (K_LAG_LIST, False),
        ("backup list-copy-jobs --by-state=CREATED", False),
        ("backup list-copy-jobs --by-state=RUNNING", False),
        ("backup list-copy-jobs --by-source-recovery-point-arn", False),
        (f"backup list-copy-jobs --by-state=RUNNING --region={SECOND}", True),
        (f"backup list-recovery-points-by-backup-vault --backup-vault-name={sc.LAG_VAULT} --region={SECOND}", True),
    ],
    ids=[
        "lag-recovery-points",
        "created-primary",
        "running-primary",
        "earlier-jobs",
        "running-destination",
        "lag-recovery-points-destination",
    ],
)
def test_04_copy_job_listing_failure_aborts(lab: Lab, key: str, second: bool) -> None:
    scenario = sc.merged(
        sc.backup_copy(source_exists=True, second_region=second), {key: sc.err("AccessDeniedException", "denied")}
    )
    if second:
        args = ["--retention-days", "7", "--region", SECOND, "--apply", "--confirm", f"copy-7d-{sc.LAG_VAULT}@{SECOND}"]
        env = {"LAB_SECOND_REGION": SECOND}
    else:
        args, env = [], {}
    result = run04(lab, scenario, *args, env=env)
    assert result.rc == 1, result.out + result.err
    assert "UNKNOWN" in result.err
    assert "no copy was started" in result.err
    assert calls_of(result.calls, "start-copy-job") == []


def test_04_plan_without_source_shows_estimated_deletion(lab: Lab) -> None:
    result = run04(lab, sc.backup_copy(), "--retention-days", "7")
    assert result.rc == 10
    assert "expected earliest deletion : not known until the backup completes" in result.out
    assert "about 2026-10-18T00:00:00Z if the backup starts now (today + 7 days, UTC)" in result.out
    assert f"--confirm {TOKEN_04}" in result.out
    assert calls_of(result.calls, "start-backup-job") == []


def test_04_plan_with_a_source_shows_the_expiry_from_the_source_creation(lab: Lab) -> None:
    result = run04(lab, sc.backup_copy(source_exists=True), "--retention-days", "7")
    assert result.rc == 10
    assert "expected earliest deletion : 2026-10-18T01:00:00Z = source creation + 7 days" in result.out
    assert "not copy completion" in result.out


def test_04_validated_arguments_exit_2_with_no_aws_call(lab: Lab) -> None:
    lab.write_scenario(sc.backup_copy())
    for args in (
        ("--phase", "bogus"),
        ("--source-recovery-point-arn", "not-an-arn", "--retention-days", "7"),
        ("--source-recovery-point-arn", "arn:aws:s3:::bucket", "--retention-days", "7"),
        ("--retention-days", "7", "--bogus"),
    ):
        result = lab.run("04_backup_and_copy.sh", *args, env=NOW)
        assert result.rc == 2, args
    assert lab.calls() == []


# --------------------------------------------------------------------------
# 05
# --------------------------------------------------------------------------


def test_05_already_accepted_is_idempotent(lab: Lab) -> None:
    done = {"body": {"resourceShareInvitations": [sc.invitation(PRIMARY, status="ACCEPTED")]}}
    lab.write_scenario(
        sc.merged(
            sc.accept(),
            {"ram get-resource-share-invitations": done, "backup list-backup-vaults --by-shared": sc.shared_vault()},
        )
    )
    result = lab.run("05_accept_share.sh", "--apply", env=NOW)
    assert result.rc == 0, result.out + result.err
    assert calls_of(result.calls, "accept-resource-share-invitation") == []
    assert "was already accepted and the vault is visible" in result.out


def test_05_already_accepted_but_vault_missing_fails(lab: Lab) -> None:
    done = {"body": {"resourceShareInvitations": [sc.invitation(PRIMARY, status="ACCEPTED")]}}
    empty = {"body": {"BackupVaultList": []}}
    lab.write_scenario(
        sc.merged(
            sc.accept(), {"ram get-resource-share-invitations": done, "backup list-backup-vaults --by-shared": empty}
        )
    )
    result = lab.run("05_accept_share.sh", "--apply", env=NOW)
    assert result.rc == 1
    assert "is not in the shared list" in result.out


def test_05_no_invitation_and_no_vault_fails(lab: Lab) -> None:
    empty = {"body": {"resourceShareInvitations": []}}
    lab.write_scenario(
        sc.merged(
            sc.accept(),
            {
                "ram get-resource-share-invitations": empty,
                "backup list-backup-vaults --by-shared": {"body": {"BackupVaultList": []}},
            },
        )
    )
    result = lab.run("05_accept_share.sh", "--apply", env=NOW)
    assert result.rc == 1
    assert "no invitation" in result.out and "the vault is not visible" in result.out
    assert calls_of(result.calls, "accept-resource-share-invitation") == []


def test_05_no_invitation_but_vault_visible_passes(lab: Lab) -> None:
    empty = {"body": {"resourceShareInvitations": []}}
    lab.write_scenario(
        sc.merged(
            sc.accept(),
            {"ram get-resource-share-invitations": empty, "backup list-backup-vaults --by-shared": sc.shared_vault()},
        )
    )
    result = lab.run("05_accept_share.sh", "--apply", env=NOW)
    assert result.rc == 0, result.out + result.err
    assert "did not need an invitation" in result.out


def test_05_old_invitation_warns(lab: Lab) -> None:
    for now, expect_warning in (("2026-10-11T12:00:00Z", True), ("2026-10-11T11:30:00Z", False)):
        local = Lab(lab.tmp / f"age-{now[11:13]}")
        local.write_scenario(sc.accept())
        result = local.run("05_accept_share.sh", "--apply", env={"LAB_NOW": now})
        assert result.rc == 0, result.out + result.err
        assert ("--repair-share --apply" in result.out) is expect_warning
        assert ("expires after 12 hours" in result.out) is expect_warning


def test_05_vault_not_visible_after_accept_fails(lab: Lab) -> None:
    lab.write_scenario(
        sc.merged(sc.accept(), {"backup list-backup-vaults --by-shared": {"body": {"BackupVaultList": []}}})
    )
    result = lab.run("05_accept_share.sh", "--apply", env=NOW)
    assert result.rc == 1
    assert "did not appear in the shared list within 60 seconds" in result.out
    assert len(lab.sleeps()) == 60 // 5
    assert len(calls_of(result.calls, "accept-resource-share-invitation")) == 1


def test_05_a_foreign_invitation_is_ignored(lab: Lab) -> None:
    foreign = sc.invitation(PRIMARY)
    foreign["senderAccountId"] = "999988887777"
    lab.write_scenario(
        sc.merged(
            sc.accept(),
            {
                "ram get-resource-share-invitations": {"body": {"resourceShareInvitations": [foreign]}},
                "backup list-backup-vaults --by-shared": {"body": {"BackupVaultList": []}},
            },
        )
    )
    result = lab.run("05_accept_share.sh", "--apply", env=NOW)
    assert result.rc == 1
    assert calls_of(result.calls, "accept-resource-share-invitation") == []


def test_05_share_arn_option_skips_the_owner_read(lab: Lab) -> None:
    lab.write_scenario(sc.accept())
    result = lab.run("05_accept_share.sh", "--share-arn", sc.share_arn(PRIMARY), "--apply", env=NOW)
    assert result.rc == 0, result.out + result.err
    assert not [c for c in result.calls if c["profile"] == OWNER_PROFILE]


def test_05_a_stack_without_a_share_points_to_repair(lab: Lab) -> None:
    body = sc.lag_stack(PRIMARY)
    body["Stacks"][0]["Outputs"][2]["OutputValue"] = "not-shared"
    lab.write_scenario(sc.merged(sc.accept(), {"cloudformation describe-stacks": {"body": body}}))
    result = lab.run("05_accept_share.sh", "--apply", env=NOW)
    assert result.rc == 1
    assert "--repair-share --apply" in result.err
    assert calls_of(result.calls, "accept-resource-share-invitation") == []


def test_since_and_arn_arguments_are_validated(lab: Lab) -> None:
    lab.write_scenario(sc.accept())
    for args in (
        ("--share-arn", "not-an-arn"),
        ("--share-arn", "arn:aws:s3:::bucket"),
        ("--region", "eu-west-1"),
        ("--bogus",),
    ):
        assert lab.run("05_accept_share.sh", *args, env=NOW).rc == 2, args
    assert lab.calls() == []


# --------------------------------------------------------------------------
# The IMPACT block before every gate
# --------------------------------------------------------------------------


def _labels(text: str) -> list[str]:
    assert "=== IMPACT ===" in text
    return re.findall(r"^  - (.+?) : ", text.split("=== IMPACT ===", 1)[1], re.M)


def test_plan_impact_lines_02_deploy(lab: Lab) -> None:
    lab.write_scenario(sc.deploy_owner())
    owner = lab.run("02_deploy.sh", "--side", "owner")
    assert _labels(owner.out) == ["creates", "cost", "remains after teardown", "time"]
    assert "10_teardown.sh --delete-key" in owner.out
    assert "about 15 minutes" in owner.out and "observed once" in owner.out
    local = Lab(lab.tmp / "recipient")
    local.write_scenario(sc.deploy_recipient())
    recipient = local.run(
        "02_deploy.sh", "--side", "recipient", env={"LAB_RECIPIENT_EXISTING_FS_ID": sc.EXISTING_RECIPIENT_FS}
    )
    assert _labels(recipient.out) == ["creates", "cost", "remains after teardown", "time"]


def test_plan_impact_lines_03_deploy_lag_share(lab: Lab) -> None:
    lab.write_scenario(sc.deploy_lag())
    result = lab.run("03_deploy_lag_share.sh", "--retention-days", "12")
    assert _labels(result.out) == ["creates", "irreversible", "until", "shares to", "cost"]
    assert "retention is 12 days (minimum = maximum)" in result.out
    assert "cannot be changed after the vault is created" in result.out
    assert f"account {sc.RECIPIENT}" in result.out
    assert "not confirmed" in result.out


def test_plan_impact_lines_03_repair_share(lab: Lab) -> None:
    scenario = sc.merged(
        sc.deploy_lag(),
        {
            "cloudformation describe-stacks": {"body": sc.lag_stack(PRIMARY)},
            "backup list-backup-vaults": {"body": {"BackupVaultList": [{"BackupVaultName": sc.LAG_VAULT}]}},
        },
    )
    lab.write_scenario(scenario)
    result = lab.run("03_deploy_lag_share.sh", "--repair-share")
    assert _labels(result.out) == ["effect", "vault", "undo"]


def test_plan_impact_lines_04_backup_and_copy(lab: Lab) -> None:
    lab.write_scenario(sc.backup_copy(source_exists=True))
    result = lab.run("04_backup_and_copy.sh", "--retention-days", "7", env=NOW)
    assert _labels(result.out) == [
        "source recovery point",
        "destination vault",
        "expected earliest deletion",
        "cannot delete vault",
        "source KMS key",
        "cost",
    ]
    local = Lab(lab.tmp / "backup-only")
    local.write_scenario(sc.backup_copy())
    backup = local.run("04_backup_and_copy.sh", "--phase", "backup", env=NOW)
    assert _labels(backup.out) == ["source recovery point", "expires in"]
    assert "2 days" in backup.out and "needs no token" in backup.out
    assert "--confirm" not in backup.out


def test_plan_impact_lines_05_accept_share(lab: Lab) -> None:
    lab.write_scenario(sc.accept())
    result = lab.run("05_accept_share.sh", env=NOW)
    assert _labels(result.out) == ["effect", "reversible by", "invitation expires"]
    assert "09_revoke_share.sh" in result.out
    assert "valid for 12 hours" in result.out


def test_scripts_state_what_is_not_yet_run_on_real_environment() -> None:
    for name in ("02_deploy.sh", "03_deploy_lag_share.sh", "04_backup_and_copy.sh", "05_accept_share.sh"):
        text = Path(LAB_SRC / "scripts" / name).read_text(encoding="utf-8")
        assert "not yet run on real environment" in text, name
        assert not re.search(r"\bverified\b", text, re.I), name
