"""SageMaker Real-time Inference Endpoint 呼び出し Lambda ハンドラ

S3 Access Point から点群データをダウンロードし、SageMaker Real-time Endpoint に
推論リクエストを送信する。レスポンスから InvokedProductionVariant ヘッダーを抽出し、
どのモデルバリアントがリクエストを処理したかを記録する。

A/B テスト構成では、複数の ProductionVariant にトラフィックが分割され、
各リクエストのバリアント情報がレスポンスに含まれる。

リトライロジック:
- ThrottlingException: exponential backoff（最大 MAX_RETRIES 回）
- ModelError: exponential backoff（最大 MAX_RETRIES 回）
- その他のエラー: リトライなし（即座に例外を raise）

Environment Variables:
    ENDPOINT_NAME: SageMaker Real-time Endpoint 名
    MAX_RETRIES: 最大リトライ回数 (default: "3")
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
from botocore.exceptions import ClientError

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)


# リトライ対象のエラーコード
_RETRYABLE_ERRORS = ("ThrottlingException", "ModelError")


def _download_from_s3ap(
    s3_client,
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


def _invoke_endpoint_with_retry(
    runtime_client,
    endpoint_name: str,
    payload: bytes,
    content_type: str,
    accept_type: str,
    max_retries: int,
) -> dict[str, Any]:
    """SageMaker InvokeEndpoint API を exponential backoff 付きで呼び出す。

    ThrottlingException および ModelError に対してリトライを行う。
    その他のエラーは即座に raise する。

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
    """SageMaker Real-time Inference Lambda ハンドラ

    S3 Access Point から点群データをダウンロードし、SageMaker Real-time Endpoint で
    推論を実行する。A/B テスト構成では InvokedProductionVariant ヘッダーから
    リクエストを処理したバリアント名を抽出する。

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
            "latency_ms": 123.45
        }

    Raises:
        ClientError: SageMaker Endpoint 呼び出しエラー（リトライ上限超過後）
        ClientError: S3 データダウンロードエラー
    """
    region = os.environ.get("REGION", os.environ.get("AWS_REGION", "ap-northeast-1"))
    endpoint_name = os.environ.get("ENDPOINT_NAME", "")
    max_retries = int(os.environ.get("MAX_RETRIES", "3"))
    s3_access_point_alias = os.environ.get("S3_ACCESS_POINT_ALIAS")
    use_case = os.environ.get("USE_CASE", "autonomous-driving")

    # 入力パラメータ取得
    s3_uri = event.get("s3_uri", "")
    content_type = event.get("content_type", "application/json")
    accept_type = event.get("accept_type", "application/json")

    if not endpoint_name:
        raise ValueError("ENDPOINT_NAME environment variable is required")
    if not s3_uri:
        raise ValueError("s3_uri is required in event payload")

    logger.info(
        "Realtime invoke started: endpoint=%s, s3_uri=%s, "
        "content_type=%s, max_retries=%d",
        endpoint_name,
        s3_uri,
        content_type,
        max_retries,
    )

    # EMF メトリクス初期化
    metrics = EmfMetrics(
        namespace="FSxN-S3AP-Patterns",
        service="realtime-invoke",
    )
    metrics.set_dimension("UseCase", use_case)

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

    # Step 2: SageMaker InvokeEndpoint（リトライ付き）
    runtime_client = boto3.client("sagemaker-runtime", region_name=region)
    invoke_start = time.time()

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
        "total_latency=%.1fms",
        parsed["variant_name"],
        invoke_ms,
        total_ms,
    )

    # EMF メトリクス出力
    metrics.put_metric("InvokeLatency", invoke_ms, "Milliseconds")
    metrics.put_metric("DownloadLatency", download_ms, "Milliseconds")
    metrics.put_metric("TotalLatency", total_ms, "Milliseconds")
    metrics.put_metric("PayloadSize", float(len(payload)), "Bytes")
    metrics.put_metric("InferenceSuccess", 1.0, "Count")
    metrics.set_property("VariantName", parsed["variant_name"])
    metrics.set_property("EndpointName", endpoint_name)
    metrics.flush()

    return {
        "prediction": parsed["prediction"],
        "variant_name": parsed["variant_name"],
        "latency_ms": round(total_ms, 2),
        "invoke_latency_ms": round(invoke_ms, 2),
        "download_latency_ms": round(download_ms, 2),
    }
