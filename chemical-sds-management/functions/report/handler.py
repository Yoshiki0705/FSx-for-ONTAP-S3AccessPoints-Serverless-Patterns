"""化学・素材 (UC28) Report Lambda ハンドラ

規制準拠サマリと研究データインデックスを生成する。

Requirement 12.4:
    - 期限切れ SDS アラート (> validity_period → priority "critical")
    - GHS 必須セクション欠落アラート
    - 研究データインデックス

Environment Variables:
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
    SNS_TOPIC_ARN: SNS トピック ARN
    SDS_VALIDITY_DAYS: SDS 有効期間日数 (default: 365)
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

# GHS 必須セクション（report 側でも参照）
GHS_MANDATORY_SECTIONS: list[str] = [
    "identification",
    "hazard_classification",
    "composition",
    "first_aid",
    "fire_fighting",
    "accidental_release",
    "handling_storage",
    "exposure_controls",
]


def compute_compliance_summary(
    sds_results: list[dict],
    labbook_results: list[dict],
    validity_days: int = 365,
) -> dict:
    """規制準拠サマリを計算する。

    Args:
        sds_results: SDS Extractor 出力
        labbook_results: Lab Book Analyzer 出力
        validity_days: SDS 有効期間日数

    Returns:
        dict: compliance summary with alerts
    """
    # 期限切れ SDS アラート
    expired_alerts: list[dict] = []
    missing_sections_alerts: list[dict] = []
    compliant_count = 0

    for result in sds_results:
        if result.get("status") != "success":
            continue

        expiry = result.get("expiry", {})
        missing_sections = result.get("missing_ghs_sections", [])

        # Requirement 12.5: 有効期限超過 → priority "critical"
        if expiry.get("is_expired"):
            expired_alerts.append({
                "key": result.get("key"),
                "substance_id": result.get("substance_id"),
                "revision_date": result.get("revision_date"),
                "days_since_revision": expiry.get("days_since_revision"),
                "priority": "critical",
            })

        # GHS 必須セクション欠落
        if missing_sections:
            missing_sections_alerts.append({
                "key": result.get("key"),
                "substance_id": result.get("substance_id"),
                "missing_sections": missing_sections,
                "priority": "high",
            })

        if not expiry.get("is_expired") and not missing_sections:
            compliant_count += 1

    # 研究データインデックス
    research_index: list[dict] = []
    for result in labbook_results:
        if result.get("status") != "success":
            continue
        research_index.append({
            "key": result.get("key"),
            "substance_id": result.get("substance_id"),
            "has_parameters": bool(result.get("experiment_data", {}).get("parameters")),
            "has_results": bool(result.get("experiment_data", {}).get("results")),
            "has_observations": bool(result.get("experiment_data", {}).get("observations")),
        })

    total_sds = sum(1 for r in sds_results if r.get("status") == "success")

    return {
        "total_sds_analyzed": total_sds,
        "compliant_count": compliant_count,
        "compliance_rate": (
            round(compliant_count / total_sds * 100, 1) if total_sds > 0 else 0.0
        ),
        "expired_sds_alerts": expired_alerts,
        "expired_sds_count": len(expired_alerts),
        "missing_sections_alerts": missing_sections_alerts,
        "missing_sections_count": len(missing_sections_alerts),
        "research_data_index": research_index,
        "research_entries_count": len(research_index),
    }


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Chemical SDS Management Report Lambda

    Input event:
        - sds_results: SDS Extractor 出力
        - labbook_results: Lab Book Analyzer 出力
        - discovery: Discovery Lambda 出力

    Returns:
        dict: report_key, summary, compliance
    """
    start_time = time.time()

    s3ap_output = S3ApHelper(
        os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ.get("S3_ACCESS_POINT", ""))
    )
    sns_topic_arn = os.environ.get("SNS_TOPIC_ARN", "")
    validity_days = int(os.environ.get("SDS_VALIDITY_DAYS", "365"))

    sds_results = event.get("sds_results", [])
    labbook_results = event.get("labbook_results", [])
    discovery_info = event.get("discovery", {})

    logger.info(
        "Chemical Report generation: sds=%d, labbooks=%d",
        len(sds_results),
        len(labbook_results),
    )

    # 規制準拠サマリ計算
    compliance = compute_compliance_summary(sds_results, labbook_results, validity_days)

    # 集計
    all_results = sds_results + labbook_results
    total_processed = len(all_results)
    success_count = sum(1 for r in all_results if r.get("status") == "success")
    error_count = sum(1 for r in all_results if r.get("status") == "error")

    processing_duration_ms = int((time.time() - start_time) * 1000)

    # JSON レポート
    report_json = {
        "report_id": context.aws_request_id,
        "use_case": "chemical-sds-management",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "summary": {
            "total_processed": total_processed,
            "success_count": success_count,
            "error_count": error_count,
            "processing_duration_ms": processing_duration_ms,
        },
        "compliance": compliance,
        "discovery_metadata": {
            "execution_id": discovery_info.get("execution_id"),
            "total_objects": discovery_info.get("total_objects", 0),
            "sds_count": discovery_info.get("sds_count", 0),
            "labbook_count": discovery_info.get("labbook_count", 0),
        },
    }

    # S3 出力
    report_period = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    execution_id = context.aws_request_id
    report_key = f"reports/chemical/{report_period}/{execution_id}.json"

    s3ap_output.put_object(
        key=report_key,
        body=json.dumps(report_json, ensure_ascii=False, default=str),
        content_type="application/json",
    )

    logger.info(
        "Chemical Report generated: key=%s, expired=%d, missing_sections=%d",
        report_key,
        compliance["expired_sds_count"],
        compliance["missing_sections_count"],
    )

    # SNS 通知 (期限切れ SDS がある場合)
    if sns_topic_arn and compliance["expired_sds_count"] > 0:
        try:
            sns_client = boto3.client("sns")
            sns_client.publish(
                TopicArn=sns_topic_arn,
                Subject=f"[UC28] CRITICAL - {compliance['expired_sds_count']} expired SDS documents",
                Message=(
                    f"Chemical SDS Compliance Report\n"
                    f"Period: {report_period}\n"
                    f"Expired SDS (>365 days): {compliance['expired_sds_count']}\n"
                    f"Missing GHS Sections: {compliance['missing_sections_count']}\n"
                    f"Compliant: {compliance['compliant_count']}/{compliance['total_sds_analyzed']}\n"
                    f"Report: {report_key}\n"
                ),
            )
        except Exception as e:
            logger.warning("SNS notification failed: %s", str(e))

    # EMF メトリクス
    metrics_emf = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="report")
    metrics_emf.set_dimension("UseCase", "chemical-sds-management")
    metrics_emf.put_metric("ProcessingDuration", float(processing_duration_ms), "Milliseconds")
    metrics_emf.put_metric("SuccessCount", float(success_count), "Count")
    metrics_emf.put_metric("ErrorCount", float(error_count), "Count")
    metrics_emf.put_metric("ObjectsProcessed", float(total_processed), "Count")
    metrics_emf.put_metric("ExpiredSds", float(compliance["expired_sds_count"]), "Count")
    metrics_emf.flush()

    return {
        "report_key": report_key,
        "summary": report_json["summary"],
        "compliance": compliance,
    }
