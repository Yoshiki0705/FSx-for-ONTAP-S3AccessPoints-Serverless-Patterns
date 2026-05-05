"""Property-Based Tests for UC11: 小売 / EC 商品画像タグ付け・カタログメタデータ生成

Hypothesis を使用したプロパティベーステスト。
画像タグ付け Lambda の信頼度閾値フラグロジックと
カタログメタデータ生成の必須フィールド完全性を検証する。

Testing Strategy:
- 最小 100 イテレーション/プロパティ
- 各テストにプロパティ番号タグを付与
- タグ形式: Feature: fsxn-s3ap-serverless-patterns-phase2, Property {number}: {property_text}
"""

from __future__ import annotations

import os
import sys

from hypothesis import given, settings, strategies as st

# shared モジュールと UC11 関数のパスを追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from functions.image_tagging.handler import evaluate_confidence
from functions.catalog_metadata.handler import (
    REQUIRED_METADATA_FIELDS,
    _ensure_required_fields,
    _generate_fallback_metadata,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# ラベル名の戦略
label_name_strategy = st.text(
    min_size=1,
    max_size=50,
    alphabet=st.characters(
        whitelist_categories=("L", "N"),
        whitelist_characters=" _-",
        max_codepoint=127,
    ),
)

# 信頼度スコアの戦略 (0.0 - 100.0)
confidence_strategy = st.floats(min_value=0.0, max_value=100.0, allow_nan=False)

# 閾値の戦略 (0.0 - 100.0)
threshold_strategy = st.floats(min_value=0.0, max_value=100.0, allow_nan=False)

# ラベルリストの戦略
label_strategy = st.fixed_dictionaries({
    "name": label_name_strategy,
    "confidence": confidence_strategy,
})

labels_list_strategy = st.lists(label_strategy, min_size=0, max_size=30)


# ---------------------------------------------------------------------------
# Property 17: Confidence threshold flagging
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    labels=st.lists(
        st.fixed_dictionaries({
            "name": label_name_strategy,
            "confidence": confidence_strategy,
        }),
        min_size=1,
        max_size=20,
    ),
    threshold=threshold_strategy,
)
def test_confidence_threshold_flagging(labels, threshold):
    """Feature: fsxn-s3ap-serverless-patterns-phase2, Property 17: Confidence threshold flagging

    For any set of AI/ML detection results with confidence scores and any
    configurable threshold value, if the maximum confidence score is below
    the threshold, the item SHALL be flagged for manual review (above_threshold=False).
    If at or above, SHALL NOT be flagged (above_threshold=True).

    Strategy: Generate random confidence scores and thresholds, verify
    flagging logic is consistent with the threshold comparison.

    **Validates: Requirements 8.5, 8.6, 9.7, 11.7**
    """
    max_confidence, above_threshold = evaluate_confidence(labels, threshold)

    # Verify max_confidence is the actual maximum
    expected_max = max(label["confidence"] for label in labels)
    assert abs(max_confidence - expected_max) < 1e-9, (
        f"max_confidence {max_confidence} != expected max {expected_max}"
    )

    # Core property: flagging logic
    if max_confidence >= threshold:
        assert above_threshold is True, (
            f"max_confidence={max_confidence} >= threshold={threshold}, "
            f"but above_threshold={above_threshold}"
        )
    else:
        assert above_threshold is False, (
            f"max_confidence={max_confidence} < threshold={threshold}, "
            f"but above_threshold={above_threshold}"
        )


@settings(max_examples=100)
@given(threshold=threshold_strategy)
def test_confidence_threshold_empty_labels(threshold):
    """Feature: fsxn-s3ap-serverless-patterns-phase2, Property 17: Confidence threshold flagging (empty case)

    For an empty label list, the max_confidence SHALL be 0.0 and
    above_threshold SHALL be False (flagged for manual review).

    **Validates: Requirements 8.5, 8.6, 9.7, 11.7**
    """
    max_confidence, above_threshold = evaluate_confidence([], threshold)

    assert max_confidence == 0.0
    assert above_threshold is False


# ---------------------------------------------------------------------------
# Property 18: Structured output contains all required fields
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    labels=st.lists(
        st.fixed_dictionaries({
            "name": label_name_strategy,
            "confidence": confidence_strategy,
        }),
        min_size=0,
        max_size=20,
    ),
    metadata=st.fixed_dictionaries({
        "product_category": st.one_of(st.none(), st.text(min_size=0, max_size=100)),
        "color": st.one_of(st.none(), st.text(min_size=0, max_size=50)),
        "material": st.one_of(st.none(), st.text(min_size=0, max_size=50)),
        "style_attributes": st.one_of(
            st.none(),
            st.lists(st.text(min_size=1, max_size=30), min_size=0, max_size=10),
        ),
    }),
)
def test_structured_output_required_fields(labels, metadata):
    """Feature: fsxn-s3ap-serverless-patterns-phase2, Property 18: Structured output contains all required fields

    For any processing result from catalog metadata, the output JSON SHALL
    contain all schema-required fields (product_category, color) and no
    required field SHALL be null or missing.

    Strategy: Generate arbitrary metadata dicts (including None/empty values)
    and verify _ensure_required_fields always produces a complete output.

    **Validates: Requirements 8.4, 10.7, 11.6**
    """
    result = _ensure_required_fields(metadata.copy(), labels)

    # All required fields must be present
    for field in REQUIRED_METADATA_FIELDS:
        assert field in result, f"Required field '{field}' is missing from output"

    # product_category and color must not be None or empty
    assert result["product_category"] is not None and result["product_category"] != "", (
        f"product_category is None or empty: {result['product_category']}"
    )
    assert result["color"] is not None and result["color"] != "", (
        f"color is None or empty: {result['color']}"
    )

    # material must not be None or empty
    assert result["material"] is not None and result["material"] != "", (
        f"material is None or empty: {result['material']}"
    )

    # style_attributes must be a list
    assert isinstance(result["style_attributes"], list), (
        f"style_attributes is not a list: {type(result['style_attributes'])}"
    )


@settings(max_examples=100)
@given(
    labels=st.lists(
        st.fixed_dictionaries({
            "name": label_name_strategy,
            "confidence": confidence_strategy,
        }),
        min_size=0,
        max_size=20,
    ),
)
def test_fallback_metadata_required_fields(labels):
    """Feature: fsxn-s3ap-serverless-patterns-phase2, Property 18: Structured output contains all required fields (fallback)

    When Bedrock response cannot be parsed, the fallback metadata generator
    SHALL produce output containing all required fields.

    **Validates: Requirements 8.4, 10.7, 11.6**
    """
    result = _generate_fallback_metadata(labels)

    # All required fields must be present
    for field in REQUIRED_METADATA_FIELDS:
        assert field in result, f"Required field '{field}' is missing from fallback"

    # Required fields must not be None
    assert result["product_category"] is not None
    assert result["color"] is not None
    assert result["material"] is not None
    assert isinstance(result["style_attributes"], list)
