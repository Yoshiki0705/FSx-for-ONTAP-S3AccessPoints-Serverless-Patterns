#!/usr/bin/env python3
"""Tests for the playbook reading-section sync.

The failure this guards against is not a wrong sentence, it is a half-written tree. The
script writes 376 files in one pass, so a locale missing from any label dictionary raises
`KeyError` partway through and leaves some READMEs updated and others not. The
completeness tests below make that a test failure instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sync_playbook_reading_section import (  # noqa: E402
    ASSIGNMENT,
    BEGIN,
    END,
    HEADING,
    INFERRED,
    LEAD,
    LOCALES,
    MODULE_LABELS,
    PLAYBOOK_ROWS,
    ROLE_FIRST,
    ROLE_SECOND,
    ROLE_UNIVERSAL,
    UNIVERSAL,
    apply,
    readme_for,
    render,
)

NAMED_BY_PLAYBOOK = frozenset(ASSIGNMENT) - INFERRED


def modules_in_use() -> set[str]:
    used = {UNIVERSAL}
    for first, second in PLAYBOOK_ROWS.values():
        used.update((first, second))
    return used


# --- completeness: the whole run fails on a missing key, so pin every dictionary ---


@pytest.mark.parametrize("module", sorted(modules_in_use()))
def test_every_module_in_use_has_a_label_in_every_locale(module: str) -> None:
    assert module in MODULE_LABELS, f"{module} is referenced but has no labels"
    missing = [loc for loc in LOCALES if not MODULE_LABELS[module].get(loc)]
    assert not missing, f"{module} has no label for {missing}"


@pytest.mark.parametrize(
    ("name", "table"),
    [
        ("HEADING", HEADING),
        ("LEAD", LEAD),
        ("ROLE_FIRST", ROLE_FIRST),
        ("ROLE_SECOND", ROLE_SECOND),
        ("ROLE_UNIVERSAL", ROLE_UNIVERSAL),
    ],
)
def test_every_locale_is_present(name: str, table: dict[str, str]) -> None:
    missing = [loc for loc in LOCALES if not table.get(loc)]
    assert not missing, f"{name} has no entry for {missing}"


def test_every_assignment_names_a_known_row() -> None:
    unknown = {sol: row for sol, row in ASSIGNMENT.items() if row not in PLAYBOOK_ROWS}
    assert not unknown, unknown


def test_no_label_dictionary_carries_an_unused_locale() -> None:
    """A locale key nobody reads is a translation that will silently rot."""
    for module, labels in MODULE_LABELS.items():
        extra = set(labels) - set(LOCALES)
        assert not extra, f"{module} has labels for unused locales: {extra}"


# --- provenance: the Playbook's own table vs this repository's inference ---


def test_inferred_is_a_subset_of_the_assignments() -> None:
    assert INFERRED <= set(ASSIGNMENT)


def test_the_fifteen_solutions_named_by_the_playbook_are_not_marked_inferred() -> None:
    """The Playbook names these directly; recording them as inference would overstate.

    Pinned as a set rather than a count so that adding a solution to one group and
    forgetting the other is a failure.
    """
    assert NAMED_BY_PLAYBOOK == {
        "industry/energy-seismic",
        "industry/semiconductor-eda",
        "industry/autonomous-driving",
        "industry/manufacturing-analytics",
        "industry/financial-idp",
        "industry/insurance-claims",
        "industry/healthcare-dicom",
        "industry/telecom-network-analytics",
        "industry/defense-satellite",
        "industry/government-archives",
        "industry/media-vfx",
        "industry/education-research",
        "industry/logistics-ocr",
        "industry/retail-catalog",
        "amplify-portal",
    }


# --- rendering ---


def test_the_section_carries_exactly_three_links() -> None:
    """Two or three, per the request. A longer index does not get followed."""
    body = render("md", "semiconductor-eda")
    assert body.count("\n- [") == 3


def test_the_japanese_readme_points_at_the_japanese_hubs() -> None:
    body = render("md", "semiconductor-eda")
    assert "/docs/ja/domains/performance" in body
    assert "/docs/en/" not in body


@pytest.mark.parametrize("locale", [loc for loc in LOCALES if loc != "md"])
def test_every_other_locale_points_at_the_english_hubs(locale: str) -> None:
    """The Playbook's domains/ and playbooks/ trees exist in ja and en only.

    Pointing a Korean README at `docs/ko/domains/...` would produce a 404, which is
    exactly the class of rot the sibling check was added for.
    """
    body = render(locale, "semiconductor-eda")
    assert "/docs/en/domains/performance" in body
    assert "/docs/ja/" not in body


def test_links_point_at_module_hubs_not_at_notes() -> None:
    """Notes get renamed; hubs do not. A `.md` target would be a note."""
    for locale in LOCALES:
        for row in PLAYBOOK_ROWS:
            for line in render(locale, row).splitlines():
                if line.startswith("- ["):
                    target = line.split("](", 1)[1].rstrip(")").split(" —")[0]
                    assert "/tree/main/docs/" in target, target
                    assert not target.endswith(".md"), target


def test_the_universal_module_is_the_third_link_everywhere() -> None:
    for row in PLAYBOOK_ROWS:
        assert render("md", row).splitlines()[-2].endswith("（全パターン共通）")
        assert UNIVERSAL in render("md", row)


def test_no_constraint_is_restated_in_the_section() -> None:
    """#88's arrangement: the Playbook owns the constraints, this side only links.

    A section that grew a constraint would be the start of the second copy, so the
    fixed prose is held to the lead sentence plus three links.
    """
    body = render("md", "financial")
    prose = [ln for ln in body.splitlines() if ln and not ln.startswith(("- [", "## ", BEGIN, END))]
    assert len(prose) == 1, prose


# --- idempotence ---


def test_applying_twice_changes_nothing() -> None:
    section = render("md", "media")
    once = apply("# Pattern\n\nBody.\n", section)
    assert apply(once, section) == once


def test_a_changed_section_replaces_rather_than_appends() -> None:
    original = apply("# Pattern\n\nBody.\n", render("md", "media"))
    updated = apply(original, render("md", "financial"))
    assert updated.count(BEGIN) == 1
    assert updated.count(END) == 1
    assert "block-storage" in updated
    assert "02-design" not in updated


def test_content_above_the_marker_is_preserved() -> None:
    original = "# Pattern\n\n## Governance Note\n\n> Not legal advice.\n"
    updated = apply(original, render("md", "media"))
    assert updated.startswith(original.rstrip("\n"))
    assert "> Not legal advice." in updated


# --- path resolution ---


def test_the_portal_readme_naming_is_inverted(tmp_path: Path) -> None:
    """`amplify-portal/README.md` is English and `README.ja.md` is Japanese."""
    assert readme_for("amplify-portal", "md", tmp_path).name == "README.ja.md"
    assert readme_for("amplify-portal", "en.md", tmp_path).name == "README.md"


def test_every_other_solution_keeps_japanese_in_readme_md(tmp_path: Path) -> None:
    assert readme_for("industry/media-vfx", "md", tmp_path).name == "README.md"
    assert readme_for("industry/media-vfx", "en.md", tmp_path).name == "README.en.md"
    assert readme_for("industry/media-vfx", "zh-CN.md", tmp_path).name == "README.zh-CN.md"


def test_every_assigned_readme_exists_on_disk() -> None:
    """ASSIGNMENT is written by hand, so a typo would silently skip eight files."""
    missing = [
        readme_for(solution, locale).as_posix()
        for solution in ASSIGNMENT
        for locale in LOCALES
        if not readme_for(solution, locale).exists()
    ]
    assert not missing, missing
