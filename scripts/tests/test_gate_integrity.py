"""A gate must fail when its tool is missing, not report success for not running.

## The failure being closed

`command -v <tool> || { echo "skipping"; exit 0; }` makes "the scanner was never
installed" indistinguishable from "the scanner found nothing". Both print a
cheerful line and exit 0, and the second is the one everybody assumes. The same
shape appears as `<tool> ... || true` and as `if command -v t; then t; fi` with no
else branch.

This repository already lost a gate to a neighbouring version of that mistake:
`make security` was not declared `.PHONY` and collides with the `security/`
directory, so make answered "up to date" and ran bandit zero times while sitting
in the pre-commit list. The first real run found nine Medium-and-above findings,
two of them genuine SQL injection vectors. See `test_makefile_phony.py`.

`scripts/lint_phase7_templates.sh` carries the residue of it: its success
condition is `[[ $RC -eq 0 ]] || [[ "$ERR_LINES" == "0" ]]`, which reports OK on
any exit code as long as no output line begins with an `E` code — so a cfn-lint
that failed to run at all reads as clean. It is not referenced by the Makefile or
by any workflow, so it is recorded here rather than treated as a live gate.

## Two kinds of check

Static: no recipe in a gate target may discard its command's exit status, and no
gate script may take a skip-and-succeed branch on a missing tool.

Executed: the gate targets are actually run with `PATH=/usr/bin:/bin` in a tree
with no `.venv`, and each one is required to exit non-zero. That is the measurement
that cannot be argued with, and it is the reason this file executes make at all
rather than only reading it.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
MAKEFILE = ROOT / "Makefile"

# Targets whose whole purpose is to fail on bad input. If one of these can exit 0
# without its tool present, it is not a gate.
GATE_TARGETS = ("lint-python-check", "lint-python-format", "lint-cfn", "security", "lint-ops", "lint-cfn-ops")

# `|| true` is legitimate in cleanup and in `grep -c`, which exits 1 on no match.
# It is never legitimate on a target whose exit code is the verdict.
ALLOWED_TRUE_TARGETS = {
    "clean",  # removing something absent is not a failure
    "security-report",  # the machine-readable twin of `security`, which is the gate
    "build-SharedLayer",  # pruning __pycache__ that may not exist
}

SKIP_AND_SUCCEED = re.compile(
    r"command -v\s+(\S+).{0,200}?(exit 0|echo\s+[\"']?skip)",
    re.IGNORECASE | re.DOTALL,
)


def recipes() -> dict[str, list[str]]:
    """Every Makefile target mapped to its recipe lines.

    Returns:
        Mapping of target name to the tab-indented lines of its recipe.
    """
    found: dict[str, list[str]] = {}
    current: str | None = None
    for line in MAKEFILE.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Za-z0-9_.\-]+):(?!=)", line)
        if match:
            current = match.group(1)
            found.setdefault(current, [])
            continue
        if line.startswith("\t") and current:
            found[current].append(line.strip())
        elif line and not line[0].isspace() and not line.startswith("#"):
            current = None
    return found


# --------------------------------------------------------------------------
# Static: a gate may not discard its verdict
# --------------------------------------------------------------------------


def test_no_gate_target_swallows_its_exit_code() -> None:
    """`|| true` on a gate makes the gate advisory without saying so."""
    offenders: list[str] = []
    for target, lines in recipes().items():
        if target in ALLOWED_TRUE_TARGETS:
            continue
        for line in lines:
            if line.startswith("#"):
                continue
            if re.search(r"\|\|\s*(true|:|exit 0)\b", line):
                offenders.append(f"{target}: {line}")
    assert not offenders, "gate recipes that discard their exit status:\n  " + "\n  ".join(offenders)


def test_no_gate_target_falls_back_to_a_second_invocation() -> None:
    """`tool --config X 2>/dev/null || tool` always runs the fallback.

    `||` reports only the second command's status, and `2>/dev/null` hides the
    first one's complaint, so the target silently uses a configuration it does
    not name and cannot fail on the path it appears to take. `lint-python-check`
    and `lint-ops` both shipped this shape.
    """
    offenders: list[str] = []
    for target, lines in recipes().items():
        # `clean` and the layer build silence "no such file" while removing things
        # that may not exist. Reporting those would be reporting correct code, and
        # a rule that does that is a rule someone deletes.
        if target in ALLOWED_TRUE_TARGETS:
            continue
        joined = " ".join(line for line in lines if not line.startswith("#"))
        if re.search(r"2>/dev/null\s*\|\|", joined):
            offenders.append(f"{target}: {joined[:160]}")
    assert not offenders, "recipes whose real command is an unconditional fallback:\n  " + "\n  ".join(offenders)


def test_gate_targets_use_the_pinned_binary() -> None:
    """A bare `ruff`/`cfn-lint`/`bandit` lets any PATH copy answer for the pin.

    Measured on the machine this was written on: homebrew ruff 0.15.20 and
    cfn-lint 1.52.1 came first on PATH against pins of 0.15.17 and 1.53.3.
    """
    bare = re.compile(r"(?<![/\w.$(-])(ruff|cfn-lint|bandit)\b")
    offenders: list[str] = []
    for target in GATE_TARGETS:
        for line in recipes().get(target, []):
            if line.startswith("#"):
                continue
            if bare.search(line):
                offenders.append(f"{target}: {line}")
    assert not offenders, (
        "gate recipes calling an unpinned binary; use $(VENV_RUFF) / $(VENV_CFN_LINT) / $(VENV_BANDIT):\n  "
        + "\n  ".join(offenders)
    )


# --------------------------------------------------------------------------
# Static: gate scripts may not skip and succeed
# --------------------------------------------------------------------------


def _gate_scripts() -> list[Path]:
    """Shell scripts invoked by a Makefile target, so their exit code is a verdict."""
    text = MAKEFILE.read_text(encoding="utf-8")
    names = set(re.findall(r"(scripts/[A-Za-z0-9_./-]+\.sh)", text))
    return sorted((ROOT / name) for name in names if (ROOT / name).is_file())


def test_gate_scripts_do_not_skip_and_succeed() -> None:
    """A gate script that cannot find its tool must exit non-zero."""
    offenders: list[str] = []
    for script in _gate_scripts():
        body = script.read_text(encoding="utf-8")
        stripped = "\n".join(line for line in body.splitlines() if not line.lstrip().startswith("#"))
        match = SKIP_AND_SUCCEED.search(stripped)
        if match:
            offenders.append(f"{script.relative_to(ROOT)}: skips on missing {match.group(1)!r} and exits 0")
    assert not offenders, "gate scripts that treat a missing tool as success:\n  " + "\n  ".join(offenders)


def test_at_least_one_gate_script_was_examined() -> None:
    """A path glob that matches nothing would make the check above vacuous."""
    assert _gate_scripts(), "no gate shell scripts found; the Makefile scan is broken"


# --------------------------------------------------------------------------
# Executed: the measurement
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def bare_checkout(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A tree holding only git-tracked files, so there is no `.venv` to fall back to.

    Args:
        tmp_path_factory: pytest factory for a module-scoped temporary directory.

    Returns:
        Root of the extracted checkout.
    """
    target = tmp_path_factory.mktemp("bare_checkout")
    archive = target / "tree.tar"
    with open(archive, "wb") as handle:
        subprocess.run(
            ["git", "-C", str(ROOT), "archive", "HEAD"],
            stdout=handle,
            check=True,
            timeout=180,
        )
    with tarfile.open(archive) as tar:
        # `filter="data"` is the 3.14 default and is explicit here so the behaviour
        # does not change under the version bump.
        tar.extractall(target, filter="data")
    archive.unlink()
    return target


@pytest.mark.skipif(shutil.which("make") is None, reason="make is not installed")
@pytest.mark.parametrize("target", GATE_TARGETS)
def test_gate_fails_when_its_tool_is_absent(target: str, bare_checkout: Path) -> None:
    """Run the gate with a PATH that has no linters. Exit 0 would be the defect.

    This is the check the whole file exists for: it does not read the recipe and
    reason about it, it runs the recipe in the condition being guarded against.
    """
    env = dict(os.environ, PATH="/usr/bin:/bin")
    env.pop("VIRTUAL_ENV", None)
    proc = subprocess.run(
        ["make", target],
        cwd=bare_checkout,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert proc.returncode != 0, (
        f"`make {target}` exited 0 with no linters on PATH, so it cannot distinguish "
        f"'nothing to report' from 'never ran'.\nstdout:\n{proc.stdout[-1500:]}\n"
        f"stderr:\n{proc.stderr[-1500:]}"
    )


# --------------------------------------------------------------------------
# Recorded, not enforced
# --------------------------------------------------------------------------


def test_no_shell_script_ors_away_a_captured_exit_code() -> None:
    """A script that records `$?` and then ORs it away cannot fail.

    `scripts/lint_phase7_templates.sh` was the instance: it captured `RC=$?` from
    cfn-lint and then decided with
    `[[ $RC -eq 0 ]] || [[ "$ERR_LINES" == "0" ]]`, so any exit code was reported as
    OK provided no output line began with an `E`. Measured before removal: cfn-lint
    exited 12 and the script printed `OK (exit=12, 0 errors)`. It was deleted on
    2026-08-15 — `make lint-cfn` runs the same pinned CLI binary over a superset of
    the templates in 21 seconds and actually fails.

    This closes the class instead of tracking that one file: the same shape in any
    script under scripts/ would fail the same silent way, and a test pinned to a
    deleted path skips forever and protects nothing.
    """
    captures_rc = re.compile(r"\b(RC|rc|STATUS|status|EXIT|exit_code)\s*=\s*\$\?")
    ors_it_away = re.compile(r"\[\[?\s*\$\{?(RC|rc|STATUS|status|EXIT|exit_code)\}?\s+-eq\s+0\s*\]\]?\s*\|\|")

    offenders: list[str] = []
    for script in sorted((ROOT / "scripts").rglob("*.sh")):
        body = script.read_text(encoding="utf-8", errors="ignore")
        stripped = "\n".join(line for line in body.splitlines() if not line.lstrip().startswith("#"))
        if captures_rc.search(stripped) and ors_it_away.search(stripped):
            offenders.append(str(script.relative_to(ROOT)))
    assert not offenders, (
        "these scripts capture an exit code and then disjoin it away, so they report "
        "success regardless of what the tool returned:\n  " + "\n  ".join(offenders)
    )


def test_the_shell_script_scan_is_not_vacuous() -> None:
    """A glob matching no scripts would make the check above pass trivially."""
    scripts = list((ROOT / "scripts").rglob("*.sh"))
    assert len(scripts) > 5, f"only {len(scripts)} shell scripts found under scripts/"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
