"""Tests for the deployed-pattern smoke check.

The script exists because a green local suite says nothing about whether a deployed
access point is reachable: the upload round-trip passed against a mock that starts
empty, on a build whose IAM policy named the access point in the bucket form and
could not have reached it at all. So the parts asserted here are the ones that
decide whether a real failure is reported as one:

  - which key the access point is read from, and that the report says which,
  - that a write is only accepted as a write when the next reader can see it,
  - that the exit codes distinguish "could not tell" from "failed",
  - that a missing dependency is not diagnosed as a permission problem.

boto3 is not available in every environment this runs in, so the AWS surface is
faked at the seam rather than mocked with moto: `resolve_access_point` imports boto3
inside the function, and the steps take a helper object.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import smoke_deployed_pattern as smoke  # noqa: E402
from smoke_deployed_pattern import (  # noqa: E402
    ACCESS_POINT_KEYS,
    DEFAULT_WRITE_PREFIX,
    EXIT_FAILED,
    EXIT_OK,
    EXIT_USAGE,
    SmokeError,
    parse_args,
    resolve_access_point,
    step_list,
    step_read,
    step_write_and_read_back,
)


class FakeHelper:
    """The subset of shared/s3ap_helper.py the steps use.

    `visible_after_put` is the interesting knob: an access point that accepts a put
    and serves it back but does not list it is the shape the script has to refuse,
    and no mock that stores into one dict can produce it.
    """

    def __init__(
        self,
        objects: dict[str, bytes] | None = None,
        *,
        visible_after_put: bool = True,
        put_error: Exception | None = None,
        list_error: Exception | None = None,
    ) -> None:
        self.objects: dict[str, bytes] = dict(objects or {})
        self.hidden: set[str] = set()
        self.visible_after_put = visible_after_put
        self.put_error = put_error
        self.list_error = list_error
        self.deleted: list[str] = []

    def list_objects(self, prefix: str = "", max_keys: int = 50) -> list[dict[str, Any]]:
        if self.list_error:
            raise self.list_error
        return [
            {"Key": key, "Size": len(body)}
            for key, body in sorted(self.objects.items())
            if key.startswith(prefix) and key not in self.hidden
        ][:max_keys]

    def head_object(self, key: str) -> dict[str, Any]:
        return {"ContentLength": len(self.objects[key]), "ContentType": "text/plain"}

    def get_object_bytes(self, key: str) -> bytes:
        return self.objects[key]

    def put_object(self, key: str, body: bytes, content_type: str | None = None) -> None:
        if self.put_error:
            raise self.put_error
        self.objects[key] = body
        if not self.visible_after_put:
            self.hidden.add(key)

    def delete_object(self, key: str) -> None:
        self.objects.pop(key, None)
        self.deleted.append(key)


def fake_boto3(stack: dict[str, Any] | None, *, error: Exception | None = None) -> Any:
    """A boto3 module whose cloudformation client returns one prepared stack."""

    class Client:
        def describe_stacks(self, StackName: str) -> dict[str, Any]:  # noqa: N803 - boto3 kwarg
            if error:
                raise error
            return {"Stacks": [stack] if stack is not None else []}

    return SimpleNamespace(client=lambda service, region_name=None: Client())


# --- Resolving the access point -------------------------------------------------


def test_parameters_are_searched_before_outputs(monkeypatch: pytest.MonkeyPatch) -> None:
    """A parameter is what the stack was told to use; an output may be derived.

    Both are present here and differ, so the assertion is about the order rather
    than about either being readable.
    """
    monkeypatch.setitem(
        sys.modules,
        "boto3",
        fake_boto3(
            {
                "Parameters": [{"ParameterKey": "S3AccessPointAlias", "ParameterValue": "from-param"}],
                "Outputs": [{"OutputKey": "S3AccessPointAlias", "OutputValue": "from-output"}],
            }
        ),
    )
    value, source = resolve_access_point("some-stack", None)
    assert value == "from-param"
    assert source == "parameter S3AccessPointAlias"


def test_key_precedence_is_the_declared_order(monkeypatch: pytest.MonkeyPatch) -> None:
    """When several known keys are populated, the first in ACCESS_POINT_KEYS wins."""
    monkeypatch.setitem(
        sys.modules,
        "boto3",
        fake_boto3(
            {
                "Parameters": [
                    {"ParameterKey": key, "ParameterValue": f"value-for-{key}"} for key in ACCESS_POINT_KEYS
                ],
                "Outputs": [],
            }
        ),
    )
    value, source = resolve_access_point("some-stack", None)
    assert value == f"value-for-{ACCESS_POINT_KEYS[0]}"
    assert ACCESS_POINT_KEYS[0] in source


@pytest.mark.parametrize("key", ACCESS_POINT_KEYS)
def test_each_declared_key_is_read(monkeypatch: pytest.MonkeyPatch, key: str) -> None:
    """Every key in the list is actually consulted.

    A name in the tuple that nothing reads is a promise the script does not keep,
    and the failure would look like "this pattern has no access point".
    """
    monkeypatch.setitem(
        sys.modules,
        "boto3",
        fake_boto3({"Parameters": [{"ParameterKey": key, "ParameterValue": "ap-value"}], "Outputs": []}),
    )
    value, source = resolve_access_point("some-stack", None)
    assert value == "ap-value"
    assert key in source


def test_output_is_used_when_no_parameter_carries_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """A pattern that only emits the access point as an output still resolves."""
    monkeypatch.setitem(
        sys.modules,
        "boto3",
        fake_boto3({"Parameters": [], "Outputs": [{"OutputKey": "S3AccessPointArn", "OutputValue": "arn:aws:s3:::x"}]}),
    )
    value, source = resolve_access_point("some-stack", None)
    assert value == "arn:aws:s3:::x"
    assert source.startswith("output ")


def test_an_empty_value_is_not_a_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    """A declared-but-blank parameter must not shadow a populated output.

    A stack can carry the parameter with an empty default, which reads as present.
    Accepting it would build a helper against "" and report the resulting error as a
    permission problem.
    """
    monkeypatch.setitem(
        sys.modules,
        "boto3",
        fake_boto3(
            {
                "Parameters": [{"ParameterKey": "S3AccessPointAlias", "ParameterValue": "   "}],
                "Outputs": [{"OutputKey": "S3AccessPointAlias", "OutputValue": "real-value"}],
            }
        ),
    )
    value, source = resolve_access_point("some-stack", None)
    assert value == "real-value"
    assert source.startswith("output ")


def test_unknown_key_name_is_matched_by_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    """A pattern using its own naming is not a dead end, and the report says so."""
    monkeypatch.setitem(
        sys.modules,
        "boto3",
        fake_boto3(
            {
                "Parameters": [{"ParameterKey": "Legal_S3AccessPoint_Name", "ParameterValue": "odd-name"}],
                "Outputs": [],
            }
        ),
    )
    value, source = resolve_access_point("some-stack", None)
    assert value == "odd-name"
    assert "matched by name" in source, "a fallback match must be distinguishable from an exact one"


def test_unresolvable_stack_names_what_it_looked_for(monkeypatch: pytest.MonkeyPatch) -> None:
    """The error has to be actionable without reading the script."""
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3({"Parameters": [], "Outputs": []}))
    with pytest.raises(SmokeError) as excinfo:
        resolve_access_point("some-stack", None)
    message = str(excinfo.value)
    assert ACCESS_POINT_KEYS[0] in message
    assert "--access-point" in message


def test_describe_failure_carries_the_stack_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """A wrong stack name or region is the common case; say which stack failed."""
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3(None, error=RuntimeError("does not exist")))
    with pytest.raises(SmokeError, match="typo-stack"):
        resolve_access_point("typo-stack", None)


# --- The steps ------------------------------------------------------------------


def test_read_verifies_the_listed_size(capsys: pytest.CaptureFixture) -> None:
    """The listing's size and the bytes fetched have to agree."""
    helper = FakeHelper({"reports/a.md": b"12345"})
    files = step_list(helper, "reports/", 50)
    step_read(helper, files)
    assert "5" in capsys.readouterr().out


def test_read_on_an_empty_listing_does_not_claim_a_read(capsys: pytest.CaptureFixture) -> None:
    """Nothing to read is a reportable state, not a passed read."""
    helper = FakeHelper({})
    step_read(helper, step_list(helper, "", 50))
    out = capsys.readouterr().out.lower()
    assert "skip" in out or "no object" in out or "empty" in out


def test_write_that_is_not_listed_is_refused() -> None:
    """The failure a mock cannot produce, and the reason this script exists.

    put returns, the read back matches, and the object is still not in a listing.
    That is what a portal user experiences as a failed upload, so a 200 alone must
    not be reported as a working write.
    """
    helper = FakeHelper(visible_after_put=False)
    with pytest.raises(SmokeError, match="does not appear"):
        step_write_and_read_back(helper, DEFAULT_WRITE_PREFIX)


def test_write_round_trip_passes_when_visible() -> None:
    """The clean path returns the key, so the caller can remove it."""
    helper = FakeHelper()
    key = step_write_and_read_back(helper, DEFAULT_WRITE_PREFIX)
    assert key.startswith(DEFAULT_WRITE_PREFIX)
    assert key in helper.objects


def test_write_prefix_must_end_in_a_slash() -> None:
    """Without the slash the object lands beside real data instead of under it."""
    with pytest.raises(SmokeError, match="must end with"):
        step_write_and_read_back(FakeHelper(), "smoke-checks")


def test_write_confined_to_the_given_prefix() -> None:
    """The script writes only where it was told to."""
    helper = FakeHelper({"reports/keep.md": b"x"})
    step_write_and_read_back(helper, "smoke-checks/")
    assert all(k.startswith(("smoke-checks/", "reports/")) for k in helper.objects)
    assert helper.objects["reports/keep.md"] == b"x"


# --- Exit codes and cleanup -----------------------------------------------------


def test_unresolved_access_point_is_usage_not_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exit 2: the check could not be run. Distinct from a check that ran and failed."""
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3({"Parameters": [], "Outputs": []}))
    assert smoke.main(["--stack", "some-stack"]) == EXIT_USAGE


def test_reachable_access_point_exits_zero_and_cleans_up(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exit 0, and nothing left behind under the write prefix."""
    helper = FakeHelper({"reports/a.md": b"hello"})
    monkeypatch.setattr(smoke, "build_helper", lambda ap, region: helper)
    assert smoke.main(["--access-point", "alias-abc", "--list-prefix", "reports/"]) == EXIT_OK
    assert helper.deleted, "the written object must be removed"
    assert not [k for k in helper.objects if k.startswith(DEFAULT_WRITE_PREFIX)]


def test_keep_leaves_the_object(monkeypatch: pytest.MonkeyPatch) -> None:
    """--keep is for inspecting the result from another client."""
    helper = FakeHelper()
    monkeypatch.setattr(smoke, "build_helper", lambda ap, region: helper)
    assert smoke.main(["--access-point", "alias-abc", "--keep"]) == EXIT_OK
    assert not helper.deleted
    assert [k for k in helper.objects if k.startswith(DEFAULT_WRITE_PREFIX)]


def test_read_only_skips_the_write(monkeypatch: pytest.MonkeyPatch) -> None:
    """For a caller with list and get but no put."""
    helper = FakeHelper({"a.md": b"x"}, put_error=AssertionError("put must not be called"))
    monkeypatch.setattr(smoke, "build_helper", lambda ap, region: helper)
    assert smoke.main(["--access-point", "alias-abc", "--read-only"]) == EXIT_OK


def test_failed_step_exits_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """A step that ran and failed is exit 1, not 2."""
    helper = FakeHelper(visible_after_put=False)
    monkeypatch.setattr(smoke, "build_helper", lambda ap, region: helper)
    assert smoke.main(["--access-point", "alias-abc"]) == EXIT_FAILED


def test_access_denied_gets_the_arn_form_hint(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    """The one error whose cause is worth naming in the output.

    AccessDenied on list, get and put alike is the signature of a policy naming the
    access point in the bucket form, which deploys and reports CREATE_COMPLETE.
    """
    helper = FakeHelper(list_error=RuntimeError("An error occurred (AccessDenied) when calling ListObjectsV2"))
    monkeypatch.setattr(smoke, "build_helper", lambda ap, region: helper)
    assert smoke.main(["--access-point", "alias-abc"]) == EXIT_FAILED
    assert "accesspoint/" in capsys.readouterr().out


def test_missing_dependency_is_not_diagnosed_as_a_permission_problem(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """The misdirection this script shipped with on its first run.

    `except Exception` caught ModuleNotFoundError and attached the IAM hint, sending
    the reader to rewrite a policy that had never been consulted.
    """

    def no_boto3(access_point: str, region: str | None) -> Any:
        raise ImportError("No module named 'boto3'")

    monkeypatch.setattr(smoke, "build_helper", no_boto3)
    assert smoke.main(["--access-point", "alias-abc"]) == EXIT_FAILED
    out = capsys.readouterr().out
    assert "make install" in out
    assert "AccessDenied" not in out


def test_alias_is_elided_in_the_output(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    """Output gets pasted into issues, and an alias carries a random token."""
    helper = FakeHelper()
    monkeypatch.setattr(smoke, "build_helper", lambda ap, region: helper)
    smoke.main(["--access-point", "eda--op-s3alias-secrettoken12345"])
    assert "secrettoken12345" not in capsys.readouterr().out


# --- Argument surface -----------------------------------------------------------


def test_a_source_is_required() -> None:
    """Neither --stack nor --access-point is a usage error, not a default."""
    with pytest.raises(SystemExit):
        parse_args([])


def test_stack_and_access_point_are_mutually_exclusive() -> None:
    """Two sources would leave the report ambiguous about which was used."""
    with pytest.raises(SystemExit):
        parse_args(["--stack", "s", "--access-point", "a"])


def test_default_write_prefix_is_confined_and_ends_in_a_slash() -> None:
    """The default must not put objects at the access point root."""
    assert DEFAULT_WRITE_PREFIX.endswith("/")
    assert DEFAULT_WRITE_PREFIX.strip("/"), "the default must not be the root"
