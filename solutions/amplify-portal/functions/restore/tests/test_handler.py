"""Tests for the restore Lambda handler.

Focus: the restore handler is the portal's first write / irreversible AWS Backup
path. The server-side acknowledgement guard must refuse a StartRestoreJob without
``acknowledgeIrreversible: true``, the new-volume metadata must be assembled as the
FSx for ONTAP restore expects, required fields and the SVM allowlist must be
enforced before any API call, and a boto3 ClientError must come back as an error
dict rather than raising to AppSync.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

# Placeholder values. The account id and ids are not real (gitleaks).
RECOVERY_POINT_ARN = "arn:aws:backup:ap-northeast-1:111122223333:recovery-point:rp-1"
ALLOWED_SVM = "svm-01234567890abcdef"
DENIED_SVM = "svm-99999999999999999"


def _valid_params(**overrides):
    """A startRestore payload that passes every guard, with overrides applied."""
    params = {
        "action": "startRestore",
        "recoveryPointArn": RECOVERY_POINT_ARN,
        "name": "restored_vol",
        "storageVirtualMachineId": ALLOWED_SVM,
        "junctionPath": "/restored_vol",
        "sizeInMegabytes": 1024,
        "acknowledgeIrreversible": True,
    }
    params.update(overrides)
    return params


@pytest.fixture
def mock_backup():
    """Patch the boto3 backup client the handler builds."""
    with patch("restore_handler.boto3") as mock_boto3:
        client = MagicMock()
        mock_boto3.client.return_value = client
        yield client


class TestAckGuard:
    def test_missing_ack_refused_without_calling_api(self, mock_backup):
        from restore_handler import handler

        result = handler(_valid_params(acknowledgeIrreversible=None), None)

        assert result["error"] is not None
        assert "acknowledgeIrreversible" in result["error"]
        mock_backup.start_restore_job.assert_not_called()

    def test_ack_false_refused_without_calling_api(self, mock_backup):
        from restore_handler import handler

        result = handler(_valid_params(acknowledgeIrreversible=False), None)

        assert result["error"] is not None
        assert "acknowledgeIrreversible" in result["error"]
        mock_backup.start_restore_job.assert_not_called()


class TestStartRestore:
    def test_happy_path_returns_job_id(self, mock_backup):
        from restore_handler import handler

        mock_backup.start_restore_job.return_value = {"RestoreJobId": "job-123"}

        result = handler(_valid_params(), None)

        assert result["error"] is None
        assert result["restoreJobId"] == "job-123"

    def test_new_volume_metadata_assembled(self, mock_backup):
        from restore_handler import handler

        mock_backup.start_restore_job.return_value = {"RestoreJobId": "job-123"}

        handler(
            _valid_params(
                storageEfficiencyEnabled=True,
                tieringPolicy="SNAPSHOT_ONLY",
            ),
            None,
        )

        kwargs = mock_backup.start_restore_job.call_args.kwargs
        assert kwargs["ResourceType"] == "FSx"
        assert kwargs["RecoveryPointArn"] == RECOVERY_POINT_ARN
        assert kwargs["IamRoleArn"]  # the configured restore role
        assert kwargs["IdempotencyToken"]  # retry-safe
        metadata = kwargs["Metadata"]
        assert metadata["Name"] == "restored_vol"
        import json as _json

        ontap = _json.loads(metadata["OntapConfiguration"])
        assert ontap["storageVirtualMachineId"] == ALLOWED_SVM
        assert ontap["junctionPath"] == "/restored_vol"
        assert ontap["sizeInMegabytes"] == "1024"
        assert ontap["storageEfficiencyEnabled"] == "true"
        assert ontap["tieringPolicy"] == "SNAPSHOT_ONLY"

    def test_optional_metadata_omitted_when_absent(self, mock_backup):
        from restore_handler import handler

        mock_backup.start_restore_job.return_value = {"RestoreJobId": "job-123"}

        handler(_valid_params(), None)

        import json as _json

        ontap = _json.loads(mock_backup.start_restore_job.call_args.kwargs["Metadata"]["OntapConfiguration"])
        assert "storageEfficiencyEnabled" not in ontap
        assert "tieringPolicy" not in ontap

    def test_caller_idempotency_token_is_used(self, mock_backup):
        from restore_handler import handler

        mock_backup.start_restore_job.return_value = {"RestoreJobId": "job-123"}

        handler(_valid_params(idempotencyToken="caller-token"), None)

        assert mock_backup.start_restore_job.call_args.kwargs["IdempotencyToken"] == "caller-token"

    @pytest.mark.parametrize(
        "missing_field",
        ["recoveryPointArn", "name", "storageVirtualMachineId", "junctionPath", "sizeInMegabytes"],
    )
    def test_required_field_validation(self, mock_backup, missing_field):
        from restore_handler import handler

        result = handler(_valid_params(**{missing_field: ""}), None)

        assert result["error"] is not None
        assert missing_field in result["error"]
        mock_backup.start_restore_job.assert_not_called()

    def test_svm_not_in_allowlist_refused(self, mock_backup):
        from restore_handler import handler

        result = handler(_valid_params(storageVirtualMachineId=DENIED_SVM), None)

        assert result["error"] is not None
        assert DENIED_SVM in result["error"]
        mock_backup.start_restore_job.assert_not_called()

    def test_client_error_is_returned_not_raised(self, mock_backup):
        from restore_handler import handler

        mock_backup.start_restore_job.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "no"}},
            "StartRestoreJob",
        )

        result = handler(_valid_params(), None)

        assert result["error"] is not None
        assert "AccessDeniedException" in result["error"]


class TestDescribeRestore:
    def test_requires_job_id(self, mock_backup):
        from restore_handler import handler

        result = handler({"action": "describeRestore"}, None)

        assert result["restoreJob"] is None
        assert "required" in result["error"]
        mock_backup.describe_restore_job.assert_not_called()

    def test_describe_happy_path(self, mock_backup):
        from restore_handler import handler

        mock_backup.describe_restore_job.return_value = {
            "RestoreJobId": "job-123",
            "Status": "RUNNING",
            "StatusMessage": "",
            "PercentDone": "40",
            "CreatedResourceArn": "arn:aws:fsx:ap-northeast-1:111122223333:volume/fs-1/fsvol-1",
        }

        result = handler({"action": "describeRestore", "restoreJobId": "job-123"}, None)

        assert result["error"] is None
        assert result["restoreJob"]["status"] == "RUNNING"
        assert result["restoreJob"]["percentDone"] == "40"


class TestUnknownAction:
    def test_unknown_action_is_reported(self, mock_backup):
        from restore_handler import handler

        result = handler({"action": "definitelyNotAnAction"}, None)

        assert "Unknown action" in result["error"]
        mock_backup.start_restore_job.assert_not_called()
