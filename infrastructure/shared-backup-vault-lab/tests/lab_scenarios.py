"""Scenario data for the script tests of the shared-vault lab (01-05).

Every value is a dummy with its own shape: ids and ARNs are complete and distinct
per kind, so a script that passes a name where an id belongs (or the reverse)
fails the value assertions. Builders return scenario dicts for
``Lab.write_scenario``; tests update a copy to make a case differ from the happy
path.

A scenario key is ``"<service> <subcommand> [--flag[=value]] [!--flag]"``. Keys
with a profile or Region value (``--profile=lab-owner``) are used where the owner
and the recipient (or two Regions) must be told apart.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from lab_testlib import LAB_SRC, SENTINEL, arn

_spec = importlib.util.spec_from_file_location(
    "lab_helpers_for_scenarios", LAB_SRC / "scripts" / "lib" / "lab_helpers.py"
)
assert _spec is not None and _spec.loader is not None
helpers = importlib.util.module_from_spec(_spec)
sys.modules["lab_helpers_for_scenarios"] = helpers
_spec.loader.exec_module(helpers)

MUTATING_PREFIXES = (
    "start-",
    "create-",
    "delete-",
    "accept-",
    "put-",
    "update-",
    "tag-resource",
    "schedule-key-deletion",
)


def mutating(calls: list[dict[str, Any]]) -> list[str]:
    """Names of the recorded calls that change state (a deploy counts)."""
    return [
        f"{c['service']} {c['subcommand']}"
        for c in calls
        if c["subcommand"] == "deploy" or c["subcommand"].startswith(MUTATING_PREFIXES)
    ]


def calls_of(calls: list[dict[str, Any]], sub: str) -> list[dict[str, Any]]:
    """The recorded calls of one subcommand."""
    return [c for c in calls if c["subcommand"] == sub]


OWNER = SENTINEL.OWNER
RECIPIENT = SENTINEL.RECIPIENT
PRIMARY = "ap-northeast-1"
SECOND = "ap-northeast-3"
TAG = "shared-vault-lab"
STD_VAULT = f"{TAG}-standard"
LAG_VAULT = f"{TAG}-lag"
SHARE_NAME = f"{TAG}-lag-share"
OWNER_PROFILE = "lab-owner"
RECIPIENT_PROFILE = "lab-recipient"

KEY_ARN = arn("kms", PRIMARY, OWNER, "key/11111111-1111-4111-8111-111111111111")
VOLUME_ARN = arn("fsx", PRIMARY, OWNER, f"volume/{SENTINEL.FS}/{SENTINEL.VOLUME}")
FS_ARN = arn("fsx", PRIMARY, OWNER, f"file-system/{SENTINEL.FS}")
SVM_ARN = arn("fsx", PRIMARY, OWNER, f"storage-virtual-machine/{SENTINEL.FS}/{SENTINEL.SVM}")
ROLE_ARN = arn("iam", "", OWNER, "role/lab-backup-role")
SRC_RP = arn("fsx", PRIMARY, OWNER, "backup/backup-0123456789abcdef0")
SRC_CREATED = "2026-10-11T10:00:00.123000+09:00"
BACKUP_JOB_ID = "11111111-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
COPY_JOB_ID = "22222222-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
VPC_OWNER = "vpc-0aaaaaaaaaaaaaaaa"
VPC_RECIPIENT = "vpc-0bbbbbbbbbbbbbbbb"
EXISTING_RECIPIENT_FS = "fs-0eeeeeeeeeeeeeeee"
RECIPIENT_RESTORE_SVM = "svm-0ffffffffffffffff"
RECIPIENT_ROLE_ARN = arn("iam", "", RECIPIENT, "role/lab-restore-role")
SESSION_OWNER = f"arn:aws:sts::{OWNER}:assumed-role/OwnerRole/session"
SESSION_RECIPIENT = f"arn:aws:sts::{RECIPIENT}:assumed-role/RecipientRole/session"


def lag_arn(region: str) -> str:
    """ARN of the air-gapped vault in a Region."""
    return arn("backup", region, OWNER, f"backup-vault:{LAG_VAULT}")


def share_arn(region: str) -> str:
    """ARN of the RAM share in a Region."""
    return arn("ram", region, OWNER, "resource-share/aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa")


def invitation_arn(region: str) -> str:
    """ARN of the RAM invitation in a Region."""
    return arn("ram", region, RECIPIENT, "resource-share-invitation/bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb")


def dest_rp(region: str) -> str:
    """ARN of the copied recovery point in the air-gapped vault of a Region."""
    return arn("backup", region, OWNER, "recovery-point:cccccccc-3333-4333-8333-cccccccccccc")


def err(code: str, text: str = "", rc: int = 254) -> dict[str, Any]:
    """An AWS CLI style error response."""
    return {"rc": rc, "stderr": f"An error occurred ({code}) when calling the Operation operation: {text}".strip()}


def no_stack(name: str = "the stack") -> dict[str, Any]:
    """The describe-stacks answer for a stack that does not exist."""
    return err("ValidationError", f"Stack with id {name} does not exist")


def all_actions() -> list[str]:
    """Every action named in required-actions.json (for the simulation answers)."""
    data = json.loads((LAB_SRC / "scripts" / "lib" / "required-actions.json").read_text(encoding="utf-8"))
    return sorted({a for key, values in data.items() if not key.startswith("_") for a in values})


def simulation(denied: dict[str, str] | None = None) -> dict[str, Any]:
    """An iam simulate-principal-policy answer: everything allowed except ``denied``."""
    denied = denied or {}
    return {
        "body": {
            "EvaluationResults": [
                {"EvalActionName": action, "EvalDecision": denied.get(action, "allowed"), "EvalResourceName": "*"}
                for action in all_actions()
            ]
        }
    }


def stack_body(
    name: str, status: str, outputs: dict[str, str] | None = None, params: dict[str, str] | None = None
) -> dict[str, Any]:
    """A describe-stacks body."""
    return {
        "Stacks": [
            {
                "StackName": name,
                "StackStatus": status,
                "Outputs": [{"OutputKey": k, "OutputValue": v} for k, v in (outputs or {}).items()],
                "Parameters": [{"ParameterKey": k, "ParameterValue": v} for k, v in (params or {}).items()],
            }
        ]
    }


# --------------------------------------------------------------------------
# 01 preflight
# --------------------------------------------------------------------------


def preflight() -> dict[str, Any]:
    """Everything is fine and nothing exists yet (side both, one Region)."""
    return {
        f"sts get-caller-identity --profile={OWNER_PROFILE}": {
            "body": {"Account": OWNER, "Arn": SESSION_OWNER, "UserId": "AROAEXAMPLE:session"}
        },
        f"sts get-caller-identity --profile={RECIPIENT_PROFILE}": {
            "body": {"Account": RECIPIENT, "Arn": SESSION_RECIPIENT, "UserId": "AROAEXAMPLE:session"}
        },
        f"ec2 describe-subnets --profile={OWNER_PROFILE}": {
            "body": {"Subnets": [{"SubnetId": SENTINEL.SUBNET, "VpcId": VPC_OWNER}]}
        },
        f"ec2 describe-subnets --profile={RECIPIENT_PROFILE}": {
            "body": {"Subnets": [{"SubnetId": SENTINEL.RECIPIENT_SUBNET, "VpcId": VPC_RECIPIENT}]}
        },
        f"ec2 describe-security-groups --profile={OWNER_PROFILE}": {
            "body": {"SecurityGroups": [{"GroupId": SENTINEL.SG, "VpcId": VPC_OWNER}]}
        },
        f"ec2 describe-security-groups --profile={RECIPIENT_PROFILE}": {
            "body": {"SecurityGroups": [{"GroupId": SENTINEL.SG, "VpcId": VPC_RECIPIENT}]}
        },
        "cloudformation describe-stacks": no_stack(),
        "cloudformation describe-type": {
            "body": {"Type": "RESOURCE", "TypeName": "AWS::Backup::LogicallyAirGappedBackupVault"}
        },
        "backup list-backup-vaults !--by-shared": {"body": {"BackupVaultList": []}},
        "backup list-backup-vaults --by-shared": {"body": {"BackupVaultList": []}},
        "backup describe-region-settings": {"body": {"ResourceTypeOptInPreference": {"FSx": True}}},
        "kms describe-key": err("NotFoundException", "Alias alias/shared-vault-lab-fs is not found."),
        "ram get-resource-shares": {"body": {"resourceShares": []}},
        "organizations describe-organization": err(
            "AWSOrganizationsNotInUseException", "Your account is not a member of an organization."
        ),
        f"iam get-role --profile={OWNER_PROFILE}": {
            "body": {
                "Role": {
                    "RoleName": "OwnerRole",
                    "Arn": f"arn:aws:iam::{OWNER}:role/aws-reserved/sso.amazonaws.com/OwnerRole",
                }
            }
        },
        f"iam get-role --profile={RECIPIENT_PROFILE}": {
            "body": {
                "Role": {
                    "RoleName": "RecipientRole",
                    "Arn": f"arn:aws:iam::{RECIPIENT}:role/aws-reserved/sso.amazonaws.com/RecipientRole",
                }
            }
        },
        "iam simulate-principal-policy": simulation(),
    }


def install_node(lab: Any, version: str = "v20.11.0") -> None:
    """Put fake node and npm on PATH (01 checks them for the recipient side)."""
    lab.add_tool("node", f"echo {version}")
    lab.add_tool("npm", "echo 10.0.0")


def run_preflight(
    lab: Any, scenario: dict[str, Any], *args: str, env: dict[str, Any] | None = None, node: bool = True
) -> Any:
    """Run 01 with a scenario and fake node/npm (unless ``node`` is False)."""
    if node:
        install_node(lab)
    lab.write_scenario(scenario)
    return lab.run("01_preflight.sh", *args, env=env)


def preflight_estimate() -> dict[str, Any]:
    """Extra answers for 01 --estimate-cost."""
    price = {
        "product": {"attributes": {"fileSystemType": "NetApp ONTAP", "regionCode": PRIMARY}},
        "terms": {"OnDemand": {"x": {"priceDimensions": {"y": {"unit": "GB-Mo", "pricePerUnit": {"USD": "0.125"}}}}}},
    }
    price2 = {
        "product": {"attributes": {"fileSystemType": "NetApp ONTAP", "regionCode": PRIMARY}},
        "terms": {"OnDemand": {"x": {"priceDimensions": {"y": {"unit": "Hrs", "pricePerUnit": {"USD": "0.512"}}}}}},
    }
    return {
        "pricing get-products": {
            "body": {"FormatVersion": "aws_v1", "PriceList": [json.dumps(price), json.dumps(price2)]}
        },
        "ce list-cost-allocation-tags": {
            "body": {"CostAllocationTags": [{"TagKey": "Project", "Type": "UserDefined", "Status": "Active"}]}
        },
    }


# --------------------------------------------------------------------------
# 02 deploy
# --------------------------------------------------------------------------

OWNER_BASE_OUTPUTS = {
    "KeyArn": KEY_ARN,
    "FileSystemId": SENTINEL.FS,
    "SvmId": SENTINEL.SVM,
    "VolumeId": SENTINEL.VOLUME,
    "VolumeArn": VOLUME_ARN,
    "StandardVaultName": STD_VAULT,
    "BackupRoleArn": ROLE_ARN,
}


def deploy_owner() -> dict[str, Any]:
    """02 --side owner: the stack is new; every resource becomes ready; tags are present."""
    tags = {"body": {"Tags": [{"Key": "Project", "Value": TAG}, {"Key": "Cleanup", "Value": "delete-when-done"}]}}
    return {
        f"sts get-caller-identity --profile={OWNER_PROFILE}": {
            "body": {"Account": OWNER, "Arn": SESSION_OWNER, "UserId": "X"}
        },
        "cloudformation describe-stacks": [
            no_stack(),
            {"body": stack_body(f"{TAG}-owner-base", "CREATE_COMPLETE", OWNER_BASE_OUTPUTS)},
        ],
        "cloudformation deploy": {"body": {}},
        "fsx describe-file-systems": {
            "body": {"FileSystems": [{"FileSystemId": SENTINEL.FS, "Lifecycle": "AVAILABLE", "ResourceARN": FS_ARN}]}
        },
        "fsx describe-storage-virtual-machines": {
            "body": {
                "StorageVirtualMachines": [
                    {"StorageVirtualMachineId": SENTINEL.SVM, "Lifecycle": "CREATED", "ResourceARN": SVM_ARN}
                ]
            }
        },
        "fsx describe-volumes": {
            "body": {"Volumes": [{"VolumeId": SENTINEL.VOLUME, "Lifecycle": "CREATED", "ResourceARN": VOLUME_ARN}]}
        },
        "fsx list-tags-for-resource": tags,
        "kms describe-key": {"body": {"KeyMetadata": {"KeyId": "k", "Arn": KEY_ARN, "KeyState": "Enabled"}}},
        "backup list-backup-vaults": {
            "body": {
                "BackupVaultList": [
                    {
                        "BackupVaultName": STD_VAULT,
                        "BackupVaultArn": arn("backup", PRIMARY, OWNER, f"backup-vault:{STD_VAULT}"),
                    }
                ]
            }
        },
    }


def deploy_recipient(existing_fs: bool = True) -> dict[str, Any]:
    """02 --side recipient (primary Region only)."""
    fs = {
        "FileSystemId": EXISTING_RECIPIENT_FS if existing_fs else "fs-0123123123123123a",
        "Lifecycle": "AVAILABLE",
        "ResourceARN": arn("fsx", PRIMARY, RECIPIENT, "file-system/fs-0eeeeeeeeeeeeeeee"),
        "NetworkType": "IPV4",
        "OntapConfiguration": {"DeploymentType": "SINGLE_AZ_1", "ThroughputCapacity": 128},
    }
    outputs = {
        "RestoreRoleArn": RECIPIENT_ROLE_ARN,
        "FileSystemId": fs["FileSystemId"],
        "RestoreSvmId": RECIPIENT_RESTORE_SVM,
    }
    return {
        f"sts get-caller-identity --profile={RECIPIENT_PROFILE}": {
            "body": {"Account": RECIPIENT, "Arn": SESSION_RECIPIENT, "UserId": "X"}
        },
        "cloudformation describe-stacks": [
            no_stack(),
            {"body": stack_body(f"{TAG}-recipient-{PRIMARY}", "CREATE_COMPLETE", outputs)},
        ],
        "cloudformation deploy": {"body": {}},
        "fsx describe-file-systems": {"body": {"FileSystems": [fs]}},
        "fsx describe-storage-virtual-machines --filters": {
            "body": {"StorageVirtualMachines": [{"Name": "svm_other"}]}
        },
        "fsx describe-storage-virtual-machines --storage-virtual-machine-ids": {
            "body": {
                "StorageVirtualMachines": [
                    {
                        "StorageVirtualMachineId": RECIPIENT_RESTORE_SVM,
                        "Lifecycle": "CREATED",
                        "ResourceARN": arn(
                            "fsx",
                            PRIMARY,
                            RECIPIENT,
                            f"storage-virtual-machine/fs-0eeeeeeeeeeeeeeee/{RECIPIENT_RESTORE_SVM}",
                        ),
                    }
                ]
            }
        },
        "fsx list-tags-for-resource": {"body": {"Tags": [{"Key": "Project", "Value": TAG}]}},
    }


# --------------------------------------------------------------------------
# 03 deploy LAG vault and share
# --------------------------------------------------------------------------


def lag_stack(region: str, retention: str = "7", status: str = "CREATE_COMPLETE") -> dict[str, Any]:
    """A describe-stacks body for the air-gapped vault stack of a Region."""
    return stack_body(
        f"{TAG}-lag-{region}",
        status,
        {"LagVaultArn": lag_arn(region), "LagVaultName": LAG_VAULT, "ResourceShareArn": share_arn(region)},
        {"RetentionDays": retention, "AcknowledgeRetentionDays": retention, "ShareEnabled": "true"},
    )


def share_list(region: str, count: int = 1) -> dict[str, Any]:
    """A ram get-resource-shares body with ``count`` ACTIVE shares of the lab name."""
    return {
        "body": {
            "resourceShares": [
                {
                    "name": SHARE_NAME,
                    "status": "ACTIVE",
                    "resourceShareArn": share_arn(region),
                    "owningAccountId": OWNER,
                }
                for _ in range(count)
            ]
        }
    }


def lag_vault(retention: int = 7, state: str = "AVAILABLE") -> dict[str, Any]:
    """A backup describe-backup-vault body for the air-gapped vault."""
    return {
        "body": {
            "BackupVaultName": LAG_VAULT,
            "BackupVaultArn": lag_arn(PRIMARY),
            "VaultType": "LOGICALLY_AIR_GAPPED_BACKUP_VAULT",
            "VaultState": state,
            "MinRetentionDays": retention,
            "MaxRetentionDays": retention,
            "NumberOfRecoveryPoints": 0,
        }
    }


def deploy_lag(retention: int = 7) -> dict[str, Any]:
    """03 create: the stack does not exist yet, the vault is not listed, then everything is ready."""
    return {
        f"sts get-caller-identity --profile={OWNER_PROFILE}": {
            "body": {"Account": OWNER, "Arn": SESSION_OWNER, "UserId": "X"}
        },
        "cloudformation describe-stacks": no_stack(),
        "backup list-backup-vaults": {"body": {"BackupVaultList": []}},
        "cloudformation deploy": {"body": {}},
        "backup describe-backup-vault": lag_vault(retention),
        "ram get-resource-shares": share_list(PRIMARY),
    }


# --------------------------------------------------------------------------
# 04 backup and copy
# --------------------------------------------------------------------------


def recovery_point(
    arn_value: str = SRC_RP, created: str = SRC_CREATED, key: str = KEY_ARN, status: str = "COMPLETED"
) -> dict[str, Any]:
    """One entry of list-recovery-points-by-backup-vault."""
    return {
        "RecoveryPointArn": arn_value,
        "ResourceArn": VOLUME_ARN,
        "Status": status,
        "CreationDate": created,
        "EncryptionKeyArn": key,
        "BackupVaultName": STD_VAULT,
    }


def backup_copy(second_region: bool = False, source_exists: bool = False) -> dict[str, Any]:
    """04 --phase all: no source yet (or ``source_exists``), nothing running, copy completes."""
    primary_stack = stack_body(f"{TAG}-owner-base", "CREATE_COMPLETE", OWNER_BASE_OUTPUTS)
    scenario: dict[str, Any] = {
        f"sts get-caller-identity --profile={OWNER_PROFILE}": {
            "body": {"Account": OWNER, "Arn": SESSION_OWNER, "UserId": "X"}
        },
        f"cloudformation describe-stacks --stack-name={TAG}-owner-base": {"body": primary_stack},
        f"cloudformation describe-stacks --stack-name={TAG}-lag-{PRIMARY}": {"body": lag_stack(PRIMARY)},
        f"backup describe-backup-vault --region={PRIMARY}": lag_vault(7),
        f"backup list-recovery-points-by-backup-vault --backup-vault-name={STD_VAULT}": (
            {"body": {"RecoveryPoints": [recovery_point()]}}
            if source_exists
            else [{"body": {"RecoveryPoints": []}}, {"body": {"RecoveryPoints": [recovery_point()]}}]
        ),
        f"backup list-recovery-points-by-backup-vault --backup-vault-name={LAG_VAULT}": {
            "body": {"RecoveryPoints": []}
        },
        "backup describe-recovery-point --backup-vault-name=" + STD_VAULT: {
            "body": {"RecoveryPointArn": SRC_RP, "EncryptionKeyArn": KEY_ARN, "Status": "COMPLETED"}
        },
        "backup start-backup-job": {"body": {"BackupJobId": BACKUP_JOB_ID}},
        "backup describe-backup-job": [
            {"body": {"BackupJobId": BACKUP_JOB_ID, "State": "RUNNING"}},
            {"body": {"BackupJobId": BACKUP_JOB_ID, "State": "COMPLETED", "RecoveryPointArn": SRC_RP}},
        ],
        "backup list-copy-jobs --by-state=CREATED": {"body": {"CopyJobs": []}},
        "backup list-copy-jobs --by-state=RUNNING": {"body": {"CopyJobs": []}},
        "backup list-copy-jobs --by-source-recovery-point-arn": {"body": {"CopyJobs": []}},
        "backup start-copy-job": {"body": {"CopyJobId": COPY_JOB_ID}},
        "backup describe-copy-job": [
            {"body": {"CopyJob": {"CopyJobId": COPY_JOB_ID, "State": "RUNNING"}}},
            {
                "body": {
                    "CopyJob": {
                        "CopyJobId": COPY_JOB_ID,
                        "State": "COMPLETED",
                        "DestinationRecoveryPointArn": dest_rp(PRIMARY),
                    }
                }
            },
        ],
        f"backup describe-recovery-point --backup-vault-name={LAG_VAULT}": {
            "body": {
                "RecoveryPointArn": dest_rp(PRIMARY),
                "CalculatedLifecycle": {"DeleteAt": "2026-10-18T01:00:00.123000+00:00"},
            }
        },
    }
    if second_region:
        scenario[f"cloudformation describe-stacks --stack-name={TAG}-lag-{SECOND}"] = {"body": lag_stack(SECOND)}
        scenario[f"backup describe-backup-vault --region={SECOND}"] = lag_vault(7)
    return scenario


def merged(base: dict[str, Any], *updates: dict[str, Any]) -> dict[str, Any]:
    """A deep copy of ``base`` updated with each of ``updates`` in turn."""
    out = copy.deepcopy(base)
    for update in updates:
        out.update(copy.deepcopy(update))
    return out


# --------------------------------------------------------------------------
# 05 accept share
# --------------------------------------------------------------------------


def invitation(region: str, status: str = "PENDING", stamp: str = "2026-10-11T01:00:00+00:00") -> dict[str, Any]:
    """One RAM invitation of the lab share."""
    return {
        "resourceShareInvitationArn": invitation_arn(region),
        "resourceShareArn": share_arn(region),
        "resourceShareName": SHARE_NAME,
        "senderAccountId": OWNER,
        "receiverAccountId": RECIPIENT,
        "status": status,
        "invitationTimestamp": stamp,
    }


def shared_vault(region: str = PRIMARY) -> dict[str, Any]:
    """A backup list-backup-vaults --by-shared body that holds the lab vault."""
    return {
        "body": {
            "BackupVaultList": [
                {"BackupVaultName": LAG_VAULT, "BackupVaultArn": lag_arn(region), "NumberOfRecoveryPoints": 0}
            ]
        }
    }


def accept(region: str = PRIMARY) -> dict[str, Any]:
    """05: one pending invitation; the vault shows up after acceptance."""
    return {
        f"sts get-caller-identity --profile={RECIPIENT_PROFILE}": {
            "body": {"Account": RECIPIENT, "Arn": SESSION_RECIPIENT, "UserId": "X"}
        },
        "cloudformation describe-stacks": {"body": lag_stack(region)},
        "ram get-resource-share-invitations": {"body": {"resourceShareInvitations": [invitation(region)]}},
        "ram accept-resource-share-invitation": {"body": {"resourceShareInvitation": {"status": "ACCEPTED"}}},
        "backup list-backup-vaults --by-shared": [{"body": {"BackupVaultList": []}}, shared_vault(region)],
    }


def read_calls(path: Path) -> list[dict[str, Any]]:
    """Read a stub call log."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
