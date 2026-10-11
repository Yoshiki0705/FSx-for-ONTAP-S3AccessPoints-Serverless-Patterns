"""Static contract between 07_portal_config.sh --ui and the Playwright spec.

Nothing here runs a browser. These tests read the spec, the portal component, the
locale file and the backend definition as text and pin the agreements the spec relies
on, so a change on either side fails here before it reaches a real run (which is not yet
run on real environment, E20/E25).

The checks (plan 3.3 C6, design 10.5):

* the element ids the spec uses (``rp-region``, ``rp-vault-scope``) exist in the portal
  component;
* the spec reads its UI strings from ``src/i18n/locales/en`` instead of duplicating them;
* the spec never clicks ``rpRestoreConfirm`` (a negative control proves the check bites);
* the presence check of the Restore button is not a ``test.skip`` (a user who is not a
  storage admin must fail the test, not silently skip it);
* the spec registers no test when ``LAB_UI_EXPECT`` is unset;
* the three ``LAB_UI_EXPECT`` values equal the ``--expect`` set of 07;
* the function description 07 matches by equals the one in ``backend.ts``.
"""

from __future__ import annotations

import re
from pathlib import Path

from lab_testlib import LAB_SRC

PORTAL = LAB_SRC.parents[1] / "solutions" / "amplify-portal"
SPEC = PORTAL / "tests" / "e2e" / "shared-vault-lab.spec.ts"
COMPONENT = PORTAL / "src" / "components" / "RecoveryPoints.tsx"
LOCALE_EN = PORTAL / "src" / "i18n" / "locales" / "en.ts"
BACKEND = PORTAL / "amplify" / "backend.ts"
SCRIPT = LAB_SRC / "scripts" / "07_portal_config.sh"

SPEC_TEXT = SPEC.read_text(encoding="utf-8")


def _spec_without_comments() -> str:
    """The spec text with block and line comments removed (so a comment cannot satisfy a check)."""
    no_block = re.sub(r"/\*.*?\*/", "", SPEC_TEXT, flags=re.DOTALL)
    return re.sub(r"//.*", "", no_block)


def test_spec_uses_ids_that_exist_in_the_component() -> None:
    component = COMPONENT.read_text(encoding="utf-8")
    for element_id in ("rp-region", "rp-vault-scope"):
        assert f"#{element_id}" in SPEC_TEXT, f"the spec no longer uses #{element_id}"
        assert f'id="{element_id}"' in component, f"RecoveryPoints.tsx has no element with id {element_id}"


def test_spec_imports_strings_from_the_english_locale() -> None:
    assert re.search(r'import\s*\{\s*en\s*\}\s*from\s*"\.\./\.\./src/i18n/locales/en"', SPEC_TEXT), (
        "the spec must import { en } from the English locale"
    )
    # The strings it asserts on are referenced through en.*, not duplicated as literals.
    locale = LOCALE_EN.read_text(encoding="utf-8")
    for key in (
        "rpTitle",
        "rpScopeSharedGroup",
        "rpAccessDeniedHint",
        "rpVaultAirgapped",
        "rpVaultOwner",
        "rpRestore",
        "rpRestoreTitle",
        "rpRestoreConfirm",
        "rpRestoreCancel",
        "rpNoSharedVaults",
    ):
        assert f"en.{key}" in SPEC_TEXT, f"the spec does not reference en.{key}"
        assert re.search(rf"\b{key}\s*:", locale), f"the English locale has no key {key}"


def _clicks_the_confirm_button(body: str) -> bool:
    """True if the spec clicks the restore confirm button, directly or through a variable.

    A click can be chained on the rpRestoreConfirm locator, or on a variable the locator
    is assigned to (``const startButton = ...rpRestoreConfirm...; startButton.click()``).
    """
    if re.search(r"rpRestoreConfirm[^\n]*\)\s*\.click\(", body):
        return True
    confirm_vars = set(re.findall(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*[^\n;]*rpRestoreConfirm", body))
    return any(re.search(rf"\b{re.escape(name)}\s*\.click\(", body) for name in confirm_vars)


def test_spec_never_clicks_the_restore_confirm_button() -> None:
    body = _spec_without_comments()
    assert "rpRestoreConfirm" in body, "the spec no longer references the confirm button at all"
    assert not _clicks_the_confirm_button(body), "the spec clicks the restore confirm button"
    # Negative control: a click on the variable the confirm button is bound to must be caught
    # by the same function that guards the real spec.
    anchor = 'const startButton = dialog.getByRole("button", { name: en.rpRestoreConfirm });'
    assert anchor in body, "the anchor line for the negative control moved; update this test"
    injected = body.replace(anchor, anchor + "\n    await startButton.click();")
    assert _clicks_the_confirm_button(injected), "the negative control is not detected"


def test_restore_button_presence_is_not_skipped() -> None:
    body = _spec_without_comments()
    # The arn-present flow asserts the Restore button is visible; it must not be test.skip.
    assert "test.skip" not in body, "the spec uses test.skip; the Restore presence check must fail, not skip"
    assert "rpRestore" in body and "toBeVisible" in body


def test_spec_registers_no_test_when_the_expectation_is_unset() -> None:
    body = _spec_without_comments()
    # Every test() is nested under `if (EXPECT !== null)`, which guards the describe block.
    assert "if (EXPECT !== null)" in body, "the describe block is not guarded by EXPECT !== null"
    guard = body.index("if (EXPECT !== null)")
    assert "test(" not in body[:guard], "a test() is registered before the EXPECT guard"
    # Any non-empty value outside the three throws at load.
    assert "throw new Error" in SPEC_TEXT


def test_spec_values_equal_the_script_expect_set() -> None:
    values = re.search(r"const VALID_EXPECT = \[([^\]]*)\]", SPEC_TEXT)
    assert values, "VALID_EXPECT not found in the spec"
    spec_values = set(re.findall(r'"([^"]+)"', values.group(1)))
    script = SCRIPT.read_text(encoding="utf-8")
    script_values = set(re.search(r'EXPECT_VALUES="([^"]+)"', script).group(1).split())
    assert spec_values == script_values == {"arn-missing", "arn-present", "revoked"}


def test_function_description_matches_the_backend() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    script_desc = re.search(r'PORTAL_CHECK_DESCRIPTION="([^"]+)"', script).group(1)
    backend = BACKEND.read_text(encoding="utf-8")
    # backend.ts has more than one description:; take the recovery-points one, which may be
    # split across two lines. The match must be the string 07 compares against at runtime.
    descriptions = re.findall(r"description:\s*\n?\s*\"([^\"]+)\"", backend)
    recovery = [d for d in descriptions if "recovery points" in d.lower()]
    assert recovery, "no recovery-points description string found in backend.ts"
    assert script_desc in recovery, (
        f"07's PORTAL_CHECK_DESCRIPTION ({script_desc!r}) is not a recovery-points description in backend.ts "
        f"({recovery!r})"
    )
