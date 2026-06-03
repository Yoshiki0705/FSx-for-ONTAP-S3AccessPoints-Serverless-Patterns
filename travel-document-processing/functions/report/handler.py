"""旅行・ホスピタリティ業界 (UC20) Report Lambda ハンドラ

施設状態トレンドレポートと予約処理サマリを生成する。
JSON と人間可読テキストの両フォーマットで出力。

出力:
    - reports/travel/{YYYY-MM-DD}/{execution_id}.json — JSON 形式レポート
    - reports/travel/{YYYY-MM-DD}/{execution_id}.txt — 人間可読テキスト
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


def aggregate_reservation_results(results: list[dict]) -> dict:
    """予約処理結果を集約する。

    Args:
        results: 予約抽出結果のリスト

    Returns:
        dict: 集約された予約処理サマリ
    """
    total = len(results)
    success_count = sum(1 for r in results if r.get("status") == "success")
    error_count = total - success_count

    # 抽出されたデータの統計
    extracted_fields: dict[str, int] = {
        "guest_name": 0,
        "check_in_date": 0,
        "check_out_date": 0,
        "room_type": 0,
        "amount": 0,
    }

    languages_detected: dict[str, int] = {}
    room_types: dict[str, int] = {}

    for result in results:
        if result.get("status") != "success":
            continue

        data = result.get("extracted_data", {})
        for field in extracted_fields:
            if data.get(field):
                extracted_fields[field] += 1

        lang = data.get("language_detected", "unknown")
        languages_detected[lang] = languages_detected.get(lang, 0) + 1

        room = data.get("room_type")
        if room:
            room_types[room] = room_types.get(room, 0) + 1

    return {
        "total_processed": total,
        "success_count": success_count,
        "error_count": error_count,
        "extraction_completeness": {
            field: {"count": count, "rate": round(count / max(success_count, 1) * 100, 1)}
            for field, count in extracted_fields.items()
        },
        "languages_detected": languages_detected,
        "room_type_distribution": room_types,
    }


def aggregate_facility_results(results: list[dict]) -> dict:
    """施設点検結果を集約する。

    Args:
        results: 施設点検結果のリスト

    Returns:
        dict: 施設状態トレンドサマリ
    """
    total = len(results)
    success_count = sum(1 for r in results if r.get("status") == "success")
    error_count = total - success_count

    scores: list[int] = []
    all_damages: dict[str, int] = {}
    total_damage_count: int = 0

    for result in results:
        if result.get("status") != "success":
            continue

        score = result.get("cleanliness_score", 0)
        scores.append(score)

        for damage in result.get("damages", []):
            dtype = damage.get("type", "unknown")
            all_damages[dtype] = all_damages.get(dtype, 0) + 1
            total_damage_count += 1

    avg_score = round(sum(scores) / max(len(scores), 1), 1)
    min_score = min(scores) if scores else 0
    max_score = max(scores) if scores else 0

    # 状態分類
    condition_distribution: dict[str, int] = {
        "excellent": 0,  # 90-100
        "good": 0,       # 70-89
        "fair": 0,       # 50-69
        "poor": 0,       # 0-49
    }
    for score in scores:
        if score >= 90:
            condition_distribution["excellent"] += 1
        elif score >= 70:
            condition_distribution["good"] += 1
        elif score >= 50:
            condition_distribution["fair"] += 1
        else:
            condition_distribution["poor"] += 1

    return {
        "total_inspected": total,
        "success_count": success_count,
        "error_count": error_count,
        "cleanliness_scores": {
            "average": avg_score,
            "minimum": min_score,
            "maximum": max_score,
        },
        "condition_distribution": condition_distribution,
        "damage_summary": {
            "total_damage_instances": total_damage_count,
            "damage_types": all_damages,
        },
    }


def generate_human_readable_report(
    reservation_summary: dict,
    facility_summary: dict,
    report_period: str,
) -> str:
    """人間可読テキストレポートを生成する。

    Args:
        reservation_summary: 予約処理サマリ
        facility_summary: 施設状態サマリ
        report_period: レポート対象期間

    Returns:
        str: テキスト形式レポート
    """
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("旅行・ホスピタリティ処理レポート")
    lines.append("Travel & Hospitality Processing Report")
    lines.append(f"Report Period: {report_period}")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append("=" * 60)
    lines.append("")

    # 予約処理セクション
    lines.append("-" * 40)
    lines.append("■ 予約文書処理サマリ (Reservation Processing)")
    lines.append("-" * 40)
    lines.append(f"  処理件数: {reservation_summary['total_processed']}")
    lines.append(f"  成功: {reservation_summary['success_count']}")
    lines.append(f"  エラー: {reservation_summary['error_count']}")
    lines.append("")

    if reservation_summary.get("extraction_completeness"):
        lines.append("  抽出完全性:")
        for field, info in reservation_summary["extraction_completeness"].items():
            lines.append(f"    {field}: {info['count']} ({info['rate']}%)")
    lines.append("")

    if reservation_summary.get("languages_detected"):
        lines.append("  検出言語:")
        for lang, count in reservation_summary["languages_detected"].items():
            lines.append(f"    {lang}: {count}")
    lines.append("")

    # 施設点検セクション
    lines.append("-" * 40)
    lines.append("■ 施設状態トレンド (Facility Condition Trend)")
    lines.append("-" * 40)
    lines.append(f"  点検件数: {facility_summary['total_inspected']}")
    lines.append(f"  成功: {facility_summary['success_count']}")
    lines.append(f"  エラー: {facility_summary['error_count']}")
    lines.append("")

    scores = facility_summary.get("cleanliness_scores", {})
    lines.append("  清潔度スコア:")
    lines.append(f"    平均: {scores.get('average', 0)}")
    lines.append(f"    最低: {scores.get('minimum', 0)}")
    lines.append(f"    最高: {scores.get('maximum', 0)}")
    lines.append("")

    condition = facility_summary.get("condition_distribution", {})
    lines.append("  状態分布:")
    lines.append(f"    Excellent (90-100): {condition.get('excellent', 0)}")
    lines.append(f"    Good (70-89): {condition.get('good', 0)}")
    lines.append(f"    Fair (50-69): {condition.get('fair', 0)}")
    lines.append(f"    Poor (0-49): {condition.get('poor', 0)}")
    lines.append("")

    damage = facility_summary.get("damage_summary", {})
    if damage.get("total_damage_instances", 0) > 0:
        lines.append(f"  損傷検出: {damage['total_damage_instances']} 件")
        for dtype, count in damage.get("damage_types", {}).items():
            lines.append(f"    {dtype}: {count}")
    else:
        lines.append("  損傷検出: なし")

    lines.append("")
    lines.append("=" * 60)
    lines.append("END OF REPORT")
    lines.append("=" * 60)

    return "\n".join(lines)


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Travel Document Processing Report Lambda

    予約処理結果と施設点検結果を集約し、レポートを生成する。

    Input event:
        - reservation_results: 予約抽出結果リスト
        - facility_results: 施設点検結果リスト
        - discovery: Discovery Lambda の出力

    Returns:
        dict: report_key, summary
    """
    start_time = time.time()

    s3ap_output = S3ApHelper(
        os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ.get("S3_ACCESS_POINT", ""))
    )
    sns_topic_arn = os.environ.get("SNS_TOPIC_ARN", "")

    reservation_results = event.get("reservation_results", [])
    facility_results = event.get("facility_results", [])
    discovery_info = event.get("discovery", {})

    logger.info(
        "Report generation started: reservation_results=%d, facility_results=%d",
        len(reservation_results),
        len(facility_results),
    )

    # 結果集約
    reservation_summary = aggregate_reservation_results(reservation_results)
    facility_summary = aggregate_facility_results(facility_results)

    # 全体サマリ
    total_processed = reservation_summary["total_processed"] + facility_summary["total_inspected"]
    total_success = reservation_summary["success_count"] + facility_summary["success_count"]
    total_errors = reservation_summary["error_count"] + facility_summary["error_count"]

    report_period = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    execution_id = context.aws_request_id

    # JSON レポート生成
    report_json = {
        "report_id": execution_id,
        "use_case": "travel-document-processing",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": report_period,
        "summary": {
            "total_processed": total_processed,
            "success_count": total_success,
            "error_count": total_errors,
            "processing_duration_ms": 0,  # 後で更新
        },
        "reservation_processing": reservation_summary,
        "facility_condition": facility_summary,
        "discovery_metadata": {
            "execution_id": discovery_info.get("execution_id"),
            "total_objects": discovery_info.get("total_objects", 0),
        },
    }

    # 人間可読テキストレポート生成
    text_report = generate_human_readable_report(
        reservation_summary, facility_summary, report_period
    )

    # 処理時間記録
    processing_duration_ms = int((time.time() - start_time) * 1000)
    report_json["summary"]["processing_duration_ms"] = processing_duration_ms

    # S3 出力
    report_key_json = f"reports/travel/{report_period}/{execution_id}.json"
    report_key_text = f"reports/travel/{report_period}/{execution_id}.txt"

    s3ap_output.put_object(
        key=report_key_json,
        body=json.dumps(report_json, ensure_ascii=False, default=str),
        content_type="application/json",
    )

    s3ap_output.put_object(
        key=report_key_text,
        body=text_report,
        content_type="text/plain; charset=utf-8",
    )

    logger.info(
        "Report generated: json=%s, text=%s, total=%d, success=%d, errors=%d",
        report_key_json,
        report_key_text,
        total_processed,
        total_success,
        total_errors,
    )

    # SNS 通知（エラーがある場合）
    if sns_topic_arn and total_errors > 0:
        try:
            sns_client = boto3.client("sns")
            sns_client.publish(
                TopicArn=sns_topic_arn,
                Subject=f"[UC20] Travel Processing Report - {total_errors} errors detected",
                Message=(
                    f"Travel Document Processing Report\n"
                    f"Period: {report_period}\n"
                    f"Total Processed: {total_processed}\n"
                    f"Success: {total_success}\n"
                    f"Errors: {total_errors}\n"
                    f"Report: {report_key_json}"
                ),
            )
        except Exception as e:
            logger.warning("SNS notification failed: %s", str(e))

    # EMF メトリクス (Requirement 13.7)
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="report")
    metrics.set_dimension("UseCase", "travel-document-processing")
    metrics.put_metric("ProcessingDuration", float(processing_duration_ms), "Milliseconds")
    metrics.put_metric("SuccessCount", float(total_success), "Count")
    metrics.put_metric("ErrorCount", float(total_errors), "Count")
    metrics.put_metric("ObjectsProcessed", float(total_processed), "Count")
    metrics.flush()

    return {
        "report_key": report_key_json,
        "report_key_text": report_key_text,
        "summary": report_json["summary"],
    }
