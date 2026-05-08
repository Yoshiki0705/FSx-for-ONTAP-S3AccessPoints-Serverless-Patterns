"""Property-Based Tests for shared.cost_validation module

Hypothesis を使用したプロパティベーステスト。
コスト最適化バリデーションの不変条件（invariants）を任意入力で検証する。

Testing Strategy:
- 最小 100 イテレーション/プロパティ
- 各テストにプロパティ番号タグを付与
- タグ形式: Feature: fsxn-s3ap-serverless-patterns-phase5, Property {number}: {property_text}
"""

from __future__ import annotations

from hypothesis import given, settings, strategies as st

from shared.cost_validation import validate_scaling_schedule, validate_billing_thresholds


# ---------------------------------------------------------------------------
# Property 5: Scheduled Scaling Time Ordering
# Feature: fsxn-s3ap-serverless-patterns-phase5, Property 5: Scheduled Scaling Time Ordering
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    start=st.integers(min_value=0, max_value=23),
    end=st.integers(min_value=0, max_value=23),
)
def test_scheduled_scaling_time_ordering_valid_when_start_lt_end(
    start: int,
    end: int,
):
    """Feature: fsxn-s3ap-serverless-patterns-phase5, Property 5: Scheduled Scaling Time Ordering

    When business_hours_start < business_hours_end, the time ordering validation
    SHALL accept the schedule as valid (assuming other params are valid).

    **Validates: Requirements 5.2, 5.3, 5.4**
    """
    # Use valid capacity values to isolate time ordering validation
    is_valid, error = validate_scaling_schedule(
        business_hours_start=start,
        business_hours_end=end,
        business_min_capacity=1,
        business_max_capacity=4,
        off_hours_min_capacity=0,
        off_hours_max_capacity=1,
    )

    if start < end:
        assert is_valid is True, (
            f"Expected valid for start={start} < end={end}, "
            f"but got error: {error}"
        )
        assert error is None
    else:
        # start >= end should be rejected
        assert is_valid is False, (
            f"Expected invalid for start={start} >= end={end}, "
            f"but got valid"
        )
        assert error is not None


@settings(max_examples=100)
@given(
    start=st.integers(min_value=0, max_value=23),
    end=st.integers(min_value=0, max_value=23),
)
def test_scheduled_scaling_time_ordering_rejected_when_start_gte_end(
    start: int,
    end: int,
):
    """Feature: fsxn-s3ap-serverless-patterns-phase5, Property 5: Scheduled Scaling Time Ordering

    When business_hours_start >= business_hours_end, the time ordering validation
    SHALL reject the schedule as invalid.

    **Validates: Requirements 5.2, 5.3, 5.4**
    """
    # Use valid capacity values to isolate time ordering validation
    is_valid, error = validate_scaling_schedule(
        business_hours_start=start,
        business_hours_end=end,
        business_min_capacity=1,
        business_max_capacity=4,
        off_hours_min_capacity=0,
        off_hours_max_capacity=1,
    )

    if start >= end:
        assert is_valid is False, (
            f"Expected invalid for start={start} >= end={end}, "
            f"but got valid"
        )
        assert error is not None
    else:
        # start < end should be accepted
        assert is_valid is True, (
            f"Expected valid for start={start} < end={end}, "
            f"but got error: {error}"
        )
        assert error is None


# ---------------------------------------------------------------------------
# Property 6: Cost Reduction Guarantee
# Feature: fsxn-s3ap-serverless-patterns-phase5, Property 6: Cost Reduction Guarantee
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    off_hours_max=st.integers(min_value=0, max_value=20),
    business_min=st.integers(min_value=0, max_value=20),
)
def test_cost_reduction_guarantee_valid_when_off_max_lte_business_min(
    off_hours_max: int,
    business_min: int,
):
    """Feature: fsxn-s3ap-serverless-patterns-phase5, Property 6: Cost Reduction Guarantee

    When off_hours_max_capacity <= business_min_capacity, the cost reduction
    guarantee validation SHALL accept the configuration as valid
    (assuming other params are valid).

    **Validates: Requirements 5.4, 5.6**
    """
    # Use valid time values and ensure business_max >= business_min
    # and off_hours_min <= off_hours_max to isolate cost reduction validation
    business_max = max(business_min, 20)
    off_hours_min = 0

    is_valid, error = validate_scaling_schedule(
        business_hours_start=9,
        business_hours_end=18,
        business_min_capacity=business_min,
        business_max_capacity=business_max,
        off_hours_min_capacity=off_hours_min,
        off_hours_max_capacity=off_hours_max,
    )

    if off_hours_max <= business_min:
        assert is_valid is True, (
            f"Expected valid for off_hours_max={off_hours_max} <= "
            f"business_min={business_min}, but got error: {error}"
        )
        assert error is None
    else:
        assert is_valid is False, (
            f"Expected invalid for off_hours_max={off_hours_max} > "
            f"business_min={business_min}, but got valid"
        )
        assert error is not None


@settings(max_examples=100)
@given(
    off_hours_max=st.integers(min_value=0, max_value=20),
    business_min=st.integers(min_value=0, max_value=20),
)
def test_cost_reduction_guarantee_rejected_when_off_max_gt_business_min(
    off_hours_max: int,
    business_min: int,
):
    """Feature: fsxn-s3ap-serverless-patterns-phase5, Property 6: Cost Reduction Guarantee

    When off_hours_max_capacity > business_min_capacity, the cost reduction
    guarantee validation SHALL reject the configuration as invalid.

    **Validates: Requirements 5.4, 5.6**
    """
    # Use valid time values and ensure business_max >= business_min
    # and off_hours_min <= off_hours_max to isolate cost reduction validation
    business_max = max(business_min, 20)
    off_hours_min = 0

    is_valid, error = validate_scaling_schedule(
        business_hours_start=9,
        business_hours_end=18,
        business_min_capacity=business_min,
        business_max_capacity=business_max,
        off_hours_min_capacity=off_hours_min,
        off_hours_max_capacity=off_hours_max,
    )

    if off_hours_max > business_min:
        assert is_valid is False, (
            f"Expected invalid for off_hours_max={off_hours_max} > "
            f"business_min={business_min}, but got valid"
        )
        assert error is not None
    else:
        assert is_valid is True, (
            f"Expected valid for off_hours_max={off_hours_max} <= "
            f"business_min={business_min}, but got error: {error}"
        )
        assert error is None


# ---------------------------------------------------------------------------
# Property 7: Billing Alarm Threshold Ordering
# Feature: fsxn-s3ap-serverless-patterns-phase5, Property 7: Billing Alarm Threshold Ordering
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    warning=st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False),
    critical=st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False),
    emergency=st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False),
)
def test_billing_alarm_threshold_ordering_valid_when_strictly_ordered(
    warning: float,
    critical: float,
    emergency: float,
):
    """Feature: fsxn-s3ap-serverless-patterns-phase5, Property 7: Billing Alarm Threshold Ordering

    When warning < critical < emergency (strict ordering), the billing alarm
    threshold validation SHALL accept the configuration as valid.

    **Validates: Requirements 7.2, 7.3**
    """
    is_valid, error = validate_billing_thresholds(
        warning=warning,
        critical=critical,
        emergency=emergency,
    )

    if warning < critical < emergency:
        assert is_valid is True, (
            f"Expected valid for warning={warning} < critical={critical} < "
            f"emergency={emergency}, but got error: {error}"
        )
        assert error is None
    else:
        assert is_valid is False, (
            f"Expected invalid for warning={warning}, critical={critical}, "
            f"emergency={emergency} (not strictly ordered), but got valid"
        )
        assert error is not None


@settings(max_examples=100)
@given(
    warning=st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False),
    critical=st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False),
    emergency=st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False),
)
def test_billing_alarm_threshold_ordering_rejected_when_not_strictly_ordered(
    warning: float,
    critical: float,
    emergency: float,
):
    """Feature: fsxn-s3ap-serverless-patterns-phase5, Property 7: Billing Alarm Threshold Ordering

    When any violation of strict ordering (warning < critical < emergency) occurs,
    the billing alarm threshold validation SHALL reject the configuration as invalid.

    **Validates: Requirements 7.2, 7.3**
    """
    is_valid, error = validate_billing_thresholds(
        warning=warning,
        critical=critical,
        emergency=emergency,
    )

    if not (warning < critical < emergency):
        assert is_valid is False, (
            f"Expected invalid for warning={warning}, critical={critical}, "
            f"emergency={emergency} (not strictly ordered), but got valid"
        )
        assert error is not None
    else:
        assert is_valid is True, (
            f"Expected valid for warning={warning} < critical={critical} < "
            f"emergency={emergency}, but got error: {error}"
        )
        assert error is None
