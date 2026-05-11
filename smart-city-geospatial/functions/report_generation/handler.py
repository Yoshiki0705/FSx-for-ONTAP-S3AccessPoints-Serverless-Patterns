"""UC17 Smart City Report Generation Lambda.

Bedrock Nova Lite を使って、土地利用・変化検出・リスク評価の結果から
都市計画レポートを自然言語で生成する。

Environment Variables:
    BEDROCK_MODEL_ID: モデル ID (default: "amazon.nova-lite-v1:0")
    MAX_TOKENS: 生成最大トークン (default: 2048)
    OUTPUT_DESTINATION: `STANDARD_S3` or `FSXN_S3AP` (デフォルト: `STANDARD_S3`)
    OUTPUT_BUCKET: STANDARD_S3 モードの出力バケット
    OUTPUT_S3AP_ALIAS: FSXN_S3AP モードの S3AP Alias or ARN
    OUTPUT_S3AP_PREFIX: FSXN_S3AP モードの出力プレフィックス
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler
from shared.output_writer import OutputWriter

logger = logging.getLogger(__name__)


def build_prompt(
    source_key: str,
    landuse: dict[str, float],
    change_magnitude: float,
    dominant_change: dict[str, Any],
    risks: dict[str, dict],
) -> str:
    """レポート生成用プロンプトを構築する。"""
    lines = [
        "あなたは都市計画の専門家です。次のデータを元に、",
        "自治体の担当者向けに簡潔な所見レポートを作成してください。",
        "",
        f"## 分析対象: {source_key}",
        "",
        "### 土地利用分布",
    ]
    for k, v in sorted(landuse.items(), key=lambda x: -x[1]):
        lines.append(f"- {k}: {v * 100:.1f}%")
    lines.append("")
    lines.append("### 変化検出")
    lines.append(f"- 変化規模: {change_magnitude:.3f}")
    if dominant_change.get("max_increase"):
        inc = dominant_change["max_increase"]
        lines.append(f"- 最大増加: {inc['class']} (+{inc['delta']:.3f})")
    if dominant_change.get("max_decrease"):
        dec = dominant_change["max_decrease"]
        lines.append(f"- 最大減少: {dec['class']} ({dec['delta']:.3f})")
    lines.append("")
    lines.append("### 災害リスク")
    for hazard, info in risks.items():
        lines.append(f"- {hazard}: {info['score']} ({info['level']})")
    lines.append("")
    lines.append("### 求められる所見")
    lines.append("1. 都市計画上の注目点（150字以内）")
    lines.append("2. 優先すべき対策案（3 件、箇条書き）")
    lines.append("3. 次回観測時に監視すべき指標（1 件）")
    return "\n".join(lines)


def invoke_bedrock(
    bedrock, model_id: str, prompt: str, max_tokens: int
) -> str:
    """Bedrock を呼び出してレポートを生成する。"""
    try:
        # Nova / Claude 共通の messages format
        if "nova" in model_id.lower():
            body = {
                "messages": [
                    {"role": "user", "content": [{"text": prompt}]}
                ],
                "inferenceConfig": {
                    "maxTokens": max_tokens,
                    "temperature": 0.3,
                },
            }
        else:
            # Anthropic format
            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }

        response = bedrock.invoke_model(
            modelId=model_id,
            body=json.dumps(body),
            contentType="application/json",
        )
        raw = json.loads(response["body"].read())

        # Nova response
        if "output" in raw:
            content_list = raw["output"].get("message", {}).get("content", [])
            for item in content_list:
                if "text" in item:
                    return item["text"]
        # Anthropic
        if "content" in raw:
            content = raw["content"]
            if isinstance(content, list) and content:
                return content[0].get("text", "")

        return json.dumps(raw)[:1000]
    except Exception as e:
        logger.error("Bedrock invocation failed: %s", e)
        return f"(Report generation failed: {e})"


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """UC17 Report Generation Lambda ハンドラ。

    Input:
        {
            "source_key": "...",
            "landuse_distribution": {...},
            "change_magnitude": float,
            "dominant_change": {...},
            "risks": {...}
        }

    Output: {"source_key": str, "report_key": str, "report_text": str}
    """
    output_writer = OutputWriter.from_env()
    model_id = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")
    max_tokens = int(os.environ.get("MAX_TOKENS", "2048"))

    source_key = event.get("source_key", "")
    landuse = event.get("landuse_distribution", {})
    change_magnitude = float(event.get("change_magnitude", 0.0))
    dominant_change = event.get("dominant_change", {})
    risks = event.get("risks", {})

    prompt = build_prompt(source_key, landuse, change_magnitude, dominant_change, risks)

    bedrock = boto3.client("bedrock-runtime")
    report_text = invoke_bedrock(bedrock, model_id, prompt, max_tokens)

    # 結果を出力先に書き出し
    report_key = f"reports/{datetime.utcnow().strftime('%Y/%m/%d')}/{source_key}.md"
    output_writer.put_text(
        key=report_key, text=report_text, content_type="text/markdown; charset=utf-8"
    )

    logger.info(
        "UC17 ReportGeneration: source=%s, report=%s, length=%d",
        source_key,
        report_key,
        len(report_text),
    )

    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="report_generation")
    metrics.set_dimension("UseCase", "smart-city-geospatial")
    metrics.set_dimension("ModelId", model_id)
    metrics.put_metric("ReportsGenerated", 1.0, "Count")
    metrics.put_metric("ReportLength", float(len(report_text)), "Count")
    metrics.flush()

    return {
        "source_key": source_key,
        "report_key": report_key,
        "report_text": report_text[:2000],  # truncate for response size
        "report_length": len(report_text),
    }
