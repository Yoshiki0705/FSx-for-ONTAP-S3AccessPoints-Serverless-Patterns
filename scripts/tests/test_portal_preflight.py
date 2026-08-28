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


class TestResult:
    """A skipped check must not read as a passing one."""

    def test_statuses_are_distinct(self) -> None:
        assert preflight.OK != preflight.SKIP != preflight.FAIL

    def test_remedy_is_optional(self) -> None:
        result = preflight.Result("name", preflight.OK, "detail")
        assert result.remedy == ""
