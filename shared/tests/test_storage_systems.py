"""Tests for the storage system inventory.

The rule under test throughout is that a declaration is not an entry: something
has to answer for it first. Every case here is about what an operator is allowed
to select, because selecting a system the actions cannot use is the failure this
layer exists to prevent.
"""

from __future__ import annotations

from typing import Any

import pytest

from shared.storage_systems import (
    ONTAP_REST_PLATFORMS,
    PLATFORM_FSX_ONTAP,
    PLATFORM_ONTAP_CLUSTER,
    Declaration,
    DiscoveryScope,
    Inventory,
    StorageSystem,
    build_inventory,
    discover_fsx_ontap,
    discover_fsx_ontap_across,
    group_svms_by_file_system,
    probe_declared,
)


class FakePaginator:
    """Returns prepared pages, so pagination is exercised rather than assumed."""

    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self._pages = pages

    def paginate(self) -> list[dict[str, Any]]:
        return self._pages


class FakeFsx:
    """A boto3 FSx client stand-in with two paginated operations."""

    def __init__(
        self,
        file_systems: list[dict[str, Any]],
        svms: list[dict[str, Any]],
        *,
        split: bool = False,
    ) -> None:
        self._pages = {
            "describe_file_systems": (
                [{"FileSystems": file_systems[:1]}, {"FileSystems": file_systems[1:]}]
                if split and len(file_systems) > 1
                else [{"FileSystems": file_systems}]
            ),
            "describe_storage_virtual_machines": [{"StorageVirtualMachines": svms}],
        }

    def get_paginator(self, name: str) -> FakePaginator:
        return FakePaginator(self._pages[name])


def fsx_record(
    file_system_id: str,
    *,
    name: str | None = None,
    address: str = "10.0.3.72",
    lifecycle: str = "AVAILABLE",
    file_system_type: str = "ONTAP",
) -> dict[str, Any]:
    """Build a describe_file_systems record."""
    record: dict[str, Any] = {
        "FileSystemId": file_system_id,
        "FileSystemType": file_system_type,
        "Lifecycle": lifecycle,
        "OntapConfiguration": {"Endpoints": {"Management": {"IpAddresses": [address]}}},
    }
    if name is not None:
        record["Tags"] = [{"Key": "Name", "Value": name}]
    return record


def svm_record(file_system_id: str, name: str, lifecycle: str = "CREATED") -> dict[str, Any]:
    """Build a describe_storage_virtual_machines record."""
    return {"FileSystemId": file_system_id, "Name": name, "Lifecycle": lifecycle}


class TestGroupSvms:
    """Grouping is what makes the SVM list a property of one system."""

    def test_groups_by_file_system_and_sorts(self) -> None:
        grouped = group_svms_by_file_system(
            [svm_record("fs-1", "svm_b"), svm_record("fs-2", "other"), svm_record("fs-1", "svm_a")]
        )
        assert grouped == {"fs-1": ("svm_a", "svm_b"), "fs-2": ("other",)}

    def test_excludes_svms_that_cannot_serve(self) -> None:
        """A transitioning SVM offered as a scope answers with an empty list."""
        grouped = group_svms_by_file_system(
            [svm_record("fs-1", "ready"), svm_record("fs-1", "half", lifecycle="CREATING")]
        )
        assert grouped == {"fs-1": ("ready",)}

    def test_records_without_identity_are_dropped(self) -> None:
        assert group_svms_by_file_system([{"Name": "no-fs"}, {"FileSystemId": "fs-1"}]) == {}

    def test_no_records_is_no_groups(self) -> None:
        assert group_svms_by_file_system([]) == {}


class TestDiscoverFsxOntap:
    """What the control plane reports, and what it is allowed to omit."""

    def test_reports_name_tag_rather_than_the_id(self) -> None:
        """The ID is not what anyone calls the system when talking about it."""
        client = FakeFsx([fsx_record("fs-1", name="lab-primary")], [])
        (system,) = discover_fsx_ontap(client)
        assert system.name == "lab-primary"
        assert system.system_id == "fs-1"

    def test_falls_back_to_the_id_when_untagged(self) -> None:
        client = FakeFsx([fsx_record("fs-1")], [])
        (system,) = discover_fsx_ontap(client)
        assert system.name == "fs-1"

    def test_attaches_the_svms_of_that_system_only(self) -> None:
        client = FakeFsx(
            [fsx_record("fs-1", name="one"), fsx_record("fs-2", name="two")],
            [svm_record("fs-1", "svm_a"), svm_record("fs-2", "svm_b")],
        )
        by_id = {s.system_id: s for s in discover_fsx_ontap(client)}
        assert by_id["fs-1"].svms == ("svm_a",)
        assert by_id["fs-2"].svms == ("svm_b",)

    def test_skips_file_systems_that_are_not_available(self) -> None:
        """Its management interface is not answering, so it is not a scope."""
        client = FakeFsx([fsx_record("fs-1", lifecycle="CREATING")], [])
        assert discover_fsx_ontap(client) == []

    def test_skips_other_file_system_types(self) -> None:
        client = FakeFsx([fsx_record("fs-1", file_system_type="WINDOWS")], [])
        assert discover_fsx_ontap(client) == []

    def test_reads_every_page(self) -> None:
        client = FakeFsx([fsx_record("fs-1", name="a"), fsx_record("fs-2", name="b")], [], split=True)
        assert len(discover_fsx_ontap(client)) == 2

    def test_missing_management_address_is_empty_not_an_error(self) -> None:
        record = fsx_record("fs-1")
        record["OntapConfiguration"] = {}
        (system,) = discover_fsx_ontap(FakeFsx([record], []))
        assert system.management_address == ""

    def test_discovered_systems_are_manageable_and_say_how_they_were_found(self) -> None:
        (system,) = discover_fsx_ontap(FakeFsx([fsx_record("fs-1")], []))
        assert system.manageable is True
        assert system.discovered_by == "fsx-control-plane"
        assert system.platform == PLATFORM_FSX_ONTAP


class TestProbeDeclared:
    """A declaration becomes an entry only when something answers for it."""

    def _declaration(self, platform: str = PLATFORM_ONTAP_CLUSTER) -> Declaration:
        return Declaration(platform=platform, system_id="cluster-1", name="On-prem")

    def test_a_system_that_answers_is_listed(self) -> None:
        declaration = self._declaration()
        found = StorageSystem(
            platform=declaration.platform,
            system_id=declaration.system_id,
            name=declaration.name,
            manageable=True,
            discovered_by="probe",
        )
        inventory = probe_declared([declaration], {declaration.platform: lambda _d: found})
        assert inventory.systems == [found]
        assert inventory.hidden == []

    def test_a_system_that_does_not_answer_is_hidden_with_a_reason(self) -> None:
        declaration = self._declaration()
        inventory = probe_declared([declaration], {declaration.platform: lambda _d: None})
        assert inventory.systems == []
        assert inventory.hidden[0]["systemId"] == "cluster-1"
        assert "answer" in inventory.hidden[0]["reason"]

    def test_a_platform_without_a_probe_stays_hidden(self) -> None:
        """Not an error: this build cannot confirm it, so it is not offered."""
        inventory = probe_declared([self._declaration(platform="SOME_PLATFORM")], {})
        assert inventory.systems == []
        assert "No discovery method" in inventory.hidden[0]["reason"]

    def test_a_raising_probe_is_hidden_rather_than_fatal(self) -> None:
        """One unreachable system must not empty the inventory of the others."""
        declaration = self._declaration()

        def explode(_d: Declaration) -> StorageSystem | None:
            raise TimeoutError("no route")

        inventory = probe_declared([declaration], {declaration.platform: explode})
        assert inventory.systems == []
        assert inventory.hidden[0]["reason"] == "Discovery failed: TimeoutError"

    def test_probes_are_selected_per_platform(self) -> None:
        answered = StorageSystem(platform=PLATFORM_ONTAP_CLUSTER, system_id="b", name="b", manageable=True)
        inventory = probe_declared(
            [
                Declaration(platform="OTHER", system_id="a"),
                Declaration(platform=PLATFORM_ONTAP_CLUSTER, system_id="b"),
            ],
            {PLATFORM_ONTAP_CLUSTER: lambda _d: answered},
        )
        assert [s.system_id for s in inventory.systems] == ["b"]
        assert [h["systemId"] for h in inventory.hidden] == ["a"]


class TestDeclarationFromDict:
    """Configuration is read leniently, except where it cannot be identified."""

    def test_reads_camel_case(self) -> None:
        declaration = Declaration.from_dict(
            {
                "platform": PLATFORM_ONTAP_CLUSTER,
                "systemId": "c1",
                "name": "Lab",
                "resourceType": "cluster",
                "managementAddress": "192.0.2.10",
                "secretName": "lab/creds",
            }
        )
        assert declaration is not None
        assert declaration.management_address == "192.0.2.10"
        assert declaration.secret_name == "lab/creds"
        assert declaration.resource_type == "cluster"

    def test_reads_snake_case(self) -> None:
        declaration = Declaration.from_dict({"platform": "P", "system_id": "c1", "management_address": "192.0.2.10"})
        assert declaration is not None
        assert declaration.management_address == "192.0.2.10"

    def test_name_defaults_to_the_identifier(self) -> None:
        declaration = Declaration.from_dict({"platform": "P", "systemId": "c1"})
        assert declaration is not None
        assert declaration.name == "c1"

    @pytest.mark.parametrize(
        "raw",
        [
            {"systemId": "c1"},
            {"platform": "P"},
            {"platform": "", "systemId": "c1"},
            {},
        ],
    )
    def test_unidentifiable_declarations_are_dropped(self, raw: dict[str, Any]) -> None:
        """Half an entry fails later for a reason unrelated to the system."""
        assert Declaration.from_dict(raw) is None


class TestBuildInventory:
    """Discovery wins over declaration for the same system."""

    def test_declared_systems_are_appended(self) -> None:
        discovered = [StorageSystem(platform=PLATFORM_FSX_ONTAP, system_id="fs-1", name="a")]
        declared = Inventory(systems=[StorageSystem(platform=PLATFORM_ONTAP_CLUSTER, system_id="c1", name="b")])
        merged = build_inventory(discovered, declared)
        assert [s.system_id for s in merged.systems] == ["fs-1", "c1"]

    def test_a_declaration_does_not_replace_a_discovered_system(self) -> None:
        """The discovered entry was read from the resource, not typed."""
        discovered = [
            StorageSystem(
                platform=PLATFORM_FSX_ONTAP,
                system_id="fs-1",
                name="from-control-plane",
                discovered_by="fsx-control-plane",
            )
        ]
        declared = Inventory(
            systems=[StorageSystem(platform=PLATFORM_FSX_ONTAP, system_id="fs-1", name="typed-by-hand")]
        )
        merged = build_inventory(discovered, declared)
        assert [s.name for s in merged.systems] == ["from-control-plane"]

    def test_hidden_entries_are_carried_through(self) -> None:
        declared = Inventory(hidden=[{"systemId": "c1", "platform": "P", "reason": "nope"}])
        assert build_inventory([], declared).hidden == [{"systemId": "c1", "platform": "P", "reason": "nope"}]

    def test_no_declarations_is_just_discovery(self) -> None:
        discovered = [StorageSystem(platform=PLATFORM_FSX_ONTAP, system_id="fs-1", name="a")]
        merged = build_inventory(discovered)
        assert merged.systems == discovered
        assert merged.hidden == []


class TestSerialisation:
    """The response shape the portal reads."""

    def test_system_as_dict_uses_camel_case(self) -> None:
        system = StorageSystem(
            platform=PLATFORM_FSX_ONTAP,
            system_id="fs-1",
            name="a",
            management_address="10.0.3.72",
            svms=("svm_a",),
            manageable=True,
            discovered_by="fsx-control-plane",
            resource_type="file system",
        )
        assert system.as_dict() == {
            "platform": "FSX_ONTAP",
            "systemId": "fs-1",
            "name": "a",
            "managementAddress": "10.0.3.72",
            "svms": ["svm_a"],
            "manageable": True,
            "discoveredBy": "fsx-control-plane",
            "resourceType": "file system",
            "connected": False,
            "account": "",
            "region": "",
        }

    def test_public_dict_omits_the_management_address(self) -> None:
        """The browser routes nothing, so it is told no endpoints."""
        system = StorageSystem(
            platform=PLATFORM_FSX_ONTAP,
            system_id="fs-1",
            name="a",
            management_address="10.0.3.72",
        )
        public = system.as_public_dict()
        assert "managementAddress" not in public
        assert public["systemId"] == "fs-1"

    def test_connected_is_false_until_something_says_otherwise(self) -> None:
        """A wrong mark is worse than no mark: it misstates what actions apply to."""
        assert StorageSystem(platform=PLATFORM_FSX_ONTAP, system_id="fs-1", name="a").connected is False

    def test_inventory_key_is_platforms(self) -> None:
        """The portal's term for the unit, whatever sits underneath it."""
        inventory = Inventory(systems=[StorageSystem(platform=PLATFORM_FSX_ONTAP, system_id="fs-1", name="a")])
        assert "platforms" in inventory.as_dict()
        assert "systems" not in inventory.as_dict()

    def test_inventory_count_counts_selectable_systems_only(self) -> None:
        inventory = Inventory(
            systems=[StorageSystem(platform=PLATFORM_FSX_ONTAP, system_id="fs-1", name="a")],
            hidden=[{"systemId": "c1", "platform": "P", "reason": "nope"}],
        )
        assert inventory.as_dict()["count"] == 1


class TestDiscoverAcrossScopes:
    """One unreachable account must not empty the inventory."""

    def _factory(self, clients: dict[tuple[str, str], Any]):
        def build(scope: DiscoveryScope) -> Any:
            key = (scope.account, scope.region)
            if key not in clients:
                raise PermissionError(f"cannot assume into {scope.label()}")
            return clients[key]

        return build

    def test_records_the_account_and_region_on_each_result(self) -> None:
        """A name is only unique within an account, so both travel with it."""
        scope = DiscoveryScope(region="us-east-1", account="111122223333", role_name="Reader")
        inventory = discover_fsx_ontap_across(
            [scope],
            self._factory({("111122223333", "us-east-1"): FakeFsx([fsx_record("fs-1")], [])}),
        )
        assert inventory.systems[0].account == "111122223333"
        assert inventory.systems[0].region == "us-east-1"

    def test_a_failed_scope_is_reported_and_the_others_still_answer(self) -> None:
        good = DiscoveryScope(region="ap-northeast-1")
        bad = DiscoveryScope(region="us-east-1", account="111122223333", role_name="Reader")
        inventory = discover_fsx_ontap_across(
            [good, bad], self._factory({("", "ap-northeast-1"): FakeFsx([fsx_record("fs-1")], [])})
        )
        assert [s.system_id for s in inventory.systems] == ["fs-1"]
        assert inventory.hidden[0]["systemId"] == "111122223333/us-east-1"
        assert "PermissionError" in inventory.hidden[0]["reason"]

    def test_every_scope_failing_is_an_empty_inventory_with_reasons(self) -> None:
        """Not an exception: the panel has to render something and say why."""
        inventory = discover_fsx_ontap_across(
            [DiscoveryScope(region="us-east-1"), DiscoveryScope(region="eu-west-1")],
            self._factory({}),
        )
        assert inventory.systems == []
        assert len(inventory.hidden) == 2

    def test_duplicate_scopes_are_read_once(self) -> None:
        calls: list[str] = []

        def build(scope: DiscoveryScope) -> Any:
            calls.append(scope.region)
            return FakeFsx([fsx_record("fs-1")], [])

        inventory = discover_fsx_ontap_across(
            [DiscoveryScope(region="us-east-1"), DiscoveryScope(region="us-east-1")], build
        )
        assert calls == ["us-east-1"]
        assert len(inventory.systems) == 1

    def test_overlapping_scopes_do_not_duplicate_a_file_system(self) -> None:
        """A file system ID is globally unique, so a repeat means overlap."""
        client = FakeFsx([fsx_record("fs-1")], [])
        inventory = discover_fsx_ontap_across(
            [DiscoveryScope(region="us-east-1"), DiscoveryScope(region="eu-west-1")],
            lambda _s: client,
        )
        assert [s.system_id for s in inventory.systems] == ["fs-1"]

    def test_results_are_sorted_across_scopes(self) -> None:
        inventory = discover_fsx_ontap_across(
            [DiscoveryScope(region="r1"), DiscoveryScope(region="r2")],
            self._factory(
                {
                    ("", "r1"): FakeFsx([fsx_record("fs-2", name="zeta")], []),
                    ("", "r2"): FakeFsx([fsx_record("fs-1", name="alpha")], []),
                }
            ),
        )
        assert [s.name for s in inventory.systems] == ["alpha", "zeta"]

    def test_scope_label_names_the_local_account_readably(self) -> None:
        assert DiscoveryScope(region="us-east-1").label() == "this account/us-east-1"
        assert DiscoveryScope(region="us-east-1", account="1").label() == "1/us-east-1"


class TestPlatformConstants:
    """Which platforms the ONTAP actions can address."""

    def test_ontap_rest_platforms_are_the_ontap_ones(self) -> None:
        assert ONTAP_REST_PLATFORMS == {PLATFORM_FSX_ONTAP, PLATFORM_ONTAP_CLUSTER}

    def test_cloud_and_on_premises_ontap_share_one_platform(self) -> None:
        """Where a cluster runs is not a difference the portal acts on."""
        assert PLATFORM_ONTAP_CLUSTER not in {PLATFORM_FSX_ONTAP}
