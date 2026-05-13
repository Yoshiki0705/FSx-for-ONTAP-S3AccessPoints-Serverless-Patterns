"""Cost Scheduler プロパティテスト + ユニットテスト.

Property 6: コスト削減見積もりの非負性
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.lambdas.cost_scheduler.handler import estimate_monthly_savings


class TestCostSchedulerProperty:
    """Property 6: コスト削減見積もりの非負性."""

    @settings(max_examples=100)
    @given(
        business_hours_rate_minutes=st.integers(min_value=1, max_value=1440),
        off_hours_rate_minutes=st.integers(min_value=1, max_value=1440),
        lambda_duration_ms=st.integers(min_value=100, max_value=900000),
        lambda_memory_mb=st.integers(min_value=128, max_value=10240),
    )
    def test_savings_non_negative_when_off_hours_slower(
        self,
        business_hours_rate_minutes: int,
        off_hours_rate_minutes: int,
        lambda_duration_ms: int,
        lambda_memory_mb: int,
    ) -> None:
        """Feature: fsxn-s3ap-serverless-patterns-phase10, Property 6: コスト削減見積もり非負性.

        off_hours_rate > business_hours_rate の場合、月間コスト削減見積もりが 0 以上。
        """
        assume(off_hours_rate_minutes > business_hours_rate_minutes)

        savings = estimate_monthly_savings(
            business_hours_rate_minutes=business_hours_rate_minutes,
            off_hours_rate_minutes=off_hours_rate_minutes,
            lambda_duration_ms=lambda_duration_ms,
            lambda_memory_mb=lambda_memory_mb,
        )

        assert savings >= 0, f"Savings {savings} is negative"

    @settings(max_examples=100)
    @given(
        rate_minutes=st.integers(min_value=1, max_value=1440),
        lambda_duration_ms=st.integers(min_value=100, max_value=900000),
        lambda_memory_mb=st.integers(min_value=128, max_value=10240),
    )
    def test_same_rate_zero_savings(
        self,
        rate_minutes: int,
        lambda_duration_ms: int,
        lambda_memory_mb: int,
    ) -> None:
        """同一レートの場合、削減額はほぼ 0."""
        savings = estimate_monthly_savings(
            business_hours_rate_minutes=rate_minutes,
            off_hours_rate_minutes=rate_minutes,
            lambda_duration_ms=lambda_duration_ms,
            lambda_memory_mb=lambda_memory_mb,
        )

        # Floating point precision: allow tiny epsilon
        assert abs(savings) < 1e-10


class TestCostSchedulerUnit:
    """Cost Scheduler ユニットテスト."""

    def test_default_parameters(self) -> None:
        """デフォルトパラメータでの見積もり."""
        savings = estimate_monthly_savings()
        assert savings > 0
        # With default params (1h business, 6h off), savings should be positive
        assert savings < 10.0  # Sanity check: not unreasonably large

    def test_higher_off_hours_rate_gives_savings(self) -> None:
        """非営業時間帯のレートが高い場合に削減額が正."""
        savings = estimate_monthly_savings(
            business_hours_rate_minutes=60,
            off_hours_rate_minutes=360,
        )
        assert savings > 0

    def test_lower_off_hours_rate_gives_zero(self) -> None:
        """非営業時間帯のレートが低い場合は削減額 0（max(0) で保証）."""
        savings = estimate_monthly_savings(
            business_hours_rate_minutes=360,
            off_hours_rate_minutes=60,
        )
        # When off-hours is more frequent, "savings" would be negative
        # but we clamp to 0
        assert savings == 0.0

    def test_large_memory_increases_savings(self) -> None:
        """メモリサイズが大きいほど削減額が増加."""
        savings_small = estimate_monthly_savings(
            business_hours_rate_minutes=60,
            off_hours_rate_minutes=360,
            lambda_memory_mb=256,
        )
        savings_large = estimate_monthly_savings(
            business_hours_rate_minutes=60,
            off_hours_rate_minutes=360,
            lambda_memory_mb=1024,
        )
        assert savings_large > savings_small
