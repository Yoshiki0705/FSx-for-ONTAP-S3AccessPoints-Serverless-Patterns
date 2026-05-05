"""UC14 保険 / 損害査定 ユニットテスト

Rekognition 損害検出、Cross-Region Textract 呼び出し、レポート生成をテストする。

Requirements: 13.1, 13.2
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from functions.damage_assessment.handler import (
    detect_damage_labels,
    classify_damage,
    sanitize_for_logging,
)
from functions.estimate_ocr.handler import (
    _extract_text_from_blocks,
    _extract_tables_from_blocks,
    _parse_estimate_data,
)
from functions.claims_report.handler import (
    _generate_human_readable_report,
)


# =========================================================================
# 損害検出テスト
# =========================================================================


class TestDetectDamageLabels:
    """Rekognition 損害ラベル検出のテスト"""

    def test_detect_labels_success(self):
        """正常系: ラベルが正しく検出されること"""
        mock_client = MagicMock()
        mock_client.detect_labels.return_value = {
            "Labels": [
                {"Name": "Car", "Confidence": 99.5, "Instances": [{}]},
                {"Name": "Damage", "Confidence": 87.3, "Instances": []},
                {"Name": "Bumper", "Confidence": 75.0, "Instances": [{}]},
            ]
        }
        result = detect_damage_labels(mock_client, b"fake_image")
        assert len(result) == 3
        assert result[0]["name"] == "Car"
        assert result[1]["name"] == "Damage"
        assert result[1]["confidence"] == 87.3

    def test_detect_labels_empty(self):
        """空レスポンスで空リストが返ること"""
        mock_client = MagicMock()
        mock_client.detect_labels.return_value = {"Labels": []}
        result = detect_damage_labels(mock_client, b"fake_image")
        assert result == []


class TestClassifyDamage:
    """損害分類のテスト"""

    def test_damage_detected(self):
        """損害ラベルが検出された場合"""
        labels = [
            {"name": "Car", "confidence": 99.0, "instances": 1},
            {"name": "Damage", "confidence": 85.0, "instances": 0},
            {"name": "Bumper", "confidence": 75.0, "instances": 1},
        ]
        result = classify_damage(labels)
        assert result["damage_detected"] is True
        assert len(result["damage_labels"]) == 1
        assert result["affected_components"] == ["bumper"]

    def test_no_damage_detected(self):
        """損害ラベルが検出されない場合"""
        labels = [
            {"name": "Car", "confidence": 99.0, "instances": 1},
            {"name": "Road", "confidence": 90.0, "instances": 0},
        ]
        result = classify_damage(labels)
        assert result["damage_detected"] is False
        assert result["reason_code"] == "NO_DAMAGE_LABELS_DETECTED"

    def test_low_confidence_damage_excluded(self):
        """低信頼度の損害ラベルが除外されること"""
        labels = [
            {"name": "Damage", "confidence": 30.0, "instances": 0},
        ]
        result = classify_damage(labels)
        assert result["damage_detected"] is False


# =========================================================================
# PII サニタイズテスト
# =========================================================================


class TestSanitizeForLogging:
    """PII サニタイズのテスト"""

    @patch.dict(os.environ, {"LOG_PII_DATA": "false"})
    def test_pii_redacted(self):
        """PII フィールドがマスクされること"""
        data = {
            "claimant_name": "田中太郎",
            "policy_number": "POL-12345",
            "damage_type": "collision",
        }
        result = sanitize_for_logging(data)
        assert result["claimant_name"] == "***REDACTED***"
        assert result["policy_number"] == "***REDACTED***"
        assert result["damage_type"] == "collision"

    @patch.dict(os.environ, {"LOG_PII_DATA": "true"})
    def test_pii_not_redacted_when_enabled(self):
        """LOG_PII_DATA=true の場合にマスクされないこと"""
        data = {
            "claimant_name": "田中太郎",
            "damage_type": "collision",
        }
        result = sanitize_for_logging(data)
        assert result["claimant_name"] == "田中太郎"


# =========================================================================
# 見積書 OCR テスト
# =========================================================================


class TestExtractTextFromBlocks:
    """Textract テキスト抽出のテスト"""

    def test_extract_lines(self):
        """LINE ブロックからテキストが抽出されること"""
        blocks = [
            {"BlockType": "LINE", "Text": "修理見積書"},
            {"BlockType": "LINE", "Text": "フロントバンパー交換"},
        ]
        result = _extract_text_from_blocks(blocks)
        assert "修理見積書" in result
        assert "フロントバンパー交換" in result

    def test_empty_blocks(self):
        """空ブロックで空文字列が返ること"""
        assert _extract_text_from_blocks([]) == ""


class TestParseEstimateData:
    """見積書データ解析のテスト"""

    def test_parse_with_tables(self):
        """テーブルから修理項目が解析されること"""
        tables = [{
            "rows": [
                ["項目", "費用", "工数"],
                ["バンパー交換", "85000", "3.0"],
                ["フード修理", "45000", "2.5"],
            ]
        }]
        result = _parse_estimate_data("", tables)
        assert len(result["repair_items"]) == 2
        assert result["repair_items"][0]["item"] == "バンパー交換"
        assert result["repair_items"][0]["cost"] == 85000
        assert result["currency"] == "JPY"

    def test_parse_empty_tables(self):
        """空テーブルで空結果が返ること"""
        result = _parse_estimate_data("", [])
        assert result["repair_items"] == []
        assert result["total_estimate"] == 0


# =========================================================================
# レポート生成テスト
# =========================================================================


class TestGenerateHumanReadableReport:
    """人間可読レポート生成のテスト"""

    def test_report_contains_claim_id(self):
        """レポートに請求IDが含まれること"""
        report = {
            "claim_id": "CLM20260115_001",
            "generated_at": "2026-01-15T10:00:00Z",
            "damage_summary": "フロント衝突損害",
            "estimate_correlation": {
                "matched_items": 3,
                "total_assessed_damage": 185000,
            },
            "recommendation": "approve",
            "confidence": 0.92,
        }
        result = _generate_human_readable_report(report)
        assert "CLM20260115_001" in result
        assert "approve" in result
        assert "185,000" in result


# =========================================================================
# Lambda ハンドラーテスト
# =========================================================================


class TestDamageAssessmentHandler:
    """損害評価 Lambda ハンドラーのテスト"""

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT": "test-ap-ext-s3alias",
        "OUTPUT_BUCKET": "test-output-bucket",
        "BEDROCK_MODEL_ID": "amazon.nova-lite-v1:0",
        "LOG_PII_DATA": "false",
    })
    @patch("functions.damage_assessment.handler.boto3")
    @patch("functions.damage_assessment.handler.S3ApHelper")
    def test_handler_manual_review(self, mock_s3ap_cls, mock_boto3):
        """損害未検出で MANUAL_REVIEW が返ること"""
        from functions.damage_assessment.handler import handler

        mock_s3ap = MagicMock()
        mock_s3ap_cls.return_value = mock_s3ap
        mock_body = MagicMock()
        mock_body.read.return_value = b"fake_image"
        mock_s3ap.get_object.return_value = {"Body": mock_body}

        mock_rekognition = MagicMock()
        mock_rekognition.detect_labels.return_value = {
            "Labels": [
                {"Name": "Car", "Confidence": 99.0, "Instances": [{}]},
            ]
        }

        mock_s3_client = MagicMock()

        def client_factory(service_name):
            if service_name == "rekognition":
                return mock_rekognition
            return mock_s3_client

        mock_boto3.client.side_effect = client_factory

        event = {"Key": "claims/CLM001/photo.jpg", "Size": 2000000}
        context = MagicMock()

        result = handler(event, context)

        assert result["status"] == "MANUAL_REVIEW"
        assert result["damage_assessment"]["reason_code"] == "NO_DAMAGE_LABELS_DETECTED"
