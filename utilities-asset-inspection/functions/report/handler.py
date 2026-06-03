"""電力・ユーティリティ (UC25) Report Lambda ハンドラ

設備状態評価と予測保全スケジュールを生成する。

出力 (Requirement 9.4):
    - reports/utilities/{YYYY-MM-DD}/{execution_id}.json — JSON レポート
    - 予測保全スケジュール: 1-365 日の保全計画
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
from collections import defaultdict
from datetime import datetime, timezone

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)


def compute_equipment_condition(
    defect_results: list[dict],
    scada_results: list[dict],
    thermal_results: list[dict],
) -> dict[str, dict]:
    """設備 ID 別の状態評価を計算する。

    Args:
        defect_results: Defect Detector 出力
        scada_results: SCADA Analyzer 出力
        thermal_results: Thermal Analyzer 出力

    Returns:
        dict: 設備 ID → 状態評価
    """
    equipment_conditions: dict[str, dict] = defaultdict(
        lambda: {
            "defect_count": 0,
            "critical_defects": 0,
            "major_defects": 0,
            "minor_defects": 0,
            "anomaly_count": 0,
            "hot_spot_count": 0,
            "overall_condition": "good",
        }
    )

    # 欠陥情報の集約
    for result in defect_results:
        if result.get("status") != "success":
            continue
        eq_id = result.get("equipment_id") or "unknown"
        defects = result.get("defects", [])
        equipment_conditions[eq_id]["defect_count"] += len(defects)
        for defect in defects:
            severity = defect.get("severity", "minor")
            if severity == "critical":
                equipment_conditions[eq_id]["critical_defects"] += 1
            elif severity == "major":
                equipment_conditions[eq_id]["major_defects"] += 1
            else:
                equipment_conditions[eq_id]["minor_defects"] += 1

    # SCADA 異常情報の集約
    for result in scada_results:
        if result.get("status") != "success":
            continue
        eq_id = result.get("equipment_id") or "unknown"
        anomalies = result.get("anomalies", [])
        equipment_conditions[eq_id]["anomaly_count"] += len(anomalies)

    # サーマル情報の集約
    for result in thermal_results:
        if result.get("status") != "success":
            continue
        eq_id = result.get("equipment_id") or "unknown"
        hot_spots = result.get("hot_spots", [])
        equipment_conditions[eq_id]["hot_spot_count"] += len(hot_spots)

    # 全体状態の決定
    for eq_id, condition in equipment_conditions.items():
        if condition["critical_defects"] > 0:
            condition["overall_condition"] = "critical"
        elif condition["major_defects"] > 0 or condition["hot_spot_count"] > 2:
            condition["overall_condition"] = "degraded"
        elif condition["minor_defects"] > 2 or condition["anomaly_count"] > 3:
            condition["overall_condition"] = "fair"
        else:
            condition["overall_condition"] = "good"

    return dict(equipment_conditions)


def generate_maintenance_schedule(
    equipment_conditions: dict[str, dict],
) -> list[dict]:
    """予測保全スケジュールを生成する (1-365 日)。

    重大度と状態に基づき保全推奨日数を計算:
    - critical: 1-7 日以内
    - degraded: 14-30 日以内
    - fair: 60-90 日以内
    - good: 180-365 日 (定期点検)

    Args:
        equipment_conditions: 設備別状態評価

    Returns:
        list[dict]: 保全スケジュール
    """
    schedule: list[dict] = []

    for eq_id, condition in equipment_conditions.items():
        overall = condition["overall_condition"]

        if overall == "critical":
            days_until_maintenance = 1
            priority = "immediate"
            action = "emergency_inspection"
        elif overall == "degraded":
            days_until_maintenance = 14
            priority = "high"
            action = "planned_maintenance"
        elif overall == "fair":
            days_until_maintenance = 60
            priority = "medium"
            action = "scheduled_inspection"
        else:
            days_until_maintenance = 180
            priority = "low"
            action = "routine_inspection"

        # 1-365 の範囲にクランプ
        days_until_maintenance = max(1, min(365, days_until_maintenance))

        schedule.append({
            "equipment_id": eq_id,
            "days_until_maintenance": days_until_maintenance,
            "priority": priority,
            "recommended_action": action,
            "condition_summary": {
                "overall": overall,
                "defects": condition["defect_count"],
                "critical_defects": condition["critical_defects"],
                "anomalies": condition["anomaly_count"],
                "hot_spots": condition["hot_spot_count"],
            },
        })

    # 優先度順にソート
    priority_order = {"immediate": 0, "high": 1, "medium": 2, "low": 3}
    schedule.sort(key=lambda x: priority_order.get(x["priority"], 4))

    return schedule


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Utilities Asset Inspection Report Lambda

    設備状態評価と予測保全スケジュールを生成する。

    Input event:
        - defect_results: Defect Detector 出力
        - scada_results: SCADA Analyzer 出力
        - thermal_results: Thermal Analyzer 出力
        - discovery: Discovery Lambda 出力

    Returns:
        dict: report_key, summary
    """
    start_time = time.time()

    s3ap_output = S3ApHelper(
        os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ.get("S3_ACCESS_POINT", ""))
    )
    sns_topic_arn = os.environ.get("SNS_TOPIC_ARN", "")

    defect_results = event.get("defect_results", [])
    scada_results = event.get("scada_results", [])
    thermal_results = event.get("thermal_results", [])
    discovery_info = event.get("discovery", {})

    logger.info(
        "Utilities Report generation started: defects=%d, scada=%d, thermal=%d",
        len(defect_results),
        len(scada_results),
        len(thermal_results),
    )

    # 設備状態評価
    equipment_conditions = compute_equipment_condition(
        defect_results, scada_results, thermal_results
    )

    # 予測保全スケジュール生成
    maintenance_schedule = generate_maintenance_schedule(equipment_conditions)

    # 集計
    all_results = defect_results + scada_results + thermal_results
    total_processed = len(all_results)
    success_count = sum(
        1 for r in all_results if r.get("status") == "success"
    )
    error_count = sum(
        1 for r in all_results if r.get("status") == "error"
    )

    # 欠陥集計 (severity 別)
    total_defects = sum(
        r.get("defect_count", 0)
        for r in defect_results
        if r.get("status") == "success"
    )
    critical_defects = sum(
        c.get("critical_defects", 0) for c in equipment_conditions.values()
    )
    major_defects = sum(
        c.get("major_defects", 0) for c in equipment_conditions.values()
    )
    minor_defects = sum(
        c.get("minor_defects", 0) for c in equipment_conditions.values()
    )

    processing_duration_ms = int((time.time() - start_time) * 1000)

    # JSON レポート生成
    report_json = {
        "report_id": context.aws_request_id,
        "use_case": "utilities-asset-inspection",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "summary": {
            "total_processed": total_processed,
            "success_count": success_count,
            "error_count": error_count,
            "processing_duration_ms": processing_duration_ms,
            "unique_equipment": len(equipment_conditions),
            "total_defects": total_defects,
            "defects_by_severity": {
                "critical": critical_defects,
                "major": major_defects,
                "minor": minor_defects,
            },
        },
        "equipment_conditions": equipment_conditions,
        "maintenance_schedule": maintenance_schedule,
        "discovery_metadata": {
            "execution_id": discovery_info.get("execution_id"),
            "total_objects": discovery_info.get("total_objects", 0),
            "drone_image_count": discovery_info.get("drone_image_count", 0),
            "thermal_image_count": discovery_info.get("thermal_image_count", 0),
            "scada_log_count": discovery_info.get("scada_log_count", 0),
        },
    }

    # S3 出力
    report_period = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    execution_id = context.aws_request_id
    report_key = f"reports/utilities/{report_period}/{execution_id}.json"

    s3ap_output.put_object(
        key=report_key,
        body=json.dumps(report_json, ensure_ascii=False, default=str),
        content_type="application/json",
    )

    logger.info(
        "Utilities Report generated: key=%s, equipment=%d, "
        "defects=%d (critical=%d), errors=%d",
        report_key,
        len(equipment_conditions),
        total_defects,
        critical_defects,
        error_count,
    )

    # SNS 通知（critical 欠陥がある場合）
    if sns_topic_arn and critical_defects > 0:
        try:
            sns_client = boto3.client("sns")
            sns_client.publish(
                TopicArn=sns_topic_arn,
                Subject=(
                    f"[UC25] CRITICAL - {critical_defects} critical defects detected"
                ),
                Message=(
                    f"Utilities Asset Inspection Report\n"
                    f"Period: {report_period}\n"
                    f"Equipment Inspected: {len(equipment_conditions)}\n"
                    f"Total Defects: {total_defects}\n"
                    f"  Critical: {critical_defects}\n"
                    f"  Major: {major_defects}\n"
                    f"  Minor: {minor_defects}\n"
                    f"Errors: {error_count}\n"
                    f"Report: {report_key}\n"
                    f"\nImmediate maintenance required for equipment: "
                    f"{[s['equipment_id'] for s in maintenance_schedule if s['priority'] == 'immediate']}"
                ),
            )
        except Exception as e:
            logger.warning("SNS notification failed: %s", str(e))

    # EMF メトリクス (Requirement 13.7)
    metrics_emf = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="report")
    metrics_emf.set_dimension("UseCase", "utilities-asset-inspection")
    metrics_emf.put_metric("ProcessingDuration", float(processing_duration_ms), "Milliseconds")
    metrics_emf.put_metric("SuccessCount", float(success_count), "Count")
    metrics_emf.put_metric("ErrorCount", float(error_count), "Count")
    metrics_emf.put_metric("ObjectsProcessed", float(total_processed), "Count")
    metrics_emf.put_metric("CriticalDefects", float(critical_defects), "Count")
    metrics_emf.flush()

    return {
        "report_key": report_key,
        "summary": report_json["summary"],
        "equipment_conditions": equipment_conditions,
        "maintenance_schedule": maintenance_schedule,
    }
