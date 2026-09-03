"""Tests for demo-account provisioning.

Only what this script owns is exercised: password generation against a policy,
stack-name parsing, and the role descriptions. Group semantics belong to
`grant_portal_roles.py` and are tested there; duplicating them here would assert that
two copies agree rather than that either is right.

The Cognito calls are not mocked. They have to run against a deployed pool, and
asserting on a mock would prove the mock matches the code rather than that the code
matches Cognito.

The password tests matter more than they look. `RequireSymbols` is the requirement
people forget, and the failure arrives as `InvalidPasswordException` only after the
user has been created -- leaving an account that exists and cannot sign in.
"""

from __future__ import annotations

import importlib.util
import string
import sys
from pathlib import Path

import grant_portal_roles
import pytest

MODULE_PATH = Path(__file__).resolve().parent.parent / "portal_provision_demo_user.py"
_spec = importlib.util.spec_from_file_location("portal_provision_demo_user", MODULE_PATH)
assert _spec and _spec.loader
provision = importlib.util.module_from_spec(_spec)
sys.modules["portal_provision_demo_user"] = provision
_spec.loader.exec_module(provision)

FULL_POLICY = {
    "MinimumLength": 8,
    "RequireUppercase": True,
    "RequireLowercase": True,
    "RequireNumbers": True,
    "RequireSymbols": True,
}


class TestGeneratePassword:
    """Generating a password the pool will accept."""

    def test_satisfies_every_required_class(self) -> None:
        for _ in range(50):
            password = provision.generate_password(FULL_POLICY)
            assert any(c in string.ascii_uppercase for c in password)
            assert any(c in string.ascii_lowercase for c in password)
            assert any(c in string.digits for c in password)
            assert any(c in provision.SYMBOL_ALPHABET for c in password)

    def test_length_floor_is_sixteen_even_when_policy_allows_eight(self) -> None:
        # The policy minimum is a floor for the pool, not a target for a credential
        # that gets pasted around during a demo.
        assert len(provision.generate_password(FULL_POLICY)) >= 16

    def test_respects_a_longer_policy_minimum(self) -> None:
        assert len(provision.generate_password({**FULL_POLICY, "MinimumLength": 24})) >= 24

    def test_omits_classes_the_policy_does_not_require(self) -> None:
        policy = {
            "MinimumLength": 20,
            "RequireUppercase": False,
            "RequireLowercase": True,
            "RequireNumbers": False,
            "RequireSymbols": False,
        }
        password = provision.generate_password(policy)
        assert password
        assert all(c in string.ascii_lowercase for c in password)

    def test_avoids_characters_that_break_a_shell_or_a_paste(self) -> None:
        for _ in range(50):
            password = provision.generate_password(FULL_POLICY)
            for hostile in ("'", '"', "\\", "`", "$", " "):
                assert hostile not in password

    def test_empty_policy_still_produces_a_password(self) -> None:
        # describe-user-pool can answer with an empty policy object; generating nothing
        # here would fail later, at admin-set-user-password.
        assert len(provision.generate_password({})) >= 16


class TestSandboxIdentifier:
    """Reading the sandbox identifier out of a stack name."""

    def test_reads_identifier_from_a_nested_stack(self) -> None:
        name = "amplify-fsxns3apamplifyportal-demo-sandbox-753443151c-auth179371D7-ABC"
        assert provision.sandbox_identifier(name) == "demo"

    def test_reads_identifier_from_a_root_stack(self) -> None:
        assert provision.sandbox_identifier("amplify-fsxns3apamplifyportal-yoshiki-sandbox-ae70db2b34") == "yoshiki"

    @pytest.mark.parametrize("name", ["", "some-other-stack", "amplify-branch-main"])
    def test_non_sandbox_names_are_reported_not_guessed(self, name: str) -> None:
        # Returning something that cannot equal a real --expected-sandbox value is the
        # point: a non-sandbox deployment must not pass the comparison by accident.
        assert provision.sandbox_identifier(name) == "(not a sandbox stack)"


class TestRoleDescriptions:
    """Every role has to have its effect stated before it is granted."""

    def test_describes_every_role_the_portal_declares(self) -> None:
        # Read from portal-groups.ts through grant_portal_roles, so a role added there
        # without a description here fails rather than being granted silently.
        roles, _ = grant_portal_roles.declared_groups()
        assert set(roles) == set(provision.ROLE_EFFECT)

    def test_scopes_are_not_described_as_roles(self) -> None:
        _, scopes = grant_portal_roles.declared_groups()
        for scope in scopes:
            assert provision.describe_role(scope) is None

    def test_describe_role_returns_none_for_an_unknown_group(self) -> None:
        assert provision.describe_role("not-a-group") is None

    def test_storage_admin_effects_are_stated(self) -> None:
        # The operator reads these before granting; an empty list would make the
        # warning block print a heading and nothing under it.
        assert provision.STORAGE_ADMIN_IRREVERSIBLE
        assert all(effect.strip() for effect in provision.STORAGE_ADMIN_IRREVERSIBLE)
