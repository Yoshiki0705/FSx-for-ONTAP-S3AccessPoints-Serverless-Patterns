#!/usr/bin/env python3
"""Fail when a lint or scan tool resolves to a version other than the pinned one.

## Why this exists

`requirements-dev.txt` exact-pins every dev tool so a laptop and a CI runner
reach the same verdict on the same tree. Nothing enforced that the pin is what
actually ran. On the machine this was written on:

    ruff      pinned 0.15.17   on PATH (homebrew) 0.15.20
    cfn-lint  pinned 1.53.3    on PATH (homebrew) 1.52.1

Both were installed for unrelated reasons and both came first on PATH. Any recipe
calling a bare `ruff` or `cfn-lint` therefore linted with a different rule set
than the pipeline and reported success, and the disagreement is invisible in the
output: a rule that does not exist in 1.52.1 produces no finding, not an error.
The Makefile resolves `.venv/bin/<tool>` for exactly this reason, and one tool
having been left out of that convention is what prompted this check.

## Why it fails instead of warning

A warning here warns about a silent divergence, which makes it the same thing it
is warning about: something that scrolls past while the wrong tool keeps
answering. The whole value of an exact pin is that violating it stops the build.

## What "resolved" means

The tool the *build* would use, not the first one on PATH: `.venv/bin/<tool>`
when present, otherwise PATH. That mirrors the Makefile's `VENV_*` variables, so
this check answers the question that matters — would `make lint` have used the
pinned version — rather than auditing PATH in the abstract.

A missing `.venv` is not a finding. A clone has none, and CI installs the pins
directly into the runner's environment; there the PATH copy *is* the pinned one,
and this check confirms that rather than complaining about the layout.

## Usage

    python3 scripts/check_tool_versions.py            # all pinned tools
    python3 scripts/check_tool_versions.py ruff        # one tool
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = ROOT / "requirements-dev.txt"

# Tools whose version is asserted. Restricted to the ones a recipe or workflow
# invokes as a binary: a library pin is enforced by the installer, but a binary
# can be shadowed by another copy on PATH, which is the failure being caught.
# `--version` output differs per tool, so the version is extracted by regex
# rather than assumed to be the last field.
CHECKED: dict[str, str] = {
    "ruff": r"(\d+\.\d+\.\d+)",
    "cfn-lint": r"(\d+\.\d+\.\d+)",
    "bandit": r"(\d+\.\d+\.\d+)",
    "pytest": r"(\d+\.\d+\.\d+)",
}

PIN = re.compile(r"^([A-Za-z0-9_.\-]+)(?:\[[^\]]*\])?==([0-9][^\s#]*)")


def pins() -> dict[str, str]:
    """Exact pins declared in requirements-dev.txt.

    Returns:
        Mapping of lowercased distribution name to pinned version. Only `==`
        pins are returned; a range cannot be asserted against a single binary.
    """
    found: dict[str, str] = {}
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = PIN.match(line)
        if match:
            found[match.group(1).lower()] = match.group(2)
    return found


def resolve(tool: str) -> tuple[Path | None, str]:
    """The binary the build would use, and where it came from.

    Args:
        tool: Executable name, e.g. ``"ruff"``.

    Returns:
        Tuple of the resolved path (None when the tool is absent) and a short
        label naming the source, for use in the failure message.
    """
    venv = ROOT / ".venv" / "bin" / tool
    if venv.is_file():
        return venv, ".venv"
    found = shutil.which(tool)
    if found:
        return Path(found), "PATH"
    return None, "absent"


def installed_version(binary: Path, pattern: str) -> str | None:
    """Version reported by ``binary --version``, or None when unreadable.

    Args:
        binary: Executable to interrogate.
        pattern: Regex with one group capturing the version.

    Returns:
        The captured version string, or None when the tool could not be run or
        printed nothing matching.
    """
    try:
        proc = subprocess.run(
            [str(binary), "--version"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.search(pattern, f"{proc.stdout}\n{proc.stderr}")
    return match.group(1) if match else None


def main(argv: list[str]) -> int:
    """Compare each pinned tool's resolved version against its pin.

    Args:
        argv: Optional tool names to restrict the check to.

    Returns:
        1 when any resolved tool disagrees with its pin or could not be read,
        otherwise 0. A tool that is simply not installed is reported and skipped
        — the recipe that needs it fails on its own, loudly, and this check runs
        in places where not every tool is expected.
    """
    declared = pins()
    wanted = argv or sorted(CHECKED)

    problems: list[str] = []
    lines: list[str] = []

    for tool in wanted:
        if tool not in CHECKED:
            problems.append(f"{tool}: not a version-checked tool. Known: {', '.join(sorted(CHECKED))}")
            continue
        pinned = declared.get(tool)
        if pinned is None:
            problems.append(
                f"{tool}: no `==` pin in requirements-dev.txt. Add one, or drop the tool "
                "from CHECKED in this script — an unpinned binary cannot be asserted."
            )
            continue

        binary, source = resolve(tool)
        if binary is None:
            lines.append(f"  {tool:<10} pinned {pinned:<10} not installed (skipped)")
            continue

        actual = installed_version(binary, CHECKED[tool])
        if actual is None:
            problems.append(f"{tool}: could not read a version from `{binary} --version`.")
            continue

        if actual != pinned:
            problems.append(
                f"{tool}: resolved {actual} from {source} ({binary}) but "
                f"requirements-dev.txt pins {pinned}.\n"
                f"      The build would lint with {actual}, so its verdict need not match CI's. Fix with:\n"
                f"        make install            # installs the pin into .venv, which is resolved first\n"
                f"      or, if {source} is intentional, change the pin in requirements-dev.txt and rerun CI."
            )
            continue

        lines.append(f"  {tool:<10} pinned {pinned:<10} {actual} from {source}")

    if problems:
        print("tool versions disagree with requirements-dev.txt:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print(
            "\nA tool that is not the pinned one applies a different rule set and still "
            "reports success, which is why this fails rather than warns.",
            file=sys.stderr,
        )
        return 1

    print("TOOL VERSIONS: PASS")
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
