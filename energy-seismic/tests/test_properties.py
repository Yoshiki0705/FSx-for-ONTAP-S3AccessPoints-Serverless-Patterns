"""Property-Based Tests for UC8: エネルギー / 石油・ガス（地震探査データ処理）

Hypothesis を使用したプロパティベーステスト。
SEG-Y メタデータ抽出および坑井ログ異常検知 Lambda の不変条件（invariants）を任意入力で検証する。

Testing Strategy:
- 最小 100 イテレーション/プロパティ
- 各テストにプロパティ番号タグを付与
- タグ形式: Feature: fsxn-s3ap-serverless-patterns-phase2, Property {number}: {property_text}
"""

from __future__ import annotations

import math
import os
import struct
import sys

from hypothesis import given, settings, strategies as st

# shared モジュールと UC8 関数のパスを追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from functions.seismic_metadata.handler import _parse_binary_header
from functions.anomaly_detection.handler import _detect_anomalies


# ---------------------------------------------------------------------------
# Helper: SEG-Y バイナリヘッダー構築
# ---------------------------------------------------------------------------


def build_segy_binary_header(
    sample_interval: int,
    trace_count: int,
    data_format_code: int,
    samples_per_trace: int = 1000,
    measurement_system: int = 1,
) -> bytes:
    """テスト用の有効な SEG-Y バイナリヘッダー (400 bytes) を構築する

    SEG-Y バイナリヘッダーのフィールド配置（ビッグエンディアン）:
        - Offset 12-13: データトレース数/アンサンブル (int16)
        - Offset 16-17: サンプル間隔（マイクロ秒） (int16)
        - Offset 20-21: データトレースあたりのサンプル数 (int16)
        - Offset 24-25: データサンプルフォーマットコード (int16)
        - Offset 54-55: 測定系 (int16): 1=meters, 2=feet

    Args:
        sample_interval: サンプル間隔（マイクロ秒）
        trace_count: トレース数
        data_format_code: データフォーマットコード
        samples_per_trace: トレースあたりのサンプル数
        measurement_system: 測定系 (1=meters, 2=feet)

    Returns:
        bytes: 400 バイトの SEG-Y バイナリヘッダー
    """
    # 400 バイトのゼロ初期化バッファ
    header = bytearray(400)

    # Offset 12-13: trace_count (int16, big-endian)
    struct.pack_into(">h", header, 12, trace_count)

    # Offset 16-17: sample_interval (int16, big-endian)
    struct.pack_into(">h", header, 16, sample_interval)

    # Offset 20-21: samples_per_trace (int16, big-endian)
    struct.pack_into(">h", header, 20, samples_per_trace)

    # Offset 24-25: data_format_code (int16, big-endian)
    struct.pack_into(">h", header, 24, data_format_code)

    # Offset 54-55: measurement_system (int16, big-endian)
    struct.pack_into(">h", header, 54, measurement_system)

    return bytes(header)


# ---------------------------------------------------------------------------
# Property 10: SEG-Y binary header parsing
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    sample_interval=st.integers(min_value=1, max_value=32767),
    trace_count=st.integers(min_value=1, max_value=32767),
    data_format_code=st.integers(min_value=1, max_value=5),
)
def test_segy_binary_header_parsing(sample_interval, trace_count, data_format_code):
    """Feature: fsxn-s3ap-serverless-patterns-phase2, Property 10: SEG-Y binary header parsing

    For any valid SEG-Y binary file header (3600 bytes: 3200-byte textual
    header + 400-byte binary header), the Seismic_Metadata_Lambda SHALL
    extract sample_interval, trace_count, and data_format_code from the
    binary header, and the extracted values SHALL match the encoded values
    in the input bytes.

    Strategy: Generate valid SEG-Y binary headers with random sample_interval,
    trace_count, and data_format_code values using struct.pack, then verify
    the parser extracts them correctly.

    **Validates: Requirements 5.2**
    """
    # Build a valid SEG-Y binary header with the given values
    binary_header = build_segy_binary_header(
        sample_interval=sample_interval,
        trace_count=trace_count,
        data_format_code=data_format_code,
    )

    # Parse the binary header using the actual handler function
    result = _parse_binary_header(binary_header)

    # Verify all required fields are present
    assert "sample_interval" in result
    assert "trace_count" in result
    assert "data_format_code" in result
    assert "measurement_system" in result
    assert "samples_per_trace" in result

    # Verify extracted values match the encoded input values
    assert result["sample_interval"] == sample_interval, (
        f"Expected sample_interval={sample_interval}, got {result['sample_interval']}"
    )
    assert result["trace_count"] == trace_count, (
        f"Expected trace_count={trace_count}, got {result['trace_count']}"
    )
    assert result["data_format_code"] == data_format_code, (
        f"Expected data_format_code={data_format_code}, got {result['data_format_code']}"
    )

    # Verify measurement_system is a valid string
    assert result["measurement_system"] in ("meters", "feet", "unknown")


# ---------------------------------------------------------------------------
# Property 11: Anomaly detection threshold correctness
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    readings=st.lists(
        st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False),
        min_size=10,
        max_size=200,
    ),
    threshold_std=st.floats(min_value=1.0, max_value=5.0),
)
def test_anomaly_detection_threshold(readings, threshold_std):
    """Feature: fsxn-s3ap-serverless-patterns-phase2, Property 11: Anomaly detection threshold correctness

    For any set of sensor readings and any configurable standard deviation
    threshold N, the Anomaly_Detection_Lambda SHALL flag exactly those
    readings whose value exceeds N standard deviations from the mean, and
    SHALL NOT flag readings within N standard deviations.

    Strategy: Generate random sensor readings and threshold values, run
    _detect_anomalies, verify that flagged values are exactly those
    exceeding the threshold.

    **Validates: Requirements 5.4**
    """
    # Build input in the format expected by _detect_anomalies:
    # curve_names: ["DEPT", "SENSOR"]
    # data_rows: [[depth, value], ...]
    curve_names = ["DEPT", "SENSOR"]
    data_rows = [[float(i), reading] for i, reading in enumerate(readings)]

    # Run anomaly detection
    anomalies = _detect_anomalies(curve_names, data_rows, threshold_std)

    # Calculate expected anomalies using the same algorithm as the handler:
    # Uses sample standard deviation (N-1 denominator)
    valid_values = [r for r in readings if not math.isnan(r)]

    if len(valid_values) < 2:
        # Not enough data for statistics - no anomalies expected
        assert anomalies == []
        return

    mean = sum(valid_values) / len(valid_values)
    variance = sum((v - mean) ** 2 for v in valid_values) / (len(valid_values) - 1)
    std_dev = math.sqrt(variance)

    if std_dev == 0:
        # All values are the same - no anomalies possible
        assert anomalies == []
        return

    threshold_value = threshold_std * std_dev

    # Determine which readings should be flagged
    expected_anomaly_values = set()
    for reading in readings:
        if not math.isnan(reading):
            deviation = abs(reading - mean)
            if deviation > threshold_value:
                expected_anomaly_values.add(round(reading, 1))

    # Get actual flagged values from the anomaly detection result
    actual_anomaly_values = {a["value"] for a in anomalies}

    # Verify: all expected anomalies are flagged
    for expected_val in expected_anomaly_values:
        assert expected_val in actual_anomaly_values, (
            f"Expected anomaly value {expected_val} not found in results. "
            f"mean={mean:.2f}, std={std_dev:.2f}, threshold={threshold_value:.2f}"
        )

    # Verify: no non-anomalous values are flagged
    for anomaly in anomalies:
        val = anomaly["value"]
        # Find the original reading that corresponds to this rounded value
        # The value should exceed the threshold
        deviation = abs(val - round(mean, 1))
        # Use a slightly relaxed check due to rounding
        # The actual check in the handler uses unrounded values
        assert val in expected_anomaly_values, (
            f"Unexpected anomaly flagged: value={val}, "
            f"mean={mean:.2f}, std={std_dev:.2f}, threshold={threshold_value:.2f}"
        )
