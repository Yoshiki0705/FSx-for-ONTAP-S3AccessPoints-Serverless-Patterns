"""Tests for what an external portal caller may do.

The cases are chosen around the two ways this can fail open: an external caller being
treated as internal, and an unconfigured or misspelled mapping being read as a grant.
"""

from __future__ import annotations

import pytest

from shared.portal_external_policy import (
    DENIED_SHARE_LINK_MAX_EXPIRY_SECONDS,
    EXTERNAL_SCOPE,
    ai_denial_reason,
    is_external,
    share_link_denial_reason,
    share_link_expiry_ceiling,
)
from shared.portal_path_scope import CONFINED_SCOPE


def test_external_scope_matches_the_boundary_module():
    """One name for "outside the organisation", not two that can drift apart."""
    assert EXTERNAL_SCOPE == CONFINED_SCOPE == "external"


class TestIsExternal:
    def test_holding_the_scope(self):
        assert is_external(["viewer", "external"]) is True

    def test_not_holding_the_scope(self):
        assert is_external(["viewer", "internal"]) is False

    @pytest.mark.parametrize("groups", [None, []])
    def test_no_groups_is_not_external(self, groups):
        """A caller predating the scope axis holds nothing and keeps its behaviour."""
        assert is_external(groups) is False


class TestAiDenialReason:
    def test_internal_caller_is_unaffected_even_when_disabled(self):
        assert ai_denial_reason(["viewer"], ai_enabled=False) is None

    def test_caller_with_no_groups_is_unaffected(self):
        assert ai_denial_reason(None, ai_enabled=False) is None
        assert ai_denial_reason([], ai_enabled=False) is None

    def test_external_caller_denied_by_default(self):
        reason = ai_denial_reason(["viewer", "external"], ai_enabled=False)
        assert reason is not None
        assert "externalDefaults.aiEnabled" in reason

    def test_external_caller_allowed_when_enabled(self):
        assert ai_denial_reason(["viewer", "external"], ai_enabled=True) is None

    def test_an_external_admin_is_still_denied(self):
        """Role does not lift the scope restriction: the two axes are independent."""
        assert ai_denial_reason(["storage-admin", "external"], ai_enabled=False) is not None


class TestShareLinkDenialReason:
    MAPPING = {"viewer": False, "contributor": True}

    def test_internal_caller_is_unaffected(self):
        assert share_link_denial_reason(["viewer"], share_links_by_role={}) is None

    def test_caller_with_no_groups_is_unaffected(self):
        assert share_link_denial_reason(None, share_links_by_role={}) is None

    def test_empty_mapping_denies_every_external_caller(self):
        """The shipped default. An unconfigured deployment must not hand out links."""
        reason = share_link_denial_reason(["contributor", "external"], share_links_by_role={})
        assert reason is not None
        assert "externalDefaults.shareLinksByRole" in reason

    def test_missing_mapping_denies(self):
        assert share_link_denial_reason(["contributor", "external"], share_links_by_role=None) is not None

    def test_role_allowed(self):
        assert share_link_denial_reason(["contributor", "external"], share_links_by_role=self.MAPPING) is None

    def test_role_explicitly_denied(self):
        assert share_link_denial_reason(["viewer", "external"], share_links_by_role=self.MAPPING) is not None

    def test_unlisted_role_is_denied_not_allowed(self):
        """A typo in a role name has to fail closed, or the setting grants by accident."""
        assert share_link_denial_reason(["auditor", "external"], share_links_by_role=self.MAPPING) is not None

    def test_the_most_permissive_held_role_wins(self):
        """Roles combine as they do elsewhere: a contributor who is also a viewer is a
        contributor."""
        assert share_link_denial_reason(["viewer", "contributor", "external"], share_links_by_role=self.MAPPING) is None

    @pytest.mark.parametrize("truthy", ["true", 1, "yes"])
    def test_only_a_real_boolean_grants(self, truthy):
        """The mapping arrives from JSON in an environment variable.

        A string is what a hand-edited value looks like, and `bool("false")` is True.
        Anything that is not literally True is treated as not configured.
        """
        assert (
            share_link_denial_reason(["contributor", "external"], share_links_by_role={"contributor": truthy})
            is not None
        )

    def test_the_external_scope_itself_is_not_a_role(self):
        """`external` appearing in the mapping must not grant by matching itself."""
        assert share_link_denial_reason(["external"], share_links_by_role={"viewer": True}) is not None

    def test_the_scope_cannot_be_used_as_a_role_key(self):
        """The reading somebody would naturally write, which must not silently work.

        `{"external": true}` looks like "external users may share links". If any held
        group were matched, it would grant every outside caller at once and cancel the
        per-role distinction the setting exists to draw. It grants nothing, and
        `backend.ts` refuses the key at synth so the intent is not lost in silence.
        """
        assert share_link_denial_reason(["viewer", "external"], share_links_by_role={"external": True}) is not None

    def test_a_custom_group_cannot_be_used_as_a_role_key(self):
        """Per-team groups belong in the path prefixes, not in a role setting."""
        assert share_link_denial_reason(["team-a", "external"], share_links_by_role={"team-a": True}) is not None


class TestShareLinkExpiryCeiling:
    """The download path, where refusing would remove retrieving the file."""

    def test_internal_caller_has_no_ceiling(self):
        assert share_link_expiry_ceiling(["viewer"], share_links_by_role={}) is None

    def test_caller_with_no_groups_has_no_ceiling(self):
        assert share_link_expiry_ceiling(None, share_links_by_role={}) is None

    def test_allowed_external_role_has_no_ceiling(self):
        assert share_link_expiry_ceiling(["contributor", "external"], share_links_by_role={"contributor": True}) is None

    def test_denied_external_role_is_capped(self):
        ceiling = share_link_expiry_ceiling(["viewer", "external"], share_links_by_role={})
        assert ceiling == DENIED_SHARE_LINK_MAX_EXPIRY_SECONDS

    def test_the_ceiling_still_permits_preview_and_download(self):
        """The point of capping rather than refusing.

        The portal previews at 300s and downloads at 60s. A ceiling below either would
        take away retrieving the file, which is what an outside member was invited to
        do.
        """
        assert DENIED_SHARE_LINK_MAX_EXPIRY_SECONDS >= 300
