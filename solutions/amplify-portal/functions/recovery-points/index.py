"""Read-only AWS Backup recovery-point surface for FSx for ONTAP volumes.

This Lambda lists AWS Backup recovery points so the portal can show them beside
the ONTAP snapshot list, labelled so the two are not confused. Amazon FSx for
NetApp ONTAP recovery points are AWS Backup objects stored in a backup vault,
distinct from ONTAP snapshots, which live inside the FSx for ONTAP file system.

Everything here is read-only; starting a restore job is ``functions/restore``.
The handler can read a vault in another Region of this account, and a logically
air-gapped vault that another account shared through AWS RAM:

* ``backupVaultRegion`` selects one Region per request. It must be this function's
  own Region or one of ``BACKUP_REGIONS``; nothing else is ever called.
* ``backupVaultAccountId`` selects a vault in another account. The request is only
  forwarded when that vault is in the current ``ByShared`` list for the Region, so a
  caller cannot probe arbitrary account IDs and a revoked share is reported as
  ``VaultNotShared`` rather than as an opaque access error.
* ``listSharedBackupVaults`` is the ``ByShared`` list the portal offers as choices.

Unlike the ONTAP read handlers this one reaches a regional AWS control-plane API
over the Lambda service network, so it needs no VPC, no shared layer, and no
Secrets Manager credential — only a boto3 ``backup`` client.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Vaults to list when the caller names none. A JSON array of vault names, supplied
# by backend.ts from config.backupVaultNames. Empty means "list every vault the
# role can see" is not attempted here — the caller must name one, or the UI reads
# the configured set. The set applies to this function's own Region and account
# only: a vault name is unique per (account, Region), so a configured name is
# meaningless anywhere else.
BACKUP_VAULT_NAMES: list[str] = json.loads(os.environ.get("BACKUP_VAULT_NAMES", "[]"))

# The Region this function runs in. Lambda always sets AWS_REGION. It is always
# allowed, and it is the only Region where restores are started (functions/restore
# builds its client without a Region).
HOME_REGION: str = os.environ.get("AWS_REGION", "")

# Further Regions a request may select, a JSON array supplied by backend.ts from
# config.backupRegions. ListBackupVaults cannot be scoped to a Region in IAM, so this
# list is what stops an authenticated caller pointing the function at any Region.
BACKUP_REGIONS: list[str] = json.loads(os.environ.get("BACKUP_REGIONS", "[]"))

# The one resource type this portal surfaces. FSx for ONTAP recovery points are
# ResourceType "FSx"; scoping the list keeps unrelated recovery points out.
FSX_RESOURCE_TYPE = "FSx"

# ``[0-9]``, not ``\d``: ``\d`` also matches the digits of other scripts.
_ACCOUNT_ID = re.compile(r"[0-9]{12}")
_REGION_NAME = re.compile(r"[a-z]{2}(-[a-z]+)+-[0-9]")

# ListBackupVaults pages are followed to the end, with a ceiling so a response that
# never stops returning a token cannot hold the function until its timeout.
_MAX_VAULT_PAGES = 20


class _Rejected(Exception):
    """A request refused before any AWS call, carrying the code the UI keys on."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _result(**fields: Any) -> dict[str, Any]:
    """A response with every key present, so no path leaves the UI guessing.

    ``errorCode`` is the AWS error code (``AccessDeniedException``) or one of this
    handler's own refusals (``InvalidParameter``, ``RegionNotAllowed``,
    ``VaultNameRequired``, ``VaultNotShared``). The UI branches on it; it never
    reads the message text to work out what happened.

    ``homeRegion`` and ``regions`` are on every path, failures included. The UI builds
    its Region selector from them, so an answer that failed (an opt-in Region that is
    not enabled, throttling) must not take the selector, and the way back to the home
    Region, away with it.
    """
    response: dict[str, Any] = {
        "recoveryPoints": [],
        "backupVaults": [],
        "recoveryPoint": None,
        "error": None,
        "errorCode": None,
        "homeRegion": HOME_REGION,
        "regions": _allowed_regions(),
    }
    response.update(fields)
    return response


def _client(region: str = ""):
    """Build the AWS Backup client for ``region``.

    Kept in a function so the tests can patch ``boto3`` before the client is built,
    rather than at import time. The home Region (or an unknown one) gets the same
    Region-less client as before, so the default path is unchanged.
    """
    if not region or region == HOME_REGION:
        return boto3.client("backup")
    return boto3.client("backup", region_name=region)


def _account_of(arn: Any) -> str:
    """The account ID in an ARN, or "" when ``arn`` is not an ARN with one."""
    if not isinstance(arn, str):
        return ""
    parts = arn.split(":")
    if len(parts) < 5 or not _ACCOUNT_ID.fullmatch(parts[4]):
        return ""
    return parts[4]


def _own_account_id(context: Any) -> str:
    """This function's account, from its invoked ARN; "" when there is no context."""
    return _account_of(getattr(context, "invoked_function_arn", ""))


def _allowed_regions() -> list[str]:
    """The Regions a request may select: home first, then the configured ones."""
    regions: list[str] = []
    for region in [HOME_REGION, *BACKUP_REGIONS]:
        if region and region not in regions:
            regions.append(region)
    return regions


def _requested_region(event: dict[str, Any]) -> str:
    """The Region a request selects, defaulting to home; refuses anything not allowed."""
    raw = event.get("backupVaultRegion")
    if raw is None or raw == "":
        return HOME_REGION
    if not isinstance(raw, str) or not _REGION_NAME.fullmatch(raw) or raw not in _allowed_regions():
        raise _Rejected("RegionNotAllowed", "backupVaultRegion is not one of the Regions this portal may read")
    return raw


def _requested_account(event: dict[str, Any]) -> str:
    """The vault-owner account a request names, "" when it names none.

    A JSON number is refused along with every other non-string: ``111122223333``
    sent as a number is a different value than the string the API takes.
    """
    raw = event.get("backupVaultAccountId")
    if raw is None or raw == "":
        return ""
    if not isinstance(raw, str) or not _ACCOUNT_ID.fullmatch(raw):
        raise _Rejected("InvalidParameter", "backupVaultAccountId must be a 12-digit AWS account ID")
    return raw


def _requested_vault_name(event: dict[str, Any]) -> str:
    raw = event.get("backupVaultName", "")
    if raw is None:
        return ""
    if not isinstance(raw, str):
        raise _Rejected("InvalidParameter", "backupVaultName must be a string")
    return raw


def _scope(event: dict[str, Any], own_account_id: str) -> dict[str, Any]:
    """Resolve which (account, Region, vault name) a request reads, or refuse.

    Refusals come before any AWS call. The configured vault names are only a default
    for this account in the home Region, so any other scope must name its vault:
    falling back would query a different vault that happens to share a name.
    """
    region = _requested_region(event)
    account_id = _requested_account(event)
    vault_name = _requested_vault_name(event)
    # With no context the account is unknown, and a named account is then treated as
    # another one — the strict reading, which forwards it and checks the share.
    cross_account = bool(account_id) and account_id != own_account_id
    if (cross_account or region != HOME_REGION) and not vault_name:
        raise _Rejected("VaultNameRequired", "backupVaultName is required outside this account's home Region")
    return {
        "region": region,
        "accountId": account_id if cross_account else "",
        "vaultName": vault_name,
        "crossAccount": cross_account,
    }


def _vault_pages(client: Any, *, shared: bool) -> list[dict[str, Any]]:
    """Every vault ListBackupVaults returns, following NextToken.

    ``ByVaultType`` is deliberately not sent with ``ByShared``: the shared list is the
    shared logically air-gapped vaults, and a second filter would only narrow it.
    """
    vaults: list[dict[str, Any]] = []
    token = None
    for _ in range(_MAX_VAULT_PAGES):
        kwargs: dict[str, Any] = {}
        if shared:
            kwargs["ByShared"] = True
        if token:
            kwargs["NextToken"] = token
        response = client.list_backup_vaults(**kwargs)
        vaults.extend(response.get("BackupVaultList", []))
        token = response.get("NextToken")
        if not token:
            break
    return vaults


def _require_shared(client: Any, vault_name: str, account_id: str) -> None:
    """Refuse unless (vault, owner) is in the current shared list for this Region.

    A revoked or never-accepted share, a name that was never shared, and an account
    ID the caller made up all look the same from here, and all are answered with
    ``VaultNotShared`` before ``ListRecoveryPointsByBackupVault`` is called.
    """
    for vault in _vault_pages(client, shared=True):
        if vault.get("BackupVaultName") == vault_name and _account_of(vault.get("BackupVaultArn")) == account_id:
            return
    raise _Rejected("VaultNotShared", "The vault is not in this Region's list of vaults shared with this account")


def _recovery_point_row(
    point: dict[str, Any], backup_vault_name: str, region: str, fallback_owner: str
) -> dict[str, Any]:
    """One recovery point reduced to the fields the list UI reads.

    ARNs come back as strings in the response, so no ``fsx:*`` or ``kms:*`` call is
    needed to render a row. ``Status`` and ``StatusMessage`` are passed through
    verbatim — the UI does not key a label on any literal the enum does not define.
    ``VaultType`` is passed through too, so a shared vault, which is not in the
    caller's own vault list, still shows its air-gapped marker.
    """
    created = point.get("CreationDate")
    vault_arn = point.get("BackupVaultArn", "")
    return {
        "recoveryPointArn": point.get("RecoveryPointArn", ""),
        "resourceArn": point.get("ResourceArn", ""),
        "resourceType": point.get("ResourceType", ""),
        "creationDate": created.isoformat() if hasattr(created, "isoformat") else "",
        "status": point.get("Status", ""),
        "statusMessage": point.get("StatusMessage", ""),
        "backupVaultName": point.get("BackupVaultName") or backup_vault_name,
        "backupVaultArn": vault_arn,
        "ownerAccountId": _account_of(vault_arn) or fallback_owner,
        "region": region,
        "vaultType": point.get("VaultType", ""),
        "isEncrypted": bool(point.get("IsEncrypted", False)),
        "encryptionKeyArn": point.get("EncryptionKeyArn", ""),
        "backupSizeInBytes": point.get("BackupSizeInBytes", 0),
    }


def _vault_row(vault: dict[str, Any], region: str, own_account_id: str) -> dict[str, Any]:
    """One backup vault reduced to the fields the list UI reads.

    ``VaultType`` is what distinguishes a logically air-gapped vault
    (``LOGICALLY_AIR_GAPPED_BACKUP_VAULT``) from an ordinary one, which the UI
    renders as an air-gapped chip. ``VaultType`` and ``VaultState`` are passed
    through unconverted, so a value the UI does not know is shown rather than hidden.
    The response has no owner field; the owner is the account in the vault ARN.
    """
    arn = vault.get("BackupVaultArn", "")
    owner = _account_of(arn)
    return {
        "backupVaultName": vault.get("BackupVaultName", ""),
        "backupVaultArn": arn,
        "ownerAccountId": owner,
        "ownedByThisAccount": bool(own_account_id) and owner == own_account_id,
        "region": region,
        "vaultType": vault.get("VaultType", ""),
        "vaultState": vault.get("VaultState", ""),
        "encryptionKeyType": vault.get("EncryptionKeyType", ""),
        "locked": bool(vault.get("Locked", False)),
        "numberOfRecoveryPoints": vault.get("NumberOfRecoveryPoints", 0),
    }


def _list_recovery_points(event: dict[str, Any], own_account_id: str) -> dict[str, Any]:
    """List FSx recovery points in one vault, or across the configured vaults.

    Reads ``backupVaultName`` (optional for this account's home Region, where the
    configured vaults are used when it is absent), ``backupVaultAccountId``
    (optional, a vault shared by another account), ``backupVaultRegion`` (optional),
    ``resourceArn`` (optional, one file system), and ``maxResults`` (optional).
    """
    scope = _scope(event, own_account_id)
    resource_arn = event.get("resourceArn", "")
    max_results = event.get("maxResults", 0)

    client = _client(scope["region"])
    if scope["crossAccount"]:
        _require_shared(client, scope["vaultName"], scope["accountId"])

    vaults = [scope["vaultName"]] if scope["vaultName"] else BACKUP_VAULT_NAMES
    fallback_owner = scope["accountId"] or own_account_id
    rows: list[dict[str, Any]] = []

    for vault in vaults:
        kwargs: dict[str, Any] = {"BackupVaultName": vault, "ByResourceType": FSX_RESOURCE_TYPE}
        if scope["crossAccount"]:
            kwargs["BackupVaultAccountId"] = scope["accountId"]
        if resource_arn:
            kwargs["ByResourceArn"] = resource_arn
        if max_results:
            kwargs["MaxResults"] = max_results
        response = client.list_recovery_points_by_backup_vault(**kwargs)
        rows.extend(
            _recovery_point_row(point, vault, scope["region"], fallback_owner)
            for point in response.get("RecoveryPoints", [])
        )

    return _result(recoveryPoints=rows)


def _list_backup_vaults(event: dict[str, Any], own_account_id: str) -> dict[str, Any]:
    """List the backup vaults this account owns in one Region, with type and lock state.

    The response also names the Regions a request may select (see ``_result``), so the
    Region selector needs no second route for configuration.
    """
    region = _requested_region(event)
    vaults = [_vault_row(vault, region, own_account_id) for vault in _vault_pages(_client(region), shared=False)]
    return _result(backupVaults=vaults, region=region)


def _list_shared_backup_vaults(event: dict[str, Any], own_account_id: str) -> dict[str, Any]:
    """List the logically air-gapped vaults shared with this account in one Region.

    An empty list is a normal answer (nothing is shared), not an error. Which side's
    list ``ByShared`` returns is not stated plainly in the documentation, so a row
    whose owner is this account carries ``ownedByThisAccount`` and the UI leaves it
    out of the choices.
    """
    region = _requested_region(event)
    vaults = [_vault_row(vault, region, own_account_id) for vault in _vault_pages(_client(region), shared=True)]
    return _result(backupVaults=vaults, region=region)


def _describe_recovery_point(event: dict[str, Any], own_account_id: str) -> dict[str, Any]:
    """Describe one recovery point.

    Both ``recoveryPointArn`` and ``backupVaultName`` are required;
    ``backupVaultAccountId`` and ``backupVaultRegion`` are optional and follow the
    same rules as in the list.
    """
    recovery_point_arn = event.get("recoveryPointArn", "")
    backup_vault_name = event.get("backupVaultName", "")
    if not recovery_point_arn or not backup_vault_name:
        return _result(
            error="recoveryPointArn and backupVaultName are required",
            errorCode="InvalidParameter",
        )

    scope = _scope(event, own_account_id)
    client = _client(scope["region"])
    if scope["crossAccount"]:
        _require_shared(client, scope["vaultName"], scope["accountId"])

    kwargs: dict[str, Any] = {"BackupVaultName": scope["vaultName"], "RecoveryPointArn": recovery_point_arn}
    if scope["crossAccount"]:
        kwargs["BackupVaultAccountId"] = scope["accountId"]
    point = client.describe_recovery_point(**kwargs)

    created = point.get("CreationDate")
    vault_arn = point.get("BackupVaultArn", "")
    return _result(
        recoveryPoint={
            "recoveryPointArn": point.get("RecoveryPointArn", ""),
            "resourceArn": point.get("ResourceArn", ""),
            "resourceType": point.get("ResourceType", ""),
            "creationDate": created.isoformat() if hasattr(created, "isoformat") else "",
            "status": point.get("Status", ""),
            "statusMessage": point.get("StatusMessage", ""),
            "backupVaultName": point.get("BackupVaultName") or scope["vaultName"],
            "backupVaultArn": vault_arn,
            "ownerAccountId": _account_of(vault_arn) or scope["accountId"] or own_account_id,
            "region": scope["region"],
            "isEncrypted": bool(point.get("IsEncrypted", False)),
            "encryptionKeyArn": point.get("EncryptionKeyArn", ""),
            "encryptionKeyType": point.get("EncryptionKeyType", ""),
            "storageClass": point.get("StorageClass", ""),
            "vaultType": point.get("VaultType", ""),
            "backupSizeInBytes": point.get("BackupSizeInBytes", 0),
        },
    )


def handler(event, context):
    """Dispatch a read-only AWS Backup query.

    Actions:
      - ``listRecoveryPoints`` (default): FSx recovery points in a vault, or across
        the configured vaults.
      - ``listBackupVaults``: the vaults this account owns in one Region, with vault
        type, and the Regions that may be selected.
      - ``listSharedBackupVaults``: the vaults other accounts shared with this one.
      - ``describeRecoveryPoint``: one recovery point in detail.

    Returns a plain dict with the same keys on every path (see ``_result``). A boto3
    ``ClientError`` or any other exception is caught and returned as ``error`` (and,
    for a ``ClientError``, ``errorCode``) so an error never raises to AppSync
    (mirrors ``functions/snapshots/index.py``).
    """
    action = event.get("action", "listRecoveryPoints")
    own_account_id = _own_account_id(context)

    try:
        if action == "listBackupVaults":
            return _list_backup_vaults(event, own_account_id)
        if action == "listSharedBackupVaults":
            return _list_shared_backup_vaults(event, own_account_id)
        if action == "describeRecoveryPoint":
            return _describe_recovery_point(event, own_account_id)
        if action == "listRecoveryPoints":
            return _list_recovery_points(event, own_account_id)
        return _result(error=f"Unknown action: {action}", errorCode="UnknownAction")
    except _Rejected as e:
        return _result(error=e.message, errorCode=e.code)
    except ClientError as e:
        logger.warning("AWS Backup call failed: %s", e)
        return _result(error=str(e), errorCode=e.response.get("Error", {}).get("Code", ""))
    except Exception as e:  # noqa: BLE001 - never raise to AppSync
        logger.exception("Error handling action %s", action)
        return _result(error=str(e))
