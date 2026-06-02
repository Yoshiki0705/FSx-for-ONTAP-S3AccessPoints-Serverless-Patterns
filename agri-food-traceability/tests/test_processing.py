"""UC21 Agri-Food Traceability — Processing Lambda unit tests.

Tests for crop_analyzer and traceability_extractor handlers.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Dynamic import — Crop Analyzer
_crop_path = Path(__file__).parent.parent / "functions" / "crop_analyzer" / "handler.py"
_crop_spec = importlib.util.spec_from_file_location("agri_crop_handler", _crop_path)
_crop_module = importlib.util.module_from_spec(_crop_spec)
sys.modules["agri_crop_handler"] = _crop_module
_crop_spec.loader.exec_module(_crop_module)

# Dynamic import — Traceability Extractor
_trace_path = Path(__file__).parent.parent / "functions" / "traceability_extractor" / "handler.py"
_trace_spec = importlib.util.spec_from_file_location("agri_trace_handler", _trace_path)
_trace_module = importlib.util.module_from_spec(_trace_spec)
sys.modules["agri_trace_handler"] = _trace_module
_trace_spec.loader.exec_module(_trace_module)

extract_exif_geolocation = _crop_module.extract_exif_geolocation
analyze_vegetation_with_rekognition = _crop_module.analyze_vegetation_with_rekognition
classify_anomalies_with_bedrock = _crop_module.classify_anomalies_with_bedrock
DEFAULT_CONFIDENCE_THRESHOLD = _crop_module.DEFAULT_CONFIDENCE_THRESHOLD

extract_traceability_fields = _trace_module.extract_traceability_fields
classify_document_by_lot = _trace_module.classify_document_by_lot
DEFAULT_TRACEABILITY_THRESHOLD = _trace_module.DEFAULT_TRACEABILITY_THRESHOLD


class TestExtractExifGeolocation:
    """EXIF GPS 抽出のテスト"""

    def test_with_gps_metadata(self):
        metadata = {"gps_latitude": "35.6812", "gps_longitude": "139.7671"}
        result = extract_exif_geolocation(metadata)
        assert result is not None
        assert result["latitude"] == pytest.approx(35.6812)
        assert result["longitude"] == pytest.approx(139.7671)

    def test_with_amz_meta_headers(self):
        metadata = {
            "x-amz-meta-gps-latitude": "36.2048",
            "x-amz-meta-gps-longitude": "138.2529",
        }
        result = extract_exif_geolocation(metadata)
        assert result is not None
        assert result["latitude"] == pytest.approx(36.2048)

    def test_missing_geolocation(self):
        """Requirement 5.5: 位置情報なしの場合は None"""
        metadata = {"camera_model": "DJI Phantom 4"}
        result = extract_exif_geolocation(metadata)
        assert result is None

    def test_empty_metadata(self):
        result = extract_exif_geolocation({})
        assert result is None

    def test_invalid_gps_values(self):
        metadata = {"gps_latitude": "invalid", "gps_longitude": "xyz"}
        result = extract_exif_geolocation(metadata)
        assert result is None


class TestAnalyzeVegetationWithRekognition:
    """Rekognition 植生解析のテスト"""

    def test_successful_detection(self):
        mock_client = MagicMock()
        mock_client.detect_labels.return_value = {
            "Labels": [
                {"Name": "Plant", "Confidence": 95.5},
                {"Name": "Farm", "Confidence": 88.0},
                {"Name": "Building", "Confidence": 72.0},
            ]
        }

        result = analyze_vegetation_with_rekognition(
            mock_client, "test-bucket", "test-key.tif"
        )

        assert result["total_labels"] == 3
        assert len(result["vegetation_labels"]) == 2
        assert result["vegetation_labels"][0]["name"] == "Plant"
        assert result["vegetation_labels"][0]["confidence"] == pytest.approx(0.955, abs=0.001)

    def test_no_vegetation_labels(self):
        mock_client = MagicMock()
        mock_client.detect_labels.return_value = {
            "Labels": [
                {"Name": "Car", "Confidence": 90.0},
                {"Name": "Road", "Confidence": 85.0},
            ]
        }

        result = analyze_vegetation_with_rekognition(
            mock_client, "test-bucket", "test-key.jpg"
        )

        assert len(result["vegetation_labels"]) == 0
        assert len(result["other_labels"]) == 2


class TestClassifyAnomaliesWithBedrock:
    """Bedrock 異常分類のテスト"""

    def test_anomalies_above_threshold(self):
        mock_client = MagicMock()
        mock_response_body = json.dumps({
            "content": [{"type": "text", "text": json.dumps([
                {"anomaly_type": "pest_damage", "confidence": 0.85, "description": "Pest observed"},
                {"anomaly_type": "irrigation_issue", "confidence": 0.72, "description": "Dry areas"},
            ])}]
        }).encode()

        mock_client.invoke_model.return_value = {
            "body": MagicMock(read=MagicMock(return_value=mock_response_body))
        }

        result = classify_anomalies_with_bedrock(
            mock_client, "test-model", {}, 0.70
        )

        assert len(result) == 2
        assert result[0]["anomaly_type"] == "pest_damage"
        assert result[0]["status"] == "confirmed"
        assert result[1]["status"] == "confirmed"

    def test_anomalies_below_threshold_marked_review(self):
        """Requirement 5.6: 閾値未満は review-required"""
        mock_client = MagicMock()
        mock_response_body = json.dumps({
            "content": [{"type": "text", "text": json.dumps([
                {"anomaly_type": "pest_damage", "confidence": 0.65, "description": "Maybe pest"},
            ])}]
        }).encode()

        mock_client.invoke_model.return_value = {
            "body": MagicMock(read=MagicMock(return_value=mock_response_body))
        }

        result = classify_anomalies_with_bedrock(
            mock_client, "test-model", {}, 0.70
        )

        assert len(result) == 1
        assert result[0]["status"] == "review-required"
        assert "below threshold" in result[0]["reason"]

    def test_invalid_bedrock_response(self):
        mock_client = MagicMock()
        mock_response_body = json.dumps({
            "content": [{"type": "text", "text": "I cannot analyze this image."}]
        }).encode()

        mock_client.invoke_model.return_value = {
            "body": MagicMock(read=MagicMock(return_value=mock_response_body))
        }

        result = classify_anomalies_with_bedrock(
            mock_client, "test-model", {}, 0.70
        )

        assert result == []


class TestExtractTraceabilityFields:
    """トレーサビリティフィールド抽出のテスト"""

    def test_japanese_keywords(self):
        key_value_pairs = {
            "ロットID": "LOT-2026-001",
            "収穫日": "2026-06-01",
            "産地": "北海道十勝郡",
            "責任者": "田中太郎",
        }

        result = extract_traceability_fields("", key_value_pairs)

        assert result["lot_id"] == "LOT-2026-001"
        assert result["date"] == "2026-06-01"
        assert result["origin_location"] == "北海道十勝郡"
        assert result["responsible_party"] == "田中太郎"

    def test_english_keywords(self):
        key_value_pairs = {
            "Lot ID": "LOT-2026-002",
            "Harvest Date": "2026-06-15",
            "Origin": "Hokkaido",
            "Producer": "Tanaka Farm",
        }

        result = extract_traceability_fields("", key_value_pairs)

        assert result["lot_id"] == "LOT-2026-002"
        assert result["date"] == "2026-06-15"
        assert result["origin_location"] == "Hokkaido"
        assert result["responsible_party"] == "Tanaka Farm"

    def test_missing_fields(self):
        key_value_pairs = {"Other Key": "value"}

        result = extract_traceability_fields("", key_value_pairs)

        assert result["lot_id"] is None
        assert result["date"] is None
        assert result["origin_location"] is None
        assert result["responsible_party"] is None


class TestClassifyDocumentByLot:
    """Comprehend ロット分類のテスト"""

    def test_classification_above_threshold(self):
        mock_client = MagicMock()
        mock_client.detect_entities.return_value = {
            "Entities": [
                {"Type": "QUANTITY", "Text": "LOT-001", "Score": 0.92},
                {"Type": "OTHER", "Text": "Farm A", "Score": 0.88},
            ]
        }
        mock_client.detect_key_phrases.return_value = {
            "KeyPhrases": [{"Text": "harvest record", "Score": 0.95}]
        }

        result = classify_document_by_lot(mock_client, "test text", 0.80)

        assert result["status"] == "classified"
        assert result["classification_confidence"] >= 0.80

    def test_classification_below_threshold(self):
        """Requirement 5.6: 0.80 未満は review-required"""
        mock_client = MagicMock()
        mock_client.detect_entities.return_value = {
            "Entities": [
                {"Type": "QUANTITY", "Text": "lot1", "Score": 0.65},
                {"Type": "OTHER", "Text": "something", "Score": 0.55},
            ]
        }
        mock_client.detect_key_phrases.return_value = {
            "KeyPhrases": []
        }

        result = classify_document_by_lot(mock_client, "test text", 0.80)

        assert result["status"] == "review-required"
        assert result["reason"] is not None
        assert "below threshold" in result["reason"]

    def test_no_entities_detected(self):
        mock_client = MagicMock()
        mock_client.detect_entities.return_value = {"Entities": []}
        mock_client.detect_key_phrases.return_value = {"KeyPhrases": []}

        result = classify_document_by_lot(mock_client, "empty text", 0.80)

        assert result["status"] == "review-required"
        assert result["classification_confidence"] == 0.0
