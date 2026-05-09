"""SageMaker Inference Components 呼び出し Lambda ハンドラ

Inference Components を使用した推論エンドポイント呼び出し。
scale-to-zero 対応のため、ModelNotReadyException に対する
リトライロジックを実装する。

Inference Components の特徴:
- 単一 Endpoint 上に複数モデルをホスト可能
- MinInstanceCount=0 による真の scale-to-zero
- scale-from-zero 時は数分のウォームアップが必要
- InvokeEndpoint API で InferenceComponentName を指定

scale-from-zero リトライロジック:
- ModelNotReadyException: コンポーネントがスケールアウト中
- ValidationError (ModelNotReadyException): エンドポイントは存在するがインスタンス未起動
- リトライ間隔: exponential backoff (初期 5 秒、最大 30 秒)
- 最大リトライ回数: MODEL_NOT_READY_MAX_RETRIES (default: 10)
- 合計タイムアウト: STEP_FUNCTIONS_TASK_TIMEOUT (default: 300 秒)

Environment Variables:
    ENDPOINT_NAME: SageMaker Endpoint 名
    INFERENCE_COMPONENT_NAME: Inference Component 名
    MAX_RETRIES: ThrottlingException/ModelError の最大リトライ回数 (default: "3")
    MODEL_NOT_READY_RETRY_DELAY: ModelNotReadyException 初期リトライ待機秒 (default: "5")
    MODEL_NOT_READY_MAX_RETRIES: ModelNotReadyException 最大リトライ回数 (default: "10")
    MODEL_NOT_READY_MAX_DELAY: ModelNotReadyException 最大リトライ待機秒 (default: "30")
    STEP_FUNCTIONS_TASK_TIMEOUT: Step Functions タスクタイムアウト秒 (default: "300")
    S3_ACCESS_POINT_ALIAS: S3 Access Point エイリアス
    USE_CASE: ユースケース名 (default: "autonomous-driving")
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)


# リトライ対象のエラーコード
_RETRYABLE_ERRORS = ("ThrottlingException", "ModelError")

# scale-from-zero 関連のエラーコード
_MODEL_NOT_READY_ERROR = "ModelNotReadyException"
_VALIDATION_ERROR = "ValidationError"


class ComponentsColdStartTimeoutError(Exception):
    """Inference Components scale-from-zero タイムアウトエラー。

    ModelNotReadyException のリトライ上限超過、または合計タイムアウト超過時に発生する。
    Step Functions の Catch ブロックで捕捉し、Batch Transform にフォールバックする。
    """

    pass


def _download_from_s3ap(
    s3_client: Any,
    s3_uri: str,
    s3_access_point_alias: str | None = None,
) -> bytes:
    """S3 Access Point から点群データをダウンロードする。

    Args:
        s3_client: boto3 S3 クライアント
        s3_uri: S3 URI (s3://bucket/key 形式)
        s3_access_point_alias: S3 AP エイリアス（指定時はバケット名を置換）

    Returns:
        bytes: ダウンロードしたデータ

    Raises:
        ClientError: S3 アクセスエラー
    """
    path = s3_uri.replace("s3://", "")
    parts = path.split("/", 1)
    bucket = parts[0]
    key = parts[1] if len(parts) > 1 else ""

    if s3_access_point_alias:
        bucket = s3_access_point_alias

    logger.info("Downloading from S3: bucket=%s, key=%s", bucket, key)

    response = s3_client.get_object(Bucket=bucket, Key=key)
    return response["Body"].read()


def _check_total_timeout(start_time: float, task_timeout: int) -> None:
    """合計タイムアウトガードチェック。

    Args:
        start_time: 処理開始時刻 (time.time())
        task_timeout: Step Functions タスクタイムアウト秒

    Raises:
        ComponentsColdStartTimeoutError: タイムアウト超過時
    """
    elapsed = time.time() - start_time
    if elapsed > task_timeout:
        raise ComponentsColdStartTimeoutError(
            f"Total elapsed time ({elapsed:.1f}s) exceeds "
            f"Step Functions task timeout ({task_timeout}s). "
            "Inference Component may still be scaling from zero."
        )


def _is_scale_from_zero_error(error: ClientError) -> bool:
    """scale-from-zero 関連のエラーかどうかを判定する。

    Inference Components が scale-to-zero 状態から起動中の場合、
    以下のエラーが発生する:
    - ModelNotReadyException: コンポーネントがスケールアウト中
    - ValidationError (message に "model" や "not ready" を含む):
      エンドポイントは存在するがインスタンス未起動

    Args:
        error: boto3 ClientError

    Returns:
        bool: scale-from-zero 関連エラーの場合 True
    """
    error_code = error.response.get("Error", {}).get("Code", "")
    error_message = error.response.get("Error", {}).get("Message", "").lower()

    if error_code == _MODEL_NOT_READY_ERROR:
        return True

    if error_code == _VALIDATION_ERROR and (
        "not ready" in error_message
        or "no instance" in error_message
        or "model" in error_message
    ):
        return True

    return False


def _invoke_with_components_retry(
    runtime_client: Any,
    endpoint_name: str,
    component_name: str,
    payload: bytes,
    content_type: str,
    accept_type: str,
    max_retries: int,
    model_not_ready_retry_delay: int,
    model_not_ready_max_retries: int,
    model_not_ready_max_delay: int,
    task_timeout: int,
    handler_start_time: float,
) -> dict[str, Any]:
    """Inference Components Endpoint を呼び出す（scale-from-zero 対応）。

    scale-from-zero 時の ModelNotReadyException に対しては exponential backoff
    リトライを適用する。通常の ThrottlingException / ModelError に対しても
    exponential backoff を適用する。

    Args:
        runtime_client: boto3 SageMaker Runtime クライアント
        endpoint_name: SageMaker Endpoint 名
        component_name: Inference Component 名
        payload: 推論ペイロード（バイナリ）
        content_type: リクエストの Content-Type
        accept_type: レスポンスの Accept タイプ
        max_retries: ThrottlingException/ModelError の最大リトライ回数
        model_not_ready_retry_delay: 初期リトライ待機秒
        model_not_ready_max_retries: scale-from-zero 最大リトライ回数
        model_not_ready_max_delay: 最大リトライ待機秒
        task_timeout: Step Functions タスクタイムアウト秒
        handler_start_time: ハンドラ開始時刻

    Returns:
        dict: InvokeEndpoint API レスポンス

    Raises:
        ComponentsColdStartTimeoutError: scale-from-zero リトライ上限超過
        ClientError: リトライ上限超過後のエラー
    """
    scale_from_zero_attempts = 0

    while True:
        # 合計タイムアウトガード
        _check_total_timeout(handler_start_time, task_timeout)

        # ThrottlingException / ModelError 用の exponential backoff ループ
        for attempt in range(max_retries + 1):
            _check_total_timeout(handler_start_time, task_timeout)

            try:
                response = runtime_client.invoke_endpoint(
                    EndpointName=endpoint_name,
                    InferenceComponentName=component_name,
                    Body=payload,
                    ContentType=content_type,
                    Accept=accept_type,
                )
                return response

            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "")

                # scale-from-zero エラー: 専用リトライ
                if _is_scale_from_zero_error(e):
                    scale_from_zero_attempts += 1
                    if scale_from_zero_attempts > model_not_ready_max_retries:
                        raise ComponentsColdStartTimeoutError(
                            f"Inference Component '{component_name}' not ready after "
                            f"{model_not_ready_max_retries} retries. "
                            "Scale-from-zero timeout."
                        )

                    # Exponential backoff with cap
                    delay = min(
                        model_not_ready_retry_delay * (2 ** (scale_from_zero_attempts - 1)),
                        model_not_ready_max_delay,
                    )
                    logger.warning(
                        "Scale-from-zero: %s on attempt %d/%d, "
                        "waiting %ds before retry (component=%s)",
                        error_code,
                        scale_from_zero_attempts,
                        model_not_ready_max_retries,
                        delay,
                        component_name,
                    )
                    time.sleep(delay)
                    break  # Reset the inner retry loop

                # ThrottlingException / ModelError: exponential backoff
                if error_code in _RETRYABLE_ERRORS and attempt < max_retries:
                    wait_time = 2**attempt
                    logger.warning(
                        "Retryable error '%s' on attempt %d/%d, "
                        "waiting %ds before retry: %s",
                        error_code,
                        attempt + 1,
                        max_retries + 1,
                        wait_time,
                        str(e),
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(
                        "Non-retryable error or max retries exceeded: "
                        "error_code=%s, attempt=%d/%d",
                        error_code,
                        attempt + 1,
                        max_retries + 1,
                    )
                    raise
        else:
            # for ループが break なしで完了 = 通常リトライ上限到達
            # ここには到達しないはず（raise で抜ける）
            pass


def _parse_inference_response(response: dict[str, Any]) -> dict[str, Any]:
    """InvokeEndpoint レスポンスを解析する。

    Args:
        response: InvokeEndpoint API レスポンス

    Returns:
        dict: 解析結果
    """
    body = response["Body"].read()
    prediction = body.decode("utf-8") if isinstance(body, bytes) else str(body)

    variant_name = response.get("InvokedProductionVariant", "unknown")
    content_type = response.get("ContentType", "application/json")

    return {
        "prediction": prediction,
        "variant_name": variant_name,
        "content_type": content_type,
    }


@trace_lambda_handler
@lambda_error_handler
def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """SageMaker Inference Components Lambda ハンドラ。

    S3 Access Point から点群データをダウンロードし、Inference Component で
    推論を実行する。scale-from-zero 時のリトライロジックを含む。

    Input:
        {
            "s3_uri": "s3://bucket/key",
            "content_type": "application/json",  (optional)
            "accept_type": "application/json"     (optional)
        }

    Output:
        {
            "prediction": "...",
            "variant_name": "...",
            "latency_ms": 123.45,
            "invoke_latency_ms": 100.0,
            "download_latency_ms": 23.45,
            "inference_type": "components",
            "component_name": "...",
            "scale_from_zero_retries": 0
        }

    Raises:
        ComponentsColdStartTimeoutError: scale-from-zero タイムアウト
        ClientError: SageMaker Endpoint 呼び出しエラー
    """
    handler_start_time = time.time()

    # 環境変数読み込み
    region = os.environ.get("REGION", os.environ.get("AWS_REGION", "ap-northeast-1"))
    endpoint_name = os.environ.get("ENDPOINT_NAME", "")
    component_name = os.environ.get("INFERENCE_COMPONENT_NAME", "")
    max_retries = int(os.environ.get("MAX_RETRIES", "3"))
    s3_access_point_alias = os.environ.get("S3_ACCESS_POINT_ALIAS")
    use_case = os.environ.get("USE_CASE", "autonomous-driving")

    # scale-from-zero 固有の設定
    model_not_ready_retry_delay = int(
        os.environ.get("MODEL_NOT_READY_RETRY_DELAY", "5")
    )
    model_not_ready_max_retries = int(
        os.environ.get("MODEL_NOT_READY_MAX_RETRIES", "10")
    )
    model_not_ready_max_delay = int(
        os.environ.get("MODEL_NOT_READY_MAX_DELAY", "30")
    )
    step_functions_task_timeout = int(
        os.environ.get("STEP_FUNCTIONS_TASK_TIMEOUT", "300")
    )

    # 入力パラメータ取得
    s3_uri = event.get("s3_uri", "")
    content_type = event.get("content_type", "application/json")
    accept_type = event.get("accept_type", "application/json")

    if not endpoint_name:
        raise ValueError("ENDPOINT_NAME environment variable is required")
    if not component_name:
        raise ValueError("INFERENCE_COMPONENT_NAME environment variable is required")
    if not s3_uri:
        raise ValueError("s3_uri is required in event payload")

    logger.info(
        "Components invoke started: endpoint=%s, component=%s, s3_uri=%s",
        endpoint_name,
        component_name,
        s3_uri,
    )

    # EMF メトリクス初期化
    metrics = EmfMetrics(
        namespace="FSxN-S3AP-Patterns",
        service="components-invoke",
    )
    metrics.set_dimension("UseCase", use_case)
    metrics.set_dimension("InferenceType", "components")
    metrics.set_dimension("ComponentName", component_name)

    # Step 1: S3 AP からデータダウンロード
    s3_client = boto3.client("s3", region_name=region)
    start_time = time.time()

    payload = _download_from_s3ap(s3_client, s3_uri, s3_access_point_alias)

    download_ms = (time.time() - start_time) * 1000
    logger.info(
        "Data downloaded: size=%d bytes, duration=%.1fms",
        len(payload),
        download_ms,
    )

    # Step 2: SageMaker InvokeEndpoint (with InferenceComponentName)
    # scale-from-zero は数分かかるため長めのタイムアウト
    boto_config = Config(
        read_timeout=120,
        retries={"max_attempts": 0},
    )
    runtime_client = boto3.client(
        "sagemaker-runtime",
        region_name=region,
        config=boto_config,
    )

    invoke_start = time.time()

    response = _invoke_with_components_retry(
        runtime_client=runtime_client,
        endpoint_name=endpoint_name,
        component_name=component_name,
        payload=payload,
        content_type=content_type,
        accept_type=accept_type,
        max_retries=max_retries,
        model_not_ready_retry_delay=model_not_ready_retry_delay,
        model_not_ready_max_retries=model_not_ready_max_retries,
        model_not_ready_max_delay=model_not_ready_max_delay,
        task_timeout=step_functions_task_timeout,
        handler_start_time=handler_start_time,
    )

    invoke_ms = (time.time() - invoke_start) * 1000

    # Step 3: レスポンス解析
    parsed = _parse_inference_response(response)
    total_ms = (time.time() - start_time) * 1000

    logger.info(
        "Inference completed: variant=%s, invoke_latency=%.1fms, "
        "total_latency=%.1fms, component=%s",
        parsed["variant_name"],
        invoke_ms,
        total_ms,
        component_name,
    )

    # Step 4: EMF メトリクス出力
    metrics.put_metric("InvokeLatency", invoke_ms, "Milliseconds")
    metrics.put_metric("DownloadLatency", download_ms, "Milliseconds")
    metrics.put_metric("TotalLatency", total_ms, "Milliseconds")
    metrics.put_metric("PayloadSize", float(len(payload)), "Bytes")
    metrics.put_metric("InferenceSuccess", 1.0, "Count")
    metrics.put_metric("ComponentsInvocationCount", 1.0, "Count")

    # scale-from-zero 検出（invoke_latency > 10 秒は scale-from-zero の可能性大）
    if invoke_ms > 10000:
        logger.info(
            "Possible scale-from-zero detected: invoke_latency=%.1fms",
            invoke_ms,
        )
        metrics.put_metric("ScaleFromZeroDetected", 1.0, "Count")
        metrics.put_metric("ScaleFromZeroLatency", invoke_ms, "Milliseconds")

    metrics.set_property("VariantName", parsed["variant_name"])
    metrics.set_property("EndpointName", endpoint_name)
    metrics.set_property("ComponentName", component_name)
    metrics.flush()

    return {
        "prediction": parsed["prediction"],
        "variant_name": parsed["variant_name"],
        "latency_ms": round(total_ms, 2),
        "invoke_latency_ms": round(invoke_ms, 2),
        "download_latency_ms": round(download_ms, 2),
        "inference_type": "components",
        "component_name": component_name,
    }
