"""Tests for the recovery-points Lambda handler.

Focus: the handler lists AWS Backup recovery points read-only, scoped to FSx for
ONTAP, and never raises to AppSync. A boto3 ClientError must come back as an error
dict so the panel can show the message rather than the request failing opaquely.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError


@pytest.fixture
def mock_backup():
    """Patch the boto3 backup client the handler builds."""
    with patch("rp_handler.boto3") as mock_boto3:
        client = MagicMock()
        mock_boto3.client.return_value = client
        yield client


# The payloads the UI actually sends. Asserting against these — rather than a
# hand-written minimal event — is what catches a UI and handler that disagree
# about parameter names.
UI_PAYLOADS: dict[str, dict] = {
    "listRecoveryPoints": {"maxResults": 50},
    "listBackupVaults": {},
    "describeRecoveryPoint": {
        "recoveryPointArn": "arn:aws:backup:ap-northeast-1:111122223333:recovery-point:rp-1",
        "backupVaultName": "vault1",
    },
}


class TestListRecoveryPoints:
    def test_happy_path_scopes_to_fsx(self, mock_backup):
        from rp_handler import handler

        mock_backup.list_recovery_points_by_backup_vault.return_value = {
            "RecoveryPoints": [
                {
                    "RecoveryPointArn": "arn:aws:backup:...:rp-1",
                    "ResourceArn": "arn:aws:fsx:...:volume/fsvol-1",
                    "ResourceType": "FSx",
                    "CreationDate": datetime(2026, 1, 2, tzinfo=timezone.utc),
                    "Status": "AVAILABLE",
                    "StatusMessage": "",
                    "BackupVaultName": "vault1",
                    "IsEncrypted": True,
                    "EncryptionKeyArn": "arn:aws:kms:...:key/abc",
                    "BackupSizeInBytes": 1024,
                }
            ]
        }

        result = handler({"action": "listRecoveryPoints", "backupVaultName": "vault1"}, None)

        assert result["error"] is None
        assert len(result["recoveryPoints"]) == 1
        row = result["recoveryPoints"][0]
        assert row["resourceType"] == "FSx"
        assert row["status"] == "AVAILABLE"
        assert row["isEncrypted"] is True
        # The call must be scoped to FSx recovery points, not the whole vault.
        kwargs = mock_backup.list_recovery_points_by_backup_vault.call_args.kwargs
        assert kwargs["ByResourceType"] == "FSx"
        assert kwargs["BackupVaultName"] == "vault1"

    def test_default_action_is_list(self, mock_backup):
        """A payload with no action lists recovery points."""
        from rp_handler import handler

        mock_backup.list_recovery_points_by_backup_vault.return_value = {"RecoveryPoints": []}

        result = handler({"backupVaultName": "vault1"}, None)

        assert result["error"] is None
        assert result["recoveryPoints"] == []

    def test_empty_vault_returns_no_rows(self, mock_backup):
        from rp_handler import handler

        mock_backup.list_recovery_points_by_backup_vault.return_value = {"RecoveryPoints": []}

        result = handler({"action": "listRecoveryPoints", "backupVaultName": "vault1"}, None)

        assert result["recoveryPoints"] == []
        assert result["error"] is None

    def test_configured_vaults_used_when_none_named(self, mock_backup):
        """Absent backupVaultName, the configured vaults are listed."""
        from rp_handler import handler

        mock_backup.list_recovery_points_by_backup_vault.return_value = {"RecoveryPoints": []}

        handler({"action": "listRecoveryPoints"}, None)

        kwargs = mock_backup.list_recovery_points_by_backup_vault.call_args.kwargs
        assert kwargs["BackupVaultName"] == "vault1"

    def test_optional_account_id_forwarded(self, mock_backup):
        """The cross-account scope selector is forwarded when present (handler param only)."""
        from rp_handler import handler

        mock_backup.list_recovery_points_by_backup_vault.return_value = {"RecoveryPoints": []}

        handler(
            {
                "action": "listRecoveryPoints",
                "backupVaultName": "vault1",
                "backupVaultAccountId": "111122223333",
            },
            None,
        )

        kwargs = mock_backup.list_recovery_points_by_backup_vault.call_args.kwargs
        assert kwargs["BackupVaultAccountId"] == "111122223333"

    def test_account_id_omitted_when_absent(self, mock_backup):
        from rp_handler import handler

        mock_backup.list_recovery_points_by_backup_vault.return_value = {"RecoveryPoints": []}

        handler({"action": "listRecoveryPoints", "backupVaultName": "vault1"}, None)

        kwargs = mock_backup.list_recovery_points_by_backup_vault.call_args.kwargs
        assert "BackupVaultAccountId" not in kwargs

    def test_client_error_is_returned_not_raised(self, mock_backup):
        from rp_handler import handler

        mock_backup.list_recovery_points_by_backup_vault.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "no"}},
            "ListRecoveryPointsByBackupVault",
        )

        result = handler({"action": "listRecoveryPoints", "backupVaultName": "vault1"}, None)

        assert result["recoveryPoints"] == []
        assert result["error"] is not None
        assert "AccessDeniedException" in result["error"]


class TestListBackupVaults:
    def test_returns_vault_type_and_lock(self, mock_backup):
        from rp_handler import handler

        mock_backup.list_backup_vaults.return_value = {
            "BackupVaultList": [
                {
                    "BackupVaultName": "lag-vault",
                    "BackupVaultArn": "arn:aws:backup:...:backup-vault:lag-vault",
                    "VaultType": "LOGICALLY_AIR_GAPPED_BACKUP_VAULT",
                    "Locked": True,
                    "NumberOfRecoveryPoints": 3,
                }
            ]
        }

        result = handler({"action": "listBackupVaults"}, None)

        assert result["error"] is None
        vault = result["backupVaults"][0]
        assert vault["vaultType"] == "LOGICALLY_AIR_GAPPED_BACKUP_VAULT"
        assert vault["locked"] is True
        assert vault["numberOfRecoveryPoints"] == 3


class TestDescribeRecoveryPoint:
    def test_requires_both_arns(self, mock_backup):
        from rp_handler import handler

        missing_vault = handler({"action": "describeRecoveryPoint", "recoveryPointArn": "arn:...:rp-1"}, None)
        missing_arn = handler({"action": "describeRecoveryPoint", "backupVaultName": "vault1"}, None)

        for result in (missing_vault, missing_arn):
            assert result["recoveryPoint"] is None
            assert "required" in result["error"]
        # No API call when a required field is missing.
        mock_backup.describe_recovery_point.assert_not_called()

    def test_describe_happy_path(self, mock_backup):
        from rp_handler import handler

        mock_backup.describe_recovery_point.return_value = {
            "RecoveryPointArn": "arn:...:rp-1",
            "ResourceType": "FSx",
            "CreationDate": datetime(2026, 1, 2, tzinfo=timezone.utc),
            "Status": "AVAILABLE",
            "StatusMessage": "",
            "BackupVaultName": "vault1",
            "IsEncrypted": True,
            "EncryptionKeyType": "CUSTOMER_MANAGED_KMS_KEY",
            "StorageClass": "WARM",
            "VaultType": "LOGICALLY_AIR_GAPPED_BACKUP_VAULT",
        }

        result = handler(
            {
                "action": "describeRecoveryPoint",
                "recoveryPointArn": "arn:...:rp-1",
                "backupVaultName": "vault1",
            },
            None,
        )

        assert result["error"] is None
        assert result["recoveryPoint"]["encryptionKeyType"] == "CUSTOMER_MANAGED_KMS_KEY"
        assert result["recoveryPoint"]["vaultType"] == "LOGICALLY_AIR_GAPPED_BACKUP_VAULT"


class TestUnknownAction:
    def test_unknown_action_is_reported(self, mock_backup):
        from rp_handler import handler

        result = handler({"action": "definitelyNotAnAction"}, None)

        assert "Unknown action" in result["error"]
        assert result["recoveryPoints"] == []
