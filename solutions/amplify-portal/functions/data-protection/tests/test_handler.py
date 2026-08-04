"""Tests for the data-protection Lambda handler.

Focus: the confirmation gate on ARP/AI containment actions.

Blocking an SMB user or an NFS client IP removes that principal's data access
across the whole SVM, and nothing in the portal expires the block automatically.
A dialog in the browser is a suggestion — anything calling AppSync directly
skips it — so the gate has to hold in the Lambda too.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
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
    """A failure building the ONTAP client must reach the UI as something usable.

    The original symptom was `{"error": "4"}`. The first attempt at a fix guessed
    that a short numeric message meant an HTTP 404 and reported "the SVM may not
    have a CIFS service configured". It was actually `IndexError: 4` from
    `Path(__file__).parents[4]` — a packaging problem being described as a
    configuration problem. So the requirement is not "produce a friendly
    message", it is "name the exception and do not guess".
    """

    def test_exception_type_is_reported_not_guessed(self, mock_secrets):
        from handler import handler

        with patch("handler._get_arp_response_client", side_effect=IndexError(4)):
            result = handler(
                {"action": "blockSmbUser", "domain": "CORP", "username": "jdoe", "confirm": True},
                None,
            )

        assert result["success"] is False
        assert result["error"] != "4"
        assert "IndexError" in result["error"]
        # The old message invented a cause. It must not come back.
        assert "CIFS" not in result["error"]

    def test_import_error_points_at_the_layer(self, mock_secrets):
        from handler import handler

        with patch("handler._get_arp_response_client", side_effect=ImportError("no module")):
            result = handler({"action": "blockNfsIp", "clientIp": "10.0.5.99", "confirm": True}, None)

        assert result["success"] is False
        assert "layer" in result["error"]

    def test_list_active_blocks_reports_the_failure(self, mock_secrets):
        """An empty list and "could not ask" must not look the same.

        This listing is the only route to finding and lifting a mistaken block,
        so reporting success with zero rows when the call failed is misleading.
        """
        from handler import handler

        with patch("handler._get_arp_response_client", side_effect=ImportError("no module")):
            result = handler({"action": "listActiveBlocks"}, None)

        assert result["success"] is False
        assert result["smbBlocks"] == []
        assert "layer" in result["error"]

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


class TestRequestPathSafety:
    """A caller-supplied snapshot id must not redirect the request."""

    def test_traversal_segment_is_refused(self):
        from handler import _is_unsafe_path

        assert _is_unsafe_path("/storage/volumes/uuid/snapshots/../../cluster/nodes")

    def test_dots_inside_a_segment_are_allowed(self):
        from handler import _is_unsafe_path

        assert not _is_unsafe_path("/storage/volumes/uuid/snapshots/daily..2026")

    def test_control_characters_are_refused(self):
        from handler import _is_unsafe_path

        assert _is_unsafe_path("/storage/volumes/a\nb")
        assert _is_unsafe_path("/storage/volumes/a\\b")

    def test_snapshot_id_is_percent_encoded(self, mock_secrets):
        from handler import handler

        captured = []

        class RecordingHttp:
            def request(self, method, url, **kwargs):
                captured.append((method, url))

                class R:
                    status = 200
                    data = json.dumps({"records": [{"uuid": "vol-1"}]}).encode()

                return R()

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = RecordingHttp()
            handler(
                {"action": "deleteSnapshot", "snapshotId": "../../cluster/nodes"},
                None,
            )

        deletes = [url for method, url in captured if method == "DELETE"]
        assert deletes, captured
        assert not any("/../" in url for url in deletes), deletes


class TestActiveBlocksResponseShape:
    """The listing must use the key names the UI reads.

    The shared module returns snake_case. The UI reads camelCase, and the error
    branches already returned camelCase, so spreading the raw result produced a
    response the Active Blocks tab silently could not read — real blocks on the
    SVM showed as none. That tab is the only way to lift a block from the
    portal, so the mismatch made a mistaken block unliftable through the UI.
    """

    def test_snake_case_from_shared_is_mapped_to_camel_case(self, mock_secrets, mock_arp):
        from handler import handler

        mock_arp.list_active_blocks.return_value = {
            "action": "list_active_blocks",
            "svm": "svm1",
            "smb_blocks": [{"pattern": "CORP\\\\testuser01", "index": 1, "replacement": " "}],
            # RFC 5737 documentation range, so the fixture cannot be mistaken
            # for a real internal address.
            "nfs_blocks": [{"policy": "default", "rule_index": 1, "client_match": "m,203.0.113.99"}],
            "total": 2,
        }

        result = handler({"action": "listActiveBlocks"}, None)

        assert result["success"] is True
        assert len(result["smbBlocks"]) == 1
        assert len(result["nfsBlocks"]) == 1
        assert result["total"] == 2
        # The raw snake_case keys must not leak through as well, or a consumer
        # could read either and the two would drift.
        assert "smb_blocks" not in result
        assert "nfs_blocks" not in result

    def test_success_and_error_shapes_agree(self, mock_secrets, mock_arp):
        """Both branches must expose the same keys, or the UI breaks on one."""
        from handler import handler

        mock_arp.list_active_blocks.return_value = {
            "action": "list_active_blocks",
            "svm": "svm1",
            "smb_blocks": [],
            "nfs_blocks": [],
            "total": 0,
        }
        ok = handler({"action": "listActiveBlocks"}, None)

        with patch("handler._get_arp_response_client", side_effect=ImportError("no module")):
            failed = handler({"action": "listActiveBlocks"}, None)

        for key in ("success", "smbBlocks", "nfsBlocks", "total", "error"):
            assert key in ok, key
            assert key in failed, key


# --- Containment block expiry (TTL auto-unblock) -----------------------------
#
# ONTAP name-mapping and export-policy rules carry no timestamp, so expiry can
# only come from the portal's own ledger. These tests pin the two properties
# that matter operationally: a block acquires an expiry by default, and the
# sweep never touches a block the portal did not place.


@pytest.fixture
def ledger():
    """Patch the ledger table with an in-memory stand-in."""
    rows: dict[str, dict] = {}
    table = MagicMock()

    def put_item(Item):
        rows[Item["blockId"]] = dict(Item)

    def update_item(Key, UpdateExpression, ExpressionAttributeNames, ExpressionAttributeValues):
        row = rows.get(Key["blockId"])
        if row is not None:
            row["status"] = ExpressionAttributeValues[":s"]
            row["liftedAt"] = ExpressionAttributeValues[":t"]
            row["liftReason"] = ExpressionAttributeValues[":r"]

    def scan(**kwargs):
        wanted = kwargs["ExpressionAttributeValues"][":s"]
        return {"Items": [r for r in rows.values() if r.get("status") == wanted]}

    table.put_item.side_effect = put_item
    table.update_item.side_effect = update_item
    table.scan.side_effect = scan

    with patch("handler._blocks_table", return_value=table):
        yield rows


class TestBlockExpiryRecording:
    def test_block_gets_a_default_expiry(self, mock_secrets, mock_arp, ledger):
        from handler import handler

        result = handler({"action": "blockSmbUser", "domain": "CORP", "username": "jdoe", "confirm": True}, None)

        assert result["success"] is True
        assert result["expiryTracked"] is True
        assert result["expiresAt"] is not None
        row = ledger["smb#fsxsvm01#CORP#jdoe"] if "smb#fsxsvm01#CORP#jdoe" in ledger else next(iter(ledger.values()))
        assert row["status"] == "active"
        assert row["blockType"] == "smb"
        # Kept past the block's own expiry, so the audit trail outlives the block.
        expires = datetime.fromisoformat(row["expiresAt"].replace("Z", "+00:00"))
        assert row["ttl"] > expires.timestamp()

    def test_zero_ttl_is_recorded_as_indefinite_not_silently_defaulted(self, mock_secrets, mock_arp, ledger):
        from handler import handler

        result = handler(
            {
                "action": "blockSmbUser",
                "domain": "CORP",
                "username": "jdoe",
                "confirm": True,
                "ttlHours": 0,
            },
            None,
        )

        assert result["success"] is True
        assert result["expiresAt"] is None
        assert result["expiryTracked"] is True
        assert next(iter(ledger.values()))["expiresAt"] is None

    @pytest.mark.parametrize(
        "bad", [-1, 24 * 91, "abc", True, [], {"h": 1}], ids=["negative", "over-max", "text", "bool", "list", "dict"]
    )
    def test_rejects_unusable_ttl(self, bad, mock_secrets, mock_arp, ledger):
        from handler import handler

        result = handler(
            {
                "action": "blockSmbUser",
                "domain": "CORP",
                "username": "jdoe",
                "confirm": True,
                "ttlHours": bad,
            },
            None,
        )

        assert result["success"] is False
        assert "ttlHours" in result["error"]
        # Nothing may be blocked when the expiry is unusable: a block whose
        # expiry was rejected would otherwise become an indefinite one.
        mock_arp.block_smb_user.assert_not_called()
        assert ledger == {}

    def test_block_still_succeeds_without_a_ledger_but_says_so(self, mock_secrets, mock_arp):
        """Containment is the urgent half; expiry is the tidy-up.

        A deployment with no table must still be able to block, but it must not
        look like the block will expire on its own.
        """
        from handler import handler

        with patch("handler._blocks_table", return_value=None):
            result = handler(
                {"action": "blockSmbUser", "domain": "CORP", "username": "jdoe", "confirm": True},
                None,
            )

        assert result["success"] is True
        assert result["expiryTracked"] is False
        assert result["expiresAt"] is None

    def test_ledger_write_failure_does_not_report_a_failed_block(self, mock_secrets, mock_arp):
        from handler import handler

        table = MagicMock()
        table.put_item.side_effect = RuntimeError("throttled")
        with patch("handler._blocks_table", return_value=table):
            result = handler(
                {"action": "blockSmbUser", "domain": "CORP", "username": "jdoe", "confirm": True},
                None,
            )

        # The block is in place, so success is accurate. What changed is that
        # nothing will expire it, which the caller has to be told.
        assert result["success"] is True
        assert result["expiryTracked"] is False
        assert result["ledgerError"] == "RuntimeError"

    def test_contain_threat_records_both_blocks_it_places(self, mock_secrets, mock_arp, ledger):
        """The most urgent route must not be the one that never expires."""
        from handler import handler

        result = handler(
            {
                "action": "containThreat",
                "domain": "CORP",
                "username": "jdoe",
                "clientIp": "203.0.113.99",
                "confirm": True,
            },
            None,
        )

        assert result["success"] is True
        assert result["expiryTracked"] is True
        assert {r["blockType"] for r in ledger.values()} == {"smb", "nfs"}
        assert all(r.get("viaContainThreat") for r in ledger.values())

    def test_manual_unblock_closes_the_row(self, mock_secrets, mock_arp, ledger):
        from handler import handler

        handler({"action": "blockSmbUser", "domain": "CORP", "username": "jdoe", "confirm": True}, None)
        handler({"action": "unblockSmbUser", "domain": "CORP", "username": "jdoe"}, None)

        row = next(iter(ledger.values()))
        assert row["status"] == "lifted"
        assert row["liftReason"] == "manual"


class TestExpirySweep:
    def _row(self, block_id, **over):
        base = {
            "blockId": block_id,
            "blockType": "smb",
            "svm": "fsxsvm01",
            "status": "active",
            "domain": "CORP",
            "username": "jdoe",
            "expiresAt": "2020-01-01T00:00:00Z",
        }
        base.update(over)
        return base

    def test_lifts_only_blocks_that_are_due(self, mock_secrets, mock_arp, ledger):
        from handler import handler

        future = (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat().replace("+00:00", "Z")
        ledger["due"] = self._row("due")
        ledger["later"] = self._row("later", username="alice", expiresAt=future)
        ledger["forever"] = self._row("forever", username="bob", expiresAt=None)

        result = handler({"action": "sweepExpiredBlocks"}, None)

        assert result["success"] is True
        assert result["swept"] == 1
        assert ledger["due"]["status"] == "lifted"
        assert ledger["due"]["liftReason"] == "expired"
        assert ledger["later"]["status"] == "active"
        assert ledger["forever"]["status"] == "active"
        assert mock_arp.unblock_smb_user.call_count == 1

    def test_ignores_blocks_the_portal_did_not_place(self, mock_secrets, mock_arp, ledger):
        """A block set at the ONTAP CLI must survive the sweep.

        The portal cannot know the intent behind it, and lifting it would be a
        silent loss of containment.
        """
        from handler import handler

        result = handler({"action": "sweepExpiredBlocks"}, None)

        assert result["swept"] == 0
        assert result["examined"] == 0
        mock_arp.unblock_smb_user.assert_not_called()
        mock_arp.unblock_nfs_ip.assert_not_called()

    def test_failed_unblock_leaves_the_row_active_for_the_next_run(self, mock_secrets, mock_arp, ledger):
        from handler import handler

        ledger["due"] = self._row("due")
        mock_arp.unblock_smb_user.side_effect = RuntimeError("ONTAP unreachable")

        result = handler({"action": "sweepExpiredBlocks"}, None)

        assert result["success"] is False
        assert result["failed"] == 1
        # Retried next tick. Unblocking twice is harmless; leaving a principal
        # cut off because one sweep failed is not.
        assert ledger["due"]["status"] == "active"

    def test_nfs_rows_use_the_export_policy_unblock(self, mock_secrets, mock_arp, ledger):
        from handler import handler

        ledger["due"] = self._row("due", blockType="nfs", policyName="default", clientIp="203.0.113.99")

        result = handler({"action": "sweepExpiredBlocks"}, None)

        assert result["swept"] == 1
        mock_arp.unblock_nfs_ip.assert_called_once()
        assert mock_arp.unblock_nfs_ip.call_args.kwargs["client_ip"] == "203.0.113.99"

    def test_unparseable_expiry_is_counted_not_ignored(self, mock_secrets, mock_arp, ledger):
        from handler import handler

        ledger["broken"] = self._row("broken", expiresAt="whenever")

        result = handler({"action": "sweepExpiredBlocks"}, None)

        assert result["failed"] == 1
        assert result["success"] is False
        mock_arp.unblock_smb_user.assert_not_called()


class TestExpiryInListing:
    def test_marks_blocks_without_a_ledger_row_as_unmanaged(self, mock_secrets, mock_arp, ledger):
        """The honest answer for a block placed outside the portal."""
        from handler import handler

        mock_arp.list_active_blocks.return_value = {
            "action": "list_active_blocks",
            "svm": "fsxsvm01",
            "smb_blocks": [{"pattern": "CORP\\\\stranger", "index": 1, "replacement": " "}],
            "nfs_blocks": [],
            "total": 1,
        }

        result = handler({"action": "listActiveBlocks"}, None)

        assert result["smbBlocks"][0]["managedByPortal"] is False
        assert result["smbBlocks"][0]["expiresAt"] is None

    def test_shows_expiry_for_a_portal_block(self, mock_secrets, mock_arp, ledger):
        from handler import handler

        handler({"action": "blockSmbUser", "domain": "CORP", "username": "jdoe", "confirm": True}, None)
        mock_arp.list_active_blocks.return_value = {
            "action": "list_active_blocks",
            "svm": "fsxsvm01",
            "smb_blocks": [{"pattern": "CORP\\\\jdoe", "index": 1, "replacement": " "}],
            "nfs_blocks": [],
            "total": 1,
        }

        result = handler({"action": "listActiveBlocks"}, None)

        assert result["smbBlocks"][0]["managedByPortal"] is True
        assert result["smbBlocks"][0]["expiresAt"] is not None


# --- Multi-SVM fan-out --------------------------------------------------------
#
# A compromised account is usually reachable on every SVM that trusts the same
# directory, so containing it one SVM at a time leaves the rest open for as long
# as that takes. These tests pin the two properties that matter: fan-out never
# happens unless asked for, and a partial result is reported as partial.


@pytest.fixture
def mock_http():
    """Patch the ONTAP GET helper used for SVM discovery."""
    with patch("handler._ontap_get") as get:
        get.return_value = {
            "records": [
                {"name": "svm1", "state": "running"},
                {"name": "svm2", "state": "running"},
                {"name": "svm_stopped", "state": "stopped"},
            ]
        }
        yield get


class TestFanOutTargeting:
    def test_no_fan_out_without_being_asked(self, mock_secrets, mock_arp, ledger):
        """An operator who names one SVM gets one SVM."""
        from handler import handler

        result = handler({"action": "blockSmbUser", "domain": "CORP", "username": "jdoe", "confirm": True}, None)

        assert result.get("fannedOut") is not True
        assert mock_arp.block_smb_user.call_count == 1

    def test_explicit_svm_list_hits_each_one(self, mock_secrets, mock_arp, ledger):
        from handler import handler

        result = handler(
            {
                "action": "blockSmbUser",
                "domain": "CORP",
                "username": "jdoe",
                "confirm": True,
                "svms": ["svmA", "svmB", "svmC"],
            },
            None,
        )

        assert result["success"] is True
        assert result["fannedOut"] is True
        assert result["succeededOn"] == ["svmA", "svmB", "svmC"]
        assert mock_arp.block_smb_user.call_count == 3
        # One ledger row per SVM, since a block on each is a separate thing to lift.
        assert len(ledger) == 3

    def test_duplicate_names_are_collapsed(self, mock_secrets, mock_arp, ledger):
        """Otherwise the repeat comes back as 'already blocked' and reads as a fault."""
        from handler import handler

        result = handler(
            {
                "action": "blockSmbUser",
                "domain": "CORP",
                "username": "jdoe",
                "confirm": True,
                "svms": ["svmA", "svmA", "svmB"],
            },
            None,
        )

        assert result["targets"] == ["svmA", "svmB"]
        assert mock_arp.block_smb_user.call_count == 2

    def test_all_svms_asks_the_cluster_and_skips_stopped_ones(self, mock_secrets, mock_arp, ledger, mock_http):
        """A block on a stopped SVM would report containment that protects nothing."""
        from handler import handler

        result = handler(
            {
                "action": "blockSmbUser",
                "domain": "CORP",
                "username": "jdoe",
                "confirm": True,
                "allSvms": True,
            },
            None,
        )

        assert result["targets"] == ["svm1", "svm2"]
        assert "svm_stopped" not in result["targets"]

    @pytest.mark.parametrize("bad", [[], "svm1", {}, [""], [None]], ids=["empty", "string", "dict", "blank", "none"])
    def test_rejects_an_unusable_svm_list(self, bad, mock_secrets, mock_arp, ledger):
        from handler import handler

        result = handler(
            {
                "action": "blockSmbUser",
                "domain": "CORP",
                "username": "jdoe",
                "confirm": True,
                "svms": bad,
            },
            None,
        )

        assert result["success"] is False
        assert "svms" in result["error"]
        mock_arp.block_smb_user.assert_not_called()

    def test_confirmation_is_checked_once_not_per_svm(self, mock_secrets, mock_arp, ledger):
        """A missing confirmation should explain itself, not return N refusals."""
        from handler import handler

        result = handler(
            {
                "action": "blockSmbUser",
                "domain": "CORP",
                "username": "jdoe",
                "svms": ["svmA", "svmB"],
            },
            None,
        )

        assert result["success"] is False
        assert "confirm=true" in result["error"]
        assert result.get("fannedOut") is not True
        mock_arp.block_smb_user.assert_not_called()


class TestFanOutPartialResults:
    def test_partial_failure_names_both_sides(self, mock_secrets, mock_arp, ledger):
        """Overall success would hide a gap; overall failure would hide real blocks.

        Either reading sends the operator to the wrong next action, so both the
        SVMs that worked and the ones that did not are named.
        """
        from handler import handler

        def block(svm_name, domain, username):
            if svm_name == "svmB":
                raise RuntimeError("ONTAP unreachable")
            return {"action": "block_smb_user", "status": "blocked"}

        mock_arp.block_smb_user.side_effect = block

        result = handler(
            {
                "action": "blockSmbUser",
                "domain": "CORP",
                "username": "jdoe",
                "confirm": True,
                "svms": ["svmA", "svmB", "svmC"],
            },
            None,
        )

        assert result["success"] is False
        assert result["succeededOn"] == ["svmA", "svmC"]
        assert result["failedOn"] == ["svmB"]
        assert "svmB" in result["error"]
        # The blocks that landed must still be recorded, or they cannot be lifted.
        assert len(ledger) == 2

    def test_one_svm_raising_does_not_abandon_the_rest(self, mock_secrets, mock_arp, ledger):
        from handler import handler

        calls = []

        def block(svm_name, domain, username):
            calls.append(svm_name)
            if svm_name == "svmA":
                raise RuntimeError("boom")
            return {"action": "block_smb_user", "status": "blocked"}

        mock_arp.block_smb_user.side_effect = block

        result = handler(
            {
                "action": "blockSmbUser",
                "domain": "CORP",
                "username": "jdoe",
                "confirm": True,
                "svms": ["svmA", "svmB"],
            },
            None,
        )

        assert calls == ["svmA", "svmB"]
        assert result["succeededOn"] == ["svmB"]


class TestListSvms:
    def test_reports_state_so_stopped_svms_are_visible(self, mock_secrets, mock_arp, mock_http):
        from handler import handler

        result = handler({"action": "listSvms"}, None)

        assert result["success"] is True
        assert result["total"] == 3
        assert {s["name"] for s in result["svms"]} == {"svm1", "svm2", "svm_stopped"}

    def test_reports_failure_rather_than_an_empty_cluster(self, mock_secrets, mock_arp):
        from handler import handler

        with patch("handler._ontap_get", side_effect=RuntimeError("timeout")):
            result = handler({"action": "listSvms"}, None)

        assert result["success"] is False
        assert result["svms"] == []
        assert "RuntimeError" in result["error"]


class TestListBlocksAcrossSvms:
    def test_each_entry_carries_its_svm(self, mock_secrets, mock_arp, ledger):
        """The unblock call needs to know where the block actually is."""
        from handler import handler

        mock_arp.list_active_blocks.side_effect = lambda svm_name: {
            "action": "list_active_blocks",
            "svm": svm_name,
            "smb_blocks": [{"pattern": f"CORP\\\\{svm_name}user", "index": 1}],
            "nfs_blocks": [],
            "total": 1,
        }

        result = handler({"action": "listActiveBlocks", "svms": ["svmA", "svmB"]}, None)

        assert result["success"] is True
        assert result["total"] == 2
        assert {b["svm"] for b in result["smbBlocks"]} == {"svmA", "svmB"}

    def test_a_skipped_svm_is_a_failure_not_a_shorter_list(self, mock_secrets, mock_arp, ledger):
        """A block hiding on an unreadable SVM cannot be lifted from the portal."""
        from handler import handler

        def listing(svm_name):
            if svm_name == "svmB":
                raise RuntimeError("unreachable")
            return {
                "action": "list_active_blocks",
                "svm": svm_name,
                "smb_blocks": [],
                "nfs_blocks": [],
                "total": 0,
            }

        mock_arp.list_active_blocks.side_effect = listing

        result = handler({"action": "listActiveBlocks", "svms": ["svmA", "svmB"]}, None)

        assert result["success"] is False
        assert "svmB" in result["error"]


# --- Audit attribution ---------------------------------------------------------
#
# The ledger row says who contained a principal. If a caller can set that, the
# audit trail is worth nothing, and the trail is the reason this feature can be
# described as auditable at all.


class TestAuditAttribution:
    def test_records_the_appsync_identity(self, mock_secrets, mock_arp, ledger):
        from handler import handler

        handler(
            {
                "action": "blockSmbUser",
                "domain": "CORP",
                "username": "jdoe",
                "confirm": True,
                "userId": "alice",
                "invokedVia": "appsync",
            },
            None,
        )

        row = next(iter(ledger.values()))
        assert row["createdBy"] == "alice"
        assert row["createdVia"] == "appsync"

    def test_a_caller_cannot_name_someone_else_without_the_appsync_marker(self, mock_secrets, mock_arp, ledger):
        """A userId with no resolver marker is a direct invocation, not a user.

        The resolver sets both together. Accepting a userId on its own would let
        anyone with lambda:InvokeFunction attribute a block to a colleague.
        """
        from handler import handler

        handler(
            {
                "action": "blockSmbUser",
                "domain": "CORP",
                "username": "jdoe",
                "confirm": True,
                "userId": "alice",
            },
            None,
        )

        row = next(iter(ledger.values()))
        assert row["createdBy"] == "unattributed"
        assert row["createdVia"] == "direct-invoke"

    def test_the_removed_actor_fallback_is_not_honoured(self, mock_secrets, mock_arp, ledger):
        """`actor` used to be trusted, and no resolver ever cleared it."""
        from handler import handler

        handler(
            {
                "action": "blockSmbUser",
                "domain": "CORP",
                "username": "jdoe",
                "confirm": True,
                "actor": "someone-else",
            },
            None,
        )

        row = next(iter(ledger.values()))
        assert row["createdBy"] == "unattributed"
        assert "someone-else" not in row.values()

    def test_an_unattributed_action_is_distinguishable_from_a_failed_lookup(self, mock_secrets, mock_arp, ledger):
        from handler import handler

        handler(
            {"action": "blockSmbUser", "domain": "CORP", "username": "jdoe", "confirm": True},
            None,
        )

        row = next(iter(ledger.values()))
        # "unknown" would read as a lookup that failed. This has to read as an
        # action nobody is accountable for.
        assert row["createdBy"] == "unattributed"
        assert row["createdVia"] == "direct-invoke"


class TestUnattributedActionIsReported:
    """The ledger already recorded a direct invocation; nothing announced it.

    A forged containment action is not preventable from inside the function — in
    one account an identity policy alone is enough to invoke it, and a Lambda
    resource policy can only grant, never revoke. So the requirement these cover
    is narrower and achievable: the case must not be silent while the containment
    is still in force.
    """

    def _metrics(self, capsys):
        """The EMF documents written to stdout, in order."""
        emitted = []
        for line in capsys.readouterr().out.split("\n"):
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                doc = json.loads(line)
            except ValueError:
                continue
            if "_aws" in doc:
                emitted.append(doc)
        return emitted

    def _named(self, capsys, name):
        return [d for d in self._metrics(capsys) if name in d]

    def test_a_direct_invocation_is_counted(self, mock_secrets, mock_arp, ledger, capsys):
        from handler import handler

        handler(
            {"action": "blockSmbUser", "domain": "CORP", "username": "jdoe", "confirm": True},
            None,
        )

        docs = self._named(capsys, "UnattributedContainmentActions")
        assert docs, "no attribution metric was emitted"
        assert docs[0]["UnattributedContainmentActions"] == 1
        assert docs[0]["AttributedContainmentActions"] == 0
        # Which action it was belongs in the log, not in a metric dimension.
        assert docs[0]["action"] == "blockSmbUser"

    def test_an_appsync_call_is_counted_as_attributed(self, mock_secrets, mock_arp, ledger, capsys):
        from handler import handler

        handler(
            {
                "action": "blockSmbUser",
                "domain": "CORP",
                "username": "jdoe",
                "confirm": True,
                "userId": "alice",
                "invokedVia": "appsync",
            },
            None,
        )

        docs = self._named(capsys, "UnattributedContainmentActions")
        assert docs[0]["UnattributedContainmentActions"] == 0
        assert docs[0]["AttributedContainmentActions"] == 1

    def test_the_scheduled_sweep_is_not_counted(self, capsys):
        """EventBridge invokes the sweep directly and carries no user by design.

        Counting it would put the alarm in breach every sweep interval, which
        trains people to ignore it — the failure mode the alarm exists to avoid.
        """
        from handler import _note_attribution

        _note_attribution("sweepExpiredBlocks", {})

        assert not self._named(capsys, "UnattributedContainmentActions")

    @pytest.mark.parametrize(
        "action",
        ["listSvms", "listActiveBlocks", "getArpStatus", "getSnapshotsWithLockStatus"],
    )
    def test_a_read_only_action_is_not_counted(self, action, capsys):
        """Reads change nothing, so an unattributed one is not an incident.

        Called directly rather than through `handler`, because these actions
        reach ONTAP over HTTPS and the suite does not stub the transport.
        """
        from handler import _note_attribution

        _note_attribution(action, {})

        assert not self._named(capsys, "UnattributedContainmentActions")

    @pytest.mark.parametrize(
        "action",
        [
            "blockSmbUser",
            "unblockSmbUser",
            "blockNfsIp",
            "unblockNfsIp",
            "containThreat",
            "disconnectSessions",
            "createSnapshot",
            "deleteSnapshot",
            "updateArpState",
            "updateRetentionPolicy",
        ],
    )
    def test_every_state_changing_action_is_counted(self, action, capsys):
        """Including the unblocks: ending containment early is also an incident."""
        from handler import _note_attribution

        _note_attribution(action, {})

        docs = self._named(capsys, "UnattributedContainmentActions")
        assert docs, f"{action} emitted no attribution metric"
        assert docs[0]["UnattributedContainmentActions"] == 1

    def test_reported_even_when_ontap_is_not_configured(self, monkeypatch, capsys):
        """An attempt that could not have worked is still worth seeing.

        Someone looking for a way in produces exactly this, and a metric that
        only counted attempts which reached the cluster would miss it. Asserted
        through `handler` because the ordering is the point: the emit has to come
        before the configuration check that returns early.
        """
        import handler as handler_module

        monkeypatch.setattr(handler_module, "MGMT_IP", "")
        result = handler_module.handler(
            {"action": "blockSmbUser", "domain": "CORP", "username": "jdoe", "confirm": True},
            None,
        )

        assert "error" in result
        docs = self._named(capsys, "UnattributedContainmentActions")
        assert docs and docs[0]["UnattributedContainmentActions"] == 1

    def test_a_metrics_failure_does_not_stop_the_action(self, monkeypatch):
        """Telemetry is the lesser concern when access is being cut or restored.

        Serialisation is broken rather than stdout: patching `print` would take
        out pytest's own capture along with the code under test.
        """
        import handler as handler_module

        def explode(*_args, **_kwargs):
            raise RuntimeError("cannot serialise")

        monkeypatch.setattr(handler_module.json, "dumps", explode)

        # Raising here would abandon a containment action over a metric.
        handler_module._note_attribution("blockSmbUser", {})


class TestSettingsSurviveABadValue:
    """A malformed setting must not take the whole function down.

    These were bare `int(os.environ.get(...))` at module scope, so a bad value
    raised during import and every action failed before its handler ran. That is
    how a configuration copied from portal-config.example.ts behaved: the example
    did not declare defaultBlockTtlHours, backend.ts writes it with
    String(config.defaultBlockTtlHours), and the environment got "undefined".
    """

    def test_a_non_numeric_value_falls_back_instead_of_raising(self, monkeypatch):
        from handler import _env_int

        monkeypatch.setenv("SOME_SETTING", "undefined")
        assert _env_int("SOME_SETTING", 24) == 24

    @pytest.mark.parametrize("value", ["", "  ", "1.5.2", "twenty", "None"])
    def test_other_malformed_values_also_fall_back(self, monkeypatch, value):
        from handler import _env_int

        monkeypatch.setenv("SOME_SETTING", value)
        assert _env_int("SOME_SETTING", 7) == 7

    def test_an_absent_value_uses_the_default(self, monkeypatch):
        from handler import _env_int

        monkeypatch.delenv("SOME_SETTING", raising=False)
        assert _env_int("SOME_SETTING", 24) == 24

    def test_a_valid_value_is_honoured(self, monkeypatch):
        from handler import _env_int

        monkeypatch.setenv("SOME_SETTING", "72")
        assert _env_int("SOME_SETTING", 24) == 72

    def test_the_module_imports_with_the_value_that_used_to_kill_it(self):
        """The regression itself, run the way it actually happened."""
        import os
        import subprocess
        import sys

        env = {**os.environ, "DEFAULT_BLOCK_TTL_HOURS": "undefined"}
        env["PYTHONPATH"] = str(Path(__file__).parent.parent)
        result = subprocess.run(
            [sys.executable, "-c", "import handler; print(handler.DEFAULT_BLOCK_TTL_HOURS)"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(Path(__file__).parent.parent),
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "24"


class TestTtlCeiling:
    def test_refuses_above_the_ceiling_and_says_what_to_do(self, monkeypatch):
        import handler as handler_module

        monkeypatch.setattr(handler_module, "MAX_BLOCK_TTL_HOURS", 24 * 30)
        hours, error = handler_module._validated_ttl_hours({"ttlHours": 24 * 365})

        assert hours is None
        # A refusal that does not name a way forward invites halving the number
        # until it is accepted, which produces an expiry nobody chose.
        assert "ttlHours=0" in error["error"]
        assert "directory" in error["error"]
        assert "maxBlockTtlHours" in error["error"]

    def test_the_ceiling_is_configurable(self, monkeypatch):
        import handler as handler_module

        monkeypatch.setattr(handler_module, "MAX_BLOCK_TTL_HOURS", 24 * 90)
        hours, error = handler_module._validated_ttl_hours({"ttlHours": 24 * 60})

        assert error is None
        assert hours == 24 * 60

    def test_zero_removes_the_ceiling(self, monkeypatch):
        """A deployment may decide the bound belongs somewhere else."""
        import handler as handler_module

        monkeypatch.setattr(handler_module, "MAX_BLOCK_TTL_HOURS", 0)
        hours, error = handler_module._validated_ttl_hours({"ttlHours": 24 * 3650})

        assert error is None
        assert hours == 24 * 3650

    def test_an_indefinite_block_is_still_allowed_under_a_ceiling(self, monkeypatch):
        """ttlHours=0 is 'no expiry', not 'zero hours', so a ceiling cannot bar it."""
        import handler as handler_module

        monkeypatch.setattr(handler_module, "MAX_BLOCK_TTL_HOURS", 24 * 30)
        hours, error = handler_module._validated_ttl_hours({"ttlHours": 0})

        assert error is None
        assert hours == 0

    def test_the_boundary_itself_is_accepted(self, monkeypatch):
        import handler as handler_module

        monkeypatch.setattr(handler_module, "MAX_BLOCK_TTL_HOURS", 720)
        hours, error = handler_module._validated_ttl_hours({"ttlHours": 720})

        assert error is None
        assert hours == 720
