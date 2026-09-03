"""Tests for the portal preflight checks.

Only the pure parts are exercised here: config parsing, stack-name reading, and
the verdict each comparison produces. The AWS-facing calls are the part that has
to be run against a deployed sandbox, and asserting on a mock of them would
prove that the mock matches the code rather than that the code matches AWS.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parent.parent / "portal_preflight.py"
_spec = importlib.util.spec_from_file_location("portal_preflight", MODULE_PATH)
assert _spec and _spec.loader
preflight = importlib.util.module_from_spec(_spec)
sys.modules["portal_preflight"] = preflight
_spec.loader.exec_module(preflight)


class TestConfigDefault:
    """Reading scalar defaults out of the TypeScript config."""

    def test_reads_literal_behind_env_fallback(self) -> None:
        source = '  vpcId: (process.env.AMPLIFY_PORTAL_VPC_ID || "vpc-abc123").trim(),'
        assert preflight.config_default(source, "vpcId") == "vpc-abc123"

    def test_absent_key_is_none(self) -> None:
        assert preflight.config_default("  other: 1,", "vpcId") is None

    def test_empty_literal_reads_as_empty(self) -> None:
        assert preflight.config_default('  vpcId: "",', "vpcId") == ""


class TestConfigBool:
    """Reading boolean defaults, including the env-derived forms."""

    @pytest.mark.parametrize(
        ("expr", "expected"),
        [
            ('process.env.X !== "0"', True),
            ('process.env.X === "1"', False),
            ("true", True),
            ("false", False),
        ],
    )
    def test_recognised_forms(self, expr: str, expected: bool) -> None:
        source = f"  dynamoDbGatewayEndpointExists: {expr},\n"
        assert preflight.config_bool(source, "dynamoDbGatewayEndpointExists") is expected

    def test_unrecognised_expression_is_none(self) -> None:
        source = "  dynamoDbGatewayEndpointExists: someHelper(a, b),\n"
        assert preflight.config_bool(source, "dynamoDbGatewayEndpointExists") is None

    def test_absent_key_is_none(self) -> None:
        assert preflight.config_bool("", "dynamoDbGatewayEndpointExists") is None


class TestSandboxIdentifier:
    """The identifier is what tells two sandboxes apart in a report."""

    def test_extracts_identifier(self) -> None:
        stack = "amplify-fsxns3apamplifyportal-demo-sandbox-753443151c-auth179371D7-X"
        assert preflight.sandbox_identifier(stack) == "demo"

    def test_non_sandbox_stack_is_named_as_such(self) -> None:
        assert preflight.sandbox_identifier("my-branch-stack") == "(not a sandbox stack)"


class TestOntapDetection:
    """What identifies an ONTAP-facing function, and how it is labelled."""

    def test_connecting_takes_an_address_and_a_credential(self) -> None:
        """The address alone is not enough, and treating it as enough misfired.

        The data platform inventory reads the address to say which platform is the
        working one. It connects to nothing and holds no credential, and on the
        address alone this check reported it as disagreeing with the other functions
        about a file system it never contacts.
        """
        assert preflight.ONTAP_CONNECT_VARS == ("ONTAP_MGMT_IP", "ONTAP_SECRET_NAME")
        assert set(preflight.ONTAP_CONNECT_VARS) <= set(preflight.ONTAP_TARGET_VARS)

    def test_detection_is_by_environment_not_name(self) -> None:
        """A name list has to be updated when a function is added; this does not.

        ListSnapshotsFunction was missed by the earlier name-hint list, and its
        panel reported ONTAP's own authorization error while the rest worked.
        """
        assert preflight.ONTAP_ADDRESS_VAR == "ONTAP_MGMT_IP"
        assert preflight.ONTAP_ADDRESS_VAR in preflight.ONTAP_TARGET_VARS

    def test_target_covers_address_svm_and_credential(self) -> None:
        """Any of the three can point at the wrong file system on its own."""
        assert set(preflight.ONTAP_TARGET_VARS) == {
            "ONTAP_MGMT_IP",
            "SVM_NAME",
            "ONTAP_SECRET_NAME",
        }

    def test_short_name_keeps_the_readable_segment(self) -> None:
        name = "amplify-fsxns3apamplifypo-ListSnapshotsFunction17E-IKzBphg7QYSo"
        assert preflight.short_name(name) == "ListSnapshotsFunction17E"

    def test_short_name_passes_through_a_plain_name(self) -> None:
        assert preflight.short_name("myfunc") == "myfunc"


class TestResult:
    """A skipped check must not read as a passing one."""

    def test_statuses_are_distinct(self) -> None:
        assert preflight.OK != preflight.SKIP != preflight.FAIL

    def test_remedy_is_optional(self) -> None:
        result = preflight.Result("name", preflight.OK, "detail")
        assert result.remedy == ""


class TestSandboxRoot:
    """Comparing two resources for "same sandbox" across different nested stacks."""

    ROOT = "amplify-fsxns3apamplifyportal-demo-sandbox-753443151c"

    def test_auth_and_data_nested_stacks_share_a_root(self) -> None:
        auth = f"{self.ROOT}-auth179371D7-1X5N7VRRW3H34"
        data = f"{self.ROOT}-data7552DF31-Z4LHLM0GG5EN"
        assert preflight.sandbox_root(auth) == preflight.sandbox_root(data) == self.ROOT

    def test_different_sandboxes_do_not_match(self) -> None:
        other = "amplify-fsxns3apamplifyportal-phase2auth-sandbox-863ba19ead-data7552DF31-1SUL4UIYCRNZ3"
        assert preflight.sandbox_root(other) != self.ROOT

    def test_non_sandbox_name_passes_through(self) -> None:
        assert preflight.sandbox_root("some-other-stack") == "some-other-stack"

    def test_empty_is_empty(self) -> None:
        assert preflight.sandbox_root("") == ""


class TestGatewayEndpointRoute:
    """Who owns the DynamoDB route, not merely whether some route exists.

    The AWS calls are stubbed here, against this file's general stance, because both
    defects were in what the answer was taken to mean rather than in the call.

    First: the check asked whether the route table carried any prefix-list route, and
    the S3 gateway endpoint puts one on the same table, so the answer was always yes.
    It reported "matching" on 2026-09-02 while the DynamoDB endpoint had been deleted
    with a leftover sandbox and the VPC Lambdas were timing out against DynamoDB.

    Second: presence alone still cannot separate "another stack owns it, so reuse the
    route" from "this stack owns it, so do not declare it external" — and the latter
    would have the next deploy remove the endpoint its own functions route through.
    """

    RTB = "rtb-0dc6848a7c1ef7ca3"
    OURS = "amplify-fsxns3apamplifyportal-demo-sandbox-753443151c-auth179371D7-1X5N7VRRW3H34"
    OUR_DATA = "amplify-fsxns3apamplifyportal-demo-sandbox-753443151c-data7552DF31-Z4LHLM0GG5EN"
    THEIR_DATA = "amplify-fsxns3apamplifyportal-phase2auth-sandbox-863ba19ead-data7552DF31-1SUL4UIYCRNZ3"

    VPC = "vpc-05192d06e1e91d756"

    def _config(self, claim: str, rtb: str | None = None) -> str:
        return (
            f"  dynamoDbGatewayEndpointExists: {claim},\n"
            f'  vpcId: (process.env.AMPLIFY_PORTAL_VPC_ID || "{self.VPC}").trim(),\n'
            f'  vpcRouteTableIds: idList(process.env.X, "{rtb or self.RTB}"),\n'
        )

    def _stub(self, monkeypatch: pytest.MonkeyPatch, endpoints: list[list]) -> None:
        """Stub `describe-vpc-endpoints` in the shape the API actually returns.

        Only `vpc-id` and `service-name` are passed as filters. `route-table-id` is
        not a valid DescribeVpcEndpoints filter and returns `InvalidFilter`; an
        earlier version of this check used it, and a stub that accepted it let the
        tests pass while the real call failed. The assertions below pin the filters
        so that cannot recur silently.
        """

        def fake_aws(*args: str) -> str:
            assert "describe-vpc-endpoints" in args, f"unexpected call: {args}"
            assert f"Name=vpc-id,Values={self.VPC}" in args
            assert any(
                a.startswith("Name=service-name,Values=com.amazonaws.") and a.endswith(".dynamodb") for a in args
            )
            assert not any("route-table-id" in a for a in args)
            return json.dumps(endpoints)

        monkeypatch.setattr(preflight, "aws", fake_aws)

    def test_no_endpoint_and_this_stack_creates_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._stub(monkeypatch, [])

        result = preflight.check_gateway_endpoint("ap-northeast-1", self._config("false"), self.OURS)

        assert result.status == preflight.OK

    def test_no_endpoint_while_config_claims_one_exists(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The outage of 2026-09-02, as the check should have reported it.

        The endpoint in the VPC sits on a different route table, which is not a route
        for these Lambdas' subnet and must not count as one.
        """
        self._stub(monkeypatch, [["vpce-0elsewhere", ["rtb-0000000000000dead"], self.THEIR_DATA]])

        result = preflight.check_gateway_endpoint("ap-northeast-1", self._config("true"), self.OURS)

        assert result.status == preflight.FAIL
        assert "no DynamoDB gateway endpoint" in result.detail

    def test_our_own_endpoint_matches_a_false_claim(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """After ownership moves to this stack, the route existing is expected."""
        self._stub(monkeypatch, [["vpce-084356979cea4cdda", [self.RTB], self.OUR_DATA]])

        result = preflight.check_gateway_endpoint("ap-northeast-1", self._config("false"), self.OURS)

        assert result.status == preflight.OK
        assert "owned by this sandbox" in result.detail

    def test_our_own_endpoint_with_a_true_claim_is_a_pending_self_inflicted_outage(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._stub(monkeypatch, [["vpce-084356979cea4cdda", [self.RTB], self.OUR_DATA]])

        result = preflight.check_gateway_endpoint("ap-northeast-1", self._config("true"), self.OURS)

        assert result.status == preflight.FAIL
        assert "belongs to this sandbox" in result.detail

    def test_another_stacks_endpoint_is_reusable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._stub(monkeypatch, [["vpce-0aaa", [self.RTB], self.THEIR_DATA]])

        result = preflight.check_gateway_endpoint("ap-northeast-1", self._config("true"), self.OURS)

        assert result.status == preflight.OK
        assert "reuses the route" in result.detail

    def test_another_stacks_endpoint_conflicts_with_a_false_claim(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The route conflict that rolls the data stack back."""
        self._stub(monkeypatch, [["vpce-0aaa", [self.RTB], self.THEIR_DATA]])

        result = preflight.check_gateway_endpoint("ap-northeast-1", self._config("false"), self.OURS)

        assert result.status == preflight.FAIL
        assert "is held by" in result.detail

    def test_a_hand_made_endpoint_is_named_as_unmanaged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An endpoint with no stack tag is the state a manual restore leaves behind."""
        self._stub(monkeypatch, [["vpce-05473e2c6181c36aa", [self.RTB], None]])

        result = preflight.check_gateway_endpoint("ap-northeast-1", self._config("false"), self.OURS)

        assert result.status == preflight.FAIL
        assert "created by hand" in result.detail

    def test_unreadable_claim_skips(self) -> None:
        result = preflight.check_gateway_endpoint(
            "ap-northeast-1", "  dynamoDbGatewayEndpointExists: f(x),\n", self.OURS
        )

        assert result.status == preflight.SKIP

    def test_missing_route_table_skips(self) -> None:
        result = preflight.check_gateway_endpoint(
            "ap-northeast-1", "  dynamoDbGatewayEndpointExists: false,\n", self.OURS
        )

        assert result.status == preflight.SKIP


class TestPrintSandboxIdentifier:
    """The exit-code contract `scripts/sandbox.sh` depends on.

    The wrapper distinguishes three answers, and conflating any two of them
    reintroduces the failure it exists to prevent:

      0  the identifier was resolved, so pass it to `ampx sandbox`
      3  nothing is deployed, so the CLI's own default is correct
      1  outputs exist but the sandbox is unknown, so **stop**

    Falling back to the default on 1 is what creates a second sandbox beside the one
    the outputs name. On 2026-09-03 that reached ~25 Lambda functions and a Cognito
    user pool before failing on the gateway-endpoint route, and Amplify does not roll
    a failed sandbox back.
    """

    def test_absent_outputs_reports_nothing_deployed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(preflight, "OUTPUTS_PATH", tmp_path / "amplify_outputs.json")
        assert preflight.print_sandbox_identifier("ap-northeast-1") == 3
        # Nothing on stdout, so a caller substituting the output cannot mistake the
        # message for an identifier.
        assert capsys.readouterr().out == ""

    def test_unparseable_outputs_stops_rather_than_defaults(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "amplify_outputs.json"
        path.write_text("not json", encoding="utf-8")
        monkeypatch.setattr(preflight, "OUTPUTS_PATH", path)
        assert preflight.print_sandbox_identifier("ap-northeast-1") == 1

    def test_outputs_without_a_pool_stops(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        path = tmp_path / "amplify_outputs.json"
        path.write_text(json.dumps({"auth": {}}), encoding="utf-8")
        monkeypatch.setattr(preflight, "OUTPUTS_PATH", path)
        assert preflight.print_sandbox_identifier("ap-northeast-1") == 1

    def test_prints_only_the_identifier_on_success(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / "amplify_outputs.json"
        path.write_text(
            json.dumps({"auth": {"user_pool_id": "ap-northeast-1_X", "aws_region": "ap-northeast-1"}}),
            encoding="utf-8",
        )
        monkeypatch.setattr(preflight, "OUTPUTS_PATH", path)
        monkeypatch.setattr(
            preflight,
            "owning_stack",
            lambda pool, region: "amplify-fsxns3apamplifyportal-demo-sandbox-753443151c",
        )
        assert preflight.print_sandbox_identifier("ap-northeast-1") == 0
        # Exactly the identifier and a newline: the wrapper interpolates this into a
        # command line, so a decorated message would become an invalid --identifier.
        assert capsys.readouterr().out == "demo\n"

    def test_a_non_sandbox_stack_stops(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # A pool owned by something that is not a sandbox has no identifier to pass.
        # Printing the placeholder would produce `--identifier "(not a sandbox stack)"`.
        path = tmp_path / "amplify_outputs.json"
        path.write_text(
            json.dumps({"auth": {"user_pool_id": "ap-northeast-1_X", "aws_region": "ap-northeast-1"}}),
            encoding="utf-8",
        )
        monkeypatch.setattr(preflight, "OUTPUTS_PATH", path)
        monkeypatch.setattr(preflight, "owning_stack", lambda pool, region: "some-other-stack")
        assert preflight.print_sandbox_identifier("ap-northeast-1") == 1

    def test_a_failure_reading_the_owner_stops(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def explode(pool: str, region: str) -> str:
            raise RuntimeError("AccessDenied")

        path = tmp_path / "amplify_outputs.json"
        path.write_text(
            json.dumps({"auth": {"user_pool_id": "ap-northeast-1_X", "aws_region": "ap-northeast-1"}}),
            encoding="utf-8",
        )
        monkeypatch.setattr(preflight, "OUTPUTS_PATH", path)
        monkeypatch.setattr(preflight, "owning_stack", explode)
        assert preflight.print_sandbox_identifier("ap-northeast-1") == 1
