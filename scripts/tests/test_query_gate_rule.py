"""The `enabled` / `isPending` rule in check_portal_drift.py.

The rule exists because the qtree panel shipped a spinner that never cleared: it gated
its query on a chosen volume, read `isPending` as loading, and rendered the spinner
instead of the volume dropdown -- so nothing could ever choose a volume and no request
was ever made. tsc, the linter and every other check here passed.

The tests below are in two halves, and the second half is the larger one. Three
successive versions of the source reader silently stopped seeing code, and a reader that
sees nothing reports a clean tree, which is the same failure the rule is meant to
prevent one level up. Each masking case here is a shape that actually broke it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import check_portal_drift as drift  # noqa: E402


@pytest.fixture
def portal(tmp_path, monkeypatch):
    """Point the checker at a throwaway portal tree and return its src directory."""
    src = tmp_path / "src"
    src.mkdir()
    monkeypatch.setattr(drift, "PORTAL", tmp_path)
    return src


def findings_for(portal: Path, body: str, name: str = "Panel.tsx") -> list[drift.Finding]:
    (portal / name).write_text(body, encoding="utf-8")
    return drift.check_query_gate_reads()


# The shape that shipped, reduced to the two lines that matter.
GATED_PENDING = """
export function Panel() {
  const {
    data: rows = [],
    isPending: loading,
  } = useQuery({
    queryKey: ["rows", volume],
    enabled: !!volume,
    queryFn: () => fetchRows(volume),
  });
  if (loading) return <Spinner />;
  return <VolumePicker onSelect={setVolume} />;
}
"""


class TestTheRuleFires:
    def test_gated_query_read_as_pending_is_a_finding(self, portal):
        findings = findings_for(portal, GATED_PENDING)
        assert len(findings) == 1, findings
        assert findings[0].rule == "query-gate-read"
        # The line of the flag, not of the destructuring that contains it: the marker
        # has to have one obvious place to go, and an author reads the reported line.
        assert findings[0].location.endswith(":5"), findings[0].location

    def test_the_object_form_is_seen_too(self, portal):
        """`const q = useQuery(...)` then `q.isPending` somewhere else in the file."""
        findings = findings_for(
            portal,
            """
            export function Panel() {
              const rows = useQuery({
                queryKey: ["rows"],
                enabled: !!volume,
                queryFn: fetchRows,
              });
              return rows.isPending ? <Spinner /> : <Table rows={rows.data} />;
            }
            """,
        )
        assert len(findings) == 1, findings
        assert findings[0].location.endswith(":8"), findings[0].location

    def test_destructured_status_is_seen(self, portal):
        """`status` is the same flag spelled out, and is pending while disabled."""
        findings = findings_for(
            portal,
            """
            export function Panel() {
              const { data, status } = useQuery({
                queryKey: ["rows"],
                enabled: !!volume,
                queryFn: fetchRows,
              });
              return status === "pending" ? <Spinner /> : <Table rows={data} />;
            }
            """,
        )
        assert findings, "a gated query read through `status` is the same defect"


class TestTheRuleStaysQuiet:
    def test_isfetching_on_a_gated_query_is_fine(self, portal):
        """The fix. False while the query is disabled, which is what loading wants."""
        assert not findings_for(portal, GATED_PENDING.replace("isPending", "isFetching"))

    def test_ungated_pending_is_fine(self, portal):
        """Without `enabled` the query runs on mount, so pending means pending."""
        body = "\n".join(line for line in GATED_PENDING.splitlines() if "enabled:" not in line)
        assert not findings_for(portal, body)

    def test_enabled_in_a_comment_is_not_the_option(self, portal):
        body = GATED_PENDING.replace("enabled: !!volume,", "// enabled: !!volume,")
        assert not findings_for(portal, body)

    @pytest.mark.parametrize(
        "marker",
        [
            "// query-gate-checked: the caller checks the same condition",
            "{/* query-gate-checked: rendered only inside the same condition */}",
        ],
    )
    def test_a_marked_read_is_accepted(self, portal, marker):
        """Both comment forms. Inside JSX `//` would render as text, so `/* */` has to
        work -- accepting only `//` made the rule unsatisfiable on markup reads."""
        body = GATED_PENDING.replace("    isPending: loading,", f"    {marker}\n    isPending: loading,")
        assert not findings_for(portal, body)

    def test_a_multi_line_marker_is_accepted(self, portal):
        """The lookback follows the comment block up. One line of it missed a marker
        written on the first line of a two-line comment."""
        body = GATED_PENDING.replace(
            "    isPending: loading,",
            "    // query-gate-checked: the reason for this is long enough that it\n"
            "    // does not fit on one line, which is the usual case.\n"
            "    isPending: loading,",
        )
        assert not findings_for(portal, body)

    def test_the_marker_needs_a_reason(self, portal):
        """A bare marker is a mute switch, so it does not count as one."""
        body = GATED_PENDING.replace("    isPending: loading,", "    // query-gate-checked:\n    isPending: loading,")
        assert findings_for(portal, body)


class TestTheReaderKeepsSeeing:
    """Shapes that made earlier versions of the reader blank real code.

    Each of these produced a passing run over a file the reader could no longer see.
    """

    @pytest.mark.parametrize(
        ("label", "hazard"),
        [
            # An apostrophe in prose opened a string that ran to end of file.
            ("apostrophe in a comment", "  // the panel's own state is not read here\n"),
            # A backtick inside a regex opened a template literal that did the same.
            ("backtick in a regex", "  const parts = text.split(/(`[^`]+`)/g);\n"),
            # `/>` after `}` looks exactly like the start of a regex.
            ("jsx self-closing tag", "  const icon = <Dot value={v} />;\n"),
            ("jsx closing tag", "  const label = <span>{v}</span>;\n"),
            # A brace inside a string would unbalance the matcher.
            ("brace in a string", '  const tpl = "{ not code }";\n'),
            ("division", "  const half = total / 2;\n"),
            ("block comment", "  /* a note { with a brace } */\n"),
        ],
    )
    def test_a_hazard_does_not_blind_the_reader(self, portal, label, hazard):
        body = GATED_PENDING.replace("export function Panel() {\n", f"export function Panel() {{\n{hazard}")
        findings = findings_for(portal, body)
        assert len(findings) == 1, f"{label}: expected the finding to survive, got {findings}"
        assert "brackets do not balance" not in findings[0].detail, label

    def test_a_blinded_reader_reports_itself(self, portal, monkeypatch):
        """The self-check, forced by breaking the masker.

        Every shape that actually broke it is handled now, and the self-check exists for
        the shape nobody has hit yet -- so there is no source text that triggers it. The
        masker is replaced with one that drops a bracket instead.
        """
        monkeypatch.setattr(drift, "_blank_strings_and_comments", lambda source: source.replace(")", " ", 1))
        findings = findings_for(portal, GATED_PENDING)
        assert len(findings) == 1, findings
        assert "brackets do not balance" in findings[0].detail

    def test_the_soundness_test_knows_both_answers(self):
        """What the invariant does and does not cover.

        It detects a loss that leaves a bracket without its partner, which is what a
        runaway does to the code it swallows. It cannot see a runaway that begins after
        the last bracket has closed, and nothing is lost there.
        """
        assert drift._masking_is_sound("const a = fn({ b: [1] });")
        assert not drift._masking_is_sound("const a = fn({ b: [1] };")
        assert drift._masking_is_sound("const a = fn();   ")

    def test_the_portal_tree_is_readable(self):
        """Every real file survives masking. Guards the rule against the repository
        growing a construct the reader cannot parse, which would silence it quietly."""
        unreadable = [
            str(path.relative_to(drift.PORTAL))
            for path in sorted((drift.PORTAL / "src").rglob("*.ts*"))
            if "useQuery" in path.read_text(encoding="utf-8")
            and not drift._masking_is_sound(drift._blank_strings_and_comments(path.read_text(encoding="utf-8")))
        ]
        assert not unreadable, unreadable
