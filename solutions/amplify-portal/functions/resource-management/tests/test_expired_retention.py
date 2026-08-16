"""Tests for listExpiredRetention, step one of expiry-driven deletion.

Deletion built on this enumeration is irreversible, so the properties pinned here
are the ones whose absence would delete the wrong thing: the clock it compares
against, the refusal to guess when that clock is unavailable, and reading both
snapshot expiry fields rather than one.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

MODULE_PATH = Path(__file__).resolve().parent.parent / "handler.py"

CLOCK = "2026-08-16T00:00:00+00:00"
PAST = "2026-08-15T00:00:00+00:00"
FUTURE = "2026-08-17T00:00:00+00:00"


def load() -> ModuleType:
    """Import handler.py fresh."""
    spec = importlib.util.spec_from_file_location("rm_expired_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["rm_expired_under_test"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def module() -> ModuleType:
    return load()


def _volume(name: str, uuid: str, snaplock: dict | None = None) -> dict:
    record: dict = {"name": name, "uuid": uuid}
    if snaplock is not None:
        record["snaplock"] = snaplock
    return record


def _run(module: ModuleType, volumes: list[dict], snapshots: dict[str, list[dict]]) -> dict:
    """Call the action with canned ONTAP responses, keyed by request path."""

    def fake_request(http: object, headers: object, verb: str, path: str, **kwargs: object) -> dict:
        if path.startswith("/storage/volumes?"):
            return {"records": volumes}
        for uuid, records in snapshots.items():
            if f"/storage/volumes/{uuid}/snapshots" in path:
                return {"records": records}
        return {"records": []}

    with patch.object(module, "_ontap_request", side_effect=fake_request):
        return module._list_expired_retention(MagicMock(), {}, {"svm": "svm1"})


def test_the_compliance_clock_is_reported_and_used(module: ModuleType) -> None:
    result = _run(
        module,
        [_volume("v1", "u1", {"type": "compliance", "compliance_clock_time": CLOCK, "expiry_time": PAST})],
        {"u1": []},
    )
    assert result["complianceClockTime"] == CLOCK
    assert result["clockSource"] == "ontap"
    assert [e["volumeName"] for e in result["expired"]] == ["v1"]
    assert result["pending"] == []


def test_a_future_expiry_is_pending_not_expired(module: ModuleType) -> None:
    result = _run(
        module,
        [_volume("v1", "u1", {"type": "compliance", "compliance_clock_time": CLOCK, "expiry_time": FUTURE})],
        {"u1": []},
    )
    assert result["expired"] == []
    assert [e["volumeName"] for e in result["pending"]] == ["v1"]


def test_without_a_compliance_clock_it_refuses_to_judge(module: ModuleType) -> None:
    # Falling back to wall time here is how an early deletion attempt gets built:
    # ONTAP measures retention on its own clock, and the two drift.
    result = _run(module, [_volume("v1", "u1")], {"u1": [{"name": "s", "uuid": "s1", "expiry_time": PAST}]})
    assert result["clockSource"] == "unavailable"
    assert result["expired"] == []
    assert result["pending"] == []
    assert "compliance clock" in result["error"]


def test_both_snapshot_expiry_fields_are_read(module: ModuleType) -> None:
    # `expiry_time` is the snapshot's own lock; `snaplock_expiry_time` comes from a
    # SnapLock volume. Reading one and not the other is what once made locked
    # snapshots look unlocked.
    result = _run(
        module,
        [_volume("v1", "u1", {"type": "compliance", "compliance_clock_time": CLOCK})],
        {
            "u1": [
                {"name": "own", "uuid": "s1", "expiry_time": PAST},
                {"name": "from_volume", "uuid": "s2", "snaplock_expiry_time": PAST},
                {"name": "unlocked", "uuid": "s3"},
            ]
        },
    )
    assert sorted(e["snapshotName"] for e in result["expired"]) == ["from_volume", "own"]


def test_an_unlocked_snapshot_is_not_listed(module: ModuleType) -> None:
    result = _run(
        module,
        [_volume("v1", "u1", {"type": "compliance", "compliance_clock_time": CLOCK})],
        {"u1": [{"name": "plain", "uuid": "s1"}]},
    )
    assert result["expired"] == []
    assert result["pending"] == []


def test_a_non_snaplock_volume_is_not_listed_as_a_volume(module: ModuleType) -> None:
    # It can still hold locked snapshots, which are reported separately.
    result = _run(
        module,
        [
            _volume("locked", "u1", {"type": "compliance", "compliance_clock_time": CLOCK, "expiry_time": PAST}),
            _volume("plain", "u2", {"type": "non_snaplock"}),
        ],
        {"u1": [], "u2": [{"name": "s", "uuid": "s9", "expiry_time": PAST}]},
    )
    volumes = [e for e in result["expired"] if e["resourceType"] == "volume"]
    snapshots = [e for e in result["expired"] if e["resourceType"] == "snapshot"]
    assert [v["volumeName"] for v in volumes] == ["locked"]
    assert [s["volumeName"] for s in snapshots] == ["plain"]


def test_a_failed_volume_listing_is_an_error_not_an_empty_answer(module: ModuleType) -> None:
    with patch.object(module, "_ontap_request", return_value={"_error": True, "_message": "unreachable"}):
        result = module._list_expired_retention(MagicMock(), {}, {})
    assert result["error"] == "unreachable"
    assert result["complianceClockTime"] is None


def test_the_action_is_reachable_through_the_handler(module: ModuleType) -> None:
    # A helper nothing dispatches to is a helper that silently does not exist.
    source = MODULE_PATH.read_text()
    assert 'action == "listExpiredRetention"' in source
    assert "_list_expired_retention(http, headers, event)" in source
