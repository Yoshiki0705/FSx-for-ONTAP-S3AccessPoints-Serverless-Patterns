"""UC27 人材・HR Property-Based Tests (Hypothesis)

Hypothesis ライブラリを使用したプロパティベーステスト。
PII フィルタが保護特性を確実に除外し、スコアリング除外プロンプトが
常に生成されることを検証する。

テスト対象プロパティ:
1. PII filter removes protected characteristics — 出力に保護特性キーなし
2. Scoring exclusion prompt always generated — プロンプトは常に非空文字列

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

# PII filter モジュール
_pii_path = os.path.join(os.path.dirname(__file__), "..", "..", "shared", "pii_filter.py")
_pii_spec = importlib.util.spec_from_file_location("pii_filter_uc27_pbt", _pii_path)
_pii_module = importlib.util.module_from_spec(_pii_spec)
_pii_spec.loader.exec_module(_pii_module)

PiiFilter = _pii_module.PiiFilter
PROTECTED_CHARACTERISTICS = _pii_module.PROTECTED_CHARACTERISTICS
mask_pii_in_text = _pii_module.mask_pii_in_text

# 保護特性キー (正規化済み)
PROTECTED_KEYS_NORMALIZED = list(PROTECTED_CHARACTERISTICS)

# テスト用の非保護キー
NON_PROTECTED_KEYS = [
    "skills", "experience_years", "education", "certifications",
    "languages", "projects", "references", "summary",
    "job_title", "company", "department", "email",
]


# =========================================================================
# Property 1: PII filter removes protected characteristics
# =========================================================================
# **Validates: Requirements 13.3**


@settings(max_examples=200)
@given(
    protected_key=st.sampled_from(PROTECTED_KEYS_NORMALIZED),
    protected_value=st.text(min_size=1, max_size=50),
    extra_data=st.dictionaries(
        keys=st.sampled_from(NON_PROTECTED_KEYS),
        values=st.text(min_size=1, max_size=50),
        min_size=0,
        max_size=5,
    ),
)
def test_protected_characteristics_always_removed(
    protected_key: str, protected_value: str, extra_data: dict
):
    """保護特性キーは出力から常に除外される。

    **Validates: Requirements 13.3**

    プロパティ: ∀ key ∈ PROTECTED_CHARACTERISTICS:
        key ∉ remove_protected_characteristics({key: val, ...}).keys()
    """
    pii_filter = PiiFilter(mode="strict")
    data = {**extra_data, protected_key: protected_value}
    result = pii_filter.remove_protected_characteristics(data)
    # Protected key must not be in output
    assert protected_key not in result
    # Non-protected keys should still be present
    for k in extra_data:
        assert k in result


@settings(max_examples=200)
@given(
    data=st.dictionaries(
        keys=st.sampled_from(PROTECTED_KEYS_NORMALIZED + NON_PROTECTED_KEYS),
        values=st.text(min_size=1, max_size=50),
        min_size=1,
        max_size=10,
    ),
)
def test_no_protected_keys_in_output(data: dict):
    """出力辞書に保護特性キーが一切含まれない。

    **Validates: Requirements 13.3**

    プロパティ: ∀ key ∈ result.keys(): key.lower() ∉ PROTECTED_CHARACTERISTICS
    """
    pii_filter = PiiFilter(mode="strict")
    result = pii_filter.remove_protected_characteristics(data)
    for key in result:
        key_normalized = key.lower().replace("-", "_").replace(" ", "_")
        assert key_normalized not in PROTECTED_CHARACTERISTICS


@settings(max_examples=200)
@given(
    data=st.dictionaries(
        keys=st.sampled_from(NON_PROTECTED_KEYS),
        values=st.text(min_size=1, max_size=50),
        min_size=0,
        max_size=8,
    ),
)
def test_non_protected_keys_preserved(data: dict):
    """非保護キーはフィルタ後も保持される。

    **Validates: Requirements 13.3**

    プロパティ: 非保護キーはそのまま出力に存在
    """
    pii_filter = PiiFilter(mode="strict")
    result = pii_filter.remove_protected_characteristics(data)
    for key, value in data.items():
        assert key in result
        assert result[key] == value


@settings(max_examples=200)
@given(
    protected_keys=st.lists(
        st.sampled_from(PROTECTED_KEYS_NORMALIZED),
        min_size=1,
        max_size=5,
        unique=True,
    ),
    value=st.text(min_size=1, max_size=20),
)
def test_multiple_protected_keys_all_removed(protected_keys: list[str], value: str):
    """複数の保護特性キーが同時に存在しても全て除去される。

    **Validates: Requirements 13.3**

    プロパティ: 複数保護キー → 全て除去
    """
    pii_filter = PiiFilter(mode="strict")
    data = {k: value for k in protected_keys}
    data["skills"] = "Python"  # non-protected
    result = pii_filter.remove_protected_characteristics(data)
    for key in protected_keys:
        assert key not in result
    assert "skills" in result


# =========================================================================
# Property 2: Scoring exclusion prompt always generated
# =========================================================================
# **Validates: Requirements 13.3**


def test_scoring_exclusion_prompt_always_non_empty():
    """スコアリング除外プロンプトは常に非空文字列。

    **Validates: Requirements 13.3**

    プロパティ: create_scoring_exclusion_prompt() は常に非空
    """
    pii_filter = PiiFilter(mode="strict")
    prompt = pii_filter.create_scoring_exclusion_prompt()
    assert isinstance(prompt, str)
    assert len(prompt) > 0


@settings(max_examples=50)
@given(
    mode=st.sampled_from(["strict", "standard"]),
)
def test_scoring_exclusion_prompt_independent_of_mode(mode: str):
    """スコアリング除外プロンプトはモードに関係なく生成される。

    **Validates: Requirements 13.3**

    プロパティ: mode に依存せず非空プロンプトを返す
    """
    pii_filter = PiiFilter(mode=mode)
    prompt = pii_filter.create_scoring_exclusion_prompt()
    assert isinstance(prompt, str)
    assert len(prompt) > 50  # Contains meaningful content


@settings(max_examples=50)
@given(
    mode=st.sampled_from(["strict", "standard"]),
)
def test_scoring_exclusion_prompt_mentions_protected_characteristics(mode: str):
    """スコアリング除外プロンプトは保護特性に言及する。

    **Validates: Requirements 13.3**

    プロパティ: プロンプトに age, gender, nationality が含まれる
    """
    pii_filter = PiiFilter(mode=mode)
    prompt = pii_filter.create_scoring_exclusion_prompt()
    # Must mention key protected characteristics
    assert "age" in prompt.lower() or "年齢" in prompt
    assert "gender" in prompt.lower() or "性別" in prompt
    assert "nationality" in prompt.lower() or "国籍" in prompt
