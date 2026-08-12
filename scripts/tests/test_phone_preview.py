"""The phone-preview script's contract: it is reachable, and it refuses bad input.

Why a test for a shell script that mostly shells out: the ways it breaks are silent.
A rename leaves `npm run phone` pointing at nothing, and the error arrives as
"sh: no such file" to someone who is trying to check a layout on a handset. The
argument parser is worth guarding because both branches exit before any process is
started, so they are the only paths that can be exercised without opening a tunnel.

Nothing here starts a dev server or a tunnel. `--help` and an unknown option both
return inside the parse loop, before the script changes directory or runs preflight.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PORTAL = REPO_ROOT / "solutions" / "amplify-portal"
SCRIPT = PORTAL / "scripts" / "phone-preview.sh"


def test_the_script_exists_and_is_executable():
    """`npm run phone` calls it directly, so the execute bit is part of the contract."""
    assert SCRIPT.is_file(), f"missing: {SCRIPT.relative_to(REPO_ROOT)}"
    mode = SCRIPT.stat().st_mode
    assert mode & stat.S_IXUSR, f"not executable: {SCRIPT.relative_to(REPO_ROOT)}"


def test_the_npm_script_points_at_it():
    """Guards the rename: package.json and the file on disk have to agree."""
    scripts = json.loads((PORTAL / "package.json").read_text(encoding="utf-8"))["scripts"]
    assert "phone" in scripts, "package.json lost the `phone` script"
    target = scripts["phone"].split()[0].lstrip("./")
    assert (PORTAL / target).is_file(), f"`npm run phone` points at a missing file: {target}"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=PORTAL,
        env={**os.environ, "CI": "1"},
        check=False,
    )


def test_help_exits_zero_and_describes_the_usage():
    """`--help` has to work without a dev server, a tunnel or AWS credentials."""
    result = _run("--help")
    assert result.returncode == 0, result.stderr
    assert "phone-preview.sh" in result.stdout
    # The secure-context reason is the one thing a reader needs before deciding
    # whether to reach for a LAN address instead.
    assert "secure context" in result.stdout


def test_an_unknown_option_is_refused_rather_than_ignored():
    """Exit 2, not 0: a typo in a flag must not silently serve on the default port."""
    result = _run("--not-a-real-flag")
    assert result.returncode == 2, f"expected exit 2, got {result.returncode}: {result.stderr}"
    assert "unknown option" in result.stderr


@pytest.mark.parametrize("flag", ["--port", "--url"])
def test_a_flag_without_its_value_fails_loudly(flag: str):
    """`--port` with nothing after it should not fall through to the default."""
    result = _run(flag)
    assert result.returncode != 0
    assert flag in result.stderr


def test_shellcheck_is_clean_when_available():
    """Skipped where shellcheck is absent; the repository has no shell lint gate in CI."""
    try:
        result = subprocess.run(["shellcheck", str(SCRIPT)], capture_output=True, text=True, timeout=60, check=False)
    except FileNotFoundError:
        pytest.skip("shellcheck not installed")
    assert result.returncode == 0, result.stdout or result.stderr
