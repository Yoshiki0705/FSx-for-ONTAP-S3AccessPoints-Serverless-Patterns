"""UC20 旅行・ホスピタリティ Property-Based Tests (Hypothesis)

Hypothesis ライブラリを使用したプロパティベーステスト。
処理コアロジックの普遍的性質を多数の入力に対して検証する。

テスト対象プロパティ:
1. Cleanliness score bounds — 0 <= score <= 100
2. Structured data extraction determinism — 同一入力で同一出力
3. File classification consistency — classify_file は決定的

Requirements: 13.1, 13.2, 13.3, 13.4
"""

from __future__ import annotations

import importlib.util
import os
import sys

from hypothesis import given, settings, strategies as st

# shared モジュールのパスを追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Discovery handler — classify_file
_discovery_path = os.path.join(os.path.dirname(__file__), "..", "functions", "discovery", "handler.py")
_discovery_spec = importlib.util.spec_from_file_location("uc20_discovery_pbt", _discovery_path)
_discovery_module = importlib.util.module_from_spec(_discovery_spec)
_discovery_spec.loader.exec_module(_discovery_module)

classify_file = _discovery_module.classify_file
RESERVATION_DOC_EXTENSIONS = _discovery_module.RESERVATION_DOC_EXTENSIONS
FACILITY_IMAGE_EXTENSIONS = _discovery_module.FACILITY_IMAGE_EXTENSIONS

# Facility Inspector handler — calculate_cleanliness_score
_inspector_path = os.path.join(os.path.dirname(__file__), "..", "functions", "facility_inspector", "handler.py")
_inspector_spec = importlib.util.spec_from_file_location("uc20_inspector_pbt", _inspector_path)
_inspector_module = importlib.util.module_from_spec(_inspector_spec)
_inspector_spec.loader.exec_module(_inspector_module)

calculate_cleanliness_score = _inspector_module.calculate_cleanliness_score
CLEANLINESS_NEGATIVE_LABELS = _inspector_module.CLEANLINESS_NEGATIVE_LABELS
CLEANLINESS_POSITIVE_LABELS = _inspector_module.CLEANLINESS_POSITIVE_LABELS
DAMAGE_LABELS = _inspector_module.DAMAGE_LABELS


# =========================================================================
# Property 1: Cleanliness score bounds — 0 <= score <= 100
# =========================================================================
# **Validates: Requirements 13.3**


# Strategy: Generate Rekognition-like label dicts
rekognition_label_strategy = st.fixed_dictionaries(
    {
        "Name": st.sampled_from(
            list(CLEANLINESS_NEGATIVE_LABELS)
            + list(CLEANLINESS_POSITIVE_LABELS)
            + list(DAMAGE_LABELS)
            + ["Floor", "Wall", "Room", "Window", "Door", "Furniture"]
        ),
        "Confidence": st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
    }
)


@settings(max_examples=200)
@given(
    labels=st.lists(rekognition_label_strategy, min_size=0, max_size=30),
)
def test_cleanliness_score_bounds(labels: list[dict]):
    """清潔度スコアは常に 0 以上 100 以下。

    **Validates: Requirements 13.3**

    プロパティ: 0 <= calculate_cleanliness_score(labels) <= 100
    任意のラベル組み合わせに対してスコアがクランプされる。
    """
    score = calculate_cleanliness_score(labels)
    assert 0 <= score <= 100


@settings(max_examples=200)
@given(
    labels=st.lists(rekognition_label_strategy, min_size=0, max_size=30),
)
def test_cleanliness_score_is_integer(labels: list[dict]):
    """清潔度スコアは常に整数値。

    **Validates: Requirements 13.3**

    プロパティ: isinstance(score, int)
    """
    score = calculate_cleanliness_score(labels)
    assert isinstance(score, int)


@settings(max_examples=200)
@given(
    labels=st.lists(rekognition_label_strategy, min_size=0, max_size=30),
)
def test_cleanliness_score_determinism(labels: list[dict]):
    """清潔度スコアは決定的（同一入力で同一出力）。

    **Validates: Requirements 13.3**

    プロパティ: f(x) == f(x)
    """
    score1 = calculate_cleanliness_score(labels)
    score2 = calculate_cleanliness_score(labels)
    assert score1 == score2


# =========================================================================
# Property 2: Structured data extraction determinism
# classify_file は同一入力に対して常に同一結果を返す
# =========================================================================
# **Validates: Requirements 13.3**


# Strategy for file keys with known extensions
file_extension_strategy = st.sampled_from(
    [
        ".pdf",
        ".jpg",
        ".jpeg",
        ".png",
        ".tiff",
        ".tif",
        ".doc",
        ".txt",
        ".csv",
        ".mp4",
        "",
    ]
)


@settings(max_examples=200)
@given(
    prefix=st.sampled_from(["reservations/", "facility-inspections/", "other/"]),
    subpath=st.text(
        alphabet=st.characters(whitelist_categories=("L", "Nd"), whitelist_characters="/-_"),
        min_size=0,
        max_size=50,
    ),
    extension=file_extension_strategy,
)
def test_file_classification_determinism(prefix: str, subpath: str, extension: str):
    """ファイル分類は同一入力に対して常に同一結果を返す。

    **Validates: Requirements 13.3**

    プロパティ: classify_file(k, p1, p2) == classify_file(k, p1, p2)
    """
    key = prefix + subpath + ("file" if subpath and not subpath.endswith("/") else "") + extension
    reservation_prefix = "reservations/"
    facility_prefix = "facility-inspections/"

    result1 = classify_file(key, reservation_prefix, facility_prefix)
    result2 = classify_file(key, reservation_prefix, facility_prefix)
    assert result1 == result2


# =========================================================================
# Property 3: File classification consistency
# 分類結果は有効な値のみを返す
# =========================================================================
# **Validates: Requirements 13.3**


@settings(max_examples=200)
@given(
    key=st.text(
        alphabet=st.characters(whitelist_categories=("L", "Nd", "P"), whitelist_characters="/-_."),
        min_size=0,
        max_size=200,
    ),
)
def test_file_classification_valid_categories(key: str):
    """classify_file は None, "reservation_doc", "facility_image" のいずれかを返す。

    **Validates: Requirements 13.3**

    プロパティ: result ∈ {None, "reservation_doc", "facility_image"}
    """
    result = classify_file(key, "reservations/", "facility-inspections/")
    assert result in (None, "reservation_doc", "facility_image")


@settings(max_examples=200)
@given(
    filename=st.text(
        alphabet=st.characters(whitelist_categories=("L", "Nd"), whitelist_characters="-_"),
        min_size=1,
        max_size=30,
    ),
    extension=st.sampled_from(list(RESERVATION_DOC_EXTENSIONS)),
)
def test_reservation_prefix_with_valid_extension_classified(filename: str, extension: str):
    """予約文書プレフィックス + 有効拡張子は常に "reservation_doc" に分類される。

    **Validates: Requirements 13.3**

    プロパティ: reservations/ + valid_ext → "reservation_doc"
    """
    key = f"reservations/{filename}{extension}"
    result = classify_file(key, "reservations/", "facility-inspections/")
    assert result == "reservation_doc"


@settings(max_examples=200)
@given(
    filename=st.text(
        alphabet=st.characters(whitelist_categories=("L", "Nd"), whitelist_characters="-_"),
        min_size=1,
        max_size=30,
    ),
    extension=st.sampled_from(list(FACILITY_IMAGE_EXTENSIONS)),
)
def test_facility_prefix_with_valid_extension_classified(filename: str, extension: str):
    """施設点検プレフィックス + 有効拡張子は常に "facility_image" に分類される。

    **Validates: Requirements 13.3**

    プロパティ: facility-inspections/ + valid_ext → "facility_image"
    """
    key = f"facility-inspections/{filename}{extension}"
    result = classify_file(key, "reservations/", "facility-inspections/")
    assert result == "facility_image"
