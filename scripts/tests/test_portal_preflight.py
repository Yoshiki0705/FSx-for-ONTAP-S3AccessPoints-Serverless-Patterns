"""Tests for the portal preflight checks.

Only the pure parts are exercised here: config parsing, stack-name reading, and
the verdict each comparison produces. The AWS-facing calls are the part that has
to be run against a deployed sandbox, and asserting on a mock of them would
prove that the mock matches the code rather than that the code matches AWS.

The exception is ``FakeAws`` near the end. It returns raw API-shaped payloads and
applies the code's own ``--query`` with ``jmespath``, so a malformed query or a
mistaken reading of the response shape fails here instead of passing against a
mock that was written to agree with the code. It is still not a deployed sandbox:
what these tests do not show is that the real CLI returns these shapes.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import jmespath
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

    def test_the_address_variable_is_part_of_the_target(self) -> None:
        """Which functions to check comes from backend.ts; these say what each must hold.

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

    RTB = "rtb-0123456789abcdef0"
    OURS = "amplify-fsxns3apamplifyportal-demo-sandbox-753443151c-auth179371D7-1X5N7VRRW3H34"
    OUR_DATA = "amplify-fsxns3apamplifyportal-demo-sandbox-753443151c-data7552DF31-Z4LHLM0GG5EN"
    THEIR_DATA = "amplify-fsxns3apamplifyportal-phase2auth-sandbox-863ba19ead-data7552DF31-1SUL4UIYCRNZ3"

    VPC = "vpc-0123456789abcdef0"

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
        self._stub(monkeypatch, [["vpce-0123456789abcdef0", [self.RTB], self.OUR_DATA]])

        result = preflight.check_gateway_endpoint("ap-northeast-1", self._config("false"), self.OURS)

        assert result.status == preflight.OK
        assert "owned by this sandbox" in result.detail

    def test_our_own_endpoint_with_a_true_claim_is_a_pending_self_inflicted_outage(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._stub(monkeypatch, [["vpce-0123456789abcdef0", [self.RTB], self.OUR_DATA]])

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
        self._stub(monkeypatch, [["vpce-0fedcba9876543210", [self.RTB], None]])

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


class TestHostedBinding:
    """Comparing the published bundle against the backend deployed now.

    The failure this catches has no signature in the browser: the page loads, the
    sign-in form renders, and every credential is rejected, which is also what an
    account in the wrong pool looks like. So it has to be caught before the URL is
    handed out rather than diagnosed afterwards.

    `aws` is stubbed rather than the whole function, because the mapping from
    Amplify's answer to a verdict is the part worth pinning.
    """

    STACK = "amplify-fsxns3apamplifyportal-demo-sandbox-753443151c-auth179371D7-AAA"
    POOL = "ap-northeast-1_current"

    def _apps(self, monkeypatch: pytest.MonkeyPatch, apps: list[dict]) -> None:
        monkeypatch.setattr(preflight, "aws", lambda *a, **k: json.dumps(apps))

    def _app(self, tags: dict | None) -> dict:
        return {
            "name": "fsxn-portal-demo",
            "appId": "d0123456789abc",
            "defaultDomain": "d0123456789abc.amplifyapp.com",
            "tags": tags,
        }

    def test_matching_pool_passes_and_names_the_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._apps(monkeypatch, [self._app({"portal:user-pool-id": self.POOL})])
        result = preflight.check_hosted_binding("ap-northeast-1", self.POOL, self.STACK)
        assert result.status == preflight.OK
        assert "https://demo.d0123456789abc.amplifyapp.com" in result.detail

    def test_a_different_pool_fails_and_names_both(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._apps(monkeypatch, [self._app({"portal:user-pool-id": "ap-northeast-1_stale"})])
        result = preflight.check_hosted_binding("ap-northeast-1", self.POOL, self.STACK)
        assert result.status == preflight.FAIL
        assert "ap-northeast-1_stale" in result.detail
        assert self.POOL in result.detail
        assert "make portal-hosting" in result.remedy

    def test_an_untagged_app_fails_rather_than_assuming_it_is_fine(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Published before the tags existed, or by hand. Absence of evidence is not
        # evidence that the binding holds, and this URL still gets handed out.
        self._apps(monkeypatch, [self._app(None)])
        result = preflight.check_hosted_binding("ap-northeast-1", self.POOL, self.STACK)
        assert result.status == preflight.FAIL

    def test_no_app_skips_because_publishing_is_optional(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The tunnel and localhost are legitimate, so "nothing published" must not be
        # a failure -- a check that fails on every unpublished checkout gets removed.
        self._apps(monkeypatch, [])
        assert preflight.check_hosted_binding("ap-northeast-1", self.POOL, self.STACK).status == preflight.SKIP

    def test_another_sandboxs_app_is_not_mistaken_for_this_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Publishing from a second sandbox creates fsxn-portal-<other>; reading its
        # tag here would compare this pool against an unrelated bundle.
        other = {**self._app({"portal:user-pool-id": "ap-northeast-1_other"}), "name": "fsxn-portal-other"}
        self._apps(monkeypatch, [other])
        assert preflight.check_hosted_binding("ap-northeast-1", self.POOL, self.STACK).status == preflight.SKIP

    def test_unknown_sandbox_skips(self) -> None:
        assert preflight.check_hosted_binding("ap-northeast-1", self.POOL, None).status == preflight.SKIP

    def test_an_aws_failure_skips_rather_than_failing_the_run(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Missing amplify:ListApps permission is not a broken binding, and reporting
        # it as one would send somebody to republish a bundle that is fine.
        def explode(*a: object, **k: object) -> str:
            raise RuntimeError("AccessDenied")

        monkeypatch.setattr(preflight, "aws", explode)
        assert preflight.check_hosted_binding("ap-northeast-1", self.POOL, self.STACK).status == preflight.SKIP


class TestConfigExpression:
    """Reading a value out of the config object rather than out of the file."""

    # The shape that broke the first version of the pre-deploy checks: the same key
    # name appears in the interface and in the object, and the declaration comes
    # first.
    INTERFACE_THEN_OBJECT = (
        "export interface PortalConfig {\n"
        "  region: string;\n"
        "  s3ApAlias: string;\n"
        "}\n"
        "\n"
        "export const config: PortalConfig = {\n"
        '  region: process.env.AMPLIFY_PORTAL_REGION || "ap-northeast-1",\n'
        '  s3ApAlias: "myap-abc123-s3alias",\n'
        "};\n"
    )

    def test_the_interface_declaration_is_not_mistaken_for_the_value(self) -> None:
        assert preflight.config_default(self.INTERFACE_THEN_OBJECT, "region") == "ap-northeast-1"

    def test_a_value_wrapped_onto_the_next_line_is_read_whole(self) -> None:
        source = (
            "export const config = {\n"
            "  ontapSecretName:\n"
            '    process.env.ONTAP_SECRET_NAME || "fsx-ontap-fsxadmin-credentials",\n'
            "};\n"
        )
        assert preflight.config_default(source, "ontapSecretName") == "fsx-ontap-fsxadmin-credentials"

    def test_a_helper_call_with_no_literal_does_not_borrow_the_next_entry(self) -> None:
        source = (
            "export const config = {\n"
            "  vpcSubnetIds: idList(process.env.AMPLIFY_PORTAL_VPC_SUBNET_IDS),\n"
            '  ontapSvmName: "svm01",\n'
            "};\n"
        )
        assert preflight.config_default(source, "vpcSubnetIds") is None


class TestEffectiveValues:
    """The environment wins over the literal, as it does in the config itself."""

    SOURCE = (
        "export const config = {\n"
        '  region: process.env.AMPLIFY_PORTAL_REGION || "ap-northeast-1",\n'
        "  vpcRouteTableIds: idList(process.env.AMPLIFY_PORTAL_VPC_ROUTE_TABLE_IDS),\n"
        '  vpcSubnetIds: idList(process.env.AMPLIFY_PORTAL_VPC_SUBNET_IDS, "subnet-aaa"),\n'
        "};\n"
    )

    def test_literal_is_used_when_the_variable_is_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AMPLIFY_PORTAL_REGION", raising=False)
        assert preflight.effective_scalar(self.SOURCE, "region") == ("ap-northeast-1", "portal-config.ts")

    def test_variable_overrides_the_literal_and_is_named(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AMPLIFY_PORTAL_REGION", "us-east-1")
        assert preflight.effective_scalar(self.SOURCE, "region") == ("us-east-1", "AMPLIFY_PORTAL_REGION")

    def test_a_blank_variable_is_not_a_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AMPLIFY_PORTAL_REGION", "   ")
        assert preflight.effective_scalar(self.SOURCE, "region")[0] == "ap-northeast-1"

    def test_list_from_the_environment_is_split_and_trimmed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AMPLIFY_PORTAL_VPC_ROUTE_TABLE_IDS", " rtb-a , rtb-b ")
        values, origin = preflight.effective_list(self.SOURCE, "vpcRouteTableIds")
        assert values == ["rtb-a", "rtb-b"]
        assert origin == "AMPLIFY_PORTAL_VPC_ROUTE_TABLE_IDS"

    def test_list_falls_back_to_the_literal_in_the_helper_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AMPLIFY_PORTAL_VPC_SUBNET_IDS", raising=False)
        assert preflight.effective_list(self.SOURCE, "vpcSubnetIds")[0] == ["subnet-aaa"]

    def test_an_env_only_list_reads_as_empty_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AMPLIFY_PORTAL_VPC_ROUTE_TABLE_IDS", raising=False)
        assert preflight.effective_list(self.SOURCE, "vpcRouteTableIds")[0] == []


class TestCheckConfig:
    """The checks that run before anything is deployed."""

    def _config(self, **overrides: str) -> str:
        values = {
            "region": '"ap-northeast-1"',
            "s3ApAlias": '""',
            "stateMachineArn": '""',
            "ontapMgmtIp": '""',
            "ontapSecretName": '""',
            "ontapSvmName": '""',
            "vpcId": '""',
            "vpcSubnetIds": "[]",
            "vpcRouteTableIds": "[]",
            "allowNoBlockExpiry": "false",
        }
        values.update(overrides)
        body = "".join(f"  {key}: {value},\n" for key, value in values.items())
        return "export const config = {\n" + body + "};\n"

    def _verdict(self, results: list, name: str) -> str:
        return next(r.status for r in results if r.name == name)

    @pytest.fixture(autouse=True)
    def _no_session_region(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Every test but the region ones runs without a session region, so a region
        # on the developer's machine does not decide whether they pass.
        monkeypatch.setattr(preflight, "session_region", lambda: None)

    def test_a_placeholder_state_machine_arn_fails(self) -> None:
        source = self._config(stateMachineArn='"arn:aws:states:ap-northeast-1:123456789012:stateMachine:placeholder"')
        results = preflight.check_config(source)
        assert self._verdict(results, "state machine") == preflight.FAIL

    def test_an_empty_state_machine_arn_skips_rather_than_fails(self) -> None:
        # Empty is a legible state: the resolver reports that processing is not
        # configured. A placeholder is the one that deploys as though it were.
        results = preflight.check_config(self._config())
        assert self._verdict(results, "state machine") == preflight.SKIP

    def test_a_real_looking_arn_passes(self) -> None:
        source = self._config(stateMachineArn='"arn:aws:states:ap-northeast-1:210987654321:stateMachine:uc1"')
        assert self._verdict(preflight.check_config(source), "state machine") == preflight.OK

    def test_a_vpc_without_route_tables_fails(self) -> None:
        source = self._config(vpcId='"vpc-abc"', vpcSubnetIds='["subnet-abc"]')
        assert self._verdict(preflight.check_config(source), "VPC wiring") == preflight.FAIL

    def test_allow_no_block_expiry_makes_that_deliberate(self) -> None:
        source = self._config(vpcId='"vpc-abc"', vpcSubnetIds='["subnet-abc"]', allowNoBlockExpiry="true")
        assert self._verdict(preflight.check_config(source), "VPC wiring") == preflight.OK

    def test_a_vpc_without_subnets_fails(self) -> None:
        source = self._config(vpcId='"vpc-abc"', vpcRouteTableIds='["rtb-abc"]')
        assert self._verdict(preflight.check_config(source), "VPC wiring") == preflight.FAIL

    def test_no_vpc_skips_because_the_admin_panels_are_optional(self) -> None:
        assert self._verdict(preflight.check_config(self._config()), "VPC wiring") == preflight.SKIP

    def test_a_half_configured_ontap_connection_fails(self) -> None:
        source = self._config(ontapMgmtIp='"10.0.3.72"', ontapSvmName='"svm01"')
        assert self._verdict(preflight.check_config(source), "ONTAP connection") == preflight.FAIL

    def test_an_absent_ontap_connection_skips(self) -> None:
        assert self._verdict(preflight.check_config(self._config()), "ONTAP connection") == preflight.SKIP

    def test_a_complete_ontap_connection_passes(self) -> None:
        source = self._config(ontapMgmtIp='"10.0.3.72"', ontapSecretName='"fsx-secret"', ontapSvmName='"svm01"')
        assert self._verdict(preflight.check_config(source), "ONTAP connection") == preflight.OK

    def test_a_region_disagreeing_with_the_session_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(preflight, "session_region", lambda: "us-east-1")
        assert self._verdict(preflight.check_config(self._config()), "region") == preflight.FAIL

    def test_a_matching_region_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(preflight, "session_region", lambda: "ap-northeast-1")
        assert self._verdict(preflight.check_config(self._config()), "region") == preflight.OK

    def test_no_session_region_skips_rather_than_guessing(self) -> None:
        assert self._verdict(preflight.check_config(self._config()), "region") == preflight.SKIP


# ---------------------------------------------------------------------------
# A fake AWS that answers in API shape
# ---------------------------------------------------------------------------

REGION = "ap-northeast-1"
VPC_ID = "vpc-0123456789abcdef0"
SUBNET_ID = "subnet-0123456789abcdef0"

# Sentinels. Output that must not hold a value is searched for these. They are
# documentation-range or obviously fake values, so they are safe to commit.
SENTINEL_IP = "203.0.113.77"
SENTINEL_SECRET = "sentinel-secret-name"
SENTINEL_ALIAS = "sentinel-alias-0001"
SENTINEL_BUCKET = "sentinel-lock-bucket"
SENTINEL_ARN = "arn:aws:states:ap-northeast-1:111122223333:stateMachine:sentinel"
SENTINELS = (SENTINEL_IP, SENTINEL_SECRET, SENTINEL_ALIAS, SENTINEL_BUCKET, SENTINEL_ARN, VPC_ID)

ONTAP_ENV = {"ONTAP_MGMT_IP": "config.ontapMgmtIp", "ONTAP_SECRET_NAME": "config.ontapSecretName"}

# The same two layouts backend.ts uses, with the three VPC functions plus two that
# must never be expected in a VPC: one reads the management address but holds no
# credential (the platform inventory), one has nothing to do with ONTAP.
SYNTHETIC_BACKEND: dict[str, dict] = {
    "ListSnapshotsFunction": {"vpc": True, "env": dict(ONTAP_ENV)},
    "ArpResponseFunction": {"vpc": True, "inline": True, "env": dict(ONTAP_ENV)},
    "ResourceMgmtFunction": {
        "vpc": True,
        "env": {**ONTAP_ENV, "S3_OBJECT_LOCK_BUCKET": "config.s3ObjectLockBucket"},
    },
    "PlatformDiscoveryFunction": {"inline": True, "env": {"ONTAP_MGMT_IP": "config.ontapMgmtIp"}},
    "ListFilesFunction": {
        "env": {"S3_AP_ALIAS": "config.s3ApAlias", "GROUP_AP_MAPPING": "JSON.stringify(config.groupApMapping || {})"}
    },
}
EXPECTED = ("ListSnapshotsFunction", "ArpResponseFunction", "ResourceMgmtFunction")


def make_backend(functions: dict[str, dict]) -> str:
    """Return a backend.ts-shaped source for ``functions``.

    ``vpc`` adds the ``...(vpcConfig && ...)`` spread, ``inline`` selects the
    one-line constructor layout, and ``env`` maps a variable to its TypeScript
    expression. The state machine override is included because it is the one
    binding that does not live in a function.
    """
    parts = ['import * as lambda from "aws-cdk-lib/aws-lambda";\n']
    for construct, spec in functions.items():
        env = "".join(f"    {var}: {expr},\n" for var, expr in spec.get("env", {}).items())
        spread = "  ...(vpcConfig && { vpc: vpcConfig.vpc }),\n" if spec.get("vpc") else ""
        body = f"  environment: {{\n{env}  }},\n  memorySize: 256,\n{spread}"
        if spec.get("inline"):
            parts.append(
                f'const {construct[0].lower()}{construct[1:]} = new lambda.Function(dataStack, "{construct}", {{\n{body}}});\n'
            )
        else:
            parts.append(
                f'const {construct[0].lower()}{construct[1:]} = new lambda.Function(\n  dataStack,\n  "{construct}",\n  {{\n{body}  }}\n);\n'
            )
    parts.append(
        'dataResources.cfnResources.cfnGraphqlApi.addPropertyOverride(\n  "EnvironmentVariables.STATE_MACHINE_ARN",\n  config.stateMachineArn\n);\n'
    )
    return "\n".join(parts)


def deployed(vpc: bool | None, **env: str) -> dict:
    """Return a ``get-function-configuration`` response.

    ``vpc`` True is a function placed in a VPC. False is the empty ``VpcConfig`` that
    Lambda reports for one that is not. None omits the key, the other shape a function
    that was never in a VPC comes back in.
    """
    payload: dict = {"Environment": {"Variables": env}} if env else {}
    if vpc:
        payload["VpcConfig"] = {"SubnetIds": [SUBNET_ID], "SecurityGroupIds": ["sg-0123456789abcdef0"], "VpcId": VPC_ID}
    elif vpc is False:
        payload["VpcConfig"] = {"SubnetIds": [], "SecurityGroupIds": [], "VpcId": ""}
    return payload


def healthy(**overrides: str) -> dict:
    """A function that took its update: in the VPC, with both ONTAP variables set."""
    env = {"ONTAP_MGMT_IP": SENTINEL_IP, "ONTAP_SECRET_NAME": SENTINEL_SECRET, "SVM_NAME": "svm-sentinel"}
    env.update(overrides)
    return deployed(True, **env)


def healthy_stack() -> dict[str, dict]:
    return {construct: healthy() for construct in EXPECTED}


def incident_stack() -> dict[str, dict]:
    """Two of the three failed to update and kept an empty VpcConfig and blank variables."""
    stack = healthy_stack()
    stack["ListSnapshotsFunction"] = deployed(False, ONTAP_MGMT_IP="", ONTAP_SECRET_NAME="", SVM_NAME="svm-sentinel")
    stack["ArpResponseFunction"] = deployed(None)
    return stack


class FakeAws:
    """Answer the preflight's read-only AWS calls with API-shaped payloads.

    The code's own ``--query`` is applied with ``jmespath`` and ``--output text`` is
    rendered the way the CLI renders it, so what is under test is the code's reading
    of the response and not the mock's agreement with the code. A verb that writes, or
    a call this class does not know, fails loudly instead of returning something.
    """

    ROOT = "amplify-fsxns3apamplifyportal-demo-sandbox-0123456789"
    AUTH = f"{ROOT}-auth179371D7-1X5N7VRRW3H34"
    DATA = f"{ROOT}-data7552DF31-Z4LHLM0GG5EN"
    API_ARN = "arn:aws:appsync:ap-northeast-1:111122223333:apis/abcdefghijklmnopqrstuvwxyz"

    def __init__(
        self,
        functions: dict[str, dict],
        api_env: dict[str, str] | None = None,
        *,
        logical_overrides: dict[str, str] | None = None,
        graphql_api: bool = True,
    ) -> None:
        self.functions = functions
        self.api_env = api_env or {}
        self.graphql_api = graphql_api
        self.calls: list[tuple[str, ...]] = []
        overrides = logical_overrides or {}
        # Construct id + eight uppercase hex digits, the form CloudFormation gives it.
        self.logical = {c: overrides.get(c, f"{c}{0x519A7386 + i:08X}") for i, c in enumerate(functions)}
        self.physical = {c: f"amplify-fsxns3apamplifypo-{c[:21]}-{i:012X}" for i, c in enumerate(functions)}

    @staticmethod
    def _options(tokens: tuple[str, ...]) -> dict[str, list[str]]:
        options: dict[str, list[str]] = {}
        flag = ""
        for token in tokens:
            if token.startswith("--"):
                flag = token
                options[flag] = []
            elif flag:
                options[flag].append(token)
        return options

    def _resources(self, stack: str) -> list[dict]:
        if stack != self.DATA:
            return [
                {
                    "ResourceType": "AWS::Cognito::UserPool",
                    "LogicalResourceId": "UserPool6BA7E5F2",
                    "PhysicalResourceId": "x",
                }
            ]
        items = [
            {
                "ResourceType": "AWS::Lambda::Function",
                "LogicalResourceId": self.logical[c],
                "PhysicalResourceId": self.physical[c],
            }
            for c in self.functions
        ]
        items.append(
            {
                "ResourceType": "AWS::IAM::Role",
                "LogicalResourceId": "ListSnapshotsLambdaRole0123ABCD",
                "PhysicalResourceId": "role",
            }
        )
        if self.graphql_api:
            items.append(
                {
                    "ResourceType": "AWS::AppSync::GraphQLApi",
                    "LogicalResourceId": "amplifyDataGraphQLAPI42A6FA33",
                    "PhysicalResourceId": self.API_ARN,
                }
            )
        return items

    def _payload(self, service: str, verb: str, opts: dict[str, list[str]]) -> object:
        if (service, verb) == ("cloudformation", "describe-stacks"):
            name = opts["--stack-name"][0]
            root_id = (
                None if name == self.ROOT else f"arn:aws:cloudformation:{REGION}:111122223333:stack/{self.ROOT}/uuid"
            )
            return {"Stacks": [{"StackName": name, "RootId": root_id}]}
        if (service, verb) == ("cloudformation", "list-stacks"):
            root_id = f"arn:aws:cloudformation:{REGION}:111122223333:stack/{self.ROOT}/uuid"
            return {
                "StackSummaries": [
                    {"StackName": self.ROOT, "RootId": None},
                    {"StackName": self.AUTH, "RootId": root_id},
                    {"StackName": self.DATA, "RootId": root_id},
                ]
            }
        if (service, verb) == ("cloudformation", "list-stack-resources"):
            return {"StackResourceSummaries": self._resources(opts["--stack-name"][0])}
        if (service, verb) == ("lambda", "get-function-configuration"):
            name = opts["--function-name"][0]
            for construct, physical in self.physical.items():
                if physical == name:
                    return self.functions[construct]
            raise RuntimeError("ResourceNotFoundException")
        if (service, verb) == ("appsync", "get-graphql-api-environment-variables"):
            assert opts["--api-id"] == ["abcdefghijklmnopqrstuvwxyz"], "an API id, not the ARN, is what the call takes"
            return {"environmentVariables": self.api_env}
        raise AssertionError(f"FakeAws does not know {service} {verb}")

    def __call__(self, *args: str) -> str:
        service, verb = args[0], args[1]
        assert verb.startswith(("describe-", "list-", "get-")), f"{service} {verb} is not a read"
        self.calls.append(args)
        opts = self._options(args[2:])
        payload = self._payload(service, verb, opts)
        if "--query" in opts:
            payload = jmespath.search(opts["--query"][0], payload)
        if opts.get("--output") == ["text"]:
            return "None" if payload is None else str(payload)
        return json.dumps(payload)


class TestParseBackend:
    """The expected function set is read from backend.ts, not from a list kept here."""

    REAL = Path(__file__).resolve().parents[2] / "solutions" / "amplify-portal" / "amplify" / "backend.ts"

    def test_the_vpc_spread_marks_the_expected_set(self) -> None:
        expected = preflight.expected_vpc_functions(make_backend(SYNTHETIC_BACKEND))
        assert [f.logical_id for f in expected] == list(EXPECTED)

    def test_both_constructor_layouts_are_read(self) -> None:
        parsed = {f.logical_id: f for f in preflight.parse_backend_functions(make_backend(SYNTHETIC_BACKEND))}
        assert set(parsed) == set(SYNTHETIC_BACKEND)
        assert parsed["ArpResponseFunction"].in_vpc  # one-line layout
        assert parsed["ListSnapshotsFunction"].in_vpc  # multi-line layout

    def test_a_function_with_ontap_vars_but_no_spread_is_not_expected(self) -> None:
        expected = {f.logical_id for f in preflight.expected_vpc_functions(make_backend(SYNTHETIC_BACKEND))}
        assert "PlatformDiscoveryFunction" not in expected
        assert "ListFilesFunction" not in expected

    def test_env_bindings_map_the_variable_to_the_config_key(self) -> None:
        parsed = {f.logical_id: f for f in preflight.parse_backend_functions(make_backend(SYNTHETIC_BACKEND))}
        assert parsed["ResourceMgmtFunction"].env == {
            "ONTAP_MGMT_IP": "ontapMgmtIp",
            "ONTAP_SECRET_NAME": "ontapSecretName",
            "S3_OBJECT_LOCK_BUCKET": "s3ObjectLockBucket",
        }

    def test_an_expression_other_than_a_bare_config_key_is_not_a_binding(self) -> None:
        parsed = {f.logical_id: f for f in preflight.parse_backend_functions(make_backend(SYNTHETIC_BACKEND))}
        assert "GROUP_AP_MAPPING" not in parsed["ListFilesFunction"].env

    def test_appsync_bindings_are_keyed_by_config_key(self) -> None:
        assert preflight.appsync_env_bindings(make_backend(SYNTHETIC_BACKEND)) == {
            "stateMachineArn": "STATE_MACHINE_ARN"
        }

    def test_a_spread_outside_a_parsed_function_is_an_error(self) -> None:
        """A construct this parser does not recognise must not shrink the set quietly."""
        source = (
            make_backend(SYNTHETIC_BACKEND)
            + '\nnew NodejsFunction(stack, "Other", {\n  ...(vpcConfig && { vpc: v }),\n});\n'
        )
        with pytest.raises(ValueError, match="vpcConfig"):
            preflight.expected_vpc_functions(source)

    def test_the_real_backend_has_a_nonempty_vpc_set_and_every_spread_is_accounted_for(self) -> None:
        source = self.REAL.read_text(encoding="utf-8")
        expected = preflight.expected_vpc_functions(source)
        assert expected
        assert len(expected) == source.count("...(vpcConfig &&")
        constructed = set(re.findall(r'new lambda\.Function\(\s*\w+,\s*"(\w+)"', source))
        assert {f.logical_id for f in expected} <= constructed
        # The function an earlier name-hint list missed.
        assert "ListSnapshotsFunction" in {f.logical_id for f in expected}

    def test_every_function_that_connects_to_ontap_is_in_the_vpc(self) -> None:
        """The property the old runtime filter checked, moved to where it can be stated.

        The check used to find ONTAP-facing functions by their environment, which
        meant a function that lost its variables stopped being checked. Expectation
        now comes from the source, so the source has to be where "connects to ONTAP"
        implies "is in the VPC".
        """
        parsed = preflight.parse_backend_functions(self.REAL.read_text(encoding="utf-8"))
        connecting = [f for f in parsed if set(preflight.ONTAP_CONNECT_VARS) <= set(f.env)]
        assert connecting
        assert [f.logical_id for f in connecting if not f.in_vpc] == []


class TestCheckLambdaVpc:
    """The VPC check is driven by the functions that should be in the VPC."""

    CONFIG = f'export const config = {{\n  vpcId: (process.env.AMPLIFY_PORTAL_VPC_ID || "{VPC_ID}").trim(),\n}};\n'
    CONFIG_NO_VPC = 'export const config = {\n  vpcId: (process.env.AMPLIFY_PORTAL_VPC_ID || "").trim(),\n};\n'

    @pytest.fixture(autouse=True)
    def _backend(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        path = tmp_path / "backend.ts"
        path.write_text(make_backend(SYNTHETIC_BACKEND), encoding="utf-8")
        # raising=False: the pre-fix module has no BACKEND_PATH, and the same tests
        # have to run against it to show what it did with the same stack.
        monkeypatch.setattr(preflight, "BACKEND_PATH", path, raising=False)
        monkeypatch.delenv("AMPLIFY_PORTAL_VPC_ID", raising=False)

    def _run(self, monkeypatch: pytest.MonkeyPatch, stack: dict[str, dict], config: str | None = None, **kw) -> tuple:
        fake = FakeAws(stack, **kw)
        monkeypatch.setattr(preflight, "aws", fake)
        return preflight.check_lambda_vpc(FakeAws.AUTH, REGION, config or self.CONFIG), fake

    def test_the_incident_shape_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Two of three functions failed to update and left both variables blank.

        The check selected functions by "both ONTAP variables are set", so a function
        that failed to update left the population it was checking and the one healthy
        function was reported as all of them.
        """
        results, fake = self._run(monkeypatch, incident_stack())

        failures = [r for r in results if r.status == preflight.FAIL]
        assert failures, "a stack where two of three expected functions failed to update passed"
        text = "\n".join(r.detail for r in failures)
        assert fake.logical["ListSnapshotsFunction"] in text
        assert fake.logical["ArpResponseFunction"] in text
        assert fake.logical["ResourceMgmtFunction"] not in text
        assert any(r.detail == "1 of 3 expected function(s) conform" for r in results)

    def test_all_conforming_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        results, _ = self._run(monkeypatch, healthy_stack())

        assert [r for r in results if r.status == preflight.FAIL] == []
        assert any(r.detail == "3 of 3 expected function(s) conform" for r in results)
        target = next(r for r in results if r.name == "ONTAP target")
        assert target.status == preflight.OK
        assert "3 of 3 expected function(s)" in target.detail

    def test_functions_outside_the_vpc_are_not_expected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stack = healthy_stack()
        stack["PlatformDiscoveryFunction"] = deployed(False, ONTAP_MGMT_IP=SENTINEL_IP)
        stack["ListFilesFunction"] = deployed(None, S3_AP_ALIAS=SENTINEL_ALIAS)

        results, _ = self._run(monkeypatch, stack)

        assert [r for r in results if r.status == preflight.FAIL] == []
        assert any(r.detail == "3 of 3 expected function(s) conform" for r in results)

    def test_empty_vpc_id_skips_without_calling_aws(self, monkeypatch: pytest.MonkeyPatch) -> None:
        results, fake = self._run(monkeypatch, incident_stack(), self.CONFIG_NO_VPC)

        assert [r.status for r in results] == [preflight.SKIP]
        assert fake.calls == []

    def test_vpc_id_from_the_environment_counts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The literal is empty; the variable is what the deploy will use."""
        monkeypatch.setenv("AMPLIFY_PORTAL_VPC_ID", VPC_ID)

        results, _ = self._run(monkeypatch, incident_stack(), self.CONFIG_NO_VPC)

        assert [r for r in results if r.status == preflight.FAIL]

    def test_an_expected_function_missing_from_the_stack_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stack = healthy_stack()
        del stack["ResourceMgmtFunction"]

        results, _ = self._run(monkeypatch, stack)

        assert any(r.detail == "2 of 3 expected function(s) conform" for r in results)
        missing = [r for r in results if r.status == preflight.FAIL and "ResourceMgmtFunction" in r.detail]
        assert missing
        assert "missing from the deployed stack" in missing[0].detail

    def test_logical_id_match_is_exact(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A different construct that shares a prefix is not the expected function."""
        overrides = {"ListSnapshotsFunction": "ListSnapshotsFunctionExtra1234ABCD"}

        results, _ = self._run(monkeypatch, healthy_stack(), logical_overrides=overrides)

        assert any(r.detail == "2 of 3 expected function(s) conform" for r in results)

    def test_vpc_without_the_secret_name_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stack = healthy_stack()
        stack["ResourceMgmtFunction"] = healthy(ONTAP_SECRET_NAME="")

        results, fake = self._run(monkeypatch, stack)

        failing = [
            r for r in results if r.status == preflight.FAIL and fake.logical["ResourceMgmtFunction"] in r.detail
        ]
        assert failing
        assert "ONTAP_SECRET_NAME" in failing[0].detail
        assert "ONTAP_MGMT_IP" not in failing[0].detail

    def test_failures_print_ids_never_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stack = incident_stack()
        stack["ResourceMgmtFunction"] = healthy(ONTAP_SECRET_NAME="")

        results, _ = self._run(monkeypatch, stack)

        output = "\n".join(f"{r.detail}\n{r.remedy}" for r in results if r.name == "VPC wiring")
        assert [s for s in SENTINELS if s in output] == [], "a configuration value reached the VPC wiring output"

    def test_unreadable_stack_still_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def explode(*args: str) -> str:
            raise RuntimeError("AccessDenied")

        monkeypatch.setattr(preflight, "aws", explode)

        results = preflight.check_lambda_vpc(FakeAws.AUTH, REGION, self.CONFIG)

        assert [r.status for r in results] == [preflight.FAIL]
        assert "cannot read functions" in results[0].detail

    def test_an_underivable_expected_set_fails_rather_than_skips(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(preflight, "BACKEND_PATH", tmp_path / "absent.ts", raising=False)
        monkeypatch.setattr(preflight, "aws", FakeAws(healthy_stack()))

        results = preflight.check_lambda_vpc(FakeAws.AUTH, REGION, self.CONFIG)

        assert [r.status for r in results] == [preflight.FAIL]
        assert "cannot derive" in results[0].detail

    def test_unknown_stack_skips(self) -> None:
        results = preflight.check_lambda_vpc(None, REGION, self.CONFIG)

        assert [r.status for r in results] == [preflight.SKIP]

    def test_targets_that_disagree_still_fail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stack = healthy_stack()
        stack["ArpResponseFunction"] = healthy(ONTAP_MGMT_IP="203.0.113.78")

        results, _ = self._run(monkeypatch, stack)

        target = next(r for r in results if r.name == "ONTAP target")
        assert target.status == preflight.FAIL

    def test_a_function_that_does_not_conform_is_left_out_of_the_target_comparison(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        results, _ = self._run(monkeypatch, incident_stack())

        target = next(r for r in results if r.name == "ONTAP target")
        assert target.status == preflight.SKIP
