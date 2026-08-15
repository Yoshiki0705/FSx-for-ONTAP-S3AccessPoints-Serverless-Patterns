"""A gate wired into `make drift` must also run in CI, and the reverse.

## The failure being closed

`make drift` and the workflows are two separate lists of checks. Nothing made
them agree. A check added to the Makefile runs for whoever types `make drift` and
never runs on a pull request; a check added to a workflow and not to the Makefile
cannot be reproduced locally when it fails.

This is the same shape that already cost this repository ~790 tests: the Makefile
`test` target and `ci.yml` each kept a hand-written list of pattern directories,
CI reached 37 and the Makefile 16, and the difference ran nowhere. That was fixed
for test directories by making `pattern-test-dirs.txt` the single source. The
*checks* had no equivalent, and the gates added on 2026-08-15 landed in `make
drift` only — which would have made them local-only conveniences rather than
gates.

## Why the assertion is "referenced somewhere in .github/workflows"

Not "runs in a specific job": which job a check belongs in is a scheduling
decision that changes, and pinning it here would fail on every reorganisation
while proving nothing extra. What matters is that a pull request cannot merge
without the check having run.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
MAKEFILE = ROOT / "Makefile"
WORKFLOWS = ROOT / ".github" / "workflows"

# Checks that are deliberately local-only, with the reason. Each needs something a
# runner does not have, so requiring them in CI would mean requiring credentials
# or network in a pull request.
# Checks that are deliberately not run from a workflow at all, with the reason.
# `check_published_articles.py` is NOT here: it runs in
# published-articles-check.yml on a schedule. Scheduled is still CI — the
# distinction this file cares about is "runs somewhere automatically" versus "runs
# only when a person types the command", and a weekly job is the former.
LOCAL_ONLY: dict[str, str] = {
    "scripts/check_ontap_connection.py": "calls AWS and needs credentials plus a deployed file system",
    "scripts/propose_cleanup.py": "needs AWS credentials; read-only inventory, not a gate",
}


def _drift_recipe() -> str:
    """The recipe lines of the `drift` target, comments removed.

    Returns:
        The commands `make drift` would run, joined by newlines.
    """
    text = MAKEFILE.read_text(encoding="utf-8")
    match = re.search(r"^drift:\n((?:\t.*\n|#.*\n)*)", text, re.M)
    assert match, "could not locate the `drift` target in the Makefile"
    return "\n".join(line.strip() for line in match.group(1).splitlines() if line.startswith("\t"))


def _workflow_text() -> str:
    """Every workflow file concatenated, for reference lookups.

    Returns:
        The combined contents of `.github/workflows/*.y*ml`.
    """
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(WORKFLOWS.glob("*.y*ml")))


def drift_scripts() -> set[str]:
    """Check scripts and test modules invoked by `make drift`.

    Returns:
        Repository-relative paths referenced in the drift recipe.
    """
    return set(re.findall(r"(scripts/[A-Za-z0-9_./-]+\.(?:py|sh))", _drift_recipe()))


# --------------------------------------------------------------------------


def test_every_drift_check_runs_in_ci() -> None:
    """The measurement: a gate that only `make drift` runs is not a gate."""
    workflows = _workflow_text()
    missing = sorted(
        path
        for path in drift_scripts()
        if path not in LOCAL_ONLY
        # A pytest module under scripts/tests/ is covered by the suite-wide run in
        # test.yaml (`pytest scripts/tests/ -v`), so it need not be named.
        and not path.startswith("scripts/tests/")
        and path not in workflows
    )
    assert not missing, (
        "these checks run in `make drift` but in no workflow, so a pull request "
        "can merge without them:\n  "
        + "\n  ".join(missing)
        + "\n\nAdd each to .github/workflows/, or record it in LOCAL_ONLY with the reason."
    )


def test_scripts_tests_directory_runs_in_ci() -> None:
    """The exemption above depends on the whole suite running; verify that."""
    workflows = _workflow_text()
    assert "scripts/tests/" in workflows, (
        "no workflow runs scripts/tests/, so the pytest modules invoked by `make drift` "
        "are exempted from the CI check on a premise that no longer holds"
    )


def test_local_only_entries_are_real_and_justified() -> None:
    """A stale exemption silently excuses a check that could be running."""
    for path, reason in LOCAL_ONLY.items():
        assert (ROOT / path).is_file(), f"LOCAL_ONLY names {path}, which does not exist"
        assert len(reason) > 25, f"LOCAL_ONLY[{path}] has no substantive reason"


def test_local_only_entries_are_not_in_a_workflow() -> None:
    """If one became runnable in CI, the exemption should be removed, not kept."""
    workflows = _workflow_text()
    contradictions = sorted(path for path in LOCAL_ONLY if path in workflows)
    assert not contradictions, (
        "these are marked local-only but a workflow runs them; drop them from LOCAL_ONLY: " + ", ".join(contradictions)
    )


def test_the_new_gates_are_present_in_both() -> None:
    """Regression pin for the three gates added on 2026-08-15."""
    drift = _drift_recipe()
    workflows = _workflow_text()
    assert "check_tool_versions.py" in drift, "the pinned-version gate left `make drift`"
    assert "check_tool_versions.py" in workflows, "the pinned-version gate left CI"
    for module in ("test_gate_integrity.py", "test_test_dir_coverage.py", "test_makefile_phony.py"):
        assert module in drift, f"{module} left `make drift`"


def test_the_scan_is_not_vacuous() -> None:
    """An empty recipe or workflow glob would make every check above pass."""
    assert len(drift_scripts()) > 8, f"only {len(drift_scripts())} drift checks found; the recipe parse is broken"
    assert len(_workflow_text()) > 5000, "workflow files not read; the glob is broken"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
