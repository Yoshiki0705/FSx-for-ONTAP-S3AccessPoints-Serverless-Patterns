"""UC11 小売 / EC 画像タグ付け・カタログメタデータ生成 ユニットテスト

Rekognition ラベル検出、閾値フラグ、カタログメタデータ生成をテストする。
Lambda ハンドラーの入出力形式、エラーハンドリング、
ヘルパー関数のロジックを検証する。

Requirements: 13.1, 13.2
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# shared モジュールと UC11 関数のパスを追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from functions.image_tagging.handler import (
    detect_labels,
    evaluate_confidence,
)
from functions.catalog_metadata.handler import (
    REQUIRED_METADATA_FIELDS,
    _ensure_required_fields,
    _generate_fallback_metadata,
)
from functions.quality_check.handler import (
    get_image_dimensions,
    validate_quality,
    _get_png_dimensions,
    _get_jpeg_dimensions,
    _get_webp_dimensions,
)


# =========================================================================
# detect_labels テスト
# =========================================================================


class TestDetectLabels:
    """Rekognition DetectLabels のテスト"""

    def test_detect_labels_success(self):
        """正常系: ラベルが正しく検出されること"""
        mock_client = MagicMock()
        mock_client.detect_labels.return_value = {
            "Labels": [
                {"Name": "Clothing", "Confidence": 99.8},
                {"Name": "Blue", "Confidence": 95.1},
                {"Name": "Shirt", "Confidence": 88.5},
            ]
        }

        result = detect_labels(mock_client, b"fake_image_bytes")

        assert len(result) == 3
        assert result[0] == {"name": "Clothing", "confidence": 99.8}
        assert result[1] == {"name": "Blue", "confidence": 95.1}
        assert result[2] == {"name": "Shirt", "confidence": 88.5}

    def test_detect_labels_empty_response(self):
        """空のレスポンスで空リストが返ること"""
        mock_client = MagicMock()
        mock_client.detect_labels.return_value = {"Labels": []}

        result = detect_labels(mock_client, b"fake_image_bytes")
        assert result == []

    def test_detect_labels_no_labels_key(self):
        """Labels キーがない場合に空リストが返ること"""
        mock_client = MagicMock()
        mock_client.detect_labels.return_value = {}

        result = detect_labels(mock_client, b"fake_image_bytes")
        assert result == []

    def test_detect_labels_max_labels(self):
        """max_labels パラメータが正しく渡されること"""
        mock_client = MagicMock()
        mock_client.detect_labels.return_value = {"Labels": []}

        detect_labels(mock_client, b"fake_image_bytes", max_labels=5)

        mock_client.detect_labels.assert_called_once_with(
            Image={"Bytes": b"fake_image_bytes"},
            MaxLabels=5,
        )


# =========================================================================
# evaluate_confidence テスト
# =========================================================================


class TestEvaluateConfidence:
    """信頼度評価のテスト"""

    def test_above_threshold(self):
        """閾値以上の場合に above_threshold=True が返ること"""
        labels = [
            {"name": "Clothing", "confidence": 99.8},
            {"name": "Blue", "confidence": 95.1},
        ]
        max_conf, above = evaluate_confidence(labels, 70.0)
        assert max_conf == 99.8
        assert above is True

    def test_below_threshold(self):
        """閾値未満の場合に above_threshold=False が返ること"""
        labels = [
            {"name": "Object", "confidence": 45.0},
            {"name": "Unknown", "confidence": 30.0},
        ]
        max_conf, above = evaluate_confidence(labels, 70.0)
        assert max_conf == 45.0
        assert above is False

    def test_at_threshold(self):
        """閾値と等しい場合に above_threshold=True が返ること"""
        labels = [{"name": "Shirt", "confidence": 70.0}]
        max_conf, above = evaluate_confidence(labels, 70.0)
        assert max_conf == 70.0
        assert above is True

    def test_empty_labels(self):
        """空リストの場合に max_confidence=0.0, above_threshold=False が返ること"""
        max_conf, above = evaluate_confidence([], 70.0)
        assert max_conf == 0.0
        assert above is False

    def test_single_label(self):
        """単一ラベルの場合に正しく評価されること"""
        labels = [{"name": "Dress", "confidence": 85.5}]
        max_conf, above = evaluate_confidence(labels, 80.0)
        assert max_conf == 85.5
        assert above is True


# =========================================================================
# _ensure_required_fields テスト
# =========================================================================


class TestEnsureRequiredFields:
    """必須フィールド補完のテスト"""

    def test_complete_metadata_unchanged(self):
        """完全なメタデータが変更されないこと"""
        metadata = {
            "product_category": "Apparel > Tops",
            "color": "Blue",
            "material": "Cotton",
            "style_attributes": ["casual"],
            "suggested_tags": ["summer"],
        }
        labels = [{"name": "Shirt", "confidence": 90.0}]

        result = _ensure_required_fields(metadata, labels)
        assert result["product_category"] == "Apparel > Tops"
        assert result["color"] == "Blue"
        assert result["material"] == "Cotton"
        assert result["style_attributes"] == ["casual"]

    def test_missing_fields_filled(self):
        """欠落フィールドがデフォルト値で補完されること"""
        metadata = {}
        labels = [{"name": "Shirt", "confidence": 90.0}]

        result = _ensure_required_fields(metadata, labels)
        assert result["product_category"] == "Uncategorized"
        assert result["color"] == "Unknown"
        assert result["material"] == "Unknown"
        assert result["style_attributes"] == []

    def test_none_fields_filled(self):
        """None フィールドがデフォルト値で補完されること"""
        metadata = {
            "product_category": None,
            "color": None,
            "material": None,
            "style_attributes": None,
        }
        labels = [{"name": "Bag", "confidence": 80.0}]

        result = _ensure_required_fields(metadata, labels)
        assert result["product_category"] == "Uncategorized"
        assert result["color"] == "Unknown"
        assert result["material"] == "Unknown"
        assert result["style_attributes"] == []

    def test_empty_string_fields_filled(self):
        """空文字列フィールドがデフォルト値で補完されること"""
        metadata = {
            "product_category": "",
            "color": "",
            "material": "",
            "style_attributes": [],
        }
        labels = []

        result = _ensure_required_fields(metadata, labels)
        assert result["product_category"] == "Uncategorized"
        assert result["color"] == "Unknown"
        assert result["material"] == "Unknown"


# =========================================================================
# _generate_fallback_metadata テスト
# =========================================================================


class TestGenerateFallbackMetadata:
    """フォールバックメタデータ生成のテスト"""

    def test_fallback_with_labels(self):
        """ラベルからフォールバックメタデータが生成されること"""
        labels = [
            {"name": "Clothing", "confidence": 99.0},
            {"name": "Blue", "confidence": 95.0},
        ]
        result = _generate_fallback_metadata(labels)

        assert result["product_category"] == "Uncategorized"
        assert result["color"] == "Unknown"
        assert result["material"] == "Unknown"
        assert result["style_attributes"] == []
        assert "Clothing" in result["suggested_tags"]
        assert "Blue" in result["suggested_tags"]

    def test_fallback_empty_labels(self):
        """空ラベルでフォールバックメタデータが生成されること"""
        result = _generate_fallback_metadata([])

        assert result["product_category"] == "Uncategorized"
        assert result["suggested_tags"] == []


# =========================================================================
# validate_quality テスト
# =========================================================================


class TestValidateQuality:
    """画像品質検証のテスト"""

    def test_pass_all_checks(self):
        """全チェック通過で PASS が返ること"""
        status, metrics, issues = validate_quality(
            width=1200, height=1200, file_size=500000
        )
        assert status == "PASS"
        assert issues == []
        assert metrics["width"] == 1200
        assert metrics["height"] == 1200

    def test_fail_low_resolution(self):
        """解像度不足で FAIL が返ること"""
        status, metrics, issues = validate_quality(
            width=400, height=400, file_size=500000
        )
        assert status == "FAIL"
        assert any("Width" in i for i in issues)
        assert any("Height" in i for i in issues)

    def test_fail_file_too_small(self):
        """ファイルサイズ不足で FAIL が返ること"""
        status, metrics, issues = validate_quality(
            width=1000, height=1000, file_size=50000
        )
        assert status == "FAIL"
        assert any("below minimum" in i for i in issues)

    def test_fail_file_too_large(self):
        """ファイルサイズ超過で FAIL が返ること"""
        status, metrics, issues = validate_quality(
            width=1000, height=1000, file_size=60000000
        )
        assert status == "FAIL"
        assert any("exceeds maximum" in i for i in issues)

    def test_fail_aspect_ratio_too_low(self):
        """アスペクト比が低すぎる場合に FAIL が返ること"""
        status, metrics, issues = validate_quality(
            width=400, height=1000, file_size=500000,
            min_resolution=100,
        )
        assert status == "FAIL"
        assert any("Aspect ratio" in i and "below" in i for i in issues)

    def test_fail_aspect_ratio_too_high(self):
        """アスペクト比が高すぎる場合に FAIL が返ること"""
        status, metrics, issues = validate_quality(
            width=2500, height=1000, file_size=500000,
            min_resolution=100,
        )
        assert status == "FAIL"
        assert any("Aspect ratio" in i and "exceeds" in i for i in issues)

    def test_none_dimensions(self):
        """解像度が None の場合に FAIL が返ること"""
        status, metrics, issues = validate_quality(
            width=None, height=None, file_size=500000
        )
        assert status == "FAIL"
        assert any("Unable to determine" in i for i in issues)

    def test_custom_thresholds(self):
        """カスタム閾値が正しく適用されること"""
        status, metrics, issues = validate_quality(
            width=500, height=500, file_size=200000,
            min_resolution=400,
            min_file_size=100000,
            max_file_size=1000000,
        )
        assert status == "PASS"
        assert issues == []


# =========================================================================
# get_image_dimensions テスト
# =========================================================================


class TestGetImageDimensions:
    """画像サイズ取得のテスト"""

    def test_png_dimensions(self):
        """PNG ヘッダーから正しいサイズが取得されること"""
        import struct
        # PNG signature + IHDR chunk
        png_data = b"\x89PNG\r\n\x1a\n"
        # IHDR chunk: length(4) + "IHDR"(4) + width(4) + height(4)
        ihdr_length = struct.pack(">I", 13)
        ihdr_type = b"IHDR"
        width = struct.pack(">I", 1920)
        height = struct.pack(">I", 1080)
        png_data += ihdr_length + ihdr_type + width + height + b"\x00" * 5

        result = get_image_dimensions(png_data, "test.png")
        assert result == (1920, 1080)

    def test_invalid_png(self):
        """不正な PNG データで None が返ること"""
        result = get_image_dimensions(b"not a png", "test.png")
        assert result is None

    def test_unknown_format(self):
        """不明なフォーマットで None が返ること"""
        result = get_image_dimensions(b"some data", "test.bmp")
        assert result is None

    def test_empty_data(self):
        """空データで None が返ること"""
        result = get_image_dimensions(b"", "test.jpg")
        assert result is None


# =========================================================================
# Lambda ハンドラーテスト (mock)
# =========================================================================


class TestImageTaggingHandler:
    """画像タグ付け Lambda ハンドラーのテスト"""

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT": "test-ap-ext-s3alias",
        "OUTPUT_BUCKET": "test-output-bucket",
        "CONFIDENCE_THRESHOLD": "70",
    })
    @patch("functions.image_tagging.handler.OutputWriter")
    @patch("functions.image_tagging.handler.boto3")
    @patch("functions.image_tagging.handler.S3ApHelper")
    def test_handler_success_above_threshold(
        self, mock_s3ap_cls, mock_boto3, mock_output_writer_cls
    ):
        """正常系: 閾値以上で SUCCESS ステータスが返ること"""
        from functions.image_tagging.handler import handler

        # Setup mocks
        mock_s3ap = MagicMock()
        mock_s3ap_cls.return_value = mock_s3ap
        mock_body = MagicMock()
        mock_body.read.return_value = b"fake_image_data"
        mock_s3ap.get_object.return_value = {"Body": mock_body}

        mock_rekognition = MagicMock()
        mock_rekognition.detect_labels.return_value = {
            "Labels": [
                {"Name": "Clothing", "Confidence": 99.8},
                {"Name": "Blue", "Confidence": 95.1},
            ]
        }

        mock_s3_client = MagicMock()

        def client_factory(service_name):
            if service_name == "rekognition":
                return mock_rekognition
            return mock_s3_client

        mock_boto3.client.side_effect = client_factory

        # OutputWriter mock
        mock_writer = MagicMock()
        mock_writer.target_description = "Standard S3 bucket 'test-output-bucket'"
        mock_writer.build_s3_uri.return_value = "s3://test-output-bucket/out.json"
        mock_output_writer_cls.from_env.return_value = mock_writer

        event = {"Key": "products/SKU12345_front.jpg", "Size": 2097152}
        context = MagicMock()

        result = handler(event, context)

        assert result["status"] == "SUCCESS"
        assert result["file_key"] == "products/SKU12345_front.jpg"
        assert result["max_confidence"] == 99.8
        assert result["above_threshold"] is True
        assert len(result["labels"]) == 2
        # OutputWriter.put_json が呼ばれたことを確認
        mock_writer.put_json.assert_called_once()

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT": "test-ap-ext-s3alias",
        "OUTPUT_BUCKET": "test-output-bucket",
        "CONFIDENCE_THRESHOLD": "70",
    })
    @patch("functions.image_tagging.handler.OutputWriter")
    @patch("functions.image_tagging.handler.boto3")
    @patch("functions.image_tagging.handler.S3ApHelper")
    def test_handler_manual_review(
        self, mock_s3ap_cls, mock_boto3, mock_output_writer_cls
    ):
        """閾値未満で MANUAL_REVIEW ステータスが返ること"""
        from functions.image_tagging.handler import handler

        mock_s3ap = MagicMock()
        mock_s3ap_cls.return_value = mock_s3ap
        mock_body = MagicMock()
        mock_body.read.return_value = b"fake_image_data"
        mock_s3ap.get_object.return_value = {"Body": mock_body}

        mock_rekognition = MagicMock()
        mock_rekognition.detect_labels.return_value = {
            "Labels": [
                {"Name": "Object", "Confidence": 45.0},
            ]
        }

        mock_s3_client = MagicMock()

        def client_factory(service_name):
            if service_name == "rekognition":
                return mock_rekognition
            return mock_s3_client

        mock_boto3.client.side_effect = client_factory

        mock_writer = MagicMock()
        mock_writer.target_description = "Standard S3 bucket 'test-output-bucket'"
        mock_writer.build_s3_uri.return_value = "s3://test-output-bucket/out.json"
        mock_output_writer_cls.from_env.return_value = mock_writer

        event = {"Key": "products/unclear_image.jpg", "Size": 500000}
        context = MagicMock()

        result = handler(event, context)

        assert result["status"] == "MANUAL_REVIEW"
        assert result["above_threshold"] is False


class TestCatalogMetadataHandler:
    """カタログメタデータ生成 Lambda ハンドラーのテスト"""

    @patch.dict(os.environ, {
        "OUTPUT_BUCKET": "test-output-bucket",
        "BEDROCK_MODEL_ID": "amazon.nova-lite-v1:0",
    })
    @patch("functions.catalog_metadata.handler.OutputWriter")
    @patch("functions.catalog_metadata.handler.boto3")
    def test_handler_success(self, mock_boto3, mock_output_writer_cls):
        """正常系: メタデータ生成が成功すること"""
        from functions.catalog_metadata.handler import handler

        mock_bedrock = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps({
            "results": [{
                "outputText": json.dumps({
                    "product_category": "Apparel > Tops > Shirts",
                    "color": "Blue",
                    "material": "Cotton",
                    "style_attributes": ["casual", "short-sleeve"],
                    "suggested_tags": ["summer", "everyday"],
                })
            }]
        }).encode()
        mock_bedrock.invoke_model.return_value = {"body": mock_body}

        mock_s3_client = MagicMock()

        def client_factory(service_name):
            if service_name == "bedrock-runtime":
                return mock_bedrock
            return mock_s3_client

        mock_boto3.client.side_effect = client_factory

        mock_writer = MagicMock()
        mock_writer.target_description = "Standard S3 bucket 'test-output-bucket'"
        mock_writer.build_s3_uri.return_value = "s3://test-output-bucket/out.json"
        mock_output_writer_cls.from_env.return_value = mock_writer

        event = {
            "file_key": "products/SKU12345_front.jpg",
            "labels": [
                {"name": "Clothing", "confidence": 99.8},
                {"name": "Blue", "confidence": 95.1},
            ],
        }
        context = MagicMock()

        result = handler(event, context)

        assert result["status"] == "SUCCESS"
        assert result["file_key"] == "products/SKU12345_front.jpg"
        assert "catalog_metadata" in result
        assert result["catalog_metadata"]["product_category"] == "Apparel > Tops > Shirts"
        assert result["catalog_metadata"]["color"] == "Blue"
        assert "output_key" in result

    @patch.dict(os.environ, {
        "OUTPUT_BUCKET": "test-output-bucket",
        "BEDROCK_MODEL_ID": "amazon.nova-lite-v1:0",
    })
    @patch("functions.catalog_metadata.handler.OutputWriter")
    @patch("functions.catalog_metadata.handler.boto3")
    def test_handler_bedrock_invalid_json_fallback(
        self, mock_boto3, mock_output_writer_cls
    ):
        """Bedrock が無効な JSON を返した場合にフォールバックが使用されること"""
        from functions.catalog_metadata.handler import handler

        mock_bedrock = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps({
            "results": [{"outputText": "This is not valid JSON at all"}]
        }).encode()
        mock_bedrock.invoke_model.return_value = {"body": mock_body}

        mock_s3_client = MagicMock()

        def client_factory(service_name):
            if service_name == "bedrock-runtime":
                return mock_bedrock
            return mock_s3_client

        mock_boto3.client.side_effect = client_factory

        mock_writer = MagicMock()
        mock_writer.target_description = "Standard S3 bucket 'test-output-bucket'"
        mock_writer.build_s3_uri.return_value = "s3://test-output-bucket/out.json"
        mock_output_writer_cls.from_env.return_value = mock_writer

        event = {
            "file_key": "products/SKU99999.png",
            "labels": [{"name": "Bag", "confidence": 80.0}],
        }
        context = MagicMock()

        result = handler(event, context)

        assert result["status"] == "SUCCESS"
        assert result["catalog_metadata"]["product_category"] == "Uncategorized"
        assert result["catalog_metadata"]["color"] == "Unknown"
