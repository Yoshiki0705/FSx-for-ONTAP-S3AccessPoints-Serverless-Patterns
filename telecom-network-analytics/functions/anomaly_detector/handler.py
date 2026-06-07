"""通信業界 (UC18) Anomaly Detector Lambda ハンドラ

CDR 分析結果と過去のベースラインデータを比較し、
3σ (3標準偏差) を超える異常レコードをフラグ付けする。
Bedrock 推論を使用して異常パターンの分類と説明を生成する。

処理フロー:
    1. CDR Analyzer / Log Analyzer の処理結果を受信
    2. 7日間ローリングベースラインとの比較
    3. 3σ 超過検出
    4. Bedrock 推論による異常分類 (retry_handler 適用)
    5. 結果出力

Requirements: 2.2, 2.6, 13.6

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN
    OUTPUT_BUCKET: 出力バケット名
    ANOMALY_THRESHOLD_STDDEV: 異常検出閾値 (σ数, default: 3)
    BASELINE_WINDOW_DAYS: ベースライン計算期間 (日数, default: 7)
    BEDROCK_MODEL_ID: Bedrock モデル ID (default: anthropic.claude-3-haiku-20240307-v1:0)
    SNS_TOPIC_ARN: 通知先 SNS トピック ARN
"""

from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timezone
from typing import Any

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler
from shared.retry_handler import execute_with_retry, RetryConfig, RetryExhaustedError

logger = logging.getLogger(__name__)

# デフォルト設定
DEFAULT_ANOMALY_THRESHOLD_STDDEV = 3.0
DEFAULT_BASELINE_WINDOW_DAYS = 7
DEFAULT_BEDROCK_MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"

# Bedrock リトライ設定
BEDROCK_RETRY_CONFIG = RetryConfig(
    max_attempts=3,
    initial_interval_seconds=2.0,
    backoff_rate=2.0,
)


def calculate_baseline_statistics(
    historical_values: list[float],
) -> dict[str, float]:
    """ヒストリカルデータからベースライン統計を計算する。

    Args:
        historical_values: 過去の計測値リスト

    Returns:
        dict: mean (平均), stddev (標準偏差), count (データ点数)
    """
    if not historical_values:
        return {"mean": 0.0, "stddev": 0.0, "count": 0}

    n = len(historical_values)
    mean = sum(historical_values) / n

    if n < 2:
        return {"mean": mean, "stddev": 0.0, "count": n}

    # 標本標準偏差 (n-1 で割る)
    variance = sum((x - mean) ** 2 for x in historical_values) / (n - 1)
    stddev = math.sqrt(variance)

    return {"mean": mean, "stddev": stddev, "count": n}


def detect_anomalies(
    current_metrics: dict[str, float],
    baseline: dict[str, dict[str, float]],
    threshold_stddev: float = DEFAULT_ANOMALY_THRESHOLD_STDDEV,
) -> list[dict[str, Any]]:
    """3σ閾値ベースの異常検出を行う。

    各メトリクスについて、現在値がベースライン平均から 3σ を超えている場合に
    異常としてフラグ付けする。

    Args:
        current_metrics: 現在の計測値 {metric_name: value}
        baseline: ベースライン統計 {metric_name: {mean, stddev, count}}
        threshold_stddev: 異常検出閾値 (σ数, デフォルト: 3)

    Returns:
        list[dict]: 検出された異常のリスト
    """
    anomalies = []

    for metric_name, current_value in current_metrics.items():
        if metric_name not in baseline:
            continue

        stats = baseline[metric_name]
        mean = stats.get("mean", 0.0)
        stddev = stats.get("stddev", 0.0)
        count = stats.get("count", 0)

        # ベースラインデータが不足している場合はスキップ
        if count < 2 or stddev == 0.0:
            continue

        # Z-score 計算
        z_score = abs(current_value - mean) / stddev

        if z_score > threshold_stddev:
            anomalies.append(
                {
                    "metric_name": metric_name,
                    "current_value": current_value,
                    "baseline_mean": round(mean, 4),
                    "baseline_stddev": round(stddev, 4),
                    "z_score": round(z_score, 4),
                    "threshold_stddev": threshold_stddev,
                    "deviation_direction": "above" if current_value > mean else "below",
                    "baseline_data_points": count,
                }
            )

    return anomalies


def load_baseline_from_s3(
    s3_client,
    output_bucket: str,
    baseline_window_days: int = DEFAULT_BASELINE_WINDOW_DAYS,
) -> dict[str, dict[str, float]]:
    """S3 出力バケットから7日間のベースラインデータをロードする。

    results/cdr/ プレフィックス下の過去7日間の結果ファイルから
    統計データを集約する。

    Args:
        s3_client: boto3 S3 クライアント
        output_bucket: 出力バケット名
        baseline_window_days: ベースライン期間 (デフォルト: 7日)

    Returns:
        dict: メトリクス名→ベースライン統計のマッピング
    """
    from datetime import timedelta

    baseline_data: dict[str, list[float]] = {
        "call_volume": [],
        "average_duration": [],
        "peak_concurrent_calls": [],
        "equipment_failures_count": [],
        "capacity_breaches_count": [],
    }

    # 過去 N 日間のプレフィックスを走査
    today = datetime.now(timezone.utc)
    for day_offset in range(1, baseline_window_days + 1):
        target_date = today - timedelta(days=day_offset)
        prefix = f"results/cdr/{target_date.strftime('%Y/%m/%d')}/"

        try:
            response = s3_client.list_objects_v2(
                Bucket=output_bucket,
                Prefix=prefix,
                MaxKeys=100,
            )

            for obj in response.get("Contents", []):
                try:
                    get_resp = s3_client.get_object(
                        Bucket=output_bucket,
                        Key=obj["Key"],
                    )
                    result = json.loads(get_resp["Body"].read())
                    get_resp["Body"].close()

                    # 統計値を抽出
                    stats = result.get("statistics", {})
                    if stats.get("total_records"):
                        baseline_data["call_volume"].append(float(stats.get("total_records", 0)))
                    if stats.get("average_duration"):
                        baseline_data["average_duration"].append(float(stats["average_duration"]))
                    if stats.get("peak_concurrent_calls"):
                        baseline_data["peak_concurrent_calls"].append(float(stats["peak_concurrent_calls"]))

                except Exception as e:
                    logger.debug("Skipping baseline file %s: %s", obj["Key"], str(e))
                    continue

        except Exception as e:
            logger.debug("Baseline scan failed for prefix %s: %s", prefix, str(e))
            continue

    # ログ結果のベースライン
    for day_offset in range(1, baseline_window_days + 1):
        target_date = today - timedelta(days=day_offset)
        prefix = f"results/logs/{target_date.strftime('%Y/%m/%d')}/"

        try:
            response = s3_client.list_objects_v2(
                Bucket=output_bucket,
                Prefix=prefix,
                MaxKeys=100,
            )

            for obj in response.get("Contents", []):
                try:
                    get_resp = s3_client.get_object(
                        Bucket=output_bucket,
                        Key=obj["Key"],
                    )
                    result = json.loads(get_resp["Body"].read())
                    get_resp["Body"].close()

                    if "equipment_failures_count" in result:
                        baseline_data["equipment_failures_count"].append(float(result["equipment_failures_count"]))
                    if "capacity_breaches_count" in result:
                        baseline_data["capacity_breaches_count"].append(float(result["capacity_breaches_count"]))
                except Exception:
                    continue

        except Exception:
            continue

    # ベースライン統計を計算
    baseline_stats = {}
    for metric_name, values in baseline_data.items():
        if values:
            baseline_stats[metric_name] = calculate_baseline_statistics(values)

    return baseline_stats


def invoke_bedrock_anomaly_classification(
    bedrock_client,
    anomalies: list[dict[str, Any]],
    model_id: str = DEFAULT_BEDROCK_MODEL_ID,
) -> dict[str, Any]:
    """Bedrock 推論により異常パターンの分類と説明を生成する。

    Args:
        bedrock_client: boto3 Bedrock Runtime クライアント
        anomalies: 検出された異常のリスト
        model_id: Bedrock モデル ID

    Returns:
        dict: 分類結果 (classification, explanation, recommendations)
    """
    if not anomalies:
        return {
            "classification": "normal",
            "explanation": "No anomalies detected",
            "recommendations": [],
        }

    # プロンプト構築
    anomaly_summary = json.dumps(anomalies, indent=2, default=str)
    prompt = (
        "You are a telecommunications network expert. Analyze the following "
        "anomalies detected in network metrics and provide:\n"
        "1. Classification (one of: traffic_surge, equipment_degradation, "
        "capacity_exhaustion, configuration_change, external_event, unknown)\n"
        "2. Brief explanation of the likely root cause\n"
        "3. Up to 3 recommended actions\n\n"
        f"Anomalies:\n{anomaly_summary}\n\n"
        "Respond in JSON format:\n"
        '{"classification": "...", "explanation": "...", "recommendations": ["...", ...]}'
    )

    def _invoke_model():
        body = json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}],
            }
        )

        response = bedrock_client.invoke_model(
            modelId=model_id,
            body=body,
            contentType="application/json",
            accept="application/json",
        )

        response_body = json.loads(response["body"].read())
        return response_body

    try:
        response_body = execute_with_retry(
            _invoke_model,
            config=BEDROCK_RETRY_CONFIG,
        )

        # レスポンスからテキストを抽出
        content_text = ""
        if "content" in response_body:
            for block in response_body["content"]:
                if block.get("type") == "text":
                    content_text += block.get("text", "")

        # JSON パース試行
        try:
            # JSON ブロックを抽出
            json_start = content_text.find("{")
            json_end = content_text.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                result = json.loads(content_text[json_start:json_end])
                return {
                    "classification": result.get("classification", "unknown"),
                    "explanation": result.get("explanation", ""),
                    "recommendations": result.get("recommendations", []),
                }
        except json.JSONDecodeError:
            pass

        # JSON パース失敗時はテキストそのままを返す
        return {
            "classification": "unknown",
            "explanation": content_text[:500],
            "recommendations": [],
        }

    except RetryExhaustedError as e:
        logger.error("Bedrock inference failed after retries: %s", str(e))
        raise


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Anomaly Detector Lambda ハンドラ

    CDR Analyzer / Log Analyzer の処理結果を集約し、
    7日間ローリングベースラインと比較して異常を検出する。

    Event 形式 (Step Functions から渡される集約結果):
        {
            "cdr_results": [...],    # CDR Analyzer の結果リスト
            "log_results": [...],    # Log Analyzer の結果リスト (optional)
            "manifest_key": "..."
        }

    Processing Flow:
        1. CDR/Log 処理結果からメトリクス集約
        2. S3 から7日間ベースラインをロード
        3. 3σ 異常検出
        4. Bedrock 推論による分類 (retry_handler 適用)
        5. 結果出力 + SNS 通知 (異常検出時)

    Returns:
        dict: 異常検出結果 (anomalies, classification, metrics)
    """
    cdr_results = event.get("cdr_results", [])
    log_results = event.get("log_results", [])
    manifest_key = event.get("manifest_key", "")

    logger.info(
        "Anomaly Detector started: cdr_results=%d, log_results=%d, manifest=%s",
        len(cdr_results),
        len(log_results),
        manifest_key,
    )

    # 環境設定
    output_bucket = os.environ.get("OUTPUT_BUCKET", "")
    threshold_stddev = float(os.environ.get("ANOMALY_THRESHOLD_STDDEV", DEFAULT_ANOMALY_THRESHOLD_STDDEV))
    baseline_window_days = int(os.environ.get("BASELINE_WINDOW_DAYS", DEFAULT_BASELINE_WINDOW_DAYS))
    model_id = os.environ.get("BEDROCK_MODEL_ID", DEFAULT_BEDROCK_MODEL_ID)
    sns_topic_arn = os.environ.get("SNS_TOPIC_ARN", "")
    s3_client = boto3.client("s3")

    # Step 1: 現在メトリクスの集約
    with xray_subsegment(
        name="aggregate_metrics",
        annotations={
            "service_name": "anomaly_detector",
            "operation": "AggregateMetrics",
            "use_case": "telecom-network-analytics",
        },
    ):
        current_metrics = _aggregate_current_metrics(cdr_results, log_results)

    logger.info("Current metrics aggregated: %s", json.dumps(current_metrics, default=str))

    # Step 2: 7日間ベースラインのロード
    baseline = {}
    if output_bucket:
        with xray_subsegment(
            name="load_baseline",
            annotations={
                "service_name": "anomaly_detector",
                "operation": "LoadBaseline",
                "use_case": "telecom-network-analytics",
            },
        ):
            baseline = load_baseline_from_s3(
                s3_client=s3_client,
                output_bucket=output_bucket,
                baseline_window_days=baseline_window_days,
            )

    logger.info(
        "Baseline loaded: metrics=%d, window=%d days",
        len(baseline),
        baseline_window_days,
    )

    # Step 3: 3σ 異常検出
    with xray_subsegment(
        name="detect_anomalies",
        annotations={
            "service_name": "anomaly_detector",
            "operation": "DetectAnomalies",
            "use_case": "telecom-network-analytics",
            "threshold_stddev": threshold_stddev,
        },
    ):
        anomalies = detect_anomalies(current_metrics, baseline, threshold_stddev)

    logger.info("Anomaly detection completed: %d anomalies found", len(anomalies))

    # Step 4: Bedrock 推論 (異常がある場合のみ)
    classification = {
        "classification": "normal",
        "explanation": "No anomalies detected",
        "recommendations": [],
    }

    if anomalies:
        try:
            bedrock_client = boto3.client("bedrock-runtime")
            with xray_subsegment(
                name="bedrock_classify",
                annotations={
                    "service_name": "bedrock",
                    "operation": "InvokeModel",
                    "use_case": "telecom-network-analytics",
                    "model_id": model_id,
                },
            ):
                classification = invoke_bedrock_anomaly_classification(
                    bedrock_client=bedrock_client,
                    anomalies=anomalies,
                    model_id=model_id,
                )
        except RetryExhaustedError as e:
            logger.error("Bedrock classification failed: %s", str(e))
            classification = {
                "classification": "unknown",
                "explanation": f"Bedrock inference failed after retries: {e}",
                "recommendations": ["Manual investigation required"],
            }
            # エラー記録
            if output_bucket:
                _record_error(
                    s3_client,
                    output_bucket,
                    "anomaly_detection",
                    "bedrock_retry_exhausted",
                    str(e),
                )

    # Step 5: 結果構築
    result = {
        "status": "success",
        "manifest_key": manifest_key,
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
        "classification": classification,
        "current_metrics": current_metrics,
        "baseline_summary": {
            metric: {
                "mean": stats.get("mean", 0),
                "stddev": stats.get("stddev", 0),
                "data_points": stats.get("count", 0),
            }
            for metric, stats in baseline.items()
        },
        "threshold_stddev": threshold_stddev,
        "baseline_window_days": baseline_window_days,
        "processing_timestamp": datetime.now(timezone.utc).isoformat(),
        "total_cdr_files": len(cdr_results),
        "total_log_files": len(log_results),
    }

    # 結果書き出し
    if output_bucket:
        date_prefix = datetime.now(timezone.utc).strftime("%Y/%m/%d")
        result_key = f"results/anomaly/{date_prefix}/{context.aws_request_id}.json"
        try:
            s3_client.put_object(
                Bucket=output_bucket,
                Key=result_key,
                Body=json.dumps(result, default=str, ensure_ascii=False),
                ContentType="application/json",
            )
        except Exception as e:
            logger.error("Failed to write anomaly result: %s", str(e))

    # SNS 通知 (異常検出時)
    if anomalies and sns_topic_arn:
        try:
            sns_client = boto3.client("sns")
            sns_client.publish(
                TopicArn=sns_topic_arn,
                Subject="[Telecom Analytics] Anomaly Detected",
                Message=json.dumps(
                    {
                        "anomaly_count": len(anomalies),
                        "classification": classification.get("classification", "unknown"),
                        "explanation": classification.get("explanation", ""),
                        "anomalies": anomalies[:5],  # 上位5件のみ通知
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                    default=str,
                    ensure_ascii=False,
                ),
            )
        except Exception as e:
            logger.error("Failed to publish SNS notification: %s", str(e))

    # EMF メトリクス
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="anomaly_detector")
    metrics.set_dimension("UseCase", "telecom-network-analytics")
    metrics.put_metric("AnomaliesDetected", float(len(anomalies)), "Count")
    metrics.put_metric("FilesProcessed", float(len(cdr_results) + len(log_results)), "Count")
    metrics.flush()

    logger.info(
        "Anomaly Detector completed: anomalies=%d, classification=%s",
        len(anomalies),
        classification.get("classification", "unknown"),
    )

    return result


def _aggregate_current_metrics(
    cdr_results: list[dict[str, Any]],
    log_results: list[dict[str, Any]],
) -> dict[str, float]:
    """CDR/Log 処理結果から現在のメトリクスを集約する。

    Args:
        cdr_results: CDR Analyzer の結果リスト
        log_results: Log Analyzer の結果リスト

    Returns:
        dict: 集約されたメトリクス {metric_name: value}
    """
    metrics: dict[str, float] = {}

    # CDR メトリクス集約
    total_records = 0
    total_duration = 0.0
    duration_count = 0
    peak_concurrent = 0

    for result in cdr_results:
        if result.get("status") != "success":
            continue
        stats = result.get("statistics", {})
        total_records += stats.get("total_records", 0)
        if stats.get("average_duration"):
            total_duration += stats["average_duration"]
            duration_count += 1
        if stats.get("peak_concurrent_calls", 0) > peak_concurrent:
            peak_concurrent = stats["peak_concurrent_calls"]

    if total_records > 0:
        metrics["call_volume"] = float(total_records)
    if duration_count > 0:
        metrics["average_duration"] = total_duration / duration_count
    if peak_concurrent > 0:
        metrics["peak_concurrent_calls"] = float(peak_concurrent)

    # Log メトリクス集約
    total_failures = 0
    total_breaches = 0

    for result in log_results:
        if result.get("status") != "success":
            continue
        total_failures += result.get("equipment_failures_count", 0)
        total_breaches += result.get("capacity_breaches_count", 0)

    metrics["equipment_failures_count"] = float(total_failures)
    metrics["capacity_breaches_count"] = float(total_breaches)

    return metrics


def _record_error(
    s3_client,
    output_bucket: str,
    context_id: str,
    error_category: str,
    error_details: str,
) -> None:
    """エラーレコードを errors/cdr/ プレフィックス下に書き出す。

    Args:
        s3_client: boto3 S3 クライアント
        output_bucket: 出力バケット名
        context_id: コンテキスト識別子
        error_category: エラーカテゴリ
        error_details: エラー詳細
    """
    error_record = {
        "file_path": context_id,
        "error_category": error_category,
        "error_details": error_details,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    date_prefix = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    error_key = f"errors/cdr/{date_prefix}/{context_id}.error.json"

    try:
        s3_client.put_object(
            Bucket=output_bucket,
            Key=error_key,
            Body=json.dumps(error_record, ensure_ascii=False),
            ContentType="application/json",
        )
    except Exception as e:
        logger.error("Failed to record error for %s: %s", context_id, str(e))
