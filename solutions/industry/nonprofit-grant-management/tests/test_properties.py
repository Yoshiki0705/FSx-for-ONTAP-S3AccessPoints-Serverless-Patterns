"""UC24 NPO・非営利団体 Property-Based Tests (Hypothesis)

Hypothesis ライブラリを使用したプロパティベーステスト。
ファイル分類ロジックの決定性と不明フォーマット時の挙動を検証する。

テスト対象プロパティ:
1. classify_file determinism — 同一入力で常に同一出力
2. Unrecognized formats always return None

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

# Discovery handler
_discovery_path = os.path.join(os.path.dirname(__file__), "..", "functions", "discovery", "handler.py")
_discovery_spec = importlib.util.spec_from_file_location("uc24_discovery_pbt", _discovery_path)
_discovery_module = importlib.util.module_from_spec(_discovery_spec)
_discovery_spec.loader.exec_module(_discovery_module)

classify_file = _discovery_module.classify_file
extract_program_area = _discovery_module.extract_program_area
extract_submission_date = _discovery_module.extract_submission_date

# 有効なドキュメントタイプ
VALID_DOC_TYPES = frozenset({"grant_application", "activity_report", None})

# テスト用プレフィックス
GRANT_PREFIX = "grant-applications/"
REPORT_PREFIX = "activity-reports/"

# 有効な拡張子
VALID_EXTENSIONS = [".pdf", ".docx", ".doc"]

# 無効な拡張子
INVALID_EXTENSIONS = [
    ".txt",
    ".csv",
    ".xlsx",
    ".jpg",
    ".png",
    ".mp4",
    ".html",
    ".xml",
    ".json",
    ".pptx",
    ".zip",
]


# =========================================================================
# Property 1: classify_file determinism
# 同一入力は常に同一出力を生成する
# =========================================================================
# **Validates: Requirements 13.3**


@settings(max_examples=200)
@given(
    key=st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "Nd", "P"),
            whitelist_characters="/.-_",
        ),
        min_size=0,
        max_size=200,
    ),
)
def test_classify_file_determinism(key: str):
    """classify_file は同一入力に対して常に同一出力を返す。

    **Validates: Requirements 13.3**

    プロパティ: classify_file(k, p1, p2) == classify_file(k, p1, p2)
    """
    result1 = classify_file(key, GRANT_PREFIX, REPORT_PREFIX)
    result2 = classify_file(key, GRANT_PREFIX, REPORT_PREFIX)
    assert result1 == result2


@settings(max_examples=200)
@given(
    key=st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "Nd", "P"),
            whitelist_characters="/.-_",
        ),
        min_size=0,
        max_size=200,
    ),
)
def test_classify_file_returns_valid_type(key: str):
    """classify_file は常に有効なドキュメントタイプまたは None を返す。

    **Validates: Requirements 13.3**

    プロパティ: result ∈ {grant_application, activity_report, None}
    """
    result = classify_file(key, GRANT_PREFIX, REPORT_PREFIX)
    assert result in VALID_DOC_TYPES


# =========================================================================
# Property 2: Unrecognized formats always return None
# =========================================================================
# **Validates: Requirements 13.3**


@settings(max_examples=200)
@given(
    filename=st.text(
        alphabet=st.characters(whitelist_categories=("L", "Nd"), whitelist_characters="_-"),
        min_size=1,
        max_size=30,
    ),
    extension=st.sampled_from(INVALID_EXTENSIONS),
    prefix=st.sampled_from([GRANT_PREFIX, REPORT_PREFIX, "other/"]),
)
def test_unrecognized_format_returns_none(filename: str, extension: str, prefix: str):
    """未対応拡張子のファイルは常に None を返す。

    **Validates: Requirements 13.3**

    プロパティ: unsupported extension → None
    """
    key = f"{prefix}{filename}{extension}"
    result = classify_file(key, GRANT_PREFIX, REPORT_PREFIX)
    assert result is None


@settings(max_examples=200)
@given(
    filename=st.text(
        alphabet=st.characters(whitelist_categories=("L", "Nd"), whitelist_characters="_-"),
        min_size=1,
        max_size=30,
    ),
)
def test_no_extension_returns_none(filename: str):
    """拡張子のないファイルは常に None を返す。

    **Validates: Requirements 13.3**

    プロパティ: no extension → None
    """
    key = f"{GRANT_PREFIX}{filename}"
    result = classify_file(key, GRANT_PREFIX, REPORT_PREFIX)
    assert result is None


@settings(max_examples=200)
@given(
    filename=st.text(
        alphabet=st.characters(whitelist_categories=("L", "Nd"), whitelist_characters="_-"),
        min_size=1,
        max_size=30,
    ),
    extension=st.sampled_from(VALID_EXTENSIONS),
)
def test_valid_extension_wrong_prefix_returns_none(filename: str, extension: str):
    """有効な拡張子でもプレフィックスが一致しない場合は None を返す。

    **Validates: Requirements 13.3**

    プロパティ: valid ext + wrong prefix → None
    """
    key = f"unknown-prefix/{filename}{extension}"
    result = classify_file(key, GRANT_PREFIX, REPORT_PREFIX)
    assert result is None


@settings(max_examples=200)
@given(
    filename=st.text(
        alphabet=st.characters(whitelist_categories=("L", "Nd"), whitelist_characters="_-"),
        min_size=1,
        max_size=30,
    ),
    extension=st.sampled_from(VALID_EXTENSIONS),
)
def test_valid_extension_correct_prefix_returns_type(filename: str, extension: str):
    """有効な拡張子 + 正しいプレフィックスなら必ずドキュメントタイプを返す。

    **Validates: Requirements 13.3**

    プロパティ: valid ext + correct prefix → not None
    """
    key = f"{GRANT_PREFIX}{filename}{extension}"
    result = classify_file(key, GRANT_PREFIX, REPORT_PREFIX)
    assert result == "grant_application"

    key2 = f"{REPORT_PREFIX}{filename}{extension}"
    result2 = classify_file(key2, GRANT_PREFIX, REPORT_PREFIX)
    assert result2 == "activity_report"
