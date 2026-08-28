"""Tests for the portal's path-scope boundary.

This is authorization, so the cases are written from the attacker's side where that
applies: the prefix check is the one that stops a caller naming another team's object
directly, and the `..` and separator rules exist so a key cannot read as one prefix to
the comparison and another to a person.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from shared.portal_path_scope import MAX_KEY_BYTES, allowed_prefixes, reject_key

MAPPING = {
    "team-a": ["teams/a/"],
    "team-b": ["teams/b/", "shared/b/"],
    "no-prefixes": [],
}


class TestAllowedPrefixes:
    """An empty result means unrestricted, which is four different situations."""

    def test_no_mapping_configured_is_unrestricted(self):
        assert allowed_prefixes(["team-a"], {}) == []
        assert allowed_prefixes(["team-a"], None) == []

    def test_no_groups_is_unrestricted(self):
        assert allowed_prefixes([], MAPPING) == []
        assert allowed_prefixes(None, MAPPING) == []

    def test_storage_admin_bypasses(self):
        """The bypass has to beat a group that does carry prefixes."""
        assert allowed_prefixes(["team-a", "storage-admin"], MAPPING) == []

    def test_an_external_admin_is_confined(self):
        """The exemption is conditional, which is what makes the two axes independent.

        Without this, granting any administrative capability to somebody outside the
        organisation would have handed them the whole volume as a side effect.
        """
        assert allowed_prefixes(["team-a", "storage-admin", "external"], MAPPING) == ["teams/a/"]

    def test_an_internal_admin_is_still_unconfined(self):
        assert allowed_prefixes(["team-a", "storage-admin", "internal"], MAPPING) == []

    def test_an_admin_with_neither_scope_is_unchanged(self):
        """Every administrator in a deployed pool predates the scope axis.

        The condition is the absence of `external` rather than the presence of
        `internal` precisely so that this case keeps its previous behaviour. Requiring
        `internal` would confine every existing administrator the moment it shipped.
        """
        assert allowed_prefixes(["team-a", "storage-admin"], MAPPING) == []

    def test_an_external_caller_with_no_admin_role_is_confined_as_before(self):
        assert allowed_prefixes(["team-a", "external"], MAPPING) == ["teams/a/"]

    def test_a_group_with_no_prefixes_is_unrestricted(self):
        assert allowed_prefixes(["no-prefixes"], MAPPING) == []

    def test_an_unknown_group_is_unrestricted(self):
        assert allowed_prefixes(["not-in-the-mapping"], MAPPING) == []

    def test_prefixes_are_collected_sorted_and_deduplicated(self):
        assert allowed_prefixes(["team-b"], MAPPING) == ["shared/b/", "teams/b/"]
        assert allowed_prefixes(["team-a", "team-b"], MAPPING) == [
            "shared/b/",
            "teams/a/",
            "teams/b/",
        ]

    def test_a_prefix_in_two_groups_appears_once(self):
        mapping = {"one": ["same/"], "two": ["same/"]}
        assert allowed_prefixes(["one", "two"], mapping) == ["same/"]


class TestRejectKeyShape:
    """Refusals that do not depend on who is asking."""

    def test_an_empty_key_is_refused(self):
        assert reject_key("", [], field="key") == {"error": "key is required"}

    def test_the_field_name_is_reported(self):
        assert "sourceKey" in reject_key("", [], field="sourceKey")["error"]

    def test_a_key_over_the_s3_limit_is_refused(self):
        assert reject_key("a" * (MAX_KEY_BYTES + 1), [], field="key") is not None
        assert reject_key("a" * MAX_KEY_BYTES, [], field="key") is None

    def test_the_limit_counts_bytes_not_characters(self):
        """A multi-byte name must not slip past a character-based count."""
        key = "\u3042" * ((MAX_KEY_BYTES // 3) + 1)  # 3 bytes each in UTF-8
        assert len(key) < MAX_KEY_BYTES
        assert reject_key(key, [], field="key") is not None

    def test_a_leading_separator_is_refused(self):
        assert reject_key("/a/b.txt", [], field="key") is not None

    def test_an_empty_path_segment_is_refused(self):
        assert reject_key("a//b.txt", [], field="key") is not None

    def test_a_parent_segment_is_refused(self):
        assert reject_key("teams/a/../b/x.txt", [], field="key") is not None

    def test_a_dotdot_inside_a_name_is_not_a_parent_segment(self):
        """Only a whole segment counts; `..config` is an ordinary file name."""
        assert reject_key("teams/a/..config", [], field="key") is None

    def test_control_characters_are_refused(self):
        assert reject_key("a/\x00b", [], field="key") is not None
        assert reject_key("a/\nb", [], field="key") is not None
        assert reject_key("a/\x7fb", [], field="key") is not None

    def test_an_ordinary_key_is_accepted(self):
        assert reject_key("teams/a/report.pdf", [], field="key") is None


class TestRejectKeyScope:
    """The boundary itself."""

    def test_no_prefixes_means_no_restriction(self):
        assert reject_key("anywhere/at/all.txt", [], field="key") is None

    def test_a_key_inside_an_allowed_prefix_is_accepted(self):
        assert reject_key("teams/a/x.txt", ["teams/a/"], field="key") is None

    def test_a_key_outside_every_allowed_prefix_is_refused(self):
        result = reject_key("teams/b/x.txt", ["teams/a/"], field="key")
        assert result is not None
        assert "outside the prefixes" in result["error"]

    def test_the_refusal_does_not_disclose_other_prefixes(self):
        """Naming them would tell one tenant what the others are called."""
        result = reject_key("teams/b/x.txt", ["teams/a/", "secret-project/"], field="key")
        assert "secret-project" not in result["error"]
        assert "teams/a/" not in result["error"]

    def test_any_one_of_several_prefixes_is_enough(self):
        allowed = ["shared/b/", "teams/b/"]
        assert reject_key("shared/b/x.txt", allowed, field="key") is None
        assert reject_key("teams/b/x.txt", allowed, field="key") is None

    def test_a_prefix_match_is_literal_not_a_path_match(self):
        """`teams/ab/` starts with `teams/a` as text, so the configured prefixes
        carry their trailing separator and this key is refused by it."""
        assert reject_key("teams/ab/x.txt", ["teams/a/"], field="key") is not None


class TestRejectKeyProperties:
    @given(
        st.text(
            alphabet=st.characters(min_codepoint=32, max_codepoint=126, blacklist_characters="/"),
            min_size=1,
            max_size=40,
        )
    )
    def test_an_accepted_key_always_sits_under_an_allowed_prefix(self, tail: str):
        """The one invariant worth stating: acceptance implies containment.

        Generated over the segment after the prefix, so both outcomes occur -- the
        prefix is prepended for half the cases and replaced for the other half.
        """
        allowed = ["teams/a/"]
        inside = f"teams/a/{tail}"
        outside = f"teams/b/{tail}"
        if reject_key(inside, allowed, field="key") is None:
            assert inside.startswith(allowed[0])
        assert reject_key(outside, allowed, field="key") is not None

    @given(st.lists(st.sampled_from(sorted(MAPPING)), max_size=4))
    def test_prefixes_are_always_sorted_and_unique(self, groups: list[str]):
        result = allowed_prefixes(groups, MAPPING)
        assert result == sorted(result)
        assert len(result) == len(set(result))
