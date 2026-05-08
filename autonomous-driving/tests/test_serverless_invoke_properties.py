"""Property-Based Tests for UC9: Serverless Inference Invocation

Hypothesis を使用したプロパティベーステスト。
Serverless Inference のタイムアウト境界とレスポンス透過性の不変条件を検証する。

Testing Strategy:
- 最小 100 イテレーション/プロパティ
- 各テストにプロパティ番号タグを付与
- タグ形式: Feature: fsxn-s3ap-serverless-patterns-phase5, Property {number}: {property_text}
"""

from __future__ import annotations

from hypothesis import given, settings, strategies as st


# ---------------------------------------------------------------------------
# Helper: Timeout Bound Validation
# ---------------------------------------------------------------------------


def validate_timeout_bound(
    initial_timeout: int,
    retry_delay: int,
    max_retries: int,
    step_functions_task_timeout: int,
) -> bool:
    """Serverless Inference の合計タイムアウトが Step Functions タスクタイムアウト以内かを検証する。

    合計タイムアウト = initial_timeout + (retry_delay × max_retries)
    この値が step_functions_task_timeout 以下であれば有効な構成。

    Args:
        initial_timeout: Serverless Inference 初期タイムアウト秒
        retry_delay: ModelNotReadyException リトライ待機秒
        max_retries: ModelNotReadyException 最大リトライ回数
        step_functions_task_timeout: Step Functions タスクタイムアウト秒

    Returns:
        bool: True if configuration is valid (within timeout bound)
    """
    total_timeout = initial_timeout + (retry_delay * max_retries)
    return total_timeout <= step_functions_task_timeout


# ---------------------------------------------------------------------------
# Helper: Build Inference Response
# ---------------------------------------------------------------------------


def build_inference_response(
    inference_type: str,
    prediction: str,
    variant_name: str,
    latency_ms: float,
) -> dict:
    """推論レスポンスを構築する。

    provisioned/serverless 両方のレスポンスが同一キーセットを持つことを保証する。

    Args:
        inference_type: "provisioned" or "serverless"
        prediction: 推論結果文字列
        variant_name: Production Variant 名
        latency_ms: レイテンシ（ミリ秒）

    Returns:
        dict: 推論レスポンス辞書
    """
    return {
        "prediction": prediction,
        "variant_name": variant_name,
        "latency_ms": latency_ms,
        "inference_type": inference_type,
    }


# ---------------------------------------------------------------------------
# Property 3: Serverless Invocation Timeout Bound
# Feature: fsxn-s3ap-serverless-patterns-phase5, Property 3: Serverless Invocation Timeout Bound
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    initial_timeout=st.integers(min_value=1, max_value=120),
    retry_delay=st.integers(min_value=1, max_value=30),
    max_retries=st.integers(min_value=0, max_value=5),
    step_functions_task_timeout=st.integers(min_value=60, max_value=300),
)
def test_serverless_invocation_timeout_bound(
    initial_timeout: int,
    retry_delay: int,
    max_retries: int,
    step_functions_task_timeout: int,
):
    """Feature: fsxn-s3ap-serverless-patterns-phase5, Property 3: Serverless Invocation Timeout Bound

    For ALL Serverless Inference invocations, the total timeout
    (initial_timeout + retry_delay × max_retries) SHALL NOT exceed the
    Step Functions task timeout. When the sum exceeds the task timeout,
    the system SHALL detect this as invalid configuration.

    **Validates: Requirements 3.2, 3.5**
    """
    total_timeout = initial_timeout + (retry_delay * max_retries)
    is_valid = validate_timeout_bound(
        initial_timeout, retry_delay, max_retries, step_functions_task_timeout
    )

    if total_timeout <= step_functions_task_timeout:
        assert is_valid is True, (
            f"Configuration should be valid: "
            f"total_timeout={total_timeout} "
            f"(initial={initial_timeout} + delay={retry_delay} × retries={max_retries}) "
            f"<= task_timeout={step_functions_task_timeout}, "
            f"but validate_timeout_bound returned False"
        )
    else:
        assert is_valid is False, (
            f"Configuration should be invalid: "
            f"total_timeout={total_timeout} "
            f"(initial={initial_timeout} + delay={retry_delay} × retries={max_retries}) "
            f"> task_timeout={step_functions_task_timeout}, "
            f"but validate_timeout_bound returned True"
        )


# ---------------------------------------------------------------------------
# Property 4: Inference Type Response Transparency
# Feature: fsxn-s3ap-serverless-patterns-phase5, Property 4: Inference Type Response Transparency
# ---------------------------------------------------------------------------


REQUIRED_RESPONSE_KEYS = frozenset({"prediction", "variant_name", "latency_ms", "inference_type"})


@settings(max_examples=100, deadline=None)
@given(
    prediction=st.text(min_size=1, max_size=200),
    variant_name=st.text(min_size=1, max_size=50),
    latency_ms=st.floats(min_value=0.1, max_value=60000.0, allow_nan=False, allow_infinity=False),
)
def test_inference_type_response_transparency(
    prediction: str,
    variant_name: str,
    latency_ms: float,
):
    """Feature: fsxn-s3ap-serverless-patterns-phase5, Property 4: Inference Type Response Transparency

    For ANY successful inference invocation, the response dictionary SHALL
    contain the same set of keys regardless of inference_type. Both "serverless"
    and "provisioned" responses MUST have identical key sets containing:
    prediction, variant_name, latency_ms, inference_type.

    **Validates: Requirements 3.6**
    """
    # Build responses for both inference types
    serverless_response = build_inference_response(
        inference_type="serverless",
        prediction=prediction,
        variant_name=variant_name,
        latency_ms=latency_ms,
    )
    provisioned_response = build_inference_response(
        inference_type="provisioned",
        prediction=prediction,
        variant_name=variant_name,
        latency_ms=latency_ms,
    )

    # Both responses must have the required key set
    serverless_keys = set(serverless_response.keys())
    provisioned_keys = set(provisioned_response.keys())

    assert serverless_keys == REQUIRED_RESPONSE_KEYS, (
        f"Serverless response keys {serverless_keys} do not match "
        f"required keys {REQUIRED_RESPONSE_KEYS}"
    )

    assert provisioned_keys == REQUIRED_RESPONSE_KEYS, (
        f"Provisioned response keys {provisioned_keys} do not match "
        f"required keys {REQUIRED_RESPONSE_KEYS}"
    )

    # Key sets must be identical between both types
    assert serverless_keys == provisioned_keys, (
        f"Response key sets differ between inference types: "
        f"serverless={serverless_keys}, provisioned={provisioned_keys}"
    )

    # Verify inference_type field is correctly set
    assert serverless_response["inference_type"] == "serverless", (
        f"Serverless response inference_type should be 'serverless', "
        f"got '{serverless_response['inference_type']}'"
    )
    assert provisioned_response["inference_type"] == "provisioned", (
        f"Provisioned response inference_type should be 'provisioned', "
        f"got '{provisioned_response['inference_type']}'"
    )
