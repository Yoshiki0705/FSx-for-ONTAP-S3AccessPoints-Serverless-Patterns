"""SageMaker Real-time / Serverless Inference Endpoint 呼び出し Lambda ハンドラ

S3 Access Point から点群データをダウンロードし、SageMaker Endpoint に
推論リクエストを送信する。INFERENCE_TYPE 環境変数により provisioned / serverless
の両モードに対応する。

Serverless Inference モード:
- 初期タイムアウト: SERVERLESS_INITIAL_TIMEOUT (default: 60s)
- ModelNotReadyException リトライ: MODEL_NOT_READY_RETRY_DELAY 秒待機、
  最大 MODEL_NOT_READY_MAX_RETRIES 回
- コールドスタート検出: レイテンシ > COLD_START_THRESHOLD_MS で EMF メトリクス出力
- 合計タイムアウトガード: elapsed > STEP_FUNCTIONS_TASK_TIMEOUT で即座に abort

Provisioned モード:
- 標準タイムアウト（短め）
- ThrottlingException / ModelError に対する exponential backoff リトライ

両モード共通:
- ThrottlingException / ModelError: exponential backoff（最大 MAX_RETRIES 回）
- レスポンスに inference_type フィールドを含む

Environment Variables:
    ENDPOINT_NAME: SageMaker Endpoint 名
    INFERENCE_TYPE: "provisioned" | "serverless" (default: "provisioned")
    MAX_RETRIES: 最大リトライ回数 (default: "3")
    SERVERLESS_INITIAL_TIMEOUT: Serverless 初期タイムアウト秒 (default: "60")
    COLD_START_THRESHOLD_MS: コールドスタート検出閾値ミリ秒 (default: "5000")
    MODEL_NOT_READY_RETRY_DELAY: ModelNotReadyException リトライ待機秒 (default: "3")
    MODEL_NOT_READY_MAX_RETRIES: ModelNotReadyException 最大リトライ回数 (default: "2")
    STEP_FUNCTIONS_TASK_TIMEOUT: Step Functions タスクタイムアウト秒 (default: "120")
    S3_ACCESS_POINT_ALIAS: S3 Access Point エイリアス
    REGION: AWS リージョン
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


# リトライ対象のエラーコード（両モード共通）
_RETRYABLE_ERRORS = ("ThrottlingException", "ModelError")

# Serverless Inference 固有のエラーコード
_MODEL_NOT_READY_ERROR = "ModelNotReadyException"


class ServerlessColdStartTimeoutError(Exception):
    """Serverless Inference コールドスタートタイムアウトエラー。

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
    # s3://bucket/key からバケットとキーを抽出
    path = s3_uri.replace("s3://", "")
    parts = path.split("/", 1)
    bucket = parts[0]
    key = parts[1] if len(parts) > 1 else ""

    # S3 AP エイリアスが指定されている場合はバケット名を置換
    if s3_access_point_alias:
        bucket = s3_access_point_alias

    logger.info(
        "Downloading from S3: bucket=%s, key=%s",
        bucket,
        key,
    )

    response = s3_client.get_object(Bucket=bucket, Key=key)
    return response["Body"].read()


def _check_total_timeout(start_time: float, task_timeout: int) -> None:
    """合計タイムアウトガードチェック。

    経過時間が Step Functions タスクタイムアウトを超過した場合に
    即座に abort する。

    Args:
        start_time: 処理開始時刻 (time.time())
        task_timeout: Step Functions タスクタイムアウト秒

    Raises:
        ServerlessColdStartTimeoutError: タイムアウト超過時
    """
    elapsed = time.time() - start_time
    if elapsed > task_timeout:
        raise ServerlessColdStartTimeoutError(
            f"Total elapsed time ({elapsed:.1f}s) exceeds "
            f"Step Functions task timeout ({task_timeout}s). Aborting."
        )


def _invoke_endpoint_serverless(
    runtime_client: Any,
    endpoint_name: str,
    payload: bytes,
    content_type: str,
    accept_type: str,
    max_retries: int,
    model_not_ready_retry_delay: int,
    model_not_ready_max_retries: int,
    task_timeout: int,
    handler_start_time: float,
) -> dict[str, Any]:
    """Serverless Inference Endpoint を呼び出す（ModelNotReadyException 対応）。

    ModelNotReadyException に対しては専用のリトライロジックを適用し、
    ThrottlingException / ModelError に対しては exponential backoff を適用する。

    Args:
        runtime_client: boto3 SageMaker Runtime クライアント
        endpoint_name: SageMaker Endpoint 名
        payload: 推論ペイロード（バイナリ）
        content_type: リクエストの Content-Type
        accept_type: レスポンスの Accept タイプ
        max_retries: ThrottlingException/ModelError の最大リトライ回数
        model_not_ready_retry_delay: ModelNotReadyException リトライ待機秒
        model_not_ready_max_retries: ModelNotReadyException 最大リトライ回数
        task_timeout: Step Functions タスクタイムアウト秒
        handler_start_time: ハンドラ開始時刻

    Returns:
        dict: InvokeEndpoint API レスポンス

    Raises:
        ServerlessColdStartTimeoutError: ModelNotReadyException リトライ上限超過
        ClientError: リトライ上限超過後のエラー
    """
    model_not_ready_attempts = 0
    last_error: ClientError | None = None

    while True:
        # 合計タイムアウトガード
        _check_total_timeout(handler_start_time, task_timeout)

        # ThrottlingException / ModelError 用の exponential backoff ループ
        for attempt in range(max_retries + 1):
            # 合計タイムアウトガード（リトライ前にも確認）
            _check_total_timeout(handler_start_time, task_timeout)

            try:
                response = runtime_client.invoke_endpoint(
                    EndpointName=endpoint_name,
                    Body=payload,
                    ContentType=content_type,
                    Accept=accept_type,
                )
                return response

            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "")
                last_error = e

                # ModelNotReadyException: Serverless 固有のコールドスタートエラー
                if error_code == _MODEL_NOT_READY_ERROR:
                    model_not_ready_attempts += 1
                    if model_not_ready_attempts > model_not_ready_max_retries:
                        raise ServerlessColdStartTimeoutError(
                            f"ModelNotReadyException persisted after "
                            f"{model_not_ready_max_retries} retries. "
                            f"Endpoint '{endpoint_name}' cold start timeout."
                        )
                    logger.warning(
                        "ModelNotReadyException on attempt %d/%d, "
                        "waiting %ds before retry",
                        model_not_ready_attempts,
                        model_not_ready_max_retries,
                        model_not_ready_retry_delay,
                    )
                    time.sleep(model_not_ready_retry_delay)
                    # ModelNotReadyException 後は exponential backoff ループをリセット
                    break

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
                    # リトライ不可能なエラーまたはリトライ上限到達
                    logger.error(
                        "Non-retryable error or max retries exceeded: "
                        "error_code=%s, attempt=%d/%d",
                        error_code,
                        attempt + 1,
                        max_retries + 1,
                    )
                    raise
        else:
            # for ループが break なしで完了 = リトライ上限到達
            if last_error:
                raise last_error


def _invoke_endpoint_with_retry(
    runtime_client: Any,
    endpoint_name: str,
    payload: bytes,
    content_type: str,
    accept_type: str,
    max_retries: int,
) -> dict[str, Any]:
    """SageMaker InvokeEndpoint API を exponential backoff 付きで呼び出す。

    ThrottlingException および ModelError に対してリトライを行う。
    その他のエラーは即座に raise する。Provisioned モードで使用。

    Args:
        runtime_client: boto3 SageMaker Runtime クライアント
        endpoint_name: SageMaker Endpoint 名
        payload: 推論ペイロード（バイナリ）
        content_type: リクエストの Content-Type
        accept_type: レスポンスの Accept タイプ
        max_retries: 最大リトライ回数

    Returns:
        dict: InvokeEndpoint API レスポンス

    Raises:
        ClientError: リトライ上限超過後のエラー
    """
    last_error: ClientError | None = None

    for attempt in range(max_retries + 1):
        try:
            response = runtime_client.invoke_endpoint(
                EndpointName=endpoint_name,
                Body=payload,
                ContentType=content_type,
                Accept=accept_type,
            )
            return response

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            last_error = e

            if error_code in _RETRYABLE_ERRORS and attempt < max_retries:
                # Exponential backoff: 2^attempt 秒（0, 2, 4 秒）
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
                # リトライ不可能なエラーまたはリトライ上限到達
                logger.error(
                    "Non-retryable error or max retries exceeded: "
                    "error_code=%s, attempt=%d/%d",
                    error_code,
                    attempt + 1,
                    max_retries + 1,
                )
                raise

    # ここに到達するのはリトライ上限超過時のみ
    raise last_error  # type: ignore[misc]


# Alias for backward compatibility
_invoke_endpoint_provisioned = _invoke_endpoint_with_retry


def _parse_inference_response(response: dict[str, Any]) -> dict[str, Any]:
    """InvokeEndpoint レスポンスを解析する。

    レスポンスボディとメタデータ（InvokedProductionVariant ヘッダー）を抽出する。

    Args:
        response: InvokeEndpoint API レスポンス

    Returns:
        dict: {
            "prediction": レスポンスボディ（文字列）,
            "variant_name": InvokedProductionVariant ヘッダー値,
            "content_type": レスポンスの Content-Type,
        }
    """
    body = response["Body"].read()
    prediction = body.decode("utf-8") if isinstance(body, bytes) else str(body)

    # InvokedProductionVariant ヘッダーからバリアント名を抽出
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
    """SageMaker Real-time / Serverless Inference Lambda ハンドラ。

    S3 Access Point から点群データをダウンロードし、SageMaker Endpoint で
    推論を実行する。INFERENCE_TYPE 環境変数により provisioned / serverless
    の両モードに対応する。

    Input:
        {
            "s3_uri": "s3://bucket/key",
            "content_type": "application/json",  (optional, default: application/json)
            "accept_type": "application/json"     (optional, default: application/json)
        }

    Output:
        {
            "prediction": "...",
            "variant_name": "model-v1",
            "latency_ms": 123.45,
            "invoke_latency_ms": 100.0,
            "download_latency_ms": 23.45,
            "inference_type": "serverless" | "provisioned"
        }

    Raises:
        ServerlessColdStartTimeoutError: Serverless コールドスタートタイムアウト
        ClientError: SageMaker Endpoint 呼び出しエラー（リトライ上限超過後）
        ClientError: S3 データダウンロードエラー
    """
    handler_start_time = time.time()

    # 環境変数読み込み
    region = os.environ.get("REGION", os.environ.get("AWS_REGION", "ap-northeast-1"))
    endpoint_name = os.environ.get("ENDPOINT_NAME", "")
    inference_type = os.environ.get("INFERENCE_TYPE", "provisioned")
    max_retries = int(os.environ.get("MAX_RETRIES", "3"))
    s3_access_point_alias = os.environ.get("S3_ACCESS_POINT_ALIAS")
    use_case = os.environ.get("USE_CASE", "autonomous-driving")

    # Serverless Inference 固有の設定
    serverless_initial_timeout = int(
        os.environ.get("SERVERLESS_INITIAL_TIMEOUT", "60")
    )
    cold_start_threshold_ms = int(
        os.environ.get("COLD_START_THRESHOLD_MS", "5000")
    )
    model_not_ready_retry_delay = int(
        os.environ.get("MODEL_NOT_READY_RETRY_DELAY", "3")
    )
    model_not_ready_max_retries = int(
        os.environ.get("MODEL_NOT_READY_MAX_RETRIES", "2")
    )
    step_functions_task_timeout = int(
        os.environ.get("STEP_FUNCTIONS_TASK_TIMEOUT", "120")
    )

    # 入力パラメータ取得
    s3_uri = event.get("s3_uri", "")
    content_type = event.get("content_type", "application/json")
    accept_type = event.get("accept_type", "application/json")

    if not endpoint_name:
        raise ValueError("ENDPOINT_NAME environment variable is required")
    if not s3_uri:
        raise ValueError("s3_uri is required in event payload")

    is_serverless = inference_type == "serverless"

    logger.info(
        "Realtime invoke started: endpoint=%s, s3_uri=%s, "
        "inference_type=%s, content_type=%s, max_retries=%d",
        endpoint_name,
        s3_uri,
        inference_type,
        content_type,
        max_retries,
    )

    # EMF メトリクス初期化
    metrics = EmfMetrics(
        namespace="FSxN-S3AP-Patterns",
        service="realtime-invoke",
    )
    metrics.set_dimension("UseCase", use_case)
    metrics.set_dimension("InferenceType", inference_type)

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

    # Step 2: SageMaker InvokeEndpoint
    # Serverless モードでは長めのタイムアウトを設定
    read_timeout = serverless_initial_timeout if is_serverless else 30
    boto_config = Config(
        read_timeout=read_timeout,
        retries={"max_attempts": 0},  # リトライは自前で制御
    )
    runtime_client = boto3.client(
        "sagemaker-runtime",
        region_name=region,
        config=boto_config,
    )

    invoke_start = time.time()

    if is_serverless:
        response = _invoke_endpoint_serverless(
            runtime_client=runtime_client,
            endpoint_name=endpoint_name,
            payload=payload,
            content_type=content_type,
            accept_type=accept_type,
            max_retries=max_retries,
            model_not_ready_retry_delay=model_not_ready_retry_delay,
            model_not_ready_max_retries=model_not_ready_max_retries,
            task_timeout=step_functions_task_timeout,
            handler_start_time=handler_start_time,
        )
    else:
        response = _invoke_endpoint_with_retry(
            runtime_client=runtime_client,
            endpoint_name=endpoint_name,
            payload=payload,
            content_type=content_type,
            accept_type=accept_type,
            max_retries=max_retries,
        )

    invoke_ms = (time.time() - invoke_start) * 1000

    # Step 3: レスポンス解析 + バリアント名抽出
    parsed = _parse_inference_response(response)
    total_ms = (time.time() - start_time) * 1000

    logger.info(
        "Inference completed: variant=%s, invoke_latency=%.1fms, "
        "total_latency=%.1fms, inference_type=%s",
        parsed["variant_name"],
        invoke_ms,
        total_ms,
        inference_type,
    )

    # Step 4: EMF メトリクス出力
    metrics.put_metric("InvokeLatency", invoke_ms, "Milliseconds")
    metrics.put_metric("DownloadLatency", download_ms, "Milliseconds")
    metrics.put_metric("TotalLatency", total_ms, "Milliseconds")
    metrics.put_metric("PayloadSize", float(len(payload)), "Bytes")
    metrics.put_metric("InferenceSuccess", 1.0, "Count")

    # Serverless Inference 固有メトリクス
    if is_serverless:
        metrics.put_metric("ServerlessInvocationLatency", invoke_ms, "Milliseconds")
        metrics.put_metric("ServerlessInvocationCount", 1.0, "Count")

        # コールドスタート検出
        if invoke_ms > cold_start_threshold_ms:
            logger.info(
                "Cold start detected: invoke_latency=%.1fms > threshold=%dms",
                invoke_ms,
                cold_start_threshold_ms,
            )
            metrics.put_metric("ColdStartDetected", 1.0, "Count")
            metrics.put_metric(
                "ServerlessColdStartLatency", invoke_ms, "Milliseconds"
            )

    metrics.set_property("VariantName", parsed["variant_name"])
    metrics.set_property("EndpointName", endpoint_name)
    metrics.set_property("InferenceType", inference_type)
    metrics.flush()

    return {
        "prediction": parsed["prediction"],
        "variant_name": parsed["variant_name"],
        "latency_ms": round(total_ms, 2),
        "invoke_latency_ms": round(invoke_ms, 2),
        "download_latency_ms": round(download_ms, 2),
        "inference_type": inference_type,
    }
