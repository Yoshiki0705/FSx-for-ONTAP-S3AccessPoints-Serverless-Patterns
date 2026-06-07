"""retry_handler モジュールのユニットテストおよびプロパティベーステスト

Unit Tests:
- エクスポネンシャルバックオフのタイミング検証
- エラーカテゴリ分類の正確性
- リトライ対象/非対象エラーの動作検証
- RetryExhaustedError の発生条件
- デコレータの動作検証

Property-Based Tests (Hypothesis):
- バックオフ時間の単調増加性
- エラーカテゴリ分類の網羅性
- リトライ回数と設定の一貫性
"""

from __future__ import annotations

import pytest
from botocore.exceptions import ClientError
from hypothesis import given, settings, strategies as st
from unittest.mock import MagicMock, patch

from shared.retry_handler import (
    DEFAULT_RETRY_CONFIG,
    PERMISSION_ERROR_CODES,
    QUOTA_ERROR_CODES,
    RETRYABLE_ERROR_CODES,
    VALIDATION_ERROR_CODES,
    ErrorCategory,
    RetryConfig,
    RetryExhaustedError,
    calculate_backoff,
    categorize_error,
    execute_with_retry,
    retry_with_backoff,
    _is_retryable,
)


# =============================================================================
# Unit Tests — RetryConfig
# =============================================================================


class TestRetryConfig:
    """RetryConfig のデフォルト値と設定テスト"""

    def test_default_config_values(self):
        """デフォルト設定が仕様通りであること (initial=2s, rate=2.0, max=3)"""
        config = RetryConfig()
        assert config.max_attempts == 3
        assert config.initial_interval_seconds == 2.0
        assert config.backoff_rate == 2.0
        assert config.retryable_errors == RETRYABLE_ERROR_CODES

    def test_custom_config(self):
        """カスタム設定が正しく適用されること"""
        config = RetryConfig(max_attempts=5, initial_interval_seconds=1.0, backoff_rate=3.0)
        assert config.max_attempts == 5
        assert config.initial_interval_seconds == 1.0
        assert config.backoff_rate == 3.0

    def test_default_retryable_errors(self):
        """デフォルトのリトライ対象エラーが4つ含まれること"""
        expected = frozenset(
            [
                "ThrottlingException",
                "ServiceUnavailableException",
                "InternalServerError",
                "ProvisionedThroughputExceededException",
            ]
        )
        assert DEFAULT_RETRY_CONFIG.retryable_errors == expected

    def test_config_is_frozen(self):
        """RetryConfig が frozen dataclass であること"""
        config = RetryConfig()
        with pytest.raises(Exception):
            config.max_attempts = 10  # type: ignore[misc]


# =============================================================================
# Unit Tests — calculate_backoff
# =============================================================================


class TestCalculateBackoff:
    """バックオフ時間の計算テスト"""

    def test_first_retry_backoff(self):
        """1回目のリトライ: 2 * 2^0 = 2秒"""
        assert calculate_backoff(0, initial_interval=2.0, backoff_rate=2.0) == 2.0

    def test_second_retry_backoff(self):
        """2回目のリトライ: 2 * 2^1 = 4秒"""
        assert calculate_backoff(1, initial_interval=2.0, backoff_rate=2.0) == 4.0

    def test_third_retry_backoff(self):
        """3回目のリトライ: 2 * 2^2 = 8秒"""
        assert calculate_backoff(2, initial_interval=2.0, backoff_rate=2.0) == 8.0

    def test_custom_initial_interval(self):
        """カスタム初回間隔: 1 * 2^1 = 2秒"""
        assert calculate_backoff(1, initial_interval=1.0, backoff_rate=2.0) == 2.0

    def test_custom_backoff_rate(self):
        """カスタムバックオフ率: 2 * 3^1 = 6秒"""
        assert calculate_backoff(1, initial_interval=2.0, backoff_rate=3.0) == 6.0


# =============================================================================
# Unit Tests — categorize_error
# =============================================================================


class TestCategorizeError:
    """エラーカテゴリ分類テスト"""

    def _make_client_error(self, code: str) -> ClientError:
        """テスト用 ClientError を生成"""
        return ClientError(
            {"Error": {"Code": code, "Message": "test error"}},
            "TestOperation",
        )

    def test_throttling_is_transient(self):
        """ThrottlingException は TRANSIENT"""
        error = self._make_client_error("ThrottlingException")
        assert categorize_error(error) == ErrorCategory.TRANSIENT

    def test_service_unavailable_is_transient(self):
        """ServiceUnavailableException は TRANSIENT"""
        error = self._make_client_error("ServiceUnavailableException")
        assert categorize_error(error) == ErrorCategory.TRANSIENT

    def test_internal_server_error_is_transient(self):
        """InternalServerError は TRANSIENT"""
        error = self._make_client_error("InternalServerError")
        assert categorize_error(error) == ErrorCategory.TRANSIENT

    def test_provisioned_throughput_exceeded_is_transient(self):
        """ProvisionedThroughputExceededException は TRANSIENT"""
        error = self._make_client_error("ProvisionedThroughputExceededException")
        assert categorize_error(error) == ErrorCategory.TRANSIENT

    def test_access_denied_is_permission_error(self):
        """AccessDeniedException は PERMISSION_ERROR"""
        error = self._make_client_error("AccessDeniedException")
        assert categorize_error(error) == ErrorCategory.PERMISSION_ERROR

    def test_quota_exceeded_is_quota_error(self):
        """ServiceQuotaExceededException は QUOTA_ERROR"""
        error = self._make_client_error("ServiceQuotaExceededException")
        assert categorize_error(error) == ErrorCategory.QUOTA_ERROR

    def test_validation_exception_is_validation_error(self):
        """ValidationException は VALIDATION_ERROR"""
        error = self._make_client_error("ValidationException")
        assert categorize_error(error) == ErrorCategory.VALIDATION_ERROR

    def test_value_error_is_parse_error(self):
        """ValueError は PARSE_ERROR"""
        assert categorize_error(ValueError("bad data")) == ErrorCategory.PARSE_ERROR

    def test_key_error_is_parse_error(self):
        """KeyError は PARSE_ERROR"""
        assert categorize_error(KeyError("missing")) == ErrorCategory.PARSE_ERROR

    def test_unicode_decode_error_is_parse_error(self):
        """UnicodeDecodeError は PARSE_ERROR"""
        error = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid byte")
        assert categorize_error(error) == ErrorCategory.PARSE_ERROR

    def test_retry_exhausted_is_transient(self):
        """RetryExhaustedError は TRANSIENT"""
        error = RetryExhaustedError("exhausted", attempts=3, last_error=RuntimeError("test"))
        assert categorize_error(error) == ErrorCategory.TRANSIENT

    def test_unknown_client_error_is_parse_error(self):
        """未知の ClientError コードは PARSE_ERROR"""
        error = self._make_client_error("UnknownCustomError")
        assert categorize_error(error) == ErrorCategory.PARSE_ERROR


# =============================================================================
# Unit Tests — execute_with_retry
# =============================================================================


class TestExecuteWithRetry:
    """リトライ実行テスト"""

    def test_success_on_first_attempt(self):
        """1回目で成功した場合はそのまま値を返す"""
        result = execute_with_retry(lambda: "success")
        assert result == "success"

    def test_success_after_transient_error(self):
        """一時的エラー後にリトライで成功する"""
        call_count = {"n": 0}

        def flaky():
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise ClientError(
                    {"Error": {"Code": "ThrottlingException", "Message": "throttled"}},
                    "Invoke",
                )
            return "recovered"

        sleep_times = []
        result = execute_with_retry(flaky, sleep_func=sleep_times.append)
        assert result == "recovered"
        assert call_count["n"] == 3
        # 2回のリトライ → 2回のスリープ
        assert len(sleep_times) == 2
        assert sleep_times[0] == 2.0  # 2 * 2^0
        assert sleep_times[1] == 4.0  # 2 * 2^1

    def test_retry_exhausted_raises_error(self):
        """全リトライ使い果たしで RetryExhaustedError を発生"""

        def always_fail():
            raise ClientError(
                {"Error": {"Code": "ThrottlingException", "Message": "throttled"}},
                "Invoke",
            )

        sleep_times = []
        with pytest.raises(RetryExhaustedError) as exc_info:
            execute_with_retry(always_fail, sleep_func=sleep_times.append)

        assert exc_info.value.attempts == 3
        assert exc_info.value.error_code == "ThrottlingException"
        assert isinstance(exc_info.value.last_error, ClientError)
        # 3回試行 → 2回のスリープ (最後の試行後はスリープしない)
        assert len(sleep_times) == 2

    def test_non_retryable_error_raises_immediately(self):
        """リトライ対象外エラーは即座に再送出される"""
        call_count = {"n": 0}

        def permission_denied():
            call_count["n"] += 1
            raise ClientError(
                {"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
                "Invoke",
            )

        sleep_times = []
        with pytest.raises(ClientError) as exc_info:
            execute_with_retry(permission_denied, sleep_func=sleep_times.append)

        assert exc_info.value.response["Error"]["Code"] == "AccessDeniedException"
        assert call_count["n"] == 1  # 1回だけ試行
        assert len(sleep_times) == 0  # スリープなし

    def test_custom_config_max_attempts(self):
        """カスタム max_attempts が反映される"""
        call_count = {"n": 0}

        def always_throttled():
            call_count["n"] += 1
            raise ClientError(
                {"Error": {"Code": "InternalServerError", "Message": "500"}},
                "Invoke",
            )

        config = RetryConfig(max_attempts=5)
        sleep_times = []
        with pytest.raises(RetryExhaustedError) as exc_info:
            execute_with_retry(always_throttled, config=config, sleep_func=sleep_times.append)

        assert call_count["n"] == 5
        assert exc_info.value.attempts == 5
        assert len(sleep_times) == 4  # 5回試行 → 4回のスリープ

    def test_provisioned_throughput_exceeded_is_retried(self):
        """ProvisionedThroughputExceededException はリトライされる"""
        call_count = {"n": 0}

        def flaky():
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise ClientError(
                    {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "exceeded"}},
                    "Query",
                )
            return "ok"

        result = execute_with_retry(flaky, sleep_func=lambda _: None)
        assert result == "ok"
        assert call_count["n"] == 2


# =============================================================================
# Unit Tests — retry_with_backoff decorator
# =============================================================================


class TestRetryWithBackoffDecorator:
    """デコレータ動作テスト"""

    def test_decorator_preserves_function_name(self):
        """デコレータが関数名を保持する"""

        @retry_with_backoff(sleep_func=lambda _: None)
        def my_function():
            return "hello"

        assert my_function.__name__ == "my_function"

    def test_decorator_retries_on_transient_error(self):
        """デコレータがリトライ対象エラーでリトライする"""
        call_count = {"n": 0}

        @retry_with_backoff(sleep_func=lambda _: None)
        def flaky_call(value):
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise ClientError(
                    {"Error": {"Code": "ServiceUnavailableException", "Message": "unavail"}},
                    "Call",
                )
            return f"result-{value}"

        result = flaky_call("test")
        assert result == "result-test"
        assert call_count["n"] == 2

    def test_decorator_with_custom_config(self):
        """デコレータにカスタム設定を適用できる"""
        call_count = {"n": 0}
        config = RetryConfig(max_attempts=2)

        @retry_with_backoff(config=config, sleep_func=lambda _: None)
        def always_fail():
            call_count["n"] += 1
            raise ClientError(
                {"Error": {"Code": "ThrottlingException", "Message": "throttled"}},
                "Call",
            )

        with pytest.raises(RetryExhaustedError):
            always_fail()

        assert call_count["n"] == 2


# =============================================================================
# Unit Tests — RetryExhaustedError
# =============================================================================


class TestRetryExhaustedError:
    """RetryExhaustedError の属性テスト"""

    def test_attributes(self):
        """エラー属性が正しく設定される"""
        original = RuntimeError("original error")
        error = RetryExhaustedError(
            "exhausted",
            attempts=3,
            last_error=original,
            error_code="ThrottlingException",
        )
        assert error.attempts == 3
        assert error.last_error is original
        assert error.error_code == "ThrottlingException"
        assert "exhausted" in str(error)

    def test_without_error_code(self):
        """error_code が None の場合もエラーが生成される"""
        error = RetryExhaustedError(
            "exhausted",
            attempts=2,
            last_error=RuntimeError("test"),
        )
        assert error.error_code is None


# =============================================================================
# Property-Based Tests (Hypothesis)
# =============================================================================


@settings(max_examples=100)
@given(
    attempt=st.integers(min_value=0, max_value=10),
    initial_interval=st.floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False),
    backoff_rate=st.floats(min_value=1.0, max_value=5.0, allow_nan=False, allow_infinity=False),
)
def test_backoff_monotonically_increases(attempt, initial_interval, backoff_rate):
    """Feature: fsxn-s3ap-serverless-patterns, Property: Backoff monotonically increases

    For any valid attempt number and configuration, the backoff time for
    attempt N+1 SHALL be greater than or equal to the backoff time for
    attempt N (monotonically non-decreasing).

    **Validates: Requirements 2.6**
    """
    current = calculate_backoff(attempt, initial_interval, backoff_rate)
    next_val = calculate_backoff(attempt + 1, initial_interval, backoff_rate)

    # バックオフは単調増加（backoff_rate >= 1.0 の場合）
    assert next_val >= current


@settings(max_examples=100)
@given(
    attempt=st.integers(min_value=0, max_value=10),
    initial_interval=st.floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False),
    backoff_rate=st.floats(min_value=1.0, max_value=5.0, allow_nan=False, allow_infinity=False),
)
def test_backoff_formula_correctness(attempt, initial_interval, backoff_rate):
    """Feature: fsxn-s3ap-serverless-patterns, Property: Backoff formula correctness

    For any valid attempt, initial_interval, and backoff_rate, the computed
    backoff time SHALL equal initial_interval * (backoff_rate ** attempt).

    **Validates: Requirements 2.6**
    """
    result = calculate_backoff(attempt, initial_interval, backoff_rate)
    expected = initial_interval * (backoff_rate**attempt)
    assert abs(result - expected) < 1e-10


@settings(max_examples=100)
@given(
    error_code=st.sampled_from(sorted(RETRYABLE_ERROR_CODES)),
)
def test_retryable_errors_categorized_as_transient(error_code):
    """Feature: fsxn-s3ap-serverless-patterns, Property: Retryable errors categorized as TRANSIENT

    For any error code in the RETRYABLE_ERROR_CODES set, categorize_error
    SHALL return ErrorCategory.TRANSIENT.

    **Validates: Requirements 13.6**
    """
    error = ClientError(
        {"Error": {"Code": error_code, "Message": "test"}},
        "TestOp",
    )
    assert categorize_error(error) == ErrorCategory.TRANSIENT


@settings(max_examples=100)
@given(
    error_code=st.sampled_from(sorted(PERMISSION_ERROR_CODES)),
)
def test_permission_errors_categorized_correctly(error_code):
    """Feature: fsxn-s3ap-serverless-patterns, Property: Permission errors categorized as PERMISSION_ERROR

    For any error code in the PERMISSION_ERROR_CODES set, categorize_error
    SHALL return ErrorCategory.PERMISSION_ERROR.

    **Validates: Requirements 13.6**
    """
    error = ClientError(
        {"Error": {"Code": error_code, "Message": "test"}},
        "TestOp",
    )
    assert categorize_error(error) == ErrorCategory.PERMISSION_ERROR


@settings(max_examples=100)
@given(
    error_code=st.sampled_from(sorted(QUOTA_ERROR_CODES)),
)
def test_quota_errors_categorized_correctly(error_code):
    """Feature: fsxn-s3ap-serverless-patterns, Property: Quota errors categorized as QUOTA_ERROR

    For any error code in the QUOTA_ERROR_CODES set, categorize_error
    SHALL return ErrorCategory.QUOTA_ERROR.

    **Validates: Requirements 13.6**
    """
    error = ClientError(
        {"Error": {"Code": error_code, "Message": "test"}},
        "TestOp",
    )
    assert categorize_error(error) == ErrorCategory.QUOTA_ERROR


@settings(max_examples=100)
@given(
    max_attempts=st.integers(min_value=1, max_value=10),
    initial_interval=st.floats(min_value=0.1, max_value=5.0, allow_nan=False, allow_infinity=False),
    backoff_rate=st.floats(min_value=1.0, max_value=3.0, allow_nan=False, allow_infinity=False),
)
def test_retry_count_matches_config(max_attempts, initial_interval, backoff_rate):
    """Feature: fsxn-s3ap-serverless-patterns, Property: Retry count matches config

    For any RetryConfig with max_attempts=N, when a retryable error is always
    raised, execute_with_retry SHALL attempt exactly N times before raising
    RetryExhaustedError with attempts=N.

    **Validates: Requirements 2.6**
    """
    call_count = {"n": 0}
    config = RetryConfig(
        max_attempts=max_attempts,
        initial_interval_seconds=initial_interval,
        backoff_rate=backoff_rate,
    )

    def always_fail():
        call_count["n"] += 1
        raise ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "throttled"}},
            "TestOp",
        )

    with pytest.raises(RetryExhaustedError) as exc_info:
        execute_with_retry(always_fail, config=config, sleep_func=lambda _: None)

    assert call_count["n"] == max_attempts
    assert exc_info.value.attempts == max_attempts


@settings(max_examples=100)
@given(
    max_attempts=st.integers(min_value=2, max_value=8),
    success_on_attempt=st.data(),
)
def test_retry_sleep_times_follow_backoff(max_attempts, success_on_attempt):
    """Feature: fsxn-s3ap-serverless-patterns, Property: Sleep times follow exponential backoff

    For any retry sequence, the sleep times between attempts SHALL follow
    the formula: initial_interval * (backoff_rate ** attempt_index).

    **Validates: Requirements 2.6**
    """
    succeed_at = success_on_attempt.draw(st.integers(min_value=2, max_value=max_attempts))
    call_count = {"n": 0}
    config = RetryConfig(max_attempts=max_attempts)

    def flaky():
        call_count["n"] += 1
        if call_count["n"] < succeed_at:
            raise ClientError(
                {"Error": {"Code": "InternalServerError", "Message": "error"}},
                "TestOp",
            )
        return "success"

    sleep_times: list[float] = []
    result = execute_with_retry(flaky, config=config, sleep_func=sleep_times.append)

    assert result == "success"
    assert len(sleep_times) == succeed_at - 1

    # 各スリープ時間がバックオフ式に従うことを検証
    for i, actual_sleep in enumerate(sleep_times):
        expected_sleep = config.initial_interval_seconds * (config.backoff_rate**i)
        assert abs(actual_sleep - expected_sleep) < 1e-10


@settings(max_examples=100)
@given(
    error_code=st.text(
        min_size=1,
        max_size=50,
        alphabet=st.characters(whitelist_categories=("L", "N")),
    ),
)
def test_categorize_error_always_returns_valid_category(error_code):
    """Feature: fsxn-s3ap-serverless-patterns, Property: categorize_error always returns valid ErrorCategory

    For any arbitrary error code string, categorize_error SHALL always return
    a valid ErrorCategory enum member (never raise or return None).

    **Validates: Requirements 13.6**
    """
    error = ClientError(
        {"Error": {"Code": error_code, "Message": "test"}},
        "TestOp",
    )
    result = categorize_error(error)
    assert isinstance(result, ErrorCategory)
    assert result in list(ErrorCategory)
