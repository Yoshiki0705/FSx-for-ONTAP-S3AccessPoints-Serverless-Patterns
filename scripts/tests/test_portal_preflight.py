"""Tests for the portal preflight checks.

Only the pure parts are exercised here: config parsing, stack-name reading, and
the verdict each comparison produces. The AWS-facing calls are the part that has
to be run against a deployed sandbox, and asserting on a mock of them would
prove that the mock matches the code rather than that the code matches AWS.
"""

from __future__ import annotations

import importlib.util
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
