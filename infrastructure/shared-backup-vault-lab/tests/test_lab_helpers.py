"""scripts/lib/lab_helpers.py: digest, portal reference, record rows and the small calculators.

The helpers are standard-library only and must run on Python 3.9 (macOS ships
/usr/bin/python3 at 3.9). Nothing here talks to AWS.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
from lab_testlib import LAB_SRC

HELPERS_PATH = LAB_SRC / "scripts" / "lib" / "lab_helpers.py"
LAB_REL = Path("infrastructure") / "shared-backup-vault-lab"
SPEC_REL = Path("solutions/amplify-portal/tests/e2e/shared-vault-lab.spec.ts")
GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("lab_helpers_under_test", HELPERS_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["lab_helpers_under_test"] = module
    spec.loader.exec_module(module)
    return module


helpers = _load()


def git(cwd: Path, *args: str) -> str:
    """Run git in an isolated environment and return stdout."""
    env = {**os.environ, **GIT_ENV}
    proc = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=True)
    return proc.stdout


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A repository-shaped copy of the lab (no git). Returns the lab root."""
    repo = tmp_path / "repo"
    root = repo / LAB_REL
    shutil.copytree(
        LAB_SRC, root, ignore=shutil.ignore_patterns("__pycache__", "tests", "docs", ".pytest_cache", "*.local.*")
    )
    return root


@pytest.fixture
def git_tree(tree: Path) -> Path:
    """The same tree, committed in a fresh git repository, with the four portal paths."""
    repo = tree.parents[1]
    portal = repo / "solutions" / "amplify-portal"
    (portal / "functions" / "recovery-points").mkdir(parents=True)
    (portal / "functions" / "restore").mkdir(parents=True)
    (portal / "src" / "components").mkdir(parents=True)
    (portal / "amplify").mkdir(parents=True)
    (portal / "functions" / "recovery-points" / "index.py").write_text("a = 1\n", encoding="utf-8")
    (portal / "functions" / "restore" / "index.py").write_text("b = 1\n", encoding="utf-8")
    (portal / "src" / "components" / "RecoveryPoints.tsx").write_text("export const c = 1;\n", encoding="utf-8")
    (portal / "amplify" / "backend.ts").write_text("export const d = 1;\n", encoding="utf-8")
    git(repo, "init", "-q")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init")
    return tree


def _edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# --------------------------------------------------------------------------
# code-digest
# --------------------------------------------------------------------------


def test_code_digest_is_stable(tree: Path) -> None:
    """Debris that is not code must not change the value (no git: allowlist walk)."""
    before = helpers.code_digest(tree)
    assert len(before) == 12 and set(before) <= set("0123456789abcdef")
    (tree / "scripts" / "lib" / "__pycache__").mkdir()
    (tree / "scripts" / "lib" / "__pycache__" / "x.pyc").write_bytes(b"\x00\x01")
    (tree / "scripts" / "lib" / ".DS_Store").write_bytes(b"junk")
    (tree / "scripts" / ".hidden.sh").write_text("echo hidden\n", encoding="utf-8")
    (tree / "scripts" / "lib" / "zz_extra.txt").write_text("notes\n", encoding="utf-8")
    (tree / "docs").mkdir(exist_ok=True)
    (tree / "docs" / "procedure.md").write_text("edited\n", encoding="utf-8")
    (tree / "cloudformation" / "parameters").mkdir(parents=True, exist_ok=True)
    (tree / "cloudformation" / "parameters" / "x.example.json").write_text("[]", encoding="utf-8")
    assert helpers.code_digest(tree) == before


def test_code_digest_is_the_same_in_git_before_and_after_staging(git_tree: Path) -> None:
    committed = helpers.code_digest(git_tree)
    (git_tree / "scripts" / "lib" / "__pycache__").mkdir()
    (git_tree / "scripts" / "lib" / "__pycache__" / "x.pyc").write_bytes(b"\x00")
    (git_tree / "scripts" / "lib" / ".DS_Store").write_bytes(b"junk")
    (git_tree / "scripts" / "lib" / "zz_extra.txt").write_text("untracked notes\n", encoding="utf-8")
    assert helpers.code_digest(git_tree) == committed
    # A new untracked script counts before it is staged and after, with the same value.
    (git_tree / "scripts" / "99_new.sh").write_text("echo new\n", encoding="utf-8")
    untracked = helpers.code_digest(git_tree)
    assert untracked != committed
    git(git_tree, "add", "scripts/99_new.sh")
    assert helpers.code_digest(git_tree) == untracked


def test_git_and_walk_modes_agree(git_tree: Path, tmp_path: Path) -> None:
    """The same files hash the same inside and outside a git work tree."""
    plain = tmp_path / "plain" / LAB_REL
    shutil.copytree(git_tree, plain, ignore=shutil.ignore_patterns("__pycache__"))
    assert helpers.code_digest(plain) == helpers.code_digest(git_tree)


def test_digest_rejects_unknown_tracked_kind(git_tree: Path) -> None:
    extra = git_tree / "scripts" / "lib" / "zz_extra.txt"
    extra.write_text("tracked notes\n", encoding="utf-8")
    git(git_tree, "add", "scripts/lib/zz_extra.txt")
    with pytest.raises(ValueError, match="unknown tracked file kind"):
        helpers.code_digest(git_tree)
    assert helpers.main(["code-digest", "--root", str(git_tree)]) == 1


def test_digest_changes_on_one_byte(tree: Path) -> None:
    before = helpers.code_digest(tree)
    _edit(tree / "scripts" / "lib" / "common.sh", "Compatibility:", "Compatibilitx:")
    assert helpers.code_digest(tree) != before


def test_digest_ignores_the_status_line_but_not_other_comments(tree: Path) -> None:
    before = helpers.code_digest(tree)
    # Swap whatever status line common.sh carries for a different valid one: the
    # digest must not move, because status-prefix lines are excluded.
    common = tree / "scripts" / "lib" / "common.sh"
    current = next(
        ln for ln in common.read_text(encoding="utf-8").splitlines() if ln.startswith("# Real-environment run:")
    )
    other = (
        "# Real-environment run: not yet done (status source: docs/verification-record.md)"
        if "recorded" in current
        else "# Real-environment run: recorded [V1]; not recorded [E13] (status source: docs/verification-record.md)"
    )
    _edit(common, current, other)
    assert helpers.code_digest(tree) == before
    _edit(tree / "scripts" / "lib" / "common.sh", "# Exit codes used", "# Exit codes seen")
    assert helpers.code_digest(tree) != before


def test_digest_ignores_a_status_line_in_templates_and_the_spec(tree: Path) -> None:
    repo = tree.parents[1]
    (tree / "cloudformation").mkdir(exist_ok=True)
    template = tree / "cloudformation" / "t.yaml"
    template.write_text(
        "# Real-environment run: not yet done (status source: docs/verification-record.md)\nResources: {}\n",
        encoding="utf-8",
    )
    spec = repo / SPEC_REL
    spec.parent.mkdir(parents=True)
    spec.write_text(
        "// Real-environment run: not yet done (status source: docs/verification-record.md)\nconst a = 1;\n",
        encoding="utf-8",
    )
    before = helpers.code_digest(tree)
    template.write_text(
        "# Real-environment run: recorded [V1] (status source: docs/verification-record.md)\nResources: {}\n",
        encoding="utf-8",
    )
    spec.write_text(
        "// Real-environment run: recorded [V3] (status source: docs/verification-record.md)\nconst a = 1;\n",
        encoding="utf-8",
    )
    assert helpers.code_digest(tree) == before


def test_spec_change_changes_digest(tree: Path) -> None:
    repo = tree.parents[1]
    without_spec = helpers.code_digest(tree)
    spec = repo / SPEC_REL
    spec.parent.mkdir(parents=True)
    spec.write_text("const a = 1;\n", encoding="utf-8")
    with_spec = helpers.code_digest(tree)
    assert with_spec != without_spec
    spec.write_text("const a = 2;\n", encoding="utf-8")
    assert helpers.code_digest(tree) != with_spec


def test_digest_normalizes_line_endings(tree: Path) -> None:
    before = helpers.code_digest(tree)
    path = tree / "scripts" / "lib" / "common.sh"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert helpers.code_digest(tree) == before


def test_digest_includes_the_library_and_the_required_actions_file(tree: Path) -> None:
    labels = [label for label, _ in helpers.digest_entries(tree)]
    assert "scripts/lib/common.sh" in labels
    assert "scripts/lib/lab_helpers.py" in labels
    assert "scripts/lib/required-actions.json" in labels
    assert not any(label.startswith(("docs/", "tests/")) for label in labels)


def test_digest_command_line_prints_the_value(tree: Path) -> None:
    proc = subprocess.run(
        [sys.executable, str(tree / "scripts" / "lib" / "lab_helpers.py"), "code-digest", "--root", str(tree)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert proc.stdout.strip() == helpers.code_digest(tree)


# --------------------------------------------------------------------------
# portal-ref
# --------------------------------------------------------------------------


def test_portal_ref_is_stable_and_changes_with_the_portal_sources(git_tree: Path) -> None:
    repo = git_tree.parents[1]
    first = helpers.portal_ref(git_tree)
    assert len(first) == 12
    (repo / "README.md").write_text("unrelated\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "unrelated")
    assert helpers.portal_ref(git_tree) == first
    backend = repo / "solutions" / "amplify-portal" / "amplify" / "backend.ts"
    backend.write_text("export const d = 2;\n", encoding="utf-8")
    git(repo, "commit", "-q", "-am", "portal change")
    assert helpers.portal_ref(git_tree) != first


@pytest.mark.parametrize(
    "dirty",
    ["solutions/amplify-portal/amplify/backend.ts", "solutions/amplify-portal/functions/restore/index.py"],
)
def test_portal_ref_refuses_uncommitted_portal_sources(git_tree: Path, dirty: str) -> None:
    repo = git_tree.parents[1]
    (repo / dirty).write_text("changed\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="uncommitted"):
        helpers.portal_ref(git_tree)


def test_portal_ref_refuses_uncommitted_lab_code(git_tree: Path) -> None:
    _edit(git_tree / "scripts" / "lib" / "common.sh", "Compatibility:", "Compatibilitx:")
    with pytest.raises(RuntimeError, match="uncommitted"):
        helpers.portal_ref(git_tree)


def test_portal_ref_refuses_an_untracked_script(git_tree: Path) -> None:
    (git_tree / "scripts" / "99_new.sh").write_text("echo x\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="uncommitted"):
        helpers.portal_ref(git_tree)


def test_portal_ref_needs_git(tree: Path) -> None:
    with pytest.raises(RuntimeError, match="git"):
        helpers.portal_ref(tree)


def test_portal_ref_fails_when_a_portal_path_is_missing_at_head(git_tree: Path) -> None:
    repo = git_tree.parents[1]
    git(repo, "rm", "-q", "-r", "solutions/amplify-portal/functions/restore")
    git(repo, "commit", "-q", "-m", "remove")
    with pytest.raises(RuntimeError, match="not found at HEAD"):
        helpers.portal_ref(git_tree)


# --------------------------------------------------------------------------
# record-row
# --------------------------------------------------------------------------


def _event(
    run: str, ts: str, event: str, item: str = "-", mode: str = "apply", detail: str = "", script: str = "06"
) -> dict:
    return {
        "ts": ts,
        "script": script,
        "region": "ap-northeast-1",
        "event": event,
        "item": item,
        "detail": detail,
        "mode": mode,
        "run": run,
    }


def _end(run: str, ts: str, exit_code: int, mode: str = "apply", digest: str = "0123456789ab") -> dict:
    return _event(run, ts, "end", detail=json.dumps({"digest": digest, "exit": exit_code}), mode=mode)


def test_record_row_aggregates_apply_runs_per_item() -> None:
    run = "2026-10-11T01:00:00Z"
    records = [
        _event(run, "2026-10-11T01:00:00Z", "check_pass", "V1"),
        _event(run, "2026-10-11T01:00:05Z", "check_pass", "V1"),
        _event(run, "2026-10-11T01:00:06Z", "check_warn", "V1"),
        _event(run, "2026-10-11T01:00:07Z", "check_fail", "V2"),
        _event(run, "2026-10-11T01:00:08Z", "check_pass", "V3"),
        _event(run, "2026-10-11T01:00:09Z", "check_pass", "-"),
        _end(run, "2026-10-11T01:02:00Z", 1),
    ]
    rows = helpers.record_rows(records, "aws-cli/2.99.0", "feedfacecafe")
    assert [(r["item"], r["result"]) for r in rows] == [
        ("V1", "2✅ 0❌ 1⚠"),
        ("V2", "0✅ 1❌ 0⚠"),
        ("V3", "1✅ 0❌ 0⚠"),
    ]
    by_item = {r["item"]: r for r in rows}
    assert by_item["V1"]["portal_ref"] == "-"
    assert by_item["V3"]["portal_ref"] == "feedfacecafe"
    assert by_item["V1"]["digest"] == "0123456789ab"
    assert by_item["V1"]["duration"] == "120s"
    assert by_item["V1"]["date"] == "2026-10-11"


def test_record_row_ignores_plan_runs() -> None:
    plan_mode = [
        _event("r1", "2026-10-11T01:00:00Z", "check_pass", "V1", mode="plan"),
        _end("r1", "2026-10-11T01:00:01Z", 10, mode="plan"),
    ]
    plan_exit_in_apply_mode = [
        _event("r2", "2026-10-11T02:00:00Z", "check_pass", "V1"),
        _end("r2", "2026-10-11T02:00:01Z", 10),
    ]
    killed = [_event("r3", "2026-10-11T03:00:00Z", "check_pass", "V1")]
    assert helpers.record_rows(plan_mode + plan_exit_in_apply_mode + killed, "cli", "ref") == []


def test_record_row_keeps_runs_apart() -> None:
    records = [
        _event("r1", "2026-10-11T01:00:00Z", "check_pass", "V1"),
        _end("r1", "2026-10-11T01:00:30Z", 0, digest="aaaaaaaaaaaa"),
        _event("r2", "2026-10-12T01:00:00Z", "check_fail", "V1"),
        _end("r2", "2026-10-12T01:00:30Z", 1, digest="bbbbbbbbbbbb"),
    ]
    rows = helpers.record_rows(records, "cli", "ref")
    assert [(r["date"], r["digest"], r["result"]) for r in rows] == [
        ("2026-10-11", "aaaaaaaaaaaa", "1✅ 0❌ 0⚠"),
        ("2026-10-12", "bbbbbbbbbbbb", "0✅ 1❌ 0⚠"),
    ]


def test_record_row_command_prints_rows_for_a_clean_tree(git_tree: Path, capsys: pytest.CaptureFixture[str]) -> None:
    log = git_tree / "lab-run.local.jsonl"
    log.write_text(
        "\n".join(
            json.dumps(r)
            for r in [
                _event("r1", "2026-10-11T01:00:00Z", "check_pass", "V3"),
                _end("r1", "2026-10-11T01:00:10Z", 0),
                {"not": "an event"},
            ]
        )
        + "\nnot json\n",
        encoding="utf-8",
    )
    assert helpers.main(["record-row", "--root", str(git_tree), "--log", str(log), "--aws-cli", "aws-cli/2.99.0"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("| 2026-10-11 | ap-northeast-1 | <fill> | aws-cli/2.99.0 | 0123456789ab | ")
    assert "| V3 | 1✅ 0❌ 0⚠ | 10s |" in out


def test_record_row_command_refuses_when_the_portal_or_lab_code_is_dirty(
    git_tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = git_tree.parents[1]
    (repo / "solutions" / "amplify-portal" / "amplify" / "backend.ts").write_text("dirty\n", encoding="utf-8")
    log = git_tree / "lab-run.local.jsonl"
    log.write_text(json.dumps(_end("r1", "2026-10-11T01:00:10Z", 0)) + "\n", encoding="utf-8")
    assert helpers.main(["record-row", "--root", str(git_tree), "--log", str(log), "--aws-cli", "cli"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "no row produced" in captured.err


def test_record_row_command_refuses_without_git(tree: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert helpers.main(["record-row", "--root", str(tree), "--aws-cli", "cli"]) == 1
    assert "no row produced" in capsys.readouterr().err


# --------------------------------------------------------------------------
# add-days
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "days", "expected"),
    [
        ("2026-10-11T01:00:00Z", 7, "2026-10-18T01:00:00Z"),
        ("2026-01-31T10:00:00Z", 30, "2026-03-02T10:00:00Z"),
        ("2026-12-25T23:59:59Z", 10, "2027-01-04T23:59:59Z"),
        ("2028-02-28T00:00:00Z", 1, "2028-02-29T00:00:00Z"),
        ("2028-02-29T12:00:00Z", 365, "2029-02-28T12:00:00Z"),
        ("2027-02-28T00:00:00Z", 1, "2027-03-01T00:00:00Z"),
        ("2026-10-11T01:00:00+09:00", 1, "2026-10-11T16:00:00Z"),
        ("2026-10-11T01:00:00", 1, "2026-10-12T01:00:00Z"),
        ("2026-10-11T01:00:00.123Z", 0, "2026-10-11T01:00:00Z"),
        ("2026-10-11T01:00:00Z", -11, "2026-09-30T01:00:00Z"),
    ],
)
def test_add_days(start: str, days: int, expected: str) -> None:
    assert helpers.add_days(start, days) == expected


def test_add_days_rejects_text_that_is_not_a_timestamp() -> None:
    with pytest.raises(ValueError):
        helpers.add_days("tomorrow", 1)
    assert helpers.main(["add-days", "--from", "tomorrow", "--days", "1"]) == 1


@pytest.mark.parametrize(
    ("value", "expected"),
    [("2024-02-29", True), ("2023-02-29", False), ("2026-1-1", False), ("2026-13-01", False), ("", False)],
)
def test_valid_date(value: str, expected: bool) -> None:
    assert helpers.valid_date(value) is expected


# --------------------------------------------------------------------------
# sso-minutes
# --------------------------------------------------------------------------


def _write_sso(tmp_path: Path, config: str, key: str | None, expires: str | None) -> tuple[Path, Path]:
    config_path = tmp_path / "config"
    cache = tmp_path / "cache"
    cache.mkdir()
    config_path.write_text(config, encoding="utf-8")
    if key is not None and expires is not None:
        digest = hashlib.sha1(key.encode("utf-8"), usedforsecurity=False).hexdigest()
        (cache / f"{digest}.json").write_text(json.dumps({"expiresAt": expires}), encoding="utf-8")
    return config_path, cache


SSO_NEW = "[profile p]\nsso_session = s1\n[sso-session s1]\nsso_start_url = https://example.invalid/start\n"
SSO_OLD = "[profile p]\nsso_start_url = https://example.invalid/start\n"


@pytest.mark.parametrize(
    ("config", "key"), [(SSO_NEW, "s1"), (SSO_OLD, "https://example.invalid/start")], ids=["new", "legacy"]
)
def test_sso_minutes_both_formats(tmp_path: Path, config: str, key: str) -> None:
    cfg, cache = _write_sso(tmp_path, config, key, "2026-10-11T00:45:30Z")
    assert helpers.sso_minutes("p", cfg, cache, "2026-10-11T00:00:00Z") == "45"


def test_sso_minutes_never_goes_negative(tmp_path: Path) -> None:
    cfg, cache = _write_sso(tmp_path, SSO_NEW, "s1", "2026-10-10T00:00:00Z")
    assert helpers.sso_minutes("p", cfg, cache, "2026-10-11T00:00:00Z") == "0"


def test_sso_minutes_reports_what_it_cannot_read(tmp_path: Path) -> None:
    cfg, cache = _write_sso(tmp_path, SSO_NEW, None, None)
    assert helpers.sso_minutes("p", cfg, cache, "2026-10-11T00:00:00Z").startswith("unknown:")
    assert helpers.sso_minutes("other", cfg, cache, "2026-10-11T00:00:00Z") == "unknown:profile not found"
    assert helpers.sso_minutes("p", tmp_path / "missing", cache, "2026-10-11T00:00:00Z").startswith("unknown:")


def test_sso_minutes_non_sso_profile_is_not_applicable(tmp_path: Path) -> None:
    cfg, cache = _write_sso(tmp_path, "[profile p]\nregion = ap-northeast-1\n", None, None)
    assert helpers.sso_minutes("p", cfg, cache, "2026-10-11T00:00:00Z") == "n/a"


def test_sso_minutes_default_profile_section(tmp_path: Path) -> None:
    cfg, cache = _write_sso(
        tmp_path,
        "[default]\nsso_start_url = https://example.invalid/start\n",
        "https://example.invalid/start",
        "2026-10-11T01:00:00Z",
    )
    assert helpers.sso_minutes("default", cfg, cache, "2026-10-11T00:00:00Z") == "60"


# --------------------------------------------------------------------------
# svm-limit
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("throughput", "network", "pairs", "expected"),
    [
        (128, "IPV4", 1, 6),
        (256, "IPV4", 1, 6),
        (384, "IPV4", 1, 6),
        (512, "IPV4", 1, 14),
        (768, "IPV4", 1, 6),
        (1024, "IPV4", 1, 14),
        (1536, "IPV4", 1, 14),
        (2048, "IPV4", 1, 24),
        (3072, "IPV4", 1, 14),
        (4096, "IPV4", 1, 24),
        (6144, "IPV4", 1, 24),
        (128, "DUAL", 1, 6),
        (512, "DUAL", 1, 11),
        (2048, "DUAL", 1, 11),
        (6144, "DUAL", 1, 11),
        (4096, "IPV4", 2, 11),
        (12345, "IPV4", 12, 11),
    ],
)
def test_svm_limit_table(throughput: int, network: str, pairs: int, expected: int) -> None:
    assert helpers.svm_limit(throughput, network, pairs) == expected


def test_svm_limit_unknown_combination_is_none_and_exit_3(capsys: pytest.CaptureFixture[str]) -> None:
    assert helpers.svm_limit(100, "IPV4", 1) is None
    assert helpers.main(["svm-limit", "--throughput", "100"]) == 3
    assert "LAB_RECIPIENT_SVM_LIMIT" in capsys.readouterr().err
    assert helpers.main(["svm-limit", "--throughput", "128"]) == 0


def test_svm_limit_table_cites_its_source() -> None:
    text = HELPERS_PATH.read_text(encoding="utf-8")
    assert "https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/managing-svms.html" in text
    assert "Retrieved 2026-10-11" in text


# --------------------------------------------------------------------------
# restore-metadata
# --------------------------------------------------------------------------

SOURCE_METADATA = {
    "Name": "vol_lab",
    "OntapConfiguration": json.dumps(
        {
            "JunctionPath": "/vol_lab",
            "SizeInMegabytes": "1024",
            "StorageEfficiencyEnabled": "true",
            "StorageVirtualMachineId": "svm-0aaaaaaaaaaaaaaaa",
            "TieringPolicy": {"Name": "NONE"},
        }
    ),
    "FileSystemId": "fs-0bbbbbbbbbbbbbbbb",
    "VolumeId": "fsvol-0cccccccccccccccc",
    "Lifecycle": "CREATED",
    "VolumeType": "ONTAP",
}


def test_restore_metadata_uses_the_documented_key_casing() -> None:
    built = helpers.build_restore_metadata(SOURCE_METADATA, "svm-0dddddddddddddddd", None, None)
    assert sorted(built) == ["Name", "OntapConfiguration"]
    assert all(isinstance(v, str) for v in built.values())
    ontap = json.loads(built["OntapConfiguration"])
    assert sorted(ontap) == ["junctionPath", "sizeInMegabytes", "storageEfficiencyEnabled", "storageVirtualMachineId"]
    assert ontap["storageVirtualMachineId"] == "svm-0dddddddddddddddd"
    assert ontap["junctionPath"] == "/vol_lab"
    assert ontap["sizeInMegabytes"] == "1024"


def test_restore_metadata_never_sends_identity_or_tiering_fields() -> None:
    built = helpers.build_restore_metadata(SOURCE_METADATA, None, None, None)
    flat = json.dumps(built).lower()
    for forbidden in ("filesystemid", "volumeid", "lifecycle", "volumetype", "tieringpolicy"):
        assert forbidden not in flat


def test_restore_metadata_overrides_and_case_insensitive_input() -> None:
    lowered = {k.lower(): v for k, v in SOURCE_METADATA.items()}
    built = helpers.build_restore_metadata(lowered, None, "vol_restored", "/vol_restored")
    ontap = json.loads(built["OntapConfiguration"])
    assert built["Name"] == "vol_restored"
    assert ontap["junctionPath"] == "/vol_restored"
    assert ontap["storageVirtualMachineId"] == "svm-0aaaaaaaaaaaaaaaa"


def test_restore_metadata_refuses_incomplete_input() -> None:
    with pytest.raises(ValueError, match="OntapConfiguration"):
        helpers.build_restore_metadata({"Name": "v"}, "svm-0dddddddddddddddd", None, None)
    with pytest.raises(ValueError, match="volume name"):
        helpers.build_restore_metadata({"OntapConfiguration": "{}"}, "svm-0dddddddddddddddd", None, None)
    with pytest.raises(ValueError, match="storageVirtualMachineId"):
        helpers.build_restore_metadata({"Name": "v", "OntapConfiguration": "{}"}, None, None, None)


def test_restore_metadata_command_reads_the_api_response(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    response = tmp_path / "response.json"
    response.write_text(json.dumps({"RestoreMetadata": SOURCE_METADATA, "ResourceType": "FSx"}), encoding="utf-8")
    assert helpers.main(["restore-metadata", "--input", str(response), "--svm-id", "svm-0dddddddddddddddd"]) == 0
    built = json.loads(capsys.readouterr().out)
    assert sorted(built) == ["Name", "OntapConfiguration"]


# --------------------------------------------------------------------------
# cost-dates
# --------------------------------------------------------------------------


def test_cost_dates_with_since() -> None:
    assert helpers.cost_dates("2026-10-01", None, "2026-10-11T23:30:00Z") == {
        "start": "2026-10-01",
        "end": "2026-10-12",
    }


def test_cost_dates_from_the_first_record(tmp_path: Path) -> None:
    record = tmp_path / "run.jsonl"
    record.write_text(
        json.dumps({"ts": "2026-10-05T03:00:00Z"}) + "\n" + json.dumps({"ts": "2026-10-09T03:00:00Z"}) + "\n",
        encoding="utf-8",
    )
    assert helpers.cost_dates(None, record, "2026-10-11T00:00:00Z")["start"] == "2026-10-05"


def test_cost_dates_needs_a_start(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no start date"):
        helpers.cost_dates(None, tmp_path / "missing.jsonl", "2026-10-11T00:00:00Z")
    with pytest.raises(ValueError, match="real"):
        helpers.cost_dates("2026-02-30", None, "2026-10-11T00:00:00Z")
    with pytest.raises(ValueError, match="before"):
        helpers.cost_dates("2026-10-12", None, "2026-10-11T00:00:00Z")


# --------------------------------------------------------------------------
# Python 3.9 and file hygiene
# --------------------------------------------------------------------------


def test_helpers_parse_as_python_3_9() -> None:
    """No syntax newer than 3.9 (match, parenthesized with-items, except*, ...)."""
    ast.parse(HELPERS_PATH.read_text(encoding="utf-8"), feature_version=(3, 9))


def _python39() -> str | None:
    for candidate in ("python3.9", "/usr/bin/python3"):
        exe = shutil.which(candidate) or (candidate if os.path.isfile(candidate) else None)
        if exe is None:
            continue
        try:
            probe = subprocess.run(
                [exe, "-c", "import sys; print(sys.version_info[:2] == (3, 9))"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if probe.stdout.strip() == "True":
            return exe
    return None


def test_helpers_run_on_python_3_9_when_available(tree: Path) -> None:
    exe = _python39()
    if exe is None:
        pytest.skip("no Python 3.9 interpreter found: execution on 3.9 is not verified here")
    proc = subprocess.run(
        [exe, str(HELPERS_PATH), "add-days", "--from", "2026-01-31T10:00:00Z", "--days", "30"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.stdout.strip() == "2026-03-02T10:00:00Z", proc.stderr
    digest = subprocess.run(
        [exe, str(tree / "scripts" / "lib" / "lab_helpers.py"), "code-digest", "--root", str(tree)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert digest.stdout.strip() == helpers.code_digest(tree), digest.stderr
    sso = subprocess.run(
        [
            exe,
            str(HELPERS_PATH),
            "sso-minutes",
            "--profile",
            "p",
            "--config",
            os.devnull,
            "--now",
            "2026-10-11T00:00:00Z",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert sso.stdout.strip().startswith("unknown:")


def test_helpers_status_line_and_language() -> None:
    lines = HELPERS_PATH.read_text(encoding="utf-8").splitlines()
    status_re = re.compile(
        r"^# Real-environment run: (not yet done|recorded (\[[VE]\d+\])+(; not recorded (\[[VE]\d+\])+)?)"
        r" \(status source: docs/verification-record\.md\)$"
    )
    assert status_re.match(lines[1]), lines[1]
    assert all(ord(ch) < 128 or ch in "✅❌⚠" for ch in HELPERS_PATH.read_text(encoding="utf-8"))


def test_required_actions_skeleton_has_the_five_groups() -> None:
    data = json.loads((LAB_SRC / "scripts" / "lib" / "required-actions.json").read_text(encoding="utf-8"))
    groups = {k: v for k, v in data.items() if not k.startswith("_")}
    assert sorted(groups) == [
        "cloudformation-provisioning-owner",
        "cloudformation-provisioning-recipient",
        "operator-optional",
        "operator-owner",
        "operator-recipient",
    ]
    for actions in groups.values():
        assert actions == sorted(actions)
        assert all(isinstance(a, str) and ":" in a for a in actions)
