"""Plan mode, --apply and the confirmation token of the state-changing scripts 02-05 and 08-10.

Every state-changing script prints a plan and exits 10 without --apply. The two
irreversible steps (03 creates the air-gapped vault, 04 copies into it) also need
``--confirm`` with the exact token printed in the plan. The token is accepted only
as an argument: an environment variable is not a confirmation.
"""

from __future__ import annotations

from typing import Any

import lab_scenarios as sc
import lab_scenarios_ops as ops
import pytest
from lab_testlib import Lab, assert_called

PRIMARY = sc.PRIMARY
SECOND = sc.SECOND
TOKEN_03 = f"lock-7d-{sc.LAG_VAULT}@{PRIMARY}"
TOKEN_04 = f"copy-7d-{sc.LAG_VAULT}@{PRIMARY}"
NOW = {"LAB_NOW": "2026-10-11T00:00:00Z"}
mutating = sc.mutating
calls_of = sc.calls_of


PLANS = {
    "02-owner": (sc.deploy_owner, ("02_deploy.sh", "--side", "owner"), {}),
    "02-recipient": (
        sc.deploy_recipient,
        ("02_deploy.sh", "--side", "recipient"),
        {"LAB_RECIPIENT_EXISTING_FS_ID": sc.EXISTING_RECIPIENT_FS},
    ),
    "03-create": (sc.deploy_lag, ("03_deploy_lag_share.sh", "--retention-days", "7"), {}),
    "04-all": (sc.backup_copy, ("04_backup_and_copy.sh", "--retention-days", "7"), NOW),
    "04-backup": (sc.backup_copy, ("04_backup_and_copy.sh", "--phase", "backup"), NOW),
    "05": (sc.accept, ("05_accept_share.sh",), {"LAB_NOW": "2026-10-11T03:00:00Z"}),
    "08-cli": (ops.restore, ("08_restore.sh",), {}),
    "09": (ops.revoke, ("09_revoke_share.sh",), {}),
    "10": (ops.teardown, ("10_teardown.sh",), {}),
    "10-delete-key": (ops.teardown, ("10_teardown.sh", "--delete-key"), {}),
}


@pytest.mark.parametrize("name", sorted(PLANS))
def test_plan_mode_exits_10_and_records_no_mutating_call(lab: Lab, name: str) -> None:
    builder, argv, env = PLANS[name]
    lab.write_scenario(builder())
    result = lab.run(*argv, env=env)
    assert result.rc == 10, result.out + result.err
    assert "PLAN ONLY: no AWS state was changed" in result.out
    assert mutating(result.calls) == []
    assert result.calls, "the plan should have read the current state"


def test_03_plan_mode_prints_the_token_and_the_full_command(lab: Lab) -> None:
    lab.write_scenario(sc.deploy_lag())
    result = lab.run("03_deploy_lag_share.sh", "--retention-days", "7")
    assert result.rc == 10
    assert f"--retention-days 7 --apply --confirm {TOKEN_03}" in result.out


def test_04_plan_mode_prints_the_token_and_the_full_command(lab: Lab) -> None:
    lab.write_scenario(sc.backup_copy())
    result = lab.run("04_backup_and_copy.sh", "--retention-days", "7", env=NOW)
    assert result.rc == 10
    assert f"--phase all --retention-days 7 --apply --confirm {TOKEN_04}" in result.out


# --------------------------------------------------------------------------
# 03: --apply needs the exact token
# --------------------------------------------------------------------------


def test_03_apply_without_token_refuses_and_shows_the_token(lab: Lab) -> None:
    lab.write_scenario(sc.deploy_lag())
    result = lab.run("03_deploy_lag_share.sh", "--retention-days", "7", "--apply")
    assert result.rc == 1
    assert f"--confirm {TOKEN_03}" in result.err
    assert mutating(result.calls) == []


@pytest.mark.parametrize(
    "token",
    [
        TOKEN_03[:-1] + "2",
        TOKEN_03.replace("7d", "8d"),
        TOKEN_03.replace(sc.LAG_VAULT, "other-vault"),
        TOKEN_03 + "+" + SECOND,
        "",
        TOKEN_03.upper(),
        " " + TOKEN_03,
    ],
)
def test_03_wrong_token_refuses(lab: Lab, token: str) -> None:
    lab.write_scenario(sc.deploy_lag())
    result = lab.run("03_deploy_lag_share.sh", "--retention-days", "7", "--apply", "--confirm", token)
    assert result.rc == 1
    assert f"--confirm {TOKEN_03}" in result.err
    assert mutating(result.calls) == []


def test_03_env_var_is_not_a_confirmation(lab: Lab) -> None:
    lab.write_scenario(sc.deploy_lag())
    env = {name: TOKEN_03 for name in ("LAB_CONFIRM", "CONFIRM", "_LAB_CONFIRM", "LAB_CONFIRM_TOKEN", "confirm")}
    result = lab.run("03_deploy_lag_share.sh", "--retention-days", "7", "--apply", env=env)
    assert result.rc == 1
    assert mutating(result.calls) == []


def test_03_correct_token_deploys_once(lab: Lab) -> None:
    lab.write_scenario(sc.deploy_lag())
    result = lab.run("03_deploy_lag_share.sh", "--retention-days", "7", "--apply", "--confirm", TOKEN_03)
    assert result.rc == 0, result.out + result.err
    assert len(calls_of(result.calls, "deploy")) == 1
    assert_called(
        result.calls,
        "cloudformation",
        "deploy",
        {
            "--parameter-overrides": [
                "LabTag=shared-vault-lab",
                f"LagVaultName={sc.LAG_VAULT}",
                f"ShareName={sc.SHARE_NAME}",
                "RetentionDays=7",
                "AcknowledgeRetentionDays=7",
                f"RecipientAccountId={sc.RECIPIENT}",
                "AllowExternalPrincipals=true",
                "ShareEnabled=true",
            ]
        },
        profile=sc.OWNER_PROFILE,
        times=1,
    )


def test_03_token_regions_follow_the_configured_regions(lab: Lab) -> None:
    lab.write_scenario(sc.deploy_lag())
    both = lab.run("03_deploy_lag_share.sh", "--retention-days", "7", env={"LAB_SECOND_REGION": SECOND})
    assert f"--confirm lock-7d-{sc.LAG_VAULT}@{PRIMARY}+{SECOND}" in both.out
    one = lab.run(
        "03_deploy_lag_share.sh", "--retention-days", "7", "--region", SECOND, env={"LAB_SECOND_REGION": SECOND}
    )
    assert f"--confirm lock-7d-{sc.LAG_VAULT}@{SECOND}" in one.out
    assert f"@{PRIMARY}" not in one.out.split("--confirm")[-1]
    single = lab.run("03_deploy_lag_share.sh", "--retention-days", "7")
    assert f"@{PRIMARY}" in single.out and "+" not in single.out.split("--confirm")[-1]


def test_03_token_for_two_regions_deploys_both_in_order(lab: Lab) -> None:
    lab.write_scenario(sc.deploy_lag())
    token = f"lock-7d-{sc.LAG_VAULT}@{PRIMARY}+{SECOND}"
    result = lab.run(
        "03_deploy_lag_share.sh",
        "--retention-days",
        "7",
        "--apply",
        "--confirm",
        token,
        env={"LAB_SECOND_REGION": SECOND},
    )
    assert result.rc == 0, result.out + result.err
    regions = [c["region"] for c in calls_of(result.calls, "deploy")]
    assert regions == [PRIMARY, SECOND]
    # The token of one Region is refused when two Regions are configured.
    refused = lab.run(
        "03_deploy_lag_share.sh",
        "--retention-days",
        "7",
        "--apply",
        "--confirm",
        TOKEN_03,
        env={"LAB_SECOND_REGION": SECOND},
    )
    assert refused.rc == 1


def test_03_repair_share_needs_no_token(lab: Lab) -> None:
    scenario = sc.deploy_lag()
    scenario["cloudformation describe-stacks"] = {"body": sc.lag_stack(PRIMARY)}
    scenario["backup list-backup-vaults"] = {"body": {"BackupVaultList": [{"BackupVaultName": sc.LAG_VAULT}]}}
    lab.write_scenario(scenario)
    plan = lab.run("03_deploy_lag_share.sh", "--repair-share")
    assert plan.rc == 10 and mutating(plan.calls) == []
    applied = lab.run("03_deploy_lag_share.sh", "--repair-share", "--apply")
    assert applied.rc == 0, applied.out + applied.err
    assert len(calls_of(applied.calls, "deploy")) == 2


@pytest.mark.parametrize("value", [None, "", "abc", "6", "36", "7.5", "-7", "07x"])
def test_03_retention_days_missing_or_out_of_range_exits_2_with_no_aws_call(lab: Lab, value: str | None) -> None:
    lab.write_scenario(sc.deploy_lag())
    args = ["03_deploy_lag_share.sh", "--apply"]
    if value is not None:
        args += ["--retention-days", value]
    result = lab.run(*args)
    assert result.rc == 2, result.out + result.err
    assert lab.calls() == []


def test_03_repair_share_and_retention_days_do_not_mix(lab: Lab) -> None:
    result = lab.run("03_deploy_lag_share.sh", "--repair-share", "--retention-days", "7")
    assert result.rc == 2
    assert lab.calls() == []


# --------------------------------------------------------------------------
# 04: copy needs the token; the backup phase does not
# --------------------------------------------------------------------------


def test_04_apply_without_token_refuses_and_shows_the_token(lab: Lab) -> None:
    lab.write_scenario(sc.backup_copy())
    result = lab.run("04_backup_and_copy.sh", "--retention-days", "7", "--apply", env=NOW)
    assert result.rc == 1
    assert f"--confirm {TOKEN_04}" in result.err
    assert mutating(result.calls) == []


@pytest.mark.parametrize(
    "token",
    [TOKEN_04[:-1] + "2", TOKEN_04.replace("copy", "lock"), TOKEN_04.replace("7d", "8d"), "", TOKEN_04.upper()],
)
def test_04_wrong_token_refuses(lab: Lab, token: str) -> None:
    lab.write_scenario(sc.backup_copy())
    result = lab.run("04_backup_and_copy.sh", "--retention-days", "7", "--apply", "--confirm", token, env=NOW)
    assert result.rc == 1
    assert f"--confirm {TOKEN_04}" in result.err
    assert calls_of(result.calls, "start-copy-job") == []
    assert calls_of(result.calls, "start-backup-job") == []


def test_04_env_var_is_not_a_confirmation(lab: Lab) -> None:
    lab.write_scenario(sc.backup_copy())
    env = {**NOW, **{name: TOKEN_04 for name in ("LAB_CONFIRM", "CONFIRM", "_LAB_CONFIRM", "confirm")}}
    result = lab.run("04_backup_and_copy.sh", "--retention-days", "7", "--apply", env=env)
    assert result.rc == 1
    assert mutating(result.calls) == []


def test_04_all_phase_wrong_token_aborts_before_start_backup_job(lab: Lab) -> None:
    """The backup takes minutes; a wrong token must be refused before it starts."""
    lab.write_scenario(sc.backup_copy())
    result = lab.run(
        "04_backup_and_copy.sh",
        "--phase",
        "all",
        "--retention-days",
        "7",
        "--apply",
        "--confirm",
        "copy-7d-wrong@x",
        env=NOW,
    )
    assert result.rc == 1
    assert calls_of(result.calls, "start-backup-job") == []
    assert calls_of(result.calls, "start-copy-job") == []
    assert lab.sleeps() == []


def test_04_correct_token_calls_once(lab: Lab) -> None:
    lab.write_scenario(sc.backup_copy())
    result = lab.run("04_backup_and_copy.sh", "--retention-days", "7", "--apply", "--confirm", TOKEN_04, env=NOW)
    assert result.rc == 0, result.out + result.err
    assert len(calls_of(result.calls, "start-copy-job")) == 1
    assert len(calls_of(result.calls, "start-backup-job")) == 1
    assert_called(
        result.calls,
        "backup",
        "start-copy-job",
        {
            "--lifecycle": "DeleteAfterDays=7",
            "--recovery-point-arn": sc.SRC_RP,
            "--source-backup-vault-name": sc.STD_VAULT,
            "--destination-backup-vault-arn": sc.lag_arn(PRIMARY),
            "--iam-role-arn": sc.ROLE_ARN,
        },
        profile=sc.OWNER_PROFILE,
        times=1,
    )


def test_04_backup_phase_needs_no_token(lab: Lab) -> None:
    lab.write_scenario(sc.backup_copy())
    result = lab.run("04_backup_and_copy.sh", "--phase", "backup", "--apply", env=NOW)
    assert result.rc == 0, result.out + result.err
    assert len(calls_of(result.calls, "start-backup-job")) == 1
    assert calls_of(result.calls, "start-copy-job") == []


def test_04_copy_phase_with_token_starts_no_backup(lab: Lab) -> None:
    lab.write_scenario(sc.backup_copy(source_exists=True))
    result = lab.run(
        "04_backup_and_copy.sh", "--phase", "copy", "--retention-days", "7", "--apply", "--confirm", TOKEN_04, env=NOW
    )
    assert result.rc == 0, result.out + result.err
    assert calls_of(result.calls, "start-backup-job") == []
    assert len(calls_of(result.calls, "start-copy-job")) == 1


def test_04_token_regions_follow_the_configured_regions(lab: Lab) -> None:
    lab.write_scenario(sc.backup_copy(second_region=True))
    env = {**NOW, "LAB_SECOND_REGION": SECOND}
    both = lab.run("04_backup_and_copy.sh", "--retention-days", "7", env=env)
    assert both.rc == 10, both.out + both.err
    assert f"--confirm copy-7d-{sc.LAG_VAULT}@{PRIMARY}+{SECOND}" in both.out
    one = lab.run("04_backup_and_copy.sh", "--retention-days", "7", "--region", SECOND, env=env)
    assert one.rc == 10, one.out + one.err
    assert f"--confirm copy-7d-{sc.LAG_VAULT}@{SECOND}" in one.out
    single = lab.run("04_backup_and_copy.sh", "--retention-days", "7", env=NOW)
    assert f"--confirm {TOKEN_04}" in single.out


@pytest.mark.parametrize("value", [None, "", "abc", "6", "36", "7.5"])
def test_04_retention_days_missing_or_out_of_range_exits_2_with_no_aws_call(lab: Lab, value: str | None) -> None:
    lab.write_scenario(sc.backup_copy())
    args = ["04_backup_and_copy.sh", "--phase", "all", "--apply"]
    if value is not None:
        args += ["--retention-days", value]
    result = lab.run(*args, env=NOW)
    assert result.rc == 2, result.out + result.err
    assert lab.calls() == []


# --------------------------------------------------------------------------
# 02 and 05 change state without a token
# --------------------------------------------------------------------------


def test_02_apply_deploys_without_a_token(lab: Lab) -> None:
    lab.write_scenario(sc.deploy_owner())
    result = lab.run("02_deploy.sh", "--side", "owner", "--apply")
    assert result.rc == 0, result.out + result.err
    assert len(calls_of(result.calls, "deploy")) == 1


def test_05_apply_accepts_exactly_one_invitation(lab: Lab) -> None:
    lab.write_scenario(sc.accept())
    result = lab.run("05_accept_share.sh", "--apply", env={"LAB_NOW": "2026-10-11T03:00:00Z"})
    assert result.rc == 0, result.out + result.err
    assert len(calls_of(result.calls, "accept-resource-share-invitation")) == 1


# --------------------------------------------------------------------------
# 08, 09: plan first; no token (a restore adds a volume, a revoke can be undone)
# --------------------------------------------------------------------------


def test_08_apply_restores_without_a_token(lab: Lab) -> None:
    lab.write_scenario(ops.restore())
    result = lab.run("08_restore.sh", "--apply")
    assert result.rc == 0, result.out + result.err
    assert len(calls_of(result.calls, "start-restore-job")) == 1


def test_09_apply_revokes_without_a_token(lab: Lab) -> None:
    lab.write_scenario(ops.revoke())
    result = lab.run("09_revoke_share.sh", "--apply")
    assert result.rc == 0, result.out + result.err
    assert len(calls_of(result.calls, "delete-resource-share")) == 1


# --------------------------------------------------------------------------
# 10: --apply deletes; --delete-key needs the exact token
# --------------------------------------------------------------------------

TOKEN_10 = ops.DELETE_KEY_TOKEN


def test_10_delete_key_plan_prints_the_token_and_the_full_command(lab: Lab) -> None:
    lab.write_scenario(ops.teardown())
    result = lab.run("10_teardown.sh", "--delete-key")
    assert result.rc == 10
    assert TOKEN_10 == "delete-key-alias/shared-vault-lab-fs"
    assert f"./scripts/10_teardown.sh --apply --delete-key --confirm {TOKEN_10}" in result.out


@pytest.mark.parametrize(
    "confirm",
    [None, "", "delete-key-alias/other-fs", "delete-key-shared-vault-lab-fs", "delete-key-alias/shared-vault-lab-fs "],
)
def test_10_delete_key_without_the_right_token_changes_nothing(lab: Lab, confirm: str | None) -> None:
    lab.write_scenario(ops.teardown())
    args = ["--apply", "--delete-key"] + (["--confirm", confirm] if confirm is not None else [])
    result = lab.run("10_teardown.sh", *args)
    assert result.rc == 1
    assert f"--confirm {TOKEN_10}" in result.err
    assert mutating(result.calls) == []
    assert not calls_of(result.calls, "schedule-key-deletion")


def test_10_token_in_the_environment_is_not_a_confirmation(lab: Lab) -> None:
    lab.write_scenario(ops.teardown())
    result = lab.run("10_teardown.sh", "--apply", "--delete-key", env={"LAB_CONFIRM": TOKEN_10, "CONFIRM": TOKEN_10})
    assert result.rc == 1
    assert mutating(result.calls) == []


def test_10_apply_without_delete_key_never_schedules_the_key(lab: Lab) -> None:
    lab.write_scenario(ops.teardown())
    result = lab.run("10_teardown.sh", "--apply")
    assert result.rc == 0, result.out + result.err
    assert not calls_of(result.calls, "schedule-key-deletion")
    assert len(calls_of(result.calls, "delete-volume")) == 2


def test_10_confirm_without_delete_key_is_a_usage_error(lab: Lab) -> None:
    lab.write_scenario(ops.teardown())
    result = lab.run("10_teardown.sh", "--apply", "--confirm", TOKEN_10)
    assert result.rc == 2
    assert result.calls == []
