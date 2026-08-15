"""Tests for the pinned-tool-version gate.

The gate exists because a shadowing binary reports success while applying a
different rule set. These tests carry more weight than the gate: a version check
that cannot see a mismatch is indistinguishable from agreement, which is the
condition it was written to end.

Each test therefore builds a fake tool whose `--version` output is controlled,
rather than asserting against whatever happens to be installed on the machine
running the suite — an assertion about the real toolchain would pass or fail for
reasons that have nothing to do with the code under test.
"""

from __future__ import annotations

import importlib.util
import stat
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent


def _load() -> ModuleType:
    """Import the checker by path, since scripts/ is not a package.

    Returns:
        The imported ``check_tool_versions`` module.
    """
    spec = importlib.util.spec_from_file_location("check_tool_versions", ROOT / "scripts" / "check_tool_versions.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load()


def _fake_tool(directory: Path, name: str, version_output: str, exit_code: int = 0) -> Path:
    """Create an executable that prints a chosen `--version` string.

    Args:
        directory: Directory to create the executable in; created if absent.
        name: Executable file name, e.g. ``"ruff"``.
        version_output: Exact text the fake tool echoes.
        exit_code: Status the fake tool exits with.

    Returns:
        Path to the created executable.
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(
        f"#!/bin/sh\necho {version_output!r}\nexit {exit_code}\n",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


# --------------------------------------------------------------------------
# Pin parsing
# --------------------------------------------------------------------------


def test_reads_exact_pins_from_the_real_requirements_file() -> None:
    """The tools the gate asserts must actually be pinned, or it asserts nothing."""
    declared = mod.pins()
    for tool in mod.CHECKED:
        assert tool in declared, f"{tool} is version-checked but has no == pin in requirements-dev.txt"


def test_extras_and_case_are_normalised(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`moto[all]==5.2.2` is a pin for `moto`; `Pillow` is reachable as `pillow`."""
    req = tmp_path / "requirements-dev.txt"
    req.write_text("moto[all]==5.2.2\nPillow==12.3.0\n# comment\nranged>=1.0\n", encoding="utf-8")
    monkeypatch.setattr(mod, "REQUIREMENTS", req)
    declared = mod.pins()
    assert declared["moto"] == "5.2.2"
    assert declared["pillow"] == "12.3.0"


def test_a_range_is_not_treated_as_a_pin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A range cannot be asserted against one binary, so it must not be claimed as a pin."""
    req = tmp_path / "requirements-dev.txt"
    req.write_text("ruff>=0.15.0\n", encoding="utf-8")
    monkeypatch.setattr(mod, "REQUIREMENTS", req)
    assert "ruff" not in mod.pins()


# --------------------------------------------------------------------------
# Resolution order — the actual subject of the gate
# --------------------------------------------------------------------------


def test_venv_wins_over_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`.venv/bin/<tool>` is what the Makefile uses, so it is what gets checked."""
    _fake_tool(tmp_path / ".venv" / "bin", "ruff", "ruff 0.15.17")
    elsewhere = tmp_path / "brew"
    _fake_tool(elsewhere, "ruff", "ruff 0.15.20")
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setenv("PATH", str(elsewhere))

    binary, source = mod.resolve("ruff")
    assert source == ".venv"
    assert mod.installed_version(binary, mod.CHECKED["ruff"]) == "0.15.17"


def test_path_is_used_when_there_is_no_venv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """CI installs the pins into the runner, where the PATH copy is the pinned one."""
    elsewhere = tmp_path / "bin"
    _fake_tool(elsewhere, "ruff", "ruff 0.15.17")
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setenv("PATH", str(elsewhere))

    binary, source = mod.resolve("ruff")
    assert source == "PATH"
    assert binary is not None


def test_absent_tool_is_reported_as_absent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    binary, source = mod.resolve("ruff")
    assert binary is None
    assert source == "absent"


# --------------------------------------------------------------------------
# The breakage the gate must catch
# --------------------------------------------------------------------------


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pin: str, reported: str) -> int:
    """Wire a fake single-tool world and run the gate.

    Args:
        tmp_path: Temporary root standing in for the repository.
        monkeypatch: Fixture used to redirect the module's globals.
        pin: Version written into the fake requirements-dev.txt.
        reported: Version string the fake tool reports.

    Returns:
        The gate's exit code.
    """
    req = tmp_path / "requirements-dev.txt"
    req.write_text(f"ruff=={pin}\n", encoding="utf-8")
    _fake_tool(tmp_path / ".venv" / "bin", "ruff", reported)
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "REQUIREMENTS", req)
    monkeypatch.setattr(mod, "CHECKED", {"ruff": r"(\d+\.\d+\.\d+)"})
    return mod.main([])


def test_matching_version_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _run(tmp_path, monkeypatch, pin="0.15.17", reported="ruff 0.15.17") == 0


def test_mismatched_version_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The measured case: homebrew 0.15.20 answering for a pinned 0.15.17."""
    assert _run(tmp_path, monkeypatch, pin="0.15.17", reported="ruff 0.15.20") == 1


def test_a_patch_level_difference_still_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rule sets change in patch releases; "close enough" is how the drift persisted."""
    assert _run(tmp_path, monkeypatch, pin="1.53.3", reported="cfn-lint 1.53.2") == 1


def test_unreadable_version_fails_rather_than_passing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A tool that prints nothing parseable must not be read as agreement."""
    assert _run(tmp_path, monkeypatch, pin="0.15.17", reported="something unparseable") == 1


def test_unpinned_checked_tool_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Asserting a tool with no pin would silently assert nothing."""
    req = tmp_path / "requirements-dev.txt"
    req.write_text("# nothing pinned\n", encoding="utf-8")
    _fake_tool(tmp_path / ".venv" / "bin", "ruff", "ruff 0.15.17")
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "REQUIREMENTS", req)
    monkeypatch.setattr(mod, "CHECKED", {"ruff": r"(\d+\.\d+\.\d+)"})
    assert mod.main([]) == 1


def test_unknown_tool_argument_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A typo'd tool name must not be reported as a pass."""
    monkeypatch.setattr(mod, "REQUIREMENTS", ROOT / "requirements-dev.txt")
    assert mod.main(["nosuchtool"]) == 1


def test_absent_tool_alone_does_not_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`make security` fails loudly on its own; this gate is not the place for it."""
    req = tmp_path / "requirements-dev.txt"
    req.write_text("ruff==0.15.17\n", encoding="utf-8")
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "REQUIREMENTS", req)
    monkeypatch.setattr(mod, "CHECKED", {"ruff": r"(\d+\.\d+\.\d+)"})
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    assert mod.main([]) == 0


# --------------------------------------------------------------------------
# The gate must not be vacuous
# --------------------------------------------------------------------------


def test_checked_is_not_empty() -> None:
    """An empty CHECKED table would make every test above pass while asserting nothing."""
    assert mod.CHECKED, "CHECKED is empty, so the gate examines no tools"


def test_the_real_repository_state_is_reported(capsys: pytest.CaptureFixture[str]) -> None:
    """Runs against the actual tree. Records the verdict rather than demanding a pass.

    A developer mid-upgrade should not have an unrelated test fail, but a silent
    skip here would hide the gate being broken, so the outcome is asserted to be
    one of the two meanings the gate defines.
    """
    code = mod.main([])
    captured = capsys.readouterr()
    assert code in (0, 1)
    assert "TOOL VERSIONS: PASS" in captured.out or "disagree" in captured.err


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
