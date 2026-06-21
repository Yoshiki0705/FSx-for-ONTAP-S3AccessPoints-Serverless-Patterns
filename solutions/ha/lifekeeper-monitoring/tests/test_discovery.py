"""HA LifeKeeper Monitoring — Discovery Lambda Unit Tests

pytest + hypothesis による Discovery Lambda のテスト。
LifeKeeper ログファイルの分類・重要度評価ロジックを検証する。
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# Add discovery function dir to sys.path for direct import
_discovery_dir = str(Path(__file__).parent.parent / "functions" / "discovery")
if _discovery_dir not in sys.path:
    sys.path.insert(0, _discovery_dir)

import handler as discovery_handler  # noqa: E402
from handler import (  # noqa: E402
    FAILOVER_KEYWORDS,
    HEALTH_KEYWORDS,
    LIFEKEEPER_PATTERNS,
    _assess_severity,
    _categorize_lifekeeper_file,
    handler,
)


# ============================================================
# Unit Tests: _categorize_lifekeeper_file
# ============================================================
class TestCategorizeLifekeeperFile:
    """LifeKeeper ファイル分類ロジックのテスト"""

    @pytest.mark.parametrize(
        "key,expected_category",
        [
            ("lifekeeper/logs/failover-2025-06-20.log", "failover_event"),
            ("var/log/lifekeeper/switchover-event.json", "failover_event"),
            ("ha-cluster/events/takeover-node2.evt", "failover_event"),
            ("lifekeeper/logs/recovery-20250620.log", "failover_event"),
            ("lifekeeper/logs/fault-detection.log", "failover_event"),
            ("lifekeeper/logs/alarm-triggered.log", "failover_event"),
        ],
    )
    def test_failover_events_detected(self, key: str, expected_category: str):
        """フェイルオーバー関連キーワードを含むファイルが正しく分類される"""
        assert _categorize_lifekeeper_file(key) == expected_category

    @pytest.mark.parametrize(
        "key,expected_category",
        [
            ("lifekeeper/logs/health-check.log", "health_check"),
            ("lifekeeper/logs/heartbeat-status.log", "health_check"),
            ("ha-cluster/monitor/canary-check.csv", "health_check"),
            ("lifekeeper/logs/status-report.json", "health_check"),
        ],
    )
    def test_health_check_detected(self, key: str, expected_category: str):
        """ヘルスチェック関連ファイルが正しく分類される"""
        assert _categorize_lifekeeper_file(key) == expected_category

    @pytest.mark.parametrize(
        "key,expected_category",
        [
            ("lifekeeper/config/resources.xml", "cluster_config"),
            ("opt/LifeKeeper/config/hierarchy.conf", "cluster_config"),
            ("lifekeeper/logs/resource-dependency.cfg", "cluster_config"),
        ],
    )
    def test_config_detected(self, key: str, expected_category: str):
        """構成ファイルが正しく分類される"""
        assert _categorize_lifekeeper_file(key) == expected_category

    @pytest.mark.parametrize(
        "key,expected_category",
        [
            ("lifekeeper/logs/sap-rkit-output.log", "recovery_kit_log"),
            ("lifekeeper/logs/oracle-db-rkit.log", "recovery_kit_log"),
            ("lifekeeper/logs/mysql-rkit-state.log", "recovery_kit_log"),
        ],
    )
    def test_recovery_kit_detected(self, key: str, expected_category: str):
        """Recovery Kit ログが正しく分類される"""
        assert _categorize_lifekeeper_file(key) == expected_category

    @pytest.mark.parametrize(
        "key,expected_category",
        [
            ("lifekeeper/logs/lcm-comm-only.log", "communication_log"),
            ("lifekeeper/logs/tcp-connection.log", "communication_log"),
        ],
    )
    def test_communication_log_detected(self, key: str, expected_category: str):
        """通信ログが正しく分類される"""
        assert _categorize_lifekeeper_file(key) == expected_category

    def test_general_log_by_extension(self):
        """拡張子ベースで一般ログと判定される"""
        assert _categorize_lifekeeper_file("lifekeeper/logs/system.log") == "general_log"
        assert _categorize_lifekeeper_file("lifekeeper/logs/daemon.log") == "general_log"

    def test_unknown_file(self):
        """分類不能ファイルは 'other' になる"""
        assert _categorize_lifekeeper_file("lifekeeper/data/unknown.dat") == "other"
        assert _categorize_lifekeeper_file("random/path/file.bin") == "other"


# ============================================================
# Unit Tests: _assess_severity
# ============================================================
class TestAssessSeverity:
    """重要度評価ロジックのテスト"""

    def test_failover_is_critical(self):
        """フェイルオーバーイベントは常に CRITICAL"""
        assert _assess_severity("any/path.log", "failover_event") == "CRITICAL"

    def test_health_check_with_error_is_high(self):
        """エラーを含むヘルスチェックは HIGH"""
        assert _assess_severity("path/fail-check.log", "health_check") == "HIGH"
        assert _assess_severity("path/error-health.log", "health_check") == "HIGH"
        assert _assess_severity("path/alarm-triggered.log", "health_check") == "HIGH"

    def test_health_check_normal_is_medium(self):
        """通常のヘルスチェックは MEDIUM"""
        assert _assess_severity("path/normal-check.log", "health_check") == "MEDIUM"

    def test_recovery_kit_is_high(self):
        """Recovery Kit ログは HIGH"""
        assert _assess_severity("path/sap-kit.log", "recovery_kit_log") == "HIGH"

    def test_communication_with_timeout_is_high(self):
        """タイムアウトを含む通信ログは HIGH"""
        assert _assess_severity("path/timeout-comm.log", "communication_log") == "HIGH"
        assert _assess_severity("path/disconnect.log", "communication_log") == "HIGH"

    def test_communication_normal_is_low(self):
        """通常の通信ログは LOW"""
        assert _assess_severity("path/normal-comm.log", "communication_log") == "LOW"

    def test_general_log_is_low(self):
        """一般ログは LOW"""
        assert _assess_severity("path/system.log", "general_log") == "LOW"
        assert _assess_severity("path/other.log", "other") == "LOW"


# ============================================================
# Property-Based Tests: _categorize_lifekeeper_file
# ============================================================
class TestCategorizeProperties:
    """Hypothesis によるプロパティベーステスト"""

    @given(
        keyword=st.sampled_from(sorted(FAILOVER_KEYWORDS)),
        prefix=st.sampled_from(["lifekeeper/logs/", "var/log/", "ha-cluster/"]),
        ext=st.sampled_from([".log", ".json", ".evt", ".csv"]),
    )
    @settings(max_examples=50)
    def test_failover_keywords_always_classified(self, keyword: str, prefix: str, ext: str):
        """フェイルオーバーキーワードを含むパスは必ず failover_event に分類"""
        key = f"{prefix}{keyword}-event{ext}"
        assert _categorize_lifekeeper_file(key) == "failover_event"

    @given(
        keyword=st.sampled_from(sorted(HEALTH_KEYWORDS)),
        prefix=st.sampled_from(["lifekeeper/logs/", "var/log/", "monitoring/"]),
        ext=st.sampled_from([".log", ".json", ".status"]),
    )
    @settings(max_examples=50)
    def test_health_keywords_classified(self, keyword: str, prefix: str, ext: str):
        """ヘルスキーワードを含むパスは health_check に分類"""
        # Note: some health keywords (like "monitor") may also match failover keywords
        # if the path contains both; failover takes priority
        key = f"{prefix}{keyword}-result{ext}"
        category = _categorize_lifekeeper_file(key)
        assert category in ("health_check", "failover_event")

    @given(
        filename=st.text(
            alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="-_./"),
            min_size=5,
            max_size=80,
        )
    )
    @settings(max_examples=100)
    def test_categorize_never_raises(self, filename: str):
        """任意のファイル名で例外が発生しない"""
        result = _categorize_lifekeeper_file(filename)
        assert isinstance(result, str)
        assert len(result) > 0

    @given(
        filename=st.text(
            alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="-_./"),
            min_size=5,
            max_size=80,
        ),
        category=st.sampled_from([
            "failover_event",
            "health_check",
            "cluster_config",
            "recovery_kit_log",
            "communication_log",
            "general_log",
            "event_log",
            "other",
        ]),
    )
    @settings(max_examples=100)
    def test_assess_severity_never_raises(self, filename: str, category: str):
        """任意の入力で _assess_severity が例外を発生しない"""
        result = _assess_severity(filename, category)
        assert result in ("CRITICAL", "HIGH", "MEDIUM", "LOW")


# ============================================================
# Integration Tests: handler function
# ============================================================
class TestDiscoveryHandler:
    """Discovery Lambda ハンドラーの統合テスト"""

    @patch("handler.s3_client")
    def test_handler_successful_discovery(self, mock_s3):
        """正常なファイル検出"""
        mock_s3.list_objects_v2.return_value = {
            "Contents": [
                {
                    "Key": "lifekeeper/logs/failover-2025-06-20.log",
                    "Size": 15000,
                    "LastModified": datetime(2025, 6, 20, 10, 30, 0, tzinfo=timezone.utc),
                },
                {
                    "Key": "lifekeeper/logs/health-check.log",
                    "Size": 8000,
                    "LastModified": datetime(2025, 6, 20, 10, 25, 0, tzinfo=timezone.utc),
                },
                {
                    "Key": "lifekeeper/logs/lifekeeper.log",
                    "Size": 50000,
                    "LastModified": datetime(2025, 6, 20, 10, 10, 0, tzinfo=timezone.utc),
                },
            ],
            "IsTruncated": False,
        }

        result = handler({}, None)

        assert result["status"] == "completed"
        assert result["object_count"] == 3
        assert result["failover_event_count"] == 1
        assert result["cluster_name"] == "test-cluster"
        assert "failover_event" in result["category_summary"]
        assert "health_check" in result["category_summary"]

    @patch("handler.s3_client")
    def test_handler_no_files(self, mock_s3):
        """ファイルが見つからない場合"""
        mock_s3.list_objects_v2.return_value = {
            "Contents": [],
            "IsTruncated": False,
        }

        result = handler({}, None)

        assert result["status"] == "completed"
        assert result["object_count"] == 0
        assert result["failover_event_count"] == 0

    @patch("handler.s3_client")
    def test_handler_s3_error(self, mock_s3):
        """S3 エラー時のハンドリング"""
        mock_s3.list_objects_v2.side_effect = Exception("Access Denied")

        result = handler({}, None)

        assert result["status"] == "error"
        assert "Access Denied" in result["error"]
        assert result["object_count"] == 0

    @patch("handler.s3_client")
    def test_handler_pagination(self, mock_s3):
        """ページネーション処理"""
        mock_s3.list_objects_v2.side_effect = [
            {
                "Contents": [
                    {
                        "Key": f"lifekeeper/logs/log-{i}.log",
                        "Size": 1000,
                        "LastModified": datetime(2025, 6, 20, 10, 0, 0, tzinfo=timezone.utc),
                    }
                    for i in range(3)
                ],
                "IsTruncated": True,
                "NextContinuationToken": "token-1",
            },
            {
                "Contents": [
                    {
                        "Key": f"lifekeeper/logs/log-{i}.log",
                        "Size": 1000,
                        "LastModified": datetime(2025, 6, 20, 10, 0, 0, tzinfo=timezone.utc),
                    }
                    for i in range(3, 5)
                ],
                "IsTruncated": False,
            },
        ]

        result = handler({}, None)

        assert result["status"] == "completed"
        assert result["object_count"] == 5
        assert mock_s3.list_objects_v2.call_count == 2

    @patch("handler.s3_client")
    def test_handler_max_files_respected(self, mock_s3):
        """MAX_FILES 制限が尊重される"""
        import os
        os.environ["MAX_FILES"] = "2"

        mock_s3.list_objects_v2.return_value = {
            "Contents": [
                {
                    "Key": f"lifekeeper/logs/log-{i}.log",
                    "Size": 1000,
                    "LastModified": datetime(2025, 6, 20, 10, 0, 0, tzinfo=timezone.utc),
                }
                for i in range(10)
            ],
            "IsTruncated": False,
        }

        result = handler({}, None)

        assert result["object_count"] <= 2

        # restore
        os.environ["MAX_FILES"] = "50"

    @patch("handler.s3_client")
    def test_failover_events_collected_separately(self, mock_s3):
        """フェイルオーバーイベントが別途集約される"""
        mock_s3.list_objects_v2.return_value = {
            "Contents": [
                {
                    "Key": "lifekeeper/logs/failover-event-1.log",
                    "Size": 5000,
                    "LastModified": datetime(2025, 6, 20, 10, 0, 0, tzinfo=timezone.utc),
                },
                {
                    "Key": "lifekeeper/logs/switchover-event-2.log",
                    "Size": 3000,
                    "LastModified": datetime(2025, 6, 20, 10, 5, 0, tzinfo=timezone.utc),
                },
                {
                    "Key": "lifekeeper/logs/normal.log",
                    "Size": 2000,
                    "LastModified": datetime(2025, 6, 20, 10, 10, 0, tzinfo=timezone.utc),
                },
            ],
            "IsTruncated": False,
        }

        result = handler({}, None)

        assert result["failover_event_count"] == 2
        assert len(result["failover_events"]) == 2
        for fe in result["failover_events"]:
            assert fe["category"] == "failover_event"
            assert fe["severity"] == "CRITICAL"
