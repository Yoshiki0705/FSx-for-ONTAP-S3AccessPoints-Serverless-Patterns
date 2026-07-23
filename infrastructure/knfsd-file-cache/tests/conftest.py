"""KNFSD File Cache integration tests — shared fixtures.

These tests validate KNFSD File Cache behavior when used alongside
FSx for ONTAP S3 Access Points. They require a deployed KNFSD cluster
and access to the FSx for ONTAP environment.

Run:
    # Unit tests (mocked, no infra required)
    python3 -m pytest infrastructure/knfsd-file-cache/tests/ -v -m "not integration"

    # Integration tests (requires deployed KNFSD + FSx for ONTAP)
    python3 -m pytest infrastructure/knfsd-file-cache/tests/ -v -m integration

Environment variables (for integration tests):
    KNFSD_IP              - KNFSD proxy private IP
    KNFSD_INSTANCE_ID     - KNFSD EC2 instance ID
    KNFSD_EXPORT_PATH     - NFS re-export path (e.g., /srv/nfs/vol1)
    S3AP_ALIAS            - S3 Access Point alias for the same volume
    FSXN_FILE_SYSTEM_ID   - FSx for ONTAP file system ID
    CLIENT_INSTANCE_ID    - EC2 instance ID for client-side tests (SSM)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add project root to path for shared module access
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "shared"))


# =============================================================================
# Environment Configuration
# =============================================================================


@pytest.fixture
def knfsd_config():
    """KNFSD cluster configuration from environment or defaults."""
    return {
        "knfsd_ip": os.environ.get("KNFSD_IP", "10.0.1.100"),
        "knfsd_instance_id": os.environ.get("KNFSD_INSTANCE_ID", "i-0test123"),
        "export_path": os.environ.get("KNFSD_EXPORT_PATH", "/srv/nfs/vol1"),
        "s3ap_alias": os.environ.get("S3AP_ALIAS", "test-ap-alias-s3alias"),
        "fsxn_file_system_id": os.environ.get("FSXN_FILE_SYSTEM_ID", "fs-0test123"),
        "client_instance_id": os.environ.get("CLIENT_INSTANCE_ID", ""),
        "region": os.environ.get("AWS_REGION", "ap-northeast-1"),
    }


@pytest.fixture
def is_integration():
    """Check if integration test environment is available."""
    return bool(os.environ.get("KNFSD_IP"))


# =============================================================================
# AWS Client Fixtures
# =============================================================================


@pytest.fixture
def boto3_session():
    """Boto3 session for integration tests."""
    try:
        import boto3
        return boto3.Session(region_name=os.environ.get("AWS_REGION", "ap-northeast-1"))
    except ImportError:
        pytest.skip("boto3 not available")


@pytest.fixture
def s3_client(boto3_session):
    """S3 client for S3 AP access."""
    return boto3_session.client("s3")


@pytest.fixture
def ec2_client(boto3_session):
    """EC2 client for instance queries."""
    return boto3_session.client("ec2")


@pytest.fixture
def ssm_client(boto3_session):
    """SSM client for remote command execution."""
    return boto3_session.client("ssm")


@pytest.fixture
def cloudwatch_client(boto3_session):
    """CloudWatch client for metrics queries."""
    return boto3_session.client("cloudwatch")


@pytest.fixture
def fsx_client(boto3_session):
    """FSx client for file system queries."""
    return boto3_session.client("fsx")


# =============================================================================
# Mock Fixtures (for unit tests without deployed infrastructure)
# =============================================================================


@pytest.fixture
def mock_ssm_response():
    """Mock SSM command response for unit tests."""
    return {
        "Command": {"CommandId": "cmd-test123"},
        "StandardOutputContent": "test output\n",
        "StandardErrorContent": "",
        "Status": "Success",
    }


@pytest.fixture
def mock_nfs_mount_output():
    """Mock NFS mount command output."""
    return "10.0.1.50:/vol1 on /srv/nfs/vol1 type nfs (rw,vers=3,hard,intr)"


@pytest.fixture
def mock_exportfs_output():
    """Mock exportfs -v output."""
    return "/srv/nfs/vol1\t*(rw,sync,no_subtree_check,crossmnt,fsid=1)"


# =============================================================================
# Pytest Markers
# =============================================================================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "integration: requires deployed KNFSD infrastructure")
    config.addinivalue_line("markers", "dual_path: tests KNFSD + S3 AP simultaneous access")
    config.addinivalue_line("markers", "benchmark: performance benchmark tests (slow)")
