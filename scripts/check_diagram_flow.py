#!/usr/bin/env python3
"""Fail when a diagram makes the reader work out which way to read it.

Three rules, all of them things that are only visible in the rendered image and therefore easy to
break while every generator function still looks correct.

**Direction.** Every edge must advance rightwards or downwards, never leftwards and never upwards.
The failure this prevents is not ugliness. A figure whose arrows change heading part-way through has
no reading order, so a reader traces each line with a finger to find out which one carries the thing
they came for -- which is usually the one claim the figure exists to make. A single backwards edge is
enough to cost that, because once one line runs the other way the reader can no longer assume any of
the others.

The verdict is reached on the two points the edge actually joins: the exit and entry anchors when the
style fixes them, and the node centres otherwise. Not on the routed path -- draw.io computes
orthogonal routing at render time and the waypoints are not in the file, so the path cannot be
recovered here.

Reading the anchors matters wherever an edge lands on something large. A restore edge dropping onto
the top-right of a 520px boundary frame advances rightwards for the reader while the frame's *centre*
sits well to the left of where the edge left, so a centres-only rule reports a backwards edge that
renders forwards. The anchors are in the file, so there is no reason to guess.

**Icon labels.** A vertex drawn as an image must carry `verticalLabelPosition=bottom`. The official
AWS asset guidance puts a service's name under its icon, and every reader of these diagrams has
learned that convention from every other AWS diagram they have seen. A label beside an icon reads as
belonging to whatever else is on that row.

**Boundary labels.** A group frame's title must not be pushed sideways with `spacingLeft` past the
standard offset. Raising it is how a boundary's name ends up sitting next to an icon that is merely
inside the boundary, which then looks exactly like that icon's own label while the icon's real label
sits underneath -- two names, one of them wrong.

Crossing edges are deliberately not checked. Whether two lines cross depends on the routing, which
is not in the file, and approximating it with straight centre-to-centre segments reports crossings
that do not render and misses ones that do. The direction rule removes most of them anyway: lines
that all advance the same way have far fewer opportunities to meet.

Nothing here is specific to one repository: paths are discovered rather than configured, so this file
is copied between repositories as-is. Two things then differ, both of them known. The suppression on
the parse call in `_parse()`: a repository whose ruff selects `S` needs `# noqa: S314` there, and one
that selects `RUF100` without `S` rejects the same comment as unused, so the divergence is isolated to
that one function rather than left to spread. And the line wrapping, because each repository's ruff
carries its own line length and reformats the copy on arrival -- so the copies are the same logic and
not the same bytes, and a diff between two of them is expected to show re-wrapped statements.

There is no debt file. This gate was wired only after every figure in the repository passed it, so
there is nothing to carry, and a gate with no exemption list cannot grow one quietly.

Run:  python3 tools/check_diagram_flow.py
      python3 tools/check_diagram_flow.py --selftest
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET  # nosec B405  reads this repository's own committed files
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Directories that hold copies of other people's files, or build output. Scanning them reports
# findings nobody in this repository can act on.
SKIP = {".git", ".venv", "node_modules", "__pycache__", ".private", "site-packages"}

# Displacement below this is treated as no movement. It is not a rounding allowance: these figures
# are laid out on a 10px grid, and a box anchored at 0.5 of its own width lands a few pixels off the
# icon above it, which renders as a straight vertical line and was being reported as a leftward edge.
# A step a reader can perceive as a direction is a column or a row -- a hundred pixels and up -- so
# nothing real hides under this, and a backwards nudge small enough to pass is one nobody can see.
EPSILON = 8.0

# The offset the AWS group shape uses to clear its own corner badge. A title at this value sits at
# the top-left of the frame, which is where a boundary name belongs; past it, the title travels
# along the top edge and lands beside whatever the frame contains.
GROUP_SPACING_LEFT = 30

IMAGE_SHAPE = re.compile(r"\bshape=image\b")
GROUP_SHAPE = re.compile(r"\bshape=mxgraph\.aws4\.group\b")
SPACING_LEFT = re.compile(r"\bspacingLeft=(\d+(?:\.\d+)?)")
EXIT_X = re.compile(r"\bexitX=(-?\d+(?:\.\d+)?)")
EXIT_Y = re.compile(r"\bexitY=(-?\d+(?:\.\d+)?)")
ENTRY_X = re.compile(r"\bentryX=(-?\d+(?:\.\d+)?)")
ENTRY_Y = re.compile(r"\bentryY=(-?\d+(?:\.\d+)?)")


@dataclass(frozen=True)
class Finding:
    path: Path
    rule: str
    detail: str


def _skipped(path: Path) -> bool:
    return bool(SKIP.intersection(path.relative_to(ROOT).parts))


def walk(pattern: str) -> list[Path]:
    return sorted(p for p in ROOT.rglob(pattern) if not _skipped(p))


def _parse(text: str) -> ET.Element:
    """Parse a committed .drawio from this repository -- never user-supplied data.

    The whole function exists to hold one line; see the module docstring for why the suppression
    cannot move.
    """
    return ET.fromstring(text)  # nosec B314


def _rect(cell: ET.Element) -> tuple[float, float, float, float] | None:
    """A vertex's rectangle in page coordinates, or None when it has no geometry of its own.

    A cell whose geometry is relative, or absent, is positioned by something else -- a label on an
    edge, or a child tracking its parent -- and has no place of its own to compare.
    """
    for geometry in cell:
        if geometry.tag != "mxGeometry":
            continue
        if geometry.get("relative") == "1":
            return None
        x, y = geometry.get("x"), geometry.get("y")
        if x is None or y is None:
            return None
        return (
            float(x),
            float(y),
            float(geometry.get("width") or 0),
            float(geometry.get("height") or 0),
        )
    return None


def _anchor(
    rect: tuple[float, float, float, float],
    style: str,
    x_pattern: re.Pattern[str],
    y_pattern: re.Pattern[str],
) -> tuple[float, float]:
    """Where the edge meets this node: its fixed anchor if the style names one, else the centre."""
    x, y, w, h = rect
    fx = x_pattern.search(style)
    fy = y_pattern.search(style)
    return (
        x + (float(fx.group(1)) if fx else 0.5) * w,
        y + (float(fy.group(1)) if fy else 0.5) * h,
    )


def _heading(dx: float, dy: float) -> str | None:
    """Which forbidden way this edge runs, or None when it advances right and/or down."""
    parts = []
    if dx < -EPSILON:
        parts.append("leftwards")
    if dy < -EPSILON:
        parts.append("upwards")
    return " and ".join(parts) if parts else None


def inspect(path: Path, text: str) -> list[Finding]:
    findings: list[Finding] = []
    root = _parse(text)
    for model in root.iter("mxGraphModel"):
        rects: dict[str, tuple[float, float, float, float]] = {}
        edges: list[tuple[str, str, str, str, str]] = []
        for cell in model.iter("mxCell"):
            cid = cell.get("id") or "?"
            style = cell.get("style") or ""
            value = (cell.get("value") or "").strip()
            if cell.get("edge") == "1":
                source, target = cell.get("source"), cell.get("target")
                if source and target:
                    edges.append((cid, source, target, value, style))
                continue
            if cell.get("vertex") != "1":
                continue
            rect = _rect(cell)
            if rect is not None:
                rects[cid] = rect
            if IMAGE_SHAPE.search(style) and "verticalLabelPosition=bottom" not in style:
                findings.append(
                    Finding(
                        path,
                        "icon-label",
                        f"cell {cid} ({value or 'unlabelled'}): an icon's label belongs underneath "
                        "it -- set verticalLabelPosition=bottom",
                    )
                )
            if GROUP_SHAPE.search(style) and value:
                match = SPACING_LEFT.search(style)
                spacing = float(match.group(1)) if match else 0.0
                if spacing > GROUP_SPACING_LEFT:
                    findings.append(
                        Finding(
                            path,
                            "boundary-label",
                            f"cell {cid} ({value}): spacingLeft={spacing:g} pushes the boundary "
                            f"title past the frame corner (max {GROUP_SPACING_LEFT}), where it "
                            "reads as the label of an icon inside the frame",
                        )
                    )
        for cid, source, target, label, style in edges:
            if source not in rects or target not in rects:
                continue
            sx, sy = _anchor(rects[source], style, EXIT_X, EXIT_Y)
            tx, ty = _anchor(rects[target], style, ENTRY_X, ENTRY_Y)
            heading = _heading(tx - sx, ty - sy)
            if heading is None:
                continue
            named = f" '{label}'" if label else ""
            findings.append(
                Finding(
                    path,
                    "flow-direction",
                    f"edge {cid}{named}: {source} -> {target} runs {heading} ({sx:.0f},{sy:.0f} -> {tx:.0f},{ty:.0f})",
                )
            )
    return findings


ADVICE = """
  Rerouting the line is rarely the fix, because the direction follows from the placement. Move the
  target so it sits right of or below its source; where two nodes must share a column, point the
  edge the way the thing it carries actually travels rather than drawing a return leg; and where a
  chain runs downwards, start it from a box, since the space under an icon belongs to that icon's
  label."""


def check() -> int:
    files = walk("*.drawio")
    if not files:
        print("diagram-flow: no .drawio files found")
        return 0

    findings: list[Finding] = []
    for path in files:
        try:
            findings += inspect(path, path.read_text(encoding="utf-8"))
        except ET.ParseError as error:
            print(f"error: {path.relative_to(ROOT)} is not valid XML: {error}", file=sys.stderr)
            return 1

    if findings:
        print("error: diagrams that do not read in one direction", file=sys.stderr)
        current = None
        for finding in findings:
            name = str(finding.path.relative_to(ROOT))
            if name != current:
                print(f"  {name}", file=sys.stderr)
                current = name
            print(f"    [{finding.rule}] {finding.detail}", file=sys.stderr)
        print(ADVICE, file=sys.stderr)
        return 1

    print(f"diagram-flow: {len(files)} file(s) read rightwards and downwards")
    return 0


# --- selftest ------------------------------------------------------------------------------------

# A gate is only trustworthy once it has been seen to fail, so every gate target runs this before the
# check itself. Without it, a refactor that makes `inspect` return nothing would look like a
# repository whose diagrams are all correct.


def _doc(cells: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?><mxfile><diagram id="d" name="d">'
        '<mxGraphModel pageWidth="880" pageHeight="600"><root>'
        '<mxCell id="0" /><mxCell id="1" parent="0" />'
        f"{cells}</root></mxGraphModel></diagram></mxfile>"
    )


def _node(cid: str, x: int, y: int, *, style: str = "rounded=1;", value: str = "n") -> str:
    return (
        f'<mxCell id="{cid}" value="{value}" style="{style}" vertex="1" parent="1">'
        f'<mxGeometry x="{x}" y="{y}" width="80" height="80" as="geometry" /></mxCell>'
    )


def _edge(cid: str, source: str, target: str, *, anchors: str = "") -> str:
    return (
        f'<mxCell id="{cid}" value="" style="endArrow=open;{anchors}" edge="1" '
        f'source="{source}" target="{target}" parent="1">'
        '<mxGeometry relative="1" as="geometry" /></mxCell>'
    )


def _frame(cid: str, x: int, y: int, w: int, h: int) -> str:
    return (
        f'<mxCell id="{cid}" value="" style="{GROUP}" vertex="1" parent="1">'
        f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry" /></mxCell>'
    )


ICON = "sketch=0;html=1;shape=image;verticalLabelPosition=bottom;verticalAlign=top;"
ICON_SIDE = "sketch=0;html=1;shape=image;verticalLabelPosition=middle;verticalAlign=middle;"
GROUP = "shape=mxgraph.aws4.group;grIcon=mxgraph.aws4.group_aws_cloud;align=left;spacingLeft=30;"
GROUP_WIDE = GROUP.replace("spacingLeft=30", "spacingLeft=160")


def selftest() -> int:
    cases: list[tuple[str, str, bool]] = [
        # (name, document, expected to be rejected)
        (
            "rightwards is accepted",
            _doc(_node("a", 0, 0) + _node("b", 200, 0) + _edge("e", "a", "b")),
            False,
        ),
        (
            "downwards is accepted",
            _doc(_node("a", 0, 0) + _node("b", 0, 200) + _edge("e", "a", "b")),
            False,
        ),
        (
            "down and to the right is accepted",
            _doc(_node("a", 0, 0) + _node("b", 200, 200) + _edge("e", "a", "b")),
            False,
        ),
        (
            "leftwards on the same row is rejected",
            _doc(_node("a", 200, 0) + _node("b", 0, 0) + _edge("e", "a", "b")),
            True,
        ),
        (
            "down and to the left is rejected, symmetric fan or not",
            _doc(
                _node("a", 200, 0)
                + _node("b", 0, 200)
                + _node("c", 400, 200)
                + _edge("e1", "a", "b")
                + _edge("e2", "a", "c")
            ),
            True,
        ),
        (
            "upwards is rejected",
            _doc(_node("a", 0, 200) + _node("b", 0, 0) + _edge("e", "a", "b")),
            True,
        ),
        (
            "a few pixels off the grid is not a direction",
            _doc(_node("a", 0, 0) + _node("b", 200, -6) + _edge("e", "a", "b")),
            False,
        ),
        (
            "a whole row up still is",
            _doc(_node("a", 0, 200) + _node("b", 200, 40) + _edge("e", "a", "b")),
            True,
        ),
        (
            "an edge to a node with no geometry of its own is skipped, not guessed at",
            _doc(_node("a", 200, 0) + _edge("e", "a", "nowhere")),
            False,
        ),
        (
            "an icon labelled underneath is accepted",
            _doc(_node("a", 0, 0, style=ICON)),
            False,
        ),
        (
            "an icon labelled beside itself is rejected",
            _doc(_node("a", 0, 0, style=ICON_SIDE)),
            True,
        ),
        (
            "a boundary title at the standard offset is accepted",
            _doc(_node("g", 0, 0, style=GROUP, value="AWS Cloud")),
            False,
        ),
        (
            "a boundary title pushed along the top edge is rejected",
            _doc(_node("g", 0, 0, style=GROUP_WIDE, value="AWS Cloud")),
            True,
        ),
        (
            "an untitled boundary is not judged on its offset",
            _doc(_node("g", 0, 0, style=GROUP_WIDE, value="")),
            False,
        ),
        (
            "a drop onto the far side of a wide frame advances, though its centre is behind",
            _doc(
                _node("a", 400, 0)
                + _frame("f", 0, 200, 520, 200)
                + _edge("e", "a", "f", anchors="exitX=0.5;exitY=1;entryX=0.9;entryY=0;")
            ),
            False,
        ),
        (
            "and a drop onto the near side of the same frame does not",
            _doc(
                _node("a", 400, 0)
                + _frame("f", 0, 200, 520, 200)
                + _edge("e", "a", "f", anchors="exitX=0.5;exitY=1;entryX=0.25;entryY=0;")
            ),
            True,
        ),
        (
            "one backwards edge among good ones is caught",
            _doc(
                _node("a", 0, 0)
                + _node("b", 200, 0)
                + _node("c", 400, 0)
                + _edge("e1", "a", "b")
                + _edge("e2", "c", "b")
            ),
            True,
        ),
    ]
    probe = ROOT / "selftest.drawio"
    failures = 0
    for name, document, should_reject in cases:
        rejected = bool(inspect(probe, document))
        if rejected != should_reject:
            verdict = "rejected" if rejected else "accepted"
            wanted = "reject" if should_reject else "accept"
            print(f"  selftest FAILED: {name} -> {verdict}, expected to {wanted}", file=sys.stderr)
            failures += 1

    fan_case = next(d for n, d, _ in cases if n.startswith("down and to the left"))
    rules = {f.rule for f in inspect(probe, fan_case)}
    if rules != {"flow-direction"}:
        print(f"  selftest FAILED: fan case reported {rules}, expected flow-direction", file=sys.stderr)
        failures += 1

    if failures:
        print(f"selftest: {failures} case(s) failed", file=sys.stderr)
        return 1
    print(f"selftest: {len(cases) + 1} case(s) behave as documented")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="prove the check rejects backwards edges and misplaced labels, and accepts compliant ones",
    )
    args = parser.parse_args()
    return selftest() if args.selftest else check()


if __name__ == "__main__":
    sys.exit(main())
