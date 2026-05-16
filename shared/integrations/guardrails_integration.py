"""shared.integrations.guardrails_integration — Guardrails オプトイン統合ヘルパー.

既存 UC Lambda が CapacityGuardrail にオプトインするためのデコレータおよび
ラッパー関数を提供する。環境変数 `GUARDRAIL_MODE` が設定されていない場合は
ガードレールチェックを完全にスキップし、既存動作に影響を与えない。

Usage (デコレータ):
    from shared.integrations.guardrails_integration import with_guardrail_check

    @with_guardrail_check(action_type="volume_grow")
    def auto_expand_volume(volume_id: str, requested_gb: float, **kwargs):
        # 実際の拡張ロジック
        fsx_client.update_file_system(...)

Usage (関数呼び出し):
    from shared.integrations.guardrails_integration import guardrail_check

    result = guardrail_check(
        action_type="volume_grow",
        requested_gb=50.0,
        execute_fn=my_expand_function,
        volume_id="vol-abc123",
    )
    if not result.allowed:
        logger.warning("Guardrail denied: %s", result.reason)

Requirements:
- 1.10: CloudFormation Conditions によるオプトイン制御で既存 UC テンプレートに影響を与えない
- 13.2: 既存 17 UC テンプレートに変更を加えない（オプトイン統合のみ）
- 13.3: 既存テストスイートを破壊しない
"""

from __future__ import annotations

import functools
import logging
import os
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def _is_guardrail_enabled() -> bool:
    """環境変数 GUARDRAIL_MODE が設定されているかチェックする.

    Returns:
        True if GUARDRAIL_MODE is set and non-empty, False otherwise.
    """
    return bool(os.environ.get("GUARDRAIL_MODE", "").strip())


def guardrail_check(
    action_type: str,
    requested_gb: float,
    execute_fn: Callable[..., Any] | None = None,
    **kwargs: Any,
) -> Any:
    """ガードレールチェックを実行し、許可された場合にアクションを実行する.

    GUARDRAIL_MODE 環境変数が設定されていない場合はガードレールをスキップし、
    execute_fn を直接実行する（opt-in 制御）。

    Args:
        action_type: アクション種別（例: "volume_grow"）
        requested_gb: リクエストされた拡張量（GB）
        execute_fn: 実行する関数。None の場合はチェックのみ。
        **kwargs: execute_fn に渡す追加引数

    Returns:
        GuardrailResult if guardrail is enabled, otherwise the result of execute_fn
        (or None if execute_fn is None).
    """
    if not _is_guardrail_enabled():
        logger.debug(
            "[GuardrailIntegration] GUARDRAIL_MODE not set, skipping guardrail check"
        )
        if execute_fn is not None:
            return execute_fn(**kwargs)
        return None

    # Lazy import to avoid import errors when guardrails module is not needed
    from shared.guardrails import CapacityGuardrail

    guardrail = CapacityGuardrail()
    result = guardrail.check_and_execute(
        action_type=action_type,
        requested_gb=requested_gb,
        execute_fn=execute_fn,
        **kwargs,
    )
    return result


def with_guardrail_check(
    action_type: str,
    requested_gb_param: str = "requested_gb",
) -> Callable[[F], F]:
    """UC Lambda の自動拡張関数にガードレールチェックを追加するデコレータ.

    GUARDRAIL_MODE 環境変数が設定されていない場合はデコレートされた関数を
    そのまま実行する（opt-in 制御）。

    Args:
        action_type: アクション種別（例: "volume_grow", "volume_shrink"）
        requested_gb_param: デコレートされた関数の引数名で拡張量（GB）を
            指定するパラメータ名。デフォルトは "requested_gb"。

    Returns:
        デコレータ関数

    Example:
        @with_guardrail_check(action_type="volume_grow")
        def expand_volume(volume_id: str, requested_gb: float = 50.0):
            # 拡張ロジック
            ...

        # GUARDRAIL_MODE が設定されていない場合: expand_volume() がそのまま実行される
        # GUARDRAIL_MODE が設定されている場合: CapacityGuardrail.check_and_execute() 経由で実行
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not _is_guardrail_enabled():
                logger.debug(
                    "[GuardrailIntegration] GUARDRAIL_MODE not set, "
                    "executing %s directly",
                    func.__name__,
                )
                return func(*args, **kwargs)

            # Extract requested_gb from kwargs or use default
            gb = kwargs.get(requested_gb_param, 0.0)
            if gb == 0.0 and args:
                # Try to get from positional args via function signature
                import inspect

                sig = inspect.signature(func)
                params = list(sig.parameters.keys())
                if requested_gb_param in params:
                    idx = params.index(requested_gb_param)
                    if idx < len(args):
                        gb = args[idx]

            # Lazy import
            from shared.guardrails import CapacityGuardrail, GuardrailResult

            guardrail = CapacityGuardrail()

            # Create a wrapper that calls the original function with its args
            def _execute(**_kw: Any) -> Any:
                return func(*args, **kwargs)

            result = guardrail.check_and_execute(
                action_type=action_type,
                requested_gb=float(gb),
                execute_fn=_execute,
            )

            if isinstance(result, GuardrailResult):
                if not result.allowed:
                    logger.warning(
                        "[GuardrailIntegration] Action denied by guardrail: "
                        "action=%s reason=%s",
                        action_type,
                        result.reason,
                    )
                return result

            return result

        return wrapper  # type: ignore[return-value]

    return decorator
