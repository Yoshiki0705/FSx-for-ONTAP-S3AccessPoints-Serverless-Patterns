"""UC25 電力・ユーティリティ Property-Based Tests (Hypothesis)

Hypothesis ライブラリを使用したプロパティベーステスト。
SCADA 閾値バウンドと欠陥重大度列挙の普遍的性質を検証する。

テスト対象プロパティ:
1. SCADA threshold bounds — 電圧/負荷/周波数の閾値判定が一貫
2. Defect severity enumeration — severity ∈ {critical, major, minor}

Requirements: 13.3
"""

from __future__ import annotations

import importlib.util
import os
import sys

from hypothesis import given, settings, assume, strategies as st

# shared モジュールのパスを追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# SCADA Analyzer
_scada_path = os.path.join(os.path.dirname(__file__), "..", "functions", "scada_analyzer", "handler.py")
_scada_spec = importlib.util.spec_from_file_location("scada_analyzer_pbt", _scada_path)
_scada_module = importlib.util.module_from_spec(_scada_spec)
_scada_spec.loader.exec_module(_scada_module)

check_voltage_anomaly = _scada_module.check_voltage_anomaly
check_load_imbalance = _scada_module.check_load_imbalance
check_frequency_anomaly = _scada_module.check_frequency_anomaly
analyze_scada_records = _scada_module.analyze_scada_records

# Defect Detector
_defect_path = os.path.join(os.path.dirname(__file__), "..", "functions", "defect_detector", "handler.py")
_defect_spec = importlib.util.spec_from_file_location("defect_detector_pbt", _defect_path)
_defect_module = importlib.util.module_from_spec(_defect_spec)
_defect_spec.loader.exec_module(_defect_module)

VALID_SEVERITIES = _defect_module.VALID_SEVERITIES


# =========================================================================
# Property 1: SCADA threshold bounds — voltage
# =========================================================================
# **Validates: Requirements 13.3**


@settings(max_examples=200)
@given(
    voltage=st.floats(min_value=0.01, max_value=1000.0, allow_nan=False, allow_infinity=False),
    nominal=st.floats(min_value=0.01, max_value=1000.0, allow_nan=False, allow_infinity=False),
    threshold=st.floats(min_value=0.1, max_value=50.0, allow_nan=False, allow_infinity=False),
)
def test_voltage_anomaly_threshold_consistency(voltage: float, nominal: float, threshold: float):
    """電圧偏差が閾値以下なら anomaly は None。

    **Validates: Requirements 13.3**

    プロパティ: |voltage - nominal| / nominal * 100 <= threshold → None
    """
    deviation_percent = abs(voltage - nominal) / nominal * 100
    result = check_voltage_anomaly(voltage, nominal, threshold)

    if deviation_percent <= threshold:
        assert result is None
    else:
        assert result is not None
        assert result["anomaly_type"] == "voltage_deviation"
        assert result["severity"] in VALID_SEVERITIES


@settings(max_examples=200)
@given(
    voltage=st.floats(min_value=0.01, max_value=1000.0, allow_nan=False, allow_infinity=False),
    nominal=st.floats(min_value=0.01, max_value=1000.0, allow_nan=False, allow_infinity=False),
    threshold=st.floats(min_value=0.1, max_value=50.0, allow_nan=False, allow_infinity=False),
)
def test_voltage_anomaly_severity_values(voltage: float, nominal: float, threshold: float):
    """電圧異常検出時の severity は常に critical または major。

    **Validates: Requirements 13.3**

    プロパティ: severity ∈ {critical, major}
    """
    result = check_voltage_anomaly(voltage, nominal, threshold)
    if result is not None:
        assert result["severity"] in ("critical", "major")


# =========================================================================
# Property 1: SCADA threshold bounds — load imbalance
# =========================================================================
# **Validates: Requirements 13.3**


@settings(max_examples=200)
@given(
    loads=st.lists(
        st.floats(min_value=0.01, max_value=1000.0, allow_nan=False, allow_infinity=False),
        min_size=3,
        max_size=3,
    ),
    threshold=st.floats(min_value=0.1, max_value=100.0, allow_nan=False, allow_infinity=False),
)
def test_load_imbalance_threshold_consistency(loads: list[float], threshold: float):
    """負荷不均衡が閾値以下なら anomaly は None。

    **Validates: Requirements 13.3**

    プロパティ: (max - min) / avg * 100 <= threshold → None
    """
    avg_load = sum(loads) / len(loads)
    assume(avg_load > 0)

    imbalance_percent = (max(loads) - min(loads)) / avg_load * 100
    result = check_load_imbalance(loads, threshold)

    if imbalance_percent <= threshold:
        assert result is None
    else:
        assert result is not None
        assert result["anomaly_type"] == "load_imbalance"
        assert result["severity"] in VALID_SEVERITIES


# =========================================================================
# Property 1: SCADA threshold bounds — frequency
# =========================================================================
# **Validates: Requirements 13.3**


@settings(max_examples=200)
@given(
    frequency=st.floats(min_value=40.0, max_value=70.0, allow_nan=False, allow_infinity=False),
    nominal=st.sampled_from([50.0, 60.0]),
    threshold=st.floats(min_value=0.01, max_value=5.0, allow_nan=False, allow_infinity=False),
)
def test_frequency_anomaly_threshold_consistency(frequency: float, nominal: float, threshold: float):
    """周波数偏差が閾値以下なら anomaly は None。

    **Validates: Requirements 13.3**

    プロパティ: |frequency - nominal| <= threshold → None
    """
    deviation = abs(frequency - nominal)
    result = check_frequency_anomaly(frequency, nominal, threshold)

    if deviation <= threshold:
        assert result is None
    else:
        assert result is not None
        assert result["anomaly_type"] == "frequency_deviation"
        assert result["severity"] in VALID_SEVERITIES


# =========================================================================
# Property 2: Defect severity enumeration
# =========================================================================
# **Validates: Requirements 13.3**


@settings(max_examples=200)
@given(
    records=st.lists(
        st.fixed_dictionaries(
            {
                "timestamp": st.text(min_size=1, max_size=20),
                "equipment_id": st.text(min_size=1, max_size=20),
                "voltage": st.one_of(
                    st.none(),
                    st.floats(min_value=0.01, max_value=500.0, allow_nan=False, allow_infinity=False),
                ),
                "nominal_voltage": st.floats(min_value=50.0, max_value=500.0, allow_nan=False, allow_infinity=False),
                "frequency": st.one_of(
                    st.none(),
                    st.floats(min_value=40.0, max_value=70.0, allow_nan=False, allow_infinity=False),
                ),
                "nominal_frequency": st.sampled_from([50.0, 60.0]),
            }
        ),
        min_size=0,
        max_size=10,
    ),
)
def test_analyze_scada_anomaly_severities_valid(records: list[dict]):
    """analyze_scada_records で検出される全異常の severity は有効値。

    **Validates: Requirements 13.3**

    プロパティ: ∀ anomaly ∈ results: anomaly.severity ∈ {critical, major, minor}
    """
    thresholds = {
        "voltage_deviation_percent": 5.0,
        "load_imbalance_percent": 10.0,
        "frequency_deviation_hz": 0.5,
    }
    anomalies = analyze_scada_records(records, thresholds)
    for anomaly in anomalies:
        assert anomaly["severity"] in VALID_SEVERITIES


@settings(max_examples=200)
@given(
    records=st.lists(
        st.fixed_dictionaries(
            {
                "timestamp": st.just("2025-01-01T00:00:00Z"),
                "equipment_id": st.just("EQ001"),
                "voltage": st.floats(min_value=0.01, max_value=500.0, allow_nan=False, allow_infinity=False),
                "nominal_voltage": st.floats(min_value=50.0, max_value=500.0, allow_nan=False, allow_infinity=False),
                "phase_loads": st.lists(
                    st.floats(min_value=0.01, max_value=500.0, allow_nan=False, allow_infinity=False),
                    min_size=3,
                    max_size=3,
                ),
                "frequency": st.floats(min_value=40.0, max_value=70.0, allow_nan=False, allow_infinity=False),
                "nominal_frequency": st.sampled_from([50.0, 60.0]),
            }
        ),
        min_size=1,
        max_size=5,
    ),
)
def test_anomaly_count_bounded_by_checks_per_record(records: list[dict]):
    """異常検出数は record 数 × チェック種類数 (3) 以下。

    **Validates: Requirements 13.3**

    プロパティ: len(anomalies) <= len(records) * 3
    """
    thresholds = {
        "voltage_deviation_percent": 5.0,
        "load_imbalance_percent": 10.0,
        "frequency_deviation_hz": 0.5,
    }
    anomalies = analyze_scada_records(records, thresholds)
    # Each record can generate at most 3 anomalies (voltage, load, frequency)
    assert len(anomalies) <= len(records) * 3
