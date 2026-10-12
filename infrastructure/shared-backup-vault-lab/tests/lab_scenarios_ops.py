"""Scenario data for scripts 06, 08, 09 and 10 of the shared-vault lab.

Same conventions as ``lab_scenarios``: complete, distinct dummy ids per kind;
builders return scenario dicts for ``Lab.write_scenario`` and tests update a copy.
A list value is a sequence: each call to the same key takes the next entry and the
last one repeats.
"""

from __future__ import annotations

import json
from typing import Any

import lab_scenarios as sc
from lab_testlib import SENTINEL, arn

PRIMARY = sc.PRIMARY
SECOND = sc.SECOND
OWNER = sc.OWNER
RECIPIENT = sc.RECIPIENT
TAG = sc.TAG
OWNER_PROFILE = sc.OWNER_PROFILE
RECIPIENT_PROFILE = sc.RECIPIENT_PROFILE

CREATED_AT = "2026-10-11T00:00:00.123000+00:00"
SHARED_RP = sc.dest_rp(PRIMARY)
DELETE_AT = "2026-10-18T01:00:00.123000+00:00"
RESTORE_JOB_ID = "33333333-cccc-4ccc-8ccc-cccccccccccc"
RESTORED_VOLUME_ID = "fsvol-0999999999999999a"
RESTORED_VOLUME_ARN = arn("fsx", PRIMARY, RECIPIENT, f"volume/{sc.EXISTING_RECIPIENT_FS}/{RESTORED_VOLUME_ID}")
ROOT_VOLUME_ID = "fsvol-0888888888888888b"
ROOT_VOLUME_ARN = arn("fsx", PRIMARY, RECIPIENT, f"volume/{sc.EXISTING_RECIPIENT_FS}/{ROOT_VOLUME_ID}")
RECIPIENT_SVM_ARN = arn(
    "fsx", PRIMARY, RECIPIENT, f"storage-virtual-machine/{sc.EXISTING_RECIPIENT_FS}/{sc.RECIPIENT_RESTORE_SVM}"
)
PORTAL_FUNCTION = "portal-restore-function"
PORTAL_RESTORE_DESCRIPTION = "Starts an AWS Backup restore job to a new FSx for ONTAP volume (approval-gated write)"
OTHER_VOLUME_ARN = arn("fsx", PRIMARY, OWNER, f"volume/{SENTINEL.FS}/fsvol-0777777777777777c")
OTHER_RP = arn("fsx", PRIMARY, OWNER, "backup/backup-0fedcba987654321f")
KEY_ID = "11111111-1111-4111-8111-111111111111"
SHARE_ARN = sc.share_arn(PRIMARY)
DELETE_KEY_TOKEN = f"delete-key-alias/{TAG}-fs"
TAGGED = {"body": {"Tags": [{"Key": "Project", "Value": TAG}]}}
NO_TAG = {"body": {"Tags": []}}
FOREIGN_TAG = {"body": {"Tags": [{"Key": "Project", "Value": "someone-else"}]}}


def who(account: str) -> dict[str, Any]:
    """An sts get-caller-identity answer."""
    return {"body": {"Account": account, "Arn": f"arn:aws:sts::{account}:assumed-role/Role/session", "UserId": "X"}}


# --------------------------------------------------------------------------
# 06
# --------------------------------------------------------------------------


def shared_row(region: str = PRIMARY, account: str = OWNER, vault_type: str = "LOGICALLY_AIR_GAPPED_BACKUP_VAULT"):
    """One row of the recipient's shared-vault list (no VaultState, zero recovery points)."""
    row: dict[str, Any] = {
        "BackupVaultName": sc.LAG_VAULT,
        "BackupVaultArn": arn("backup", region, account, f"backup-vault:{sc.LAG_VAULT}"),
        "NumberOfRecoveryPoints": 0,
    }
    if vault_type:
        row["VaultType"] = vault_type
    return row


def shared_recovery_point(region: str = PRIMARY, status: str = "COMPLETED") -> dict[str, Any]:
    """One recovery point of the shared vault as the recipient lists it."""
    return {
        "RecoveryPointArn": arn("backup", region, OWNER, "recovery-point:cccccccc-3333-4333-8333-cccccccccccc"),
        "Status": status,
        "CreationDate": CREATED_AT,
        "CalculatedLifecycle": {"DeleteAt": DELETE_AT},
    }


def verify() -> dict[str, Any]:
    """06 (one Region): sharing works, the account id is required, one recovery point exists."""
    owner_stack = sc.stack_body(f"{TAG}-owner-base", "CREATE_COMPLETE", sc.OWNER_BASE_OUTPUTS)
    recipient_stack = sc.stack_body(
        f"{TAG}-recipient-{PRIMARY}",
        "CREATE_COMPLETE",
        {"RestoreRoleArn": sc.RECIPIENT_ROLE_ARN, "FileSystemId": "fs-0123123123123123a", "RestoreSvmId": "svm-0f"},
    )
    return {
        f"sts get-caller-identity --profile={OWNER_PROFILE}": who(OWNER),
        f"sts get-caller-identity --profile={RECIPIENT_PROFILE}": who(RECIPIENT),
        f"backup list-backup-vaults --by-shared --profile={RECIPIENT_PROFILE}": {
            "body": {"BackupVaultList": [shared_row()]}
        },
        f"backup list-backup-vaults --by-shared --profile={OWNER_PROFILE}": {"body": {"BackupVaultList": []}},
        "backup list-recovery-points-by-backup-vault !--backup-vault-account-id": sc.err(
            "AccessDeniedException", "User is not authorized to perform: backup:ListRecoveryPointsByBackupVault"
        ),
        "backup list-recovery-points-by-backup-vault --backup-vault-account-id": {
            "body": {"RecoveryPoints": [shared_recovery_point()]}
        },
        "backup get-recovery-point-restore-metadata": {"body": {"RestoreMetadata": restore_metadata()}},
        f"cloudformation describe-stacks --stack-name={TAG}-owner-base": {"body": owner_stack},
        f"cloudformation describe-stacks --stack-name={TAG}-recipient-{PRIMARY}": {"body": recipient_stack},
        f"fsx describe-file-systems --profile={OWNER_PROFILE}": {
            "body": {"FileSystems": [{"FileSystemId": SENTINEL.FS, "CreationTime": "2026-10-11T09:00:00+09:00"}]}
        },
        f"fsx describe-file-systems --profile={RECIPIENT_PROFILE}": {
            "body": {
                "FileSystems": [{"FileSystemId": "fs-0123123123123123a", "CreationTime": "2026-10-11T10:00:00+09:00"}]
            }
        },
    }


def cost_body(amount: str = "12.3456", service: str = "Amazon FSx") -> dict[str, Any]:
    """A Cost Explorer get-cost-and-usage answer with one group."""
    return {
        "ResultsByTime": [
            {
                "TimePeriod": {"Start": "2026-10-11", "End": "2026-10-12"},
                "Groups": [{"Keys": [service], "Metrics": {"UnblendedCost": {"Amount": amount, "Unit": "USD"}}}],
            }
        ]
    }


def cost() -> dict[str, Any]:
    """06 --cost: both accounts answer."""
    return {
        f"sts get-caller-identity --profile={OWNER_PROFILE}": who(OWNER),
        f"sts get-caller-identity --profile={RECIPIENT_PROFILE}": who(RECIPIENT),
        "ce get-cost-and-usage": {"body": cost_body()},
    }


# --------------------------------------------------------------------------
# 08
# --------------------------------------------------------------------------


def restore_metadata() -> dict[str, str]:
    """RestoreMetadata as get-recovery-point-restore-metadata returns it (capitalised keys)."""
    ontap = {
        "JunctionPath": "/vol_lab",
        "SizeInMegabytes": "1024",
        "StorageEfficiencyEnabled": "false",
        "StorageVirtualMachineId": SENTINEL.SVM,
        "TieringPolicy": '{"Name":"AUTO"}',
        "VolumeType": "ONTAP",
    }
    return {
        "Name": "vol_lab",
        "OntapConfiguration": json.dumps(ontap),
        "FileSystemId": SENTINEL.FS,
        "VolumeId": SENTINEL.VOLUME,
        "Lifecycle": "CREATED",
    }


def recipient_fs(svm_ids: list[str]) -> dict[str, Any]:
    """fsx describe-file-systems and describe-storage-virtual-machines answers for the recipient FS."""
    fs = {
        "FileSystemId": sc.EXISTING_RECIPIENT_FS,
        "Lifecycle": "AVAILABLE",
        "NetworkType": "IPV4",
        "OntapConfiguration": {"DeploymentType": "SINGLE_AZ_1", "ThroughputCapacity": 128},
    }
    svms = [
        {"StorageVirtualMachineId": svm, "Lifecycle": "CREATED", "Name": f"svm_{index}"}
        for index, svm in enumerate(svm_ids)
    ]
    return {
        "fsx describe-file-systems": {"body": {"FileSystems": [fs]}},
        "fsx describe-storage-virtual-machines --filters": {"body": {"StorageVirtualMachines": svms}},
    }


def restored_volume(state: str = "CREATED") -> dict[str, Any]:
    """The volume the restore creates, as describe-volumes lists it."""
    return {
        "VolumeId": RESTORED_VOLUME_ID,
        "Name": "vol_restored",
        "Lifecycle": state,
        "ResourceARN": RESTORED_VOLUME_ARN,
        "OntapConfiguration": {"StorageVirtualMachineRoot": False},
    }


def volumes(*vols: dict[str, Any]) -> dict[str, Any]:
    """A describe-volumes body."""
    return {"body": {"Volumes": list(vols)}}


def restore(via: str = "cli") -> dict[str, Any]:
    """08: one COMPLETED recovery point; the job is RUNNING once, then COMPLETED; the volume is created."""
    scenario: dict[str, Any] = {
        f"sts get-caller-identity --profile={RECIPIENT_PROFILE}": who(RECIPIENT),
        f"cloudformation describe-stacks --stack-name={TAG}-recipient-{PRIMARY}": {
            "body": sc.stack_body(
                f"{TAG}-recipient-{PRIMARY}",
                "CREATE_COMPLETE",
                {
                    "RestoreRoleArn": sc.RECIPIENT_ROLE_ARN,
                    "FileSystemId": sc.EXISTING_RECIPIENT_FS,
                    "RestoreSvmId": sc.RECIPIENT_RESTORE_SVM,
                },
            )
        },
        "backup list-recovery-points-by-backup-vault": {"body": {"RecoveryPoints": [shared_recovery_point()]}},
        "backup get-recovery-point-restore-metadata": {"body": {"RestoreMetadata": restore_metadata()}},
        "backup start-restore-job": {"body": {"RestoreJobId": RESTORE_JOB_ID}},
        "backup describe-restore-job": [
            {"body": {"RestoreJobId": RESTORE_JOB_ID, "Status": "RUNNING", "PercentDone": "0.0"}},
            {"body": {"RestoreJobId": RESTORE_JOB_ID, "Status": "COMPLETED", "PercentDone": "100.0"}},
        ],
        # first call: the pre-check (no volume of that name yet); then the polls
        "fsx describe-volumes --filters": [volumes(), volumes(restored_volume())],
        "fsx tag-resource": {"body": {}},
    }
    scenario.update(recipient_fs([sc.RECIPIENT_RESTORE_SVM]))
    if via == "portal":
        scenario["lambda list-functions"] = {
            "body": {
                "Functions": [
                    {"FunctionName": PORTAL_FUNCTION, "Description": PORTAL_RESTORE_DESCRIPTION},
                    {"FunctionName": "some-other-function", "Description": "something else"},
                ]
            }
        }
        scenario["lambda invoke"] = [
            {"body": {"restoreJobId": RESTORE_JOB_ID, "error": None}},
            {"body": {"restoreJob": {"restoreJobId": RESTORE_JOB_ID, "status": "RUNNING", "statusMessage": ""}}},
            {"body": {"restoreJob": {"restoreJobId": RESTORE_JOB_ID, "status": "COMPLETED", "statusMessage": ""}}},
        ]
        for key in ("backup start-restore-job", "backup describe-restore-job"):
            scenario.pop(key)
    return scenario


# --------------------------------------------------------------------------
# 09
# --------------------------------------------------------------------------


def revoke() -> dict[str, Any]:
    """09 (one Region): one ACTIVE share; the recipient list still holds the vault once, then not."""
    return {
        f"sts get-caller-identity --profile={OWNER_PROFILE}": who(OWNER),
        f"sts get-caller-identity --profile={RECIPIENT_PROFILE}": who(RECIPIENT),
        "ram get-resource-shares": sc.share_list(PRIMARY),
        "ram delete-resource-share": {"body": {"returnValue": True}},
        f"backup list-backup-vaults --by-shared --profile={RECIPIENT_PROFILE}": [
            {"body": {"BackupVaultList": [shared_row()]}},
            {"body": {"BackupVaultList": []}},
        ],
        "backup list-recovery-points-by-backup-vault": sc.err("AccessDeniedException", "not authorized"),
    }


# --------------------------------------------------------------------------
# 10
# --------------------------------------------------------------------------


def lag_listing(count: int = 0, region: str = PRIMARY) -> dict[str, Any]:
    """Scenario keys for an air-gapped vault with ``count`` recovery points in ``region``."""
    rps = [
        {
            "RecoveryPointArn": arn("backup", region, OWNER, f"recovery-point:dddddddd-0000-4000-8000-00000000000{i}"),
            "ResourceArn": sc.VOLUME_ARN,
            "CalculatedLifecycle": {"DeleteAt": DELETE_AT},
        }
        for i in range(count)
    ]
    return {
        f"backup list-backup-vaults --by-vault-type --region={region}": {
            "body": {
                "BackupVaultList": [
                    {
                        "BackupVaultName": sc.LAG_VAULT,
                        "BackupVaultArn": sc.lag_arn(region),
                        "VaultType": "LOGICALLY_AIR_GAPPED_BACKUP_VAULT",
                        "NumberOfRecoveryPoints": count,
                    }
                ]
            }
        },
        f"backup list-recovery-points-by-backup-vault --backup-vault-name={sc.LAG_VAULT} --region={region}": {
            "body": {"RecoveryPoints": rps}
        },
    }


def teardown(delete_key: bool = False) -> dict[str, Any]:
    """10 (one Region): everything exists once and is gone after its delete call.

    describe-stacks of each stack answers "present" for the first read and "absent"
    afterwards; ram get-resource-shares answers the share once; the volume reads
    answer VolumeNotFound; the LAG vault is empty and managed by its stack.
    """
    present_owner = sc.stack_body(f"{TAG}-owner-base", "CREATE_COMPLETE", sc.OWNER_BASE_OUTPUTS)
    present_lag = sc.lag_stack(PRIMARY)
    present_recipient = sc.stack_body(
        f"{TAG}-recipient-{PRIMARY}",
        "CREATE_COMPLETE",
        {
            "RestoreRoleArn": sc.RECIPIENT_ROLE_ARN,
            "FileSystemId": sc.EXISTING_RECIPIENT_FS,
            "RestoreSvmId": sc.RECIPIENT_RESTORE_SVM,
        },
    )
    own_rp = {"RecoveryPointArn": sc.SRC_RP, "ResourceArn": sc.VOLUME_ARN, "Status": "COMPLETED"}
    scenario: dict[str, Any] = {
        f"sts get-caller-identity --profile={OWNER_PROFILE}": who(OWNER),
        f"sts get-caller-identity --profile={RECIPIENT_PROFILE}": who(RECIPIENT),
        "backup list-backup-jobs": {"body": {"BackupJobs": []}},
        "backup list-copy-jobs": {"body": {"CopyJobs": []}},
        "backup list-restore-jobs": {"body": {"RestoreJobs": []}},
        "ram get-resource-shares": [sc.share_list(PRIMARY), {"body": {"resourceShares": []}}],
        "ram delete-resource-share": {"body": {"returnValue": True}},
        f"cloudformation describe-stacks --stack-name={TAG}-owner-base": [
            {"body": present_owner},
            sc.no_stack(f"{TAG}-owner-base"),
        ],
        f"cloudformation describe-stacks --stack-name={TAG}-lag-{PRIMARY}": [
            {"body": present_lag},
            sc.no_stack(f"{TAG}-lag-{PRIMARY}"),
        ],
        f"cloudformation describe-stacks --stack-name={TAG}-recipient-{PRIMARY}": [
            {"body": present_recipient},
            sc.no_stack(f"{TAG}-recipient-{PRIMARY}"),
        ],
        "cloudformation describe-stack-resource": {
            "body": {"StackResourceDetail": {"LogicalResourceId": "StandardVault", "PhysicalResourceId": sc.STD_VAULT}}
        },
        "cloudformation delete-stack": {"body": {}},
        f"backup list-recovery-points-by-backup-vault --backup-vault-name={sc.STD_VAULT}": [
            {"body": {"RecoveryPoints": [own_rp]}},
            {"body": {"RecoveryPoints": []}},
        ],
        "backup delete-recovery-point": {"body": {}},
        "fsx describe-storage-virtual-machines --storage-virtual-machine-ids": {
            "body": {
                "StorageVirtualMachines": [
                    {
                        "StorageVirtualMachineId": sc.RECIPIENT_RESTORE_SVM,
                        "Lifecycle": "CREATED",
                        "ResourceARN": RECIPIENT_SVM_ARN,
                    }
                ]
            }
        },
        f"fsx list-tags-for-resource --resource-arn={RECIPIENT_SVM_ARN}": TAGGED,
        f"fsx list-tags-for-resource --resource-arn={sc.VOLUME_ARN}": TAGGED,
        "fsx describe-volumes --filters": volumes(
            {
                "VolumeId": ROOT_VOLUME_ID,
                "Name": "svm_restore_root",
                "Lifecycle": "CREATED",
                "ResourceARN": ROOT_VOLUME_ARN,
                "OntapConfiguration": {"StorageVirtualMachineRoot": True},
            },
            restored_volume(),
        ),
        "fsx describe-volumes --volume-ids": sc.err("VolumeNotFound", "The volume does not exist."),
        "fsx delete-volume": {"body": {"VolumeId": "x", "Lifecycle": "DELETING"}},
        "kms describe-key": {
            "body": {
                "KeyMetadata": {
                    "KeyId": KEY_ID,
                    "Arn": sc.KEY_ARN,
                    "KeyState": "Enabled",
                    "Description": "lab key",
                }
            }
        },
        "fsx describe-file-systems": {"body": {"FileSystems": []}},
        "fsx describe-backups": {"body": {"Backups": []}},
        "kms schedule-key-deletion": {"body": {"KeyId": sc.KEY_ARN, "DeletionDate": "2026-10-18T00:00:00+00:00"}},
        "kms delete-alias": {"body": {}},
    }
    scenario.update(lag_listing(0))
    return scenario
