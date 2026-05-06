"""Event Processor Lambda ユニットテスト

イベント処理ロジックのテスト:
- EventBridge イベントからのファイル情報抽出
- Rekognition DetectLabels 呼び出し
- 信頼度評価ロジック
- Bedrock メタデータ生成
- S3 出力書き込み
- エラーハンドリング

カバレッジ目標: 80%以上
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, ANY

import pytest

# Add project root to path for shared module imports
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Import handler module
_handler_path = Path(__file__).resolve().parent.parent / "lambdas" / "event_processor" / "handler.py"
_spec = importlib.util.spec_from_file_location("event_processor_handler", _handler_path)
_module = importlib.util.module_from_spec(_spec)
sys.modules["event_processor_handler"] = _module
_spec.loader.exec_module(_module)

from event_processor_handler import (
    detect_labels,
    evaluate_confidence,
    generate_catalog_metadata,
    process_image,
    handler,
)


class TestDetectLabels:
    """detect_labels 関数のテスト"""

    def test_returns_labels_with_name_and_confidence(self):
        """正常なレスポンスからラベルリストを返す"""
        mock_client = MagicMock()
        mock_client.detect_labels.return_value = {
            "Labels": [
                {"Name": "Product", "Confidence": 95.5},
                {"Name": "Electronics", "Confidence": 88.123},
            ]
        }

        result = detect_labels(mock_client, b"fake_image_data")

        assert len(result) == 2
        assert result[0] == {"name": "Product", "confidence": 95.5}
        assert result[1] == {"name": "Electronics", "confidence": 88.12}

    def test_empty_labels_response(self):
        """ラベルが検出されない場合は空リストを返す"""
        mock_client = MagicMock()
        mock_client.detect_labels.return_value = {"Labels": []}

        result = detect_labels(mock_client, b"fake_image_data")

        assert result == []

    def test_respects_max_labels_parameter(self):
        """max_labels パラメータが Rekognition に渡される"""
        mock_client = MagicMock()
        mock_client.detect_labels.return_value = {"Labels": []}

        detect_labels(mock_client, b"fake_image_data", max_labels=5)

        mock_client.detect_labels.assert_called_once_with(
            Image={"Bytes": b"fake_image_data"},
            MaxLabels=5,
        )

    def test_confidence_rounded_to_two_decimals(self):
        """信頼度は小数点以下2桁に丸められる"""
        mock_client = MagicMock()
        mock_client.detect_labels.return_value = {
            "Labels": [{"Name": "Test", "Confidence": 87.6789}]
        }

        result = detect_labels(mock_client, b"fake_image_data")

        assert result[0]["confidence"] == 87.68


class TestEvaluateConfidence:
    """evaluate_confidence 関数のテスト"""

    def test_above_threshold(self):
        """最大信頼度が閾値以上の場合"""
        labels = [
            {"name": "Product", "confidence": 95.0},
            {"name": "Object", "confidence": 60.0},
        ]

        max_conf, above = evaluate_confidence(labels, 70.0)

        assert max_conf == 95.0
        assert above is True

    def test_below_threshold(self):
        """最大信頼度が閾値未満の場合"""
        labels = [
            {"name": "Product", "confidence": 50.0},
            {"name": "Object", "confidence": 60.0},
        ]

        max_conf, above = evaluate_confidence(labels, 70.0)

        assert max_conf == 60.0
        assert above is False

    def test_empty_labels(self):
        """ラベルが空の場合"""
        max_conf, above = evaluate_confidence([], 70.0)

        assert max_conf == 0.0
        assert above is False

    def test_exactly_at_threshold(self):
        """信頼度が閾値と完全一致の場合"""
        labels = [{"name": "Product", "confidence": 70.0}]

        max_conf, above = evaluate_confidence(labels, 70.0)

        assert max_conf == 70.0
        assert above is True


class TestGenerateCatalogMetadata:
    """generate_catalog_metadata 関数のテスト"""

    def test_successful_bedrock_invocation(self):
        """Bedrock 呼び出し成功時にメタデータを返す"""
        mock_client = MagicMock()
        response_body = json.dumps({
            "results": [{"outputText": json.dumps({
                "title": "Test Product",
                "description": "A test product",
                "category": "electronics",
                "tags": ["product", "electronics"],
            })}]
        }).encode()
        mock_client.invoke_model.return_value = {
            "body": MagicMock(read=MagicMock(return_value=response_body))
        }

        result = generate_catalog_metadata(
            mock_client, "amazon.nova-lite-v1:0",
            "products/test.jpg",
            [{"name": "Product", "confidence": 95.0}],
        )

        assert result["title"] == "Test Product"
        assert result["category"] == "electronics"

    def test_bedrock_failure_returns_fallback(self):
        """Bedrock 呼び出し失敗時にフォールバックメタデータを返す"""
        mock_client = MagicMock()
        mock_client.invoke_model.side_effect = Exception("Service unavailable")

        labels = [
            {"name": "Product", "confidence": 95.0},
            {"name": "Electronics", "confidence": 88.0},
        ]

        result = generate_catalog_metadata(
            mock_client, "amazon.nova-lite-v1:0",
            "products/test_item.jpg",
            labels,
        )

        assert result["title"] == "test_item"
        assert result["category"] == "uncategorized"
        assert "Product" in result["tags"]

    def test_non_json_bedrock_response(self):
        """Bedrock が非 JSON テキストを返した場合"""
        mock_client = MagicMock()
        response_body = json.dumps({
            "results": [{"outputText": "This is not valid JSON"}]
        }).encode()
        mock_client.invoke_model.return_value = {
            "body": MagicMock(read=MagicMock(return_value=response_body))
        }

        result = generate_catalog_metadata(
            mock_client, "amazon.nova-lite-v1:0",
            "products/item.jpg",
            [{"name": "Product", "confidence": 90.0}],
        )

        assert "title" in result
        assert "category" in result


class TestProcessImage:
    """process_image 関数のテスト"""

    def test_successful_processing(self):
        """正常な画像処理フロー"""
        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=MagicMock(return_value=b"fake_image_bytes"))
        }

        mock_rek = MagicMock()
        mock_rek.detect_labels.return_value = {
            "Labels": [
                {"Name": "Product", "Confidence": 95.0},
                {"Name": "Shoe", "Confidence": 88.0},
            ]
        }

        mock_bedrock = MagicMock()
        response_body = json.dumps({
            "results": [{"outputText": json.dumps({
                "title": "Running Shoe",
                "description": "Athletic footwear",
                "category": "shoes",
                "tags": ["shoe", "athletic"],
            })}]
        }).encode()
        mock_bedrock.invoke_model.return_value = {
            "body": MagicMock(read=MagicMock(return_value=response_body))
        }

        result = process_image(
            s3_client=mock_s3,
            rekognition_client=mock_rek,
            bedrock_client=mock_bedrock,
            source_bucket="test-source",
            output_bucket="test-output",
            file_key="products/shoe_001.jpg",
            confidence_threshold=70.0,
            bedrock_model_id="amazon.nova-lite-v1:0",
            event_time="2024-01-15T10:30:00Z",
        )

        assert result["status"] == "SUCCESS"
        assert result["file_key"] == "products/shoe_001.jpg"
        assert result["max_confidence"] == 95.0
        assert result["above_threshold"] is True
        assert len(result["labels"]) == 2
        assert result["processing_duration_ms"] > 0
        assert "tags_output_key" in result
        assert "metadata_output_key" in result

        # Verify S3 writes
        assert mock_s3.put_object.call_count == 2

    def test_below_threshold_returns_manual_review(self):
        """信頼度が閾値未満の場合 MANUAL_REVIEW を返す"""
        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=MagicMock(return_value=b"blurry_image"))
        }

        mock_rek = MagicMock()
        mock_rek.detect_labels.return_value = {
            "Labels": [{"Name": "Unknown", "Confidence": 30.0}]
        }

        mock_bedrock = MagicMock()
        mock_bedrock.invoke_model.side_effect = Exception("skip")

        result = process_image(
            s3_client=mock_s3,
            rekognition_client=mock_rek,
            bedrock_client=mock_bedrock,
            source_bucket="test-source",
            output_bucket="test-output",
            file_key="products/blurry.jpg",
            confidence_threshold=70.0,
            bedrock_model_id="amazon.nova-lite-v1:0",
        )

        assert result["status"] == "MANUAL_REVIEW"
        assert result["above_threshold"] is False

    def test_event_to_processing_latency_calculated(self):
        """event_time が指定された場合にレイテンシが計算される"""
        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=MagicMock(return_value=b"image"))
        }

        mock_rek = MagicMock()
        mock_rek.detect_labels.return_value = {"Labels": []}

        mock_bedrock = MagicMock()
        mock_bedrock.invoke_model.side_effect = Exception("skip")

        result = process_image(
            s3_client=mock_s3,
            rekognition_client=mock_rek,
            bedrock_client=mock_bedrock,
            source_bucket="test-source",
            output_bucket="test-output",
            file_key="products/test.jpg",
            confidence_threshold=70.0,
            bedrock_model_id="amazon.nova-lite-v1:0",
            event_time="2020-01-01T00:00:00Z",
        )

        # event_time is in the past, so latency should be positive
        assert result["event_to_processing_ms"] is not None
        assert result["event_to_processing_ms"] > 0


class TestHandler:
    """handler 関数のテスト"""

    @patch.dict(os.environ, {
        "SOURCE_BUCKET": "test-source",
        "OUTPUT_BUCKET": "test-output",
        "CONFIDENCE_THRESHOLD": "70",
        "BEDROCK_MODEL_ID": "amazon.nova-lite-v1:0",
        "USE_CASE": "event-driven-prototype",
    })
    @patch("event_processor_handler.boto3")
    def test_eventbridge_event_format(self, mock_boto3):
        """EventBridge イベント形式からファイル情報を正しく抽出する"""
        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=MagicMock(return_value=b"image_data"))
        }
        mock_rek = MagicMock()
        mock_rek.detect_labels.return_value = {
            "Labels": [{"Name": "Product", "Confidence": 90.0}]
        }
        mock_bedrock = MagicMock()
        mock_bedrock.invoke_model.side_effect = Exception("skip")

        mock_boto3.client.side_effect = lambda svc: {
            "s3": mock_s3,
            "rekognition": mock_rek,
            "bedrock-runtime": mock_bedrock,
        }[svc]

        event = {
            "detail": {
                "bucket": {"name": "test-source"},
                "object": {"key": "products/item.jpg", "size": 1024},
            },
            "time": "2024-01-15T10:30:00Z",
        }
        context = MagicMock()
        context.function_name = "test-function"
        context.aws_request_id = "test-request-id"

        result = handler(event, context)

        assert result["file_key"] == "products/item.jpg"
        assert result["status"] in ("SUCCESS", "MANUAL_REVIEW")

    @patch.dict(os.environ, {
        "SOURCE_BUCKET": "test-source",
        "OUTPUT_BUCKET": "test-output",
        "CONFIDENCE_THRESHOLD": "70",
        "BEDROCK_MODEL_ID": "amazon.nova-lite-v1:0",
        "USE_CASE": "event-driven-prototype",
    })
    @patch("event_processor_handler.boto3")
    def test_step_functions_direct_input(self, mock_boto3):
        """Step Functions 直接呼び出し形式を処理する"""
        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=MagicMock(return_value=b"image_data"))
        }
        mock_rek = MagicMock()
        mock_rek.detect_labels.return_value = {
            "Labels": [{"Name": "Shoe", "Confidence": 85.0}]
        }
        mock_bedrock = MagicMock()
        mock_bedrock.invoke_model.side_effect = Exception("skip")

        mock_boto3.client.side_effect = lambda svc: {
            "s3": mock_s3,
            "rekognition": mock_rek,
            "bedrock-runtime": mock_bedrock,
        }[svc]

        event = {"Key": "products/shoe.jpg", "event_time": "2024-01-15T10:30:00Z"}
        context = MagicMock()
        context.function_name = "test-function"
        context.aws_request_id = "test-request-id"

        result = handler(event, context)

        assert result["file_key"] == "products/shoe.jpg"

    @patch.dict(os.environ, {
        "SOURCE_BUCKET": "test-source",
        "OUTPUT_BUCKET": "test-output",
        "USE_CASE": "event-driven-prototype",
    })
    def test_missing_file_key_raises_error(self):
        """ファイルキーが見つからない場合はエラーレスポンスを返す"""
        event = {"detail": {}}
        context = MagicMock()
        context.function_name = "test-function"
        context.aws_request_id = "test-request-id"

        result = handler(event, context)

        # lambda_error_handler catches the ValueError
        assert result["statusCode"] == 500
        body = json.loads(result["body"])
        assert "error" in body
