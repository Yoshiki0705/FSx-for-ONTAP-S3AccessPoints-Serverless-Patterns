"""OPS2 Storage Efficiency conftest."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
FUNCTIONS_DIR = Path(__file__).parent.parent / "functions"


@pytest.fixture(autouse=True)
def ops2_env(monkeypatch):
    monkeypatch.setenv("FILE_SYSTEM_IDS", "fs-test01")
    monkeypatch.setenv("ONTAP_SECRET_ARN", "")
    monkeypatch.setenv("AUTOMATION_LEVEL", "0")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("ENABLE_BEDROCK_SUMMARY", "false")
    monkeypatch.setenv("REPORT_FORMAT", "JSON")
    monkeypatch.setenv("REPORT_BUCKET", "test-bucket")
    monkeypatch.setenv("ALERT_TOPIC_ARN", "")
    monkeypatch.setenv("MIN_EFFICIENCY_RATIO", "1.5")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")


@pytest.fixture
def collect_handler():
    spec = importlib.util.spec_from_file_location("ops2_collect", FUNCTIONS_DIR / "collect" / "handler.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["ops2_collect"] = m
    spec.loader.exec_module(m)
    return m


@pytest.fixture
def analyze_handler():
    spec = importlib.util.spec_from_file_location("ops2_analyze", FUNCTIONS_DIR / "analyze" / "handler.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["ops2_analyze"] = m
    spec.loader.exec_module(m)
    return m


@pytest.fixture
def report_handler():
    spec = importlib.util.spec_from_file_location("ops2_report", FUNCTIONS_DIR / "report" / "handler.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["ops2_report"] = m
    spec.loader.exec_module(m)
    return m


@pytest.fixture
def collect_output():
    return {
        "file_systems": [
            {
                "fs_id": "fs-test01",
                "volumes": [
                    {
                        "name": "vol_prod",
                        "uuid": "u1",
                        "svm_name": "svm1",
                        "dedupe_enabled": True,
                        "compression_enabled": True,
                        "dedupe_savings_bytes": 214748364800,
                        "compression_savings_bytes": 107374182400,
                        "overall_ratio": 2.1,
                        "logical_used_bytes": 1963268506009,
                        "physical_used_bytes": 934584532377,
                        "fs_id": "fs-test01",
                    },
                    {
                        "name": "vol_dev",
                        "uuid": "u2",
                        "svm_name": "svm1",
                        "dedupe_enabled": False,
                        "compression_enabled": False,
                        "dedupe_savings_bytes": 0,
                        "compression_savings_bytes": 0,
                        "overall_ratio": 1.0,
                        "logical_used_bytes": 109951162778,
                        "physical_used_bytes": 109951162778,
                        "fs_id": "fs-test01",
                    },
                    {
                        "name": "vol_archive",
                        "uuid": "u3",
                        "svm_name": "svm1",
                        "dedupe_enabled": True,
                        "compression_enabled": True,
                        "dedupe_savings_bytes": 549755813888,
                        "compression_savings_bytes": 274877906944,
                        "overall_ratio": 3.2,
                        "logical_used_bytes": 5629499534214,
                        "physical_used_bytes": 1759218604442,
                        "fs_id": "fs-test01",
                    },
                ],
                "collected_at": "2026-07-13T00:00:00+00:00",
            }
        ],
        "collected_at": "2026-07-13T00:00:00+00:00",
        "demo_mode": True,
    }
