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
    EXCLUDED,
    HEADING,
    INFERRED,
    LEAD,
    LOCALES,
    MODULE_LABELS,
    OPERATIONS_LOCALES,
    OPERATIONS_ROW,
    PLAYBOOK_ROWS,
    ROLE_S3AP,
    ROLE_SPECIFIC,
    ROLE_UNIVERSAL,
    UNIVERSAL_FIRST,
    UNIVERSAL_LAST,
    MarkerError,
    apply,
    check_coverage,
    hub_urls,
    operations_dirs,
    readme_for,
    render,
    row_specific,
)

NAMED_BY_PLAYBOOK = frozenset(ASSIGNMENT) - INFERRED


def modules_in_use() -> set[str]:
    used = {UNIVERSAL_FIRST, UNIVERSAL_LAST}
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
        ("ROLE_S3AP", ROLE_S3AP),
        ("ROLE_SPECIFIC", ROLE_SPECIFIC),
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


def test_both_universal_modules_appear_in_every_row() -> None:
    """The defect this replaced: 27 of 47 READMEs never linked to the S3 AP constraints.

    Both links from the Playbook's per-industry row meant a pattern whose row happens not to
    include `data-utilization` never reached the two notes #385 actually named.
    """
    for row in PLAYBOOK_ROWS:
        body = render("md", row)
        assert f"/{UNIVERSAL_FIRST}" in body, row
        assert f"/{UNIVERSAL_LAST}" in body, row
        assert body.splitlines()[-2].endswith("（全パターン共通）")


def test_the_row_specific_link_is_never_one_of_the_universals() -> None:
    """Otherwise a row would spend two of its three links on the same page."""
    for row in PLAYBOOK_ROWS:
        assert row_specific(row) not in (UNIVERSAL_FIRST, UNIVERSAL_LAST), row


def test_every_solution_reaches_the_s3_access_point_constraints() -> None:
    """Every pattern here reaches its data through an S3 Access Point, so every one needs it."""
    for solution, row in ASSIGNMENT.items():
        assert f"/{UNIVERSAL_FIRST}" in render("md", row), solution


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


# --- marker damage: the case that used to delete content ---


def test_a_lone_begin_marker_refuses_rather_than_appending() -> None:
    """The defect this replaces: an orphaned marker took the append path.

    That produced BEGIN...BEGIN...END, and the NEXT write run treated everything between the
    first BEGIN and the first END as the block and deleted it -- so content survived one run
    and was gone after the one `--check` tells you to make.
    """
    damaged = f"# Pattern\n\n{BEGIN}\n## old\n\n## Governance Note\n\n> Keep me.\n"
    with pytest.raises(MarkerError) as caught:
        apply(damaged, render("md", "media"))
    assert "1" in str(caught.value) and "0" in str(caught.value)


def test_a_lone_end_marker_also_refuses() -> None:
    with pytest.raises(MarkerError):
        apply(f"# Pattern\n\nBody.\n{END}\n", render("md", "media"))


def test_duplicate_marker_pairs_collapse_to_one() -> None:
    """Two pairs used to be a fixed point: `--check` called the file up to date with both."""
    section = render("md", "media")
    doubled = f"# Pattern\n\n{section}\n{section}"
    once = apply(doubled, section)
    assert once.count(BEGIN) == 1
    assert once.count(END) == 1
    assert apply(once, section) == once


def test_content_after_a_duplicate_pair_is_kept() -> None:
    section = render("md", "media")
    text = f"# Pattern\n\n{section}\n{section}\n## Governance Note\n\n> Keep me.\n"
    result = apply(text, section)
    assert "> Keep me." in result
    assert result.count(BEGIN) == 1


# --- coverage runs both ways now ---


def test_a_solution_on_disk_outside_the_mapping_is_reported(tmp_path: Path) -> None:
    """`main()` walks ASSIGNMENT, so this is the direction it structurally cannot see."""
    (tmp_path / "solutions" / "industry" / "brand-new").mkdir(parents=True)
    (tmp_path / "solutions" / "industry" / "brand-new" / "README.md").write_text("# x", "utf-8")
    problems = check_coverage(tmp_path)
    assert len(problems) == 1
    assert "industry/brand-new" in problems[0]


def test_an_excluded_directory_is_not_reported(tmp_path: Path) -> None:
    for name in EXCLUDED:
        (tmp_path / "solutions" / name).mkdir(parents=True)
        (tmp_path / "solutions" / name / "README.md").write_text("# x", "utf-8")
    assert check_coverage(tmp_path) == []


def test_every_excluded_directory_carries_a_reason() -> None:
    assert all(reason.strip() for reason in EXCLUDED.values())


def test_the_real_tree_is_fully_covered() -> None:
    assert check_coverage() == []


# --- hub URLs ---


def test_every_hub_url_is_a_tree_url_under_the_playbook() -> None:
    urls = hub_urls()
    assert len(urls) == 24
    for url in urls:
        assert url.startswith("https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/")
        assert not url.endswith(".md")


def test_hub_urls_cover_both_languages_and_every_module_in_use() -> None:
    urls = hub_urls()
    assert sum(1 for u in urls if "/docs/ja/" in u) == len(urls) // 2
    for module in modules_in_use():
        assert any(u.endswith(f"/docs/ja/{module}") for u in urls), module


# --- the operations pillar: one row, discovered directories ---


def test_the_operations_row_exists_and_names_operate_first() -> None:
    """Agreed with the Playbook side: one row for the pillar, 05-operate then performance."""
    assert OPERATIONS_ROW in PLAYBOOK_ROWS
    assert PLAYBOOK_ROWS[OPERATIONS_ROW] == ("playbooks/05-operate", "domains/performance")


def test_operations_is_two_locales_not_eight() -> None:
    """`operations/*/README.md` is declared ja+en in the manifest, unlike the pattern READMEs."""
    assert OPERATIONS_LOCALES == ("md", "en.md")
    assert set(OPERATIONS_LOCALES) < set(LOCALES)


def test_operations_directories_are_discovered_not_listed(tmp_path: Path) -> None:
    """A seventh pattern must need no edit here, and none on the Playbook side either.

    That is the point of the pillar getting one row: listing the six would make the other
    repository's table a copy of this catalogue, stale the moment a seventh lands.
    """
    for name in ("alpha", "beta"):
        (tmp_path / "operations" / name).mkdir(parents=True)
        (tmp_path / "operations" / name / "README.md").write_text("# x", "utf-8")
    (tmp_path / "operations" / "tests").mkdir()  # no README: shared, not a pattern
    assert operations_dirs(tmp_path) == ["alpha", "beta"]


def test_operations_dirs_is_empty_when_the_tree_is_absent(tmp_path: Path) -> None:
    assert operations_dirs(tmp_path) == []


def test_every_operations_readme_exists_for_both_locales() -> None:
    for name in operations_dirs():
        for locale in OPERATIONS_LOCALES:
            suffix = "README.md" if locale == "md" else f"README.{locale}"
            assert (Path("operations") / name / suffix).exists(), f"{name}/{suffix}"


def test_the_real_operations_tree_is_the_six_ops_patterns() -> None:
    assert len(operations_dirs()) == 6


# --- the operations pillar does not go through an access point ---


def test_the_operations_pillar_is_not_told_about_access_point_constraints() -> None:
    """AGENTS.md defines operations/ as the pillar that does not use S3 Access Points.

    The first draft of the universal link labelled `data-utilization` "constraints of reaching
    data through an access point" for every README, which stated something untrue in the twelve
    operations files. A link is not harmless when its label makes a claim.
    """
    body = render("md", OPERATIONS_ROW, via_access_point=False)
    assert "S3 Access Point" not in body
    assert f"/{UNIVERSAL_FIRST}" not in body
    assert f"/{UNIVERSAL_LAST}" in body


def test_the_operations_section_still_carries_three_links() -> None:
    assert render("md", OPERATIONS_ROW, via_access_point=False).count("\n- [") == 3


def test_the_operations_section_uses_its_rows_own_two_modules() -> None:
    first, second = PLAYBOOK_ROWS[OPERATIONS_ROW]
    body = render("md", OPERATIONS_ROW, via_access_point=False)
    assert f"/{first}" in body
    assert f"/{second}" in body


def test_solutions_still_get_the_access_point_link() -> None:
    for row in PLAYBOOK_ROWS:
        if row == OPERATIONS_ROW:
            continue
        assert f"/{UNIVERSAL_FIRST}" in render("md", row), row


def test_the_committed_operations_readmes_make_no_access_point_claim() -> None:
    """Checked against the files, not only against render()."""
    for name in operations_dirs():
        for suffix in ("README.md", "README.en.md"):
            text = (Path("operations") / name / suffix).read_text(encoding="utf-8")
            section = text.split(BEGIN)[-1].split(END)[0]
            assert "Access Point" not in section, f"{name}/{suffix}"
