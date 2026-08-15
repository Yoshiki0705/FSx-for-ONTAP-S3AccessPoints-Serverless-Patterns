"""Tests for the colour-literal check on the portal stylesheet.

The check exists because a hardcoded light colour cannot be seen by the person who
writes it: their theme is the one it was written for. It surfaces only when someone
opens the portal in dark mode and finds a white slab in the middle of the page.

It shipped unable to do that. The pattern was anchored to the start of a line, and
this stylesheet writes status rules on one line:

    .state-online { background: #dcfce7; color: #166534; }

An anchored pattern sees `.state-online`, not `background`, so every rule in that
shape was invisible. The check reported 5 literals while 201 were present, and passed
through every edit that added another. The first case below is that exact shape: it is
the one thing this file exists to keep working.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import check_portal_drift as drift  # noqa: E402


@pytest.fixture
def stylesheet(tmp_path, monkeypatch):
    """Point the check at a stylesheet this test writes.

    Returns:
        A callable taking CSS source and returning the findings for it, with the
        budget forced to zero so any literal is reported.
    """

    def write(css: str) -> list[drift.Finding]:
        (tmp_path / "src").mkdir(exist_ok=True)
        (tmp_path / "src" / "index.css").write_text(css, encoding="utf-8")
        monkeypatch.setattr(drift, "PORTAL", tmp_path)
        monkeypatch.setattr(drift, "THEME_LITERAL_BUDGET", 0)
        return drift.check_theme_literals()

    return write


def test_finds_a_literal_in_a_single_line_rule(stylesheet):
    """The regression. Declarations after a selector on the same line count."""
    findings = stylesheet(".state-online { background: #dcfce7; color: #166534; }\n")
    assert findings, "a one-line rule hid 201 literals from this check once"
    assert "#dcfce7" in findings[0].detail
    assert "#166534" in findings[0].detail


def test_finds_several_declarations_on_one_line(stylesheet):
    """Every literal on the line, not just the first."""
    findings = stylesheet(".b { padding: 1rem; background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; }\n")
    detail = findings[0].detail
    assert detail.count("src/index.css:1") == 3


def test_ignores_the_palette_definitions(stylesheet):
    """The token blocks are where literals belong."""
    assert not stylesheet(
        ":root {\n  --color-surface: #ffffff;\n  --color-text: #16191f;\n}\n"
        '[data-theme="dark"] {\n  --color-surface: #1c2128;\n}\n'
    )


def test_ignores_a_custom_property_outside_the_palette(stylesheet):
    """A token declared on a component still defines a value, not consumes one."""
    assert not stylesheet(".panel {\n  --panel-accent: #0972d3;\n}\n")


def test_accepts_a_token_reference(stylesheet):
    """The shape the stylesheet is supposed to be in."""
    assert not stylesheet(".ok { background: var(--color-success-bg); color: var(--color-success-text); }\n")


def test_counts_a_literal_used_as_a_var_fallback(stylesheet):
    """A fallback applies whenever the token is unset, so it has to follow the theme."""
    findings = stylesheet(".fallback { background: var(--color-surface, #ffffff); }\n")
    assert findings and "#ffffff" in findings[0].detail


def test_ignores_properties_that_do_not_carry_a_theme_colour(stylesheet):
    """Shadows go through --color-shadow; brand-mark fills do not change."""
    assert not stylesheet(".mark { box-shadow: 0 2px 8px rgba(0,0,0,0.2); fill: #ff9900; }\n")


def test_named_colours_count(stylesheet):
    """`white` was both a surface and inverse text, which is why roles were needed."""
    findings = stylesheet(".n { color: white; }\n")
    assert findings and "white" in findings[0].detail


def test_stays_quiet_within_budget(stylesheet, tmp_path, monkeypatch):
    """The budget is a ceiling, not a ban: the deliberate literals are documented."""
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "index.css").write_text(".tooltip { background: #1a1a2e; }\n", encoding="utf-8")
    monkeypatch.setattr(drift, "PORTAL", tmp_path)
    monkeypatch.setattr(drift, "THEME_LITERAL_BUDGET", 1)
    assert not drift.check_theme_literals()


def test_reports_a_missing_stylesheet(stylesheet, tmp_path, monkeypatch):
    """Silence would otherwise read as compliance."""
    monkeypatch.setattr(drift, "PORTAL", tmp_path / "absent")
    findings = drift.check_theme_literals()
    assert findings and "missing" in findings[0].detail


class TestInlineStyleLiterals:
    """A literal in a JSX `style={{ }}` cannot be restyled by any later rule.

    This is where the theme leaked the second time, and it leaked because the check
    on the stylesheet reads one file. Six agent task cards kept pale fills under the
    dark theme and took the dark theme's light text with them: a card title at
    1.1:1 against its own background, with every gate green.
    """

    @staticmethod
    def _run(tmp_path, monkeypatch, source: str, name: str = "Panel.tsx"):
        (tmp_path / "src").mkdir(exist_ok=True)
        (tmp_path / "src" / name).write_text(source, encoding="utf-8")
        monkeypatch.setattr(drift, "PORTAL", tmp_path)
        return drift.check_inline_style_literals()

    def test_finds_a_hex_fill(self, tmp_path, monkeypatch):
        findings = self._run(tmp_path, monkeypatch, 'const card = { background: "#ebf8ff" };\n')
        assert findings and "#ebf8ff" in findings[0].detail

    def test_finds_a_literal_hiding_in_a_var_fallback(self, tmp_path, monkeypatch):
        """The shape that read as themed and never was."""
        findings = self._run(tmp_path, monkeypatch, 'const s = { color: "var(--accent-color, #0066cc)" };\n')
        assert findings and "#0066cc" in findings[0].detail

    def test_accepts_a_token_reference(self, tmp_path, monkeypatch):
        assert not self._run(tmp_path, monkeypatch, 'const s = { background: "var(--color-primary-light)" };\n')

    def test_has_no_budget(self, tmp_path, monkeypatch):
        """One is reported. There is no case for a literal that cannot be restyled."""
        assert self._run(tmp_path, monkeypatch, 'const s = { color: "#fff" };\n')

    def test_finds_literals_a_ternary_puts_past_the_colon(self, tmp_path, monkeypatch):
        """The shape this rule could not see, taken from the volume capacity bar.

        The value of a colour property is an expression as often as it is a string.
        Anchoring on a quote directly after the colon meant three hex fills chosen
        by a ternary were invisible here, and they stayed light under the dark theme.
        """
        findings = self._run(
            tmp_path,
            monkeypatch,
            'const bar = { backgroundColor: pct > 90 ? "#ef4444" : pct > 75 ? "#f97316" : "#22c55e" };\n',
        )
        # One finding per literal: each is a separate fill somebody has to replace.
        assert len(findings) == 3
        reported = " ".join(f.detail for f in findings)
        assert all(literal in reported for literal in ("#ef4444", "#f97316", "#22c55e"))

    def test_accepts_a_ternary_that_picks_between_tokens(self, tmp_path, monkeypatch):
        """The fix for the above, which must not be reported in turn."""
        assert not self._run(
            tmp_path,
            monkeypatch,
            'const bar = { backgroundColor: pct > 90 ? "var(--color-error)" : "var(--color-success)" };\n',
        )

    def test_reports_each_occurrence_separately(self, tmp_path, monkeypatch):
        """Per-line, unlike the stylesheet count: each one is a specific component."""
        findings = self._run(
            tmp_path,
            monkeypatch,
            'const a = { background: "#fff5f5" };\nconst b = { borderColor: "#fed7d7" };\n',
        )
        assert len(findings) == 2
        assert {f.location.rsplit(":", 1)[1] for f in findings} == {"1", "2"}


class TestUndefinedTokens:
    """`var(--name)` where the palette has no `--name`.

    The quietest of the three failures. Ten invented names were in use across 71
    references -- `--text-secondary` for `--color-text-secondary`, `--surface-color`
    for `--color-surface`. Each resolved to its fallback every time, and the ones
    written without a fallback dropped the declaration entirely, so the text
    inherited whatever it sat on.
    """

    @staticmethod
    def _run(tmp_path, monkeypatch, css: str, extra: dict[str, str] | None = None):
        (tmp_path / "src").mkdir(exist_ok=True)
        (tmp_path / "src" / "index.css").write_text(css, encoding="utf-8")
        for name, source in (extra or {}).items():
            (tmp_path / "src" / name).write_text(source, encoding="utf-8")
        monkeypatch.setattr(drift, "PORTAL", tmp_path)
        return drift.check_undefined_tokens()

    PALETTE = ":root {\n  --color-surface: #ffffff;\n  --color-text-secondary: #5f6b7a;\n}\n"

    def test_finds_an_invented_name(self, tmp_path, monkeypatch):
        findings = self._run(tmp_path, monkeypatch, self.PALETTE + ".x { color: var(--text-secondary, #666); }\n")
        assert findings and "--text-secondary" in findings[0].detail

    def test_finds_one_with_no_fallback(self, tmp_path, monkeypatch):
        """Worse than the fallback case: the declaration is dropped."""
        findings = self._run(tmp_path, monkeypatch, self.PALETTE + ".x { border: 1px solid var(--border-color); }\n")
        assert findings and "dropping the declaration" in findings[0].detail

    def test_accepts_every_defined_token(self, tmp_path, monkeypatch):
        assert not self._run(
            tmp_path,
            monkeypatch,
            self.PALETTE + ".x { background: var(--color-surface); color: var(--color-text-secondary); }\n",
        )

    def test_reads_definitions_beyond_the_first_line(self, tmp_path, monkeypatch):
        """The regression in the check itself.

        Definitions are collected with findall over the whole file. Without
        re.MULTILINE only the first line could match, so every token read as
        undefined -- 969 findings, which looks like a broken check rather than a
        broken stylesheet, and would have been silenced by whoever hit it.
        """
        css = ":root {\n  --color-a: #111;\n  --color-b: #222;\n  --color-c: #333;\n}\n.x { color: var(--color-c); }\n"
        assert not self._run(tmp_path, monkeypatch, css)

    def test_covers_tsx_as_well_as_css(self, tmp_path, monkeypatch):
        findings = self._run(
            tmp_path,
            monkeypatch,
            self.PALETTE,
            {"Panel.tsx": 'const s = { background: "var(--surface-color)" };\n'},
        )
        assert findings and "Panel.tsx" in findings[0].location

    def test_suggests_a_defined_name_when_one_is_close(self, tmp_path, monkeypatch):
        findings = self._run(tmp_path, monkeypatch, self.PALETTE + ".x { background: var(--surface); }\n")
        assert findings and "Did you mean --color-surface?" in findings[0].detail


class TestLocaleEscaping:
    r"""Locale strings escaped one level too many.

    37 strings across all eight locales read `\\"` where they meant `\"`, so a
    confirmation dialog said `Delete user \"admin\"?` in every language. Nothing
    caught it: the key exists everywhere, the types agree, the value is a valid
    string. Only its content was wrong, and a diff of escaped CJK is where an eye
    slides past.
    """

    @staticmethod
    def _run(tmp_path, monkeypatch, source: str):
        locales = tmp_path / "src" / "i18n" / "locales"
        locales.mkdir(parents=True, exist_ok=True)
        (locales / "ja.ts").write_text(source, encoding="utf-8")
        monkeypatch.setattr(drift, "PORTAL", tmp_path)
        return drift.check_locale_escaping()

    def test_finds_an_over_escaped_quote(self, tmp_path, monkeypatch):
        r"""Three backslashes then a quote: the exact form that shipped."""
        findings = self._run(tmp_path, monkeypatch, r'  a: "Delete user \\\"{name}\\\"?",' + "\n")
        assert findings, "this rendered the backslashes to the user in all eight locales"

    def test_finds_an_over_escaped_backslash(self, tmp_path, monkeypatch):
        r"""Four backslashes render two; the placeholder wants one."""
        findings = self._run(tmp_path, monkeypatch, r'  b: "User name or DOMAIN\\\\user",' + "\n")
        assert findings

    def test_accepts_a_correctly_escaped_quote(self, tmp_path, monkeypatch):
        assert not self._run(tmp_path, monkeypatch, r'  c: "Delete user \"{name}\"?",' + "\n")

    def test_accepts_a_correctly_escaped_backslash(self, tmp_path, monkeypatch):
        assert not self._run(tmp_path, monkeypatch, r'  d: "User name or DOMAIN\\user",' + "\n")

    def test_accepts_plain_text(self, tmp_path, monkeypatch):
        assert not self._run(tmp_path, monkeypatch, '  e: "ユーザーを削除しますか？",\n')

    def test_reports_a_missing_locale_directory(self, tmp_path, monkeypatch):
        monkeypatch.setattr(drift, "PORTAL", tmp_path / "absent")
        findings = drift.check_locale_escaping()
        assert findings and "missing" in findings[0].detail


class TestHardcodedStringsOnATCall:
    """A t() call on the line no longer excuses an untranslated literal.

    t() ends `?? key`, so it always returns a non-empty string and
    `t("x") || "literal"` never reaches the literal. The old rule waved through any
    line mentioning t(), which let 29 dead Japanese fallbacks and a
    `deleting ? "削除中..." : t("rmDelete")` ternary sit in one component, counted as
    benign.
    """

    @staticmethod
    def _run(tmp_path, monkeypatch, source: str):
        (tmp_path / "src").mkdir(exist_ok=True)
        (tmp_path / "src" / "Panel.tsx").write_text(source, encoding="utf-8")
        monkeypatch.setattr(drift, "PORTAL", tmp_path)
        findings, _ = drift.check_hardcoded_strings(baseline=set())
        return [f for f in findings if f.location != "(how to resolve)"]

    def test_flags_a_literal_in_a_ternary_beside_a_t_call(self, tmp_path, monkeypatch):
        source = 'const a = <span>{deleting ? "削除中..." : t("rmDelete")}</span>;\n'
        assert self._run(tmp_path, monkeypatch, source)

    def test_flags_a_dead_or_fallback(self, tmp_path, monkeypatch):
        source = 'const b = <span>{t("fcacheCreated") || "作成しました"}</span>;\n'
        assert self._run(tmp_path, monkeypatch, source)

    def test_flags_bare_jsx_text(self, tmp_path, monkeypatch):
        assert self._run(tmp_path, monkeypatch, "const c = <span>合計</span>;\n")

    def test_accepts_a_line_that_only_calls_t(self, tmp_path, monkeypatch):
        assert not self._run(tmp_path, monkeypatch, 'const d = <span>{t("rmDelete")}</span>;\n')

    def test_ignores_cjk_outside_a_literal_or_text_node(self, tmp_path, monkeypatch):
        """A comment is stripped before the line is examined."""
        assert not self._run(tmp_path, monkeypatch, "// 削除ボタンのラベル\nconst e = 1;\n")


class TestThemeContrast:
    """Text against its fill, in both themes.

    Tokens made the theme switchable without making it legible. The dark palette
    lightens the accent fills -- it must, or they disappear against a dark page -- and
    inverse text stayed white on top: every primary button at 3.4:1, the approve
    button at 2.8:1. No rule was a light slab, so every colour rule above was
    satisfied. This is what forced --color-on-primary / -success / -error: text that
    flips with the theme while its fill does not.
    """

    PALETTE = (
        ":root {\n"
        "  --color-primary: #0972d3;\n"
        "  --color-text-inverse: #ffffff;\n"
        "  --color-on-primary: #ffffff;\n"
        "  --color-surface: #ffffff;\n"
        "  --color-text: #16191f;\n"
        "}\n"
        '[data-theme="dark"] {\n'
        "  --color-primary: #3b8fe0;\n"
        "  --color-text-inverse: #ffffff;\n"
        "  --color-on-primary: #08182b;\n"
        "  --color-surface: #1c2128;\n"
        "  --color-text: #e6edf3;\n"
        "}\n"
    )

    @staticmethod
    def _run(tmp_path, monkeypatch, rules: str):
        (tmp_path / "src").mkdir(exist_ok=True)
        (tmp_path / "src" / "index.css").write_text(TestThemeContrast.PALETTE + rules, encoding="utf-8")
        monkeypatch.setattr(drift, "PORTAL", tmp_path)
        return drift.check_theme_contrast()

    def test_finds_inverse_text_on_an_accent_fill(self, tmp_path, monkeypatch):
        """The shape that shipped on every primary button."""
        rules = ".btn { background: var(--color-primary); color: var(--color-text-inverse); }\n"
        findings = self._run(tmp_path, monkeypatch, rules)
        assert len(findings) == 1, findings
        assert "dark" in findings[0].location
        assert "3.4:1" in findings[0].detail

    def test_accepts_the_on_token(self, tmp_path, monkeypatch):
        """The fix: text that flips, on a fill that does not."""
        rules = ".btn { background: var(--color-primary); color: var(--color-on-primary); }\n"
        assert not self._run(tmp_path, monkeypatch, rules)

    def test_checks_both_themes(self, tmp_path, monkeypatch):
        """A pair can be legible in one theme and not the other, which is the point."""
        rules = ".odd { background: var(--color-surface); color: var(--color-text-inverse); }\n"
        findings = self._run(tmp_path, monkeypatch, rules)
        assert len(findings) == 1
        assert "light" in findings[0].location

    def test_accepts_a_pair_that_passes_in_both(self, tmp_path, monkeypatch):
        rules = ".body { background: var(--color-surface); color: var(--color-text); }\n"
        assert not self._run(tmp_path, monkeypatch, rules)

    def test_large_bold_text_uses_the_lower_threshold(self, tmp_path, monkeypatch):
        """WCAG allows 3:1 for large text, and a heading is not a caption."""
        rules = (
            ".head { background: var(--color-primary); color: var(--color-text-inverse);"
            " font-size: 1.5rem; font-weight: 700; }\n"
        )
        assert not self._run(tmp_path, monkeypatch, rules)

    def test_small_text_on_the_same_pair_is_still_reported(self, tmp_path, monkeypatch):
        rules = ".small { background: var(--color-primary); color: var(--color-text-inverse); font-size: 0.75rem; }\n"
        assert self._run(tmp_path, monkeypatch, rules)

    def test_skips_a_translucent_fill(self, tmp_path, monkeypatch):
        """`rgba(0, 0, 0, 0.05)` over a card is a real technique.

        Treating it as opaque black reports 1.2:1 for text that is comfortably
        legible, and a check that cries wolf gets switched off. Compositing needs the
        cascade, so those belong to the browser sweep.
        """
        rules = ".chip { background: rgba(0, 0, 0, 0.05); color: var(--color-text); }\n"
        assert not self._run(tmp_path, monkeypatch, rules)

    def test_ignores_a_rule_that_sets_only_one_of_the_two(self, tmp_path, monkeypatch):
        """Without both in the same rule the pairing needs the cascade to resolve."""
        rules = ".only-fill { background: var(--color-primary); }\n.only-text { color: var(--color-text-inverse); }\n"
        assert not self._run(tmp_path, monkeypatch, rules)

    def test_does_not_mistake_border_colour_for_text(self, tmp_path, monkeypatch):
        """`border-color` is not text, and a 3:1 border is not a defect."""
        rules = ".bordered { background: var(--color-surface); border-color: var(--color-primary); }\n"
        assert not self._run(tmp_path, monkeypatch, rules)

    def test_reports_a_palette_that_is_not_a_pair(self, tmp_path, monkeypatch):
        """One palette means the comparison it exists to make cannot happen."""
        (tmp_path / "src").mkdir(exist_ok=True)
        (tmp_path / "src" / "index.css").write_text(":root {\n  --color-text: #16191f;\n}\n", encoding="utf-8")
        monkeypatch.setattr(drift, "PORTAL", tmp_path)
        findings = drift.check_theme_contrast()
        assert findings and "palette" in findings[0].detail


class TestDeadMediaOverrides:
    """Responsive rules the cascade throws away.

    A media query adds no specificity, so a mobile rule loses to the same selector
    later in the file and to any more specific selector anywhere in it. The
    declaration stays present, valid and ignored.

    Two were live at once. `.portal-layout { grid-template-columns: minmax(0, 1fr) }`
    lost to `.portal-layout.sidebar-collapsed` 200 lines earlier -- and collapsed is
    the default state on a phone, so the desktop three-column grid was applied against
    a one-area template and the topbar rendered 40px wide. Both were found by reading
    computed styles in a browser, one rule at a time.
    """

    @staticmethod
    def _run(tmp_path, monkeypatch, css: str):
        (tmp_path / "src").mkdir(exist_ok=True)
        (tmp_path / "src" / "index.css").write_text(css, encoding="utf-8")
        monkeypatch.setattr(drift, "PORTAL", tmp_path)
        return drift.check_dead_media_overrides()

    def test_finds_a_loss_to_higher_specificity(self, tmp_path, monkeypatch):
        """The 40px topbar, reduced to its two rules."""
        css = (
            ".layout { grid-template-columns: 220px 1fr; }\n"
            ".layout.collapsed { grid-template-columns: 0px 1fr; }\n"
            "@media (max-width: 768px) {\n  .layout { grid-template-columns: minmax(0, 1fr); }\n}\n"
        )
        findings = self._run(tmp_path, monkeypatch, css)
        assert len(findings) == 1, findings
        assert "specificity" in findings[0].detail

    def test_finds_a_loss_to_source_order(self, tmp_path, monkeypatch):
        """Same selector, later in the file: the checkbox case."""
        css = "@media (max-width: 768px) {\n  .box { width: 24px; }\n}\n.box { width: 14px; }\n"
        findings = self._run(tmp_path, monkeypatch, css)
        assert len(findings) == 1, findings
        assert "source order" in findings[0].detail

    def test_accepts_a_rule_declared_before_the_media_block(self, tmp_path, monkeypatch):
        """Equal specificity and earlier: the media rule wins, which is the norm."""
        css = ".box { width: 14px; }\n@media (max-width: 768px) {\n  .box { width: 24px; }\n}\n"
        assert not self._run(tmp_path, monkeypatch, css)

    def test_a_companion_rule_in_the_same_block_rescues_it(self, tmp_path, monkeypatch):
        """The fix that was applied: name the stronger selector in the block too."""
        css = (
            ".layout { grid-template-columns: 220px 1fr; }\n"
            ".layout.collapsed { grid-template-columns: 0px 1fr; }\n"
            "@media (max-width: 768px) {\n"
            "  .layout { grid-template-columns: minmax(0, 1fr); }\n"
            "  .layout.collapsed { grid-template-columns: minmax(0, 1fr); }\n"
            "}\n"
        )
        assert not self._run(tmp_path, monkeypatch, css)

    def test_important_in_the_media_block_is_not_reported(self, tmp_path, monkeypatch):
        """The field-size floor uses it deliberately.

        The browser zooms the viewport for any field under 16px regardless of which
        component owns the field, so the floor has to outrank component styling.
        """
        css = (
            ".panel textarea { font-size: 0.9rem; }\n"
            "@media (max-width: 768px) {\n  textarea { font-size: 16px !important; }\n}\n"
        )
        assert not self._run(tmp_path, monkeypatch, css)

    def test_a_descendant_selector_is_not_an_override(self, tmp_path, monkeypatch):
        """`.table th` styles a different element from `.table`.

        Four of the eight findings on the first pass were this, and a check that
        reports them gets switched off.
        """
        css = "@media (max-width: 768px) {\n  .table { font-size: 0.75rem; }\n}\n.table th { font-size: 0.9rem; }\n"
        assert not self._run(tmp_path, monkeypatch, css)

    def test_an_identical_value_is_not_reported(self, tmp_path, monkeypatch):
        """Losing to a rule that says the same thing changes nothing."""
        css = "@media (max-width: 768px) {\n  .box { width: 14px; }\n}\n.box { width: 14px; }\n"
        assert not self._run(tmp_path, monkeypatch, css)

    def test_only_max_width_blocks_are_considered(self, tmp_path, monkeypatch):
        """A print or min-width block is not the responsive layout this guards."""
        css = "@media print {\n  .box { width: 24px; }\n}\n.box { width: 14px; }\n"
        assert not self._run(tmp_path, monkeypatch, css)

    def test_reports_a_missing_stylesheet(self, tmp_path, monkeypatch):
        monkeypatch.setattr(drift, "PORTAL", tmp_path / "absent")
        findings = drift.check_dead_media_overrides()
        assert findings and "missing" in findings[0].detail


class TestDeadMediaOverrideRescue:
    """When a second rule in the same breakpoint counts as a fix, and when it does not.

    The rescue clause is where this check got the answer wrong twice, and both wrong
    answers were silent: it reported nothing while the defect was present.
    """

    @staticmethod
    def _run(tmp_path, monkeypatch, css: str):
        (tmp_path / "src").mkdir(exist_ok=True)
        (tmp_path / "src" / "index.css").write_text(css, encoding="utf-8")
        monkeypatch.setattr(drift, "PORTAL", tmp_path)
        return drift.check_dead_media_overrides()

    def test_two_identical_dead_rules_do_not_rescue_each_other(self, tmp_path, monkeypatch):
        """Both are before the winner, so neither applies -- and both are reported.

        Two `.form-group label` rules existed in two blocks with the same media text,
        each satisfying "a sibling at this breakpoint also sets it" for the other. The
        pair reported nothing while the label stayed at the desktop size.
        """
        css = (
            "@media (max-width: 480px) {\n  .a label { font-size: 0.85rem; }\n}\n"
            "@media (max-width: 480px) {\n  .a label { font-size: 0.85rem; }\n}\n"
            ".a label { font-size: 0.78rem; }\n"
        )
        assert len(self._run(tmp_path, monkeypatch, css)) == 2

    def test_a_sibling_after_the_winner_does_rescue(self, tmp_path, monkeypatch):
        """Equal specificity and later in the file is exactly how the cascade decides."""
        css = (
            "@media (max-width: 480px) {\n  .a label { font-size: 0.85rem; }\n}\n"
            ".a label { font-size: 0.78rem; }\n"
            "@media (max-width: 480px) {\n  .a label { font-size: 0.85rem; }\n}\n"
        )
        assert not self._run(tmp_path, monkeypatch, css)

    def test_a_more_specific_sibling_rescues_from_anywhere(self, tmp_path, monkeypatch):
        """The shape of the applied fix for the collapsed-sidebar grid."""
        css = (
            ".layout { grid-template-columns: 220px 1fr; }\n"
            ".layout.collapsed { grid-template-columns: 0px 1fr; }\n"
            "@media (max-width: 768px) {\n"
            "  .layout { grid-template-columns: minmax(0, 1fr); }\n"
            "  .layout.collapsed { grid-template-columns: minmax(0, 1fr); }\n"
            "}\n"
        )
        assert not self._run(tmp_path, monkeypatch, css)

    def test_a_rule_does_not_rescue_itself(self, tmp_path, monkeypatch):
        """A selector's specificity is trivially >= its own.

        Without excluding the rule under test, every loss on source order was
        dismissed as already handled.
        """
        css = "@media (max-width: 768px) {\n  .box { width: 24px; }\n}\n.box { width: 14px; }\n"
        assert len(self._run(tmp_path, monkeypatch, css)) == 1


class TestBreakpointAgreement:
    """One number, two files.

    The stylesheet decides when the sidebar becomes a drawer over the content. App.tsx
    decides when it should start closed and close itself after a section is picked.
    Between two disagreeing values there is a band of widths where the drawer covers
    the content and nothing dismisses it -- the state the portal shipped in at every
    width, so not a hypothetical.
    """

    @staticmethod
    def _run(tmp_path, monkeypatch, app: str, css: str):
        (tmp_path / "src").mkdir(exist_ok=True)
        (tmp_path / "src" / "App.tsx").write_text(app, encoding="utf-8")
        (tmp_path / "src" / "index.css").write_text(css, encoding="utf-8")
        monkeypatch.setattr(drift, "PORTAL", tmp_path)
        return drift.check_breakpoint_agreement()

    def test_agreement_passes(self, tmp_path, monkeypatch):
        app = "const NARROW_VIEWPORT = 768;\n"
        css = "@media (max-width: 768px) {\n  .a { color: red; }\n}\n"
        assert not self._run(tmp_path, monkeypatch, app, css)

    def test_a_mismatch_is_reported(self, tmp_path, monkeypatch):
        app = "const NARROW_VIEWPORT = 700;\n"
        css = "@media (max-width: 768px) {\n  .a { color: red; }\n}\n"
        findings = self._run(tmp_path, monkeypatch, app, css)
        assert findings and "700px" in findings[0].detail

    def test_any_matching_breakpoint_counts(self, tmp_path, monkeypatch):
        """The stylesheet has several; the constant has to match one of them."""
        app = "const NARROW_VIEWPORT = 480;\n"
        css = (
            "@media (max-width: 768px) {\n  .a { color: red; }\n}\n"
            "@media (max-width: 480px) {\n  .b { color: blue; }\n}\n"
        )
        assert not self._run(tmp_path, monkeypatch, app, css)

    def test_a_renamed_constant_is_reported_rather_than_ignored(self, tmp_path, monkeypatch):
        """Not finding the constant is the outcome that would help nobody.

        A check that goes quiet when its anchor disappears reports success for a file
        it is no longer reading.
        """
        app = "const SOMETHING_ELSE = 768;\n"
        css = "@media (max-width: 768px) {\n  .a { color: red; }\n}\n"
        findings = self._run(tmp_path, monkeypatch, app, css)
        assert findings and "gone" in findings[0].detail

    def test_missing_files_are_reported(self, tmp_path, monkeypatch):
        monkeypatch.setattr(drift, "PORTAL", tmp_path / "absent")
        findings = drift.check_breakpoint_agreement()
        assert findings and "missing" in findings[0].detail


class TestDeadMediaOverrideScope:
    """What counts as a competing rule, and what only looks like one.

    Widening this check to compare two media blocks against each other immediately
    produced two findings that were correct CSS, so the shape of "the same box,
    unconditionally" had to be pinned down.
    """

    @staticmethod
    def _run(tmp_path, monkeypatch, css: str):
        (tmp_path / "src").mkdir(exist_ok=True)
        (tmp_path / "src" / "index.css").write_text(css, encoding="utf-8")
        monkeypatch.setattr(drift, "PORTAL", tmp_path)
        return drift.check_dead_media_overrides()

    def test_two_blocks_at_the_same_breakpoint_compete(self, tmp_path, monkeypatch):
        """The gap that let a redundant bottom-sheet rule be written.

        `.file-preview-popover` was given a second mobile treatment at the same
        breakpoint while an existing one 700 lines later was doing the work. Both were
        inside media queries, and the check only looked at unqueried rules.
        """
        css = (
            "@media (max-width: 768px) {\n  .sheet { top: 52px; }\n}\n"
            "@media (max-width: 768px) {\n  .sheet { top: auto; }\n}\n"
        )
        findings = self._run(tmp_path, monkeypatch, css)
        assert len(findings) == 1, findings
        assert "top" in findings[0].detail

    def test_a_narrower_breakpoint_does_not_count(self, tmp_path, monkeypatch):
        """480 inside 768 is how breakpoints nest, not a mistake."""
        css = (
            "@media (max-width: 768px) {\n  .box { padding: 1rem; }\n}\n"
            "@media (max-width: 480px) {\n  .box { padding: 0.5rem; }\n}\n"
        )
        assert not self._run(tmp_path, monkeypatch, css)

    def test_a_pseudo_element_is_a_different_box(self, tmp_path, monkeypatch):
        """`.file-select:checked::before` does not override `.file-select`."""
        css = (
            "@media (max-width: 768px) {\n  .check { background: none; }\n}\n"
            ".check:checked::before { background: blue; }\n"
        )
        assert not self._run(tmp_path, monkeypatch, css)

    def test_a_state_selector_with_an_extra_ancestor_does_not_count(self, tmp_path, monkeypatch):
        """How the drawer is built: a default, overridden by a state on an ancestor.

        `.portal-layout:not(.sidebar-collapsed) .portal-sidebar` is meant to beat
        `.portal-sidebar`.
        """
        css = (
            "@media (max-width: 768px) {\n  .drawer { transform: translateX(-100%); }\n}\n"
            "@media (max-width: 768px) {\n  .layout:not(.closed) .drawer { transform: translateX(0); }\n}\n"
        )
        assert not self._run(tmp_path, monkeypatch, css)

    def test_a_descendant_of_the_same_name_does_not_count(self, tmp_path, monkeypatch):
        css = "@media (max-width: 768px) {\n  .table { font-size: 12px; }\n}\n.table td { font-size: 14px; }\n"
        assert not self._run(tmp_path, monkeypatch, css)

    def test_an_extra_class_on_the_same_compound_still_counts(self, tmp_path, monkeypatch):
        """The verified real case: the collapsed-sidebar grid."""
        css = (
            ".layout.collapsed { grid-template-columns: 0px 1fr; }\n"
            "@media (max-width: 768px) {\n  .layout { grid-template-columns: minmax(0, 1fr); }\n}\n"
        )
        assert len(self._run(tmp_path, monkeypatch, css)) == 1

    def test_the_same_ancestor_chain_still_counts(self, tmp_path, monkeypatch):
        """Depth is fine as long as it matches; it is a *difference* in depth that is not."""
        css = (
            "@media (max-width: 768px) {\n  .panel .field { font-size: 16px; }\n}\n.panel .field { font-size: 13px; }\n"
        )
        assert len(self._run(tmp_path, monkeypatch, css)) == 1
