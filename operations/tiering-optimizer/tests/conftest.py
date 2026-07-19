"""OPS3 Tiering Optimizer テスト用 conftest."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
FUNCTIONS_DIR = Path(__file__).parent.parent / "functions"


@pytest.fixture(autouse=True)
def ops3_env_vars(monkeypatch):
    monkeypatch.setenv("FILE_SYSTEM_IDS", "fs-test01")
    monkeypatch.setenv("ONTAP_SECRET_ARN", "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:test")
    monkeypatch.setenv("AUTOMATION_LEVEL", "0")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("ENABLE_BEDROCK_SUMMARY", "false")
    monkeypatch.setenv("REPORT_FORMAT", "JSON")
    monkeypatch.setenv("REPORT_BUCKET", "test-report-bucket")
    monkeypatch.setenv("ALERT_TOPIC_ARN", "")
    monkeypatch.setenv("COLD_DATA_THRESHOLD_PERCENT", "30")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")


@pytest.fixture
def collect_handler():
    spec = importlib.util.spec_from_file_location("ops3_collect", FUNCTIONS_DIR / "collect" / "handler.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["ops3_collect"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def analyze_handler():
    spec = importlib.util.spec_from_file_location("ops3_analyze", FUNCTIONS_DIR / "analyze" / "handler.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["ops3_analyze"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def report_handler():
    spec = importlib.util.spec_from_file_location("ops3_report", FUNCTIONS_DIR / "report" / "handler.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["ops3_report"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def collect_output():
    """Simulated Collect output with mixed tiering policies."""
    return {
        "file_systems": [
            {
                "fs_id": "fs-test01",
                "volumes": [
                    {
                        "name": "vol_production_data",
                        "uuid": "u1",
                        "svm_name": "svm-prod",
                        "tiering_policy": "auto",
                        "cooling_period_days": 31,
                        "cloud_storage_used_bytes": 214748364800,
                        "fs_id": "fs-test01",
                    },
                    {
                        "name": "vol_dev_workspace",
                        "uuid": "u2",
                        "svm_name": "svm-dev",
                        "tiering_policy": "none",
                        "cooling_period_days": 31,
                        "cloud_storage_used_bytes": 0,
                        "fs_id": "fs-test01",
                    },
                    {
                        "name": "vol_archive_2023",
                        "uuid": "u3",
                        "svm_name": "svm-prod",
                        "tiering_policy": "snapshot-only",
                        "cooling_period_days": 2,
                        "cloud_storage_used_bytes": 549755813888,
                        "fs_id": "fs-test01",
                    },
                    {
                        "name": "vol_analytics",
                        "uuid": "u4",
                        "svm_name": "svm-analytics",
                        "tiering_policy": "auto",
                        "cooling_period_days": 14,
                        "cloud_storage_used_bytes": 53687091200,
                        "fs_id": "fs-test01",
                    },
                    {
                        "name": "vol_backup_temp",
                        "uuid": "u5",
                        "svm_name": "svm-prod",
                        "tiering_policy": "none",
                        "cooling_period_days": 31,
                        "cloud_storage_used_bytes": 0,
                        "fs_id": "fs-test01",
                    },
                ],
                "collected_at": "2026-07-13T00:00:00+00:00",
            }
        ],
        "collected_at": "2026-07-13T00:00:00+00:00",
        "demo_mode": True,
    }
