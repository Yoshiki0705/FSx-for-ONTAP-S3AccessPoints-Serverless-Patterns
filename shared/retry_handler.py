"""統一リトライハンドラー — Exponential Backoff with Error Categorization

全 UC (UC18–UC28) で使用する共通リトライメカニズム。
AWS サービスの一時的エラーに対してエクスポネンシャルバックオフでリトライを行い、
エラーを5つのカテゴリに分類して適切なアクションを決定する。

Retry Config:
- max_attempts: 3
- initial_interval_seconds: 2
- backoff_rate: 2.0
- retryable_errors: ThrottlingException, ServiceUnavailableException,
                    InternalServerError, ProvisionedThroughputExceededException

Error Categories:
- TRANSIENT: Retry with backoff (Throttling, 5xx)
- PARSE_ERROR: Skip file, log error
- VALIDATION_ERROR: Flag for review
- PERMISSION_ERROR: Fail fast, alert
- QUOTA_ERROR: Stop batch, alert

Usage:
    from shared.retry_handler import retry_with_backoff, RetryConfig, ErrorCategory, categorize_error

    # デコレータとして使用
    @retry_with_backoff()
    def call_bedrock(prompt):
        return bedrock_client.invoke_model(...)

    # カスタム設定で使用
    @retry_with_backoff(config=RetryConfig(max_attempts=5))
    def call_athena(query):
        return athena_client.start_query_execution(...)

    # 関数として使用
    result = execute_with_retry(lambda: client.invoke_model(...))
"""

from __future__ import annotations

import enum
import functools
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar

from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ─────────────────────────────────────────────────────────────────────────────
# Error Categories
# ─────────────────────────────────────────────────────────────────────────────


class ErrorCategory(str, enum.Enum):
    """エラーカテゴリ分類

    各カテゴリに対するアクション:
    - TRANSIENT: Retry with exponential backoff
    - PARSE_ERROR: Skip file, log error
    - VALIDATION_ERROR: Flag for review
    - PERMISSION_ERROR: Fail fast, alert
    - QUOTA_ERROR: Stop batch, alert
    """

    TRANSIENT = "TRANSIENT"
    PARSE_ERROR = "PARSE_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    PERMISSION_ERROR = "PERMISSION_ERROR"
    QUOTA_ERROR = "QUOTA_ERROR"


# ─────────────────────────────────────────────────────────────────────────────
# Retry Configuration
# ─────────────────────────────────────────────────────────────────────────────

# リトライ対象のエラーコード (AWS SDK ClientError.response["Error"]["Code"])
RETRYABLE_ERROR_CODES: frozenset[str] = frozenset(
    [
        "ThrottlingException",
        "ServiceUnavailableException",
        "InternalServerError",
        "ProvisionedThroughputExceededException",
    ]
)

# 権限エラーコード
PERMISSION_ERROR_CODES: frozenset[str] = frozenset(
    [
        "AccessDeniedException",
        "AccessDenied",
        "UnauthorizedAccess",
        "ExpiredTokenException",
        "InvalidIdentityToken",
    ]
)

# クォータエラーコード
QUOTA_ERROR_CODES: frozenset[str] = frozenset(
    [
        "ServiceQuotaExceededException",
        "LimitExceededException",
        "TooManyRequestsException",
    ]
)

# バリデーションエラーコード
VALIDATION_ERROR_CODES: frozenset[str] = frozenset(
    [
        "ValidationException",
        "InvalidParameterException",
        "InvalidRequestException",
        "MalformedQueryString",
    ]
)


@dataclass(frozen=True)
class RetryConfig:
    """リトライ設定

    Attributes:
        max_attempts: 最大リトライ回数 (デフォルト: 3)
        initial_interval_seconds: 初回リトライ間隔 (デフォルト: 2秒)
        backoff_rate: バックオフ倍率 (デフォルト: 2.0)
        retryable_errors: リトライ対象エラーコード
    """

    max_attempts: int = 3
    initial_interval_seconds: float = 2.0
    backoff_rate: float = 2.0
    retryable_errors: frozenset[str] = field(default_factory=lambda: RETRYABLE_ERROR_CODES)


# デフォルト設定インスタンス
DEFAULT_RETRY_CONFIG = RetryConfig()


# ─────────────────────────────────────────────────────────────────────────────
# Retry Exhausted Exception
# ─────────────────────────────────────────────────────────────────────────────


class RetryExhaustedError(Exception):
    """全リトライ回数を使い果たした場合に発生する例外

    Attributes:
        attempts: 試行回数
        last_error: 最後に発生したエラー
        error_code: AWS エラーコード (存在する場合)
    """

    def __init__(
        self,
        message: str,
        attempts: int,
        last_error: Exception,
        error_code: str | None = None,
    ):
        super().__init__(message)
        self.attempts = attempts
        self.last_error = last_error
        self.error_code = error_code


# ─────────────────────────────────────────────────────────────────────────────
# Error Categorization
# ─────────────────────────────────────────────────────────────────────────────


def categorize_error(error: Exception) -> ErrorCategory:
    """エラーをカテゴリに分類する

    Args:
        error: 分類対象の例外

    Returns:
        ErrorCategory: エラーカテゴリ

    分類ロジック:
    1. ClientError の場合、Error.Code で判定
    2. それ以外の一般例外は PARSE_ERROR として扱う
    """
    if isinstance(error, ClientError):
        error_code = error.response.get("Error", {}).get("Code", "")
        return _categorize_error_code(error_code)

    if isinstance(error, RetryExhaustedError):
        return ErrorCategory.TRANSIENT

    # 一般的な Python 例外はパースエラーとして分類
    if isinstance(error, (ValueError, KeyError, TypeError, UnicodeDecodeError)):
        return ErrorCategory.PARSE_ERROR

    # デフォルトは TRANSIENT (安全側に倒す)
    return ErrorCategory.TRANSIENT


def _categorize_error_code(error_code: str) -> ErrorCategory:
    """AWS エラーコードをカテゴリに分類する

    Args:
        error_code: AWS SDK のエラーコード文字列

    Returns:
        ErrorCategory: エラーカテゴリ
    """
    if error_code in RETRYABLE_ERROR_CODES:
        return ErrorCategory.TRANSIENT

    if error_code in PERMISSION_ERROR_CODES:
        return ErrorCategory.PERMISSION_ERROR

    if error_code in QUOTA_ERROR_CODES:
        return ErrorCategory.QUOTA_ERROR

    if error_code in VALIDATION_ERROR_CODES:
        return ErrorCategory.VALIDATION_ERROR

    # 未分類のエラーコードはデフォルトで PARSE_ERROR
    return ErrorCategory.PARSE_ERROR


# ─────────────────────────────────────────────────────────────────────────────
# Backoff Calculation
# ─────────────────────────────────────────────────────────────────────────────


def calculate_backoff(
    attempt: int,
    initial_interval: float = 2.0,
    backoff_rate: float = 2.0,
) -> float:
    """指定された試行回数に対するバックオフ時間を計算する

    計算式: initial_interval * (backoff_rate ^ attempt)
    ※ attempt は 0-indexed (0回目の試行, 1回目のリトライ, ...)

    Args:
        attempt: 現在の試行回数 (0-indexed)
        initial_interval: 初回リトライ間隔（秒）
        backoff_rate: バックオフ倍率

    Returns:
        float: 待機時間（秒）
    """
    return initial_interval * (backoff_rate ** attempt)


# ─────────────────────────────────────────────────────────────────────────────
# Core Retry Logic
# ─────────────────────────────────────────────────────────────────────────────


def _is_retryable(error: Exception, retryable_errors: frozenset[str]) -> bool:
    """エラーがリトライ対象かどうかを判定する

    Args:
        error: 判定対象の例外
        retryable_errors: リトライ対象エラーコードの集合

    Returns:
        bool: リトライ対象の場合 True
    """
    if isinstance(error, ClientError):
        error_code = error.response.get("Error", {}).get("Code", "")
        return error_code in retryable_errors
    return False


def execute_with_retry(
    func: Callable[[], T],
    config: RetryConfig | None = None,
    sleep_func: Callable[[float], None] | None = None,
) -> T:
    """関数をリトライ付きで実行する

    Args:
        func: 実行する関数（引数なし）
        config: リトライ設定（未指定時はデフォルト設定を使用）
        sleep_func: スリープ関数（テスト用にオーバーライド可能）

    Returns:
        T: 関数の戻り値

    Raises:
        RetryExhaustedError: 全リトライ回数を使い果たした場合
        Exception: リトライ対象外のエラーが発生した場合（即座に再送出）
    """
    if config is None:
        config = DEFAULT_RETRY_CONFIG
    if sleep_func is None:
        sleep_func = time.sleep

    last_error: Exception | None = None

    for attempt in range(config.max_attempts):
        try:
            return func()
        except Exception as e:
            last_error = e

            if not _is_retryable(e, config.retryable_errors):
                # リトライ対象外のエラーは即座に再送出
                raise

            if attempt < config.max_attempts - 1:
                # 最後の試行でなければバックオフして再試行
                wait_time = calculate_backoff(
                    attempt,
                    config.initial_interval_seconds,
                    config.backoff_rate,
                )
                logger.warning(
                    "Retryable error (attempt %d/%d): %s. "
                    "Waiting %.1f seconds before retry.",
                    attempt + 1,
                    config.max_attempts,
                    str(e),
                    wait_time,
                )
                sleep_func(wait_time)
            else:
                # 最後の試行でも失敗
                error_code = None
                if isinstance(e, ClientError):
                    error_code = e.response.get("Error", {}).get("Code", "")

                logger.error(
                    "All retry attempts exhausted (%d/%d): %s",
                    config.max_attempts,
                    config.max_attempts,
                    str(e),
                )
                raise RetryExhaustedError(
                    f"All {config.max_attempts} retry attempts exhausted. "
                    f"Last error: {e}",
                    attempts=config.max_attempts,
                    last_error=e,
                    error_code=error_code,
                ) from e

    # ここに到達することはないが型安全性のため
    assert last_error is not None
    raise last_error  # pragma: no cover


# ─────────────────────────────────────────────────────────────────────────────
# Decorator
# ─────────────────────────────────────────────────────────────────────────────


def retry_with_backoff(
    config: RetryConfig | None = None,
    sleep_func: Callable[[float], None] | None = None,
) -> Callable:
    """リトライ付きデコレータ

    Args:
        config: リトライ設定（未指定時はデフォルト設定を使用）
        sleep_func: スリープ関数（テスト用にオーバーライド可能）

    Usage:
        @retry_with_backoff()
        def call_bedrock(prompt):
            return bedrock_client.invoke_model(...)

        @retry_with_backoff(config=RetryConfig(max_attempts=5))
        def call_athena(query):
            return athena_client.start_query_execution(...)
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            return execute_with_retry(
                lambda: func(*args, **kwargs),
                config=config,
                sleep_func=sleep_func,
            )

        return wrapper

    return decorator
