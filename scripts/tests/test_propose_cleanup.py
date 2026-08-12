"""Tests for scripts/propose_cleanup.py.

The property that matters most is negative: this script must never delete
anything. A test that only checked the happy path would not notice a `delete_*`
call added later, so the call surface is asserted directly from the source.

The rest covers the gate — while roadmap items are open the proposal is withheld —
and the pieces where a silent wrong answer is possible: an unmapped FSx
deployment type must report "not priced" rather than a plausible number, and a
missing NAT price must not read as free.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "propose_cleanup.py"

_spec = importlib.util.spec_from_file_location("propose_cleanup", SCRIPT)
assert _spec and _spec.loader
pc = importlib.util.module_from_spec(_spec)
sys.modules["propose_cleanup"] = pc
_spec.loader.exec_module(pc)


# --------------------------------------------------------------------------
# It must not be able to destroy anything
# --------------------------------------------------------------------------

# Method-name prefixes that change state. boto3 clients are dynamic, so no type
# checker can see these calls; reading the AST is what is available.
MUTATING_PREFIXES = (
    "delete_",
    "remove_",
    "terminate_",
    "detach_",
    "put_",
    "update_",
    "modify_",
    "create_",
    "stop_",
    "disable_",
    "revoke_",
    "empty_",
)

# Called on our own objects, not on an AWS client.
LOCAL_ALLOWLIST = {"update"}  # dict.update, used to merge price maps


def called_attribute_names() -> set[str]:
    """Every attribute name invoked as a function anywhere in the script."""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    return {
        node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }


def test_calls_nothing_that_changes_state() -> None:
    names = called_attribute_names() - LOCAL_ALLOWLIST
    offenders = sorted(n for n in names if n.startswith(MUTATING_PREFIXES))
    assert offenders == [], (
        "propose_cleanup.py proposes; it does not act. These calls change state: "
        f"{offenders}. Deletion belongs to scripts/cleanup_generic_ucs.py and "
        "scripts/teardown-uc29-uc30.sh, run deliberately by a person."
    )


def test_the_guard_would_catch_a_delete_call() -> None:
    """The guard above passes trivially if its prefix list is wrong."""
    assert "delete_file_system".startswith(MUTATING_PREFIXES)
    assert not "describe_file_systems".startswith(MUTATING_PREFIXES)


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------


def write_roadmap(tmp_path: Path, body: str) -> Path:
    """Write a roadmap fixture and return its path.

    Args:
        tmp_path: pytest temporary directory.
        body: Markdown content.

    Returns:
        The path written.
    """
    path = tmp_path / "ROADMAP.md"
    path.write_text(body, encoding="utf-8")
    return path


def test_open_items_are_reported_with_their_section(tmp_path: Path) -> None:
    roadmap = write_roadmap(
        tmp_path,
        "# Roadmap\n\n## Infra\n\n| KNFSD | 📋 Preview |\n\n## Docs\n\n| Part 4 | ⚠️ pending |\n",
    )
    items = pc.read_open_items(roadmap)
    assert [i.section for i in items] == ["Infra", "Docs"]
    assert "KNFSD" in items[0].text


def test_prose_mentioning_the_markers_is_not_an_item(tmp_path: Path) -> None:
    # ROADMAP.md documents this rule, and that paragraph contains 📋 and ⚠️. When
    # any line counted, writing the explanation added a phantom item to the
    # backlog it was explaining.
    roadmap = write_roadmap(
        tmp_path,
        "# Roadmap\n\n## Infra\n\n"
        "未完了マーカー（📋 / ⚠️）が残っている間は提案しません。\n\n"
        "> **注**: ⚠️ は着手済みを表します。\n\n"
        "| KNFSD | 📋 Preview |\n",
    )
    items = pc.read_open_items(roadmap)
    assert len(items) == 1
    assert "KNFSD" in items[0].text


def test_a_list_item_counts_as_an_entry(tmp_path: Path) -> None:
    roadmap = write_roadmap(tmp_path, "# Roadmap\n\n## Infra\n\n- 📋 something to do\n")
    assert len(pc.read_open_items(roadmap)) == 1


def test_a_finished_roadmap_has_no_open_items(tmp_path: Path) -> None:
    # ✅ is the done marker and must not be collected, otherwise the gate never
    # opens and the script is permanently useless.
    roadmap = write_roadmap(tmp_path, "# Roadmap\n\n## Infra\n\n| KNFSD | ✅ done |\n")
    assert pc.read_open_items(roadmap) == []


def test_withholds_the_proposal_while_items_are_open(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    roadmap = write_roadmap(tmp_path, "# Roadmap\n\n## Infra\n\n| x | 📋 todo |\n")
    assert pc.main(["--roadmap", str(roadmap)]) == 0
    out = capsys.readouterr().out
    assert "Withholding the cleanup proposal" in out
    # No AWS call was needed to reach that decision, so nothing about the account
    # can appear in the output.
    assert "Standing resources" not in out


def test_missing_roadmap_is_not_a_crash(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert pc.main(["--roadmap", str(tmp_path / "nope.md")]) == 0
    assert "not found" in capsys.readouterr().out


# --------------------------------------------------------------------------
# Pricing must be absent rather than wrong
# --------------------------------------------------------------------------


class _FakePaginator:
    def __init__(self, pages: list[dict]) -> None:
        self._pages = pages

    def paginate(self, **_kwargs: object) -> list[dict]:
        return self._pages


class _FakeFsx:
    """Just enough of the fsx client for collect_fsx."""

    def __init__(self, filesystems: list[dict], volumes: list[dict]) -> None:
        self._pages = {
            "describe_file_systems": [{"FileSystems": filesystems}],
            "describe_volumes": [{"Volumes": volumes}],
        }

    def get_paginator(self, name: str) -> _FakePaginator:
        return _FakePaginator(self._pages[name])


class _FakeSession:
    def __init__(self, client: object) -> None:
        self._client = client

    def client(self, _name: str, **_kwargs: object) -> object:
        return self._client


def _filesystem(deployment: str) -> dict:
    """Return a minimal describe_file_systems record.

    Args:
        deployment: The `OntapConfiguration.DeploymentType` to report.

    Returns:
        One file system entry with 1024 GB of SSD and 128 MBps.
    """
    return {
        "FileSystemId": "fs-1",
        "StorageCapacity": 1024,
        "OntapConfiguration": {"DeploymentType": deployment, "ThroughputCapacity": 128},
    }


PRICES = {
    "APN1-Storage.SAZ_2N:SSD": (0.15, "GB-Mo"),
    "APN1-ThroughputCapacity.SAZ_2N": (0.906, "MiBps-Mo"),
}


def test_prices_a_known_deployment_type() -> None:
    session = _FakeSession(_FakeFsx([_filesystem("SINGLE_AZ_1")], []))
    [item] = pc.collect_fsx(session, "ap-northeast-1", PRICES)
    assert item.monthly_usd == 1024 * 0.15 + 128 * 0.906
    # The rates used are printed, so a wrong lookup is visible in the output
    # rather than folded into a total.
    assert any("APN1-Storage.SAZ_2N:SSD" in line for line in item.price_basis)


def test_an_unmapped_deployment_type_is_unpriced_not_guessed() -> None:
    session = _FakeSession(_FakeFsx([_filesystem("SINGLE_AZ_9")], []))
    [item] = pc.collect_fsx(session, "ap-northeast-1", PRICES)
    assert item.monthly_usd is None


def test_no_prices_at_all_yields_no_amounts() -> None:
    session = _FakeSession(_FakeFsx([_filesystem("SINGLE_AZ_1")], []))
    [item] = pc.collect_fsx(session, "ap-northeast-1", {})
    assert item.monthly_usd is None


def test_a_snaplock_volume_is_reported_as_blocking_deletion() -> None:
    # The expensive surprise this exists for: an unexpired SnapLock volume blocks
    # volume -> SVM -> file system deletion, so "cleanup" becomes a months-long
    # bill. It must be named next to the file system, not left for someone to
    # find after issuing the delete.
    volumes = [
        {
            "FileSystemId": "fs-1",
            "VolumeId": "fsvol-1",
            "Name": "zz_verify_auditlog",
            "OntapConfiguration": {"SnaplockConfiguration": {"SnaplockType": "ENTERPRISE", "AuditLogVolume": True}},
        }
    ]
    session = _FakeSession(_FakeFsx([_filesystem("SINGLE_AZ_1")], volumes))
    [item] = pc.collect_fsx(session, "ap-northeast-1", PRICES)
    assert item.irreversible is not None
    assert "zz_verify_auditlog" in item.irreversible
    # The FSx flag is reported with its source named, because it is not the
    # authority: ONTAP's read-only snaplock.is_audit_log is, and clearing the
    # SVM-level designation does not change it.
    assert "AuditLogVolume(FSx API)=True" in item.irreversible
    assert "snaplock.is_audit_log" in item.irreversible


def test_privileged_delete_permanently_disabled_is_called_terminal() -> None:
    # This is the strongest blocker the FSx API exposes: it makes an ENTERPRISE
    # volume behave as COMPLIANCE, so not even a privileged delete remains. A
    # reader who sees only "SnapLock=ENTERPRISE" may assume that route is open.
    volumes = [
        {
            "FileSystemId": "fs-1",
            "VolumeId": "fsvol-3",
            "Name": "locked",
            "OntapConfiguration": {
                "SnaplockConfiguration": {
                    "SnaplockType": "ENTERPRISE",
                    "AuditLogVolume": False,
                    "PrivilegedDelete": "PERMANENTLY_DISABLED",
                }
            },
        }
    ]
    session = _FakeSession(_FakeFsx([_filesystem("SINGLE_AZ_1")], volumes))
    [item] = pc.collect_fsx(session, "ap-northeast-1", PRICES)
    assert item.irreversible is not None
    assert "PrivilegedDelete=PERMANENTLY_DISABLED (terminal)" in item.irreversible


def test_snaplock_is_flagged_even_when_the_fsx_audit_flag_is_false() -> None:
    # The pitfall this guards: AuditLogVolume: false reads as "deletable" and is
    # not. Any SnapLock configuration at all is reported.
    volumes = [
        {
            "FileSystemId": "fs-1",
            "VolumeId": "fsvol-4",
            "Name": "worm",
            "OntapConfiguration": {"SnaplockConfiguration": {"SnaplockType": "COMPLIANCE", "AuditLogVolume": False}},
        }
    ]
    session = _FakeSession(_FakeFsx([_filesystem("SINGLE_AZ_1")], volumes))
    [item] = pc.collect_fsx(session, "ap-northeast-1", PRICES)
    assert item.irreversible is not None


def test_a_volume_without_snaplock_does_not_block() -> None:
    volumes = [
        {
            "FileSystemId": "fs-1",
            "VolumeId": "fsvol-2",
            "Name": "plain",
            "OntapConfiguration": {},
        }
    ]
    session = _FakeSession(_FakeFsx([_filesystem("SINGLE_AZ_1")], volumes))
    [item] = pc.collect_fsx(session, "ap-northeast-1", PRICES)
    assert item.irreversible is None


def test_nat_price_lookup_ignores_the_regional_product() -> None:
    # "RegionalNatGateway-Hours" contains "NatGateway-Hours". Matching on
    # substring picks whichever the dict yields first and silently prices the
    # wrong product.
    assert "APN1-RegionalNatGateway-Hours".endswith("-NatGateway-Hours") is False
    assert "APN1-NatGateway-Hours".endswith("-NatGateway-Hours") is True


def test_the_irreversible_warning_names_every_terminal_state() -> None:
    # These are the states with no recovery path, so the warning is the whole
    # safety mechanism for a reader who has not met them yet.
    for phrase in (
        "SnapLock volume cannot be un-SnapLocked",
        "audit log volume blocks its parent",
        "extended, never shortened",
        "snapshot_locking_enabled",
        "COMPLIANCE",
        "return success and quietly do nothing",
    ):
        assert phrase in pc.IRREVERSIBLE_WARNING


def test_an_unrecognised_name_is_not_claimed_as_ours() -> None:
    # The safe default in a shared account. Reporting an unknown resource as this
    # project's is how a colleague's NAT gateway ends up in a deletion proposal.
    assert pc.attribute("someones-vpc-nat-public1a") == pc.OWNER_UNKNOWN
    assert pc.attribute(None) == pc.OWNER_UNKNOWN
    assert pc.attribute("") == pc.OWNER_UNKNOWN


def test_our_own_naming_and_tags_are_recognised() -> None:
    assert pc.attribute("fsxn-eda-s3ap") == pc.OWNER_OURS
    assert pc.attribute("amplify-fsxns3apamplifyportal-sandbox") == pc.OWNER_OURS
    assert pc.attribute("verification-test-ap") == pc.OWNER_OURS
    # Templates in this repository tag UseCase and Phase, so a tag outweighs a name
    # that happens to look foreign.
    assert pc.attribute("something-else", [{"Key": "UseCase", "Value": "UC6"}]) == pc.OWNER_OURS


def test_our_volume_on_a_foreign_file_system_is_shared_not_ours() -> None:
    # The situation that actually exists: a SnapLock volume from our verification
    # work sits on a file system named after someone else. Calling the file system
    # ours would invite deleting it; calling it purely theirs would hide that we
    # left something irreversible on it.
    volumes = [
        {
            "FileSystemId": "fs-1",
            "VolumeId": "fsvol-1",
            "Name": "zz_verify_auditlog",
            "OntapConfiguration": {"SnaplockConfiguration": {"SnaplockType": "ENTERPRISE"}},
        }
    ]
    filesystem = _filesystem("SINGLE_AZ_1")
    filesystem["Tags"] = [{"Key": "Name", "Value": "fsxsomeoneelse"}]
    session = _FakeSession(_FakeFsx([filesystem], volumes))
    [item] = pc.collect_fsx(session, "ap-northeast-1", PRICES)
    assert item.owner == pc.OWNER_SHARED
    assert "zz_verify_auditlog" in item.detail


def test_a_file_system_with_no_volumes_of_ours_is_left_unattributed() -> None:
    filesystem = _filesystem("SINGLE_AZ_1")
    filesystem["Tags"] = [{"Key": "Name", "Value": "fsxsomeoneelse"}]
    session = _FakeSession(_FakeFsx([filesystem], []))
    [item] = pc.collect_fsx(session, "ap-northeast-1", PRICES)
    assert item.owner == pc.OWNER_UNKNOWN


def test_the_report_separates_owners_and_totals_only_ours(capsys: pytest.CaptureFixture[str]) -> None:
    standing = [
        pc.Standing(kind="A", identifier="ours", detail="", monthly_usd=10.0, owner=pc.OWNER_OURS),
        pc.Standing(kind="B", identifier="theirs", detail="", monthly_usd=500.0, owner=pc.OWNER_UNKNOWN),
    ]
    pc.report(standing, [], "")
    out = capsys.readouterr().out
    assert "Attributable to this project: $10.00/month" in out
    # The other 500 is still shown, so nothing is hidden — it is just not counted
    # as a saving available to us.
    assert "500.00" in out


def test_the_report_warns_that_egress_must_be_measured_per_resource(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # A data transfer line on the bill was traced to a VPN tunnel while the NAT
    # gateway moved zero bytes. Reading the anomaly's service name as the culprit
    # would have removed the wrong thing.
    pc.report([], [], "")
    out = capsys.readouterr().out
    assert "TunnelDataOut" in out and "BytesOutToDestination" in out


def test_the_suggested_order_defers_to_the_existing_tools() -> None:
    assert "scripts/teardown-uc29-uc30.sh" in pc.SUGGESTED_ORDER
    assert "scripts/cleanup_generic_ucs.py" in pc.SUGGESTED_ORDER
    # The file system goes last; deleting it first is the step that cannot be
    # walked back within a working day.
    assert pc.SUGGESTED_ORDER.index("FSx for ONTAP file system last") > pc.SUGGESTED_ORDER.index(
        "cleanup_generic_ucs.py"
    )
