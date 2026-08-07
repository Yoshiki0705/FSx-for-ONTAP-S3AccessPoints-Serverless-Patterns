"""Tests for the portal action-parameter check.

The check exists because a button that never worked shipped and stayed shipped:
the Tamperproof tab sent `{snapshotName, retentionDays}` to an action reading
`snapshotId` and `expiryTime`, so every click returned "snapshotId and expiryTime
required". TypeScript cannot see across an untyped `params` blob, and no test
mocked the boundary, so nothing objected.

The cases below are the shapes that made the first three versions of the checker
wrong, each of which reported working code as broken:

  * two handlers dispatching one action name with different contracts
  * `if not days and not years` — either/or, not both required
  * a shape guard nested under `if requested is not None:` — validates, not demands
  * `params` nested by one resolver and spread by the others
  * `action = event.get("action", "listSnapshots")` — dispatch by default
  * a key read through a module constant rather than a literal
  * a callback handed to a fan-out helper, which reads the payload one level out

A checker that fires on any of those trains people to ignore it, which is worse
than not having it. So each is pinned here, alongside the bug it must still catch.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from check_portal_action_params import (  # noqa: E402
    ActionContract,
    _blank_comments,
    _default_actions,
    _payload_variable,
    _top_level_keys,
    handler_contracts,
    module_string_constants,
)


def contracts_from(source: str, tmp_path: Path, flattened: bool = True, injected=frozenset({"action", "userId"})):
    """Parse a handler snippet the way the checker does."""
    path = tmp_path / "handler.py"
    path.write_text(source)
    # handler_contracts reports locations relative to the portal root, so the file
    # has to sit under a path it can make relative. Patching that is more fragile
    # than giving it one.
    import check_portal_action_params as checker

    original = checker.PORTAL
    checker.PORTAL = tmp_path
    try:
        return handler_contracts(path, flattened, injected)
    finally:
        checker.PORTAL = original


class TestRequirementDetection:
    def test_a_guarded_key_is_required(self, tmp_path):
        source = """
def handler(event, context):
    action = event.get("action", "")
    if action == "lockSnapshot":
        snap = event.get("snapshotId", "")
        expiry = event.get("expiryTime", "")
        if not snap or not expiry:
            return {"success": False, "error": "snapshotId and expiryTime required"}
        return {"success": True}
"""
        contracts = contracts_from(source, tmp_path)
        groups = contracts["lockSnapshot"].groups
        # Two independent requirements, not one either/or.
        assert {frozenset(g) for g in groups} == {frozenset({"snapshotId"}), frozenset({"expiryTime"})}

    def test_the_known_broken_call_is_caught(self, tmp_path):
        """The lock button's actual shape: right action, wrong parameters."""
        source = """
def handler(event, context):
    action = event.get("action", "")
    if action == "lockSnapshot":
        snap = event.get("snapshotId", "")
        expiry = event.get("expiryTime", "")
        if not snap or not expiry:
            return {"success": False, "error": "snapshotId and expiryTime required"}
        return {"success": True}
"""
        contract = contracts_from(source, tmp_path)["lockSnapshot"]
        sent = {"snapshotName", "retentionDays", "acknowledgeIrreversible"}
        unsatisfied = contract.unsatisfied(sent)
        assert {frozenset(g) for g in unsatisfied} == {frozenset({"snapshotId"}), frozenset({"expiryTime"})}

    def test_either_or_is_one_requirement(self, tmp_path):
        """`if not days and not years` asks for one of the two, not for both.

        Reading it as two requirements flagged every caller that sent only days,
        which is all of them.
        """
        source = """
def handler(event, context):
    action = event.get("action", "")
    if action == "putS3ObjectLockRetention":
        days = event.get("days")
        years = event.get("years")
        if not days and not years:
            return {"success": False, "error": "Either days or years is required"}
        return {"success": True}
"""
        contract = contracts_from(source, tmp_path)["putS3ObjectLockRetention"]
        assert contract.unsatisfied({"days"}) == []
        assert contract.unsatisfied({"years"}) == []
        assert [frozenset(g) for g in contract.unsatisfied(set())] == [frozenset({"days", "years"})]

    def test_not_all_requires_each(self, tmp_path):
        source = """
def handler(event, context):
    action = event.get("action", "")
    if action == "createShare":
        name = event.get("name", "")
        path = event.get("path", "")
        if not all([name, path]):
            return {"success": False, "error": "name and path are required"}
        return {"success": True}
"""
        contract = contracts_from(source, tmp_path)["createShare"]
        assert contract.unsatisfied({"name", "path"}) == []
        assert len(contract.unsatisfied({"name"})) == 1

    def test_a_shape_guard_does_not_make_a_key_required(self, tmp_path):
        """Validating a value when supplied is not the same as demanding it.

        `svms` is optional and falls back to a single SVM, but inside
        `if requested is not None:` there is a guard that returns. Reading that as
        a requirement made every containment call look broken.
        """
        source = """
def handler(event, context):
    action = event.get("action", "")
    if action == "blockSmbUser":
        requested = event.get("svms")
        if requested is not None:
            if not requested:
                return {"success": False, "error": "svms must be a non-empty list"}
        return {"success": True}
"""
        contract = contracts_from(source, tmp_path)["blockSmbUser"]
        assert contract.unsatisfied(set()) == []

    def test_subscript_access_is_required(self, tmp_path):
        source = """
def handler(event, context):
    action = event.get("action", "")
    if action == "resize":
        size = event["sizeGiB"]
        return {"size": size}
"""
        contract = contracts_from(source, tmp_path)["resize"]
        assert [frozenset(g) for g in contract.unsatisfied(set())] == [frozenset({"sizeGiB"})]

    def test_a_guarded_subscript_is_optional(self, tmp_path):
        """The optional-field copy: `if event.get("k"): body["k"] = event["k"]`.

        The subscript cannot raise there, so it says nothing about what the caller
        must send. Counting it made three actions demand every field they accept —
        cluster peering asked for a name and an ipspace that ONTAP defaults.
        """
        source = """
def handler(event, context):
    action = event.get("action", "")
    if action == "createClusterPeer":
        addresses = event.get("remoteAddresses") or []
        if not addresses:
            return {"success": False, "error": "remoteAddresses is required"}
        body = {"remote": {"ip_addresses": addresses}}
        if event.get("name"):
            body["name"] = event["name"]
        if event.get("ipspace"):
            body["ipspace"] = {"name": event["ipspace"]}
        return {"success": True}
"""
        contract = contracts_from(source, tmp_path)["createClusterPeer"]
        assert [frozenset(g) for g in contract.unsatisfied({"remoteAddresses"})] == []
        # Still recognised as keys the handler reads, just not as requirements.
        assert {"name", "ipspace"} <= contract.read

    def test_a_conditional_requirement_is_not_unconditional(self, tmp_path):
        """A retention period is required for a SnapLock volume and not otherwise.

        Reporting it flatly told every caller creating an ordinary volume that it
        was missing three parameters it must not send.
        """
        source = """
def handler(event, context):
    action = event.get("action", "")
    if action == "createVolume":
        name = event.get("name", "")
        if not name:
            return {"success": False, "error": "name is required"}
        snaplock = event.get("snaplockType", "")
        if snaplock:
            if not event.get("retentionDefault"):
                return {"success": False, "error": "retentionDefault is required"}
        return {"success": True}
"""
        contract = contracts_from(source, tmp_path)["createVolume"]
        assert [frozenset(g) for g in contract.unsatisfied({"name", "sizeGiB"})] == []
        assert [frozenset(g) for g in contract.unsatisfied(set())] == [frozenset({"name"})]


class TestDispatchShapes:
    def test_default_action_counts_as_dispatched(self, tmp_path):
        """`event.get("action", "listSnapshots")` serves listSnapshots.

        Scanning only for `action == "..."` concluded the handler did not support
        the action it exists to serve, and three call sites were reported as
        calling something that was not there.
        """
        source = """
def handler(event, context):
    action = event.get("action", "listSnapshots")
    max_results = event.get("maxResults", 10)
    if action == "getArpStatus":
        return {"arp": True}
    return {"snapshots": [], "max": max_results}
"""
        contracts = contracts_from(source, tmp_path)
        assert "listSnapshots" in contracts
        assert "maxResults" in contracts["listSnapshots"].read

    def test_compound_branch_test(self, tmp_path):
        """`action == "x" and event.get("y")` still dispatches x."""
        source = """
def handler(event, context):
    action = event.get("action", "listFiles")
    if action == "listFilesFromAp" and event.get("apAlias"):
        return {"files": []}
    return {"files": []}
"""
        assert "listFilesFromAp" in contracts_from(source, tmp_path)

    def test_action_in_tuple(self, tmp_path):
        source = """
def handler(event, context):
    action = event.get("action", "")
    if action in ("trashFile", "restoreFromTrash"):
        return {"ok": True}
"""
        contracts = contracts_from(source, tmp_path)
        assert {"trashFile", "restoreFromTrash"} <= set(contracts)

    def test_single_purpose_handler_has_no_contract(self, tmp_path):
        """A Lambda that never reads `action` does one thing; the name is decoration."""
        source = """
def handler(event, context):
    prefix = event.get("prefix", "")
    return {"zip": prefix}
"""
        assert contracts_from(source, tmp_path) is None

    def test_nested_params_are_followed(self, tmp_path):
        """One resolver nests `params` instead of spreading it.

        The agent endpoint sends `payload: {action, params, userId}`, so its handler
        reads `params.get(...)`. Assuming the spread shape reported every agent
        action as ignoring everything it was sent.
        """
        source = """
def _load_session(user_id, params):
    return {"id": params.get("sessionId")}


def handler(event, context):
    action = event.get("action", "")
    params = event.get("params", {})
    user_id = event.get("userId", "anonymous")
    if action == "loadSession":
        return _load_session(user_id, params)
"""
        contract = contracts_from(source, tmp_path, flattened=False)["loadSession"]
        assert "sessionId" in contract.read

    def test_payload_variable_detection(self, tmp_path):
        nested = ast.parse('def handler(event, context):\n    body = event.get("params", {})\n')
        assert _payload_variable(nested, flattened=False) == "body"
        assert _payload_variable(nested, flattened=True) == "event"


class TestIndirection:
    def test_module_constant_keys_resolve(self, tmp_path):
        """A key read through a constant is still a key.

        `event.get(_IRREVERSIBLE_ACK_FIELD)` reported the acknowledgement flag as
        something nothing reads, on every call site that correctly sends it.
        """
        source = """
_ACK = "acknowledgeIrreversible"


def _require_ack(event):
    if event.get(_ACK) is True:
        return None
    return {"success": False, "error": "ack required"}


def handler(event, context):
    action = event.get("action", "")
    if action == "enableSnapshotLocking":
        refused = _require_ack(event)
        if refused:
            return refused
        return {"success": True}
"""
        contract = contracts_from(source, tmp_path)["enableSnapshotLocking"]
        assert "acknowledgeIrreversible" in contract.read

    def test_callback_delegates_are_followed(self, tmp_path):
        """A function passed to a fan-out helper reads the payload one level out."""
        source = """
def _disconnect(event):
    user = event.get("user")
    client_ip = event.get("clientIp")
    if not user and not client_ip:
        return {"success": False, "error": "one of user or clientIp"}
    return {"success": True}


def _fan_out(event, single):
    return single({**event, "svm": "svm1"})


def handler(event, context):
    action = event.get("action", "")
    if action == "disconnectSessions":
        return _fan_out(event, _disconnect)
"""
        contract = contracts_from(source, tmp_path)["disconnectSessions"]
        assert {"user", "clientIp"} <= contract.read

    def test_resolver_injected_keys_are_not_requirements(self, tmp_path):
        source = """
def handler(event, context):
    action = event.get("action", "")
    if action == "doThing":
        user = event.get("userId", "")
        if not user:
            return {"success": False, "error": "userId required"}
        return {"success": True}
"""
        contract = contracts_from(source, tmp_path)["doThing"]
        # The resolver supplies userId, so a caller omitting it is not at fault.
        assert contract.unsatisfied(set()) == []


class TestCallSiteParsing:
    @pytest.mark.parametrize(
        ("body", "expected"),
        [
            ("volumeUuid, days: 30", {"volumeUuid", "days"}),
            ('bucket: "b", mode: s3Mode', {"bucket", "mode"}),
            ("...(retention ? { acknowledgeIrreversible: true } : {})", {"acknowledgeIrreversible"}),
            ("schedules: JSON.stringify([{ schedule: s, count: c }])", {"schedules"}),
        ],
    )
    def test_keys_are_read_from_object_literals(self, body, expected):
        keys, _ = _top_level_keys(body)
        assert keys == expected

    def test_a_computed_spread_is_opaque(self):
        _, opaque = _top_level_keys("...buildParams()")
        assert opaque

    def test_comments_are_blanked_not_removed(self):
        """A usage example in a doc comment is not a call site.

        The admin hook documents itself with `mutate("createVolume", {...})`, and
        reading that as a call reported the hook's own comment as broken code. Line
        numbers have to survive the blanking so real findings still point at source.
        """
        source = 'const a = 1;\n// mutate("createVolume", { name: "x" })\nconst b = 2;\n'
        blanked = _blank_comments(source)
        assert "createVolume" not in blanked
        assert blanked.count("\n") == source.count("\n")
        assert len(blanked) == len(source)

    def test_block_comments_are_blanked(self):
        source = 'a\n/* client.mutations.adminMutation({ action: "x" }) */\nb\n'
        blanked = _blank_comments(source)
        assert "adminMutation" not in blanked
        assert blanked.count("\n") == source.count("\n")

    def test_nested_braces_do_not_leak_keys(self):
        keys, _ = _top_level_keys("outer: { inner: 1 }, other: 2")
        assert keys == {"outer", "other"}


class TestHelpers:
    def test_module_string_constants(self):
        tree = ast.parse('A = "x"\nB = 3\nC = "y"\n')
        assert module_string_constants(tree) == {"A": "x", "C": "y"}

    def test_default_actions_ignores_empty_default(self):
        tree = ast.parse('def h(event):\n    action = event.get("action", "")\n')
        assert _default_actions(tree, {"event"}) == set()

    def test_contract_unsatisfied_is_group_wise(self):
        contract = ActionContract(handler="h", groups=[{"a"}, {"b", "c"}])
        assert contract.unsatisfied({"a", "b"}) == []
        assert [frozenset(g) for g in contract.unsatisfied({"a"})] == [frozenset({"b", "c"})]
