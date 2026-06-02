"""UC19 広告・マーケティング Property-Based Tests (Hypothesis)

Hypothesis ライブラリを使用したプロパティベーステスト。
処理コアロジックの普遍的性質を多数の入力に対して検証する。

テスト対象プロパティ:
1. Tag count bounds — 0 <= tag_count <= MAX_TAGS_PER_ASSET (50)
2. Moderation threshold consistency — confidence >= threshold → "requires-review"
3. Compliance rule evaluation determinism — 同一入力 → 同一結果

Requirements: 13.3
"""

from __future__ import annotations

import importlib.util
import os
import sys

from hypothesis import given, settings, strategies as st

# shared モジュールのパスを追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Visual Analyzer handler
_va_path = os.path.join(
    os.path.dirname(__file__), "..", "functions", "visual_analyzer", "handler.py"
)
_va_spec = importlib.util.spec_from_file_location("va_handler_pbt", _va_path)
_va_module = importlib.util.module_from_spec(_va_spec)
_va_spec.loader.exec_module(_va_module)

generate_tags = _va_module.generate_tags
check_compliance = _va_module.check_compliance

# Report handler
_report_path = os.path.join(
    os.path.dirname(__file__), "..", "functions", "report", "handler.py"
)
_report_spec = importlib.util.spec_from_file_location("report_handler_pbt", _report_path)
_report_module = importlib.util.module_from_spec(_report_spec)
_report_spec.loader.exec_module(_report_module)

evaluate_moderation_status = _report_module.evaluate_moderation_status
build_catalog_record = _report_module.build_catalog_record

# Text Compliance handler
_tc_path = os.path.join(
    os.path.dirname(__file__), "..", "functions", "text_compliance", "handler.py"
)
_tc_spec = importlib.util.spec_from_file_location("tc_handler_pbt", _tc_path)
_tc_module = importlib.util.module_from_spec(_tc_spec)
_tc_spec.loader.exec_module(_tc_module)

_rule_based_brand_check = _tc_module._rule_based_brand_check

# Constants
MAX_TAGS_PER_ASSET = 50


# =========================================================================
# Property 1: Tag count bounds
# 0 <= tag_count <= MAX_TAGS_PER_ASSET (50)
# =========================================================================


# Strategy for generating label lists
label_strategy = st.lists(
    st.fixed_dictionaries({
        "name": st.text(
            alphabet=st.characters(whitelist_categories=("L", "Nd", "Zs")),
            min_size=1,
            max_size=30,
        ),
        "confidence": st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
        "categories": st.just([]),
    }),
    min_size=0,
    max_size=100,
)


@settings(max_examples=200)
@given(
    labels=label_strategy,
    max_tags=st.integers(min_value=1, max_value=MAX_TAGS_PER_ASSET),
)
def test_tag_count_upper_bound(labels: list[dict], max_tags: int):
    """生成されるタグ数は常に max_tags 以下。

    **Validates: Requirements 13.3**

    プロパティ: len(generate_tags(labels, max_tags)) <= max_tags
    """
    tags = generate_tags(labels, max_tags)
    assert len(tags) <= max_tags


@settings(max_examples=200)
@given(labels=label_strategy)
def test_tag_count_lower_bound(labels: list[dict]):
    """生成されるタグ数は常に 0 以上。

    **Validates: Requirements 13.3**

    プロパティ: len(generate_tags(labels, max_tags)) >= 0
    """
    tags = generate_tags(labels, MAX_TAGS_PER_ASSET)
    assert len(tags) >= 0


@settings(max_examples=200)
@given(labels=label_strategy)
def test_tag_count_no_duplicates(labels: list[dict]):
    """生成されるタグには重複がない。

    **Validates: Requirements 13.3**

    プロパティ: len(tags) == len(set(tags))
    """
    tags = generate_tags(labels, MAX_TAGS_PER_ASSET)
    assert len(tags) == len(set(tags))


@settings(max_examples=200)
@given(
    labels=label_strategy,
    max_tags=st.integers(min_value=1, max_value=MAX_TAGS_PER_ASSET),
)
def test_tag_count_within_bounds(labels: list[dict], max_tags: int):
    """タグ数は常に 0 <= count <= MAX_TAGS_PER_ASSET (50) の範囲内。

    **Validates: Requirements 13.3**

    プロパティ: 0 <= len(tags) <= 50
    """
    tags = generate_tags(labels, max_tags)
    assert 0 <= len(tags) <= MAX_TAGS_PER_ASSET


# =========================================================================
# Property 2: Moderation threshold consistency
# confidence >= threshold → "requires-review"
# =========================================================================


@settings(max_examples=200)
@given(
    confidence=st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
    threshold=st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
)
def test_moderation_threshold_flagging(confidence: float, threshold: float):
    """確信度が閾値以上の場合は常に requires-review にフラグ付けされる。

    **Validates: Requirements 13.3**

    プロパティ: confidence >= threshold → review_status == "requires-review"
    """
    labels = [{"name": "TestLabel", "confidence": confidence}]
    result = evaluate_moderation_status(labels, threshold)

    if confidence >= threshold:
        assert result["review_status"] == "requires-review"
        assert result["violation_category"] == "TestLabel"
        assert result["violation_confidence"] == confidence
    else:
        assert result["review_status"] == "approved"
        assert result["violation_category"] is None


@settings(max_examples=200)
@given(
    threshold=st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
)
def test_moderation_empty_labels_always_approved(threshold: float):
    """空のモデレーションラベルは常に approved。

    **Validates: Requirements 13.3**

    プロパティ: evaluate_moderation_status([], threshold) == "approved"
    """
    result = evaluate_moderation_status([], threshold)
    assert result["review_status"] == "approved"


@settings(max_examples=200)
@given(
    confidences=st.lists(
        st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
        min_size=1,
        max_size=10,
    ),
    threshold=st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
)
def test_moderation_at_least_one_above_implies_review(
    confidences: list[float],
    threshold: float,
):
    """少なくとも1つの確信度が閾値以上であれば requires-review。

    **Validates: Requirements 13.3**

    プロパティ: any(c >= threshold for c in confidences) →
                review_status == "requires-review"
    """
    labels = [{"name": f"Label{i}", "confidence": c} for i, c in enumerate(confidences)]
    result = evaluate_moderation_status(labels, threshold)

    if any(c >= threshold for c in confidences):
        assert result["review_status"] == "requires-review"
    else:
        assert result["review_status"] == "approved"


# =========================================================================
# Property 3: Compliance rule evaluation determinism
# 同一入力は常に同一結果を返す
# =========================================================================


moderation_label_strategy = st.lists(
    st.fixed_dictionaries({
        "name": st.sampled_from(["Violence", "Nudity", "Explicit", "Drugs", "Gambling"]),
        "confidence": st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
        "parent_name": st.text(max_size=20),
    }),
    min_size=0,
    max_size=5,
)

text_detection_strategy = st.lists(
    st.fixed_dictionaries({
        "text": st.text(
            alphabet=st.characters(whitelist_categories=("L", "Nd", "Zs", "P")),
            min_size=0,
            max_size=50,
        ),
        "confidence": st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
        "type": st.sampled_from(["LINE", "WORD"]),
    }),
    min_size=0,
    max_size=10,
)

compliance_rules_strategy = st.fixed_dictionaries({
    "prohibited_moderation_categories": st.lists(
        st.sampled_from(["Violence", "Nudity", "Explicit", "Drugs"]),
        min_size=0,
        max_size=3,
    ),
    "required_disclaimer_keywords": st.lists(
        st.text(
            alphabet=st.characters(whitelist_categories=("L", "Nd")),
            min_size=1,
            max_size=10,
        ),
        min_size=0,
        max_size=3,
    ),
    "size_constraints": st.fixed_dictionaries({
        "max_bytes": st.integers(min_value=1_000_000, max_value=10_000_000_000),
    }),
})


@settings(max_examples=200)
@given(
    moderation_labels=moderation_label_strategy,
    text_detections=text_detection_strategy,
    file_size=st.integers(min_value=0, max_value=10_000_000_000),
    compliance_rules=compliance_rules_strategy,
)
def test_compliance_evaluation_determinism(
    moderation_labels: list[dict],
    text_detections: list[dict],
    file_size: int,
    compliance_rules: dict,
):
    """同一入力に対するコンプライアンス評価は常に同一結果を返す。

    **Validates: Requirements 13.3**

    プロパティ: check_compliance(x) == check_compliance(x) for identical x
    """
    result1 = check_compliance(moderation_labels, text_detections, file_size, compliance_rules)
    result2 = check_compliance(moderation_labels, text_detections, file_size, compliance_rules)
    assert result1 == result2


@settings(max_examples=200)
@given(
    moderation_labels=moderation_label_strategy,
    text_detections=text_detection_strategy,
    file_size=st.integers(min_value=0, max_value=10_000_000_000),
    compliance_rules=compliance_rules_strategy,
)
def test_compliance_status_is_valid(
    moderation_labels: list[dict],
    text_detections: list[dict],
    file_size: int,
    compliance_rules: dict,
):
    """コンプライアンスステータスは常に "compliant" or "non-compliant"。

    **Validates: Requirements 13.3**

    プロパティ: result["status"] in {"compliant", "non-compliant"}
    """
    result = check_compliance(moderation_labels, text_detections, file_size, compliance_rules)
    assert result["status"] in ("compliant", "non-compliant")


@settings(max_examples=200)
@given(
    moderation_labels=moderation_label_strategy,
    text_detections=text_detection_strategy,
    file_size=st.integers(min_value=0, max_value=10_000_000_000),
    compliance_rules=compliance_rules_strategy,
)
def test_compliance_violations_imply_non_compliant(
    moderation_labels: list[dict],
    text_detections: list[dict],
    file_size: int,
    compliance_rules: dict,
):
    """バイオレーションが 1 つ以上存在する場合は non-compliant。

    **Validates: Requirements 13.3**

    プロパティ: len(result["violations"]) > 0 → result["status"] == "non-compliant"
    """
    result = check_compliance(moderation_labels, text_detections, file_size, compliance_rules)
    if len(result["violations"]) > 0:
        assert result["status"] == "non-compliant"


@settings(max_examples=200)
@given(
    extracted_text=st.text(
        alphabet=st.characters(whitelist_categories=("L", "Nd", "Zs", "P")),
        min_size=0,
        max_size=200,
    ),
    prohibited_terms=st.lists(
        st.text(
            alphabet=st.characters(whitelist_categories=("L", "Nd")),
            min_size=1,
            max_size=10,
        ),
        min_size=0,
        max_size=5,
    ),
    required_terms=st.lists(
        st.text(
            alphabet=st.characters(whitelist_categories=("L", "Nd")),
            min_size=1,
            max_size=10,
        ),
        min_size=0,
        max_size=5,
    ),
)
def test_rule_based_brand_check_determinism(
    extracted_text: str,
    prohibited_terms: list[str],
    required_terms: list[str],
):
    """ルールベースブランドチェックは同一入力で常に同一結果。

    **Validates: Requirements 13.3**

    プロパティ: _rule_based_brand_check(x, y) == _rule_based_brand_check(x, y)
    """
    guidelines = {
        "prohibited_terms": prohibited_terms,
        "required_terms": required_terms,
    }
    result1 = _rule_based_brand_check(extracted_text, guidelines)
    result2 = _rule_based_brand_check(extracted_text, guidelines)
    assert result1 == result2
