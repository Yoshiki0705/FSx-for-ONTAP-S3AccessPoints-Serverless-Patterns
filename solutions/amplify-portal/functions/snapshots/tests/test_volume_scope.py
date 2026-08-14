"""Tests for which volume the data-protection handler acts on.

Every action in this function read `VOLUME_NAME` from the environment, so the whole
data-protection area could only ever describe one volume. The ARP page showed the name as
a fixed badge with no way to change it, which made protection turned on anywhere else
indistinguishable from protection that had not taken effect -- the report that led here.

The volume is now a request parameter that falls back to the environment, so these pin
both halves: the fallback still works for a caller that names nothing (a reader without
the storage-admin group), and a named volume actually reaches ONTAP's query.

`lockSnapshot` is covered for the same reason it is never exercised against hardware: a
lock cannot be undone, so a lock applied to a snapshot of the wrong volume is permanent.
The parameter has to reach it, and only a test can say so here.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

MODULE_PATH = Path(__file__).resolve().parent.parent / "index.py"
CONFIGURED = "vol_configured"
OTHER = "vol_other"


def load_module() -> Any:
    """Import index.py fresh: its constants are read at import time."""
    env = {
        "ONTAP_MGMT_IP": "10.0.0.1",
        "ONTAP_SECRET_NAME": "test/secret",
        "VOLUME_NAME": CONFIGURED,
        "SVM_NAME": "svm1",
    }
    with patch.dict(os.environ, env, clear=False):
        spec = importlib.util.spec_from_file_location("snapshots_volume_scope", MODULE_PATH)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules["snapshots_volume_scope"] = module
        spec.loader.exec_module(module)
    return module


class Response:
    def __init__(self, payload: dict, status: int = 200) -> None:
        self.status = status
        self.data = json.dumps(payload).encode()


@pytest.fixture
def protection(monkeypatch: pytest.MonkeyPatch) -> Any:
    """The handler with credentials stubbed and every ONTAP call recorded."""
    module = load_module()

    calls: list[tuple[str, str]] = []
    # Locking off is the ordinary case and the one the lock path checks first. The lock
    # test turns it on, because otherwise the handler refuses before it reaches the PATCH
    # and the test would pass without exercising what it names.
    state = {"snapshot_locking_enabled": False}

    class Pool:
        def request(self, method: str, url: str, **kwargs: Any) -> Response:
            calls.append((method, url))
            if "/storage/volumes" in url and "snapshots" not in url:
                return Response(
                    {
                        "records": [
                            {
                                "uuid": "v-uuid",
                                "anti_ransomware": {"state": "enabled", "attack_probability": "none"},
                                "snaplock": {"type": "non_snaplock"},
                                "snapshot_locking_enabled": state["snapshot_locking_enabled"],
                            }
                        ]
                    }
                )
            return Response({"records": []})

    monkeypatch.setattr(module, "get_credentials", lambda: ("fsxadmin", "pw"))
    monkeypatch.setattr(module.urllib3, "PoolManager", lambda **kwargs: Pool())
    module._calls = calls
    module._state = state
    return module


def test_the_configured_volume_is_the_default(protection: Any) -> None:
    """A caller that names no volume still gets the one the deployment configured."""
    result = protection.handler({"action": "getArpStatus"}, None)

    assert result["volumeName"] == CONFIGURED
    assert f"name={CONFIGURED}" in protection._calls[0][1]


def test_a_named_volume_reaches_the_query(protection: Any) -> None:
    """The report this fixes: the page could not ask about any other volume."""
    result = protection.handler({"action": "getArpStatus", "volumeName": OTHER}, None)

    assert result["volumeName"] == OTHER
    assert f"name={OTHER}" in protection._calls[0][1]
    assert CONFIGURED not in protection._calls[0][1]


def test_an_empty_volume_name_falls_back_rather_than_querying_nothing(protection: Any) -> None:
    """`params: {}` from the client arrives as an absent key or an empty string."""
    result = protection.handler({"action": "getArpStatus", "volumeName": ""}, None)

    assert result["volumeName"] == CONFIGURED


def test_the_name_is_encoded_into_the_query(protection: Any) -> None:
    """The name now comes from the client, so it cannot be allowed to add parameters."""
    protection.handler({"action": "getArpStatus", "volumeName": "a&svm.name=elsewhere"}, None)

    url = protection._calls[0][1]
    assert "a%26svm.name%3Delsewhere" in url
    # One `svm.name=` only: the injected one did not survive.
    assert url.count("svm.name=") == 1


def test_snaplock_status_follows_the_same_volume(protection: Any) -> None:
    result = protection.handler({"action": "getSnaplockStatus", "volumeName": OTHER}, None)

    assert result["volumeName"] == OTHER
    assert f"name={OTHER}" in protection._calls[0][1]


def test_the_snapshot_listing_follows_the_same_volume(protection: Any) -> None:
    """Otherwise the listing and the panel's header would describe different volumes."""
    result = protection.handler({"action": "listSnapshots", "volumeName": OTHER}, None)

    assert result["volumeName"] == OTHER
    assert f"name={OTHER}" in protection._calls[0][1]


def test_locking_resolves_the_named_volume(protection: Any) -> None:
    """A lock is irreversible, so the subject it resolves must be the one on screen."""
    protection._state["snapshot_locking_enabled"] = True
    protection.handler(
        {
            "action": "lockSnapshot",
            "volumeName": OTHER,
            "snapshotId": "snap-uuid",
            "expiryTime": "2027-01-01T00:00:00Z",
            "acknowledgeIrreversible": True,
        },
        None,
    )

    # The volume lookup that precedes the lock names the volume that was asked for.
    assert f"name={OTHER}" in protection._calls[0][1]
    # And the lock itself is issued against the UUID that lookup returned, not against
    # a UUID resolved from the configured volume.
    assert any(method == "PATCH" and "/volumes/v-uuid/snapshots/" in url for method, url in protection._calls)


def test_locking_is_refused_when_the_volume_does_not_allow_it(protection: Any) -> None:
    """The refusal has to come from the named volume's record, not the configured one."""
    protection._state["snapshot_locking_enabled"] = False

    result = protection.handler(
        {
            "action": "lockSnapshot",
            "volumeName": OTHER,
            "snapshotId": "snap-uuid",
            "expiryTime": "2027-01-01T00:00:00Z",
            "acknowledgeIrreversible": True,
        },
        None,
    )

    assert result["success"] is False
    assert "not enabled" in result["error"]
    assert not any(method == "PATCH" for method, _ in protection._calls)


def test_a_missing_configuration_still_reports_which_volume_was_meant(
    protection: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The not-configured response is a reader's first screen; it should name the subject."""
    monkeypatch.setattr(protection, "ONTAP_MGMT_IP", "")

    result = protection.handler({"action": "getArpStatus", "volumeName": OTHER}, None)

    assert result["volumeName"] == OTHER
    assert "ONTAP_MGMT_IP" in json.dumps(result)


def test_boto3_is_not_reached_when_the_configuration_is_missing(
    protection: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing variable must fail before the credential fetch, not through it."""
    monkeypatch.setattr(protection, "SECRET_NAME", "")
    sm = MagicMock()
    monkeypatch.setattr(protection, "get_credentials", sm)

    protection.handler({"action": "getArpStatus"}, None)

    sm.assert_not_called()
