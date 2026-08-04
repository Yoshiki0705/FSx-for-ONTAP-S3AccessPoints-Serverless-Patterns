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
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORTAL = ROOT / "solutions" / "amplify-portal"

# Characters that only appear in a user-facing string. Comments are exempt: they
# are for whoever maintains the file, not for the person using the portal.
CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]")


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

    components = sorted((PORTAL / "src").rglob("*.tsx"))
    if not components:
        return [Finding("hardcoded-string", "src", "no .tsx files found, so nothing is covered")], []

    for path in components:
        for number, text in _strip_comments_and_imports(path.read_text()):
            if not CJK.search(text):
                continue
            if "t(" in text:
                fallbacks += 1
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
                "add a key to src/i18n/locales/ja.ts and the other seven locales, or if this "
                "is genuinely not user-facing, append the line to scripts/portal-drift-baseline.txt "
                f"with a reason. {fallbacks} existing t()-with-fallback lines are not counted here.",
            )
        )
    return findings, fingerprints


# A claim that is false, paired with the code that disproves it. Both halves are
# checked: the rule only fires while the contradicting code is present, so it
# stops complaining by itself if the behaviour is ever removed.
CONTRADICTIONS = [
    {
        "claim": re.compile(
            r"(blocks?\s+do\s+not\s+expire"
            r"|nothing\s+expires\s+it\s+automatically"
            r"|no\s+TTL\s+and\s+no\s+scheduled\s+unblock"
            r"|ブロックは自動では失効しません"
            r"|TTL もスケジュール解除もない)",
            re.IGNORECASE,
        ),
        "disproved_by": ("functions/data-protection/handler.py", "sweepExpiredBlocks"),
        "why": "the expiry sweep exists, so blocks do expire",
    },
]
# A rule matching "read-only" near "containment" was tried and removed: the
# sentence "regular users can view ARP status (read-only) but cannot execute
# containment actions" is correct, and no pattern over those words separates it
# from a false claim. A rule that cannot tell a true statement from a false one
# trains people to ignore the check.

DOC_GLOBS = ["docs/ja/*.md", "docs/en/*.md", "solutions/amplify-portal/docs/*.md"]


def check_doc_contradictions() -> list[Finding]:
    findings: list[Finding] = []
    for rule in CONTRADICTIONS:
        handler_path, marker = rule["disproved_by"]
        handler = PORTAL / handler_path
        if not handler.exists() or marker not in handler.read_text():
            # The claim may now be accurate; nothing to enforce.
            continue
        for pattern in DOC_GLOBS:
            for path in sorted(ROOT.glob(pattern)):
                for number, line in enumerate(path.read_text().split("\n"), start=1):
                    if rule["claim"].search(line):
                        findings.append(
                            Finding(
                                "doc-contradiction",
                                f"{path.relative_to(ROOT)}:{number}",
                                f"{rule['why']}: {line.strip()[:90]}",
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
            "# Hardcoded user-facing strings in the portal that predate this check.\n"
            "#\n"
            "# The check fails only on lines absent from this file, so new drift is\n"
            "# blocked without demanding the whole backlog be cleared first. Removing a\n"
            "# line from here after adding a translation key is the intended direction;\n"
            "# adding one needs a reason.\n"
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
    findings = check_action_inventories() + hardcoded + check_doc_contradictions()

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
