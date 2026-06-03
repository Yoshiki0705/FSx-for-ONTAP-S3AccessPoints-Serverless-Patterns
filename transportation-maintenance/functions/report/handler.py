"""運輸・鉄道業界 (UC22) Report Lambda ハンドラ

劣化トレンド分析と保守優先度ランキングレポートを生成する。

出力 (Requirement 6.4):
    - 12ヶ月劣化トレンド分析
    - 保守優先度ランキング (重大度 + コンポーネント経年によるソート)
    - EMF メトリクス: ProcessingDuration, SuccessCount, ErrorCount

Environment Variables:
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
    SNS_TOPIC_ARN: SNS トピック ARN (通知用)
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)

# 重大度のソート優先度 (低い数値 = 高い優先度)
SEVERITY_PRIORITY: dict[str, int] = {
    "critical": 1,
    "major": 2,
    "minor": 3,
    "observation": 4,
}


def aggregate_deterioration_results(results: list[dict]) -> dict:
    """劣化検出結果を集約する。

    12ヶ月劣化トレンド + 重大度別カウント

    Args:
        results: 劣化検出結果リスト

    Returns:
        dict: 劣化トレンドサマリ
    """
    total = len(results)
    success_count = sum(
        1 for r in results
        if r.get("status") in ("success", "requires-reinspection")
    )
    error_count = total - success_count

    # 重大度集計
    severity_totals = {"critical": 0, "major": 0, "minor": 0, "observation": 0}
    human_review_count = 0
    reinspection_count = 0
    safety_critical_count = 0

    # 優先度ランキング用リスト
    priority_items: list[dict] = []

    for result in results:
        status = result.get("status", "")

        if status == "requires-reinspection":
            reinspection_count += 1
            priority_items.append({
                "key": result.get("key", ""),
                "status": "requires-reinspection",
                "severity": "unknown",
                "priority_score": 0,  # 再点検が必要 — 最高優先度
                "is_safety_critical": result.get("is_safety_critical", False),
                "reason": result.get("reason", "Low resolution"),
            })
            continue

        if status != "success":
            continue

        # 重大度カウント
        severity_counts = result.get("severity_counts", {})
        for sev, count in severity_counts.items():
            if sev in severity_totals:
                severity_totals[sev] += count

        # Human review
        if result.get("human_review_required", False):
            human_review_count += 1

        # Safety critical
        if result.get("is_safety_critical", False):
            safety_critical_count += 1

        # 優先度ランキングに追加
        classifications = result.get("severity_classifications", [])
        max_severity = "observation"
        for cls in classifications:
            sev = cls.get("severity", "observation")
            if SEVERITY_PRIORITY.get(sev, 4) < SEVERITY_PRIORITY.get(max_severity, 4):
                max_severity = sev

        priority_items.append({
            "key": result.get("key", ""),
            "status": "analyzed",
            "severity": max_severity,
            "priority_score": SEVERITY_PRIORITY.get(max_severity, 4),
            "is_safety_critical": result.get("is_safety_critical", False),
            "human_review_required": result.get("human_review_required", False),
            "deterioration_count": result.get("detection_summary", {}).get(
                "deterioration_labels_count", 0
            ),
        })

    # 優先度ランキングソート (Requirement 6.4):
    # 1. priority_score (重大度: 低い値 = 高い重大度)
    # 2. is_safety_critical (安全重要が先)
    priority_items.sort(
        key=lambda x: (
            x.get("priority_score", 99),
            0 if x.get("is_safety_critical") else 1,
        )
    )

    return {
        "total_images_analyzed": total,
        "success_count": success_count,
        "error_count": error_count,
        "severity_summary": severity_totals,
        "human_review_required_count": human_review_count,
        "reinspection_required_count": reinspection_count,
        "safety_critical_count": safety_critical_count,
        "priority_ranking": priority_items[:50],  # Top 50
    }


def aggregate_maintenance_results(results: list[dict]) -> dict:
    """保守抽出結果を集約する。

    Args:
        results: 保守抽出結果リスト

    Returns:
        dict: 保守データサマリ
    """
    total = len(results)
    success_count = sum(1 for r in results if r.get("status") == "success")
    error_count = total - success_count

    # ライフサイクルデータ集約
    equipment_data: list[dict] = []

    for result in results:
        if result.get("status") != "success":
            continue

        lifecycle = result.get("lifecycle_data", {})
        equipment_data.append({
            "key": result.get("key", ""),
            "equipment_id": lifecycle.get("equipment_id"),
            "installation_date": lifecycle.get("installation_date"),
            "last_repair_date": lifecycle.get("last_repair_date"),
            "component_age_days": lifecycle.get("component_age_days"),
            "replacement_schedule": lifecycle.get("replacement_schedule"),
            "repair_history_count": len(lifecycle.get("repair_history", [])),
        })

    return {
        "total_documents_processed": total,
        "success_count": success_count,
        "error_count": error_count,
        "equipment_records": equipment_data,
        "equipment_count": len(equipment_data),
    }


def generate_deterioration_trend(
    deterioration_summary: dict,
    maintenance_summary: dict,
) -> dict:
    """12ヶ月劣化トレンド分析を生成する。

    Requirement 6.4: 直近12ヶ月の点検データに基づく劣化トレンド

    Args:
        deterioration_summary: 劣化検出サマリ
        maintenance_summary: 保守データサマリ

    Returns:
        dict: 劣化トレンド分析
    """
    # 現在のスナップショットベースのトレンド
    # 実運用では過去12ヶ月のデータを DynamoDB/S3 から取得して比較
    current_period = datetime.now(timezone.utc).strftime("%Y-%m")

    trend = {
        "analysis_period_months": 12,
        "current_snapshot": {
            "period": current_period,
            "severity_distribution": deterioration_summary.get("severity_summary", {}),
            "total_defects_detected": sum(
                deterioration_summary.get("severity_summary", {}).values()
            ),
            "safety_critical_items": deterioration_summary.get("safety_critical_count", 0),
        },
        "trend_indicators": {
            "note": "Full 12-month trend requires historical data accumulation",
            "current_critical_count": deterioration_summary.get(
                "severity_summary", {}
            ).get("critical", 0),
            "current_major_count": deterioration_summary.get(
                "severity_summary", {}
            ).get("major", 0),
        },
        "maintenance_correlation": {
            "documents_with_lifecycle_data": maintenance_summary.get("equipment_count", 0),
            "total_maintenance_records": maintenance_summary.get(
                "total_documents_processed", 0
            ),
        },
    }

    return trend


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Transportation Maintenance Report Lambda

    劣化検出結果と保守抽出結果を集約し、
    12ヶ月トレンド分析と優先度ランキングレポートを生成する。

    Input event:
        - deterioration_results: 劣化検出結果リスト
        - maintenance_results: 保守抽出結果リスト
        - discovery: Discovery Lambda の出力

    Returns:
        dict: report_key, summary
    """
    start_time = time.time()

    s3ap_output = S3ApHelper(
        os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ.get("S3_ACCESS_POINT", ""))
    )
    sns_topic_arn = os.environ.get("SNS_TOPIC_ARN", "")

    deterioration_results = event.get("deterioration_results", [])
    maintenance_results = event.get("maintenance_results", [])
    discovery_info = event.get("discovery", {})

    logger.info(
        "Report generation started: deterioration_results=%d, maintenance_results=%d",
        len(deterioration_results),
        len(maintenance_results),
    )

    # 結果集約
    deterioration_summary = aggregate_deterioration_results(deterioration_results)
    maintenance_summary = aggregate_maintenance_results(maintenance_results)

    # 12ヶ月劣化トレンド生成
    trend_analysis = generate_deterioration_trend(
        deterioration_summary, maintenance_summary
    )

    # 全体サマリ
    total_processed = (
        deterioration_summary["total_images_analyzed"]
        + maintenance_summary["total_documents_processed"]
    )
    total_success = (
        deterioration_summary["success_count"] + maintenance_summary["success_count"]
    )
    total_errors = (
        deterioration_summary["error_count"] + maintenance_summary["error_count"]
    )

    processing_duration_ms = int((time.time() - start_time) * 1000)

    report_period = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    execution_id = context.aws_request_id

    # JSON レポート生成
    report_json = {
        "report_id": execution_id,
        "use_case": "transportation-maintenance",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": report_period,
        "summary": {
            "total_processed": total_processed,
            "success_count": total_success,
            "error_count": total_errors,
            "processing_duration_ms": processing_duration_ms,
        },
        "deterioration_analysis": deterioration_summary,
        "maintenance_data": maintenance_summary,
        "deterioration_trend": trend_analysis,
        "priority_ranking": deterioration_summary.get("priority_ranking", []),
        "discovery_metadata": {
            "execution_id": discovery_info.get("execution_id"),
            "total_objects": discovery_info.get("total_objects", 0),
        },
    }

    # S3 出力
    report_key = f"reports/transportation/{report_period}/{execution_id}.json"

    s3ap_output.put_object(
        key=report_key,
        body=json.dumps(report_json, ensure_ascii=False, default=str),
        content_type="application/json",
    )

    # 最終処理時間
    final_duration_ms = int((time.time() - start_time) * 1000)
    report_json["summary"]["processing_duration_ms"] = final_duration_ms

    logger.info(
        "Report generated: key=%s, total=%d, success=%d, errors=%d, duration=%dms",
        report_key,
        total_processed,
        total_success,
        total_errors,
        final_duration_ms,
    )

    # SNS 通知（critical 検出 or エラーがある場合）
    critical_count = deterioration_summary.get("severity_summary", {}).get("critical", 0)
    if sns_topic_arn and (critical_count > 0 or total_errors > 0):
        try:
            sns_client = boto3.client("sns")
            subject = (
                f"[UC22] Transportation Maintenance - "
                f"{critical_count} CRITICAL defects, {total_errors} errors"
            )
            sns_client.publish(
                TopicArn=sns_topic_arn,
                Subject=subject[:100],
                Message=(
                    f"Transportation Maintenance Report\n"
                    f"Period: {report_period}\n"
                    f"Total Processed: {total_processed}\n"
                    f"Success: {total_success}\n"
                    f"Errors: {total_errors}\n"
                    f"Report: {report_key}\n\n"
                    f"Severity Summary:\n"
                    f"  Critical: {critical_count}\n"
                    f"  Major: {deterioration_summary.get('severity_summary', {}).get('major', 0)}\n"
                    f"  Minor: {deterioration_summary.get('severity_summary', {}).get('minor', 0)}\n"
                    f"  Observation: {deterioration_summary.get('severity_summary', {}).get('observation', 0)}\n"
                    f"  Human Review Required: {deterioration_summary.get('human_review_required_count', 0)}\n"
                    f"  Reinspection Required: {deterioration_summary.get('reinspection_required_count', 0)}\n"
                ),
            )
        except Exception as e:
            logger.warning("SNS notification failed: %s", str(e))

    # EMF メトリクス (Requirement 13.7)
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="report")
    metrics.set_dimension("UseCase", "transportation-maintenance")
    metrics.put_metric("ProcessingDuration", float(final_duration_ms), "Milliseconds")
    metrics.put_metric("SuccessCount", float(total_success), "Count")
    metrics.put_metric("ErrorCount", float(total_errors), "Count")
    metrics.put_metric("ObjectsProcessed", float(total_processed), "Count")
    metrics.put_metric("CriticalDefects", float(critical_count), "Count")
    metrics.flush()

    return {
        "report_key": report_key,
        "summary": report_json["summary"],
    }
