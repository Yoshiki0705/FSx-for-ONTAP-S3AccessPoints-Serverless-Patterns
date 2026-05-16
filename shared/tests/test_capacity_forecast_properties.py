"""Capacity Forecast プロパティベーステスト.

Property 3: Linear Regression Correctness
  - 完全に線形なデータ (y = a*x + b) に対して元のパラメータ a, b を正確に復元する
Property 4: Capacity Prediction Consistency
  - 正の slope で days_until_full > 0、slope <= 0 で -1 を返す

**Validates: Requirements 4.3, 4.4, 4.7**
"""

from __future__ import annotations

import math
import time

import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from shared.lambdas.capacity_forecast.handler import (
    linear_regression,
    predict_days_until_full,
)


# --- Hypothesis Strategies ---

# Use normalized x values (0-based offsets) to avoid floating-point issues
# with large epoch timestamps. We test the math, not the epoch scale.
num_points_strategy = st.integers(min_value=3, max_value=100)

# Time step between data points (seconds) — 1 hour to 1 day
time_step_strategy = st.floats(
    min_value=3600.0,
    max_value=86400.0,
    allow_nan=False,
    allow_infinity=False,
)


# --- Property 3: Linear Regression Correctness ---


class TestLinearRegressionCorrectness:
    """Property 3: Linear Regression Correctness.

    **Validates: Requirements 4.3**

    完全に線形なデータ (y = a*x + b) に対して、linear_regression() が
    元のパラメータ a (slope) と b (intercept) を正確に復元することを検証する。
    """

    @pytest.mark.property
    @given(
        slope_per_step=st.floats(min_value=0.01, max_value=10.0, allow_nan=False, allow_infinity=False),
        intercept=st.floats(min_value=0.0, max_value=500.0, allow_nan=False, allow_infinity=False),
        num_points=num_points_strategy,
        time_step=time_step_strategy,
    )
    @settings(max_examples=200, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_recovers_exact_parameters_for_linear_data(
        self,
        slope_per_step: float,
        intercept: float,
        num_points: int,
        time_step: float,
    ):
        """完全に線形なデータから slope と intercept を正確に復元する.

        To avoid floating-point precision issues with large epoch timestamps,
        we use small x-offsets (0, time_step, 2*time_step, ...) and verify
        the regression recovers the correct slope and intercept.
        """
        # Generate perfectly linear data: y = slope_per_step/time_step * x + intercept
        # Using x values starting from 0 to avoid large-number precision issues
        slope = slope_per_step / time_step  # Convert to per-second slope
        data_points = [
            (i * time_step, slope * (i * time_step) + intercept)
            for i in range(num_points)
        ]

        recovered_slope, recovered_intercept = linear_regression(data_points)

        # With small x values, we get much better precision
        slope_tolerance = max(abs(slope) * 1e-8, 1e-14)
        intercept_tolerance = max(abs(intercept) * 1e-8, 1e-10)

        assert abs(recovered_slope - slope) < slope_tolerance, (
            f"Slope mismatch: expected {slope}, got {recovered_slope} "
            f"(diff={abs(recovered_slope - slope)}, tol={slope_tolerance})"
        )
        assert abs(recovered_intercept - intercept) < intercept_tolerance, (
            f"Intercept mismatch: expected {intercept}, got {recovered_intercept} "
            f"(diff={abs(recovered_intercept - intercept)}, tol={intercept_tolerance})"
        )

    @pytest.mark.property
    @given(
        slope_per_step=st.floats(min_value=-10.0, max_value=-0.01, allow_nan=False, allow_infinity=False),
        intercept=st.floats(min_value=100.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        num_points=num_points_strategy,
        time_step=time_step_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_regression_with_negative_slope(
        self,
        slope_per_step: float,
        intercept: float,
        num_points: int,
        time_step: float,
    ):
        """負の slope を含む線形データでも正確に復元する."""
        slope = slope_per_step / time_step
        data_points = [
            (i * time_step, slope * (i * time_step) + intercept)
            for i in range(num_points)
        ]

        # Ensure all y values are non-negative
        for _, y in data_points:
            assume(y >= 0)

        recovered_slope, recovered_intercept = linear_regression(data_points)

        slope_tolerance = max(abs(slope) * 1e-8, 1e-14)
        intercept_tolerance = max(abs(intercept) * 1e-8, 1e-10)

        assert abs(recovered_slope - slope) < slope_tolerance
        assert abs(recovered_intercept - intercept) < intercept_tolerance

    @pytest.mark.property
    @given(
        constant_y=st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        num_points=num_points_strategy,
        time_step=time_step_strategy,
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_flat_data_returns_zero_slope(
        self,
        constant_y: float,
        num_points: int,
        time_step: float,
    ):
        """一定値のデータに対して slope≈0 を返す."""
        data_points = [
            (i * time_step, constant_y)
            for i in range(num_points)
        ]

        recovered_slope, recovered_intercept = linear_regression(data_points)

        assert abs(recovered_slope) < 1e-10, (
            f"Expected zero slope for flat data, got {recovered_slope}"
        )
        assert abs(recovered_intercept - constant_y) < max(abs(constant_y) * 1e-10, 1e-10), (
            f"Expected intercept={constant_y}, got {recovered_intercept}"
        )


# --- Property 4: Capacity Prediction Consistency ---


class TestCapacityPredictionConsistency:
    """Property 4: Capacity Prediction Consistency.

    **Validates: Requirements 4.4, 4.7**

    - 正の slope → days_until_full > 0 (current_usage < total_capacity の場合)
    - slope <= 0 → days_until_full = -1
    - current_usage >= total_capacity → days_until_full = 0
    """

    @pytest.mark.property
    @given(
        slope=st.floats(min_value=1e-8, max_value=1e-3, allow_nan=False, allow_infinity=False),
        current_usage_pct=st.floats(min_value=0.01, max_value=0.95, allow_nan=False, allow_infinity=False),
        total_capacity=st.floats(min_value=100.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200, suppress_health_check=[
        HealthCheck.function_scoped_fixture,
        HealthCheck.filter_too_much,
    ])
    def test_positive_slope_returns_non_negative_days(
        self,
        slope: float,
        current_usage_pct: float,
        total_capacity: float,
    ):
        """正の slope で current_usage < total_capacity なら days_until_full >= 0.

        Note: returns 0 when less than 1 day remains (int truncation).
        """
        # Construct intercept so that current_usage = current_usage_pct * total_capacity
        current_time = 1_700_000_000.0  # Fixed time to avoid flakiness
        current_usage = current_usage_pct * total_capacity
        intercept = current_usage - slope * current_time

        days = predict_days_until_full(slope, intercept, total_capacity, current_time)

        # With positive slope and usage below capacity, result must be >= 0 (never -1)
        assert days >= 0, (
            f"Expected non-negative days for positive slope={slope}, "
            f"current_usage={current_usage:.2f}, capacity={total_capacity:.2f}, "
            f"got days={days}"
        )
        # Verify it's NOT -1 (which would mean "never fills up")
        assert days != -1, (
            f"Got -1 (never fills) despite positive slope={slope}"
        )

    @pytest.mark.property
    @given(
        slope=st.floats(min_value=-1e-3, max_value=0.0, allow_nan=False, allow_infinity=False),
        current_usage_pct=st.floats(min_value=0.01, max_value=0.95, allow_nan=False, allow_infinity=False),
        total_capacity=st.floats(min_value=100.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200, suppress_health_check=[
        HealthCheck.function_scoped_fixture,
        HealthCheck.filter_too_much,
    ])
    def test_non_positive_slope_returns_minus_one(
        self,
        slope: float,
        current_usage_pct: float,
        total_capacity: float,
    ):
        """slope <= 0 なら days_until_full = -1 (容量枯渇しない)."""
        current_time = 1_700_000_000.0
        current_usage = current_usage_pct * total_capacity
        intercept = current_usage - slope * current_time

        # Verify our setup: current_usage should be below capacity
        actual_usage = slope * current_time + intercept
        assume(actual_usage < total_capacity)
        assume(actual_usage >= 0)

        days = predict_days_until_full(slope, intercept, total_capacity, current_time)

        assert days == -1, (
            f"Expected -1 for non-positive slope={slope}, got days={days}"
        )

    @pytest.mark.property
    @given(
        slope=st.floats(min_value=-1e-3, max_value=1e-3, allow_nan=False, allow_infinity=False),
        excess_pct=st.floats(min_value=0.01, max_value=0.5, allow_nan=False, allow_infinity=False),
        total_capacity=st.floats(min_value=100.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, suppress_health_check=[
        HealthCheck.function_scoped_fixture,
        HealthCheck.filter_too_much,
    ])
    def test_at_capacity_returns_zero(
        self,
        slope: float,
        excess_pct: float,
        total_capacity: float,
    ):
        """current_usage >= total_capacity なら days_until_full = 0."""
        current_time = 1_700_000_000.0
        # Set current_usage above capacity
        current_usage = total_capacity * (1.0 + excess_pct)
        intercept = current_usage - slope * current_time

        days = predict_days_until_full(slope, intercept, total_capacity, current_time)

        assert days == 0, (
            f"Expected 0 when at/above capacity, got days={days}. "
            f"current_usage={current_usage:.2f}, capacity={total_capacity:.2f}"
        )

    @pytest.mark.property
    @given(
        slope=st.floats(min_value=-1e-3, max_value=1e-3, allow_nan=False, allow_infinity=False),
        intercept=st.floats(min_value=-500.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        total_capacity=st.floats(min_value=100.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, suppress_health_check=[
        HealthCheck.function_scoped_fixture,
        HealthCheck.filter_too_much,
    ])
    def test_days_until_full_is_non_negative_or_minus_one(
        self,
        slope: float,
        intercept: float,
        total_capacity: float,
    ):
        """predict_days_until_full は常に >= 0 または -1 を返す."""
        current_time = 1_700_000_000.0
        current_usage = slope * current_time + intercept
        assume(math.isfinite(current_usage))
        # Avoid cases where time_at_full would overflow int
        if slope > 0 and current_usage < total_capacity:
            time_at_full = (total_capacity - intercept) / slope
            seconds_remaining = time_at_full - current_time
            assume(math.isfinite(seconds_remaining))
            assume(abs(seconds_remaining) < 1e15)  # Avoid int overflow

        days = predict_days_until_full(slope, intercept, total_capacity, current_time)

        assert days >= -1, f"Unexpected negative value: {days}"
        assert days == -1 or days >= 0, f"Invalid return value: {days}"
