"""OPS1 Capacity Rightsizing テスト用 conftest.

sys.path にプロジェクトルートと functions ディレクトリを追加し、
共通フィクスチャを定義する。

Note: 各テストファイルでは importlib を使って正しい handler をロードする。
      sys.path に複数の handler.py がある問題を回避するため。
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Project root
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Base path for function directories
FUNCTIONS_DIR = Path(__file__).parent.parent / "functions"


@pytest.fixture(autouse=True)
def ops1_env_vars(monkeypatch):
    """Standard environment variables for OPS1 tests."""
    monkeypatch.setenv("FILE_SYSTEM_IDS", "fs-test01")
    monkeypatch.setenv("ONTAP_SECRET_ARN", "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:test")
    monkeypatch.setenv("AUTOMATION_LEVEL", "0")
    monkeypatch.setenv("THRESHOLD_PERCENT", "80")
    monkeypatch.setenv("LOW_UTILIZATION_THRESHOLD_PERCENT", "20")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("ENABLE_BEDROCK_SUMMARY", "false")
    monkeypatch.setenv("REPORT_FORMAT", "JSON")
    monkeypatch.setenv("REPORT_BUCKET", "test-report-bucket")
    monkeypatch.setenv("ALERT_TOPIC_ARN", "")
    monkeypatch.setenv("POWERTOOLS_SERVICE_NAME", "test-ops1")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")


@pytest.fixture
def collect_handler():
    """Import collect handler module dynamically."""
    spec = importlib.util.spec_from_file_location("collect_handler", FUNCTIONS_DIR / "collect" / "handler.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["collect_handler"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def analyze_handler():
    """Import analyze handler module dynamically."""
    spec = importlib.util.spec_from_file_location("analyze_handler", FUNCTIONS_DIR / "analyze" / "handler.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["analyze_handler"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def report_handler():
    """Import report handler module dynamically."""
    spec = importlib.util.spec_from_file_location("report_handler", FUNCTIONS_DIR / "report" / "handler.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["report_handler"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def mock_volume_space_data():
    """Volume space mock data from test-data/ops/."""
    fixture_path = PROJECT_ROOT / "test-data" / "ops" / "volume_space.json"
    with open(fixture_path) as f:
        return json.load(f)


@pytest.fixture
def mock_aggregate_space_data():
    """Aggregate space mock data from test-data/ops/."""
    fixture_path = PROJECT_ROOT / "test-data" / "ops" / "aggregate_space.json"
    with open(fixture_path) as f:
        return json.load(f)


@pytest.fixture
def mock_cloudwatch_data():
    """CloudWatch metrics mock data from test-data/ops/."""
    fixture_path = PROJECT_ROOT / "test-data" / "ops" / "cloudwatch_metrics.json"
    with open(fixture_path) as f:
        return json.load(f)


@pytest.fixture
def collect_output(mock_volume_space_data, mock_aggregate_space_data, mock_cloudwatch_data):
    """Simulated output from Collect Lambda (input to Analyze)."""
    for vol in mock_volume_space_data:
        vol["fs_id"] = "fs-test01"
    for aggr in mock_aggregate_space_data:
        aggr["fs_id"] = "fs-test01"
    mock_cloudwatch_data["fs_id"] = "fs-test01"

    return {
        "file_systems": [
            {
                "fs_id": "fs-test01",
                "volumes": mock_volume_space_data,
                "aggregates": mock_aggregate_space_data,
                "cloudwatch": mock_cloudwatch_data,
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
                "recommendations": [
                    {
                        "fs_id": "fs-test01",
                        "recommendation_type": "upsize",
                        "target": "vol_production_data",
                        "current_value": "85.0% (1024 GB)",
                        "recommended_value": "Enable autosize (grow)",
                        "reason": "Volume at 85% utilization, autosize disabled.",
                        "monthly_cost_delta_usd": 25.60,
                        "confidence": 0.70,
                        "automation_action": "volume_autosize_enable",
                    },
                    {
                        "fs_id": "fs-test01",
                        "recommendation_type": "upsize",
                        "target": "vol_analytics_staging",
                        "current_value": "90.0% (256 GB)",
                        "recommended_value": "Expand +51 GB",
                        "reason": "Volume at 90% utilization.",
                        "monthly_cost_delta_usd": 6.40,
                        "confidence": 0.85,
                        "automation_action": None,
                    },
                ],
                "what_if_scenarios": [
                    {
                        "fs_id": "fs-test01",
                        "scenario_name": "Upgrade to 256 MBps",
                        "current_monthly_cost_usd": 47.36,
                        "projected_monthly_cost_usd": 94.72,
                        "monthly_delta_usd": 47.36,
                        "description": "Throughput tier change: 128 → 256 MBps.",
                    },
                ],
                "summary_stats": {
                    "total_volumes": 5,
                    "volumes_above_threshold": 2,
                    "volumes_below_low_threshold": 1,
                    "avg_volume_utilization_percent": 57.0,
                    "max_volume_utilization_percent": 90.0,
                    "throughput_utilization_percent": 62.5,
                    "recommendation_count": 2,
                    "total_monthly_cost_delta_usd": 32.0,
                },
                "ai_summary": None,
                "analyzed_at": "2026-07-13T00:01:00+00:00",
            }
        ],
        "total_recommendations": 2,
        "analyzed_at": "2026-07-13T00:01:00+00:00",
    }
