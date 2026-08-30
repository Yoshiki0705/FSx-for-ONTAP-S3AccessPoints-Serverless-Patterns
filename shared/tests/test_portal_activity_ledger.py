"""Tests for the per-user portal activity ledger.

The cases are chosen around the two properties that make the ledger worth having: it must
record who acted and what they held at the time, and it must never turn a gap in the
record into a failed request. A ledger that raises is a ledger that gets removed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from shared.portal_activity_ledger import (
    ACTION_DELETE,
    ACTION_DOWNLOAD,
    ACTION_SHARE_LINK,
    ACTION_UPLOAD_LINK,
    DEFAULT_RETENTION_DAYS,
    record_activity,
)


@pytest.fixture
def table():
    """A stand-in DynamoDB table, with the written item reachable as `.put_item`."""
    fake = MagicMock()
    with patch("shared.portal_activity_ledger.boto3.resource") as resource:
        resource.return_value.Table.return_value = fake
        yield fake


def written(table) -> dict:
    """The item passed to `put_item`."""
    assert table.put_item.called, "nothing was written"
    return table.put_item.call_args.kwargs["Item"]


def test_no_table_configured_writes_nothing(table):
    """An unconfigured ledger is silent rather than broken.

    The alternative would be every portal action failing on a deployment that has not
    set the table up.
    """
    assert (
        record_activity(
            table_name="",
            action=ACTION_DOWNLOAD,
            user_id="alice",
            key="teams/a/report.pdf",
            access_point="team-a-alias",
        )
        is False
    )
    assert not table.put_item.called


def test_a_row_names_the_actor_the_action_and_the_access_point(table):
    assert (
        record_activity(
            table_name="ledger",
            action=ACTION_DOWNLOAD,
            user_id="alice",
            key="teams/a/report.pdf",
            access_point="team-a-alias",
        )
        is True
    )
    item = written(table)
    assert item["action"] == ACTION_DOWNLOAD
    assert item["generated_by"] == "alice"
    assert item["file_key"] == "teams/a/report.pdf"
    # The ONTAP identity follows from the access point, so two rows naming the same key
    # are otherwise indistinguishable even when one carried far wider access.
    assert item["access_point"] == "team-a-alias"


def test_the_groups_held_at_the_time_are_recorded(table):
    """Membership changes. A row naming only the user cannot show what they held."""
    record_activity(
        table_name="ledger",
        action=ACTION_DELETE,
        user_id="alice",
        key="teams/a/old.pdf",
        access_point="team-a-alias",
        groups=["internal", "contributor"],
    )
    assert written(table)["groups"] == ["contributor", "internal"]


def test_groups_default_to_an_empty_list_not_a_missing_field(table):
    # A missing field and "held nothing" read the same in a query result. An explicit
    # empty list distinguishes "no groups" from "not recorded".
    record_activity(
        table_name="ledger",
        action=ACTION_DELETE,
        user_id="alice",
        key="k",
        access_point="ap",
    )
    assert written(table)["groups"] == []


def test_retention_outlives_the_thing_it_describes(table):
    """The previous inline version deleted each row a day after the URL expired.

    The record of who was given access then disappeared days after the access did, and an
    audit trail that outlives only its subject cannot answer a question asked later --
    which is when audit questions get asked.
    """
    record_activity(
        table_name="ledger",
        action=ACTION_SHARE_LINK,
        user_id="alice",
        key="k",
        access_point="ap",
        detail={"expires_in_seconds": 300},
    )
    item = written(table)
    lifetime = datetime.fromtimestamp(item["ttl"], tz=timezone.utc) - datetime.fromisoformat(item["generated_at"])
    # Rounded: `ttl` is an integer epoch, so it truncates the sub-second remainder and
    # the difference lands a fraction under the whole number of days.
    assert round(lifetime.total_seconds() / 86400) == DEFAULT_RETENTION_DAYS
    # The property that matters, stated separately from the exact number: the row must
    # outlive the URL whose creation it records.
    assert lifetime.total_seconds() > item["expires_in_seconds"]


def test_detail_fields_are_merged(table):
    record_activity(
        table_name="ledger",
        action=ACTION_UPLOAD_LINK,
        user_id="alice",
        key="uploads/x.bin",
        access_point="ap",
        detail={"expires_in_seconds": 3600, "destination_key": "uploads/x.bin"},
    )
    item = written(table)
    assert item["expires_in_seconds"] == 3600
    assert item["destination_key"] == "uploads/x.bin"


def test_a_failed_write_is_reported_and_not_raised(table):
    """The action being recorded has already succeeded.

    Raising here would convert a gap in the record into a failed request, and whoever
    hit it would remove the ledger rather than fix the table.
    """
    table.put_item.side_effect = RuntimeError("throughput exceeded")
    assert (
        record_activity(
            table_name="ledger",
            action=ACTION_DOWNLOAD,
            user_id="alice",
            key="k",
            access_point="ap",
        )
        is False
    )


def test_a_failed_write_is_logged_so_the_gap_is_visible(table, caplog):
    """A gap nobody can see is worse than one that shows up in the log."""
    table.put_item.side_effect = RuntimeError("throughput exceeded")
    with caplog.at_level("WARNING"):
        record_activity(
            table_name="ledger",
            action=ACTION_DOWNLOAD,
            user_id="alice",
            key="teams/a/report.pdf",
            access_point="ap",
        )
    assert "teams/a/report.pdf" in caplog.text
    assert "alice" in caplog.text


def test_each_row_is_distinct(table):
    """Two identical actions are two events, not one."""
    for _ in range(2):
        record_activity(
            table_name="ledger",
            action=ACTION_DOWNLOAD,
            user_id="alice",
            key="k",
            access_point="ap",
        )
    ids = {call.kwargs["Item"]["id"] for call in table.put_item.call_args_list}
    assert len(ids) == 2
