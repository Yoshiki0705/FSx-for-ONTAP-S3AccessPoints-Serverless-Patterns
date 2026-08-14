"""Tests for the unsubstituted-placeholder check on the portal's translations.

The check exists because the quota panel asked `「{name}」を本当に削除しますか？` in a
delete confirmation, with the braces on screen. Four other panels call that same key and
all four substitute; this one passed the key through. Types, lint, the locale coverage
rules and the hardcoded-string rule all pass on it: the key exists in eight locales, the
string is valid, and `t()` returns exactly what it was handed.

The portal fills placeholders three ways, and the first version of this rule knew only
one of them -- `.replace("{tok}", value)` -- so it reported all four call sites that use
the `fill()` and `withNodes()` helpers instead. Those are the middle two cases here: a
rule that reports correct code is a rule someone turns off, which is the failure mode
this file is here to prevent.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import check_portal_drift as drift  # noqa: E402

# (ja.ts body, source body) -> findings for that pair.
Check = Callable[[str, str], list["drift.Finding"]]


@pytest.fixture
def portal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Check:
    """Point the check at a locale file and one source file this test writes.

    Args:
        tmp_path: Directory standing in for the portal root.
        monkeypatch: Used to repoint the module's `PORTAL` at it.

    Returns:
        A callable taking the ja.ts body and the source body, and returning the
        findings for that pair.
    """

    def write(locale: str, source: str) -> list[drift.Finding]:
        locales = tmp_path / "src" / "i18n" / "locales"
        locales.mkdir(parents=True, exist_ok=True)
        (locales / "ja.ts").write_text(f"export const ja = {{\n{locale}\n}};\n", encoding="utf-8")
        (tmp_path / "src" / "Panel.tsx").write_text(source, encoding="utf-8")
        monkeypatch.setattr(drift, "PORTAL", tmp_path)
        return drift.check_unsubstituted_placeholders()

    return write


DELETE_KEY = '  rmDeleteConfirm: "「{name}」を本当に削除しますか？",'


def test_reports_a_placeholder_nothing_replaces(portal: Check) -> None:
    """The regression: the key is used as-is, so the reader sees the braces."""
    findings = portal(DELETE_KEY, 'if (!window.confirm(t("rmDeleteConfirm"))) return;\n')

    assert findings, "an unsubstituted {name} in a confirm dialog shipped once"
    assert "{name}" in findings[0].detail
    assert "rmDeleteConfirm" in findings[0].detail


def test_accepts_a_replace_on_the_same_line(portal: Check) -> None:
    """The ordinary form: the substitution is part of the same expression."""
    findings = portal(
        DELETE_KEY,
        'if (!window.confirm(t("rmDeleteConfirm").replace("{name}", target))) return;\n',
    )

    assert findings == []


def test_accepts_a_replace_a_few_lines_later(portal: Check) -> None:
    """The file browser assigns the string first and substitutes on the next line."""
    findings = portal(
        '  filesBulkTrashConfirm: "{n} 件をゴミ箱へ移動しますか？",',
        'const question = inTrash ? t("filesBulkRestoreConfirm") : t("filesBulkTrashConfirm");\n'
        'if (!window.confirm(question.replace("{n}", String(targets.length)))) return;\n',
    )

    assert findings == []


def test_accepts_the_fill_helper_naming_the_token_as_a_key(portal: Check) -> None:
    """`fill(t(key), { n: days })` substitutes without ever writing "{n}"."""
    findings = portal(
        '  durationDaysWithMonths: "{n} 日 (約 {m} か月)",',
        'return fill(t("durationDaysWithMonths"), { n: days, m: days / 30 });\n',
    )

    assert findings == []


def test_accepts_the_withNodes_helper(portal: Check) -> None:
    """`withNodes` splices React nodes in, keyed the same way as `fill`."""
    findings = portal(
        '  aqExamplesNote: "{cmd} で一覧を確認できます",',
        '{withNodes(t("aqExamplesNote"), { cmd: <code>SHOW TABLES IN default</code> })}\n',
    )

    assert findings == []


def test_a_bare_property_of_the_same_name_does_not_excuse_a_plain_call(portal: Check) -> None:
    """Only a helper call may satisfy the rule by naming the token as a key.

    Otherwise any nearby `name:` -- and there is one in most mutation calls -- would
    silence the finding this file exists for.
    """
    findings = portal(
        DELETE_KEY,
        'if (!window.confirm(t("rmDeleteConfirm"))) return;\n'
        'const data = await adminMutate({ action: "deleteX", params: { name: target } });\n',
    )

    assert findings, "a `name:` property is not a substitution"


def test_reports_each_missing_token_separately_from_the_filled_one(portal: Check) -> None:
    """A key with two placeholders can have one of them filled in."""
    findings = portal(
        '  luRemoveMemberConfirm: "{member} を {group} から外しますか？",',
        'window.confirm(t("luRemoveMemberConfirm").replace("{member}", m.name));\n',
    )

    assert len(findings) == 1
    assert "{group}" in findings[0].detail
    assert "{member}" not in findings[0].detail


def test_ignores_keys_without_placeholders(portal: Check) -> None:
    """Most keys have none, and they are the bulk of every call site.

    The locale also carries a key that does have one, and the source does not call it:
    the file-level guard below is about a locale with no placeholders anywhere, not
    about a call site that needs no substitution.
    """
    findings = portal(
        f'  rmDelete: "削除",\n{DELETE_KEY}',
        'return <button>{t("rmDelete")}</button>;\n',
    )

    assert findings == []


def test_says_so_when_it_can_read_nothing(portal: Check) -> None:
    """A reader that sees no placeholders reports a clean tree, so it fails instead."""
    findings = portal('  rmDelete: "削除",', "")

    # No placeholders anywhere in the locale: the rule cannot be satisfied by silence.
    assert findings
    assert "no placeholders" in findings[0].detail


def test_an_exemption_needs_a_reason(portal: Check) -> None:
    """The marker with nothing after it is not a mute switch."""
    bare = portal(
        DELETE_KEY,
        '// i18n-placeholder-checked:\nwindow.confirm(t("rmDeleteConfirm"));\n',
    )
    assert bare, "a marker with no reason must not silence the rule"

    given = portal(
        DELETE_KEY,
        '// i18n-placeholder-checked: the caller substitutes downstream\nwindow.confirm(t("rmDeleteConfirm"));\n',
    )
    assert given == []
