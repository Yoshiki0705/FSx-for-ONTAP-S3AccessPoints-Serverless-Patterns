"""不動産 (UC26) Report Lambda ハンドラ

ポートフォリオサマリレポートを生成する。

出力 (Requirement 10.4):
    - reports/real-estate/{YYYY-MM-DD}/{execution_id}.json — JSON レポート
    - 空室状況、契約更新タイムライン、状態評価

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


def compute_portfolio_summary(
    property_results: list[dict],
    contract_results: list[dict],
) -> dict:
    """物件ポートフォリオサマリを計算する。

    Args:
        property_results: Property Analyzer 出力
        contract_results: Contract Extractor 出力

    Returns:
        dict: vacancy_status, renewal_timeline, condition_ratings
    """
    # 物件別の状態集計
    property_conditions: dict[str, dict] = defaultdict(
        lambda: {
            "image_count": 0,
            "condition": "good",
            "pii_flagged": False,
            "amenities": set(),
            "rooms": set(),
        }
    )

    for result in property_results:
        if result.get("status") != "success":
            continue
        pid = result.get("property_id") or "unknown"
        property_conditions[pid]["image_count"] += 1
        if result.get("condition") == "needs_repair":
            property_conditions[pid]["condition"] = "needs_repair"
        if result.get("pii_detected"):
            property_conditions[pid]["pii_flagged"] = True
        property_conditions[pid]["amenities"].update(result.get("amenities", []))
        property_conditions[pid]["rooms"].update(result.get("rooms", []))

    # 契約情報集計
    contract_info: dict[str, dict] = {}
    for result in contract_results:
        if result.get("status") != "success":
            continue
        pid = result.get("property_id") or "unknown"
        terms = result.get("lease_terms", {})
        contract_info[pid] = {
            "rent_amount": terms.get("rent_amount"),
            "lease_period_months": terms.get("lease_period_months"),
            "tenant_name": terms.get("tenant_name"),
            "has_contract": True,
        }

    # 空室状況推定
    all_property_ids = set(property_conditions.keys()) | set(contract_info.keys())
    vacancy_status: dict[str, str] = {}
    for pid in all_property_ids:
        if pid in contract_info and contract_info[pid].get("has_contract"):
            vacancy_status[pid] = "occupied"
        else:
            vacancy_status[pid] = "vacant"

    vacant_count = sum(1 for v in vacancy_status.values() if v == "vacant")
    occupied_count = sum(1 for v in vacancy_status.values() if v == "occupied")

    # 状態評価
    condition_ratings: dict[str, str] = {}
    for pid, cond in property_conditions.items():
        condition_ratings[pid] = cond["condition"]

    good_count = sum(1 for v in condition_ratings.values() if v == "good")
    repair_count = sum(1 for v in condition_ratings.values() if v == "needs_repair")

    return {
        "total_properties": len(all_property_ids),
        "vacancy": {
            "vacant": vacant_count,
            "occupied": occupied_count,
            "vacancy_rate": (
                round(vacant_count / len(all_property_ids) * 100, 1)
                if all_property_ids
                else 0.0
            ),
        },
        "condition": {
            "good": good_count,
            "needs_repair": repair_count,
        },
        "pii_flagged_properties": [
            pid
            for pid, cond in property_conditions.items()
            if cond["pii_flagged"]
        ],
        "contract_summary": {
            "with_contract": len(contract_info),
            "average_rent": (
                round(
                    sum(
                        c["rent_amount"]
                        for c in contract_info.values()
                        if c.get("rent_amount")
                    )
                    / max(
                        sum(1 for c in contract_info.values() if c.get("rent_amount")),
                        1,
                    )
                )
                if contract_info
                else 0
            ),
        },
    }


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Real Estate Portfolio Report Lambda

    ポートフォリオサマリレポートを生成する。

    Input event:
        - property_results: Property Analyzer 出力
        - contract_results: Contract Extractor 出力
        - discovery: Discovery Lambda 出力

    Returns:
        dict: report_key, summary
    """
    start_time = time.time()

    s3ap_output = S3ApHelper(
        os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ.get("S3_ACCESS_POINT", ""))
    )
    sns_topic_arn = os.environ.get("SNS_TOPIC_ARN", "")

    property_results = event.get("property_results", [])
    contract_results = event.get("contract_results", [])
    discovery_info = event.get("discovery", {})

    logger.info(
        "Real Estate Report generation started: properties=%d, contracts=%d",
        len(property_results),
        len(contract_results),
    )

    # ポートフォリオサマリ計算
    portfolio_summary = compute_portfolio_summary(property_results, contract_results)

    # 集計
    all_results = property_results + contract_results
    total_processed = len(all_results)
    success_count = sum(1 for r in all_results if r.get("status") == "success")
    error_count = sum(1 for r in all_results if r.get("status") == "error")

    processing_duration_ms = int((time.time() - start_time) * 1000)

    # JSON レポート生成
    report_json = {
        "report_id": context.aws_request_id,
        "use_case": "real-estate-portfolio",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "summary": {
            "total_processed": total_processed,
            "success_count": success_count,
            "error_count": error_count,
            "processing_duration_ms": processing_duration_ms,
        },
        "portfolio": portfolio_summary,
        "discovery_metadata": {
            "execution_id": discovery_info.get("execution_id"),
            "total_objects": discovery_info.get("total_objects", 0),
            "property_image_count": discovery_info.get("property_image_count", 0),
            "contract_count": discovery_info.get("contract_count", 0),
        },
    }

    # S3 出力
    report_period = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    execution_id = context.aws_request_id
    report_key = f"reports/real-estate/{report_period}/{execution_id}.json"

    s3ap_output.put_object(
        key=report_key,
        body=json.dumps(report_json, ensure_ascii=False, default=str),
        content_type="application/json",
    )

    logger.info(
        "Real Estate Report generated: key=%s, properties=%d, vacancy_rate=%.1f%%",
        report_key,
        portfolio_summary["total_properties"],
        portfolio_summary["vacancy"]["vacancy_rate"],
    )

    # SNS 通知 (PII フラグ付き物件がある場合)
    if sns_topic_arn and portfolio_summary["pii_flagged_properties"]:
        try:
            sns_client = boto3.client("sns")
            sns_client.publish(
                TopicArn=sns_topic_arn,
                Subject="[UC26] PII detected in property images - redaction required",
                Message=(
                    f"Real Estate Portfolio Report\n"
                    f"Period: {report_period}\n"
                    f"Properties with PII: {portfolio_summary['pii_flagged_properties']}\n"
                    f"Action Required: Review and redact before public listing\n"
                    f"Report: {report_key}\n"
                ),
            )
        except Exception as e:
            logger.warning("SNS notification failed: %s", str(e))

    # EMF メトリクス (Requirement 13.7)
    metrics_emf = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="report")
    metrics_emf.set_dimension("UseCase", "real-estate-portfolio")
    metrics_emf.put_metric("ProcessingDuration", float(processing_duration_ms), "Milliseconds")
    metrics_emf.put_metric("SuccessCount", float(success_count), "Count")
    metrics_emf.put_metric("ErrorCount", float(error_count), "Count")
    metrics_emf.put_metric("ObjectsProcessed", float(total_processed), "Count")
    metrics_emf.flush()

    return {
        "report_key": report_key,
        "summary": report_json["summary"],
        "portfolio": portfolio_summary,
    }
