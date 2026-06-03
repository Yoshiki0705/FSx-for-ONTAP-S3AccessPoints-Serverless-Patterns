"""通信業界 (UC18) Report Lambda ハンドラ

デイリーネットワーク健全性サマリおよび異常アラートレポートを生成する。
出力は S3 の `reports/daily/{YYYY-MM-DD}/` プレフィックス配下に書き込む。
クリティカル異常検出時は SNS 通知を送信する。
CloudWatch EMF メトリクスとして ProcessingDuration, SuccessCount, ErrorCount を出力する。

処理フロー:
    1. Anomaly Detector の結果を受信
    2. CDR/Log/Anomaly 結果を集約してレポート生成
    3. reports/daily/{YYYY-MM-DD}/ プレフィックスに JSON レポート出力
    4. クリティカル異常時は SNS 通知
    5. EMF メトリクス出力 (ProcessingDuration, SuccessCount, ErrorCount)

Requirements: 2.4, 2.7, 2.8, 13.7

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
    OUTPUT_BUCKET: 出力バケット名
    SNS_TOPIC_ARN: 通知先 SNS トピック ARN
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)


def generate_report_id() -> str:
    """一意のレポート ID を生成する。"""
    return str(uuid.uuid4())


def aggregate_results(event: dict[str, Any]) -> dict[str, Any]:
    """Anomaly Detector からの結果を集約してレポートデータを構築する。

    Args:
        event: Step Functions から渡されるイベント

    Returns:
        dict: 集約レポートデータ
    """
    anomaly_result = event.get("anomaly_result", event)

    # 異常情報
    anomalies = anomaly_result.get("anomalies", [])
    anomaly_count = anomaly_result.get("anomaly_count", len(anomalies))
    classification = anomaly_result.get("classification", {})

    # メトリクス情報
    current_metrics = anomaly_result.get("current_metrics", {})
    baseline_summary = anomaly_result.get("baseline_summary", {})

    # 処理サマリ
    total_cdr_files = anomaly_result.get("total_cdr_files", 0)
    total_log_files = anomaly_result.get("total_log_files", 0)

    # CDR/Log 結果 (Step Functions から直接渡される場合)
    cdr_results = event.get("cdr_results", [])
    log_results = event.get("log_results", [])

    # 成功/エラーカウント
    success_count = 0
    error_count = 0

    for result in cdr_results:
        if result.get("status") == "success":
            success_count += 1
        else:
            error_count += 1

    for result in log_results:
        if result.get("status") == "success":
            success_count += 1
        else:
            error_count += 1

    # 直接的なファイル数が渡されていない場合は anomaly_result から取得
    if not cdr_results and not log_results:
        total_processed = total_cdr_files + total_log_files
        # anomaly_result が success なら全ファイルが成功扱い
        if anomaly_result.get("status") == "success":
            success_count = total_processed
            error_count = 0
        else:
            success_count = total_processed
            error_count = 0

    total_processed = success_count + error_count

    return {
        "anomalies": anomalies,
        "anomaly_count": anomaly_count,
        "classification": classification,
        "current_metrics": current_metrics,
        "baseline_summary": baseline_summary,
        "total_cdr_files": total_cdr_files,
        "total_log_files": total_log_files,
        "total_processed": total_processed,
        "success_count": success_count,
        "error_count": error_count,
    }


def build_network_health_report(
    report_id: str,
    aggregated: dict[str, Any],
    report_date: str,
) -> dict[str, Any]:
    """ネットワーク健全性レポートを構築する。

    Args:
        report_id: レポート ID
        aggregated: 集約済みデータ
        report_date: レポート対象日 (YYYY-MM-DD)

    Returns:
        dict: レポート JSON 構造
    """
    classification = aggregated.get("classification", {})
    anomalies = aggregated.get("anomalies", [])

    # 重大度判定
    severity = "normal"
    if anomalies:
        max_z_score = max(a.get("z_score", 0) for a in anomalies)
        classification_type = classification.get("classification", "unknown")

        if classification_type in ("equipment_degradation", "capacity_exhaustion"):
            severity = "critical"
        elif max_z_score > 5.0:
            severity = "critical"
        elif max_z_score > 4.0:
            severity = "warning"
        else:
            severity = "info"

    report = {
        "report_id": report_id,
        "use_case": "telecom-network-analytics",
        "report_type": "daily_network_health",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "report_date": report_date,
        "severity": severity,
        "summary": {
            "network_status": "degraded" if severity == "critical" else (
                "attention_required" if severity == "warning" else "healthy"
            ),
            "anomaly_count": aggregated["anomaly_count"],
            "classification": classification.get("classification", "normal"),
            "explanation": classification.get("explanation", ""),
            "recommendations": classification.get("recommendations", []),
        },
        "metrics": {
            "total_processed": aggregated["total_processed"],
            "success_count": aggregated["success_count"],
            "error_count": aggregated["error_count"],
            "total_cdr_files": aggregated["total_cdr_files"],
            "total_log_files": aggregated["total_log_files"],
        },
        "current_metrics": aggregated["current_metrics"],
        "baseline_summary": aggregated["baseline_summary"],
        "anomalies": anomalies,
        "details": {
            "top_anomalies": anomalies[:10],
            "metric_deviations": [
                {
                    "metric": a.get("metric_name"),
                    "current": a.get("current_value"),
                    "baseline_mean": a.get("baseline_mean"),
                    "z_score": a.get("z_score"),
                    "direction": a.get("deviation_direction"),
                }
                for a in anomalies
            ],
        },
    }

    return report


def is_critical_anomaly(report: dict[str, Any]) -> bool:
    """レポートにクリティカル異常が含まれているかどうか判定する。

    Args:
        report: 生成済みレポート

    Returns:
        bool: クリティカル異常がある場合 True
    """
    return report.get("severity") == "critical"


def publish_critical_alert(
    sns_client,
    topic_arn: str,
    report: dict[str, Any],
) -> None:
    """クリティカル異常検出時に SNS 通知を発行する。

    Args:
        sns_client: boto3 SNS クライアント
        topic_arn: SNS トピック ARN
        report: レポートデータ
    """
    summary = report.get("summary", {})
    anomaly_count = summary.get("anomaly_count", 0)
    classification = summary.get("classification", "unknown")
    explanation = summary.get("explanation", "")

    subject = (
        f"[CRITICAL] Telecom Network Anomaly: {classification} "
        f"({anomaly_count} anomalies)"
    )
    # SNS subject 最大 100 文字
    if len(subject) > 100:
        subject = subject[:97] + "..."

    message = {
        "alert_type": "critical_network_anomaly",
        "report_id": report.get("report_id"),
        "report_date": report.get("report_date"),
        "severity": "critical",
        "anomaly_count": anomaly_count,
        "classification": classification,
        "explanation": explanation,
        "recommendations": summary.get("recommendations", []),
        "top_anomalies": report.get("details", {}).get("top_anomalies", [])[:5],
        "generated_at": report.get("generated_at"),
    }

    try:
        sns_client.publish(
            TopicArn=topic_arn,
            Subject=subject,
            Message=json.dumps(message, default=str, ensure_ascii=False),
        )
        logger.info("Critical alert published to SNS: %s", topic_arn)
    except Exception as e:
        logger.error("Failed to publish SNS alert: %s", str(e))


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Report Lambda ハンドラ

    Step Functions の最終ステップとして呼び出され、デイリーレポートを生成する。

    Event 形式 (Step Functions から渡される):
        {
            "anomaly_result": { ... },  # Anomaly Detector の結果
            "cdr_results": [...],       # CDR Analyzer 結果 (optional)
            "log_results": [...],       # Log Analyzer 結果 (optional)
            "manifest_key": "..."
        }

    Processing Flow:
        1. 結果集約
        2. レポート生成
        3. S3 reports/daily/{YYYY-MM-DD}/ に書き出し
        4. クリティカル異常時 SNS 通知
        5. EMF メトリクス出力

    Returns:
        dict: レポート生成結果 (report_key, severity, anomaly_count)
    """
    start_time = time.time()

    logger.info("Report Lambda started: event_keys=%s", list(event.keys()))

    # 環境設定
    output_bucket = os.environ.get("OUTPUT_BUCKET", "")
    sns_topic_arn = os.environ.get("SNS_TOPIC_ARN", "")
    s3_client = boto3.client("s3")

    report_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report_id = generate_report_id()

    success_count = 0
    error_count = 0

    try:
        # Step 1: 結果集約
        with xray_subsegment(
            name="aggregate_results",
            annotations={
                "service_name": "report",
                "operation": "AggregateResults",
                "use_case": "telecom-network-analytics",
            },
        ):
            aggregated = aggregate_results(event)

        # Step 2: レポート生成
        with xray_subsegment(
            name="build_report",
            annotations={
                "service_name": "report",
                "operation": "BuildReport",
                "use_case": "telecom-network-analytics",
            },
        ):
            report = build_network_health_report(
                report_id=report_id,
                aggregated=aggregated,
                report_date=report_date,
            )

        # Step 3: S3 書き出し
        report_key = f"reports/daily/{report_date}/{report_id}.json"

        if output_bucket:
            with xray_subsegment(
                name="write_report",
                annotations={
                    "service_name": "s3",
                    "operation": "PutObject",
                    "use_case": "telecom-network-analytics",
                },
            ):
                s3_client.put_object(
                    Bucket=output_bucket,
                    Key=report_key,
                    Body=json.dumps(report, default=str, ensure_ascii=False),
                    ContentType="application/json",
                )

            logger.info("Report written to s3://%s/%s", output_bucket, report_key)

        # Step 4: クリティカル異常時 SNS 通知
        if is_critical_anomaly(report) and sns_topic_arn:
            with xray_subsegment(
                name="publish_alert",
                annotations={
                    "service_name": "sns",
                    "operation": "Publish",
                    "use_case": "telecom-network-analytics",
                },
            ):
                sns_client = boto3.client("sns")
                publish_critical_alert(sns_client, sns_topic_arn, report)

        success_count = aggregated.get("success_count", 1)
        error_count = aggregated.get("error_count", 0)

    except Exception as e:
        logger.error("Report generation failed: %s", str(e))
        error_count = 1
        raise
    finally:
        # Step 5: EMF メトリクス出力 (Requirement 13.7)
        processing_duration_ms = (time.time() - start_time) * 1000

        metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="report")
        metrics.set_dimension("UseCase", "telecom-network-analytics")
        metrics.put_metric("ProcessingDuration", processing_duration_ms, "Milliseconds")
        metrics.put_metric("SuccessCount", float(success_count), "Count")
        metrics.put_metric("ErrorCount", float(error_count), "Count")
        metrics.flush()

        logger.info(
            "Report Lambda metrics emitted: ProcessingDuration=%.2fms, "
            "SuccessCount=%d, ErrorCount=%d",
            processing_duration_ms,
            success_count,
            error_count,
        )

    result = {
        "status": "success",
        "report_id": report_id,
        "report_key": report_key,
        "report_date": report_date,
        "severity": report.get("severity", "normal"),
        "anomaly_count": aggregated.get("anomaly_count", 0),
        "total_processed": aggregated.get("total_processed", 0),
        "success_count": success_count,
        "error_count": error_count,
        "processing_duration_ms": round(processing_duration_ms, 2),
    }

    logger.info(
        "Report Lambda completed: report_key=%s, severity=%s, anomalies=%d",
        report_key,
        report.get("severity"),
        aggregated.get("anomaly_count", 0),
    )

    return result
