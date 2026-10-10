"""Tests for the recovery-points Lambda handler.

Focus: the handler lists AWS Backup recovery points read-only, scoped to FSx for
ONTAP, and never raises to AppSync. A boto3 ClientError must come back as an error
dict so the panel can show the message rather than the request failing opaquely.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

HOME = "ap-northeast-1"
OTHER_REGION = "us-east-1"
# The account this Lambda runs in, and the account that owns a shared vault. Both
# are documentation placeholders, not real accounts.
OWN_ACCOUNT = "123456789012"
OWNER_ACCOUNT = "111122223333"
LAG = "LOGICALLY_AIR_GAPPED_BACKUP_VAULT"
CONTEXT = SimpleNamespace(invoked_function_arn=f"arn:aws:lambda:{HOME}:{OWN_ACCOUNT}:function:recovery-points")


@pytest.fixture(autouse=True)
def _pin_regions(monkeypatch):
    """Fix the home Region and the extra allowed Region on the module.

    ``raising=False`` so that, run against a handler that has no such attribute, the
    tests fail on what they assert about behaviour rather than on this fixture.
    """
    import rp_handler

    monkeypatch.setattr(rp_handler, "HOME_REGION", HOME, raising=False)
    monkeypatch.setattr(rp_handler, "BACKUP_REGIONS", [OTHER_REGION], raising=False)


@pytest.fixture
def mock_boto3():
    """Patch the boto3 module the handler builds its backup client from."""
    with patch("rp_handler.boto3") as patched:
        patched.client.return_value = MagicMock()
        yield patched


@pytest.fixture
def mock_backup(mock_boto3):
    """The stubbed boto3 backup client."""
    return mock_boto3.client.return_value


def shared_vault(name="shared-vault", owner=OWNER_ACCOUNT, region=HOME):
    """One entry of a ListBackupVaults(ByShared=True) response."""
    return {
        "BackupVaultName": name,
        "BackupVaultArn": f"arn:aws:backup:{region}:{owner}:backup-vault:{name}",
        "VaultType": LAG,
        "VaultState": "AVAILABLE",
        "EncryptionKeyType": "CUSTOMER_MANAGED_KMS_KEY",
    }


def stub_shared(client, *vaults):
    """Make the stubbed client's ListBackupVaults return ``vaults``."""
    client.list_backup_vaults.return_value = {"BackupVaultList": list(vaults)}


def shared_point(**overrides):
    """One recovery point in a vault another account shared."""
    point = {
        "RecoveryPointArn": f"arn:aws:backup:{HOME}:{OWNER_ACCOUNT}:recovery-point:rp-shared",
        "ResourceArn": f"arn:aws:fsx:{HOME}:{OWNER_ACCOUNT}:volume/fs-0123/fsvol-0123",
        "ResourceType": "FSx",
        "CreationDate": datetime(2026, 1, 2, tzinfo=timezone.utc),
        "Status": "AVAILABLE",
        "StatusMessage": "",
        "BackupVaultName": "shared-vault",
        "BackupVaultArn": f"arn:aws:backup:{HOME}:{OWNER_ACCOUNT}:backup-vault:shared-vault",
        "VaultType": LAG,
        "IsEncrypted": True,
        "BackupSizeInBytes": 2048,
    }
    point.update(overrides)
    return point


# The payloads the UI actually sends. Asserting against these — rather than a
# hand-written minimal event — is what catches a UI and handler that disagree
# about parameter names. The keys are the ones src/components/RecoveryPoints.tsx
# builds; TestUiPayloads runs every one through the handler.
UI_PAYLOADS: dict[str, dict] = {
    "listRecoveryPoints": {"maxResults": 50},
    "listRecoveryPoints (another Region)": {
        "maxResults": 100,
        "backupVaultName": "regional-vault",
        "backupVaultRegion": OTHER_REGION,
    },
    "listRecoveryPoints (shared vault)": {
        "maxResults": 100,
        "backupVaultName": "shared-vault",
        "backupVaultAccountId": OWNER_ACCOUNT,
    },
    "listBackupVaults": {},
    "listBackupVaults (another Region)": {"backupVaultRegion": OTHER_REGION},
    "listSharedBackupVaults": {},
    "listSharedBackupVaults (another Region)": {"backupVaultRegion": OTHER_REGION},
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
        """The vault owner's account is forwarded once the vault is in the shared list."""
        from rp_handler import handler

        stub_shared(mock_backup, shared_vault("vault1"))
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


class TestSharedVaultList:
    """``listSharedBackupVaults``: the vaults other accounts shared with this one."""

    def test_zero_shared_vaults_is_an_empty_answer_not_an_error(self, mock_backup):
        from rp_handler import handler

        stub_shared(mock_backup)

        result = handler({"action": "listSharedBackupVaults"}, CONTEXT)

        assert result["backupVaults"] == []
        assert result["error"] is None
        assert result["errorCode"] is None
        # The shared list is ByShared alone; a second filter would only narrow it.
        kwargs = mock_backup.list_backup_vaults.call_args.kwargs
        assert kwargs["ByShared"] is True
        assert "ByVaultType" not in kwargs

    def test_all_pages_are_followed(self, mock_backup):
        from rp_handler import handler

        mock_backup.list_backup_vaults.side_effect = [
            {"BackupVaultList": [shared_vault("first")], "NextToken": "page-2"},
            {"BackupVaultList": [shared_vault("second")]},
        ]

        result = handler({"action": "listSharedBackupVaults"}, CONTEXT)

        assert [v["backupVaultName"] for v in result["backupVaults"]] == ["first", "second"]
        second_call = mock_backup.list_backup_vaults.call_args_list[1].kwargs
        assert second_call["NextToken"] == "page-2"
        assert second_call["ByShared"] is True

    def test_owner_comes_from_the_arn_and_own_vaults_are_flagged(self, mock_backup):
        from rp_handler import handler

        stub_shared(mock_backup, shared_vault("theirs"), shared_vault("ours", owner=OWN_ACCOUNT))

        result = handler({"action": "listSharedBackupVaults"}, CONTEXT)

        theirs, ours = result["backupVaults"]
        assert theirs["ownerAccountId"] == OWNER_ACCOUNT
        assert theirs["ownedByThisAccount"] is False
        assert theirs["vaultType"] == LAG
        assert theirs["vaultState"] == "AVAILABLE"
        assert theirs["encryptionKeyType"] == "CUSTOMER_MANAGED_KMS_KEY"
        assert ours["ownerAccountId"] == OWN_ACCOUNT
        assert ours["ownedByThisAccount"] is True

    def test_selected_region_builds_a_client_for_that_region(self, mock_boto3):
        from rp_handler import handler

        stub_shared(mock_boto3.client.return_value)

        result = handler({"action": "listSharedBackupVaults", "backupVaultRegion": OTHER_REGION}, CONTEXT)

        mock_boto3.client.assert_called_once_with("backup", region_name=OTHER_REGION)
        assert result["region"] == OTHER_REGION

    def test_region_outside_the_allow_list_is_refused(self, mock_boto3):
        from rp_handler import handler

        result = handler({"action": "listSharedBackupVaults", "backupVaultRegion": "eu-west-1"}, CONTEXT)

        assert result["errorCode"] == "RegionNotAllowed"
        assert result["backupVaults"] == []
        mock_boto3.client.assert_not_called()


class TestListBackupVaultsScope:
    def test_rows_carry_owner_state_and_key_type_and_unknown_types_pass_through(self, mock_backup):
        from rp_handler import handler

        restore_access = {
            "BackupVaultName": "restore-access",
            "BackupVaultArn": f"arn:aws:backup:{HOME}:{OWN_ACCOUNT}:backup-vault:restore-access",
            "VaultType": "RESTORE_ACCESS_BACKUP_VAULT",
            "VaultState": "AVAILABLE",
            "EncryptionKeyType": "AWS_OWNED_KMS_KEY",
        }
        stub_shared(mock_backup, restore_access)

        result = handler({"action": "listBackupVaults"}, CONTEXT)

        row = result["backupVaults"][0]
        # A VaultType the UI does not know is shown, not hidden.
        assert row["vaultType"] == "RESTORE_ACCESS_BACKUP_VAULT"
        assert row["ownerAccountId"] == OWN_ACCOUNT
        assert row["ownedByThisAccount"] is True
        assert row["vaultState"] == "AVAILABLE"
        assert row["encryptionKeyType"] == "AWS_OWNED_KMS_KEY"
        # The own-account list is not the shared list.
        assert "ByShared" not in mock_backup.list_backup_vaults.call_args.kwargs

    def test_response_names_the_selectable_regions(self, mock_backup):
        from rp_handler import handler

        stub_shared(mock_backup)

        result = handler({"action": "listBackupVaults"}, CONTEXT)

        assert result["homeRegion"] == HOME
        assert result["region"] == HOME
        assert result["regions"] == [HOME, OTHER_REGION]

    def test_selected_region_builds_a_client_for_that_region(self, mock_boto3):
        from rp_handler import handler

        stub_shared(mock_boto3.client.return_value)

        result = handler({"action": "listBackupVaults", "backupVaultRegion": OTHER_REGION}, CONTEXT)

        mock_boto3.client.assert_called_once_with("backup", region_name=OTHER_REGION)
        assert result["region"] == OTHER_REGION

    def test_pages_are_followed(self, mock_backup):
        from rp_handler import handler

        mock_backup.list_backup_vaults.side_effect = [
            {"BackupVaultList": [shared_vault("a", owner=OWN_ACCOUNT)], "NextToken": "t"},
            {"BackupVaultList": [shared_vault("b", owner=OWN_ACCOUNT)]},
        ]

        result = handler({"action": "listBackupVaults"}, CONTEXT)

        assert [v["backupVaultName"] for v in result["backupVaults"]] == ["a", "b"]


class TestSharedVaultRecoveryPoints:
    """Recovery points in a vault that another account shared through AWS RAM."""

    def test_listed_with_the_owner_account_once_the_vault_is_shared(self, mock_backup):
        from rp_handler import handler

        stub_shared(mock_backup, shared_vault())
        mock_backup.list_recovery_points_by_backup_vault.return_value = {"RecoveryPoints": [shared_point()]}

        result = handler(
            {
                "action": "listRecoveryPoints",
                "backupVaultName": "shared-vault",
                "backupVaultAccountId": OWNER_ACCOUNT,
            },
            CONTEXT,
        )

        assert result["error"] is None
        kwargs = mock_backup.list_recovery_points_by_backup_vault.call_args.kwargs
        assert kwargs["BackupVaultAccountId"] == OWNER_ACCOUNT
        assert kwargs["BackupVaultName"] == "shared-vault"
        assert kwargs["ByResourceType"] == "FSx"
        row = result["recoveryPoints"][0]
        assert row["ownerAccountId"] == OWNER_ACCOUNT
        assert row["region"] == HOME
        assert row["vaultType"] == LAG
        assert row["backupVaultArn"].endswith(":backup-vault:shared-vault")

    def test_revoked_share_is_reported_and_the_vault_is_not_queried(self, mock_backup):
        """RAM share revoked: the vault is gone from the shared list."""
        from rp_handler import handler

        stub_shared(mock_backup)

        result = handler(
            {
                "action": "listRecoveryPoints",
                "backupVaultName": "shared-vault",
                "backupVaultAccountId": OWNER_ACCOUNT,
            },
            CONTEXT,
        )

        assert result["errorCode"] == "VaultNotShared"
        assert result["recoveryPoints"] == []
        mock_backup.list_recovery_points_by_backup_vault.assert_not_called()

    def test_same_name_from_a_different_owner_is_not_a_match(self, mock_backup):
        from rp_handler import handler

        stub_shared(mock_backup, shared_vault(owner="999988887777"))

        result = handler(
            {
                "action": "listRecoveryPoints",
                "backupVaultName": "shared-vault",
                "backupVaultAccountId": OWNER_ACCOUNT,
            },
            CONTEXT,
        )

        assert result["errorCode"] == "VaultNotShared"
        mock_backup.list_recovery_points_by_backup_vault.assert_not_called()

    def test_access_denied_after_the_share_check_is_returned_with_its_code(self, mock_backup):
        """The share is listed but AWS still refuses (for example, the role's ARN scope)."""
        from rp_handler import handler

        stub_shared(mock_backup, shared_vault())
        mock_backup.list_recovery_points_by_backup_vault.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "no"}},
            "ListRecoveryPointsByBackupVault",
        )

        result = handler(
            {
                "action": "listRecoveryPoints",
                "backupVaultName": "shared-vault",
                "backupVaultAccountId": OWNER_ACCOUNT,
            },
            CONTEXT,
        )

        assert result["errorCode"] == "AccessDeniedException"
        assert "AccessDeniedException" in result["error"]
        assert result["recoveryPoints"] == []

    def test_completed_with_issues_point_keeps_status_and_message_verbatim(self, mock_backup):
        """A COMPLETED point carrying a status message is not relabelled or dropped."""
        from rp_handler import handler

        stub_shared(mock_backup, shared_vault())
        issue = "Resource has no data to back up for one volume"
        mock_backup.list_recovery_points_by_backup_vault.return_value = {
            "RecoveryPoints": [shared_point(Status="COMPLETED", StatusMessage=issue)]
        }

        result = handler(
            {
                "action": "listRecoveryPoints",
                "backupVaultName": "shared-vault",
                "backupVaultAccountId": OWNER_ACCOUNT,
            },
            CONTEXT,
        )

        row = result["recoveryPoints"][0]
        assert row["status"] == "COMPLETED"
        assert row["statusMessage"] == issue
        assert row["ownerAccountId"] == OWNER_ACCOUNT

    def test_own_account_id_is_a_plain_listing(self, mock_backup):
        """Naming this account is not cross-account: no share lookup, no account argument."""
        from rp_handler import handler

        mock_backup.list_recovery_points_by_backup_vault.return_value = {"RecoveryPoints": []}

        result = handler(
            {"action": "listRecoveryPoints", "backupVaultName": "vault1", "backupVaultAccountId": OWN_ACCOUNT},
            CONTEXT,
        )

        assert result["error"] is None
        mock_backup.list_backup_vaults.assert_not_called()
        assert "BackupVaultAccountId" not in mock_backup.list_recovery_points_by_backup_vault.call_args.kwargs

    def test_another_account_without_a_vault_name_does_not_fall_back_to_the_configured_vaults(self, mock_boto3):
        from rp_handler import handler

        result = handler({"action": "listRecoveryPoints", "backupVaultAccountId": OWNER_ACCOUNT}, CONTEXT)

        assert result["errorCode"] == "VaultNameRequired"
        assert result["recoveryPoints"] == []
        mock_boto3.client.assert_not_called()

    def test_unknown_own_account_is_treated_as_another_account(self, mock_backup):
        """With no Lambda context the account is unknown; the strict reading applies."""
        from rp_handler import handler

        stub_shared(mock_backup)

        result = handler(
            {"action": "listRecoveryPoints", "backupVaultName": "vault1", "backupVaultAccountId": OWN_ACCOUNT},
            None,
        )

        assert result["errorCode"] == "VaultNotShared"


class TestRegionSelection:
    def test_allowed_region_builds_a_client_for_that_region(self, mock_boto3):
        from rp_handler import handler

        client = mock_boto3.client.return_value
        client.list_recovery_points_by_backup_vault.return_value = {"RecoveryPoints": [shared_point()]}

        result = handler(
            {"action": "listRecoveryPoints", "backupVaultName": "regional-vault", "backupVaultRegion": OTHER_REGION},
            CONTEXT,
        )

        mock_boto3.client.assert_called_once_with("backup", region_name=OTHER_REGION)
        assert result["error"] is None
        assert result["recoveryPoints"][0]["region"] == OTHER_REGION
        # Another Region of this account is not another account.
        assert "BackupVaultAccountId" not in client.list_recovery_points_by_backup_vault.call_args.kwargs

    def test_region_outside_the_allow_list_is_refused_before_any_client_is_built(self, mock_boto3):
        from rp_handler import handler

        result = handler(
            {"action": "listRecoveryPoints", "backupVaultName": "v", "backupVaultRegion": "eu-west-1"}, CONTEXT
        )

        assert result["errorCode"] == "RegionNotAllowed"
        assert result["recoveryPoints"] == []
        mock_boto3.client.assert_not_called()

    @pytest.mark.parametrize(
        "region",
        ["ap-northeast", "US-EAST-1", "us-east-1 ", "us-east-1\n", " us-east-1", "us east 1", "../us-east-1", 1],
    )
    def test_malformed_region_is_refused(self, mock_boto3, region):
        from rp_handler import handler

        result = handler({"action": "listRecoveryPoints", "backupVaultName": "v", "backupVaultRegion": region}, CONTEXT)

        assert result["errorCode"] == "RegionNotAllowed"
        mock_boto3.client.assert_not_called()

    def test_another_region_without_a_vault_name_does_not_fall_back_to_the_configured_vaults(self, mock_boto3):
        from rp_handler import handler

        result = handler({"action": "listRecoveryPoints", "backupVaultRegion": OTHER_REGION}, CONTEXT)

        assert result["errorCode"] == "VaultNameRequired"
        mock_boto3.client.assert_not_called()


class TestAccountIdValidation:
    @pytest.mark.parametrize(
        "account_id",
        [
            "1111222233",  # 10 digits
            "1111222233334",  # 13 digits
            "11112222333a",  # letter
            "１１１１２２２２３３３３",  # full-width digits  # i18n-exempt: test input
            " 111122223333",
            "111122223333 ",
            "111122223333\n",
            "arn:aws:iam::111122223333:root",
            111122223333,  # a JSON number, not the string the API takes
        ],
    )
    def test_malformed_account_id_is_refused_before_any_aws_call(self, mock_boto3, account_id):
        from rp_handler import handler

        for action in ("listRecoveryPoints", "describeRecoveryPoint"):
            result = handler(
                {
                    "action": action,
                    "backupVaultName": "shared-vault",
                    "recoveryPointArn": "arn:aws:backup:ap-northeast-1:111122223333:recovery-point:rp-1",
                    "backupVaultAccountId": account_id,
                },
                CONTEXT,
            )

            assert result["errorCode"] == "InvalidParameter"
            assert result["error"]
        mock_boto3.client.assert_not_called()

    def test_twelve_ascii_digits_are_accepted(self, mock_backup):
        from rp_handler import handler

        stub_shared(mock_backup, shared_vault())
        mock_backup.list_recovery_points_by_backup_vault.return_value = {"RecoveryPoints": []}

        result = handler(
            {
                "action": "listRecoveryPoints",
                "backupVaultName": "shared-vault",
                "backupVaultAccountId": OWNER_ACCOUNT,
            },
            CONTEXT,
        )

        assert result["error"] is None
        assert result["errorCode"] is None


class TestDescribeAcrossAccounts:
    EVENT = {
        "action": "describeRecoveryPoint",
        "recoveryPointArn": f"arn:aws:backup:{HOME}:{OWNER_ACCOUNT}:recovery-point:rp-shared",
        "backupVaultName": "shared-vault",
        "backupVaultAccountId": OWNER_ACCOUNT,
    }

    def test_forwards_the_owner_account_when_the_vault_is_shared(self, mock_backup):
        from rp_handler import handler

        stub_shared(mock_backup, shared_vault())
        mock_backup.describe_recovery_point.return_value = shared_point(Status="COMPLETED", StatusMessage="x")

        result = handler(self.EVENT, CONTEXT)

        assert result["error"] is None
        assert mock_backup.describe_recovery_point.call_args.kwargs["BackupVaultAccountId"] == OWNER_ACCOUNT
        assert result["recoveryPoint"]["ownerAccountId"] == OWNER_ACCOUNT
        assert result["recoveryPoint"]["statusMessage"] == "x"

    def test_a_vault_that_is_not_shared_is_not_described(self, mock_backup):
        from rp_handler import handler

        stub_shared(mock_backup)

        result = handler(self.EVENT, CONTEXT)

        assert result["errorCode"] == "VaultNotShared"
        assert result["recoveryPoint"] is None
        mock_backup.describe_recovery_point.assert_not_called()

    def test_another_region_is_checked_against_the_allow_list(self, mock_boto3):
        from rp_handler import handler

        result = handler({**self.EVENT, "backupVaultRegion": "eu-west-1"}, CONTEXT)

        assert result["errorCode"] == "RegionNotAllowed"
        mock_boto3.client.assert_not_called()


class TestRegionContextOnEveryPath:
    """The Region selector is built from the answer, so a failed answer must still carry it.

    The UI reads ``homeRegion`` and ``regions`` from the vault list. If only a
    successful ``listBackupVaults`` carried them, one failed call (an opt-in Region
    that is not enabled, throttling) would remove the selector and leave the user
    no way back to the home Region.
    """

    EXPECTED_REGIONS = [HOME, OTHER_REGION]

    @pytest.mark.parametrize("action", ["listBackupVaults", "listSharedBackupVaults", "listRecoveryPoints"])
    def test_a_failed_aws_call_still_names_the_regions(self, mock_backup, action):
        from rp_handler import handler

        mock_backup.list_backup_vaults.side_effect = ClientError(
            {"Error": {"Code": "UnrecognizedClientException", "Message": "The security token is invalid"}},
            "ListBackupVaults",
        )
        mock_backup.list_recovery_points_by_backup_vault.side_effect = mock_backup.list_backup_vaults.side_effect

        result = handler({"action": action, "backupVaultRegion": OTHER_REGION, "backupVaultName": "v"}, CONTEXT)

        assert result["errorCode"] == "UnrecognizedClientException"
        assert result["homeRegion"] == HOME
        assert result["regions"] == self.EXPECTED_REGIONS

    @pytest.mark.parametrize(
        "event",
        [
            {"action": "listBackupVaults", "backupVaultRegion": "eu-west-1"},
            {"action": "listRecoveryPoints", "backupVaultAccountId": "bad"},
            {"action": "listRecoveryPoints", "backupVaultRegion": OTHER_REGION},
            {"action": "definitelyNotAnAction"},
        ],
        ids=["region-refused", "account-refused", "name-required", "unknown-action"],
    )
    def test_a_refusal_still_names_the_regions(self, mock_boto3, event):
        from rp_handler import handler

        result = handler(event, CONTEXT)

        assert result["errorCode"]
        assert result["homeRegion"] == HOME
        assert result["regions"] == self.EXPECTED_REGIONS

    def test_an_unexpected_exception_still_names_the_regions(self, mock_backup):
        from rp_handler import handler

        mock_backup.list_backup_vaults.side_effect = RuntimeError("boom")

        result = handler({"action": "listBackupVaults"}, CONTEXT)

        assert result["error"] == "boom"
        assert result["homeRegion"] == HOME
        assert result["regions"] == self.EXPECTED_REGIONS

    def test_a_revoked_share_still_names_the_regions(self, mock_backup):
        from rp_handler import handler

        stub_shared(mock_backup)

        result = handler(
            {"action": "listRecoveryPoints", "backupVaultName": "shared-vault", "backupVaultAccountId": OWNER_ACCOUNT},
            CONTEXT,
        )

        assert result["errorCode"] == "VaultNotShared"
        assert result["homeRegion"] == HOME
        assert result["regions"] == self.EXPECTED_REGIONS

    def test_a_success_names_the_regions_too(self, mock_backup):
        from rp_handler import handler

        mock_backup.list_recovery_points_by_backup_vault.return_value = {"RecoveryPoints": []}

        result = handler({"action": "listRecoveryPoints", "backupVaultName": "v"}, CONTEXT)

        assert result["error"] is None
        assert result["homeRegion"] == HOME
        assert result["regions"] == self.EXPECTED_REGIONS


class TestUiPayloads:
    """Every payload the UI builds must be accepted and answered with the full key set."""

    @pytest.mark.parametrize("label", list(UI_PAYLOADS))
    def test_payload_is_accepted(self, mock_backup, label):
        from rp_handler import handler

        # One stub serves every payload: the shared list contains the vault the shared
        # payload names, and the point lists are empty.
        stub_shared(mock_backup, shared_vault(), shared_vault("regional-vault", owner=OWN_ACCOUNT))
        mock_backup.list_recovery_points_by_backup_vault.return_value = {"RecoveryPoints": []}
        mock_backup.describe_recovery_point.return_value = shared_point()
        action = label.split(" ")[0]

        result = handler({"action": action, **UI_PAYLOADS[label]}, CONTEXT)

        assert result["error"] is None, result
        assert set(result) >= {
            "recoveryPoints",
            "backupVaults",
            "recoveryPoint",
            "error",
            "errorCode",
            "homeRegion",
            "regions",
        }

    def test_every_refusal_carries_the_full_key_set(self, mock_boto3):
        from rp_handler import handler

        for event in (
            {"action": "definitelyNotAnAction"},
            {"action": "listRecoveryPoints", "backupVaultAccountId": "bad"},
            {"action": "describeRecoveryPoint"},
        ):
            result = handler(event, CONTEXT)
            assert set(result) >= {
                "recoveryPoints",
                "backupVaults",
                "recoveryPoint",
                "error",
                "errorCode",
                "homeRegion",
                "regions",
            }
            assert result["error"]
            assert result["errorCode"]
