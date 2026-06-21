"""HA LifeKeeper Monitoring — Test Configuration

sys.path の設定と共通フィクスチャ。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# sys.path: repo root + discovery function only
# (each test file imports from its specific function directory)
# tests → lifekeeper-monitoring → ha → solutions → root (5 levels)
REPO_ROOT = str(Path(__file__).parent.parent.parent.parent.parent)
DISCOVERY_DIR = str(Path(__file__).parent.parent / "functions" / "discovery")
PROCESSING_DIR = str(Path(__file__).parent.parent / "functions" / "processing")
REPORT_DIR = str(Path(__file__).parent.parent / "functions" / "report")

# Only add repo root by default; test files manage function-specific paths
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


@pytest.fixture(autouse=True)
def env_vars():
    """テスト用環境変数を設定する"""
    env = {
        "S3_ACCESS_POINT_ALIAS": "test-s3ap-alias",
        "FILE_PREFIX": "lifekeeper/logs/",
        "MAX_FILES": "50",
        "CLUSTER_NAME": "test-cluster",
        "OUTPUT_BUCKET": "test-output-bucket",
        "BEDROCK_MODEL_ID": "amazon.nova-pro-v1:0",
        "FAILOVER_ALERT_SEVERITY": "CRITICAL",
        "SNS_TOPIC_ARN": "arn:aws:sns:ap-northeast-1:123456789012:test-topic",
        "DEMO_MODE": "true",
    }
    with patch.dict(os.environ, env):
        yield env


@pytest.fixture
def sample_discovery_output():
    """Discovery Lambda の出力サンプル"""
    return {
        "status": "completed",
        "object_count": 5,
        "objects": [
            {
                "key": "lifekeeper/logs/failover-2025-06-20.log",
                "size": 15000,
                "last_modified": "2025-06-20T10:30:00+00:00",
                "category": "failover_event",
                "severity": "CRITICAL",
                "cluster_name": "test-cluster",
            },
            {
                "key": "lifekeeper/logs/health-check.log",
                "size": 8000,
                "last_modified": "2025-06-20T10:25:00+00:00",
                "category": "health_check",
                "severity": "MEDIUM",
                "cluster_name": "test-cluster",
            },
            {
                "key": "lifekeeper/logs/comm-path-status.log",
                "size": 3000,
                "last_modified": "2025-06-20T10:20:00+00:00",
                "category": "communication_log",
                "severity": "LOW",
                "cluster_name": "test-cluster",
            },
            {
                "key": "lifekeeper/logs/sap-recovery-kit.log",
                "size": 12000,
                "last_modified": "2025-06-20T10:15:00+00:00",
                "category": "recovery_kit_log",
                "severity": "HIGH",
                "cluster_name": "test-cluster",
            },
            {
                "key": "lifekeeper/logs/lifekeeper.log",
                "size": 50000,
                "last_modified": "2025-06-20T10:10:00+00:00",
                "category": "general_log",
                "severity": "LOW",
                "cluster_name": "test-cluster",
            },
        ],
        "failover_events": [
            {
                "key": "lifekeeper/logs/failover-2025-06-20.log",
                "size": 15000,
                "last_modified": "2025-06-20T10:30:00+00:00",
                "category": "failover_event",
                "severity": "CRITICAL",
                "cluster_name": "test-cluster",
            },
        ],
        "failover_event_count": 1,
        "category_summary": {
            "failover_event": 1,
            "health_check": 1,
            "communication_log": 1,
            "recovery_kit_log": 1,
            "general_log": 1,
        },
        "prefix": "lifekeeper/logs/",
        "cluster_name": "test-cluster",
        "timestamp": 1750412400,
    }


@pytest.fixture
def sample_processing_output():
    """Processing Lambda の出力サンプル"""
    return {
        "status": "completed",
        "cluster_name": "test-cluster",
        "health_score": {
            "score": 70,
            "level": "WARNING",
            "failover_count": 1,
            "deduction_breakdown": {
                "failover_events": 30,
                "total_deducted": 30,
            },
        },
        "failover_analyses": [
            {
                "file": "lifekeeper/logs/failover-2025-06-20.log",
                "indicators_found": [
                    {"indicator": "FAILOVER", "line": "2025-06-20 10:30:01 FAILOVER initiated for resource sap-app"},
                ],
                "state_transitions": [
                    {"state": "ISP→OSF", "description": "Primary failure detected"},
                    {"state": "ISS→ISP", "description": "Failover completed (secondary promoted)"},
                ],
                "indicator_count": 1,
                "severity": "CRITICAL",
                "last_modified": "2025-06-20T10:30:00+00:00",
            }
        ],
        "root_cause_analysis": {
            "analysis": "Demo mode: Root cause analysis skipped.",
            "recommendations": [
                "Check LifeKeeper communication paths between cluster nodes.",
                "Verify NFS/iSCSI mount points on FSx for ONTAP volumes.",
                "Review Recovery Kit configuration for protected applications.",
            ],
            "model_id": "amazon.nova-pro-v1:0",
            "demo_mode": True,
        },
        "log_summary": {
            "category_counts": {
                "failover_event": 1,
                "health_check": 1,
                "communication_log": 1,
                "recovery_kit_log": 1,
                "general_log": 1,
            },
            "severity_counts": {
                "CRITICAL": 1,
                "HIGH": 1,
                "MEDIUM": 1,
                "LOW": 2,
            },
            "total_files": 5,
            "total_size_bytes": 88000,
        },
        "processed_count": 5,
        "failover_count": 1,
        "timestamp": 1750412400,
    }
