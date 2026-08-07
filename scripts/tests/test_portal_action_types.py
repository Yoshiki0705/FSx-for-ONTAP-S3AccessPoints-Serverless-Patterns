"""Tests for the generated TypeScript parameter map.

The map exists to close the one thing the parameter check cannot see: a key whose
*name* is right and whose *value* is wrong. A volume name passed where a UUID is
expected spells the key correctly, so only a type can object.

Two things have to hold for that to be worth anything:

  * the generated types describe what the handlers actually read, and keep doing so
  * the tables that decide which values are interchangeable are right

The second is where this went wrong once. An enum table keyed on the parameter *name*
asserted that `protocol` is `nfs | cifs | s3` — true for the action whose handler
validates it, wrong for FPolicy events, which take ONTAP's `cifs | nfsv3 | nfsv4`.
The table rejected a screen that worked. Enums are now read from the handler's own
`if x not in (...)` guard, and the cases below pin that.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import check_portal_action_params as checker  # noqa: E402
import portal_action_types as types  # noqa: E402
from check_portal_action_params import ActionContract  # noqa: E402


def contracts_from(source: str, tmp_path: Path):
    """Parse a handler snippet the way the generator does."""
    path = tmp_path / "handler.py"
    path.write_text(source)
    original = checker.PORTAL
    checker.PORTAL = tmp_path
    try:
        return checker.handler_contracts(path, flattened=True, injected=frozenset({"action", "userId"}))
    finally:
        checker.PORTAL = original


class TestDerivedEnums:
    def test_a_membership_guard_becomes_a_union(self, tmp_path):
        source = """
def handler(event, context):
    action = event.get("action", "")
    if action == "putS3ObjectLockRetention":
        mode = event.get("mode", "GOVERNANCE")
        if mode not in ("GOVERNANCE", "COMPLIANCE"):
            return {"success": False, "error": "Mode must be GOVERNANCE or COMPLIANCE"}
        return {"success": True}
"""
        contract = contracts_from(source, tmp_path)["putS3ObjectLockRetention"]
        assert contract.enums["mode"] == ("GOVERNANCE", "COMPLIANCE")
        assert types._type_for("putS3ObjectLockRetention", "mode", contract) == '"GOVERNANCE" | "COMPLIANCE"'

    def test_an_unchecked_parameter_stays_a_string(self, tmp_path):
        """The FPolicy case: no guard, and the values are not the ones a sibling uses.

        Guessing here is what rejected a working screen, so the absence of a guard
        has to produce `string` rather than a plausible-looking union.
        """
        source = """
def handler(event, context):
    action = event.get("action", "")
    if action == "createFpolicyEvent":
        name = event.get("name", "")
        protocol = event.get("protocol", "")
        if not name or not protocol:
            return {"success": False, "error": "name and protocol are required"}
        return {"success": True}
"""
        contract = contracts_from(source, tmp_path)["createFpolicyEvent"]
        assert "protocol" not in contract.enums
        assert types._type_for("createFpolicyEvent", "protocol", contract) == "string"

    def test_the_same_name_can_differ_between_actions(self, tmp_path):
        source = """
def handler(event, context):
    action = event.get("action", "")
    if action == "createFpolicyEvent":
        protocol = event.get("protocol", "")
        if not protocol:
            return {"success": False, "error": "protocol is required"}
        return {"success": True}
    if action == "setProtocolServiceEnabled":
        protocol = event.get("protocol", "")
        if protocol not in ("nfs", "cifs", "s3"):
            return {"success": False, "error": "Invalid protocol"}
        return {"success": True}
"""
        contracts = contracts_from(source, tmp_path)
        assert types._type_for("createFpolicyEvent", "protocol", contracts["createFpolicyEvent"]) == "string"
        assert (
            types._type_for("setProtocolServiceEnabled", "protocol", contracts["setProtocolServiceEnabled"])
            == '"nfs" | "cifs" | "s3"'
        )

    def test_a_guard_inside_a_branch_is_not_a_global_constraint(self, tmp_path):
        """A conditional guard restricts that path, not the parameter."""
        source = """
def handler(event, context):
    action = event.get("action", "")
    if action == "updateRetentionPolicy":
        target = event.get("target", "")
        mode = event.get("mode", "")
        if target == "s3_object_lock":
            if mode not in ("GOVERNANCE", "COMPLIANCE"):
                return {"success": False, "error": "Invalid mode"}
        return {"success": True}
"""
        contract = contracts_from(source, tmp_path)["updateRetentionPolicy"]
        assert "mode" not in contract.enums


class TestTypeSelection:
    def test_a_brand_wins_over_everything(self):
        contract = ActionContract(handler="h", enums={"volumeUuid": ("a", "b")})
        # An identifier is branded whatever else is known about it: the point is that
        # a plain string cannot be one, and a union of strings still admits strings.
        assert types._type_for("resizeVolume", "volumeUuid", contract) == "VolumeUuid"

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("expiryTime", "IsoTimestamp"),
            ("retentionPeriod", "IsoDuration"),
            ("snapshotUuid", "SnapshotId"),
            ("days", "number"),
            ("confirm", "boolean"),
            ("acknowledgeIrreversible", "true"),
            ("events", "string[]"),
            ("comment", "string"),
        ],
    )
    def test_scalars_lists_and_brands(self, name, expected):
        assert types._type_for("anyAction", name, ActionContract(handler="h")) == expected

    def test_the_acknowledgement_flag_admits_only_true(self):
        # The guard refuses the string "true", so a boolean type would let a caller
        # write `false` and be told at runtime what the type could have said.
        assert types._type_for("createVolume", "acknowledgeIrreversible", ActionContract(handler="h")) == "true"


class TestRequiredAndOptional:
    def test_single_alternative_groups_are_required(self):
        contract = ActionContract(handler="h", groups=[{"a"}, {"b", "c"}], branch_read={"a", "b", "c", "d"})
        assert types._required_keys(contract) == {"a"}
        # An either/or pair cannot be expressed as two required fields, so both are
        # optional and the handler's own guard remains the thing that enforces it.
        assert types._optional_keys(contract) == {"b", "c", "d"}

    def test_optional_keys_come_from_the_branch_not_the_module(self):
        """`read` is deliberately wide; using it would let every action take every key."""
        contract = ActionContract(handler="h", branch_read={"a"}, read={"a", "unrelated"})
        assert types._optional_keys(contract) == {"a"}


class TestGeneratedModule:
    def test_it_matches_the_handlers(self):
        """`--check` on the committed file, which is what CI runs."""
        assert types.check() == 0

    def test_emit_is_stable(self):
        """Generating twice gives the same bytes, so a regeneration is a clean diff."""
        assert types.emit() == types.emit()

    def test_the_committed_file_is_what_emit_produces(self):
        """Otherwise the file has been hand-edited and the next regeneration reverts it."""
        assert types.TARGET.read_text() == types.emit()

    def test_every_endpoint_map_names_a_real_handler(self):
        for handler_dir in types.HANDLER_MAPS:
            assert (types.PORTAL / "functions" / handler_dir).is_dir()

    def test_unchecked_enums_name_real_actions(self):
        """A table entry for an action that no longer exists silently stops applying."""
        by_handler = types.handler_contract_sets()
        known = {action for contracts in by_handler.values() for action in contracts}
        for action, parameter in types.UNCHECKED_ENUMS:
            assert action in known, f"{action} is not dispatched by any handler"
            actions = [c for c in by_handler.values() if action in c]
            contract = actions[0][action]
            assert parameter in contract.branch_read, f"{action} does not read {parameter}"
