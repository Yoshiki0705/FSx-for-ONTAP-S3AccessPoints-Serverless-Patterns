"""Scenario data for the 07_portal_config.sh tests.

Builders return stub scenarios (``Lab.write_scenario``) and environments for the fake
external commands. Values are dummies: the function, role and stack names are invented,
and every id carries its own shape (see ``lab_scenarios``).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import lab_scenarios as sc
from lab_testlib import SENTINEL, arn

PRIMARY = sc.PRIMARY
SECOND = sc.SECOND
OWNER = sc.OWNER
RECIPIENT = sc.RECIPIENT
RECIPIENT_PROFILE = sc.RECIPIENT_PROFILE
LAG_VAULT = sc.LAG_VAULT

FUNCTION = "portal-recovery-points-function"
FUNCTION_DESCRIPTION = "Lists AWS Backup recovery points for FSx for ONTAP volumes (read-only)"
ROLE_NAME = "portal-recovery-points-role"
ROLE_ARN = arn("iam", "", RECIPIENT, f"role/service-role/{ROLE_NAME}")
SANDBOX_ID = "lab-sandbox"
PASSWORD = "Zq7!pLm2#Rt9-xKw"
USERNAME = "lab-ui@example.com"

SHARED_PAYLOAD = json.dumps({"action": "listSharedBackupVaults"}, separators=(",", ":"))
RP_PAYLOAD = json.dumps(
    {"action": "listRecoveryPoints", "backupVaultName": LAG_VAULT, "backupVaultAccountId": OWNER},
    separators=(",", ":"),
)

EXPECT_VALUES = ("arn-missing", "arn-present", "revoked")


def who_ambient(account: str = RECIPIENT) -> dict[str, Any]:
    """The answer to the ambient ``sts get-caller-identity`` (no --profile)."""
    return {"body": {"Account": account, "Arn": f"arn:aws:sts::{account}:assumed-role/Ambient/session", "UserId": "X"}}


def base() -> dict[str, Any]:
    """The recipient identity (profile) and the ambient identity of portal children."""
    return {
        f"sts get-caller-identity --profile={RECIPIENT_PROFILE}": {
            "body": {"Account": RECIPIENT, "Arn": sc.SESSION_RECIPIENT, "UserId": "X"}
        },
        "sts get-caller-identity !--profile": who_ambient(),
    }


# --------------------------------------------------------------------------
# --check
# --------------------------------------------------------------------------


def function_row(
    name: str = FUNCTION, description: str = FUNCTION_DESCRIPTION, regions: list[str] | None = None
) -> dict:
    """One ``lambda list-functions`` row."""
    return {
        "FunctionName": name,
        "Description": description,
        "Role": ROLE_ARN,
        "Environment": {"Variables": {"BACKUP_REGIONS": json.dumps(SECOND_ONLY if regions is None else regions)}},
    }


SECOND_ONLY = [SECOND]


def shared_body(present: bool = True, error: str | None = None) -> dict[str, Any]:
    """The ``listSharedBackupVaults`` response."""
    vaults = []
    if present:
        vaults.append(
            {
                "backupVaultName": LAG_VAULT,
                "backupVaultArn": sc.lag_arn(PRIMARY),
                "ownerAccountId": OWNER,
                "ownedByThisAccount": False,
                "region": PRIMARY,
                "vaultType": "LOGICALLY_AIR_GAPPED_BACKUP_VAULT",
            }
        )
    return {"body": {"backupVaults": vaults, "error": error, "errorCode": error, "homeRegion": PRIMARY}}


def recovery_points_body(rows: int = 1, error: str | None = None) -> dict[str, Any]:
    """The ``listRecoveryPoints`` response."""
    points = [
        {"recoveryPointArn": f"{sc.dest_rp(PRIMARY)}{i}", "status": "COMPLETED", "backupVaultName": LAG_VAULT}
        for i in range(rows)
    ]
    return {"body": {"recoveryPoints": points, "error": error, "errorCode": error, "homeRegion": PRIMARY}}


def policy_body(arns: list[str]) -> dict[str, Any]:
    """The ``iam get-role-policy`` answer for AwsBackupRead."""
    statements: list[dict[str, Any]] = []
    if arns:
        statements.append(
            {
                "Effect": "Allow",
                "Action": [
                    "backup:ListRecoveryPointsByBackupVault",
                    "backup:DescribeRecoveryPoint",
                    "backup:DescribeBackupVault",
                ],
                "Resource": arns,
            }
        )
    statements.append({"Effect": "Allow", "Action": ["backup:ListBackupVaults"], "Resource": "*"})
    return {
        "body": {
            "RoleName": ROLE_NAME,
            "PolicyName": "AwsBackupRead",
            "PolicyDocument": {"Version": "2012-10-17", "Statement": statements},
        }
    }


def check(expect: str = "arn-present") -> dict[str, Any]:
    """The portal as it looks in one of the three states (the success path of ``--check``)."""
    if expect == "arn-missing":
        shared, points, arns = shared_body(), recovery_points_body(0, "AccessDeniedException"), []
    elif expect == "arn-present":
        shared, points, arns = shared_body(), recovery_points_body(1), [sc.lag_arn(PRIMARY)]
    elif expect == "revoked":
        shared, points, arns = shared_body(False), recovery_points_body(0, "VaultNotShared"), [sc.lag_arn(PRIMARY)]
    else:
        raise AssertionError(f"unknown state {expect}")
    return {
        **base(),
        "lambda list-functions": {
            "body": {"Functions": [function_row("some-other-function", "something else"), function_row()]}
        },
        "iam get-role-policy": policy_body(arns),
        "lambda invoke": [shared, points],
    }


# --------------------------------------------------------------------------
# --print
# --------------------------------------------------------------------------


def print_scenario(second: bool = True) -> dict[str, Any]:
    """``--print``: the lab vault is shared in both Regions; the recipient stack has its outputs."""
    out: dict[str, Any] = {
        **base(),
        f"backup list-backup-vaults --by-shared --region={PRIMARY}": sc.shared_vault(PRIMARY),
        f"cloudformation describe-stacks --stack-name={sc.TAG}-recipient-{PRIMARY}": {
            "body": sc.stack_body(
                f"{sc.TAG}-recipient-{PRIMARY}",
                "CREATE_COMPLETE",
                {
                    "RestoreRoleArn": sc.RECIPIENT_ROLE_ARN,
                    "FileSystemId": sc.EXISTING_RECIPIENT_FS,
                    "RestoreSvmId": sc.RECIPIENT_RESTORE_SVM,
                },
            )
        },
    }
    if second:
        out[f"backup list-backup-vaults --by-shared --region={SECOND}"] = sc.shared_vault(SECOND)
    return out


# --------------------------------------------------------------------------
# --deploy
# --------------------------------------------------------------------------

STAMP_OLD = "2026-10-11T01:00:00.000000+00:00"
STAMP_NEW = "2026-10-11T02:00:00.000000+00:00"


def stack(name: str, status: str = "UPDATE_COMPLETE", stamp: str = STAMP_OLD, created: bool = False) -> dict:
    """One ``describe-stacks`` row of an Amplify stack."""
    row: dict[str, Any] = {"StackName": name, "StackStatus": status, "CreationTime": STAMP_OLD}
    if not created:
        row["LastUpdatedTime"] = stamp
    return row


def stacks(rows: list[dict]) -> dict[str, Any]:
    """A ``describe-stacks`` answer."""
    return {"body": {"Stacks": rows}}


ROOT = "amplify-portaldemo-labsandbox-sandbox-aaaaaaaaaa"
DATA = "amplify-portaldemo-labsandbox-sandbox-aaaaaaaaaa-data1234-BBBBBBBB"
UNRELATED = "other-application-stack"


def deploy(
    before: list[dict] | None = None, after: list[dict] | list[list[dict]] | None = None, events: bool = False
) -> dict[str, Any]:
    """``--deploy``: the stacks before the sandbox command, then after (a list of lists = polls).

    The default is the success case: both Amplify stacks are updated after the run.
    """
    before = before if before is not None else [stack(ROOT), stack(DATA), stack(UNRELATED)]
    after = (
        after if after is not None else [stack(ROOT, stamp=STAMP_NEW), stack(DATA, stamp=STAMP_NEW), stack(UNRELATED)]
    )
    answers = [stacks(before)]
    if after and isinstance(after[0], list):
        answers.extend(stacks(item) for item in after)
    else:
        answers.append(stacks(after))  # type: ignore[arg-type]
    scenario: dict[str, Any] = {**base(), "cloudformation describe-stacks !--stack-name": answers}
    if events:
        scenario["cloudformation describe-stack-events"] = {
            "body": {
                "StackEvents": [
                    {
                        "StackName": DATA,
                        "LogicalResourceId": "AwsCliLayerStub",
                        "ResourceStatus": "UPDATE_FAILED",
                        "ResourceStatusReason": "Stub reason: the update was refused",
                    },
                    {"StackName": DATA, "LogicalResourceId": "Fine", "ResourceStatus": "UPDATE_COMPLETE"},
                ]
            }
        }
    return scenario


# --------------------------------------------------------------------------
# --ui
# --------------------------------------------------------------------------


def report(expected: int = 1, unexpected: int = 0, skipped: int = 0, flaky: int = 0, extra: str = "") -> str:
    """A Playwright JSON report with the given stats (``extra`` is added to a spec title)."""
    return json.dumps(
        {
            "suites": [
                {
                    "title": "shared-vault-lab.spec.ts",
                    "specs": [{"title": f"stub spec{extra}", "ok": unexpected == 0 and skipped == 0}],
                }
            ],
            "stats": {"expected": expected, "skipped": skipped, "unexpected": unexpected, "flaky": flaky},
        }
    )


def write_report(path: Path, **kwargs: Any) -> Path:
    """Write a report file for ``$STUB_NPX_REPORT``."""
    path.write_text(report(**kwargs), encoding="utf-8")
    return path


def sha256(text: str) -> str:
    """Digest the fake children record instead of the password itself."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def calls_of_name(records: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    """The JSON records of one fake external command."""
    return [r for r in records if r["name"] == name]


__all__ = [
    "DATA",
    "EXPECT_VALUES",
    "FUNCTION",
    "FUNCTION_DESCRIPTION",
    "PASSWORD",
    "RECIPIENT",
    "ROLE_NAME",
    "ROOT",
    "RP_PAYLOAD",
    "SANDBOX_ID",
    "SENTINEL",
    "SHARED_PAYLOAD",
    "STAMP_NEW",
    "USERNAME",
    "calls_of_name",
    "check",
    "deploy",
    "print_scenario",
    "report",
    "sha256",
    "stack",
    "write_report",
]
