"""OPS2 Analyze Handler — ストレージ効率分析.

重複排除/圧縮の効率比を分析し、低効率ボリュームに有効化推奨を生成。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

SSD_PRICE_PER_GB_MONTH = 0.125


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    min_ratio = float(os.environ.get("MIN_EFFICIENCY_RATIO", "1.5"))
    enable_bedrock = os.environ.get("ENABLE_BEDROCK_SUMMARY", "true") == "true"

    file_systems = event.get("file_systems", [])

    all_results = []
    for fs_data in file_systems:
        fs_id = fs_data.get("fs_id", "unknown")
        volumes = fs_data.get("volumes", [])

        recommendations = []
        total_savings = 0
        for vol in volumes:
            ratio = vol.get("overall_ratio", 1.0)
            dedupe = vol.get("dedupe_enabled", False)
            compression = vol.get("compression_enabled", False)
            name = vol.get("name", "unknown")
            physical_gb = vol.get("physical_used_bytes", 0) / (1024**3)

            if not dedupe and not compression:
                # Neither enabled — recommend both
                estimated_ratio = 2.0  # conservative estimate
                potential_savings_gb = physical_gb * (1 - 1 / estimated_ratio)
                savings_usd = potential_savings_gb * SSD_PRICE_PER_GB_MONTH
                if savings_usd > 1.0:
                    recommendations.append({
                        "fs_id": fs_id,
                        "volume_name": name,
                        "current_ratio": ratio,
                        "dedupe_enabled": dedupe,
                        "compression_enabled": compression,
                        "recommendation": "Enable deduplication and compression",
                        "estimated_ratio_after": estimated_ratio,
                        "estimated_savings_gb": round(potential_savings_gb, 1),
                        "estimated_monthly_savings_usd": round(savings_usd, 2),
                        "confidence": 0.65,
                    })
                    total_savings += savings_usd
            elif ratio < min_ratio and physical_gb > 10:
                # Enabled but low ratio — may need tuning
                recommendations.append({
                    "fs_id": fs_id,
                    "volume_name": name,
                    "current_ratio": ratio,
                    "dedupe_enabled": dedupe,
                    "compression_enabled": compression,
                    "recommendation": f"Efficiency ratio {ratio:.1f}:1 is below target {min_ratio}:1. Consider enabling both dedup+compression or reviewing data patterns.",
                    "estimated_ratio_after": min_ratio,
                    "estimated_savings_gb": 0,
                    "estimated_monthly_savings_usd": 0,
                    "confidence": 0.40,
                })

        summary = {
            "total_volumes": len(volumes),
            "volumes_with_both_enabled": sum(1 for v in volumes if v.get("dedupe_enabled") and v.get("compression_enabled")),
            "volumes_with_none": sum(1 for v in volumes if not v.get("dedupe_enabled") and not v.get("compression_enabled")),
            "avg_efficiency_ratio": round(sum(v.get("overall_ratio", 1) for v in volumes) / max(len(volumes), 1), 2),
            "total_dedupe_savings_gb": round(sum(v.get("dedupe_savings_bytes", 0) for v in volumes) / (1024**3), 1),
            "total_compression_savings_gb": round(sum(v.get("compression_savings_bytes", 0) for v in volumes) / (1024**3), 1),
            "recommendation_count": len(recommendations),
            "total_potential_savings_usd": round(total_savings, 2),
        }

        ai_summary = None
        if enable_bedrock and recommendations:
            ai_summary = _generate_ai_summary(fs_id, summary, recommendations)

        all_results.append({
            "fs_id": fs_id,
            "recommendations": recommendations,
            "summary": summary,
            "ai_summary": ai_summary,
            "analyzed_at": datetime.now(UTC).isoformat(),
        })

    return {
        "analyses": all_results,
        "total_recommendations": sum(len(r["recommendations"]) for r in all_results),
        "analyzed_at": datetime.now(UTC).isoformat(),
    }


def _generate_ai_summary(fs_id: str, summary: dict, recs: list) -> str | None:
    try:
        import boto3
        bedrock = boto3.client("bedrock-runtime")
        prompt = (
            "Analyze FSx for ONTAP storage efficiency data. Provide 3 bullet points in Japanese: "
            "current savings from dedup/compression, potential additional savings, recommended actions.\n"
            f"FS: {fs_id}\nSummary: {json.dumps(summary)}\nRecs: {json.dumps(recs[:3])}"
        )
        resp = bedrock.invoke_model(modelId="amazon.nova-lite-v1:0", contentType="application/json", accept="application/json",
                                    body=json.dumps({"messages": [{"role": "user", "content": [{"text": prompt}]}], "inferenceConfig": {"maxTokens": 400, "temperature": 0.3}}))
        result = json.loads(resp["body"].read())
        content = result.get("output", {}).get("message", {}).get("content", [{}])
        return content[0].get("text", "") if content else None
    except Exception as e:
        logger.warning("Bedrock failed: %s", e)
        return None
