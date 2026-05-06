"""Property-Based Tests for UC9: Real-time Inference + A/B Testing

Hypothesis を使用したプロパティベーステスト。
推論ルーティング、バリアント重み正規化、集計ロジックの不変条件を検証する。

Testing Strategy:
- 最小 100 イテレーション/プロパティ
- 各テストにプロパティ番号タグを付与
- タグ形式: Feature: fsxn-s3ap-serverless-patterns-phase4, Property {number}: {property_text}
"""

from __future__ import annotations

import os
import sys

from hypothesis import given, settings, strategies as st

# shared モジュールと UC9 関数のパスを追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from functions.inference_comparison.handler import aggregate_by_variant


# ---------------------------------------------------------------------------
# Helper: Inference Routing Decision
# ---------------------------------------------------------------------------


def route_inference(file_count: int, threshold: int) -> str:
    """ファイル数と閾値に基づいて推論パスを決定する。

    file_count < threshold → Real-time Endpoint（低レイテンシ）
    file_count >= threshold → Batch Transform（コスト効率）

    Args:
        file_count: 処理対象のファイル数
        threshold: ルーティング閾値

    Returns:
        str: "realtime" or "batch_transform"
    """
    if file_count < threshold:
        return "realtime"
    return "batch_transform"


# ---------------------------------------------------------------------------
# Helper: Variant Weight Normalization
# ---------------------------------------------------------------------------


def normalize_weights(weights: list[float]) -> list[float]:
    """バリアント重みリストを正規化し、合計が 1.0 になるようにする。

    各重みを全体の合計で割ることで比例的に正規化する。

    Args:
        weights: 正の浮動小数点数のリスト

    Returns:
        list[float]: 正規化された重みリスト（合計 = 1.0）
    """
    total = sum(weights)
    return [w / total for w in weights]


# ---------------------------------------------------------------------------
# Property 8: File Count Threshold Routing
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    file_count=st.integers(min_value=0, max_value=1000),
    threshold=st.integers(min_value=1, max_value=100),
)
def test_file_count_threshold_routing(file_count: int, threshold: int):
    """Feature: fsxn-s3ap-serverless-patterns-phase4, Property 8: File Count Threshold Routing

    For any input file count and configurable threshold, if file_count < threshold
    the routing decision SHALL be "realtime" (Real-time Endpoint path), otherwise
    it SHALL be "batch_transform" (Batch Transform path). The routing decision is
    deterministic for a given file count and threshold.

    **Validates: Requirements 5.2**
    """
    result = route_inference(file_count, threshold)

    if file_count < threshold:
        assert result == "realtime", (
            f"Expected 'realtime' for file_count={file_count} < threshold={threshold}, "
            f"but got '{result}'"
        )
    else:
        assert result == "batch_transform", (
            f"Expected 'batch_transform' for file_count={file_count} >= threshold={threshold}, "
            f"but got '{result}'"
        )

    # Determinism: same inputs always produce same output
    assert route_inference(file_count, threshold) == result


# ---------------------------------------------------------------------------
# Property 9: Variant Weight Normalization
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    weights=st.lists(
        st.floats(min_value=0.01, max_value=10.0),
        min_size=2,
        max_size=5,
    ),
)
def test_variant_weight_normalization(weights: list[float]):
    """Feature: fsxn-s3ap-serverless-patterns-phase4, Property 9: Variant Weight Normalization

    For any list of Production Variant weight configurations, the sum of all
    normalized weights SHALL equal 1.0 (within floating-point tolerance of ±0.001).

    **Validates: Requirements 6.1**
    """
    normalized = normalize_weights(weights)

    # Sum of normalized weights must equal 1.0 within tolerance
    weight_sum = sum(normalized)
    assert abs(weight_sum - 1.0) <= 0.001, (
        f"Normalized weight sum {weight_sum} is not within ±0.001 of 1.0. "
        f"Input weights: {weights}, normalized: {normalized}"
    )

    # Each normalized weight must be positive
    for i, w in enumerate(normalized):
        assert w > 0, (
            f"Normalized weight at index {i} is not positive: {w}. "
            f"Input weights: {weights}"
        )

    # Number of weights must be preserved
    assert len(normalized) == len(weights), (
        f"Normalization changed list length: {len(weights)} -> {len(normalized)}"
    )

    # Proportionality: relative ordering is preserved
    for i in range(len(weights) - 1):
        for j in range(i + 1, len(weights)):
            if weights[i] > weights[j]:
                assert normalized[i] > normalized[j], (
                    f"Proportionality violated: weights[{i}]={weights[i]} > "
                    f"weights[{j}]={weights[j]} but normalized[{i}]={normalized[i]} "
                    f"<= normalized[{j}]={normalized[j]}"
                )
            elif weights[i] < weights[j]:
                assert normalized[i] < normalized[j], (
                    f"Proportionality violated: weights[{i}]={weights[i]} < "
                    f"weights[{j}]={weights[j]} but normalized[{i}]={normalized[i]} "
                    f">= normalized[{j}]={normalized[j]}"
                )


# ---------------------------------------------------------------------------
# Property 10: Inference Comparison Aggregation Correctness
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    items=st.lists(
        st.fixed_dictionaries({
            "test_id": st.just("test-endpoint"),
            "timestamp": st.integers(min_value=1000000000, max_value=2000000000),
            "variant_name": st.sampled_from(["model-v1", "model-v2", "model-v3"]),
            "latency_ms": st.floats(min_value=1.0, max_value=5000.0),
            "is_error": st.booleans(),
        }),
        min_size=1,
        max_size=100,
    ),
)
def test_inference_comparison_aggregation_correctness(
    items: list[dict],
):
    """Feature: fsxn-s3ap-serverless-patterns-phase4, Property 10: Inference Comparison Aggregation Correctness

    For any set of inference result records with multiple variant names, the
    Inference Comparison Lambda SHALL compute per-variant metrics where:
    - avg_latency equals the arithmetic mean of all latency values for that variant
    - error_rate equals the count of errors divided by total requests for that variant
    - request_count equals the total number of requests for that variant

    **Validates: Requirements 6.4**
    """
    result = aggregate_by_variant(items)

    # Compute expected values manually per variant
    expected: dict[str, dict] = {}
    for item in items:
        variant = str(item["variant_name"])
        if variant not in expected:
            expected[variant] = {
                "total_latency": 0.0,
                "error_count": 0,
                "request_count": 0,
            }
        expected[variant]["request_count"] += 1
        expected[variant]["total_latency"] += float(item["latency_ms"])
        if item["is_error"]:
            expected[variant]["error_count"] += 1

    # Verify all variants are present in result
    assert set(result.keys()) == set(expected.keys()), (
        f"Variant mismatch: result has {set(result.keys())}, "
        f"expected {set(expected.keys())}"
    )

    for variant_name, exp_data in expected.items():
        res = result[variant_name]

        # request_count must match
        assert res["request_count"] == exp_data["request_count"], (
            f"Variant '{variant_name}': request_count mismatch. "
            f"Expected {exp_data['request_count']}, got {res['request_count']}"
        )

        # avg_latency must equal arithmetic mean (within rounding tolerance)
        expected_avg = exp_data["total_latency"] / exp_data["request_count"]
        assert abs(res["avg_latency_ms"] - round(expected_avg, 2)) <= 0.01, (
            f"Variant '{variant_name}': avg_latency_ms mismatch. "
            f"Expected ~{expected_avg:.2f}, got {res['avg_latency_ms']}"
        )

        # error_rate must equal errors / total
        expected_error_rate = (
            exp_data["error_count"] / exp_data["request_count"]
        )
        assert abs(res["error_rate"] - round(expected_error_rate, 4)) <= 0.0001, (
            f"Variant '{variant_name}': error_rate mismatch. "
            f"Expected ~{expected_error_rate:.4f}, got {res['error_rate']}"
        )

        # error_count must match
        assert res["error_count"] == exp_data["error_count"], (
            f"Variant '{variant_name}': error_count mismatch. "
            f"Expected {exp_data['error_count']}, got {res['error_count']}"
        )
