"""UC23 サステナビリティ/ESG Property-Based Tests (Hypothesis)

Hypothesis ライブラリを使用したプロパティベーステスト。
単位正規化ロジックとメトリクスレコードスキーマの普遍的性質を検証する。

テスト対象プロパティ:
1. Unit normalization consistency — target units ∈ {tCO2e, MWh, t, m3}
2. normalize_value always returns NormalizationResult
3. Metric record schema completeness

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

# unit_normalizer モジュールの読み込み
_normalizer_path = os.path.join(
    os.path.dirname(__file__), "..", "shared", "unit_normalizer.py"
)
_normalizer_spec = importlib.util.spec_from_file_location(
    "unit_normalizer_pbt", _normalizer_path
)
_normalizer_module = importlib.util.module_from_spec(_normalizer_spec)
sys.modules["unit_normalizer_pbt"] = _normalizer_module
_normalizer_spec.loader.exec_module(_normalizer_module)

normalize_value = _normalizer_module.normalize_value
normalize_metric_record = _normalizer_module.normalize_metric_record
NormalizationResult = _normalizer_module.NormalizationResult
get_target_unit = _normalizer_module.get_target_unit
get_supported_categories = _normalizer_module.get_supported_categories
UNIT_NORMALIZATION = _normalizer_module.UNIT_NORMALIZATION

# 有効なターゲット単位セット
VALID_TARGET_UNITS = frozenset({"tCO2e", "MWh", "t", "m3"})

# 全カテゴリ
ALL_CATEGORIES = list(UNIT_NORMALIZATION.keys())

# カテゴリごとの有効なソース単位を構築
CATEGORY_SOURCE_UNITS: dict[str, list[str]] = {}
for cat, config in UNIT_NORMALIZATION.items():
    CATEGORY_SOURCE_UNITS[cat] = list(config["conversions"].keys()) + [config["target"]]


# =========================================================================
# Property 1: Target units always in defined set
# =========================================================================
# **Validates: Requirements 13.3**


@settings(max_examples=200)
@given(
    category=st.sampled_from(ALL_CATEGORIES),
    value=st.floats(min_value=0.0, max_value=1e6, allow_nan=False, allow_infinity=False),
)
def test_target_unit_in_defined_set(category: str, value: float):
    """正規化結果の target unit は常に {tCO2e, MWh, t, m3} のいずれか。

    **Validates: Requirements 13.3**

    プロパティ: get_target_unit(category) ∈ {tCO2e, MWh, t, m3}
    """
    target = get_target_unit(category)
    assert target in VALID_TARGET_UNITS


@settings(max_examples=200)
@given(
    category=st.sampled_from(ALL_CATEGORIES),
    value=st.floats(min_value=-1e8, max_value=1e8, allow_nan=False, allow_infinity=False),
    unit=st.one_of(
        st.none(),
        st.text(min_size=0, max_size=10),
    ),
)
def test_normalize_result_unit_always_valid_or_unknown(
    category: str, value: float, unit: str | None
):
    """normalize_value の返却 unit は常に定義済み or "unknown"。

    **Validates: Requirements 13.3**

    プロパティ: result.unit ∈ VALID_TARGET_UNITS ∪ {"unknown"}
    """
    result = normalize_value(value, unit, category)
    assert result.unit in VALID_TARGET_UNITS | {"unknown"}


# =========================================================================
# Property 2: normalize_value always returns NormalizationResult
# =========================================================================
# **Validates: Requirements 13.3**


@settings(max_examples=200)
@given(
    category=st.sampled_from(ALL_CATEGORIES),
    value=st.floats(min_value=-1e8, max_value=1e8, allow_nan=False, allow_infinity=False),
    unit=st.one_of(
        st.none(),
        st.just(""),
        st.sampled_from(["kg", "kWh", "L", "t", "GWh", "GJ", "Mt", "kL", "ML", "tCO2e", "MWh", "m3"]),
        st.text(min_size=1, max_size=10),
    ),
)
def test_normalize_always_returns_normalization_result(
    category: str, value: float, unit: str | None
):
    """normalize_value は常に NormalizationResult を返す。

    **Validates: Requirements 13.3**

    プロパティ: isinstance(result, NormalizationResult)
    """
    result = normalize_value(value, unit, category)
    assert isinstance(result, NormalizationResult)
    assert result.status in ("success", "requires-validation")
    assert result.original_value == value
    assert result.original_unit == unit


@settings(max_examples=200)
@given(
    value=st.floats(min_value=-1e8, max_value=1e8, allow_nan=False, allow_infinity=False),
    unit=st.text(min_size=0, max_size=10),
    category=st.text(min_size=1, max_size=20),
)
def test_normalize_unknown_category_returns_requires_validation(
    value: float, unit: str, category: str
):
    """未知のカテゴリに対しては status="requires-validation" を返す。

    **Validates: Requirements 13.3**

    プロパティ: unknown category → requires-validation
    """
    if category in ALL_CATEGORIES:
        return  # skip known categories
    result = normalize_value(value, unit, category)
    assert result.status == "requires-validation"
    assert result.reason == "unknown_category"


@settings(max_examples=200)
@given(
    category=st.sampled_from(ALL_CATEGORIES),
    value=st.floats(min_value=0.001, max_value=1e5, allow_nan=False, allow_infinity=False),
)
def test_normalize_valid_unit_returns_success(category: str, value: float):
    """有効な単位のカテゴリで正常範囲値なら status="success" を返す。

    **Validates: Requirements 13.3**

    プロパティ: valid unit + in-range → success
    """
    source_units = list(UNIT_NORMALIZATION[category]["conversions"].keys())
    if not source_units:
        return
    # Pick first valid unit
    unit = source_units[0]
    result = normalize_value(value, unit, category)
    # Result is either success or out_of_range (for very large converted values)
    assert result.status in ("success", "requires-validation")
    if result.status == "requires-validation":
        assert result.reason == "out_of_range"


# =========================================================================
# Property 3: Metric record schema completeness
# =========================================================================
# **Validates: Requirements 13.3**


@settings(max_examples=200)
@given(
    value=st.one_of(
        st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
        st.integers(min_value=-1000000, max_value=1000000),
    ),
    unit=st.one_of(st.none(), st.text(min_size=0, max_size=10)),
    category=st.one_of(st.none(), st.sampled_from(ALL_CATEGORIES)),
)
def test_metric_record_always_has_normalization_fields(
    value, unit, category
):
    """normalize_metric_record は常に正規化フィールドを持つ辞書を返す。

    **Validates: Requirements 13.3**

    プロパティ: 出力には normalized_value, normalized_unit,
    normalization_status, normalization_reason が含まれる
    """
    record = {"value": value, "unit": unit, "category": category}
    result = normalize_metric_record(record)
    assert "normalized_value" in result
    assert "normalized_unit" in result
    assert "normalization_status" in result
    assert "normalization_reason" in result
    assert result["normalization_status"] in ("success", "requires-validation")
