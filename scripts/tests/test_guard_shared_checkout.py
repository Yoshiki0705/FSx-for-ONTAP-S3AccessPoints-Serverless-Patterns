"""Tests for `scripts/guard_shared_checkout.py`.

Built around the sequence that made the guard necessary: an agent ran
`git switch main -f` and `git reset --hard origin/main` in a clone where another
agent had three files staged, and then reported that nothing was lost because
`git log main..<branch>` showed no commits.

So the cases that matter are the ones where the tree is dirty and the command
looks routine. Each test builds a real repository in a temp directory, because the
verdict depends on `git status` — a guard tested only against command strings would
pass while answering from the wrong tree, which is the failure mode of the sibling
repository's version of this.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
GUARD = ROOT / "scripts" / "guard_shared_checkout.py"


def _load() -> ModuleType:
    """Import the guard by path.

    Returns:
        The imported module.
    """
    spec = importlib.util.spec_from_file_location("guard_shared_checkout", GUARD)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["guard_shared_checkout"] = module
    spec.loader.exec_module(module)
    return module


guard = _load()


def _repo(tmp_path: Path, *, branch: str = "work", dirty: bool = False, staged: bool = False) -> Path:
    """Build a repository in a known state.

    Args:
        tmp_path: Directory to build in.
        branch: Branch to leave HEAD on.
        dirty: Leave an unstaged modification.
        staged: Leave a staged modification.

    Returns:
        The repository path.
    """

    def run(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, capture_output=True, timeout=30, check=True)

    run("init", "-q", "-b", "main")
    run("config", "user.email", "t@example.com")
    run("config", "user.name", "t")
    (tmp_path / "tracked.txt").write_text("one\n", encoding="utf-8")
    run("add", "tracked.txt")
    run("commit", "-q", "-m", "base")
    if branch != "main":
        run("switch", "-qc", branch)
    if dirty:
        (tmp_path / "tracked.txt").write_text("two\n", encoding="utf-8")
    if staged:
        (tmp_path / "theirs.txt").write_text("someone else's work\n", encoding="utf-8")
        run("add", "theirs.txt")
    return tmp_path


# --- blocked outright ---


@pytest.mark.parametrize(
    "command",
    ["git add -A", "git add --all", "git add .", "git add -A .", "git commit -am 'x'", "git commit --all -m x"],
)
def test_staging_by_scope_is_blocked(command: str, tmp_path: Path) -> None:
    code, message = guard.classify(command, cwd=_repo(tmp_path))
    assert code == guard.BLOCK, f"{command!r} stages another agent's edits"
    assert "name" in message.lower()


@pytest.mark.parametrize("command", ["git add path/one", "git add a b c", "git commit -m x", "git commit --amend"])
def test_naming_paths_is_allowed(command: str, tmp_path: Path) -> None:
    code, _ = guard.classify(command, cwd=_repo(tmp_path))
    assert code == guard.ALLOW, f"{command!r} names what it stages"


def test_amend_is_not_read_as_all() -> None:
    """`--amend` contains an `a` and must not match the `-a` bundle pattern."""
    assert not guard.COMMIT_ALL.match("--amend")
    assert guard.COMMIT_ALL.match("-am") and guard.COMMIT_ALL.match("-va")
    assert not guard.COMMIT_ALL.match("-m")


def test_committing_on_main_is_blocked(tmp_path: Path) -> None:
    """The file that landed on main did so because HEAD had been moved there."""
    code, message = guard.classify("git commit -m x", cwd=_repo(tmp_path, branch="main"))
    assert code == guard.BLOCK
    assert "main" in message and "pull request" in message


def test_committing_on_a_branch_is_allowed(tmp_path: Path) -> None:
    code, _ = guard.classify("git commit -m x", cwd=_repo(tmp_path, branch="work"))
    assert code == guard.ALLOW


def test_the_staged_set_is_printed_at_commit_time(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`git show --stat` afterwards is too late; that is how the loss was noticed."""
    guard.classify("git commit -m x", cwd=_repo(tmp_path, branch="work", staged=True))
    printed = capsys.readouterr().err
    assert "theirs.txt" in printed, "the commit has to name what it is about to include"
    assert "not yours" in printed


# --- asked when dirty, silent when clean ---


@pytest.mark.parametrize(
    "command",
    [
        "git reset --hard origin/main",
        "git reset",
        "git switch main -f",
        "git checkout main",
        "git checkout -- tracked.txt",
        "git restore tracked.txt",
        "git stash",
        "git clean -fd",
        "git branch -f other HEAD",
        "git branch -D other",
    ],
)
def test_a_destructive_command_asks_when_the_tree_is_dirty(command: str, tmp_path: Path) -> None:
    code, message = guard.classify(command, cwd=_repo(tmp_path, dirty=True, staged=True))
    assert code == guard.ALLOW, "asking is exit 0 with a reason, not a block"
    assert message, f"{command!r} must not pass silently over uncommitted work"
    assert "theirs.txt" in message, "the prompt has to list what would be lost"
    assert "worktree" in message, "and point at the arrangement that avoids the question"


@pytest.mark.parametrize(
    "command",
    ["git reset --hard origin/main", "git switch main", "git stash", "git clean -fd", "git branch -D other"],
)
def test_the_same_command_passes_silently_on_a_clean_tree(command: str, tmp_path: Path) -> None:
    code, message = guard.classify(command, cwd=_repo(tmp_path))
    assert (code, message) == (guard.ALLOW, ""), "nothing is at risk, so there is nothing to ask about"


def test_a_read_only_stash_or_branch_is_not_treated_as_destructive(tmp_path: Path) -> None:
    repo = _repo(tmp_path, dirty=True, staged=True)
    for command in ("git stash list", "git stash show", "git branch", "git branch -a", "git branch new"):
        code, message = guard.classify(command, cwd=repo)
        assert (code, message) == (guard.ALLOW, ""), f"{command!r} discards nothing"


def test_clean_without_force_is_not_asked_about(tmp_path: Path) -> None:
    """git refuses it anyway, so a prompt would be friction with no finding behind it."""
    code, message = guard.classify("git clean -n", cwd=_repo(tmp_path, dirty=True))
    assert (code, message) == (guard.ALLOW, "")


def test_git_being_unanswerable_is_not_read_as_clean(tmp_path: Path) -> None:
    """An empty result from a failed git call is what made a sibling guard inert.

    A directory that is not a repository stands in for git failing: the question
    cannot be answered, so the verdict has to be "ask", never "allow".
    """
    code, message = guard.classify("git reset --hard", cwd=tmp_path)
    assert code == guard.ALLOW
    assert message and "not a clean tree" in message


# --- command parsing ---


def test_a_git_command_inside_another_command_is_judged_on_the_git_call(tmp_path: Path) -> None:
    repo = _repo(tmp_path, dirty=True, staged=True)
    code, message = guard.classify("cd /tmp && git reset --hard", cwd=repo)
    assert message, "a chained command still runs the reset"
    code, _ = guard.classify("grep -rn 'git reset --hard' docs/", cwd=repo)
    assert code == guard.ALLOW


def test_a_non_git_command_is_ignored(tmp_path: Path) -> None:
    repo = _repo(tmp_path, dirty=True)
    for command in ("ls -la", "python3 -m pytest", "echo hello"):
        assert guard.classify(command, cwd=repo) == (guard.ALLOW, "")


def test_an_unparseable_command_does_not_block(tmp_path: Path) -> None:
    """Failing closed would deny every command with an unbalanced quote in it."""
    assert guard.classify('git commit -m "unbalanced', cwd=_repo(tmp_path)) == (guard.ALLOW, "")


# --- the hook contract ---


def test_the_hook_exits_two_on_a_blocked_command() -> None:
    proc = subprocess.run(
        [sys.executable, str(GUARD)],
        cwd=ROOT,
        input=json.dumps({"tool_input": {"command": "git add -A"}}),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == guard.BLOCK
    assert "BLOCKED" in proc.stderr


def test_the_hook_emits_an_ask_payload_rather_than_blocking(tmp_path: Path) -> None:
    """Verified against this repository's own tree, whatever state it is in."""
    state = guard.dirty()
    proc = subprocess.run(
        [sys.executable, str(GUARD)],
        cwd=ROOT,
        input=json.dumps({"tool_input": {"command": "git reset --hard origin/main"}}),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == guard.ALLOW
    if state and (state[0] or state[1]):
        payload = json.loads(proc.stdout)
        assert payload["hookSpecificOutput"]["permissionDecision"] == "ask"


def test_malformed_input_does_not_break_the_tool_call() -> None:
    for body in ("", "not json", "[]", '{"tool_input": null}'):
        proc = subprocess.run(
            [sys.executable, str(GUARD)],
            cwd=ROOT,
            input=body,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert proc.returncode == guard.ALLOW, f"{body!r} must not deny the command"


def test_the_selftest_agrees_with_this_file() -> None:
    proc = subprocess.run(
        [sys.executable, str(GUARD), "--selftest"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_the_guard_is_tracked_in_the_repository() -> None:
    """A guard living only in `.kiro/` does not exist for a fresh clone or for CI."""
    proc = subprocess.run(
        ["git", "ls-files", "scripts/guard_shared_checkout.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.stdout.strip() == "scripts/guard_shared_checkout.py"


def test_the_hook_runs_the_tracked_copy() -> None:
    hook = ROOT / ".kiro" / "hooks" / "shared-checkout-guard.json"
    if not hook.is_file():
        pytest.skip(".kiro/ is not present in this checkout (gitignored by design)")
    config = json.loads(hook.read_text(encoding="utf-8"))
    commands = [h.get("action", {}).get("command", "") for h in config.get("hooks", [])]
    joined = " ".join(commands)
    assert "scripts/guard_shared_checkout.py" in joined
    assert "$HOME" not in joined and "~/.kiro" not in joined
    assert [h.get("trigger") for h in config.get("hooks", [])] == ["PreToolUse"]
    assert "|| exit 0" in joined, "a guard that cannot find itself must not deny every command"
