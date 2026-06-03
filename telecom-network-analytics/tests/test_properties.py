"""UC18 通信業界 Property-Based Tests (Hypothesis)

Hypothesis ライブラリを使用したプロパティベーステスト。
処理コアロジックの普遍的性質を多数の入力に対して検証する。

テスト対象プロパティ:
1. Discovery filter consistency — 同一入力で常に同一出力
2. anomaly_count bounds — 0 <= anomaly_count <= total_records
3. Metric accuracy — success_count + error_count == total_processed

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
_discovery_spec = importlib.util.spec_from_file_location("discovery_handler", _discovery_path)
_discovery_module = importlib.util.module_from_spec(_discovery_spec)
_discovery_spec.loader.exec_module(_discovery_module)

parse_suffix_filter = _discovery_module.parse_suffix_filter

# Anomaly Detector handler
_anomaly_path = os.path.join(os.path.dirname(__file__), "..", "functions", "anomaly_detector", "handler.py")
_anomaly_spec = importlib.util.spec_from_file_location("anomaly_handler_pbt", _anomaly_path)
_anomaly_module = importlib.util.module_from_spec(_anomaly_spec)
_anomaly_spec.loader.exec_module(_anomaly_module)

detect_anomalies = _anomaly_module.detect_anomalies
calculate_baseline_statistics = _anomaly_module.calculate_baseline_statistics

# Report handler
_report_path = os.path.join(os.path.dirname(__file__), "..", "functions", "report", "handler.py")
_report_spec = importlib.util.spec_from_file_location("report_handler_pbt", _report_path)
_report_module = importlib.util.module_from_spec(_report_spec)
_report_spec.loader.exec_module(_report_module)

aggregate_results = _report_module.aggregate_results


# =========================================================================
# Property 1: Discovery filter consistency
# 同一入力は常に同一出力を生成する (決定的動作)
# =========================================================================
# **Validates: Requirements 13.3**


@settings(max_examples=200)
@given(
    suffix_filter=st.text(
        alphabet=st.characters(whitelist_categories=("L", "Nd", "P"), whitelist_characters=".,_ -/"),
        min_size=0,
        max_size=200,
    ),
)
def test_discovery_filter_consistency(suffix_filter: str):
    """Discovery filter は同一入力に対して常に同一出力を返す。

    **Validates: Requirements 13.3**

    プロパティ: 決定性
    - parse_suffix_filter(x) == parse_suffix_filter(x) for any x
    """
    result1 = parse_suffix_filter(suffix_filter)
    result2 = parse_suffix_filter(suffix_filter)
    assert result1 == result2


@settings(max_examples=200)
@given(
    suffixes=st.lists(
        st.text(
            alphabet=st.characters(whitelist_categories=("L", "Nd"), whitelist_characters=".-_"),
            min_size=1,
            max_size=10,
        ),
        min_size=0,
        max_size=30,
    ),
)
def test_discovery_filter_max_patterns_bounded(suffixes: list[str]):
    """Discovery filter は最大 20 パターンに制限される。

    **Validates: Requirements 13.3**

    プロパティ: len(parse_suffix_filter(input)) <= 20 for any input
    """
    suffix_str = ",".join(suffixes)
    result = parse_suffix_filter(suffix_str)
    assert len(result) <= 20


@settings(max_examples=200)
@given(
    suffix_filter=st.text(
        alphabet=st.characters(whitelist_categories=("L", "Nd", "P"), whitelist_characters=".,_ -/"),
        min_size=0,
        max_size=200,
    ),
)
def test_discovery_filter_no_empty_entries(suffix_filter: str):
    """Discovery filter は空文字列エントリを含まない。

    **Validates: Requirements 13.3**

    プロパティ: "" not in parse_suffix_filter(x) for any x
    """
    result = parse_suffix_filter(suffix_filter)
    for entry in result:
        assert entry != ""
        assert entry.strip() == entry  # No leading/trailing whitespace


# =========================================================================
# Property 2: anomaly_count bounds
# 0 <= anomaly_count <= total_records (メトリクス数)
# =========================================================================
# **Validates: Requirements 13.3**


# Strategy for generating metric dictionaries
metric_value_strategy = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)


@settings(max_examples=200)
@given(
    metric_values=st.dictionaries(
        keys=st.sampled_from(["call_volume", "average_duration", "peak_concurrent_calls", "equipment_failures_count", "capacity_breaches_count"]),
        values=metric_value_strategy,
        min_size=1,
        max_size=5,
    ),
    baseline_mean=st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False),
    baseline_stddev=st.floats(min_value=0.01, max_value=1e4, allow_nan=False, allow_infinity=False),
    baseline_count=st.integers(min_value=2, max_value=100),
    threshold=st.floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False),
)
def test_anomaly_count_bounds(
    metric_values: dict[str, float],
    baseline_mean: float,
    baseline_stddev: float,
    baseline_count: int,
    threshold: float,
):
    """異常検出数は常に 0 以上かつ入力メトリクス数以下。

    **Validates: Requirements 13.3**

    プロパティ: 0 <= len(anomalies) <= len(current_metrics)
    """
    baseline = {
        name: {"mean": baseline_mean, "stddev": baseline_stddev, "count": baseline_count}
        for name in metric_values
    }
    anomalies = detect_anomalies(metric_values, baseline, threshold_stddev=threshold)
    assert 0 <= len(anomalies) <= len(metric_values)


@settings(max_examples=200)
@given(
    values=st.lists(
        st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
        min_size=0,
        max_size=50,
    ),
)
def test_baseline_statistics_count_matches_input(values: list[float]):
    """ベースライン統計の count は常に入力リストの長さと一致する。

    **Validates: Requirements 13.3**

    プロパティ: stats["count"] == len(input_values)
    """
    stats = calculate_baseline_statistics(values)
    assert stats["count"] == len(values)


@settings(max_examples=200)
@given(
    values=st.lists(
        st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
        min_size=0,
        max_size=50,
    ),
)
def test_baseline_statistics_stddev_non_negative(values: list[float]):
    """標準偏差は常に 0 以上。

    **Validates: Requirements 13.3**

    プロパティ: stats["stddev"] >= 0
    """
    stats = calculate_baseline_statistics(values)
    assert stats["stddev"] >= 0.0


# =========================================================================
# Property 3: Metric accuracy
# success_count + error_count == total_processed
# =========================================================================
# **Validates: Requirements 13.3**


@settings(max_examples=200)
@given(
    success_results=st.lists(
        st.fixed_dictionaries({"status": st.just("success")}),
        min_size=0,
        max_size=50,
    ),
    error_results=st.lists(
        st.fixed_dictionaries({"status": st.sampled_from(["parse_error", "error", "retrieval_error"])}),
        min_size=0,
        max_size=50,
    ),
)
def test_metric_accuracy_cdr_results(
    success_results: list[dict],
    error_results: list[dict],
):
    """success_count + error_count == total_processed (CDR 結果)。

    **Validates: Requirements 13.3**

    プロパティ: aggregate_results のメトリクス整合性
    """
    all_results = success_results + error_results
    event = {
        "anomaly_result": {
            "anomalies": [],
            "anomaly_count": 0,
            "classification": {},
            "current_metrics": {},
            "baseline_summary": {},
            "total_cdr_files": len(all_results),
            "total_log_files": 0,
            "status": "success",
        },
        "cdr_results": all_results,
        "log_results": [],
    }
    result = aggregate_results(event)
    assert result["success_count"] + result["error_count"] == result["total_processed"]


@settings(max_examples=200)
@given(
    cdr_success=st.integers(min_value=0, max_value=100),
    cdr_error=st.integers(min_value=0, max_value=100),
    log_success=st.integers(min_value=0, max_value=100),
    log_error=st.integers(min_value=0, max_value=100),
)
def test_metric_accuracy_combined(
    cdr_success: int,
    cdr_error: int,
    log_success: int,
    log_error: int,
):
    """success_count + error_count == total_processed (CDR + Log 結合)。

    **Validates: Requirements 13.3**

    プロパティ: メトリクス整合性は CDR と Log を合わせても成立する
    """
    cdr_results = [{"status": "success"}] * cdr_success + [{"status": "error"}] * cdr_error
    log_results = [{"status": "success"}] * log_success + [{"status": "error"}] * log_error

    event = {
        "anomaly_result": {
            "anomalies": [],
            "anomaly_count": 0,
            "classification": {},
            "current_metrics": {},
            "baseline_summary": {},
            "total_cdr_files": len(cdr_results),
            "total_log_files": len(log_results),
            "status": "success",
        },
        "cdr_results": cdr_results,
        "log_results": log_results,
    }
    result = aggregate_results(event)
    expected_total = cdr_success + cdr_error + log_success + log_error
    assert result["success_count"] + result["error_count"] == expected_total
    assert result["total_processed"] == expected_total
    assert result["success_count"] == cdr_success + log_success
    assert result["error_count"] == cdr_error + log_error
