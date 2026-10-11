"""What scripts 01-05 actually call, with the VALUES they pass.

``EXPECTED_CALLS`` is keyed by the scripts found on disk. Each row names the literal
call site in the script (``aws_owner backup start-copy-job``), the profile and
Region, and the exact flag values (sentinels: an id where an id belongs, a name
where a name belongs). Three kinds of check bind it to the scripts:

* the success run records every row (``test_script_calls_match_expected``);
* a script that only *prints* the commands records nothing, so it fails
  (``test_echo_only_script_is_rejected``);
* replacing any one real call with ``echo`` makes the success run fail
  (``test_echo_substitution_fails_every_script``).

A script that is added without rows fails ``test_every_script_has_expected_calls``.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import botocore.session
import lab_scenarios as sc
import pytest
import yaml
from botocore import xform_name
from lab_testlib import LAB_SRC, SENTINEL, Lab, Result, assert_called, substitute_with_echo

SCRIPTS_DIR = LAB_SRC / "scripts"
PRIMARY = sc.PRIMARY
OWNER = sc.OWNER_PROFILE
RECIPIENT = sc.RECIPIENT_PROFILE
PINNED_NOW = "2026-10-11T00:00:00Z"

helpers = sc.helpers


@dataclass(frozen=True)
class Row:
    """One expected call."""

    run: str
    literal: str
    service: str = ""
    sub: str = ""
    flags: dict[str, Any] = field(default_factory=dict)
    profile: str | None = None
    region: str | None = PRIMARY
    kind: str = "aws"


def aws(run: str, literal: str, flags: dict[str, Any] | None = None, region: str | None = PRIMARY) -> Row:
    """A row for a literal ``aws_owner|aws_recipient <service> <sub>`` call site."""
    prefix, service, sub = literal.split()
    profile = OWNER if prefix == "aws_owner" else RECIPIENT
    return Row(run, literal, service, sub, flags or {}, profile, region)


def ext(run: str, literal: str, needle: str) -> Row:
    """A row for a ``run_external`` call site; ``needle`` must appear in the external log."""
    return Row(run, literal, flags={"needle": needle}, kind="external")


TEMPLATE_OWNER_BASE = "{root}/cloudformation/owner-base.yaml"
TEMPLATE_RECIPIENT = "{root}/cloudformation/recipient-restore.yaml"
TEMPLATE_LAG = "{root}/cloudformation/owner-lag-share.yaml"
OWNER_BASE_PARAMS = [
    "LabTag=shared-vault-lab",
    f"SubnetId={SENTINEL.SUBNET}",
    "SecurityGroupId=",
    "StorageCapacityGiB=1024",
    "ThroughputCapacity=128",
    "SvmName=svm_lab",
    "VolumeName=vol_lab",
    "VolumeSizeMB=1024",
    f"StandardVaultName={sc.STD_VAULT}",
]
RECIPIENT_PARAMS = [
    "LabTag=shared-vault-lab",
    f"ExistingFileSystemId={sc.EXISTING_RECIPIENT_FS}",
    f"SubnetId={SENTINEL.RECIPIENT_SUBNET}",
    "SecurityGroupId=",
    "ThroughputCapacity=128",
    "RestoreSvmName=svm_restore",
]
TAGS = ["Project=shared-vault-lab", "Cleanup=delete-when-done"]


def lag_params(enabled: str = "true", days: str = "7") -> list[str]:
    """The parameter overrides 03 sends."""
    return [
        "LabTag=shared-vault-lab",
        f"LagVaultName={sc.LAG_VAULT}",
        f"ShareName={sc.SHARE_NAME}",
        f"RetentionDays={days}",
        f"AcknowledgeRetentionDays={days}",
        f"RecipientAccountId={sc.RECIPIENT}",
        "AllowExternalPrincipals=true",
        f"ShareEnabled={enabled}",
    ]


def backup_token() -> str:
    """The idempotency token 04 derives for the backup (the clock is pinned)."""
    return helpers.text_digest([sc.VOLUME_ARN, sc.STD_VAULT, PINNED_NOW])


def copy_token() -> str:
    """The idempotency token 04 derives for the copy."""
    return helpers.text_digest([sc.SRC_RP, sc.lag_arn(PRIMARY), "7"])


EXPECTED_CALLS: dict[str, list[Row]] = {
    "01_preflight.sh": [
        aws("all", "aws_owner sts get-caller-identity"),
        aws("all", "aws_recipient sts get-caller-identity"),
        aws("all", "aws_owner ec2 describe-subnets", {"--subnet-ids": SENTINEL.SUBNET}),
        aws("all", "aws_recipient ec2 describe-subnets", {"--subnet-ids": SENTINEL.RECIPIENT_SUBNET}),
        aws("all", "aws_owner cloudformation describe-stacks", {"--stack-name": "shared-vault-lab-owner-base"}),
        aws("all", "aws_owner cloudformation describe-stacks", {"--stack-name": f"shared-vault-lab-lag-{PRIMARY}"}),
        aws(
            "all",
            "aws_recipient cloudformation describe-stacks",
            {"--stack-name": f"shared-vault-lab-recipient-{PRIMARY}"},
        ),
        aws("all", "aws_owner backup list-backup-vaults"),
        aws("all", "aws_owner kms describe-key", {"--key-id": "alias/shared-vault-lab-fs"}),
        aws("all", "aws_owner backup describe-region-settings"),
        aws(
            "all",
            "aws_owner cloudformation describe-type",
            {"--type": "RESOURCE", "--type-name": "AWS::Backup::LogicallyAirGappedBackupVault"},
        ),
        aws(
            "all",
            "aws_owner ram get-resource-shares",
            {"--resource-owner": "SELF", "--name": sc.SHARE_NAME, "--resource-share-status": "ACTIVE"},
        ),
        aws("all", "aws_owner organizations describe-organization"),
        aws("all", "aws_recipient backup list-backup-vaults", {"--by-shared": []}),
        aws("all", "aws_owner iam get-role", {"--role-name": "OwnerRole"}),
        aws("all", "aws_recipient iam get-role", {"--role-name": "RecipientRole"}),
        aws(
            "all",
            "aws_owner iam simulate-principal-policy",
            {"--policy-source-arn": f"arn:aws:iam::{sc.OWNER}:role/aws-reserved/sso.amazonaws.com/OwnerRole"},
        ),
        aws(
            "all",
            "aws_recipient iam simulate-principal-policy",
            {"--policy-source-arn": f"arn:aws:iam::{sc.RECIPIENT}:role/aws-reserved/sso.amazonaws.com/RecipientRole"},
        ),
        aws(
            "all",
            "aws_owner pricing get-products",
            {"--service-code": "AmazonFSx", "--filters": f"Type=TERM_MATCH,Field=regionCode,Value={PRIMARY}"},
            region="us-east-1",
        ),
        aws("all", "aws_owner ce list-cost-allocation-tags", {"--tag-keys": "Project"}),
        ext("all", "run_external node", "node --version"),
    ],
    "02_deploy.sh": [
        aws("owner", "aws_owner sts get-caller-identity"),
        aws("owner", "aws_owner cloudformation describe-stacks", {"--stack-name": "shared-vault-lab-owner-base"}),
        aws(
            "owner",
            "aws_owner cloudformation deploy",
            {
                "--template-file": TEMPLATE_OWNER_BASE,
                "--stack-name": "shared-vault-lab-owner-base",
                "--capabilities": "CAPABILITY_IAM",
                "--parameter-overrides": OWNER_BASE_PARAMS,
                "--tags": TAGS,
                "--no-fail-on-empty-changeset": [],
            },
        ),
        aws("owner", "aws_owner fsx describe-file-systems", {"--file-system-ids": SENTINEL.FS}),
        aws(
            "owner", "aws_owner fsx describe-storage-virtual-machines", {"--storage-virtual-machine-ids": SENTINEL.SVM}
        ),
        aws("owner", "aws_owner fsx describe-volumes", {"--volume-ids": SENTINEL.VOLUME}),
        aws("owner", "aws_owner fsx list-tags-for-resource", {"--resource-arn": sc.FS_ARN}),
        aws("owner", "aws_owner fsx list-tags-for-resource", {"--resource-arn": sc.SVM_ARN}),
        aws("owner", "aws_owner fsx list-tags-for-resource", {"--resource-arn": sc.VOLUME_ARN}),
        aws("owner", "aws_owner kms describe-key", {"--key-id": "alias/shared-vault-lab-fs"}),
        aws("owner", "aws_owner backup list-backup-vaults"),
        aws("recipient", "aws_recipient sts get-caller-identity"),
        aws(
            "recipient",
            "aws_recipient cloudformation describe-stacks",
            {"--stack-name": f"shared-vault-lab-recipient-{PRIMARY}"},
        ),
        aws("recipient", "aws_recipient fsx describe-file-systems", {"--file-system-ids": sc.EXISTING_RECIPIENT_FS}),
        aws(
            "recipient",
            "aws_recipient fsx describe-storage-virtual-machines",
            {"--filters": f"Name=file-system-id,Values={sc.EXISTING_RECIPIENT_FS}"},
        ),
        aws(
            "recipient",
            "aws_recipient cloudformation deploy",
            {
                "--template-file": TEMPLATE_RECIPIENT,
                "--stack-name": f"shared-vault-lab-recipient-{PRIMARY}",
                "--capabilities": "CAPABILITY_IAM",
                "--parameter-overrides": RECIPIENT_PARAMS,
                "--tags": TAGS,
                "--no-fail-on-empty-changeset": [],
            },
        ),
        aws(
            "recipient",
            "aws_recipient fsx describe-storage-virtual-machines",
            {"--storage-virtual-machine-ids": sc.RECIPIENT_RESTORE_SVM},
        ),
        aws(
            "recipient",
            "aws_recipient fsx list-tags-for-resource",
            {
                "--resource-arn": f"arn:aws:fsx:{PRIMARY}:{sc.RECIPIENT}:storage-virtual-machine/{sc.EXISTING_RECIPIENT_FS}/{sc.RECIPIENT_RESTORE_SVM}"
            },
        ),
    ],
    "03_deploy_lag_share.sh": [
        aws("create", "aws_owner sts get-caller-identity"),
        aws("create", "aws_owner cloudformation describe-stacks", {"--stack-name": f"shared-vault-lab-lag-{PRIMARY}"}),
        aws("create", "aws_owner backup list-backup-vaults"),
        aws(
            "create",
            "aws_owner cloudformation deploy",
            {
                "--template-file": TEMPLATE_LAG,
                "--stack-name": f"shared-vault-lab-lag-{PRIMARY}",
                "--parameter-overrides": lag_params(),
                "--tags": TAGS,
                "--no-fail-on-empty-changeset": [],
            },
        ),
        aws("create", "aws_owner backup describe-backup-vault", {"--backup-vault-name": sc.LAG_VAULT}),
        aws(
            "create",
            "aws_owner ram get-resource-shares",
            {"--resource-owner": "SELF", "--name": sc.SHARE_NAME, "--resource-share-status": "ACTIVE"},
        ),
        aws(
            "repair",
            "aws_owner cloudformation deploy",
            {"--stack-name": f"shared-vault-lab-lag-{PRIMARY}", "--parameter-overrides": lag_params("false")},
        ),
        aws(
            "repair",
            "aws_owner cloudformation deploy",
            {"--stack-name": f"shared-vault-lab-lag-{PRIMARY}", "--parameter-overrides": lag_params("true")},
        ),
    ],
    "04_backup_and_copy.sh": [
        aws("all", "aws_owner sts get-caller-identity"),
        aws("all", "aws_owner cloudformation describe-stacks", {"--stack-name": "shared-vault-lab-owner-base"}),
        aws("all", "aws_owner cloudformation describe-stacks", {"--stack-name": f"shared-vault-lab-lag-{PRIMARY}"}),
        aws("all", "aws_owner backup describe-backup-vault", {"--backup-vault-name": sc.LAG_VAULT}),
        aws(
            "all",
            "aws_owner backup list-recovery-points-by-backup-vault",
            {"--backup-vault-name": sc.STD_VAULT, "--by-resource-arn": sc.VOLUME_ARN},
        ),
        aws(
            "all",
            "aws_owner backup start-backup-job",
            {
                "--backup-vault-name": sc.STD_VAULT,
                "--resource-arn": sc.VOLUME_ARN,
                "--iam-role-arn": sc.ROLE_ARN,
                "--lifecycle": "DeleteAfterDays=2",
                "--idempotency-token": backup_token(),
            },
        ),
        aws("all", "aws_owner backup describe-backup-job", {"--backup-job-id": sc.BACKUP_JOB_ID}),
        aws(
            "all",
            "aws_owner backup describe-recovery-point",
            {"--backup-vault-name": sc.STD_VAULT, "--recovery-point-arn": sc.SRC_RP},
        ),
        aws(
            "all",
            "aws_owner backup list-recovery-points-by-backup-vault",
            {"--backup-vault-name": sc.LAG_VAULT, "--by-resource-arn": sc.VOLUME_ARN},
        ),
        aws("all", "aws_owner backup list-copy-jobs", {"--by-state": "CREATED"}),
        aws("all", "aws_owner backup list-copy-jobs", {"--by-state": "RUNNING"}),
        aws("all", "aws_owner backup list-copy-jobs", {"--by-source-recovery-point-arn": sc.SRC_RP}),
        aws(
            "all",
            "aws_owner backup start-copy-job",
            {
                "--recovery-point-arn": sc.SRC_RP,
                "--source-backup-vault-name": sc.STD_VAULT,
                "--destination-backup-vault-arn": sc.lag_arn(PRIMARY),
                "--iam-role-arn": sc.ROLE_ARN,
                "--lifecycle": "DeleteAfterDays=7",
                "--idempotency-token": copy_token(),
            },
        ),
        aws("all", "aws_owner backup describe-copy-job", {"--copy-job-id": sc.COPY_JOB_ID}),
        aws(
            "all",
            "aws_owner backup describe-recovery-point",
            {"--backup-vault-name": sc.LAG_VAULT, "--recovery-point-arn": sc.dest_rp(PRIMARY)},
        ),
    ],
    "05_accept_share.sh": [
        aws("accept", "aws_recipient sts get-caller-identity"),
        aws("accept", "aws_owner cloudformation describe-stacks", {"--stack-name": f"shared-vault-lab-lag-{PRIMARY}"}),
        aws("accept", "aws_recipient ram get-resource-share-invitations"),
        aws(
            "accept",
            "aws_recipient ram accept-resource-share-invitation",
            {"--resource-share-invitation-arn": sc.invitation_arn(PRIMARY)},
        ),
        aws("accept", "aws_recipient backup list-backup-vaults", {"--by-shared": []}),
    ],
}


# --------------------------------------------------------------------------
# The success runs
# --------------------------------------------------------------------------


def run_01_all(lab: Lab, **kw: Any) -> Result:
    sc.install_node(lab)
    lab.write_scenario(sc.merged(sc.preflight(), sc.preflight_estimate()))
    return lab.run("01_preflight.sh", "--estimate-cost", **kw)


def run_02_owner(lab: Lab, **kw: Any) -> Result:
    lab.write_scenario(sc.deploy_owner())
    return lab.run("02_deploy.sh", "--side", "owner", "--apply", **kw)


def run_02_recipient(lab: Lab, **kw: Any) -> Result:
    lab.write_scenario(sc.deploy_recipient())
    return lab.run(
        "02_deploy.sh",
        "--side",
        "recipient",
        "--apply",
        env={"LAB_RECIPIENT_EXISTING_FS_ID": sc.EXISTING_RECIPIENT_FS},
        **kw,
    )


def run_03_create(lab: Lab, **kw: Any) -> Result:
    lab.write_scenario(sc.deploy_lag())
    return lab.run(
        "03_deploy_lag_share.sh",
        "--retention-days",
        "7",
        "--apply",
        "--confirm",
        f"lock-7d-{sc.LAG_VAULT}@{PRIMARY}",
        **kw,
    )


def run_03_repair(lab: Lab, **kw: Any) -> Result:
    scenario = sc.deploy_lag()
    scenario["cloudformation describe-stacks"] = {"body": sc.lag_stack(PRIMARY)}
    scenario["backup list-backup-vaults"] = {"body": {"BackupVaultList": [{"BackupVaultName": sc.LAG_VAULT}]}}
    lab.write_scenario(scenario)
    return lab.run("03_deploy_lag_share.sh", "--repair-share", "--apply", **kw)


def run_04_all(lab: Lab, **kw: Any) -> Result:
    lab.write_scenario(sc.backup_copy())
    return lab.run(
        "04_backup_and_copy.sh",
        "--retention-days",
        "7",
        "--apply",
        "--confirm",
        f"copy-7d-{sc.LAG_VAULT}@{PRIMARY}",
        env={"LAB_NOW": PINNED_NOW},
        **kw,
    )


def run_05_accept(lab: Lab, **kw: Any) -> Result:
    lab.write_scenario(sc.accept())
    return lab.run("05_accept_share.sh", "--apply", env={"LAB_NOW": "2026-10-11T03:00:00Z"}, **kw)


RUNS: dict[tuple[str, str], Callable[..., Result]] = {
    ("01_preflight.sh", "all"): run_01_all,
    ("02_deploy.sh", "owner"): run_02_owner,
    ("02_deploy.sh", "recipient"): run_02_recipient,
    ("03_deploy_lag_share.sh", "create"): run_03_create,
    ("03_deploy_lag_share.sh", "repair"): run_03_repair,
    ("04_backup_and_copy.sh", "all"): run_04_all,
    ("05_accept_share.sh", "accept"): run_05_accept,
}


def _render(value: Any, lab: Lab) -> Any:
    if isinstance(value, str):
        return value.format(root=lab.root) if "{root}" in value else value
    if isinstance(value, list):
        return [_render(v, lab) for v in value]
    return value


def check_run(script: str, run: str, lab: Lab, **kw: Any) -> Result:
    """Run one success scenario and assert every expected row. Raises AssertionError."""
    result = RUNS[(script, run)](lab, **kw)
    assert result.rc == 0, f"{script} ({run}) exited {result.rc}:\n{result.out}\n{result.err}"
    for row in (r for r in EXPECTED_CALLS[script] if r.run == run):
        if row.kind == "external":
            assert any(row.flags["needle"] in line for line in lab.external_calls()), (
                f"no external call {row.flags['needle']!r}"
            )
            continue
        assert_called(
            result.calls,
            row.service,
            row.sub,
            {flag: _render(value, lab) for flag, value in row.flags.items()},
            profile=row.profile,
            region=row.region,
        )
    return result


def _runs_of(script: str) -> list[str]:
    return sorted({r.run for r in EXPECTED_CALLS[script]})


ALL_RUNS = [(script, run) for script in sorted(EXPECTED_CALLS) for run in _runs_of(script)]
ALL_LITERALS = sorted(
    {(script, run, row.literal) for script, rows in EXPECTED_CALLS.items() for row in rows for run in [row.run]}
)


# --------------------------------------------------------------------------
# Binding the table to the scripts
# --------------------------------------------------------------------------


def test_every_script_has_expected_calls() -> None:
    scripts = sorted(p.name for p in SCRIPTS_DIR.glob("[0-9][0-9]_*.sh"))
    assert set(EXPECTED_CALLS) == set(scripts)
    assert set(RUNS) == {(s, r) for s in EXPECTED_CALLS for r in _runs_of(s)}


@pytest.mark.parametrize(("script", "run"), ALL_RUNS)
def test_script_calls_match_expected(lab: Lab, script: str, run: str) -> None:
    check_run(script, run, lab)


@pytest.mark.parametrize(("script", "run"), ALL_RUNS)
def test_echo_only_script_is_rejected(lab: Lab, script: str, run: str) -> None:
    """A script that prints each command instead of running it records no call."""
    lines = ["#!/bin/bash"]
    for row in EXPECTED_CALLS[script]:
        if row.run == run and row.kind == "aws":
            lines.append(f"echo aws {row.service} {row.sub} " + " ".join(str(v) for v in row.flags.values()))
    lab.install_script(script, "\n".join(lines) + "\n")
    with pytest.raises(AssertionError):
        check_run(script, run, lab, allow_stub_failure=True)


@pytest.mark.parametrize(("script", "run", "literal"), ALL_LITERALS)
def test_echo_substitution_fails_every_script(lab: Lab, script: str, run: str, literal: str) -> None:
    """Replace one real call (every occurrence) with echo: the success run must fail."""
    text = (SCRIPTS_DIR / script).read_text(encoding="utf-8")
    if literal in text:
        lab.install_script(script, substitute_with_echo(text, literal))
    else:
        # The account check (assert_account) lives in the shared library.
        library = (SCRIPTS_DIR / "lib" / "common.sh").read_text(encoding="utf-8")
        (lab.scripts / "lib" / "common.sh").write_text(substitute_with_echo(library, literal), encoding="utf-8")
    with pytest.raises(AssertionError):
        check_run(script, run, lab, allow_stub_failure=True)


def test_expected_value_assert_rejects_name_where_id_expected(lab: Lab) -> None:
    """The recorded calls of a real run: a name never satisfies an expectation for an id."""
    result = check_run("02_deploy.sh", "owner", lab)
    assert_called(result.calls, "fsx", "describe-file-systems", {"--file-system-ids": SENTINEL.FS})
    with pytest.raises(AssertionError):
        assert_called(result.calls, "fsx", "describe-file-systems", {"--file-system-ids": SENTINEL.NAME_FS})
    with pytest.raises(AssertionError):
        assert_called(result.calls, "fsx", "describe-volumes", {"--volume-ids": SENTINEL.NAME_VOLUME})


def test_a_one_character_change_in_a_value_is_caught(lab: Lab) -> None:
    result = check_run("04_backup_and_copy.sh", "all", lab)
    wrong = sc.lag_arn(PRIMARY)[:-1] + "x"
    with pytest.raises(AssertionError):
        assert_called(result.calls, "backup", "start-copy-job", {"--destination-backup-vault-arn": wrong})


def test_stub_scenario_key_can_match_flag_values(lab: Lab) -> None:
    """A key with --profile=... or --region=... answers only calls that pass that value."""
    lab.write_scenario(
        {
            "sts get-caller-identity --profile=lab-owner": {"body": {"Account": sc.OWNER}},
            "sts get-caller-identity --profile=lab-recipient": {"body": {"Account": sc.RECIPIENT}},
            "backup list-backup-vaults --region=ap-northeast-3": {
                "body": {"BackupVaultList": [{"BackupVaultName": "osaka"}]}
            },
        }
    )
    base = ["--output", "json"]
    owner = lab.stub("--profile", "lab-owner", *base, "sts", "get-caller-identity")
    other = lab.stub("--profile", "lab-recipient", *base, "sts", "get-caller-identity")
    assert json.loads(owner.stdout)["Account"] == sc.OWNER
    assert json.loads(other.stdout)["Account"] == sc.RECIPIENT
    osaka = lab.stub("--region", "ap-northeast-3", *base, "backup", "list-backup-vaults")
    assert osaka.returncode == 0 and "osaka" in osaka.stdout
    tokyo = lab.stub("--region", "ap-northeast-1", *base, "backup", "list-backup-vaults")
    assert tokyo.returncode == 99


# --------------------------------------------------------------------------
# Template parameters and permissions
# --------------------------------------------------------------------------


class _Loader(yaml.SafeLoader):
    pass


_Loader.add_multi_constructor("!", lambda loader, suffix, node: None)


def _template_parameters(name: str) -> tuple[set[str], set[str]]:
    data = yaml.load((LAB_SRC / "cloudformation" / name).read_text(encoding="utf-8"), Loader=_Loader)  # noqa: S506
    params = data["Parameters"]
    return set(params), {k for k, v in params.items() if "Default" not in v}


def test_template_parameters_contract(lab: Lab) -> None:
    """Every override names a template parameter; every parameter without a default is passed."""
    seen = 0
    for script, run in (
        ("02_deploy.sh", "owner"),
        ("02_deploy.sh", "recipient"),
        ("03_deploy_lag_share.sh", "create"),
        ("03_deploy_lag_share.sh", "repair"),
    ):
        local = Lab(lab.tmp / f"{script}-{run}")
        result = RUNS[(script, run)](local)
        assert result.rc == 0, result.out + result.err
        for call in (c for c in result.calls if c["subcommand"] == "deploy"):
            template = Path(call["args"]["--template-file"][0]).name
            declared, required = _template_parameters(template)
            keys = {item.split("=", 1)[0] for item in call["args"]["--parameter-overrides"]}
            assert keys <= declared, f"{script}: {keys - declared} is not a parameter of {template}"
            assert required <= keys, f"{script}: {required - keys} has no default in {template} and is not passed"
            seen += 1
    assert seen == 5


def _actions_of(calls: list[dict[str, Any]]) -> set[str]:
    session = botocore.session.get_session()
    out: set[str] = set()
    for call in calls:
        service, sub = call["service"], call["subcommand"]
        if (service, sub) == ("sts", "get-caller-identity"):
            continue  # needs no permission
        if (service, sub) == ("cloudformation", "deploy"):
            out |= {
                f"cloudformation:{op}"
                for op in ("CreateChangeSet", "DescribeChangeSet", "DescribeStacks", "ExecuteChangeSet")
            }
            continue
        model = session.get_service_model(service)
        names = {xform_name(n, "-"): n for n in model.operation_names}
        out.add(f"{service}:{names[sub]}")
    return out


def test_required_actions_cover_every_call_of_scripts_01_to_05(lab: Lab) -> None:
    """Whatever 01-05 call is named in required-actions.json (a later commit adds the exact-match test)."""
    data = json.loads((SCRIPTS_DIR / "lib" / "required-actions.json").read_text(encoding="utf-8"))
    operator = {a for key in ("operator-owner", "operator-recipient", "operator-optional") for a in data[key]}
    recorded: set[str] = set()
    for index, (script, run) in enumerate(ALL_RUNS):
        local = Lab(lab.tmp / f"cover-{index}")
        result = RUNS[(script, run)](local)
        assert result.rc == 0, result.out + result.err
        recorded |= _actions_of(result.calls)
    missing = recorded - operator
    assert not missing, f"calls without an entry in required-actions.json: {sorted(missing)}"
    assert {"iam:PassRole"} <= operator


def test_required_actions_have_a_pass_role_entry_for_both_service_roles() -> None:
    data = json.loads((SCRIPTS_DIR / "lib" / "required-actions.json").read_text(encoding="utf-8"))
    assert "iam:PassRole" in data["operator-owner"]
    assert "iam:PassRole" in data["operator-recipient"]


# --------------------------------------------------------------------------
# lab.env.example
# --------------------------------------------------------------------------

LIBRARY_ONLY = {"LAB_ROOT", "LAB_REPO_ROOT", "LAB_NOW", "LAB_UI_EXPECT"}


def _names_in_text(text: str) -> set[str]:
    return set(re.findall(r"\bLAB_[A-Z0-9_]*[A-Z0-9]\b", text))


def test_env_example_lists_every_documented_variable_and_not_the_test_only_one() -> None:
    example = (LAB_SRC / "lab.env.example").read_text(encoding="utf-8")
    listed = {m.group(1) for m in re.finditer(r"^(?:# )?(LAB_[A-Z0-9_]+)=", example, re.M)}
    common = (SCRIPTS_DIR / "lib" / "common.sh").read_text(encoding="utf-8")
    validated = set(re.findall(r"^_lab_validate (LAB_[A-Z0-9_]+) ", common, re.M))
    assert validated - LIBRARY_ONLY <= listed, sorted(validated - LIBRARY_ONLY - listed)
    used = set()
    for path in SCRIPTS_DIR.glob("[0-9][0-9]_*.sh"):
        used |= _names_in_text(path.read_text(encoding="utf-8"))
    assert used - LIBRARY_ONLY <= listed | {"LAB_ROOT"}, sorted(used - LIBRARY_ONLY - listed)
    assert "LAB_NOW" not in example
    assert "LAB_UI_EXPECT" not in example.replace("LAB_UI_EXPECT is", "")


def test_env_example_loads_with_the_required_values_only(lab: Lab) -> None:
    result = lab.bash("echo loaded", lab_env=False, env={"LAB_ENV_FILE": str(lab.root / "lab.env.example")})
    assert result.rc == 0, result.err
    assert "loaded" in result.out


def test_env_example_loads_with_every_optional_line_enabled(lab: Lab) -> None:
    text = (LAB_SRC / "lab.env.example").read_text(encoding="utf-8")
    enabled = re.sub(r"^# (LAB_(?!ENV_FILE)[A-Z0-9_]+=)", r"\1", text, flags=re.M)
    assert enabled != text
    path = lab.tmp / "enabled.env"
    path.write_text(enabled, encoding="utf-8")
    result = lab.bash("echo loaded", lab_env=False, env={"LAB_ENV_FILE": str(path)})
    assert result.rc == 0, result.err
    assert "loaded" in result.out


def test_env_example_uses_placeholders_only() -> None:
    text = (LAB_SRC / "lab.env.example").read_text(encoding="utf-8")
    accounts = set(re.findall(r"\b\d{12}\b", text))
    assert accounts <= {sc.OWNER, sc.RECIPIENT}
    assert not re.search(r"@|/Users/|/home/", text)


# --------------------------------------------------------------------------
# Script hygiene shared by 01-05
# --------------------------------------------------------------------------

SCRIPT_FILES = sorted(SCRIPTS_DIR.glob("[0-9][0-9]_*.sh"))


@pytest.mark.parametrize("path", SCRIPT_FILES, ids=lambda p: p.name)
def test_script_header_and_safety_flags(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "#!/bin/bash"
    assert lines[1] == "# Real-environment run: not yet done (status source: docs/verification-record.md)"
    text = "\n".join(lines)
    assert "set -euo pipefail" in text
    assert re.search(r"^# Exit codes:", text, re.M), "the usage/exit-code comment block is missing"
    assert re.search(r"^# Usage:", text, re.M)
    assert text.index("set -euo pipefail") < text.index("lib/common.sh")


@pytest.mark.parametrize("path", SCRIPT_FILES, ids=lambda p: p.name)
def test_aws_is_called_only_through_literal_wrappers(path: Path) -> None:
    code = [line for line in path.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("#")]
    for line in code:
        for match in re.finditer(r"\baws_(?:owner|recipient)\b(.*)", line):
            rest = match.group(1)
            if line.lstrip().startswith(("aws_owner()", "aws_recipient()")):
                continue
            assert re.match(r"\s+[a-z0-9-]+\s+[a-z][a-z0-9-]+\b", rest), (
                f"service/subcommand not literal: {line.strip()}"
            )
        stripped = line.strip()
        assert not re.match(r"^(?:if !? )?(?:[a-z_]+=\$\()?aws\s", stripped) or "aws --version" in stripped, stripped


@pytest.mark.parametrize("path", SCRIPT_FILES, ids=lambda p: p.name)
def test_every_check_carries_an_item_id(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    calls = re.findall(r"\bcheck_(?:pass|fail|warn) (\S+)", text)
    assert calls
    bad = [item for item in calls if not re.fullmatch(r"-|V[1-8]|E(?:[1-9]|1[0-9]|2[0-6])", item)]
    assert not bad, f"check calls without an item id: {bad}"


@pytest.mark.parametrize("path", [*SCRIPT_FILES, *sorted((LAB_SRC / "tests").glob("*.py"))], ids=lambda p: p.name)
def test_no_japanese_in_scripts_and_tests(path: Path) -> None:
    assert not re.search(r"[\u3040-\u30ff\u3400-\u9fff\uff00-\uffef]", path.read_text(encoding="utf-8")), path.name


def test_json_is_built_with_jq_not_by_string_concatenation() -> None:
    for path in SCRIPT_FILES:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"""--payload\s+["']\{""", text), f"{path.name} builds a payload by hand"
        assert not re.search(r"""echo\s+["']\{.*\$""", text), f"{path.name} builds JSON by hand"


def test_scripts_are_executable() -> None:
    for path in SCRIPT_FILES:
        assert path.stat().st_mode & 0o111, f"{path.name} is not executable"


def test_helpers_cli_text_digest_and_age_are_stable() -> None:
    def run(*args: str) -> str:
        return subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "lib" / "lab_helpers.py"), *args],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    assert run("text-digest", "a", "b") == helpers.text_digest(["a", "b"])
    assert len(run("text-digest", "a")) == 32
    assert run("text-digest", "a", "b") != run("text-digest", "a", "c")
    assert run("age-minutes", "--from", "2026-10-11T01:00:00+09:00", "--now", "2026-10-11T12:00:00Z") == "1200"
    assert run("age-minutes", "--from", "2026-10-12T01:00:00Z", "--now", "2026-10-11T12:00:00Z") == "0"
