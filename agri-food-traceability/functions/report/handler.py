"""農業・食品業界 (UC21) Report Lambda ハンドラ

作物健全性レポートとトレーサビリティ監査サマリを生成する。
120 秒以内に完了する設計 (Requirement 5.4)。

出力:
    - reports/agri/{YYYY-MM-DD}/{execution_id}.json — JSON 形式レポート
    - EMF メトリクス: ProcessingDuration, SuccessCount, ErrorCount

レポート内容:
    - 作物健全性評価: フィールド別異常カウント、異常タイプ、座標
    - トレーサビリティ監査サマリ: ロット別文書数、分類信頼度分布

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

# レポート生成最大時間 (秒) — SLO
REPORT_TIMEOUT_SECONDS: int = 120


def aggregate_crop_results(results: list[dict]) -> dict:
    """作物分析結果を集約する。

    Per-field anomaly count, anomaly types, affected area coordinates (Req 5.4)

    Args:
        results: 作物分析結果リスト

    Returns:
        dict: 作物健全性評価サマリ
    """
    total = len(results)
    success_count = sum(1 for r in results if r.get("status") == "success")
    error_count = total - success_count

    # 位置情報ステータス集計
    verified_count = 0
    unverified_count = 0

    # 異常集計
    anomaly_type_counts: dict[str, int] = {}
    total_confirmed_anomalies = 0
    total_review_required = 0
    affected_coordinates: list[dict] = []

    for result in results:
        if result.get("status") != "success":
            continue

        # 位置情報ステータス
        location_status = result.get("location_status", "location-unverified")
        if location_status == "verified":
            verified_count += 1
        else:
            unverified_count += 1

        # 異常データ
        anomalies = result.get("anomalies", {})
        confirmed = anomalies.get("confirmed", [])
        review_req = anomalies.get("review_required", [])

        total_confirmed_anomalies += len(confirmed)
        total_review_required += len(review_req)

        for anomaly in confirmed:
            atype = anomaly.get("anomaly_type", "unknown")
            anomaly_type_counts[atype] = anomaly_type_counts.get(atype, 0) + 1

        # 座標情報の収集
        geolocation = result.get("geolocation")
        if geolocation and confirmed:
            affected_coordinates.append({
                "key": result.get("key"),
                "latitude": geolocation.get("latitude"),
                "longitude": geolocation.get("longitude"),
                "anomaly_count": len(confirmed),
                "anomaly_types": [a.get("anomaly_type") for a in confirmed],
            })

    return {
        "total_images_analyzed": total,
        "success_count": success_count,
        "error_count": error_count,
        "location_status": {
            "verified": verified_count,
            "unverified": unverified_count,
        },
        "anomaly_summary": {
            "total_confirmed": total_confirmed_anomalies,
            "total_review_required": total_review_required,
            "anomaly_type_distribution": anomaly_type_counts,
        },
        "affected_areas": affected_coordinates,
    }


def aggregate_traceability_results(results: list[dict]) -> dict:
    """トレーサビリティ抽出結果を集約する。

    Document count per lot, classification confidence distribution (Req 5.4)

    Args:
        results: トレーサビリティ抽出結果リスト

    Returns:
        dict: トレーサビリティ監査サマリ
    """
    total = len(results)
    success_count = sum(1 for r in results if r.get("status") == "success")
    error_count = total - success_count

    # ロット別集計
    lot_document_counts: dict[str, int] = {}
    confidence_values: list[float] = []
    classified_count = 0
    review_required_count = 0

    for result in results:
        if result.get("status") != "success":
            continue

        # ロットID
        fields = result.get("extracted_fields", {})
        lot_id = fields.get("lot_id") or "unknown"
        lot_document_counts[lot_id] = lot_document_counts.get(lot_id, 0) + 1

        # 分類信頼度
        classification = result.get("classification", {})
        confidence = classification.get("classification_confidence", 0.0)
        confidence_values.append(confidence)

        status = classification.get("status", "review-required")
        if status == "classified":
            classified_count += 1
        else:
            review_required_count += 1

    # 信頼度分布の計算
    confidence_distribution = {
        "min": round(min(confidence_values), 4) if confidence_values else 0.0,
        "max": round(max(confidence_values), 4) if confidence_values else 0.0,
        "mean": round(
            sum(confidence_values) / len(confidence_values), 4
        ) if confidence_values else 0.0,
        "above_threshold": classified_count,
        "below_threshold": review_required_count,
    }

    return {
        "total_documents_processed": total,
        "success_count": success_count,
        "error_count": error_count,
        "lot_summary": {
            "unique_lots": len(lot_document_counts),
            "documents_per_lot": lot_document_counts,
        },
        "classification_summary": {
            "classified": classified_count,
            "review_required": review_required_count,
            "confidence_distribution": confidence_distribution,
        },
    }


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Agri-Food Traceability Report Lambda

    作物分析結果とトレーサビリティ抽出結果を集約し、
    レポートを生成する (120 秒以内)。

    Input event:
        - crop_results: 作物分析結果リスト
        - traceability_results: トレーサビリティ抽出結果リスト
        - discovery: Discovery Lambda の出力

    Returns:
        dict: report_key, summary
    """
    start_time = time.time()

    s3ap_output = S3ApHelper(
        os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ.get("S3_ACCESS_POINT", ""))
    )
    sns_topic_arn = os.environ.get("SNS_TOPIC_ARN", "")

    crop_results = event.get("crop_results", [])
    traceability_results = event.get("traceability_results", [])
    discovery_info = event.get("discovery", {})

    logger.info(
        "Report generation started: crop_results=%d, traceability_results=%d",
        len(crop_results),
        len(traceability_results),
    )

    # 結果集約
    crop_summary = aggregate_crop_results(crop_results)
    traceability_summary = aggregate_traceability_results(traceability_results)

    # 全体サマリ
    total_processed = (
        crop_summary["total_images_analyzed"]
        + traceability_summary["total_documents_processed"]
    )
    total_success = crop_summary["success_count"] + traceability_summary["success_count"]
    total_errors = crop_summary["error_count"] + traceability_summary["error_count"]

    processing_duration_ms = int((time.time() - start_time) * 1000)

    report_period = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    execution_id = context.aws_request_id

    # JSON レポート生成
    report_json = {
        "report_id": execution_id,
        "use_case": "agri-food-traceability",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": report_period,
        "summary": {
            "total_processed": total_processed,
            "success_count": total_success,
            "error_count": total_errors,
            "processing_duration_ms": processing_duration_ms,
        },
        "crop_health_assessment": crop_summary,
        "traceability_audit": traceability_summary,
        "discovery_metadata": {
            "execution_id": discovery_info.get("execution_id"),
            "total_objects": discovery_info.get("total_objects", 0),
        },
    }

    # S3 出力
    report_key = f"reports/agri/{report_period}/{execution_id}.json"

    s3ap_output.put_object(
        key=report_key,
        body=json.dumps(report_json, ensure_ascii=False, default=str),
        content_type="application/json",
    )

    # 最終処理時間確認
    final_duration_ms = int((time.time() - start_time) * 1000)
    report_json["summary"]["processing_duration_ms"] = final_duration_ms

    if final_duration_ms > REPORT_TIMEOUT_SECONDS * 1000:
        logger.warning(
            "Report generation exceeded SLO: %dms > %dms",
            final_duration_ms,
            REPORT_TIMEOUT_SECONDS * 1000,
        )

    logger.info(
        "Report generated: key=%s, total=%d, success=%d, errors=%d, duration=%dms",
        report_key,
        total_processed,
        total_success,
        total_errors,
        final_duration_ms,
    )

    # SNS 通知（エラーがある場合）
    if sns_topic_arn and total_errors > 0:
        try:
            sns_client = boto3.client("sns")
            sns_client.publish(
                TopicArn=sns_topic_arn,
                Subject=f"[UC21] Agri-Food Report - {total_errors} errors detected",
                Message=(
                    f"Agri-Food Traceability Report\n"
                    f"Period: {report_period}\n"
                    f"Total Processed: {total_processed}\n"
                    f"Success: {total_success}\n"
                    f"Errors: {total_errors}\n"
                    f"Report: {report_key}\n"
                    f"Anomalies Confirmed: {crop_summary['anomaly_summary']['total_confirmed']}\n"
                    f"Review Required: {crop_summary['anomaly_summary']['total_review_required']}"
                ),
            )
        except Exception as e:
            logger.warning("SNS notification failed: %s", str(e))

    # EMF メトリクス (Requirement 13.7)
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="report")
    metrics.set_dimension("UseCase", "agri-food-traceability")
    metrics.put_metric("ProcessingDuration", float(final_duration_ms), "Milliseconds")
    metrics.put_metric("SuccessCount", float(total_success), "Count")
    metrics.put_metric("ErrorCount", float(total_errors), "Count")
    metrics.put_metric("ObjectsProcessed", float(total_processed), "Count")
    metrics.flush()

    return {
        "report_key": report_key,
        "summary": report_json["summary"],
    }
