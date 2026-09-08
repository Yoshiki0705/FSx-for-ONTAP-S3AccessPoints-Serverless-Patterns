#!/usr/bin/env python3
"""Corpus and tests for the unobserved-workflow merge guard.

## Why the corpus lives here

`scripts/guard_unobserved_workflow_merge.py --selftest` imports `ASK_CASES` and
`ALLOW_CASES` from this module, so there is one list of cases rather than a pytest list and
a separate hand-run list that disagree. A sibling guard in this repository was ported
precisely because those two drifted: the executing copy allowed 10 of the 26 cases the
tracked copy documented, and nothing compared them.

## Two outcomes, not three

This guard never blocks. Dispatching a workflow needs the branch pushed, so the useful
order -- push, dispatch, read the run, merge -- is a sequence a human drives, and there are
real reasons to merge without it. A block would be wrong often enough to get switched off,
and a guard that is switched off protects nothing.

## What the cases have to span

The failure that produced this guard was a break test that proved a detector fires on **one
member of a family** and said nothing about the rest. So the trigger-parsing cases below
cover every `on:` shape in this repository plus the ones that would be misread: the inline
list, the two-space mapping, a nested `branches:` under `push:`, and a file whose `on:`
block cannot be found at all. The last is the one that decides between "ask on every merge"
and "stay quiet", and getting it wrong in the noisy direction is how the prompt becomes
something people wave through.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load() -> object:
    spec = importlib.util.spec_from_file_location(
        "guard_unobserved_workflow_merge", ROOT / "scripts" / "guard_unobserved_workflow_merge.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load()


def _repo(tmp: Path, workflows: dict[str, str], baseline: dict[str, str] | None = None) -> Path:
    """A git repository whose branch differs from origin/main by the given workflows.

    Args:
        tmp: Directory to create the repository in.
        workflows: Workflow files added on the branch.
        baseline: Workflow files present on `origin/main` already, so the branch does not
            touch them.
    """
    (tmp / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    run = lambda *a: subprocess.run(a, cwd=tmp, capture_output=True, check=True)  # noqa: E731
    run("git", "init", "-q", "-b", "main")
    run("git", "config", "user.email", "t@example.com")
    run("git", "config", "user.name", "t")
    (tmp / "seed.txt").write_text("seed\n", encoding="utf-8")
    for name, body in (baseline or {}).items():
        (tmp / ".github" / "workflows" / name).write_text(body, encoding="utf-8")
    run("git", "add", "-A")
    run("git", "commit", "-qm", "seed")
    run("git", "branch", "-f", "origin/main", "main")  # a local ref named like the remote
    run("git", "checkout", "-qb", "topic")
    for name, body in workflows.items():
        (tmp / ".github" / "workflows" / name).write_text(body, encoding="utf-8")
    # Always something to commit: the "touches no workflow" case is a real corpus entry, and
    # `git commit` refuses an empty one, so the branch would have no diff for a different
    # reason than the one under test.
    (tmp / "unrelated.md").write_text("change\n", encoding="utf-8")
    run("git", "add", "-A")
    run("git", "commit", "-qm", "branch work")
    return tmp


SCHEDULED = "name: S\non:\n  schedule:\n    - cron: '0 4 * * 1'\n  workflow_dispatch:\njobs: {}\n"
ON_PR = "name: P\non:\n  pull_request:\n  push:\n    branches: [main]\njobs: {}\n"


# --- the corpus the selftest shares. (command, root_factory, expected) ---

ASK_CASES: list[tuple[str, object, str]] = [
    ("gh pr merge 389 --squash --delete-branch", lambda: corpus_root("ask"), "ask"),
    ("gh pr merge --admin 12", lambda: corpus_root("ask"), "ask"),
    ("cd /tmp && gh pr merge 3 --merge", lambda: corpus_root("ask"), "ask"),
]

ALLOW_CASES: list[tuple[str, object, str]] = [
    # Not a merge.
    ("gh pr create --title x --body y", lambda: corpus_root("ask"), "allow"),
    ("gh pr view 389", lambda: corpus_root("ask"), "allow"),
    ("git merge main", lambda: corpus_root("ask"), "allow"),
    ("make drift", lambda: corpus_root("ask"), "allow"),
    # A merge that touches only a workflow every pull request already ran.
    ("gh pr merge 1 --squash", lambda: corpus_root("observed"), "allow"),
    # A merge touching no workflow at all.
    ("gh pr merge 1 --squash", lambda: corpus_root("none"), "allow"),
]

_LAYOUTS: dict[str, dict[str, str]] = {
    "ask": {"repo-name-redirects.yml": SCHEDULED},
    "observed": {"validators.yml": ON_PR},
    "none": {},
}

# An unobserved workflow that the branch does NOT touch. git working -> allow; git failing ->
# every unobserved workflow -> ask. The only layout where the two are distinguishable.
_BASELINE_LAYOUTS: dict[str, dict[str, str]] = {
    "untouched": {"repo-name-redirects.yml": SCHEDULED},
}
_CACHE: dict[str, Path] = {}


def corpus_root(kind: str) -> Path:
    """Build a scratch repository for one corpus case, once per process.

    Built here rather than in a pytest fixture because `--selftest` imports the case lists
    without pytest running: a fixture-populated global is `NameError` there, so the selftest
    would have failed on its own corpus while the pytest run passed. That is the same defect
    the shared corpus exists to prevent, one level up.
    """
    if kind not in _CACHE:
        base = Path(tempfile.mkdtemp(prefix=f"guard-corpus-{kind}-"))
        _CACHE[kind] = _repo(base / kind, _LAYOUTS.get(kind, {}), _BASELINE_LAYOUTS.get(kind))
    return _CACHE[kind]


# --- trigger parsing: every shape, including the ones that would be misread ---


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (SCHEDULED, {"schedule", "workflow_dispatch"}),
        (ON_PR, {"pull_request", "push"}),
        ("name: x\non: [push, pull_request]\njobs: {}\n", {"push", "pull_request"}),
        ("name: x\non: push\njobs: {}\n", {"push"}),
        ("name: x\non:\n  workflow_dispatch:\njobs: {}\n", {"workflow_dispatch"}),
    ],
)
def test_triggers_are_read_from_every_shape_in_use(body: str, expected: set[str]) -> None:
    assert guard.triggers(body) == expected


def test_a_trigger_option_is_not_read_as_a_trigger() -> None:
    """`push:\\n  branches:` must yield `push`, not `push` and `branches`."""
    assert guard.triggers(ON_PR) == {"pull_request", "push"}


def test_an_unreadable_on_block_yields_nothing() -> None:
    assert guard.triggers("name: x\njobs: {}\n") == set()


def test_a_workflow_with_no_readable_triggers_is_not_called_unobserved(tmp_path: Path) -> None:
    """The noisy direction is the dangerous one.

    Treating a parse failure as unobserved makes the guard ask on every merge, and a prompt
    that always fires is one people learn to dismiss without reading.
    """
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "broken.yml").write_text("nonsense\n", encoding="utf-8")
    assert guard.unobserved_workflows(tmp_path) == set()


@pytest.mark.parametrize("trigger", ["pull_request", "pull_request_target", "push", "merge_group"])
def test_anything_a_pull_request_runs_is_observed(tmp_path: Path, trigger: str) -> None:
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "w.yml").write_text(
        f"name: x\non:\n  {trigger}:\njobs: {{}}\n", encoding="utf-8"
    )
    assert guard.unobserved_workflows(tmp_path) == set()


def test_a_schedule_only_workflow_is_unobserved(tmp_path: Path) -> None:
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "w.yml").write_text(SCHEDULED, encoding="utf-8")
    assert guard.unobserved_workflows(tmp_path) == {"w.yml"}


# --- the real repository, which is what the guard actually runs against ---


def test_the_four_unobserved_workflows_here_are_the_expected_ones() -> None:
    """Pinned as a set. A new schedule-only workflow should show up as a test failure first.

    Measured 2026-09-07. If this list grows, the guard's scope grew with it, which is worth
    noticing deliberately rather than discovering when the prompt fires.
    """
    assert guard.unobserved_workflows(ROOT) == {
        "bedrock-default-validation.yml",
        "e2e-portal.yml",
        "published-articles-check.yml",
        "repo-name-redirects.yml",
    }


def test_every_other_workflow_here_runs_on_a_pull_request() -> None:
    """Written as a property, not a count.

    The first version asserted a number, and the number was wrong: it came from counting
    `*.yml` while the guard scans `*.y*ml`, so `lint.yaml` and `test.yaml` were outside the
    figure but inside the scan. A property cannot drift out of step with the scan it
    describes, and it keeps saying something when a workflow is added.
    """
    unobserved = guard.unobserved_workflows(ROOT)
    for path in (ROOT / ".github" / "workflows").glob("*.y*ml"):
        if path.name in unobserved:
            continue
        found = guard.triggers(path.read_text(encoding="utf-8"))
        assert found & set(guard.OBSERVED_TRIGGERS), f"{path.name}: {sorted(found)}"


# --- decisions ---


@pytest.mark.parametrize(("command", "root", "expected"), ASK_CASES)
def test_ask_cases(command: str, root: object, expected: str) -> None:
    outcome, reason = guard.decide(command, root() if callable(root) else root)
    assert outcome == expected
    assert "gh workflow run" in reason


@pytest.mark.parametrize(("command", "root", "expected"), ALLOW_CASES)
def test_allow_cases(command: str, root: object, expected: str) -> None:
    outcome, reason = guard.decide(command, root() if callable(root) else root)
    assert outcome == expected
    assert reason == ""


def test_a_broken_git_comparison_asks_rather_than_staying_silent(tmp_path: Path) -> None:
    """No origin/main to diff against: the guard must not conclude "nothing changed"."""
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "w.yml").write_text(SCHEDULED, encoding="utf-8")
    outcome, _reason = guard.decide("gh pr merge 1 --squash", tmp_path)
    assert outcome == "ask"


def test_the_reason_names_the_workflow_and_the_command_to_run() -> None:
    outcome, reason = guard.decide("gh pr merge 1 --squash", corpus_root("ask"))
    assert outcome == "ask"
    assert "repo-name-redirects.yml" in reason
    assert "gh workflow run repo-name-redirects.yml --ref" in reason


# --- the hook contract, and the selftest that must agree with this file ---


def _guard_in(root: Path) -> Path:
    """Copy the guard into a corpus repository so its ROOT resolves there.

    The guard derives ROOT from its own location, deliberately -- a hook has no reliable cwd.
    Copying it is how the end-to-end path gets exercised against a controlled tree without
    adding a test-only override to the guard itself.
    """
    target = root / "scripts"
    target.mkdir(exist_ok=True)
    destination = target / "guard_unobserved_workflow_merge.py"
    destination.write_text(
        (ROOT / "scripts" / "guard_unobserved_workflow_merge.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return destination


def test_the_hook_emits_an_ask_payload_and_exits_zero() -> None:
    """The whole path: stdin event, real git diff, ask payload on stdout, exit 0."""
    guard_copy = _guard_in(corpus_root("ask"))
    result = subprocess.run(
        [sys.executable, str(guard_copy)],
        input='{"tool_input":{"command":"gh pr merge 1 --squash"}}',
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert '"permissionDecision": "ask"' in result.stdout
    assert "repo-name-redirects.yml" in result.stdout


def test_the_hook_is_silent_when_the_branch_touches_no_unobserved_workflow() -> None:
    guard_copy = _guard_in(corpus_root("observed"))
    result = subprocess.run(
        [sys.executable, str(guard_copy)],
        input='{"tool_input":{"command":"gh pr merge 1 --squash"}}',
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_the_hook_is_silent_on_an_unrelated_command() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "guard_unobserved_workflow_merge.py")],
        input='{"tool_input":{"command":"ls -la"}}',
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_malformed_input_does_not_break_the_tool_call() -> None:
    for payload in ("not json", "{}", '{"tool_input":{}}', '{"tool_input":{"command":123}}'):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "guard_unobserved_workflow_merge.py")],
            input=payload,
            capture_output=True,
            text=True,
            cwd=ROOT,
            check=False,
        )
        assert result.returncode == 0, payload


def test_the_selftest_agrees_with_this_corpus() -> None:
    """The check that the two lists have not drifted, which is why they are one list."""
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "guard_unobserved_workflow_merge.py"),
            "--selftest",
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert f"{len(ASK_CASES) + len(ALLOW_CASES)} case(s) as documented" in result.stdout


# --- cwd independence, with a case that can tell the two apart ---


def test_the_verdict_does_not_depend_on_the_process_working_directory(tmp_path: Path) -> None:
    """A sibling repository shipped this guard's equivalent inert.

    Its `git diff` inherited whatever directory the hook process happened to start in, git
    failed there, and the empty result read as "the branch touches no workflow" -- so every
    merge passed in silence. It had been tested from inside the repository, which is the one
    place the bug cannot appear.

    The corpus here is the `untouched` one on purpose: it holds an unobserved workflow that the
    branch does not touch, so a working comparison answers `allow` while a broken one answers
    `ask` (this guard reports everything when git cannot answer). On any other corpus both
    answers coincide and the test would pass with `cwd=` deleted from the subprocess call.
    """
    root = corpus_root("untouched")
    guard_copy = _guard_in(root)
    for where in (tmp_path, Path.home(), Path("/")):
        result = subprocess.run(
            [sys.executable, str(guard_copy)],
            input='{"tool_input":{"command":"gh pr merge 1 --squash"}}',
            capture_output=True,
            text=True,
            cwd=where,
            check=False,
        )
        assert result.returncode == 0, where
        assert result.stdout.strip() == "", f"ran from {where}: {result.stdout}"


def test_the_untouched_corpus_really_would_flip_if_git_were_broken() -> None:
    """Proves the test above discriminates, rather than trusting that it does.

    Points the guard at a tree with no git repository at all: the comparison fails, and the
    verdict must become `ask` rather than staying `allow`. If this returned `allow`, the test
    above would be vacuous.
    """
    root = corpus_root("untouched")
    assert guard.decide("gh pr merge 1 --squash", root)[0] == "allow"

    import tempfile as _tempfile

    nogit = Path(_tempfile.mkdtemp(prefix="guard-nogit-"))
    (nogit / ".github" / "workflows").mkdir(parents=True)
    (nogit / ".github" / "workflows" / "w.yml").write_text(SCHEDULED, encoding="utf-8")
    assert guard.decide("gh pr merge 1 --squash", nogit)[0] == "ask"
