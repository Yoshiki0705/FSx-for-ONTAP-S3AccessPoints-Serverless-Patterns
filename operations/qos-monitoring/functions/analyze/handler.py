"""OPS6 Analyze Handler — QoS ポリシー分析.

QoS ポリシーの有無、ボリューム割当て状況を分析し、
ワークロード分離の推奨を生成する。
"""

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
        policies = fs_data.get("qos_policies", [])
        unassigned = fs_data.get("volumes_without_qos", [])

        recommendations = []

        # Volumes without QoS
        if unassigned:
            recommendations.append(
                {
                    "type": "assign_qos_policy",
                    "target_volumes": unassigned,
                    "description": f"{len(unassigned)} volumes have no QoS policy. Consider assigning a policy to prevent noisy-neighbor issues.",
                    "severity": "medium",
                }
            )

        # Default/unlimited policies
        unlimited_policies = [
            p for p in policies if p.get("max_throughput_iops") is None and p.get("max_throughput_mbps") is None
        ]
        if unlimited_policies:
            total_vols = sum(p.get("assigned_volume_count", 0) for p in unlimited_policies)
            if total_vols > 0:
                recommendations.append(
                    {
                        "type": "set_limits",
                        "target_policies": [p["name"] for p in unlimited_policies],
                        "description": f"{len(unlimited_policies)} policies have no throughput limits ({total_vols} volumes). Set max_throughput to prevent bandwidth contention.",
                        "severity": "low",
                    }
                )

        # Check for potential contention (many volumes on one policy)
        for policy in policies:
            if policy.get("assigned_volume_count", 0) > 10:
                recommendations.append(
                    {
                        "type": "split_policy",
                        "target_policy": policy["name"],
                        "description": f"Policy '{policy['name']}' has {policy['assigned_volume_count']} volumes. Consider splitting into workload-specific policies.",
                        "severity": "low",
                    }
                )

        summary = {
            "total_policies": len(policies),
            "policies_with_limits": sum(
                1 for p in policies if p.get("max_throughput_iops") or p.get("max_throughput_mbps")
            ),
            "policies_unlimited": len(unlimited_policies),
            "volumes_without_qos": len(unassigned),
            "recommendation_count": len(recommendations),
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


def _generate_ai_summary(fs_id: str, summary: dict, recs: list) -> str | None:
    try:
        import boto3

        bedrock = boto3.client("bedrock-runtime")
        prompt = (
            "Analyze QoS policy data for FSx for ONTAP. Provide 3 bullet points in Japanese: "
            "current QoS coverage, bandwidth contention risks, recommended actions.\n"
            f"FS: {fs_id}\nSummary: {json.dumps(summary)}\nRecs: {json.dumps(recs[:3])}"
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
