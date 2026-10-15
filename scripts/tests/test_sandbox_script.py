"""The order and gating of the checks in ``sandbox.sh``.

The wrapper runs three Python checks and then ``npx ampx sandbox``. What can go wrong
silently is the order and the conditions: the config-vs-live check running after
``ampx`` has already started, running when the user asked to delete, or being skipped
by the variable that exists to skip a different check. Each of those looks like a
working wrapper.

Nothing here reaches AWS or starts ``ampx``. ``python3`` and ``npx`` are replaced by
scripts that append their arguments to a log and exit with a status the test chose;
the wrapper itself is the real file.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "solutions" / "amplify-portal" / "scripts" / "sandbox.sh"

FAKE_PYTHON = """#!/usr/bin/env bash
echo "python3 $*" >> "$CALLS_LOG"
case "$*" in
  *--check-config-vs-live*) exit "${FAKE_LIVE_STATUS:-0}" ;;
  *--print-sandbox-identifier*)
    if [ "${FAKE_ID_STATUS:-0}" = 0 ]; then echo "${FAKE_ID:-demo}"; fi
    exit "${FAKE_ID_STATUS:-0}" ;;
  *--check-config*) exit "${FAKE_CONFIG_STATUS:-0}" ;;
esac
exit 99
"""

FAKE_NPX = """#!/usr/bin/env bash
echo "npx $*" >> "$CALLS_LOG"
exit 0
"""

# Variables the wrapper reads; cleared so the machine running the tests cannot decide the outcome.
WRAPPER_VARS = (
    "AMPLIFY_PORTAL_SANDBOX_IDENTIFIER",
    "AMPLIFY_PORTAL_SKIP_CONFIG_CHECK",
    "AMPLIFY_PORTAL_ALLOW_CONFIG_BLANKING",
)


def _run(tmp_path: Path, *args: str, **env: str) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name, body in (("python3", FAKE_PYTHON), ("npx", FAKE_NPX)):
        path = bin_dir / name
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "calls.log"
    log.write_text("", encoding="utf-8")
    base = {k: v for k, v in os.environ.items() if k not in WRAPPER_VARS}
    result = subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env={**base, "PATH": f"{bin_dir}:{base['PATH']}", "CALLS_LOG": str(log), **env},
    )
    return result, log.read_text(encoding="utf-8").splitlines()


def _tools(calls: list[str]) -> list[str]:
    """Reduce each logged call to the flag or tool that identifies it."""
    out = []
    for call in calls:
        if call.startswith("npx"):
            out.append("npx")
        else:
            out.append(call.split(" ", 2)[2])  # drop "python3 <script path>"
    return out


def test_the_live_check_runs_after_the_others_and_before_ampx(tmp_path: Path) -> None:
    result, calls = _run(tmp_path, "--once")

    assert result.returncode == 0, result.stderr
    assert _tools(calls) == [
        "--check-config",
        "--print-sandbox-identifier",
        "--check-config-vs-live --identifier demo",
        "npx",
    ]


def test_a_failing_live_check_stops_before_ampx(tmp_path: Path) -> None:
    result, calls = _run(tmp_path, "--once", FAKE_LIVE_STATUS="1")

    assert result.returncode == 1
    assert "npx" not in _tools(calls)
    assert "AMPLIFY_PORTAL_ALLOW_CONFIG_BLANKING" in result.stderr


def test_a_live_check_that_could_not_run_also_stops(tmp_path: Path) -> None:
    """Exit 2 is a missing portal-config.ts; ampx must not start on it either."""
    result, calls = _run(tmp_path, "--once", FAKE_LIVE_STATUS="2")

    assert result.returncode == 1
    assert "npx" not in _tools(calls)


def test_delete_does_not_run_the_live_check(tmp_path: Path) -> None:
    result, calls = _run(tmp_path, "delete", FAKE_LIVE_STATUS="1")

    assert result.returncode == 0, result.stderr
    assert not any("--check-config-vs-live" in call for call in calls)
    assert any(call.startswith("npx ampx sandbox delete") for call in calls)


def test_skipping_the_config_check_does_not_skip_the_live_check(tmp_path: Path) -> None:
    """That variable is set for a different reason, often from habit."""
    result, calls = _run(tmp_path, "--once", AMPLIFY_PORTAL_SKIP_CONFIG_CHECK="1", FAKE_LIVE_STATUS="1")

    assert result.returncode == 1
    assert not any(call.endswith("--check-config") for call in calls)  # the other check was skipped
    assert any("--check-config-vs-live" in call for call in calls)
    assert "npx" not in _tools(calls)


def test_the_identifier_override_is_passed_to_the_live_check(tmp_path: Path) -> None:
    _, calls = _run(tmp_path, "--once", AMPLIFY_PORTAL_SANDBOX_IDENTIFIER="second")

    assert "--check-config-vs-live --identifier second" in _tools(calls)
    assert not any("--print-sandbox-identifier" in call for call in calls)


def test_no_outputs_file_still_launches_and_the_check_gets_no_identifier(tmp_path: Path) -> None:
    result, calls = _run(tmp_path, "--once", FAKE_ID_STATUS="3")

    assert result.returncode == 0, result.stderr
    assert "--check-config-vs-live" in _tools(calls)
    assert any(call == "npx ampx sandbox --once" for call in calls)


def test_an_unidentifiable_sandbox_stops_before_the_live_check(tmp_path: Path) -> None:
    result, calls = _run(tmp_path, "--once", FAKE_ID_STATUS="1")

    assert result.returncode == 1
    assert not any("--check-config-vs-live" in call for call in calls)


@pytest.mark.skipif(
    subprocess.run(["bash", "-c", "command -v shellcheck"], capture_output=True, check=False).returncode != 0,
    reason="shellcheck not installed",
)
def test_shellcheck_is_clean() -> None:
    result = subprocess.run(["shellcheck", str(SCRIPT)], capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stdout
