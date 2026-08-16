"""Corpus and tests for the tracked irreversible-operations guard.

## Why the corpus lives here

`scripts/guard_irreversible_ops.py --selftest` imports `BLOCK_CASES`,
`ASK_CASES` and `ALLOW_CASES` from this module, so there is one list of cases
rather than a pytest list and a separate hand-run list that disagree. That
disagreement is the exact failure the guard was ported to fix: in the sibling
repository the executing copy allowed 10 of the 26 cases the tracked copy
documented, because the two were never compared.

## Three outcomes, not two

A guard with only block/allow cannot express "I could not read this payload".
`aws fsx create-volume --cli-input-json file://vol.json` may or may not contain
`SnaplockConfiguration`; the guard cannot know, and answering "allow" makes its
silence mean two different things. So each case declares one of:

    block  exit 2 and stderr        — refuse
    ask    exit 0 and an ask payload — hand the decision to the human
    allow  exit 0 and empty stdout   — proceed silently

## Payload shapes

Cases are written as the `tool_input` mapping a PreToolUse event actually
carries, in the three forms this repository produces: an `execute_bash` command
string, a `use_aws` structured call, and a portal dispatch action name. The
portal form matters most and is easiest to forget — an agent driving the dispatch
endpoint sends `{"action": "enableSnapshotLocking", ...}` and never types a CLI
string, so a guard matching only CLI shapes leaves the portal path open.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
GUARD = ROOT / "scripts" / "guard_irreversible_ops.py"
GLOBAL_GUARD = Path(os.environ.get("KIRO_HOME") or Path.home() / ".kiro") / "hooks/scripts/guard_irreversible_ops.py"


def _load(path: Path, name: str) -> ModuleType:
    """Import a guard module by path.

    Args:
        path: File to import.
        name: Module name to register it under.

    Returns:
        The imported module.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


guard = _load(GUARD, "tracked_guard")


# --------------------------------------------------------------------------
# The corpus. (label, tool_input)
# --------------------------------------------------------------------------

BLOCK_CASES: list[tuple[str, dict[str, object]]] = [
    # --- SnapLock audit log: the operation that prompted all of this ---
    (
        "ONTAP CLI snaplock log create",
        {"command": "ssh admin@cluster 'snaplock log create -vserver svm1 -volume auditlog'"},
    ),
    (
        "ONTAP REST POST to snaplock/audit-logs",
        {"command": 'curl -X POST https://mgmt/api/storage/snaplock/audit-logs -d \'{"svm":{"name":"svm1"}}\''},
    ),
    (
        "audit log volume flag",
        {"command": "aws fsx create-volume --audit-log-volume true"},
    ),
    # --- SnapLock volume creation ---
    (
        "FSx CLI snaplock-type compliance",
        {"command": "aws fsx create-volume --ontap-configuration snaplock-type=compliance"},
    ),
    (
        "FSx API SnaplockType COMPLIANCE",
        {"operation_name": "CreateVolume", "parameters": {"OntapConfiguration": {"SnaplockType": "COMPLIANCE"}}},
    ),
    (
        "FSx API SnaplockType ENTERPRISE",
        {"operation_name": "CreateVolume", "parameters": {"OntapConfiguration": {"SnaplockType": "ENTERPRISE"}}},
    ),
    (
        "ONTAP REST nested snaplock.type",
        {"command": 'curl -X POST /api/storage/volumes -d \'{"name":"v","snaplock":{"type":"compliance"}}\''},
    ),
    (
        "portal createVolume carrying snaplockType",
        {"action": "createVolume", "params": {"name": "v1", "snaplockType": "compliance"}},
    ),
    # --- Terminal states ---
    (
        "PrivilegedDelete permanently disabled",
        {"command": "aws fsx update-volume --ontap-configuration privileged-delete=PERMANENTLY_DISABLED"},
    ),
    # --- Snapshot locking ---
    (
        "snapshot_locking_enabled true via REST",
        {"command": "curl -X PATCH /api/storage/volumes/abc -d '{\"snapshot_locking_enabled\": true}'"},
    ),
    (
        "portal enableSnapshotLocking",
        {"action": "enableSnapshotLocking", "params": {"volumeUuid": "abc", "enabled": True}},
    ),
    (
        "portal lockSnapshot",
        {"action": "lockSnapshot", "params": {"snapshotUuid": "s1", "expiryTime": "2027-01-01T00:00:00Z"}},
    ),
    (
        "ONTAP CLI snaplock-expiry-time",
        {"command": "volume snapshot modify-snaplock-expiry-time -expiry-time 2027-01-01"},
    ),
    # --- Locked snapshot policies ---
    (
        "snapshot policy create with retention-period",
        {"command": "snapshot policy create -vserver svm1 -policy p1 -retention-period 30days"},
    ),
    (
        "snapmirror policy add-rule with retention-period",
        {"command": "snapmirror policy add-rule -policy p -rule r -retention-period 1years"},
    ),
    # --- S3 Object Lock ---
    (
        "S3 object lock mode COMPLIANCE",
        {"command": 'aws s3api put-object-retention --retention \'{"Mode":"COMPLIANCE","RetainUntilDate":"x"}\''},
    ),
    (
        "S3 put-object-lock-configuration",
        {"command": "aws s3api put-object-lock-configuration --bucket b --object-lock-configuration x"},
    ),
    (
        "ObjectLockEnabled Enabled",
        {"operation_name": "CreateBucket", "parameters": {"ObjectLockEnabledForBucket": True}},
    ),
    (
        "portal putS3ObjectLockRetention",
        {"action": "putS3ObjectLockRetention", "params": {"key": "k", "mode": "COMPLIANCE"}},
    ),
    # --- Other AWS lock families ---
    (
        "Glacier complete-vault-lock",
        {"command": "aws glacier complete-vault-lock --vault-name v --lock-id id --account-id -"},
    ),
    (
        "Backup vault lock",
        {"command": "aws backup put-backup-vault-lock-configuration --backup-vault-name v --changeable-for-days 3"},
    ),
    (
        "EBS lock-snapshot",
        {"command": "aws ec2 lock-snapshot --snapshot-id snap-1 --lock-mode compliance"},
    ),
]

ASK_CASES: list[tuple[str, dict[str, object]]] = [
    (
        # The looser mode asks rather than blocks: the rule can be replaced and a
        # caller with the bypass permission can delete the object at once. The
        # stricter mode is in BLOCK_CASES, and enabling Object Lock on a bucket
        # stays there too, so relaxing this one did not relax those.
        "portal putS3ObjectLockRetention GOVERNANCE",
        {"action": "putS3ObjectLockRetention", "params": {"bucket": "b", "mode": "GOVERNANCE", "days": 1}},
    ),
    (
        "FSx delete-file-system",
        {"command": "aws fsx delete-file-system --file-system-id fs-0123456789abcdef0"},
    ),
    (
        "FSx delete-volume",
        {"command": "aws fsx delete-volume --volume-id fsvol-0123456789abcdef0"},
    ),
    (
        "DeleteStorageVirtualMachine via use_aws",
        {"operation_name": "DeleteStorageVirtualMachine", "parameters": {"StorageVirtualMachineId": "svm-1"}},
    ),
    (
        "create-volume with an opaque external payload",
        {"command": "aws fsx create-volume --cli-input-json file://volume.json"},
    ),
    (
        "portal deleteVolume",
        {"action": "deleteVolume", "params": {"volumeUuid": "abc"}},
    ),
    (
        "portal updateSnaplockRetention",
        {"action": "updateSnaplockRetention", "params": {"volumeUuid": "abc", "retention": "30d"}},
    ),
    (
        "portal deleteFileForever",
        {"action": "deleteFileForever", "params": {"key": "k"}},
    ),
]

ALLOW_CASES: list[tuple[str, dict[str, object]]] = [
    (
        "describe file systems",
        {"command": "aws fsx describe-file-systems"},
    ),
    (
        "describe volumes with a snaplock filter",
        {"command": "aws fsx describe-volumes --query 'Volumes[?OntapConfiguration.SnaplockConfiguration]'"},
    ),
    (
        "ONTAP CLI object-first show of snaplock expiry",
        {"command": "volume snapshot show -fields snaplock-expiry-time"},
    ),
    (
        "snaplock CLI show",
        {"command": "snaplock compliance-clock show"},
    ),
    (
        "portal getSnapLockConfig",
        {"action": "getSnapLockConfig", "params": {"volumeUuid": "abc"}},
    ),
    (
        "portal getSnapshotLockingStatus",
        {"action": "getSnapshotLockingStatus", "params": {"volumeUuid": "abc"}},
    ),
    (
        "portal getSnapshotsWithLockStatus",
        {"action": "getSnapshotsWithLockStatus", "params": {"volumeUuid": "abc"}},
    ),
    (
        "portal getS3ObjectLockStatus",
        {"action": "getS3ObjectLockStatus", "params": {"bucket": "b"}},
    ),
    (
        "listing active blocks",
        {"action": "listActiveBlocks", "params": {}},
    ),
    (
        "an ordinary volume creation",
        {"action": "createVolume", "params": {"name": "v1", "sizeGb": 100}},
    ),
    (
        "reading a file",
        {"command": "cat README.md"},
    ),
    (
        "running the test suite",
        {"command": "make test-quick"},
    ),
]


# --------------------------------------------------------------------------
# In-process behaviour
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("label", "payload"), BLOCK_CASES, ids=[c[0] for c in BLOCK_CASES])
def test_blocked(label: str, payload: dict[str, object]) -> None:
    code, message = guard.classify(payload)
    assert code == 2, f"{label}: expected a block, got {'ask' if message else 'allow'}"
    assert "BLOCKED" in message
    assert len(message) > 120, f"{label}: block message must explain the consequence"


@pytest.mark.parametrize(("label", "payload"), ASK_CASES, ids=[c[0] for c in ASK_CASES])
def test_asked(label: str, payload: dict[str, object]) -> None:
    code, message = guard.classify(payload)
    assert code == 0, f"{label}: an ask case must not block"
    assert message, f"{label}: expected an ask reason, got a silent allow"


@pytest.mark.parametrize(("label", "payload"), ALLOW_CASES, ids=[c[0] for c in ALLOW_CASES])
def test_allowed(label: str, payload: dict[str, object]) -> None:
    code, message = guard.classify(payload)
    assert code == 0 and not message, f"{label}: expected a silent allow, got {'block' if code else 'ask'}: {message}"


# --------------------------------------------------------------------------
# The hook contract, exercised as a subprocess
# --------------------------------------------------------------------------


def _run(event: object) -> subprocess.CompletedProcess[str]:
    """Invoke the guard the way Kiro does: JSON on stdin."""
    return subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_block_exits_2_with_stderr() -> None:
    """Only exit 2 blocks. Any other non-zero is a warning Kiro does not act on."""
    proc = _run({"tool_input": {"command": "snaplock log create -volume auditlog"}})
    assert proc.returncode == 2
    assert "BLOCKED" in proc.stderr
    assert proc.stdout == ""


def test_ask_exits_0_with_a_valid_decision_payload() -> None:
    """The ask path is a precise JSON shape; a typo in it degrades to allow."""
    proc = _run({"tool_input": {"command": "aws fsx delete-file-system --file-system-id fs-1"}})
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["hookSpecificOutput"]["permissionDecision"] == "ask"
    assert payload["hookSpecificOutput"]["permissionDecisionReason"]


def test_allow_exits_0_silently() -> None:
    proc = _run({"tool_input": {"command": "aws fsx describe-file-systems"}})
    assert proc.returncode == 0
    assert proc.stdout == ""


@pytest.mark.parametrize(
    "raw",
    ["", "not json", "[]", "null", '{"tool_input": "a string"}', '{"tool_input": null}', "{}"],
    ids=["empty", "garbage", "list", "null", "string-input", "null-input", "no-input"],
)
def test_malformed_events_never_block(raw: str) -> None:
    """Failing closed on an unparseable event would block all work.

    A guard that blocks everything gets removed, and then it protects nothing —
    so the safe direction for a parse failure is to allow.
    """
    proc = subprocess.run(
        [sys.executable, str(GUARD)],
        input=raw,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, f"malformed event {raw!r} must not block"


def test_selftest_entrypoint_passes() -> None:
    """`--selftest` is the documented way to verify by hand; it must work."""
    proc = subprocess.run(
        [sys.executable, str(GUARD), "--selftest"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    total = len(BLOCK_CASES) + len(ASK_CASES) + len(ALLOW_CASES)
    assert f"{total}/{total} passed" in proc.stdout


# --------------------------------------------------------------------------
# The guard must be tracked, and the hook must point at the tracked copy
# --------------------------------------------------------------------------


def test_guard_is_git_tracked() -> None:
    """A guard only in .kiro/ does not exist for a collaborator, a clone, or CI.

    "Tracked" here means what the rest of this repository's checks mean by it:
    committed, or present and not ignored. A guard added in the same change as
    this test is not yet committed but will be, whereas one under `.kiro/` is
    ignored and never will be — which is the distinction that matters.
    """
    proc = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, "git ls-files failed"
    published = set(proc.stdout.splitlines())
    assert "scripts/guard_irreversible_ops.py" in published, (
        "scripts/guard_irreversible_ops.py is not in the repository (ignored or absent), "
        "so collaborators and CI would have no guard"
    )


def test_hook_invokes_the_tracked_copy_not_home() -> None:
    """A hook pointing at $HOME silently protects one machine.

    Measured in the sibling repository: the `$HOME` copy was the one executing and
    it allowed 10 of the 26 cases the tracked copy documented.
    """
    hook = ROOT / ".kiro" / "hooks" / "irreversible-ops-guard.json"
    if not hook.is_file():
        pytest.skip(".kiro/ is not present in this checkout (gitignored by design)")
    config = json.loads(hook.read_text(encoding="utf-8"))
    commands = [h.get("action", {}).get("command", "") for h in config.get("hooks", [])]
    joined = " ".join(commands)
    assert "scripts/guard_irreversible_ops.py" in joined, "the hook must run the tracked guard"
    assert "rev-parse --show-toplevel" in joined, "resolve the repository root rather than a fixed path"
    assert ".kiro/hooks/scripts/guard" not in joined, "the hook must not run the untracked .kiro copy"
    assert "$HOME" not in joined and "~/.kiro" not in joined, "the hook must not depend on a home-directory copy"
    triggers = [h.get("trigger") for h in config.get("hooks", [])]
    assert "PreToolUse" in triggers, "the guard has to run BEFORE the tool, not after"


@pytest.mark.skipif(not GLOBAL_GUARD.is_file(), reason="no global guard on this machine")
def test_covers_every_global_block_category() -> None:
    """This file may add rules but must not silently cover less than the global copy.

    Two guards drift. This makes the drift a test failure instead of a gap that
    only shows up as an operation nobody was asked about.
    """
    other = _load(GLOBAL_GUARD, "global_guard")
    missing: list[str] = []
    for label, payload in BLOCK_CASES:
        if other.scan(json.dumps(payload, ensure_ascii=False))[0] == 2:
            if guard.classify(payload)[0] != 2:
                missing.append(label)
    assert not missing, "the global guard blocks these but the tracked guard does not: " + ", ".join(missing)


@pytest.mark.skipif(not GLOBAL_GUARD.is_file(), reason="no global guard on this machine")
def test_reports_what_the_global_guard_would_miss() -> None:
    """Informational: records repo-specific coverage the global copy lacks.

    Not a failure — the portal action names are specific to this repository and
    the global guard has no reason to carry them. Asserting the count is non-zero
    would be asserting that the global copy stays behind, so this only records.
    """
    other = _load(GLOBAL_GUARD, "global_guard2")
    only_here = [
        label
        for label, payload in BLOCK_CASES
        if guard.classify(payload)[0] == 2 and other.scan(json.dumps(payload, ensure_ascii=False))[0] != 2
    ]
    print(f"\n{len(only_here)} block case(s) covered only by the tracked guard:")
    for label in only_here:
        print(f"  - {label}")


# --------------------------------------------------------------------------
# The corpus must not be vacuous
# --------------------------------------------------------------------------


def test_all_three_outcomes_are_represented() -> None:
    """A guard tested only on block cases could be blocking everything."""
    assert len(BLOCK_CASES) >= 20, f"only {len(BLOCK_CASES)} block cases"
    assert len(ASK_CASES) >= 5, f"only {len(ASK_CASES)} ask cases"
    assert len(ALLOW_CASES) >= 10, f"only {len(ALLOW_CASES)} allow cases"


def test_case_labels_are_unique() -> None:
    """Duplicate ids silently collapse in parametrize, hiding a case."""
    labels = [c[0] for c in (*BLOCK_CASES, *ASK_CASES, *ALLOW_CASES)]
    duplicates = {label for label in labels if labels.count(label) > 1}
    assert not duplicates, f"duplicate case labels: {duplicates}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
