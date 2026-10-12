"""Documentation parity and hygiene for the shared-vault lab (design 4.3, 14, 16).

Nothing here runs AWS. The tests read the README, the runbook and the verification
record (Japanese and English), the scripts, the templates and the UI spec as text.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from lab_testlib import LAB_SRC

DOCS = LAB_SRC / "docs"
SCRIPTS = LAB_SRC / "scripts"
TEMPLATES = LAB_SRC / "cloudformation"
REPO_SRC = LAB_SRC.parents[1]
SPEC = REPO_SRC / "solutions" / "amplify-portal" / "tests" / "e2e" / "shared-vault-lab.spec.ts"
REQUIRED_ACTIONS = SCRIPTS / "lib" / "required-actions.json"
LAB_ENV_EXAMPLE = LAB_SRC / "lab.env.example"
GETTING_STARTED = REPO_SRC / "solutions" / "amplify-portal" / "docs" / "GETTING-STARTED.md"

PAIRS = [
    (LAB_SRC / "README.md", LAB_SRC / "README.en.md"),
    (DOCS / "procedure.md", DOCS / "procedure.en.md"),
    (DOCS / "verification-record.md", DOCS / "verification-record.en.md"),
]

CJK = re.compile(r"[\u3000-\u30ff\u4e00-\u9fff]")
HEADING = re.compile(r"^(#{1,6}) ")
TABLE_ROW = re.compile(r"^\|.*\|\s*$")
CODE_FENCE = re.compile(r"^\s*(```|~~~)")


def _strip_fences(text: str) -> list[str]:
    out: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if CODE_FENCE.match(line):
            in_fence = not in_fence
            out.append("")
            continue
        out.append("" if in_fence else line)
    return out


def _heading_levels(text: str) -> list[int]:
    return [len(m.group(1)) for line in _strip_fences(text) if (m := HEADING.match(line))]


def _table_row_count(text: str) -> int:
    return sum(1 for line in _strip_fences(text) if TABLE_ROW.match(line))


# --------------------------------------------------------------------------
# JA / EN parity
# --------------------------------------------------------------------------


def test_heading_structure_parity() -> None:
    for ja, en in PAIRS:
        ja_levels = _heading_levels(ja.read_text(encoding="utf-8"))
        en_levels = _heading_levels(en.read_text(encoding="utf-8"))
        assert ja_levels == en_levels, f"{ja.name} vs {en.name}: heading levels differ ({ja_levels} vs {en_levels})"


def test_table_row_count_parity() -> None:
    for ja, en in PAIRS:
        ja_rows = _table_row_count(ja.read_text(encoding="utf-8"))
        en_rows = _table_row_count(en.read_text(encoding="utf-8"))
        assert ja_rows == en_rows, f"{ja.name} vs {en.name}: table row counts differ ({ja_rows} vs {en_rows})"


# --------------------------------------------------------------------------
# screenshot markers
# --------------------------------------------------------------------------

MARKER = re.compile(r"<!-- SCREENSHOT:\s*([^|]+)\|([^|]+)\|([^>]+?)-->")
LIST_PNG = re.compile(r"\| ([a-z0-9-]+\.png) \|")


def _marker_names(text: str) -> list[str]:
    names = [m.group(1).strip() for m in MARKER.finditer(text)]
    return [n for n in names if "<" not in n and ">" not in n]


def test_screenshot_markers_match_the_closing_list() -> None:
    for doc in (DOCS / "procedure.md", DOCS / "procedure.en.md"):
        text = doc.read_text(encoding="utf-8")
        markers = _marker_names(text)
        listed = LIST_PNG.findall(text)
        assert markers, f"{doc.name} has no screenshot markers"
        assert sorted(set(markers)) == sorted(set(listed)), (
            f"{doc.name}: marker set and closing list differ: "
            f"only in markers {sorted(set(markers) - set(listed))}, only in list {sorted(set(listed) - set(markers))}"
        )
        assert len(markers) == len(listed), f"{doc.name}: marker count {len(markers)} != list rows {len(listed)}"


def test_screenshot_markers_are_english() -> None:
    for doc in (DOCS / "procedure.md", DOCS / "procedure.en.md"):
        for m in MARKER.finditer(doc.read_text(encoding="utf-8")):
            name = m.group(1).strip()
            if "<" in name or ">" in name:
                continue  # the template-example marker, not a real screenshot
            whole = m.group(0)
            assert not CJK.search(whole), f"{doc.name}: a screenshot marker contains Japanese: {whole[:60]}"


def test_screenshot_marker_count_parity() -> None:
    ja = len(_marker_names((DOCS / "procedure.md").read_text(encoding="utf-8")))
    en = len(_marker_names((DOCS / "procedure.en.md").read_text(encoding="utf-8")))
    assert ja == en, f"screenshot marker counts differ: ja {ja}, en {en}"


# --------------------------------------------------------------------------
# English documents hold no Japanese
# --------------------------------------------------------------------------

# Japanese is written as \u escapes so the test file itself holds no Japanese bytes
# (the lab contract: no Japanese in scripts or tests).
SWITCHER = re.compile("\\[\u65e5\u672c\u8a9e\\]\\(")


def test_en_docs_have_no_japanese() -> None:
    for _, en in PAIRS:
        for number, line in enumerate(en.read_text(encoding="utf-8").splitlines(), 1):
            if SWITCHER.search(line):
                continue  # the language switcher is bilingual by design
            assert not CJK.search(line), f"{en.name}:{number} contains Japanese: {line.strip()[:80]}"


# --------------------------------------------------------------------------
# Japanese headings are noun phrases (global-writing-style detector)
# --------------------------------------------------------------------------

KANA = re.compile(r"[\u3040-\u30ff]")
VIOLATION = re.compile(
    "(\u307e\u3059|\u307e\u305b\u3093|\u3067\u3059|\u3067\u3057\u305f|\u304f\u3060\u3055\u3044|\u304b"
    "|[\u3046\u304f\u3050\u3059\u305a\u3064\u306c\u3075\u3076\u3080\u308b\u308c])$"
)
ALREADY_NOUN = re.compile(
    "(\u554f\u3044|\u9805\u76ee|\u624b\u9806|\u7bc4\u56f2|\u4e00\u89a7|\u7406\u7531|\u6761\u4ef6"
    "|\u5834\u5408|\u70b9|\u6271\u3044|\u3053\u3068|\u3082\u306e|\u5f62|\u578b)$"
)


def _noun_phrase_violations(text: str) -> list[str]:
    findings: list[str] = []
    for line in _strip_fences(text):
        m = HEADING.match(line)
        if not m:
            continue
        heading = line[len(m.group(1)) :].strip().rstrip(":\uff1a")
        if not KANA.search(heading):
            continue
        if VIOLATION.search(heading) and not ALREADY_NOUN.search(heading):
            findings.append(heading)
    return findings


def test_japanese_headings_are_noun_phrases() -> None:
    for ja, _ in PAIRS:
        violations = _noun_phrase_violations(ja.read_text(encoding="utf-8"))
        assert not violations, f"{ja.name}: non-noun-phrase headings: {violations}"


def test_noun_phrase_detector_has_a_negative_control() -> None:
    verb_heading = "## \u8a2d\u5b9a\u3092\u5909\u66f4\u3057\u307e\u3059\n"  # a heading ending in a verb
    noun_heading = "## \u8a2d\u5b9a\u306e\u5909\u66f4\u624b\u9806\n"  # a noun-phrase heading
    assert _noun_phrase_violations(verb_heading) == [verb_heading.strip().lstrip("# ")]
    assert _noun_phrase_violations(noun_heading) == []


# --------------------------------------------------------------------------
# internal-abbreviation ban (design 4.3)
# --------------------------------------------------------------------------

INTERNAL_ABBR = re.compile(
    "\\b[OTLCDFG][0-9]{1,2}\\b|\u7b2c ?[0-9.]+ ?\u7bc0"
    "|delivery-conventions-map|verification-log|redo-fact-sheet|design-review|\\.private"
)
# E and V are the public item letters, so EN / VN are allowed; so is 'ONTAP' etc.
INTERNAL_ABBR_ALLOW = re.compile(r"\b[EV][0-9]{1,2}\b")


def _internal_abbr_hits(text: str) -> list[str]:
    hits: list[str] = []
    for line in _strip_fences(text):
        cleaned = re.sub(r"`[^`]*`", "", line)
        for m in INTERNAL_ABBR.finditer(cleaned):
            token = m.group(0)
            if INTERNAL_ABBR_ALLOW.fullmatch(token):
                continue
            hits.append(token)
    return hits


def test_no_internal_abbreviations_in_published_docs() -> None:
    for ja, en in PAIRS:
        for doc in (ja, en):
            hits = _internal_abbr_hits(doc.read_text(encoding="utf-8"))
            assert not hits, f"{doc.name}: internal abbreviations leaked: {hits}"


def test_internal_abbreviation_detector_has_a_negative_control() -> None:
    positive = "See O12 and the \u7b2c 7.9 \u7bc0 of design-review."  # internal refs
    assert _internal_abbr_hits(positive)
    assert not _internal_abbr_hits("See V1 and E26 in the definition table.")


# --------------------------------------------------------------------------
# placeholder account ids, naming and neutrality
# --------------------------------------------------------------------------

REAL_ACCOUNT = re.compile(r"\b\d{12}\b")
PLACEHOLDER_ACCOUNTS = {"111122223333", "444455556666", "123456789012", "999999999999", "555500000000"}


def test_account_ids_are_placeholders() -> None:
    for ja, en in PAIRS:
        for doc in (ja, en):
            for number, raw in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
                line = re.sub(r"`[^`]*`", "", raw)
                for account in REAL_ACCOUNT.findall(line):
                    assert account in PLACEHOLDER_ACCOUNTS, f"{doc.name}:{number}: real-looking account id {account}"


FORBIDDEN_NAMING = re.compile(r"\bFSxN\b|\bFSx ONTAP\b|Workload Factory|NetApp Console|BlueXP")
NEUTRALITY = re.compile(
    "\\bbeats\\b|\u3088\u308a\u512a\u308c\u3066\u3044\u308b|\u7af6\u5408\u30c4\u30fc\u30eb|game-changer|differentiator",  # allow:neutrality this detector pattern lists the banned words so a doc using them fails
    re.IGNORECASE,
)


def test_naming_and_neutrality() -> None:
    for ja, en in PAIRS:
        for doc in (ja, en):
            text = doc.read_text(encoding="utf-8")
            assert not FORBIDDEN_NAMING.search(text), f"{doc.name}: forbidden product naming"
            assert not NEUTRALITY.search(text), f"{doc.name}: vendor-versus wording"


# --------------------------------------------------------------------------
# environment-variable coverage
# --------------------------------------------------------------------------

TEST_ONLY = {"LAB_NOW"}
LAB_VAR = re.compile(r"\bLAB_[A-Z0-9_]+\b")


def _lab_vars_in_example() -> set[str]:
    return set(LAB_VAR.findall(LAB_ENV_EXAMPLE.read_text(encoding="utf-8")))


def _lab_vars_in_scripts() -> set[str]:
    found: set[str] = set()
    for path in list(SCRIPTS.glob("*.sh")) + [SCRIPTS / "lib" / "common.sh"]:
        found.update(LAB_VAR.findall(path.read_text(encoding="utf-8")))
    # A trailing underscore is an indirect-reference prefix (LAB_SECOND_RECIPIENT_${k}),
    # not a variable name; the concrete names it builds are documented in the example.
    return {name for name in found if not name.endswith("_")}


def _lab_vars_in_readme() -> set[str]:
    return set(LAB_VAR.findall((LAB_SRC / "README.md").read_text(encoding="utf-8")))


def test_lab_now_is_test_only_and_pinned_to_now() -> None:
    assert "LAB_NOW" not in LAB_ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "LAB_NOW" not in (LAB_SRC / "README.md").read_text(encoding="utf-8")
    # LAB_NOW is referenced only by now() in common.sh.
    common = (SCRIPTS / "lib" / "common.sh").read_text(encoding="utf-8")
    assert "LAB_NOW" in common


def test_env_var_coverage_example_scripts_readme() -> None:
    example = _lab_vars_in_example() - TEST_ONLY
    scripts = _lab_vars_in_scripts() - TEST_ONLY
    # Every variable the example documents is used by a script.
    unused = example - scripts
    assert not unused, f"lab.env.example documents variables no script uses: {sorted(unused)}"
    # Every required variable the scripts read is documented in the example.
    missing = scripts - example - set(_derived_names())
    assert not missing, f"scripts read LAB_* not in lab.env.example: {sorted(missing)}"


def _derived_names() -> set[str]:
    """Names common.sh derives from LAB_TAG rather than reading from the file."""
    return {
        "LAB_STANDARD_VAULT_NAME",
        "LAB_LAG_VAULT_NAME",
        "LAB_SHARE_NAME",
        "LAB_REPO_ROOT",
        "LAB_ROOT",
        "LAB_ENV_FILE",
    }


def test_portal_and_ui_expect_are_not_lab_prefixed() -> None:
    example = LAB_ENV_EXAMPLE.read_text(encoding="utf-8")
    for name in ("PORTAL_URL", "PORTAL_USER", "PORTAL_PASSWORD"):
        assert name in example, f"{name} is not documented in lab.env.example"
    # LAB_UI_EXPECT is set by 07 for the spec; readers do not set it, so it is not a
    # LAB_* row that env-var coverage must pin.
    assert "LAB_UI_EXPECT" not in _lab_vars_in_example() or "readers do not set" in example


def test_node_min_matches_getting_started() -> None:
    helpers = (SCRIPTS / "lib" / "lab_helpers.py").read_text(encoding="utf-8")
    m = re.search(r"NODE_MIN_MAJOR = (\d+)", helpers)
    assert m, "NODE_MIN_MAJOR not found"
    node_min = int(m.group(1))
    gs = GETTING_STARTED.read_text(encoding="utf-8")
    majors = {int(x) for x in re.findall(r"(\d+)\.x", gs)}
    assert node_min in majors, f"NODE_MIN_MAJOR {node_min} is not a major version in GETTING-STARTED.md ({majors})"


# --------------------------------------------------------------------------
# README permission table equals required-actions.json
# --------------------------------------------------------------------------

ACTION = re.compile(r"^[a-z0-9-]+:[A-Za-z]+$")


def _permission_actions_in_readme(path: Path) -> set[str]:
    actions: set[str] = set()
    in_fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if CODE_FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence and ACTION.match(line.strip()):
            actions.add(line.strip())
    return actions


def test_readme_permission_table_matches_required_actions() -> None:
    data = json.loads(REQUIRED_ACTIONS.read_text(encoding="utf-8"))
    operator = set(data["operator-owner"]) | set(data["operator-recipient"])
    for readme in (LAB_SRC / "README.md", LAB_SRC / "README.en.md"):
        listed = _permission_actions_in_readme(readme)
        assert listed == operator, (
            f"{readme.name}: permission list differs from required-actions.json operator groups: "
            f"only in README {sorted(listed - operator)}, only in JSON {sorted(operator - listed)}"
        )


# --------------------------------------------------------------------------
# template types equal the README 'created resource types' list
# --------------------------------------------------------------------------

CFN_TYPE = re.compile(r"`(AWS::[A-Za-z0-9]+::[A-Za-z0-9]+)`")
TEMPLATE_TYPE = re.compile(r"^\s+Type:\s*(AWS::[A-Za-z0-9]+::[A-Za-z0-9]+)")


def _types_in_templates() -> set[str]:
    types: set[str] = set()
    for path in TEMPLATES.glob("*.yaml"):
        for line in path.read_text(encoding="utf-8").splitlines():
            m = TEMPLATE_TYPE.match(line)
            if m:
                types.add(m.group(1))
    return types


def _types_in_readme(path: Path) -> set[str]:
    types: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if (
            line.strip().startswith("| owner-base")
            or line.strip().startswith("| owner-lag-share")
            or line.strip().startswith("| recipient-restore")
        ):
            types.update(CFN_TYPE.findall(line))
    return types


def test_template_types_match_readme_list() -> None:
    template_types = _types_in_templates()
    assert template_types, "no CloudFormation types found in the templates"
    for readme in (LAB_SRC / "README.md", LAB_SRC / "README.en.md"):
        readme_types = _types_in_readme(readme)
        assert readme_types == template_types, (
            f"{readme.name}: resource-type list differs from the templates: "
            f"only in README {sorted(readme_types - template_types)}, only in templates {sorted(template_types - readme_types)}"
        )
        # The FSx three types carry the transcribed/unverified note.
        text = readme.read_text(encoding="utf-8")
        assert "AWS::FSx::FileSystem" in text and ("transcrib" in text or "\u8ee2\u8a18" in text)
        assert "E23" in text


# --------------------------------------------------------------------------
# README has no first-observation wording (H20)
# --------------------------------------------------------------------------

FIRST_OBS = re.compile("\u521d\u56de\u306e\u89b3\u6e2c|n=1|first observation", re.IGNORECASE)


def test_readme_has_no_first_observation_wording() -> None:
    for readme in (LAB_SRC / "README.md", LAB_SRC / "README.en.md"):
        for number, line in enumerate(readme.read_text(encoding="utf-8").splitlines(), 1):
            assert not FIRST_OBS.search(line), f"{readme.name}:{number}: first-observation wording: {line.strip()[:80]}"


# --------------------------------------------------------------------------
# no Japanese outside docs (scripts, templates, spec, tests)
# --------------------------------------------------------------------------


def test_no_japanese_outside_docs() -> None:
    targets = (
        list(SCRIPTS.glob("*.sh"))
        + [SCRIPTS / "lib" / "common.sh", SCRIPTS / "lib" / "lab_helpers.py", SCRIPTS / "lib" / "required-actions.json"]
        + list(TEMPLATES.glob("*.yaml"))
        + [SPEC]
    )
    for path in targets:
        if not path.is_file():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            assert not CJK.search(line), f"{path.name}:{number} contains Japanese outside docs: {line.strip()[:80]}"
