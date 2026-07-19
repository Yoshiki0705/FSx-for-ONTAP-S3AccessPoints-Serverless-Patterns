"""OPS1 Analyze Handler — 分析 + 推奨生成

Collect ステップの出力を分析し、容量/スループットの推奨 + What-If シナリオを生成。
EnableBedrockSummary=true の場合は Bedrock Nova で自然言語推奨も生成する。

このパターンが提供する追加機能 (既存ソリューション: NetApp fsxn-monitoring-auto-resizing との違い):
    - 閾値超過 → 即リサイズではなく、分析 → 推奨 → (承認後) 実行
    - What-If シミュレーション (コスト差分を事前に計算)
    - AI による自然言語推奨 (技術者以外にも理解可能)
    - 低利用率の検出 (ダウンサイジング推奨)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# FSx for ONTAP throughput tier pricing (ap-northeast-1, USD/MBps/month)
# Reference: https://aws.amazon.com/fsx/netapp-ontap/pricing/
THROUGHPUT_TIERS_MBPS = [128, 256, 512, 1024, 2048, 4096]
THROUGHPUT_PRICE_PER_MBPS_MONTH = 0.370  # ap-northeast-1 approximate

# SSD storage pricing (ap-northeast-1, USD/GB/month)
SSD_PRICE_PER_GB_MONTH = 0.125


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Analyze collected metrics and generate recommendations.

    Args:
        event: Output from Collect step (file_systems list)
        context: Lambda context

    Returns:
        dict: OpsAnalyzeOutput-compatible structure with recommendations
    """
    threshold = int(os.environ.get("THRESHOLD_PERCENT", "80"))
    low_threshold = int(os.environ.get("LOW_UTILIZATION_THRESHOLD_PERCENT", "20"))
    enable_bedrock = os.environ.get("ENABLE_BEDROCK_SUMMARY", "true") == "true"

    file_systems = event.get("file_systems", [])
    logger.info("Analyzing %d file systems (threshold=%d%%)", len(file_systems), threshold)

    all_results = []
    for fs_data in file_systems:
        fs_id = fs_data.get("fs_id", "unknown")
        volumes = fs_data.get("volumes", [])
        aggregates = fs_data.get("aggregates", [])
        cloudwatch = fs_data.get("cloudwatch", {})

        # Generate recommendations
        recommendations = _analyze_capacity(fs_id, volumes, threshold, low_threshold)
        recommendations.extend(_analyze_throughput(fs_id, cloudwatch, threshold))

        # Generate What-If scenarios
        what_if_scenarios = _generate_what_if(fs_id, cloudwatch)

        # Summary statistics
        summary = _compute_summary(volumes, aggregates, cloudwatch, recommendations)

        # AI summary (optional)
        ai_summary = None
        if enable_bedrock and recommendations:
            ai_summary = _generate_ai_summary(fs_id, recommendations, summary)

        all_results.append(
            {
                "fs_id": fs_id,
                "recommendations": recommendations,
                "what_if_scenarios": what_if_scenarios,
                "summary_stats": summary,
                "ai_summary": ai_summary,
                "analyzed_at": datetime.now(UTC).isoformat(),
            }
        )

    return {
        "analyses": all_results,
        "total_recommendations": sum(len(r["recommendations"]) for r in all_results),
        "analyzed_at": datetime.now(UTC).isoformat(),
    }


def _analyze_capacity(
    fs_id: str,
    volumes: list[dict],
    threshold: int,
    low_threshold: int,
) -> list[dict[str, Any]]:
    """ボリューム容量を分析して推奨を生成する."""
    recommendations = []

    for vol in volumes:
        util = vol.get("utilization_percent", 0)
        name = vol.get("name", "unknown")
        autosize_enabled = vol.get("autosize_enabled", False)
        autosize_mode = vol.get("autosize_mode", "off")

        # High utilization → upsize recommendation
        if util >= threshold:
            if autosize_enabled:
                reason = (
                    f"Volume '{name}' is at {util:.1f}% utilization. "
                    f"Autosize is enabled (mode={autosize_mode}), but current usage "
                    f"exceeds the alert threshold of {threshold}%. "
                    f"Consider increasing the maximum autosize limit or expanding manually."
                )
                rec_type = "upsize"
                action = None
            else:
                reason = (
                    f"Volume '{name}' is at {util:.1f}% utilization "
                    f"(threshold: {threshold}%). Autosize is disabled. "
                    f"Recommend enabling autosize (grow mode) or expanding volume size."
                )
                rec_type = "upsize"
                action = "volume_autosize_enable"

            size_gb = vol.get("size_bytes", 0) / (1024**3)
            expand_gb = size_gb * 0.2  # Suggest 20% expansion
            cost_delta = expand_gb * SSD_PRICE_PER_GB_MONTH

            recommendations.append(
                {
                    "fs_id": fs_id,
                    "recommendation_type": rec_type,
                    "target": name,
                    "current_value": f"{util:.1f}% ({size_gb:.0f} GB)",
                    "recommended_value": (
                        "Enable autosize (grow)" if not autosize_enabled else f"Expand +{expand_gb:.0f} GB"
                    ),
                    "reason": reason,
                    "monthly_cost_delta_usd": round(cost_delta, 2),
                    "confidence": 0.85 if util >= 90 else 0.70,
                    "automation_action": action,
                }
            )

        # Low utilization → downsize recommendation (only if autosize not managing it)
        elif util <= low_threshold and not autosize_enabled:
            size_gb = vol.get("size_bytes", 0) / (1024**3)
            used_gb = vol.get("used_bytes", 0) / (1024**3)
            # Recommend shrinking to 2x current usage (with minimum)
            recommended_gb = max(used_gb * 2, 20)  # Minimum 20 GB
            savings = (size_gb - recommended_gb) * SSD_PRICE_PER_GB_MONTH

            if savings > 1.0:  # Only recommend if savings > $1/month
                recommendations.append(
                    {
                        "fs_id": fs_id,
                        "recommendation_type": "downsize",
                        "target": name,
                        "current_value": f"{util:.1f}% ({size_gb:.0f} GB allocated, {used_gb:.0f} GB used)",
                        "recommended_value": f"Shrink to {recommended_gb:.0f} GB or enable autosize (grow_shrink)",
                        "reason": (
                            f"Volume '{name}' is at only {util:.1f}% utilization "
                            f"({used_gb:.0f} GB used of {size_gb:.0f} GB). "
                            f"Consider enabling autosize (grow_shrink) or shrinking to {recommended_gb:.0f} GB."
                        ),
                        "monthly_cost_delta_usd": round(-savings, 2),
                        "confidence": 0.60,
                        "automation_action": "volume_autosize_enable_grow_shrink",
                    }
                )

    return recommendations


def _analyze_throughput(
    fs_id: str,
    cloudwatch: dict[str, Any],
    threshold: int,
) -> list[dict[str, Any]]:
    """スループットキャパシティを分析して推奨を生成する."""
    recommendations = []

    # Network throughput utilization (Gen2 only)
    net_util = cloudwatch.get("network_throughput_utilization_percent")
    current_mbps = cloudwatch.get("throughput_capacity_mbps", 0)

    if net_util is not None and net_util >= threshold and current_mbps > 0:
        # Recommend next tier up
        next_tier = _get_next_tier(current_mbps)
        if next_tier:
            cost_current = current_mbps * THROUGHPUT_PRICE_PER_MBPS_MONTH
            cost_next = next_tier * THROUGHPUT_PRICE_PER_MBPS_MONTH
            delta = cost_next - cost_current

            recommendations.append(
                {
                    "fs_id": fs_id,
                    "recommendation_type": "tier_upgrade",
                    "target": fs_id,
                    "current_value": f"{current_mbps} MBps ({net_util:.1f}% utilized)",
                    "recommended_value": f"{next_tier} MBps",
                    "reason": (
                        f"Network throughput utilization is {net_util:.1f}% "
                        f"(threshold: {threshold}%). Current tier: {current_mbps} MBps. "
                        f"Upgrading to {next_tier} MBps will provide headroom for growth."
                    ),
                    "monthly_cost_delta_usd": round(delta, 2),
                    "confidence": 0.80,
                    "automation_action": "fsx_update_throughput",
                }
            )

    # Gen1: calculate from network bytes
    elif net_util is None and current_mbps > 0:
        sent_bps = cloudwatch.get("network_sent_bytes_per_sec", 0)
        recv_bps = cloudwatch.get("network_received_bytes_per_sec", 0)
        total_mbps = (max(sent_bps, recv_bps)) / (1024 * 1024)
        calc_util = (total_mbps / current_mbps * 100) if current_mbps > 0 else 0

        if calc_util >= threshold:
            next_tier = _get_next_tier(current_mbps)
            if next_tier:
                cost_delta = (next_tier - current_mbps) * THROUGHPUT_PRICE_PER_MBPS_MONTH
                recommendations.append(
                    {
                        "fs_id": fs_id,
                        "recommendation_type": "tier_upgrade",
                        "target": fs_id,
                        "current_value": f"{current_mbps} MBps (~{calc_util:.1f}% utilized, Gen1 estimate)",
                        "recommended_value": f"{next_tier} MBps",
                        "reason": (
                            f"Estimated throughput utilization is ~{calc_util:.1f}% "
                            f"(Gen1: calculated from network bytes). "
                            f"Current tier: {current_mbps} MBps."
                        ),
                        "monthly_cost_delta_usd": round(cost_delta, 2),
                        "confidence": 0.65,  # Lower confidence for Gen1 estimate
                        "automation_action": "fsx_update_throughput",
                    }
                )

    return recommendations


def _generate_what_if(
    fs_id: str,
    cloudwatch: dict[str, Any],
) -> list[dict[str, Any]]:
    """What-If シナリオを生成する (ティア変更時のコスト差分)."""
    current_mbps = cloudwatch.get("throughput_capacity_mbps", 0)
    if current_mbps == 0:
        return []

    current_cost = current_mbps * THROUGHPUT_PRICE_PER_MBPS_MONTH
    scenarios = []

    for tier in THROUGHPUT_TIERS_MBPS:
        if tier == current_mbps:
            continue
        tier_cost = tier * THROUGHPUT_PRICE_PER_MBPS_MONTH
        delta = tier_cost - current_cost
        direction = "Upgrade" if tier > current_mbps else "Downgrade"

        scenarios.append(
            {
                "fs_id": fs_id,
                "scenario_name": f"{direction} to {tier} MBps",
                "current_monthly_cost_usd": round(current_cost, 2),
                "projected_monthly_cost_usd": round(tier_cost, 2),
                "monthly_delta_usd": round(delta, 2),
                "description": (
                    f"Throughput tier change: {current_mbps} → {tier} MBps. "
                    f"Monthly cost {'increase' if delta > 0 else 'decrease'}: "
                    f"${abs(delta):.2f}/month."
                ),
            }
        )

    return scenarios


def _compute_summary(
    volumes: list[dict],
    aggregates: list[dict],
    cloudwatch: dict[str, Any],
    recommendations: list[dict],
) -> dict[str, Any]:
    """集約統計を計算する."""
    vol_utils = [v.get("utilization_percent", 0) for v in volumes]

    return {
        "total_volumes": len(volumes),
        "volumes_above_threshold": sum(1 for u in vol_utils if u >= int(os.environ.get("THRESHOLD_PERCENT", "80"))),
        "volumes_below_low_threshold": sum(
            1 for u in vol_utils if u <= int(os.environ.get("LOW_UTILIZATION_THRESHOLD_PERCENT", "20"))
        ),
        "avg_volume_utilization_percent": round(sum(vol_utils) / len(vol_utils), 2) if vol_utils else 0,
        "max_volume_utilization_percent": max(vol_utils) if vol_utils else 0,
        "throughput_utilization_percent": cloudwatch.get("network_throughput_utilization_percent"),
        "recommendation_count": len(recommendations),
        "total_monthly_cost_delta_usd": round(sum(r.get("monthly_cost_delta_usd", 0) for r in recommendations), 2),
    }


def _generate_ai_summary(
    fs_id: str,
    recommendations: list[dict],
    summary: dict[str, Any],
) -> str | None:
    """Bedrock Nova で自然言語推奨サマリを生成する."""
    try:
        import boto3

        bedrock = boto3.client("bedrock-runtime")

        prompt = (
            "You are an AWS storage operations advisor. "
            "Analyze the following FSx for ONTAP capacity metrics and recommendations, "
            "then provide a concise action summary in Japanese (3-5 bullet points). "
            "Focus on: what to do first, estimated cost impact, and risk if no action is taken.\n\n"
            f"File System: {fs_id}\n"
            f"Summary: {json.dumps(summary, ensure_ascii=False)}\n"
            f"Recommendations: {json.dumps(recommendations[:5], ensure_ascii=False)}\n\n"
            "Output format: Japanese bullet points with priority order."
        )

        response = bedrock.invoke_model(
            modelId="amazon.nova-lite-v1:0",
            contentType="application/json",
            accept="application/json",
            body=json.dumps(
                {
                    "messages": [{"role": "user", "content": [{"text": prompt}]}],
                    "inferenceConfig": {
                        "maxTokens": 500,
                        "temperature": 0.3,
                    },
                }
            ),
        )

        result = json.loads(response["body"].read())
        output_text = result.get("output", {}).get("message", {}).get("content", [{}])
        if output_text:
            return output_text[0].get("text", "")
        return None

    except Exception as e:
        logger.warning("Bedrock summary generation failed: %s", e)
        return None


def _get_next_tier(current_mbps: int) -> int | None:
    """現在のティアの次のティアを返す."""
    for tier in THROUGHPUT_TIERS_MBPS:
        if tier > current_mbps:
            return tier
    return None
