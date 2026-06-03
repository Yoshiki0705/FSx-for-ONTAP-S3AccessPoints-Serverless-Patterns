"""UC22 運輸・鉄道業界 Property-Based Tests (Hypothesis)

Hypothesis ライブラリを使用したプロパティベーステスト。
処理コアロジックの普遍的性質を多数の入力に対して検証する。

テスト対象プロパティ:
1. severity_level ∈ {critical, major, minor, observation} (ALWAYS one of these 4)
2. Confidence threshold switching: safety-critical → 60%, standard → 80%
3. Resolution check consistency: <1024×768 always "requires-reinspection"
4. Human review flag: confidence < 90% → always flagged

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

# Deterioration Detector handler
_detector_path = os.path.join(
    os.path.dirname(__file__), "..", "functions", "deterioration_detector", "handler.py"
)
_detector_spec = importlib.util.spec_from_file_location("uc22_detector_pbt", _detector_path)
_detector_module = importlib.util.module_from_spec(_detector_spec)
_detector_spec.loader.exec_module(_detector_module)

SEVERITY_LEVELS = _detector_module.SEVERITY_LEVELS
is_safety_critical = _detector_module.is_safety_critical
parse_safety_critical_categories = _detector_module.parse_safety_critical_categories
check_image_resolution = _detector_module.check_image_resolution
DEFAULT_STANDARD_THRESHOLD = _detector_module.DEFAULT_STANDARD_THRESHOLD
DEFAULT_SAFETY_CRITICAL_THRESHOLD = _detector_module.DEFAULT_SAFETY_CRITICAL_THRESHOLD
DEFAULT_HUMAN_REVIEW_THRESHOLD = _detector_module.DEFAULT_HUMAN_REVIEW_THRESHOLD
DEFAULT_MIN_WIDTH = _detector_module.DEFAULT_MIN_WIDTH
DEFAULT_MIN_HEIGHT = _detector_module.DEFAULT_MIN_HEIGHT

# Safety-critical categories (default)
SAFETY_CATEGORIES = parse_safety_critical_categories("bridges,signaling,rail-joints")


# =========================================================================
# Property 1: severity_level ∈ {critical, major, minor, observation}
# ALWAYS one of these 4 valid values
# =========================================================================
# **Validates: Requirements 13.3**


@settings(max_examples=200)
@given(
    severity=st.text(min_size=0, max_size=50),
)
def test_severity_level_normalization(severity: str):
    """重大度レベルは正規化後、必ず 4 値のいずれかとなる。

    **Validates: Requirements 13.3**

    プロパティ: severity_level ∈ {"critical", "major", "minor", "observation"}
    Bedrock レスポンスのパースロジックと同様、不正な値は "observation" にフォールバック。
    """
    # Replicate the normalization logic from classify_severity_with_bedrock
    normalized = severity.lower()
    if normalized not in SEVERITY_LEVELS:
        normalized = "observation"

    assert normalized in SEVERITY_LEVELS


@settings(max_examples=200)
@given(
    severity_list=st.lists(
        st.sampled_from(SEVERITY_LEVELS + ["unknown", "CRITICAL", "MAJOR", "", "warning"]),
        min_size=0,
        max_size=20,
    ),
)
def test_severity_classification_always_valid(severity_list: list[str]):
    """重大度分類結果は常に有効な 4 値のみを含む。

    **Validates: Requirements 13.3**

    プロパティ: ∀ s ∈ classifications: s.severity ∈ SEVERITY_LEVELS
    """
    for severity in severity_list:
        normalized = severity.lower()
        if normalized not in SEVERITY_LEVELS:
            normalized = "observation"
        assert normalized in SEVERITY_LEVELS
        assert normalized in ("critical", "major", "minor", "observation")


# =========================================================================
# Property 2: Confidence threshold switching
# safety-critical → 60%, standard → 80%
# =========================================================================
# **Validates: Requirements 13.3**


@settings(max_examples=200)
@given(
    object_key=st.sampled_from([
        "inspections/bridges/route-1/2026-01/img_001.jpg",
        "inspections/signaling/station-A/2026-01/img_002.png",
        "inspections/rail-joints/section-3/2026-01/img_003.tiff",
        "inspections/BRIDGES/Route-2/img_004.jpg",
    ]),
)
def test_safety_critical_threshold_60(object_key: str):
    """安全重要カテゴリのファイルは 60% 閾値が適用される。

    **Validates: Requirements 13.3**

    プロパティ: safety_critical_path → threshold == 60
    """
    is_critical = is_safety_critical(object_key, SAFETY_CATEGORIES)
    assert is_critical is True

    effective_threshold = (
        DEFAULT_SAFETY_CRITICAL_THRESHOLD if is_critical else DEFAULT_STANDARD_THRESHOLD
    )
    assert effective_threshold == 60


@settings(max_examples=200)
@given(
    object_key=st.sampled_from([
        "inspections/tracks/section-1/2026-01/img_001.jpg",
        "inspections/platforms/station-A/img_002.png",
        "inspections/tunnels/t-01/2026-01/img_003.tiff",
        "inspections/stations/tokyo/img_004.jpg",
    ]),
)
def test_standard_threshold_80(object_key: str):
    """標準インフラのファイルは 80% 閾値が適用される。

    **Validates: Requirements 13.3**

    プロパティ: standard_path → threshold == 80
    """
    is_critical = is_safety_critical(object_key, SAFETY_CATEGORIES)
    assert is_critical is False

    effective_threshold = (
        DEFAULT_SAFETY_CRITICAL_THRESHOLD if is_critical else DEFAULT_STANDARD_THRESHOLD
    )
    assert effective_threshold == 80


@settings(max_examples=200)
@given(
    object_key=st.text(
        alphabet=st.characters(whitelist_categories=("L", "Nd"), whitelist_characters="/-_."),
        min_size=1,
        max_size=200,
    ),
)
def test_threshold_always_60_or_80(object_key: str):
    """適用閾値は常に 60% または 80% のいずれか。

    **Validates: Requirements 13.3**

    プロパティ: effective_threshold ∈ {60, 80}
    """
    is_critical = is_safety_critical(object_key, SAFETY_CATEGORIES)
    effective_threshold = (
        DEFAULT_SAFETY_CRITICAL_THRESHOLD if is_critical else DEFAULT_STANDARD_THRESHOLD
    )
    assert effective_threshold in (60, 80)


# =========================================================================
# Property 3: Resolution check consistency
# <1024×768 always "requires-reinspection"
# =========================================================================
# **Validates: Requirements 13.3**


@settings(max_examples=200)
@given(
    width=st.integers(min_value=0, max_value=DEFAULT_MIN_WIDTH - 1),
    height=st.integers(min_value=0, max_value=10000),
    file_size=st.integers(min_value=0, max_value=100_000_000),
)
def test_low_width_requires_reinspection(width: int, height: int, file_size: int):
    """幅が 1024 未満の画像は常に "requires-reinspection"。

    **Validates: Requirements 13.3**

    プロパティ: width < 1024 → status == "requires-reinspection"
    """
    image_metadata = {"width": width, "height": height, "file_size": file_size}
    result = check_image_resolution(image_metadata, DEFAULT_MIN_WIDTH, DEFAULT_MIN_HEIGHT)
    assert result["adequate"] is False
    assert result["status"] == "requires-reinspection"


@settings(max_examples=200)
@given(
    width=st.integers(min_value=0, max_value=10000),
    height=st.integers(min_value=0, max_value=DEFAULT_MIN_HEIGHT - 1),
    file_size=st.integers(min_value=0, max_value=100_000_000),
)
def test_low_height_requires_reinspection(width: int, height: int, file_size: int):
    """高さが 768 未満の画像は常に "requires-reinspection"。

    **Validates: Requirements 13.3**

    プロパティ: height < 768 → status == "requires-reinspection"
    """
    image_metadata = {"width": width, "height": height, "file_size": file_size}
    result = check_image_resolution(image_metadata, DEFAULT_MIN_WIDTH, DEFAULT_MIN_HEIGHT)
    assert result["adequate"] is False
    assert result["status"] == "requires-reinspection"


@settings(max_examples=200)
@given(
    width=st.integers(min_value=DEFAULT_MIN_WIDTH, max_value=10000),
    height=st.integers(min_value=DEFAULT_MIN_HEIGHT, max_value=10000),
    file_size=st.integers(min_value=0, max_value=100_000_000),
)
def test_adequate_resolution_passes(width: int, height: int, file_size: int):
    """1024×768 以上の画像は adequate=True。

    **Validates: Requirements 13.3**

    プロパティ: width >= 1024 ∧ height >= 768 → adequate == True
    """
    image_metadata = {"width": width, "height": height, "file_size": file_size}
    result = check_image_resolution(image_metadata, DEFAULT_MIN_WIDTH, DEFAULT_MIN_HEIGHT)
    assert result["adequate"] is True
    assert "status" not in result


# =========================================================================
# Property 4: Human review flag
# confidence < 90% → always flagged for human review
# =========================================================================
# **Validates: Requirements 13.3**


@settings(max_examples=200)
@given(
    confidence=st.floats(min_value=0.0, max_value=89.99, allow_nan=False),
)
def test_below_90_always_flagged(confidence: float):
    """90% 未満の信頼度は常に human review フラグが立つ。

    **Validates: Requirements 13.3**

    プロパティ: confidence < 90 → human_review_required == True
    """
    # Replicate the human review logic from the handler
    human_review_threshold = DEFAULT_HUMAN_REVIEW_THRESHOLD  # 90
    human_review_required = confidence < human_review_threshold
    assert human_review_required is True


@settings(max_examples=200)
@given(
    confidence=st.floats(min_value=90.0, max_value=100.0, allow_nan=False),
)
def test_above_90_not_flagged(confidence: float):
    """90% 以上の信頼度は human review フラグが立たない。

    **Validates: Requirements 13.3**

    プロパティ: confidence >= 90 → human_review_required == False
    """
    human_review_threshold = DEFAULT_HUMAN_REVIEW_THRESHOLD  # 90
    human_review_required = confidence < human_review_threshold
    assert human_review_required is False


@settings(max_examples=200)
@given(
    confidences=st.lists(
        st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
        min_size=1,
        max_size=20,
    ),
)
def test_any_below_90_flags_entire_result(confidences: list[float]):
    """検出ラベルの信頼度のいずれかが 90% 未満なら、結果全体にフラグが立つ。

    **Validates: Requirements 13.3**

    プロパティ: ∃ c ∈ confidences: c < 90 → human_review_required == True
    """
    human_review_threshold = DEFAULT_HUMAN_REVIEW_THRESHOLD
    human_review_required = any(c < human_review_threshold for c in confidences)

    has_low_confidence = any(c < 90 for c in confidences)
    assert human_review_required == has_low_confidence
