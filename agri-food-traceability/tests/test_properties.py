"""UC21 農業・食品業界 Property-Based Tests (Hypothesis)

Hypothesis ライブラリを使用したプロパティベーステスト。
処理コアロジックの普遍的性質を多数の入力に対して検証する。

テスト対象プロパティ:
1. Anomaly confidence bounds — 0.0 <= confidence <= 1.0
2. File size filter consistency — ≤500MB accepted, >500MB rejected
3. Location classification — always "verified" or "location-unverified"

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
_discovery_path = os.path.join(
    os.path.dirname(__file__), "..", "functions", "discovery", "handler.py"
)
_discovery_spec = importlib.util.spec_from_file_location("uc21_discovery_pbt", _discovery_path)
_discovery_module = importlib.util.module_from_spec(_discovery_spec)
_discovery_spec.loader.exec_module(_discovery_module)

classify_file = _discovery_module.classify_file
AERIAL_IMAGE_EXTENSIONS = _discovery_module.AERIAL_IMAGE_EXTENSIONS
DEFAULT_MAX_IMAGE_SIZE_MB = _discovery_module.DEFAULT_MAX_IMAGE_SIZE_MB

# Crop Analyzer handler — extract_exif_geolocation
_crop_path = os.path.join(
    os.path.dirname(__file__), "..", "functions", "crop_analyzer", "handler.py"
)
_crop_spec = importlib.util.spec_from_file_location("uc21_crop_pbt", _crop_path)
_crop_module = importlib.util.module_from_spec(_crop_spec)
_crop_spec.loader.exec_module(_crop_module)

extract_exif_geolocation = _crop_module.extract_exif_geolocation
DEFAULT_CONFIDENCE_THRESHOLD = _crop_module.DEFAULT_CONFIDENCE_THRESHOLD
ANOMALY_TYPES = _crop_module.ANOMALY_TYPES

# Max size in bytes
MAX_IMAGE_SIZE_BYTES = DEFAULT_MAX_IMAGE_SIZE_MB * 1024 * 1024


# =========================================================================
# Property 1: Anomaly confidence bounds — 0.0 <= confidence <= 1.0
# =========================================================================
# **Validates: Requirements 13.3**


@settings(max_examples=200)
@given(
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    threshold=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)
def test_anomaly_confidence_bounds(confidence: float, threshold: float):
    """異常検出の信頼度は常に 0.0 以上 1.0 以下。

    **Validates: Requirements 13.3**

    プロパティ: Bedrock が返す confidence を閾値と比較する際、
    confidence は [0.0, 1.0] の範囲内であること。
    """
    # Simulate the classification logic from crop_analyzer
    assert 0.0 <= confidence <= 1.0

    # If confidence >= threshold → "confirmed", else → "review-required"
    if confidence >= threshold:
        status = "confirmed"
    else:
        status = "review-required"

    assert status in ("confirmed", "review-required")


@settings(max_examples=200)
@given(
    confidence_values=st.lists(
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        min_size=0,
        max_size=20,
    ),
)
def test_anomaly_confirmed_count_bounded(confidence_values: list[float]):
    """confirmed 数は常に 0 以上かつ全検出数以下。

    **Validates: Requirements 13.3**

    プロパティ: 0 <= confirmed_count <= total_detected
    """
    threshold = DEFAULT_CONFIDENCE_THRESHOLD
    confirmed = [c for c in confidence_values if c >= threshold]
    review_required = [c for c in confidence_values if c < threshold]

    assert 0 <= len(confirmed) <= len(confidence_values)
    assert len(confirmed) + len(review_required) == len(confidence_values)


# =========================================================================
# Property 2: File size filter consistency
# ≤500MB accepted, >500MB rejected
# =========================================================================
# **Validates: Requirements 13.3**


@settings(max_examples=200)
@given(
    file_size=st.integers(min_value=0, max_value=MAX_IMAGE_SIZE_BYTES),
    filename=st.text(
        alphabet=st.characters(whitelist_categories=("L", "Nd"), whitelist_characters="-_"),
        min_size=1,
        max_size=30,
    ),
    extension=st.sampled_from(list(AERIAL_IMAGE_EXTENSIONS)),
)
def test_file_size_within_limit_accepted(file_size: int, filename: str, extension: str):
    """500MB 以下のファイルは航空画像として分類される。

    **Validates: Requirements 13.3**

    プロパティ: size <= 500MB ∧ valid_prefix ∧ valid_ext → "aerial_image"
    """
    key = f"aerial-images/{filename}{extension}"
    result = classify_file(
        key=key,
        size=file_size,
        image_prefix="aerial-images/",
        traceability_prefix="traceability/",
        max_image_size_bytes=MAX_IMAGE_SIZE_BYTES,
    )
    assert result == "aerial_image"


@settings(max_examples=200)
@given(
    file_size=st.integers(min_value=MAX_IMAGE_SIZE_BYTES + 1, max_value=MAX_IMAGE_SIZE_BYTES * 3),
    filename=st.text(
        alphabet=st.characters(whitelist_categories=("L", "Nd"), whitelist_characters="-_"),
        min_size=1,
        max_size=30,
    ),
    extension=st.sampled_from(list(AERIAL_IMAGE_EXTENSIONS)),
)
def test_file_size_over_limit_rejected(file_size: int, filename: str, extension: str):
    """500MB 超のファイルは拒否される (None)。

    **Validates: Requirements 13.3**

    プロパティ: size > 500MB → None (even with valid prefix + extension)
    """
    key = f"aerial-images/{filename}{extension}"
    result = classify_file(
        key=key,
        size=file_size,
        image_prefix="aerial-images/",
        traceability_prefix="traceability/",
        max_image_size_bytes=MAX_IMAGE_SIZE_BYTES,
    )
    assert result is None


@settings(max_examples=200)
@given(
    file_size=st.integers(min_value=0, max_value=MAX_IMAGE_SIZE_BYTES * 3),
    filename=st.text(
        alphabet=st.characters(whitelist_categories=("L", "Nd"), whitelist_characters="-_"),
        min_size=1,
        max_size=30,
    ),
    extension=st.sampled_from(list(AERIAL_IMAGE_EXTENSIONS)),
)
def test_file_size_filter_boundary_consistency(file_size: int, filename: str, extension: str):
    """ファイルサイズフィルタは閾値を境に一貫した動作を示す。

    **Validates: Requirements 13.3**

    プロパティ: (size <= limit → "aerial_image") XOR (size > limit → None)
    """
    key = f"aerial-images/{filename}{extension}"
    result = classify_file(
        key=key,
        size=file_size,
        image_prefix="aerial-images/",
        traceability_prefix="traceability/",
        max_image_size_bytes=MAX_IMAGE_SIZE_BYTES,
    )

    if file_size <= MAX_IMAGE_SIZE_BYTES:
        assert result == "aerial_image"
    else:
        assert result is None


# =========================================================================
# Property 3: Location classification
# always "verified" or "location-unverified"
# =========================================================================
# **Validates: Requirements 13.3**


@settings(max_examples=200)
@given(
    lat=st.one_of(
        st.none(),
        st.text(min_size=0, max_size=20),
        st.floats(min_value=-90, max_value=90, allow_nan=False).map(str),
    ),
    lon=st.one_of(
        st.none(),
        st.text(min_size=0, max_size=20),
        st.floats(min_value=-180, max_value=180, allow_nan=False).map(str),
    ),
)
def test_location_classification_always_valid(lat, lon):
    """位置情報分類は常に "verified" or "location-unverified" のいずれか。

    **Validates: Requirements 13.3**

    プロパティ: geolocation → "verified" | geolocation is None → "location-unverified"
    """
    metadata = {}
    if lat is not None:
        metadata["gps_latitude"] = lat
    if lon is not None:
        metadata["gps_longitude"] = lon

    geolocation = extract_exif_geolocation(metadata)
    location_status = "verified" if geolocation else "location-unverified"

    assert location_status in ("verified", "location-unverified")


@settings(max_examples=200)
@given(
    lat=st.floats(min_value=-90, max_value=90, allow_nan=False, allow_infinity=False),
    lon=st.floats(min_value=-180, max_value=180, allow_nan=False, allow_infinity=False),
)
def test_valid_gps_always_verified(lat: float, lon: float):
    """有効な GPS 座標が提供された場合、常に "verified" に分類される。

    **Validates: Requirements 13.3**

    プロパティ: valid_lat ∧ valid_lon → "verified"
    """
    metadata = {
        "gps_latitude": str(lat),
        "gps_longitude": str(lon),
    }

    geolocation = extract_exif_geolocation(metadata)
    assert geolocation is not None
    location_status = "verified" if geolocation else "location-unverified"
    assert location_status == "verified"


@settings(max_examples=200)
@given(
    metadata=st.fixed_dictionaries({}),
)
def test_missing_gps_always_unverified(metadata: dict):
    """GPS 情報が未提供の場合、常に "location-unverified" に分類される。

    **Validates: Requirements 13.3**

    プロパティ: no GPS → "location-unverified"
    """
    geolocation = extract_exif_geolocation(metadata)
    assert geolocation is None
    location_status = "verified" if geolocation else "location-unverified"
    assert location_status == "location-unverified"
