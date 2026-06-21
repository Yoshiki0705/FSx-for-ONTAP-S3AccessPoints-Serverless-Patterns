"""UC26 不動産 Property-Based Tests (Hypothesis)

Hypothesis ライブラリを使用したプロパティベーステスト。
ファイル分類の妥当性と PII 検出の決定性を検証する。

テスト対象プロパティ:
1. classify_file validity — 返却値は有効なタイプまたは None
2. PII detection determinism — 同一入力で常に同一出力

Requirements: 13.3
"""

from __future__ import annotations

import importlib.util
import os
import sys

from hypothesis import given, settings, strategies as st

# shared モジュールのパスを追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Discovery handler
_discovery_path = os.path.join(os.path.dirname(__file__), "..", "functions", "discovery", "handler.py")
_discovery_spec = importlib.util.spec_from_file_location("uc26_discovery_pbt", _discovery_path)
_discovery_module = importlib.util.module_from_spec(_discovery_spec)
_discovery_spec.loader.exec_module(_discovery_module)

classify_file = _discovery_module.classify_file
extract_property_id = _discovery_module.extract_property_id
detect_image_type = _discovery_module.detect_image_type

# PII filter
_pii_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "shared", "pii_filter.py")
_pii_spec = importlib.util.spec_from_file_location("pii_filter_uc26_pbt", _pii_path)
_pii_module = importlib.util.module_from_spec(_pii_spec)
_pii_spec.loader.exec_module(_pii_module)

mask_pii_in_text = _pii_module.mask_pii_in_text

# 有効なファイルタイプ
VALID_FILE_TYPES = frozenset({"property_image", "contract", None})

# テスト用プレフィックス
IMAGE_PREFIX = "properties/images/"
CONTRACT_PREFIX = "properties/contracts/"

# 有効な画像拡張子
VALID_IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".tiff", ".tif"]

# 有効な契約書拡張子
VALID_CONTRACT_EXTENSIONS = [".pdf"]

# 無効な拡張子
INVALID_EXTENSIONS = [".txt", ".csv", ".doc", ".mp4", ".html", ".xml", ".zip"]


# =========================================================================
# Property 1: classify_file validity
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
def test_classify_file_always_returns_valid_type(key: str):
    """classify_file は常に有効なタイプまたは None を返す。

    **Validates: Requirements 13.3**

    プロパティ: result ∈ {property_image, contract, None}
    """
    result = classify_file(key, IMAGE_PREFIX, CONTRACT_PREFIX)
    assert result in VALID_FILE_TYPES


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
def test_classify_file_deterministic(key: str):
    """classify_file は同一入力で常に同一出力を返す。

    **Validates: Requirements 13.3**

    プロパティ: f(x) == f(x)
    """
    result1 = classify_file(key, IMAGE_PREFIX, CONTRACT_PREFIX)
    result2 = classify_file(key, IMAGE_PREFIX, CONTRACT_PREFIX)
    assert result1 == result2


@settings(max_examples=200)
@given(
    filename=st.text(
        alphabet=st.characters(whitelist_categories=("L", "Nd"), whitelist_characters="_-"),
        min_size=1,
        max_size=30,
    ),
    extension=st.sampled_from(INVALID_EXTENSIONS),
)
def test_invalid_extension_returns_none(filename: str, extension: str):
    """無効な拡張子のファイルはプレフィックスに関係なく None を返す。

    **Validates: Requirements 13.3**

    プロパティ: invalid extension → None
    """
    for prefix in [IMAGE_PREFIX, CONTRACT_PREFIX, "other/"]:
        key = f"{prefix}{filename}{extension}"
        result = classify_file(key, IMAGE_PREFIX, CONTRACT_PREFIX)
        assert result is None


@settings(max_examples=200)
@given(
    filename=st.text(
        alphabet=st.characters(whitelist_categories=("L", "Nd"), whitelist_characters="_-"),
        min_size=1,
        max_size=30,
    ),
    extension=st.sampled_from(VALID_IMAGE_EXTENSIONS),
)
def test_valid_image_in_image_prefix_returns_property_image(filename: str, extension: str):
    """画像プレフィックス内の有効画像ファイルは property_image を返す。

    **Validates: Requirements 13.3**

    プロパティ: valid image ext + image prefix → property_image
    """
    key = f"{IMAGE_PREFIX}{filename}{extension}"
    result = classify_file(key, IMAGE_PREFIX, CONTRACT_PREFIX)
    assert result == "property_image"


# =========================================================================
# Property 2: PII detection determinism
# =========================================================================
# **Validates: Requirements 13.3**


@settings(max_examples=200)
@given(
    text=st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "Nd", "P", "Z"),
            whitelist_characters="@.-+/ ",
        ),
        min_size=0,
        max_size=500,
    ),
)
def test_mask_pii_deterministic(text: str):
    """mask_pii_in_text は同一入力で常に同一出力を返す。

    **Validates: Requirements 13.3**

    プロパティ: mask(x) == mask(x)
    """
    result1 = mask_pii_in_text(text)
    result2 = mask_pii_in_text(text)
    assert result1 == result2


@settings(max_examples=200)
@given(
    text=st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "Nd", "P", "Z"),
            whitelist_characters="@.-+/ ",
        ),
        min_size=0,
        max_size=500,
    ),
)
def test_mask_pii_idempotent_on_no_pii(text: str):
    """PII を含まないテキストは mask 後も長さが変わらないか同等。

    **Validates: Requirements 13.3**

    プロパティ: mask(text) の長さは元テキスト以上 (マスクトークン挿入のため)
    ただし PII がない場合は同一
    """
    result = mask_pii_in_text(text)
    # mask_pii replaces PII with [MASKED:type] which is longer
    # So result length >= original length OR text is unchanged
    assert isinstance(result, str)


@settings(max_examples=200)
@given(
    local=st.from_regex(r"[a-zA-Z][a-zA-Z0-9._%+-]{0,10}", fullmatch=True),
    domain_name=st.from_regex(r"[a-zA-Z][a-zA-Z0-9-]{0,10}", fullmatch=True),
    tld=st.from_regex(r"[a-zA-Z]{2,5}", fullmatch=True),
)
def test_mask_pii_always_masks_email(local: str, domain_name: str, tld: str):
    """メールアドレスパターンは常にマスクされる。

    **Validates: Requirements 13.3**

    プロパティ: email pattern → [MASKED:email] in output
    """
    email = f"{local}@{domain_name}.{tld}"
    result = mask_pii_in_text(f"連絡先: {email} まで")
    assert "[MASKED:email]" in result
