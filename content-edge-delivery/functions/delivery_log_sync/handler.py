"""Content Edge Delivery — Delivery Log Sync Lambda ハンドラ

CDN/エッジ配信ネットワークの配信ログを正規化し、FSx for ONTAP S3 AP へ
書き戻すことで、制作・管理データと配信実績を同一基盤で突合可能にする。

本ハンドラは配信ベンダー非依存。各 CDN のログ形式差分は _normalize_log_record で吸収する
（雛形では汎用 JSON Lines を想定。各 CDN 固有パーサは拡張ポイント）。

注意（privacy）:
    配信ログには視聴者の IP / User-Agent 等の PII が含まれ得る。
    REDACT_CLIENT_IP=true の場合、クライアント IP をマスクして書き戻す。

Environment Variables:
    S3_ACCESS_POINT_OUTPUT: 正規化ログ書き込み用 S3 AP Alias or ARN
    LOG_SOURCE_ENDPOINT: 配信ログ取得元の S3 互換エンドポイント URL（任意）
    LOG_SOURCE_BUCKET: 配信ログ取得元バケット（任意）
    LOG_SOURCE_PREFIX: 配信ログのプレフィックス（デフォルト: "cdn-logs/"）
    REDACT_CLIENT_IP: "true" でクライアント IP をマスク（デフォルト: true）
    DEMO_MODE: "true" の場合、event 内の inline ログを使用（外部取得をスキップ）
    DATA_CLASSIFICATION: 出力データ分類（デフォルト: INTERNAL）
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from shared.data_classification import get_classification
from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler
from shared.s3ap_helper import S3ApHelper
from shared.schemas.events import DeliveryLogSummaryOutput

logger = logging.getLogger(__name__)

DEFAULT_LOG_SOURCE_PREFIX = "cdn-logs/"


def _is_demo_mode() -> bool:
    return os.environ.get("DEMO_MODE", "false").lower() == "true"


def _should_redact_ip() -> bool:
    return os.environ.get("REDACT_CLIENT_IP", "true").lower() == "true"


def _redact_ip(ip: str) -> str:
    """クライアント IP の下位オクテットをマスクする（IPv4 簡易版）。"""
    if not ip:
        return ip
    parts = ip.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.x.x"
    return "x.x.x.x"


def _normalize_log_record(record: dict) -> dict:
    """配信ログ 1 件を正規化する。

    雛形では汎用キー（timestamp, key, status, bytes, client_ip, cdn_target）を想定。
    各 CDN 固有形式（CloudFront 標準ログ、Akamai DataStream 等）のパーサはここを拡張する。
    """
    client_ip = str(record.get("client_ip", ""))
    if _should_redact_ip():
        client_ip = _redact_ip(client_ip)
    return {
        "timestamp": record.get("timestamp", ""),
        "key": record.get("key", ""),
        "status": record.get("status", ""),
        "bytes": int(record.get("bytes", 0) or 0),
        "client_ip": client_ip,
        "cdn_target": record.get("cdn_target", ""),
    }


def _load_records(event: dict) -> list[dict]:
    """配信ログレコードを取得する。

    DemoMode では event["log_records"] を使用。本番では外部 S3 互換ストアから取得する
    （雛形では外部取得は未実装の拡張ポイントとし、空リストを返す）。
    """
    if _is_demo_mode():
        return list(event.get("log_records", []))
    # 拡張ポイント: LOG_SOURCE_ENDPOINT/BUCKET から JSON Lines を取得してパースする
    logger.info("Non-demo log fetch is an extension point; returning empty record set in scaffold.")
    return []


@trace_lambda_handler
@lambda_error_handler
def handler(event, context) -> DeliveryLogSummaryOutput:
    """Delivery Log Sync Lambda。

    配信ログを正規化し、サマリを S3 AP へ書き戻す。

    Returns:
        dict: summary_key, record_count, total_bytes, data_classification
    """
    s3ap_output = S3ApHelper(os.environ["S3_ACCESS_POINT_OUTPUT"])

    raw_records = _load_records(event or {})
    normalized = [_normalize_log_record(r) for r in raw_records]
    total_bytes = sum(r["bytes"] for r in normalized)

    classification = get_classification()
    summary = {
        "execution_id": context.aws_request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "record_count": len(normalized),
        "total_bytes": total_bytes,
        "client_ip_redacted": _should_redact_ip(),
        "records": normalized,
        "data_classification": classification.value,
        "data_classification_label": classification.label,
    }

    summary_key = (
        f"delivery-log-summaries/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{context.aws_request_id}.json"
    )
    s3ap_output.put_object(
        key=summary_key,
        body=json.dumps(summary, default=str),
        content_type="application/json",
    )

    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="delivery_log_sync")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "content-edge-delivery"))
    metrics.put_metric("DeliveryLogRecords", float(len(normalized)), "Count")
    metrics.flush()

    logger.info(
        "Delivery log sync completed: records=%d, total_bytes=%d, summary=%s",
        len(normalized),
        total_bytes,
        summary_key,
    )

    return {
        "summary_key": summary_key,
        "record_count": len(normalized),
        "total_bytes": total_bytes,
        "data_classification": classification.value,
    }
