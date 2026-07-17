"""OPS5 Cost Optimization conftest."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
FUNCTIONS_DIR = Path(__file__).parent.parent / "functions"


@pytest.fixture(autouse=True)
def ops5_env(monkeypatch):
    monkeypatch.setenv("FILE_SYSTEM_IDS", "fs-test01")
    monkeypatch.setenv("ONTAP_SECRET_ARN", "")
    monkeypatch.setenv("AUTOMATION_LEVEL", "0")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("ENABLE_BEDROCK_SUMMARY", "false")
    monkeypatch.setenv("REPORT_FORMAT", "JSON")
    monkeypatch.setenv("REPORT_BUCKET", "test-bucket")
    monkeypatch.setenv("ALERT_TOPIC_ARN", "")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")


@pytest.fixture
def collect_handler():
    spec = importlib.util.spec_from_file_location("ops5_collect", FUNCTIONS_DIR / "collect" / "handler.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["ops5_collect"] = m
    spec.loader.exec_module(m)
    return m


@pytest.fixture
def analyze_handler():
    spec = importlib.util.spec_from_file_location("ops5_analyze", FUNCTIONS_DIR / "analyze" / "handler.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["ops5_analyze"] = m
    spec.loader.exec_module(m)
    return m


@pytest.fixture
def report_handler():
    spec = importlib.util.spec_from_file_location("ops5_report", FUNCTIONS_DIR / "report" / "handler.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["ops5_report"] = m
    spec.loader.exec_module(m)
    return m
