"""MaxConcurrency Controller プロパティベーステスト + ユニットテスト.

Property 2: MaxConcurrency 算出値の境界と正確性
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.max_concurrency_controller import calculate_max_concurrency


class TestMaxConcurrencyProperty:
    """Property 2: MaxConcurrency 算出値の境界と正確性."""

    @settings(max_examples=200)
    @given(
        detected_file_count=st.integers(min_value=0, max_value=100000),
        ontap_rate_limit=st.integers(min_value=1, max_value=10000),
        api_calls_per_file=st.integers(min_value=1, max_value=100),
        max_concurrency_upper_bound=st.integers(min_value=1, max_value=1000),
    )
    def test_result_within_bounds(
        self,
        detected_file_count: int,
        ontap_rate_limit: int,
        api_calls_per_file: int,
        max_concurrency_upper_bound: int,
    ) -> None:
        """Feature: fsxn-s3ap-serverless-patterns-phase10, Property 2: MaxConcurrency 境界.

        算出値が常に 1 以上かつ max_concurrency_upper_bound 以下であることを検証。
        """
        result = calculate_max_concurrency(
            detected_file_count=detected_file_count,
            ontap_rate_limit=ontap_rate_limit,
            api_calls_per_file=api_calls_per_file,
            max_concurrency_upper_bound=max_concurrency_upper_bound,
        )

        assert result >= 1, f"Result {result} is less than 1"
        assert result <= max_concurrency_upper_bound, (
            f"Result {result} exceeds upper bound {max_concurrency_upper_bound}"
        )

    @settings(max_examples=200)
    @given(
        detected_file_count=st.integers(min_value=0, max_value=100000),
        ontap_rate_limit=st.integers(min_value=1, max_value=10000),
        api_calls_per_file=st.integers(min_value=1, max_value=100),
        max_concurrency_upper_bound=st.integers(min_value=1, max_value=1000),
    )
    def test_result_equals_expected_formula(
        self,
        detected_file_count: int,
        ontap_rate_limit: int,
        api_calls_per_file: int,
        max_concurrency_upper_bound: int,
    ) -> None:
        """Feature: fsxn-s3ap-serverless-patterns-phase10, Property 2: MaxConcurrency 正確性.

        算出値が min(files, rate_limit//calls, upper_bound) を 1 でクランプした値と等しい。
        """
        result = calculate_max_concurrency(
            detected_file_count=detected_file_count,
            ontap_rate_limit=ontap_rate_limit,
            api_calls_per_file=api_calls_per_file,
            max_concurrency_upper_bound=max_concurrency_upper_bound,
        )

        expected = max(
            min(
                detected_file_count,
                ontap_rate_limit // api_calls_per_file,
                max_concurrency_upper_bound,
            ),
            1,
        )

        assert result == expected, (
            f"Result {result} != expected {expected} "
            f"(files={detected_file_count}, rate={ontap_rate_limit}, "
            f"calls={api_calls_per_file}, bound={max_concurrency_upper_bound})"
        )

    @settings(max_examples=100)
    @given(
        ontap_rate_limit=st.integers(min_value=1, max_value=10000),
        api_calls_per_file=st.integers(min_value=1, max_value=100),
        max_concurrency_upper_bound=st.integers(min_value=1, max_value=1000),
    )
    def test_zero_files_returns_one(
        self,
        ontap_rate_limit: int,
        api_calls_per_file: int,
        max_concurrency_upper_bound: int,
    ) -> None:
        """検出ファイル数が 0 の場合、結果は常に 1."""
        result = calculate_max_concurrency(
            detected_file_count=0,
            ontap_rate_limit=ontap_rate_limit,
            api_calls_per_file=api_calls_per_file,
            max_concurrency_upper_bound=max_concurrency_upper_bound,
        )
        assert result == 1


class TestMaxConcurrencyUnit:
    """MaxConcurrency Controller ユニットテスト."""

    def test_basic_calculation(self) -> None:
        """基本的な算出."""
        result = calculate_max_concurrency(
            detected_file_count=150,
            ontap_rate_limit=100,
            api_calls_per_file=2,
            max_concurrency_upper_bound=40,
        )
        # min(150, 100//2=50, 40) = 40
        assert result == 40

    def test_file_count_is_limiting(self) -> None:
        """ファイル数が制約要因."""
        result = calculate_max_concurrency(
            detected_file_count=5,
            ontap_rate_limit=100,
            api_calls_per_file=2,
            max_concurrency_upper_bound=40,
        )
        # min(5, 50, 40) = 5
        assert result == 5

    def test_rate_limit_is_limiting(self) -> None:
        """レートリミットが制約要因."""
        result = calculate_max_concurrency(
            detected_file_count=1000,
            ontap_rate_limit=20,
            api_calls_per_file=5,
            max_concurrency_upper_bound=40,
        )
        # min(1000, 20//5=4, 40) = 4
        assert result == 4

    def test_upper_bound_is_limiting(self) -> None:
        """上限値が制約要因."""
        result = calculate_max_concurrency(
            detected_file_count=1000,
            ontap_rate_limit=1000,
            api_calls_per_file=1,
            max_concurrency_upper_bound=10,
        )
        # min(1000, 1000, 10) = 10
        assert result == 10

    def test_zero_files(self) -> None:
        """ファイル数 0 → 結果 1."""
        result = calculate_max_concurrency(
            detected_file_count=0,
            ontap_rate_limit=100,
            api_calls_per_file=2,
            max_concurrency_upper_bound=40,
        )
        assert result == 1

    def test_negative_file_count_raises(self) -> None:
        """負のファイル数で ValueError."""
        with pytest.raises(ValueError, match="detected_file_count"):
            calculate_max_concurrency(detected_file_count=-1)

    def test_zero_rate_limit_raises(self) -> None:
        """レートリミット 0 で ValueError."""
        with pytest.raises(ValueError, match="ontap_rate_limit"):
            calculate_max_concurrency(
                detected_file_count=10, ontap_rate_limit=0
            )

    def test_zero_api_calls_raises(self) -> None:
        """API 呼び出し回数 0 で ValueError."""
        with pytest.raises(ValueError, match="api_calls_per_file"):
            calculate_max_concurrency(
                detected_file_count=10, api_calls_per_file=0
            )

    def test_zero_upper_bound_raises(self) -> None:
        """上限値 0 で ValueError."""
        with pytest.raises(ValueError, match="max_concurrency_upper_bound"):
            calculate_max_concurrency(
                detected_file_count=10, max_concurrency_upper_bound=0
            )
