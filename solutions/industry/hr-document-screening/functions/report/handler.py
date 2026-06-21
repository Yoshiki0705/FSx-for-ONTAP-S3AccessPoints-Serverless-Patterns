"""HR (UC27) Report Lambda ハンドラ

候補者パイプラインサマリとスキル分布分析レポートを生成する。

Environment Variables:
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
    SNS_TOPIC_ARN: SNS トピック ARN (通知用)
    PII_MODE: PII 保護モード
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler
from shared.pii_filter import PiiFilter
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)


def compute_pipeline_summary(scored_results: list[dict]) -> dict:
    """候補者パイプラインサマリを計算する。

    Args:
        scored_results: Candidate Scorer 出力

    Returns:
        dict: pipeline summary with skill distribution
    """
    total = len(scored_results)
    successful = [r for r in scored_results if r.get("status") == "success"]
    errors = [r for r in scored_results if r.get("status") == "error"]

    # スコア分布
    scores = [r.get("scoring", {}).get("score", 0) for r in successful]

    # スキル分布
    all_skills: list[str] = []
    for r in successful:
        candidate_data = r.get("candidate_data", {})
        all_skills.extend(candidate_data.get("skills", []))

    skill_distribution = dict(Counter(all_skills).most_common(20))

    # 職種別集計
    position_breakdown: dict[str, dict] = defaultdict(lambda: {"count": 0, "avg_score": 0, "total_score": 0})
    for r in successful:
        pos_type = r.get("position_type", "general")
        score = r.get("scoring", {}).get("score", 0)
        position_breakdown[pos_type]["count"] += 1
        position_breakdown[pos_type]["total_score"] += score

    for pos_type, data in position_breakdown.items():
        if data["count"] > 0:
            data["avg_score"] = round(data["total_score"] / data["count"], 1)
        del data["total_score"]

    # スコアレンジ
    high_match = [r for r in successful if r.get("scoring", {}).get("score", 0) >= 80]
    medium_match = [r for r in successful if 50 <= r.get("scoring", {}).get("score", 0) < 80]
    low_match = [r for r in successful if r.get("scoring", {}).get("score", 0) < 50]

    return {
        "total_candidates": total,
        "processed": len(successful),
        "errors": len(errors),
        "score_distribution": {
            "high_match_80_plus": len(high_match),
            "medium_match_50_79": len(medium_match),
            "low_match_below_50": len(low_match),
            "average_score": (round(sum(scores) / len(scores), 1) if scores else 0.0),
        },
        "skill_distribution": skill_distribution,
        "position_breakdown": dict(position_breakdown),
    }


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """HR Document Screening Report Lambda

    Input event:
        - scored_results: Candidate Scorer 出力
        - discovery: Discovery Lambda 出力

    Returns:
        dict: report_key, summary
    """
    start_time = time.time()

    s3ap_output = S3ApHelper(os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ.get("S3_ACCESS_POINT", "")))
    sns_topic_arn = os.environ.get("SNS_TOPIC_ARN", "")
    pii_filter = PiiFilter()

    # SECURITY: Output bucket enforces SSE-KMS via default encryption policy (template.yaml).
    # For defense-in-depth, consider adding explicit ServerSideEncryption to put_object calls
    # when S3ApHelper supports it. See: shared/s3ap_helper.py

    scored_results = event.get("scored_results", [])
    discovery_info = event.get("discovery", {})

    logger.info("HR Report generation started: %d candidates", len(scored_results))

    # パイプラインサマリ計算
    pipeline_summary = compute_pipeline_summary(scored_results)

    total_processed = pipeline_summary["total_candidates"]
    success_count = pipeline_summary["processed"]
    error_count = pipeline_summary["errors"]

    processing_duration_ms = int((time.time() - start_time) * 1000)

    # JSON レポート (PII なし)
    report_json = {
        "report_id": context.aws_request_id,
        "use_case": "hr-document-screening",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "pii_mode": pii_filter.mode,
        "summary": {
            "total_processed": total_processed,
            "success_count": success_count,
            "error_count": error_count,
            "processing_duration_ms": processing_duration_ms,
        },
        "pipeline": pipeline_summary,
        "discovery_metadata": {
            "execution_id": discovery_info.get("execution_id"),
            "total_objects": discovery_info.get("total_objects", 0),
        },
    }

    # S3 出力 (暗号化)
    report_period = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    execution_id = context.aws_request_id
    report_key = f"reports/hr/{report_period}/{execution_id}.json"

    # Note: Output bucket enforces SSE-KMS encryption via bucket default encryption policy
    # (configured in template.yaml OutputBucket resource)
    s3ap_output.put_object(
        key=report_key,
        body=json.dumps(report_json, ensure_ascii=False, default=str),
        content_type="application/json",
    )

    logger.info(
        "HR Report generated: key=%s, candidates=%d, avg_score=%.1f",
        report_key,
        total_processed,
        pipeline_summary["score_distribution"]["average_score"],
    )

    # SNS 通知
    if sns_topic_arn and pipeline_summary["score_distribution"]["high_match_80_plus"] > 0:
        try:
            sns_client = boto3.client("sns")
            sns_client.publish(
                TopicArn=sns_topic_arn,
                Subject=f"[UC27] {pipeline_summary['score_distribution']['high_match_80_plus']} high-match candidates found",
                Message=(
                    f"HR Document Screening Report\n"
                    f"Period: {report_period}\n"
                    f"Total Candidates: {total_processed}\n"
                    f"High Match (80+): {pipeline_summary['score_distribution']['high_match_80_plus']}\n"
                    f"Report: {report_key}\n"
                ),
            )
        except Exception as e:
            logger.warning("SNS notification failed: %s", str(e))

    # EMF メトリクス
    metrics_emf = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="report")
    metrics_emf.set_dimension("UseCase", "hr-document-screening")
    metrics_emf.put_metric("ProcessingDuration", float(processing_duration_ms), "Milliseconds")
    metrics_emf.put_metric("SuccessCount", float(success_count), "Count")
    metrics_emf.put_metric("ErrorCount", float(error_count), "Count")
    metrics_emf.put_metric("ObjectsProcessed", float(total_processed), "Count")
    metrics_emf.flush()

    return {
        "report_key": report_key,
        "summary": report_json["summary"],
        "pipeline": pipeline_summary,
    }
