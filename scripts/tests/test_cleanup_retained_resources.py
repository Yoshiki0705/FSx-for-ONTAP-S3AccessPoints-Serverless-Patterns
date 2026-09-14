"""Tests for the retained-resource cleanup.

This script deletes things, so what is asserted here is mostly what it refuses to
do. Two guards carry the weight:

  - a prefix too short to identify one stack's leftovers is refused, because a name
    fragment matches live resources as readily as leftovers;
  - `--apply` is refused while a stack matching the prefix is still standing. This
    repository's own portal prefix matches six DynamoDB tables that are in use.

The third thing asserted is that the search range is wide enough. The manual sweep
this script replaced looked only at `/aws/lambda/<prefix>` in one region, and missed
an API Gateway access-log group retained for 365 days and a log group in us-east-1.
The range a detector covers is part of its result, so it is tested rather than
described.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cleanup_retained_resources as cleanup  # noqa: E402
from cleanup_retained_resources import (  # noqa: E402
    EXIT_FOUND_OR_FAILED,
    EXIT_OK,
    EXIT_USAGE,
    FINDERS,
    KINDS,
    NEVER_TOUCHED,
    REMOVERS,
    Leftover,
    collect,
    live_stacks,
    parse_args,
)


class FakeCfn:
    """CloudFormation's list_stacks paginator, with prepared summaries."""

    def __init__(self, summaries: list[dict[str, str]]) -> None:
        self.summaries = summaries

    def get_paginator(self, name: str) -> Any:
        summaries = self.summaries

        class Paginator:
            def paginate(self) -> list[dict[str, Any]]:
                # Two pages, so a single-page read would fail this.
                half = len(summaries) // 2
                return [
                    {"StackSummaries": summaries[:half]},
                    {"StackSummaries": summaries[half:]},
                ]

        return Paginator()


def use_cfn(monkeypatch: pytest.MonkeyPatch, summaries: list[dict[str, str]]) -> None:
    """Point the module's client factory at a prepared CloudFormation."""
    monkeypatch.setattr(cleanup, "_client", lambda service, region: FakeCfn(summaries))


# --- The prefix guard -----------------------------------------------------------


@pytest.mark.parametrize("prefix", ["a", "ab", "abc", "  ab  ", "_a_"])
def test_short_prefix_is_refused(prefix: str, capsys: pytest.CaptureFixture) -> None:
    """Refused rather than confirmed: the confirmation would be answered by whoever
    typed the prefix."""
    assert cleanup.main(["--stack-prefix", prefix]) == EXIT_USAGE
    assert "too short" in capsys.readouterr().out


@pytest.mark.parametrize("prefix", ["abcd", "fsxn-portal-nx", "uc12"])
def test_prefix_of_four_or_more_is_accepted(prefix: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """The guard is on length, so a legitimate short stack name still works."""
    monkeypatch.setattr(cleanup, "collect", lambda p, r, k: cleanup.Report())
    assert cleanup.main(["--stack-prefix", prefix]) == EXIT_OK


def test_prefix_is_required() -> None:
    """No default. The script must not be able to sweep an account."""
    with pytest.raises(SystemExit):
        parse_args([])


# --- The --apply guard ----------------------------------------------------------


def test_apply_is_refused_while_a_matching_stack_stands(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """The guard that matters. Checked against CloudFormation, not asked."""
    use_cfn(
        monkeypatch,
        [
            {"StackName": "fsxn-portal-nx-infra-sandbox", "StackStatus": "CREATE_COMPLETE"},
            {"StackName": "fsxn-portal-nx-data", "StackStatus": "UPDATE_COMPLETE"},
        ],
    )
    monkeypatch.setattr(cleanup, "collect", lambda p, r, k: cleanup.Report())
    assert cleanup.main(["--stack-prefix", "fsxn-portal-nx", "--apply"]) == EXIT_USAGE
    out = capsys.readouterr().out
    assert "refused" in out
    assert "fsxn-portal-nx-infra-sandbox" in out, "the blocking stack must be named"


def test_apply_proceeds_once_the_stacks_are_gone(monkeypatch: pytest.MonkeyPatch) -> None:
    """A DELETE_COMPLETE entry stays listable for 90 days and must not block."""
    use_cfn(
        monkeypatch,
        [
            {"StackName": "fsxn-portal-nx-infra-sandbox", "StackStatus": "DELETE_COMPLETE"},
            {"StackName": "fsxn-portal-nx-data", "StackStatus": "DELETE_COMPLETE"},
        ],
    )
    monkeypatch.setattr(cleanup, "collect", lambda p, r, k: cleanup.Report())
    assert cleanup.main(["--stack-prefix", "fsxn-portal-nx", "--apply"]) == EXIT_OK


def test_delete_in_progress_still_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    """A stack mid-deletion still owns its resources."""
    use_cfn(
        monkeypatch,
        [{"StackName": "fsxn-portal-nx-a", "StackStatus": "DELETE_IN_PROGRESS"}],
    )
    monkeypatch.setattr(cleanup, "collect", lambda p, r, k: cleanup.Report())
    assert cleanup.main(["--stack-prefix", "fsxn-portal-nx", "--apply"]) == EXIT_USAGE


def test_live_stacks_reads_every_page(monkeypatch: pytest.MonkeyPatch) -> None:
    """An account has more stacks than one page holds.

    A single-page read would report an empty result and let --apply through against
    a standing stack, which is the failure mode this guard exists to prevent.
    """
    summaries = [{"StackName": f"keepme-{i}", "StackStatus": "CREATE_COMPLETE"} for i in range(10)]
    use_cfn(monkeypatch, summaries)
    assert len(live_stacks("keepme-", None)) == 10


def test_live_stacks_ignores_other_prefixes(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unrelated standing stack must not block a legitimate cleanup."""
    use_cfn(
        monkeypatch,
        [
            {"StackName": "someone-elses-stack", "StackStatus": "CREATE_COMPLETE"},
            {"StackName": "fsxn-portal-nx-a", "StackStatus": "DELETE_COMPLETE"},
        ],
    )
    assert live_stacks("fsxn-portal-nx", None) == []


def test_report_only_run_does_not_consult_cloudformation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reporting changes nothing, so it must work without list_stacks permission.

    Someone diagnosing a teardown may have read access to the resources and not to
    CloudFormation; refusing to report would send them to the console instead.
    """

    def explode(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("live_stacks must not be called without --apply")

    monkeypatch.setattr(cleanup, "live_stacks", explode)
    monkeypatch.setattr(cleanup, "collect", lambda p, r, k: cleanup.Report())
    assert cleanup.main(["--stack-prefix", "fsxn-portal-nx"]) == EXIT_OK


# --- What is never touched ------------------------------------------------------


def test_never_touched_covers_the_irreversible_resources() -> None:
    """The exclusions are a value in the program, not an intent in a comment.

    A retention lock is not a leftover: it is behaving as configured, and its period
    cannot be shortened afterwards. So these are listed where the code can be read
    against them.
    """
    text = " ".join(NEVER_TOUCHED).lower()
    for subject in ("snaplock", "worm", "volume", "svm", "file system", "s3", "secret"):
        assert subject in text, f"{subject} is not named in NEVER_TOUCHED"


def test_no_finder_or_remover_handles_an_excluded_service() -> None:
    """The exclusions have to hold in the code, not only in the list.

    A `KINDS` entry naming one of them would make the list decorative, which is the
    failure mode of writing the intent down and not enforcing it.
    """
    for kind in KINDS:
        assert not any(word in kind for word in ("fsx", "volume", "svm", "snaplock", "s3", "secret")), kind
    assert set(FINDERS) == set(KINDS), "a kind without a finder reports nothing and looks clean"
    assert set(REMOVERS) == set(KINDS), "a kind without a remover would report and never remove"


# --- Search range ---------------------------------------------------------------


def test_log_group_search_covers_the_three_prefix_shapes() -> None:
    """The two misses that motivated the range.

    The manual sweep grepped `/aws/lambda/<prefix>`, so an API Gateway access-log
    group -- whose name does not start with `/aws/lambda/` -- stayed, retained for
    365 days. Asserted against the source because the shapes are what the API is
    called with, and a fake would be asserting the fake.
    """
    source = Path(cleanup.__file__).read_text(encoding="utf-8")
    assert "/aws/lambda/" in source
    assert '"/aws/' in source or "'/aws/" in source
    body = source.split("def find_log_groups", 1)[1].split("\ndef ", 1)[0]
    assert body.count("prefix") >= 3, "the three prefix shapes are what caught the retained groups"


def test_collect_reports_an_unreadable_service_without_hiding_the_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One service erroring must not turn the run into a clean report.

    Silence here would read as "nothing left behind", which is the same shape as the
    silent no-op that made an earlier gate untrustworthy.
    """

    def bad_finder(prefix: str, region: str | None) -> list[Leftover]:
        raise RuntimeError("AccessDenied")

    def good_finder(prefix: str, region: str | None) -> list[Leftover]:
        return [Leftover(kind="log-groups", name="/aws/lambda/x", reason="never expires")]

    monkeypatch.setitem(FINDERS, "dynamodb", bad_finder)
    monkeypatch.setitem(FINDERS, "log-groups", good_finder)
    report = collect("fsxn-portal-nx", None, ("log-groups", "dynamodb"))
    assert len(report.leftovers) == 1
    assert report.failed and "dynamodb" in report.failed[0][0]


def test_leftovers_found_exits_one_so_it_can_gate_a_teardown(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exit 1 while reporting means "found something", so a check can use it."""
    report = cleanup.Report()
    report.leftovers.append(Leftover(kind="log-groups", name="/aws/lambda/x", reason="never expires"))
    monkeypatch.setattr(cleanup, "collect", lambda p, r, k: report)
    assert cleanup.main(["--stack-prefix", "fsxn-portal-nx"]) == EXIT_FOUND_OR_FAILED


def test_report_says_why_it_survived_and_what_is_lost(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """A name alone does not let a reader decide whether to delete it."""
    report = cleanup.Report()
    report.leftovers.append(
        Leftover(
            kind="dynamodb",
            name="fsxn-portal-nx-Todo",
            reason="deletion protection enabled",
            detail="about 3 items",
        )
    )
    monkeypatch.setattr(cleanup, "collect", lambda p, r, k: report)
    cleanup.main(["--stack-prefix", "fsxn-portal-nx"])
    out = capsys.readouterr().out
    assert "deletion protection enabled" in out
    assert "about 3 items" in out


# --- Argument surface -----------------------------------------------------------


@pytest.mark.parametrize("kind", KINDS)
def test_only_accepts_each_kind(kind: str) -> None:
    """--only narrows the run; every declared kind is selectable."""
    assert parse_args(["--stack-prefix", "abcd", "--only", kind]).only == [kind]


def test_only_rejects_an_unknown_kind() -> None:
    """A typo must not silently widen the run to everything."""
    with pytest.raises(SystemExit):
        parse_args(["--stack-prefix", "abcd", "--only", "s3-buckets"])


def test_default_changes_nothing() -> None:
    """Report-only is the default; removal is opt-in."""
    assert parse_args(["--stack-prefix", "abcd"]).apply is False
