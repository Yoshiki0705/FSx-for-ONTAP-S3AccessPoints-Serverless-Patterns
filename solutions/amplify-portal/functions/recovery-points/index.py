"""Read-only AWS Backup recovery-point surface for FSx for ONTAP volumes.

This Lambda lists AWS Backup recovery points so the portal can show them beside
the ONTAP snapshot list, labelled so the two are not confused. Amazon FSx for
NetApp ONTAP recovery points are AWS Backup objects stored in a backup vault,
distinct from ONTAP snapshots, which live inside the FSx for ONTAP file system.

Everything here is read-only. There is no restore path and no mutation: starting
a restore job (#460) and the cross-account UI / job-state alerting (#461) are
deliberately out of scope. The handler accepts an optional ``backupVaultAccountId``
so a later cross-account surface needs no handler change, but it ships no UI that
sets it.

Unlike the ONTAP read handlers this one reaches a regional AWS control-plane API
over the Lambda service network, so it needs no VPC, no shared layer, and no
Secrets Manager credential — only a boto3 ``backup`` client.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Vaults to list when the caller names none. A JSON array of vault names, supplied
# by backend.ts from config.backupVaultNames. Empty means "list every vault the
# role can see" is not attempted here — the caller must name one, or the UI reads
# the configured set.
BACKUP_VAULT_NAMES: list[str] = json.loads(os.environ.get("BACKUP_VAULT_NAMES", "[]"))

# The one resource type this portal surfaces. FSx for ONTAP recovery points are
# ResourceType "FSx"; scoping the list keeps unrelated recovery points out.
FSX_RESOURCE_TYPE = "FSx"


def _client():
    """Build the AWS Backup client.

    Kept in a function so the tests can patch ``boto3`` before the client is built,
    rather than at import time.
    """
    return boto3.client("backup")


def _recovery_point_row(point: dict[str, Any], backup_vault_name: str) -> dict[str, Any]:
    """One recovery point reduced to the fields the list UI reads.

    ARNs come back as strings in the response, so no ``fsx:*`` or ``kms:*`` call is
    needed to render a row. ``Status`` and ``StatusMessage`` are passed through
    verbatim — the UI does not key a label on any literal the enum does not define.
    """
    created = point.get("CreationDate")
    return {
        "recoveryPointArn": point.get("RecoveryPointArn", ""),
        "resourceArn": point.get("ResourceArn", ""),
        "resourceType": point.get("ResourceType", ""),
        "creationDate": created.isoformat() if hasattr(created, "isoformat") else "",
        "status": point.get("Status", ""),
        "statusMessage": point.get("StatusMessage", ""),
        "backupVaultName": point.get("BackupVaultName") or backup_vault_name,
        "isEncrypted": bool(point.get("IsEncrypted", False)),
        "encryptionKeyArn": point.get("EncryptionKeyArn", ""),
        "backupSizeInBytes": point.get("BackupSizeInBytes", 0),
    }


def _vault_row(vault: dict[str, Any]) -> dict[str, Any]:
    """One backup vault reduced to the fields the list UI reads.

    ``VaultType`` is what distinguishes a logically air-gapped vault
    (``LOGICALLY_AIR_GAPPED_BACKUP_VAULT``) from an ordinary one, which the UI
    renders as an air-gapped chip.
    """
    return {
        "backupVaultName": vault.get("BackupVaultName", ""),
        "backupVaultArn": vault.get("BackupVaultArn", ""),
        "vaultType": vault.get("VaultType", ""),
        "locked": bool(vault.get("Locked", False)),
        "numberOfRecoveryPoints": vault.get("NumberOfRecoveryPoints", 0),
    }


def _list_recovery_points(event: dict[str, Any]) -> dict[str, Any]:
    """List FSx recovery points in one vault, or across the configured vaults.

    Reads ``backupVaultName`` (optional; the configured vaults are used when it is
    absent), ``backupVaultAccountId`` (optional, forwarded for a future
    cross-account surface), ``resourceArn`` (optional, one file system), and
    ``maxResults`` (optional).
    """
    backup_vault_name = event.get("backupVaultName", "")
    backup_vault_account_id = event.get("backupVaultAccountId", "")
    resource_arn = event.get("resourceArn", "")
    max_results = event.get("maxResults", 0)

    vaults = [backup_vault_name] if backup_vault_name else BACKUP_VAULT_NAMES
    client = _client()
    rows: list[dict[str, Any]] = []

    for vault in vaults:
        kwargs: dict[str, Any] = {"BackupVaultName": vault, "ByResourceType": FSX_RESOURCE_TYPE}
        if backup_vault_account_id:
            kwargs["BackupVaultAccountId"] = backup_vault_account_id
        if resource_arn:
            kwargs["ByResourceArn"] = resource_arn
        if max_results:
            kwargs["MaxResults"] = max_results
        response = client.list_recovery_points_by_backup_vault(**kwargs)
        rows.extend(_recovery_point_row(point, vault) for point in response.get("RecoveryPoints", []))

    return {"recoveryPoints": rows, "error": None}


def _list_backup_vaults(event: dict[str, Any]) -> dict[str, Any]:
    """List the backup vaults the role can see, with their vault type and lock state."""
    client = _client()
    response = client.list_backup_vaults()
    vaults = [_vault_row(vault) for vault in response.get("BackupVaultList", [])]
    return {"backupVaults": vaults, "error": None}


def _describe_recovery_point(event: dict[str, Any]) -> dict[str, Any]:
    """Describe one recovery point.

    Both ``recoveryPointArn`` and ``backupVaultName`` are required;
    ``backupVaultAccountId`` is optional and forwarded when present.
    """
    recovery_point_arn = event.get("recoveryPointArn", "")
    backup_vault_name = event.get("backupVaultName", "")
    if not recovery_point_arn or not backup_vault_name:
        return {"recoveryPoint": None, "error": "recoveryPointArn and backupVaultName are required"}

    backup_vault_account_id = event.get("backupVaultAccountId", "")
    client = _client()
    kwargs: dict[str, Any] = {"BackupVaultName": backup_vault_name, "RecoveryPointArn": recovery_point_arn}
    if backup_vault_account_id:
        kwargs["BackupVaultAccountId"] = backup_vault_account_id
    point = client.describe_recovery_point(**kwargs)

    created = point.get("CreationDate")
    return {
        "recoveryPoint": {
            "recoveryPointArn": point.get("RecoveryPointArn", ""),
            "resourceArn": point.get("ResourceArn", ""),
            "resourceType": point.get("ResourceType", ""),
            "creationDate": created.isoformat() if hasattr(created, "isoformat") else "",
            "status": point.get("Status", ""),
            "statusMessage": point.get("StatusMessage", ""),
            "backupVaultName": point.get("BackupVaultName") or backup_vault_name,
            "isEncrypted": bool(point.get("IsEncrypted", False)),
            "encryptionKeyArn": point.get("EncryptionKeyArn", ""),
            "encryptionKeyType": point.get("EncryptionKeyType", ""),
            "storageClass": point.get("StorageClass", ""),
            "vaultType": point.get("VaultType", ""),
            "backupSizeInBytes": point.get("BackupSizeInBytes", 0),
        },
        "error": None,
    }


def handler(event, context):
    """Dispatch a read-only AWS Backup query.

    Actions:
      - ``listRecoveryPoints`` (default): FSx recovery points in a vault, or across
        the configured vaults.
      - ``listBackupVaults``: the vaults the role can see, with vault type.
      - ``describeRecoveryPoint``: one recovery point in detail.

    Returns a plain dict on every path. A boto3 ``ClientError`` or any other
    exception is caught and returned as ``{"...": [], "error": str(e)}`` so an
    error never raises to AppSync (mirrors ``functions/snapshots/index.py``).
    """
    action = event.get("action", "listRecoveryPoints")

    try:
        if action == "listBackupVaults":
            return _list_backup_vaults(event)
        if action == "describeRecoveryPoint":
            return _describe_recovery_point(event)
        if action == "listRecoveryPoints":
            return _list_recovery_points(event)
        return {"recoveryPoints": [], "error": f"Unknown action: {action}"}
    except ClientError as e:
        logger.warning("AWS Backup call failed: %s", e)
        return {"recoveryPoints": [], "backupVaults": [], "recoveryPoint": None, "error": str(e)}
    except Exception as e:  # noqa: BLE001 - never raise to AppSync
        logger.exception("Error handling action %s", action)
        return {"recoveryPoints": [], "backupVaults": [], "recoveryPoint": None, "error": str(e)}
