"""OPS3 Analyze Handler — ティアリングポリシー最適化分析.

ボリュームごとのティアリングポリシーとコールドデータ率を分析し、
ポリシー変更やクーリング期間調整の推奨 + コスト試算を生成する。

FSx for ONTAP pricing reference (ap-northeast-1):
  SSD: ~$0.125/GB/month
  Capacity Pool: ~$0.021/GB/month
  差額: ~$0.104/GB/month (SSD → Capacity Pool 移行時の節約)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# Pricing constants (ap-northeast-1 approximate)
SSD_PRICE_PER_GB_MONTH = 0.125
CAPACITY_POOL_PRICE_PER_GB_MONTH = 0.021
SAVINGS_PER_GB_MONTH = SSD_PRICE_PER_GB_MONTH - CAPACITY_POOL_PRICE_PER_GB_MONTH


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Analyze tiering policy and generate recommendations."""
    cold_threshold = int(os.environ.get("COLD_DATA_THRESHOLD_PERCENT", "30"))
    enable_bedrock = os.environ.get("ENABLE_BEDROCK_SUMMARY", "true") == "true"

    file_systems = event.get("file_systems", [])
    logger.info("Analyzing tiering for %d file systems (cold_threshold=%d%%)", len(file_systems), cold_threshold)

    all_results = []
    for fs_data in file_systems:
        fs_id = fs_data.get("fs_id", "unknown")
        volumes = fs_data.get("volumes", [])

        recommendations = []
        for vol in volumes:
            rec = _analyze_volume(fs_id, vol, cold_threshold)
            if rec:
                recommendations.append(rec)

        summary = {
            "total_volumes": len(volumes),
            "volumes_with_recommendations": len(recommendations),
            "total_potential_savings_usd": round(
                sum(r.get("estimated_monthly_savings_usd", 0) for r in recommendations), 2
            ),
            "policy_distribution": _count_policies(volumes),
        }

        ai_summary = None
        if enable_bedrock and recommendations:
            ai_summary = _generate_ai_summary(fs_id, summary, recommendations)

        all_results.append(
            {
                "fs_id": fs_id,
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


def _analyze_volume(fs_id: str, vol: dict, cold_threshold: int) -> dict[str, Any] | None:
    """単一ボリュームのティアリング推奨を生成."""
    policy = vol.get("tiering_policy", "none")
    cooling_days = vol.get("cooling_period_days", 31)
    cloud_used = vol.get("cloud_storage_used_bytes", 0)
    vol_name = vol.get("name", "unknown")

    # Estimate volume size from cloud storage ratio (simplified for demo)
    # In production, this would come from volume space data
    cloud_used_gb = cloud_used / (1024**3)

    # Recommendation logic
    if policy == "none":
        # Volume has no tiering — recommend enabling if it likely has cold data
        # (In production, we'd check performance-tier-inactive-user-data-percent)
        estimated_savings = cloud_used_gb * SAVINGS_PER_GB_MONTH if cloud_used_gb > 0 else 10.0 * SAVINGS_PER_GB_MONTH
        return {
            "fs_id": fs_id,
            "volume_name": vol_name,
            "current_policy": "none",
            "recommended_policy": "auto",
            "current_cooling_days": cooling_days,
            "recommended_cooling_days": 31,
            "estimated_monthly_savings_usd": round(estimated_savings, 2),
            "reason": (
                f"Volume '{vol_name}' has tiering_policy=none. "
                f"Enabling 'auto' policy with 31-day cooling period will "
                f"automatically tier inactive data to capacity pool storage "
                f"(~${SAVINGS_PER_GB_MONTH:.3f}/GB/month savings)."
            ),
            "confidence": 0.70,
        }

    elif policy == "snapshot-only" and cloud_used_gb > 50:
        # Has significant cold snapshot data — consider upgrading to auto
        additional_savings = cloud_used_gb * 0.3 * SAVINGS_PER_GB_MONTH  # estimate 30% more could tier
        return {
            "fs_id": fs_id,
            "volume_name": vol_name,
            "current_policy": "snapshot-only",
            "recommended_policy": "auto",
            "current_cooling_days": cooling_days,
            "recommended_cooling_days": 31,
            "estimated_monthly_savings_usd": round(additional_savings, 2),
            "reason": (
                f"Volume '{vol_name}' uses snapshot-only policy with "
                f"{cloud_used_gb:.0f} GB in capacity pool. Upgrading to 'auto' "
                f"would also tier inactive user data (not just snapshots)."
            ),
            "confidence": 0.60,
        }

    elif policy == "auto" and cooling_days > 14:
        # Already on auto but could benefit from shorter cooling
        # Only suggest if there's meaningful cloud data showing the tier works
        if cloud_used_gb > 100:
            savings_from_shorter = cloud_used_gb * 0.1 * SAVINGS_PER_GB_MONTH
            if savings_from_shorter > 1.0:
                return {
                    "fs_id": fs_id,
                    "volume_name": vol_name,
                    "current_policy": "auto",
                    "recommended_policy": "auto",
                    "current_cooling_days": cooling_days,
                    "recommended_cooling_days": 14,
                    "estimated_monthly_savings_usd": round(savings_from_shorter, 2),
                    "reason": (
                        f"Volume '{vol_name}' uses auto policy with {cooling_days}-day "
                        f"cooling period and {cloud_used_gb:.0f} GB already tiered. "
                        f"Reducing cooling period to 14 days may tier data sooner."
                    ),
                    "confidence": 0.50,
                }

    return None


def _count_policies(volumes: list[dict]) -> dict[str, int]:
    """ポリシー別ボリューム数をカウント."""
    counts: dict[str, int] = {}
    for vol in volumes:
        policy = vol.get("tiering_policy", "none")
        counts[policy] = counts.get(policy, 0) + 1
    return counts


def _generate_ai_summary(fs_id: str, summary: dict, recommendations: list[dict]) -> str | None:
    """Bedrock AI サマリ生成."""
    try:
        import boto3

        bedrock = boto3.client("bedrock-runtime")
        prompt = (
            "You are an AWS storage cost advisor. Analyze these FSx for ONTAP tiering "
            "recommendations and provide 3-4 bullet points in Japanese about: "
            "potential savings, recommended actions, and risks of changing tiering policy.\n\n"
            f"FS: {fs_id}\nSummary: {json.dumps(summary, ensure_ascii=False)}\n"
            f"Top recs: {json.dumps(recommendations[:3], ensure_ascii=False)}\n"
        )
        response = bedrock.invoke_model(
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
        result = json.loads(response["body"].read())
        content = result.get("output", {}).get("message", {}).get("content", [{}])
        return content[0].get("text", "") if content else None
    except Exception as e:
        logger.warning("Bedrock failed: %s", e)
        return None
