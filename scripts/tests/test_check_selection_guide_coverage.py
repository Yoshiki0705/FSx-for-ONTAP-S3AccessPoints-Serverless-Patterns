#!/usr/bin/env python3
"""Tests for the selection-guide coverage check.

The defect this check exists for was a guide that named 16 of 28 use cases and no operations
pattern at all, so the tests that matter are the ones asserting it fires on a gap. A test that
only proved the current tree passes would be satisfied by a check that never fails.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_selection_guide_coverage import is_pattern, missing, patterns  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def _tree(root: Path, deployable: list[str], shared: list[str], guides: dict[str, str]) -> None:
    for rel in deployable:
        (root / rel).mkdir(parents=True, exist_ok=True)
        (root / rel / "template.yaml").write_text("Resources: {}\n", encoding="utf-8")
    for rel in shared:
        (root / rel).mkdir(parents=True, exist_ok=True)
    (root / "docs").mkdir(exist_ok=True)
    for name, body in guides.items():
        (root / "docs" / name).write_text(body, encoding="utf-8")


BOTH = ("pattern-selection-guide.md", "pattern-selection-guide.en.md")


# --- what counts as a pattern ---


def test_a_directory_with_a_template_is_a_pattern(tmp_path: Path) -> None:
    (tmp_path / "template.yaml").write_text("Resources: {}\n", encoding="utf-8")
    assert is_pattern(tmp_path)


def test_a_directory_with_an_amplify_dir_is_a_pattern(tmp_path: Path) -> None:
    """The portal has no template.yaml; it is CDK under amplify/."""
    (tmp_path / "amplify").mkdir()
    assert is_pattern(tmp_path)


def test_a_shared_directory_is_not_a_pattern(tmp_path: Path) -> None:
    """`operations/docs` and `operations/tests` must not be demanded of the guide.

    Decided by contents rather than by a list of names, so this holds for a shared directory
    nobody has created yet.
    """
    (tmp_path / "notes.md").write_text("x", encoding="utf-8")
    assert not is_pattern(tmp_path)


def test_patterns_are_discovered_across_every_family(tmp_path: Path) -> None:
    _tree(
        tmp_path,
        deployable=[
            "solutions/industry/one",
            "solutions/flexcache/two",
            "solutions/amplify-portal",
            "operations/three",
        ],
        shared=["operations/tests", "solutions/industry/.hidden-not-a-dir"],
        guides=dict.fromkeys(BOTH, ""),
    )
    (tmp_path / "solutions" / "amplify-portal" / "template.yaml").unlink()
    (tmp_path / "solutions" / "amplify-portal" / "amplify").mkdir()
    found = patterns(tmp_path)
    assert "solutions/industry/one" in found
    assert "solutions/flexcache/two" in found
    assert "solutions/amplify-portal" in found
    assert "operations/three" in found
    assert "operations/tests" not in found


# --- the check fires on a gap ---


def test_a_pattern_absent_from_the_guide_is_reported(tmp_path: Path) -> None:
    _tree(
        tmp_path,
        deployable=["solutions/industry/present", "solutions/industry/absent"],
        shared=[],
        guides=dict.fromkeys(BOTH, "see solutions/industry/present/ for details\n"),
    )
    gaps = missing(tmp_path)
    assert set(gaps) == set(BOTH)
    for absent in gaps.values():
        assert absent == ["solutions/industry/absent"]


def test_a_gap_in_only_one_locale_is_reported_for_that_locale(tmp_path: Path) -> None:
    """The pair drifted before: the JA guide was edited and the EN one was not."""
    _tree(
        tmp_path,
        deployable=["solutions/industry/one"],
        shared=[],
        guides={
            "pattern-selection-guide.md": "solutions/industry/one/\n",
            "pattern-selection-guide.en.md": "nothing here\n",
        },
    )
    gaps = missing(tmp_path)
    assert list(gaps) == ["pattern-selection-guide.en.md"]


def test_a_missing_guide_is_itself_a_finding(tmp_path: Path) -> None:
    _tree(tmp_path, deployable=["solutions/industry/one"], shared=[], guides={})
    assert set(missing(tmp_path)) == set(BOTH)


def test_a_complete_guide_is_clean(tmp_path: Path) -> None:
    _tree(
        tmp_path,
        deployable=["solutions/industry/one", "operations/two"],
        shared=["operations/docs"],
        guides=dict.fromkeys(BOTH, "solutions/industry/one/ and operations/two/\n"),
    )
    assert missing(tmp_path) == {}


# --- the real tree ---


def test_every_pattern_in_this_repository_is_reachable_from_both_guides() -> None:
    gaps = missing()
    assert gaps == {}, gaps


def test_the_real_pattern_count_is_what_the_families_add_up_to() -> None:
    """Pinned as a property of the tree, not a hardcoded number.

    A number here would have to be edited whenever a pattern lands, which is the maintenance
    the guide already failed at.
    """
    found = patterns()
    assert len([p for p in found if p.startswith("solutions/industry/")]) == 28
    assert len([p for p in found if p.startswith("operations/")]) == 6
    assert "solutions/amplify-portal" in found
