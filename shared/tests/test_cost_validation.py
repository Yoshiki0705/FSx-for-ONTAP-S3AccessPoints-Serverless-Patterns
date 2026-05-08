"""Unit Tests for shared.cost_validation module

validate_scaling_schedule と validate_billing_thresholds の単体テスト。
具体的な入力値でバリデーションロジックの正確性を検証する。

Coverage target: 100% for cost_validation.py
"""

from __future__ import annotations

import pytest

from shared.cost_validation import validate_scaling_schedule, validate_billing_thresholds


# ===========================================================================
# Tests for validate_scaling_schedule
# ===========================================================================


class TestValidateScalingScheduleValid:
    """Valid configuration tests for validate_scaling_schedule."""

    def test_valid_default_config(self):
        """Default configuration (9-18, capacity 1/4, off 0/1) is valid."""
        is_valid, error = validate_scaling_schedule(
            business_hours_start=9,
            business_hours_end=18,
            business_min_capacity=1,
            business_max_capacity=4,
            off_hours_min_capacity=0,
            off_hours_max_capacity=1,
        )
        assert is_valid is True
        assert error is None

    def test_valid_minimal_hours_difference(self):
        """Start=0, End=1 (minimal 1-hour difference) is valid."""
        is_valid, error = validate_scaling_schedule(
            business_hours_start=0,
            business_hours_end=1,
            business_min_capacity=1,
            business_max_capacity=1,
            off_hours_min_capacity=0,
            off_hours_max_capacity=0,
        )
        assert is_valid is True
        assert error is None

    def test_valid_maximum_hours_range(self):
        """Start=0, End=23 (maximum range) is valid."""
        is_valid, error = validate_scaling_schedule(
            business_hours_start=0,
            business_hours_end=23,
            business_min_capacity=2,
            business_max_capacity=10,
            off_hours_min_capacity=0,
            off_hours_max_capacity=2,
        )
        assert is_valid is True
        assert error is None

    def test_valid_equal_min_max_capacity(self):
        """Equal min and max capacity (fixed scaling) is valid."""
        is_valid, error = validate_scaling_schedule(
            business_hours_start=8,
            business_hours_end=20,
            business_min_capacity=3,
            business_max_capacity=3,
            off_hours_min_capacity=0,
            off_hours_max_capacity=0,
        )
        assert is_valid is True
        assert error is None

    def test_valid_off_hours_max_equals_business_min(self):
        """off_hours_max == business_min (boundary) is valid."""
        is_valid, error = validate_scaling_schedule(
            business_hours_start=9,
            business_hours_end=18,
            business_min_capacity=2,
            business_max_capacity=8,
            off_hours_min_capacity=0,
            off_hours_max_capacity=2,
        )
        assert is_valid is True
        assert error is None

    def test_valid_all_zero_capacity(self):
        """All capacities at zero is valid (off_hours_max <= business_min)."""
        is_valid, error = validate_scaling_schedule(
            business_hours_start=9,
            business_hours_end=18,
            business_min_capacity=0,
            business_max_capacity=0,
            off_hours_min_capacity=0,
            off_hours_max_capacity=0,
        )
        assert is_valid is True
        assert error is None


class TestValidateScalingScheduleInvalidTimeOrdering:
    """Invalid time ordering tests for validate_scaling_schedule."""

    def test_invalid_start_equals_end(self):
        """start == end is invalid."""
        is_valid, error = validate_scaling_schedule(
            business_hours_start=9,
            business_hours_end=9,
            business_min_capacity=1,
            business_max_capacity=4,
            off_hours_min_capacity=0,
            off_hours_max_capacity=1,
        )
        assert is_valid is False
        assert error is not None
        assert "must be less than" in error

    def test_invalid_start_greater_than_end(self):
        """start > end is invalid."""
        is_valid, error = validate_scaling_schedule(
            business_hours_start=18,
            business_hours_end=9,
            business_min_capacity=1,
            business_max_capacity=4,
            off_hours_min_capacity=0,
            off_hours_max_capacity=1,
        )
        assert is_valid is False
        assert error is not None
        assert "must be less than" in error

    def test_invalid_start_out_of_range_negative(self):
        """Negative start hour is invalid."""
        is_valid, error = validate_scaling_schedule(
            business_hours_start=-1,
            business_hours_end=18,
            business_min_capacity=1,
            business_max_capacity=4,
            off_hours_min_capacity=0,
            off_hours_max_capacity=1,
        )
        assert is_valid is False
        assert error is not None
        assert "Invalid business_hours_start" in error

    def test_invalid_start_out_of_range_high(self):
        """Start hour > 23 is invalid."""
        is_valid, error = validate_scaling_schedule(
            business_hours_start=24,
            business_hours_end=18,
            business_min_capacity=1,
            business_max_capacity=4,
            off_hours_min_capacity=0,
            off_hours_max_capacity=1,
        )
        assert is_valid is False
        assert error is not None
        assert "Invalid business_hours_start" in error

    def test_invalid_end_out_of_range_high(self):
        """End hour > 23 is invalid."""
        is_valid, error = validate_scaling_schedule(
            business_hours_start=9,
            business_hours_end=24,
            business_min_capacity=1,
            business_max_capacity=4,
            off_hours_min_capacity=0,
            off_hours_max_capacity=1,
        )
        assert is_valid is False
        assert error is not None
        assert "Invalid business_hours_end" in error


class TestValidateScalingScheduleInvalidCapacity:
    """Invalid capacity ordering tests for validate_scaling_schedule."""

    def test_invalid_business_min_greater_than_max(self):
        """business_min > business_max is invalid."""
        is_valid, error = validate_scaling_schedule(
            business_hours_start=9,
            business_hours_end=18,
            business_min_capacity=5,
            business_max_capacity=2,
            off_hours_min_capacity=0,
            off_hours_max_capacity=1,
        )
        assert is_valid is False
        assert error is not None
        assert "business_min_capacity" in error

    def test_invalid_off_hours_min_greater_than_max(self):
        """off_hours_min > off_hours_max is invalid."""
        is_valid, error = validate_scaling_schedule(
            business_hours_start=9,
            business_hours_end=18,
            business_min_capacity=1,
            business_max_capacity=4,
            off_hours_min_capacity=3,
            off_hours_max_capacity=1,
        )
        assert is_valid is False
        assert error is not None
        assert "off_hours_min_capacity" in error

    def test_invalid_off_hours_max_greater_than_business_min(self):
        """off_hours_max > business_min violates cost reduction guarantee."""
        is_valid, error = validate_scaling_schedule(
            business_hours_start=9,
            business_hours_end=18,
            business_min_capacity=1,
            business_max_capacity=4,
            off_hours_min_capacity=0,
            off_hours_max_capacity=2,
        )
        assert is_valid is False
        assert error is not None
        assert "cost reduction guarantee" in error

    def test_invalid_negative_business_min_capacity(self):
        """Negative business_min_capacity is invalid."""
        is_valid, error = validate_scaling_schedule(
            business_hours_start=9,
            business_hours_end=18,
            business_min_capacity=-1,
            business_max_capacity=4,
            off_hours_min_capacity=0,
            off_hours_max_capacity=1,
        )
        assert is_valid is False
        assert error is not None
        assert "Invalid business_min_capacity" in error

    def test_invalid_negative_business_max_capacity(self):
        """Negative business_max_capacity is invalid."""
        is_valid, error = validate_scaling_schedule(
            business_hours_start=9,
            business_hours_end=18,
            business_min_capacity=1,
            business_max_capacity=-1,
            off_hours_min_capacity=0,
            off_hours_max_capacity=1,
        )
        assert is_valid is False
        assert error is not None
        assert "Invalid business_max_capacity" in error

    def test_invalid_negative_off_hours_min_capacity(self):
        """Negative off_hours_min_capacity is invalid."""
        is_valid, error = validate_scaling_schedule(
            business_hours_start=9,
            business_hours_end=18,
            business_min_capacity=1,
            business_max_capacity=4,
            off_hours_min_capacity=-1,
            off_hours_max_capacity=1,
        )
        assert is_valid is False
        assert error is not None
        assert "Invalid off_hours_min_capacity" in error

    def test_invalid_negative_off_hours_max_capacity(self):
        """Negative off_hours_max_capacity is invalid."""
        is_valid, error = validate_scaling_schedule(
            business_hours_start=9,
            business_hours_end=18,
            business_min_capacity=1,
            business_max_capacity=4,
            off_hours_min_capacity=0,
            off_hours_max_capacity=-1,
        )
        assert is_valid is False
        assert error is not None
        assert "Invalid off_hours_max_capacity" in error


# ===========================================================================
# Tests for validate_billing_thresholds
# ===========================================================================


class TestValidateBillingThresholdsValid:
    """Valid configuration tests for validate_billing_thresholds."""

    def test_valid_default_thresholds(self):
        """Default thresholds (50, 100, 500) are valid."""
        is_valid, error = validate_billing_thresholds(
            warning=50.0, critical=100.0, emergency=500.0
        )
        assert is_valid is True
        assert error is None

    def test_valid_small_thresholds(self):
        """Small thresholds (0.01, 0.02, 0.03) are valid."""
        is_valid, error = validate_billing_thresholds(
            warning=0.01, critical=0.02, emergency=0.03
        )
        assert is_valid is True
        assert error is None

    def test_valid_large_thresholds(self):
        """Large thresholds (1000, 5000, 10000) are valid."""
        is_valid, error = validate_billing_thresholds(
            warning=1000.0, critical=5000.0, emergency=10000.0
        )
        assert is_valid is True
        assert error is None

    def test_valid_close_thresholds(self):
        """Close but strictly ordered thresholds are valid."""
        is_valid, error = validate_billing_thresholds(
            warning=99.99, critical=100.0, emergency=100.01
        )
        assert is_valid is True
        assert error is None


class TestValidateBillingThresholdsInvalid:
    """Invalid configuration tests for validate_billing_thresholds."""

    def test_invalid_equal_warning_critical(self):
        """warning == critical is invalid (not strictly ordered)."""
        is_valid, error = validate_billing_thresholds(
            warning=100.0, critical=100.0, emergency=500.0
        )
        assert is_valid is False
        assert error is not None
        assert "warning" in error

    def test_invalid_equal_critical_emergency(self):
        """critical == emergency is invalid (not strictly ordered)."""
        is_valid, error = validate_billing_thresholds(
            warning=50.0, critical=500.0, emergency=500.0
        )
        assert is_valid is False
        assert error is not None
        assert "critical" in error

    def test_invalid_reversed_warning_critical(self):
        """warning > critical is invalid."""
        is_valid, error = validate_billing_thresholds(
            warning=200.0, critical=100.0, emergency=500.0
        )
        assert is_valid is False
        assert error is not None

    def test_invalid_reversed_critical_emergency(self):
        """critical > emergency is invalid."""
        is_valid, error = validate_billing_thresholds(
            warning=50.0, critical=600.0, emergency=500.0
        )
        assert is_valid is False
        assert error is not None

    def test_invalid_all_equal(self):
        """All thresholds equal is invalid."""
        is_valid, error = validate_billing_thresholds(
            warning=100.0, critical=100.0, emergency=100.0
        )
        assert is_valid is False
        assert error is not None

    def test_invalid_zero_warning(self):
        """Zero warning threshold is invalid (must be > 0)."""
        is_valid, error = validate_billing_thresholds(
            warning=0.0, critical=100.0, emergency=500.0
        )
        assert is_valid is False
        assert error is not None
        assert "warning" in error.lower() or "Invalid" in error

    def test_invalid_negative_warning(self):
        """Negative warning threshold is invalid."""
        is_valid, error = validate_billing_thresholds(
            warning=-10.0, critical=100.0, emergency=500.0
        )
        assert is_valid is False
        assert error is not None

    def test_invalid_zero_critical(self):
        """Zero critical threshold is invalid (must be > 0)."""
        is_valid, error = validate_billing_thresholds(
            warning=0.01, critical=0.0, emergency=500.0
        )
        assert is_valid is False
        assert error is not None

    def test_invalid_negative_critical(self):
        """Negative critical threshold is invalid."""
        is_valid, error = validate_billing_thresholds(
            warning=0.01, critical=-5.0, emergency=500.0
        )
        assert is_valid is False
        assert error is not None

    def test_invalid_zero_emergency(self):
        """Zero emergency threshold is invalid (must be > 0)."""
        is_valid, error = validate_billing_thresholds(
            warning=50.0, critical=100.0, emergency=0.0
        )
        assert is_valid is False
        assert error is not None

    def test_invalid_negative_emergency(self):
        """Negative emergency threshold is invalid."""
        is_valid, error = validate_billing_thresholds(
            warning=50.0, critical=100.0, emergency=-1.0
        )
        assert is_valid is False
        assert error is not None
