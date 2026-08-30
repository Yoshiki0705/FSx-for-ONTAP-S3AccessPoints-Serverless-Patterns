"""Tests for the second audit source: the per-user portal activity ledger.

The two sources answer different questions, so what is asserted here is mostly that the
routing is on the caller's `source` and that a caller who does not pass it stays on the
CloudTrail path. Beyond that, the filters have to mean the same thing in both sections --
the audit tab applies one set of controls to both, and a date range that excluded its own
end date in one section and not the other would read as missing rows rather than as a
different comparison.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

LEDGER_TABLE = "portal-activity-ledger"


MODULE_NAME = "audit_log_index"
MODULE_PATH = Path(__file__).resolve().parent.parent / "index.py"


def load_index(ledger_table: str = LEDGER_TABLE) -> ModuleType:
    """Import the handler with the ledger table configured.

    Executes the file rather than calling `importlib.reload`. The module is registered
    under a name of its own -- fourteen functions here have an `index.py`, so `index`
    belongs to none of them -- and `reload` re-resolves the spec by name through the
    finders, which cannot see a name that exists only in `sys.modules`.

    Args:
        ledger_table: Value for `URL_AUDIT_TABLE_NAME`, read at import time.

    Returns:
        A freshly executed module, rebound in `sys.modules` so that a string patch target
        of `"audit_log_index.…"` refers to it.
    """
    with patch.dict(os.environ, {"URL_AUDIT_TABLE_NAME": ledger_table}, clear=False):
        spec = importlib.util.spec_from_file_location(MODULE_NAME, MODULE_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[MODULE_NAME] = module
        spec.loader.exec_module(module)
        return module


def rows(*items: dict) -> MagicMock:
    """A DynamoDB table stand-in returning `items` from a single scan page."""
    table = MagicMock()
    table.scan.return_value = {"Items": list(items)}
    return table


def row(**overrides) -> dict:
    """One ledger row, with the fields the handler reads."""
    item = {
        "id": "row-1",
        "action": "DELETE",
        "file_key": "teams/a/report.pdf",
        "generated_by": "alice",
        "access_point": "team-a-alias",
        "generated_at": "2026-08-20T10:00:00+00:00",
        "groups": ["contributor", "internal"],
    }
    item.update(overrides)
    return item


def query(index, table, **event) -> dict:
    """Invoke the handler against a stand-in table."""
    with patch.object(index.boto3, "resource") as resource:
        resource.return_value.Table.return_value = table
        return index.handler({"source": "PORTAL", **event}, None)


class TestRouting:
    def test_no_source_stays_on_cloudtrail(self):
        """A caller that does not pass `source` keeps the behaviour it had."""
        index = load_index()
        with patch.object(index.boto3, "client") as client:
            client.return_value.start_query_execution.return_value = {"QueryExecutionId": "q-1"}
            client.return_value.get_query_execution.return_value = {
                "QueryExecution": {"Status": {"State": "FAILED", "StateChangeReason": "x"}}
            }
            index.handler({}, None)
        # Athena was reached, which is the point: the ledger path never started.
        assert client.called

    @pytest.mark.parametrize("source", ["PORTAL", "portal", "Portal"])
    def test_the_source_is_matched_case_insensitively(self, source):
        index = load_index()
        result = query(index, rows(row()), source=source)
        assert result["error"] is None
        assert len(result["events"]) == 1

    def test_an_unconfigured_ledger_says_so_instead_of_returning_nothing(self):
        """Empty results and "there is no ledger" are different answers.

        The table went uncreated for the whole life of the previous inline writer, and the
        symptom was an empty trail that read as "nobody did anything".
        """
        index = load_index(ledger_table="")
        result = index.handler({"source": "PORTAL"}, None)
        assert result["events"] == []
        assert "not configured" in result["error"]


class TestRowShape:
    def test_the_cognito_user_is_what_this_source_adds(self):
        """CloudTrail attributes every portal read to one IAM role. This names the user."""
        index = load_index()
        event = query(index, rows(row()))["events"][0]
        assert event["userArn"] == "alice"
        assert event["fileKey"] == "teams/a/report.pdf"
        assert event["action"] == "DELETE"
        assert event["bucketName"] == "team-a-alias"

    def test_the_groups_held_at_the_time_are_surfaced(self):
        index = load_index()
        event = query(index, rows(row()))["events"][0]
        assert event["principalId"] == "contributor,internal"

    def test_no_source_ip_is_invented(self):
        """The request reached AppSync. Where it came from is CloudTrail's to report."""
        index = load_index()
        assert query(index, rows(row()))["events"][0]["sourceIp"] == ""

    def test_a_row_missing_optional_fields_does_not_break_the_page(self):
        index = load_index()
        event = query(index, rows({"id": "x", "generated_at": "2026-08-20T10:00:00+00:00"}))["events"][0]
        assert event["userArn"] == ""
        assert event["principalId"] == ""


class TestFilters:
    def test_the_key_prefix_filters(self):
        index = load_index()
        table = rows(row(), row(id="row-2", file_key="teams/b/other.pdf"))
        result = query(index, table, fileKeyPrefix="teams/a/")
        assert [e["fileKey"] for e in result["events"]] == ["teams/a/report.pdf"]

    def test_the_action_filters(self):
        index = load_index()
        table = rows(row(), row(id="row-2", action="DOWNLOAD"))
        result = query(index, table, eventType="DOWNLOAD")
        assert [e["action"] for e in result["events"]] == ["DOWNLOAD"]

    def test_all_means_every_action(self):
        index = load_index()
        table = rows(row(), row(id="row-2", action="DOWNLOAD"))
        assert len(query(index, table, eventType="ALL")["events"]) == 2

    def test_the_end_date_includes_the_day_it_names(self):
        """Compared on the date part.

        Against the full timestamp, an end date of 2026-08-20 would be less than
        "2026-08-20T10:00:00" and exclude everything that happened on the day the caller
        asked for -- which reads as missing rows, not as a different comparison.
        """
        index = load_index()
        result = query(index, rows(row()), startDate="2026-08-20", endDate="2026-08-20")
        assert len(result["events"]) == 1

    def test_a_row_outside_the_range_is_dropped(self):
        index = load_index()
        table = rows(row(), row(id="row-2", generated_at="2026-07-01T10:00:00+00:00"))
        result = query(index, table, startDate="2026-08-01", endDate="2026-08-31")
        assert len(result["events"]) == 1

    def test_newest_first(self):
        index = load_index()
        table = rows(
            row(generated_at="2026-08-01T10:00:00+00:00"),
            row(id="row-2", generated_at="2026-08-20T10:00:00+00:00"),
        )
        stamps = [e["timestamp"] for e in query(index, table)["events"]]
        assert stamps == sorted(stamps, reverse=True)

    def test_max_results_is_validated_the_same_way_as_the_athena_path(self):
        """One rule for the argument, not one per source."""
        index = load_index()
        result = query(index, rows(row()), maxResults="not-a-number")
        assert result["events"] == []
        assert "maxResults" in result["error"]

    def test_max_results_bounds_the_page(self):
        index = load_index()
        table = rows(*[row(id=f"row-{n}") for n in range(5)])
        assert len(query(index, table, maxResults=2)["events"]) == 2


class TestFailures:
    def test_a_read_failure_is_reported_rather_than_raised(self):
        index = load_index()
        table = MagicMock()
        table.scan.side_effect = index.ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "no"}}, "Scan"
        )
        result = query(index, table)
        assert result["events"] == []
        assert result["error"]

    def test_pagination_stops_without_walking_the_whole_table(self):
        """A filter that matches nothing must not turn into an unbounded scan.

        The pages are a finite `side_effect` rather than a repeating `return_value` on
        purpose: with the bound removed, a repeating page would make this hang instead of
        fail, and a test that hangs gets deleted rather than read.
        """
        index = load_index()
        table = MagicMock()
        table.scan.side_effect = [
            {
                "Items": [row(id=f"row-{page}-{n}") for n in range(50)],
                "LastEvaluatedKey": {"id": f"page-{page}"},
            }
            for page in range(3)
        ]
        query(index, table, maxResults=1)
        # Bounded by rows read (maxResults * 20), so one page of 50 already suffices.
        assert table.scan.call_count == 1
