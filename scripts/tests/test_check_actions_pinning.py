"""Tests for scripts/check_actions_pinning.py.

The point of these is that the checker is seen rejecting each thing it claims to
reject. The previous version of this script passed on `actions/checkout@v4`
because first-party actions were exempt, and passed on a workflow parked in a
nested `.github/workflows` that GitHub never reads — so its green result meant
less than it looked like.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "check_actions_pinning", REPO_ROOT / "scripts" / "check_actions_pinning.py"
)
assert _spec and _spec.loader
cap = importlib.util.module_from_spec(_spec)
sys.modules["check_actions_pinning"] = cap
_spec.loader.exec_module(cap)

GOOD_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"


def write_workflow(root: Path, name: str, body: str, subdir: str = "") -> Path:
    """Write a workflow file and return its path.

    Args:
        root: Fixture repository root.
        name: Workflow file name, including the suffix.
        body: File contents.
        subdir: Path relative to ``root`` to nest the ``.github/workflows``
            directory under. Empty means the root directory GitHub reads.

    Returns:
        The path the workflow was written to.
    """
    base = root / subdir if subdir else root
    directory = base / ".github" / "workflows"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(body, encoding="utf-8")
    return path


def steps(uses_line: str) -> str:
    """Return a minimal workflow whose single step is ``uses_line``.

    Args:
        uses_line: The ``uses: owner/action@ref`` line under test.

    Returns:
        Workflow YAML as a string.
    """
    return f"""name: t
on: [push]
jobs:
  j:
    runs-on: ubuntu-latest
    steps:
      - {uses_line}
"""


def test_sha_pinned_with_version_comment_passes(tmp_path: Path) -> None:
    write_workflow(tmp_path, "ok.yml", steps(f"uses: actions/checkout@{GOOD_SHA} # v7.0.1"))
    assert cap.main(["--root", str(tmp_path)]) == 0


@pytest.mark.parametrize(
    "action",
    [
        "actions/checkout@v4",
        "github/codeql-action/upload-sarif@v3",
        "ossf/scorecard-action@v2.4.4",
    ],
)
def test_tag_reference_is_rejected_including_first_party(tmp_path: Path, action: str) -> None:
    """`actions/*` and `github/*` used to be exempt. A moved tag is a moved tag."""
    write_workflow(tmp_path, "bad.yml", steps(f"uses: {action}"))
    assert cap.main(["--root", str(tmp_path)]) == 1


def test_sha_without_version_comment_is_rejected(tmp_path: Path) -> None:
    """A bare hash is unreviewable: v4 and v7 look identical."""
    write_workflow(tmp_path, "bare.yml", steps(f"uses: actions/checkout@{GOOD_SHA}"))
    assert cap.main(["--root", str(tmp_path)]) == 1


def test_short_sha_is_rejected(tmp_path: Path) -> None:
    write_workflow(tmp_path, "short.yml", steps("uses: actions/checkout@3d3c42e # v7.0.1"))
    assert cap.main(["--root", str(tmp_path)]) == 1


def test_nested_workflow_directory_is_rejected(tmp_path: Path) -> None:
    """GitHub reads only the root .github/workflows; anything else never runs."""
    write_workflow(tmp_path, "ok.yml", steps(f"uses: actions/checkout@{GOOD_SHA} # v7.0.1"))
    write_workflow(
        tmp_path,
        "validate.yml",
        steps(f"uses: actions/checkout@{GOOD_SHA} # v7.0.1"),
        subdir="infrastructure/lab",
    )
    assert cap.main(["--root", str(tmp_path)]) == 1


def test_nested_directory_detection_ignores_node_modules(tmp_path: Path) -> None:
    write_workflow(tmp_path, "ok.yml", steps(f"uses: actions/checkout@{GOOD_SHA} # v7.0.1"))
    write_workflow(
        tmp_path,
        "ci.yml",
        steps("uses: actions/checkout@v4"),
        subdir="node_modules/some-package",
    )
    assert cap.main(["--root", str(tmp_path)]) == 0


def test_missing_workflow_directory_is_not_a_failure(tmp_path: Path) -> None:
    assert cap.main(["--root", str(tmp_path)]) == 0


def test_yaml_suffix_is_checked_too(tmp_path: Path) -> None:
    write_workflow(tmp_path, "lint.yaml", steps("uses: actions/checkout@v4"))
    assert cap.main(["--root", str(tmp_path)]) == 1


def test_this_repository_passes() -> None:
    """The real workflows, not a fixture."""
    assert cap.main(["--root", str(REPO_ROOT)]) == 0
