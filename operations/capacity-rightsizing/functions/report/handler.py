"""OPS1 Report Handler — レポート生成 + アラート

Analyze ステップの出力から JSON/HTML レポートを保存し、
CloudWatch カスタムメトリクスを publish し、
AutomationLevel >= 1 の場合は SNS アラートを発報する。

出力先 (OUTPUT_DESTINATION 環境変数):
    STANDARD_S3 (デフォルト):
        専用 S3 バケットに書き込み。追加設定不要。
    FSXN_S3AP:
        FSx for ONTAP ボリュームに S3 Access Point 経由で書き込み。
        NFS/SMB ユーザがファイルサーバー上でレポートを直接閲覧可能。
        考慮事項:
          - S3 AP alias を REPORT_BUCKET 環境変数として受け取る
          - Internet-origin AP → Lambda は VPC-external であること
          - VPC-origin AP → NAT Gateway or S3 Interface Endpoint が必要
          - PutObject 最大 5 GB (レポートは通常 < 1 MB)
          - ONTAP ファイルシステム ID の UNIX UID に書き込み権限が必要

カスタムメトリクス (CloudWatch namespace: FSxOps):
    - AvgVolumeUtilizationPercent (per fs_id)
    - RecommendationCount (per fs_id)
    - MonthlyCostDeltaUSD (per fs_id)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

CW_NAMESPACE = "FSxOps"


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Generate reports and publish metrics/alerts.

    Args:
        event: Output from Analyze step
        context: Lambda context

    Returns:
        dict: OpsReportOutput-compatible structure
    """
    report_bucket = os.environ.get("REPORT_BUCKET", "")
    report_format = os.environ.get("REPORT_FORMAT", "BOTH")
    automation_level = int(os.environ.get("AUTOMATION_LEVEL", "0"))
    alert_topic_arn = os.environ.get("ALERT_TOPIC_ARN", "")
    output_destination = os.environ.get("OUTPUT_DESTINATION", "STANDARD_S3")
    s3ap_alias = os.environ.get("S3_ACCESS_POINT_ALIAS", "")

    # Determine write target: S3 bucket name or S3 AP alias
    # boto3 put_object accepts both in the Bucket parameter transparently
    write_target = s3ap_alias if (output_destination == "FSXN_S3AP" and s3ap_alias) else report_bucket
    alert_topic_arn = os.environ.get("ALERT_TOPIC_ARN", "")

    analyses = event.get("analyses", [])
    total_recommendations = event.get("total_recommendations", 0)

    logger.info(
        "Generating reports for %d file systems (%d recommendations, dest=%s)",
        len(analyses),
        total_recommendations,
        output_destination,
    )

    s3_client = boto3.client("s3")
    cw_client = boto3.client("cloudwatch")
    now = datetime.now(UTC)
    date_prefix = now.strftime("%Y/%m/%d")

    results = []
    for analysis in analyses:
        fs_id = analysis.get("fs_id", "unknown")
        recommendations = analysis.get("recommendations", [])
        what_if = analysis.get("what_if_scenarios", [])
        summary = analysis.get("summary_stats", {})
        ai_summary = analysis.get("ai_summary")

        # Build report data
        report_data = {
            "fs_id": fs_id,
            "generated_at": now.isoformat(),
            "summary": summary,
            "recommendations": recommendations,
            "what_if_scenarios": what_if,
            "ai_summary": ai_summary,
        }

        # Save JSON report
        json_key = None
        if report_format in ("JSON", "BOTH"):
            json_key = f"reports/{date_prefix}/{fs_id}/capacity-report.json"
            _upload_json(s3_client, write_target, json_key, report_data)

        # Save HTML report
        html_key = None
        if report_format in ("HTML", "BOTH"):
            html_key = f"reports/{date_prefix}/{fs_id}/capacity-report.html"
            html_content = _generate_html_report(report_data)
            _upload_html(s3_client, write_target, html_key, html_content)

        # Publish CloudWatch custom metrics
        _publish_metrics(cw_client, fs_id, summary, recommendations)

        # Send alert if Level >= 1 and there are recommendations
        alert_required = automation_level >= 1 and len(recommendations) > 0
        if alert_required and alert_topic_arn:
            _send_alert(alert_topic_arn, fs_id, recommendations, ai_summary)

        results.append({
            "fs_id": fs_id,
            "report_s3_key": json_key,
            "html_report_s3_key": html_key,
            "ai_summary": ai_summary,
            "recommendation_count": len(recommendations),
            "alert_required": alert_required,
            "reported_at": now.isoformat(),
        })

    return {
        "reports": results,
        "total_recommendations": total_recommendations,
        "reported_at": now.isoformat(),
    }


def _upload_json(
    s3_client: Any, bucket: str, key: str, data: dict
) -> None:
    """JSON レポートを S3 (バケット or S3 AP alias) にアップロードする.

    Note: bucket パラメータは S3 バケット名または S3 Access Point alias の
    どちらでも動作する。boto3 の put_object は Bucket パラメータに
    S3 AP alias を渡すと自動的に AP 経由でアクセスする。
    """
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(data, ensure_ascii=False, indent=2),
        ContentType="application/json",
    )
    logger.info("JSON report uploaded: s3://%s/%s", bucket, key)


def _upload_html(
    s3_client: Any, bucket: str, key: str, html: str
) -> None:
    """HTML レポートを S3 (バケット or S3 AP alias) にアップロードする."""
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=html.encode("utf-8"),
        ContentType="text/html; charset=utf-8",
    )
    logger.info("HTML report uploaded: s3://%s/%s", bucket, key)


def _generate_html_report(report_data: dict) -> str:
    """HTML レポートを生成する."""
    fs_id = report_data["fs_id"]
    summary = report_data.get("summary", {})
    recommendations = report_data.get("recommendations", [])
    what_if = report_data.get("what_if_scenarios", [])
    ai_summary = report_data.get("ai_summary", "")
    generated_at = report_data.get("generated_at", "")

    # Build recommendations HTML
    rec_rows = ""
    for rec in recommendations:
        color = "#dc3545" if "upsize" in rec.get("recommendation_type", "") or "upgrade" in rec.get("recommendation_type", "") else "#28a745"
        rec_rows += f"""
        <tr>
            <td><span style="color:{color}; font-weight:bold;">{rec.get('recommendation_type', '')}</span></td>
            <td>{rec.get('target', '')}</td>
            <td>{rec.get('current_value', '')}</td>
            <td>{rec.get('recommended_value', '')}</td>
            <td>${rec.get('monthly_cost_delta_usd', 0):.2f}/月</td>
        </tr>"""

    # Build What-If HTML
    whatif_rows = ""
    for scenario in what_if:
        delta = scenario.get("monthly_delta_usd", 0)
        color = "#dc3545" if delta > 0 else "#28a745"
        whatif_rows += f"""
        <tr>
            <td>{scenario.get('scenario_name', '')}</td>
            <td>${scenario.get('current_monthly_cost_usd', 0):.2f}</td>
            <td>${scenario.get('projected_monthly_cost_usd', 0):.2f}</td>
            <td style="color:{color}; font-weight:bold;">${delta:+.2f}</td>
        </tr>"""

    ai_section = ""
    if ai_summary:
        ai_section = f"""
        <div class="section">
            <h2>AI 推奨サマリ (Bedrock Nova)</h2>
            <div class="ai-summary">{ai_summary}</div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>OPS1 Capacity Rightsizing Report - {fs_id}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 2rem; background: #f8f9fa; }}
        .header {{ background: #232f3e; color: white; padding: 1.5rem; border-radius: 8px; margin-bottom: 2rem; }}
        .section {{ background: white; padding: 1.5rem; border-radius: 8px; margin-bottom: 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
        th, td {{ padding: 0.75rem; text-align: left; border-bottom: 1px solid #dee2e6; }}
        th {{ background: #f1f3f5; font-weight: 600; }}
        .stat-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; }}
        .stat-card {{ background: #e3f2fd; padding: 1rem; border-radius: 8px; text-align: center; }}
        .stat-value {{ font-size: 2rem; font-weight: bold; color: #1565c0; }}
        .stat-label {{ color: #666; margin-top: 0.25rem; }}
        .ai-summary {{ background: #fff3e0; padding: 1rem; border-radius: 8px; white-space: pre-wrap; }}
        .footer {{ color: #666; font-size: 0.875rem; margin-top: 2rem; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>OPS1: Capacity Rightsizing Report</h1>
        <p>File System: {fs_id} | Generated: {generated_at}</p>
    </div>

    <div class="section">
        <h2>サマリ</h2>
        <div class="stat-grid">
            <div class="stat-card">
                <div class="stat-value">{summary.get('total_volumes', 0)}</div>
                <div class="stat-label">Total Volumes</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{summary.get('volumes_above_threshold', 0)}</div>
                <div class="stat-label">Above Threshold</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{summary.get('avg_volume_utilization_percent', 0):.1f}%</div>
                <div class="stat-label">Avg Utilization</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{summary.get('recommendation_count', 0)}</div>
                <div class="stat-label">Recommendations</div>
            </div>
        </div>
    </div>

    {ai_section}

    <div class="section">
        <h2>推奨アクション ({len(recommendations)} 件)</h2>
        <table>
            <thead><tr><th>種別</th><th>対象</th><th>現在</th><th>推奨</th><th>コスト影響</th></tr></thead>
            <tbody>{rec_rows if rec_rows else '<tr><td colspan="5">推奨なし</td></tr>'}</tbody>
        </table>
    </div>

    <div class="section">
        <h2>What-If シミュレーション (スループットティア変更)</h2>
        <table>
            <thead><tr><th>シナリオ</th><th>現在コスト</th><th>変更後コスト</th><th>月額差分</th></tr></thead>
            <tbody>{whatif_rows if whatif_rows else '<tr><td colspan="4">シナリオなし</td></tr>'}</tbody>
        </table>
    </div>

    <div class="footer">
        <p>Generated by FSx for ONTAP Operations Pattern (OPS1: capacity-rightsizing)</p>
        <p>Governance Note: This report provides recommendations only. Data retention requirements
        (FISC/HIPAA/NARA) are not affected by capacity changes.</p>
    </div>
</body>
</html>"""


def _publish_metrics(
    cw_client: Any,
    fs_id: str,
    summary: dict,
    recommendations: list[dict],
) -> None:
    """CloudWatch カスタムメトリクスを publish する."""
    metric_data = [
        {
            "MetricName": "AvgVolumeUtilizationPercent",
            "Value": summary.get("avg_volume_utilization_percent", 0),
            "Unit": "Percent",
            "Dimensions": [{"Name": "FileSystemId", "Value": fs_id}],
        },
        {
            "MetricName": "RecommendationCount",
            "Value": len(recommendations),
            "Unit": "Count",
            "Dimensions": [{"Name": "FileSystemId", "Value": fs_id}],
        },
        {
            "MetricName": "MonthlyCostDeltaUSD",
            "Value": summary.get("total_monthly_cost_delta_usd", 0),
            "Unit": "None",
            "Dimensions": [{"Name": "FileSystemId", "Value": fs_id}],
        },
    ]

    # Throughput utilization (if available)
    throughput_util = summary.get("throughput_utilization_percent")
    if throughput_util is not None:
        metric_data.append({
            "MetricName": "ThroughputUtilizationPercent",
            "Value": throughput_util,
            "Unit": "Percent",
            "Dimensions": [{"Name": "FileSystemId", "Value": fs_id}],
        })

    cw_client.put_metric_data(Namespace=CW_NAMESPACE, MetricData=metric_data)
    logger.info("Published %d custom metrics for %s", len(metric_data), fs_id)


def _send_alert(
    topic_arn: str,
    fs_id: str,
    recommendations: list[dict],
    ai_summary: str | None,
) -> None:
    """SNS アラートを送信する."""
    sns_client = boto3.client("sns")

    # Build alert message
    rec_summary = "\n".join(
        f"  - [{r['recommendation_type']}] {r['target']}: {r['reason']}"
        for r in recommendations[:5]
    )

    message = (
        f"[OPS1] FSx for ONTAP Capacity Alert\n"
        f"{'=' * 50}\n"
        f"File System: {fs_id}\n"
        f"Recommendations: {len(recommendations)}\n\n"
        f"Top recommendations:\n{rec_summary}\n"
    )

    if ai_summary:
        message += f"\nAI Summary:\n{ai_summary}\n"

    message += (
        "\nFull report available in S3 (report bucket).\n"
        "AutomationLevel=2 required for auto-execution.\n"
    )

    sns_client.publish(
        TopicArn=topic_arn,
        Subject=f"[OPS1] Capacity Alert - {fs_id} ({len(recommendations)} recommendations)",
        Message=message,
    )
    logger.info("Alert sent to %s for %s", topic_arn, fs_id)
