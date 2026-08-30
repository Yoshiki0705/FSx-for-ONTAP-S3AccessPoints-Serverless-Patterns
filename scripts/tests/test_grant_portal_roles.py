"""Tests for the role-granting migration script.

The planning is separated from the API calls so the decisions can be exercised against a
pool that does not exist. What is asserted here is every branch somebody has to be able
to audit before it touches real accounts: what is refused, what is reported as already
done, and what the script declines to decide on the operator's behalf.

The refusals matter more than the grants. A script that quietly did something reasonable
with a malformed line, a group the pool does not have, or two conflicting scopes would
hand out permissions nobody asked for and report success.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from scripts.grant_portal_roles import (
    ALREADY,
    GRANT,
    REFUSED,
    Assignment,
    declared_groups,
    parse_assignment,
    plan,
    read_assignment_file,
)

ROLES = ["viewer", "contributor", "storage-admin", "auditor"]
SCOPES = ["internal", "external"]
IN_POOL = set(ROLES) | set(SCOPES)


def outcomes(actions: list, outcome: str) -> list[tuple[str, str]]:
    """The (user, group) pairs with a given outcome."""
    return [(a.user, a.group) for a in actions if a.outcome == outcome]


class TestDeclaredGroups:
    def test_read_from_the_typescript_declaration(self):
        """Read from source so the script cannot offer a group the deployment lacks."""
        roles, scopes = declared_groups()
        assert roles == ROLES
        assert scopes == SCOPES


class TestParseAssignment:
    def test_a_role_and_a_scope(self):
        assert parse_assignment("a@example.com=contributor,internal") == Assignment(
            "a@example.com", ("contributor", "internal")
        )

    def test_whitespace_is_tolerated(self):
        assert parse_assignment(" a@example.com = viewer , external ") == Assignment(
            "a@example.com", ("viewer", "external")
        )

    @pytest.mark.parametrize("text", ["a@example.com", "=viewer", "a@example.com=", "a@example.com=,"])
    def test_a_malformed_line_raises(self, text):
        """Raised rather than skipped: a dropped line reads as a user granted nothing."""
        with pytest.raises(argparse.ArgumentTypeError):
            parse_assignment(text)


class TestReadAssignmentFile:
    def test_comments_and_blank_lines_are_ignored(self, tmp_path: Path):
        path = tmp_path / "roles.txt"
        path.write_text(
            "# who gets what\n\na@example.com=viewer,internal\nb@example.net=contributor,external  # a partner\n"
        )
        assert read_assignment_file(path) == [
            Assignment("a@example.com", ("viewer", "internal")),
            Assignment("b@example.net", ("contributor", "external")),
        ]

    def test_a_bad_line_names_the_line_number(self, tmp_path: Path):
        path = tmp_path / "roles.txt"
        path.write_text("a@example.com=viewer,internal\nnonsense\n")
        with pytest.raises(SystemExit) as error:
            read_assignment_file(path)
        assert "roles.txt:2" in str(error.value)


class TestPlan:
    def build(self, assignments, *, membership=None, in_pool=IN_POOL):
        return plan(
            assignments,
            existing_groups=in_pool,
            current_membership=membership or {},
            roles=ROLES,
            scopes=SCOPES,
        )

    def test_a_new_grant(self):
        actions = self.build([Assignment("a@example.com", ("viewer", "internal"))])
        assert outcomes(actions, GRANT) == [
            ("a@example.com", "viewer"),
            ("a@example.com", "internal"),
        ]
        assert outcomes(actions, REFUSED) == []

    def test_running_twice_grants_nothing_the_second_time(self):
        """Idempotent, so adding one person later does not need a record of the first run."""
        actions = self.build(
            [Assignment("a@example.com", ("viewer", "internal"))],
            membership={"a@example.com": {"viewer", "internal"}},
        )
        assert outcomes(actions, GRANT) == []
        assert len(outcomes(actions, ALREADY)) == 2

    def test_a_partially_granted_user_gets_the_remainder(self):
        actions = self.build(
            [Assignment("a@example.com", ("contributor", "external"))],
            membership={"a@example.com": {"external"}},
        )
        assert outcomes(actions, GRANT) == [("a@example.com", "contributor")]
        assert outcomes(actions, ALREADY) == [("a@example.com", "external")]

    def test_an_unknown_group_is_refused(self):
        actions = self.build([Assignment("a@example.com", ("admin", "internal"))])
        assert ("a@example.com", "admin") in outcomes(actions, REFUSED)

    def test_a_group_missing_from_the_pool_is_refused_not_created(self):
        """Creating it here would leave a group `defineAuth` does not own.

        The drift check would then find a group nobody declared, and the reason it exists
        would be in somebody's shell history.
        """
        actions = self.build(
            [Assignment("a@example.com", ("auditor", "internal"))],
            in_pool=IN_POOL - {"auditor"},
        )
        refused = [a for a in actions if a.outcome == REFUSED and a.group == "auditor"]
        assert refused
        assert "Deploy first" in refused[0].reason

    def test_two_roles_are_refused(self):
        """Not corrected. Which role somebody should hold is not this script's decision."""
        actions = self.build([Assignment("a@example.com", ("viewer", "contributor", "internal"))])
        assert any("more than one role" in a.reason for a in actions if a.outcome == REFUSED)

    def test_both_scopes_are_refused(self):
        """`internal` does not cancel `external`, so holding both is not a middle ground."""
        actions = self.build([Assignment("a@example.com", ("viewer", "internal", "external"))])
        assert any("both scopes" in a.reason for a in actions if a.outcome == REFUSED)

    def test_no_scope_is_refused(self):
        """Absent means internal, which is the wrong default to reach by omission."""
        actions = self.build([Assignment("a@example.com", ("viewer",))])
        assert any("no scope" in a.reason for a in actions if a.outcome == REFUSED)

    def test_a_scope_already_held_satisfies_the_scope_requirement(self):
        actions = self.build(
            [Assignment("a@example.com", ("contributor",))],
            membership={"a@example.com": {"external"}},
        )
        assert not any("no scope" in a.reason for a in actions if a.outcome == REFUSED)

    def test_an_external_administrator_is_allowed_and_confined_elsewhere(self):
        """Not refused here.

        It is a real configuration -- an outside member who administers their own
        exchange area -- and the confinement happens at the path boundary, which keeps
        the exemption only for an administrator without the external scope.
        """
        actions = self.build([Assignment("a@example.net", ("storage-admin", "external"))])
        assert outcomes(actions, REFUSED) == []
        assert len(outcomes(actions, GRANT)) == 2
