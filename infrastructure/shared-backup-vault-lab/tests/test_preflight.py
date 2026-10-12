"""01_preflight.sh: what it checks, what it refuses, and what it never calls."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import lab_scenarios as sc
import pytest
from lab_testlib import LAB_SRC, SENTINEL, Lab, assert_called

SCRIPT = "01_preflight.sh"
OWNER_PROFILE = sc.OWNER_PROFILE
RECIPIENT_PROFILE = sc.RECIPIENT_PROFILE


run01 = sc.run_preflight


# --------------------------------------------------------------------------
# The happy path and its calls
# --------------------------------------------------------------------------


def test_clean_environment_passes(lab: Lab) -> None:
    result = run01(lab, sc.preflight())
    assert result.rc == 0, result.out + result.err
    assert "Failed: 0" in result.out
    assert "digest=" in result.err
    calls = result.calls
    assert_called(calls, "sts", "get-caller-identity", profile=OWNER_PROFILE, region="ap-northeast-1", times=1)
    assert_called(calls, "sts", "get-caller-identity", profile=RECIPIENT_PROFILE, region="ap-northeast-1", times=1)
    assert_called(calls, "ec2", "describe-subnets", {"--subnet-ids": SENTINEL.SUBNET}, profile=OWNER_PROFILE)
    assert_called(
        calls, "ec2", "describe-subnets", {"--subnet-ids": SENTINEL.RECIPIENT_SUBNET}, profile=RECIPIENT_PROFILE
    )
    assert_called(calls, "kms", "describe-key", {"--key-id": "alias/shared-vault-lab-fs"}, profile=OWNER_PROFILE)
    assert_called(
        calls,
        "cloudformation",
        "describe-type",
        {"--type": "RESOURCE", "--type-name": "AWS::Backup::LogicallyAirGappedBackupVault"},
        profile=OWNER_PROFILE,
    )
    assert_called(calls, "backup", "list-backup-vaults", profile=RECIPIENT_PROFILE)
    assert any(c["service"] == "backup" and "--by-shared" in c["args"] for c in calls)
    assert lab.external_calls()[0].startswith("node --version")


def test_every_check_carries_an_item_id_and_the_run_is_recorded(lab: Lab) -> None:
    result = run01(lab, sc.preflight())
    assert result.rc == 0, result.out + result.err
    records = lab.records()
    checks = [r for r in records if r["event"].startswith("check_")]
    assert checks
    assert all(re.fullmatch(r"-|V[1-8]|E([1-9]|1[0-9]|2[0-6])", r["item"]) for r in checks)
    assert {r["item"] for r in checks} >= {"E16", "E17", "E18", "E19"}
    # 01 reads only, so its results count as a real run for the record.
    assert {r["mode"] for r in records} == {"apply"}


# --------------------------------------------------------------------------
# Tools (75) and required variables (78)
# --------------------------------------------------------------------------


def test_other_scripts_point_at_01_when_a_required_variable_is_empty(lab: Lab) -> None:
    result = lab.run("02_deploy.sh", "--side", "owner", env={"LAB_OWNER_PROFILE": ""})
    assert result.rc == 2
    assert "01_preflight.sh" in result.err


def test_01_python_version_below_3_9_exits_75(lab: Lab) -> None:
    fake_dir = lab.tools_dir
    # A python3 that fails the version probe only; every other use runs the real one.
    real = sys.executable
    lab.add_tool("python3", f'case "$*" in *version_info*) exit 1 ;; esac\nexec "{real}" "$@"')
    assert fake_dir.is_dir()
    result = run01(lab, sc.preflight())
    assert result.rc == 75
    assert "Python 3.9" in result.err
    assert lab.calls() == []


def test_01_node_below_minimum_exits_75(lab: Lab) -> None:
    lab.write_scenario(sc.preflight())
    lab.add_tool("node", "echo v18.17.0")
    lab.add_tool("npm", "echo 10.0.0")
    result = lab.run(SCRIPT)
    assert result.rc == 75
    assert "Node.js 20" in result.err


def test_01_missing_node_exits_75_for_recipient_and_both_but_not_owner(lab: Lab) -> None:
    lab.write_scenario(sc.preflight())
    for side in ("recipient", "both"):
        assert lab.run(SCRIPT, "--side", side).rc == 75
    owner_only = lab.run(SCRIPT, "--side", "owner")
    assert owner_only.rc == 0, owner_only.out + owner_only.err
    assert lab.external_calls() == []


def test_node_min_matches_getting_started() -> None:
    from_helper = json.loads(
        __import__("subprocess")
        .run(
            [sys.executable, str(LAB_SRC / "scripts/lib/lab_helpers.py"), "node-min-major"],
            capture_output=True,
            text=True,
            check=True,
        )
        .stdout
    )
    table = (LAB_SRC.parents[1] / "solutions/amplify-portal/docs/GETTING-STARTED.md").read_text(encoding="utf-8")
    match = re.search(r"\|\s*Node\.js\s*\|[^|]*\|\s*(\d+)\.x", table)
    assert match, "the prerequisites table no longer states a Node.js major version"
    assert from_helper == int(match.group(1))


def test_01_rejects_unknown_arguments_and_sides(lab: Lab) -> None:
    assert lab.run(SCRIPT, "--bogus").rc == 2
    assert lab.run(SCRIPT, "--side", "nobody").rc == 2
    assert lab.calls() == []


# --------------------------------------------------------------------------
# Accounts and SSO
# --------------------------------------------------------------------------


def test_account_mismatch_fails_with_78(lab: Lab) -> None:
    scenario = sc.merged(
        sc.preflight(),
        {
            f"sts get-caller-identity --profile={OWNER_PROFILE}": {
                "body": {"Account": "999988887777", "Arn": sc.SESSION_OWNER}
            }
        },
    )
    result = run01(lab, scenario)
    assert result.rc == 78
    assert "resolves to account 999988887777" in result.out


def test_sso_minutes_low_fails_and_enough_passes(lab: Lab) -> None:
    config = lab.home / ".aws" / "config"
    cache = lab.home / ".aws" / "sso" / "cache"
    cache.mkdir(parents=True)
    config.write_text(
        "[profile lab-owner]\nsso_session = lab\n[sso-session lab]\nsso_start_url = https://example.invalid/start\n",
        encoding="utf-8",
    )
    import hashlib

    name = hashlib.sha1(b"lab").hexdigest()  # noqa: S324 - the cache key botocore uses
    (cache / f"{name}.json").write_text(json.dumps({"expiresAt": "2026-10-11T00:10:00Z"}), encoding="utf-8")
    low = run01(lab, sc.preflight(), env={"LAB_NOW": "2026-10-11T00:00:00Z"})
    assert low.rc == 78
    assert "10 minutes left" in low.out
    (cache / f"{name}.json").write_text(json.dumps({"expiresAt": "2026-10-11T01:00:00Z"}), encoding="utf-8")
    ok = lab.run(SCRIPT, env={"LAB_NOW": "2026-10-11T00:00:00Z"})
    assert ok.rc == 0, ok.out + ok.err
    assert "60 minutes left" in ok.out


# --------------------------------------------------------------------------
# Subnets and security groups
# --------------------------------------------------------------------------


def test_01_security_group_in_the_same_vpc_passes(lab: Lab) -> None:
    result = run01(lab, sc.preflight(), env={"LAB_OWNER_SECURITY_GROUP_ID": SENTINEL.SG})
    assert result.rc == 0, result.out + result.err
    assert "owner security group is in the same VPC" in result.out


def test_01_missing_subnet_fails(lab: Lab) -> None:
    scenario = sc.merged(
        sc.preflight(),
        {f"ec2 describe-subnets --profile={OWNER_PROFILE}": sc.err("InvalidSubnetID.NotFound", "no such subnet")},
    )
    result = run01(lab, scenario)
    assert result.rc == 78
    assert f"owner subnet {SENTINEL.SUBNET} could not be read" in result.out


# --------------------------------------------------------------------------
# Recipient SVM budget
# --------------------------------------------------------------------------


def _svm_scenario(
    count: int, throughput: int = 128, deployment: str = "SINGLE_AZ_1", extra_fs: dict | None = None
) -> dict:
    fs = {
        "FileSystemId": sc.EXISTING_RECIPIENT_FS,
        "Lifecycle": "AVAILABLE",
        "NetworkType": "IPV4",
        "OntapConfiguration": {"DeploymentType": deployment, "ThroughputCapacity": throughput},
    }
    fs.update(extra_fs or {})
    return sc.merged(
        sc.preflight(),
        {
            "fsx describe-file-systems": {"body": {"FileSystems": [fs]}},
            "fsx describe-storage-virtual-machines": {
                "body": {"StorageVirtualMachines": [{"Name": f"svm_{i}"} for i in range(count)]}
            },
        },
    )


@pytest.mark.parametrize(
    ("count", "rc", "needle"),
    [
        (6, 78, "already holds 6 of 6 SVMs"),
        (5, 0, "fills the last slot"),
        (0, 0, "holds 0 of 6 SVMs: a slot is free"),
    ],
)
def test_01_svm_budget_first_generation_128(lab: Lab, count: int, rc: int, needle: str) -> None:
    result = run01(lab, _svm_scenario(count), env={"LAB_RECIPIENT_EXISTING_FS_ID": sc.EXISTING_RECIPIENT_FS})
    assert result.rc == rc, result.out + result.err
    assert needle in result.out
    assert_called(
        result.calls,
        "fsx",
        "describe-file-systems",
        {"--file-system-ids": sc.EXISTING_RECIPIENT_FS},
        profile=RECIPIENT_PROFILE,
    )
    assert_called(
        result.calls,
        "fsx",
        "describe-storage-virtual-machines",
        {"--filters": f"Name=file-system-id,Values={sc.EXISTING_RECIPIENT_FS}"},
        profile=RECIPIENT_PROFILE,
    )


def test_01_svm_budget_second_generation_row(lab: Lab) -> None:
    scenario = _svm_scenario(
        13,
        deployment="SINGLE_AZ_2",
        extra_fs={
            "OntapConfiguration": {"DeploymentType": "SINGLE_AZ_2", "ThroughputCapacityPerHAPair": 3072, "HAPairs": 1}
        },
    )
    result = run01(lab, scenario, env={"LAB_RECIPIENT_EXISTING_FS_ID": sc.EXISTING_RECIPIENT_FS})
    assert "holds 13 of 14 SVMs" in result.out, result.out
    assert "fills the last slot" in result.out


def test_01_svm_budget_configuration_not_in_the_table_needs_a_limit(lab: Lab) -> None:
    env = {"LAB_RECIPIENT_EXISTING_FS_ID": sc.EXISTING_RECIPIENT_FS}
    result = run01(lab, _svm_scenario(1, throughput=100), env=env)
    assert result.rc == 78
    assert "LAB_RECIPIENT_SVM_LIMIT" in result.out
    given = lab.run(SCRIPT, env={**env, "LAB_RECIPIENT_SVM_LIMIT": "6"})
    assert given.rc == 0, given.out + given.err
    assert "holds 1 of 6 SVMs" in given.out


def test_01_restore_svm_name_collision_fails(lab: Lab) -> None:
    scenario = sc.merged(
        _svm_scenario(1),
        {"fsx describe-storage-virtual-machines": {"body": {"StorageVirtualMachines": [{"Name": "svm_restore"}]}}},
    )
    result = run01(lab, scenario, env={"LAB_RECIPIENT_EXISTING_FS_ID": sc.EXISTING_RECIPIENT_FS})
    assert result.rc == 78
    assert "an SVM named svm_restore already exists" in result.out


def test_01_new_recipient_file_system_uses_the_table(lab: Lab) -> None:
    result = run01(lab, sc.preflight())
    assert "a new minimal recipient file system (128 MBps) allows 6 SVMs" in result.out


# --------------------------------------------------------------------------
# Name collisions
# --------------------------------------------------------------------------


def test_01_name_collisions_without_a_stack_fail(lab: Lab) -> None:
    owner_vaults = {
        "body": {
            "BackupVaultList": [
                {"BackupVaultName": sc.STD_VAULT, "BackupVaultArn": "x", "NumberOfRecoveryPoints": 0},
            ]
        }
    }
    cases = {
        "standard vault": ("backup list-backup-vaults !--by-shared", owner_vaults, "no owner-base stack owns it"),
        "alias": (
            "kms describe-key",
            {"body": {"KeyMetadata": {"KeyState": "Enabled"}}},
            "no owner-base stack owns it",
        ),
        "share": ("ram get-resource-shares", sc.share_list(sc.PRIMARY), "no stack owns it"),
    }
    for label, (key, response, needle) in cases.items():
        result = run01(lab, sc.merged(sc.preflight(), {key: response}))
        assert result.rc == 78, (label, result.out)
        assert needle in result.out, (label, result.out)


def test_01_existing_healthy_stacks_are_not_collisions(lab: Lab) -> None:
    scenario = sc.merged(
        sc.preflight(),
        {
            "cloudformation describe-stacks": {"body": sc.stack_body("x", "CREATE_COMPLETE")},
            "backup list-backup-vaults !--by-shared": {
                "body": {
                    "BackupVaultList": [
                        {"BackupVaultName": sc.STD_VAULT},
                        {"BackupVaultName": sc.LAG_VAULT, "NumberOfRecoveryPoints": 1},
                    ]
                }
            },
            "kms describe-key": {"body": {"KeyMetadata": {"KeyState": "Enabled"}}},
            "ram get-resource-shares": sc.share_list(sc.PRIMARY),
        },
    )
    result = run01(lab, scenario)
    assert result.rc == 0, result.out + result.err
    assert "created by the stack" in result.out


def test_01_failed_stack_state_fails_with_the_recovery_command(lab: Lab) -> None:
    scenario = sc.merged(
        sc.preflight(), {"cloudformation describe-stacks": {"body": sc.stack_body("x", "ROLLBACK_COMPLETE")}}
    )
    result = run01(lab, scenario)
    assert result.rc == 78
    assert "ROLLBACK_COMPLETE" in result.out
    assert "aws cloudformation delete-stack --stack-name shared-vault-lab-owner-base" in result.out


def test_01_retained_lag_vault_collision_reports_expiry(lab: Lab) -> None:
    scenario = sc.merged(
        sc.preflight(),
        {
            "backup list-backup-vaults !--by-shared": {
                "body": {"BackupVaultList": [{"BackupVaultName": sc.LAG_VAULT, "NumberOfRecoveryPoints": 2}]}
            },
            "backup list-recovery-points-by-backup-vault": {
                "body": {
                    "RecoveryPoints": [
                        {"RecoveryPointArn": "a", "CalculatedLifecycle": {"DeleteAt": "2026-10-18T01:00:00+00:00"}},
                        {"RecoveryPointArn": "b", "CalculatedLifecycle": {"DeleteAt": "2026-10-19T09:30:00+00:00"}},
                    ]
                }
            },
        },
    )
    result = run01(lab, scenario)
    assert result.rc == 78
    assert "retained air-gapped vault named shared-vault-lab-lag exists in ap-northeast-1 without a stack" in result.out
    assert "recovery points: 2" in result.out
    assert "latest expiry: 2026-10-19T09:30:00+00:00" in result.out
    assert "shared-vault-lab-2" in result.out
    assert_called(
        result.calls,
        "backup",
        "list-recovery-points-by-backup-vault",
        {"--backup-vault-name": sc.LAG_VAULT},
        profile=OWNER_PROFILE,
    )


def test_01_existence_check_uses_list_not_describe(lab: Lab) -> None:
    """describe-backup-vault stays unregistered (default deny): 01 must not need it."""
    scenario = sc.preflight()
    assert "backup describe-backup-vault" not in scenario
    result = run01(lab, scenario)
    assert result.rc == 0, result.out + result.err
    assert not [c for c in result.calls if c["subcommand"] == "describe-backup-vault"]


def test_default_names_follow_lab_tag(lab: Lab) -> None:
    result = run01(lab, sc.preflight(), env={"LAB_TAG": "other-tag"})
    assert result.rc == 0, result.out + result.err
    assert_called(result.calls, "kms", "describe-key", {"--key-id": "alias/other-tag-fs"})
    assert_called(
        result.calls,
        "cloudformation",
        "describe-stacks",
        {"--stack-name": "other-tag-owner-base"},
    )
    assert_called(result.calls, "ram", "get-resource-shares", {"--name": "other-tag-lag-share"})


# --------------------------------------------------------------------------
# CLI, Region availability, organization state
# --------------------------------------------------------------------------


def test_01_region_probe_outcomes(lab: Lab) -> None:
    cases = [
        (sc.err("TypeNotFoundException", "type not found"), 78, "was not found in ap-northeast-1"),
        (sc.err("AccessDenied", "denied"), 0, "could not be determined"),
    ]
    for response, rc, needle in cases:
        result = run01(lab, sc.merged(sc.preflight(), {"cloudformation describe-type": response}))
        assert result.rc == rc, result.out
        assert needle in result.out


def test_01_checks_the_second_region_too(lab: Lab) -> None:
    result = run01(lab, sc.preflight(), env={"LAB_SECOND_REGION": sc.SECOND})
    assert result.rc == 0, result.out + result.err
    assert_called(result.calls, "cloudformation", "describe-type", profile=OWNER_PROFILE, region=sc.SECOND, times=1)
    assert_called(result.calls, "cloudformation", "describe-type", profile=OWNER_PROFILE, region=sc.PRIMARY, times=1)
    assert "no second-Region recipient configuration" in result.out


def test_01_fsx_opt_in_is_a_warning(lab: Lab) -> None:
    for body, needle in (({"FSx": False}, "disabled"), ({}, "no Amazon FSx entry")):
        result = run01(
            lab,
            sc.merged(
                sc.preflight(), {"backup describe-region-settings": {"body": {"ResourceTypeOptInPreference": body}}}
            ),
        )
        assert result.rc == 0, result.out
        assert needle in result.out


def test_01_org_state_not_in_organization(lab: Lab) -> None:
    result = run01(lab, sc.preflight())
    assert "not in an organization" in result.out
    refused = run01(lab, sc.preflight(), env={"LAB_ALLOW_EXTERNAL_PRINCIPALS": "false"})
    assert refused.rc == 78
    assert "needs an organization" in refused.out


def test_01_org_state_management_and_member_accounts(lab: Lab) -> None:
    org = {"body": {"Organization": {"Id": "o-aaaaaaaaaa", "MasterAccountId": sc.OWNER}}}
    enabled = sc.merged(
        sc.preflight(),
        {
            "organizations describe-organization": org,
            "organizations list-aws-service-access-for-organization": {
                "body": {"EnabledServicePrincipals": [{"ServicePrincipal": "ram.amazonaws.com"}]}
            },
        },
    )
    assert "sharing with the organization is enabled" in run01(lab, enabled).out
    disabled = sc.merged(
        enabled, {"organizations list-aws-service-access-for-organization": {"body": {"EnabledServicePrincipals": []}}}
    )
    refused = run01(lab, disabled, env={"LAB_ALLOW_EXTERNAL_PRINCIPALS": "false"})
    assert refused.rc == 78
    assert "aws ram enable-sharing-with-aws-organization --profile <management-account-profile>" in refused.out
    member = sc.merged(
        sc.preflight(),
        {"organizations describe-organization": {"body": {"Organization": {"MasterAccountId": "999988887777"}}}},
    )
    member_out = run01(lab, member).out
    assert "cannot be read from here" in member_out


# --------------------------------------------------------------------------
# Permission simulation
# --------------------------------------------------------------------------


def test_01_permission_simulation_denied_action_names_the_operation(lab: Lab) -> None:
    denied = sc.simulation({"backup:StartCopyJob": "implicitDeny"})
    result = run01(lab, sc.merged(sc.preflight(), {"iam simulate-principal-policy": denied}))
    assert result.rc == 78
    assert "backup:StartCopyJob" in result.out
    assert "does not guarantee" in result.out


def test_01_permission_simulation_uses_the_role_arn_with_its_path(lab: Lab) -> None:
    result = run01(lab, sc.preflight())
    assert_called(result.calls, "iam", "get-role", {"--role-name": "OwnerRole"}, profile=OWNER_PROFILE)
    owner_call = next(
        c for c in result.calls if c["subcommand"] == "simulate-principal-policy" and c["profile"] == OWNER_PROFILE
    )
    assert owner_call["args"]["--policy-source-arn"] == [
        f"arn:aws:iam::{sc.OWNER}:role/aws-reserved/sso.amazonaws.com/OwnerRole"
    ]
    assert "backup:StartCopyJob" in owner_call["args"]["--action-names"]


def test_01_permission_check_refused_is_a_warning(lab: Lab) -> None:
    for key in ("iam get-role --profile=lab-owner", "iam simulate-principal-policy"):
        scenario = sc.merged(sc.preflight(), {key: sc.err("AccessDenied", "not allowed")})
        result = run01(lab, scenario)
        assert result.rc == 0, (key, result.out)
        assert "cannot be pre-checked" in result.out


def test_01_optional_actions_are_warnings_and_pass_role_is_a_warning(lab: Lab) -> None:
    denied = sc.simulation({"pricing:GetProducts": "implicitDeny", "iam:PassRole": "implicitDeny"})
    result = run01(lab, sc.merged(sc.preflight(), {"iam simulate-principal-policy": denied}))
    assert result.rc == 0, result.out
    assert "optional actions" in result.out and "pricing:GetProducts" in result.out
    assert "iam:PassRole shows as not allowed" in result.out


# --------------------------------------------------------------------------
# --estimate-cost
# --------------------------------------------------------------------------


def test_01_estimate_cost_reads_and_prints_only(lab: Lab) -> None:
    result = run01(lab, sc.merged(sc.preflight(), sc.preflight_estimate()), "--estimate-cost")
    assert result.rc == 0, result.out + result.err
    assert "2 USD values from 0.125 to 0.512 per unit" in result.out
    assert "the mapping of rows to this lab's resources is uncertain" in result.out
    assert_called(
        result.calls,
        "pricing",
        "get-products",
        {"--service-code": "AmazonFSx", "--filters": "Type=TERM_MATCH,Field=regionCode,Value=ap-northeast-1"},
        profile=OWNER_PROFILE,
        region="us-east-1",
        times=1,
    )
    assert_called(result.calls, "ce", "list-cost-allocation-tags", {"--tag-keys": "Project"}, profile=OWNER_PROFILE)


def test_01_estimate_cost_without_matching_rows_shows_no_figure(lab: Lab) -> None:
    scenario = sc.merged(sc.preflight(), sc.preflight_estimate(), {"pricing get-products": {"body": {"PriceList": []}}})
    result = run01(lab, scenario, "--estimate-cost")
    assert "no estimate is shown" in result.out
    assert "USD values" not in result.out


def test_01_estimate_cost_inactive_tag_prints_the_command_as_text(lab: Lab) -> None:
    scenario = sc.merged(
        sc.preflight(),
        sc.preflight_estimate(),
        {"ce list-cost-allocation-tags": {"body": {"CostAllocationTags": []}}},
    )
    result = run01(lab, scenario, "--estimate-cost")
    assert (
        "aws ce update-cost-allocation-tags-status --cost-allocation-tags-status TagKey=Project,Status=Active"
        in result.out
    )


def test_01_without_estimate_cost_makes_no_price_or_tag_call(lab: Lab) -> None:
    result = run01(lab, sc.preflight())
    assert not [c for c in result.calls if c["service"] in ("pricing", "ce")]


# --------------------------------------------------------------------------
# Side selection
# --------------------------------------------------------------------------


def test_01_owner_side_skips_the_recipient_account(lab: Lab) -> None:
    result = run01(lab, sc.preflight(), "--side", "owner", node=False)
    assert result.rc == 0, result.out + result.err
    assert not [c for c in result.calls if c["profile"] == RECIPIENT_PROFILE]


def test_01_recipient_side_skips_the_owner_account(lab: Lab) -> None:
    result = run01(lab, sc.preflight(), "--side", "recipient")
    assert result.rc == 0, result.out + result.err
    assert not [c for c in result.calls if c["profile"] == OWNER_PROFILE]


def test_01_makes_no_mutating_call(lab: Lab) -> None:
    result = run01(lab, sc.merged(sc.preflight(), sc.preflight_estimate()), "--estimate-cost")
    verbs = ("create", "delete", "put", "start", "update", "accept", "tag", "deploy", "schedule", "enable")
    assert not [c for c in result.calls if c["subcommand"].startswith(verbs)]


def test_01_status_line_and_language() -> None:
    lines = Path(LAB_SRC / "scripts" / SCRIPT).read_text(encoding="utf-8").splitlines()
    status_re = re.compile(
        r"^# Real-environment run: (not yet done|recorded (\[[VE]\d+\])+(; not recorded (\[[VE]\d+\])+)?)"
        r" \(status source: docs/verification-record\.md\)$"
    )
    assert status_re.match(lines[1]), lines[1]
