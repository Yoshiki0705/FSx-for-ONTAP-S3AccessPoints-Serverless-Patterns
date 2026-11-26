"""Every error name in a Retry or Catch of either state machine is accounted for.

Why this exists: the SDK integrations of Step Functions report an AWS error under a different name
than the API reference gives. The first real restore run found one (S3.S3Exception, not
S3.RestoreAlreadyInProgressException). Structure tests and moto could not find it, because neither
produces the integration's error names. The fixture lists the names seen in real runs and, with a
reason, the names that were never seen. A name in neither list fails the test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_definitions import ARCHIVE, RESTORE, _states, _tasks

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "observed_sdk_errors.json").read_text())
BUILT_IN = set(FIXTURE["built_in_matchers"])
OBSERVED = set(FIXTURE["observed"])
NOT_OBSERVED = set(FIXTURE["not_observed"])


def _names(definition):
    for state_name, state in _states(definition):
        for kind in ("Retry", "Catch"):
            for rule in state.get(kind, []):
                for error in rule["ErrorEquals"]:
                    yield state_name, kind, error


@pytest.mark.parametrize("definition", [ARCHIVE, RESTORE], ids=["archive", "restore"])
def test_every_error_name_is_built_in_observed_or_listed_as_not_observed(definition):
    unknown = {(s, k, e) for s, k, e in _names(definition) if e not in BUILT_IN | OBSERVED | NOT_OBSERVED}
    assert not unknown, f"error names with no record and no stated reason: {sorted(unknown)}"


def test_the_fixture_has_no_name_that_no_state_machine_uses():
    used = {e for d in (ARCHIVE, RESTORE) for _, _, e in _names(d)}
    assert (OBSERVED | NOT_OBSERVED) <= used, sorted((OBSERVED | NOT_OBSERVED) - used)


def test_no_name_is_both_observed_and_not_observed():
    assert not OBSERVED & NOT_OBSERVED


def test_every_observed_name_has_a_record_and_a_place():
    for name, entry in FIXTURE["observed"].items():
        assert entry["record"] and entry["where"], name


def test_every_not_observed_name_has_a_reason():
    assert all(reason.strip() for reason in FIXTURE["not_observed"].values())


@pytest.mark.parametrize("definition", [ARCHIVE, RESTORE], ids=["archive", "restore"])
def test_every_task_ends_its_catch_list_with_states_all(definition):
    """An error name nobody has seen yet must still reach a failure path, not stop the execution."""
    for name, state in _tasks(definition):
        catches = state["Catch"]
        assert "States.ALL" in catches[-1]["ErrorEquals"], f"{name}: the last Catch is not States.ALL"
        assert catches[-1]["ResultPath"], name


def test_each_observed_name_is_caught_by_name_where_it_was_seen():
    archive_plan = ARCHIVE["States"]["Plan"]["Catch"]
    assert any("InvalidInput" in c["ErrorEquals"] and c["Next"] == "FailInvalidInput" for c in archive_plan)
    restore_select = RESTORE["States"]["Select"]["Catch"]
    assert any("InvalidInput" in c["ErrorEquals"] and c["Next"] == "FailInvalidInput" for c in restore_select)
    request = RESTORE["States"]["RestoreFiles"]["ItemProcessor"]["States"]["RequestRestore"]["Catch"]
    assert any("S3.S3Exception" in c["ErrorEquals"] for c in request)


@pytest.mark.parametrize("definition", [ARCHIVE, RESTORE], ids=["archive", "restore"])
def test_every_task_has_a_timeout_and_the_wait_for_a_person_is_bounded(definition):
    for name, state in _tasks(definition):
        assert "TimeoutSeconds" in state or "TimeoutSecondsPath" in state, name
    if definition is ARCHIVE:
        wait = ARCHIVE["States"]["RequestApproval"]
        assert wait["TimeoutSecondsPath"] == "$.plan.config.approvalTimeoutSeconds"


def test_a_rejected_or_timed_out_approval_reaches_a_state_that_deletes_the_token():
    """Both a send-task-failure (Rejected) and the approval timeout are caught and end in summarize,
    which deletes the stored task token."""
    request = ARCHIVE["States"]["RequestApproval"]
    assert [c["Next"] for c in request["Catch"]] == ["SummarizeRejected"]
    assert ARCHIVE["States"]["ApprovalCheck"]["Default"] == "SummarizeRejected"
    assert ARCHIVE["States"]["SummarizeRejected"]["Resource"].startswith("${SummarizeFunctionArn")
