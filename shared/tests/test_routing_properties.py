"""Property-Based Tests for shared.routing module

Hypothesis を使用したプロパティベーステスト。
ルーティングロジックの不変条件（invariants）を任意入力で検証する。

Testing Strategy:
- 最小 100 イテレーション/プロパティ
- 各テストにプロパティ番号タグを付与
- タグ形式: Feature: fsxn-s3ap-serverless-patterns-phase5, Property {number}: {property_text}
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st

from shared.routing import InferencePath, determine_inference_path


# ---------------------------------------------------------------------------
# Property 1: Three-Way Routing Determinism
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    file_count=st.integers(min_value=0, max_value=10000),
    batch_threshold=st.integers(min_value=1, max_value=1000),
    inference_type=st.sampled_from(["provisioned", "serverless", "none"]),
)
def test_three_way_routing_determinism_exactly_one_path(
    file_count: int,
    batch_threshold: int,
    inference_type: str,
):
    """Feature: fsxn-s3ap-serverless-patterns-phase5, Property 1: Three-Way Routing Determinism

    For ANY valid combination of file_count, batch_threshold, and InferenceType,
    `determine_inference_path` SHALL return exactly one of three paths:
    BATCH_TRANSFORM, REALTIME_ENDPOINT, or SERVERLESS_INFERENCE.

    **Validates: Requirements 1.1, 1.2, 1.4, 1.5**
    """
    result = determine_inference_path(
        file_count=file_count,
        batch_threshold=batch_threshold,
        inference_type=inference_type,
    )

    # Result must be exactly one of the three valid InferencePath values
    valid_paths = {
        InferencePath.BATCH_TRANSFORM,
        InferencePath.REALTIME_ENDPOINT,
        InferencePath.SERVERLESS_INFERENCE,
    }
    assert result in valid_paths, (
        f"Expected one of {valid_paths}, got {result} "
        f"for file_count={file_count}, batch_threshold={batch_threshold}, "
        f"inference_type={inference_type}"
    )


@settings(max_examples=100)
@given(
    file_count=st.integers(min_value=0, max_value=10000),
    batch_threshold=st.integers(min_value=1, max_value=1000),
    inference_type=st.sampled_from(["provisioned", "serverless", "none"]),
)
def test_three_way_routing_determinism_same_result(
    file_count: int,
    batch_threshold: int,
    inference_type: str,
):
    """Feature: fsxn-s3ap-serverless-patterns-phase5, Property 1: Three-Way Routing Determinism

    Calling `determine_inference_path` twice with the same inputs SHALL return
    the same result (determinism guarantee).

    **Validates: Requirements 1.1, 1.2, 1.4, 1.5**
    """
    result1 = determine_inference_path(
        file_count=file_count,
        batch_threshold=batch_threshold,
        inference_type=inference_type,
    )
    result2 = determine_inference_path(
        file_count=file_count,
        batch_threshold=batch_threshold,
        inference_type=inference_type,
    )

    assert result1 == result2, (
        f"Non-deterministic result: first call returned {result1}, "
        f"second call returned {result2} "
        f"for file_count={file_count}, batch_threshold={batch_threshold}, "
        f"inference_type={inference_type}"
    )


@settings(max_examples=100)
@given(
    file_count=st.integers(min_value=0, max_value=10000),
    batch_threshold=st.integers(min_value=1, max_value=1000),
    invalid_type=st.text(
        min_size=1,
        max_size=50,
        alphabet=st.characters(whitelist_categories=("L", "N")),
    ).filter(lambda x: x not in {"provisioned", "serverless", "none", "components"}),
)
def test_three_way_routing_invalid_inference_type_raises(
    file_count: int,
    batch_threshold: int,
    invalid_type: str,
):
    """Feature: fsxn-s3ap-serverless-patterns-phase5, Property 1: Three-Way Routing Determinism

    For ANY inference_type value NOT in {"provisioned", "serverless", "none", "components"},
    `determine_inference_path` SHALL raise a ValueError.

    **Validates: Requirements 1.1, 1.2, 1.4, 1.5**
    """
    with pytest.raises(ValueError):
        determine_inference_path(
            file_count=file_count,
            batch_threshold=batch_threshold,
            inference_type=invalid_type,
        )


# ---------------------------------------------------------------------------
# Property 2: ServerlessConfig Validation
# ---------------------------------------------------------------------------

from shared.routing import validate_serverless_config, VALID_MEMORY_SIZES_MB


@settings(max_examples=100)
@given(
    memory_size_mb=st.integers(min_value=0, max_value=10000),
)
def test_serverless_config_memory_size_accepted_iff_valid(
    memory_size_mb: int,
):
    """Feature: fsxn-s3ap-serverless-patterns-phase5, Property 2: ServerlessConfig Validation

    MemorySizeInMB is accepted if and only if it is in {1024, 2048, 3072, 4096, 5120, 6144}.

    **Validates: Requirements 2.2, 2.3**
    """
    # Use valid values for other params to isolate memory validation
    is_valid, error = validate_serverless_config(
        memory_size_mb=memory_size_mb,
        max_concurrency=5,
        provisioned_concurrency=0,
    )

    if memory_size_mb in VALID_MEMORY_SIZES_MB:
        assert is_valid is True, (
            f"Expected valid for memory_size_mb={memory_size_mb}, "
            f"but got error: {error}"
        )
        assert error is None
    else:
        assert is_valid is False, (
            f"Expected invalid for memory_size_mb={memory_size_mb}, "
            f"but got valid"
        )
        assert error is not None


@settings(max_examples=100)
@given(
    max_concurrency=st.integers(min_value=-10, max_value=500),
)
def test_serverless_config_max_concurrency_accepted_iff_in_range(
    max_concurrency: int,
):
    """Feature: fsxn-s3ap-serverless-patterns-phase5, Property 2: ServerlessConfig Validation

    MaxConcurrency is accepted if and only if it is in range [1, 200].

    **Validates: Requirements 2.2, 2.3**
    """
    # Use valid values for other params to isolate concurrency validation
    is_valid, error = validate_serverless_config(
        memory_size_mb=4096,
        max_concurrency=max_concurrency,
        provisioned_concurrency=0,
    )

    if 1 <= max_concurrency <= 200:
        assert is_valid is True, (
            f"Expected valid for max_concurrency={max_concurrency}, "
            f"but got error: {error}"
        )
        assert error is None
    else:
        assert is_valid is False, (
            f"Expected invalid for max_concurrency={max_concurrency}, "
            f"but got valid"
        )
        assert error is not None


@settings(max_examples=100)
@given(
    provisioned_concurrency=st.integers(min_value=-10, max_value=500),
)
def test_serverless_config_provisioned_concurrency_non_negative(
    provisioned_concurrency: int,
):
    """Feature: fsxn-s3ap-serverless-patterns-phase5, Property 2: ServerlessConfig Validation

    ProvisionedConcurrency must be >= 0.

    **Validates: Requirements 2.2, 2.3**
    """
    # Use valid values for other params to isolate provisioned_concurrency validation
    is_valid, error = validate_serverless_config(
        memory_size_mb=4096,
        max_concurrency=5,
        provisioned_concurrency=provisioned_concurrency,
    )

    if provisioned_concurrency >= 0:
        assert is_valid is True, (
            f"Expected valid for provisioned_concurrency={provisioned_concurrency}, "
            f"but got error: {error}"
        )
        assert error is None
    else:
        assert is_valid is False, (
            f"Expected invalid for provisioned_concurrency={provisioned_concurrency}, "
            f"but got valid"
        )
        assert error is not None



# ---------------------------------------------------------------------------
# Property 3: Four-Way Routing Determinism (Phase 6B)
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    file_count=st.integers(min_value=0, max_value=10000),
    batch_threshold=st.integers(min_value=1, max_value=1000),
    inference_type=st.sampled_from(["provisioned", "serverless", "none", "components"]),
)
def test_four_way_routing_determinism_exactly_one_path(
    file_count: int,
    batch_threshold: int,
    inference_type: str,
):
    """Feature: fsxn-s3ap-serverless-patterns-phase6b, Property 3: Four-Way Routing Determinism

    For ANY valid combination of file_count, batch_threshold, and InferenceType
    (including "components"), `determine_inference_path` SHALL return exactly one
    of four paths: BATCH_TRANSFORM, REALTIME_ENDPOINT, SERVERLESS_INFERENCE,
    or INFERENCE_COMPONENTS.

    **Validates: Requirements 4.1, 4.2**
    """
    result = determine_inference_path(
        file_count=file_count,
        batch_threshold=batch_threshold,
        inference_type=inference_type,
    )

    # Result must be exactly one of the four valid InferencePath values
    valid_paths = {
        InferencePath.BATCH_TRANSFORM,
        InferencePath.REALTIME_ENDPOINT,
        InferencePath.SERVERLESS_INFERENCE,
        InferencePath.INFERENCE_COMPONENTS,
    }
    assert result in valid_paths, (
        f"Expected one of {valid_paths}, got {result} "
        f"for file_count={file_count}, batch_threshold={batch_threshold}, "
        f"inference_type={inference_type}"
    )


@settings(max_examples=100)
@given(
    file_count=st.integers(min_value=0, max_value=10000),
    batch_threshold=st.integers(min_value=1, max_value=1000),
    inference_type=st.sampled_from(["provisioned", "serverless", "none", "components"]),
)
def test_four_way_routing_determinism_same_result(
    file_count: int,
    batch_threshold: int,
    inference_type: str,
):
    """Feature: fsxn-s3ap-serverless-patterns-phase6b, Property 3: Four-Way Routing Determinism

    Calling `determine_inference_path` twice with the same inputs (including
    "components") SHALL return the same result (determinism guarantee).

    **Validates: Requirements 4.1, 4.2**
    """
    result1 = determine_inference_path(
        file_count=file_count,
        batch_threshold=batch_threshold,
        inference_type=inference_type,
    )
    result2 = determine_inference_path(
        file_count=file_count,
        batch_threshold=batch_threshold,
        inference_type=inference_type,
    )

    assert result1 == result2, (
        f"Non-deterministic result: first call returned {result1}, "
        f"second call returned {result2} "
        f"for file_count={file_count}, batch_threshold={batch_threshold}, "
        f"inference_type={inference_type}"
    )


@settings(max_examples=100)
@given(
    file_count=st.integers(min_value=0, max_value=10000),
    batch_threshold=st.integers(min_value=1, max_value=1000),
)
def test_four_way_routing_components_always_returns_inference_components(
    file_count: int,
    batch_threshold: int,
):
    """Feature: fsxn-s3ap-serverless-patterns-phase6b, Property 3: Four-Way Routing Determinism

    For inference_type="components", `determine_inference_path` SHALL always
    return INFERENCE_COMPONENTS regardless of file_count and batch_threshold.

    **Validates: Requirements 4.1**
    """
    result = determine_inference_path(
        file_count=file_count,
        batch_threshold=batch_threshold,
        inference_type="components",
    )

    assert result == InferencePath.INFERENCE_COMPONENTS, (
        f"Expected INFERENCE_COMPONENTS for inference_type='components', "
        f"got {result} for file_count={file_count}, batch_threshold={batch_threshold}"
    )


# ---------------------------------------------------------------------------
# Property 4: validate_inference_config (Phase 6B)
# ---------------------------------------------------------------------------

from shared.routing import validate_inference_config


@settings(max_examples=100)
@given(
    endpoint_name=st.text(
        min_size=1,
        max_size=50,
        alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-"),
    ),
    component_name=st.text(
        min_size=1,
        max_size=50,
        alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-"),
    ),
)
def test_validate_inference_config_components_requires_both_names(
    endpoint_name: str,
    component_name: str,
):
    """Feature: fsxn-s3ap-serverless-patterns-phase6b, Property 4: validate_inference_config

    For inference_type="components", validation SHALL pass if and only if both
    endpoint_name and component_name are non-empty.

    **Validates: Requirements 4.3**
    """
    # Both provided → valid
    is_valid, error = validate_inference_config(
        inference_type="components",
        endpoint_name=endpoint_name,
        component_name=component_name,
    )
    assert is_valid is True
    assert error is None

    # Missing component_name → invalid
    is_valid, error = validate_inference_config(
        inference_type="components",
        endpoint_name=endpoint_name,
        component_name="",
    )
    assert is_valid is False
    assert "component_name" in error

    # Missing endpoint_name → invalid
    is_valid, error = validate_inference_config(
        inference_type="components",
        endpoint_name="",
        component_name=component_name,
    )
    assert is_valid is False
    assert "endpoint_name" in error
