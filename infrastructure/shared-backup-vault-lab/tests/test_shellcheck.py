"""shellcheck over every shell file in the lab, including extensionless test stubs.

``tests/stubs/aws`` has no extension, and ruff does not read it, so the set of files
is derived from git (or, outside git, from a walk) rather than from a ``*.sh`` glob.
Without shellcheck the check is skipped locally and FAILS in CI: a check that did not
run must not look like a check that found nothing.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from lab_testlib import LAB_SRC

SHELLCHECK_ARGS = ["-x", "--severity=style", "--shell=bash"]


def _is_shell(path: Path) -> bool:
    if path.suffix == ".sh":
        return True
    if path.suffix or not path.is_file():
        return False
    try:
        first = path.read_text(encoding="utf-8").splitlines()[0]
    except (UnicodeDecodeError, IndexError, OSError):
        return False
    return first.startswith("#!") and any(shell in first for shell in ("/sh", "/bash", "env sh", "env bash"))


def shellcheck_targets(root: Path) -> list[Path]:
    """List the shell files under ``root``.

    Inside git it is ``git ls-files -co --exclude-standard`` (tracked plus untracked
    and not ignored); otherwise a walk that skips caches. ``.sh`` files and
    extensionless files with a shell shebang qualify.

    Args:
        root: Lab root.

    Returns:
        Sorted absolute paths.
    """
    names: list[str] = []
    proc = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if proc.returncode == 0:
        names = [n for n in proc.stdout.decode("utf-8").split("\0") if n]
    else:
        names = [
            str(p.relative_to(root))
            for p in root.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and not any(part.startswith(".") for part in p.parts)
        ]
    return sorted(p for p in (root / n for n in names) if _is_shell(p))


def missing_tool_outcome(env: dict[str, str]) -> str:
    """Decide what a missing shellcheck means.

    Args:
        env: Process environment.

    Returns:
        ``fail`` in CI, ``skip`` elsewhere.
    """
    return "fail" if env.get("CI") else "skip"


def run_shellcheck(paths: list[Path]) -> subprocess.CompletedProcess[str]:
    """Run shellcheck with the lab's settings.

    Args:
        paths: Files to check.

    Returns:
        The completed process.
    """
    return subprocess.run(
        ["shellcheck", *SHELLCHECK_ARGS, *map(str, paths)], capture_output=True, text=True, check=False
    )


REQUIRED_TARGETS = ("scripts/lib/common.sh", "tests/stubs/aws", "tests/stubs/sleep")


def missing_required_targets(targets: set[str]) -> list[str]:
    """Return the files the set must contain but does not.

    Args:
        targets: Lab-relative paths of the files that would be checked.

    Returns:
        Missing required paths (empty when the set is complete).
    """
    return [required for required in REQUIRED_TARGETS if required not in targets]


def test_shellcheck_set_includes_common_lib() -> None:
    targets = {str(p.relative_to(LAB_SRC)) for p in shellcheck_targets(LAB_SRC)}
    assert missing_required_targets(targets) == []
    assert not any(t.endswith(".py") for t in targets)


def test_shellcheck_set_check_reports_a_set_without_common_lib() -> None:
    """Negative control: dropping lib/common.sh from the set must be reported."""
    targets = {str(p.relative_to(LAB_SRC)) for p in shellcheck_targets(LAB_SRC)}
    assert missing_required_targets(targets - {"scripts/lib/common.sh"}) == ["scripts/lib/common.sh"]
    assert missing_required_targets(targets - {"tests/stubs/aws"}) == ["tests/stubs/aws"]


def test_shellcheck_set_negative_control(tmp_path: Path) -> None:
    """A set that lacks lib/common.sh must be reported as incomplete."""
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "01_a.sh").write_text("#!/bin/bash\necho a\n", encoding="utf-8")
    (tmp_path / "scripts" / "notes.txt").write_text("x\n", encoding="utf-8")
    (tmp_path / "scripts" / "extensionless").write_text("#!/bin/sh\necho b\n", encoding="utf-8")
    (tmp_path / "scripts" / "binary").write_text("not a script\n", encoding="utf-8")
    targets = {str(p.relative_to(tmp_path)) for p in shellcheck_targets(tmp_path)}
    assert targets == {"scripts/01_a.sh", "scripts/extensionless"}
    assert "scripts/lib/common.sh" not in targets


def test_a_missing_shellcheck_fails_in_ci_and_skips_locally() -> None:
    assert missing_tool_outcome({"CI": "true"}) == "fail"
    assert missing_tool_outcome({}) == "skip"
    assert missing_tool_outcome({"CI": ""}) == "skip"


def _require_shellcheck() -> str:
    path = shutil.which("shellcheck")
    if path is None:
        if missing_tool_outcome(dict(os.environ)) == "fail":
            pytest.fail("shellcheck is required in CI and was not found on PATH")
        pytest.skip("shellcheck is not installed: the shell files were NOT checked")
    return path


def test_shellcheck_reports_a_real_defect(tmp_path: Path) -> None:
    """Negative control: the settings above must fail on an unquoted expansion."""
    _require_shellcheck()
    bad = tmp_path / "bad.sh"
    bad.write_text("#!/bin/bash\nname=$1\nrm -rf $name/*\n", encoding="utf-8")
    assert run_shellcheck([bad]).returncode != 0
    good = tmp_path / "good.sh"
    good.write_text('#!/bin/bash\nname=$1\necho "$name"\n', encoding="utf-8")
    assert run_shellcheck([good]).returncode == 0


def test_shellcheck_is_clean_on_every_lab_shell_file() -> None:
    _require_shellcheck()
    targets = shellcheck_targets(LAB_SRC)
    assert targets
    version = subprocess.run(["shellcheck", "--version"], capture_output=True, text=True, check=False).stdout
    proc = run_shellcheck(targets)
    assert proc.returncode == 0, f"{version}\n{proc.stdout}{proc.stderr}"
