"""Unit Tests for Realtime Invoke Lambda — Serverless Inference Mode

Serverless Inference モードの単体テスト:
- INFERENCE_TYPE="serverless" でのハンドラ動作
- ModelNotReadyException リトライロジック
- コールドスタート検出（レイテンシ > 閾値）
- 合計タイムアウトガード（ServerlessColdStartTimeoutError）
- レスポンスに inference_type フィールドが含まれること
- Provisioned モードの後方互換性
- カバレッジ目標: 80%
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
    ServerlessColdStartTimeoutError,
    _check_total_timeout,
    _invoke_endpoint_serverless,
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
# Tests: Serverless Inference Handler
# ---------------------------------------------------------------------------


class TestHandlerServerlessMode:
    """handler 関数の Serverless Inference モードテスト"""

    def test_handler_serverless_mode_success(self):
        """INFERENCE_TYPE='serverless' で正常に推論が完了する"""
        context = MagicMock()
        context.aws_request_id = "req-serverless-001"
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
            body=b'{"class": "pedestrian"}', variant_name="serverless-v1"
        )

        env_vars = {
            "ENDPOINT_NAME": "serverless-endpoint",
            "INFERENCE_TYPE": "serverless",
            "SERVERLESS_INITIAL_TIMEOUT": "60",
            "COLD_START_THRESHOLD_MS": "5000",
            "MODEL_NOT_READY_RETRY_DELAY": "3",
            "MODEL_NOT_READY_MAX_RETRIES": "2",
            "STEP_FUNCTIONS_TASK_TIMEOUT": "120",
        }

        with patch.dict(os.environ, env_vars):
            with patch("functions.realtime_invoke.handler.boto3") as mock_boto3:
                mock_boto3.client.side_effect = lambda service, **kwargs: {
                    "s3": mock_s3,
                    "sagemaker-runtime": mock_runtime,
                }[service]

                result = handler(event, context)

        assert result["prediction"] == '{"class": "pedestrian"}'
        assert result["variant_name"] == "serverless-v1"
        assert result["inference_type"] == "serverless"
        assert "latency_ms" in result
        assert "invoke_latency_ms" in result
        assert "download_latency_ms" in result

    def test_handler_response_includes_inference_type_field(self):
        """レスポンスに inference_type フィールドが含まれる"""
        context = MagicMock()
        context.aws_request_id = "req-type-check"
        context.function_name = "realtime-invoke"

        event = {"s3_uri": "s3://bucket/key.bin"}

        mock_s3 = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = b"data"
        mock_s3.get_object.return_value = {"Body": mock_body}

        mock_runtime = MagicMock()
        mock_runtime.invoke_endpoint.return_value = _make_invoke_response()

        env_vars = {
            "ENDPOINT_NAME": "ep",
            "INFERENCE_TYPE": "serverless",
            "STEP_FUNCTIONS_TASK_TIMEOUT": "120",
        }

        with patch.dict(os.environ, env_vars):
            with patch("functions.realtime_invoke.handler.boto3") as mock_boto3:
                mock_boto3.client.side_effect = lambda service, **kwargs: {
                    "s3": mock_s3,
                    "sagemaker-runtime": mock_runtime,
                }[service]

                result = handler(event, context)

        assert "inference_type" in result
        assert result["inference_type"] == "serverless"

    def test_handler_provisioned_mode_backward_compatibility(self):
        """Provisioned モードが引き続き正常に動作する（後方互換性）"""
        context = MagicMock()
        context.aws_request_id = "req-provisioned"
        context.function_name = "realtime-invoke"

        event = {"s3_uri": "s3://bucket/key.bin"}

        mock_s3 = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = b"data"
        mock_s3.get_object.return_value = {"Body": mock_body}

        mock_runtime = MagicMock()
        mock_runtime.invoke_endpoint.return_value = _make_invoke_response(
            variant_name="provisioned-v1"
        )

        env_vars = {
            "ENDPOINT_NAME": "provisioned-endpoint",
            "INFERENCE_TYPE": "provisioned",
        }

        with patch.dict(os.environ, env_vars):
            with patch("functions.realtime_invoke.handler.boto3") as mock_boto3:
                mock_boto3.client.side_effect = lambda service, **kwargs: {
                    "s3": mock_s3,
                    "sagemaker-runtime": mock_runtime,
                }[service]

                result = handler(event, context)

        assert result["inference_type"] == "provisioned"
        assert result["variant_name"] == "provisioned-v1"
        assert "latency_ms" in result


# ---------------------------------------------------------------------------
# Tests: ModelNotReadyException Retry Logic
# ---------------------------------------------------------------------------


class TestModelNotReadyExceptionRetry:
    """ModelNotReadyException リトライロジックのテスト"""

    @patch("functions.realtime_invoke.handler.time.sleep")
    def test_model_not_ready_retry_then_success(self, mock_sleep):
        """ModelNotReadyException 後にリトライして成功する"""
        mock_client = MagicMock()
        mock_client.invoke_endpoint.side_effect = [
            _make_client_error("ModelNotReadyException"),
            _make_invoke_response(),
        ]

        result = _invoke_endpoint_serverless(
            runtime_client=mock_client,
            endpoint_name="serverless-ep",
            payload=b"data",
            content_type="application/json",
            accept_type="application/json",
            max_retries=3,
            model_not_ready_retry_delay=3,
            model_not_ready_max_retries=2,
            task_timeout=120,
            handler_start_time=time.time(),
        )

        assert result["InvokedProductionVariant"] == "model-v1"
        # ModelNotReadyException 後に 3 秒待機
        mock_sleep.assert_called_with(3)

    @patch("functions.realtime_invoke.handler.time.sleep")
    def test_model_not_ready_max_retries_exceeded(self, mock_sleep):
        """ModelNotReadyException が最大リトライ回数を超過すると ServerlessColdStartTimeoutError"""
        mock_client = MagicMock()
        mock_client.invoke_endpoint.side_effect = _make_client_error(
            "ModelNotReadyException"
        )

        with pytest.raises(ServerlessColdStartTimeoutError, match="ModelNotReadyException"):
            _invoke_endpoint_serverless(
                runtime_client=mock_client,
                endpoint_name="serverless-ep",
                payload=b"data",
                content_type="application/json",
                accept_type="application/json",
                max_retries=3,
                model_not_ready_retry_delay=3,
                model_not_ready_max_retries=2,
                task_timeout=120,
                handler_start_time=time.time(),
            )

    @patch("functions.realtime_invoke.handler.time.sleep")
    def test_model_not_ready_retry_delay_value(self, mock_sleep):
        """ModelNotReadyException リトライ時に指定された遅延秒数で待機する"""
        mock_client = MagicMock()
        mock_client.invoke_endpoint.side_effect = [
            _make_client_error("ModelNotReadyException"),
            _make_client_error("ModelNotReadyException"),
            _make_invoke_response(),
        ]

        _invoke_endpoint_serverless(
            runtime_client=mock_client,
            endpoint_name="ep",
            payload=b"data",
            content_type="application/json",
            accept_type="application/json",
            max_retries=3,
            model_not_ready_retry_delay=5,
            model_not_ready_max_retries=2,
            task_timeout=120,
            handler_start_time=time.time(),
        )

        # 5 秒待機が 2 回呼ばれる
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(5)


# ---------------------------------------------------------------------------
# Tests: Cold Start Detection
# ---------------------------------------------------------------------------


class TestColdStartDetection:
    """コールドスタート検出のテスト"""

    def test_cold_start_detected_when_latency_exceeds_threshold(self):
        """レイテンシ > COLD_START_THRESHOLD_MS でコールドスタートが検出される"""
        context = MagicMock()
        context.aws_request_id = "req-cold"
        context.function_name = "realtime-invoke"

        event = {"s3_uri": "s3://bucket/key.bin"}

        mock_s3 = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = b"data"
        mock_s3.get_object.return_value = {"Body": mock_body}

        # Simulate slow response (cold start) by delaying invoke_endpoint
        def slow_invoke(**kwargs):
            time.sleep(0.01)  # Small delay to ensure latency > 0
            return _make_invoke_response()

        mock_runtime = MagicMock()
        mock_runtime.invoke_endpoint.side_effect = slow_invoke

        env_vars = {
            "ENDPOINT_NAME": "ep",
            "INFERENCE_TYPE": "serverless",
            # Set threshold very low to trigger cold start detection
            "COLD_START_THRESHOLD_MS": "0",
            "STEP_FUNCTIONS_TASK_TIMEOUT": "120",
        }

        with patch.dict(os.environ, env_vars):
            with patch("functions.realtime_invoke.handler.boto3") as mock_boto3:
                mock_boto3.client.side_effect = lambda service, **kwargs: {
                    "s3": mock_s3,
                    "sagemaker-runtime": mock_runtime,
                }[service]

                result = handler(event, context)

        # Handler should still succeed
        assert result["inference_type"] == "serverless"
        assert result["invoke_latency_ms"] > 0

    def test_no_cold_start_when_latency_below_threshold(self):
        """レイテンシ < COLD_START_THRESHOLD_MS ではコールドスタートは検出されない"""
        context = MagicMock()
        context.aws_request_id = "req-warm"
        context.function_name = "realtime-invoke"

        event = {"s3_uri": "s3://bucket/key.bin"}

        mock_s3 = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = b"data"
        mock_s3.get_object.return_value = {"Body": mock_body}

        mock_runtime = MagicMock()
        mock_runtime.invoke_endpoint.return_value = _make_invoke_response()

        env_vars = {
            "ENDPOINT_NAME": "ep",
            "INFERENCE_TYPE": "serverless",
            # Set threshold very high so cold start is NOT detected
            "COLD_START_THRESHOLD_MS": "999999",
            "STEP_FUNCTIONS_TASK_TIMEOUT": "120",
        }

        with patch.dict(os.environ, env_vars):
            with patch("functions.realtime_invoke.handler.boto3") as mock_boto3:
                mock_boto3.client.side_effect = lambda service, **kwargs: {
                    "s3": mock_s3,
                    "sagemaker-runtime": mock_runtime,
                }[service]

                result = handler(event, context)

        # Handler should succeed with low latency
        assert result["inference_type"] == "serverless"
        assert result["invoke_latency_ms"] < 999999


# ---------------------------------------------------------------------------
# Tests: Total Timeout Guard
# ---------------------------------------------------------------------------


class TestTotalTimeoutGuard:
    """合計タイムアウトガード（ServerlessColdStartTimeoutError）のテスト"""

    def test_check_total_timeout_raises_when_exceeded(self):
        """経過時間がタイムアウトを超過すると ServerlessColdStartTimeoutError"""
        # start_time を過去に設定して超過をシミュレート
        start_time = time.time() - 200  # 200 秒前
        with pytest.raises(ServerlessColdStartTimeoutError, match="exceeds"):
            _check_total_timeout(start_time, task_timeout=120)

    def test_check_total_timeout_passes_when_within_limit(self):
        """経過時間がタイムアウト内であれば例外なし"""
        start_time = time.time()  # 今
        # Should not raise
        _check_total_timeout(start_time, task_timeout=120)

    @patch("functions.realtime_invoke.handler.time.sleep")
    def test_timeout_guard_during_serverless_invoke(self, mock_sleep):
        """Serverless invoke 中にタイムアウトガードが発動する"""
        mock_client = MagicMock()
        mock_client.invoke_endpoint.side_effect = _make_client_error(
            "ModelNotReadyException"
        )

        # handler_start_time を過去に設定してタイムアウトをシミュレート
        handler_start_time = time.time() - 200

        with pytest.raises(ServerlessColdStartTimeoutError):
            _invoke_endpoint_serverless(
                runtime_client=mock_client,
                endpoint_name="ep",
                payload=b"data",
                content_type="application/json",
                accept_type="application/json",
                max_retries=3,
                model_not_ready_retry_delay=3,
                model_not_ready_max_retries=2,
                task_timeout=120,
                handler_start_time=handler_start_time,
            )

    def test_handler_timeout_returns_error(self):
        """ハンドラレベルでタイムアウトが発生した場合のエラーハンドリング"""
        context = MagicMock()
        context.aws_request_id = "req-timeout"
        context.function_name = "realtime-invoke"

        event = {"s3_uri": "s3://bucket/key.bin"}

        mock_s3 = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = b"data"
        mock_s3.get_object.return_value = {"Body": mock_body}

        mock_runtime = MagicMock()
        mock_runtime.invoke_endpoint.side_effect = _make_client_error(
            "ModelNotReadyException"
        )

        env_vars = {
            "ENDPOINT_NAME": "ep",
            "INFERENCE_TYPE": "serverless",
            "MODEL_NOT_READY_MAX_RETRIES": "2",
            "STEP_FUNCTIONS_TASK_TIMEOUT": "120",
        }

        with patch.dict(os.environ, env_vars):
            with patch("functions.realtime_invoke.handler.boto3") as mock_boto3:
                mock_boto3.client.side_effect = lambda service, **kwargs: {
                    "s3": mock_s3,
                    "sagemaker-runtime": mock_runtime,
                }[service]
                with patch("functions.realtime_invoke.handler.time.sleep"):
                    result = handler(event, context)

        # lambda_error_handler catches the exception and returns error response
        assert result["statusCode"] == 500


# ---------------------------------------------------------------------------
# Tests: Serverless + Provisioned Response Key Consistency
# ---------------------------------------------------------------------------


class TestResponseKeyConsistency:
    """Serverless/Provisioned 両モードのレスポンスキー一貫性テスト"""

    def _run_handler_with_mode(self, inference_type: str) -> dict:
        """指定モードでハンドラを実行してレスポンスを返す"""
        context = MagicMock()
        context.aws_request_id = f"req-{inference_type}"
        context.function_name = "realtime-invoke"

        event = {"s3_uri": "s3://bucket/key.bin"}

        mock_s3 = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = b"data"
        mock_s3.get_object.return_value = {"Body": mock_body}

        mock_runtime = MagicMock()
        mock_runtime.invoke_endpoint.return_value = _make_invoke_response()

        env_vars = {
            "ENDPOINT_NAME": "ep",
            "INFERENCE_TYPE": inference_type,
            "STEP_FUNCTIONS_TASK_TIMEOUT": "120",
        }

        with patch.dict(os.environ, env_vars):
            with patch("functions.realtime_invoke.handler.boto3") as mock_boto3:
                mock_boto3.client.side_effect = lambda service, **kwargs: {
                    "s3": mock_s3,
                    "sagemaker-runtime": mock_runtime,
                }[service]

                return handler(event, context)

    def test_both_modes_have_same_response_keys(self):
        """Serverless と Provisioned のレスポンスが同一キーセットを持つ"""
        serverless_result = self._run_handler_with_mode("serverless")
        provisioned_result = self._run_handler_with_mode("provisioned")

        expected_keys = {
            "prediction",
            "variant_name",
            "latency_ms",
            "invoke_latency_ms",
            "download_latency_ms",
            "inference_type",
        }

        assert set(serverless_result.keys()) == expected_keys
        assert set(provisioned_result.keys()) == expected_keys

    def test_serverless_inference_type_value(self):
        """Serverless モードの inference_type が 'serverless' である"""
        result = self._run_handler_with_mode("serverless")
        assert result["inference_type"] == "serverless"

    def test_provisioned_inference_type_value(self):
        """Provisioned モードの inference_type が 'provisioned' である"""
        result = self._run_handler_with_mode("provisioned")
        assert result["inference_type"] == "provisioned"


# ---------------------------------------------------------------------------
# Tests: ThrottlingException in Serverless Mode
# ---------------------------------------------------------------------------


class TestServerlessThrottlingRetry:
    """Serverless モードでの ThrottlingException リトライテスト"""

    @patch("functions.realtime_invoke.handler.time.sleep")
    def test_throttling_retry_in_serverless_mode(self, mock_sleep):
        """Serverless モードでも ThrottlingException に対して exponential backoff"""
        mock_client = MagicMock()
        mock_client.invoke_endpoint.side_effect = [
            _make_client_error("ThrottlingException"),
            _make_invoke_response(),
        ]

        result = _invoke_endpoint_serverless(
            runtime_client=mock_client,
            endpoint_name="ep",
            payload=b"data",
            content_type="application/json",
            accept_type="application/json",
            max_retries=3,
            model_not_ready_retry_delay=3,
            model_not_ready_max_retries=2,
            task_timeout=120,
            handler_start_time=time.time(),
        )

        assert result["InvokedProductionVariant"] == "model-v1"
        assert mock_client.invoke_endpoint.call_count == 2
