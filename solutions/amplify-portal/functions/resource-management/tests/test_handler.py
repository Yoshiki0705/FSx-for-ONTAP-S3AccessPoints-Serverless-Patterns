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

    def find(self, method, url_fragment):
        """The first recorded call matching a method and a URL fragment.

        Assertions used to index `calls[0]`, which assumed the operation under test
        was the first ONTAP request the handler made. Several handlers now run a
        pre-flight lookup first -- resolving whether the target is a FlexCache, or an
        SVM UUID -- so position is not a stable way to name a call. Fails loudly
        rather than returning None, so a missing call reads as a missing call.
        """
        for call in self.calls:
            if call[0] == method and url_fragment in call[1]:
                return call
        raise AssertionError(
            f"no {method} call containing {url_fragment!r}; recorded: "
            + ", ".join(f"{m} {u}" for m, u, _ in self.calls)
        )

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


def snapmirror_client(pool):
    """Patch the handler's client builder onto `pool`.

    The SnapMirror actions go through shared/ontap_client.py rather than this
    handler's own urllib3 pool, so `patch("handler.urllib3.PoolManager")` no longer
    reaches them. Injecting the same MockHttp keeps these tests at the wire level,
    which is where their value is: they assert the request path, the body and the
    requested `fields`, and one of them exists because a field name real ONTAP
    rejects silently emptied a list on a live cluster.

    `_pool` and `_credentials` are set directly so the fake stays off both the
    network and Secrets Manager. Note that a SnapMirror test which forgets this
    patch does not merely fail -- it reaches out for real and hangs, which is why
    the handler hands the client its own boto3 session.
    """
    from shared.ontap_client import OntapClient, OntapClientConfig

    client = OntapClient(
        OntapClientConfig(
            management_ip="10.0.0.1",
            secret_name="test/secret",
            verify_ssl=False,
        )
    )
    client._pool = pool
    client._credentials = {"username": "fsxadmin", "password": "test"}
    return patch("handler._shared_client", return_value=client)


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


class TestVolumeCapacityBreakdown:
    """What a volume is holding, split into the parts that behave differently.

    `space.used` answers a narrower question than the volume row implies, and it does
    not answer it the same way on two volumes: snapshot data inside the reserve is
    excluded from it while snapshot data past the reserve is included. Both shapes are
    fixed here from measurements taken on the file system this portal manages.
    """

    @pytest.fixture(autouse=True)
    def _secrets(self, mock_secrets):
        """Every case in here reaches ONTAP, so the credential read is always mocked."""

    def _volumes(self, record):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp(
                {"/storage/volumes": {"status": 200, "data": {"records": [record], "num_records": 1}}}
            )
            return handler({"action": "listVolumes"}, None)["volumes"][0]

    def test_snapshot_usage_inside_the_reserve_is_reported_and_is_not_spill(self):
        """Measured on clone03: used 18.1 MiB, snapshots 77.3 MiB, reserve 5 GiB.

        The snapshots hold four times what the active file system does, and `used`
        does not mention them because they fit in the reserve. Deleting files here
        moves blocks into that hidden number instead of releasing them.
        """
        vol = self._volumes(
            {
                "name": "clone03",
                "uuid": "uuid-c3",
                "size": 107374182400,
                "space": {
                    "used": 18_979_840,
                    "used_by_afs": 18_979_840,
                    "snapshot": {
                        "used": 81_055_744,
                        "reserve_percent": 5,
                        "reserve_size": 5_368_709_120,
                        "autodelete_enabled": False,
                    },
                },
            }
        )

        assert vol["afsUsedBytes"] == 18_979_840
        assert vol["snapshotUsedBytes"] == 81_055_744
        assert vol["snapshotReservePercent"] == 5
        # Nothing has escaped the reserve, so the active file system is not being
        # squeezed yet -- which is a different situation from the one below and has
        # to stay distinguishable.
        assert vol["snapshotSpillBytes"] == 0
        assert vol["snapshotAutodeleteEnabled"] is False

    def test_snapshot_usage_past_the_reserve_is_reported_as_spill(self):
        """With no reserve, every snapshot block competes with live data."""
        vol = self._volumes(
            {
                "name": "ds_migtoaws_bk",
                "uuid": "uuid-ds",
                "size": 2199023255552,
                "space": {
                    "used": 87_745_069_056,
                    "used_by_afs": 85_916_483_584,
                    "snapshot": {"used": 1_828_585_472, "reserve_percent": 0, "reserve_size": 0},
                },
            }
        )

        assert vol["snapshotSpillBytes"] == 1_828_585_472
        # `used` already counts the spill, so the two must not be added together by a
        # caller trying to reconstruct the total.
        assert vol["usedBytes"] == vol["afsUsedBytes"] + vol["snapshotSpillBytes"]

    def test_a_volume_reporting_no_space_object_still_produces_numbers(self):
        """Absent fields read as zero rather than as a missing key.

        The list is rendered straight into a table, and one volume answering with a
        shorter record than the rest used to be able to take the row down with it.
        """
        vol = self._volumes({"name": "bare", "uuid": "uuid-b", "size": 1024})

        assert vol["afsUsedBytes"] == 0
        assert vol["snapshotUsedBytes"] == 0
        assert vol["snapshotReserveBytes"] == 0
        assert vol["snapshotSpillBytes"] == 0
        assert vol["snapshotAutodeleteEnabled"] is False


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
                    "/storage/aggregates": {"data": {"records": [{"name": "aggr1"}]}},
                    "/storage/volumes": {"status": 202, "data": {}},
                }
            )

            result = handler({"action": "createVolume", "name": "test_vol", "sizeGiB": 50}, None)

        assert result["success"] is True
        assert result["volumeName"] == "test_vol"

    def test_a_flexvol_is_given_a_style_and_a_resolved_aggregate(self, mock_secrets):
        """Both are required, and neither is something a portal user can supply.

        Without `style` ONTAP answers 787140; with `style: flexvol` and no aggregate it
        answers 918242. On FSx for ONTAP AWS manages the aggregates, so the name is
        looked up rather than asked for. This create had never once succeeded.
        """
        from handler import handler

        http = MockHttp(
            {
                "/storage/aggregates": {"data": {"records": [{"name": "aggr1"}]}},
                "/storage/volumes": {"status": 202, "data": {}},
            }
        )
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler({"action": "createVolume", "name": "test_vol", "sizeGiB": 50}, None)

        assert result["success"] is True
        body = json.loads(http.find("POST", "/storage/volumes")[2]["body"])
        assert body["style"] == "flexvol"
        assert body["aggregates"] == [{"name": "aggr1"}]

    def test_a_flexgroup_is_given_an_aggregate_too(self, mock_secrets):
        """This used to assert the opposite, on the strength of how ONTAP is documented.

        A FlexGroup is placed automatically in principle, and that placement cannot
        succeed on FSx for ONTAP: the aggregate is a FabricPool aggregate and automatic
        selection excludes it. Measured -- a FlexGroup with no aggregate named failed
        with "No suitable storage can be found for the specified requirements.
        Aggregates not matching FabricPool requirements: aggr1", and the same request
        naming aggr1 succeeded. The FlexCache path already knew this and says so with
        `use_tiered_aggregate`; the volume path did not, so creating a FlexGroup here
        had never worked.
        """
        from handler import handler

        http = MockHttp(
            {
                "/storage/aggregates": {"data": {"records": [{"name": "aggr1"}]}},
                "/storage/volumes": {"status": 202, "data": {}},
            }
        )
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler(
                {"action": "createVolume", "name": "big_vol", "sizeGiB": 400, "style": "flexgroup"},
                None,
            )

        assert result["success"] is True
        body = json.loads(http.find("POST", "/storage/volumes")[2]["body"])
        assert body["style"] == "flexgroup"
        assert body["aggregates"] == [{"name": "aggr1"}]

    def test_a_named_aggregate_is_used_as_given(self, mock_secrets):
        """A caller that knows which aggregate it wants is not overridden."""
        from handler import handler

        http = MockHttp({"/storage/volumes": {"status": 202, "data": {}}})
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            handler(
                {
                    "action": "createVolume",
                    "name": "big_vol",
                    "sizeGiB": 400,
                    "style": "flexgroup",
                    "aggregates": ["aggr2"],
                },
                None,
            )

        body = json.loads(http.find("POST", "/storage/volumes")[2]["body"])
        assert body["aggregates"] == [{"name": "aggr2"}]
        # And the aggregate listing is not consulted when one was named.
        assert not any("/storage/aggregates" in call[1] for call in http.calls)

    def test_an_empty_aggregate_list_is_explained(self, mock_secrets):
        """ONTAP's own 918242 asks for a value the caller cannot know."""
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()
            result = handler({"action": "createVolume", "name": "test_vol", "sizeGiB": 50}, None)

        assert result["success"] is False
        assert "flexgroup" in result["error"]

    def test_a_refused_request_asks_the_cluster_nothing(self, mock_secrets):
        """Validation comes first, so a bad name costs no ONTAP round trip."""
        from handler import handler

        http = MockHttp()
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler({"action": "createVolume", "name": "bad-name", "sizeGiB": 50}, None)

        assert result["success"] is False
        assert http.calls == []


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

    def test_reports_a_failed_delete_job_as_a_failure(self, mock_secrets):
        """A 202 on the DELETE is not a deleted volume.

        Both the offline and the delete are jobs. Reporting success from the 202 told
        the caller the volume was gone while it was still listed -- observed on a
        former SnapMirror destination, where the delete job failed because the volume
        was still online.
        """
        from handler import handler

        http = MockHttp(
            {
                "/storage/volumes/uuid-1": {"data": {"job": {"uuid": "job-del"}}},
                "/cluster/jobs/job-del": {"data": {"state": "failure", "message": "volume is not offline"}},
            }
        )
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http

            result = handler(
                {
                    "action": "deleteVolume",
                    "volumeUuid": "uuid-1",
                    "volumeName": "vol1",
                    "confirm": True,
                },
                None,
            )

        assert result["success"] is False
        assert "not offline" in result["error"]

    def test_a_mounted_volume_is_unmounted_first(self, mock_secrets):
        """ONTAP will not offline a mounted volume and will not unmount it for you.

        Without this the delete only ever worked on a volume with no junction path -- a
        SnapMirror destination. Every volume the portal creates is mounted.
        """
        from handler import handler

        http = MockHttp(
            {
                "/storage/volumes/uuid-1?fields=nas.path": {"data": {"nas": {"path": "/test_vol"}}},
                "/storage/volumes/uuid-1": {"data": {"job": {"uuid": "job-1"}}},
                "/cluster/jobs/job-1": {"data": {"state": "success", "message": "done"}},
            }
        )
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler({"action": "deleteVolume", "volumeUuid": "uuid-1", "confirm": True}, None)

        assert result["success"] is True
        patches = [json.loads(c[2]["body"]) for c in http.calls if c[0] == "PATCH"]
        # Unmount before offline, in that order.
        assert patches[0] == {"nas": {"path": ""}}
        assert patches[1] == {"state": "offline"}

    def test_an_unmounted_volume_is_not_patched_for_it(self, mock_secrets):
        """A volume with no junction path needs no unmount, so none is sent."""
        from handler import handler

        http = MockHttp(
            {
                "/storage/volumes/uuid-1?fields=nas.path": {"data": {"nas": {}}},
                "/storage/volumes/uuid-1": {"data": {"job": {"uuid": "job-1"}}},
                "/cluster/jobs/job-1": {"data": {"state": "success", "message": "done"}},
            }
        )
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler({"action": "deleteVolume", "volumeUuid": "uuid-1", "confirm": True}, None)

        assert result["success"] is True
        patches = [json.loads(c[2]["body"]) for c in http.calls if c[0] == "PATCH"]
        assert patches == [{"state": "offline"}]

    def test_waits_for_the_offline_job_before_deleting(self, mock_secrets):
        from handler import handler

        http = MockHttp(
            {
                "/storage/volumes/uuid-1": {"data": {"job": {"uuid": "job-1"}}},
                "/cluster/jobs/job-1": {"data": {"state": "success", "message": "done"}},
            }
        )
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http

            result = handler(
                {
                    "action": "deleteVolume",
                    "volumeUuid": "uuid-1",
                    "volumeName": "vol1",
                    "confirm": True,
                },
                None,
            )

        assert result["success"] is True
        # The offline is polled before the DELETE is issued, not after.
        methods = [c[0] for c in http.calls]
        assert methods.index("GET") < methods.index("DELETE")


class TestBringVolumeOnline:
    """Reversing the offline step a failed delete leaves behind.

    The delete above takes the volume offline as its second step, and the third can fail:
    ONTAP refused one with "it has one or more clones" after the clone had already gone.
    That leaves a volume offline -- unreachable to its clients -- and until this action
    existed nothing in the portal could undo the step that had succeeded.
    """

    def test_requires_a_uuid(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()
            result = handler({"action": "bringVolumeOnline", "volumeName": "vol1"}, None)

        assert result["success"] is False
        assert "volumeUuid" in result["error"]

    def test_patches_the_state_to_online(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/storage/volumes/uuid-1": {"data": {}}})
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler(
                {"action": "bringVolumeOnline", "volumeUuid": "uuid-1", "volumeName": "vol1"},
                None,
            )

        assert result["success"] is True
        method, url, kwargs = http.find("PATCH", "/storage/volumes/uuid-1")
        assert json.loads(kwargs["body"]) == {"state": "online"}

    def test_does_not_remount(self, mock_secrets):
        """The junction path the delete cleared is a separate decision.

        Remounting at a path the operator has not named again would be a guess at where
        the volume belongs.
        """
        from handler import handler

        http = MockHttp({"/storage/volumes/uuid-1": {"data": {}}})
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            handler({"action": "bringVolumeOnline", "volumeUuid": "uuid-1"}, None)

        bodies = [json.loads(c[2]["body"]) for c in http.calls if c[0] == "PATCH"]
        assert all("nas" not in b for b in bodies)


class TestVolumeRebalance:
    """Capacity rebalancing on a FlexGroup volume.

    A FlexGroup reports no space when any one constituent is full, so the interesting
    question is not the volume's used percentage but how far its constituents have
    drifted apart. Three things have to stay distinguishable here, because two of them
    read the same way if the code is careless: a volume of the wrong style, a FlexGroup
    ONTAP does not track rebalancing for, and a FlexGroup with nothing to do.
    """

    @pytest.fixture(autouse=True)
    def _secrets(self, mock_secrets):
        """Every case here reaches ONTAP."""

    @staticmethod
    def _http(volume: dict):
        return MockHttp({"/storage/volumes/uuid-1": {"data": volume}})

    FLEXGROUP = {
        "name": "fg1",
        "style": "flexgroup",
        "constituents": [{"name": "fg1__0001"}, {"name": "fg1__0002"}],
        "rebalancing": {
            "state": "not_running",
            "imbalance_percent": 3,
            "imbalance_size": 12288,
            "max_constituent_imbalance_percent": 27,
            "max_runtime": "PT6H",
            "min_file_size": 104857600,
            "max_threshold": 20,
            "min_threshold": 5,
            "max_file_moves": 25,
            "exclude_snapshots": True,
        },
    }

    def test_a_flexvol_is_answered_rather_than_failed(self):
        """The panel has to be able to say why the operation is not offered."""
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = self._http({"name": "vol1", "style": "flexvol"})
            result = handler({"action": "getVolumeRebalance", "volumeUuid": "uuid-1"}, None)

        assert result["error"] is None
        assert result["supported"] is False
        assert result["reason"] == "NOT_FLEXGROUP"
        assert result["volumeStyle"] == "flexvol"

    def test_an_object_store_volume_is_reported_by_its_own_reason(self):
        """An ONTAP S3 bucket's backing volume is a FlexGroup and still unsupported.

        Reporting only the style here would leave the panel offering the operation on
        the one FlexGroup where NetApp documents it as unavailable.
        """
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = self._http(
                {"name": "fg_oss", "style": "flexgroup", "is_object_store": True, "constituents": [{"name": "a"}]}
            )
            result = handler({"action": "getVolumeRebalance", "volumeUuid": "uuid-1"}, None)

        assert result["supported"] is False
        assert result["reason"] == "OBJECT_STORE"
        assert result["constituentCount"] == 1

    def test_a_flexgroup_without_a_rebalancing_object_is_not_reported_as_unknown(self):
        """Measured on this file system with every field requested: a FlexCache cache
        volume is a FlexGroup and carries no rebalancing object at all. Defaulting its
        state to "unknown" with zeroes would look like a balanced volume ONTAP had
        merely failed to inspect, and the panel would offer to start an operation.
        """
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = self._http({"name": "cache1", "style": "flexgroup"})
            result = handler({"action": "getVolumeRebalance", "volumeUuid": "uuid-1"}, None)

        assert result["supported"] is True
        assert result["reported"] is False

    def test_reports_the_worst_constituent_alongside_the_volume(self):
        """The volume can read 3% out of balance while a constituent is at 27%.

        The constituent is the one that returns ENOSPC, so both numbers travel.
        """
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = self._http(self.FLEXGROUP)
            result = handler({"action": "getVolumeRebalance", "volumeUuid": "uuid-1"}, None)

        assert result["reported"] is True
        assert result["constituentCount"] == 2
        assert result["rebalance"]["imbalancePercent"] == 3
        assert result["rebalance"]["maxConstituentImbalancePercent"] == 27
        # The settings the next run will use, read from the volume rather than assumed.
        assert result["rebalance"]["maxRuntime"] == "PT6H"
        assert result["rebalance"]["minFileSizeBytes"] == 104857600
        assert result["rebalance"]["maxThresholdPercent"] == 20

    def test_asks_ontap_for_the_fields_that_decide_eligibility(self):
        """`rebalancing`, `is_object_store` and `constituents` are explicit-request
        fields. Without them the answer is silence, which reads as "nothing to do".
        """
        from handler import handler

        http = self._http(self.FLEXGROUP)
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            handler({"action": "getVolumeRebalance", "volumeUuid": "uuid-1"}, None)

        _, url, _ = http.find("GET", "/storage/volumes/uuid-1")
        for field in ("rebalancing", "is_object_store", "granular_data", "constituents"):
            assert field in url

    def test_start_requires_the_acknowledgement(self):
        """Starting enables granular data, which cannot be switched off again."""
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = self._http(self.FLEXGROUP)
            result = handler({"action": "startVolumeRebalance", "volumeUuid": "uuid-1"}, None)

        assert result["success"] is False
        assert "acknowledgeIrreversible" in result["error"]
        assert "granular data" in result["error"]
        # And it points at the rebalancing documentation rather than at the SnapLock
        # design note, which is where the shared helper's default sends readers.
        assert "tamperproof" not in result["error"]

    def test_start_refuses_a_flexvol(self):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = self._http({"name": "vol1", "style": "flexvol"})
            result = handler(
                {"action": "startVolumeRebalance", "volumeUuid": "uuid-1", "acknowledgeIrreversible": True},
                None,
            )

        assert result["success"] is False
        assert "FlexGroup" in result["error"]

    def test_start_refuses_an_object_store_volume(self):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = self._http({"name": "fg_oss", "style": "flexgroup", "is_object_store": True})
            result = handler(
                {"action": "startVolumeRebalance", "volumeUuid": "uuid-1", "acknowledgeIrreversible": True},
                None,
            )

        assert result["success"] is False
        assert "ONTAP S3" in result["error"]

    def test_start_refuses_while_one_is_running(self):
        """Two rebalances on one volume is not a state ONTAP offers."""
        from handler import handler

        running = dict(self.FLEXGROUP, rebalancing={"state": "rebalancing"})
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = self._http(running)
            result = handler(
                {"action": "startVolumeRebalance", "volumeUuid": "uuid-1", "acknowledgeIrreversible": True},
                None,
            )

        assert result["success"] is False
        assert "already" in result["error"]

    def test_start_refuses_a_runtime_that_is_not_a_period(self):
        """ONTAP rejects it too, but only after the caller has been told it started."""
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = self._http(self.FLEXGROUP)
            result = handler(
                {
                    "action": "startVolumeRebalance",
                    "volumeUuid": "uuid-1",
                    "acknowledgeIrreversible": True,
                    "maxRuntime": "6h",
                },
                None,
            )

        assert result["success"] is False
        assert "ISO-8601" in result["error"]

    def test_start_sends_the_state_and_the_options_it_was_given(self):
        from handler import handler

        http = self._http(self.FLEXGROUP)
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler(
                {
                    "action": "startVolumeRebalance",
                    "volumeUuid": "uuid-1",
                    "acknowledgeIrreversible": True,
                    "maxRuntime": "P1D",
                    "startTime": "2026-08-20T02:00:00Z",
                },
                None,
            )

        assert result["success"] is True
        # A start_time makes it a schedule rather than a start, and the caller is told
        # which of the two happened.
        assert result["scheduled"] is True
        _, _, kwargs = http.find("PATCH", "/storage/volumes/uuid-1")
        assert json.loads(kwargs["body"]) == {
            "rebalancing": {"state": "starting", "max_runtime": "P1D", "start_time": "2026-08-20T02:00:00Z"}
        }

    def test_start_without_a_runtime_leaves_ontaps_default_alone(self):
        """Six hours. Sending an explicit value would freeze a default that is ONTAP's
        to choose, and a run that hits the limit is not a failure.
        """
        from handler import handler

        http = self._http(self.FLEXGROUP)
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            handler(
                {"action": "startVolumeRebalance", "volumeUuid": "uuid-1", "acknowledgeIrreversible": True},
                None,
            )

        _, _, kwargs = http.find("PATCH", "/storage/volumes/uuid-1")
        assert json.loads(kwargs["body"]) == {"rebalancing": {"state": "starting"}}

    def test_stop_sends_stopping_and_needs_no_acknowledgement(self):
        """Stopping takes nothing away that starting had not already committed."""
        from handler import handler

        http = self._http({})
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler(
                {"action": "stopVolumeRebalance", "volumeUuid": "uuid-1", "volumeName": "fg1"},
                None,
            )

        assert result["success"] is True
        _, _, kwargs = http.find("PATCH", "/storage/volumes/uuid-1")
        assert json.loads(kwargs["body"]) == {"rebalancing": {"state": "stopping"}}


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

        http = MockHttp({"/svm/svms": {"data": {"records": [{"uuid": "svm-uuid-1"}]}}})
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler({"action": "deleteLocalUser", "sid": "S-1-5-21-1", "name": "bob"}, None)

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
            result = handler({"action": "createFlexCache", "name": "cache1", "sizeGiB": 10}, None)

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

        http = MockHttp({"/storage/flexcache/flexcaches": {"data": {"job": {"uuid": "job-1"}}}})
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
        body = json.loads(http.find("POST", "/storage/flexcache/flexcaches")[2]["body"])
        assert body["size"] == 10 * 1024**3
        assert body["path"] == "/cache1"
        assert body["prepopulate"] == {"dir_paths": ["/a", "/b"]}
        assert body["origins"][0]["volume"]["name"] == "vol1"
        # Auto-provisioning on FSx for ONTAP has to be told a FabricPool aggregate is
        # acceptable, or the job fails with "Aggregates not matching FabricPool
        # requirements" after the POST has already been accepted.
        assert body["use_tiered_aggregate"] is True
        assert "constituents_per_aggregate" not in body

    def test_delete_requires_uuid(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()
            result = handler({"action": "deleteFlexCache", "name": "cache1"}, None)

        assert result["success"] is False
        assert "uuid" in result["error"]

    def test_writeback_requires_an_explicit_state(self, mock_secrets):
        """Omitting `enabled` must not be read as a mode change in either direction."""
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()
            result = handler({"action": "setFlexcacheWriteback", "uuid": "uuid-1"}, None)

        assert result["success"] is False
        assert "enabled" in result["error"]

    def test_writeback_patches_the_nested_field(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/storage/flexcache/flexcaches/uuid-1": {"data": {}}})
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler(
                {"action": "setFlexcacheWriteback", "uuid": "uuid-1", "enabled": True},
                None,
            )

        assert result["success"] is True
        assert result["writebackEnabled"] is True
        body = json.loads(http.find("PATCH", "/storage/flexcache/flexcaches/uuid-1")[2]["body"])
        assert body == {"writeback": {"enabled": True}}

    def test_create_omits_writeback_unless_asked(self, mock_secrets):
        """A cluster older than 9.15.1 has no such field, so false is not sent as false."""
        from handler import handler

        http = MockHttp({"/storage/flexcache/flexcaches": {"data": {}}})
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            handler(
                {
                    "action": "createFlexCache",
                    "name": "cache1",
                    "originVolume": "vol1",
                    "sizeGiB": 10,
                },
                None,
            )

        body = json.loads(http.find("POST", "/storage/flexcache/flexcaches")[2]["body"])
        assert "writeback" not in body

    def test_create_sends_writeback_when_asked(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/storage/flexcache/flexcaches": {"data": {}}})
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            handler(
                {
                    "action": "createFlexCache",
                    "name": "cache1",
                    "originVolume": "vol1",
                    "sizeGiB": 10,
                    "writebackEnabled": True,
                },
                None,
            )

        body = json.loads(http.find("POST", "/storage/flexcache/flexcaches")[2]["body"])
        assert body["writeback"] == {"enabled": True}

    def test_delete_of_a_writeback_cache_is_refused_on_the_call(self, mock_secrets):
        """ONTAP 66846980 arrives on the DELETE, before any job exists.

        Measured on 9.18.1P3D1. ONTAP's own message names the endpoint to PATCH, so the
        hint adds only what it omits: that disabling moves data.
        """
        from handler import handler

        http = MockHttp(
            {
                "/storage/flexcache/flexcaches/uuid-1": {
                    "status": 400,
                    "data": {
                        "error": {
                            "code": "66846980",
                            "message": (
                                'Failed to delete FlexCache volume "c" in SVM "s" because '
                                'the "writeback.enabled" property is true.'
                            ),
                        }
                    },
                },
            }
        )
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler({"action": "deleteFlexCache", "uuid": "uuid-1"}, None)

        assert result["success"] is False
        assert "flushes" in result["error"]

    def test_delete_reports_a_failed_job(self, mock_secrets):
        """The other path: accepted with a 202, then failed inside the job."""
        from handler import handler

        http = MockHttp(
            {
                "/storage/flexcache/flexcaches/uuid-1": {"data": {"job": {"uuid": "job-1"}}},
                "/cluster/jobs/job-1": {"data": {"state": "failure", "message": "No suitable storage can be found"}},
            }
        )
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler({"action": "deleteFlexCache", "uuid": "uuid-1"}, None)

        assert result["success"] is False
        assert "No suitable storage" in result["error"]


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
        body = json.loads(http.find("POST", "/storage/volumes")[2]["body"])
        assert body["name"] == "c1"
        assert body["clone"]["parent_volume"] == {"name": "vol1"}
        assert body["clone"]["parent_snapshot"] == {"name": "snap1"}
        # What makes it a clone rather than a volume that mentions a parent. Without it
        # ONTAP reads this as an ordinary volume create and answers 787140, asking for an
        # aggregate or a style -- and satisfying *that* produces a 20 MB volume with no
        # clone relationship, reported as success. Measured 2026-08-15 on 9.18.1P3D1.
        assert body["clone"]["is_flexclone"] is True
        # Placement is the parent's. Naming an aggregate here is the trap above.
        assert "aggregates" not in body
        assert "style" not in body
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

        body = json.loads(http.find("POST", "/storage/volumes")[2]["body"])
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


# --- SnapMirror (inventory and lifecycle) ---


class TestSnapMirror:
    def test_list_maps_source_and_destination(self, mock_secrets):
        from handler import handler

        with snapmirror_client(
            MockHttp(
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
        ):
            result = handler({"action": "listSnapmirrorRelationships"}, None)

        rel = result["relationships"][0]
        assert rel["sourcePath"] == "svmA:vol1"
        assert rel["destinationSvm"] == "svmB"
        assert rel["healthy"] is True
        assert rel["policy"] == "MirrorAllSnapshots"

    def test_snapmirror_does_not_request_unsupported_fields(self, mock_secrets):
        """Guard the requested `fields` list, not just the response mapping.

        A mock ONTAP returns records whatever `fields` we ask for, so asserting
        only on the mapped output cannot catch an invalid field name. Real ONTAP
        9.17 rejects the entire request when one field is unknown, which silently
        emptied the relationship list until this was found on a live cluster.
        """
        from handler import handler

        mock_http = MockHttp()
        with snapmirror_client(mock_http):
            handler({"action": "listSnapmirrorRelationships"}, None)

        urls = [url for _method, url, _kwargs in mock_http.calls]
        assert any("/snapmirror/relationships" in u for u in urls)
        assert not any("last_transfer_size" in u for u in urls)

    def test_transfers_require_relationship_uuid(self, mock_secrets):
        from handler import handler

        with snapmirror_client(MockHttp()):
            result = handler({"action": "getSnapmirrorTransfers"}, None)

        assert result["transfers"] == []
        assert "relationshipUuid" in result["error"]

    def test_transfers_maps_fields(self, mock_secrets):
        from handler import handler

        with snapmirror_client(
            MockHttp(
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
        ):
            result = handler({"action": "getSnapmirrorTransfers", "relationshipUuid": "r1"}, None)

        assert result["transfers"][0]["bytesTransferred"] == 2048
        assert result["transfers"][0]["duration"] == "PT30S"

    def test_transfers_are_newest_first(self, mock_secrets):
        """ONTAP does not order these, and the panel presents them as a history.

        Measured after an update: the transfer that had just run came back third of five,
        so the row a reader looks at first was not the one they had just caused.
        """
        from handler import handler

        with snapmirror_client(
            MockHttp(
                {
                    "/transfers": {
                        "data": {
                            "records": [
                                {"state": "success", "end_time": "2026-08-03T00:00:00Z"},
                                {"state": "success", "end_time": "2026-08-05T00:00:00Z"},
                                {"state": "success", "end_time": "2026-08-04T00:00:00Z"},
                            ]
                        }
                    }
                }
            )
        ):
            result = handler({"action": "getSnapmirrorTransfers", "relationshipUuid": "r1"}, None)

        assert [t["endTime"] for t in result["transfers"]] == [
            "2026-08-05T00:00:00Z",
            "2026-08-04T00:00:00Z",
            "2026-08-03T00:00:00Z",
        ]

    def test_a_running_transfer_sorts_above_finished_ones(self, mock_secrets):
        """It has no end time, and it is the one the reader is waiting on."""
        from handler import handler

        with snapmirror_client(
            MockHttp(
                {
                    "/transfers": {
                        "data": {
                            "records": [
                                {"state": "success", "end_time": "2026-08-05T00:00:00Z"},
                                {"state": "transferring", "bytes_transferred": 128},
                            ]
                        }
                    }
                }
            )
        ):
            result = handler({"action": "getSnapmirrorTransfers", "relationshipUuid": "r1"}, None)

        assert result["transfers"][0]["state"] == "transferring"


# --- Vscan (status and policy management) ---


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
            mock_pool.return_value = MockHttp({"/protocols/vscan": {"data": {"records": [{"enabled": True}]}}})
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


# --- FPolicy (status and policy management) ---


class TestFPolicy:
    def test_status_flattens_connections(self, mock_secrets):
        from handler import handler

        # Server connection status lives on /protocols/fpolicy/{svm.uuid}/connections,
        # so the handler resolves the SVM UUID first and the records it reads are the
        # connections themselves. Asking /protocols/fpolicy for a `connections` field
        # made ONTAP reject the whole request.
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp(
                {
                    "/svm/svms": {"data": {"records": [{"uuid": "svm-uuid-1"}]}},
                    "/connections": {
                        "data": {
                            "records": [
                                {
                                    "node": {"name": "node1"},
                                    "policy": {"name": "audit"},
                                    "server": "198.51.100.10",
                                    "state": "connected",
                                }
                            ]
                        }
                    },
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


class TestSharedClientConstruction:
    """Guard the two properties of _shared_client() that tests depend on."""

    def test_uses_the_handler_module_boto3_session(self):
        """A client with its own session escapes `patch("handler.boto3")`.

        Every other action in this handler reads its credential through
        `handler.boto3`, so patching that module used to control all AWS access. A
        client building its own session breaks that, and the symptom is not a
        failing test: the unpatched test reaches real Secrets Manager and hangs on
        credential discovery. That happened while this was being written.
        """
        import handler as handler_module

        with patch("handler.boto3") as mock_boto3:
            client = handler_module._shared_client()

        assert client._session is mock_boto3.Session.return_value

    def test_tls_verification_matches_the_rest_of_the_handler(self):
        """The other actions use cert_reqs=CERT_NONE; this must not differ silently.

        Turning verification on is not a flag flip. The FSx for ONTAP management
        LIF presents a self-signed certificate by default, so a client that
        verifies would fail every SnapMirror call in an environment where the rest
        of the handler works.
        """
        import handler as handler_module

        with patch("handler.boto3"):
            client = handler_module._shared_client()

        assert client._config.verify_ssl is False


# --- SnapMirror write operations ---


class TestSnapMirrorWrites:
    def test_update_now_posts_transfer(self, mock_secrets):
        from handler import handler

        http = MockHttp(
            {
                "/cluster/jobs/j1": {"data": {"state": "success", "message": "done"}},
                "/transfers": {"data": {"job": {"uuid": "j1"}}},
            }
        )
        with snapmirror_client(http):
            result = handler({"action": "updateSnapmirrorNow", "relationshipUuid": "r1"}, None)

        assert result["success"] is True
        assert result["jobId"] == "j1"
        method, url, _ = http.calls[0]
        assert method == "POST"
        assert url.endswith("/snapmirror/relationships/r1/transfers")

    def test_a_failed_transfer_job_is_reported_as_a_failure(self, mock_secrets):
        """The SnapMirror actions reach ONTAP through the shared client, and that
        transport had no job confirmation at all: every one of them reported the 202."""
        from handler import handler

        http = MockHttp(
            {
                "/cluster/jobs/j1": {"data": {"state": "failure", "message": "not peered for snapmirror"}},
                "/transfers": {"data": {"job": {"uuid": "j1"}}},
            }
        )
        with snapmirror_client(http):
            result = handler({"action": "updateSnapmirrorNow", "relationshipUuid": "r1"}, None)

        assert result["success"] is False
        # Translated, not passed through raw.
        assert "applications include snapmirror" in result["error"]

    def test_a_failed_break_job_is_reported_as_a_failure(self, mock_secrets):
        from handler import handler

        http = MockHttp(
            {
                "/cluster/jobs/j2": {"data": {"state": "failure", "message": "relationship is transferring"}},
                "/snapmirror/relationships/r1": {"data": {"job": {"uuid": "j2"}}},
            }
        )
        with snapmirror_client(http):
            result = handler({"action": "breakSnapmirror", "relationshipUuid": "r1", "confirm": True}, None)

        assert result["success"] is False
        assert "transferring" in result["error"]

    def test_update_now_requires_uuid(self, mock_secrets):
        from handler import handler

        with snapmirror_client(MockHttp()):
            result = handler({"action": "updateSnapmirrorNow"}, None)

        assert result["success"] is False
        assert "relationshipUuid" in result["error"]

    def test_quiesce_patches_state_paused(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/snapmirror/relationships/r1": {"data": {}}})
        with snapmirror_client(http):
            result = handler({"action": "quiesceSnapmirror", "relationshipUuid": "r1"}, None)

        assert result["state"] == "paused"
        assert json.loads(http.calls[0][2]["body"]) == {"state": "paused"}

    def test_resume_patches_state_snapmirrored(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/snapmirror/relationships/r1": {"data": {}}})
        with snapmirror_client(http):
            result = handler({"action": "resumeSnapmirror", "relationshipUuid": "r1"}, None)

        assert result["state"] == "snapmirrored"

    def test_break_requires_confirm(self, mock_secrets):
        from handler import handler

        with snapmirror_client(MockHttp()):
            result = handler({"action": "breakSnapmirror", "relationshipUuid": "r1"}, None)

        assert result["success"] is False
        assert "confirm" in result["error"]

    def test_break_patches_broken_off_when_confirmed(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/snapmirror/relationships/r1": {"data": {}}})
        with snapmirror_client(http):
            result = handler({"action": "breakSnapmirror", "relationshipUuid": "r1", "confirm": True}, None)

        assert result["success"] is True
        assert json.loads(http.calls[0][2]["body"]) == {"state": "broken_off"}

    def test_resync_requires_confirm(self, mock_secrets):
        from handler import handler

        with snapmirror_client(MockHttp()):
            result = handler({"action": "resyncSnapmirror", "relationshipUuid": "r1"}, None)

        assert result["success"] is False
        assert "confirm" in result["error"]

    def test_abort_transfer_patches_aborted(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/transfers/t1": {"data": {}}})
        with snapmirror_client(http):
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

        with snapmirror_client(MockHttp()):
            result = handler({"action": "deleteSnapmirror", "relationshipUuid": "r1"}, None)

        assert result["success"] is False
        assert "confirm" in result["error"]

    def test_write_error_is_propagated(self, mock_secrets):
        from handler import handler

        with snapmirror_client(
            MockHttp(
                {
                    "/snapmirror/relationships/r1": {
                        "status": 409,
                        "data": {"error": {"message": "relationship is busy"}},
                    }
                }
            )
        ):
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
            result = handler({"action": "createFpolicyEvent", "name": "ev1", "protocol": "cifs"}, None)

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
            result = handler({"action": "setFpolicyPolicyEnabled", "name": "audit", "enabled": True}, None)

        assert result["success"] is False
        assert "priority" in result["error"]

    def test_disable_policy_omits_priority(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/svm/svms": {"data": {"records": [{"uuid": "svm-1"}]}}})
        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = http
            result = handler({"action": "setFpolicyPolicyEnabled", "name": "audit", "enabled": False}, None)

        assert result["success"] is True
        body = json.loads(http.calls[-1][2]["body"])
        assert body == {"enabled": False}

    def test_delete_event_uses_svm_scoped_path(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/svm/svms": {"data": {"records": [{"uuid": "svm-1"}]}}})
        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = http
            result = handler({"action": "deleteFpolicyEvent", "name": "ev1", "confirm": True}, None)

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
            result = handler({"action": "createClusterPeer", "remoteAddresses": ["198.51.100.7"]}, None)

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
                {"/cluster/peers": {"data": {"records": [{"authentication": {"passphrase": "abc-123"}}]}}}
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
            result = handler({"action": "acceptClusterPeer", "uuid": "cp1", "passphrase": "abc"}, None)

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
                {"/cluster?": {"data": {"name": "Cluster1", "version": {"full": "NetApp Release 9.17.1"}}}}
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
            result = handler({"action": "setNetworkInterfaceEnabled", "uuid": "i1", "enabled": False}, None)

        assert result["success"] is False
        assert "confirm" in result["error"]

    def test_enabling_a_lif_needs_no_confirm(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/network/ip/interfaces/i1": {"data": {}}})
        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = http
            result = handler({"action": "setNetworkInterfaceEnabled", "uuid": "i1", "enabled": True}, None)

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
                    "/protocols/nfs/services": {"data": {"records": [{"enabled": True, "state": "online"}]}},
                    "/protocols/cifs/services": {
                        "data": {"records": [{"enabled": True, "ad_domain": {"fqdn": "demo.fsx.local"}}]}
                    },
                    "/protocols/s3/services": {"data": {"records": [{"enabled": True, "name": "svm1_s3"}]}},
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
            result = handler({"action": "setProtocolServiceEnabled", "protocol": "smb", "enabled": True}, None)

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


class TestConfirmGatedDeletesMatchUiPayloads:
    """Assert the confirm-gated deletes accept exactly what the UI sends.

    A panel that omits ``confirm`` renders a delete button that can never
    succeed. That shipped once for Vscan and FPolicy, so the contract is pinned
    here: without ``confirm`` the handler must refuse, and with the parameters
    the UI actually sends it must succeed.
    """

    # (action, params the UI sends, response key the handler writes to)
    UI_DELETE_PAYLOADS = [
        ("deleteVscanPolicy", {"name": "scan_all_cifs", "confirm": True}, "/on-access-policies"),
        ("deleteFpolicyPolicy", {"name": "audit_all", "confirm": True}, "/policies"),
        ("deleteFpolicyEvent", {"name": "file_ops_cifs", "confirm": True}, "/events"),
        ("deleteSnapmirror", {"relationshipUuid": "sm-1", "confirm": True}, "/snapmirror"),
        ("breakSnapmirror", {"relationshipUuid": "sm-1", "confirm": True}, "/snapmirror"),
        ("resyncSnapmirror", {"relationshipUuid": "sm-1", "confirm": True}, "/snapmirror"),
        ("deleteClusterPeer", {"uuid": "cp-1", "confirm": True}, "/cluster/peers"),
        ("deleteSvmPeer", {"uuid": "sp-1", "confirm": True}, "/svm/peers"),
    ]

    @pytest.mark.parametrize("action,params,_path", UI_DELETE_PAYLOADS)
    def test_refuses_without_confirm(self, action, params, _path, mock_secrets):
        from handler import handler

        without_confirm = {k: v for k, v in params.items() if k != "confirm"}
        pool = MockHttp({"/svm/svms": {"data": {"records": [{"uuid": "u1"}]}}})
        # Three of these actions go through the shared client and five through
        # this handler's own pool, so both are faked for every row.
        with patch("handler.urllib3.PoolManager", return_value=pool), snapmirror_client(pool):
            result = handler({"action": action, **without_confirm}, None)

        assert result.get("success") is False, f"{action} should refuse without confirm"
        assert "confirm" in (result.get("error") or "").lower()

    @pytest.mark.parametrize("action,params,_path", UI_DELETE_PAYLOADS)
    def test_succeeds_with_ui_payload(self, action, params, _path, mock_secrets):
        from handler import handler

        pool = MockHttp({"/svm/svms": {"data": {"records": [{"uuid": "u1"}]}}})
        with patch("handler.urllib3.PoolManager", return_value=pool), snapmirror_client(pool):
            result = handler({"action": action, **params}, None)

        assert result.get("success") is True, f"{action} failed with the UI payload: {result}"
        assert result.get("error") is None

    def test_delete_vscan_policy_targets_the_named_policy(self, mock_secrets):
        """The policy name must appear in the request path, not the body."""
        from handler import handler

        http = MockHttp({"/svm/svms": {"data": {"records": [{"uuid": "svm-1"}]}}})
        with patch("handler.urllib3.PoolManager") as mp:
            mp.return_value = http
            result = handler(
                {"action": "deleteVscanPolicy", "name": "scan_all_cifs", "confirm": True},
                None,
            )

        assert result["success"] is True
        deletes = [c for c in http.calls if c[0] == "DELETE"]
        assert len(deletes) == 1
        assert "/protocols/vscan/svm-1/on-access-policies/scan_all_cifs" in deletes[0][1]


# --- Request path safety ---


class TestRequestPathSafety:
    """Caller-supplied names must not be able to redirect an ONTAP request.

    Many actions build the request path from a name the caller sent. Without
    encoding, a value containing a traversal segment sends the request to a
    different endpoint than the action advertises — a share delete reaching a
    cluster resource, for example.
    """

    def test_traversal_segment_is_refused(self):
        from handler import _is_unsafe_path

        assert _is_unsafe_path("/protocols/cifs/shares/uuid/../../cluster/nodes")
        assert _is_unsafe_path("/storage/volumes/..")

    def test_dots_inside_a_name_are_allowed(self):
        """`..` within a segment is a legal character sequence in a name."""
        from handler import _is_unsafe_path

        assert not _is_unsafe_path("/protocols/cifs/shares/uuid/my..share")
        assert not _is_unsafe_path("/storage/volumes?name=vol.1.2")

    def test_control_characters_and_backslash_are_refused(self):
        from handler import _is_unsafe_path

        assert _is_unsafe_path("/storage/volumes/a\nb")
        assert _is_unsafe_path("/storage/volumes/a\x00b")
        assert _is_unsafe_path("/storage/volumes/a\\b")

    def test_ordinary_paths_pass(self):
        from handler import _is_unsafe_path

        assert not _is_unsafe_path("/storage/volumes?svm.name=svm1&fields=uuid")
        assert not _is_unsafe_path("/protocols/cifs/shares/1234-5678/data")

    def test_unsafe_path_never_reaches_the_network(self, mock_secrets):
        from handler import _ontap_request

        mock_http = MockHttp()
        result = _ontap_request(mock_http, {}, "DELETE", "/protocols/cifs/shares/u/../../cluster")

        assert result["_error"] is True
        assert result["_status"] == 400
        assert mock_http.calls == []

    def test_share_name_is_percent_encoded(self, mock_secrets):
        from handler import handler

        mock_http = MockHttp()
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = mock_http
            handler(
                {
                    "action": "deleteCifsShare",
                    "name": "../../cluster/nodes",
                    "confirm": True,
                },
                None,
            )

        urls = [url for _m, url, _k in mock_http.calls]
        # The traversal must be encoded rather than forming path segments.
        assert not any("/../" in u for u in urls), urls

    def test_svm_query_value_is_encoded(self, mock_secrets):
        """An `&` in a name would otherwise append query parameters."""
        from handler import handler

        mock_http = MockHttp()
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = mock_http
            handler({"action": "listVolumes", "svm": "svm1&fields=uuid"}, None)

        urls = [url for _m, url, _k in mock_http.calls]
        assert any("svm1%26fields%3Duuid" in u for u in urls), urls


# --- Irreversible-operation acknowledgement ----------------------------------
#
# The portal shows a dialog stating what becomes undeletable and until when, but
# that dialog is client-side. These tests hold the server side of it: the lock
# must not be creatable by a caller that never saw the consequences, whether that
# is a script, a direct AppSync call, or an agent.
#
# Each case asserts both directions. Asserting only the refusal would pass just
# as well if the guard rejected everything, and asserting only the success would
# pass if the guard were removed.


class TestIrreversibleAcknowledgement:
    def test_snaplock_volume_refused_without_ack(self, mock_secrets):
        from handler import handler

        mock_http = MockHttp(
            {
                "/storage/aggregates": {"data": {"records": [{"name": "aggr1"}]}},
                "/storage/volumes": {"status": 202, "data": {}},
            }
        )
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = mock_http

            result = handler(
                {
                    "action": "createVolume",
                    "name": "worm_vol",
                    "sizeGiB": 50,
                    "snaplockType": "enterprise",
                    "retentionDefault": "P30D",
                },
                None,
            )

        assert result["success"] is False
        assert "acknowledgeIrreversible" in result["error"]
        # The refusal has to name the effect, not just demand a flag.
        assert "cannot be deleted" in result["error"]
        # Nothing may reach ONTAP: a refusal that still created the volume would
        # be worse than no guard at all.
        assert not any(method == "POST" for method, _url, _kwargs in mock_http.calls)

    def test_snaplock_volume_created_with_ack(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp(
                {
                    "/storage/aggregates": {"data": {"records": [{"name": "aggr1"}]}},
                    "/storage/volumes": {"status": 202, "data": {}},
                }
            )

            result = handler(
                {
                    "action": "createVolume",
                    "name": "worm_vol",
                    "sizeGiB": 50,
                    "snaplockType": "enterprise",
                    "retentionDefault": "P30D",
                    "acknowledgeIrreversible": True,
                },
                None,
            )

        assert result["success"] is True

    def test_plain_volume_needs_no_ack(self, mock_secrets):
        """The guard is scoped to SnapLock, so ordinary volume work is unchanged."""
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp(
                {
                    "/storage/aggregates": {"data": {"records": [{"name": "aggr1"}]}},
                    "/storage/volumes": {"status": 202, "data": {}},
                }
            )

            result = handler(
                {"action": "createVolume", "name": "plain_vol", "sizeGiB": 50},
                None,
            )

        assert result["success"] is True

    def test_ack_must_be_true_not_truthy(self, mock_secrets):
        """A string body would make `if event.get(...)` pass; the check is `is True`."""
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp(
                {
                    "/storage/aggregates": {"data": {"records": [{"name": "aggr1"}]}},
                    "/storage/volumes": {"status": 202, "data": {}},
                }
            )

            result = handler(
                {
                    "action": "createVolume",
                    "name": "worm_vol",
                    "sizeGiB": 50,
                    "snaplockType": "compliance",
                    "acknowledgeIrreversible": "true",
                },
                None,
            )

        assert result["success"] is False
        assert "acknowledgeIrreversible" in result["error"]

    def test_retention_update_refused_without_ack(self, mock_secrets):
        from handler import handler

        mock_http = MockHttp()
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = mock_http

            result = handler(
                {"action": "updateSnaplockRetention", "volumeUuid": "uuid-1", "days": 30},
                None,
            )

        assert result["success"] is False
        assert "acknowledgeIrreversible" in result["error"]
        assert "30 days" in result["error"]
        assert not any(method == "PATCH" for method, _url, _kwargs in mock_http.calls)

    def test_retention_update_applied_with_ack(self, mock_secrets):
        from handler import handler

        mock_http = MockHttp()
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = mock_http

            result = handler(
                {
                    "action": "updateSnaplockRetention",
                    "volumeUuid": "uuid-1",
                    "days": 30,
                    "acknowledgeIrreversible": True,
                },
                None,
            )

        assert result["success"] is True
        assert any(method == "PATCH" for method, _url, _kwargs in mock_http.calls)

    def test_enable_snapshot_locking_refused_without_ack(self, mock_secrets):
        from handler import handler

        mock_http = MockHttp()
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = mock_http

            result = handler(
                {"action": "enableSnapshotLocking", "volumeUuid": "uuid-1", "enabled": True},
                None,
            )

        assert result["success"] is False
        assert "cannot be disabled" in result["error"]
        assert not any(method == "PATCH" for method, _url, _kwargs in mock_http.calls)

    def test_enable_snapshot_locking_allowed_with_ack(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()

            result = handler(
                {
                    "action": "enableSnapshotLocking",
                    "volumeUuid": "uuid-1",
                    "enabled": True,
                    "acknowledgeIrreversible": True,
                },
                None,
            )

        assert result["success"] is True

    def test_disabling_snapshot_locking_needs_no_ack(self, mock_secrets):
        """Only enabling creates the one-way state; disabling creates no lock."""
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()

            result = handler(
                {"action": "enableSnapshotLocking", "volumeUuid": "uuid-1", "enabled": False},
                None,
            )

        # ONTAP refuses this itself; the point is that the guard is not what
        # refused it, so the caller sees the real reason.
        assert "acknowledgeIrreversible" not in str(result.get("error") or "")

    def test_lock_snapshot_refused_without_ack(self, mock_secrets):
        from handler import handler

        mock_http = MockHttp()
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = mock_http

            result = handler(
                {
                    "action": "lockSnapshot",
                    "volumeUuid": "uuid-1",
                    "snapshotUuid": "snap-1",
                    "retentionDays": 7,
                },
                None,
            )

        assert result["success"] is False
        assert "acknowledgeIrreversible" in result["error"]
        assert "7 days" in result["error"]
        assert not any(method == "PATCH" for method, _url, _kwargs in mock_http.calls)

    def test_lock_snapshot_allowed_with_ack(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()

            result = handler(
                {
                    "action": "lockSnapshot",
                    "volumeUuid": "uuid-1",
                    "snapshotUuid": "snap-1",
                    "retentionDays": 7,
                    "acknowledgeIrreversible": True,
                },
                None,
            )

        assert result["success"] is True

    def test_validation_runs_before_the_guard(self, mock_secrets):
        """A caller with a bad value should hear about the value, not the flag.

        Otherwise adding the acknowledgement would mask every input error behind
        it, and the operator would set the flag to find out what was wrong.
        """
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()

            result = handler(
                {"action": "updateSnaplockRetention", "volumeUuid": "uuid-1", "days": 0},
                None,
            )

        assert result["success"] is False
        assert "days must be > 0" in result["error"]
        assert "acknowledgeIrreversible" not in result["error"]

    def test_s3_object_lock_compliance_names_its_own_effect(self, mock_secrets):
        """COMPLIANCE and GOVERNANCE differ in what the operator is agreeing to."""
        from handler import handler

        with patch("handler.boto3") as mock_boto3:
            mock_sm = MagicMock()
            mock_sm.get_secret_value.return_value = {
                "SecretString": json.dumps({"username": "fsxadmin", "password": "test"})
            }
            mock_boto3.client.return_value = mock_sm

            compliance = handler(
                {
                    "action": "putS3ObjectLockRetention",
                    "bucket": "example-bucket",
                    "mode": "COMPLIANCE",
                    "days": 14,
                },
                None,
            )
            governance = handler(
                {
                    "action": "putS3ObjectLockRetention",
                    "bucket": "example-bucket",
                    "mode": "GOVERNANCE",
                    "days": 14,
                },
                None,
            )

        assert compliance["success"] is False
        assert "cannot be shortened or removed" in compliance["error"]
        assert governance["success"] is False
        assert "BypassGovernanceRetention" in governance["error"]

    def test_snapshot_policy_with_retention_refused_without_ack(self, mock_secrets):
        """A retention period on a policy locks every snapshot it ever takes.

        This is the recurring form of a snapshot lock, and the one nothing asked
        about: the form field was free text, so a mistyped period would have kept
        producing locks on a schedule with nobody watching.
        """
        from handler import handler

        mock_http = MockHttp({"/storage/snapshot-policies": {"status": 201, "data": {}}})
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = mock_http

            result = handler(
                {
                    "action": "createSnapshotPolicy",
                    "name": "nightly_worm",
                    "schedules": [{"schedule": "daily", "count": 7, "retentionPeriod": "P30D"}],
                },
                None,
            )

        assert result["success"] is False
        assert "acknowledgeIrreversible" in result["error"]
        # The refusal has to name the period and the recurrence, not just the flag.
        assert "P30D" in result["error"]
        assert "every run of the schedule" in result["error"]
        assert not any(method == "POST" for method, _url, _kwargs in mock_http.calls)

    def test_snapshot_policy_with_retention_created_with_ack(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp({"/storage/snapshot-policies": {"status": 201, "data": {}}})

            result = handler(
                {
                    "action": "createSnapshotPolicy",
                    "name": "nightly_worm",
                    "schedules": [{"schedule": "daily", "count": 7, "retentionPeriod": "P30D"}],
                    "acknowledgeIrreversible": True,
                },
                None,
            )

        assert result["success"] is True

    def test_snapshot_policy_without_retention_needs_no_ack(self, mock_secrets):
        """Policies that only rotate snapshots are reversible and stay unguarded."""
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp({"/storage/snapshot-policies": {"status": 201, "data": {}}})

            result = handler(
                {
                    "action": "createSnapshotPolicy",
                    "name": "plain_daily",
                    "schedules": [{"schedule": "daily", "count": 7}],
                },
                None,
            )

        assert result["success"] is True

    def test_snapshot_policy_guard_runs_after_validation(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()

            result = handler(
                {
                    "action": "createSnapshotPolicy",
                    "name": "",
                    "schedules": [{"schedule": "daily", "retentionPeriod": "P30D"}],
                },
                None,
            )

        assert result["success"] is False
        assert "Policy name is required" in result["error"]
        assert "acknowledgeIrreversible" not in result["error"]

    def test_delete_snapshot_policy_requires_confirm(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()

            result = handler(
                {"action": "deleteSnapshotPolicy", "policyUuid": "uuid-1"},
                None,
            )

        assert result["success"] is False
        assert "confirm" in result["error"]

    def test_delete_snapshot_policy_reports_a_failed_job(self, mock_secrets):
        """ONTAP refuses the delete while a volume still references the policy."""
        from handler import handler

        http = MockHttp(
            {
                "/storage/snapshot-policies/uuid-1": {"data": {"job": {"uuid": "job-1"}}},
                "/cluster/jobs/job-1": {"data": {"state": "failure", "message": "policy is in use by a volume"}},
            }
        )
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http

            result = handler(
                {"action": "deleteSnapshotPolicy", "policyUuid": "uuid-1", "confirm": True},
                None,
            )

        assert result["success"] is False
        assert "in use" in result["error"]
        assert http.find("DELETE", "/storage/snapshot-policies/uuid-1")

    def test_assigning_a_locking_policy_refused_without_ack(self, mock_secrets):
        """Attaching a policy that locks starts the same recurrence on that volume."""
        from handler import handler

        mock_http = MockHttp(
            {
                "/storage/snapshot-policies": {
                    "status": 200,
                    "data": {
                        "records": [{"copies": [{"retention_period": "P6M"}]}],
                        "num_records": 1,
                    },
                },
            }
        )
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = mock_http

            result = handler(
                {
                    "action": "assignSnapshotPolicy",
                    "volumeUuid": "uuid-1",
                    "policyName": "nightly_worm",
                },
                None,
            )

        assert result["success"] is False
        assert "acknowledgeIrreversible" in result["error"]
        assert "P6M" in result["error"]
        assert not any(method == "PATCH" for method, _url, _kwargs in mock_http.calls)

    def test_assigning_a_plain_policy_needs_no_ack(self, mock_secrets):
        """Whether to ask depends on the policy, so a harmless one is not blocked."""
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp(
                {
                    "/storage/snapshot-policies": {
                        "status": 200,
                        "data": {"records": [{"copies": [{"count": 7}]}], "num_records": 1},
                    },
                    "/storage/volumes": {"status": 200, "data": {}},
                }
            )

            result = handler(
                {
                    "action": "assignSnapshotPolicy",
                    "volumeUuid": "uuid-1",
                    "policyName": "plain_daily",
                },
                None,
            )

        assert result["success"] is True

    def test_unreadable_policy_still_asks(self, mock_secrets):
        """Fails closed: an unknown policy must not be assumed to be harmless."""
        from handler import handler

        mock_http = MockHttp({"/storage/snapshot-policies": {"status": 500, "data": {"error": {"message": "boom"}}}})
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = mock_http

            result = handler(
                {
                    "action": "assignSnapshotPolicy",
                    "volumeUuid": "uuid-1",
                    "policyName": "nightly_worm",
                },
                None,
            )

        assert result["success"] is False
        assert "acknowledgeIrreversible" in result["error"]
        assert not any(method == "PATCH" for method, _url, _kwargs in mock_http.calls)


class TestFailureClassification:
    """Which of the five ways it failed, not just that it failed.

    The portal reported "Volume 'vol1' not found on SVM 'fsxsvm01'" for a volume the AWS
    control plane listed as CREATED, and offered advice about subnets and security
    groups. ONTAP had actually answered 401 with "User is not authorized." Naming the
    wrong layer costs more than saying nothing, because the reader believes it.
    """

    def test_rejected_credentials_are_reported_as_such(self, mock_secrets):
        """A 401 is the secret's contents, not the network."""
        from handler import handler

        mock_http = MockHttp(
            {"/storage/volumes": {"status": 401, "data": {"error": {"message": "User is not authorized."}}}}
        )
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = mock_http
            result = handler({"action": "listVolumes"}, None)

        assert result["errorClass"] == "CREDENTIALS_REJECTED"
        assert result["errorStatus"] == 401
        # The message the panel has always shown is left alone; the class is the new part.
        assert result["error"] == "User is not authorized."

    def test_a_403_lands_in_the_same_class_as_a_401(self, mock_secrets):
        """Which one arrived is worth recording, but both send the reader to the secret."""
        from handler import handler

        mock_http = MockHttp({"/storage/volumes": {"status": 403, "data": {"error": {"message": "not authorized"}}}})
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = mock_http
            result = handler({"action": "listVolumes"}, None)

        assert result["errorClass"] == "CREDENTIALS_REJECTED"
        assert result["errorStatus"] == 403

    def test_other_ontap_errors_carry_the_status_and_code(self, mock_secrets):
        """The code is the first thing a support case asks for."""
        from handler import handler

        mock_http = MockHttp(
            {
                "/storage/volumes": {
                    "status": 500,
                    "data": {"error": {"message": "internal error", "code": "6684732"}},
                }
            }
        )
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = mock_http
            result = handler({"action": "listVolumes"}, None)

        assert result["errorClass"] == "ONTAP_ERROR"
        assert result["errorStatus"] == 500
        assert result["errorCode"] == "6684732"

    def test_a_later_validation_failure_is_not_labelled_an_ontap_failure(self, mock_secrets):
        """The recorded class only attaches to the error it was recorded for.

        This action reads a policy, tolerates the read failing, and then refuses for a
        different reason. Attaching the read's class here would tell the reader to go and
        check a password over a missing acknowledgement.
        """
        from handler import handler

        mock_http = MockHttp(
            {"/storage/snapshot-policies": {"status": 401, "data": {"error": {"message": "User is not authorized."}}}}
        )
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = mock_http
            result = handler(
                {
                    "action": "assignSnapshotPolicy",
                    "volumeUuid": "uuid-1",
                    "policyName": "nightly_worm",
                },
                None,
            )

        assert result["success"] is False
        assert "acknowledgeIrreversible" in result["error"]
        assert "errorClass" not in result

    def test_the_class_does_not_survive_into_the_next_invocation(self, mock_secrets):
        """The slot is per-request. A warm container must not report a stale cause."""
        from handler import handler

        failing = MockHttp(
            {"/storage/volumes": {"status": 401, "data": {"error": {"message": "User is not authorized."}}}}
        )
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = failing
            assert handler({"action": "listVolumes"}, None)["errorClass"] == "CREDENTIALS_REJECTED"

        # Same container, an action that fails for a reason ONTAP never saw.
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()
            result = handler({"action": "nonsense"}, None)

        assert "Unknown action" in result["error"]
        assert "errorClass" not in result

    def test_an_unconfigured_deployment_names_what_is_missing(self, mock_secrets):
        """ "ONTAP connection not configured" did not say which variable was blank."""
        import handler as handler_module

        with patch.object(handler_module, "MGMT_IP", ""):
            result = handler_module.handler({"action": "listVolumes"}, None)

        assert result["errorClass"] == "NOT_CONFIGURED"
        assert "ONTAP_MGMT_IP" in result["error"]

    def test_nothing_answering_is_not_reported_as_a_missing_volume(self, mock_secrets):
        """The only class where inspecting the VPC is the right next step."""
        import handler as handler_module
        import urllib3

        class RefusingHttp:
            def request(self, *_args, **_kwargs):
                raise urllib3.exceptions.NewConnectionError(None, "connection refused")

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = RefusingHttp()
            result = handler_module.handler({"action": "listVolumes"}, None)

        assert result["errorClass"] == "UNREACHABLE"
        assert "management LIF" in result["error"]


class TestInPlaceUpdates:
    """The four actions that existed only as delete-and-recreate.

    Each of those round trips loses something: a quota rule's usage accounting, a
    qtree's contents, a local user's SID (which is what NTFS ACLs name), and, for a
    name mapping, the rule itself for the window between the two calls.
    """

    def test_quota_rule_update_patches_limits_only(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/storage/quota/rules/r1": {"data": {}}})
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler(
                {
                    "action": "updateQuotaRule",
                    "ruleUuid": "r1",
                    "spaceHardLimitGiB": 200,
                    "filesHardLimit": 5000,
                },
                None,
            )

        assert result["success"] is True
        body = json.loads(http.find("PATCH", "/storage/quota/rules/r1")[2]["body"])
        assert body["space"]["hard_limit"] == 200 * 1024**3
        assert body["files"]["hard_limit"] == 5000
        # The target is not in the body: it cannot be changed after creation.
        assert "volume" not in body and "qtree" not in body

    def test_quota_rule_update_maps_zero_to_no_limit(self, mock_secrets):
        """0 in the form means "no limit", which ONTAP spells -1."""
        from handler import handler

        http = MockHttp({"/storage/quota/rules/r1": {"data": {}}})
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            handler({"action": "updateQuotaRule", "ruleUuid": "r1", "spaceHardLimitGiB": 0}, None)

        body = json.loads(http.find("PATCH", "/storage/quota/rules/r1")[2]["body"])
        assert body["space"]["hard_limit"] == -1

    def test_quota_rule_update_refuses_an_empty_change(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()
            result = handler({"action": "updateQuotaRule", "ruleUuid": "r1"}, None)

        assert result["success"] is False
        assert "at least one of" in result["error"]

    def test_qtree_update_resolves_the_volume_uuid(self, mock_secrets):
        from handler import handler

        http = MockHttp(
            {
                "/storage/volumes?name=": {"data": {"records": [{"uuid": "v1"}]}},
                "/storage/qtrees/v1/3": {"data": {}},
            }
        )
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler(
                {
                    "action": "updateQtree",
                    "volumeName": "vol1",
                    "qtreeId": "3",
                    "securityStyle": "ntfs",
                },
                None,
            )

        assert result["success"] is True
        body = json.loads(http.find("PATCH", "/storage/qtrees/v1/3")[2]["body"])
        assert body == {"security_style": "ntfs"}

    def test_qtree_update_rejects_an_unknown_security_style(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()
            result = handler(
                {
                    "action": "updateQtree",
                    "volumeName": "vol1",
                    "qtreeId": "3",
                    "securityStyle": "posix",
                },
                None,
            )

        assert result["success"] is False
        assert "securityStyle" in result["error"]

    def test_local_user_update_sends_the_password_without_logging_it(self, mock_secrets, caplog):
        from handler import handler

        http = MockHttp(
            {
                "/svm/svms": {"data": {"records": [{"uuid": "svm-1"}]}},
                "/protocols/cifs/local-users/svm-1/S-1-5-21-1": {"data": {}},
            }
        )
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            with caplog.at_level("INFO"):
                result = handler(
                    {
                        "action": "updateLocalUser",
                        "sid": "S-1-5-21-1",
                        "password": "s3cret-passphrase",
                        "enabled": False,
                    },
                    None,
                )

        assert result["success"] is True
        body = json.loads(http.find("PATCH", "/protocols/cifs/local-users/svm-1/S-1-5-21-1")[2]["body"])
        # ONTAP's field is `account_disabled`; sending `enabled` is refused with 262179.
        assert body == {"password": "s3cret-passphrase", "account_disabled": True}
        assert "s3cret-passphrase" not in caplog.text

    def test_local_user_update_refuses_an_empty_change(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()
            result = handler({"action": "updateLocalUser", "sid": "S-1-5-21-1"}, None)

        assert result["success"] is False
        assert "at least one of" in result["error"]

    def test_name_mapping_update_patches_the_indexed_rule(self, mock_secrets):
        from handler import handler

        http = MockHttp(
            {
                "/svm/svms": {"data": {"records": [{"uuid": "svm-1"}]}},
                "/name-services/name-mappings/svm-1/win_unix/2": {"data": {}},
            }
        )
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler(
                {
                    "action": "updateNameMapping",
                    "direction": "win_unix",
                    "index": 2,
                    "pattern": "EXAMPLE\\\\(.+)",
                },
                None,
            )

        assert result["success"] is True
        body = json.loads(http.find("PATCH", "/name-services/name-mappings/svm-1/win_unix/2")[2]["body"])
        assert body == {"pattern": "EXAMPLE\\\\(.+)"}

    def test_name_mapping_update_refuses_s3_unix(self, mock_secrets):
        """FSx for ONTAP owns those entries; it creates and removes them itself."""
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()
            result = handler(
                {
                    "action": "updateNameMapping",
                    "direction": "s3_unix",
                    "index": 1,
                    "pattern": "x",
                },
                None,
            )

        assert result["success"] is False
        assert "s3_unix" in result["error"]


class TestMovesAndEnforcement:
    """Operations that move a thing, and the one that switches enforcement on.

    Separate from TestInPlaceUpdates because these are not edits. A rename moves the
    path clients hold, a name-mapping move changes which rule matches first, and quota
    enforcement decides whether any of the rules listed next to it apply at all.
    """

    def test_qtree_rename_requires_confirmation(self, mock_secrets):
        """Without it, the rename is one click from the settings edit beside it."""
        from handler import handler

        http = MockHttp({"/storage/volumes?name=": {"data": {"records": [{"uuid": "v1"}]}}})
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler(
                {
                    "action": "renameQtree",
                    "volumeName": "vol1",
                    "qtreeId": "2",
                    "newName": "archive",
                },
                None,
            )
        assert result["success"] is False
        assert "confirm=true" in result["error"]
        # Nothing was sent: the refusal is before the volume lookup.
        assert http.calls == []

    def test_qtree_rename_patches_the_name(self, mock_secrets):
        from handler import handler

        http = MockHttp(
            {
                "/storage/volumes?name=": {"data": {"records": [{"uuid": "v1"}]}},
                "/storage/qtrees/v1/2": {"data": {}},
            }
        )
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler(
                {
                    "action": "renameQtree",
                    "volumeName": "vol1",
                    "qtreeId": "2",
                    "newName": "archive",
                    "confirm": True,
                },
                None,
            )
        assert result["success"] is True
        body = json.loads(http.find("PATCH", "/storage/qtrees/v1/2")[2]["body"])
        # The name only. The id stays as it was, which is why a rename does not
        # invalidate the identifier the panel holds.
        assert body == {"name": "archive"}

    def test_qtree_rename_rejects_a_path_separator_in_the_name(self, mock_secrets):
        """A qtree name is a path component, so a separator would move it elsewhere."""
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()
            result = handler(
                {
                    "action": "renameQtree",
                    "volumeName": "vol1",
                    "qtreeId": "2",
                    "newName": "../escaped",
                    "confirm": True,
                },
                None,
            )
        assert result["success"] is False
        assert "newName" in result["error"]

    def test_name_mapping_move_sends_new_index(self, mock_secrets):
        from handler import handler

        http = MockHttp(
            {
                "/svm/svms": {"data": {"records": [{"uuid": "svm-1"}]}},
                "/name-services/name-mappings/svm-1/win_unix/2": {"data": {}},
            }
        )
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler(
                {"action": "moveNameMapping", "direction": "win_unix", "index": 2, "newIndex": 1},
                None,
            )
        assert result["success"] is True
        call = http.find("PATCH", "/name-services/name-mappings/svm-1/win_unix/2")
        # `new_index`, not `index`: the second would be read as a filter, not a move.
        assert json.loads(call[2]["body"]) == {"new_index": 1}

    def test_name_mapping_move_refuses_the_position_it_holds(self, mock_secrets):
        """ONTAP rejects it too, but the reason it gives does not say which field."""
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()
            result = handler(
                {"action": "moveNameMapping", "direction": "win_unix", "index": 2, "newIndex": 2},
                None,
            )
        assert result["success"] is False
        assert "already holds" in result["error"]

    def test_name_mapping_move_refuses_s3_unix(self, mock_secrets):
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()
            result = handler(
                {"action": "moveNameMapping", "direction": "s3_unix", "index": 1, "newIndex": 2},
                None,
            )
        assert result["success"] is False
        assert "s3_unix" in result["error"]

    def test_volume_quota_enabled_writes_enabled_and_reports_state(self, mock_secrets):
        """The write field and the read field are not the same one.

        `quota.enabled` is the request; `quota.state` is what the volume is doing. On
        9.18.1P3D1 a volume enforcing quotas reports `state: "on"` with `enabled` still
        false, so echoing the request back would tell the caller the opposite of the
        truth for as long as ONTAP is still scanning.
        """
        from handler import handler

        http = MockHttp({"/storage/volumes/v1": {"data": {"quota": {"state": "initializing"}}}})
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler(
                {"action": "setVolumeQuotaEnabled", "volumeUuid": "v1", "enabled": True},
                None,
            )
        assert result["success"] is True
        assert result["quotaState"] == "initializing"
        assert "enabled" not in result
        assert json.loads(http.find("PATCH", "/storage/volumes/v1")[2]["body"]) == {"quota": {"enabled": True}}

    def test_volume_quota_enabled_requires_the_flag(self, mock_secrets):
        """Absent is not false: it would silently turn enforcement off."""
        from handler import handler

        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = MockHttp()
            result = handler({"action": "setVolumeQuotaEnabled", "volumeUuid": "v1"}, None)
        assert result["success"] is False
        assert "enabled is required" in result["error"]

    def test_volume_quota_disable_sends_false(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/storage/volumes/v1": {"data": {"quota": {"state": "off"}}}})
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler(
                {"action": "setVolumeQuotaEnabled", "volumeUuid": "v1", "enabled": False},
                None,
            )
        assert result["success"] is True
        assert result["quotaState"] == "off"
        assert json.loads(http.find("PATCH", "/storage/volumes/v1")[2]["body"]) == {"quota": {"enabled": False}}

    def test_resize_reports_a_job_failure_rather_than_the_size_asked_for(self, mock_secrets):
        """A FlexCache below its FlexGroup floor fails inside the job, not on the PATCH.

        This is the path the FlexCache panel's resize takes -- a cache is a volume and
        shares its UUID -- so a 202 reported as success would leave the panel showing a
        size the cache never reached.
        """
        from handler import handler

        http = MockHttp(
            {
                "/storage/volumes/c1": {"data": {"job": {"uuid": "j1"}}},
                "/cluster/jobs/j1": {
                    "data": {
                        "state": "failure",
                        "message": "Volumes of this type must be at least 50GB",
                    }
                },
            }
        )
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler({"action": "resizeVolume", "volumeUuid": "c1", "newSizeGiB": 20}, None)
        assert result["success"] is False
        assert result["jobId"] == "j1"
        # The hint explains why the floor is far above a single volume's 1 GiB.
        assert "FlexGroup" in result["error"]

    def test_resize_reports_a_long_running_job_as_accepted(self, mock_secrets, monkeypatch):
        """Shrinking a FlexGroup outlives the request, and that is not a failure.

        Measured on 9.18.1P3D1: a FlexCache shrink was still running when the wait ran
        out and then completed. Reporting it as failed was as wrong as the 202-as-success
        it replaced, in the other direction -- the size had changed and the panel said it
        had not.
        """
        from handler import handler

        # Collapse the wait rather than sleeping through it.
        monkeypatch.setattr("handler._JOB_WAIT_SECONDS", 0.2)
        monkeypatch.setattr("handler._JOB_POLL_INTERVAL", 0.05)
        http = MockHttp(
            {
                "/storage/volumes/c1": {"data": {"job": {"uuid": "j1"}}},
                "/cluster/jobs/j1": {"data": {"state": "running", "message": "shrinking"}},
            }
        )
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler({"action": "resizeVolume", "volumeUuid": "c1", "newSizeGiB": 20}, None)
        assert result["success"] is True
        # `pending` is how the panel knows the size it lists is still the old one.
        assert result["pending"] is True
        assert result["jobId"] == "j1"


class TestQosAssignment:
    """Assigning a QoS policy, and the removal that makes the delete usable.

    ONTAP refuses to delete a policy group while a storage object is assigned to it, so
    a panel that can assign but not unassign can create a policy it cannot delete.
    """

    def test_assign_sends_the_policy_name(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/storage/volumes/v1": {"data": {}}})
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler(
                {"action": "assignQosToVolume", "volumeUuid": "v1", "policyName": "zz_qos"},
                None,
            )
        assert result["success"] is True
        assert result["cleared"] is False
        assert json.loads(http.find("PATCH", "/storage/volumes/v1")[2]["body"]) == {
            "qos": {"policy": {"name": "zz_qos"}}
        }

    def test_none_removes_the_assignment(self, mock_secrets):
        """`none` is ONTAP's reserved keyword, not a portal placeholder."""
        from handler import handler

        http = MockHttp({"/storage/volumes/v1": {"data": {}}})
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler(
                {"action": "assignQosToVolume", "volumeUuid": "v1", "policyName": "none"},
                None,
            )
        assert result["success"] is True
        # The caller needs to distinguish "assigned" from "removed" to report it.
        assert result["cleared"] is True
        assert json.loads(http.find("PATCH", "/storage/volumes/v1")[2]["body"]) == {"qos": {"policy": {"name": "none"}}}

    def test_an_empty_policy_name_is_refused_and_names_the_keyword(self, mock_secrets):
        """Sending "" would reach ONTAP as a validation error that does not name the field."""
        from handler import handler

        http = MockHttp()
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler({"action": "assignQosToVolume", "volumeUuid": "v1"}, None)
        assert result["success"] is False
        assert "none" in result["error"]
        assert http.calls == []

    def test_assign_waits_for_the_job(self, mock_secrets, monkeypatch):
        """The PATCH can answer 202, and the assignment is not in effect until it ends."""
        from handler import handler

        monkeypatch.setattr("handler._JOB_WAIT_SECONDS", 0.2)
        monkeypatch.setattr("handler._JOB_POLL_INTERVAL", 0.05)
        http = MockHttp(
            {
                "/storage/volumes/v1": {"data": {"job": {"uuid": "j1"}}},
                "/cluster/jobs/j1": {"data": {"state": "failure", "message": "policy not found"}},
            }
        )
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler(
                {"action": "assignQosToVolume", "volumeUuid": "v1", "policyName": "zz_qos"},
                None,
            )
        assert result["success"] is False
        assert result["error"] == "policy not found"

    def test_volume_listing_reports_the_assigned_policy(self, mock_secrets):
        """Without this the panel offers a delete for a policy it cannot see is in use."""
        from handler import handler

        http = MockHttp(
            {
                "/storage/volumes?svm.name=": {
                    "data": {
                        "records": [
                            {
                                "name": "vol1",
                                "uuid": "v1",
                                "size": 1024,
                                "state": "online",
                                "qos": {"policy": {"name": "zz_qos"}},
                            },
                            {"name": "vol2", "uuid": "v2", "size": 1024, "state": "online"},
                        ]
                    }
                }
            }
        )
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler({"action": "listVolumes"}, None)
        by_name = {v["name"]: v for v in result["volumes"]}
        assert by_name["vol1"]["qosPolicyName"] == "zz_qos"
        # Absent means none, not unknown.
        assert by_name["vol2"]["qosPolicyName"] == ""
        assert "qos.policy.name" in http.find("GET", "/storage/volumes?svm.name=")[1]


class TestArpStateReadBack:
    """The ARP state a caller is told about is the one ONTAP settled on.

    Measured on 9.18.1P3D1: a request for `dry_run` leaves the volume `enabled`, because
    ARP/AI carries a pre-trained model and has no learning period to enter. ONTAP does not
    report that it declined the state. Echoing the request would tell an operator the
    volume was learning while it was actively protecting.
    """

    def test_the_state_is_read_back_not_echoed(self, mock_secrets):
        from handler import handler

        http = MockHttp(
            {
                # The FlexCache pre-flight, the PATCH and the read-back all address the
                # same path, so one entry answers each in turn.
                "/storage/volumes/v1": {"data": {"anti_ransomware": {"state": "enabled"}}},
            }
        )
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler(
                {"action": "updateArpStateAdmin", "volumeUuid": "v1", "state": "dry_run"},
                None,
            )
        assert result["success"] is True
        assert result["state"] == "enabled"
        assert result["requested"] == "dry_run"
        # The caller needs to know the two disagree in order to say so.
        assert result["differs"] is True
        assert "newState" not in result

    def test_an_in_progress_state_is_not_reported_as_a_disagreement(self, mock_secrets):
        """Turning it off passes through `disable_in_progress` for minutes.

        That is the requested transition under way, not ONTAP settling somewhere else, so
        it must not be flagged as a divergence -- an operator would read that as a refusal.
        """
        from handler import handler

        http = MockHttp({"/storage/volumes/v1": {"data": {"anti_ransomware": {"state": "disable_in_progress"}}}})
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler(
                {"action": "updateArpStateAdmin", "volumeUuid": "v1", "state": "disabled"},
                None,
            )
        assert result["state"] == "disable_in_progress"
        assert result["differs"] is False

    def test_a_matching_state_is_not_flagged(self, mock_secrets):
        from handler import handler

        http = MockHttp({"/storage/volumes/v1": {"data": {"anti_ransomware": {"state": "enabled"}}}})
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler(
                {"action": "updateArpStateAdmin", "volumeUuid": "v1", "state": "enabled"},
                None,
            )
        assert result["state"] == "enabled"
        assert result["settling"] is False
        assert result["differs"] is False

    def test_a_failed_read_back_does_not_turn_a_success_into_a_divergence(self, mock_secrets):
        """An unreadable state is unknown, and unknown is not disagreement."""
        from handler import handler

        http = MockHttp(
            {
                "/storage/volumes/v1?fields=anti_ransomware.state": {
                    "status": 500,
                    "data": {"error": {"message": "internal"}},
                },
                "/storage/volumes/v1": {"data": {}},
            }
        )
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler(
                {"action": "updateArpStateAdmin", "volumeUuid": "v1", "state": "enabled"},
                None,
            )
        assert result["success"] is True
        assert result["state"] == ""
        assert result["differs"] is False


class TestVolumeListingScale:
    """Whether the volume listing admits that it is only the first page.

    The listing asks ONTAP for 50 and stops. On a file system with hundreds of volumes a
    dropdown of the first fifty looks exactly like a complete list, and an operator whose
    volume is not among them concludes it does not exist. ONTAP says there is more through
    `_links.next`; the answer is to pass that on, not to raise the ceiling.
    """

    def test_a_further_page_is_reported(self, mock_secrets):
        from handler import handler

        http = MockHttp(
            {
                "/storage/volumes?svm.name=": {
                    "data": {
                        "records": [{"name": "v", "uuid": "u", "size": 1024, "state": "online"}],
                        "_links": {"next": {"href": "/api/storage/volumes?start.uuid=u"}},
                    }
                }
            }
        )
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler({"action": "listVolumes"}, None)
        assert result["truncated"] is True

    def test_a_complete_listing_is_not_reported_as_truncated(self, mock_secrets):
        """Otherwise every list would carry a warning and the warning would mean nothing."""
        from handler import handler

        http = MockHttp(
            {
                "/storage/volumes?svm.name=": {
                    "data": {
                        "records": [{"name": "v", "uuid": "u", "size": 1024, "state": "online"}],
                        "_links": {"self": {"href": "/api/storage/volumes"}},
                    }
                }
            }
        )
        with patch("handler.urllib3.PoolManager") as mock_pool:
            mock_pool.return_value = http
            result = handler({"action": "listVolumes"}, None)
        assert result["truncated"] is False
