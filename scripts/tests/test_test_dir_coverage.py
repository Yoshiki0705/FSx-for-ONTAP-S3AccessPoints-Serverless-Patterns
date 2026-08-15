"""Every tests/ directory must run somewhere, or be excluded on the record.

## The failure being closed

A `tests/` directory that no runner lists does not fail. It passes locally when
someone types the path by hand, and it is absent from every pipeline. The tests
inside keep being written, keep being green on the author's machine, and protect
nothing.

It had already happened twice here. The Makefile and `ci.yml` each kept their own
hand-written list; CI reached 37 directories and the Makefile 16, and 13
directories holding roughly 790 tests were in neither. That was fixed by moving
the list into `pattern-test-dirs.txt` as a single source of truth. The move did
not make the list *complete* — on 2026-08-15 three more directories were still
outside it:

    solutions/amplify-portal/functions/thumbnails   37 tests
    solutions/amplify-portal/functions/snapshots    13 tests
    security                                         3 tests

53 passing tests, running nowhere. Adding them fixes the instance. This closes the
class: a new `tests/` directory must be listed or explicitly excluded, and an
exclusion has to say why.

## Why exclusions live in the manifest's comments

An exclusion is a claim that needs a reason a reader can check — "requires a
deployed stack" is verifiable, an unexplained absence is not. Parsing them out of
the comment block keeps the reason next to the decision instead of in a separate
allowlist that drifts away from it.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
MANIFEST = ROOT / "pattern-test-dirs.txt"

# Invoked by name rather than through the manifest loop: the Makefile `test` target
# and the workflows run these directly, with coverage settings of their own.
RUN_DIRECTLY = {
    "shared",  # make test, test.yaml, ci.yml
    "scripts",  # make test, test.yaml
    "operations",  # make test-ops, and per-pattern entries in the manifest
}

# Directories that hold no test file. Not an exclusion to justify — there is
# nothing to run — but they must not be reported as uncovered either.
EMPTY_IS_FINE = {
    "solutions/event-driven/fpolicy",
    "solutions/amplify-portal",
    "tests",
}


def tracked_test_dirs() -> set[str]:
    """Every directory containing a tracked test file, as a repo-relative parent.

    Uses git rather than the filesystem: a `tests/` directory that exists only on
    one machine is not something a pipeline can be expected to run, and counting
    it would produce a finding nobody else can reproduce.

    Returns:
        Parent directories of tracked ``tests/`` trees, e.g. ``{"shared", "security"}``.
    """
    proc = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--", "*/tests/*.py", "tests/*.py", "tests/*/*.py"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    found: set[str] = set()
    for line in proc.stdout.splitlines():
        path = Path(line)
        if not path.name.startswith("test_") and not path.name.endswith("_test.py"):
            continue
        parts = path.parts
        if "tests" not in parts:
            continue
        index = parts.index("tests")
        parent = "/".join(parts[:index])
        found.add(parent or "tests")
    return found


def manifest_entries() -> set[str]:
    """Directories listed for the per-pattern pytest loop.

    Returns:
        Entries with comments and blank lines removed.
    """
    return {
        line.strip()
        for line in MANIFEST.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def stated_exclusions() -> dict[str, str]:
    """Paths the manifest's comment block declares excluded, with the stated reason.

    Returns:
        Mapping of repo-relative path to the reason text following it.
    """
    lines = MANIFEST.read_text(encoding="utf-8").splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.startswith("# Excluded on purpose:"))
    except StopIteration:
        return {}

    found: dict[str, str] = {}
    current: list[str] | None = None
    for raw in lines[start + 1 :]:
        if not raw.startswith("#"):
            break
        body = raw[1:].rstrip()
        if not body.strip():
            break  # a bare `#` closes the block; prose follows it
        # An entry begins in the path column (3 spaces in). A reason that wraps is
        # indented past it. Distinguishing the two by indent is what makes a
        # wrapped reason part of its entry instead of a new path — the previous
        # version read every continuation line as its own reasonless exclusion.
        entry = re.match(r"^ {3}(\S.*)$", body)
        if entry:
            # Path column and reason column are separated by a run of 2+ spaces.
            # Splitting on that rather than matching a path shape is what handles
            # the one entry listing two comma-separated paths.
            parts = re.split(r"\s{2,}", entry.group(1), maxsplit=1)
            paths, reason = parts[0], (parts[1] if len(parts) > 1 else "")
            current = [reason]
            for path in paths.split(","):
                path = path.strip()
                if path:
                    found[path] = current  # type: ignore[assignment]
            continue
        if current is not None and re.match(r"^ {4,}\S", body):
            current.append(body.strip())

    # Join each entry's wrapped reason, and expose the parent a runner would see.
    joined = {path: " ".join(reason).strip() for path, reason in found.items()}  # type: ignore[union-attr]
    for path, reason in list(joined.items()):
        if path.startswith("tests/"):
            joined.setdefault("tests", reason)
    return joined


# --------------------------------------------------------------------------


def test_every_tracked_test_dir_runs_or_is_excluded() -> None:
    """The measurement. An unlisted, unexcluded tests/ directory runs nowhere."""
    covered = manifest_entries() | RUN_DIRECTLY | set(stated_exclusions()) | EMPTY_IS_FINE
    orphans = sorted(tracked_test_dirs() - covered)
    assert not orphans, (
        "these directories hold tracked tests that no runner lists:\n  "
        + "\n  ".join(orphans)
        + "\n\nAdd each to pattern-test-dirs.txt, or state it under "
        "'# Excluded on purpose:' in that file with the reason."
    )


def test_every_manifest_entry_has_tests() -> None:
    """A listed directory with no tests makes the loop exit 5 and fail the build."""
    missing = sorted(entry for entry in manifest_entries() if not (ROOT / entry / "tests").is_dir())
    assert not missing, "pattern-test-dirs.txt lists directories with no tests/ directory:\n  " + "\n  ".join(missing)


def test_each_exclusion_states_a_reason() -> None:
    """An unexplained exclusion is indistinguishable from an oversight."""
    for path, reason in stated_exclusions().items():
        assert len(reason) > 15, f"exclusion {path!r} has no substantive reason: {reason!r}"


def test_excluded_paths_are_not_also_listed() -> None:
    """Listing and excluding the same path means one of the two is a lie."""
    both = sorted(manifest_entries() & set(stated_exclusions()))
    assert not both, "these are both listed and declared excluded: " + ", ".join(both)


def test_the_three_directories_found_on_2026_08_15_are_listed() -> None:
    """Regression pin for the specific gap this file was written for.

    Named individually because the general check above would also pass if the
    manifest were emptied and everything moved to exclusions.
    """
    entries = manifest_entries()
    for path in (
        "solutions/amplify-portal/functions/thumbnails",
        "solutions/amplify-portal/functions/snapshots",
        "security",
    ):
        assert path in entries, f"{path} holds passing tests that ran nowhere; it must stay listed"


def test_the_scan_is_not_vacuous() -> None:
    """A git glob that matches nothing would make every check above pass."""
    found = tracked_test_dirs()
    assert len(found) > 40, f"only {len(found)} test directories discovered; the git glob is broken"
    assert "shared" in found, "shared/tests not discovered; the git glob is broken"


def test_ci_uses_the_manifest_rather_than_its_own_list() -> None:
    """The two lists drifting apart is the original failure; keep one source."""
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "pattern-test-dirs.txt" in ci, (
        "ci.yml no longer reads pattern-test-dirs.txt, so CI and the Makefile can again examine different trees"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
