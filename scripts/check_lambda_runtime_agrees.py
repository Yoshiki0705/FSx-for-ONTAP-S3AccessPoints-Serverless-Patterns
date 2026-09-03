#!/usr/bin/env python3
"""Check that every place naming a Python version for Lambda agrees with PY_VERSION.

## The gap being closed

`Makefile` already declares the version once and says so:

    # Target Python version — must match the Lambda runtime in the SAM templates
    # (`Runtime: python3.13`). Declared once here so `install`, the interpreter
    # fallback, and the venv freshness check cannot drift apart.
    PY_VERSION := 3.13

Nothing verified the "must match". `scripts/check_runtime_pins_agree.py` has a
similar name and compares *dependency* pins between pyproject.toml and
requirements.txt; it never reads a Lambda runtime. `make drift` had no runtime
entry either.

So the version is repeated in 350+ places with no single source: 325
`Runtime: python3.13` lines across the SAM and CloudFormation templates, 26
`PYTHON_3_13` tokens in the portal's CDK, and one in a CDK assertion test. Raising
`PY_VERSION` alone changes which interpreter runs the tests and nothing that gets
deployed. Raising some templates and not others deploys two runtimes from one
repository, and the templates are independent stacks, so no build step would ever
put the two side by side.

This is not urgent work — `python3.13` is projected to deprecate on 2029-06-30 —
but the count is exactly why it needs to be mechanical before then.

## What is compared

| Site | Rule |
|---|---|
| `Runtime: pythonX.Y` in tracked CFn/SAM templates | equals `PY_VERSION` |
| `PYTHON_X_Y` in tracked TypeScript | equals `PY_VERSION` |
| `compatibleRuntimes: [...]` on a CDK layer | contains `PY_VERSION` |
| `requires-python` and ruff `target-version` | agree with each other |
| that floor | not newer than `PY_VERSION` |
| `strategy.matrix.python-version` in the workflows | contains `PY_VERSION`, lowest equals the floor |

A layer's `compatibleRuntimes` is a superset by design — a layer may stay
attachable from an older runtime — so extra entries there are not a finding. Every
other site names the version that gets deployed, and there is only one of those.

The source floor is deliberately *below* the runtime (`>=3.12` against
`python3.13`) so the modules stay importable on the older interpreter; that is why
the rule is "not newer" rather than "equal".

Usage:
    python3 scripts/check_lambda_runtime_agrees.py
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

PY_VERSION_RE = re.compile(r"^PY_VERSION\s*:?=\s*(\d+\.\d+)\s*$", re.M)
TEMPLATE_RUNTIME_RE = re.compile(r"Runtime:\s*python(\d+\.\d+)")
CDK_TOKEN_RE = re.compile(r"PYTHON_(\d+)_(\d+)")
COMPATIBLE_RUNTIMES_RE = re.compile(r"compatibleRuntimes\s*:\s*\[(.*?)\]", re.S)
RUFF_TARGET_RE = re.compile(r"^py(\d)(\d+)$")
MATRIX_PYTHON_RE = re.compile(r"python-version\s*:\s*\[([^\]]*)\]")
QUOTED_VERSION_RE = re.compile(r"['\"](\d+\.\d+)['\"]")

TEMPLATE_SUFFIXES = {".yaml", ".yml"}
CDK_SUFFIXES = {".ts"}

Version = tuple[int, int]


def parse_version(text: str) -> Version:
    """Turn ``"3.13"`` into ``(3, 13)``.

    Args:
        text: Dotted major.minor version.

    Returns:
        The version as a comparable tuple.
    """
    major, minor = text.split(".", 1)
    return int(major), int(minor)


def format_version(version: Version) -> str:
    """Render ``(3, 13)`` as ``"3.13"``.

    Args:
        version: Major/minor tuple.

    Returns:
        The dotted form.
    """
    return f"{version[0]}.{version[1]}"


def tracked_files(root: Path) -> list[Path]:
    """List git-tracked files, as paths relative to ``root``.

    Build artefacts under ``.aws-sam/`` hold copies of the templates and are not
    tracked, so asking git rather than globbing keeps them out. A stale artefact
    naming an older runtime is not drift — it is a directory `make clean` removes.

    Args:
        root: Repository root.

    Returns:
        Relative paths of every tracked file.
    """
    out = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "ls-files", "-z"],  # noqa: S607 - git resolved from PATH by design
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [Path(name) for name in out.split("\0") if name]


def line_of(text: str, offset: int) -> int:
    """Return the 1-based line number containing ``offset``.

    Args:
        text: The searched text.
        offset: Character offset into ``text``.

    Returns:
        The line number.
    """
    return text.count("\n", 0, offset) + 1


def blank_compatible_runtimes(text: str) -> str:
    """Replace each ``compatibleRuntimes: [...]`` body with spaces.

    Length is preserved so line numbers computed afterwards still point at the
    right source line.

    Args:
        text: TypeScript source.

    Returns:
        The source with the list bodies blanked out.
    """
    out = list(text)
    for match in COMPATIBLE_RUNTIMES_RE.finditer(text):
        for index in range(match.start(1), match.end(1)):
            if out[index] != "\n":
                out[index] = " "
    return "".join(out)


def template_findings(path: Path, text: str, expected: Version) -> list[str]:
    """Report ``Runtime:`` declarations that disagree with ``expected``.

    Args:
        path: Path used in the message.
        text: File contents.
        expected: The version from ``PY_VERSION``.

    Returns:
        One message per disagreeing declaration.
    """
    findings = []
    for match in TEMPLATE_RUNTIME_RE.finditer(text):
        found = parse_version(match.group(1))
        if found != expected:
            findings.append(f"{path}:{line_of(text, match.start())}  Runtime: python{match.group(1)}")
    return findings


def cdk_findings(path: Path, text: str, expected: Version) -> list[str]:
    """Report CDK runtime tokens that disagree with ``expected``.

    Tokens inside a ``compatibleRuntimes`` list are excluded; those are checked by
    `compatible_runtimes_findings` instead, which asks whether the pinned runtime
    is present rather than whether it is the only entry.

    Args:
        path: Path used in the message.
        text: TypeScript source.
        expected: The version from ``PY_VERSION``.

    Returns:
        One message per disagreeing token.
    """
    scannable = blank_compatible_runtimes(text)
    findings = []
    for match in CDK_TOKEN_RE.finditer(scannable):
        found = (int(match.group(1)), int(match.group(2)))
        if found != expected:
            findings.append(f"{path}:{line_of(text, match.start())}  {match.group(0)}")
    return findings


def compatible_runtimes_findings(path: Path, text: str, expected: Version) -> list[str]:
    """Report ``compatibleRuntimes`` lists that omit ``expected``.

    Args:
        path: Path used in the message.
        text: TypeScript source.
        expected: The version from ``PY_VERSION``.

    Returns:
        One message per list that cannot be attached from the pinned runtime.
    """
    want = f"PYTHON_{expected[0]}_{expected[1]}"
    findings = []
    for match in COMPATIBLE_RUNTIMES_RE.finditer(text):
        if want not in match.group(1):
            listed = ", ".join(m.group(0) for m in CDK_TOKEN_RE.finditer(match.group(1))) or "(none)"
            findings.append(f"{path}:{line_of(text, match.start())}  lists {listed}, not {want}")
    return findings


def read_py_version(path: Path) -> Version | None:
    """Read ``PY_VERSION`` from the Makefile.

    Args:
        path: Path to the ``Makefile``.

    Returns:
        The declared version, or ``None`` when the assignment is absent.
    """
    match = PY_VERSION_RE.search(path.read_text(encoding="utf-8"))
    return parse_version(match.group(1)) if match else None


def read_source_floor(path: Path) -> tuple[Version | None, Version | None]:
    """Read the declared source-compatibility floor from pyproject.toml.

    Args:
        path: Path to ``pyproject.toml``.

    Returns:
        ``(requires-python floor, ruff target-version)``, each ``None`` when the
        setting is absent or is not a plain ``>=X.Y`` / ``pyXY`` form.
    """
    data = tomllib.loads(path.read_text(encoding="utf-8"))

    requires = data.get("project", {}).get("requires-python", "")
    floor_match = re.fullmatch(r">=\s*(\d+\.\d+)", requires.strip())
    floor = parse_version(floor_match.group(1)) if floor_match else None

    target = data.get("tool", {}).get("ruff", {}).get("target-version", "")
    target_match = RUFF_TARGET_RE.fullmatch(target.strip())
    ruff = (int(target_match.group(1)), int(target_match.group(2))) if target_match else None

    return floor, ruff


def read_matrices(paths: list[Path]) -> list[tuple[Path, list[Version]]]:
    """Read every ``python-version`` matrix list out of the given workflows.

    Parsed with a regex rather than a YAML loader on purpose: the loader would
    also have to be told which job holds the matrix, and pinning the job name here
    turns a rename into a failure that says nothing about runtimes.

    Args:
        paths: Workflow files to read.

    Returns:
        ``(path, versions)`` for each inline matrix list found.
    """
    out = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for match in MATRIX_PYTHON_RE.finditer(text):
            versions = [parse_version(m.group(1)) for m in QUOTED_VERSION_RE.finditer(match.group(1))]
            if versions:
                out.append((path, versions))
    return out


def main(argv: list[str] | None = None) -> int:
    """Compare every runtime declaration against ``PY_VERSION``.

    Args:
        argv: Command-line arguments. ``None`` reads ``sys.argv``.

    Returns:
        ``0`` when every site agrees, ``1`` otherwise.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="repository root to scan")
    parser.add_argument("--makefile", type=Path, default=None)
    parser.add_argument("--pyproject", type=Path, default=None)
    args = parser.parse_args(argv)

    root: Path = args.root
    makefile: Path = args.makefile or root / "Makefile"
    pyproject: Path = args.pyproject or root / "pyproject.toml"

    expected = read_py_version(makefile)
    if expected is None:
        print(f"ERROR: no `PY_VERSION := X.Y` assignment in {makefile}.")
        print("   That assignment is the single source this check compares against.")
        return 1
    pinned = format_version(expected)
    print(f"PY_VERSION = {pinned} ({makefile.relative_to(root) if makefile.is_relative_to(root) else makefile})")

    templates: list[Path] = []
    cdk: list[Path] = []
    for relative in tracked_files(root):
        if relative.suffix.lower() in TEMPLATE_SUFFIXES and ".github/workflows" not in relative.as_posix():
            templates.append(relative)
        elif relative.suffix.lower() in CDK_SUFFIXES:
            cdk.append(relative)

    template_hits = 0
    cdk_hits = 0
    compatible_lists = 0
    findings: list[str] = []

    for relative in templates:
        text = (root / relative).read_text(encoding="utf-8", errors="replace")
        template_hits += len(TEMPLATE_RUNTIME_RE.findall(text))
        findings += template_findings(relative, text, expected)

    for relative in cdk:
        text = (root / relative).read_text(encoding="utf-8", errors="replace")
        cdk_hits += len(CDK_TOKEN_RE.findall(blank_compatible_runtimes(text)))
        compatible_lists += len(COMPATIBLE_RUNTIMES_RE.findall(text))
        findings += cdk_findings(relative, text, expected)
        findings += compatible_runtimes_findings(relative, text, expected)

    print(
        f"Scanned {template_hits} template runtime declaration(s), {cdk_hits} CDK token(s), {compatible_lists} layer compatibility list(s)."
    )

    # A scanner that reads nothing reports a clean tree. Both corpora are large and
    # non-optional here, so an empty result means the discovery broke, not that the
    # declarations went away.
    if template_hits == 0 or cdk_hits == 0:
        print("\nERROR: found no declarations to compare.")
        print(f"   templates matched: {template_hits}, CDK tokens matched: {cdk_hits}")
        print("   Expected hundreds of both. The file discovery or the patterns are broken,")
        print("   and a check that scans nothing passes for the wrong reason.")
        return 1

    if findings:
        print(f"\n{len(findings)} declaration(s) disagree with PY_VERSION = {pinned}:\n")
        for line in findings:
            print(f"  {line}")
        print(
            f"\n   Every site above names the runtime that gets deployed, so they cannot\n"
            f"   differ from each other. Set them all to {pinned}, or change PY_VERSION\n"
            f"   and this check will tell you the rest.\n"
            f"   Deployed templates are independent stacks: nothing else in this\n"
            f"   repository ever puts two of them side by side to notice."
        )
        return 1

    floor, ruff_target = read_source_floor(pyproject)
    if floor is None or ruff_target is None:
        print("\nERROR: could not read the source-compatibility floor from pyproject.toml.")
        print(f"   requires-python parsed as {floor}, ruff target-version as {ruff_target}.")
        print("   Both are needed: they decide which interpreters the modules must import on.")
        return 1
    if floor != ruff_target:
        print(
            f"\nERROR: requires-python is >={format_version(floor)} but ruff targets py{ruff_target[0]}{ruff_target[1]}."
        )
        print("   ruff would then accept syntax the declared floor cannot parse, or reject")
        print("   syntax the floor allows. Set both to the same version.")
        return 1
    if floor > expected:
        print(f"\nERROR: the source floor (>={format_version(floor)}) is newer than the Lambda runtime ({pinned}).")
        print("   The deployed interpreter cannot run code the project declares it requires.")
        return 1
    print(f"Source floor = {format_version(floor)} (requires-python and ruff agree, not newer than the runtime).")

    matrices = read_matrices(sorted((root / ".github" / "workflows").glob("*.y*ml")))
    if not matrices:
        print("\nERROR: no `python-version: [...]` matrix found in .github/workflows/.")
        print("   Without one, no workflow proves the modules import on the deployed runtime.")
        return 1
    for path, versions in matrices:
        shown = ", ".join(format_version(v) for v in versions)
        relative = path.relative_to(root) if path.is_relative_to(root) else path
        if expected not in versions:
            print(f"\nERROR: {relative} tests [{shown}] and not {pinned}.")
            print("   The deployed runtime is the one version that has to be in the matrix.")
            return 1
        if min(versions) != floor:
            print(f"\nERROR: {relative} tests [{shown}], lowest {format_version(min(versions))},")
            print(f"   but requires-python declares >={format_version(floor)}.")
            print("   Testing below the floor gates the build on a version the project does not")
            print("   support; testing above it leaves the claim unverified. Make them equal.")
            return 1
        print(f"Matrix in {relative} = [{shown}].")

    print(f"\nEvery Lambda runtime declaration agrees with PY_VERSION = {pinned}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
