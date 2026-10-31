"""Report Lambda — Step Functions × AgentCore Gateway pattern.

Map 処理の結果を集計し、サマリーレポートを生成して SNS 通知を送る。
ワークフローの最終 Task。エージェントは DescribeExecution（includedData=ALL_DATA）で
この戻り値を受け取り、処理結果を報告する。

出力には shared.data_classification.get_classification() 由来の data_classification
ラベルを付ける（この リポジトリの出力データ規約）。

Environment Variables:
    SNS_TOPIC_ARN: SNS トピック ARN（任意）
    DATA_CLASSIFICATION: 出力データの分類ラベル（shared が解釈。デフォルト INTERNAL）
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import boto3

from shared.data_classification import get_classification
from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_sns = boto3.client("sns")


@lambda_error_handler
def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Report Lambda ハンドラー。

    Map の結果配列（または NoFiles / ReportError 経路の入力）を集計する。

    Args:
        event: ワークフローの状態。処理結果は `processed`（Map の ResultPath）か
            `objects` に入る。ReportError 経路では `status=ERROR` と `error` が入る。
        context: Lambda コンテキスト。

    Returns:
        dict: {status, report, data_classification}。
    """
    error_mode = event.get("status") == "ERROR"
    results = event.get("processed") or []
    if not isinstance(results, list):
        results = []

    total = len(results)
    succeeded = sum(1 for r in results if r.get("status") == "completed")
    failed = total - succeeded
    review_required = sum(1 for r in results if r.get("human_review", {}).get("requires_review"))

    category_counts: dict[str, int] = {}
    for r in results:
        cat = r.get("category", "unknown")
        category_counts[cat] = category_counts.get(cat, 0) + 1

    report = {
        "report_type": "stepfunctions_agentcore_summary",
        "timestamp": int(time.time()),
        "summary": {
            "total_files": total,
            "succeeded": succeeded,
            "failed": failed,
            "human_review_required": review_required,
            "success_rate_pct": round(succeeded / total * 100, 1) if total else 0.0,
        },
        "category_breakdown": category_counts,
        "data_classification": get_classification().label,
    }

    if error_mode:
        report["error"] = event.get("error")

    metrics = EmfMetrics(service="stepfunctions-agentcore-tools")
    metrics.put_metric("WorkflowReports", 1, "Count")
    metrics.put_metric("FilesSucceeded", succeeded, "Count")
    metrics.flush()

    _notify(report, succeeded, total)

    logger.info("Report: %d/%d succeeded, review_required=%d", succeeded, total, review_required)

    return {
        "status": "error" if error_mode else "completed",
        "report": report,
        "data_classification": report["data_classification"],
    }


def _notify(report: dict[str, Any], succeeded: int, total: int) -> None:
    """SNS にサマリーを通知する（トピック未設定ならスキップ）。

    Args:
        report: 集計済みレポート。
        succeeded: 成功件数。
        total: 総件数。
    """
    topic_arn = os.environ.get("SNS_TOPIC_ARN", "")
    if not topic_arn:
        return

    subject = f"Workflow summary: {succeeded}/{total} succeeded"
    review = report["summary"]["human_review_required"]
    if review:
        subject = f"[REVIEW {review}] {subject}"

    lines = [
        "Step Functions × AgentCore workflow summary",
        "=" * 40,
        f"Total: {total}",
        f"Succeeded: {succeeded}",
        f"Failed: {report['summary']['failed']}",
        f"Human review required: {review}",
        f"Data classification: {report['data_classification']}",
    ]
    try:
        _sns.publish(TopicArn=topic_arn, Subject=subject[:100], Message="\n".join(lines))
    except Exception as e:  # noqa: BLE001 — 通知失敗はワークフローを失敗させない
        logger.warning("SNS publish failed: %s", str(e))
