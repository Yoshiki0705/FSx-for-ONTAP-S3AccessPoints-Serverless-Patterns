"""Tests for the data platform inventory handler.

The behaviour worth pinning here is what happens when part of the answer is
unavailable. A discovery endpoint that fails closed takes the selector with it,
and a selector that cannot render leaves an operator with no way to change scope
at all -- which is worse than an inventory that is missing an entry and says so.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest
from platform_discovery_handler import _declarations, handler

from shared.storage_systems import PLATFORM_FSX_ONTAP, StorageSystem


@pytest.fixture
def one_platform() -> list[StorageSystem]:
    """A single discovered file system."""
    return [
        StorageSystem(
            platform=PLATFORM_FSX_ONTAP,
            system_id="fs-1",
            name="lab-primary",
            management_address="10.0.3.72",
            svms=("svm_a",),
            manageable=True,
            discovered_by="fsx-control-plane",
            resource_type="file system",
        )
    ]


class TestListDataPlatforms:
    """The inventory an operator selects from."""

    def test_returns_discovered_platforms(self, one_platform: list[StorageSystem]) -> None:
        with patch("platform_discovery_handler.discover_fsx_ontap", return_value=one_platform):
            result = handler({"action": "listDataPlatforms"}, None)
        assert result["error"] is None
        assert result["count"] == 1
        assert result["platforms"][0]["name"] == "lab-primary"
        assert result["platforms"][0]["svms"] == ["svm_a"]

    def test_does_not_publish_the_management_address(self, one_platform: list[StorageSystem]) -> None:
        """The browser has no use for it, and routing does not come from the browser."""
        with patch("platform_discovery_handler.discover_fsx_ontap", return_value=one_platform):
            result = handler({"action": "listDataPlatforms"}, None)
        assert "managementAddress" not in result["platforms"][0]
        assert "10.0.3.72" not in json.dumps(result)

    def test_a_failed_fsx_call_names_what_failed(self) -> None:
        """Not a bare error: the panel has to say which half is unavailable."""
        with patch(
            "platform_discovery_handler.discover_fsx_ontap",
            side_effect=RuntimeError("denied"),
        ):
            result = handler({"action": "listDataPlatforms"}, None)
        assert result["platforms"] == []
        assert "FSx inventory" in result["error"]
        assert "RuntimeError" in result["error"]

    def test_unknown_action_is_reported(self) -> None:
        assert "Unknown action" in handler({"action": "nope"}, None)["error"]

    def test_missing_action_is_reported(self) -> None:
        assert "Unknown action" in handler({}, None)["error"]


class TestDeclaredPlatforms:
    """A declaration is a claim, and stays hidden until something answers."""

    def _with_declared(self, value: str) -> list:
        with patch("platform_discovery_handler.DECLARED_PLATFORMS", value):
            return _declarations()

    def test_reads_a_declaration(self) -> None:
        declarations = self._with_declared(json.dumps([{"platform": "ONTAP_CLUSTER", "systemId": "c1", "name": "Lab"}]))
        assert [d.system_id for d in declarations] == ["c1"]

    @pytest.mark.parametrize(
        "value",
        ["", "   ", "not json", '{"platform": "X"}', "[1, 2, 3]"],
    )
    def test_unusable_configuration_is_no_declarations_rather_than_fatal(self, value: str) -> None:
        """FSx platforms are discovered and must not be lost to a typo here."""
        assert self._with_declared(value) == []

    def test_entries_without_an_identity_are_dropped(self) -> None:
        declarations = self._with_declared(
            json.dumps([{"platform": "ONTAP_CLUSTER"}, {"platform": "ONTAP_CLUSTER", "systemId": "c1"}])
        )
        assert [d.system_id for d in declarations] == ["c1"]

    def test_a_declared_platform_without_a_probe_is_hidden_with_a_reason(
        self, one_platform: list[StorageSystem]
    ) -> None:
        declared = json.dumps([{"platform": "ONTAP_CLUSTER", "systemId": "c1", "name": "Lab"}])
        with (
            patch("platform_discovery_handler.discover_fsx_ontap", return_value=one_platform),
            patch("platform_discovery_handler.DECLARED_PLATFORMS", declared),
        ):
            result = handler({"action": "listDataPlatforms"}, None)
        assert [p["systemId"] for p in result["platforms"]] == ["fs-1"]
        assert result["hidden"][0]["systemId"] == "c1"
        assert "No discovery method" in result["hidden"][0]["reason"]

    def test_no_probes_are_registered_yet(self) -> None:
        """Guards the claim in the module comment, so it cannot go stale silently."""
        import platform_discovery_handler as module

        assert module._PROBES == {}


class TestResponseShape:
    """What the selector reads."""

    def test_shape_is_stable_when_empty(self) -> None:
        with patch("platform_discovery_handler.discover_fsx_ontap", return_value=[]):
            result = handler({"action": "listDataPlatforms"}, None)
        assert result == {"platforms": [], "hidden": [], "count": 0, "error": None}

    def test_payload_is_json_serialisable(self, one_platform: list[StorageSystem]) -> None:
        """It crosses AppSync, so a tuple left in place would fail at the edge."""
        with patch("platform_discovery_handler.discover_fsx_ontap", return_value=one_platform):
            result: dict[str, Any] = handler({"action": "listDataPlatforms"}, None)
        assert json.loads(json.dumps(result))["platforms"][0]["platform"] == "FSX_ONTAP"
