"""D1 must agree with markdown-it on whether a `**` renders.

Adapted from the Adoption Playbook's `scripts/tests/test_ai_style_strong_fixtures.py`. The fixture
`fixtures/ai_style_strong.json` is vendored byte-identical from the Playbook, where markdown-it
produced the expected values through a Node script. That regenerator is not ported here, so the
generator-path check is relaxed to the renderer name only.

The case that motivated the rule reads correctly in the source and does not render:
`は**「X」**で` leaves four literal asterisks, because a `**` between a Japanese particle and a
bracket is neither left- nor right-flanking. Nobody notices it in an editor, which is why it is
checked against a renderer rather than against intuition.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from ai_style_rules import unrendered_strong

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "ai_style_strong.json"
SYNTHETIC = "上は**「自分の構成」**で引く。次は**自分の構成**で引く。"


class StrongFixturesAgreeWithMarkdownIt(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.cases = cls.data["cases"]

    def test_every_case_matches_the_renderer(self) -> None:
        for case in self.cases:
            with self.subTest(case=case["id"]):
                self.assertEqual(
                    len(unrendered_strong(case["markdown"])),
                    case["literal_double_stars"],
                    f"{case['id']}: Python and markdown-it disagree on {case['markdown']!r}",
                )

    def test_the_fixture_can_tell_the_two_outcomes_apart(self) -> None:
        """An all-zero fixture would pass against an engine that never reports anything."""
        self.assertGreaterEqual(len(self.cases), 25)
        values = {case["literal_double_stars"] for case in self.cases}
        self.assertIn(0, values)
        self.assertTrue(any(value > 0 for value in values))

    def test_the_motivating_sentence_is_present_and_broken(self) -> None:
        matching = [case for case in self.cases if SYNTHETIC in case["markdown"]]
        self.assertTrue(matching, "the bracketed-bold sentence is missing from the fixture")
        self.assertGreaterEqual(matching[0]["literal_double_stars"], 1)

    def test_the_fixture_names_its_generator(self) -> None:
        # The Node regenerator named in `generated_by` lives in the Playbook and is not ported, so
        # only the renderer name is checked here.
        self.assertTrue(self.data["renderer"].startswith("markdown-it "))


if __name__ == "__main__":
    unittest.main()
