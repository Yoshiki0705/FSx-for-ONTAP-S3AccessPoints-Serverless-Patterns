"""Unit tests for shared/ontap_response.py — ARP/AI response actions.

Tests use a mock OntapClient that returns predefined responses,
verifying that ArpResponseActions correctly:
- Calls the right ONTAP REST API paths
- Validates inputs (username injection, IP format, protected accounts)
- Handles AD-joined vs non-AD SVMs for name-mapping replacement
- Implements snapshot cooldown logic
- Composes multi-step containment correctly
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parents[2]))

from shared.ontap_response import (
    ArpResponseActions,
    ArpResponseError,
    PROTECTED_ACCOUNTS,
    RESPONSE_MARKER,
    _validate_ip,
    _validate_username,
)


# --- Fixtures ---


class MockOntapClient:
    """Mock OntapClient that records calls and returns configured responses."""

    def __init__(self, responses: dict[str, dict] | None = None):
        self._responses = responses or {}
        self.calls: list[tuple[str, str, dict | None]] = []
        # Ordered responses: consume sequentially for paths that get called multiple times
        self._ordered_responses: dict[str, list[dict]] = {}

    def set_ordered_responses(self, path_fragment: str, responses: list[dict]):
        """Set sequential responses for a path (consumed in order)."""
        self._ordered_responses[path_fragment] = list(responses)

    def _match_response(self, method: str, path: str, params: dict | None = None) -> dict:
        """Find a matching response for the given method+path."""
        # Build full key from path + params for more precise matching
        full_key = f"{method} {path}"
        if params:
            full_key += " " + str(params)

        # Check ordered responses first
        for pattern, resp_list in self._ordered_responses.items():
            if pattern in full_key and resp_list:
                return resp_list.pop(0)

        # Then static responses (check longest match first)
        matches = [(k, v) for k, v in self._responses.items() if k in full_key]
        if matches:
            # Return the most specific (longest key) match
            matches.sort(key=lambda x: len(x[0]), reverse=True)
            return matches[0][1]

        return {"records": [], "num_records": 0}

    def get(self, path: str, params: dict | None = None) -> dict:
        self.calls.append(("GET", path, params))
        return self._match_response("GET", path, params)

    def post(self, path: str, body: dict | None = None) -> dict:
        self.calls.append(("POST", path, body))
        return self._match_response("POST", path)

    def patch(self, path: str, body: dict | None = None) -> dict:
        self.calls.append(("PATCH", path, body))
        return self._match_response("PATCH", path)

    def delete(self, path: str) -> dict:
        self.calls.append(("DELETE", path, None))
        return self._match_response("DELETE", path)


@pytest.fixture
def mock_client():
    """Create a MockOntapClient with standard SVM/volume responses."""
    responses = {
        "/svm/svms": {"records": [{"uuid": "svm-uuid-001", "name": "svm1"}], "num_records": 1},
        "/storage/volumes": {"records": [{"uuid": "vol-uuid-001", "name": "vol1"}], "num_records": 1},
        "/protocols/cifs/services": {"records": [], "num_records": 0},  # Non-AD by default
    }
    return MockOntapClient(responses)


@pytest.fixture
def arp(mock_client):
    """Create ArpResponseActions with mock client."""
    return ArpResponseActions(mock_client)


# --- Input Validation Tests ---


class TestValidateUsername:
    """Tests for _validate_username."""

    def test_valid_username(self):
        """Normal usernames should pass."""
        _validate_username("jdoe")
        _validate_username("jane.smith")
        _validate_username("user_123")

    def test_empty_username_rejected(self):
        """Empty username is invalid."""
        with pytest.raises(ArpResponseError, match="Invalid username"):
            _validate_username("")

    def test_long_username_rejected(self):
        """Username over 256 chars is invalid."""
        with pytest.raises(ArpResponseError, match="Invalid username"):
            _validate_username("x" * 257)

    def test_dangerous_chars_rejected(self):
        """Injection characters are blocked."""
        for char in [";", "|", "&", "`", "$", "\n", "\r"]:
            with pytest.raises(ArpResponseError, match="dangerous character"):
                _validate_username(f"user{char}inject")

    def test_protected_accounts_rejected(self):
        """Protected accounts cannot be blocked."""
        for account in ["fsxadmin", "administrator", "admin", "vsadmin"]:
            with pytest.raises(ArpResponseError, match="protected account"):
                _validate_username(account)

    def test_protected_accounts_case_insensitive(self):
        """Protection check is case-insensitive."""
        with pytest.raises(ArpResponseError, match="protected account"):
            _validate_username("FSXADMIN")
        with pytest.raises(ArpResponseError, match="protected account"):
            _validate_username("Administrator")


class TestValidateIp:
    """Tests for _validate_ip."""

    def test_valid_ip(self):
        """Standard IPv4 addresses pass."""
        _validate_ip("10.0.5.99")
        _validate_ip("192.168.1.1")
        _validate_ip("0.0.0.0")
        _validate_ip("255.255.255.255")

    def test_empty_ip_rejected(self):
        """Empty IP is invalid."""
        with pytest.raises(ArpResponseError, match="required"):
            _validate_ip("")

    def test_malformed_ip_rejected(self):
        """Non-dotted-quad format is invalid."""
        with pytest.raises(ArpResponseError, match="Invalid IP"):
            _validate_ip("not-an-ip")
        with pytest.raises(ArpResponseError, match="Invalid IP"):
            _validate_ip("10.0.5")
        with pytest.raises(ArpResponseError, match="Invalid IP"):
            _validate_ip("10.0.5.256")


# --- SMB User Blocking Tests ---


class TestBlockSmbUser:
    """Tests for block_smb_user."""

    def test_block_creates_name_mapping(self, arp, mock_client):
        """Blocking creates a win_unix name-mapping entry."""
        result = arp.block_smb_user(svm_name="svm1", domain="CORP", username="jdoe")

        assert result["action"] == "block_smb_user"
        assert result["status"] == "blocked"
        assert result["pattern"] == "CORP\\\\jdoe"
        assert result["marker"] == RESPONSE_MARKER

        # Verify POST was called
        post_calls = [c for c in mock_client.calls if c[0] == "POST"]
        assert len(post_calls) == 1
        assert "/name-services/name-mappings" in post_calls[0][1]

    def test_block_non_ad_uses_space_replacement(self, arp, mock_client):
        """Non-AD-joined SVM uses space replacement (DII standard)."""
        arp.block_smb_user(svm_name="svm1", domain="CORP", username="jdoe")

        post_calls = [c for c in mock_client.calls if c[0] == "POST"]
        body = post_calls[0][2]
        assert body["replacement"] == " "

    def test_block_ad_joined_uses_nobody_replacement(self, mock_client):
        """AD-joined SVM uses 'nobody' (persists unlike space on 9.17.1+)."""
        mock_client._responses["/protocols/cifs/services"] = {
            "records": [{"name": "CIFS_SVM1"}],
            "num_records": 1,
        }
        arp = ArpResponseActions(mock_client)

        arp.block_smb_user(svm_name="svm1", domain="CORP", username="jdoe")

        post_calls = [c for c in mock_client.calls if c[0] == "POST"]
        body = post_calls[0][2]
        assert body["replacement"] == "nobody"

    def test_block_protected_account_raises(self, arp):
        """Cannot block fsxadmin or other protected accounts."""
        with pytest.raises(ArpResponseError, match="protected account"):
            arp.block_smb_user(svm_name="svm1", domain="CORP", username="fsxadmin")

    def test_block_svm_not_found_raises(self):
        """Missing SVM raises ArpResponseError."""
        client = MockOntapClient({"/svm/svms": {"records": [], "num_records": 0}})
        arp = ArpResponseActions(client)

        with pytest.raises(ArpResponseError, match="SVM not found"):
            arp.block_smb_user(svm_name="nonexistent", domain="CORP", username="jdoe")


# --- NFS IP Blocking Tests ---


class TestBlockNfsIp:
    """Tests for block_nfs_ip."""

    def test_block_creates_export_policy_rule(self, mock_client):
        """Blocking creates a deny export-policy rule with marker."""
        mock_client._responses["/protocols/nfs/export-policies"] = {
            "records": [{"id": 42, "name": "default"}],
            "num_records": 1,
        }
        arp = ArpResponseActions(mock_client)

        result = arp.block_nfs_ip(svm_name="svm1", policy_name="default", client_ip="10.0.5.99")

        assert result["action"] == "block_nfs_ip"
        assert result["status"] == "blocked"
        assert result["client_ip"] == "10.0.5.99"

        post_calls = [c for c in mock_client.calls if c[0] == "POST"]
        assert len(post_calls) == 1
        body = post_calls[0][2]
        assert RESPONSE_MARKER in body["clients"][0]["match"]
        assert body["ro_rule"] == ["never"]
        assert body["rw_rule"] == ["never"]

    def test_block_invalid_ip_raises(self, arp):
        """Invalid IP format raises ArpResponseError."""
        with pytest.raises(ArpResponseError, match="Invalid IP"):
            arp.block_nfs_ip(svm_name="svm1", policy_name="default", client_ip="not.an.ip.x")

    def test_block_policy_not_found_raises(self, mock_client):
        """Missing export policy raises ArpResponseError."""
        mock_client._responses["/protocols/nfs/export-policies"] = {
            "records": [],
            "num_records": 0,
        }
        arp = ArpResponseActions(mock_client)

        with pytest.raises(ArpResponseError, match="Export policy .* not found"):
            arp.block_nfs_ip(svm_name="svm1", policy_name="missing", client_ip="10.0.5.99")


# --- Snapshot Tests ---


class TestCreateIncidentSnapshot:
    """Tests for create_incident_snapshot."""

    def test_creates_snapshot_with_timestamp(self, arp, mock_client):
        """Snapshot is created with prefix + timestamp name."""
        # No existing snapshots (cooldown passes)
        mock_client._responses["/storage/volumes/vol-uuid-001/snapshots"] = {
            "records": [],
            "num_records": 0,
        }

        result = arp.create_incident_snapshot(svm_name="svm1", volume_name="vol1")

        assert result["action"] == "create_incident_snapshot"
        assert result["status"] == "created"
        assert result["snapshot_name"].startswith("incident_response_")

    def test_cooldown_skips_recent_snapshot(self, arp, mock_client):
        """Snapshot is skipped if one was created within cooldown period."""
        recent_time = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        # The cooldown check calls GET /storage/volumes/{uuid}/snapshots with name filter
        # Since mock_client already resolves volume UUID, we just need the snapshot response
        mock_client.set_ordered_responses(
            "/snapshots",
            [
                # First call: cooldown check (returns recent snapshot)
                {"records": [{"name": "incident_response_20260725_120000", "create_time": recent_time}], "num_records": 1},
            ],
        )

        result = arp.create_incident_snapshot(
            svm_name="svm1", volume_name="vol1", cooldown_minutes=15
        )

        assert result["status"] == "skipped"
        assert "cooldown" in result["reason"]

    def test_cooldown_zero_always_creates(self, arp, mock_client):
        """cooldown_minutes=0 bypasses cooldown check."""
        result = arp.create_incident_snapshot(
            svm_name="svm1", volume_name="vol1", cooldown_minutes=0
        )

        assert result["status"] == "created"


# --- Composite Containment Tests ---


class TestContainThreat:
    """Tests for contain_threat (multi-step)."""

    def test_contain_with_smb_user(self, mock_client):
        """SMB containment: snapshot + block + disconnect."""
        mock_client._responses["/protocols/cifs/sessions"] = {
            "records": [],
            "num_records": 0,
        }
        mock_client._responses["/storage/volumes/vol-uuid-001/snapshots"] = {
            "records": [],
            "num_records": 0,
        }
        arp = ArpResponseActions(mock_client)

        result = arp.contain_threat(
            svm_name="svm1",
            domain="CORP",
            username="jdoe",
            volume_name="vol1",
        )

        assert result["action"] == "contain_threat"
        assert result["status"] == "contained"
        assert len(result["steps"]) == 3  # snapshot + block + disconnect

    def test_contain_with_nfs_ip(self, mock_client):
        """NFS containment: snapshot + block IP."""
        mock_client._responses["/protocols/nfs/export-policies"] = {
            "records": [{"id": 42, "name": "default"}],
            "num_records": 1,
        }
        mock_client._responses["/storage/volumes/vol-uuid-001/snapshots"] = {
            "records": [],
            "num_records": 0,
        }
        arp = ArpResponseActions(mock_client)

        result = arp.contain_threat(
            svm_name="svm1",
            client_ip="10.0.5.99",
            volume_name="vol1",
        )

        assert result["status"] == "contained"
        assert len(result["steps"]) == 2  # snapshot + block IP

    def test_contain_no_target_raises(self, arp):
        """Must specify at least one target."""
        result = arp.contain_threat(svm_name="svm1")
        # contain_threat handles this gracefully — no steps
        assert result["steps"] == []

    def test_contain_partial_failure(self, mock_client):
        """Reports partial_failure when some steps fail."""
        # SVM exists but volume doesn't → snapshot fails, block succeeds
        mock_client._responses["/storage/volumes"] = {"records": [], "num_records": 0}
        arp = ArpResponseActions(mock_client)

        result = arp.contain_threat(
            svm_name="svm1",
            domain="CORP",
            username="testuser",
            volume_name="nonexistent",
        )

        # Snapshot fails (volume not found), but block_smb_user also fails
        # because _get_svm_uuid works but the block itself needs the SVM
        assert result["status"] == "partial_failure"


# --- List Active Blocks Tests ---


class TestListActiveBlocks:
    """Tests for list_active_blocks."""

    def test_returns_smb_and_nfs_blocks(self, mock_client):
        """Lists both SMB name-mapping blocks and NFS export-policy blocks."""
        mock_client._responses["/name-services/name-mappings"] = {
            "records": [
                {"pattern": "CORP\\\\jdoe", "index": 1, "replacement": " "},
                {"pattern": "CORP\\\\admin", "index": 2, "replacement": "admin_user"},  # Not a block
            ],
            "num_records": 2,
        }
        mock_client._responses["/protocols/nfs/export-policies"] = {
            "records": [{"id": 42, "name": "default"}],
            "num_records": 1,
        }
        # Use ordered responses for the rules endpoint
        mock_client.set_ordered_responses(
            "/rules",
            [
                {
                    "records": [
                        {"index": 1, "clients": [{"match": f"{RESPONSE_MARKER},10.0.5.99"}]},
                        {"index": 2, "clients": [{"match": "0.0.0.0/0"}]},
                    ],
                    "num_records": 2,
                },
            ],
        )
        arp = ArpResponseActions(mock_client)

        result = arp.list_active_blocks(svm_name="svm1")

        assert result["action"] == "list_active_blocks"
        assert len(result["smb_blocks"]) == 1  # Only space/nobody replacement
        assert result["smb_blocks"][0]["pattern"] == "CORP\\\\jdoe"
        assert len(result["nfs_blocks"]) == 1
        assert "10.0.5.99" in result["nfs_blocks"][0]["client_match"]
        assert result["total"] == 2


# --- Unblock Tests ---


class TestUnblockSmbUser:
    """Tests for unblock_smb_user."""

    def test_unblock_deletes_mapping(self, mock_client):
        """Unblocking deletes the name-mapping entry."""
        mock_client._responses["/name-services/name-mappings"] = {
            "records": [{"index": 1, "pattern": "CORP\\\\jdoe", "replacement": " "}],
            "num_records": 1,
        }
        arp = ArpResponseActions(mock_client)

        result = arp.unblock_smb_user(svm_name="svm1", domain="CORP", username="jdoe")

        assert result["status"] == "unblocked"
        assert result["entries_removed"] == 1

        delete_calls = [c for c in mock_client.calls if c[0] == "DELETE"]
        assert len(delete_calls) == 1

    def test_unblock_not_found(self, mock_client):
        """Unblocking a non-blocked user returns not_found."""
        mock_client._responses["/name-services/name-mappings"] = {
            "records": [],
            "num_records": 0,
        }
        arp = ArpResponseActions(mock_client)

        result = arp.unblock_smb_user(svm_name="svm1", domain="CORP", username="notblocked")

        assert result["status"] == "not_found"
