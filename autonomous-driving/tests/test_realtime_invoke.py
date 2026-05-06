"""Unit Tests for Realtime Invoke Lambda (Phase 4 — Real-time Inference)

SageMaker Real-time Endpoint 呼び出し Lambda のユニットテスト。
- InvokeEndpoint API 呼び出し
- InvokedProductionVariant ヘッダー抽出
- リトライロジック（ThrottlingException, ModelError）
- S3 AP データダウンロード
- ハンドラ統合テスト
"""

from __future__ import annotations

import io
import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

# パス設定
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 環境変数設定（インポート前に必要）
os.environ.setdefault("ENDPOINT_NAME", "test-endpoint")
os.environ.setdefault("MAX_RETRIES", "3")
os.environ.setdefault("REGION", "ap-northeast-1")
os.environ.setdefault("USE_CASE", "autonomous-driving")
os.environ.setdefault("ENABLE_XRAY", "false")

from functions.realtime_invoke.handler import (
    _download_from_s3ap,
    _invoke_endpoint_with_retry,
    _parse_inference_response,
    handler,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client_error(error_code: str, message: str = "Error") -> ClientError:
    """テスト用 ClientError を生成する。"""
    return ClientError(
        error_response={"Error": {"Code": error_code, "Message": message}},
        operation_name="InvokeEndpoint",
    )


def _make_invoke_response(
    body: bytes = b'{"prediction": "result"}',
    variant_name: str = "model-v1",
    content_type: str = "application/json",
) -> dict:
    """テスト用 InvokeEndpoint レスポンスを生成する。"""
    return {
        "Body": io.BytesIO(body),
        "InvokedProductionVariant": variant_name,
        "ContentType": content_type,
    }


# ---------------------------------------------------------------------------
# Tests: _invoke_endpoint_with_retry
# ---------------------------------------------------------------------------


class TestInvokeEndpointWithRetry:
    """_invoke_endpoint_with_retry のテスト"""

    def test_successful_invocation(self):
        """正常な InvokeEndpoint 呼び出しが成功する"""
        mock_client = MagicMock()
        mock_client.invoke_endpoint.return_value = _make_invoke_response()

        result = _invoke_endpoint_with_retry(
            runtime_client=mock_client,
            endpoint_name="test-endpoint",
            payload=b"test-data",
            content_type="application/json",
            accept_type="application/json",
            max_retries=3,
        )

        assert result["InvokedProductionVariant"] == "model-v1"
        mock_client.invoke_endpoint.assert_called_once_with(
            EndpointName="test-endpoint",
            Body=b"test-data",
            ContentType="application/json",
            Accept="application/json",
        )

    def test_invoked_production_variant_extraction(self):
        """InvokedProductionVariant ヘッダーが正しく抽出される"""
        mock_client = MagicMock()
        mock_client.invoke_endpoint.return_value = _make_invoke_response(
            variant_name="model-v2-canary"
        )

        result = _invoke_endpoint_with_retry(
            runtime_client=mock_client,
            endpoint_name="ep",
            payload=b"data",
            content_type="application/json",
            accept_type="application/json",
            max_retries=3,
        )

        assert result["InvokedProductionVariant"] == "model-v2-canary"

    @patch("functions.realtime_invoke.handler.time.sleep")
    def test_retry_on_throttling_exception(self, mock_sleep):
        """ThrottlingException に対して exponential backoff でリトライする"""
        mock_client = MagicMock()
        mock_client.invoke_endpoint.side_effect = [
            _make_client_error("ThrottlingException"),
            _make_client_error("ThrottlingException"),
            _make_invoke_response(),
        ]

        result = _invoke_endpoint_with_retry(
            runtime_client=mock_client,
            endpoint_name="ep",
            payload=b"data",
            content_type="application/json",
            accept_type="application/json",
            max_retries=3,
        )

        assert result["InvokedProductionVariant"] == "model-v1"
        assert mock_client.invoke_endpoint.call_count == 3
        # Exponential backoff: 2^0=1, 2^1=2
        mock_sleep.assert_any_call(1)
        mock_sleep.assert_any_call(2)

    @patch("functions.realtime_invoke.handler.time.sleep")
    def test_retry_on_model_error(self, mock_sleep):
        """ModelError に対して exponential backoff でリトライする"""
        mock_client = MagicMock()
        mock_client.invoke_endpoint.side_effect = [
            _make_client_error("ModelError"),
            _make_invoke_response(),
        ]

        result = _invoke_endpoint_with_retry(
            runtime_client=mock_client,
            endpoint_name="ep",
            payload=b"data",
            content_type="application/json",
            accept_type="application/json",
            max_retries=3,
        )

        assert result["InvokedProductionVariant"] == "model-v1"
        assert mock_client.invoke_endpoint.call_count == 2
        mock_sleep.assert_called_once_with(1)

    def test_non_retryable_error_raises_immediately(self):
        """リトライ不可能なエラーは即座に raise する"""
        mock_client = MagicMock()
        mock_client.invoke_endpoint.side_effect = _make_client_error(
            "ValidationError", "Invalid input"
        )

        with pytest.raises(ClientError) as exc_info:
            _invoke_endpoint_with_retry(
                runtime_client=mock_client,
                endpoint_name="ep",
                payload=b"data",
                content_type="application/json",
                accept_type="application/json",
                max_retries=3,
            )

        assert exc_info.value.response["Error"]["Code"] == "ValidationError"
        # 1 回だけ呼ばれる（リトライなし）
        mock_client.invoke_endpoint.assert_called_once()

    @patch("functions.realtime_invoke.handler.time.sleep")
    def test_max_retries_exceeded_raises_client_error(self, mock_sleep):
        """最大リトライ回数超過後に ClientError を raise する"""
        mock_client = MagicMock()
        mock_client.invoke_endpoint.side_effect = _make_client_error(
            "ThrottlingException"
        )

        with pytest.raises(ClientError) as exc_info:
            _invoke_endpoint_with_retry(
                runtime_client=mock_client,
                endpoint_name="ep",
                payload=b"data",
                content_type="application/json",
                accept_type="application/json",
                max_retries=2,
            )

        assert exc_info.value.response["Error"]["Code"] == "ThrottlingException"
        # max_retries=2 → 初回 + 2 リトライ = 3 回呼ばれる
        assert mock_client.invoke_endpoint.call_count == 3


# ---------------------------------------------------------------------------
# Tests: _download_from_s3ap
# ---------------------------------------------------------------------------


class TestDownloadFromS3AP:
    """_download_from_s3ap のテスト"""

    def test_download_from_s3_uri(self):
        """S3 URI からデータをダウンロードする"""
        mock_s3 = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = b"point-cloud-data"
        mock_s3.get_object.return_value = {"Body": mock_body}

        result = _download_from_s3ap(mock_s3, "s3://my-bucket/data/file.bin")

        assert result == b"point-cloud-data"
        mock_s3.get_object.assert_called_once_with(
            Bucket="my-bucket", Key="data/file.bin"
        )

    def test_download_with_s3_access_point_alias(self):
        """S3 AP エイリアス指定時はバケット名を置換する"""
        mock_s3 = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = b"data"
        mock_s3.get_object.return_value = {"Body": mock_body}

        result = _download_from_s3ap(
            mock_s3, "s3://original-bucket/key.bin", "my-ap-alias-s3alias"
        )

        assert result == b"data"
        mock_s3.get_object.assert_called_once_with(
            Bucket="my-ap-alias-s3alias", Key="key.bin"
        )

    def test_download_without_key(self):
        """キーなしの S3 URI（バケットのみ）"""
        mock_s3 = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = b""
        mock_s3.get_object.return_value = {"Body": mock_body}

        _download_from_s3ap(mock_s3, "s3://bucket-only")

        mock_s3.get_object.assert_called_once_with(Bucket="bucket-only", Key="")


# ---------------------------------------------------------------------------
# Tests: _parse_inference_response
# ---------------------------------------------------------------------------


class TestParseInferenceResponse:
    """_parse_inference_response のテスト"""

    def test_extracts_variant_name(self):
        """InvokedProductionVariant ヘッダーからバリアント名を抽出する"""
        response = _make_invoke_response(
            body=b'{"result": "ok"}', variant_name="model-v2"
        )
        parsed = _parse_inference_response(response)

        assert parsed["variant_name"] == "model-v2"
        assert parsed["prediction"] == '{"result": "ok"}'
        assert parsed["content_type"] == "application/json"

    def test_missing_variant_defaults_to_unknown(self):
        """InvokedProductionVariant がない場合は 'unknown' を返す"""
        response = {
            "Body": io.BytesIO(b"data"),
            "ContentType": "application/json",
        }
        parsed = _parse_inference_response(response)

        assert parsed["variant_name"] == "unknown"


# ---------------------------------------------------------------------------
# Tests: handler integration
# ---------------------------------------------------------------------------


class TestHandlerIntegration:
    """handler 関数の統合テスト"""

    def test_handler_success(self):
        """handler: S3 ダウンロード + SageMaker 呼び出しの正常フロー"""
        context = MagicMock()
        context.aws_request_id = "req-123"
        context.function_name = "realtime-invoke"

        event = {
            "s3_uri": "s3://test-bucket/data/input.bin",
            "content_type": "application/json",
        }

        mock_s3 = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = b"payload-data"
        mock_s3.get_object.return_value = {"Body": mock_body}

        mock_runtime = MagicMock()
        mock_runtime.invoke_endpoint.return_value = _make_invoke_response(
            body=b'{"class": "vehicle"}', variant_name="model-v1"
        )

        with patch.dict(os.environ, {"ENDPOINT_NAME": "my-endpoint"}):
            with patch("functions.realtime_invoke.handler.boto3") as mock_boto3:
                mock_boto3.client.side_effect = lambda service, **kwargs: {
                    "s3": mock_s3,
                    "sagemaker-runtime": mock_runtime,
                }[service]

                result = handler(event, context)

        assert result["variant_name"] == "model-v1"
        assert result["prediction"] == '{"class": "vehicle"}'
        assert "latency_ms" in result
        assert "invoke_latency_ms" in result
        assert "download_latency_ms" in result

    def test_handler_missing_endpoint_name_raises_value_error(self):
        """handler: ENDPOINT_NAME 未設定で ValueError"""
        context = MagicMock()
        context.aws_request_id = "req-456"
        context.function_name = "realtime-invoke"

        event = {"s3_uri": "s3://bucket/key"}

        with patch.dict(os.environ, {"ENDPOINT_NAME": ""}, clear=False):
            result = handler(event, context)

        # lambda_error_handler がキャッチして 500 レスポンスを返す
        assert result["statusCode"] == 500
        assert "ENDPOINT_NAME" in result["body"]

    def test_handler_missing_s3_uri_raises_value_error(self):
        """handler: s3_uri 未指定で ValueError"""
        context = MagicMock()
        context.aws_request_id = "req-789"
        context.function_name = "realtime-invoke"

        event = {}

        with patch.dict(os.environ, {"ENDPOINT_NAME": "my-endpoint"}):
            result = handler(event, context)

        # lambda_error_handler がキャッチして 500 レスポンスを返す
        assert result["statusCode"] == 500
        assert "s3_uri" in result["body"]
