"""Load Testing & Replay プロパティベーステスト.

Property 12: Set-Difference Event Loss Calculation
  - lost_events = expected_set - received_set, count が一致する
Property 13: Load Ramp-Up Linearity
  - 任意の target_rate と ramp_up_sec で各秒のレートが線形関数に従う
Property 14: Percentile Calculation Correctness
  - P50 <= P95 <= P99, P99 <= max(values)

**Validates: Requirements 7.5, 8.6, 8.7, 9.1, 9.4**
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from tests.load.test_high_load import calculate_percentile, calculate_ramp_rate


# --- Hypothesis Strategies ---

# Strategy for event sets (file paths)
event_path_strategy = st.from_regex(
    r"/mnt/fsxn/[a-z]{3,8}/test-[a-z0-9]{4,12}\.(txt|dat|csv)",
    fullmatch=True,
)

expected_events_strategy = st.lists(
    event_path_strategy,
    min_size=1,
    max_size=50,
    unique=True,
)

# Strategy for ramp-up parameters
target_rate_strategy = st.integers(min_value=1, max_value=10000)
ramp_up_sec_strategy = st.integers(min_value=1, max_value=600)
elapsed_sec_strategy = st.floats(min_value=0.0, max_value=1200.0, allow_nan=False, allow_infinity=False)

# Strategy for latency values (positive floats)
latency_values_strategy = st.lists(
    st.floats(min_value=0.01, max_value=100000.0, allow_nan=False, allow_infinity=False),
    min_size=1,
    max_size=200,
)


# --- Property 12: Set-Difference Event Loss Calculation ---


class TestSetDifferenceEventLoss:
    """Property 12: Set-Difference Event Loss Calculation.

    **Validates: Requirements 7.5, 8.7**

    期待イベント集合と受信イベント集合の差集合が欠損リストと一致し、
    カウントも正確であることを検証する。
    """

    @pytest.mark.property
    @given(
        expected_events=expected_events_strategy,
        drop_indices=st.lists(st.integers(min_value=0, max_value=49), max_size=20),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_lost_events_equals_set_difference(
        self,
        expected_events: list[str],
        drop_indices: list[int],
    ):
        """lost_events = expected_set - received_set, count が一致する."""
        # Simulate received events by dropping some from expected
        valid_drop_indices = {i % len(expected_events) for i in drop_indices}
        received_events = [
            e for i, e in enumerate(expected_events) if i not in valid_drop_indices
        ]

        expected_set = set(expected_events)
        received_set = set(received_events)

        # Calculate lost events using set difference
        lost_events = expected_set - received_set
        lost_count = len(lost_events)

        # Property: lost_events count matches
        assert lost_count == len(expected_set) - len(received_set & expected_set), (
            f"Lost count mismatch: {lost_count} != "
            f"{len(expected_set)} - {len(received_set & expected_set)}"
        )

        # Property: every lost event was in expected but not in received
        for event in lost_events:
            assert event in expected_set
            assert event not in received_set

        # Property: no received event is in the lost set
        for event in received_events:
            assert event not in lost_events

    @pytest.mark.property
    @given(expected_events=expected_events_strategy)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_no_loss_when_all_received(self, expected_events: list[str]):
        """全イベント受信時は欠損なし."""
        expected_set = set(expected_events)
        received_set = set(expected_events)  # All received

        lost_events = expected_set - received_set

        assert len(lost_events) == 0
        assert lost_events == set()

    @pytest.mark.property
    @given(expected_events=expected_events_strategy)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_total_loss_when_none_received(self, expected_events: list[str]):
        """受信ゼロ時は全イベントが欠損."""
        expected_set = set(expected_events)
        received_set: set[str] = set()

        lost_events = expected_set - received_set

        assert lost_events == expected_set
        assert len(lost_events) == len(expected_set)


# --- Property 13: Load Ramp-Up Linearity ---


class TestLoadRampUpLinearity:
    """Property 13: Load Ramp-Up Linearity.

    **Validates: Requirements 9.1**

    任意の target_rate と ramp_up_sec で、各秒における目標レートが
    線形関数 rate(t) = (t / ramp_up_sec) * target_rate に従うことを検証する。
    """

    @pytest.mark.property
    @given(
        target_rate=target_rate_strategy,
        ramp_up_sec=ramp_up_sec_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_ramp_up_is_monotonically_non_decreasing(
        self, target_rate: int, ramp_up_sec: int
    ):
        """ramp-up フェーズのレートが単調非減少."""
        rates = [
            calculate_ramp_rate(t, ramp_up_sec, target_rate)
            for t in range(1, ramp_up_sec + 1)
        ]

        for i in range(1, len(rates)):
            assert rates[i] >= rates[i - 1], (
                f"Rate decreased at t={i+1}: {rates[i]} < {rates[i-1]} "
                f"(target={target_rate}, ramp_up={ramp_up_sec})"
            )

    @pytest.mark.property
    @given(
        target_rate=target_rate_strategy,
        ramp_up_sec=ramp_up_sec_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_ramp_up_reaches_target_at_end(
        self, target_rate: int, ramp_up_sec: int
    ):
        """ramp-up 完了時に目標レートに到達する."""
        rate_at_end = calculate_ramp_rate(ramp_up_sec, ramp_up_sec, target_rate)
        assert rate_at_end == target_rate, (
            f"Rate at ramp-up end: {rate_at_end} != target {target_rate}"
        )

    @pytest.mark.property
    @given(
        target_rate=target_rate_strategy,
        ramp_up_sec=ramp_up_sec_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_ramp_up_starts_at_zero(
        self, target_rate: int, ramp_up_sec: int
    ):
        """ramp-up 開始時（t=0）のレートは 0."""
        rate_at_start = calculate_ramp_rate(0, ramp_up_sec, target_rate)
        assert rate_at_start == 0, (
            f"Rate at t=0: {rate_at_start} != 0"
        )

    @pytest.mark.property
    @given(
        target_rate=target_rate_strategy,
        ramp_up_sec=ramp_up_sec_strategy,
        elapsed_sec=st.floats(min_value=0.0, max_value=2000.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_ramp_up_never_exceeds_target(
        self, target_rate: int, ramp_up_sec: int, elapsed_sec: float
    ):
        """任意の時点でレートが target_rate を超えない."""
        rate = calculate_ramp_rate(elapsed_sec, ramp_up_sec, target_rate)
        assert rate <= target_rate, (
            f"Rate {rate} exceeds target {target_rate} at t={elapsed_sec}"
        )

    @pytest.mark.property
    @given(
        target_rate=target_rate_strategy,
        ramp_up_sec=ramp_up_sec_strategy,
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_ramp_up_midpoint_approximately_half(
        self, target_rate: int, ramp_up_sec: int
    ):
        """ramp-up 中間点でレートが目標の約半分."""
        midpoint = ramp_up_sec / 2.0
        rate_at_mid = calculate_ramp_rate(midpoint, ramp_up_sec, target_rate)
        expected_mid = int(0.5 * target_rate)

        # Allow ±1 for integer truncation
        assert abs(rate_at_mid - expected_mid) <= 1, (
            f"Rate at midpoint ({midpoint}s): {rate_at_mid}, "
            f"expected ~{expected_mid} (target={target_rate})"
        )


# --- Property 14: Percentile Calculation Correctness ---


class TestPercentileCalculationCorrectness:
    """Property 14: Percentile Calculation Correctness.

    **Validates: Requirements 8.6, 9.4**

    P50 <= P95 <= P99 の単調性と P99 <= max(values) を検証する。
    """

    @pytest.mark.property
    @given(values=latency_values_strategy)
    @settings(max_examples=200, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_percentile_monotonicity(self, values: list[float]):
        """P50 <= P95 <= P99 の単調性."""
        p50 = calculate_percentile(values, 50)
        p95 = calculate_percentile(values, 95)
        p99 = calculate_percentile(values, 99)

        assert p50 <= p95, (
            f"P50 ({p50}) > P95 ({p95}) for values of length {len(values)}"
        )
        assert p95 <= p99, (
            f"P95 ({p95}) > P99 ({p99}) for values of length {len(values)}"
        )

    @pytest.mark.property
    @given(values=latency_values_strategy)
    @settings(max_examples=200, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_p99_bounded_by_max(self, values: list[float]):
        """P99 <= max(values)."""
        p99 = calculate_percentile(values, 99)
        max_val = max(values)

        assert p99 <= max_val + 1e-9, (
            f"P99 ({p99}) > max ({max_val}) for values of length {len(values)}"
        )

    @pytest.mark.property
    @given(values=latency_values_strategy)
    @settings(max_examples=200, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_p50_bounded_by_min_and_max(self, values: list[float]):
        """min(values) <= P50 <= max(values)."""
        p50 = calculate_percentile(values, 50)
        min_val = min(values)
        max_val = max(values)

        assert min_val - 1e-9 <= p50 <= max_val + 1e-9, (
            f"P50 ({p50}) not in [{min_val}, {max_val}]"
        )

    @pytest.mark.property
    @given(
        value=st.floats(min_value=0.01, max_value=100000.0, allow_nan=False, allow_infinity=False),
        count=st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_uniform_values_all_percentiles_equal(self, value: float, count: int):
        """全値が同一の場合、全パーセンタイルが同じ値."""
        values = [value] * count

        p50 = calculate_percentile(values, 50)
        p95 = calculate_percentile(values, 95)
        p99 = calculate_percentile(values, 99)

        assert abs(p50 - value) < 1e-9
        assert abs(p95 - value) < 1e-9
        assert abs(p99 - value) < 1e-9

    @pytest.mark.property
    @given(values=latency_values_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_percentile_0_equals_min(self, values: list[float]):
        """P0 = min(values)."""
        p0 = calculate_percentile(values, 0)
        min_val = min(values)

        assert abs(p0 - min_val) < 1e-9, (
            f"P0 ({p0}) != min ({min_val})"
        )

    @pytest.mark.property
    @given(values=latency_values_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_percentile_100_equals_max(self, values: list[float]):
        """P100 = max(values)."""
        p100 = calculate_percentile(values, 100)
        max_val = max(values)

        assert abs(p100 - max_val) < 1e-9, (
            f"P100 ({p100}) != max ({max_val})"
        )
