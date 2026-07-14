"""OPS3 Report Handler — ティアリング最適化レポート + アラート."""

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
    """Generate tiering optimization report."""
    report_bucket = os.environ.get("REPORT_BUCKET", "")
    report_format = os.environ.get("REPORT_FORMAT", "BOTH")
    automation_level = int(os.environ.get("AUTOMATION_LEVEL", "0"))
    alert_topic_arn = os.environ.get("ALERT_TOPIC_ARN", "")

    analyses = event.get("analyses", [])
    total_recs = event.get("total_recommendations", 0)

    s3_client = boto3.client("s3")
    cw_client = boto3.client("cloudwatch")
    now = datetime.now(UTC)
    date_prefix = now.strftime("%Y/%m/%d")

    results = []
    for analysis in analyses:
        fs_id = analysis.get("fs_id", "unknown")
        recommendations = analysis.get("recommendations", [])
        summary = analysis.get("summary", {})
        ai_summary = analysis.get("ai_summary")

        report_data = {
            "fs_id": fs_id,
            "generated_at": now.isoformat(),
            "summary": summary,
            "recommendations": recommendations,
            "ai_summary": ai_summary,
        }

        json_key = None
        if report_format in ("JSON", "BOTH"):
            json_key = f"reports/{date_prefix}/{fs_id}/tiering-report.json"
            s3_client.put_object(Bucket=report_bucket, Key=json_key, Body=json.dumps(report_data, ensure_ascii=False, indent=2), ContentType="application/json")

        html_key = None
        if report_format in ("HTML", "BOTH"):
            html_key = f"reports/{date_prefix}/{fs_id}/tiering-report.html"
            s3_client.put_object(Bucket=report_bucket, Key=html_key, Body=_generate_html(report_data).encode("utf-8"), ContentType="text/html; charset=utf-8")

        _publish_metrics(cw_client, fs_id, summary)

        alert_required = automation_level >= 1 and len(recommendations) > 0
        if alert_required and alert_topic_arn:
            _send_alert(alert_topic_arn, fs_id, summary, recommendations, ai_summary)

        results.append({
            "fs_id": fs_id,
            "report_s3_key": json_key,
            "html_report_s3_key": html_key,
            "recommendation_count": len(recommendations),
            "potential_savings_usd": summary.get("total_potential_savings_usd", 0),
            "alert_required": alert_required,
            "reported_at": now.isoformat(),
        })

    return {"reports": results, "total_recommendations": total_recs, "reported_at": now.isoformat()}


def _publish_metrics(cw_client: Any, fs_id: str, summary: dict) -> None:
    cw_client.put_metric_data(
        Namespace=CW_NAMESPACE,
        MetricData=[
            {"MetricName": "TieringRecommendationCount", "Value": summary.get("volumes_with_recommendations", 0), "Unit": "Count", "Dimensions": [{"Name": "FileSystemId", "Value": fs_id}]},
            {"MetricName": "TieringPotentialSavingsUSD", "Value": summary.get("total_potential_savings_usd", 0), "Unit": "None", "Dimensions": [{"Name": "FileSystemId", "Value": fs_id}]},
        ],
    )


def _send_alert(topic_arn: str, fs_id: str, summary: dict, recs: list[dict], ai_summary: str | None) -> None:
    sns_client = boto3.client("sns")
    rec_lines = "\n".join(f"  - {r['volume_name']}: {r['current_policy']}→{r['recommended_policy']} (${r['estimated_monthly_savings_usd']:.2f}/mo)" for r in recs[:5])
    message = (
        f"[OPS3] Tiering Optimization Alert\n{'=' * 50}\n"
        f"File System: {fs_id}\n"
        f"Recommendations: {len(recs)}\n"
        f"Potential Savings: ${summary.get('total_potential_savings_usd', 0):.2f}/month\n\n"
        f"{rec_lines}\n"
    )
    if ai_summary:
        message += f"\nAI Summary:\n{ai_summary}\n"
    sns_client.publish(TopicArn=topic_arn, Subject=f"[OPS3] Tiering Alert - {fs_id}", Message=message)


def _generate_html(report_data: dict) -> str:
    fs_id = report_data["fs_id"]
    summary = report_data.get("summary", {})
    recs = report_data.get("recommendations", [])
    ai_summary = report_data.get("ai_summary", "")

    rec_rows = "".join(
        f"<tr><td>{r['volume_name']}</td><td>{r['current_policy']}</td>"
        f"<td>{r['recommended_policy']}</td><td>{r['current_cooling_days']}→{r['recommended_cooling_days']}</td>"
        f"<td>${r['estimated_monthly_savings_usd']:.2f}</td></tr>"
        for r in recs
    )

    ai_section = f'<div class="ai-summary"><h3>AI 推奨</h3><pre>{ai_summary}</pre></div>' if ai_summary else ""

    return f"""<!DOCTYPE html><html lang="ja"><head><meta charset="UTF-8">
<title>OPS3 Tiering Report - {fs_id}</title>
<style>body{{font-family:sans-serif;margin:2rem;background:#f8f9fa}}.header{{background:#232f3e;color:white;padding:1.5rem;border-radius:8px;margin-bottom:2rem}}
.section{{background:white;padding:1.5rem;border-radius:8px;margin-bottom:1.5rem;box-shadow:0 1px 3px rgba(0,0,0,.1)}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:.75rem;text-align:left;border-bottom:1px solid #dee2e6}}th{{background:#f1f3f5}}
.ai-summary{{background:#fff3e0;padding:1rem;border-radius:8px;margin-top:1rem}}pre{{white-space:pre-wrap}}</style></head>
<body><div class="header"><h1>OPS3: Tiering Optimizer Report</h1><p>{fs_id} | {report_data.get('generated_at','')}</p></div>
<div class="section"><h2>サマリ</h2><p>対象ボリューム: {summary.get('total_volumes',0)} | 推奨数: {summary.get('volumes_with_recommendations',0)} | 月額削減見込: ${summary.get('total_potential_savings_usd',0):.2f}</p>
<p>ポリシー分布: {json.dumps(summary.get('policy_distribution',{}))}</p></div>
<div class="section"><h2>推奨アクション</h2><table><thead><tr><th>Volume</th><th>現在</th><th>推奨</th><th>Cooling</th><th>月額削減</th></tr></thead><tbody>{rec_rows or '<tr><td colspan="5">推奨なし</td></tr>'}</tbody></table>{ai_section}</div>
<div class="section"><p><strong>参考</strong>: SSD ${0.125}/GB/月, Capacity Pool ${0.021}/GB/月. ティアリングポリシー変更は <a href="https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/volume-data-tiering.html">AWS Docs</a> 参照.</p></div>
</body></html>"""
