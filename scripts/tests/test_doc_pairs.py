"""Tests for the documentation pair check.

Two things had shipped that this check exists to stop, and both are pinned here
against the shapes they actually took.

A translation with nothing pointing at it: 27 of 83 pairs carried no language
switcher, so a reader who landed on one language could not reach the other. The
work was done; it was unreachable.

A relative link that resolves to nothing: 18 were dead in the portal docs alone,
because `../../docs/` from `solutions/amplify-portal/docs/` is `solutions/docs/`.
GitHub renders a dead relative link as ordinary text, so reading the page does
not reveal it — which is why every cross-tree link in two documents was broken
and nobody had noticed.

The awkward part is what the pair finder must NOT do. Six conventions coexist,
including one where the unmarked file is English and the Japanese one carries the
marker. Anything that infers language from position gets that pair backwards.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

SWITCHER_JA = "🌐 **Language / 言語**: **日本語** | [English](guide.en.md)"
SWITCHER_EN = "🌐 **Language / 言語**: [日本語](guide.md) | **English**"


@pytest.fixture(scope="module")
def pairs():
    spec = importlib.util.spec_from_file_location("check_doc_pairs", SCRIPTS / "check_doc_pairs.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_doc_pairs"] = module
    spec.loader.exec_module(module)
    return module


def _repo(tmp_path: Path) -> Path:
    for name in ("docs/ja", "docs/en", "docs/guides", "solutions/amplify-portal/docs"):
        (tmp_path / name).mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_the_repository_passes(pairs):
    """Guards the fix: 27 pairs and 27 links were failing when this landed."""
    assert pairs.check_switchers() == []
    assert pairs.check_links() == []


def test_it_finds_pairs_at_all(pairs):
    """A finder that matches nothing would report PASS on everything.

    This is the failure mode a pair check degrades into after a directory is
    renamed: it keeps passing and stops meaning anything.
    """
    found = pairs.find_pairs()
    assert len(found) >= 80, f"only {len(found)} pairs found; the finder has stopped matching the layout"
    assert all(len(group) >= 2 for group in found)


def test_a_pair_without_a_switcher_is_reported(pairs, tmp_path, monkeypatch):
    root = _repo(tmp_path)
    (root / "docs" / "guide.md").write_text("# 手引き\n\n本文\n", encoding="utf-8")
    (root / "docs" / "guide.en.md").write_text("# Guide\n\nBody\n", encoding="utf-8")
    monkeypatch.setattr(pairs, "ROOT", root)

    findings = pairs.check_switchers()

    assert len(findings) == 1, findings
    assert "guide.md" in findings[0] and "guide.en.md" in findings[0]


def test_one_sided_switcher_is_still_reported(pairs, tmp_path, monkeypatch):
    """The real one-sided case: s3ap-compatibility-notes had it only in English.

    A switcher on one side is not enough — the reader on the other side is the
    one who cannot navigate.
    """
    root = _repo(tmp_path)
    (root / "docs" / "guide.md").write_text("# 手引き\n\n本文\n", encoding="utf-8")
    (root / "docs" / "guide.en.md").write_text(f"# Guide\n\n{SWITCHER_EN}\n\nBody\n", encoding="utf-8")
    monkeypatch.setattr(pairs, "ROOT", root)

    findings = pairs.check_switchers()

    assert len(findings) == 1
    assert "guide.md" in findings[0]
    assert "guide.en.md" not in findings[0], "reported the side that has one"


def test_a_complete_pair_is_left_alone(pairs, tmp_path, monkeypatch):
    root = _repo(tmp_path)
    (root / "docs" / "guide.md").write_text(f"# 手引き\n\n{SWITCHER_JA}\n\n本文\n", encoding="utf-8")
    (root / "docs" / "guide.en.md").write_text(f"# Guide\n\n{SWITCHER_EN}\n\nBody\n", encoding="utf-8")
    monkeypatch.setattr(pairs, "ROOT", root)
    assert pairs.check_switchers() == []


def test_both_switcher_phrasings_are_accepted(pairs, tmp_path, monkeypatch):
    """Two formats are in use, 79 files and 17. Neither is a finding.

    Rejecting the minority format would have flagged 17 correct files, and the
    usual response to that is to switch the check off.
    """
    root = _repo(tmp_path)
    (root / "docs" / "guide.md").write_text(
        "# 手引き\n\n> 🌐 言語: **日本語** | [English](guide.en.md)\n\n本文\n", encoding="utf-8"
    )
    (root / "docs" / "guide.en.md").write_text(
        "# Guide\n\n> 🌐 Language: **English** | [日本語](guide.md)\n\nBody\n", encoding="utf-8"
    )
    monkeypatch.setattr(pairs, "ROOT", root)
    assert pairs.check_switchers() == []


def test_a_single_language_document_is_not_a_pair(pairs, tmp_path, monkeypatch):
    """215 documents exist in Japanese only. None of them needs a switcher.

    Demanding one would report 215 findings that cannot be fixed by adding a
    link, only by writing a translation — which is a different decision.
    """
    root = _repo(tmp_path)
    (root / "docs" / "solo.md").write_text("# 単独\n\n本文\n", encoding="utf-8")
    monkeypatch.setattr(pairs, "ROOT", root)
    assert pairs.find_pairs() == []
    assert pairs.check_switchers() == []


def test_the_eight_locale_dash_convention_is_one_group(pairs, tmp_path, monkeypatch):
    """`X.md` + `X-ko.md` + six more is one document, not seven pairs."""
    root = _repo(tmp_path)
    base = root / "docs" / "guides" / "setup.md"
    base.write_text("# 設定\n\n本文\n", encoding="utf-8")
    for locale in ("en", "ko", "zh-CN", "zh-TW", "fr", "de", "es"):
        (root / "docs" / "guides" / f"setup-{locale}.md").write_text(f"# Setup {locale}\n", encoding="utf-8")
    monkeypatch.setattr(pairs, "ROOT", root)

    groups = [g for g in pairs.find_pairs() if g[0] == base]

    assert len(groups) == 1
    assert len(groups[0]) == 8


def test_a_locale_file_is_never_treated_as_its_own_base(pairs, tmp_path, monkeypatch):
    """`setup-ko.md` must not start a second group of its own.

    Without the suffix guard, each locale file becomes a base and the same
    document is reported eight times.
    """
    root = _repo(tmp_path)
    (root / "docs" / "guides" / "setup.md").write_text("# 設定\n", encoding="utf-8")
    for locale in ("en", "ko", "fr"):
        (root / "docs" / "guides" / f"setup-{locale}.md").write_text(f"# Setup {locale}\n", encoding="utf-8")
    monkeypatch.setattr(pairs, "ROOT", root)

    bases = [group[0].name for group in pairs.find_pairs()]

    assert bases == ["setup.md"], bases


def test_a_document_is_claimed_by_one_convention_only(pairs, tmp_path, monkeypatch):
    """`docs/X.md` + `docs/en/X.md` must not also be found by a suffix rule."""
    root = _repo(tmp_path)
    (root / "docs" / "topic.md").write_text("# 話題\n", encoding="utf-8")
    (root / "docs" / "en" / "topic.md").write_text("# Topic\n", encoding="utf-8")
    monkeypatch.setattr(pairs, "ROOT", root)

    groups = pairs.find_pairs()

    assert len(groups) == 1, [[str(p) for p in g] for g in groups]


def test_a_dead_relative_link_is_reported(pairs, tmp_path, monkeypatch):
    """The exact shape that was dead 18 times over."""
    root = _repo(tmp_path)
    portal = root / "solutions" / "amplify-portal" / "docs"
    (portal / "impl.md").write_text(
        "# Impl\n\nSee the [user guide](../../docs/en/portal-user-guide.md).\n", encoding="utf-8"
    )
    (root / "docs" / "en" / "portal-user-guide.md").write_text("# Guide\n", encoding="utf-8")
    monkeypatch.setattr(pairs, "ROOT", root)

    findings = pairs.check_links()

    assert len(findings) == 1, findings
    assert "impl.md:3" in findings[0]
    assert "../../docs/en/portal-user-guide.md" in findings[0]


def test_the_corrected_depth_is_accepted(pairs, tmp_path, monkeypatch):
    """`../../../docs/` is the repair; it must not be reported in turn."""
    root = _repo(tmp_path)
    portal = root / "solutions" / "amplify-portal" / "docs"
    (portal / "impl.md").write_text(
        "# Impl\n\nSee the [user guide](../../../docs/en/portal-user-guide.md).\n", encoding="utf-8"
    )
    (root / "docs" / "en" / "portal-user-guide.md").write_text("# Guide\n", encoding="utf-8")
    monkeypatch.setattr(pairs, "ROOT", root)
    assert pairs.check_links() == []


@pytest.mark.parametrize(
    "line",
    [
        "See [the docs](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/what-is-fsx-ontap.html).",
        "See [the sibling](sibling.md) in this directory.",
        "Run `cat ../../docs/thing.md` to inspect it.",
    ],
)
def test_things_that_are_not_broken_relative_links(pairs, tmp_path, monkeypatch, line):
    """Absolute URLs, same-directory links and prose are not this check's business.

    The same-directory link is the one that matters: `[x](sibling.md)` has no
    leading `./`, and a pattern loose enough to catch it would try to resolve
    every inline code span containing a filename.
    """
    root = _repo(tmp_path)
    (root / "docs" / "page.md").write_text(f"# Page\n\n{line}\n", encoding="utf-8")
    monkeypatch.setattr(pairs, "ROOT", root)
    assert pairs.check_links() == []


def test_an_anchor_does_not_stop_the_file_resolving(pairs, tmp_path, monkeypatch):
    """`../guide.md#section` resolves on the path, with the fragment ignored.

    Both halves matter. Keeping the fragment would make every anchored link look
    broken; dropping the check for anchored links would exempt them, and an
    anchored link into a file that no longer exists is exactly as dead as a plain
    one.
    """
    root = _repo(tmp_path)
    (root / "docs" / "ja" / "page.md").write_text(
        "# ページ\n\nSee [an anchor](../guide.md#section).\n", encoding="utf-8"
    )
    monkeypatch.setattr(pairs, "ROOT", root)

    assert pairs.check_links(), "an anchored link into a missing file should still be reported"

    (root / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    assert pairs.check_links() == [], "the fragment must not stop the path from resolving"


def test_an_empty_tree_fails_rather_than_passing(pairs, tmp_path, monkeypatch, capsys):
    """No pairs means the finder is broken, and the exit code should say so."""
    monkeypatch.setattr(pairs, "ROOT", _repo(tmp_path))
    assert pairs.main() == 1
    assert "found no pairs" in capsys.readouterr().out
