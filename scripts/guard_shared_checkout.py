#!/usr/bin/env python3
"""Stop one agent's git command from discarding another agent's staged work.

## What happened

Two agents worked in this clone at the same time. One created a branch and staged
three files. The other, tidying up, ran `git switch main -f` followed by
`git reset --hard origin/main` while HEAD was on that branch. The reset restored
tracked files and left untracked ones, so of the three files only the new one
survived — and HEAD was now main, so it was committed **directly to main**,
bypassing every pull-request gate.

Then the second agent reported that nothing had been lost, having checked
`git log main..<branch>` and found no commits. **A branch with no commits still has
an index.** The thing to check was `git status --porcelain` and `git diff --cached`.

## Why this is a hook and not a rule in a document

The rule was already written down. It was read every turn and not applied. What
makes the difference is the check running at the moment of the command, with the
list of what would be discarded in front of whoever is about to discard it.

## The four shapes

**Blocked outright**, because there is no case for them in a shared checkout:

- `git add -A` / `git add .` / `git add --all`, and `git commit -a`. They stage
  whatever is in the tree, including another agent's edits, which is how someone
  else's half-finished work ends up in your commit.
- `git commit` while HEAD is `main` or `master`. Work goes to a branch. Had this
  existed, the file above would have failed to land on main rather than landing
  there unnoticed.

**Asked, with the exact list of what would be lost**: `reset --hard`, `restore`,
`checkout -- <path>`, `switch`, `checkout <branch>`, `branch -f`, `branch -D`,
`stash`, `clean -f` — but only when the tree or the index is dirty. Clean, they
discard nothing and pass silently.

**Printed at commit time**: the branch and the staged file list, on every
`git commit`. Not a prompt, because a prompt on every commit teaches people to
click through. The requirement it answers is that the staged set has to be visible
*before* the commit, not reconstructed from `git show --stat` afterwards.

**Everything else** passes.

## The real fix is one checkout per agent

This guard reduces the damage; it does not make sharing safe. `git worktree add`
gives each session its own tree and index over the same object store, and this
repository already uses it. The ask messages say so, because a guard that only says
no teaches nothing.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PROTECTED_BRANCHES = ("main", "master")

# `git add` forms that stage by scope rather than by name.
ADD_EVERYTHING = re.compile(r"^-(?:A|-all)$|^\.$|^:/$")
# `git commit` forms that stage by scope. `-a` may be bundled: `-am`, `-va`.
COMMIT_ALL = re.compile(r"^-(?!-)[a-zA-Z]*a[a-zA-Z]*$|^--all$")

# Subcommands that can discard uncommitted work, and the phrase naming what each
# one puts at risk. `switch` and `checkout` are here for moving HEAD while the tree
# is dirty, which carries the edits onto another branch or refuses partway.
DESTRUCTIVE = {
    "reset": "the index, and with --hard the working tree",
    "restore": "the working-tree copy of the paths named",
    "checkout": "the working tree, or HEAD's idea of which branch you are on",
    "switch": "which branch HEAD is on, carrying or refusing the current edits",
    "stash": "the working tree (recoverable from the stash, if you remember it is there)",
    "clean": "untracked files, which no reflog and no stash can bring back",
    "branch": "a branch ref, and with -f or -D the commits only that ref pointed at",
}

BLOCK = 2
ALLOW = 0


def _git(*args: str, cwd: Path = ROOT) -> tuple[int, str]:
    """Run a git command and capture stdout.

    Args:
        args: Arguments after `git`.
        cwd: Directory to run in.

    Returns:
        `(returncode, stdout)`. A non-zero return means the caller must not read
        the output as an answer -- an empty result from a failed git call is what
        made a sibling repository's guard pass every merge silently.
    """
    try:
        proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return proc.returncode, proc.stdout


def branch(cwd: Path = ROOT) -> str | None:
    """Name of the branch HEAD is on.

    Args:
        cwd: Directory to run in.

    Returns:
        The branch name, `None` when git could not answer or HEAD is detached.
    """
    code, out = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd)
    if code != 0:
        return None
    name = out.strip()
    return None if not name or name == "HEAD" else name


def dirty(cwd: Path = ROOT) -> tuple[list[str], list[str]] | None:
    """Staged and unstaged paths.

    Args:
        cwd: Directory to run in.

    Returns:
        `(staged, unstaged)`, or `None` when git could not answer. `None` is not
        "clean": the caller has to treat an unanswerable question as a reason to
        ask rather than as permission.
    """
    code, out = _git("status", "--porcelain", cwd=cwd)
    if code != 0:
        return None
    staged: list[str] = []
    unstaged: list[str] = []
    for line in out.splitlines():
        if len(line) < 4:
            continue
        index_state, tree_state, path = line[0], line[1], line[3:]
        if index_state not in (" ", "?"):
            staged.append(path)
        if tree_state != " " or index_state == "?":
            unstaged.append(path)
    return staged, unstaged


def _describe(staged: list[str], unstaged: list[str]) -> str:
    """Render what is currently at risk.

    Args:
        staged: Paths with index changes.
        unstaged: Paths with working-tree changes or untracked.

    Returns:
        A short listing, truncated so the prompt stays readable.
    """
    lines = []
    for label, paths in (("staged", staged), ("not staged / untracked", unstaged)):
        if not paths:
            continue
        shown = ", ".join(paths[:8])
        more = f" (+{len(paths) - 8} more)" if len(paths) > 8 else ""
        lines.append(f"  {len(paths)} {label}: {shown}{more}")
    return "\n".join(lines)


def classify(command: str, cwd: Path = ROOT) -> tuple[int, str]:
    """Decide on one shell command.

    Args:
        command: The command the hook intercepted.
        cwd: Repository directory, overridable for tests.

    Returns:
        `(BLOCK, reason)` to deny, `(ALLOW, reason)` to ask when the reason is
        non-empty, `(ALLOW, "")` to pass.
    """
    try:
        words = shlex.split(command)
    except ValueError:
        return ALLOW, ""
    if "git" not in words:
        return ALLOW, ""
    # Take the segment starting at the last `git`, so a chained command is judged on
    # the git call rather than on whatever ran before it.
    words = words[words.index("git") :]
    flags = [w for w in words[1:] if w.startswith("-")]
    rest = [w for w in words[1:] if not w.startswith("-")]
    if not rest:
        return ALLOW, ""
    sub = rest[0]
    args = words[words.index(sub) + 1 :]

    if sub == "add" and any(ADD_EVERYTHING.match(a) for a in args):
        return BLOCK, (
            "BLOCKED: `git add` by scope in a shared checkout.\n\n"
            "It stages whatever is in the tree, including edits another agent has in "
            "flight. Name the files:\n"
            "  git add path/one path/two\n\n"
            "If you genuinely own every change here, list them anyway -- the listing is "
            "what makes the commit's contents a decision instead of a snapshot.\n\n"
            "  docs/agent/shared-checkout.md"
        )

    if sub == "commit" and any(COMMIT_ALL.match(f) for f in flags):
        return BLOCK, (
            "BLOCKED: `git commit -a` stages by scope, the same way `git add -A` does.\n\n"
            "Stage the files you mean by name, then commit without -a."
        )

    if sub == "commit":
        current = branch(cwd)
        if current in PROTECTED_BRANCHES:
            return BLOCK, (
                f"BLOCKED: HEAD is on `{current}`.\n\n"
                "Commits go to a branch and reach main through a pull request, which is "
                "where the gates run. A file once landed on main this way, from a session "
                "that had been moved off its own branch by another agent and did not "
                "notice.\n\n"
                "  git switch -c <branch>   # then commit"
            )
        state = dirty(cwd)
        if state is not None:
            staged, _ = state
            listing = "\n".join(f"    {p}" for p in staged[:20])
            more = f"\n    (+{len(staged) - 20} more)" if len(staged) > 20 else ""
            print(
                f"[shared-checkout] committing on `{current}` with {len(staged)} staged "
                f"file(s):\n{listing}{more}\n"
                "  If anything above is not yours, stop: unstage it before committing.",
                file=sys.stderr,
            )
        return ALLOW, ""

    if sub not in DESTRUCTIVE:
        return ALLOW, ""

    # `branch` only risks anything with -f or -D/-M.
    if sub == "branch" and not any(f in ("-f", "--force", "-D", "-M") for f in flags):
        return ALLOW, ""
    # `stash list`/`show` read; `stash`/`push`/`save` write.
    if sub == "stash" and args and args[0] in ("list", "show"):
        return ALLOW, ""
    # `clean` without a force flag refuses to do anything anyway.
    if sub == "clean" and not any("f" in f.lstrip("-") for f in flags):
        return ALLOW, ""

    state = dirty(cwd)
    if state is None:
        return ALLOW, (
            f"`git {sub}` — and git could not be asked what is uncommitted here, so what "
            "this would discard is unknown.\n\n"
            "An unanswerable question is not a clean tree. Check by hand before continuing."
        )
    staged, unstaged = state
    if not staged and not unstaged:
        return ALLOW, ""

    return ALLOW, (
        f"`git {sub}` puts {DESTRUCTIVE[sub]} at risk, and this checkout is not clean:\n\n"
        f"{_describe(staged, unstaged)}\n\n"
        "Two agents have shared this clone before, and a `reset --hard` here discarded "
        "the other one's staged files. A branch with no commits still has an index, so "
        "`git log` showing nothing is not evidence that nothing would be lost.\n\n"
        "If any of the above is not yours, do not continue. Give this session its own "
        "tree instead:\n"
        "  git worktree add /tmp/wt-<name> -b <branch>\n\n"
        "  docs/agent/shared-checkout.md"
    )


def main(argv: list[str]) -> int:
    """Read a PreToolUse event from stdin and emit the decision.

    Args:
        argv: Command-line arguments; `--selftest` exercises the corpus.

    Returns:
        2 to block, otherwise 0.
    """
    if "--selftest" in argv:
        return _selftest()
    if sys.stdin.isatty():
        print(
            "This is a PreToolUse hook: it expects a JSON event on stdin.\n"
            '  echo \'{"tool_input":{"command":"git add -A"}}\' '
            "| python3 scripts/guard_shared_checkout.py\n"
            "  python3 scripts/guard_shared_checkout.py --selftest",
            file=sys.stderr,
        )
        return ALLOW
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return ALLOW  # never fail closed: that would block all work
    if not isinstance(event, dict):
        return ALLOW
    tool_input = event.get("tool_input") or {}
    command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
    if not isinstance(command, str):
        return ALLOW
    code, message = classify(command)
    if code == BLOCK:
        print(message, file=sys.stderr)
        return BLOCK
    if message:
        json.dump(
            {"hookSpecificOutput": {"permissionDecision": "ask", "permissionDecisionReason": message}},
            sys.stdout,
        )
    return ALLOW


def _selftest() -> int:
    """Check block and allow behaviour without a repository state.

    Returns:
        0 when every case behaves as declared, 1 otherwise.
    """
    failures: list[str] = []
    for command in ("git add -A", "git add .", "git add --all", "git commit -am 'x'", "git commit --all"):
        code, _ = classify(command, cwd=ROOT)
        if code != BLOCK:
            failures.append(f"{command!r} was not blocked")
    for command in ("git add path/one", "git status", "git log --oneline", "echo git reset --hard"):
        with tempfile.TemporaryDirectory() as tmp:
            code, message = classify(command, cwd=Path(tmp))
        if code != ALLOW:
            failures.append(f"{command!r} was blocked")
    for line in failures:
        print(f"  {line}", file=sys.stderr)
    print("selftest: " + ("FAIL" if failures else "every case behaved as declared"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
