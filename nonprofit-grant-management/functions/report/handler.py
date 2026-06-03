"""NPO・非営利団体 (UC24) Report Lambda ハンドラ

助成金ポートフォリオサマリを生成する。
コンプライアンスステータスと成果達成率を含む。

出力 (Requirement 8.4):
    - reports/grants/{YYYY-MM-DD}/{execution_id}.json — JSON レポート
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


def compute_compliance_status(grant_results: list[dict]) -> dict:
    """助成金のコンプライアンスステータスを計算する。

    Args:
        grant_results: Grant Extractor 出力リスト

    Returns:
        dict: コンプライアンスステータス集計
    """
    total = len(grant_results)
    compliant = 0
    non_compliant = 0
    pending_review = 0

    for result in grant_results:
        if result.get("status") == "success":
            info = result.get("extracted_info", {})
            # 必須フィールドの充足チェック
            has_applicant = bool(
                info.get("applicant_info", {}).get("organization_name")
            )
            has_budget = info.get("budget", {}).get("total_amount") is not None
            has_project = bool(
                info.get("project_description", {}).get("title")
            )

            if has_applicant and has_budget and has_project:
                compliant += 1
            else:
                pending_review += 1
        elif result.get("status") == "error":
            non_compliant += 1
        elif result.get("status") == "skipped":
            pending_review += 1

    return {
        "total": total,
        "compliant": compliant,
        "non_compliant": non_compliant,
        "pending_review": pending_review,
        "compliance_rate": round(compliant / total * 100, 1) if total > 0 else 0.0,
    }


def compute_achievement_rates(outcome_results: list[dict]) -> dict:
    """成果達成率を計算する。

    Args:
        outcome_results: Outcome Matcher 出力リスト

    Returns:
        dict: 達成率集計
    """
    total = len(outcome_results)
    achieved = 0
    partially_achieved = 0
    not_achieved = 0
    achievement_scores: list[float] = []

    for result in outcome_results:
        if result.get("status") != "success":
            continue

        outcome_data = result.get("outcome_data", {})
        overall_rate = outcome_data.get("overall_achievement_rate")

        if overall_rate is not None:
            try:
                rate = float(overall_rate)
                achievement_scores.append(rate)
                if rate >= 80:
                    achieved += 1
                elif rate >= 50:
                    partially_achieved += 1
                else:
                    not_achieved += 1
            except (ValueError, TypeError):
                pass

        # objective_matching から集計
        for match in outcome_data.get("objective_matching", []):
            status = match.get("achievement_status", "")
            if status == "achieved":
                achieved += 1
            elif status == "partially_achieved":
                partially_achieved += 1
            elif status == "not_achieved":
                not_achieved += 1

    avg_achievement = (
        round(sum(achievement_scores) / len(achievement_scores), 1)
        if achievement_scores
        else 0.0
    )

    return {
        "total_reports": total,
        "achieved": achieved,
        "partially_achieved": partially_achieved,
        "not_achieved": not_achieved,
        "average_achievement_rate": avg_achievement,
    }


def aggregate_by_program_area(
    grant_results: list[dict],
    outcome_results: list[dict],
) -> dict[str, dict]:
    """プログラムエリア別に集約する。

    Args:
        grant_results: Grant Extractor 出力リスト
        outcome_results: Outcome Matcher 出力リスト

    Returns:
        dict: プログラムエリア → 集計情報
    """
    area_stats: dict[str, dict] = defaultdict(
        lambda: {
            "grant_applications": 0,
            "activity_reports": 0,
            "total_budget_requested": 0.0,
            "compliance_count": 0,
        }
    )

    for result in grant_results:
        if result.get("status") != "success":
            continue
        info = result.get("extracted_info", {})
        metadata = info.get("_metadata", {})
        area = metadata.get("program_area", "general")

        area_stats[area]["grant_applications"] += 1

        budget = info.get("budget", {})
        total_amount = budget.get("total_amount")
        if total_amount is not None:
            try:
                area_stats[area]["total_budget_requested"] += float(total_amount)
            except (ValueError, TypeError):
                pass

        # コンプライアンスチェック
        has_required_fields = bool(
            info.get("applicant_info", {}).get("organization_name")
            and budget.get("total_amount") is not None
            and info.get("project_description", {}).get("title")
        )
        if has_required_fields:
            area_stats[area]["compliance_count"] += 1

    for result in outcome_results:
        if result.get("status") != "success":
            continue
        outcome_data = result.get("outcome_data", {})
        metadata = outcome_data.get("_metadata", {})
        area = metadata.get("program_area", "general")
        area_stats[area]["activity_reports"] += 1

    return dict(area_stats)


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Nonprofit Grant Report Lambda

    助成金ポートフォリオサマリを生成する。

    Input event:
        - grant_results: Grant Extractor 出力リスト
        - outcome_results: Outcome Matcher 出力リスト
        - discovery: Discovery Lambda の出力

    Returns:
        dict: report_key, summary
    """
    start_time = time.time()

    s3ap_output = S3ApHelper(
        os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ.get("S3_ACCESS_POINT", ""))
    )
    sns_topic_arn = os.environ.get("SNS_TOPIC_ARN", "")

    grant_results = event.get("grant_results", [])
    outcome_results = event.get("outcome_results", [])
    discovery_info = event.get("discovery", {})

    logger.info(
        "Grant Report generation started: grant_results=%d, outcome_results=%d",
        len(grant_results),
        len(outcome_results),
    )

    # コンプライアンスステータス計算
    compliance_status = compute_compliance_status(grant_results)

    # 達成率計算
    achievement_rates = compute_achievement_rates(outcome_results)

    # プログラムエリア別集計
    program_area_breakdown = aggregate_by_program_area(
        grant_results, outcome_results
    )

    # エラー・スキップ集計
    total_processed = len(grant_results) + len(outcome_results)
    success_count = sum(
        1 for r in grant_results + outcome_results if r.get("status") == "success"
    )
    error_count = sum(
        1 for r in grant_results + outcome_results if r.get("status") == "error"
    )
    skipped_count = sum(
        1 for r in grant_results + outcome_results if r.get("status") == "skipped"
    )

    processing_duration_ms = int((time.time() - start_time) * 1000)

    # JSON レポート生成
    report_json = {
        "report_id": context.aws_request_id,
        "use_case": "nonprofit-grant-management",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "summary": {
            "total_documents_processed": total_processed,
            "success_count": success_count,
            "error_count": error_count,
            "skipped_count": skipped_count,
            "processing_duration_ms": processing_duration_ms,
        },
        "compliance_status": compliance_status,
        "achievement_rates": achievement_rates,
        "program_area_breakdown": program_area_breakdown,
        "discovery_metadata": {
            "execution_id": discovery_info.get("execution_id"),
            "total_objects": discovery_info.get("total_objects", 0),
            "grant_application_count": discovery_info.get(
                "grant_application_count", 0
            ),
            "activity_report_count": discovery_info.get(
                "activity_report_count", 0
            ),
        },
    }

    # S3 出力
    report_period = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    execution_id = context.aws_request_id
    report_key = f"reports/grants/{report_period}/{execution_id}.json"

    s3ap_output.put_object(
        key=report_key,
        body=json.dumps(report_json, ensure_ascii=False, default=str),
        content_type="application/json",
    )

    logger.info(
        "Grant Report generated: key=%s, compliance_rate=%.1f%%, "
        "avg_achievement=%.1f%%, errors=%d, skipped=%d",
        report_key,
        compliance_status["compliance_rate"],
        achievement_rates["average_achievement_rate"],
        error_count,
        skipped_count,
    )

    # SNS 通知（エラーまたは低達成率がある場合）
    if sns_topic_arn and (
        error_count > 0 or achievement_rates["average_achievement_rate"] < 50
    ):
        try:
            sns_client = boto3.client("sns")
            sns_client.publish(
                TopicArn=sns_topic_arn,
                Subject=(
                    f"[UC24] Grant Portfolio Report - "
                    f"{error_count} errors, "
                    f"achievement {achievement_rates['average_achievement_rate']}%"
                ),
                Message=(
                    f"Grant Portfolio Report\n"
                    f"Period: {report_period}\n"
                    f"Total Processed: {total_processed}\n"
                    f"Success: {success_count}\n"
                    f"Errors: {error_count}\n"
                    f"Skipped: {skipped_count}\n"
                    f"Compliance Rate: {compliance_status['compliance_rate']}%\n"
                    f"Achievement Rate: {achievement_rates['average_achievement_rate']}%\n"
                    f"Report: {report_key}"
                ),
            )
        except Exception as e:
            logger.warning("SNS notification failed: %s", str(e))

    # EMF メトリクス (Requirement 13.7)
    metrics_emf = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="report")
    metrics_emf.set_dimension("UseCase", "nonprofit-grant-management")
    metrics_emf.put_metric("ProcessingDuration", float(processing_duration_ms), "Milliseconds")
    metrics_emf.put_metric("SuccessCount", float(success_count), "Count")
    metrics_emf.put_metric("ErrorCount", float(error_count), "Count")
    metrics_emf.put_metric("ObjectsProcessed", float(total_processed), "Count")
    metrics_emf.flush()

    return {
        "report_key": report_key,
        "summary": report_json["summary"],
        "compliance_status": compliance_status,
        "achievement_rates": achievement_rates,
    }
