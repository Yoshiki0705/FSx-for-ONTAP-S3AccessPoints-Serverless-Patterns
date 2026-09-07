#!/usr/bin/env python3
"""Ask before merging a change to a workflow that no pull request ever runs.

## The failure this exists to stop

`repo-name-redirects.yml` was written, verified locally, reviewed, and merged with 31
green checks. **None of those 31 was the workflow itself** -- its triggers are `schedule`
and `workflow_dispatch`, so a pull request cannot run it. Dispatched by hand after merge,
it failed on its first execution: `github.com` returned 504 for two repositories on every
attempt from a GitHub-hosted runner, something no local run had produced.

Then it got worse. Local runs had 504'd on *different* URLs each time, so the failure was
diagnosed as transient and a retry was merged. The runner's 504s were persistent, so the
retry was the wrong fix and a second change was needed to replace the mechanism outright.

**Two merges spent on a problem one dispatch would have surfaced.** The green checks were
not wrong; they were about a different thing, and the gap between "the checks passed" and
"this workflow works" was invisible because nothing named it.

## Why ask rather than block

Dispatching needs the branch pushed, so the correct order is push, dispatch, read the run,
then merge. That is a sequence a human drives, and there are legitimate reasons to merge
without it -- a comment-only edit, a workflow deliberately left unrun until a secret
exists. A block would be wrong often enough to get switched off. An ask at the moment of
merging is the last point where the information still changes the decision.

## Why merge time rather than authoring time

At authoring time there is nothing to dispatch: `workflow_dispatch` resolves a `--ref`, so
the workflow has to exist on a pushed branch first. Merge is the first moment when
dispatching is both possible and still useful.

## Scope

A workflow is *unobserved* when its triggers include neither `pull_request` nor `push`.
Measured 2026-09-07 in this repository: four of fourteen -- `bedrock-default-validation`,
`e2e-portal`, `published-articles-check`, `repo-name-redirects`. The other ten run on every
pull request, so a change to them is already exercised before merge and asking would be
noise.

Usage:
    python3 scripts/guard_unobserved_workflow_merge.py            # PreToolUse, JSON on stdin
    python3 scripts/guard_unobserved_workflow_merge.py --selftest # ask/allow corpus
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"

# Merging is the decision this guard is about. `gh pr create` is not: at that point the
# branch is pushed but the pull request does not exist yet, and asking then would fire on
# every draft.
MERGE_RE = re.compile(r"\bgh\s+pr\s+merge\b")

# Triggers that make a workflow run on a pull request, and so make it observed. `push` counts
# because a branch push exercises it before the merge decision.
OBSERVED_TRIGGERS = ("pull_request", "pull_request_target", "push", "merge_group")

TRIGGER_RE = re.compile(r"^(?P<indent>[ \t]{0,4})(?P<name>[a-z_]+)[ \t]*:", re.MULTILINE)


def triggers(text: str) -> set[str]:
    """Extract the trigger names from a workflow's `on:` block.

    Parsed with a regex rather than a YAML library on purpose: this runs as a PreToolUse
    hook on every shell command, so it must not depend on anything outside the standard
    library. The shapes that matter are `on:` followed by an indented mapping and the inline
    `on: [push]` list; both appear in this repository.

    Args:
        text: Full contents of a workflow file.

    Returns:
        Lowercased trigger names. Empty when no `on:` block was found, which the caller
        treats as unknown rather than as unobserved.
    """
    inline = re.search(r"^on:\s*\[(?P<list>[^\]]+)\]", text, re.MULTILINE)
    if inline:
        return {t.strip().strip("\"'").lower() for t in inline.group("list").split(",")}

    block = re.search(r"^on:\s*$(?P<body>.*?)(?=^\S)", text, re.MULTILINE | re.DOTALL)
    if not block:
        single = re.search(r"^on:\s*(?P<one>[a-z_]+)\s*$", text, re.MULTILINE)
        return {single.group("one").lower()} if single else set()

    found: set[str] = set()
    for match in TRIGGER_RE.finditer(block.group("body")):
        # Only the mapping's own keys, which sit at two spaces. Deeper indentation is a
        # trigger's configuration -- `branches:`, `cron:` -- and naming one of those as a
        # trigger would misread `push:\n  branches:` shapes.
        if len(match.group("indent")) <= 2:
            found.add(match.group("name").lower())
    return found


def unobserved_workflows(root: Path = ROOT) -> set[str]:
    """Workflow filenames that no pull request or branch push can run.

    Args:
        root: Repository root, overridable for tests.

    Returns:
        Filenames relative to `.github/workflows/`. A file whose `on:` block cannot be read
        is excluded: guessing "unobserved" from a parse failure would ask on every merge and
        teach people to wave the prompt through.
    """
    directory = root / ".github" / "workflows"
    if not directory.is_dir():
        return set()
    names: set[str] = set()
    for path in sorted(directory.glob("*.y*ml")):
        try:
            found = triggers(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        if found and not found.intersection(OBSERVED_TRIGGERS):
            names.add(path.name)
    return names


def changed_workflows(root: Path = ROOT) -> set[str]:
    """Unobserved workflows touched by the branch being merged.

    Compares the current branch against the default branch. When git cannot answer -- a
    detached head, no upstream, git absent -- this returns every unobserved workflow rather
    than none, so a broken comparison produces a question instead of silence.

    Args:
        root: Repository root, overridable for tests.

    Returns:
        Filenames relative to `.github/workflows/`.
    """
    unobserved = unobserved_workflows(root)
    if not unobserved:
        return set()
    try:
        diff = subprocess.run(
            ["git", "diff", "--name-only", "origin/main...HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return unobserved
    if diff.returncode != 0:
        return unobserved
    touched = {Path(line).name for line in diff.stdout.splitlines() if line.startswith(".github/workflows/")}
    return touched & unobserved


def decide(command: str, root: Path = ROOT) -> tuple[str, str]:
    """Classify a command.

    Args:
        command: The shell command the hook intercepted.
        root: Repository root, overridable for tests.

    Returns:
        `("ask", reason)` or `("allow", "")`.
    """
    if not MERGE_RE.search(command):
        return "allow", ""
    names = changed_workflows(root)
    if not names:
        return "allow", ""
    listed = ", ".join(sorted(names))
    return "ask", (
        f"This merge changes {listed}, which no pull request runs: its triggers include "
        "neither pull_request nor push, so none of the green checks on this PR executed it. "
        "A scheduled workflow merged unrun failed on its first dispatch once already, and "
        "the misdiagnosis that followed cost a second merge. Dispatch it on this branch "
        "first and read the run:\n"
        f"  gh workflow run {sorted(names)[0]} --ref $(git branch --show-current)\n"
        "Then merge. Proceed anyway only if there is nothing to observe -- a comment-only "
        "edit, or a workflow waiting on a secret that does not exist yet."
    )


def main(argv: list[str]) -> int:
    """Read a PreToolUse event from stdin and emit the hook decision.

    Args:
        argv: Command-line arguments; `--selftest` runs the corpus instead.

    Returns:
        0 always. This guard asks; it never blocks.
    """
    if "--selftest" in argv:
        return _selftest()

    if sys.stdin.isatty():
        print(
            "This is a PreToolUse hook: it expects a JSON event on stdin.\n"
            '  echo \'{"tool_input":{"command":"gh pr merge 1 --squash"}}\' '
            "| python3 scripts/guard_unobserved_workflow_merge.py\n"
            "To verify ask/allow behaviour:\n"
            "  python3 scripts/guard_unobserved_workflow_merge.py --selftest",
            file=sys.stderr,
        )
        return 0

    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    tool_input = event.get("tool_input") or {}
    command = tool_input.get("command") or ""
    if not isinstance(command, str):
        return 0

    outcome, reason = decide(command)
    if outcome == "ask":
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "permissionDecision": "ask",
                        "permissionDecisionReason": reason,
                    }
                }
            )
        )
    return 0


def _selftest() -> int:
    """Run the tracked corpus.

    Imported from the test module so there is one list of cases rather than a pytest list
    and a hand-run list that disagree -- the failure a sibling guard was ported to fix,
    where the executing copy allowed 10 of the 26 cases the tracked copy documented.
    """
    sys.path.insert(0, str(ROOT / "scripts" / "tests"))
    from guard_unobserved_workflow_merge_test import ALLOW_CASES, ASK_CASES  # noqa: PLC0415

    failures = 0
    for command, root, expected in [*ASK_CASES, *ALLOW_CASES]:
        outcome, _reason = decide(command, root() if callable(root) else root)
        if outcome != expected:
            print(f"  {expected} expected, {outcome} returned: {command!r}", file=sys.stderr)
            failures += 1
    total = len(ASK_CASES) + len(ALLOW_CASES)
    print(f"selftest: {total - failures}/{total} case(s) as documented")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
