"""Property-Based Tests for Replay Storm Metrics — Hypothesis

Properties 2, 3, 4: Out-of-order distance, duplicate detection, event loss flagging.
"""

from __future__ import annotations

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from shared.tests.test_replay_storm_metrics import (
    calculate_out_of_order_distance,
    count_duplicates,
    calculate_event_loss_rate,
    is_flagged_as_risk,
)


# --- Property 2: Out-of-Order Distance ---


class TestOutOfOrderDistanceProperty:
    """Property 2: Max absolute positional displacement."""

    @given(
        events=st.lists(
            st.text(alphabet="abcdefghij", min_size=1, max_size=5),
            min_size=1,
            max_size=20,
            unique=True,
        )
    )
    @settings(max_examples=200)
    def test_identity_permutation_is_zero(self, events: list[str]):
        """Same order → distance 0."""
        assert calculate_out_of_order_distance(events, events) == 0

    @given(
        events=st.lists(
            st.text(alphabet="abcdefghij", min_size=1, max_size=5),
            min_size=2,
            max_size=15,
            unique=True,
        )
    )
    @settings(max_examples=200)
    def test_distance_is_non_negative(self, events: list[str]):
        """Distance is always >= 0."""
        import random

        shuffled = events.copy()
        random.shuffle(shuffled)
        result = calculate_out_of_order_distance(events, shuffled)
        assert result >= 0

    @given(
        events=st.lists(
            st.text(alphabet="abcdefghij", min_size=1, max_size=5),
            min_size=2,
            max_size=15,
            unique=True,
        )
    )
    @settings(max_examples=200)
    def test_distance_bounded_by_length(self, events: list[str]):
        """Distance <= len(events) - 1."""
        import random

        shuffled = events.copy()
        random.shuffle(shuffled)
        result = calculate_out_of_order_distance(events, shuffled)
        assert result <= len(events) - 1

    @given(
        events=st.lists(
            st.text(alphabet="abcdefghij", min_size=1, max_size=5),
            min_size=2,
            max_size=10,
            unique=True,
        )
    )
    @settings(max_examples=100)
    def test_reversed_gives_max_distance(self, events: list[str]):
        """Fully reversed → distance = len - 1."""
        reversed_events = list(reversed(events))
        result = calculate_out_of_order_distance(events, reversed_events)
        assert result == len(events) - 1


# --- Property 3: Duplicate Detection ---


class TestDuplicateDetectionProperty:
    """Property 3: Exact count of extra occurrences."""

    @given(
        events=st.lists(
            st.text(alphabet="abcde", min_size=1, max_size=3),
            min_size=0,
            max_size=30,
        )
    )
    @settings(max_examples=200)
    def test_duplicates_equals_total_minus_unique(self, events: list[str]):
        """Duplicates = total count - unique count."""
        result = count_duplicates(events)
        assert result == len(events) - len(set(events))

    @given(
        events=st.lists(
            st.text(alphabet="abcde", min_size=1, max_size=3),
            min_size=0,
            max_size=20,
            unique=True,
        )
    )
    @settings(max_examples=100)
    def test_unique_list_has_zero_duplicates(self, events: list[str]):
        """A list with all unique elements has 0 duplicates."""
        assert count_duplicates(events) == 0

    @given(
        event=st.text(alphabet="abc", min_size=1, max_size=3),
        count=st.integers(min_value=1, max_value=20),
    )
    @settings(max_examples=100)
    def test_repeated_element(self, event: str, count: int):
        """A list of N identical elements has N-1 duplicates."""
        events = [event] * count
        assert count_duplicates(events) == count - 1


# --- Property 4: Event Loss Threshold Flagging ---


class TestEventLossFlaggingProperty:
    """Property 4: Flagged iff loss rate > threshold."""

    @given(
        queued=st.integers(min_value=1, max_value=100000),
        replayed=st.integers(min_value=0, max_value=100000),
    )
    @settings(max_examples=200)
    def test_flagging_consistency(self, queued: int, replayed: int):
        """Flag is True iff loss rate > 0.001."""
        assume(replayed <= queued)
        loss_rate = calculate_event_loss_rate(queued, replayed)
        flagged = is_flagged_as_risk(loss_rate)

        if loss_rate > 0.001:
            assert flagged is True
        else:
            assert flagged is False

    @given(queued=st.integers(min_value=1, max_value=100000))
    @settings(max_examples=100)
    def test_zero_loss_never_flagged(self, queued: int):
        """Zero loss is never flagged."""
        loss_rate = calculate_event_loss_rate(queued, queued)
        assert loss_rate == 0.0
        assert is_flagged_as_risk(loss_rate) is False

    @given(queued=st.integers(min_value=1, max_value=100000))
    @settings(max_examples=100)
    def test_total_loss_always_flagged(self, queued: int):
        """Total loss is always flagged."""
        loss_rate = calculate_event_loss_rate(queued, 0)
        assert loss_rate == 1.0
        assert is_flagged_as_risk(loss_rate) is True
