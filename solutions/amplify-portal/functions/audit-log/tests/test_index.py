"""Tests for the audit-log Lambda.

The emphasis is on query construction. Every value the caller controls used to
be interpolated straight into the Athena SQL with an f-string, so a request
could close the quote and append its own SQL. Athena would run it under the
Lambda's role, which can read whatever the Glue catalog exposes.

These tests assert on the generated SQL rather than mocking it away, because
the vulnerability lived in the string, not in the call.
"""

from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

import pytest

# Values that terminate the string literal and continue the statement, plus the
# LIKE wildcards that silently widen a "prefix" filter.
INJECTION_ATTEMPTS = [
    "' OR '1'='1",
    "x' OR 1=1 --",
    "'; DROP TABLE cloudtrail_s3_events; --",
    "' UNION ALL SELECT * FROM secrets --",
    "a'--",
    "%",
    "_",
    "%' --",
    "\\",
    "a\nOR TRUE",
]


def _build(**event):
    from index import _build_query

    return _build_query(event)


class TestKeyPrefixIsNotInjectable:
    @pytest.mark.parametrize("payload", INJECTION_ATTEMPTS)
    def test_rejected_or_neutralised(self, payload):
        from index import AuditQueryError, _build_query

        try:
            sql, _ = _build_query({"fileKeyPrefix": payload})
        except AuditQueryError:
            return  # Rejected outright, which is the preferred outcome.

        # If it was accepted it must be inert: no unescaped quote can survive,
        # so the statement still has balanced literals and no appended clause.
        assert sql.count("'") % 2 == 0, sql
        for keyword in ("DROP", "UNION", "--", ";"):
            assert keyword not in sql.upper().replace("S3.AMAZONAWS.COM", ""), sql

    def test_quote_is_doubled_not_dropped(self):
        """A legitimate value containing a quote must survive as data."""
        from index import _sql_literal

        assert _sql_literal("O'Brien") == "'O''Brien'"

    def test_wildcards_are_escaped_so_a_prefix_is_literal(self):
        from index import _like_operand

        assert _like_operand("100%_raw") == "100\\%\\_raw"

    def test_backslash_is_escaped(self):
        from index import _like_operand

        assert _like_operand("a\\b") == "a\\\\b"

    def test_accepted_prefix_appears_with_escape_clause(self):
        sql, _ = _build(fileKeyPrefix="finance/2026")

        assert "requestparameters LIKE '%finance/2026%' ESCAPE '\\'" in sql


class TestTimestampValidation:
    @pytest.mark.parametrize(
        "value",
        ["2026-08-01", "2026-08-01T00:00:00", "2026-08-01 12:30", "2026-08-01T12:30:00Z"],
    )
    def test_accepts_expected_shapes(self, value):
        sql, _ = _build(startDate=value)

        assert f"eventtime >= '{value}'" in sql

    @pytest.mark.parametrize(
        "value",
        ["2026-08-01' OR '1'='1", "yesterday", "'; DROP TABLE t; --", "2026/08/01", 20260801],
    )
    def test_rejects_anything_else(self, value):
        from index import AuditQueryError

        with pytest.raises(AuditQueryError):
            _build(startDate=value)

    def test_end_date_is_validated_too(self):
        from index import AuditQueryError

        with pytest.raises(AuditQueryError):
            _build(endDate="' OR 1=1 --")


class TestEventType:
    @pytest.mark.parametrize("event_type", ["ALL", "READ", "WRITE", "LOCK"])
    def test_known_types_produce_an_in_list(self, event_type):
        sql, _ = _build(eventType=event_type)

        assert "eventname IN (" in sql
        assert "eventsource = 's3.amazonaws.com'" in sql

    def test_unknown_type_is_refused(self):
        """Previously an unknown type produced a query with an empty WHERE."""
        from index import AuditQueryError

        with pytest.raises(AuditQueryError):
            _build(eventType="EVERYTHING")

    def test_read_and_write_select_different_events(self):
        read_sql, _ = _build(eventType="READ")
        write_sql, _ = _build(eventType="WRITE")

        assert "'GetObject'" in read_sql and "'PutObject'" not in read_sql
        assert "'PutObject'" in write_sql and "'GetObject'" not in write_sql


class TestMaxResults:
    def test_defaults_to_50(self):
        _, max_results = _build()

        assert max_results == 50

    def test_capped_at_200(self):
        sql, max_results = _build(maxResults=100000)

        assert max_results == 200
        assert "LIMIT 200" in sql

    @pytest.mark.parametrize("value", ["abc", None, True, [], {}])
    def test_non_numeric_is_refused_or_defaulted(self, value):
        """A string used to raise an unhandled TypeError from min()."""
        from index import AuditQueryError

        if value is None:
            _, max_results = _build(maxResults=value)
            assert max_results == 50
            return
        with pytest.raises(AuditQueryError):
            _build(maxResults=value)

    @pytest.mark.parametrize("value", [0, -1, -200])
    def test_non_positive_is_refused(self, value):
        """A negative value used to produce `LIMIT -1`."""
        from index import AuditQueryError

        with pytest.raises(AuditQueryError):
            _build(maxResults=value)

    def test_limit_is_always_an_integer_literal(self):
        sql, _ = _build(maxResults="25")

        assert re.search(r"LIMIT 25\s*$", sql.strip()) is not None


class TestIdentifierValidation:
    def test_bad_table_name_is_refused(self):
        from index import AuditQueryError

        with patch("index.ATHENA_TABLE", 'events" UNION SELECT 1 --'):
            with pytest.raises(AuditQueryError):
                _build()


class TestHandlerContract:
    def test_not_configured_returns_a_clear_error(self):
        from index import handler

        with patch("index.ATHENA_OUTPUT", ""):
            result = handler({}, None)

        assert result["events"] == []
        assert "not configured" in result["error"]

    def test_invalid_input_does_not_reach_athena(self):
        from index import handler

        with patch("index.boto3") as mock_boto3:
            result = handler({"startDate": "' OR 1=1 --"}, None)

        assert mock_boto3.client.call_count == 0
        assert result["events"] == []
        assert "startDate" in result["error"]

    def test_successful_query_maps_rows(self):
        from index import handler

        athena = MagicMock()
        athena.start_query_execution.return_value = {"QueryExecutionId": "q-1"}
        athena.get_query_execution.return_value = {"QueryExecution": {"Status": {"State": "SUCCEEDED"}}}
        athena.get_query_results.return_value = {
            "ResultSet": {
                "Rows": [
                    {
                        "Data": [
                            {"VarCharValue": "eventtime"},
                            {"VarCharValue": "eventname"},
                            {"VarCharValue": "user_arn"},
                            {"VarCharValue": "file_key"},
                        ]
                    },
                    {
                        "Data": [
                            {"VarCharValue": "2026-08-01T10:00:00Z"},
                            {"VarCharValue": "GetObject"},
                            {"VarCharValue": "arn:aws:sts::123456789012:assumed-role/r/u"},
                            {"VarCharValue": "finance/report.xlsx"},
                        ]
                    },
                ]
            }
        }

        with patch("index.boto3") as mock_boto3:
            mock_boto3.client.return_value = athena
            result = handler({"eventType": "READ", "fileKeyPrefix": "finance/"}, None)

        assert result["error"] is None
        assert len(result["events"]) == 1
        assert result["events"][0]["action"] == "GetObject"
        assert result["events"][0]["fileKey"] == "finance/report.xlsx"

    def test_failed_query_reports_the_reason(self):
        from index import handler

        athena = MagicMock()
        athena.start_query_execution.return_value = {"QueryExecutionId": "q-2"}
        athena.get_query_execution.return_value = {
            "QueryExecution": {"Status": {"State": "FAILED", "StateChangeReason": "TABLE_NOT_FOUND"}}
        }

        with patch("index.boto3") as mock_boto3:
            mock_boto3.client.return_value = athena
            result = handler({}, None)

        assert result["events"] == []
        assert "TABLE_NOT_FOUND" in result["error"]

    def test_the_query_sent_to_athena_is_the_validated_one(self):
        """Guard against a future refactor that rebuilds the SQL inline."""
        from index import handler

        athena = MagicMock()
        athena.start_query_execution.return_value = {"QueryExecutionId": "q-3"}
        athena.get_query_execution.return_value = {"QueryExecution": {"Status": {"State": "SUCCEEDED"}}}
        athena.get_query_results.return_value = {"ResultSet": {"Rows": []}}

        with patch("index.boto3") as mock_boto3:
            mock_boto3.client.return_value = athena
            handler({"fileKeyPrefix": "hr/", "maxResults": 10}, None)

        sent = athena.start_query_execution.call_args.kwargs["QueryString"]
        assert "ESCAPE '\\'" in sent
        assert "LIMIT 10" in sent
        assert sent.count("'") % 2 == 0
