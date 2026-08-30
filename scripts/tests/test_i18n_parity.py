r"""Tests for the i18n manifest, the parity check and the switcher generator.

## Why these carry more weight than the checks themselves

Every one of the bugs below was in the first working version, and each produced a
*plausible* number rather than an error — which is the only kind of bug that
survives in a check nobody re-derives by hand:

* **`fnmatch` lets `*` cross `/`.** `solutions/*/*/README.md` therefore matched
  `solutions/genai/kb-selfservice-curation/sample-data/README.md` and demanded seven
  translations of a sample-data README. A rule that appears to say one thing and
  matches another is precisely what a manifest exists to prevent.
* **`docs/en/x.md` was read as a source**, so the checker asked for
  `docs/en/x.en.md`. 34 findings were the checker reporting its own bug as a
  repository defect.
* **The inverted group.** `solutions/amplify-portal/README.md` is English with
  `README.ja.md` beside it. Deriving sibling paths from the manifest's nominal
  source locale made the Japanese lookup return the base file itself, so
  `README.ja.md` — present in the tree — was reported missing.
* **The switcher regex missed the blockquote form.** 66 switchers are written
  `> 🌐 ...`; `^\s*🌐` does not match a `>` prefix, so `--write` inserted a second
  switcher above the first instead of replacing it. Caught by running one file
  before 502.

The manifest's own numbers are asserted too. A ratchet that is quietly raised stops
being a ratchet, and a `keep` rule that silently became "all" would invent hundreds
of obligations.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
MANIFEST = ROOT / "docs" / "i18n-manifest.toml"


def _load(name: str) -> ModuleType:
    """Import a script from scripts/ by path.

    Args:
        name: Module file stem under scripts/.

    Returns:
        The imported module.
    """
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


parity = _load("check_i18n_parity")
switcher = _load("sync_lang_switcher")


# --------------------------------------------------------------------------
# Path-aware globbing
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "pattern", "expected"),
    [
        ("solutions/industry/legal-compliance/README.md", "solutions/*/*/README.md", True),
        # The measured false positive: `*` must not span a separator.
        ("solutions/genai/kb-selfservice-curation/sample-data/README.md", "solutions/*/*/README.md", False),
        ("solutions/industry/legal-compliance/docs/demo-guide.md", "solutions/industry/*/docs/*.md", True),
        ("solutions/flexcache/anycast-dr/docs/demo-guide.md", "solutions/industry/*/docs/*.md", False),
        ("docs/cdn-comparison.md", "docs/*.md", True),
        ("docs/ja/deployment-guide.md", "docs/*.md", False),
        ("docs/ja/deployment-guide.md", "docs/ja/*.md", True),
        ("README.md", "README.md", True),
        ("solutions/amplify-portal/README.md", "README.md", False),
    ],
)
def test_glob_is_segment_aware(path: str, pattern: str, expected: bool) -> None:
    assert parity.matches(path, pattern) is expected, f"{pattern!r} vs {path!r}"


def test_double_star_crosses_separators() -> None:
    """`**/` is the explicit any-depth form, so it must still span directories."""
    assert parity.matches("a/b/c/README.md", "**/README.md")
    assert parity.matches("README.md", "**/README.md")


# --------------------------------------------------------------------------
# Manifest integrity
# --------------------------------------------------------------------------


def test_every_rule_has_a_substantive_reason() -> None:
    """A requirement nobody justified is a requirement nobody can review."""
    _, _, rules = parity.load_manifest()
    for rule in rules:
        why = str(rule["why"]).strip()
        assert len(why) > 30, f"rule {rule['glob']!r} has no substantive 'why': {why!r}"


def test_locales_all_is_the_eight_this_repo_publishes() -> None:
    locales_all, source, _ = parity.load_manifest()
    assert source == "ja"
    assert set(locales_all) == {"ja", "en", "ko", "zh-CN", "zh-TW", "fr", "de", "es"}


def test_keep_rules_exist() -> None:
    """`keep` is what stops the manifest inventing obligations; losing it is a regression.

    Requiring English across all 279 documents in `docs/` reported 245 missing
    translations on the first run — an ambition with a gate attached.
    """
    _, _, rules = parity.load_manifest()
    keeps = [r for r in rules if r["locales"] == "keep"]
    assert keeps, "no `keep` rules; a blanket requirement will report aspirations as defects"


def test_docs_agent_is_japanese_only_on_purpose() -> None:
    """16 agent notes would otherwise look like 112 missing translations."""
    _, _, rules = parity.load_manifest()
    assert parity.required_for("docs/agent/pitfalls-snaplock.md", rules) == ["ja"]


def test_the_inverted_group_is_governed() -> None:
    _, _, rules = parity.load_manifest()
    required = parity.required_for("solutions/amplify-portal/README.md", rules)
    assert required is not None and "ja" in required and "en" in required


# --------------------------------------------------------------------------
# Source selection
# --------------------------------------------------------------------------


def test_locale_directories_are_not_sources() -> None:
    """`docs/en/x.md` is the English side of a pair, not a document needing a twin."""
    missing, _, _ = parity.analyse()
    assert not [f for f in missing if f.startswith("docs/en/")], (
        "docs/en/ files are being treated as sources; they would each be asked for a .en.md twin"
    )


def test_inverted_base_locale_is_detected() -> None:
    """README.md is English here because README.ja.md exists beside it."""
    published = parity.tracked()
    assert parity.base_locale_of("solutions/amplify-portal/README.md", published, "ja") == "en"
    assert parity.base_locale_of("README.md", published, "ja") == "ja"


def test_the_inverted_group_is_not_reported_as_missing_japanese() -> None:
    """README.ja.md is present, so asking for it is the checker misreading the group."""
    missing, _, _ = parity.analyse()
    offenders = [f for f in missing if "amplify-portal/README.md" in f]
    assert not offenders, offenders


def test_a_single_declared_locale_names_the_base_file() -> None:
    """A rule naming one locale states what the unsuffixed file IS.

    `docs/aws-feature-requests/fsxn-s3ap-improvements.md` is English with no twin at
    all — a single bilingual document whose Japanese is one appendix. Twin-based
    inference has nothing to work from there, so it read the file as Japanese and
    reported the English document as missing its English translation.
    """
    published = parity.tracked()
    assert parity.base_locale_of("docs/x.md", published, "ja", ["en"]) == "en"
    # Two or more declared locales: fall back to inference rather than guessing.
    assert parity.base_locale_of("docs/x.md", published, "ja", ["ja", "en"]) == "ja"


def test_the_english_primary_feature_request_is_not_reported_missing() -> None:
    """Regression pin for the file that prompted the declared-locale override."""
    missing, _, _ = parity.analyse()
    offenders = [f for f in missing if "fsxn-s3ap-improvements" in f]
    assert not offenders, offenders


# --------------------------------------------------------------------------
# Heading extraction
# --------------------------------------------------------------------------


def test_headings_inside_fences_are_not_counted(tmp_path: Path) -> None:
    """`# Wait for AVAILABLE status` in a shell block is a comment, not a heading.

    The older parity check counts them, which turns 22 headings into 37 on
    docs/ja/portal-deployment-runbook.md and misaligns its section walk.
    """
    doc = tmp_path / "x.md"
    doc.write_text(
        "# Title\n\n## Real\n\n```bash\n# Wait for AVAILABLE status\n## also not a heading\n```\n\n## Also real\n",
        encoding="utf-8",
    )
    assert parity.headings(doc) == ["# Title", "## Real", "## Also real"]


def test_unclosed_fence_does_not_swallow_everything(tmp_path: Path) -> None:
    doc = tmp_path / "y.md"
    doc.write_text("# A\n\n## B\n\n```\nunclosed\n", encoding="utf-8")
    assert parity.headings(doc) == ["# A", "## B"]


# --------------------------------------------------------------------------
# The ratchet
# --------------------------------------------------------------------------


def test_baselines_match_the_current_tree() -> None:
    """A ratchet quietly raised is not a ratchet. Fails in EITHER direction.

    Rising means a gap was added; falling means one was closed and the baseline
    was not locked in, which lets it be reopened for free.
    """
    missing, structure, examined = parity.analyse()
    assert examined > 150, f"only {examined} groups governed; the manifest or reader is broken"
    assert len(missing) == parity.DEFAULT_MAX_MISSING, (
        f"missing is {len(missing)}, baseline is {parity.DEFAULT_MAX_MISSING}. "
        "Update DEFAULT_MAX_MISSING (down when closing a gap) and this test together."
    )
    assert len(structure) == parity.DEFAULT_MAX_STRUCTURE, (
        f"structural is {len(structure)}, baseline is {parity.DEFAULT_MAX_STRUCTURE}. "
        "Update DEFAULT_MAX_STRUCTURE and this test together."
    )


def test_by_source_collapses_findings_into_work_items(capsys: pytest.CaptureFixture[str]) -> None:
    """269 findings is not 269 problems, and a bare count is not actionable.

    They come from 51 source documents, most contributing exactly 7 — one per
    locale, because the six non-English translations were produced in one batch and
    none received the sections the Japanese source gained afterwards. The unit of
    work is the source document.
    """
    assert parity.main(["--by-source"]) == 0
    out = capsys.readouterr().out
    _, structure, _ = parity.analyse()
    sources = {finding.split("source ")[1].split()[0] for finding in structure if "source " in finding}
    assert f"{len(structure)} finding(s) from {len(sources)} source document(s)" in out
    assert len(sources) < len(structure), "the by-source view must collapse findings, not restate them"


def test_by_source_is_a_report_not_a_gate() -> None:
    """It must exit 0 even though findings exist, or it becomes a second gate."""
    assert parity.main(["--by-source"]) == 0


def test_strict_mode_fails_while_gaps_remain() -> None:
    """--strict is the mode for clearing one group; it must not pass vacuously."""
    assert parity.main(["--strict", "--quiet"]) == 1


def test_exceeding_the_structural_baseline_fails() -> None:
    assert parity.main(["--max-missing", "999999", "--max-structure", "0", "--quiet"]) == 1


def test_a_newly_missing_translation_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """The missing baseline is 0, so it cannot be exceeded by lowering the ceiling.

    Simulating the regression is the only way to exercise the path: a document that
    the manifest requires in a locale, with that locale absent. Before this test the
    assertion was `--max-missing 0`, which stopped meaning anything the moment the
    real count reached 0 — a test that passes because the world improved, not because
    the code works.
    """
    monkeypatch.setattr(parity, "analyse", lambda only=None: (["docs/x.md: no en translation"], [], 210))
    assert parity.main(["--quiet"]) == 1


def test_at_baseline_passes() -> None:
    assert parity.main(["--quiet"]) == 0


# --------------------------------------------------------------------------
# The switcher generator
# --------------------------------------------------------------------------


def test_current_language_is_plain_text_never_a_link() -> None:
    """The root README linked 日本語 to the file the reader was already on."""
    group = {"ja": "README.md", "en": "README.en.md"}
    line = switcher.switcher_for("ja", group, "README.md", ["ja", "en"])
    assert "日本語 |" in line or line.endswith("日本語")
    assert "[日本語]" not in line
    assert "[English](README.en.md)" in line


def test_links_resolve_across_locale_directories() -> None:
    """docs/ja/x.md must reach docs/en/x.md as ../en/x.md, not en/x.md."""
    group = {"ja": "docs/ja/x.md", "en": "docs/en/x.md"}
    line = switcher.switcher_for("ja", group, "docs/ja/x.md", ["ja", "en"])
    assert "(../en/x.md)" in line, line


def test_order_follows_the_manifest() -> None:
    locales_all, _, _ = parity.load_manifest()
    group = dict.fromkeys(locales_all, "")
    group = {loc: ("README.md" if loc == "ja" else f"README.{loc}.md") for loc in locales_all}
    line = switcher.switcher_for("en", group, "README.md", locales_all)
    positions = [line.index(switcher.LABELS[loc]) for loc in locales_all]
    assert positions == sorted(positions), "switcher entries are not in manifest order"


@pytest.mark.parametrize(
    ("existing", "should_match"),
    [
        ("🌐 **Language / 言語**: 日本語", True),
        ("> 🌐 言語: **日本語** | [English](x.en.md)", True),  # 66 files; the bug that inserted a duplicate
        ("  🌐 Language: x", True),
        ("| 🌐 cell |", False),  # a table cell, 5 files
        ("## 🌐 heading", False),  # a heading, 2 files
        ("トップバーの 🌐 を押す", False),  # prose
    ],
)
def test_existing_switcher_detection(existing: str, should_match: bool) -> None:
    assert bool(switcher.EXISTING.match(existing)) is should_match, existing


def test_blockquote_marker_is_preserved() -> None:
    """Dropping the `>` would split a multi-line quote block."""
    text = "# T\n> 🌐 言語: **日本語** | [English](x.en.md)\nbody\n"
    out = switcher._apply(text, "🌐 **Language / 言語**: 日本語")
    assert "> 🌐 **Language / 言語**: 日本語" in out
    assert out.count("🌐") == 1, "replaced, not duplicated"


def test_replacing_never_duplicates() -> None:
    """The measured failure: an unmatched prefix made --write append a second line."""
    for existing in ("🌐 old", "> 🌐 old", "   🌐 old"):
        text = f"# T\n{existing}\nbody\n"
        out = switcher._apply(text, "🌐 new")
        assert out.count("🌐") == 1, f"duplicated for prefix {existing!r}: {out!r}"


def test_a_second_header_switcher_is_removed() -> None:
    """Four files shipped two switchers in the header, 2 lines apart.

    docs/architecture-diagrams.{md,en.md} carried the canonical line followed by an
    older `🌐 **言語**:` form, and docs/partner-si-one-pager.{ko,zh-CN}.md carried a
    stale copy that linked the reader's own language back to the page they were
    already reading.
    """
    text = "# T\n\n🌐 old one\n\n🌐 **言語**: stale\n\nbody\n"
    out = switcher._apply(text, "🌐 canonical")
    assert out.count("🌐") == 1, out
    assert "canonical" in out
    assert "stale" not in out
    assert "body" in out, "removing the duplicate must not take content with it"


def test_a_footer_switcher_is_left_alone() -> None:
    """The root README and the portal READMEs carry one 216-698 lines down.

    That is content, not a duplicate. De-duplicating the whole file would delete it.
    """
    text = "# T\n\n🌐 header\n\n" + "filler\n" * 40 + "\n🌐 footer\n"
    out = switcher._apply(text, "🌐 canonical")
    assert out.count("🌐") == 2, out
    assert "🌐 footer" in out


def test_switcher_is_inserted_under_the_h1_when_absent() -> None:
    text = "# Title\n\nbody\n"
    out = switcher._apply(text, "🌐 X")
    lines = out.split("\n")
    assert lines[0] == "# Title"
    assert "🌐 X" in lines[:4]


def test_generated_switchers_are_in_sync() -> None:
    """After `--write`, `--check` must be clean, or the gate cannot mean anything."""
    assert switcher.main(["--check"]) == 0, (
        "switchers differ from the generated form. Run: python3 scripts/sync_lang_switcher.py --write"
    )


# --------------------------------------------------------------------------
# Not vacuous
# --------------------------------------------------------------------------


def test_the_manifest_is_actually_read() -> None:
    assert MANIFEST.is_file()
    _, _, rules = parity.load_manifest()
    assert len(rules) > 10, f"only {len(rules)} rules parsed from the manifest"


def test_manifest_is_git_tracked() -> None:
    """Committed, or present and not ignored — the definition used elsewhere here.

    A manifest that is only on one machine declares requirements CI cannot see.
    """
    proc = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert "docs/i18n-manifest.toml" in set(proc.stdout.splitlines()), (
        "the manifest must be in the repository, not local-only or ignored"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
