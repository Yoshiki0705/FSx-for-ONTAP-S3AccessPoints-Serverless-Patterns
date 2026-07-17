"""OPS4 Report Handler — 監査レポート生成 + アラート

Analyze の出力から JSON/HTML 監査レポートを S3 に保存し、
CloudWatch カスタムメトリクスを publish し、アラートを発報する。

カスタムメトリクス (CloudWatch namespace: FSxOps):
    - ExpiredSnapshotCount (per fs_id)
    - ExpiredSnapshotSizeGB (per fs_id)
    - PolicyDriftVolumeCount (per fs_id)
    - RetentionCompliancePercent (per fs_id)
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
    """Generate snapshot audit reports and publish metrics/alerts."""
    report_bucket = os.environ.get("REPORT_BUCKET", "")
    report_format = os.environ.get("REPORT_FORMAT", "BOTH")
    automation_level = int(os.environ.get("AUTOMATION_LEVEL", "0"))
    alert_topic_arn = os.environ.get("ALERT_TOPIC_ARN", "")

    analyses = event.get("analyses", [])
    total_expired = event.get("total_expired_snapshots", 0)

    logger.info(
        "Generating snapshot audit reports for %d file systems (%d expired)",
        len(analyses), total_expired,
    )

    s3_client = boto3.client("s3")
    cw_client = boto3.client("cloudwatch")
    now = datetime.now(UTC)
    date_prefix = now.strftime("%Y/%m/%d")

    results = []
    for analysis in analyses:
        fs_id = analysis.get("fs_id", "unknown")
        volume_audits = analysis.get("volume_audits", [])
        summary = analysis.get("summary", {})
        ai_summary = analysis.get("ai_summary")

        # Build report
        report_data = {
            "fs_id": fs_id,
            "generated_at": now.isoformat(),
            "summary": summary,
            "volume_audits": volume_audits,
            "ai_summary": ai_summary,
        }

        # Save JSON report
        json_key = None
        if report_format in ("JSON", "BOTH"):
            json_key = f"reports/{date_prefix}/{fs_id}/snapshot-audit.json"
            s3_client.put_object(
                Bucket=report_bucket,
                Key=json_key,
                Body=json.dumps(report_data, ensure_ascii=False, indent=2),
                ContentType="application/json",
            )
            logger.info("JSON report uploaded: s3://%s/%s", report_bucket, json_key)

        # Save HTML report
        html_key = None
        if report_format in ("HTML", "BOTH"):
            html_key = f"reports/{date_prefix}/{fs_id}/snapshot-audit.html"
            html_content = _generate_html_report(report_data)
            s3_client.put_object(
                Bucket=report_bucket,
                Key=html_key,
                Body=html_content.encode("utf-8"),
                ContentType="text/html; charset=utf-8",
            )
            logger.info("HTML report uploaded: s3://%s/%s", report_bucket, html_key)

        # Publish CloudWatch metrics
        _publish_metrics(cw_client, fs_id, summary, volume_audits)

        # Alert
        alert_required = (
            automation_level >= 1
            and (summary.get("total_expired_snapshots", 0) > 0
                 or summary.get("volumes_with_drift", 0) > 0)
        )
        if alert_required and alert_topic_arn:
            _send_alert(alert_topic_arn, fs_id, summary, volume_audits, ai_summary)

        results.append({
            "fs_id": fs_id,
            "report_s3_key": json_key,
            "html_report_s3_key": html_key,
            "ai_summary": ai_summary,
            "expired_count": summary.get("total_expired_snapshots", 0),
            "drift_count": summary.get("volumes_with_drift", 0),
            "alert_required": alert_required,
            "reported_at": now.isoformat(),
        })

    return {
        "reports": results,
        "total_expired_snapshots": total_expired,
        "reported_at": now.isoformat(),
    }


def _publish_metrics(
    cw_client: Any,
    fs_id: str,
    summary: dict,
    volume_audits: list[dict],
) -> None:
    """CloudWatch カスタムメトリクスを publish."""
    total_snapshots = summary.get("total_snapshots_scanned", 0)
    total_expired = summary.get("total_expired_snapshots", 0)
    compliance_pct = (
        ((total_snapshots - total_expired) / total_snapshots * 100)
        if total_snapshots > 0
        else 100.0
    )

    metric_data = [
        {
            "MetricName": "ExpiredSnapshotCount",
            "Value": total_expired,
            "Unit": "Count",
            "Dimensions": [{"Name": "FileSystemId", "Value": fs_id}],
        },
        {
            "MetricName": "ExpiredSnapshotSizeGB",
            "Value": summary.get("total_expired_gb", 0),
            "Unit": "Gigabytes",
            "Dimensions": [{"Name": "FileSystemId", "Value": fs_id}],
        },
        {
            "MetricName": "PolicyDriftVolumeCount",
            "Value": summary.get("volumes_with_drift", 0),
            "Unit": "Count",
            "Dimensions": [{"Name": "FileSystemId", "Value": fs_id}],
        },
        {
            "MetricName": "RetentionCompliancePercent",
            "Value": round(compliance_pct, 2),
            "Unit": "Percent",
            "Dimensions": [{"Name": "FileSystemId", "Value": fs_id}],
        },
    ]

    cw_client.put_metric_data(Namespace=CW_NAMESPACE, MetricData=metric_data)
    logger.info("Published %d snapshot metrics for %s", len(metric_data), fs_id)


def _send_alert(
    topic_arn: str,
    fs_id: str,
    summary: dict,
    volume_audits: list[dict],
    ai_summary: str | None,
) -> None:
    """SNS アラートを送信."""
    sns_client = boto3.client("sns")

    expired_details = []
    for audit in volume_audits:
        if audit.get("expired_count", 0) > 0:
            expired_details.append(
                f"  - {audit['volume_name']}: {audit['expired_count']} expired "
                f"(oldest: {audit['oldest_snapshot_age_days']} days)"
            )

    drift_details = []
    for audit in volume_audits:
        if audit.get("policy_drift_detected"):
            drift_details.append(
                f"  - {audit['volume_name']}: {audit['policy_drift_details']}"
            )

    message = (
        f"[OPS4] Snapshot Lifecycle Alert\n"
        f"{'=' * 50}\n"
        f"File System: {fs_id}\n"
        f"Policy: {summary.get('retention_policy', 'CUSTOM')}\n"
        f"Max Retention: {summary.get('effective_max_retention_days', 0)} days\n\n"
        f"Expired Snapshots: {summary.get('total_expired_snapshots', 0)} "
        f"({summary.get('total_expired_gb', 0):.1f} GB)\n"
    )

    if expired_details:
        message += "\nExpired by volume:\n" + "\n".join(expired_details[:10]) + "\n"

    if drift_details:
        message += f"\nPolicy Drift Detected ({summary.get('volumes_with_drift', 0)} volumes):\n"
        message += "\n".join(drift_details[:5]) + "\n"

    if ai_summary:
        message += f"\nAI Summary:\n{ai_summary}\n"

    message += (
        "\nAction required: Review expired snapshots and approve cleanup.\n"
        "AutomationLevel=2 enables Human Review based deletion.\n"
    )

    sns_client.publish(
        TopicArn=topic_arn,
        Subject=f"[OPS4] Snapshot Alert - {fs_id} ({summary.get('total_expired_snapshots', 0)} expired)",
        Message=message,
    )
    logger.info("Snapshot alert sent for %s", fs_id)


def _generate_html_report(report_data: dict) -> str:
    """HTML 監査レポートを生成."""
    fs_id = report_data["fs_id"]
    summary = report_data.get("summary", {})
    volume_audits = report_data.get("volume_audits", [])
    ai_summary = report_data.get("ai_summary", "")
    generated_at = report_data.get("generated_at", "")

    # Volume audit rows
    audit_rows = ""
    for audit in volume_audits:
        compliance_icon = "✅" if audit["retention_compliant"] else "❌"
        drift_icon = "⚠️" if audit["policy_drift_detected"] else "—"
        audit_rows += f"""
        <tr>
            <td>{audit['volume_name']}</td>
            <td>{audit['total_snapshots']}</td>
            <td>{audit['expired_count']}</td>
            <td>{audit['oldest_snapshot_age_days']} days</td>
            <td>{compliance_icon}</td>
            <td>{drift_icon}</td>
        </tr>"""

    ai_section = ""
    if ai_summary:
        ai_section = f"""
        <div class="section">
            <h2>AI 推奨サマリ</h2>
            <div class="ai-summary">{ai_summary}</div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>OPS4 Snapshot Audit - {fs_id}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 2rem; background: #f8f9fa; }}
        .header {{ background: #232f3e; color: white; padding: 1.5rem; border-radius: 8px; margin-bottom: 2rem; }}
        .section {{ background: white; padding: 1.5rem; border-radius: 8px; margin-bottom: 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
        th, td {{ padding: 0.75rem; text-align: left; border-bottom: 1px solid #dee2e6; }}
        th {{ background: #f1f3f5; font-weight: 600; }}
        .stat-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; }}
        .stat-card {{ background: #e3f2fd; padding: 1rem; border-radius: 8px; text-align: center; }}
        .stat-card.warning {{ background: #fff3e0; }}
        .stat-card.danger {{ background: #ffebee; }}
        .stat-value {{ font-size: 1.8rem; font-weight: bold; color: #1565c0; }}
        .stat-card.warning .stat-value {{ color: #e65100; }}
        .stat-card.danger .stat-value {{ color: #c62828; }}
        .stat-label {{ color: #666; margin-top: 0.25rem; font-size: 0.875rem; }}
        .ai-summary {{ background: #fff3e0; padding: 1rem; border-radius: 8px; white-space: pre-wrap; }}
        .governance {{ background: #e8f5e9; padding: 1rem; border-radius: 8px; border-left: 4px solid #4caf50; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>OPS4: Snapshot Lifecycle Audit</h1>
        <p>File System: {fs_id} | Generated: {generated_at}</p>
        <p>Policy: {summary.get('retention_policy', 'CUSTOM')} | Max Retention: {summary.get('effective_max_retention_days', 0)} days</p>
    </div>

    <div class="section">
        <h2>サマリ</h2>
        <div class="stat-grid">
            <div class="stat-card">
                <div class="stat-value">{summary.get('total_snapshots_scanned', 0)}</div>
                <div class="stat-label">Total Snapshots</div>
            </div>
            <div class="stat-card {'danger' if summary.get('total_expired_snapshots', 0) > 0 else ''}">
                <div class="stat-value">{summary.get('total_expired_snapshots', 0)}</div>
                <div class="stat-label">Expired</div>
            </div>
            <div class="stat-card {'warning' if summary.get('total_expired_gb', 0) > 10 else ''}">
                <div class="stat-value">{summary.get('total_expired_gb', 0):.1f} GB</div>
                <div class="stat-label">Expired Size</div>
            </div>
            <div class="stat-card {'warning' if summary.get('volumes_with_drift', 0) > 0 else ''}">
                <div class="stat-value">{summary.get('volumes_with_drift', 0)}</div>
                <div class="stat-label">Policy Drift</div>
            </div>
        </div>
    </div>

    {ai_section}

    <div class="section">
        <h2>ボリューム別監査結果</h2>
        <table>
            <thead><tr><th>Volume</th><th>Total</th><th>Expired</th><th>Oldest</th><th>Compliant</th><th>Drift</th></tr></thead>
            <tbody>{audit_rows if audit_rows else '<tr><td colspan="6">No volumes scanned</td></tr>'}</tbody>
        </table>
    </div>

    <div class="section">
        <div class="governance">
            <strong>Governance Note:</strong> This report identifies snapshots that exceed the configured
            retention period. Deletion requires Human Review (AutomationLevel=2+).
            Snapshots within MinRetentionDays ({summary.get('min_retention_days', 7)} days) are never
            recommended for deletion. Regulatory requirements (FISC/HIPAA/NARA) take precedence
            over cost optimization.
        </div>
    </div>
</body>
</html>"""
