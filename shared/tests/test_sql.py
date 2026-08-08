"""Tests for SQL literal rendering.

The property that matters is not "quotes are doubled" but "no input can end the
literal early". A unit test with a handful of payloads proves the payloads it
lists; hypothesis is here because the interesting input is the one nobody thought
of. The parser check below is the real assertion: it walks the rendered literal
the way Trino does and requires that it closes exactly once, at the end.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from shared.sql import like_operand, sql_literal


def closes_once_at_the_end(rendered: str) -> bool:
    """Whether a rendered literal terminates only at its final character.

    Mirrors how a SQL parser reads a single-quoted literal: a doubled quote is a
    literal quote and does not end the string; a lone quote ends it. If that
    happens before the last character, the remainder would be parsed as SQL.
    """
    assert rendered.startswith("'") and rendered.endswith("'")
    index = 1
    end = len(rendered) - 1
    while index < end:
        if rendered[index] == "'":
            if index + 1 < end and rendered[index + 1] == "'":
                index += 2  # escaped quote, still inside the literal
                continue
            return False  # literal ended early
        index += 1
    return True


class TestSqlLiteral:
    @pytest.mark.parametrize(
        "payload",
        [
            "PUMP-01",
            "O'Brien",
            "' OR '1'='1",
            "'; DROP TABLE scada_readings; --",
            "x' UNION SELECT password FROM users --",
            "''''",
            "'",
            "",
            "multi\nline",
            "日本語の設備名",
            "tab\tand\\backslash",
        ],
    )
    def test_payloads_cannot_end_the_literal(self, payload: str) -> None:
        assert closes_once_at_the_end(sql_literal(payload))

    def test_quotes_are_doubled(self) -> None:
        assert sql_literal("O'Brien") == "'O''Brien'"

    def test_plain_value_is_just_quoted(self) -> None:
        assert sql_literal("PUMP-01") == "'PUMP-01'"

    def test_backslash_is_not_an_escape_character(self) -> None:
        r"""Trino does not treat `\` as an escape in string literals.

        Escaping it, as one would for MySQL, would corrupt the value instead of
        protecting it.
        """
        assert sql_literal("a\\b") == "'a\\b'"

    def test_non_strings_are_coerced(self) -> None:
        """A value read from JSON may be an int or None, and must not raise."""
        assert sql_literal(42) == "'42'"
        assert sql_literal(None) == "'None'"

    @settings(max_examples=300, deadline=None)
    @given(st.text())
    def test_no_text_can_end_the_literal_early(self, value: str) -> None:
        assert closes_once_at_the_end(sql_literal(value))

    @settings(max_examples=200, deadline=None)
    @given(st.text(alphabet="'\"\\;-- \n%_aA1", min_size=0, max_size=40))
    def test_metacharacter_soup_cannot_end_the_literal_early(self, value: str) -> None:
        assert closes_once_at_the_end(sql_literal(value))


class TestLikeOperand:
    def test_wildcards_are_escaped(self) -> None:
        assert like_operand("100%_done") == "100\\%\\_done"

    def test_backslash_is_escaped_first(self) -> None:
        r"""Escaping `%` before `\` would double-escape the inserted backslashes."""
        assert like_operand("a\\b") == "a\\\\b"

    def test_plain_value_is_unchanged(self) -> None:
        assert like_operand("PUMP-01") == "PUMP-01"

    @settings(max_examples=200, deadline=None)
    @given(st.text())
    def test_result_survives_literal_rendering(self, value: str) -> None:
        """A LIKE operand still has to be a safe literal after escaping."""
        assert closes_once_at_the_end(sql_literal(like_operand(value)))

    @settings(max_examples=200, deadline=None)
    @given(st.text(alphabet="abc%_\\", min_size=0, max_size=20))
    def test_no_bare_wildcard_remains(self, value: str) -> None:
        escaped = like_operand(value)
        index = 0
        while index < len(escaped):
            char = escaped[index]
            if char == "\\":
                index += 2  # the escape consumes the next character
                continue
            assert char not in "%_", f"unescaped wildcard in {escaped!r}"
            index += 1
