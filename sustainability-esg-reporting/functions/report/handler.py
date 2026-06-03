"""サステナビリティ・ESG (UC23) Report Lambda ハンドラ

統合 ESG レポートを生成する。カテゴリ別・期間別に集約し、
2 期間以上のデータがある場合は YoY トレンド分析を行う。

出力:
    - reports/esg/{YYYY-MM-DD}/{execution_id}.json — JSON 形式レポート
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


def aggregate_by_category(results: list[dict]) -> dict[str, list[dict]]:
    """処理結果を ESG カテゴリ別に集約する。

    Args:
        results: Framework Mapper 出力リスト

    Returns:
        dict: カテゴリ → メトリクスリスト
    """
    categorized: dict[str, list[dict]] = defaultdict(list)

    for result in results:
        if result.get("status") == "error":
            continue

        mapped_metrics = result.get("mapped_metrics", [])
        for metric in mapped_metrics:
            esg_cat = metric.get("esg_category", "unknown")
            categorized[esg_cat].append(metric)

    return dict(categorized)


def aggregate_by_period(metrics: list[dict]) -> dict[str, list[dict]]:
    """メトリクスを期間別に集約する。

    Args:
        metrics: メトリクスリスト

    Returns:
        dict: 期間 → メトリクスリスト
    """
    by_period: dict[str, list[dict]] = defaultdict(list)

    for metric in metrics:
        period = metric.get("period", "unknown")
        by_period[period].append(metric)

    return dict(by_period)


def compute_yoy_trend(
    period_data: dict[str, list[dict]],
) -> list[dict] | None:
    """YoY トレンドを計算する (Requirement 7.4)。

    2 期間以上のデータがある場合にのみ計算する。

    Args:
        period_data: 期間 → メトリクスリスト

    Returns:
        list[dict] | None: YoY トレンドリスト (2 期間未満なら None)
    """
    periods = sorted(period_data.keys())
    if len(periods) < 2:
        return None

    trends: list[dict] = []

    # 各カテゴリ別にトレンド計算
    for i in range(1, len(periods)):
        current_period = periods[i]
        previous_period = periods[i - 1]

        current_metrics = period_data[current_period]
        previous_metrics = period_data[previous_period]

        # カテゴリごとの合計を比較
        current_totals = _sum_by_metric_category(current_metrics)
        previous_totals = _sum_by_metric_category(previous_metrics)

        for category, current_value in current_totals.items():
            previous_value = previous_totals.get(category, 0)
            if previous_value > 0:
                change_pct = round(
                    (current_value - previous_value) / previous_value * 100, 2
                )
            elif current_value > 0:
                change_pct = 100.0  # 前期ゼロ → 今期正
            else:
                change_pct = 0.0

            trends.append({
                "category": category,
                "current_period": current_period,
                "previous_period": previous_period,
                "current_value": current_value,
                "previous_value": previous_value,
                "change_percent": change_pct,
                "direction": "increase" if change_pct > 0 else (
                    "decrease" if change_pct < 0 else "unchanged"
                ),
            })

    return trends


def _sum_by_metric_category(metrics: list[dict]) -> dict[str, float]:
    """メトリクスを category 別に合計する (正規化済み値を使用)。"""
    totals: dict[str, float] = defaultdict(float)
    for m in metrics:
        if m.get("status") == "success" and m.get("normalized_value") is not None:
            cat = m.get("category", "unknown")
            totals[cat] += m["normalized_value"]
    return dict(totals)


def generate_esg_summary(
    categorized: dict[str, list[dict]],
) -> dict:
    """ESG カテゴリ別サマリを生成する。

    Args:
        categorized: カテゴリ → メトリクスリスト

    Returns:
        dict: カテゴリ別サマリ
    """
    summary: dict[str, dict] = {}

    for esg_cat, metrics in categorized.items():
        success_metrics = [m for m in metrics if m.get("status") == "success"]
        validation_metrics = [
            m for m in metrics if m.get("status") == "requires-validation"
        ]

        # メトリクスカテゴリ別集計
        category_totals: dict[str, dict] = {}
        for m in success_metrics:
            cat = m.get("category", "unknown")
            if cat not in category_totals:
                category_totals[cat] = {
                    "total_value": 0.0,
                    "unit": m.get("normalized_unit", ""),
                    "count": 0,
                }
            category_totals[cat]["total_value"] += m.get("normalized_value", 0)
            category_totals[cat]["count"] += 1

        # フレームワークカバレッジ
        frameworks_covered: dict[str, int] = {"GRI": 0, "TCFD": 0, "CDP": 0}
        for m in success_metrics:
            fw = m.get("framework_mappings", {})
            for fw_name in frameworks_covered:
                if fw.get(fw_name):
                    frameworks_covered[fw_name] += 1

        summary[esg_cat] = {
            "total_metrics": len(metrics),
            "success_count": len(success_metrics),
            "requires_validation_count": len(validation_metrics),
            "metric_categories": category_totals,
            "framework_coverage": frameworks_covered,
        }

    return summary


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """ESG Report Lambda

    メトリクス抽出・フレームワークマッピング結果を集約し、
    統合 ESG レポートを生成する。

    Input event:
        - results: Framework Mapper 出力リスト
        - discovery: Discovery Lambda の出力

    Returns:
        dict: report_key, summary
    """
    start_time = time.time()

    s3ap_output = S3ApHelper(
        os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ.get("S3_ACCESS_POINT", ""))
    )
    sns_topic_arn = os.environ.get("SNS_TOPIC_ARN", "")

    results = event.get("results", [])
    discovery_info = event.get("discovery", {})

    logger.info("ESG Report generation started: results_count=%d", len(results))

    # カテゴリ別集約
    categorized = aggregate_by_category(results)

    # 全メトリクスをフラット化
    all_metrics: list[dict] = []
    for metrics_list in categorized.values():
        all_metrics.extend(metrics_list)

    # 期間別集約
    period_data = aggregate_by_period(all_metrics)

    # YoY トレンド計算 (Requirement 7.4: 2期間以上で実施)
    yoy_trends = compute_yoy_trend(period_data)

    # ESG サマリ生成
    esg_summary = generate_esg_summary(categorized)

    # 全体統計
    total_metrics = len(all_metrics)
    total_success = sum(1 for m in all_metrics if m.get("status") == "success")
    total_validation = sum(
        1 for m in all_metrics if m.get("status") == "requires-validation"
    )
    total_errors = sum(1 for r in results if r.get("status") == "error")

    processing_duration_ms = int((time.time() - start_time) * 1000)

    # JSON レポート生成
    report_json = {
        "report_id": context.aws_request_id,
        "use_case": "sustainability-esg-reporting",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "summary": {
            "total_documents_processed": len(results),
            "total_metrics_extracted": total_metrics,
            "success_count": total_success,
            "requires_validation_count": total_validation,
            "error_count": total_errors,
            "processing_duration_ms": processing_duration_ms,
        },
        "esg_categories": esg_summary,
        "period_breakdown": {
            period: len(metrics) for period, metrics in period_data.items()
        },
        "yoy_trends": yoy_trends,
        "frameworks": ["GRI", "TCFD", "CDP"],
        "discovery_metadata": {
            "execution_id": discovery_info.get("execution_id"),
            "total_objects": discovery_info.get("total_objects", 0),
        },
        "all_metrics": all_metrics,
    }

    # S3 出力
    report_period = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    execution_id = context.aws_request_id
    report_key = f"reports/esg/{report_period}/{execution_id}.json"

    s3ap_output.put_object(
        key=report_key,
        body=json.dumps(report_json, ensure_ascii=False, default=str),
        content_type="application/json",
    )

    logger.info(
        "ESG Report generated: key=%s, total_metrics=%d, success=%d, "
        "validation=%d, errors=%d, yoy_available=%s",
        report_key,
        total_metrics,
        total_success,
        total_validation,
        total_errors,
        yoy_trends is not None,
    )

    # SNS 通知（バリデーション必要なメトリクスがある場合）
    if sns_topic_arn and total_validation > 0:
        try:
            sns_client = boto3.client("sns")
            sns_client.publish(
                TopicArn=sns_topic_arn,
                Subject=(
                    f"[UC23] ESG Report - {total_validation} metrics require validation"
                ),
                Message=(
                    f"ESG Metrics Report\n"
                    f"Period: {report_period}\n"
                    f"Total Metrics: {total_metrics}\n"
                    f"Success: {total_success}\n"
                    f"Requires Validation: {total_validation}\n"
                    f"Errors: {total_errors}\n"
                    f"Report: {report_key}"
                ),
            )
        except Exception as e:
            logger.warning("SNS notification failed: %s", str(e))

    # EMF メトリクス (Requirement 13.7)
    metrics_emf = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="report")
    metrics_emf.set_dimension("UseCase", "sustainability-esg-reporting")
    metrics_emf.put_metric("ProcessingDuration", float(processing_duration_ms), "Milliseconds")
    metrics_emf.put_metric("SuccessCount", float(total_success), "Count")
    metrics_emf.put_metric("ErrorCount", float(total_errors), "Count")
    metrics_emf.put_metric("ObjectsProcessed", float(len(results)), "Count")
    metrics_emf.put_metric("MetricsExtracted", float(total_metrics), "Count")
    metrics_emf.flush()

    return {
        "report_key": report_key,
        "summary": report_json["summary"],
    }
