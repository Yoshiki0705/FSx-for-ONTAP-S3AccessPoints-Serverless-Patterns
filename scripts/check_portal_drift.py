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


_STRING_LITERAL = re.compile(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|`(?:[^`\\]|\\.)*`')
_JSX_TEXT = re.compile(r">([^<>{}]+)<")


def _translatable_literals(text: str) -> list[str]:
    """The parts of a line that reach the user: string literals and JSX text.

    Everything else on the line -- identifiers, a t() key, a className -- is not
    rendered, so CJK found outside these is not a bypass.
    """
    return _STRING_LITERAL.findall(text) + _JSX_TEXT.findall(text)


def check_hardcoded_strings(baseline: set[str] | None = None) -> tuple[list[Finding], list[str]]:
    """Find user-facing text that bypasses the translation layer.

    Returns (findings, all_fingerprints). The portal already carries a backlog of
    these, so the check fails only on lines absent from the baseline. Failing on
    the whole backlog would mean turning the check off, which protects nothing.

    A line that also calls `t(...)` used to be waved through as a fallback, on the
    reasoning that the literal only shows when a locale lacks the key. That is not
    how this t() behaves: it ends `?? key`, so it returns the key name -- a non-empty
    string -- and `t("x") || "literal"` never reaches the literal at all.

    The exemption cost more than it saved. Twenty-nine dead Japanese fallbacks sat in
    one component and were counted as benign, and a ternary next to them
    (`deleting ? "削除中..." : t("rmDelete")`) got the same pass because the line
    mentioned t() somewhere. The check now looks for a CJK *string literal*, so a
    line may call t() as often as it likes and is still reported if it also carries
    untranslated text of its own.
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
            # Only text inside a string literal or a JSX text node counts. A t() call
            # on the same line no longer excuses it.
            if not any(CJK.search(literal) for literal in _translatable_literals(text)):
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
                f"it. {fallbacks} line(s) whose CJK is not in a rendered string, and "
                f"{exempted} exempted line(s), are not "
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


# Claims a measurement has disproved. Separate from CONTRADICTIONS above because
# the retirement condition differs: a CONTRADICTIONS rule retires itself when the
# code it names starts doing the thing, whereas a measurement does not stop being
# true. What could change is the product, and that shows up as a new measurement
# under a new date, not as a marker appearing in a handler.
#
# The scan range differs too, and that is the point. CONTRADICTIONS only reads
# DOC_GLOBS, which excludes `docs/*.md` at the top level -- and that is where most
# of this claim lived: the design considerations table, the S3 bucket user guide,
# the compatibility notes, the trigger-mode decision guide, the data-collection
# README and a CloudFormation parameter description. A guard that had only read
# `docs/ja/` and `docs/en/` would have reported PASS over all of them.
#
# Each pattern names the false assertion -- FPolicy offered as the answer to a
# missing S3 event notification, or as a control on the access point path -- not
# the topic. "FPolicy detects NFS/SMB file operations" is true and must not match;
# so must "FPolicy is not a substitute", which is the corrected wording and
# contains both words.
MEASURED_FALSE = [
    {
        "name": "fpolicy-covers-s3ap",
        "claim": re.compile(
            # FPolicy named as the alternative to the absent notification feature.
            r"(?:代替|alternative)\s*[:：]\s*FPolicy"
            r"|FPolicy\s*(?:\+\s*EventBridge\s*)?で(?:同等機能を実現|イベント駆動を実現)"
            r"|FPolicy\s*\+\s*EventBridge\s*で"
            r"|FPolicy\s+(?:or|または)\s+EventBridge\s+Scheduler\s+を?使用"
            r"|Use\s+FPolicy\s+or\s+EventBridge\s+Scheduler"
            r"|FPolicy\s+\+\s+EventBridge\s+for\s+(?:event-driven|equivalent)"
            # FPolicy asserted to cover, or pair with, the access point path.
            r"|FPolicy\s*\+\s*S3\s*AP"
            r"|FPolicy\s*(?:が|は)\s*S3\s*AP\s*経由[^。\n]{0,20}(?:検知|通知|記録)し(?!ない|ません)"
            r"|FPolicy\s+(?:sees|covers|detects)\s+(?:operations\s+)?(?:through|via)\s+"
            r"(?:the\s+)?S3\s+access\s+point"
            # FPolicy counted as an enforcement boundary alongside the S3 controls.
            r"|ACL\s*\+\s*FPolicy\s*\+\s*S3\s*AP"
            r"|ONTAP\s*ACL/FPolicy"
            # The phrasings the published articles actually used. They say the same
            # thing as the table rows above in different words, which is how the
            # first version of this rule reported PASS over all four of them. Each
            # carries a negative lookahead for the qualifier that makes the sentence
            # true, so the corrected wording does not match -- the qualifier has to
            # sit in the same paragraph, because scan_text reads a paragraph at a
            # time and a note appended at the end of an article is out of reach.
            r"|EVENT_DRIVEN\s*\(\s*FPolicy-based"
            r"(?![\s\S]{0,700}?(?:only where writes arrive over NFS"
            r"|raise no FPolicy notification))"
            r"|S3 Access Points はネイティブのイベント通知をサポートしていません"
            r"(?![\s\S]{0,700}?(?:NFS / SMB 経由で届く場合"
            r"|FPolicy 通知を発火(?:せず|しない)))"
            r"|The answer is ONTAP FPolicy"
            r"(?![\s\S]{0,700}?(?:only where writes arrive over NFS"
            r"|writes that arrive over NFS"
            r"|raise no FPolicy notification))"
            r"|interim event-driven pattern"
            r"(?![\s\S]{0,700}?(?:only where writes arrive over NFS"
            r"|writes that arrive over NFS"
            r"|raise no FPolicy notification))",
            re.IGNORECASE,
        ),
        # Not a code marker: the record of the measurement. If this file is ever
        # renamed away, check_measured_false_claims raises rather than passing
        # quietly -- a guard that cannot find its own evidence has not run.
        "evidence": "docs/aws-feature-requests/native-s3ap-notifications-evidence.md",
        "why": (
            "measured 2026-08-26 on ONTAP 9.18.1P3D1: operations through an FSx for ONTAP "
            "S3 access point raise no FPolicy notification and are not blocked even by a "
            "`mandatory` synchronous policy, so FPolicy is not an alternative to S3 event "
            "notifications on that path and is not an enforcement boundary for it"
        ),
    },
]


def check_measured_false_claims() -> list[Finding]:
    """Claims that a measurement has disproved, across every tracked document.

    Reads Markdown and CloudFormation alike, because the claim reached a template
    parameter description as well as prose, and a reader configuring `TriggerMode`
    never opens the docs.

    An empty corpus is a failure, not a pass. `git ls-files` returns nothing when
    it is run outside a work tree, and every scan built on it then reports clean.
    """
    findings: list[Finding] = []
    for rule in MEASURED_FALSE:
        evidence = ROOT / rule["evidence"]
        if not evidence.exists():
            raise SystemExit(
                f"check_measured_false_claims: evidence file missing for rule "
                f"{rule['name']!r}: {rule['evidence']}. The guard cannot run; "
                f"restore the file or update the rule."
            )

    candidates = [
        path
        for name in tracked_files()
        if name.endswith((".md", ".yaml", ".yml"))
        and not name.startswith((".aws-sam/", "node_modules/"))
        and "/.aws-sam/" not in name
        and "/.amplify/" not in name
        and (path := ROOT / name).is_file()
    ]
    if not candidates:
        raise SystemExit(
            "check_measured_false_claims: no tracked documents found. `git ls-files` "
            "returned nothing, so this scan proves nothing."
        )

    for path in sorted(candidates):
        text = path.read_text(encoding="utf-8", errors="replace")
        if EXEMPT_FILE.search(text):
            continue
        lines = text.split("\n")
        for rule, number, matched in scan_text(text, MEASURED_FALSE):
            if EXEMPT_LINE.search(lines[number - 1]):
                continue
            findings.append(
                Finding(
                    "measured-false-claim",
                    f"{path.relative_to(ROOT)}:{number}",
                    f"{rule['why']}: {matched[:110]}",
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
    """Paths that are, or are about to be, in the repository.

    Walking the working tree instead counts files CI cannot see. The first
    version did, and reported 229 test files against CI's 228: the extra one was
    `.private/test_s3ap_write.py`, gitignored and never pushed. A count that
    differs between a laptop and the pipeline is not a count of anything.

    `--others --exclude-standard` includes files that exist but are not staged
    yet, which matters for the order people actually work in: adding a test file
    and running `make drift` before `git add` would otherwise report the old
    count locally and the new one in CI. Ignored paths stay excluded, so
    `.private/` is still invisible either way.
    """
    result = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--cached", "--others", "--exclude-standard"],
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
        # The whole directory, not one file: the harness became two files when the
        # cdk-nag v3 migration added cdk-nag-v3.test.ts, and a single-file counter
        # would have kept reporting the smaller number as correct.
        lambda: sum(
            _count_in(path, r"^[ \t]*it\(") for path in sorted((PORTAL / "tests" / "infrastructure").glob("*.test.ts"))
        ),
        "it( blocks under tests/infrastructure/",
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


def check_cognito_groups() -> list[Finding]:
    """Every group an authorization rule names must be one `defineAuth` creates.

    `allow.groups(["storage-admin"])` synthesises and deploys whether or not the
    group exists, and a request from a member of a group that does not exist is
    simply unauthorised. That shipped: five endpoints were guarded on
    `storage-admin` while `defineAuth` declared no groups at all, so the group
    existed only where somebody had created it with the CLI. A sandbox that had
    been running a while had it and worked; a freshly deployed one did not, and
    the symptom was not an error but the administrative sections quietly missing
    — which reads as "not built yet" rather than "misconfigured".

    The reverse is not checked. A declared group with no rule naming it is how a
    group is introduced before the endpoints that will use it.
    """
    data = PORTAL / "amplify" / "data" / "resource.ts"
    auth = PORTAL / "amplify" / "auth" / "resource.ts"
    if not data.exists() or not auth.exists():
        return [Finding("cognito-group", "amplify/", "auth or data resource definition is missing")]

    referenced: dict[str, int] = {}
    for number, line in enumerate(data.read_text(encoding="utf-8").splitlines(), start=1):
        for match in re.finditer(r"allow\.groups\(\[([^\]]*)\]\)", line):
            for name in re.findall(r'"([^"]+)"', match.group(1)):
                referenced.setdefault(name, number)

    # The declaration is a `groups:` array in the defineAuth call. Read as a block
    # so a list spanning several lines is seen whole.
    auth_text = auth.read_text(encoding="utf-8")
    declared: set[str] = set()
    block = re.search(r"^\s*groups:\s*\[(.*?)\]", auth_text, re.MULTILINE | re.DOTALL)
    if block:
        declared = set(re.findall(r'"([^"]+)"', block.group(1)))

    return [
        Finding(
            "cognito-group",
            f"amplify/data/resource.ts:{line}",
            f'authorization names the group "{name}", which amplify/auth/resource.ts does not '
            f"declare. Add it to `groups` in defineAuth, or a fresh deploy will have no such "
            f"group and every caller will be unauthorised. Declared: {sorted(declared) or 'none'}",
        )
        for name, line in sorted(referenced.items())
        if name not in declared
    ]


def check_orphan_env_reads() -> list[Finding]:
    """Environment variables a deployed handler reads that no template sets.

    Two of these were found together, and neither announced itself. One was a
    leftover: the notification bridge kept reading an `APPSYNC_API_URL` from
    before it wrote to DynamoDB directly, defaulting to "" and used nowhere. The
    other was worse — a second copy of the S3 Object Lock reader in the
    data-protection handler, on an `OUTPUT_BUCKET` no template set, under a role
    with no S3 permissions. It was reachable through the API and could only fail,
    and it failed as "OUTPUT_BUCKET not configured", which points the operator at
    a setting rather than at the wrong endpoint.

    Only reads that fall back to an empty value are reported. A read with a real
    default is a tunable — `MAX_ZIP_FILES` falling back to 500 gives the ZIP
    export the limit the documentation states, and nothing is broken by the
    template staying silent about it. A read that falls back to "" is different in
    kind: the empty string is not a setting anyone chose, and every feature behind
    one of these is written as `if not value: return` or fails downstream.

    Only functions wired into `backend.ts` are considered: `office-convert` and
    `secure-viewer` are checked in but not deployed, and their variables are
    correctly absent.

    Set anywhere in `backend.ts` counts as set. Associating a variable with the
    one function that receives it would need the TypeScript parsed rather than
    scanned, and the failure this catches is a name nothing provides at all.
    """
    backend = PORTAL / "amplify" / "backend.ts"
    if not backend.exists():
        return [Finding("orphan-env", "amplify/backend.ts", "backend definition is missing")]
    backend_text = backend.read_text(encoding="utf-8")

    provided = set(re.findall(r"^\s+([A-Z][A-Z_0-9]*):", backend_text, re.MULTILINE))
    # Lambda provides these to every function; no template mentions them.
    runtime_supplied = {"AWS_REGION", "AWS_LAMBDA_FUNCTION_NAME", "AWS_EXECUTION_ENV"}

    findings: list[Finding] = []
    for directory in sorted((PORTAL / "functions").iterdir()):
        if not directory.is_dir() or f'functions/{directory.name}"' not in backend_text:
            continue
        for source in sorted(directory.glob("*.py")):
            for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
                for match in re.finditer(r'os\.environ(?:\.get)?\(?\[?"([A-Z][A-Z_0-9]*)"', line):
                    name = match.group(1)
                    if name in provided or name in runtime_supplied:
                        continue
                    # Whether a fallback was supplied at all, and whether it is the
                    # empty string. Tested on the text after the name rather than by
                    # matching a literal, because a default can be an expression:
                    # `str(500 * 1024 * 1024)` is a real limit, and a pattern looking
                    # only for a quoted value reads it as no default and reports the
                    # ZIP export as switched off.
                    rest = line[match.end() :].lstrip()
                    if rest.startswith(",") and rest[1:].lstrip()[:2] not in ('""', "''"):
                        continue  # a tunable with a working default, not a dead feature
                    findings.append(
                        Finding(
                            "orphan-env",
                            f"functions/{directory.name}/{source.name}:{number}",
                            f'reads "{name}" with an empty fallback, and amplify/backend.ts never '
                            f"sets it. Either set it on this function, or delete the read: the "
                            f"feature behind it is switched off in a way that looks like the "
                            f"operator forgot a setting.",
                        )
                    )
    return findings


# Colour literals still written directly into a rule, rather than taken from a
# token. Four remain -- an overlay that stays dark, a saturated purple fill, and the
# two amber shades of a starred item -- and each carries a comment at its line
# saying why. The number is a ceiling so it can only fall: a new panel that
# hardcodes a light background is invisible until somebody opens the portal in dark
# mode, which is exactly the kind of rot the theme was added to stop.
THEME_LITERAL_BUDGET = 4

# Properties whose value has to follow the theme. `box-shadow` and `fill` are
# deliberately out: shadows go through --color-shadow already, and the SVG fills are
# on brand marks that do not change.
#
# Not anchored to the start of the line, and stopping at `}` as well as `;`. This
# stylesheet writes status rules on one line -- `.state-online { background: #dcfce7;
# color: #166534; }` -- and an anchored pattern sees the selector, not the
# declaration. It reported 5 literals while 201 were present, so the budget passed
# for a year of edits that each added a light-only colour.
_THEMED_PROPERTY = re.compile(
    r"\b(background(?:-color)?|color|border[a-z-]*|outline(?:-color)?)\s*:(?P<value>[^;}]*)",
    re.IGNORECASE,
)
_COLOUR_LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b|\bwhite\b|\bblack\b")


def check_theme_literals() -> list[Finding]:
    """Colour literals in the portal stylesheet that no token stands behind.

    The stylesheet had 612 of these across 167 distinct values, which is why there
    was no dark theme for so long: adding one meant finding and pairing every last
    literal. They are now roles — `--color-surface`, `--color-text-secondary`,
    `--color-error-bg` — and the few that remain are listed against a budget.

    Reported as a count rather than per-line on purpose. The individual lines are
    fine; what matters is that the total does not grow, because the failure mode is
    silent. A component that writes `background: #fff` looks correct to whoever
    wrote it and is a white slab to everyone using the dark theme.

    The palette definitions themselves are skipped: they are where the literals are
    supposed to be.
    """
    stylesheet = PORTAL / "src" / "index.css"
    if not stylesheet.exists():
        return [Finding("theme-literal", "src/index.css", "the portal stylesheet is missing")]

    offenders: list[str] = []
    inside_palette = False
    for number, line in enumerate(stylesheet.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        # The palette blocks are the selectors that define the tokens.
        if stripped.startswith((":root", '[data-theme="dark"]')):
            inside_palette = True
        elif inside_palette and stripped == "}":
            inside_palette = False
        if inside_palette or stripped.startswith("--"):
            continue
        for match in _THEMED_PROPERTY.finditer(line):
            # A literal inside a var() fallback still applies when the property is
            # unset, so it counts.
            for literal in _COLOUR_LITERAL.findall(match.group("value")):
                offenders.append(f"src/index.css:{number} {match.group(1)}: {literal}")

    if len(offenders) <= THEME_LITERAL_BUDGET:
        return []
    return [
        Finding(
            "theme-literal",
            "src/index.css",
            f"{len(offenders)} colour literals outside the palette, over the budget of "
            f"{THEME_LITERAL_BUDGET}. Use a role token so the value follows the theme; a "
            f"hardcoded light colour is invisible until someone opens the portal in dark "
            f"mode. If one genuinely belongs in both themes, lower the budget instead by "
            f"replacing another. Offenders:\n      " + "\n      ".join(offenders),
        )
    ]


# An inline style, written as a JSX `style={{ ... }}` value.
_INLINE_COLOUR = re.compile(
    r"\b(background(?:Color)?|color|border(?:Color|Top|Bottom|Left|Right|LeftColor)?)"
    # Everything the property is set to, up to the next property or the end of the
    # object -- not just a string sitting immediately after the colon. The value is
    # often an expression, and a ternary picking between three hex fills put the
    # literal several characters past where a `\"` anchor could see it. Three of them
    # were painting the volume capacity bar in every theme while this rule reported
    # the file clean.
    # A comma ends the value, because the next property starts there -- except inside
    # parentheses, where `var(--name, #fallback)` uses one and the fallback is the
    # literal this rule most wants to see.
    r"\s*:\s*(?P<value>(?:[^,}\n(]|\([^)\n]*\))*)",
)


def check_inline_style_literals() -> list[Finding]:
    """Colour literals in inline styles, which no theme can reach.

    A rule in the stylesheet can at least be overridden by a later selector. An
    inline style cannot: it wins against everything short of `!important`, so a
    literal here is a permanent light-mode fill.

    This is the second place the theme leaked, and it leaked because the check
    above reads one file. Six agent task cards kept their pale fills under the dark
    theme and inherited the dark theme's light text, leaving a 1.1:1 title -- text
    the same colour as the card. Every gate the repository has was green.

    No budget. Unlike the stylesheet there is no case for a literal here: a value
    that genuinely belongs in both themes can be a token whose two definitions
    happen to match.
    """
    findings: list[Finding] = []
    for path in sorted((PORTAL / "src").rglob("*.ts*")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for match in _INLINE_COLOUR.finditer(line):
                for literal in _COLOUR_LITERAL.findall(match.group("value")):
                    findings.append(
                        Finding(
                            "inline-colour",
                            f"{path.relative_to(PORTAL)}:{number}",
                            f"inline style sets {match.group(1)} to the literal {literal}. An "
                            f"inline style cannot be restyled, so this stays as written in every "
                            f"theme. Use var(--color-...) -- an inline style may hold one.",
                        )
                    )
    return findings


_VAR_REFERENCE = re.compile(r"var\(\s*(--[a-z][a-z0-9-]*)")
# MULTILINE because the definitions are collected with findall over the whole file.
# Without it only the first line can match, every token reads as undefined, and 969
# findings is indistinguishable from the check being broken -- which it was.
_VAR_DEFINITION = re.compile(r"^\s*(--[a-z][a-z0-9-]*)\s*:", re.MULTILINE)


def check_undefined_tokens() -> list[Finding]:
    """`var(--name)` where nothing defines `--name`.

    The quietest of the three. `var(--text-secondary, #666)` reads as themed and is
    the literal every single time, because the token is called --color-text-secondary
    and nothing declares the shorter name. Without a fallback it is worse: the
    declaration is invalid, the property is dropped, and the text inherits whatever
    it happens to sit on.

    Ten such names were in use, across 71 references. They are the reason a check on
    literals alone is not enough -- these have no literal to find at the reference,
    and the fallback that carries the real value sits inside a construct that looks
    like the fix.

    Also catches the reverse, which is how the names got there: a component invents
    --surface-color, the palette calls it --color-surface, and both spellings look
    equally plausible at the call site.
    """
    stylesheet = PORTAL / "src" / "index.css"
    if not stylesheet.exists():
        return [Finding("undefined-token", "src/index.css", "the portal stylesheet is missing")]

    defined = set(_VAR_DEFINITION.findall(stylesheet.read_text(encoding="utf-8")))
    findings: list[Finding] = []
    for path in sorted((PORTAL / "src").rglob("*")):
        if path.suffix not in {".css", ".ts", ".tsx"} or not path.is_file():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if _VAR_DEFINITION.match(line):
                continue
            for name in _VAR_REFERENCE.findall(line):
                if name in defined:
                    continue
                near = sorted(d for d in defined if name.lstrip("-") in d or d.lstrip("-") in name)
                findings.append(
                    Finding(
                        "undefined-token",
                        f"{path.relative_to(PORTAL)}:{number}",
                        f"reads {name}, which the palette never defines, so this resolves to its "
                        f"fallback every time -- or to nothing, dropping the declaration."
                        + (f" Did you mean {near[0]}?" if near else ""),
                    )
                )
    return findings


# In a TypeScript double-quoted string, `\\"` is a backslash followed by a quote, and
# `\\\\` is two backslashes. Neither is anything a UI string wants to say.
_OVER_ESCAPED = re.compile(r'\\\\(?:\\"|\\\\)')


def check_locale_escaping() -> list[Finding]:
    """Locale strings escaped one level too many.

    37 strings across all eight locales read `\\\\"` where they meant `\\"`, so the
    rendered text was `Delete user \\"admin\\"?` -- the backslashes on screen, in a
    confirmation dialog, in every language. The same doubling hit the one string that
    wants a real backslash: `DOMAIN\\\\\\\\user` rendered as `DOMAIN\\\\user`.

    Nothing caught it because it is not a missing key, not an untranslated string and
    not a type error: the key exists in all eight locales, the types agree, and the
    value is a valid string. Only its content is wrong, and reviewing a diff of
    escaped CJK is exactly where an eye slides past.

    Consistent across every locale and only on strings containing a quote or a
    backslash, which is the signature of an escaping pass that ran twice.
    """
    findings: list[Finding] = []
    locales = PORTAL / "src" / "i18n" / "locales"
    if not locales.is_dir():
        return [Finding("locale-escaping", "src/i18n/locales", "the locale directory is missing")]
    for path in sorted(locales.glob("*.ts")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if _OVER_ESCAPED.search(line):
                findings.append(
                    Finding(
                        "locale-escaping",
                        f"{path.relative_to(PORTAL)}:{number}",
                        "escaped one level too many, so the backslash is rendered to the user. "
                        'Write \\" for a quote and \\\\ for a backslash: '
                        f"{line.strip()[:90]}",
                    )
                )
    return findings


# A locale entry: two-space indent, key, string value. Enough for ja.ts, which is written
# one entry per line and is the file the type is derived from.
_LOCALE_ENTRY = re.compile(r'^  ([A-Za-z][\w$]*): "(.*)",?$')
_PLACEHOLDER = re.compile(r"\{[A-Za-z][\w]*\}")
_T_CALL = re.compile(r'\bt\(\s*"([A-Za-z][\w$]*)"\s*\)')
# The portal fills placeholders three ways: `.replace("{tok}", value)`, and the helpers
# `fill(t(key), { tok: value })` and `withNodes(t(key), { tok: <node> })`, which name the
# token as an object key. A rule that knew only the first reported all four helper call
# sites, and a rule that reports correct code is a rule that gets switched off.
_TOKEN_HELPER = re.compile(r"\b(?:fill|withNodes)\(\s*$")
_PLACEHOLDER_EXEMPT = re.compile(r"/[/*][ \t]*i18n-placeholder-checked:[ \t]*\S")
# How far after the call to look for the substitution. The value is usually replaced in
# the same expression; the widest real case in this codebase assigns the string first and
# replaces it on the next line.
_SUBSTITUTION_WINDOW = 15


def check_unsubstituted_placeholders() -> list[Finding]:
    """A translation used without filling in the placeholders it carries.

    The quota panel asked `「{name}」を本当に削除しますか？` -- with the braces on
    screen, in a delete confirmation. Four other panels call the same key and all four
    substitute; this one passed the key through untouched.

    Nothing else could catch it. The key exists in all eight locales, the types agree,
    the string is valid, and `t()` returns exactly what it was given: the defect is a
    call site that did not finish the job, and it is only visible in the rendered text.

    Reported per placeholder, because a key with two of them can have one filled in.
    """
    findings: list[Finding] = []
    ja = PORTAL / "src" / "i18n" / "locales" / "ja.ts"
    if not ja.is_file():
        return [Finding("i18n-placeholder", "src/i18n/locales/ja.ts", "the source locale is missing")]

    # ja.ts is the type source, so its placeholders are the contract every locale copies.
    tokens: dict[str, set[str]] = {}
    for line in ja.read_text(encoding="utf-8").splitlines():
        entry = _LOCALE_ENTRY.match(line)
        if not entry:
            continue
        found = set(_PLACEHOLDER.findall(entry.group(2)))
        if found:
            tokens[entry.group(1)] = found

    if not tokens:
        return [
            Finding("i18n-placeholder", "src/i18n/locales/ja.ts", "no placeholders found, so the rule reads nothing")
        ]

    sources = sorted(p for p in (PORTAL / "src").rglob("*.ts*") if "locales" not in p.parts)
    if not sources:
        return [Finding("i18n-placeholder", "src", "no sources found, so nothing is covered")]

    for path in sources:
        lines = path.read_text(encoding="utf-8").splitlines()
        for number, text in enumerate(lines, start=1):
            for call in _T_CALL.finditer(text):
                key = call.group(1)
                if key not in tokens:
                    continue
                window = "\n".join(lines[max(0, number - 4) : number + _SUBSTITUTION_WINDOW])
                if _PLACEHOLDER_EXEMPT.search(window):
                    continue
                # Only a helper call gets to satisfy the rule by naming the token as an
                # object key; elsewhere a bare `name:` nearby is some other property.
                helper = bool(_TOKEN_HELPER.search(text[: call.start()]))
                missing = sorted(
                    tok
                    for tok in tokens[key]
                    if f'"{tok}"' not in window and not (helper and re.search(rf"\b{tok[1:-1]}\s*:", window))
                )
                if missing:
                    findings.append(
                        Finding(
                            "i18n-placeholder",
                            f"{path.relative_to(PORTAL)}:{number}",
                            f't("{key}") carries {", ".join(missing)} and nothing nearby replaces it, '
                            'so the reader sees the braces. Add .replace("{token}", value) '
                            "or mark the line '// i18n-placeholder-checked: <reason>'",
                        )
                    )
    return findings


_S3_CLIENT = re.compile(r"boto3\.client\(\s*[\"']s3[\"']")
_PRESIGN = re.compile(r"generate_presigned_url")


def check_presign_safe_s3_clients() -> list[Finding]:
    """An S3 client in the portal that cannot presign a usable URL.

    `generate_presigned_url` does not sign with SigV4 unless told to, and under the
    default addressing style botocore presigns the global `s3.amazonaws.com` even with a
    region configured. S3 answers such a URL with 301 PermanentRedirect naming the
    regional host, and the signature covers `host`, so the redirect cannot be followed.
    The upload link the portal handed out was unusable for exactly this reason, and had
    been since it shipped.

    Six other functions in the portal presign too, and all six were already correct --
    each naming an explicit regional `endpoint_url` alongside `s3v4`. Measured
    2026-08-15: both that shape (path-style) and `addressing_style="virtual"` return 200
    against an Access Point alias. The one that broke was the one client written without
    either.

    So the rule is not about which of the two shapes to use. It is that a module which
    presigns must not leave both to the default, because the default is the one
    combination that does not work.
    """
    findings: list[Finding] = []
    functions = PORTAL / "functions"
    if not functions.is_dir():
        return [Finding("presign-config", "functions", "the functions directory is missing")]

    sources = sorted(p for p in functions.rglob("*.py") if "tests" not in p.parts)
    if not sources:
        return [Finding("presign-config", "functions", "no handlers found, so nothing is covered")]

    for path in sources:
        text = path.read_text(encoding="utf-8")
        if not _PRESIGN.search(text) or not _S3_CLIENT.search(text):
            continue
        # The client construction spans lines, so the whole module is the window. A
        # module that builds two clients and configures one is not distinguished here;
        # that would need the call extent, and no module in the portal does it.
        if "s3v4" not in text:
            findings.append(
                Finding(
                    "presign-config",
                    str(path.relative_to(PORTAL)),
                    "presigns a URL with an S3 client that does not ask for SigV4. "
                    'Add config=Config(signature_version="s3v4", ...)',
                )
            )
            continue
        if "endpoint_url" not in text and "addressing_style" not in text:
            findings.append(
                Finding(
                    "presign-config",
                    str(path.relative_to(PORTAL)),
                    "asks for SigV4 but leaves the endpoint to the default, which presigns "
                    "the global host and answers 301. Name a regional endpoint_url, or "
                    's3={"addressing_style": "virtual"}',
                )
            )
    return findings


_USE_QUERY = re.compile(r"\buseQuery\s*\(")
# Start-of-line so a stray `enabled` inside a queryFn body is not read as the option.
_ENABLED_OPTION = re.compile(r"^\s*enabled\s*:", re.MULTILINE)
# `const { ... } = useQuery(` or `const name = useQuery(`. Applied to the text before
# the call, rightmost match, so only the declaration that receives it is considered.
_QUERY_BINDING = re.compile(r"(?:const|let)\s+(\{[^{}]*\}|[A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*$")
_PENDING_FIELD = re.compile(r"\bisPending\b|\bstatus\b")
# Both comment forms: inside JSX the marker has to be `{/* ... */}`, because `//` there
# would be rendered as text. Accepting only `//` made the rule impossible to satisfy on
# exactly the reads that are written in markup.
#
# `[ \t]*` and not `\s*` after the colon: `\s` matches a newline, so a bare marker with
# nothing after it found the first word of the next line and read as a reason. That made
# `// query-gate-checked:` a mute switch, which is what requiring a reason prevents.
_GATE_EXEMPT = re.compile(r"/[/*][ \t]*query-gate-checked:[ \t]*\S")


# A `/` after one of these opens a regular expression rather than dividing. Enough to
# tell the two apart in this codebase, where every regex literal follows a call paren,
# an `=`, a comma or a `return`.
_REGEX_PRECEDES = set("(,=:[!&|?{};+-*%^~")
# ...but not when what follows rules a pattern out. `/>` closes a JSX tag and `/=`
# divides in place; both sit after a `}` or a quote, which is in the set above. Reading
# either as a regex blanked the rest of its line, taking a `)}` with it.
_NOT_REGEX_AFTER = {">", "=", "/", "*", " ", "\t", "\n", ""}


def _blank_strings_and_comments(source: str) -> str:
    """The source with strings, comments and regex literals blanked, offsets intact.

    Brace matching below would otherwise be thrown by a bracket inside any of them, and
    `enabled:` written in a comment would read as the option. Lengths are preserved so
    every offset still maps to the same line.

    All three kinds have to be handled, and each was found by breaking:

    - strings only: the apostrophe in a prose comment opened a string that never closed
      and blanked the rest of the file;
    - strings and comments: ``text.split(/(\\*\\*[^*]+\\*\\*|`[^`]+`)/g)`` put a
      backtick inside a regex, which opened a template literal that ran to the end.

    Both times the checker then found nothing and reported it as a pass, which is why
    `_masking_is_sound` runs over the result.
    """
    out = list(source)
    index = 0
    end = len(source)
    previous = ""
    while index < end:
        char = source[index]
        two = source[index : index + 2]
        if two == "//":
            while index < end and source[index] != "\n":
                out[index] = " "
                index += 1
        elif two == "/*":
            while index < end and source[index : index + 2] != "*/":
                if source[index] != "\n":
                    out[index] = " "
                index += 1
            for offset in range(index, min(index + 2, end)):
                out[offset] = " "
            index += 2
        elif char in "\"'`" or (
            char == "/" and previous in _REGEX_PRECEDES and source[index + 1 : index + 2] not in _NOT_REGEX_AFTER
        ):
            closer = char
            in_class = False
            index += 1
            while index < end:
                current = source[index]
                if current == "\\":
                    out[index] = " "
                    if index + 1 < end and source[index + 1] != "\n":
                        out[index + 1] = " "
                    index += 2
                    continue
                if closer == "/":
                    # A `/` inside a character class does not end the pattern.
                    if current == "[":
                        in_class = True
                    elif current == "]":
                        in_class = False
                    elif current == "\n":
                        break  # An unterminated regex is a mis-read `/`; give up on it.
                if current == closer and not in_class:
                    break
                if current != "\n":
                    out[index] = " "
                index += 1
            index += 1
        else:
            if not char.isspace():
                previous = char
            index += 1
    return "".join(out)


def _masking_is_sound(masked: str) -> bool:
    """Whether the masked source still has balanced brackets.

    Independent of what the caller is looking for. A runaway string or comment blanks
    real code, which leaves an opening bracket without its partner, so this catches a
    mis-read of any cause -- including one nobody has hit yet. Counting the construct
    under test instead would not: a `useQuery(` written inside a doc comment is
    correctly blanked and would read as a loss.
    """
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: list[str] = []
    for char in masked:
        if char in "([{":
            stack.append(char)
        elif char in pairs:
            if not stack or stack.pop() != pairs[char]:
                return False
    return not stack


def _call_extent(text: str, open_paren: int) -> int:
    """Index of the `)` closing the call that opens at `open_paren`, or -1."""
    depth = 0
    for index in range(open_paren, len(text)):
        char = text[index]
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
            if depth == 0:
                return index
    return -1


_COMMENT_ONLY = re.compile(r"^\s*(?://|/?\*|\{?/\*)")


def _marker_window(lines: list[str], number: int) -> str:
    """The read's own line, the one above it, and any comment block continuing upward.

    One line of lookback is not enough: the reason for an exemption rarely fits on one,
    and a marker on the first line of a two-line comment was missed by the version that
    looked back exactly one line -- which reads as an unmarked violation, the opposite
    of what the author wrote.
    """
    first = max(0, number - 2)
    while first > 0 and _COMMENT_ONLY.match(lines[first - 1]):
        first -= 1
    return "\n".join(lines[first:number])


def check_query_gate_reads() -> list[Finding]:
    """`isPending` read from a useQuery that declares `enabled`.

    A disabled query is `status: "pending"` with `fetchStatus: "idle"`, because it has
    no data and never asked for any. So `isPending` on a gated query does not mean "a
    request is in flight", it means "nothing has loaded yet" -- and while the gate is
    shut that is permanently true.

    The qtree panel shipped this. It gated on a chosen volume, read `isPending` as
    `loading`, and returned a spinner for the whole panel while loading -- so the
    volume dropdown, the only thing that could open the gate, was never rendered. No
    request was ever made and the spinner never cleared. `tsc`, the linter and every
    other check here passed: the types are right, the query is correct, and the bug is
    entirely in what the flag was taken to mean.

    `isFetching` is false while a query is disabled, which is what a loading flag
    wants. A read that genuinely needs "no data yet" has to check the gate itself on
    the same path, and can say so with `// query-gate-checked: <reason>` on the read
    or the line above it.
    """
    findings: list[Finding] = []
    for path in sorted((PORTAL / "src").rglob("*.ts*")):
        source = path.read_text(encoding="utf-8")
        if "useQuery" not in source:
            continue
        masked = _blank_strings_and_comments(source)
        lines = source.splitlines()

        # A reader that quietly stops seeing calls reports a clean tree, which is the
        # failure this whole check exists to prevent.
        if not _masking_is_sound(masked):
            findings.append(
                Finding(
                    "query-gate-read",
                    str(path.relative_to(PORTAL)),
                    "brackets do not balance after masking strings, comments and regex "
                    "literals, so a string or comment ran past its end and blanked real "
                    "code. This file is not being checked. Fix "
                    "_blank_strings_and_comments in this script, not the file.",
                )
            )
            continue
        for call in _USE_QUERY.finditer(masked):
            close = _call_extent(masked, masked.index("(", call.start()))
            if close < 0:
                continue
            options = masked[call.end() : close]
            if not _ENABLED_OPTION.search(options):
                continue

            binding = _QUERY_BINDING.search(masked[: call.start()])
            if not binding:
                continue
            target = binding.group(1)

            # Destructured: the pending flag is named in the pattern itself. Object
            # form: it is read later as `name.isPending`.
            if target.startswith("{"):
                # Offset of the field inside the pattern, not of the pattern, so the
                # report names the line the flag is on and the marker has one place
                # to go in either shape.
                reads = [
                    (binding.start(1) + field.start(), field.group(0)) for field in _PENDING_FIELD.finditer(target)
                ]
            else:
                reads = [
                    (match.start(), match.group(1))
                    for match in re.finditer(rf"\b{re.escape(target)}\.(isPending|status)\b", masked)
                ]

            for offset, field in reads:
                number = masked.count("\n", 0, offset) + 1
                if _GATE_EXEMPT.search(_marker_window(lines, number)):
                    continue
                findings.append(
                    Finding(
                        "query-gate-read",
                        f"{path.relative_to(PORTAL)}:{number}",
                        f"reads {field} from a useQuery that sets `enabled`. A disabled query "
                        f"stays pending forever, so this is true whenever the gate is shut, not "
                        f"only while a request is running. Use isFetching for a loading flag -- "
                        f"or, if this path already checks the same condition as `enabled`, say so "
                        f"with `// query-gate-checked: <reason>` above the read, or "
                        f"`{{/* query-gate-checked: <reason> */}}` inside JSX.",
                    )
                )
    return findings


_PALETTE_BLOCK = re.compile(r"(:root|\[data-theme=\"dark\"\])\s*\{(.*?)\n\}", re.DOTALL)
_TOKEN_DEFINITION = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;]+);")
_RULE_BLOCK = re.compile(r"([^{}]*)\{([^{}]*)\}")
_BLOCK_BACKGROUND = re.compile(r"(?<![-a-z])background(?:-color)?\s*:\s*([^;]+)")
_BLOCK_COLOUR = re.compile(r"(?<![-a-z])color\s*:\s*([^;]+)")
_BLOCK_FONT_SIZE = re.compile(r"(?<![-a-z])font-size\s*:\s*([\d.]+)rem")
_BLOCK_FONT_WEIGHT = re.compile(r"(?<![-a-z])font-weight\s*:\s*(\d+)")
_HEX = re.compile(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_TOKEN_REFERENCE = re.compile(r"var\((--[a-z0-9-]+)\)$")


def _resolve(value: str, tokens: dict[str, str], depth: int = 0) -> tuple[int, int, int] | None:
    """A colour as RGB, following token references. None when it is not a plain hex."""
    value = value.strip()
    if depth > 4:
        return None
    if reference := _TOKEN_REFERENCE.match(value):
        target = tokens.get(reference.group(1))
        return _resolve(target, tokens, depth + 1) if target else None
    if match := _HEX.match(value):
        digits = match.group(1)
        if len(digits) == 3:
            digits = "".join(c * 2 for c in digits)
        return int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16)
    return None


def _contrast(first: tuple[int, int, int], second: tuple[int, int, int]) -> float:
    def relative(colour: tuple[int, int, int]) -> float:
        def channel(value: float) -> float:
            value /= 255
            return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

        red, green, blue = (channel(c) for c in colour)
        return 0.2126 * red + 0.7152 * green + 0.0722 * blue

    lighter, darker = sorted((relative(first), relative(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def check_theme_contrast() -> list[Finding]:
    """Text and its fill, in both themes, against the WCAG AA threshold.

    Tokens made the theme switchable and did not make it legible. The dark palette
    lightens the accent fills -- it has to, or they vanish against a dark page -- and
    inverse text stayed white on top of them: every primary button at 3.4:1, the
    approve button at 2.8:1. Nothing was a light slab, so the fill rules above were
    all satisfied, and it is the kind of thing that reads as merely "a bit soft"
    rather than as a defect.

    The fix those numbers forced was --color-on-primary / -success / -error: text that
    flips with the theme while the fill it sits on does not.

    Only pairs written in the *same rule* are compared. A `color` whose background
    comes from a different selector needs the cascade to resolve, which needs a
    browser; that half runs against the live portal. This half needs no browser and so
    can run on every commit, which is the half that catches a new button.

    Translucent fills are skipped: `rgba(0, 0, 0, 0.05)` over a card is a real
    technique, and treating it as opaque black reports 1.2:1 for text that is
    comfortably legible. Those are the browser sweep's business.
    """
    stylesheet = PORTAL / "src" / "index.css"
    if not stylesheet.exists():
        return [Finding("theme-contrast", "src/index.css", "the portal stylesheet is missing")]
    css = stylesheet.read_text(encoding="utf-8")

    palettes: dict[str, dict[str, str]] = {}
    for match in _PALETTE_BLOCK.finditer(css):
        palettes[match.group(1)] = dict(_TOKEN_DEFINITION.findall(match.group(2)))
    if len(palettes) != 2:
        return [
            Finding(
                "theme-contrast",
                "src/index.css",
                f'expected a :root and a [data-theme="dark"] palette, found {sorted(palettes)}',
            )
        ]

    findings: list[Finding] = []
    for block in _RULE_BLOCK.finditer(css):
        selector, body = block.group(1), block.group(2)
        background = _BLOCK_BACKGROUND.search(body)
        colour = _BLOCK_COLOUR.search(body)
        if not background or not colour:
            continue
        # A named threshold needs the rendered size; use what the block declares and
        # fall back to the stricter one, which is the default for body text anyway.
        size = _BLOCK_FONT_SIZE.search(body)
        weight = _BLOCK_FONT_WEIGHT.search(body)
        points = float(size.group(1)) * 16 if size else 16.0
        bold = int(weight.group(1)) >= 700 if weight else False
        threshold = 3.0 if points >= 24 or (bold and points >= 18.66) else 4.5

        name = selector.strip().splitlines()[-1].strip() if selector.strip() else "(unknown)"
        for label, tokens in (("light", palettes[":root"]), ("dark", palettes['[data-theme="dark"]'])):
            text = _resolve(colour.group(1), tokens)
            fill = _resolve(background.group(1), tokens)
            if not text or not fill:
                continue
            ratio = _contrast(text, fill)
            if ratio < threshold:
                findings.append(
                    Finding(
                        "theme-contrast",
                        f"src/index.css ({label})",
                        f"{name}: {colour.group(1).strip()} on {background.group(1).strip()} is "
                        f"{ratio:.1f}:1, under {threshold}:1. An accent fill that lightens for the "
                        f"dark theme cannot carry --color-text-inverse; use the matching "
                        f"--color-on-* token, which flips with the theme.",
                    )
                )
    return findings


_DECLARATION = re.compile(r"([a-z-]+)\s*:\s*([^;]+)")


@dataclass(frozen=True)
class _CssRule:
    selector: str
    declarations: dict[str, str]
    important: frozenset[str]
    position: int
    line: int
    media: str | None
    specificity: tuple[int, int, int]
    target: str

    def __hash__(self) -> int:  # dict is unhashable; identity is enough here
        return hash((self.selector, self.position))


def _specificity(selector: str) -> tuple[int, int, int]:
    """(ids, classes, elements). Enough to compare two selectors for this purpose."""
    selector = re.sub(r"::[a-z-]+", "", selector)
    ids = len(re.findall(r"#[\w-]+", selector))
    classes = len(re.findall(r"\.[\w-]+", selector)) + len(re.findall(r"\[[^\]]+\]", selector))
    classes += len(re.findall(r":(?!not\()[a-z-]+", selector))
    elements = len(re.findall(r"(?:^|[\s>+~])([a-z][\w-]*)", selector))
    return ids, classes, elements


def _parse_rules(css: str) -> list[_CssRule]:
    """Every rule in source order, with the media query it sits in."""
    rules: list[_CssRule] = []
    media: list[str] = []
    index = 0
    while index < len(css):
        brace = css.find("{", index)
        if brace == -1:
            break
        close = css.find("}", index)
        if close != -1 and close < brace:
            if media:
                media.pop()
            index = close + 1
            continue
        prelude = css[index:brace].strip().splitlines()
        head = prelude[-1].strip() if prelude else ""
        if head.startswith("@media"):
            media.append(head)
            index = brace + 1
            continue
        if head.startswith("@"):
            index = brace + 1
            continue
        end = css.find("}", brace)
        body = css[brace + 1 : end] if end != -1 else ""
        declarations = {m.group(1): m.group(2).strip() for m in _DECLARATION.finditer(body)}
        important = frozenset(key for key, value in declarations.items() if "!important" in value)
        for selector in (s.strip() for s in head.split(",")):
            if not selector:
                continue
            rules.append(
                _CssRule(
                    selector=selector,
                    declarations=declarations,
                    important=important,
                    position=brace,
                    line=css.count("\n", 0, brace) + 1,
                    media=media[-1] if media else None,
                    specificity=_specificity(selector),
                    target=re.split(r"[\s>+~]+", selector.strip())[-1],
                )
            )
        index = end + 1 if end != -1 else brace + 1
    return rules


def _same_element(loser: _CssRule, winner: _CssRule) -> bool:
    """Whether the winner styles the same box as the loser, unconditionally.

    Three pairings look like overrides and are not:

      * `.snapshot-table th` against `.snapshot-table` -- a descendant is a different
        element, and its font-size is not competing. Four of the eight first-pass
        findings were this.
      * `.file-select:checked::before` against `.file-select` -- a pseudo-element is a
        box of its own.
      * `.portal-layout:not(.sidebar-collapsed) .portal-sidebar` against
        `.portal-sidebar` -- a state selector overriding a default is how the drawer is
        built, not a mistake.

    So the ancestor chain has to match exactly, and only the final compound may carry
    extra classes. That deliberately gives up one real case: a variant with an extra
    ancestor, such as `.lock-dialog .dialog-content` shadowing a responsive
    `.dialog-content`, leaves the responsive rule dead for that variant alone. It is
    indistinguishable in shape from the state-selector pattern above, and a rule that
    reports both would be turned off for the noise.
    """
    if "::" in winner.selector:
        return False
    loser_chain = re.split(r"\s*[\s>+~]\s*", loser.selector.strip())
    winner_chain = re.split(r"\s*[\s>+~]\s*", winner.selector.strip())
    if len(loser_chain) != len(winner_chain):
        return False
    if loser_chain[:-1] != winner_chain[:-1]:
        return False
    a, b = loser_chain[-1], winner_chain[-1]
    if a == b:
        return True
    return b.startswith(a) and b[len(a) :].startswith((".", ":", "["))


def check_dead_media_overrides() -> list[Finding]:
    """Responsive rules that the cascade discards.

    A media query adds no specificity. A rule inside `@media (max-width: 768px)` is
    therefore beaten by the same selector appearing later in the file, and by any more
    specific selector anywhere in it -- and the declaration stays present, valid and
    ignored, which is why this is worth a check rather than a comment.

    Two of these were live at once, both in the mobile layout:

      * `.portal-layout { grid-template-columns: minmax(0, 1fr) }` lost to
        `.portal-layout.sidebar-collapsed { … 0px 1fr auto }` 200 lines earlier -- two
        classes against one. Since collapsed is the default state on a phone, the
        three-column desktop grid was applied against a one-area template and the
        topbar came out 40px wide.
      * `.file-select { min-width: 24px }` lost `margin` to a rule 900 lines later.

    Both were found by reading computed styles in a browser, one at a time.

    `!important` is honoured in both directions, so the field-size floor -- which uses
    it deliberately, because the browser zooms below 16px regardless of which
    component owns the field -- is not reported.
    """
    stylesheet = PORTAL / "src" / "index.css"
    if not stylesheet.exists():
        return [Finding("dead-media-override", "src/index.css", "the portal stylesheet is missing")]

    rules = _parse_rules(stylesheet.read_text(encoding="utf-8"))
    findings: list[Finding] = []
    seen: set[str] = set()
    for rule in rules:
        if not rule.media or "max-width" not in rule.media:
            continue
        for prop, value in rule.declarations.items():
            for other in rules:
                if other is rule:
                    continue
                # A rule outside any query always competes. A rule inside one competes
                # only when it applies at exactly the same widths -- the same condition
                # text. Two blocks with the same breakpoint are common in a long
                # stylesheet, and the later silently wins for the whole range.
                #
                # This was the gap that let a second, redundant bottom-sheet rule be
                # written for `.file-preview-popover` at `max-width: 768px` while an
                # existing one 700 lines later was doing the work. Overlapping but
                # unequal ranges are deliberately not compared: `max-width: 480px`
                # beating `max-width: 768px` below 480 is how breakpoints are meant to
                # nest, and reporting it would bury the real cases.
                if other.media is not None and other.media != rule.media:
                    continue
                if prop not in other.declarations or other.declarations[prop] == value:
                    continue
                if prop in rule.important and prop not in other.important:
                    continue
                if not _same_element(rule, other):
                    continue
                beaten = (other.selector == rule.selector and other.position > rule.position) or (
                    other.specificity > rule.specificity
                )
                if not beaten:
                    continue
                # Already handled if this media block restates it in a form that
                # actually beats the winner. That is the cascade's own rule: higher
                # specificity, or equal specificity and later in the file.
                #
                # Both halves were learned from a wrong answer. `sibling is not rule`
                # is needed because a selector's specificity is trivially >= its own,
                # so the rule rescued itself whenever the winner won on order. And
                # requiring the sibling to out-position the winner is needed because
                # two identical dead rules in two blocks with the same media text
                # rescued each other, and the pair reported nothing.
                if any(
                    sibling is not rule
                    and sibling.media == rule.media
                    and prop in sibling.declarations
                    and _same_element(other, sibling)
                    and (
                        sibling.specificity > other.specificity
                        or (sibling.specificity == other.specificity and sibling.position > other.position)
                    )
                    for sibling in rules
                ):
                    continue
                key = f"{rule.line}:{rule.selector}:{prop}"
                if key in seen:
                    continue
                seen.add(key)
                findings.append(
                    Finding(
                        "dead-media-override",
                        f"src/index.css:{rule.line}",
                        f"inside {rule.media}, `{rule.selector} {{ {prop} }}` is discarded: line "
                        f"{other.line} `{other.selector}` wins on "
                        f"{'source order' if other.selector == rule.selector else 'specificity'}. A "
                        f"media query adds no specificity. Name the stronger selector here too, or "
                        f"move this rule below the one it has to beat.",
                    )
                )
    return findings


_NARROW_CONSTANT = re.compile(r"const NARROW_VIEWPORT\s*=\s*(\d+)")


def check_breakpoint_agreement() -> list[Finding]:
    """The width in App.tsx against the width the stylesheet switches at.

    Two sources for one number. The stylesheet decides when the sidebar becomes a
    drawer over the content; App.tsx decides when it should start closed and close
    itself after a section is picked. Move one and not the other and there is a band of
    widths where the drawer covers the content and nothing dismisses it -- which is the
    state the portal shipped in at every width, so it is not a hypothetical failure.

    A comment saying "keep these in step" is what was there before.
    """
    app = PORTAL / "src" / "App.tsx"
    stylesheet = PORTAL / "src" / "index.css"
    if not app.exists() or not stylesheet.exists():
        return [Finding("breakpoint", "src", "App.tsx or index.css is missing")]

    match = _NARROW_CONSTANT.search(app.read_text(encoding="utf-8"))
    if not match:
        return [
            Finding(
                "breakpoint",
                "src/App.tsx",
                "NARROW_VIEWPORT is gone. If the drawer no longer needs a width in "
                "JavaScript, delete this check; if it was renamed, point the check at the "
                "new name. Silently not finding it is the one outcome that helps nobody.",
            )
        ]

    declared = int(match.group(1))
    widths = {int(w) for w in re.findall(r"@media\s*\(max-width:\s*(\d+)px\)", stylesheet.read_text(encoding="utf-8"))}
    if declared in widths:
        return []
    return [
        Finding(
            "breakpoint",
            "src/App.tsx",
            f"NARROW_VIEWPORT is {declared}px and the stylesheet has no "
            f"`@media (max-width: {declared}px)` block; it breaks at {sorted(widths)}. Between "
            f"the two values the sidebar is a drawer over the content that nothing closes.",
        )
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
    findings = (
        check_action_inventories()
        + hardcoded
        + check_doc_contradictions()
        + check_measured_false_claims()
        + check_count_claims()
        + check_cognito_groups()
        + check_orphan_env_reads()
        + check_theme_literals()
        + check_inline_style_literals()
        + check_undefined_tokens()
        + check_theme_contrast()
        + check_dead_media_overrides()
        + check_breakpoint_agreement()
        + check_locale_escaping()
        + check_unsubstituted_placeholders()
        + check_presign_safe_s3_clients()
        + check_query_gate_reads()
    )

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
