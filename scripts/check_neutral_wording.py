#!/usr/bin/env python3
"""Refuse vendor-versus wording in published files.

The standard is to present alternatives as options suited to different contexts,
never as competitors to be beaten. This checker holds the machine-checkable part of
it: a short list of words whose only use is to rank one product above another.

Two things about the shape of this file.

**It is the single copy of the rule.** The check began as a `grep` inlined in
`.github/workflows/agent-output-audit.yml`, which meant the pattern could not be
tested -- there was no way to assert that a document it should refuse actually
fails, so the gate's own correctness rested on reading it. The workflow now calls
this script, and `make drift` runs the same script locally, so the rule has one
definition and both callers get whatever it says.

**The word list is deliberately short.** Deciding what to include is a judgement
about false positives, not about which words are undesirable. `顧客` appears 18
times in this tree and every one is legitimate ("not the customer data itself",
"customer-managed CMK", fictional demo records). `競合` appears about 30 times and
every one is technical contention -- a VPC endpoint collision, bandwidth contention
between S3 AP and NFS/SMB, a write conflict, a port clash. Adding either would make
this gate produce dozens of findings on every run that a reader must dismiss one by
one, and a gate whose output is routinely dismissed is a gate that gets removed.
So the list holds only words that do not occur legitimately here, and
`allow:neutrality` is available for the case where one does.

What it caught when first run over the tree, none of which any existing check saw:

- `| Category | Service | Key differentiator |` -- a comparison table asking, in its
  column heading, what makes each service better than the others.
- "the production preset's differentiator" -- describing a preset's own feature.
- 他社列 / 他社の -- "the other companies' column", where 比較対象 says the same thing
  without the framing.
- 差別化要素 in fictional sample data. Fictional, but still authored and published,
  and the demo works identically without it.

Exits 1 on any finding, and also on an empty file set: globs that no longer fit the
tree would otherwise report a tick over nothing.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

#: A line carrying this marker is not reported. Needed because a document that
#: records the guardrail, or explains why a comparison is framed the way it is, has
#: to be able to contain the word it is discussing.
ALLOW_MARKER = "allow:neutrality"

#: Each pattern with the reason it is refused and what to write instead. The reason
#: is printed with the finding: a checker that says only "violation" leaves the
#: author guessing at which of several rules they hit and how to satisfy it.
#:
#: Patterns are matched case-insensitively.
RULES: tuple[tuple[str, str], ...] = (
    (
        r"differentiator",
        "ranks products against each other; describe the capability itself "
        "(e.g. 'Notable capabilities', 'CloudFront delivery, added by this preset')",
    ),
    (
        r"差別化",
        "ベンダー間の優劣を含意する。機能そのものを書く（例: 「選定理由として挙がる」）",
    ),
    (
        r"他社",
        "比較を「自社 vs 他社」の枠に置く。「各サービス」「比較対象」を使う",
    ),
    (
        r"優位性",
        "優劣の主張。用途に応じた向き不向きとして書く",
    ),
    (
        r"競合ツール",
        "他の製品を競合として位置づける。「選択肢」「他のアプローチ」を使う",
    ),
    (
        r"より優れ",
        "優劣の主張。「A は〜に向く / B は〜に向く」と対称に書く",
    ),
    (
        r"最強|game[- ]changer|ゲームチェンジャー",
        "marketing superlative; state the fact that supports the claim instead",
    ),
    (
        r"competitive advantage",
        "positions the work against competitors; state the outcome for the reader",
    ),
    (
        r"is better than|is superior to",
        "ranks one option above another; state the trade-off symmetrically",
    ),
)

#: Which files are audited. Derived from the tree by glob rather than listed, so a
#: new document is covered by the commit that adds it.
#:
#: Not markdown only. The inline predecessor scanned `.md`, and the sibling naming
#: check learned the same lesson the harder way: restricted to `.md`, it let the
#: violation sit in a shell comment, a Python comment and a CloudFormation
#: description indefinitely, because nothing looked there. A published repository
#: publishes its comments.
SCAN_GLOBS = (
    "**/*.md",
    "**/*.py",
    "**/*.ts",
    "**/*.tsx",
    "**/*.yaml",
    "**/*.yml",
    "**/*.sh",
)

#: Directory prefixes skipped entirely, each for a reason that is not "it has
#: findings we do not want to see".
EXCLUDED_PREFIXES: tuple[str, ...] = (
    # A rule cannot be written without naming what it forbids. These paths define
    # the standard, so their matches are the rule text itself.
    ".github/",
    ".kiro/",
    "AGENTS.md",
    "scripts/check_neutral_wording.py",
    "scripts/tests/test_check_neutral_wording.py",
    # Not authored here.
    "node_modules/",
    ".venv/",
    "cdk.out/",
    ".aws-sam/",
    ".git/",
    ".canonical-audit/",
)


def _is_excluded(rel_path: str) -> bool:
    """Whether a repository-relative path is outside the audited set."""
    return any(rel_path.startswith(prefix) for prefix in EXCLUDED_PREFIXES)


def discover_files(project_root: Path, paths: list[str] | None = None) -> list[Path]:
    """Audited files: either the ones named, or every match of SCAN_GLOBS.

    Naming paths explicitly is how CI narrows the run to a pull request's changed
    files. The exclusions still apply to a named path, so a caller passing a rule
    file does not turn the rule text into a finding.
    """
    if paths:
        candidates = [project_root / p for p in paths]
    else:
        candidates = [match for glob in SCAN_GLOBS for match in project_root.glob(glob) if match.is_file()]

    seen: set[Path] = set()
    out: list[Path] = []
    for candidate in sorted(candidates):
        if not candidate.is_file():
            continue
        try:
            rel = candidate.relative_to(project_root).as_posix()
        except ValueError:
            continue
        if _is_excluded(rel) or candidate in seen:
            continue
        seen.add(candidate)
        out.append(candidate)
    return out


def check_file(path: Path) -> list[tuple[int, str, str]]:
    """Findings in one file as (line number, matched text, reason)."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, OSError):
        # Binary or unreadable. Not a finding: a file this checker cannot read is
        # not a file it can make a claim about.
        return []

    findings: list[tuple[int, str, str]] = []
    for lineno, line in enumerate(lines, start=1):
        if ALLOW_MARKER in line:
            continue
        for pattern, reason in RULES:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                findings.append((lineno, match.group(0), reason))
    return findings


def main(argv: list[str] | None = None, project_root: Path | None = None) -> int:
    """Report vendor-versus wording; return 1 if any was found.

    `project_root` is a parameter so the tests can run the real entry point over a
    fixture tree. Without it they could only assert on `check_file`, leaving the exit
    code -- the part CI actually consumes -- unasserted.
    """
    args = list(argv if argv is not None else sys.argv[1:])
    if project_root is None:
        project_root = Path(__file__).parent.parent
    files = discover_files(project_root, args or None)

    # An empty set means the globs stopped fitting the tree, or every named path was
    # excluded. Either way there is nothing behind a tick, so say so.
    if not files:
        print("❌ No files matched. SCAN_GLOBS no longer fits the tree, or all paths were excluded.")
        return 1

    total = 0
    for path in files:
        findings = check_file(path)
        if not findings:
            continue
        rel = path.relative_to(project_root).as_posix()
        for lineno, matched, reason in findings:
            print(f"{rel}:{lineno}: '{matched}' — {reason}")
            total += 1

    print()
    print(f"Scanned {len(files)} files.")
    if total == 0:
        print("✅ No vendor-versus wording found.")
        return 0
    print(f"❌ Found {total} occurrence(s) of vendor-versus wording.")
    print(
        f"\nRewrite as a trade-off rather than a ranking. If a line has to contain the "
        f"word — a document recording this guardrail, for instance — mark it "
        f"'{ALLOW_MARKER}'."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
