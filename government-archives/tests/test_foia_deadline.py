"""Unit tests for UC16 FOIA Deadline Reminder Lambda."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch


def test_is_business_day_weekday(foia_deadline_handler):
    # Monday = weekday 0
    assert foia_deadline_handler.is_business_day(date(2026, 5, 11)) is True  # Monday


def test_is_business_day_saturday(foia_deadline_handler):
    assert foia_deadline_handler.is_business_day(date(2026, 5, 9)) is False  # Saturday


def test_is_business_day_sunday(foia_deadline_handler):
    assert foia_deadline_handler.is_business_day(date(2026, 5, 10)) is False  # Sunday


def test_is_business_day_federal_holiday(foia_deadline_handler):
    # 2026-07-04 is a Saturday (Independence Day)
    assert foia_deadline_handler.is_business_day(date(2026, 7, 4)) is False
    # 2026-01-19 is MLK Day (Monday)
    assert foia_deadline_handler.is_business_day(date(2026, 1, 19)) is False


def test_add_business_days_basic(foia_deadline_handler):
    # From a Monday, add 5 business days → next Monday (skip weekend)
    start = date(2026, 5, 4)  # Monday
    result = foia_deadline_handler.add_business_days(start, 5)
    # 5 business days later = 2026-05-11 (next Monday)
    assert result == date(2026, 5, 11)


def test_add_business_days_skips_weekend(foia_deadline_handler):
    # From a Friday, add 1 business day → next Monday
    start = date(2026, 5, 1)  # Friday
    result = foia_deadline_handler.add_business_days(start, 1)
    assert result == date(2026, 5, 4)


def test_add_business_days_skips_holiday(foia_deadline_handler):
    # From 2026-01-16 (Friday), add 1 business day.
    # 2026-01-19 is MLK Day (Monday), so next business day is 2026-01-20 (Tuesday)
    start = date(2026, 1, 16)
    result = foia_deadline_handler.add_business_days(start, 1)
    assert result == date(2026, 1, 20)


def test_compute_foia_deadline_20_business_days(foia_deadline_handler):
    """FOIA deadline is 20 business days from receipt."""
    # Starting on Monday 2026-05-04, 20 business days later
    deadline = foia_deadline_handler.compute_foia_deadline("2026-05-04")
    deadline_date = date.fromisoformat(deadline)
    # Calculate manually: 20 business days skipping weekends
    # Approx 28 calendar days (4 weeks)
    delta = (deadline_date - date(2026, 5, 4)).days
    # Should be between 27-31 days (4 weekends × 2 = 8 non-business days, plus holidays)
    assert 27 <= delta <= 31


def test_days_until_deadline_in_future(foia_deadline_handler):
    today = date(2026, 5, 11)  # Monday
    deadline = "2026-05-18"  # Next Monday (5 business days)
    days = foia_deadline_handler.days_until_deadline(deadline, today=today)
    assert days == 5


def test_days_until_deadline_past(foia_deadline_handler):
    today = date(2026, 5, 11)
    deadline = "2026-05-01"  # In the past
    days = foia_deadline_handler.days_until_deadline(deadline, today=today)
    assert days == 0


def test_handler_checks_and_sends_reminders(
    foia_deadline_handler, lambda_context, monkeypatch
):
    monkeypatch.setenv("FOIA_TABLE", "test-foia-table")
    monkeypatch.setenv("SNS_TOPIC_ARN", "arn:aws:sns:us-east-1:123:foia")
    monkeypatch.setenv("REMINDER_DAYS_BEFORE", "3")

    today = date.today()
    # Two items: one overdue, one approaching
    mock_items = [
        {
            "request_id": "REQ-001",
            "status": "PENDING",
            "deadline": "2020-01-01",  # overdue
        },
        {
            "request_id": "REQ-002",
            "status": "PENDING",
            "deadline": (today.isoformat()),  # today (due)
        },
    ]

    mock_table = MagicMock()
    mock_table.scan.return_value = {"Items": mock_items}
    mock_resource = MagicMock()
    mock_resource.Table.return_value = mock_table

    mock_sns = MagicMock()
    mock_sns.publish.return_value = {"MessageId": "m1"}

    def boto3_client(service):
        if service == "sns":
            return mock_sns
        return MagicMock()

    with patch.object(foia_deadline_handler, "boto3") as mock_boto3:
        mock_boto3.resource.return_value = mock_resource
        mock_boto3.client.side_effect = boto3_client
        result = foia_deadline_handler.handler({}, lambda_context)

    assert result["checked"] == 2
    # At least one overdue alert
    assert result["overdue"] >= 1
