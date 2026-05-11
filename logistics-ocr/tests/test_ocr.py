"""UC12 物流 / サプライチェーン OCR・データ構造化・在庫分析 ユニットテスト

Cross-Region Textract 呼び出し、データ正規化、在庫画像分析をテストする。
Lambda ハンドラーの入出力形式、エラーハンドリング、
ヘルパー関数のロジックを検証する。

Requirements: 13.1, 13.2
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch


# shared モジュールと UC12 関数のパスを追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from functions.ocr.handler import (
    _extract_text_from_blocks,
    _extract_forms_from_blocks,
    _evaluate_confidence,
)
from functions.data_structuring.handler import (
    _ensure_required_fields,
    _parse_bedrock_response,
)
from functions.inventory_analysis.handler import (
    detect_inventory_objects,
    count_inventory_items,
    estimate_shelf_occupancy,
)


# =========================================================================
# OCR テキスト抽出テスト
# =========================================================================


class TestExtractTextFromBlocks:
    """Textract ブロックからのテキスト抽出テスト"""

    def test_extract_lines(self):
        """LINE ブロックからテキストが正しく抽出されること"""
        blocks = [
            {"BlockType": "LINE", "Text": "送り主: 東京物流株式会社"},
            {"BlockType": "LINE", "Text": "届け先: 大阪配送センター"},
            {"BlockType": "WORD", "Text": "ignored"},
        ]
        result = _extract_text_from_blocks(blocks)
        assert "東京物流株式会社" in result
        assert "大阪配送センター" in result
        assert "ignored" not in result

    def test_empty_blocks(self):
        """空ブロックで空文字列が返ること"""
        result = _extract_text_from_blocks([])
        assert result == ""

    def test_no_line_blocks(self):
        """LINE ブロックがない場合に空文字列が返ること"""
        blocks = [
            {"BlockType": "WORD", "Text": "word1"},
            {"BlockType": "TABLE", "Id": "t1"},
        ]
        result = _extract_text_from_blocks(blocks)
        assert result == ""


# =========================================================================
# OCR フォーム抽出テスト
# =========================================================================


class TestExtractFormsFromBlocks:
    """Textract ブロックからのフォーム抽出テスト"""

    def test_extract_key_value_pairs(self):
        """KEY_VALUE_SET からフォームフィールドが抽出されること"""
        blocks = [
            {
                "Id": "key1",
                "BlockType": "KEY_VALUE_SET",
                "EntityTypes": ["KEY"],
                "Confidence": 95.0,
                "Relationships": [
                    {"Type": "CHILD", "Ids": ["word1"]},
                    {"Type": "VALUE", "Ids": ["val1"]},
                ],
            },
            {
                "Id": "val1",
                "BlockType": "KEY_VALUE_SET",
                "EntityTypes": ["VALUE"],
                "Relationships": [
                    {"Type": "CHILD", "Ids": ["word2"]},
                ],
            },
            {"Id": "word1", "BlockType": "WORD", "Text": "追跡番号"},
            {"Id": "word2", "BlockType": "WORD", "Text": "1234-5678-9012"},
        ]
        result = _extract_forms_from_blocks(blocks)
        assert len(result) == 1
        assert result[0]["key"] == "追跡番号"
        assert result[0]["value"] == "1234-5678-9012"
        assert result[0]["confidence"] == 95.0

    def test_empty_blocks(self):
        """空ブロックで空リストが返ること"""
        result = _extract_forms_from_blocks([])
        assert result == []


# =========================================================================
# 信頼度評価テスト
# =========================================================================


class TestEvaluateConfidence:
    """信頼度評価のテスト"""

    def test_all_above_threshold(self):
        """全フィールドが閾値以上の場合"""
        forms = [
            {"key": "sender", "value": "Tokyo", "confidence": 95.0},
            {"key": "recipient", "value": "Osaka", "confidence": 88.0},
        ]
        all_above, low_fields = _evaluate_confidence(forms, 80.0)
        assert all_above is True
        assert low_fields == []

    def test_some_below_threshold(self):
        """一部フィールドが閾値未満の場合"""
        forms = [
            {"key": "sender", "value": "Tokyo", "confidence": 95.0},
            {"key": "tracking", "value": "???", "confidence": 60.0},
        ]
        all_above, low_fields = _evaluate_confidence(forms, 80.0)
        assert all_above is False
        assert len(low_fields) == 1
        assert low_fields[0]["key"] == "tracking"

    def test_empty_forms(self):
        """空フォームで all_above=True が返ること"""
        all_above, low_fields = _evaluate_confidence([], 80.0)
        assert all_above is True
        assert low_fields == []


# =========================================================================
# データ構造化テスト
# =========================================================================


class TestEnsureRequiredFields:
    """必須フィールド補完のテスト"""

    def test_complete_data_unchanged(self):
        """完全なデータが変更されないこと"""
        data = {
            "sender_name": "東京物流",
            "sender_address": "東京都港区",
            "recipient_name": "大阪配送",
            "recipient_address": "大阪市北区",
            "tracking_number": "1234-5678",
            "items": [{"description": "書類", "quantity": 1}],
            "total_quantity": 1,
        }
        result = _ensure_required_fields(data)
        assert result["sender_name"] == "東京物流"
        assert result["tracking_number"] == "1234-5678"

    def test_missing_fields_filled(self):
        """欠落フィールドがデフォルト値で補完されること"""
        data = {}
        result = _ensure_required_fields(data)
        assert result["sender_name"] == "Unknown"
        assert result["recipient_name"] == "Unknown"
        assert result["tracking_number"] == "Unknown"
        assert result["items"] == []
        assert result["total_quantity"] == 0


class TestParsBedrockResponse:
    """Bedrock レスポンス解析のテスト"""

    def test_parse_nova_response(self):
        """Nova モデルレスポンスが正しく解析されること"""
        response_body = json.dumps({
            "results": [{
                "outputText": json.dumps({
                    "sender_name": "テスト送り主",
                    "tracking_number": "ABC-123",
                })
            }]
        }).encode()
        result = _parse_bedrock_response(response_body)
        assert result["sender_name"] == "テスト送り主"
        assert result["tracking_number"] == "ABC-123"

    def test_parse_invalid_json_returns_empty(self):
        """無効な JSON で空辞書が返ること"""
        response_body = json.dumps({
            "results": [{"outputText": "This is not JSON"}]
        }).encode()
        result = _parse_bedrock_response(response_body)
        assert result == {}


# =========================================================================
# 在庫分析テスト
# =========================================================================


class TestDetectInventoryObjects:
    """Rekognition 在庫物体検出のテスト"""

    def test_detect_labels_success(self):
        """正常系: ラベルが正しく検出されること"""
        mock_client = MagicMock()
        mock_client.detect_labels.return_value = {
            "Labels": [
                {
                    "Name": "Box",
                    "Confidence": 98.5,
                    "Instances": [{"BoundingBox": {}}] * 5,
                    "Parents": [{"Name": "Package"}],
                },
                {
                    "Name": "Shelf",
                    "Confidence": 95.0,
                    "Instances": [{"BoundingBox": {}}],
                    "Parents": [],
                },
            ]
        }
        result = detect_inventory_objects(mock_client, b"fake_image")
        assert len(result) == 2
        assert result[0]["name"] == "Box"
        assert result[0]["instances"] == 5
        assert result[1]["name"] == "Shelf"

    def test_detect_labels_empty(self):
        """空レスポンスで空リストが返ること"""
        mock_client = MagicMock()
        mock_client.detect_labels.return_value = {"Labels": []}
        result = detect_inventory_objects(mock_client, b"fake_image")
        assert result == []


class TestCountInventoryItems:
    """在庫アイテムカウントのテスト"""

    def test_count_inventory_labels(self):
        """在庫関連ラベルが正しくカウントされること"""
        labels = [
            {"name": "Box", "confidence": 95.0, "instances": 10, "parents": ["Package"]},
            {"name": "Pallet", "confidence": 88.0, "instances": 3, "parents": []},
            {"name": "Person", "confidence": 99.0, "instances": 2, "parents": []},
        ]
        result = count_inventory_items(labels, 70.0)
        assert result["item_counts"]["Box"]["count"] == 10
        assert result["item_counts"]["Pallet"]["count"] == 3
        assert "Person" not in result["item_counts"]
        assert result["total_items"] == 13

    def test_below_threshold_excluded(self):
        """閾値未満のラベルが除外されること"""
        labels = [
            {"name": "Box", "confidence": 50.0, "instances": 5, "parents": []},
        ]
        result = count_inventory_items(labels, 70.0)
        assert result["total_items"] == 0


class TestEstimateShelfOccupancy:
    """棚占有率推定のテスト"""

    def test_with_shelf_and_items(self):
        """棚とアイテムがある場合に占有率が計算されること"""
        labels = [
            {"name": "Shelf", "confidence": 95.0, "instances": 1, "parents": []},
            {"name": "Box", "confidence": 90.0, "instances": 10, "parents": []},
        ]
        result = estimate_shelf_occupancy(labels)
        assert 0.0 < result <= 1.0

    def test_no_shelf_returns_zero(self):
        """棚がない場合に 0.0 が返ること"""
        labels = [
            {"name": "Box", "confidence": 90.0, "instances": 10, "parents": []},
        ]
        result = estimate_shelf_occupancy(labels)
        assert result == 0.0

    def test_empty_labels(self):
        """空ラベルで 0.0 が返ること"""
        result = estimate_shelf_occupancy([])
        assert result == 0.0


# =========================================================================
# Lambda ハンドラーテスト (mock)
# =========================================================================


class TestOcrHandler:
    """OCR Lambda ハンドラーのテスト"""

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT": "test-ap-ext-s3alias",
        "OUTPUT_BUCKET": "test-output-bucket",
        "CROSS_REGION": "us-east-1",
        "CONFIDENCE_THRESHOLD": "80",
    })
    @patch("functions.ocr.handler.OutputWriter")
    @patch("functions.ocr.handler.CrossRegionClient")
    @patch("functions.ocr.handler.S3ApHelper")
    def test_handler_success(self, mock_s3ap_cls, mock_cr_cls, mock_output_writer_cls):
        """正常系: OCR が成功すること"""
        from functions.ocr.handler import handler

        mock_s3ap = MagicMock()
        mock_s3ap_cls.return_value = mock_s3ap
        mock_body = MagicMock()
        mock_body.read.return_value = b"fake_pdf_data"
        mock_body.close = MagicMock()
        mock_s3ap.get_object.return_value = {"Body": mock_body}

        mock_cr = MagicMock()
        mock_cr_cls.return_value = mock_cr
        mock_cr.analyze_document.return_value = {
            "Blocks": [
                {"BlockType": "LINE", "Text": "配送伝票"},
            ]
        }

        mock_writer = MagicMock()
        mock_writer.target_description = "Standard S3 bucket 'test-output-bucket'"
        mock_writer.build_s3_uri.return_value = "s3://test-output-bucket/out.json"
        mock_output_writer_cls.from_env.return_value = mock_writer

        event = {"Key": "slips/delivery_001.pdf", "Size": 1048576}
        context = MagicMock()

        result = handler(event, context)

        assert result["status"] == "SUCCESS"
        assert result["file_key"] == "slips/delivery_001.pdf"
        assert "配送伝票" in result["extracted_text"]
