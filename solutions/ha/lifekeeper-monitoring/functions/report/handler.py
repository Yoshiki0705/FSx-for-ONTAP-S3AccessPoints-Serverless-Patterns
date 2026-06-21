"""HA LifeKeeper Monitoring — Report Lambda

ヘルスレポート生成とフェイルオーバーアラート送信を行う。
クラスタの健全性スコアに基づき、SNS 通知を送信する。

SIOS LifeKeeper クラスタの運用状態を以下の観点でレポート:
- クラスタヘルススコア (0-100)
- フェイルオーバーイベント履歴
- 根本原因分析結果
- 推奨アクション

Environment Variables:
    OUTPUT_BUCKET: レポート出力先 S3 バケット
    SNS_TOPIC_ARN: フェイルオーバーアラート SNS トピック
    FAILOVER_ALERT_SEVERITY: アラート最低重要度 (LOW/MEDIUM/HIGH/CRITICAL)
    CLUSTER_NAME: LifeKeeper クラスタ名
    DEMO_MODE: デモモード ("true"/"false")
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

s3_client = boto3.client("s3")
sns_client = boto3.client("sns")

# 重要度の順序
SEVERITY_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Report Lambda ハンドラー

    ヘルスレポートを生成し、必要に応じて SNS アラートを送信する。
    """
    output_bucket = os.environ.get("OUTPUT_BUCKET", "")
    sns_topic_arn = os.environ.get("SNS_TOPIC_ARN", "")
    alert_severity = os.environ.get("FAILOVER_ALERT_SEVERITY", "CRITICAL")
    cluster_name = os.environ.get("CLUSTER_NAME", "lifekeeper-cluster")

    health_score = event.get("health_score", {})
    failover_analyses = event.get("failover_analyses", [])
    root_cause_analysis = event.get("root_cause_analysis")
    log_summary = event.get("log_summary", {})
    processed_count = event.get("processed_count", 0)
    failover_count = event.get("failover_count", 0)

    score = health_score.get("score", 100)
    level = health_score.get("level", "HEALTHY")

    logger.info(
        "Report: cluster=%s, score=%d, level=%s, failovers=%d",
        cluster_name,
        score,
        level,
        failover_count,
    )

    # レポート生成
    report = _generate_report(
        cluster_name=cluster_name,
        health_score=health_score,
        failover_analyses=failover_analyses,
        root_cause_analysis=root_cause_analysis,
        log_summary=log_summary,
        processed_count=processed_count,
    )

    # レポートを S3 に保存
    report_key = ""
    if output_bucket:
        report_key = _save_report(report, output_bucket, cluster_name)

    # アラート判定・送信
    alert_sent = False
    if sns_topic_arn and _should_send_alert(level, alert_severity):
        alert_sent = _send_failover_alert(
            sns_topic_arn=sns_topic_arn,
            cluster_name=cluster_name,
            health_score=health_score,
            failover_count=failover_count,
            root_cause_analysis=root_cause_analysis,
        )

    return {
        "status": "completed",
        "cluster_name": cluster_name,
        "health_score": score,
        "health_level": level,
        "failover_count": failover_count,
        "alert_sent": alert_sent,
        "report_key": report_key,
        "timestamp": int(time.time()),
    }


def _generate_report(
    cluster_name: str,
    health_score: dict[str, Any],
    failover_analyses: list[dict[str, Any]],
    root_cause_analysis: dict[str, Any] | None,
    log_summary: dict[str, Any],
    processed_count: int,
) -> str:
    """Markdown 形式のヘルスレポートを生成する"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    score = health_score.get("score", 100)
    level = health_score.get("level", "HEALTHY")

    report_lines = [
        f"# LifeKeeper HA Cluster Health Report",
        f"",
        f"**Cluster**: {cluster_name}",
        f"**Generated**: {now}",
        f"**Health Score**: {score}/100 ({level})",
        f"**Files Analyzed**: {processed_count}",
        f"",
        f"---",
        f"",
        f"## Health Score Breakdown",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Score | {score}/100 |",
        f"| Level | {level} |",
        f"| Failover Events | {health_score.get('failover_count', 0)} |",
        f"| Total Deducted | -{health_score.get('deduction_breakdown', {}).get('total_deducted', 0)} |",
        f"",
    ]

    # ログサマリ
    if log_summary:
        report_lines.extend([
            f"## Log Analysis Summary",
            f"",
            f"| Category | Count |",
            f"|----------|-------|",
        ])
        for cat, count in log_summary.get("category_counts", {}).items():
            report_lines.append(f"| {cat} | {count} |")
        report_lines.append("")

        report_lines.extend([
            f"| Severity | Count |",
            f"|----------|-------|",
        ])
        for sev, count in log_summary.get("severity_counts", {}).items():
            report_lines.append(f"| {sev} | {count} |")
        report_lines.append("")

    # フェイルオーバー分析
    if failover_analyses:
        report_lines.extend([
            f"## Failover Event Analysis",
            f"",
        ])
        for i, analysis in enumerate(failover_analyses, 1):
            report_lines.extend([
                f"### Event {i}: {analysis.get('file', 'unknown')}",
                f"",
                f"- **Severity**: {analysis.get('severity', 'N/A')}",
                f"- **Indicators Found**: {analysis.get('indicator_count', 0)}",
                f"- **Last Modified**: {analysis.get('last_modified', 'N/A')}",
                f"",
            ])
            if analysis.get("state_transitions"):
                report_lines.append("**State Transitions**:")
                for trans in analysis["state_transitions"]:
                    report_lines.append(
                        f"  - `{trans['state']}`: {trans['description']}"
                    )
                report_lines.append("")

    # 根本原因分析
    if root_cause_analysis:
        report_lines.extend([
            f"## Root Cause Analysis (AI-powered)",
            f"",
            f"**Model**: {root_cause_analysis.get('model_id', 'N/A')}",
            f"",
            f"{root_cause_analysis.get('analysis', 'No analysis available.')}",
            f"",
        ])
        if root_cause_analysis.get("recommendations"):
            report_lines.append("### Recommendations")
            report_lines.append("")
            for rec in root_cause_analysis["recommendations"]:
                report_lines.append(f"- {rec}")
            report_lines.append("")

    # アーキテクチャ参考情報
    report_lines.extend([
        f"---",
        f"",
        f"## Architecture Reference",
        f"",
        f"This cluster uses **SIOS LifeKeeper** for application-level HA with",
        f"**Amazon FSx for NetApp ONTAP** Multi-AZ as shared storage.",
        f"",
        f"- LifeKeeper manages VIP failover, application start/stop, and recovery",
        f"- FSx for ONTAP provides NFS/iSCSI shared storage across AZs",
        f"- S3 Access Points enable non-disruptive log analytics without impacting HA operations",
        f"",
        f"### References",
        f"",
        f"- [SIOS LifeKeeper と Amazon FSx for NetApp ONTAP を活用した高可用性ソリューション (AWS JAPAN APN Blog)](https://aws.amazon.com/jp/blogs/psa/high-availability-solution-with-sios-lifekeeper-and-amazon-fsx-for-netapp-ontap/)",
        f"- [NetApp ONTAP と LifeKeeper による高可用性設計 (SIOS bcblog)](https://bcblog.sios.jp/netapp-ontap-lifekeeper-high-availability-design/)",
        f"- [Amazon FSx for NetApp ONTAP を LifeKeeper の共有ディスクとして利用 (SIOS bcblog)](https://bcblog.sios.jp/amazon-fsx-netapp-ontap-lifekeeper-shared-disk/)",
        f"- [SIOS Protection Suite for Linux on AWS](https://aws.amazon.com/solutions/partners/sios-protection-suite/)",
        f"- [SIOS LifeKeeper for Linux — AWS Partner Solution](https://aws-ia.github.io/cfn-ps-sios-protection-suite/)",
        f"- [Deploying highly available SAP systems using SIOS Protection Suite on AWS](https://aws.amazon.com/blogs/awsforsap/deploying-highly-available-sap-systems-using-sios-protection-suite-on-aws/)",
        f"- [SQL Server HA with Amazon FSx for NetApp ONTAP](https://aws.amazon.com/blogs/modernizing-with-aws/sql-server-high-availability-amazon-fsx-for-netapp-ontap/)",
        f"",
    ])

    return "\n".join(report_lines)


def _save_report(report: str, output_bucket: str, cluster_name: str) -> str:
    """レポートを S3 に保存する"""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    key = f"ha-monitoring/{cluster_name}/reports/{timestamp}-health-report.md"

    try:
        s3_client.put_object(
            Bucket=output_bucket,
            Key=key,
            Body=report.encode("utf-8"),
            ContentType="text/markdown; charset=utf-8",
        )
        logger.info("Report saved: s3://%s/%s", output_bucket, key)
        return key
    except Exception as e:
        logger.error("Failed to save report: %s", str(e))
        return ""


def _should_send_alert(current_level: str, threshold_severity: str) -> bool:
    """アラートを送信すべきか判定する"""
    current_order = SEVERITY_ORDER.get(current_level, 0)
    # level→severity マッピング: CRITICAL/DEGRADED → CRITICAL/HIGH
    level_to_severity = {
        "HEALTHY": "LOW",
        "WARNING": "MEDIUM",
        "DEGRADED": "HIGH",
        "CRITICAL": "CRITICAL",
    }
    effective_severity = level_to_severity.get(current_level, "LOW")
    effective_order = SEVERITY_ORDER.get(effective_severity, 0)
    threshold_order = SEVERITY_ORDER.get(threshold_severity, 3)

    return effective_order >= threshold_order


def _send_failover_alert(
    sns_topic_arn: str,
    cluster_name: str,
    health_score: dict[str, Any],
    failover_count: int,
    root_cause_analysis: dict[str, Any] | None,
) -> bool:
    """SNS 経由でフェイルオーバーアラートを送信する"""
    score = health_score.get("score", 0)
    level = health_score.get("level", "UNKNOWN")

    subject = f"[{level}] LifeKeeper Cluster Alert: {cluster_name} (Score: {score}/100)"

    message_lines = [
        f"LifeKeeper HA Cluster Failover Alert",
        f"=====================================",
        f"",
        f"Cluster: {cluster_name}",
        f"Health Score: {score}/100 ({level})",
        f"Failover Events Detected: {failover_count}",
        f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"",
    ]

    if root_cause_analysis and root_cause_analysis.get("analysis"):
        message_lines.extend([
            f"Root Cause Analysis:",
            f"-------------------",
            f"{root_cause_analysis['analysis'][:500]}",
            f"",
        ])

    message_lines.extend([
        f"Recommended Actions:",
        f"- Check LifeKeeper GUI or `lcdstatus` for current resource states",
        f"- Verify FSx for ONTAP NFS/iSCSI mount health on all cluster nodes",
        f"- Review communication paths: `lcdstatus -q -d node_name`",
        f"- Check ONTAP volume availability: ONTAP REST API or CLI",
        f"",
        f"This alert was generated by the HA LifeKeeper Monitoring pattern",
        f"using FSx for ONTAP S3 Access Points for non-disruptive log access.",
    ])

    message = "\n".join(message_lines)

    try:
        sns_client.publish(
            TopicArn=sns_topic_arn,
            Subject=subject[:100],  # SNS subject limit
            Message=message,
        )
        logger.info("Failover alert sent: %s", subject)
        return True
    except Exception as e:
        logger.error("Failed to send alert: %s", str(e))
        return False
