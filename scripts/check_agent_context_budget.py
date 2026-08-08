#!/usr/bin/env python3
"""Keep the agent-facing documentation reachable, published, and within budget.

Three failures are guarded here, all of which happened.

**AGENTS.md grew to 78 KB.** It is loaded on every turn and cannot be made
conditional, so every byte was paid for in every session — mostly for pitfall
tables relevant only while doing that one kind of work. Splitting it out fixed
the size, and nothing stopped it from creeping back one useful paragraph at a
time. Prose asking future contributors to be disciplined does not survive contact
with a deadline. A failing check does.

**Eleven steering files declared `inclusion: auto` without the `name` and
`description` that auto inclusion requires.** Kiro never registered them, so
roughly 110 KB of guidance was never loaded. Nothing failed. An agent missing
knowledge it was given looks exactly like an agent that was never given it.

**The first split moved that content into `.kiro/`, which is deliberately not
published.** The pitfall tables had been public documentation in AGENTS.md, so
the move silently deleted them from the repository and left twelve pointers that
resolve to nothing for anyone who clones it. Content therefore lives in
`docs/agent/` and `.kiro/` holds only the front matter that decides when to load
it. The loader budget below is what keeps it that way: a loader that grows is
knowledge leaking back to the side nobody else can read.

Front-matter parsing is duplicated from the SessionStart hook rather than shared.
The hook must run in any repository without this one on its path, and this check
must run in CI without a home directory. Two twenty-line parsers cost less than a
dependency that breaks one of those two environments.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

AGENTS_BUDGET = 28_000
AGENT_DOC_BUDGET = 14_000
LOADER_BUDGET = 2_000

VALID_INCLUSION = {"always", "fileMatch", "manual", "auto"}
ROOT = Path(__file__).resolve().parent.parent


def front_matter(path: Path) -> dict[str, str]:
    """Parse leading YAML front matter into top-level key/value pairs.

    Args:
        path: File whose front matter should be read.

    Returns:
        Mapping of key to value. A key whose value is an indented block is
        reported as ``"<block>"`` so callers can tell "present" from "omitted".
        An empty mapping means the file has no front matter.
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    lines = text[3:end].splitlines()
    fields: dict[str, str] = {}
    for index, line in enumerate(lines):
        if not line.strip() or line.lstrip().startswith("#") or line[0] in " \t":
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        value = value.strip()
        if not value:
            for following in lines[index + 1 :]:
                if not following.strip():
                    continue
                if following[:1] in (" ", "\t"):
                    value = "<block>"
                break
        fields[key.strip()] = value
    return fields


def tracked() -> set[str] | None:
    """Paths git tracks, or None when git cannot answer.

    Only git decides what a reader of the repository can open. The filesystem
    says yes to files `.gitignore` excludes, which is how a link to a gitignored
    translation shipped and 404'd for everyone but its author.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "--cached", "--others", "--exclude-standard"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return {line for line in proc.stdout.splitlines() if line}


def kiro_present() -> bool:
    """Whether this checkout carries the local agent configuration at all.

    `.kiro/` is gitignored by design, so a clone and a CI runner have none of it.
    The loader checks are skipped there rather than reporting an expected absence
    as a finding: a check that is noisy in CI gets removed from CI.
    """
    return (ROOT / ".kiro/steering").is_dir() or (ROOT / ".kiro/skills").is_dir()


def check_budgets(problems: list[str]) -> None:
    """Append a problem for any agent-facing file over its budget.

    Args:
        problems: Accumulator appended to in place.
    """
    size = len((ROOT / "AGENTS.md").read_bytes())
    if size > AGENTS_BUDGET:
        problems.append(
            f"AGENTS.md が {size:,} B で予算 {AGENTS_BUDGET:,} B を超えています。"
            "常時ロードなので全セッションで課金されます。作業内容に依存する記述は "
            "docs/agent/ に移し、AGENTS.md の索引に 1 行だけ足してください。"
        )

    for path in sorted((ROOT / "docs/agent").glob("*.md")):
        size = len(path.read_bytes())
        if size > AGENT_DOC_BUDGET:
            problems.append(
                f"{path.relative_to(ROOT)} が {size:,} B で予算 {AGENT_DOC_BUDGET:,} B を"
                "超えています。トピックが広すぎないか、分割できないか検討してください。"
            )

    if not kiro_present():
        return

    loaders = sorted((ROOT / ".kiro/steering").glob("*.md")) + sorted((ROOT / ".kiro/skills").glob("*/SKILL.md"))
    for path in loaders:
        fields = front_matter(path)
        if fields.get("inclusion") in {None, "always"} and "steering" in path.parts:
            continue  # always-on project steering may legitimately hold content
        size = len(path.read_bytes())
        if size > LOADER_BUDGET:
            problems.append(
                f"{path.relative_to(ROOT)} が {size:,} B で予算 {LOADER_BUDGET:,} B を"
                "超えています。.kiro/ は公開されないので、本文は docs/agent/ に置き、"
                "こちらは読み込み条件とポインタだけにしてください。"
            )


def check_index_targets(problems: list[str]) -> None:
    """Append a problem for any AGENTS.md pointer a reader could not follow.

    Args:
        problems: Accumulator appended to in place.
    """
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    published = tracked()

    links = re.findall(r"\]\((?!https?://|/|#|mailto:)([^)#\s]+)", text)
    if not any(link.startswith("docs/agent/") for link in links):
        problems.append("AGENTS.md が docs/agent/ を一つも参照していません。分割した知識への入口が失われています。")
    for link in sorted(set(links)):
        target = ROOT / link
        if not target.exists():
            problems.append(f"AGENTS.md のリンク {link} が存在しません。索引が壊れています。")
        elif published is not None and link not in published:
            problems.append(
                f"AGENTS.md のリンク {link} はリポジトリに含まれていません"
                "（gitignore）。clone した読者には 404 になります。"
            )
        if link.startswith(".kiro/"):
            problems.append(
                f"AGENTS.md が .kiro/ 配下 ({link}) をリンクしています。"
                ".kiro/ は公開しないため、リンク先は docs/agent/ に置いてください。"
            )


def check_loaders(problems: list[str]) -> None:
    """Append a problem for each loader Kiro would never register, or that dangles.

    Args:
        problems: Accumulator appended to in place.
    """
    if not kiro_present():
        return

    published = tracked()

    for path in sorted((ROOT / ".kiro/steering").glob("*.md")):
        fields = front_matter(path)
        name = path.relative_to(ROOT)
        inclusion = fields.get("inclusion")
        if inclusion is not None:
            if inclusion not in VALID_INCLUSION:
                problems.append(f"{name}: inclusion '{inclusion}' は無効な値です。")
            if inclusion == "auto":
                for required in ("name", "description"):
                    if not fields.get(required):
                        problems.append(
                            f"{name}: inclusion:auto に {required} がありません。"
                            "この状態では登録されず、一度も読み込まれません。"
                        )
            if inclusion == "fileMatch" and not fields.get("fileMatchPattern"):
                problems.append(f"{name}: inclusion:fileMatch に fileMatchPattern がありません。")
        _check_pointer(path, name, published, problems)

    for path in sorted((ROOT / ".kiro/skills").glob("*/SKILL.md")):
        fields = front_matter(path)
        name = path.relative_to(ROOT)
        expected = path.parent.name
        if fields.get("name") != expected:
            problems.append(
                f"{name}: name が {fields.get('name')!r} でディレクトリ名 {expected!r} と"
                "一致しません。スキルとして認識されません。"
            )
        if not fields.get("description"):
            problems.append(f"{name}: description がありません。呼び出されません。")
        _check_pointer(path, name, published, problems)


def _check_pointer(path: Path, name: Path, published: set[str] | None, problems: list[str]) -> None:
    """Verify every docs/agent path a loader points at exists and is published."""
    body = path.read_text(encoding="utf-8")
    for target in sorted(set(re.findall(r"(docs/agent/[A-Za-z0-9._/-]+\.md)", body))):
        if not (ROOT / target).exists():
            problems.append(f"{name}: 参照先 {target} が存在しません。読み込んでも空になります。")
        elif published is not None and target not in published:
            problems.append(
                f"{name}: 参照先 {target} がリポジトリに含まれていません。本体を公開側に置く前提が崩れています。"
            )


def main() -> int:
    """Run every check and report.

    Returns:
        1 when any problem was found, otherwise 0.
    """
    problems: list[str] = []
    check_budgets(problems)
    check_index_targets(problems)
    check_loaders(problems)

    if problems:
        print("エージェントコンテキストの予算 / 到達性に問題があります:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    size = len((ROOT / "AGENTS.md").read_bytes())
    docs = len(list((ROOT / "docs/agent").glob("*.md")))
    if not kiro_present():
        print(
            f"agent context OK: AGENTS.md {size:,} B / {AGENTS_BUDGET:,} B, "
            f"docs/agent {docs} 件。.kiro/ はこのチェックアウトに無いためローダーは未検査。"
        )
        return 0

    loaders = len(list((ROOT / ".kiro/steering").glob("*.md"))) + len(list((ROOT / ".kiro/skills").glob("*/SKILL.md")))
    print(f"agent context OK: AGENTS.md {size:,} B / {AGENTS_BUDGET:,} B, docs/agent {docs} 件, ローダー {loaders} 件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
