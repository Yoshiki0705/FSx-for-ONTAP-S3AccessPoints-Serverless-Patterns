"""Unit tests for resource-management Lambda handler.

Tests use a mock ONTAP REST API (patched urllib3) to verify:
- Volume CRUD operations
- Export Policy rule management
- QoS policy operations
- SnapLock configuration reads and retention updates
- Input validation (volume names, sizes, confirmations)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add handler to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set required env vars before import
os.environ["ONTAP_MGMT_IP"] = "10.0.0.1"
os.environ["ONTAP_SECRET_NAME"] = "test/secret"
os.environ["SVM_NAME"] = "svm1"


class MockResponse:
    """Mock urllib3 response."""

    def __init__(self, status: int, data: dict):
        self.status = status
        self.data = json.dumps(data).encode()


class MockHttp:
    """Mock urllib3 PoolManager that records calls."""

    def __init__(self, responses: dict | None = None):
        self._responses = responses or {}
        self.calls: list[tuple] = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        # Match by URL suffix
        for pattern, resp in self._responses.items():
            if pattern in url:
                return MockResponse(resp.get("status", 200), resp.get("data", {}))
        return MockResponse(200, {"records": [], "num_records": 0})


@pytest.fixture
def mock_secrets():
    """Patch Secrets Manager."""
    with patch("handler.boto3") as mock_boto3:
        mock_sm = MagicMock()
        mock_sm.get_secret_value.return_value = {
            "SecretString": json.dumps({"username": "fsxadmin", "password": "test"})
        }
        mock_boto3.client.return_value = mock_sm
        yield mock_sm


@pytest.fixture
def mock_http():
    """Create a MockHttp instance."""
    return MockHttp()


# --- Volume Tests ---


class TestListVolumes:
    def test_returns_volumes(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp({
                "/storage/volumes": {
                    "status": 200,
                    "data": {
                        "records": [
                            {"name": "vol1", "uuid": "uuid-1", "size": 107374182400,
                             "state": "online", "type": "rw", "style": "flexvol",
                             "nas": {"security_style": "unix"},
                             "space": {"used": 53687091200},
                             "snaplock": {"type": "non_snaplock"}},
                        ],
                        "num_records": 1,
                    },
                },
            })

            result = handler({"action": "listVolumes"}, None)

        assert result["error"] is None
        assert result["count"] == 1
        assert result["volumes"][0]["name"] == "vol1"
        assert result["volumes"][0]["sizeGiB"] == 100.0
        assert result["volumes"][0]["usedPercent"] == 50.0
        assert result["volumes"][0]["securityStyle"] == "unix"


class TestCreateVolume:
    def test_validates_name_format(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()

            # Hyphens not allowed
            result = handler({"action": "createVolume", "name": "bad-name", "sizeGiB": 100}, None)
            assert result["success"] is False
            assert "alphanumeric" in result["error"]

    def test_validates_name_required(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()

            result = handler({"action": "createVolume", "name": "", "sizeGiB": 100}, None)
            assert result["success"] is False
            assert "required" in result["error"]

    def test_validates_size_positive(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()

            result = handler({"action": "createVolume", "name": "vol1", "sizeGiB": 0}, None)
            assert result["success"] is False
            assert "Size" in result["error"]

    def test_success_creates_volume(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp({
                "/storage/volumes": {"status": 202, "data": {}},
            })

            result = handler({"action": "createVolume", "name": "test_vol", "sizeGiB": 50}, None)

        assert result["success"] is True
        assert result["volumeName"] == "test_vol"


class TestDeleteVolume:
    def test_requires_confirm(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()

            result = handler({
                "action": "deleteVolume", "volumeUuid": "uuid-1",
                "volumeName": "vol1", "confirm": False,
            }, None)

        assert result["success"] is False
        assert "confirm" in result["error"]

    def test_requires_uuid(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()

            result = handler({
                "action": "deleteVolume", "volumeUuid": "",
                "volumeName": "vol1", "confirm": True,
            }, None)

        assert result["success"] is False
        assert "volumeUuid" in result["error"]


class TestResizeVolume:
    def test_validates_inputs(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()

            result = handler({"action": "resizeVolume", "volumeUuid": "", "newSizeGiB": 200}, None)
            assert result["success"] is False

            result = handler({"action": "resizeVolume", "volumeUuid": "uuid-1", "newSizeGiB": 0}, None)
            assert result["success"] is False


# --- Export Policy Tests ---


class TestExportPolicies:
    def test_list_policies(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp({
                "/protocols/nfs/export-policies": {
                    "status": 200,
                    "data": {"records": [{"id": 1, "name": "default", "rules": [{}]}]},
                },
            })

            result = handler({"action": "listExportPolicies"}, None)

        assert result["error"] is None
        assert len(result["policies"]) == 1
        assert result["policies"][0]["name"] == "default"

    def test_create_rule_requires_fields(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()

            result = handler({
                "action": "createExportPolicyRule",
                "policyId": "", "clientMatch": "10.0.0.0/16",
            }, None)
            assert result["success"] is False

            result = handler({
                "action": "createExportPolicyRule",
                "policyId": "42", "clientMatch": "",
            }, None)
            assert result["success"] is False


# --- QoS Policy Tests ---


class TestQosPolicies:
    def test_list_qos(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp({
                "/storage/qos/policies": {
                    "status": 200,
                    "data": {"records": [
                        {"name": "gold", "uuid": "q-1", "fixed": {"max_throughput_iops": 10000}, "adaptive": {}},
                    ]},
                },
            })

            result = handler({"action": "listQosPolicies"}, None)

        assert result["error"] is None
        assert len(result["policies"]) == 1
        assert result["policies"][0]["name"] == "gold"

    def test_create_fixed_requires_limits(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()

            result = handler({
                "action": "createQosPolicy", "name": "test",
                "policyType": "fixed",
            }, None)

        assert result["success"] is False
        assert "maxIops" in result["error"] or "required" in result["error"]

    def test_create_adaptive_requires_iops(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()

            result = handler({
                "action": "createQosPolicy", "name": "test",
                "policyType": "adaptive",
            }, None)

        assert result["success"] is False
        assert "expectedIops" in result["error"]


# --- SnapLock Tests ---


class TestSnaplock:
    def test_get_config_requires_volume(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()

            result = handler({"action": "getSnaplockConfig"}, None)

        assert result["config"] is None
        assert "required" in result["error"]

    def test_update_retention_validates_days(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()

            result = handler({
                "action": "updateSnaplockRetention",
                "volumeUuid": "uuid-1", "days": 0,
            }, None)

        assert result["success"] is False
        assert "days" in result["error"]


# --- Error Handling ---


class TestErrorHandling:
    def test_missing_ontap_config(self, mock_secrets):
        from handler import handler

        # Temporarily clear env
        orig = os.environ.get("ONTAP_MGMT_IP")
        os.environ["ONTAP_MGMT_IP"] = ""
        try:
            result = handler({"action": "listVolumes"}, None)
            assert "error" in result
            assert "not configured" in result["error"]
        finally:
            os.environ["ONTAP_MGMT_IP"] = orig or "10.0.0.1"

    def test_unknown_action(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()
            result = handler({"action": "unknownAction"}, None)

        assert "Unknown action" in result["error"]
