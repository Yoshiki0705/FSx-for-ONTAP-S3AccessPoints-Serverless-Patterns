"""UC28 化学・素材 Property-Based Tests (Hypothesis)

Hypothesis ライブラリを使用したプロパティベーステスト。
GHS セクション検証の完全性と SDS 有効期限チェックの一貫性を検証する。

テスト対象プロパティ:
1. GHS section check completeness — 常に 8 セクション全てをチェック
2. SDS expiry check — >365 days → priority "critical"

Requirements: 13.3
"""

from __future__ import annotations

import importlib.util
import os
import sys
from datetime import datetime, timedelta, timezone

from hypothesis import given, settings, assume, strategies as st

# shared モジュールのパスを追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# SDS Extractor handler
_sds_path = os.path.join(os.path.dirname(__file__), "..", "functions", "sds_extractor", "handler.py")
_sds_spec = importlib.util.spec_from_file_location("sds_extractor_pbt", _sds_path)
_sds_module = importlib.util.module_from_spec(_sds_spec)
_sds_spec.loader.exec_module(_sds_module)

check_ghs_sections = _sds_module.check_ghs_sections
get_missing_ghs_sections = _sds_module.get_missing_ghs_sections
check_sds_expiry = _sds_module.check_sds_expiry
GHS_MANDATORY_SECTIONS = _sds_module.GHS_MANDATORY_SECTIONS

# GHS 必須セクション数
GHS_SECTION_COUNT = 8


# =========================================================================
# Property 1: GHS section check completeness
# 常に 8 セクション全てをチェックする
# =========================================================================
# **Validates: Requirements 13.3**


@settings(max_examples=200)
@given(
    text=st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "Nd", "Z", "P"),
        ),
        min_size=0,
        max_size=2000,
    ),
)
def test_ghs_check_always_returns_8_sections(text: str):
    """check_ghs_sections は常に 8 セクションの結果を返す。

    **Validates: Requirements 13.3**

    プロパティ: len(check_ghs_sections(text)) == 8
    """
    result = check_ghs_sections(text)
    assert len(result) == GHS_SECTION_COUNT


@settings(max_examples=200)
@given(
    text=st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "Nd", "Z", "P"),
        ),
        min_size=0,
        max_size=2000,
    ),
)
def test_ghs_check_keys_match_mandatory_sections(text: str):
    """check_ghs_sections の返却キーは GHS_MANDATORY_SECTIONS と一致する。

    **Validates: Requirements 13.3**

    プロパティ: result.keys() == set(GHS_MANDATORY_SECTIONS)
    """
    result = check_ghs_sections(text)
    assert set(result.keys()) == set(GHS_MANDATORY_SECTIONS)


@settings(max_examples=200)
@given(
    text=st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "Nd", "Z", "P"),
        ),
        min_size=0,
        max_size=2000,
    ),
)
def test_ghs_check_values_are_boolean(text: str):
    """check_ghs_sections の各値は bool 型。

    **Validates: Requirements 13.3**

    プロパティ: ∀ v ∈ result.values(): isinstance(v, bool)
    """
    result = check_ghs_sections(text)
    for section, found in result.items():
        assert isinstance(found, bool), f"{section} is not bool: {type(found)}"


@settings(max_examples=100)
@given(
    text=st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "Nd", "Z", "P"),
        ),
        min_size=0,
        max_size=2000,
    ),
)
def test_missing_sections_subset_of_mandatory(text: str):
    """get_missing_ghs_sections は GHS_MANDATORY_SECTIONS のサブセット。

    **Validates: Requirements 13.3**

    プロパティ: missing ⊆ GHS_MANDATORY_SECTIONS
    """
    ghs_check = check_ghs_sections(text)
    missing = get_missing_ghs_sections(ghs_check)
    assert set(missing).issubset(set(GHS_MANDATORY_SECTIONS))


def test_empty_text_all_sections_missing():
    """空テキストでは全 8 セクションが不足と判定される。

    **Validates: Requirements 13.3**

    プロパティ: check_ghs_sections("") → 全 False
    """
    result = check_ghs_sections("")
    assert all(not found for found in result.values())
    missing = get_missing_ghs_sections(result)
    assert len(missing) == GHS_SECTION_COUNT


# =========================================================================
# Property 2: SDS expiry check
# >365 days → priority "critical"
# =========================================================================
# **Validates: Requirements 13.3**


@settings(max_examples=200)
@given(
    days_ago=st.integers(min_value=366, max_value=3650),
)
def test_expired_sds_returns_critical_priority(days_ago: int):
    """365 日超過の SDS は常に priority="critical" を返す。

    **Validates: Requirements 13.3**

    プロパティ: days_since_revision > 365 → priority == "critical"
    """
    revision_date = (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%d")
    result = check_sds_expiry(revision_date, validity_days=365)
    assert result["is_expired"] is True
    assert result["priority"] == "critical"
    assert result["days_since_revision"] >= days_ago - 1  # Allow 1 day tolerance


@settings(max_examples=200)
@given(
    days_ago=st.integers(min_value=0, max_value=364),
)
def test_valid_sds_returns_no_priority(days_ago: int):
    """365 日以内の SDS は priority=None を返す。

    **Validates: Requirements 13.3**

    プロパティ: days_since_revision <= 365 → priority is None
    """
    revision_date = (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%d")
    result = check_sds_expiry(revision_date, validity_days=365)
    assert result["is_expired"] is False
    assert result["priority"] is None


@settings(max_examples=100)
@given(
    validity_days=st.integers(min_value=1, max_value=1000),
    days_ago=st.integers(min_value=0, max_value=2000),
)
def test_expiry_threshold_consistency(validity_days: int, days_ago: int):
    """有効期間と経過日数の関係が一貫している。

    **Validates: Requirements 13.3**

    プロパティ: days_ago > validity_days ↔ is_expired == True
    """
    revision_date = (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%d")
    result = check_sds_expiry(revision_date, validity_days=validity_days)

    # Allow 1-day tolerance due to time-of-day differences
    if days_ago > validity_days + 1:
        assert result["is_expired"] is True
    elif days_ago < validity_days - 1:
        assert result["is_expired"] is False


def test_none_revision_date_returns_not_expired():
    """revision_date が None の場合は期限切れではない。

    **Validates: Requirements 13.3**

    プロパティ: None → is_expired=False, priority=None
    """
    result = check_sds_expiry(None, validity_days=365)
    assert result["is_expired"] is False
    assert result["priority"] is None
    assert result["days_since_revision"] is None


@settings(max_examples=100)
@given(
    invalid_date=st.text(
        alphabet=st.characters(whitelist_categories=("L", "Nd", "P")),
        min_size=1,
        max_size=20,
    ),
)
def test_invalid_date_format_returns_not_expired(invalid_date: str):
    """無効な日付形式は期限切れ判定しない。

    **Validates: Requirements 13.3**

    プロパティ: invalid date format → is_expired=False
    """
    # Skip strings that happen to be valid YYYY-MM-DD
    try:
        datetime.strptime(invalid_date, "%Y-%m-%d")
        return  # Valid date, skip
    except ValueError:
        pass

    result = check_sds_expiry(invalid_date, validity_days=365)
    assert result["is_expired"] is False
    assert result["priority"] is None
