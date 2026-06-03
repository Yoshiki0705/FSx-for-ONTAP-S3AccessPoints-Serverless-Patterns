"""UC25 Utilities Asset Inspection — Processing Lambdas unit tests.

Tests for:
- Defect Detector (Rekognition + Bedrock)
- SCADA Analyzer (Athena time-series)
- Thermal Analyzer (FLIR hot-spot)
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ─── Defect Detector ───────────────────────────────────────────────────────
_defect_path = Path(__file__).parent.parent / "functions" / "defect_detector" / "handler.py"
_defect_spec = importlib.util.spec_from_file_location("utilities_defect_handler", _defect_path)
_defect_module = importlib.util.module_from_spec(_defect_spec)
sys.modules["utilities_defect_handler"] = _defect_module
_defect_spec.loader.exec_module(_defect_module)

detect_defects_rekognition = _defect_module.detect_defects_rekognition
assess_severity_bedrock = _defect_module.assess_severity_bedrock
_parse_severity_response = _defect_module._parse_severity_response
DEFECT_LABEL_MAPPING = _defect_module.DEFECT_LABEL_MAPPING
VALID_SEVERITIES = _defect_module.VALID_SEVERITIES

# ─── SCADA Analyzer ────────────────────────────────────────────────────────
_scada_path = Path(__file__).parent.parent / "functions" / "scada_analyzer" / "handler.py"
_scada_spec = importlib.util.spec_from_file_location("utilities_scada_handler", _scada_path)
_scada_module = importlib.util.module_from_spec(_scada_spec)
sys.modules["utilities_scada_handler"] = _scada_module
_scada_spec.loader.exec_module(_scada_module)

check_voltage_anomaly = _scada_module.check_voltage_anomaly
check_load_imbalance = _scada_module.check_load_imbalance
check_frequency_anomaly = _scada_module.check_frequency_anomaly
analyze_scada_records = _scada_module.analyze_scada_records
get_thresholds = _scada_module.get_thresholds
SCADA_THRESHOLDS = _scada_module.SCADA_THRESHOLDS

# ─── Thermal Analyzer ──────────────────────────────────────────────────────
_thermal_path = Path(__file__).parent.parent / "functions" / "thermal_analyzer" / "handler.py"
_thermal_spec = importlib.util.spec_from_file_location("utilities_thermal_handler", _thermal_path)
_thermal_module = importlib.util.module_from_spec(_thermal_spec)
sys.modules["utilities_thermal_handler"] = _thermal_module
_thermal_spec.loader.exec_module(_thermal_module)

classify_thermal_differential = _thermal_module.classify_thermal_differential
extract_thermal_data = _thermal_module.extract_thermal_data
CLASSIFICATION_HOT_SPOT = _thermal_module.CLASSIFICATION_HOT_SPOT
CLASSIFICATION_SEVERE_HOT_SPOT = _thermal_module.CLASSIFICATION_SEVERE_HOT_SPOT
CLASSIFICATION_NORMAL = _thermal_module.CLASSIFICATION_NORMAL


# ═══════════════════════════════════════════════════════════════════════════
# Defect Detector Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestDetectDefectsRekognition:
    """Rekognition 欠陥検出のテスト"""

    def test_detects_insulator_damage(self):
        mock_client = MagicMock()
        mock_client.detect_labels.return_value = {
            "Labels": [
                {"Name": "Crack on surface", "Confidence": 85.0},
                {"Name": "Metal Structure", "Confidence": 92.0},
            ]
        }
        result = detect_defects_rekognition(
            "test-ap", "test.jpg", 70.0, rekognition_client=mock_client
        )
        assert len(result) == 1
        assert result[0]["defect_type"] == "insulator_damage"
        assert result[0]["confidence"] == 85.0

    def test_detects_vegetation_encroachment(self):
        mock_client = MagicMock()
        mock_client.detect_labels.return_value = {
            "Labels": [
                {"Name": "Tree branch near wire", "Confidence": 78.0},
            ]
        }
        result = detect_defects_rekognition(
            "test-ap", "test.jpg", 70.0, rekognition_client=mock_client
        )
        assert len(result) == 1
        assert result[0]["defect_type"] == "vegetation_encroachment"

    def test_no_defects_detected(self):
        mock_client = MagicMock()
        mock_client.detect_labels.return_value = {
            "Labels": [
                {"Name": "Sky", "Confidence": 99.0},
                {"Name": "Power Line", "Confidence": 95.0},
            ]
        }
        result = detect_defects_rekognition(
            "test-ap", "test.jpg", 70.0, rekognition_client=mock_client
        )
        assert len(result) == 0

    def test_confidence_threshold_applied(self):
        mock_client = MagicMock()
        mock_client.detect_labels.return_value = {"Labels": []}
        detect_defects_rekognition(
            "test-ap", "test.jpg", 70.0, rekognition_client=mock_client
        )
        call_kwargs = mock_client.detect_labels.call_args[1]
        assert call_kwargs["MinConfidence"] == 70.0


class TestAssessSeverityBedrock:
    """Bedrock 重大度評価のテスト"""

    def test_severity_assignment(self):
        mock_client = MagicMock()
        mock_response_body = MagicMock()
        mock_response_body.read.return_value = json.dumps({
            "content": [{"text": '[{"defect_type": "insulator_damage", "severity": "critical", "reason": "test"}]'}]
        }).encode()
        mock_client.invoke_model.return_value = {"body": mock_response_body}

        defects = [{"defect_type": "insulator_damage", "confidence": 85.0, "label": "Crack"}]
        result = assess_severity_bedrock(
            defects, "EQ-001", bedrock_client=mock_client
        )
        assert result[0]["severity"] == "critical"

    def test_fallback_to_minor_on_failure(self):
        mock_client = MagicMock()
        mock_client.invoke_model.side_effect = RuntimeError("API error")

        defects = [{"defect_type": "insulator_damage", "confidence": 85.0, "label": "Crack"}]
        result = assess_severity_bedrock(
            defects, "EQ-001", bedrock_client=mock_client
        )
        assert result[0]["severity"] == "minor"

    def test_empty_defects_returns_empty(self):
        result = assess_severity_bedrock([], "EQ-001")
        assert result == []


class TestParseSeverityResponse:
    """Bedrock レスポンスパースのテスト"""

    def test_valid_json_array(self):
        text = 'Here is the result: [{"defect_type": "crack", "severity": "major"}]'
        result = _parse_severity_response(text)
        assert len(result) == 1
        assert result[0]["severity"] == "major"

    def test_invalid_json(self):
        result = _parse_severity_response("no json here")
        assert result == []

    def test_malformed_json(self):
        result = _parse_severity_response("[{invalid}]")
        assert result == []


# ═══════════════════════════════════════════════════════════════════════════
# SCADA Analyzer Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestCheckVoltageAnomaly:
    """電圧偏差チェックのテスト"""

    def test_normal_voltage(self):
        # 100V ± 5% = 95-105V, 102V is normal
        result = check_voltage_anomaly(102.0, 100.0, 5.0)
        assert result is None

    def test_voltage_above_threshold(self):
        # 100V + 6% = 106V → anomaly
        result = check_voltage_anomaly(106.0, 100.0, 5.0)
        assert result is not None
        assert result["anomaly_type"] == "voltage_deviation"
        assert result["deviation_percent"] == 6.0

    def test_voltage_below_threshold(self):
        # 100V - 6% = 94V → anomaly
        result = check_voltage_anomaly(94.0, 100.0, 5.0)
        assert result is not None
        assert result["anomaly_type"] == "voltage_deviation"

    def test_critical_severity_over_double_threshold(self):
        # 100V + 11% = 111V → critical (>10%)
        result = check_voltage_anomaly(111.0, 100.0, 5.0)
        assert result is not None
        assert result["severity"] == "critical"

    def test_major_severity_within_double_threshold(self):
        # 100V + 6% = 106V → major (5-10%)
        result = check_voltage_anomaly(106.0, 100.0, 5.0)
        assert result is not None
        assert result["severity"] == "major"

    def test_zero_nominal_voltage(self):
        result = check_voltage_anomaly(100.0, 0.0, 5.0)
        assert result is None


class TestCheckLoadImbalance:
    """負荷不均衡チェックのテスト"""

    def test_balanced_load(self):
        result = check_load_imbalance([100.0, 102.0, 101.0], 10.0)
        assert result is None

    def test_imbalanced_load(self):
        # (120 - 80) / 100 * 100 = 40% → anomaly
        result = check_load_imbalance([120.0, 100.0, 80.0], 10.0)
        assert result is not None
        assert result["anomaly_type"] == "load_imbalance"
        assert result["imbalance_percent"] == 40.0

    def test_critical_severity(self):
        # imbalance > 20% → critical
        result = check_load_imbalance([150.0, 100.0, 50.0], 10.0)
        assert result is not None
        assert result["severity"] == "critical"

    def test_empty_phases(self):
        result = check_load_imbalance([], 10.0)
        assert result is None

    def test_single_phase(self):
        result = check_load_imbalance([100.0], 10.0)
        assert result is None

    def test_zero_average(self):
        result = check_load_imbalance([0.0, 0.0, 0.0], 10.0)
        assert result is None


class TestCheckFrequencyAnomaly:
    """周波数偏差チェックのテスト"""

    def test_normal_frequency_50hz(self):
        result = check_frequency_anomaly(50.2, 50.0, 0.5)
        assert result is None

    def test_frequency_above_threshold(self):
        result = check_frequency_anomaly(50.6, 50.0, 0.5)
        assert result is not None
        assert result["anomaly_type"] == "frequency_deviation"
        assert result["deviation_hz"] == 0.6

    def test_frequency_below_threshold(self):
        result = check_frequency_anomaly(49.4, 50.0, 0.5)
        assert result is not None
        assert result["anomaly_type"] == "frequency_deviation"

    def test_critical_severity(self):
        # deviation > 1.0 Hz → critical
        result = check_frequency_anomaly(51.2, 50.0, 0.5)
        assert result is not None
        assert result["severity"] == "critical"

    def test_60hz_system(self):
        result = check_frequency_anomaly(60.1, 60.0, 0.5)
        assert result is None


class TestAnalyzeScadaRecords:
    """SCADA レコード解析のテスト"""

    def test_mixed_anomalies(self):
        records = [
            {
                "timestamp": "2025-06-01T10:00:00Z",
                "equipment_id": "EQ-001",
                "voltage": 112.0,
                "nominal_voltage": 100.0,
            },
            {
                "timestamp": "2025-06-01T10:05:00Z",
                "equipment_id": "EQ-001",
                "frequency": 50.8,
                "nominal_frequency": 50.0,
            },
        ]
        thresholds = {
            "voltage_deviation_percent": 5.0,
            "load_imbalance_percent": 10.0,
            "frequency_deviation_hz": 0.5,
        }
        anomalies = analyze_scada_records(records, thresholds)
        assert len(anomalies) == 2

    def test_no_anomalies(self):
        records = [
            {
                "timestamp": "2025-06-01T10:00:00Z",
                "equipment_id": "EQ-001",
                "voltage": 101.0,
                "nominal_voltage": 100.0,
                "frequency": 50.1,
                "nominal_frequency": 50.0,
            },
        ]
        thresholds = SCADA_THRESHOLDS
        anomalies = analyze_scada_records(records, thresholds)
        assert len(anomalies) == 0

    def test_empty_records(self):
        anomalies = analyze_scada_records([], SCADA_THRESHOLDS)
        assert anomalies == []


# ═══════════════════════════════════════════════════════════════════════════
# Thermal Analyzer Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestClassifyThermalDifferential:
    """温度差分分類のテスト"""

    def test_normal(self):
        result = classify_thermal_differential(5.0, 10.0)
        assert result == CLASSIFICATION_NORMAL

    def test_hot_spot(self):
        result = classify_thermal_differential(12.0, 10.0)
        assert result == CLASSIFICATION_HOT_SPOT

    def test_severe_hot_spot(self):
        result = classify_thermal_differential(22.0, 10.0)
        assert result == CLASSIFICATION_SEVERE_HOT_SPOT

    def test_exact_threshold(self):
        result = classify_thermal_differential(10.0, 10.0)
        assert result == CLASSIFICATION_HOT_SPOT

    def test_exact_double_threshold(self):
        result = classify_thermal_differential(20.0, 10.0)
        assert result == CLASSIFICATION_SEVERE_HOT_SPOT

    def test_zero_differential(self):
        result = classify_thermal_differential(0.0, 10.0)
        assert result == CLASSIFICATION_NORMAL


class TestExtractThermalData:
    """サーマルデータ抽出のテスト"""

    def test_with_baseline(self):
        metadata = {
            "measurements": [
                {
                    "component_id": "bushing-A",
                    "max_temperature": 75.0,
                    "baseline_temperature": 55.0,
                    "ambient_temperature": 30.0,
                }
            ]
        }
        result = extract_thermal_data(metadata)
        assert len(result) == 1
        assert result[0]["temperature_differential"] == 20.0
        assert result[0]["component_id"] == "bushing-A"

    def test_without_baseline_uses_ambient(self):
        metadata = {
            "measurements": [
                {
                    "component_id": "connector-B",
                    "max_temperature": 60.0,
                    "ambient_temperature": 35.0,
                }
            ]
        }
        result = extract_thermal_data(metadata)
        assert len(result) == 1
        assert result[0]["temperature_differential"] == 25.0

    def test_empty_measurements(self):
        metadata = {"measurements": []}
        result = extract_thermal_data(metadata)
        assert result == []

    def test_missing_temperatures(self):
        metadata = {
            "measurements": [
                {"component_id": "unknown"}
            ]
        }
        result = extract_thermal_data(metadata)
        assert result == []

    def test_multiple_components(self):
        metadata = {
            "measurements": [
                {
                    "component_id": "comp-1",
                    "max_temperature": 50.0,
                    "baseline_temperature": 45.0,
                },
                {
                    "component_id": "comp-2",
                    "max_temperature": 80.0,
                    "baseline_temperature": 55.0,
                },
            ]
        }
        result = extract_thermal_data(metadata)
        assert len(result) == 2
        assert result[0]["temperature_differential"] == 5.0
        assert result[1]["temperature_differential"] == 25.0
