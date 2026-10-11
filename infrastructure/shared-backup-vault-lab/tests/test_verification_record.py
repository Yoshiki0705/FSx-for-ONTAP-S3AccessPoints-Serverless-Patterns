"""The 'verified' discipline of design 16: records, tags, digests and status lines.

Nothing here runs AWS. The tests read the verification record, the scripts, the
templates and the UI spec as text, and exercise lab_helpers against throwaway git
trees. The record table is empty in C7, so the "backed" checks run against a table
with zero rows: every ``verified`` term in the lab must then be absent, in a code
span, or a negation, because no tag can be satisfied yet.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
from lab_testlib import LAB_SRC

DOCS = LAB_SRC / "docs"
RECORD_JA = DOCS / "verification-record.md"
RECORD_EN = DOCS / "verification-record.en.md"
SCRIPTS = LAB_SRC / "scripts"
TEMPLATES = LAB_SRC / "cloudformation"
HELPERS_PATH = SCRIPTS / "lib" / "lab_helpers.py"
REPO_SRC = LAB_SRC.parents[1]
SPEC = REPO_SRC / "solutions" / "amplify-portal" / "tests" / "e2e" / "shared-vault-lab.spec.ts"

STATUS_PREFIX = "# Real-environment run:"
# Items emitted by no check: observable only outside these scripts (design 15, 16).
MANUAL_ITEMS = {"V8", "E7", "E22", "E23", "E24"}
DEFINED = [f"V{i}" for i in range(1, 9)] + [f"E{i}" for i in range(1, 27)]

GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


def _load_helpers() -> ModuleType:
    spec = importlib.util.spec_from_file_location("lab_helpers_vr", HELPERS_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["lab_helpers_vr"] = module
    spec.loader.exec_module(module)
    return module


HELPERS = _load_helpers()


# --------------------------------------------------------------------------
# record-row validation and its negative controls
# --------------------------------------------------------------------------

RESULT_RE = re.compile(r"^\d+✅ \d+❌ \d+⚠$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
REGION_RE = re.compile(r"^[a-z]{2}(-[a-z]+)+-[0-9]$")
DIGEST_RE = re.compile(r"^[0-9a-f]{12}$")
DURATION_RE = re.compile(r"^\d+s$")
PLACEHOLDERS = ("—", "xxx", "TBD", "…", "111122223333", "444455556666", "<fill>")
RECORD_COLUMNS = ("date", "region", "config", "aws_cli", "digest", "portal_ref", "item", "result", "duration", "notes")


def _validate_record_row(row: dict[str, str], defined: set[str]) -> list[str]:
    """Return the problems in one record row (empty means valid).

    Every column except notes is non-empty; the date is a real past-or-today date;
    the Region, AWS CLI, digest and duration match their shapes; the item is in the
    closed set; the result is ``N✅ N❌ N⚠``; no placeholder appears anywhere.
    """
    problems: list[str] = []
    for column in RECORD_COLUMNS:
        if column == "notes":
            continue
        if not str(row.get(column, "")).strip():
            problems.append(f"empty column: {column}")
    for column, value in row.items():
        if any(ph in str(value) for ph in PLACEHOLDERS):
            problems.append(f"placeholder in {column}: {value!r}")
    if not DATE_RE.match(str(row.get("date", ""))):
        problems.append("date is not YYYY-MM-DD")
    elif str(row["date"]) > _today():
        problems.append("date is in the future")
    if not REGION_RE.match(str(row.get("region", ""))):
        problems.append("region shape")
    if not re.match(r"^aws-cli/\d+\.\d+\.\d+$", str(row.get("aws_cli", ""))):
        problems.append("aws cli shape")
    if not DIGEST_RE.match(str(row.get("digest", ""))):
        problems.append("digest shape")
    if str(row.get("item", "")) not in defined:
        problems.append("item not in the defined set")
    if not RESULT_RE.match(str(row.get("result", ""))):
        problems.append("result shape")
    if not DURATION_RE.match(str(row.get("duration", ""))):
        problems.append("duration shape")
    return problems


def _today() -> str:
    import datetime as dt

    return dt.datetime.now(dt.timezone.utc).date().isoformat()


def _valid_row() -> dict[str, str]:
    return {
        "date": "2026-10-11",
        "region": "ap-northeast-1",
        "config": "SINGLE_AZ_1 128MBps 1024GiB",
        "aws_cli": "aws-cli/2.36.5",
        "digest": "abcdef123456",
        "portal_ref": "0123456789ab",
        "item": "V1",
        "result": "1✅ 0❌ 0⚠",
        "duration": "900s",
        "notes": "script 06_verify.sh",
    }


def test_record_rows_are_valid() -> None:
    # The C7 table is empty, so a known-good row must validate for the check to mean
    # anything.
    assert _validate_record_row(_valid_row(), set(DEFINED)) == []


def test_record_row_validation_has_negative_controls() -> None:
    base = _valid_row()
    breakers = [
        ("date", ""),
        ("date", "2099-01-01"),
        ("date", "2026-13-40"),
        ("item", "V99"),
        ("result", "ok"),
        ("digest", "nothex"),
        ("region", "tokyo"),
        ("aws_cli", "2.36.5"),
        ("duration", "15m"),
        ("config", "111122223333"),
    ]
    for column, value in breakers:
        bad = dict(base)
        bad[column] = value
        assert _validate_record_row(bad, set(DEFINED)), f"breaking {column}={value!r} was not caught"


# --------------------------------------------------------------------------
# every claim of 'verified' is tagged and backed
# --------------------------------------------------------------------------

CODE_SPAN = re.compile(r"`[^`]*`")
# Japanese is written as \u escapes so the test file holds no Japanese bytes.
VERIFIED_TERMS = re.compile(
    "\u691c\u8a3c\u6e08\u307f|\u691c\u8a3c\u6e08|\u78ba\u8a8d\u6e08\u307f"
    "|\u52d5\u4f5c\u78ba\u8a8d|\u5b9f\u6a5f\u3067\u78ba\u8a8d|verified|confirmed|validated",
    re.IGNORECASE,
)
NEGATIONS = (
    "not verified",
    "not yet verified",
    "to be verified",
    "to be confirmed",
    "unverified",
    "not confirmed",
    "unconfirmed",
    "not validated",
    "unvalidated",
    "\u672a\u691c\u8a3c",
    "\u672a\u78ba\u8a8d",
)
TAG = re.compile(r"\[(V[1-8]|E[1-9]|E1[0-9]|E2[0-6])(@[0-9a-f]{12})?\]")


def _lab_text_files() -> list[Path]:
    """README, runbook, record, scripts and templates (not tests)."""
    files = [
        LAB_SRC / "README.md",
        LAB_SRC / "README.en.md",
        RECORD_JA,
        RECORD_EN,
        DOCS / "procedure.md",
        DOCS / "procedure.en.md",
    ]
    files += sorted(SCRIPTS.glob("*.sh"))
    files += sorted(TEMPLATES.glob("*.yaml"))
    return [f for f in files if f.is_file()]


def _strip_code(text: str) -> list[str]:
    """Lines with inline code spans and fenced blocks removed."""
    out: list[str] = []
    in_fence = False
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            out.append("")
            continue
        if in_fence:
            out.append("")
            continue
        out.append(CODE_SPAN.sub("", line))
    return out


# A term negated earlier in the clause: "no early-deletion route is confirmed",
# "neither price is confirmed", "never validated". These assert the opposite of a
# verified claim, so they are allowed like the explicit negation phrases.
NEGATION_SCOPE = re.compile(r"\b(no|neither|never|without)\b[^.]*\b(verified|confirmed|validated)\b", re.IGNORECASE)


def _is_negated(line: str) -> bool:
    low = line.lower()
    if any(neg.lower() in low for neg in NEGATIONS):
        return True
    return bool(NEGATION_SCOPE.search(line))


def _unbacked_verified_claims(records_held: set[str]) -> list[str]:
    """Lines asserting 'verified' with no satisfied tag, outside code and negations."""
    findings: list[str] = []
    for path in _lab_text_files():
        lines = _strip_code(path.read_text(encoding="utf-8"))
        for index, line in enumerate(lines):
            if not VERIFIED_TERMS.search(line):
                continue
            # A negation often wraps onto the previous line in a comment block
            # ("...; no\n# early-deletion route is confirmed."), so check both.
            previous = lines[index - 1] if index > 0 else ""
            if _is_negated(line) or _is_negated(previous + " " + line):
                continue
            tags = [m.group(1) for m in TAG.finditer(line)]
            if not tags or not all(t in records_held for t in tags):
                findings.append(f"{path.name}:{index + 1}: {line.strip()[:80]}")
    return findings


def test_every_verified_claim_is_tagged_and_backed() -> None:
    # The record table is empty, so no item is held. Every 'verified' term in the lab
    # must therefore be in a code span or a negation; none may stand as a bare claim.
    assert _unbacked_verified_claims(records_held=set()) == []


def test_verified_claim_scan_has_negative_controls() -> None:
    # A bare claim with no tag is caught.
    assert _scan_text("The restore path is verified.", held=set())
    # A tag for an item that is not held is caught.
    assert _scan_text("The restore path is verified [V7].", held=set())
    # A satisfied tag passes.
    assert not _scan_text("The restore path is verified [V7].", held={"V7"})
    # Japanese term with no tag is caught.
    assert _scan_text("\u5fa9\u5143\u306f\u78ba\u8a8d\u6e08\u307f\u3067\u3059\u3002", held=set())
    # A negation does not report.
    assert not _scan_text("The restore path is not yet verified.", held=set())
    assert not _scan_text("\u5fa9\u5143\u306f\u672a\u691c\u8a3c\u3067\u3059\u3002", held=set())
    # A term in a code span does not report.
    assert not _scan_text("The word `verified` is a term here.", held=set())


def _scan_text(text: str, held: set[str]) -> bool:
    """True when ``text`` holds an unbacked 'verified' claim (helper for controls)."""
    for line in _strip_code(text):
        if not VERIFIED_TERMS.search(line):
            continue
        if _is_negated(line):
            continue
        tags = [m.group(1) for m in TAG.finditer(line)]
        if not tags or not all(t in held for t in tags):
            return True
    return False


# --------------------------------------------------------------------------
# status line, header lines and the record
# --------------------------------------------------------------------------

NOT_YET_DONE = "# Real-environment run: not yet done (status source: docs/verification-record.md)"
PARTIAL_RE = re.compile(
    r"^# Real-environment run: recorded (\[(?:V[1-8]|E\d+)\])+(?:; not recorded (\[(?:V[1-8]|E\d+)\])+)?"
    r" \(status source: docs/verification-record\.md\)$"
)


def _record_rows_from_doc(path: Path) -> list[dict[str, str]]:
    """Parse the record table of the verification record (returns [] when empty)."""
    rows: list[dict[str, str]] = []
    in_table = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("| Date (UTC) |") or line.startswith("| \u5b9f\u65bd\u65e5"):
            in_table = True
            continue
        if in_table:
            if not line.startswith("|"):
                break
            if set(line.strip()) <= {"|", "-", " "}:
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) == len(RECORD_COLUMNS):
                rows.append(dict(zip(RECORD_COLUMNS, cells)))
    return rows


def test_status_line_matches_the_record() -> None:
    # The table is empty in C7, so the status line of every document is 'not yet done'.
    for path in (
        RECORD_JA,
        RECORD_EN,
        LAB_SRC / "README.md",
        LAB_SRC / "README.en.md",
        DOCS / "procedure.md",
        DOCS / "procedure.en.md",
    ):
        first = path.read_text(encoding="utf-8").splitlines()[0]
        assert first == NOT_YET_DONE, f"{path.name} status line is {first!r}"
    assert _record_rows_from_doc(RECORD_JA) == []
    assert _record_rows_from_doc(RECORD_EN) == []


def test_partial_status_grammar_of_d5() -> None:
    # The D-5 grammar: 'recorded ...; not recorded ...' and the plain 'not yet done'.
    assert PARTIAL_RE.match(
        "# Real-environment run: recorded [V1][V4]; not recorded [E13] (status source: docs/verification-record.md)"
    )
    assert PARTIAL_RE.match("# Real-environment run: recorded [V1][V2] (status source: docs/verification-record.md)")
    assert NOT_YET_DONE.startswith("# Real-environment run: not yet done")
    # 'recorded' with nothing listed is not valid; that case must be 'not yet done'.
    assert not PARTIAL_RE.match("# Real-environment run: recorded  (status source: docs/verification-record.md)")


def test_script_and_template_headers_match_the_record() -> None:
    # No item holds, so every script and template must carry the 'not yet done' line.
    for path in list(SCRIPTS.glob("*.sh")) + [SCRIPTS / "lib" / "lab_helpers.py"] + list(TEMPLATES.glob("*.yaml")):
        head = [ln for ln in path.read_text(encoding="utf-8").splitlines()[:3] if STATUS_PREFIX in ln.lstrip("/ ")]
        assert head, f"{path.name} has no status line in its first three lines"
        line = head[0].lstrip("#/ ").rstrip()
        assert line.startswith("Real-environment run: not yet done"), f"{path.name}: {line!r}"


# --------------------------------------------------------------------------
# every defined item is emitted by a check, or is a MANUAL item with a reason
# --------------------------------------------------------------------------

CHECK_ITEM = re.compile(r"check_(?:pass|fail|warn)\s+(V\d+|E\d+)")


def _emitted_items() -> set[str]:
    items: set[str] = set()
    for path in SCRIPTS.glob("*.sh"):
        items.update(CHECK_ITEM.findall(path.read_text(encoding="utf-8")))
    return items


def _definition_items() -> dict[str, str]:
    """Items in the definition table of the record mapped to their scripts column."""
    mapping: dict[str, str] = {}
    for line in RECORD_EN.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\| (V[1-8]|E\d+) \| .* \| (scripts: .*?)(?:<!--.*)? \|", line)
        if m:
            mapping[m.group(1)] = m.group(2).strip()
    return mapping


def test_every_defined_item_is_emitted_by_a_check() -> None:
    emitted = _emitted_items()
    definition = _definition_items()
    assert set(definition) == set(DEFINED), (
        f"definition table item set differs: missing {set(DEFINED) - set(definition)}, "
        f"extra {set(definition) - set(DEFINED)}"
    )
    for item in DEFINED:
        if item in MANUAL_ITEMS:
            assert item not in emitted, f"{item} is a MANUAL item but a check emits it"
            assert "MANUAL" in definition[item], f"{item} is manual but the definition does not say so"
        else:
            assert item in emitted, f"{item} is defined but no check emits it"


# --------------------------------------------------------------------------
# digest and portal-ref
# --------------------------------------------------------------------------


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, **GIT_ENV}
    return subprocess.run(["git", *args], cwd=str(cwd), env=env, capture_output=True, text=True, check=True)


def _make_tree(tmp: Path) -> Path:
    """A throwaway git repo with the lab and the UI spec at the right paths."""
    repo = tmp / "repo"
    lab = repo / "infrastructure" / "shared-backup-vault-lab"
    lab.parent.mkdir(parents=True)
    shutil.copytree(
        LAB_SRC, lab, ignore=shutil.ignore_patterns("__pycache__", "tests", "docs", ".pytest_cache", "*.local.*")
    )
    spec_dst = repo / "solutions" / "amplify-portal" / "tests" / "e2e" / "shared-vault-lab.spec.ts"
    spec_dst.parent.mkdir(parents=True)
    shutil.copyfile(SPEC, spec_dst)
    for extra in ("functions/recovery-points", "functions/restore"):
        (repo / "solutions" / "amplify-portal" / extra).mkdir(parents=True)
        (repo / "solutions" / "amplify-portal" / extra / "handler.py").write_text("x\n", encoding="utf-8")
    (repo / "solutions" / "amplify-portal" / "src" / "components").mkdir(parents=True)
    (repo / "solutions" / "amplify-portal" / "src" / "components" / "RecoveryPoints.tsx").write_text(
        "x\n", encoding="utf-8"
    )
    (repo / "solutions" / "amplify-portal" / "amplify").mkdir(parents=True)
    (repo / "solutions" / "amplify-portal" / "amplify" / "backend.ts").write_text("x\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    return lab


def test_code_digest_is_stable_and_ignores_the_status_line(tmp_path: Path) -> None:
    lab = _make_tree(tmp_path)
    first = HELPERS.code_digest(lab)
    # The same content copied elsewhere digests the same. Copy the whole repo so the
    # UI spec sibling (a digest input) is preserved at its repository-relative path.
    other_repo = tmp_path / "copy"
    shutil.copytree(lab.parents[1], other_repo)
    other_lab = other_repo / "infrastructure" / "shared-backup-vault-lab"
    assert HELPERS.code_digest(other_lab) == first
    # Rewriting the status line does not change the digest.
    script = next(lab.glob("scripts/*.sh"))
    text = script.read_text(encoding="utf-8")
    script.write_text(
        text.replace(
            "# Real-environment run: not yet done (status source: docs/verification-record.md)",
            "# Real-environment run: recorded [V1] (status source: docs/verification-record.md)",
        ),
        encoding="utf-8",
    )
    assert HELPERS.code_digest(lab) == first
    # A one-byte change to a script does change the digest.
    script.write_text(script.read_text(encoding="utf-8") + "\n# x\n", encoding="utf-8")
    assert HELPERS.code_digest(lab) != first


def test_spec_change_changes_digest(tmp_path: Path) -> None:
    lab = _make_tree(tmp_path)
    first = HELPERS.code_digest(lab)
    spec = lab.parents[1] / "solutions" / "amplify-portal" / "tests" / "e2e" / "shared-vault-lab.spec.ts"
    spec.write_text(spec.read_text(encoding="utf-8") + "\n// changed\n", encoding="utf-8")
    assert HELPERS.code_digest(lab) != first


def test_portal_ref_change_invalidates_portal_items(tmp_path: Path) -> None:
    lab = _make_tree(tmp_path)
    repo = lab.parents[1]
    first = HELPERS.portal_ref(lab)
    # Change a portal source and commit: the reference changes.
    handler = repo / "solutions" / "amplify-portal" / "functions" / "restore" / "handler.py"
    handler.write_text("y\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "change restore")
    assert HELPERS.portal_ref(lab) != first
    # A V3 (portal) row would need the new portal-ref; a V1 (non-portal) row would not.
    assert "V3" in HELPERS.PORTAL_ITEMS and "V1" not in HELPERS.PORTAL_ITEMS


# --------------------------------------------------------------------------
# record-row ignores plan runs
# --------------------------------------------------------------------------


def test_record_row_ignores_plan_runs() -> None:
    plan = [
        {
            "run": "r1",
            "ts": "2026-10-11T00:00:00Z",
            "event": "check_pass",
            "item": "V1",
            "mode": "plan",
            "script": "06_verify.sh",
            "region": "ap-northeast-1",
        },
        {
            "run": "r1",
            "ts": "2026-10-11T00:01:00Z",
            "event": "end",
            "mode": "plan",
            "detail": '{"exit": 10, "digest": "abcdef123456"}',
        },
    ]
    assert HELPERS.record_rows(plan, "aws-cli/2.36.5", "0123456789ab") == []
    apply = [
        {
            "run": "r2",
            "ts": "2026-10-11T00:00:00Z",
            "event": "check_pass",
            "item": "V1",
            "mode": "apply",
            "script": "06_verify.sh",
            "region": "ap-northeast-1",
        },
        {
            "run": "r2",
            "ts": "2026-10-11T00:05:00Z",
            "event": "end",
            "mode": "apply",
            "detail": '{"exit": 0, "digest": "abcdef123456"}',
        },
    ]
    rows = HELPERS.record_rows(apply, "aws-cli/2.36.5", "0123456789ab")
    assert len(rows) == 1 and rows[0]["item"] == "V1" and rows[0]["result"] == "1✅ 0❌ 0⚠"
