"""Tests for the data-protection Lambda handler.

Focus: the confirmation gate on ARP/AI containment actions.

Blocking an SMB user or an NFS client IP removes that principal's data access
across the whole SVM, and nothing in the portal expires the block automatically.
A dialog in the browser is a suggestion — anything calling AppSync directly
skips it — so the gate has to hold in the Lambda too.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_secrets():
    """Patch Secrets Manager so the handler can build its ONTAP headers."""
    with patch("handler.boto3") as mock_boto3:
        mock_sm = MagicMock()
        mock_sm.get_secret_value.return_value = {
            "SecretString": json.dumps({"username": "fsxadmin", "password": "test"})
        }
        mock_boto3.client.return_value = mock_sm
        yield mock_sm


@pytest.fixture
def mock_arp():
    """Patch the ArpResponseActions factory and hand back the stub."""
    with patch("handler._get_arp_response_client") as factory:
        actions = MagicMock()
        actions.block_smb_user.return_value = {"action": "block_smb_user", "status": "blocked"}
        actions.block_nfs_ip.return_value = {"action": "block_nfs_ip", "status": "blocked"}
        actions.contain_threat.return_value = {"action": "contain_threat", "status": "contained", "steps": []}
        actions.disconnect_smb_sessions.return_value = {
            "action": "disconnect_smb_sessions",
            "status": "disconnected",
            "disconnected": 2,
        }
        actions.unblock_smb_user.return_value = {"action": "unblock_smb_user", "status": "unblocked"}
        actions.unblock_nfs_ip.return_value = {"action": "unblock_nfs_ip", "status": "unblocked"}
        factory.return_value = actions
        yield actions


# The payloads the UI actually sends (ArpResponseActions.tsx). Asserting against
# these — rather than against a hand-written minimal event — is what catches a
# UI and backend that disagree about the parameter names.
UI_PAYLOADS: dict[str, dict] = {
    "blockSmbUser": {"domain": "CORP", "username": "jdoe"},
    "blockNfsIp": {"clientIp": "10.0.5.99"},
    "containThreat": {
        "domain": "CORP",
        "username": "jdoe",
        "clientIp": "10.0.5.99",
        "volumeName": "vol1",
        "reason": "portal-initiated",
    },
    "disconnectSessions": {"user": "CORP\\jdoe", "clientIp": "10.0.5.99"},
}


class TestContainmentConfirmGate:
    @pytest.mark.parametrize("action", sorted(UI_PAYLOADS))
    def test_refuses_without_confirm(self, action, mock_secrets, mock_arp):
        from handler import handler

        result = handler({"action": action, **UI_PAYLOADS[action]}, None)

        assert result["success"] is False
        assert "confirm=true is required" in result["error"]

    @pytest.mark.parametrize("action", sorted(UI_PAYLOADS))
    def test_no_ontap_call_when_unconfirmed(self, action, mock_secrets, mock_arp):
        """The gate must sit in front of the ONTAP call, not after it."""
        from handler import handler

        handler({"action": action, **UI_PAYLOADS[action]}, None)

        assert mock_arp.block_smb_user.call_count == 0
        assert mock_arp.block_nfs_ip.call_count == 0
        assert mock_arp.contain_threat.call_count == 0
        assert mock_arp.disconnect_smb_sessions.call_count == 0

    @pytest.mark.parametrize("action", sorted(UI_PAYLOADS))
    def test_succeeds_with_ui_payload_plus_confirm(self, action, mock_secrets, mock_arp):
        from handler import handler

        result = handler({"action": action, **UI_PAYLOADS[action], "confirm": True}, None)

        assert result["success"] is True, result

    def test_validation_error_precedes_confirm_gate(self, mock_secrets, mock_arp):
        """A missing target is reported as such, not as a missing confirmation."""
        from handler import handler

        result = handler({"action": "blockSmbUser", "domain": "CORP", "confirm": True}, None)

        assert result["success"] is False
        assert "domain and username are required" in result["error"]


class TestUnblockIsNotGated:
    """Unblocking restores access; a confirmation step there only delays recovery."""

    def test_unblock_smb_user_without_confirm(self, mock_secrets, mock_arp):
        from handler import handler

        result = handler({"action": "unblockSmbUser", "domain": "CORP", "username": "jdoe"}, None)

        assert result["success"] is True
        assert mock_arp.unblock_smb_user.call_count == 1

    def test_unblock_nfs_ip_without_confirm(self, mock_secrets, mock_arp):
        from handler import handler

        result = handler({"action": "unblockNfsIp", "clientIp": "10.0.5.99"}, None)

        assert result["success"] is True
        assert mock_arp.unblock_nfs_ip.call_count == 1


class TestClientFailureIsReadable:
    """A failure building the ONTAP client must not reach the UI as a bare code.

    Observed against a live SVM with no CIFS service: the action returned
    {"error": "4"}, which tells an operator nothing about what to fix.
    """

    def test_numeric_error_is_translated(self, mock_secrets):
        from handler import handler

        with patch("handler._get_arp_response_client", side_effect=Exception("4")):
            result = handler(
                {"action": "blockSmbUser", "domain": "CORP", "username": "jdoe", "confirm": True},
                None,
            )

        assert result["success"] is False
        assert result["error"] != "4"
        assert "CIFS" in result["error"]

    def test_import_error_is_named(self, mock_secrets):
        from handler import handler

        with patch("handler._get_arp_response_client", side_effect=ImportError("no module")):
            result = handler({"action": "blockNfsIp", "clientIp": "10.0.5.99", "confirm": True}, None)

        assert result["success"] is False
        assert "not available" in result["error"]

    def test_client_is_not_built_before_the_gate(self, mock_secrets):
        """An unconfirmed call must not even try to construct the client."""
        from handler import handler

        with patch("handler._get_arp_response_client") as factory:
            result = handler({"action": "blockSmbUser", "domain": "CORP", "username": "jdoe"}, None)

        assert factory.call_count == 0
        assert "confirm=true is required" in result["error"]


class TestUnknownAction:
    def test_unknown_action_is_reported(self, mock_secrets):
        from handler import handler

        result = handler({"action": "definitelyNotAnAction"}, None)

        assert "Unknown action" in result["error"]
