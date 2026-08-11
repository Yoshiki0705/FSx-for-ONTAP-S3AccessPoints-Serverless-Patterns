#!/usr/bin/env python3
"""Check that runtime pins shared by pyproject.toml and requirements.txt agree.

Runtime dependencies are pinned in both files, and which one takes effect depends
on how the environment was built: every CI workflow and the Makefile install from
`requirements.txt`, while `pyproject.toml` is what anyone installing this
repository as a package gets. A comment in pyproject.toml already asked for the
two to be kept equal — and Renovate broke it anyway, raising boto3 to 1.43.68 in
pyproject.toml and leaving requirements.txt on 1.43.67. Renovate treats the two
files as separate managers, so this will recur.

Nothing noticed. The tests ran against the requirements.txt version, the package
metadata claimed the other, and neither is wrong on its own terms.

Only shared names are compared. A dependency declared in one file and not the
other is intentional (`aws-xray-sdk` is optional and belongs to requirements.txt
alone), so its absence is not a finding.

Usage:
    python3 scripts/check_runtime_pins_agree.py
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# `name==version`, ignoring extras and environment markers.
PIN = re.compile(r"^([A-Za-z0-9_.-]+)\s*==\s*([^\s;]+)")


def parse_pyproject(path: Path) -> dict[str, str]:
    """Read the pinned runtime dependencies from pyproject.toml.

    Args:
        path: Path to `pyproject.toml`.

    Returns:
        Lowercased distribution name -> pinned version. Entries that are not an
        exact `==` pin are skipped.
    """
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for spec in data.get("project", {}).get("dependencies", []):
        match = PIN.match(spec.strip())
        if match:
            out[match.group(1).lower()] = match.group(2)
    return out


def parse_requirements(path: Path) -> dict[str, str]:
    """Read the pinned dependencies from a requirements file.

    Args:
        path: Path to `requirements.txt`.

    Returns:
        Lowercased distribution name -> pinned version.
    """
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        match = PIN.match(line)
        if match:
            out[match.group(1).lower()] = match.group(2)
    return out


def disagreements(pyproject: dict[str, str], requirements: dict[str, str]) -> list[tuple[str, str, str]]:
    """Find shared names whose pinned versions differ.

    Args:
        pyproject: Output of `parse_pyproject`.
        requirements: Output of `parse_requirements`.

    Returns:
        `(name, pyproject version, requirements version)` for each disagreement,
        sorted by name. Names present in only one file are ignored.
    """
    return sorted(
        (name, pyproject[name], requirements[name])
        for name in set(pyproject) & set(requirements)
        if pyproject[name] != requirements[name]
    )


def main(argv: list[str] | None = None) -> int:
    """Compare the two pin sets.

    Args:
        argv: Command-line arguments. `None` reads `sys.argv`.

    Returns:
        `0` when every shared pin matches, `1` otherwise.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pyproject", type=Path, default=REPO_ROOT / "pyproject.toml")
    parser.add_argument("--requirements", type=Path, default=REPO_ROOT / "requirements.txt")
    args = parser.parse_args(argv)

    pyproject = parse_pyproject(args.pyproject)
    requirements = parse_requirements(args.requirements)
    shared = set(pyproject) & set(requirements)
    found = disagreements(pyproject, requirements)

    print(f"Comparing {len(shared)} shared runtime pin(s)...")
    if found:
        print(f"\n{len(found)} pin(s) disagree:\n")
        for name, in_pyproject, in_requirements in found:
            print(f"  {name}")
            print(f"    pyproject.toml   {in_pyproject}")
            print(f"    requirements.txt {in_requirements}")
        print(
            "\n   Which one applies depends on how the environment was built: CI and\n"
            "   the Makefile install from requirements.txt, while pyproject.toml is\n"
            "   what installing this repository as a package gives. Set both to the\n"
            "   same version.\n"
            "   Renovate updates them as separate managers, so a dependency PR that\n"
            "   touches only one file is the expected cause."
        )
        return 1

    print("All shared runtime pins agree.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
