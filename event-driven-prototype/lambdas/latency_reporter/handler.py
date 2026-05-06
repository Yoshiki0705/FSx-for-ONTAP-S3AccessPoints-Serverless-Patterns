"""Event-Driven Prototype: レイテンシ計測・EMF 出力 Lambda ハンドラ

Step Functions ワークフローの最終ステップとして呼び出され、
イベント駆動パイプラインのレイテンシメトリクスを CloudWatch EMF 形式で出力する。

計測メトリクス:
- EventToProcessingLatency: イベント発生から処理開始までのレイテンシ (ms)
- EndToEndDuration: イベント発生から処理完了までの全体所要時間 (ms)
- EventVolumePerMinute: 1分あたりのイベント処理数

Environment Variables:
    USE_CASE: ユースケース名 (event-driven-prototype)
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)


def calculate_latency_metrics(
    event_time: str | None,
    processing_duration_ms: float | None,
    event_to_processing_ms: float | None,
) -> dict:
    """レイテンシメトリクスを計算する。

    Args:
        event_time: イベント発生時刻 (ISO 8601)
        processing_duration_ms: 処理所要時間 (ms)
        event_to_processing_ms: イベント発生から処理開始までのレイテンシ (ms)

    Returns:
        dict: 計算されたレイテンシメトリクス
    """
    now = time.time()
    metrics = {
        "event_to_processing_latency_ms": 0.0,
        "end_to_end_duration_ms": 0.0,
        "processing_duration_ms": processing_duration_ms or 0.0,
        "reported_at": datetime.now(timezone.utc).isoformat(),
    }

    # Event-to-Processing Latency
    if event_to_processing_ms is not None:
        metrics["event_to_processing_latency_ms"] = event_to_processing_ms

    # End-to-End Duration (event time → now)
    if event_time:
        try:
            event_dt = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
            end_to_end_ms = (now - event_dt.timestamp()) * 1000
            metrics["end_to_end_duration_ms"] = round(end_to_end_ms, 2)
        except (ValueError, TypeError):
            # If event_time is invalid, use processing_duration as fallback
            metrics["end_to_end_duration_ms"] = processing_duration_ms or 0.0
    elif processing_duration_ms:
        metrics["end_to_end_duration_ms"] = processing_duration_ms

    return metrics


def emit_latency_metrics(metrics: dict, use_case: str) -> None:
    """CloudWatch EMF 形式でレイテンシメトリクスを出力する。

    Args:
        metrics: レイテンシメトリクス辞書
        use_case: ユースケース名
    """
    emf = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="latency_reporter")
    emf.set_dimension("UseCase", use_case)
    emf.set_dimension("TriggerMode", "event-driven")

    # Event-to-Processing Latency
    emf.put_metric(
        "EventToProcessingLatency",
        metrics["event_to_processing_latency_ms"],
        "Milliseconds",
    )

    # End-to-End Duration
    emf.put_metric(
        "EndToEndDuration",
        metrics["end_to_end_duration_ms"],
        "Milliseconds",
    )

    # Processing Duration
    emf.put_metric(
        "ProcessingDuration",
        metrics["processing_duration_ms"],
        "Milliseconds",
    )

    # Event Volume (1 event processed)
    emf.put_metric("EventVolumePerMinute", 1.0, "Count")

    emf.flush()


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """レイテンシ計測・EMF 出力 Lambda。

    Step Functions の前段 (EventProcessor) の結果を受け取り、
    レイテンシメトリクスを計算して CloudWatch EMF 形式で出力する。

    Args:
        event: Step Functions からの入力
            {
                "detail": {...},
                "time": "...",
                "processing_result": {
                    "processing_duration_ms": ...,
                    "event_to_processing_ms": ...,
                    "event_time": "...",
                    ...
                },
                "error": {...}  # optional, if processing failed
            }

    Returns:
        dict: レイテンシレポート
    """
    use_case = os.environ.get("USE_CASE", "event-driven-prototype")

    # 前段の処理結果を取得
    processing_result = event.get("processing_result", {})
    error_info = event.get("error")

    event_time = (
        processing_result.get("event_time")
        or event.get("time")
    )
    processing_duration_ms = processing_result.get("processing_duration_ms")
    event_to_processing_ms = processing_result.get("event_to_processing_ms")

    logger.info(
        "Latency reporting: event_time=%s, processing_duration_ms=%s, "
        "event_to_processing_ms=%s, has_error=%s",
        event_time,
        processing_duration_ms,
        event_to_processing_ms,
        error_info is not None,
    )

    # レイテンシメトリクス計算
    latency_metrics = calculate_latency_metrics(
        event_time=event_time,
        processing_duration_ms=processing_duration_ms,
        event_to_processing_ms=event_to_processing_ms,
    )

    # EMF メトリクス出力
    emit_latency_metrics(latency_metrics, use_case)

    # エラー情報があれば記録
    if error_info:
        latency_metrics["processing_error"] = str(error_info)
        logger.warning("Processing error detected: %s", error_info)

    logger.info(
        "Latency report completed: e2e=%.2fms, event_to_proc=%.2fms",
        latency_metrics["end_to_end_duration_ms"],
        latency_metrics["event_to_processing_latency_ms"],
    )

    return latency_metrics
