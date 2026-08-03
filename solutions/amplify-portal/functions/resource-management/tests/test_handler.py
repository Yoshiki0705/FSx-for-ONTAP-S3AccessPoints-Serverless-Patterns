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
            mock_pool.return_value = MockHttp(
                {
                    "/storage/volumes": {
                        "status": 200,
                        "data": {
                            "records": [
                                {
                                    "name": "vol1",
                                    "uuid": "uuid-1",
                                    "size": 107374182400,
                                    "state": "online",
                                    "type": "rw",
                                    "style": "flexvol",
                                    "nas": {"security_style": "unix"},
                                    "space": {"used": 53687091200},
                                    "snaplock": {"type": "non_snaplock"},
                                },
                            ],
                            "num_records": 1,
                        },
                    },
                }
            )

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
            mock_pool.return_value = MockHttp(
                {
                    "/storage/volumes": {"status": 202, "data": {}},
                }
            )

            result = handler({"action": "createVolume", "name": "test_vol", "sizeGiB": 50}, None)

        assert result["success"] is True
        assert result["volumeName"] == "test_vol"


class TestDeleteVolume:
    def test_requires_confirm(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()

            result = handler(
                {
                    "action": "deleteVolume",
                    "volumeUuid": "uuid-1",
                    "volumeName": "vol1",
                    "confirm": False,
                },
                None,
            )

        assert result["success"] is False
        assert "confirm" in result["error"]

    def test_requires_uuid(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()

            result = handler(
                {
                    "action": "deleteVolume",
                    "volumeUuid": "",
                    "volumeName": "vol1",
                    "confirm": True,
                },
                None,
            )

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
            mock_pool.return_value = MockHttp(
                {
                    "/protocols/nfs/export-policies": {
                        "status": 200,
                        "data": {"records": [{"id": 1, "name": "default", "rules": [{}]}]},
                    },
                }
            )

            result = handler({"action": "listExportPolicies"}, None)

        assert result["error"] is None
        assert len(result["policies"]) == 1
        assert result["policies"][0]["name"] == "default"

    def test_create_rule_requires_fields(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()

            result = handler(
                {
                    "action": "createExportPolicyRule",
                    "policyId": "",
                    "clientMatch": "10.0.0.0/16",
                },
                None,
            )
            assert result["success"] is False

            result = handler(
                {
                    "action": "createExportPolicyRule",
                    "policyId": "42",
                    "clientMatch": "",
                },
                None,
            )
            assert result["success"] is False


# --- QoS Policy Tests ---


class TestQosPolicies:
    def test_list_qos(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp(
                {
                    "/storage/qos/policies": {
                        "status": 200,
                        "data": {
                            "records": [
                                {
                                    "name": "gold",
                                    "uuid": "q-1",
                                    "fixed": {"max_throughput_iops": 10000},
                                    "adaptive": {},
                                },
                            ]
                        },
                    },
                }
            )

            result = handler({"action": "listQosPolicies"}, None)

        assert result["error"] is None
        assert len(result["policies"]) == 1
        assert result["policies"][0]["name"] == "gold"

    def test_create_fixed_requires_limits(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()

            result = handler(
                {
                    "action": "createQosPolicy",
                    "name": "test",
                    "policyType": "fixed",
                },
                None,
            )

        assert result["success"] is False
        assert "maxIops" in result["error"] or "required" in result["error"]

    def test_create_adaptive_requires_iops(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()

            result = handler(
                {
                    "action": "createQosPolicy",
                    "name": "test",
                    "policyType": "adaptive",
                },
                None,
            )

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

            result = handler(
                {
                    "action": "updateSnaplockRetention",
                    "volumeUuid": "uuid-1",
                    "days": 0,
                },
                None,
            )

        assert result["success"] is False
        assert "days" in result["error"]


# --- Error Handling ---


class TestErrorHandling:
    def test_missing_ontap_config(self, mock_secrets):
        import handler as handler_module
        from handler import handler

        # MGMT_IP is read into a module-level constant at import time, so
        # clearing the environment variable here would not affect the handler:
        # it would fall through the guard and attempt a real HTTPS connection to
        # the placeholder address, hanging until the socket timed out. Patch the
        # resolved constant instead so the guard is actually exercised.
        with patch.object(handler_module, "MGMT_IP", ""):
            result = handler({"action": "listVolumes"}, None)

        assert "error" in result
        assert "not configured" in result["error"]

    def test_unknown_action(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()
            result = handler({"action": "unknownAction"}, None)

        assert "Unknown action" in result["error"]


# --- SMB Local Users and Groups ---


class TestLocalUsers:
    def test_list_maps_ontap_fields_and_strips_svm_prefix(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp(
                {
                    "/protocols/cifs/local-users": {
                        "data": {
                            "records": [
                                {
                                    "name": "SVM1\\alice",
                                    "sid": "S-1-5-21-1",
                                    "full_name": "Alice Example",
                                    "description": "desc",
                                    "account_disabled": False,
                                    "membership": [{"name": "BUILTIN\\Users"}],
                                }
                            ]
                        }
                    }
                }
            )
            result = handler({"action": "listLocalUsers"}, None)

        assert result["error"] is None
        assert result["count"] == 1
        user = result["users"][0]
        assert user["name"] == "alice"
        assert user["sid"] == "S-1-5-21-1"
        assert user["fullName"] == "Alice Example"
        assert user["disabled"] is False
        assert user["memberOf"] == ["BUILTIN\\Users"]

    def test_create_requires_name_and_password(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()
            result = handler({"action": "createLocalUser", "name": "bob"}, None)

        assert result["success"] is False
        assert "password" in result["error"]

    def test_create_posts_to_local_users(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/protocols/cifs/local-users": {"data": {}}})
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler(
                {
                    "action": "createLocalUser",
                    "name": "bob",
                    "password": "secret",
                    "fullName": "Bob Example",
                },
                None,
            )

        assert result["success"] is True
        method, url, kwargs = http.calls[0]
        assert method == "POST"
        assert url.endswith("/protocols/cifs/local-users")
        body = json.loads(kwargs["body"])
        assert body["name"] == "bob"
        assert body["full_name"] == "Bob Example"

    def test_create_does_not_log_the_password(self, mock_secrets, caplog):
        from handler import handler

        with caplog.at_level("INFO"), patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp({"/protocols/cifs/local-users": {"data": {}}})
            handler(
                {"action": "createLocalUser", "name": "bob", "password": "sup3rsecret"},
                None,
            )

        assert "sup3rsecret" not in caplog.text

    def test_delete_requires_sid(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()
            result = handler({"action": "deleteLocalUser", "name": "bob"}, None)

        assert result["success"] is False
        assert "sid" in result["error"]

    def test_delete_resolves_svm_uuid_then_deletes(self, mock_secrets):
        from handler import handler

        http = MockHttp(
            {"/svm/svms": {"data": {"records": [{"uuid": "svm-uuid-1"}]}}}
        )
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler(
                {"action": "deleteLocalUser", "sid": "S-1-5-21-1", "name": "bob"}, None
            )

        assert result["success"] is True
        assert http.calls[-1][0] == "DELETE"
        assert "/protocols/cifs/local-users/svm-uuid-1/S-1-5-21-1" in http.calls[-1][1]


class TestLocalGroups:
    def test_list_returns_groups(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp(
                {
                    "/protocols/cifs/local-groups": {
                        "data": {
                            "records": [
                                {
                                    "name": "SVM1\\analysts",
                                    "sid": "S-1-5-21-9",
                                    "description": "Analyst team",
                                }
                            ]
                        }
                    }
                }
            )
            result = handler({"action": "listLocalGroups"}, None)

        assert result["count"] == 1
        assert result["groups"][0]["name"] == "analysts"
        assert result["groups"][0]["description"] == "Analyst team"

    def test_create_requires_name(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()
            result = handler({"action": "createLocalGroup", "description": "x"}, None)

        assert result["success"] is False
        assert "name" in result["error"]

    def test_create_group_posts_body(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/protocols/cifs/local-groups": {"data": {}}})
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler(
                {"action": "createLocalGroup", "name": "analysts", "description": "team"},
                None,
            )

        assert result["success"] is True
        method, url, kwargs = http.calls[0]
        assert method == "POST"
        body = json.loads(kwargs["body"])
        assert body["name"] == "analysts"
        assert body["description"] == "team"

    def test_create_group_surfaces_ontap_error(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp(
                {
                    "/protocols/cifs/local-groups": {
                        "status": 400,
                        "data": {"error": {"message": "duplicate entry"}},
                    }
                }
            )
            result = handler({"action": "createLocalGroup", "name": "analysts"}, None)

        assert result["success"] is False
        assert result["error"] == "duplicate entry"


class TestGroupMembers:
    def test_list_requires_group_sid(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()
            result = handler({"action": "listGroupMembers"}, None)

        assert result["members"] == []
        assert "groupSid" in result["error"]

    def test_add_member_posts_name(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/svm/svms": {"data": {"records": [{"uuid": "svm-uuid-1"}]}}})
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler(
                {
                    "action": "addGroupMember",
                    "groupSid": "S-1-5-21-9",
                    "groupName": "analysts",
                    "memberName": "alice",
                },
                None,
            )

        assert result["success"] is True
        method, url, kwargs = http.calls[-1]
        assert method == "POST"
        assert "/local-groups/svm-uuid-1/S-1-5-21-9/members" in url
        assert json.loads(kwargs["body"]) == {"name": "alice"}

    def test_remove_member_percent_encodes_domain_name(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/svm/svms": {"data": {"records": [{"uuid": "svm-uuid-1"}]}}})
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler(
                {
                    "action": "removeGroupMember",
                    "groupSid": "S-1-5-21-9",
                    "memberName": "DEMO\\alice",
                },
                None,
            )

        assert result["success"] is True
        assert http.calls[-1][0] == "DELETE"
        assert "DEMO%5Calice" in http.calls[-1][1]


# --- Name Mapping ---


class TestNameMappings:
    def test_list_sorts_by_direction_and_index(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp(
                {
                    "/name-services/name-mappings": {
                        "data": {
                            "records": [
                                {
                                    "direction": "win_unix",
                                    "index": 2,
                                    "pattern": "b",
                                    "replacement": "y",
                                },
                                {
                                    "direction": "win_unix",
                                    "index": 1,
                                    "pattern": "a",
                                    "replacement": "x",
                                },
                            ]
                        }
                    }
                }
            )
            result = handler({"action": "listNameMappings"}, None)

        assert [m["index"] for m in result["mappings"]] == [1, 2]

    def test_create_rejects_s3_unix_direction(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()
            result = handler(
                {
                    "action": "createNameMapping",
                    "direction": "s3_unix",
                    "index": 1,
                    "pattern": "x",
                    "replacement": "y",
                },
                None,
            )

        assert result["success"] is False
        assert "managed automatically" in result["error"]

    def test_create_requires_index(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()
            result = handler(
                {
                    "action": "createNameMapping",
                    "direction": "win_unix",
                    "pattern": "x",
                    "replacement": "y",
                },
                None,
            )

        assert result["success"] is False
        assert "index" in result["error"]

    def test_delete_uses_svm_direction_index_path(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/svm/svms": {"data": {"records": [{"uuid": "svm-uuid-1"}]}}})
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler(
                {"action": "deleteNameMapping", "direction": "win_unix", "index": 3},
                None,
            )

        assert result["success"] is True
        assert "/name-services/name-mappings/svm-uuid-1/win_unix/3" in http.calls[-1][1]


# --- FlexCache ---


class TestFlexCache:
    def test_list_converts_size_and_flattens_origins(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp(
                {
                    "/storage/flexcache/flexcaches": {
                        "data": {
                            "records": [
                                {
                                    "name": "cache1",
                                    "uuid": "u1",
                                    "svm": {"name": "svm1"},
                                    "size": 10 * 1024**3,
                                    "path": "/cache1",
                                    "origins": [
                                        {
                                            "cluster": {"name": "origin-cluster"},
                                            "svm": {"name": "origin-svm"},
                                            "volume": {"name": "origin-vol"},
                                            "state": "online",
                                        }
                                    ],
                                    "global_file_locking_enabled": True,
                                }
                            ]
                        }
                    }
                }
            )
            result = handler({"action": "listFlexCaches"}, None)

        cache = result["caches"][0]
        assert cache["sizeGiB"] == 10.0
        assert cache["globalFileLocking"] is True
        assert cache["origins"][0]["clusterName"] == "origin-cluster"
        assert cache["origins"][0]["volumeName"] == "origin-vol"

    def test_create_requires_origin_volume(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()
            result = handler(
                {"action": "createFlexCache", "name": "cache1", "sizeGiB": 10}, None
            )

        assert result["success"] is False
        assert "originVolume" in result["error"]

    def test_create_rejects_size_below_one_gib(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()
            result = handler(
                {
                    "action": "createFlexCache",
                    "name": "cache1",
                    "originVolume": "vol1",
                    "sizeGiB": 0.5,
                },
                None,
            )

        assert result["success"] is False
        assert "at least 1" in result["error"]

    def test_create_converts_gib_and_returns_job_id(self, mock_secrets):
        from handler import handler

        http = MockHttp(
            {
                "/storage/flexcache/flexcaches": {
                    "data": {"job": {"uuid": "job-1"}}
                }
            }
        )
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler(
                {
                    "action": "createFlexCache",
                    "name": "cache1",
                    "originVolume": "vol1",
                    "sizeGiB": 10,
                    "prepopulatePaths": ["/a", "/b"],
                },
                None,
            )

        assert result["success"] is True
        assert result["jobId"] == "job-1"
        body = json.loads(http.calls[0][2]["body"])
        assert body["size"] == 10 * 1024**3
        assert body["path"] == "/cache1"
        assert body["prepopulate"] == {"dir_paths": ["/a", "/b"]}
        assert body["origins"][0]["volume"]["name"] == "vol1"

    def test_delete_requires_uuid(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()
            result = handler({"action": "deleteFlexCache", "name": "cache1"}, None)

        assert result["success"] is False
        assert "uuid" in result["error"]


# --- FlexClone ---


class TestFlexClone:
    def test_list_filters_on_is_flexclone(self, mock_secrets):
        from handler import handler

        http = MockHttp(
            {
                "/storage/volumes": {
                    "data": {
                        "records": [
                            {
                                "name": "clone1",
                                "uuid": "u1",
                                "size": 5 * 1024**3,
                                "state": "online",
                                "space": {"used": 1024**3},
                                "clone": {
                                    "parent_volume": {"name": "vol1"},
                                    "parent_snapshot": {"name": "snap1"},
                                    "split_initiated": False,
                                    "split_complete_percent": 0,
                                },
                            }
                        ]
                    }
                }
            }
        )
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler({"action": "listFlexClones"}, None)

        assert "clone.is_flexclone=true" in http.calls[0][1]
        clone = result["clones"][0]
        assert clone["parentVolume"] == "vol1"
        assert clone["parentSnapshot"] == "snap1"
        assert clone["sizeGiB"] == 5.0
        assert clone["usedGiB"] == 1.0

    def test_create_requires_parent_volume(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()
            result = handler({"action": "createFlexClone", "cloneName": "c1"}, None)

        assert result["success"] is False
        assert "parentVolume" in result["error"]

    def test_create_sends_clone_block(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/storage/volumes": {"data": {}}})
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler(
                {
                    "action": "createFlexClone",
                    "cloneName": "c1",
                    "parentVolume": "vol1",
                    "parentSnapshot": "snap1",
                },
                None,
            )

        assert result["success"] is True
        body = json.loads(http.calls[0][2]["body"])
        assert body["name"] == "c1"
        assert body["clone"]["parent_volume"] == {"name": "vol1"}
        assert body["clone"]["parent_snapshot"] == {"name": "snap1"}
        # Security style is inherited from the parent and must not be sent.
        assert "nas" not in body

    def test_create_without_snapshot_omits_parent_snapshot(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/storage/volumes": {"data": {}}})
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            handler(
                {
                    "action": "createFlexClone",
                    "cloneName": "c1",
                    "parentVolume": "vol1",
                },
                None,
            )

        body = json.loads(http.calls[0][2]["body"])
        assert "parent_snapshot" not in body["clone"]

    def test_split_patches_split_initiated(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/storage/volumes/u1": {"data": {}}})
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler(
                {"action": "splitFlexClone", "volumeUuid": "u1", "volumeName": "c1"},
                None,
            )

        assert result["success"] is True
        method, url, kwargs = http.calls[0]
        assert method == "PATCH"
        assert url.endswith("/storage/volumes/u1")
        assert json.loads(kwargs["body"]) == {"clone": {"split_initiated": True}}

    def test_split_requires_volume_uuid(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()
            result = handler({"action": "splitFlexClone", "volumeName": "c1"}, None)

        assert result["success"] is False
        assert "volumeUuid" in result["error"]


# --- SnapMirror (read-only) ---


class TestSnapMirror:
    def test_list_maps_source_and_destination(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp(
                {
                    "/snapmirror/relationships": {
                        "data": {
                            "records": [
                                {
                                    "uuid": "r1",
                                    "source": {
                                        "path": "svmA:vol1",
                                        "svm": {"name": "svmA"},
                                    },
                                    "destination": {
                                        "path": "svmB:vol1_dp",
                                        "svm": {"name": "svmB"},
                                    },
                                    "state": "snapmirrored",
                                    "healthy": True,
                                    "policy": {"name": "MirrorAllSnapshots"},
                                    "lag_time": "PT1H",
                                    "last_transfer_type": "update",
                                    "last_transfer_size": 1024,
                                }
                            ]
                        }
                    }
                }
            )
            result = handler({"action": "listSnapmirrorRelationships"}, None)

        rel = result["relationships"][0]
        assert rel["sourcePath"] == "svmA:vol1"
        assert rel["destinationSvm"] == "svmB"
        assert rel["healthy"] is True
        assert rel["policy"] == "MirrorAllSnapshots"

    def test_transfers_require_relationship_uuid(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()
            result = handler({"action": "getSnapmirrorTransfers"}, None)

        assert result["transfers"] == []
        assert "relationshipUuid" in result["error"]

    def test_transfers_maps_fields(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp(
                {
                    "/transfers": {
                        "data": {
                            "records": [
                                {
                                    "state": "success",
                                    "bytes_transferred": 2048,
                                    "end_time": "2026-08-03T00:00:00Z",
                                    "total_duration": "PT30S",
                                }
                            ]
                        }
                    }
                }
            )
            result = handler(
                {"action": "getSnapmirrorTransfers", "relationshipUuid": "r1"}, None
            )

        assert result["transfers"][0]["bytesTransferred"] == 2048
        assert result["transfers"][0]["duration"] == "PT30S"


# --- Vscan (read-only) ---


class TestVscan:
    def test_status_false_when_no_records(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()
            result = handler({"action": "getVscanStatus"}, None)

        assert result == {"enabled": False, "error": None}

    def test_status_reads_enabled(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp(
                {"/protocols/vscan": {"data": {"records": [{"enabled": True}]}}}
            )
            result = handler({"action": "getVscanStatus"}, None)

        assert result["enabled"] is True

    def test_policies_flatten_on_access_policies(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp(
                {
                    "/protocols/vscan": {
                        "data": {
                            "records": [
                                {
                                    "on_access_policies": [
                                        {
                                            "name": "default_CIFS",
                                            "enabled": True,
                                            "mandatory": True,
                                            "scope": {
                                                "max_file_size": 2147483648,
                                                "exclude_paths": ["/tmp"],
                                                "exclude_extensions": ["tmp"],
                                            },
                                        }
                                    ]
                                }
                            ]
                        }
                    }
                }
            )
            result = handler({"action": "listVscanPolicies"}, None)

        pol = result["policies"][0]
        assert pol["name"] == "default_CIFS"
        assert pol["mandatory"] is True
        assert pol["excludedPaths"] == ["/tmp"]
        assert pol["excludedExtensions"] == ["tmp"]


# --- FPolicy (read-only) ---


class TestFPolicy:
    def test_status_flattens_connections(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp(
                {
                    "/protocols/fpolicy": {
                        "data": {
                            "records": [
                                {
                                    "connections": [
                                        {
                                            "node": {"name": "node1"},
                                            "policy": {"name": "audit"},
                                            "server": "198.51.100.10",
                                            "state": "connected",
                                        }
                                    ]
                                }
                            ]
                        }
                    }
                }
            )
            result = handler({"action": "getFpolicyStatus"}, None)

        conn = result["connections"][0]
        assert conn["node"] == "node1"
        assert conn["policy"] == "audit"
        assert conn["state"] == "connected"

    def test_policies_map_engine_and_events(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp(
                {
                    "/protocols/fpolicy": {
                        "data": {
                            "records": [
                                {
                                    "policies": [
                                        {
                                            "name": "audit",
                                            "enabled": True,
                                            "priority": 1,
                                            "engine": {"name": "external"},
                                            "events": [{"name": "ev1"}, "ev2"],
                                        }
                                    ]
                                }
                            ]
                        }
                    }
                }
            )
            result = handler({"action": "listFpolicyPolicies"}, None)

        pol = result["policies"][0]
        assert pol["engineType"] == "external"
        assert pol["events"] == ["ev1", "ev2"]

    def test_events_keep_only_enabled_file_operations(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp(
                {
                    "/protocols/fpolicy": {
                        "data": {
                            "records": [
                                {
                                    "events": [
                                        {
                                            "name": "ev1",
                                            "protocol": "cifs",
                                            "file_operations": {
                                                "create": True,
                                                "delete": True,
                                                "read": False,
                                            },
                                        }
                                    ]
                                }
                            ]
                        }
                    }
                }
            )
            result = handler({"action": "listFpolicyEvents"}, None)

        ev = result["events"][0]
        assert ev["protocol"] == "cifs"
        assert ev["fileOperations"] == ["create", "delete"]


class TestNewActionsAreRouted:
    """Every action the 7 panels call must resolve to a handler, not fall through."""

    ACTIONS = [
        "listLocalUsers",
        "createLocalUser",
        "deleteLocalUser",
        "listLocalGroups",
        "createLocalGroup",
        "deleteLocalGroup",
        "listGroupMembers",
        "addGroupMember",
        "removeGroupMember",
        "listNameMappings",
        "createNameMapping",
        "deleteNameMapping",
        "listFlexCaches",
        "createFlexCache",
        "deleteFlexCache",
        "listFlexClones",
        "createFlexClone",
        "splitFlexClone",
        "listSnapmirrorRelationships",
        "getSnapmirrorTransfers",
        "getVscanStatus",
        "listVscanPolicies",
        "getFpolicyStatus",
        "listFpolicyPolicies",
        "listFpolicyEvents",
    ]

    @pytest.mark.parametrize("action", ACTIONS)
    def test_action_is_not_unknown(self, action, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()
            result = handler({"action": action}, None)

        assert result.get("error") != f"Unknown action: {action}"


# --- SnapMirror write operations ---


class TestSnapMirrorWrites:
    def test_update_now_posts_transfer(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/transfers": {"data": {"job": {"uuid": "j1"}}}})
        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = http
            result = handler(
                {"action": "updateSnapmirrorNow", "relationshipUuid": "r1"}, None
            )

        assert result["success"] is True
        assert result["jobId"] == "j1"
        method, url, _ = http.calls[0]
        assert method == "POST"
        assert url.endswith("/snapmirror/relationships/r1/transfers")

    def test_update_now_requires_uuid(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = MockHttp()
            result = handler({"action": "updateSnapmirrorNow"}, None)

        assert result["success"] is False
        assert "relationshipUuid" in result["error"]

    def test_quiesce_patches_state_paused(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/snapmirror/relationships/r1": {"data": {}}})
        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = http
            result = handler({"action": "quiesceSnapmirror", "relationshipUuid": "r1"}, None)

        assert result["state"] == "paused"
        assert json.loads(http.calls[0][2]["body"]) == {"state": "paused"}

    def test_resume_patches_state_snapmirrored(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/snapmirror/relationships/r1": {"data": {}}})
        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = http
            result = handler({"action": "resumeSnapmirror", "relationshipUuid": "r1"}, None)

        assert result["state"] == "snapmirrored"

    def test_break_requires_confirm(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = MockHttp()
            result = handler({"action": "breakSnapmirror", "relationshipUuid": "r1"}, None)

        assert result["success"] is False
        assert "confirm" in result["error"]

    def test_break_patches_broken_off_when_confirmed(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/snapmirror/relationships/r1": {"data": {}}})
        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = http
            result = handler(
                {"action": "breakSnapmirror", "relationshipUuid": "r1", "confirm": True}, None
            )

        assert result["success"] is True
        assert json.loads(http.calls[0][2]["body"]) == {"state": "broken_off"}

    def test_resync_requires_confirm(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = MockHttp()
            result = handler({"action": "resyncSnapmirror", "relationshipUuid": "r1"}, None)

        assert result["success"] is False
        assert "confirm" in result["error"]

    def test_abort_transfer_patches_aborted(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/transfers/t1": {"data": {}}})
        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = http
            result = handler(
                {
                    "action": "abortSnapmirrorTransfer",
                    "relationshipUuid": "r1",
                    "transferUuid": "t1",
                },
                None,
            )

        assert result["success"] is True
        assert json.loads(http.calls[0][2]["body"]) == {"state": "aborted"}

    def test_delete_requires_confirm(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = MockHttp()
            result = handler({"action": "deleteSnapmirror", "relationshipUuid": "r1"}, None)

        assert result["success"] is False
        assert "confirm" in result["error"]

    def test_write_error_is_propagated(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = MockHttp(
                {
                    "/snapmirror/relationships/r1": {
                        "status": 409,
                        "data": {"error": {"message": "relationship is busy"}},
                    }
                }
            )
            result = handler({"action": "quiesceSnapmirror", "relationshipUuid": "r1"}, None)

        assert result["success"] is False
        assert result["error"] == "relationship is busy"


# --- Vscan write operations ---


class TestVscanWrites:
    def test_set_enabled_patches_vscan(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/svm/svms": {"data": {"records": [{"uuid": "svm-1"}]}}})
        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = http
            result = handler({"action": "setVscanEnabled", "enabled": True}, None)

        assert result["success"] is True
        method, url, kwargs = http.calls[-1]
        assert method == "PATCH"
        assert url.endswith("/protocols/vscan/svm-1")
        assert json.loads(kwargs["body"]) == {"enabled": True}

    def test_set_enabled_requires_value(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = MockHttp()
            result = handler({"action": "setVscanEnabled"}, None)

        assert result["success"] is False
        assert "enabled" in result["error"]

    def test_create_policy_builds_scope(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/svm/svms": {"data": {"records": [{"uuid": "svm-1"}]}}})
        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = http
            result = handler(
                {
                    "action": "createVscanPolicy",
                    "name": "scan_all",
                    "mandatory": True,
                    "maxFileSize": 2147483648,
                    "excludedExtensions": ["tmp"],
                },
                None,
            )

        assert result["success"] is True
        body = json.loads(http.calls[-1][2]["body"])
        assert body["name"] == "scan_all"
        assert body["mandatory"] is True
        assert body["scope"]["max_file_size"] == 2147483648
        assert body["scope"]["exclude_extensions"] == ["tmp"]

    def test_toggle_policy_encodes_name(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/svm/svms": {"data": {"records": [{"uuid": "svm-1"}]}}})
        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = http
            result = handler(
                {"action": "setVscanPolicyEnabled", "name": "scan all", "enabled": False},
                None,
            )

        assert result["success"] is True
        assert "scan%20all" in http.calls[-1][1]

    def test_delete_policy_requires_name(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = MockHttp()
            result = handler({"action": "deleteVscanPolicy"}, None)

        assert result["success"] is False
        assert "name" in result["error"]


# --- FPolicy write operations ---


class TestFPolicyWrites:
    def test_create_event_maps_operations_to_flags(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/svm/svms": {"data": {"records": [{"uuid": "svm-1"}]}}})
        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = http
            result = handler(
                {
                    "action": "createFpolicyEvent",
                    "name": "ev1",
                    "protocol": "cifs",
                    "fileOperations": ["create", "delete"],
                },
                None,
            )

        assert result["success"] is True
        body = json.loads(http.calls[-1][2]["body"])
        assert body["file_operations"] == {"create": True, "delete": True}
        assert "/protocols/fpolicy/svm-1/events" in http.calls[-1][1]

    def test_create_event_requires_operations(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = MockHttp()
            result = handler(
                {"action": "createFpolicyEvent", "name": "ev1", "protocol": "cifs"}, None
            )

        assert result["success"] is False
        assert "file operation" in result["error"]

    def test_create_policy_wraps_event_names(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/svm/svms": {"data": {"records": [{"uuid": "svm-1"}]}}})
        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = http
            result = handler(
                {
                    "action": "createFpolicyPolicy",
                    "name": "audit",
                    "events": ["ev1", "ev2"],
                    "engineName": "external",
                    "priority": 2,
                },
                None,
            )

        assert result["success"] is True
        body = json.loads(http.calls[-1][2]["body"])
        assert body["events"] == [{"name": "ev1"}, {"name": "ev2"}]
        assert body["engine"] == {"name": "external"}
        assert body["priority"] == 2

    def test_create_policy_requires_events(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = MockHttp()
            result = handler({"action": "createFpolicyPolicy", "name": "audit"}, None)

        assert result["success"] is False
        assert "event" in result["error"]

    def test_enable_policy_requires_priority(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = MockHttp()
            result = handler(
                {"action": "setFpolicyPolicyEnabled", "name": "audit", "enabled": True}, None
            )

        assert result["success"] is False
        assert "priority" in result["error"]

    def test_disable_policy_omits_priority(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/svm/svms": {"data": {"records": [{"uuid": "svm-1"}]}}})
        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = http
            result = handler(
                {"action": "setFpolicyPolicyEnabled", "name": "audit", "enabled": False}, None
            )

        assert result["success"] is True
        body = json.loads(http.calls[-1][2]["body"])
        assert body == {"enabled": False}

    def test_delete_event_uses_svm_scoped_path(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/svm/svms": {"data": {"records": [{"uuid": "svm-1"}]}}})
        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = http
            result = handler({"action": "deleteFpolicyEvent", "name": "ev1"}, None)

        assert result["success"] is True
        assert http.calls[-1][0] == "DELETE"
        assert "/protocols/fpolicy/svm-1/events/ev1" in http.calls[-1][1]


# --- Peering ---


class TestInterclusterLifs:
    def test_list_filters_on_intercluster_service(self, mock_secrets):
        from handler import handler

        http = MockHttp(
            {
                "/network/ip/interfaces": {
                    "data": {
                        "records": [
                            {
                                "name": "inter_1",
                                "uuid": "l1",
                                "ip": {"address": "198.51.100.57"},
                                "enabled": True,
                                "state": "up",
                                "location": {"node": {"name": "node1"}},
                            }
                        ]
                    }
                }
            }
        )
        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = http
            result = handler({"action": "listInterclusterLifs"}, None)

        assert "services=intercluster_core" in http.calls[0][1]
        lif = result["lifs"][0]
        assert lif["address"] == "198.51.100.57"
        assert lif["node"] == "node1"


class TestClusterPeers:
    def test_list_maps_remote_and_auth(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = MockHttp(
                {
                    "/cluster/peers": {
                        "data": {
                            "records": [
                                {
                                    "name": "peer1",
                                    "uuid": "cp1",
                                    "status": {"state": "available"},
                                    "remote": {
                                        "name": "RemoteCluster",
                                        "ip_addresses": ["198.51.100.7"],
                                    },
                                    "authentication": {"state": "ok"},
                                    "encryption": {"state": "tls_psk"},
                                }
                            ]
                        }
                    }
                }
            )
            result = handler({"action": "listClusterPeers"}, None)

        p = result["peers"][0]
        assert p["state"] == "available"
        assert p["remoteName"] == "RemoteCluster"
        assert p["remoteAddresses"] == ["198.51.100.7"]
        assert p["authState"] == "ok"

    def test_create_requires_remote_addresses(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = MockHttp()
            result = handler({"action": "createClusterPeer", "generatePassphrase": True}, None)

        assert result["success"] is False
        assert "remoteAddresses" in result["error"]

    def test_create_requires_a_passphrase_source(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = MockHttp()
            result = handler(
                {"action": "createClusterPeer", "remoteAddresses": ["198.51.100.7"]}, None
            )

        assert result["success"] is False
        assert "passphrase" in result["error"]

    def test_create_with_generate_sets_flag(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/cluster/peers": {"data": {}}})
        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = http
            result = handler(
                {
                    "action": "createClusterPeer",
                    "remoteAddresses": ["198.51.100.7"],
                    "generatePassphrase": True,
                },
                None,
            )

        assert result["success"] is True
        body = json.loads(http.calls[0][2]["body"])
        assert body["generate_passphrase"] is True
        assert body["remote"]["ip_addresses"] == ["198.51.100.7"]
        assert "authentication" not in body

    def test_create_returns_generated_passphrase(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = MockHttp(
                {
                    "/cluster/peers": {
                        "data": {
                            "records": [{"authentication": {"passphrase": "abc-123"}}]
                        }
                    }
                }
            )
            result = handler(
                {
                    "action": "createClusterPeer",
                    "remoteAddresses": ["198.51.100.7"],
                    "generatePassphrase": True,
                },
                None,
            )

        assert result["passphrase"] == "abc-123"

    def test_create_with_explicit_passphrase_sends_authentication(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/cluster/peers": {"data": {}}})
        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = http
            handler(
                {
                    "action": "createClusterPeer",
                    "remoteAddresses": ["198.51.100.7"],
                    "passphrase": "secret",
                },
                None,
            )

        body = json.loads(http.calls[0][2]["body"])
        assert body["authentication"] == {"passphrase": "secret"}
        assert "generate_passphrase" not in body

    def test_accept_requires_uuid_and_passphrase(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = MockHttp()
            result = handler({"action": "acceptClusterPeer", "uuid": "cp1"}, None)

        assert result["success"] is False
        assert "passphrase" in result["error"]

    def test_accept_patches_authentication(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/cluster/peers/cp1": {"data": {}}})
        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = http
            result = handler(
                {"action": "acceptClusterPeer", "uuid": "cp1", "passphrase": "abc"}, None
            )

        assert result["success"] is True
        assert http.calls[0][0] == "PATCH"
        assert json.loads(http.calls[0][2]["body"]) == {"authentication": {"passphrase": "abc"}}

    def test_delete_requires_confirm(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = MockHttp()
            result = handler({"action": "deleteClusterPeer", "uuid": "cp1"}, None)

        assert result["success"] is False
        assert "confirm" in result["error"]


class TestSvmPeers:
    def test_list_maps_peer_svm_and_cluster(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = MockHttp(
                {
                    "/svm/peers": {
                        "data": {
                            "records": [
                                {
                                    "name": "sp1",
                                    "uuid": "u1",
                                    "state": "peered",
                                    "applications": ["snapmirror"],
                                    "svm": {"name": "svm1"},
                                    "peer": {
                                        "svm": {"name": "svm_dr"},
                                        "cluster": {"name": "RemoteCluster"},
                                    },
                                }
                            ]
                        }
                    }
                }
            )
            result = handler({"action": "listSvmPeers"}, None)

        p = result["peers"][0]
        assert p["localSvm"] == "svm1"
        assert p["peerSvm"] == "svm_dr"
        assert p["peerCluster"] == "RemoteCluster"
        assert p["applications"] == ["snapmirror"]

    def test_create_requires_peer_svm(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = MockHttp()
            result = handler({"action": "createSvmPeer"}, None)

        assert result["success"] is False
        assert "peerSvm" in result["error"]

    def test_create_defaults_to_snapmirror_application(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/svm/peers": {"data": {}}})
        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = http
            result = handler(
                {"action": "createSvmPeer", "peerSvm": "svm_dr", "peerCluster": "Remote"},
                None,
            )

        assert result["success"] is True
        body = json.loads(http.calls[0][2]["body"])
        assert body["applications"] == ["snapmirror"]
        assert body["peer"]["cluster"] == {"name": "Remote"}

    def test_accept_patches_state_peered(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/svm/peers/u1": {"data": {}}})
        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = http
            result = handler({"action": "acceptSvmPeer", "uuid": "u1"}, None)

        assert result["success"] is True
        assert json.loads(http.calls[0][2]["body"]) == {"state": "peered"}

    def test_delete_requires_confirm(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = MockHttp()
            result = handler({"action": "deleteSvmPeer", "uuid": "u1"}, None)

        assert result["success"] is False
        assert "confirm" in result["error"]


# --- Cluster inventory and services ---


class TestClusterInventory:
    def test_cluster_info_reads_version(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = MockHttp(
                {
                    "/cluster?": {
                        "data": {"name": "Cluster1", "version": {"full": "NetApp Release 9.17.1"}}
                    }
                }
            )
            result = handler({"action": "getClusterInfo"}, None)

        assert result["name"] == "Cluster1"
        assert "9.17.1" in result["version"]

    def test_nodes_map_ha_partners(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = MockHttp(
                {
                    "/cluster/nodes": {
                        "data": {
                            "records": [
                                {
                                    "name": "node1",
                                    "uuid": "n1",
                                    "state": "up",
                                    "uptime": 90000,
                                    "ha": {"enabled": True, "partners": [{"name": "node2"}]},
                                }
                            ]
                        }
                    }
                }
            )
            result = handler({"action": "listNodes"}, None)

        n = result["nodes"][0]
        assert n["haEnabled"] is True
        assert n["haPartners"] == ["node2"]

    def test_licenses_take_first_expiry(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = MockHttp(
                {
                    "/cluster/licensing/licenses": {
                        "data": {
                            "records": [
                                {
                                    "name": "flexcache",
                                    "state": "compliant",
                                    "scope": "cluster",
                                    "licenses": [{"expiry_time": "2027-01-01T00:00:00Z"}],
                                }
                            ]
                        }
                    }
                }
            )
            result = handler({"action": "listLicenses"}, None)

        assert result["licenses"][0]["expiryTime"].startswith("2027")

    def test_interfaces_include_services(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = MockHttp(
                {
                    "/network/ip/interfaces": {
                        "data": {
                            "records": [
                                {
                                    "name": "mgmt",
                                    "uuid": "i1",
                                    "ip": {"address": "198.51.100.5"},
                                    "enabled": True,
                                    "state": "up",
                                    "services": ["management_core"],
                                    "location": {
                                        "node": {"name": "node1"},
                                        "port": {"name": "e0e"},
                                    },
                                }
                            ]
                        }
                    }
                }
            )
            result = handler({"action": "listNetworkInterfaces"}, None)

        i = result["interfaces"][0]
        assert i["services"] == ["management_core"]
        assert i["port"] == "e0e"

    def test_disabling_a_lif_requires_confirm(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = MockHttp()
            result = handler(
                {"action": "setNetworkInterfaceEnabled", "uuid": "i1", "enabled": False}, None
            )

        assert result["success"] is False
        assert "confirm" in result["error"]

    def test_enabling_a_lif_needs_no_confirm(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/network/ip/interfaces/i1": {"data": {}}})
        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = http
            result = handler(
                {"action": "setNetworkInterfaceEnabled", "uuid": "i1", "enabled": True}, None
            )

        assert result["success"] is True
        assert json.loads(http.calls[0][2]["body"]) == {"enabled": True}

    def test_dns_config_read(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = MockHttp(
                {
                    "/name-services/dns": {
                        "data": {
                            "records": [
                                {
                                    "domains": ["demo.fsx.local"],
                                    "servers": ["198.51.100.10"],
                                    "dynamic_dns": {"enabled": True},
                                }
                            ]
                        }
                    }
                }
            )
            result = handler({"action": "getDnsConfig"}, None)

        assert result["domains"] == ["demo.fsx.local"]
        assert result["dynamicDns"] is True

    def test_dns_update_requires_both_fields(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = MockHttp()
            result = handler({"action": "updateDnsConfig", "domains": ["a"]}, None)

        assert result["success"] is False
        assert "servers" in result["error"]

    def test_protocol_services_reports_three_protocols(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = MockHttp(
                {
                    "/protocols/nfs/services": {
                        "data": {"records": [{"enabled": True, "state": "online"}]}
                    },
                    "/protocols/cifs/services": {
                        "data": {
                            "records": [
                                {"enabled": True, "ad_domain": {"fqdn": "demo.fsx.local"}}
                            ]
                        }
                    },
                    "/protocols/s3/services": {
                        "data": {"records": [{"enabled": True, "name": "svm1_s3"}]}
                    },
                }
            )
            result = handler({"action": "listProtocolServices"}, None)

        by_proto = {s["protocol"]: s for s in result["services"]}
        assert by_proto["nfs"]["enabled"] is True
        assert by_proto["cifs"]["detail"] == "demo.fsx.local"
        assert by_proto["s3"]["detail"] == "svm1_s3"

    def test_protocol_toggle_validates_protocol(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = MockHttp()
            result = handler(
                {"action": "setProtocolServiceEnabled", "protocol": "smb", "enabled": True}, None
            )

        assert result["success"] is False
        assert "nfs, cifs or s3" in result["error"]

    def test_disabling_a_protocol_requires_confirm(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = MockHttp()
            result = handler(
                {"action": "setProtocolServiceEnabled", "protocol": "nfs", "enabled": False},
                None,
            )

        assert result["success"] is False
        assert "confirm" in result["error"]

    def test_enabling_a_protocol_patches_service(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/svm/svms": {"data": {"records": [{"uuid": "svm-1"}]}}})
        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = http
            result = handler(
                {"action": "setProtocolServiceEnabled", "protocol": "cifs", "enabled": True},
                None,
            )

        assert result["success"] is True
        assert "/protocols/cifs/services/svm-1" in http.calls[-1][1]

    def test_jobs_list_maps_state_and_message(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = MockHttp(
                {
                    "/cluster/jobs": {
                        "data": {
                            "records": [
                                {
                                    "uuid": "j1",
                                    "description": "FlexCache create",
                                    "state": "success",
                                    "message": "complete",
                                    "code": 0,
                                }
                            ]
                        }
                    }
                }
            )
            result = handler({"action": "listJobs"}, None)

        assert result["jobs"][0]["state"] == "success"
        assert result["jobs"][0]["description"] == "FlexCache create"

    def test_get_job_requires_id(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = MockHttp()
            result = handler({"action": "getJob"}, None)

        assert "jobId" in result["error"]


class TestPeeringAndClusterActionsAreRouted:
    """Every action the peering and cluster panels call must resolve."""

    ACTIONS = [
        "updateSnapmirrorNow",
        "quiesceSnapmirror",
        "resumeSnapmirror",
        "breakSnapmirror",
        "resyncSnapmirror",
        "abortSnapmirrorTransfer",
        "deleteSnapmirror",
        "setVscanEnabled",
        "createVscanPolicy",
        "setVscanPolicyEnabled",
        "deleteVscanPolicy",
        "createFpolicyEvent",
        "deleteFpolicyEvent",
        "createFpolicyPolicy",
        "setFpolicyPolicyEnabled",
        "deleteFpolicyPolicy",
        "listInterclusterLifs",
        "listClusterPeers",
        "createClusterPeer",
        "acceptClusterPeer",
        "deleteClusterPeer",
        "listSvmPeers",
        "createSvmPeer",
        "acceptSvmPeer",
        "deleteSvmPeer",
        "getClusterInfo",
        "listNodes",
        "listLicenses",
        "listNetworkInterfaces",
        "setNetworkInterfaceEnabled",
        "getDnsConfig",
        "updateDnsConfig",
        "listProtocolServices",
        "setProtocolServiceEnabled",
        "listJobs",
        "getJob",
    ]

    @pytest.mark.parametrize("action", ACTIONS)
    def test_action_is_not_unknown(self, action, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = MockHttp()
            result = handler({"action": action}, None)

        assert result.get("error") != f"Unknown action: {action}"
