"""Tests for the ONTAP catalog snapshot Lambda (operations/ontap-catalog-snapshot, OPS7).

The handler is loaded by path under a unique module name: ``handler`` is a name several Lambda
functions in this repository share, and a plain import would collide.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
import pytest
from moto import mock_aws

HANDLER_PATH = Path(__file__).parent.parent / "functions" / "snapshot" / "handler.py"
spec = importlib.util.spec_from_file_location("ops7_catalog_snapshot_handler", HANDLER_PATH)
snap = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = snap  # dataclasses looks the module up here
spec.loader.exec_module(snap)  # type: ignore[union-attr]

snap.PROBE_PAUSE_S = 0
BASE = "/api/private/cli/security/login/role"
NOW = datetime(2026, 11, 4, 9, 0, 0, tzinfo=timezone.utc)
PASSWORD = "Pa55w0rd-do-not-log"
LONG = lambda: 10_000_000  # noqa: E731


def ok(body: Any) -> snap.Reply:
    return snap.Reply(200, body, "", "")


def err(status: int, code: str, message: str) -> snap.Reply:
    return snap.Reply(status, None, code, message)


class FakeOntap:
    """Answers by path prefix and records every request it receives."""

    def __init__(self, rest: list[dict[str, Any]] | None = None, version: str = "NetApp Release 9.18.1P6: Fri Aug 07") -> None:
        self.requests: list[str] = []
        self.version = version
        self.rest = rest if rest is not None else [
            {"endpoint": "/cluster/nodes", "supported_operations": ["GET"], "commands": ["system node show"]},
            {"endpoint": "/security/multi-admin-verify", "supported_operations": ["GET", "PATCH"], "commands": ["security multi-admin-verify"]},
            {"endpoint": "/storage/volumes/{uuid}", "supported_operations": ["GET", "PATCH", "DELETE"], "commands": ["volume show"]},
            {"endpoint": "/storage/volumes", "supported_operations": ["POST"], "commands": ["volume create"]},
        ]
        self.capability = [
            {"object_name": "volume.clone", "operation_name": "create"},
            {"object_name": "volume", "operation_name": "show"},
        ]
        self.overrides: dict[str, snap.Reply] = {}

    def get(self, path: str) -> snap.Reply:
        self.requests.append(path)
        for prefix, reply in self.overrides.items():
            if path.startswith(prefix):
                return reply
        if path.startswith("/api/cluster"):
            return ok({"name": "FsxId0123456789abcdef0", "version": {"full": self.version}})
        if path.startswith(BASE + "/show-user-capability"):
            return ok({"records": self.capability})
        if path.startswith(BASE + "/show-rest"):
            return ok({"records": self.rest})
        if path.startswith(BASE + "/show-ontapi"):
            return ok({"records": [{"ontapi": "aggr-create", "command": "storage aggregate create"}]})
        if path.startswith(BASE):
            return ok({"records": [{"vserver": "FsxId0123456789abcdef0", "role": "fsxadmin", "cmddirname": "DEFAULT", "access": "all", "query": ""}]})
        if path == "/api/security/multi-admin-verify?max_records=1":
            return err(403, "6", "not authorized for that command")
        return ok({"records": []})


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_object(self, Bucket: str, Key: str, Body: bytes, ContentType: str) -> None:  # noqa: N803
        self.objects[Key] = Body

    def get_object(self, Bucket: str, Key: str) -> dict[str, Any]:  # noqa: N803
        if Key not in self.objects:
            raise KeyError(Key)

        class _B:
            def __init__(self, b: bytes) -> None:
                self._b = b

            def read(self) -> bytes:
                return self._b

        return {"Body": _B(self.objects[Key])}


def cfg(**kw: Any) -> snap.Config:
    base = dict(management_endpoint="management.fs-0123456789abcdef0.fsx.ap-northeast-1.amazonaws.com", secret_arn="arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:x-XXXXXX", bucket="b", file_system_id="fs-0123456789abcdef0")
    base.update(kw)
    return snap.Config(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- versions and masking


def test_parse_version_keeps_the_patch_level() -> None:
    assert snap.parse_version("NetApp Release 9.18.1P6: Fri Aug 07 23:43:59 UTC 2026") == "9.18.1P6"
    assert snap.parse_version("NetApp Release 9.17.1P7D1: Mon") == "9.17.1P7D1"
    assert snap.parse_version("garbage") == "unknown"


def test_mask_removes_cluster_names() -> None:
    assert "FsxId0123456789abcdef0" not in snap.mask('Cluster "FsxId0123456789abcdef0-01" is not configured')


# --------------------------------------------------------------------------- lockout protection


def test_a_refused_credential_stops_the_run_after_one_request() -> None:
    ontap = FakeOntap()
    ontap.overrides["/api/cluster"] = err(401, "6691623", "User is not authorized.")
    with pytest.raises(snap.AuthenticationAbort):
        snap.collect(cfg(), ontap, LONG)
    assert ontap.requests == ["/api/cluster?fields=name,version"], "nothing may follow a refused credential"


def test_a_credential_refused_midway_stops_the_probe() -> None:
    ontap = FakeOntap()
    ontap.overrides["/api/cluster/nodes"] = err(401, "6691623", "User is not authorized.")
    with pytest.raises(snap.AuthenticationAbort):
        snap.collect(cfg(), ontap, LONG)
    probes = [r for r in ontap.requests if r.endswith("max_records=1")]
    assert probes == ["/api/cluster/nodes?max_records=1"], "the probe must stop at the first refusal"


def test_a_401_without_an_ontap_code_is_treated_as_a_refused_credential() -> None:
    ontap = FakeOntap()
    ontap.overrides["/api/cluster"] = snap.Reply(401, None, "", "")
    with pytest.raises(snap.AuthenticationAbort):
        snap.collect(cfg(), ontap, LONG)


def test_a_role_authorization_401_is_data_not_a_reason_to_stop() -> None:
    ontap = FakeOntap(rest=[
        {"endpoint": "/storage/snaplock/litigations", "supported_operations": ["GET"], "commands": []},
        {"endpoint": "/cluster/nodes", "supported_operations": ["GET"], "commands": []},
    ])
    ontap.overrides["/api/storage/snaplock/litigations"] = err(401, "13763280", 'Only a user with the security login role "vsadmin-snaplock" is allowed')
    result = snap.collect(cfg(), ontap, LONG)
    by = {e["endpoint"]: e for e in result.files["rest-endpoints"]}
    assert by["/storage/snaplock/litigations"]["get_http"] == 401
    assert by["/cluster/nodes"]["get_http"] == 200, "later endpoints must still be probed"


def test_a_403_is_recorded_and_the_run_continues() -> None:
    result = snap.collect(cfg(), FakeOntap(), LONG)
    by = {e["endpoint"]: e for e in result.files["rest-endpoints"]}
    assert by["/security/multi-admin-verify"]["get_http"] == 403
    assert by["/security/multi-admin-verify"]["get_code"] == "6"


def test_a_secret_tagged_for_another_file_system_is_refused_before_ontap_is_called() -> None:
    class Secrets:
        def describe_secret(self, SecretId: str) -> dict[str, Any]:  # noqa: N803
            return {"Tags": [{"Key": "FileSystemId", "Value": "fs-0aaaaaaaaaaaaaaaa"}]}

        def get_secret_value(self, SecretId: str) -> dict[str, Any]:  # noqa: N803
            raise AssertionError("the secret value must not be read for the wrong file system")

    with pytest.raises(snap.SecretProblem):
        snap.load_credentials(Secrets(), cfg())


# --------------------------------------------------------------------------- what is sent


def test_only_get_requests_with_pinned_fields_are_sent() -> None:
    ontap = FakeOntap()
    snap.collect(cfg(), ontap, LONG)
    assert (BASE + "?fields=vserver,role,cmddirname,access,query&max_records=20000") in ontap.requests
    assert (BASE + "/show-user-capability?fields=object_name,operation_name&max_records=20000") in ontap.requests
    assert (BASE + "/show-rest?fields=endpoint,commands,supported-operations&max_records=20000") in ontap.requests
    assert (BASE + "/show-ontapi?fields=ontapi,command&max_records=20000") in ontap.requests


def test_only_endpoints_that_allow_get_and_have_no_path_parameter_are_probed() -> None:
    ontap = FakeOntap()
    snap.collect(cfg(), ontap, LONG)
    probes = sorted(r for r in ontap.requests if r.endswith("max_records=1"))
    assert probes == ["/api/cluster/nodes?max_records=1", "/api/security/multi-admin-verify?max_records=1"]


def test_the_probe_can_be_switched_off() -> None:
    ontap = FakeOntap()
    result = snap.collect(cfg(probe_rest_get=False), ontap, LONG)
    assert not [r for r in ontap.requests if r.endswith("max_records=1")]
    assert result.manifest["counts"]["rest_get_probed"] == 0


def test_the_probe_stops_when_time_is_running_out() -> None:
    result = snap.collect(cfg(), FakeOntap(), lambda: 1_000)
    assert result.manifest["probe_truncated"] is True


def test_an_endpoint_with_an_unsafe_path_is_never_requested() -> None:
    ontap = FakeOntap(rest=[{"endpoint": "/cluster/../etc", "supported_operations": ["GET"], "commands": []}])
    snap.collect(cfg(), ontap, LONG)
    assert not [r for r in ontap.requests if "etc" in r]


def test_an_unsafe_next_link_is_not_followed() -> None:
    class Paged(FakeOntap):
        def get(self, path: str) -> snap.Reply:
            self.requests.append(path)
            return ok({"records": [{"a": 1}], "_links": {"next": {"href": "https://elsewhere.example/x"}}})

    ontap = Paged()
    records, status = snap.get_records(ontap, BASE, "a", "x")
    assert records == [{"a": 1}] and status == 200 and len(ontap.requests) == 1


def test_a_denied_collection_is_reported_as_unavailable() -> None:
    ontap = FakeOntap()
    ontap.overrides[BASE + "/show-ontapi"] = err(403, "6", "not authorized for that command")
    result = snap.collect(cfg(), ontap, LONG)
    assert result.manifest["unavailable"] == {"show-ontapi": 403}


def test_response_bodies_are_not_stored() -> None:
    result = snap.collect(cfg(), FakeOntap(), LONG)
    blob = json.dumps(result.files)
    assert '"records"' not in blob
    assert result.manifest["bodies_stored"] is False and result.manifest["get_only"] is True


# --------------------------------------------------------------------------- output and diff


def test_a_run_writes_the_expected_objects_and_a_pointer() -> None:
    s3 = FakeS3()
    result = snap.run(cfg(), FakeOntap(), s3, "fsxadmin", NOW, LONG)
    prefix = "ontap-catalog/fs-0123456789abcdef0/9.18.1P6/20261104T090000Z"
    assert result.manifest["output_prefix"] == prefix
    for name in ("manifest", "diff", "roles", "cli-user-capability", "rest-endpoints", "show-ontapi"):
        assert f"{prefix}/{name}.json" in s3.objects
    assert json.loads(s3.objects["ontap-catalog/fs-0123456789abcdef0/latest.json"])["prefix"] == prefix
    assert json.loads(s3.objects[f"{prefix}/manifest.json"])["ran_as"] == "fsxadmin"
    assert json.loads(s3.objects[f"{prefix}/cli-user-capability.json"]) == ["volume clone create", "volume show"]


def test_the_second_run_reports_what_changed() -> None:
    s3 = FakeS3()
    snap.run(cfg(), FakeOntap(), s3, "fsxadmin", NOW, LONG)
    newer = FakeOntap(version="NetApp Release 9.18.1P7: Fri Sep 04")
    newer.capability.append({"object_name": "security.multi-admin-verify", "operation_name": "show"})
    newer.overrides["/api/cluster/nodes"] = err(403, "6", "not authorized for that command")
    second = snap.run(cfg(), newer, s3, "fsxadmin", datetime(2026, 12, 1, tzinfo=timezone.utc), LONG)
    assert second.diff["previous_version"] == "9.18.1P6"
    assert second.diff["cli_commands_added"] == ["security multi-admin-verify show"]
    assert second.diff["rest_get_http_changed"] == ["/cluster/nodes"]
    assert second.diff["changed"] is True


def test_an_identical_second_run_reports_no_change() -> None:
    s3 = FakeS3()
    snap.run(cfg(), FakeOntap(), s3, "fsxadmin", NOW, LONG)
    second = snap.run(cfg(), FakeOntap(), s3, "fsxadmin", datetime(2026, 11, 11, tzinfo=timezone.utc), LONG)
    assert second.diff["changed"] is False


def test_the_first_run_has_nothing_to_compare() -> None:
    result = snap.run(cfg(), FakeOntap(), FakeS3(), "fsxadmin", NOW, LONG)
    assert result.diff["previous"] is None


class _ClientError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class _S3Failing(FakeS3):
    def __init__(self, code: str) -> None:
        super().__init__()
        self.code = code

    def get_object(self, Bucket: str, Key: str) -> dict[str, Any]:  # noqa: N803
        raise _ClientError(self.code)


def test_a_missing_pointer_is_a_quiet_first_run(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        assert snap.load_previous(_S3Failing("NoSuchKey"), "b", "p") is None
    assert "first snapshot" in caplog.text
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_a_permission_error_is_not_mistaken_for_a_first_run(caplog: pytest.LogCaptureFixture) -> None:
    """AccessDenied means every later run would silently have no diff, so it must be a warning."""
    with caplog.at_level(logging.INFO):
        assert snap.load_previous(_S3Failing("AccessDenied"), "b", "p") is None
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings and "AccessDenied" in warnings[0].getMessage()


# --------------------------------------------------------------------------- the handler end to end


@mock_aws
def test_handler_end_to_end_with_moto(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    region = "ap-northeast-1"
    sm = boto3.client("secretsmanager", region_name=region)
    arn = sm.create_secret(
        Name="ontap-admin",
        SecretString=json.dumps({"username": "fsxadmin", "password": PASSWORD}),
        Tags=[{"Key": "FileSystemId", "Value": "fs-0123456789abcdef0"}],
    )["ARN"]
    s3c = boto3.client("s3", region_name=region)
    s3c.create_bucket(Bucket="snap-bucket", CreateBucketConfiguration={"LocationConstraint": region})
    monkeypatch.setenv("AWS_DEFAULT_REGION", region)
    monkeypatch.setenv("ONTAP_MANAGEMENT_ENDPOINT", "management.fs-0123456789abcdef0.fsx.ap-northeast-1.amazonaws.com")
    monkeypatch.setenv("ONTAP_SECRET_ARN", arn)
    monkeypatch.setenv("OUTPUT_BUCKET", "snap-bucket")
    monkeypatch.setenv("FILE_SYSTEM_ID", "fs-0123456789abcdef0")
    seen: dict[str, str] = {}

    class Ctx:
        def get_remaining_time_in_millis(self) -> int:
            return 10_000_000

    def fake_transport(host: str, username: str, password: str, verify_ssl: bool) -> FakeOntap:
        seen.update(host=host, username=username)
        return FakeOntap()

    monkeypatch.setattr(snap, "OntapTransport", fake_transport)
    caplog.clear()  # the lines written while the test created the secret are not the handler's
    # Ask for the most verbose logging. The handler must keep the SDK at WARNING anyway:
    # botocore logs the GetSecretValue response, which holds the password, at DEBUG.
    with caplog.at_level(logging.DEBUG):
        out = snap.handler({}, Ctx())
    assert out["statusCode"] == 200 and out["ontap_version"] == "9.18.1P6"
    assert seen["username"] == "fsxadmin"
    keys = [o["Key"] for o in s3c.list_objects_v2(Bucket="snap-bucket")["Contents"]]
    assert any(k.endswith("/manifest.json") for k in keys)
    assert PASSWORD not in caplog.text, "the password must never reach the log"
    for k in keys:
        body = s3c.get_object(Bucket="snap-bucket", Key=k)["Body"].read().decode()
        assert PASSWORD not in body


@mock_aws
def test_handler_propagates_a_refused_credential_so_the_invocation_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    region = "ap-northeast-1"
    sm = boto3.client("secretsmanager", region_name=region)
    arn = sm.create_secret(Name="ontap-admin", SecretString=json.dumps({"username": "fsxadmin", "password": PASSWORD}))["ARN"]
    boto3.client("s3", region_name=region).create_bucket(Bucket="snap-bucket", CreateBucketConfiguration={"LocationConstraint": region})
    monkeypatch.setenv("AWS_DEFAULT_REGION", region)
    monkeypatch.setenv("ONTAP_MANAGEMENT_ENDPOINT", "management.example.invalid")
    monkeypatch.setenv("ONTAP_SECRET_ARN", arn)
    monkeypatch.setenv("OUTPUT_BUCKET", "snap-bucket")

    class Ctx:
        def get_remaining_time_in_millis(self) -> int:
            return 10_000_000

    refused = FakeOntap()
    refused.overrides["/api/cluster"] = err(401, "6691623", "User is not authorized.")
    monkeypatch.setattr(snap, "OntapTransport", lambda *a, **k: refused)
    with pytest.raises(snap.AuthenticationAbort):
        snap.handler({}, Ctx())
    assert refused.requests == ["/api/cluster?fields=name,version"]


def test_the_transport_rejects_a_host_that_is_not_a_plain_host_name() -> None:
    with pytest.raises(snap.SnapshotError):
        snap.OntapTransport("evil.example/..;x", "u", "p", False)
