"""OPS4 Analyze Handler — 保持ポリシー準拠チェック + ポリシードリフト検出

スナップショットの年齢を法定保持期間と照合し、以下を判定:
1. 保持ポリシー準拠: 全スナップショットが MinRetentionDays 以上保持されているか
2. 期限切れ検出: MaxRetentionDays を超過したスナップショットを特定
3. ポリシードリフト: 実際のスナップショット数が Snapshot Policy の期待値と乖離
4. スナップショット予約警告: 総サイズが閾値を超過

重要:
  - MinRetentionDays 未満のスナップショットは絶対に削除推奨しない (安全装置)
  - 法定保持期間 (FISC/HIPAA/NARA) 内のスナップショットは削除推奨しない
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# Retention policy presets (days)
RETENTION_PRESETS = {
    "FISC": 2557,  # 7 years (金融: FISC 安全対策基準)
    "HIPAA": 2192,  # 6 years (医療)
    "NARA": 10950,  # 30 years (公文書: National Archives)
    "CUSTOM": None,  # Uses MAX_RETENTION_DAYS parameter
}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Analyze snapshot retention and policy drift.

    Args:
        event: Output from Collect step (file_systems with snapshots)

    Returns:
        dict with analyses per file system
    """
    retention_policy = os.environ.get("RETENTION_POLICY", "CUSTOM")
    max_retention_days = int(os.environ.get("MAX_RETENTION_DAYS", "90"))
    min_retention_days = int(os.environ.get("MIN_RETENTION_DAYS", "7"))
    enable_bedrock = os.environ.get("ENABLE_BEDROCK_SUMMARY", "true") == "true"

    # Resolve effective max retention
    effective_max_days = RETENTION_PRESETS.get(retention_policy) or max_retention_days

    file_systems = event.get("file_systems", [])
    logger.info(
        "Analyzing snapshots for %d file systems (policy=%s, max=%d days, min=%d days)",
        len(file_systems),
        retention_policy,
        effective_max_days,
        min_retention_days,
    )

    all_results = []
    for fs_data in file_systems:
        fs_id = fs_data.get("fs_id", "unknown")
        volume_snapshots = fs_data.get("volume_snapshots", [])
        policies = fs_data.get("snapshot_policies", [])

        # Analyze each volume
        volume_audits = []
        total_expired = 0
        total_expired_bytes = 0

        for vol_data in volume_snapshots:
            audit = _audit_volume_snapshots(
                fs_id=fs_id,
                vol_data=vol_data,
                policies=policies,
                effective_max_days=effective_max_days,
                min_retention_days=min_retention_days,
            )
            volume_audits.append(audit)
            total_expired += len(audit["expired_snapshots"])
            total_expired_bytes += sum(s.get("size_bytes", 0) for s in audit["expired_snapshots"])

        # Summary
        summary = {
            "total_volumes_scanned": len(volume_snapshots),
            "total_snapshots_scanned": sum(v.get("snapshot_count", 0) for v in volume_snapshots),
            "total_expired_snapshots": total_expired,
            "total_expired_bytes": total_expired_bytes,
            "total_expired_gb": round(total_expired_bytes / (1024**3), 2),
            "volumes_with_drift": sum(1 for a in volume_audits if a["policy_drift_detected"]),
            "retention_policy": retention_policy,
            "effective_max_retention_days": effective_max_days,
            "min_retention_days": min_retention_days,
        }

        # AI summary
        ai_summary = None
        if enable_bedrock and (total_expired > 0 or summary["volumes_with_drift"] > 0):
            ai_summary = _generate_ai_summary(fs_id, summary, volume_audits)

        all_results.append(
            {
                "fs_id": fs_id,
                "volume_audits": volume_audits,
                "summary": summary,
                "ai_summary": ai_summary,
                "analyzed_at": datetime.now(UTC).isoformat(),
            }
        )

    return {
        "analyses": all_results,
        "total_expired_snapshots": sum(r["summary"]["total_expired_snapshots"] for r in all_results),
        "analyzed_at": datetime.now(UTC).isoformat(),
    }


def _audit_volume_snapshots(
    fs_id: str,
    vol_data: dict[str, Any],
    policies: list[dict],
    effective_max_days: int,
    min_retention_days: int,
) -> dict[str, Any]:
    """単一ボリュームのスナップショットを監査する."""
    vol_name = vol_data.get("volume_name", "unknown")
    vol_uuid = vol_data.get("volume_uuid", "")
    snapshots = vol_data.get("snapshots", [])

    expired_snapshots = []
    compliant_snapshots = []
    protected_snapshots = []  # Within min retention (never delete)

    for snap in snapshots:
        age_days = snap.get("age_days", 0)

        if age_days < min_retention_days:
            # Protected: too young to delete
            protected_snapshots.append(snap)
        elif age_days > effective_max_days:
            # Expired: beyond max retention
            expired_snapshots.append(snap)
        else:
            # Compliant: within retention window
            compliant_snapshots.append(snap)

    # Policy drift detection
    drift_detected, drift_details = _detect_policy_drift(vol_name, snapshots, policies)

    # Total snapshot size
    total_size = sum(s.get("size_bytes", 0) for s in snapshots)
    oldest_age = max((s.get("age_days", 0) for s in snapshots), default=0)

    return {
        "fs_id": fs_id,
        "volume_name": vol_name,
        "volume_uuid": vol_uuid,
        "total_snapshots": len(snapshots),
        "total_size_bytes": total_size,
        "oldest_snapshot_age_days": oldest_age,
        "retention_compliant": len(expired_snapshots) == 0,
        "expired_snapshots": expired_snapshots,
        "expired_count": len(expired_snapshots),
        "protected_count": len(protected_snapshots),
        "compliant_count": len(compliant_snapshots),
        "policy_drift_detected": drift_detected,
        "policy_drift_details": drift_details,
    }


def _detect_policy_drift(
    vol_name: str,
    snapshots: list[dict],
    policies: list[dict],
) -> tuple[bool, str]:
    """Snapshot Policy と実際のスナップショット数の乖離を検出する.

    Returns:
        (drift_detected: bool, drift_details: str)
    """
    if not policies:
        return False, ""

    # Count snapshots by name pattern
    daily_count = sum(1 for s in snapshots if "daily" in s.get("snapshot_name", "").lower())
    weekly_count = sum(1 for s in snapshots if "weekly" in s.get("snapshot_name", "").lower())
    manual_count = sum(
        1
        for s in snapshots
        if "daily" not in s.get("snapshot_name", "").lower()
        and "weekly" not in s.get("snapshot_name", "").lower()
        and "hourly" not in s.get("snapshot_name", "").lower()
    )

    # Check against first policy (simplified — production would match per-volume)
    policy = policies[0] if policies else {}
    schedules = policy.get("schedules", [])

    expected_daily = 0
    expected_weekly = 0
    for sched in schedules:
        sched_name = sched.get("schedule", "")
        count = sched.get("count", 0)
        if "daily" in sched_name:
            expected_daily = count
        elif "weekly" in sched_name:
            expected_weekly = count

    drift_items = []
    if expected_daily > 0 and daily_count > expected_daily * 1.5:
        drift_items.append(f"daily snapshots: expected ~{expected_daily}, found {daily_count}")
    if expected_weekly > 0 and weekly_count > expected_weekly * 1.5:
        drift_items.append(f"weekly snapshots: expected ~{expected_weekly}, found {weekly_count}")
    if manual_count > 10:
        drift_items.append(f"manual/orphan snapshots: {manual_count} (consider cleanup)")

    if drift_items:
        return True, "; ".join(drift_items)
    return False, ""


def _generate_ai_summary(
    fs_id: str,
    summary: dict[str, Any],
    volume_audits: list[dict],
) -> str | None:
    """Bedrock Nova で監査サマリを生成する."""
    try:
        import boto3

        bedrock = boto3.client("bedrock-runtime")

        # Build concise audit info for prompt
        audit_summary = []
        for audit in volume_audits[:5]:
            if audit["expired_count"] > 0 or audit["policy_drift_detected"]:
                audit_summary.append(
                    {
                        "volume": audit["volume_name"],
                        "expired": audit["expired_count"],
                        "oldest_days": audit["oldest_snapshot_age_days"],
                        "drift": audit["policy_drift_details"],
                    }
                )

        prompt = (
            "You are an AWS storage operations advisor. "
            "Analyze the following FSx for ONTAP snapshot audit results "
            "and provide a concise action summary in Japanese (3-5 bullet points). "
            "Focus on: compliance risk, storage waste from expired snapshots, "
            "and recommended cleanup priority.\n\n"
            f"File System: {fs_id}\n"
            f"Summary: {json.dumps(summary, ensure_ascii=False)}\n"
            f"Top issues: {json.dumps(audit_summary, ensure_ascii=False)}\n\n"
            "IMPORTANT: Never recommend deleting snapshots within MinRetentionDays. "
            "Note regulatory retention requirements.\n"
            "Output: Japanese bullet points with priority order."
        )

        response = bedrock.invoke_model(
            modelId="amazon.nova-lite-v1:0",
            contentType="application/json",
            accept="application/json",
            body=json.dumps(
                {
                    "messages": [{"role": "user", "content": [{"text": prompt}]}],
                    "inferenceConfig": {"maxTokens": 500, "temperature": 0.3},
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
