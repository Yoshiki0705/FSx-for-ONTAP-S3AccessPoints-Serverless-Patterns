"""Which Region each call of scripts 01-05 is sent to.

``--region`` means something different in each script: for 04 it picks the copy
DESTINATION, while the copy request itself is sent to the primary Region. The
table below is the contract; every test runs with ``LAB_SECOND_REGION`` set and
empty. Sending the copy to the source Region follows from the shape of the API
and is not yet run on real environment.
"""

from __future__ import annotations

from typing import Any

import lab_scenarios as sc
import pytest
from lab_testlib import Lab, assert_called

PRIMARY = sc.PRIMARY
SECOND = sc.SECOND
WITH_SECOND = {"LAB_SECOND_REGION": SECOND}
NOW = {"LAB_NOW": "2026-10-11T00:00:00Z"}


def regions_of(calls: list[dict[str, Any]], service: str, sub: str) -> list[str]:
    """The Regions a call was sent to, in order."""
    return [c["region"] for c in calls if c["service"] == service and c["subcommand"] == sub]


# --------------------------------------------------------------------------
# 01: every configured Region is read
# --------------------------------------------------------------------------


def test_01_reads_every_configured_region(lab: Lab) -> None:
    result = sc.run_preflight(lab, sc.preflight(), env=WITH_SECOND)
    assert result.rc == 0, result.out + result.err
    for service, sub in (
        ("cloudformation", "describe-type"),
        ("ram", "get-resource-shares"),
    ):
        assert regions_of(result.calls, service, sub) == [PRIMARY, SECOND], (service, sub)
    owner_vault_lists = [
        c["region"] for c in result.calls if c["subcommand"] == "list-backup-vaults" and "--by-shared" not in c["args"]
    ]
    assert owner_vault_lists == [PRIMARY, PRIMARY, SECOND]  # standard vault, then one list per Region
    # Resources that exist once are read in the primary Region only.
    assert set(regions_of(result.calls, "kms", "describe-key")) == {PRIMARY}
    assert set(regions_of(result.calls, "backup", "describe-region-settings")) == {PRIMARY}
    assert set(regions_of(result.calls, "organizations", "describe-organization")) == {PRIMARY}


def test_01_reads_only_the_primary_region_when_there_is_no_second(lab: Lab) -> None:
    result = sc.run_preflight(lab, sc.preflight())
    assert result.rc == 0, result.out + result.err
    assert {c["region"] for c in result.calls} == {PRIMARY}


def test_the_price_list_is_always_read_from_us_east_1(lab: Lab) -> None:
    """A fixed exception to the table: the price list endpoint exists in three Regions only."""
    for env in ({}, WITH_SECOND, {"LAB_PRIMARY_REGION": "eu-west-1"}):
        local = Lab(lab.tmp / f"price-{len(env)}-{env.get('LAB_PRIMARY_REGION', 'x')}")
        result = sc.run_preflight(local, sc.merged(sc.preflight(), sc.preflight_estimate()), "--estimate-cost", env=env)
        assert result.rc == 0, result.out + result.err
        assert regions_of(result.calls, "pricing", "get-products") == ["us-east-1"]


# --------------------------------------------------------------------------
# 02
# --------------------------------------------------------------------------


@pytest.mark.parametrize("env", [{}, WITH_SECOND], ids=["one-region", "two-regions"])
def test_02_owner_works_in_the_primary_region_only(lab: Lab, env: dict[str, str]) -> None:
    lab.write_scenario(sc.deploy_owner())
    result = lab.run("02_deploy.sh", "--side", "owner", "--apply", env=env)
    assert result.rc == 0, result.out + result.err
    assert {c["region"] for c in result.calls} == {PRIMARY}


def test_02_owner_refuses_the_second_region(lab: Lab) -> None:
    lab.write_scenario(sc.deploy_owner())
    result = lab.run("02_deploy.sh", "--side", "owner", "--region", SECOND, "--apply", env=WITH_SECOND)
    assert result.rc == 2
    assert "primary Region only" in result.err
    assert lab.calls() == []


def test_02_recipient_skips_a_second_region_without_its_own_configuration(lab: Lab) -> None:
    lab.write_scenario(sc.deploy_recipient())
    result = lab.run(
        "02_deploy.sh",
        "--side",
        "recipient",
        "--apply",
        env={**WITH_SECOND, "LAB_RECIPIENT_EXISTING_FS_ID": sc.EXISTING_RECIPIENT_FS},
    )
    assert result.rc == 0, result.out + result.err
    assert "no recipient configuration for ap-northeast-3" in result.out
    assert {c["region"] for c in result.calls} == {PRIMARY}
    assert len([c for c in result.calls if c["subcommand"] == "deploy"]) == 1


def test_02_recipient_deploys_both_regions_when_the_second_is_configured(lab: Lab) -> None:
    lab.write_scenario(sc.deploy_recipient())
    env = {
        **WITH_SECOND,
        "LAB_RECIPIENT_EXISTING_FS_ID": sc.EXISTING_RECIPIENT_FS,
        "LAB_SECOND_RECIPIENT_EXISTING_FS_ID": "fs-0aaaaaaaaaaaaaaaa",
    }
    result = lab.run("02_deploy.sh", "--side", "recipient", "--apply", env=env)
    assert result.rc == 0, result.out + result.err
    assert regions_of(result.calls, "cloudformation", "deploy") == [PRIMARY, SECOND]
    stacks = [c["args"]["--stack-name"][0] for c in result.calls if c["subcommand"] == "deploy"]
    assert stacks == [f"shared-vault-lab-recipient-{PRIMARY}", f"shared-vault-lab-recipient-{SECOND}"]
    second_deploy = [c for c in result.calls if c["subcommand"] == "deploy"][1]
    assert "ExistingFileSystemId=fs-0aaaaaaaaaaaaaaaa" in second_deploy["args"]["--parameter-overrides"]


def test_02_recipient_region_option_limits_the_run(lab: Lab) -> None:
    lab.write_scenario(sc.deploy_recipient())
    env = {
        **WITH_SECOND,
        "LAB_RECIPIENT_EXISTING_FS_ID": sc.EXISTING_RECIPIENT_FS,
        "LAB_SECOND_RECIPIENT_EXISTING_FS_ID": "fs-0aaaaaaaaaaaaaaaa",
    }
    result = lab.run("02_deploy.sh", "--side", "recipient", "--region", SECOND, "--apply", env=env)
    assert result.rc == 0, result.out + result.err
    assert regions_of(result.calls, "cloudformation", "deploy") == [SECOND]


# --------------------------------------------------------------------------
# 03
# --------------------------------------------------------------------------


def test_03_processes_every_configured_region_in_order(lab: Lab) -> None:
    lab.write_scenario(sc.deploy_lag())
    token = f"lock-7d-{sc.LAG_VAULT}@{PRIMARY}+{SECOND}"
    result = lab.run("03_deploy_lag_share.sh", "--retention-days", "7", "--apply", "--confirm", token, env=WITH_SECOND)
    assert result.rc == 0, result.out + result.err
    assert regions_of(result.calls, "cloudformation", "deploy") == [PRIMARY, SECOND]
    assert regions_of(result.calls, "backup", "describe-backup-vault") == [PRIMARY, SECOND]
    assert regions_of(result.calls, "ram", "get-resource-shares") == [PRIMARY, SECOND]


def test_03_region_option_limits_the_run(lab: Lab) -> None:
    lab.write_scenario(sc.deploy_lag())
    token = f"lock-7d-{sc.LAG_VAULT}@{SECOND}"
    result = lab.run(
        "03_deploy_lag_share.sh",
        "--retention-days",
        "7",
        "--region",
        SECOND,
        "--apply",
        "--confirm",
        token,
        env=WITH_SECOND,
    )
    assert result.rc == 0, result.out + result.err
    # The identity check (sts) is not Regional; every other call goes to the chosen Region.
    assert {c["region"] for c in result.calls if c["service"] != "sts"} == {SECOND}


def test_03_without_a_second_region_only_the_primary_is_used(lab: Lab) -> None:
    lab.write_scenario(sc.deploy_lag())
    result = lab.run(
        "03_deploy_lag_share.sh", "--retention-days", "7", "--apply", "--confirm", f"lock-7d-{sc.LAG_VAULT}@{PRIMARY}"
    )
    assert result.rc == 0, result.out + result.err
    assert {c["region"] for c in result.calls} == {PRIMARY}


# --------------------------------------------------------------------------
# 04: the API region column
# --------------------------------------------------------------------------


def test_04_start_copy_job_is_sent_to_source_region(lab: Lab) -> None:
    """The copy to a second Region is requested from the primary Region (the source); the destination is only in the vault ARN."""
    lab.write_scenario(sc.backup_copy(second_region=True))
    token = f"copy-7d-{sc.LAG_VAULT}@{SECOND}"
    result = lab.run(
        "04_backup_and_copy.sh",
        "--retention-days",
        "7",
        "--region",
        SECOND,
        "--apply",
        "--confirm",
        token,
        env={**NOW, **WITH_SECOND},
    )
    assert result.rc == 0, result.out + result.err
    assert_called(
        result.calls,
        "backup",
        "start-copy-job",
        {"--destination-backup-vault-arn": sc.lag_arn(SECOND), "--source-backup-vault-name": sc.STD_VAULT},
        profile=sc.OWNER_PROFILE,
        region=PRIMARY,
        times=1,
    )
    assert regions_of(result.calls, "backup", "start-backup-job") == [PRIMARY]
    assert regions_of(result.calls, "backup", "describe-copy-job") == [PRIMARY, PRIMARY]


def test_04_destination_state_is_read_in_the_destination_region(lab: Lab) -> None:
    lab.write_scenario(sc.backup_copy(second_region=True))
    token = f"copy-7d-{sc.LAG_VAULT}@{SECOND}"
    result = lab.run(
        "04_backup_and_copy.sh",
        "--retention-days",
        "7",
        "--region",
        SECOND,
        "--apply",
        "--confirm",
        token,
        env={**NOW, **WITH_SECOND},
    )
    assert result.rc == 0, result.out + result.err
    assert regions_of(result.calls, "backup", "describe-backup-vault") == [SECOND]
    lag_lists = [
        c["region"]
        for c in result.calls
        if c["subcommand"] == "list-recovery-points-by-backup-vault"
        and c["args"]["--backup-vault-name"] == [sc.LAG_VAULT]
    ]
    assert lag_lists == [SECOND]
    std_lists = [
        c["region"]
        for c in result.calls
        if c["subcommand"] == "list-recovery-points-by-backup-vault"
        and c["args"]["--backup-vault-name"] == [sc.STD_VAULT]
    ]
    assert set(std_lists) == {PRIMARY}
    # The copy jobs in progress are looked up in the source Region and in the destination Region.
    running = [
        c["region"]
        for c in result.calls
        if c["subcommand"] == "list-copy-jobs" and c["args"].get("--by-state") == ["RUNNING"]
    ]
    assert running == [PRIMARY, SECOND]
    created = [
        c["region"]
        for c in result.calls
        if c["subcommand"] == "list-copy-jobs" and c["args"].get("--by-state") == ["CREATED"]
    ]
    assert created == [PRIMARY, SECOND]
    # Earlier jobs of the source recovery point are read where the source lives.
    earlier = [
        c["region"]
        for c in result.calls
        if c["subcommand"] == "list-copy-jobs" and "--by-source-recovery-point-arn" in c["args"]
    ]
    assert earlier == [PRIMARY]


def test_04_same_region_destination_reads_the_copy_jobs_once(lab: Lab) -> None:
    lab.write_scenario(sc.backup_copy())
    result = lab.run(
        "04_backup_and_copy.sh",
        "--retention-days",
        "7",
        "--apply",
        "--confirm",
        f"copy-7d-{sc.LAG_VAULT}@{PRIMARY}",
        env=NOW,
    )
    assert result.rc == 0, result.out + result.err
    running = [
        c for c in result.calls if c["subcommand"] == "list-copy-jobs" and c["args"].get("--by-state") == ["RUNNING"]
    ]
    assert [c["region"] for c in running] == [PRIMARY]


def test_04_backup_is_always_taken_in_the_primary_region(lab: Lab) -> None:
    lab.write_scenario(sc.backup_copy(second_region=True))
    result = lab.run(
        "04_backup_and_copy.sh",
        "--retention-days",
        "7",
        "--region",
        SECOND,
        "--apply",
        "--confirm",
        f"copy-7d-{sc.LAG_VAULT}@{SECOND}",
        env={**NOW, **WITH_SECOND},
    )
    assert result.rc == 0, result.out + result.err
    assert regions_of(result.calls, "backup", "start-backup-job") == [PRIMARY]
    assert regions_of(result.calls, "backup", "describe-backup-job") == [PRIMARY, PRIMARY]


def test_04_default_destinations_are_every_configured_region(lab: Lab) -> None:
    lab.write_scenario(sc.backup_copy(second_region=True))
    token = f"copy-7d-{sc.LAG_VAULT}@{PRIMARY}+{SECOND}"
    result = lab.run(
        "04_backup_and_copy.sh", "--retention-days", "7", "--apply", "--confirm", token, env={**NOW, **WITH_SECOND}
    )
    assert result.rc == 0, result.out + result.err
    destinations = [
        c["args"]["--destination-backup-vault-arn"][0] for c in result.calls if c["subcommand"] == "start-copy-job"
    ]
    assert destinations == [sc.lag_arn(PRIMARY), sc.lag_arn(SECOND)]
    assert set(regions_of(result.calls, "backup", "start-copy-job")) == {PRIMARY}


# --------------------------------------------------------------------------
# 05
# --------------------------------------------------------------------------


def test_05_accepts_in_every_configured_region(lab: Lab) -> None:
    lab.write_scenario(sc.accept())
    result = lab.run("05_accept_share.sh", "--apply", env={**WITH_SECOND, "LAB_NOW": "2026-10-11T03:00:00Z"})
    assert result.rc == 0, result.out + result.err
    assert regions_of(result.calls, "ram", "accept-resource-share-invitation") == [PRIMARY, SECOND]
    assert regions_of(result.calls, "ram", "get-resource-share-invitations") == [PRIMARY, SECOND]


def test_05_region_option_limits_the_run(lab: Lab) -> None:
    lab.write_scenario(sc.accept())
    result = lab.run(
        "05_accept_share.sh", "--region", SECOND, "--apply", env={**WITH_SECOND, "LAB_NOW": "2026-10-11T03:00:00Z"}
    )
    assert result.rc == 0, result.out + result.err
    assert {c["region"] for c in result.calls if c["service"] == "ram"} == {SECOND}


# --------------------------------------------------------------------------
# A Region that is neither the primary nor the second
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        ("02_deploy.sh", "--side", "recipient", "--region", "eu-west-1"),
        ("03_deploy_lag_share.sh", "--retention-days", "7", "--region", "eu-west-1"),
        ("04_backup_and_copy.sh", "--retention-days", "7", "--region", "eu-west-1"),
        ("05_accept_share.sh", "--region", "eu-west-1"),
        ("03_deploy_lag_share.sh", "--retention-days", "7", "--region", SECOND),
    ],
    ids=["02", "03", "04", "05", "03-second-not-configured"],
)
def test_a_region_that_is_not_configured_exits_2_with_no_aws_call(lab: Lab, argv: tuple[str, ...]) -> None:
    lab.write_scenario(sc.deploy_lag())
    result = lab.run(*argv)
    assert result.rc == 2, result.out + result.err
    assert "--region must be LAB_PRIMARY_REGION" in result.err
    assert lab.calls() == []
