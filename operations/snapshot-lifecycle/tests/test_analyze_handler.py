"""OPS4 Analyze Handler テスト."""

from __future__ import annotations

import pytest


class TestRetentionCompliance:
    """保持ポリシー準拠チェックのテスト."""

    def test_expired_snapshots_detected(self, analyze_handler, collect_output):
        """MaxRetentionDays 超過のスナップショットが検出される."""
        result = analyze_handler.handler(collect_output, None)

        analyses = result["analyses"]
        assert len(analyses) == 1
        assert result["total_expired_snapshots"] >= 2  # 134 days + 210 days > 90

    def test_min_retention_protects_recent_snapshots(self, analyze_handler, collect_output):
        """MinRetentionDays 未満のスナップショットは期限切れにならない."""
        result = analyze_handler.handler(collect_output, None)

        vol_audit = result["analyses"][0]["volume_audits"][0]
        expired_names = [s["snapshot_name"] for s in vol_audit["expired_snapshots"]]
        # 1-day and 2-day old snapshots must NOT be expired
        assert "daily.2026-07-12_0010" not in expired_names
        assert "daily.2026-07-11_0010" not in expired_names

    def test_fisc_retention_preset(self, analyze_handler, collect_output, monkeypatch):
        """FISC (2557 days) プリセットでは全スナップショットが準拠."""
        monkeypatch.setenv("RETENTION_POLICY", "FISC")

        result = analyze_handler.handler(collect_output, None)

        # All snapshots are < 2557 days old, so none should be expired
        assert result["total_expired_snapshots"] == 0
        for audit in result["analyses"][0]["volume_audits"]:
            assert audit["retention_compliant"] is True

    def test_custom_short_retention(self, analyze_handler, collect_output, monkeypatch):
        """短い MaxRetentionDays で多くのスナップショットが期限切れ."""
        monkeypatch.setenv("MAX_RETENTION_DAYS", "30")

        result = analyze_handler.handler(collect_output, None)

        # 134, 210, 559 days old → all expired with 30-day max
        assert result["total_expired_snapshots"] >= 3

    def test_volume_compliance_status(self, analyze_handler, collect_output):
        """ボリュームごとの compliance ステータスが正しい."""
        result = analyze_handler.handler(collect_output, None)

        vol_audits = result["analyses"][0]["volume_audits"]
        # vol_production_data has expired (210 > 90) → non-compliant
        prod_audit = next(a for a in vol_audits if a["volume_name"] == "vol_production_data")
        assert prod_audit["retention_compliant"] is False
        assert prod_audit["expired_count"] >= 1


class TestPolicyDrift:
    """ポリシードリフト検出テスト."""

    def test_no_drift_with_normal_counts(self, analyze_handler, collect_output):
        """正常なスナップショット数ではドリフトなし."""
        result = analyze_handler.handler(collect_output, None)

        # vol_production_data has 2 daily + 2 weekly → within expected range
        vol_audits = result["analyses"][0]["volume_audits"]
        prod_audit = next(a for a in vol_audits if a["volume_name"] == "vol_production_data")
        assert prod_audit["policy_drift_detected"] is False

    def test_drift_detected_with_excessive_manual_snapshots(self, analyze_handler, monkeypatch):
        """手動スナップショットが多すぎるとドリフト検出."""
        # Create input with many manual snapshots
        input_data = {
            "file_systems": [
                {
                    "fs_id": "fs-test01",
                    "volume_snapshots": [
                        {
                            "volume_name": "vol_many_manual",
                            "volume_uuid": "uuid-001",
                            "snapshot_count": 15,
                            "snapshots": [
                                {
                                    "snapshot_name": f"manual_backup_{i}",
                                    "snapshot_uuid": f"s{i}",
                                    "size_bytes": 1073741824,
                                    "age_days": 30 + i,
                                    "volume_name": "vol_many_manual",
                                    "volume_uuid": "uuid-001",
                                    "fs_id": "fs-test01",
                                }
                                for i in range(15)
                            ],
                        }
                    ],
                    "snapshot_policies": [
                        {
                            "name": "default",
                            "uuid": "p1",
                            "enabled": True,
                            "schedules": [{"schedule": "daily", "count": 7}],
                        },
                    ],
                    "collected_at": "2026-07-13T00:00:00+00:00",
                }
            ],
            "collected_at": "2026-07-13T00:00:00+00:00",
            "demo_mode": True,
        }

        result = analyze_handler.handler(input_data, None)

        vol_audit = result["analyses"][0]["volume_audits"][0]
        assert vol_audit["policy_drift_detected"] is True
        assert "manual" in vol_audit["policy_drift_details"].lower()


class TestSummaryStats:
    """集約統計テスト."""

    def test_summary_has_required_fields(self, analyze_handler, collect_output):
        """サマリに必須フィールドが含まれる."""
        result = analyze_handler.handler(collect_output, None)

        summary = result["analyses"][0]["summary"]
        assert "total_volumes_scanned" in summary
        assert "total_snapshots_scanned" in summary
        assert "total_expired_snapshots" in summary
        assert "total_expired_gb" in summary
        assert "volumes_with_drift" in summary
        assert "retention_policy" in summary
        assert "effective_max_retention_days" in summary

    def test_expired_size_calculated(self, analyze_handler, collect_output):
        """期限切れスナップショットの合計サイズが計算される."""
        result = analyze_handler.handler(collect_output, None)

        summary = result["analyses"][0]["summary"]
        assert summary["total_expired_bytes"] > 0
        assert summary["total_expired_gb"] > 0


class TestBedrockDisabled:
    """Bedrock 無効時テスト."""

    def test_ai_summary_none(self, analyze_handler, collect_output):
        """EnableBedrockSummary=false で ai_summary が None."""
        result = analyze_handler.handler(collect_output, None)

        assert result["analyses"][0]["ai_summary"] is None
