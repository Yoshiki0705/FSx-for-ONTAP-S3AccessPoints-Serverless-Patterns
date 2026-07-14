"""OPS4 Snapshot Lifecycle テスト用 conftest."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

FUNCTIONS_DIR = Path(__file__).parent.parent / "functions"


@pytest.fixture(autouse=True)
def ops4_env_vars(monkeypatch):
    """Standard environment variables for OPS4 tests."""
    monkeypatch.setenv("FILE_SYSTEM_IDS", "fs-test01")
    monkeypatch.setenv("ONTAP_SECRET_ARN", "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:test")
    monkeypatch.setenv("AUTOMATION_LEVEL", "0")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("ENABLE_BEDROCK_SUMMARY", "false")
    monkeypatch.setenv("REPORT_FORMAT", "JSON")
    monkeypatch.setenv("REPORT_BUCKET", "test-report-bucket")
    monkeypatch.setenv("ALERT_TOPIC_ARN", "")
    monkeypatch.setenv("RETENTION_POLICY", "CUSTOM")
    monkeypatch.setenv("MAX_RETENTION_DAYS", "90")
    monkeypatch.setenv("MIN_RETENTION_DAYS", "7")
    monkeypatch.setenv("SNAPSHOT_RESERVE_WARNING_PERCENT", "80")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")


@pytest.fixture
def collect_handler():
    """Import collect handler module dynamically."""
    spec = importlib.util.spec_from_file_location(
        "ops4_collect_handler", FUNCTIONS_DIR / "collect" / "handler.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["ops4_collect_handler"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def analyze_handler():
    """Import analyze handler module dynamically."""
    spec = importlib.util.spec_from_file_location(
        "ops4_analyze_handler", FUNCTIONS_DIR / "analyze" / "handler.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["ops4_analyze_handler"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def report_handler():
    """Import report handler module dynamically."""
    spec = importlib.util.spec_from_file_location(
        "ops4_report_handler", FUNCTIONS_DIR / "report" / "handler.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["ops4_report_handler"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def collect_output():
    """Simulated output from Collect Lambda (input to Analyze)."""
    return {
        "file_systems": [
            {
                "fs_id": "fs-test01",
                "volume_snapshots": [
                    {
                        "volume_name": "vol_production_data",
                        "volume_uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "snapshot_count": 5,
                        "snapshots": [
                            {"snapshot_name": "daily.2026-07-12_0010", "snapshot_uuid": "s1", "create_time": "2026-07-12T00:10:00+00:00", "size_bytes": 1073741824, "age_days": 1, "volume_name": "vol_production_data", "volume_uuid": "a1b2c3d4", "fs_id": "fs-test01"},
                            {"snapshot_name": "daily.2026-07-11_0010", "snapshot_uuid": "s2", "create_time": "2026-07-11T00:10:00+00:00", "size_bytes": 1073741824, "age_days": 2, "volume_name": "vol_production_data", "volume_uuid": "a1b2c3d4", "fs_id": "fs-test01"},
                            {"snapshot_name": "weekly.2026-07-06_0015", "snapshot_uuid": "s3", "create_time": "2026-07-06T00:15:00+00:00", "size_bytes": 5368709120, "age_days": 7, "volume_name": "vol_production_data", "volume_uuid": "a1b2c3d4", "fs_id": "fs-test01"},
                            {"snapshot_name": "weekly.2026-03-01_0015", "snapshot_uuid": "s4", "create_time": "2026-03-01T00:15:00+00:00", "size_bytes": 10737418240, "age_days": 134, "volume_name": "vol_production_data", "volume_uuid": "a1b2c3d4", "fs_id": "fs-test01"},
                            {"snapshot_name": "manual_before_migration", "snapshot_uuid": "s5", "create_time": "2025-12-15T10:30:00+00:00", "size_bytes": 21474836480, "age_days": 210, "volume_name": "vol_production_data", "volume_uuid": "a1b2c3d4", "fs_id": "fs-test01"},
                        ],
                    },
                    {
                        "volume_name": "vol_archive_2023",
                        "volume_uuid": "c3d4e5f6-a7b8-9012-cdef-123456789012",
                        "snapshot_count": 2,
                        "snapshots": [
                            {"snapshot_name": "daily.2026-07-12_0010", "snapshot_uuid": "s6", "create_time": "2026-07-12T00:10:00+00:00", "size_bytes": 2147483648, "age_days": 1, "volume_name": "vol_archive_2023", "volume_uuid": "c3d4e5f6", "fs_id": "fs-test01"},
                            {"snapshot_name": "yearly_2024", "snapshot_uuid": "s7", "create_time": "2025-01-01T00:00:00+00:00", "size_bytes": 53687091200, "age_days": 559, "volume_name": "vol_archive_2023", "volume_uuid": "c3d4e5f6", "fs_id": "fs-test01"},
                        ],
                    },
                ],
                "snapshot_policies": [
                    {
                        "name": "default",
                        "uuid": "policy-001",
                        "enabled": True,
                        "schedules": [
                            {"schedule": "daily", "count": 7},
                            {"schedule": "weekly", "count": 4},
                        ],
                    },
                ],
                "collected_at": "2026-07-13T00:00:00+00:00",
            }
        ],
        "collected_at": "2026-07-13T00:00:00+00:00",
        "demo_mode": True,
    }


@pytest.fixture
def analyze_output():
    """Simulated output from Analyze Lambda (input to Report)."""
    return {
        "analyses": [
            {
                "fs_id": "fs-test01",
                "volume_audits": [
                    {
                        "fs_id": "fs-test01",
                        "volume_name": "vol_production_data",
                        "volume_uuid": "a1b2c3d4",
                        "total_snapshots": 5,
                        "total_size_bytes": 39728447488,
                        "oldest_snapshot_age_days": 210,
                        "retention_compliant": False,
                        "expired_snapshots": [
                            {"snapshot_name": "weekly.2026-03-01_0015", "age_days": 134, "size_bytes": 10737418240},
                            {"snapshot_name": "manual_before_migration", "age_days": 210, "size_bytes": 21474836480},
                        ],
                        "expired_count": 2,
                        "protected_count": 2,
                        "compliant_count": 1,
                        "policy_drift_detected": False,
                        "policy_drift_details": "",
                    },
                    {
                        "fs_id": "fs-test01",
                        "volume_name": "vol_archive_2023",
                        "volume_uuid": "c3d4e5f6",
                        "total_snapshots": 2,
                        "total_size_bytes": 55834574848,
                        "oldest_snapshot_age_days": 559,
                        "retention_compliant": False,
                        "expired_snapshots": [
                            {"snapshot_name": "yearly_2024", "age_days": 559, "size_bytes": 53687091200},
                        ],
                        "expired_count": 1,
                        "protected_count": 1,
                        "compliant_count": 0,
                        "policy_drift_detected": False,
                        "policy_drift_details": "",
                    },
                ],
                "summary": {
                    "total_volumes_scanned": 2,
                    "total_snapshots_scanned": 7,
                    "total_expired_snapshots": 3,
                    "total_expired_bytes": 85899345920,
                    "total_expired_gb": 79.97,
                    "volumes_with_drift": 0,
                    "retention_policy": "CUSTOM",
                    "effective_max_retention_days": 90,
                    "min_retention_days": 7,
                },
                "ai_summary": None,
                "analyzed_at": "2026-07-13T00:01:00+00:00",
            }
        ],
        "total_expired_snapshots": 3,
        "analyzed_at": "2026-07-13T00:01:00+00:00",
    }
