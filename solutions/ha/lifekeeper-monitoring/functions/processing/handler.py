"""HA LifeKeeper Monitoring — Processing Lambda

LifeKeeper ログを解析し、Bedrock を使ってフェイルオーバーの根本原因分析、
ヘルススコアリング、予兆検知を行う。

SIOS LifeKeeper ログの主要解析対象:
- フェイルオーバーイベント: resource switchover/takeover/recovery
- ヘルスチェック結果: heartbeat timeout, communication path failure
- リソース状態遷移: ISP→OSU→OSF→ISP (In Service Primary → Out of Service)
- Recovery Kit 固有イベント: SAP/Oracle/NFS/IP リソース状態

Environment Variables:
    S3_ACCESS_POINT_ALIAS: S3 AP Alias (入力読み取り用)
    OUTPUT_BUCKET: 出力先 S3 バケット
    BEDROCK_MODEL_ID: Bedrock モデル ID
    CLUSTER_NAME: LifeKeeper クラスタ名
    FAILOVER_ALERT_SEVERITY: アラート最低重要度
    DEMO_MODE: デモモード ("true"/"false")
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

s3_client = boto3.client("s3")
bedrock_client = boto3.client("bedrock-runtime")

# LifeKeeper ログのパース用キーワード
FAILOVER_INDICATORS = [
    "FAILOVER",
    "SWITCHOVER",
    "TAKEOVER",
    "restore",
    "recovery action",
    "resource fault",
    "local recovery",
    "remove from service",
    "bring in service",
    "comm path down",
    "heartbeat lost",
]

RESOURCE_STATE_TRANSITIONS = {
    "ISP": "In Service Primary",
    "ISS": "In Service Secondary",
    "OSU": "Out of Service Unknown",
    "OSF": "Out of Service Failed",
    "ISP→OSF": "Primary failure detected",
    "ISS→ISP": "Failover completed (secondary promoted)",
    "OSF→ISP": "Recovery completed",
}

# ヘルススコア基準
HEALTH_SCORE_DEDUCTIONS = {
    "failover_event": 30,
    "heartbeat_timeout": 20,
    "comm_path_failure": 15,
    "resource_fault": 25,
    "recovery_kit_error": 10,
    "config_change": 5,
}

MAX_CONTENT_SIZE = 100_000  # 100KB per file for Bedrock context


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Processing Lambda ハンドラー

    LifeKeeper ログを読み取り、AI による根本原因分析を実行する。
    """
    s3ap_alias = os.environ.get("S3_ACCESS_POINT_ALIAS", "")
    output_bucket = os.environ.get("OUTPUT_BUCKET", "")
    model_id = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-pro-v1:0")
    cluster_name = os.environ.get("CLUSTER_NAME", "lifekeeper-cluster")
    demo_mode = os.environ.get("DEMO_MODE", "false").lower() == "true"

    objects = event.get("objects", [])
    failover_events = event.get("failover_events", [])

    logger.info(
        "Processing: %d objects, %d failover events, cluster=%s",
        len(objects),
        len(failover_events),
        cluster_name,
    )

    # フェイルオーバーイベントの詳細分析
    failover_analyses = []
    if failover_events:
        for fe in failover_events[:5]:  # 最大5件の直近イベントを分析
            analysis = _analyze_failover_event(fe, s3ap_alias, model_id, demo_mode)
            failover_analyses.append(analysis)

    # ヘルススコア算出
    health_score = _calculate_health_score(objects, failover_events)

    # ログサマリ生成
    log_summary = _generate_log_summary(objects)

    # Bedrock による総合分析（フェイルオーバーイベントがある場合）
    root_cause_analysis = None
    if failover_analyses:
        root_cause_analysis = _perform_root_cause_analysis(
            failover_analyses, health_score, cluster_name, model_id, demo_mode
        )

    # 結果を S3 に保存
    result = {
        "status": "completed",
        "cluster_name": cluster_name,
        "health_score": health_score,
        "failover_analyses": failover_analyses,
        "root_cause_analysis": root_cause_analysis,
        "log_summary": log_summary,
        "processed_count": len(objects),
        "failover_count": len(failover_events),
        "timestamp": int(time.time()),
    }

    if output_bucket:
        _save_result(result, output_bucket, cluster_name)

    return result


def _analyze_failover_event(
    file_entry: dict[str, Any],
    s3ap_alias: str,
    model_id: str,
    demo_mode: bool,
) -> dict[str, Any]:
    """個別フェイルオーバーイベントを分析する"""
    key = file_entry["key"]

    # ログ内容を取得
    content = _read_log_content(s3ap_alias, key)

    # ログからフェイルオーバー指標を抽出
    indicators_found = []
    for line in content.split("\n"):
        for indicator in FAILOVER_INDICATORS:
            if indicator.lower() in line.lower():
                indicators_found.append({"indicator": indicator, "line": line.strip()[:200]})
                break

    # 状態遷移を検出
    state_transitions = _detect_state_transitions(content)

    return {
        "file": key,
        "indicators_found": indicators_found[:20],
        "state_transitions": state_transitions,
        "indicator_count": len(indicators_found),
        "severity": file_entry.get("severity", "HIGH"),
        "last_modified": file_entry.get("last_modified", ""),
    }


def _detect_state_transitions(content: str) -> list[dict[str, str]]:
    """LifeKeeper リソースの状態遷移を検出する"""
    transitions = []
    for state_code, description in RESOURCE_STATE_TRANSITIONS.items():
        if state_code in content:
            transitions.append({"state": state_code, "description": description})
    return transitions


def _calculate_health_score(objects: list[dict[str, Any]], failover_events: list[dict[str, Any]]) -> dict[str, Any]:
    """クラスタのヘルススコアを算出する (100点満点)"""
    score = 100

    # フェイルオーバーイベント数による減点
    failover_count = len(failover_events)
    score -= min(failover_count * HEALTH_SCORE_DEDUCTIONS["failover_event"], 60)

    # カテゴリ別の減点
    for obj in objects:
        category = obj.get("category", "")
        severity = obj.get("severity", "LOW")

        if category == "communication_log" and severity in ("HIGH", "CRITICAL"):
            score -= HEALTH_SCORE_DEDUCTIONS["comm_path_failure"]
        elif category == "recovery_kit_log" and severity in ("HIGH", "CRITICAL"):
            score -= HEALTH_SCORE_DEDUCTIONS["recovery_kit_error"]

    # 最低 0 点
    score = max(score, 0)

    # スコアレベル判定
    if score >= 90:
        level = "HEALTHY"
    elif score >= 70:
        level = "WARNING"
    elif score >= 50:
        level = "DEGRADED"
    else:
        level = "CRITICAL"

    return {
        "score": score,
        "level": level,
        "failover_count": failover_count,
        "deduction_breakdown": {
            "failover_events": min(failover_count * 30, 60),
            "total_deducted": 100 - score,
        },
    }


def _perform_root_cause_analysis(
    failover_analyses: list[dict[str, Any]],
    health_score: dict[str, Any],
    cluster_name: str,
    model_id: str,
    demo_mode: bool,
) -> dict[str, Any]:
    """Bedrock による根本原因分析"""
    if demo_mode:
        return {
            "analysis": "Demo mode: Root cause analysis skipped.",
            "recommendations": [
                "Check LifeKeeper communication paths between cluster nodes.",
                "Verify NFS/iSCSI mount points on FSx for ONTAP volumes.",
                "Review Recovery Kit configuration for protected applications.",
            ],
            "model_id": model_id,
            "demo_mode": True,
        }

    # 分析用プロンプト構築
    prompt = _build_analysis_prompt(failover_analyses, health_score, cluster_name)

    try:
        response = bedrock_client.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": [{"text": prompt}],
                        }
                    ],
                    "inferenceConfig": {
                        "maxTokens": 2048,
                        "temperature": 0.2,
                    },
                }
            ),
        )

        response_body = json.loads(response["body"].read())
        analysis_text = response_body.get("output", {}).get("message", {}).get("content", [{}])[0].get("text", "")

        return {
            "analysis": analysis_text,
            "model_id": model_id,
            "demo_mode": False,
        }

    except Exception as e:
        logger.error("Bedrock analysis failed: %s", str(e))
        return {
            "analysis": f"Analysis failed: {str(e)}",
            "model_id": model_id,
            "error": str(e),
        }


def _build_analysis_prompt(
    failover_analyses: list[dict[str, Any]],
    health_score: dict[str, Any],
    cluster_name: str,
) -> str:
    """Bedrock 分析プロンプトを構築する"""
    indicators_text = ""
    for analysis in failover_analyses:
        indicators_text += f"\nFile: {analysis['file']}\n"
        for ind in analysis.get("indicators_found", [])[:5]:
            indicators_text += f"  - {ind['indicator']}: {ind['line']}\n"
        for trans in analysis.get("state_transitions", []):
            indicators_text += f"  - State: {trans['state']} ({trans['description']})\n"

    return f"""You are an expert in SIOS LifeKeeper high availability clustering
and Amazon FSx for NetApp ONTAP storage systems.

Analyze the following failover events from LifeKeeper cluster "{cluster_name}"
and provide root cause analysis with actionable recommendations.

## Cluster Health Score
- Score: {health_score["score"]}/100 ({health_score["level"]})
- Failover events detected: {health_score["failover_count"]}

## Failover Event Details
{indicators_text}

## Analysis Required
1. Identify the most likely root cause of the failover(s).
2. Assess whether this is a storage-layer issue (FSx for ONTAP),
   network/communication path issue, or application-layer issue.
3. Provide specific remediation steps.
4. Recommend preventive measures.

Focus on:
- NFS/iSCSI mount health between EC2 and FSx for ONTAP
- LifeKeeper communication path (TCP/UDP heartbeat) stability
- Recovery Kit resource dependency chain integrity
- FSx for ONTAP Multi-AZ failover vs LifeKeeper application failover distinction

Respond in structured JSON with keys: root_cause, affected_layer,
remediation_steps (array), preventive_measures (array), confidence_level (HIGH/MEDIUM/LOW).
"""


def _generate_log_summary(objects: list[dict[str, Any]]) -> dict[str, Any]:
    """ログカテゴリサマリを生成する"""
    summary: dict[str, int] = {}
    severity_counts: dict[str, int] = {}
    total_size = 0

    for obj in objects:
        cat = obj.get("category", "other")
        sev = obj.get("severity", "LOW")
        summary[cat] = summary.get(cat, 0) + 1
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
        total_size += obj.get("size", 0)

    return {
        "category_counts": summary,
        "severity_counts": severity_counts,
        "total_files": len(objects),
        "total_size_bytes": total_size,
    }


def _read_log_content(s3ap_alias: str, key: str) -> str:
    """S3 AP 経由でログファイルの内容を読み取る"""
    try:
        response = s3_client.get_object(
            Bucket=s3ap_alias,
            Key=key,
            Range=f"bytes=0-{MAX_CONTENT_SIZE}",
        )
        content = response["Body"].read().decode("utf-8", errors="replace")
        return content
    except Exception as e:
        logger.warning("Failed to read %s: %s", key, str(e))
        return ""


def _save_result(result: dict[str, Any], output_bucket: str, cluster_name: str) -> None:
    """分析結果を S3 に保存する"""
    timestamp = int(time.time())
    key = f"ha-monitoring/{cluster_name}/{timestamp}/analysis.json"

    try:
        s3_client.put_object(
            Bucket=output_bucket,
            Key=key,
            Body=json.dumps(result, ensure_ascii=False, indent=2, default=str),
            ContentType="application/json",
        )
        logger.info("Result saved to s3://%s/%s", output_bucket, key)
    except Exception as e:
        logger.error("Failed to save result: %s", str(e))
