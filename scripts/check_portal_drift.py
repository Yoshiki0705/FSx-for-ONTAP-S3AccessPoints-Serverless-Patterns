#!/usr/bin/env python3
"""Catch the portal drift that reviews keep missing.

Three classes of drift, all of which have actually shipped in this repository:

1. An action inventory comment that no longer matches the handler's dispatch.
   `listSvms` was added to the ARP handler and the "Provides:" comment listing
   the actions was not updated in the same change.

2. A user-facing string hardcoded in a component instead of going through i18n.
   The portal ships eight locales; a literal is invisible in seven of them.

3. Documentation asserting behaviour the code contradicts. Four files said
   containment blocks never expire for a release after the expiry sweep landed.
   Each rule here pairs a claim with the code that disproves it, so the rule
   retires itself when the claim becomes true again.

Run with no arguments to check everything:

    python3 scripts/check_portal_drift.py

The claim rules are shared with `check_published_articles.py`, which applies them
to the published blog posts over the network. Two articles carried a stale claim
for a month while this check passed, because the rules only knew the phrasings
used in `docs/` and the globs only covered files that are committed.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORTAL = ROOT / "solutions" / "amplify-portal"

# Characters that only appear in a user-facing string. Comments are exempt: they
# are for whoever maintains the file, not for the person using the portal.
CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]")

# Wider than CJK above: this one decides whether joining two wrapped lines needs a
# space between them, so it has to include CJK punctuation and fullwidth forms.
# Japanese does not space its words, and a renderer inserts nothing at a line
# break between two wide characters. Joining "TTL も" and "スケジュール解除もない"
# with a space produces text that exists nowhere and matches nothing.
WIDE = re.compile(r"[\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uff00-\uffef]")


def unwrap(lines: list[str]) -> str:
    """Join hard-wrapped lines back into one string, the way a reader sees them."""
    joined = ""
    for line in lines:
        piece = line.strip()
        if not piece:
            continue
        if joined and not (WIDE.match(piece[0]) and WIDE.search(joined[-1])):
            joined += " "
        joined += piece
    return re.sub(r"[ \t]+", " ", joined).strip()


@dataclass
class Finding:
    rule: str
    location: str
    detail: str


def dispatch_actions(handler: Path) -> set[str]:
    """Actions a handler dispatches on, read from its `action == "..."` checks."""
    return set(re.findall(r'action\s*==\s*"([A-Za-z][A-Za-z0-9_]*)"', handler.read_text()))


def check_action_inventories() -> list[Finding]:
    """Compare each declared inventory comment against the handler it names.

    The association is explicit rather than inferred, so the check cannot
    silently stop covering a handler that gets renamed or moved.

        // Actions from: functions/data-protection/handler.py
        // Provides: blockSmbUser, unblockSmbUser, ...
    """
    findings: list[Finding] = []
    backend = PORTAL / "amplify" / "backend.ts"
    if not backend.exists():
        return [Finding("action-inventory", str(backend), "backend.ts not found")]

    text = backend.read_text()
    blocks = re.finditer(
        r"//\s*Actions from:\s*(?P<path>[^\s]+)\s*\n"
        r"(?P<comment>(?:\s*//[^\n]*\n)+)",
        text,
    )

    found_any = False
    for block in blocks:
        found_any = True
        handler = PORTAL / block.group("path")
        if not handler.exists():
            findings.append(
                Finding(
                    "action-inventory",
                    "amplify/backend.ts",
                    f"declares actions from {block.group('path')}, which does not exist",
                )
            )
            continue

        # Only the "Provides:" continuation lines describe actions; anything after
        # a blank comment line is prose.
        comment = block.group("comment")
        provides = re.search(r"//\s*Provides:(?P<body>(?:[^\n]*\n(?:\s*//\s{2,}[^\n]*\n)*))", comment)
        if not provides:
            findings.append(
                Finding(
                    "action-inventory",
                    "amplify/backend.ts",
                    f"'Actions from: {block.group('path')}' has no 'Provides:' list beneath it",
                )
            )
            continue

        documented = set(re.findall(r"\b([a-z][A-Za-z0-9]{3,})\b", provides.group("body")))
        actual = dispatch_actions(handler)

        # Prose in the same comment ("not exposed through AppSync") would look like
        # an action name, so only words that are plausible identifiers count, and
        # anything the handler does not dispatch is reported rather than guessed at.
        missing = actual - documented
        stale = {
            word
            for word in documented - actual
            if word in _ALL_PORTAL_ACTIONS or word[0].islower() and any(c.isupper() for c in word)
        }

        for action in sorted(missing):
            findings.append(
                Finding(
                    "action-inventory",
                    f"amplify/backend.ts -> {block.group('path')}",
                    f"handler dispatches '{action}' but the Provides comment omits it",
                )
            )
        for word in sorted(stale):
            findings.append(
                Finding(
                    "action-inventory",
                    f"amplify/backend.ts -> {block.group('path')}",
                    f"Provides comment lists '{word}' but the handler does not dispatch it",
                )
            )

    if not found_any:
        findings.append(
            Finding(
                "action-inventory",
                "amplify/backend.ts",
                "no 'Actions from:' inventory declarations found, so nothing is covered",
            )
        )
    return findings


# Declares a literal as deliberately untranslated. Some text must not go through
# i18n at all — a language picker shows each language in its own script, so
# "日本語" is correct in every locale and translating it would be a bug.
#
# This is separate from the baseline on purpose. The baseline means "not fixed
# yet"; an exemption means "correct as it is". Collapsing the two would leave a
# backlog nobody can finish, because some of it should never change.
EXEMPT = re.compile(r"//\s*i18n-exempt\b(?::\s*(?P<reason>.+))?")


def _strip_comments_and_imports(source: str) -> list[tuple[int, str]]:
    """Source lines with comments removed, keeping original line numbers."""
    lines = source.split("\n")
    out: list[tuple[int, str]] = []
    in_block = False
    for number, line in enumerate(lines, start=1):
        text = line
        if in_block:
            end = text.find("*/")
            if end == -1:
                continue
            text = text[end + 2 :]
            in_block = False
        while True:
            start = text.find("/*")
            if start == -1:
                break
            end = text.find("*/", start + 2)
            if end == -1:
                text = text[:start]
                in_block = True
                break
            text = text[:start] + text[end + 2 :]
        text = re.sub(r"//.*$", "", text)
        if text.strip().startswith("import "):
            continue
        out.append((number, text))
    return out


BASELINE = Path(__file__).resolve().parent / "portal-drift-baseline.txt"


def _fingerprint(path: Path, text: str) -> str:
    """Identity of an offending line that survives the line moving.

    Keyed on the file and the collapsed text rather than a line number, so
    unrelated edits above it do not churn the baseline.
    """
    return f"{path.relative_to(PORTAL)}\t{' '.join(text.split())}"


def load_baseline() -> set[str]:
    if not BASELINE.exists():
        return set()
    return {line.rstrip("\n") for line in BASELINE.read_text().split("\n") if line.strip() and not line.startswith("#")}


def check_hardcoded_strings(baseline: set[str] | None = None) -> tuple[list[Finding], list[str]]:
    """Find user-facing text that bypasses the translation layer.

    Returns (findings, all_fingerprints). The portal already carries a backlog of
    these, so the check fails only on lines absent from the baseline. Failing on
    the whole backlog would mean turning the check off, which protects nothing.

    A line that also calls `t(...)` is a fallback rather than a bypass: the key
    exists and the literal only shows if a locale is missing it. Those are
    reported as a count, not as failures.
    """
    known = baseline if baseline is not None else load_baseline()
    findings: list[Finding] = []
    fingerprints: list[str] = []
    fallbacks = 0
    exempted = 0

    components = sorted((PORTAL / "src").rglob("*.tsx"))
    if not components:
        return [Finding("hardcoded-string", "src", "no .tsx files found, so nothing is covered")], []

    for path in components:
        raw_lines = path.read_text().split("\n")
        for number, text in _strip_comments_and_imports(path.read_text()):
            if not CJK.search(text):
                continue
            if "t(" in text:
                fallbacks += 1
                continue
            # An exemption may sit on the line or immediately above it, so a long
            # line does not have to carry the marker and the reason.
            here = raw_lines[number - 1] if number <= len(raw_lines) else ""
            above = raw_lines[number - 2] if number >= 2 else ""
            if EXEMPT.search(here) or EXEMPT.search(above):
                exempted += 1
                continue
            fingerprint = _fingerprint(path, text)
            fingerprints.append(fingerprint)
            if fingerprint in known:
                continue
            findings.append(
                Finding(
                    "hardcoded-string",
                    f"{path.relative_to(PORTAL)}:{number}",
                    f"user-facing text with no translation key, so seven locales cannot see it: {text.strip()[:80]}",
                )
            )

    if findings:
        findings.append(
            Finding(
                "hardcoded-string",
                "(how to resolve)",
                "add a key to src/i18n/locales/ja.ts and the other seven locales. If the text "
                "must stay as it is in every locale — a language name in its own script, for "
                "instance — mark the line with '// i18n-exempt: <reason>' rather than baselining "
                f"it. {fallbacks} t()-with-fallback and {exempted} exempted line(s) are not "
                "counted here.",
            )
        )
    return findings, fingerprints


# A claim that is false, paired with the code that disproves it. Both halves are
# checked: the rule only fires while the contradicting code is present, so it
# stops complaining by itself if the behaviour is ever removed.
#
# Each pattern names the *false half* of a sentence, not the topic. Two published
# articles listed "TTL auto-unblock (EventBridge Scheduler)" and "a multi-SVM
# fan-out" as things you still had to build outside the portal, months after both
# shipped. The goal phrasings on the left of those table rows ("not leave a
# false-positive block in place indefinitely") are true statements and are
# deliberately not matched: they read the same whether the capability exists or
# not. Only the right-hand answer — "here is what you must go and build" — turns
# false when the feature lands.
CONTRADICTIONS = [
    {
        "name": "block-expiry",
        "claim": re.compile(
            r"(blocks?\s+do\s+not\s+expire"
            r"|nothing\s+expires\s+it\s+automatically"
            r"|no\s+TTL\s+and\s+no\s+scheduled\s+unblock"
            # Wording that actually shipped in the published Part 2 articles.
            r"|(?:portal|it)\s+has\s+no\s+TTL"
            r"|nothing\s+lifts\s+it\s+but\s+a\s+person"
            r"|TTL\s+auto-unblock\s*\(\s*EventBridge"
            r"|ブロックは自動では失効しません"
            r"|TTL もスケジュール解除もない"
            r"|ポータルには\s*TTL\s*がない"
            r"|TTL\s*自動解除\s*（\s*EventBridge)",
            re.IGNORECASE,
        ),
        "disproved_by": ("functions/data-protection/handler.py", "sweepExpiredBlocks"),
        "why": "the expiry sweep exists, so blocks do expire",
    },
    {
        "name": "system-manager-vpn",
        # Written against on-premises ONTAP, where a network that reaches the
        # cluster management LIF can open the System Manager web UI directly. For
        # FSx for ONTAP the management endpoint offers SSH and the REST API; the
        # System Manager UI is reached only through the vendor SaaS, which covers
        # FSx for ONTAP in its SaaS-connected mode alone. So "VPN to System
        # Manager" describes a path that does not exist here, and it shipped in
        # both published Part 2 articles and the capability map.
        #
        # Only the reachability claim is matched. "UI inspired by System Manager"
        # and "System Manager-equivalent operations" are about design and
        # familiarity, are true, and are deliberately left alone.
        "claim": re.compile(
            # A VPN as the way to reach System Manager.
            r"(VPN\s+(?:connection\s+)?to\s+(?:the\s+)?System\s+Manager"
            r"|VPN\s+to\s+System\s+Manager"
            r"|System\s+Manager[^.\n]{0,40}requires?\s+a\s+VPN"
            r"|accessing\s+it\s+requires\s+a\s+VPN"
            r"|System\s+Manager\s*(?:に|へ)\s*VPN"
            r"|System\s+Manager[^。\n]{0,30}VPN\s*(?:経由|接続)"
            r"|System\s+Manager\s*\+\s*VPN"
            r"|確認に\s*System\s+Manager"
            # System Manager named as the owner of operations that, on FSx for
            # ONTAP, AWS performs and the customer never does.
            r"|System\s+Manager\s*(?:と|／|/)\s*ONTAP\s*CLI\s*の担当範囲"
            r"|remain\s+with\s+System\s+Manager"
            # System Manager presented as an interface the reader is using or can
            # fall back to. "System Manager-equivalent operations" and "follows
            # System Manager's card navigation" are about familiarity and design,
            # are true, and must not match — hence the specific verbs.
            r"|(?:back\s+to|accessing|access)\s+ONTAP\s+System\s+Manager"
            r"|Using\s+ONTAP\s+System\s+Manager\s+daily"
            r"|existing\s+ONTAP\s+System\s+Manager\s+workflows"
            r"|System\s+Manager\s*(?:や|または)\s*CLI\s*(?:に|へ)\s*(?:アクセス|戻る)"
            r"|System\s+Manager\s*ワークフロー"
            r"|System\s+Manager\s*を日常利用)",
            re.IGNORECASE,
        ),
        "disproved_by": ("functions/resource-management/handler.py", "ontap_request"),
        "why": (
            "System Manager is not reachable for FSx for ONTAP without the vendor "
            "SaaS; the portal's peer is the ONTAP CLI / REST API. See "
            "docs/ja/fsx-ontap-management-interfaces.md"
        ),
    },
    {
        "name": "multi-svm-fanout",
        "claim": re.compile(
            r"(multi-SVM\s+fan-?out" r"|マルチ\s*SVM\s*へのファンアウト)",
            re.IGNORECASE,
        ),
        "disproved_by": ("functions/data-protection/handler.py", "allSvms"),
        "why": "the handler accepts `svms` and `allSvms`, so fan-out is built in",
    },
]
# A rule matching "read-only" near "containment" was tried and removed: the
# sentence "regular users can view ARP status (read-only) but cannot execute
# containment actions" is correct, and no pattern over those words separates it
# from a false claim. A rule that cannot tell a true statement from a false one
# trains people to ignore the check.
#
# Tense matters in the corrected text and the patterns respect it. "a block
# stayed until a person lifted it" and "当時は有効期限がなく" describe the old
# behaviour and are accurate; "nothing lifts it but a person" and "TTL がない"
# assert it about the present and are not.

# `drafts/` is gitignored, so in CI this glob matches nothing and costs nothing.
# Locally it is the only place the article text exists, and an article is where
# this class of drift has actually reached readers — catching it in the draft is
# the cheapest place to catch it.
DOC_GLOBS = [
    "docs/ja/*.md",
    "docs/en/*.md",
    "solutions/amplify-portal/docs/*.md",
    "drafts/blog/*.md",
]


def active_contradictions() -> list[dict]:
    """Rules whose disproving code is still present in the portal handlers."""
    active = []
    for rule in CONTRADICTIONS:
        handler_path, marker = rule["disproved_by"]
        handler = PORTAL / handler_path
        if handler.exists() and marker in handler.read_text():
            active.append(rule)
    return active


def scan_text(text: str, rules: list[dict] | None = None) -> list[tuple[dict, int, str]]:
    """Find claims in `text`, as (rule, line number, the matching text).

    Both whole lines and unwrapped paragraphs are searched. Article prose is
    hard-wrapped at about 80 columns, so a claim regularly straddles two lines and
    appears on neither: "blocks do not\\nexpire". Lines are tried first because
    they pin the exact number; the unwrapped paragraph is the fallback that
    catches the wrapped case, and a hit found both ways is reported once.
    """
    if rules is None:
        rules = active_contradictions()
    lines = text.split("\n")
    hits: list[tuple[dict, int, str]] = []

    for rule in rules:
        matched_lines: set[int] = set()
        for number, line in enumerate(lines, start=1):
            if rule["claim"].search(line):
                matched_lines.add(number)
                hits.append((rule, number, line.strip()))

        # Paragraphs: runs of non-blank lines, joined so wrapped claims surface.
        # A paragraph that already produced a line hit for this rule is skipped,
        # so a second, wrapped instance of the same rule in that paragraph is not
        # listed separately. The paragraph is already named in the output and
        # whoever opens it sees both.
        start = None
        for index, line in enumerate(lines + [""]):
            if line.strip():
                if start is None:
                    start = index
                continue
            if start is None:
                continue
            block = lines[start:index]
            if not any(number in matched_lines for number in range(start + 1, index + 1)):
                collapsed = unwrap(block)
                match = rule["claim"].search(collapsed)
                if match:
                    window = collapsed[max(0, match.start() - 30) : match.end() + 30]
                    hits.append((rule, start + 1, f"...{window}..."))
            start = None

    return hits


# Some files quote a stale claim on purpose: a correction sheet has to carry the
# before text verbatim to be usable as one. The marker names a reason so the next
# reader can tell a deliberate quotation from an oversight, and it is deliberately
# unavailable to published articles — a live article asserting something false is
# a finding whatever the intent behind it.
EXEMPT_FILE = re.compile(r"<!--\s*drift-exempt-file:\s*(.+?)\s*-->")
EXEMPT_LINE = re.compile(r"<!--\s*drift-exempt:\s*(.+?)\s*-->")


def check_doc_contradictions() -> list[Finding]:
    rules = active_contradictions()
    if not rules:
        return []
    findings: list[Finding] = []
    exempt_files = 0
    for pattern in DOC_GLOBS:
        for path in sorted(ROOT.glob(pattern)):
            text = path.read_text()
            if EXEMPT_FILE.search(text):
                exempt_files += 1
                continue
            lines = text.split("\n")
            for rule, number, matched in scan_text(text, rules):
                if EXEMPT_LINE.search(lines[number - 1]):
                    continue
                findings.append(
                    Finding(
                        "doc-contradiction",
                        f"{path.relative_to(ROOT)}:{number}",
                        f"{rule['why']}: {matched[:110]}",
                    )
                )
    if exempt_files and findings:
        findings.append(
            Finding(
                "doc-contradiction",
                "(note)",
                f"{exempt_files} file(s) skipped via 'drift-exempt-file'.",
            )
        )
    return findings


# Counts a document states about the portal, paired with where the real number
# lives. The CONTRADICTIONS rules above cannot cover these: a rule matches the
# *false half of a phrasing*, and "13 sections" is not a phrasing — it is a
# number that was true when it was written and quietly stopped being true.
#
# The section count had drifted in three places at once when this check was
# added: two published articles said 13, eight README locales said 16, and the
# tabs guide said 12, while the sidebar carried 17. The first two were found by
# reading; the third was found by this check, after the reading had declared
# itself finished. Nobody wrote anything wrong — the number aged, which is
# exactly the failure a person cannot be asked to notice.
COUNT_CLAIMS = [
    {
        "name": "sidebar-sections",
        # "4 groups × 17 sections", "4 グループ × 17 セクション", "(17 Sections)",
        # "（17 セクション）", "(17개 섹션)", "（17 个部分）" and so on. Only the
        # number is captured; the surrounding words differ per locale and are
        # deliberately not pinned, so a rewording does not silently disable this.
        "pattern": re.compile(
            r"(?:×|x)\s*(\d+)\s*(?:sections?|セクション|Bereiche|secciones|개 섹션|个部分|個部分)"
            r"|[(（]\s*(\d+)\s*"
            r"(?:Sections?|セクション|Bereiche|secciones|sections?|개 섹션|个部分|個部分)\s*[)）]",
            re.IGNORECASE,
        ),
        "count": lambda: len(
            re.findall(
                r"\{\s*id:\s*\"[^\"]+\",\s*icon:",
                (PORTAL / "src" / "App.tsx").read_text(),
            )
        ),
        "source": "NAV_ITEMS in src/App.tsx",
    },
]


def _templates_under(*relative: str) -> int:
    """Pattern directories under `relative`, counted by their template.yaml.

    One template is one deployable pattern, which is the unit the prose counts.
    """
    total = 0
    for part in relative:
        base = ROOT / part
        if not base.is_dir():
            continue
        total += sum(1 for _ in base.glob("*/template.yaml"))
    return total


def tracked_files() -> list[str]:
    """Paths git tracks, which is what "in the repository" means.

    Walking the working tree instead counts files CI cannot see. The first
    version of this did, and reported 229 test files against CI's 228: the extra
    one was `.private/test_s3ap_write.py`, gitignored and never pushed. A count
    that differs between a laptop and the pipeline is not a count of anything.
    """
    result = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return result.stdout.split("\n")


def _count_in(path: Path, pattern: str) -> int:
    """Occurrences of `pattern` in `path`, or 0 if the file has moved.

    Returning 0 rather than raising lets `check_count_claims` report a broken
    reader, which names the real problem: a rename nobody propagated.
    """
    if not path.is_file():
        return 0
    return len(re.findall(pattern, path.read_text(), re.MULTILINE))


def _test_files(suffix: str, prefix: str = "", *skip: str) -> int:
    """Tracked test files whose basename matches, excluding `skip` directories."""
    total = 0
    for path in tracked_files():
        name = path.rpartition("/")[2]
        if not name.endswith(suffix) or not name.startswith(prefix):
            continue
        if any(part in skip for part in path.split("/")):
            continue
        total += 1
    return total


# Counts stated in prose that name a directory or a suite. Each entry pairs a
# phrasing with the thing to count, and both halves are narrow on purpose: a
# single "(\d+) patterns" rule would compare every category against one number,
# and a single "across (\d+) files" rule would compare the pytest and vitest
# counts against the same total.
#
# These are the numbers that had actually drifted: FlexCache said 7 with 10 on
# disk, edge said 1 with 2, the coverage line said 126 files with 229, and five
# of six operations patterns were annotated "(planned)" while all six were built.
#
# Each category is written both ways in the same file, so both are matched:
# the summary sentence puts the number first ("10 FlexCache/FlexClone
# patterns"), the directory tree puts it after ("FlexCache/FlexClone patterns
# (10)"). Matching only the parenthesised form left the summary line — the one
# line most people read — unchecked, which is where these numbers went stale in
# the first place.
def _either_order(subject: str) -> str:
    return rf"(\d+)\s*(?:\*\*\s*)?{subject}|{subject}\s*\((\d+)"


_COUNTED_IN_PROSE = [
    (
        "flexcache-patterns",
        _either_order(r"FlexCache/FlexClone patterns?"),
        lambda: _templates_under("solutions/flexcache"),
        "solutions/flexcache/*/template.yaml",
    ),
    (
        "genai-patterns",
        _either_order(r"GenAI patterns?"),
        lambda: _templates_under("solutions/genai"),
        "solutions/genai/*/template.yaml",
    ),
    (
        "event-driven-patterns",
        _either_order(r"event-driven patterns?"),
        lambda: _templates_under("solutions/event-driven"),
        "solutions/event-driven/*/template.yaml",
    ),
    (
        "edge-patterns",
        _either_order(r"(?:CDN/)?edge delivery patterns?"),
        lambda: _templates_under("solutions/edge"),
        "solutions/edge/*/template.yaml",
    ),
    (
        "operations-patterns",
        _either_order(r"operation(?:s|al) optimization patterns?"),
        lambda: _templates_under("operations"),
        "operations/*/template.yaml",
    ),
    (
        "cdk-harness-tests",
        r"CDK (?:harness tests|ハーネステスト)[^|\n]*?\((?:構造アサーション\s*)?(\d+)\s*(?:tests|assertions)",
        lambda: _count_in(
            PORTAL / "tests" / "infrastructure" / "backend-assertions.test.ts",
            r"^[ \t]*it\(",
        ),
        "it( blocks in tests/infrastructure/backend-assertions.test.ts",
    ),
    (
        "portal-lambda-count",
        r"Lambda\s*(?:x|×)\s*(\d+)",
        lambda: _count_in(PORTAL / "amplify" / "backend.ts", r"new lambda\.Function\("),
        "new lambda.Function( in amplify/backend.ts",
    ),
    (
        "pytest-files",
        r"Python tests across (\d+) files",
        lambda: _test_files(".py", "test_", "e2e", "load"),
        "tracked test_*.py, excluding e2e and load",
    ),
    (
        "vitest-files",
        r"vitest tests across (\d+) files",
        lambda: _test_files(".test.ts") + _test_files(".test.tsx"),
        "tracked *.test.ts(x)",
    ),
]

for _name, _regex, _counter, _source in _COUNTED_IN_PROSE:
    COUNT_CLAIMS.append(
        {
            "name": _name,
            "pattern": re.compile(_regex, re.IGNORECASE),
            "count": _counter,
            "source": _source,
        }
    )

# A claim rule for the dispatch endpoint count was written and removed. "8
# endpoints" in the design notes is the same shape as "Use the v2.0 endpoint",
# "the public S3 endpoint" and "ONTAP の管理エンドポイント", and six of the ten
# hits on the first run were sentences about a service endpoint that had nothing
# to do with dispatch. Narrowing it to "generic endpoints" would have passed, but
# only until someone wrote the true number without that adjective — a rule that
# only fires on one phrasing gives cover, not coverage. The endpoint count is
# printed by `check_portal_action_params.py` on every run, which is where a reader
# who needs it should look.

# Files whose numbers are checked. Published-article text is not reachable from
# here; `check_published_articles.py` imports this table and applies it there.
COUNT_GLOBS = [
    # AGENTS.md is where the pattern and test counts live, and where they had all
    # gone stale. It was outside this list, which is why nothing noticed.
    "AGENTS.md",
    "README.md",
    "solutions/amplify-portal/README*.md",
    "solutions/amplify-portal/docs/*.md",
    "operations/README.md",
    "docs/ja/*.md",
    "docs/en/*.md",
    "drafts/blog/*.md",
]


def check_count_claims() -> list[Finding]:
    """Numbers a document asserts about the portal, against the implementation.

    A mismatch is reported, not corrected: the sentence around the number may
    need to change too, and a script that rewrites prose to fix arithmetic tends
    to produce sentences no one would have written.
    """
    findings: list[Finding] = []
    for claim in COUNT_CLAIMS:
        try:
            expected = claim["count"]()
        except OSError as error:
            findings.append(Finding("count-claim", claim["source"], f"could not read the source: {error}"))
            continue
        if not expected:
            findings.append(
                Finding(
                    "count-claim",
                    claim["source"],
                    "counted zero, which means the pattern that reads the implementation has stopped matching it",
                )
            )
            continue
        for pattern in COUNT_GLOBS:
            for path in sorted(ROOT.glob(pattern)):
                text = path.read_text()
                if EXEMPT_FILE.search(text):
                    continue
                for number, line in enumerate(text.split("\n"), start=1):
                    if EXEMPT_LINE.search(line):
                        continue
                    for match in claim["pattern"].finditer(line):
                        stated = next(g for g in match.groups() if g)
                        if int(stated) != expected:
                            findings.append(
                                Finding(
                                    "count-claim",
                                    f"{path.relative_to(ROOT)}:{number}",
                                    f"says {stated} but {claim['source']} has {expected}: {line.strip()[:100]}",
                                )
                            )
    return findings


_ALL_PORTAL_ACTIONS: set[str] = set()


def main() -> int:
    global _ALL_PORTAL_ACTIONS
    _ALL_PORTAL_ACTIONS = {
        action
        for handler in (PORTAL / "functions").rglob("*.py")
        if "tests" not in handler.parts
        for action in dispatch_actions(handler)
    }

    if "--write-baseline" in sys.argv:
        _, fingerprints = check_hardcoded_strings(baseline=set())
        BASELINE.write_text(
            "# Hardcoded user-facing strings in the portal that are not translated yet.\n"
            "#\n"
            "# This file is empty, and that is the intended state: the backlog it was\n"
            "# created to hold has been worked off. The check fails on any line absent\n"
            "# from here, so with the file empty every new hardcoded string is a failure.\n"
            "#\n"
            "# Do not add a line here to make the check pass. Either add a translation\n"
            "# key, or — if the text must read the same in every locale, such as a\n"
            "# language name in its own script — mark the line with\n"
            "# '// i18n-exempt: <reason>' instead. An entry here says 'still to do',\n"
            "# which is a promise to someone; an exemption says 'correct as it is'.\n"
            "#\n"
            "# Regenerate with: python3 scripts/check_portal_drift.py --write-baseline\n"
            "#\n"
            "# Format: <path relative to solutions/amplify-portal>\\t<collapsed line text>\n"
            + "\n".join(sorted(set(fingerprints)))
            + "\n"
        )
        print(f"wrote {len(set(fingerprints))} entries to {BASELINE.relative_to(ROOT)}")
        return 0

    hardcoded, _ = check_hardcoded_strings()
    findings = check_action_inventories() + hardcoded + check_doc_contradictions() + check_count_claims()

    if not findings:
        print(f"PORTAL DRIFT: PASS ({len(_ALL_PORTAL_ACTIONS)} actions across the portal handlers)")
        return 0

    by_rule: dict[str, list[Finding]] = {}
    for finding in findings:
        by_rule.setdefault(finding.rule, []).append(finding)

    for rule, items in sorted(by_rule.items()):
        print(f"\n{rule} ({len(items)}):")
        for item in items:
            print(f"  {item.location}\n      {item.detail}")

    print(f"\nPORTAL DRIFT: {len(findings)} finding(s)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
