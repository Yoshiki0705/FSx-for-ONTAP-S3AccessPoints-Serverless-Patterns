"""OPS5 Analyze Handler — コスト最適化分析."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    enable_bedrock = os.environ.get("ENABLE_BEDROCK_SUMMARY", "true") == "true"
    file_systems = event.get("file_systems", [])

    all_results = []
    for fs_data in file_systems:
        fs_id = fs_data.get("fs_id", "unknown")
        breakdown = fs_data.get("monthly_cost_breakdown", {})
        total = fs_data.get("total_monthly_cost_usd", 0)
        cost_per_gb = fs_data.get("cost_per_gb_usd", 0)

        # Identify top cost driver
        top_driver = max(breakdown.items(), key=lambda x: x[1])[0] if breakdown else "unknown"

        # Simple growth projection (5% monthly growth as baseline)
        growth_rate = 5.0
        projected_3mo = round(total * (1 + growth_rate / 100) ** 3, 2)

        recommendations = []
        # Recommend if throughput is > 50% of total cost
        if breakdown.get("throughput", 0) > total * 0.5:
            recommendations.append(
                {
                    "type": "throughput_review",
                    "description": "Throughput cost is >50% of total. Review if current tier is needed.",
                    "potential_savings_usd": round(breakdown["throughput"] * 0.3, 2),
                }
            )
        # Recommend tiering if SSD is > 60% of total and no capacity pool usage
        if breakdown.get("ssd", 0) > total * 0.6 and fs_data.get("capacity_pool_gb", 0) < 10:
            recommendations.append(
                {
                    "type": "enable_tiering",
                    "description": "SSD dominates cost with minimal tiering. Enable auto tiering.",
                    "potential_savings_usd": round(breakdown["ssd"] * 0.2, 2),
                }
            )

        summary = {
            "total_monthly_cost_usd": total,
            "cost_per_gb_usd": cost_per_gb,
            "top_cost_driver": top_driver,
            "projected_3month_cost_usd": projected_3mo,
            "growth_rate_percent": growth_rate,
            "recommendation_count": len(recommendations),
        }

        ai_summary = None
        if enable_bedrock and total > 0:
            ai_summary = _generate_ai_summary(fs_id, summary, breakdown)

        all_results.append(
            {
                "fs_id": fs_id,
                "cost_breakdown": breakdown,
                "recommendations": recommendations,
                "summary": summary,
                "ai_summary": ai_summary,
                "analyzed_at": datetime.now(UTC).isoformat(),
            }
        )

    return {
        "analyses": all_results,
        "total_recommendations": sum(len(r["recommendations"]) for r in all_results),
        "analyzed_at": datetime.now(UTC).isoformat(),
    }


def _generate_ai_summary(fs_id: str, summary: dict, breakdown: dict) -> str | None:
    try:
        import boto3

        bedrock = boto3.client("bedrock-runtime")
        prompt = (
            "Analyze this FSx for ONTAP cost data. Provide 3-4 bullet points in Japanese: "
            "current cost drivers, projected growth, and cost reduction opportunities.\n"
            f"FS: {fs_id}\nBreakdown: {json.dumps(breakdown)}\nSummary: {json.dumps(summary)}"
        )
        resp = bedrock.invoke_model(
            modelId="amazon.nova-lite-v1:0",
            contentType="application/json",
            accept="application/json",
            body=json.dumps(
                {
                    "messages": [{"role": "user", "content": [{"text": prompt}]}],
                    "inferenceConfig": {"maxTokens": 400, "temperature": 0.3},
                }
            ),
        )
        result = json.loads(resp["body"].read())
        content = result.get("output", {}).get("message", {}).get("content", [{}])
        return content[0].get("text", "") if content else None
    except Exception as e:
        logger.warning("Bedrock failed: %s", e)
        return None
