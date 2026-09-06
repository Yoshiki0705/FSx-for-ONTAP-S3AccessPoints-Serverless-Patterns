#!/usr/bin/env python3
"""Declarative builder for compliant draw.io architecture diagrams.

Encodes the rules from the `global-architecture-diagram-standards.md` steering so
compliance holds by construction rather than by review:

  * Official AWS Architecture Icons embedded at their native size (service 80x80
    from `Arch_*_64.svg`, resource 48x48 from `Res_*_48.svg`) — never rescaled.
  * Labels are passed through verbatim, but `check_labels()` fails the build when an
    AWS service label is missing its `Amazon`/`AWS` prefix or uses an abbreviation.
  * Every edge is the preset Open Arrow in a single colour.
  * Notes render as `※1` / `*1` items with a bold headline and detail line.
  * Nodes are placed on a grid, so spacing is uniform and collisions are structural
    rather than accidental.

All attribute values are escaped with `esc()`. Note that
`xml.sax.saxutils.escape()` does not escape double quotes, which silently corrupts
drawio files — `esc()` handles that.
"""

from __future__ import annotations

import base64
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, replace
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))

# The gate's own formula, not a copy of it. Two copies of "what size does this width
# need" would be free to disagree, and the one in the gate is the one that decides
# whether the result passes.
from check_diagram_fonts import MIN_SOURCE_PX, required_font  # noqa: E402

# ---------------------------------------------------------------- geometry ----
COL_PITCH = 210  # official names run ~130px at 13px, so keep generous clearance
# 165 was enough when a vertical run only had to hold a node label and an edge label.
# A stacked layout adds a third thing to the same run -- the group's own name, drawn
# inside its top-left corner where the entering edge crosses it -- and at the label
# floor the three no longer fit: the edge label ended up 3px into the node label,
# reading as its second line. Rows cost height, and height is not what a reader's
# column is short of.
ROW_PITCH = 195
MARGIN_X = 90
MARGIN_Y = 150  # leaves room for the title above the canvas

SERVICE_SIZE = 80
RESOURCE_SIZE = 48
BOX_W = 190
BOX_H = 64

SQUID = "#232F3E"
# The page background. Also what a node label is masked with, so a vertical connector
# leaving an icon does not read as a stroke through its own label. The dark generator
# remaps #FFFFFF to its surface colour, so both themes follow one value.
CANVAS = "#FFFFFF"

# ---------------------------------------------------------------- styling ----
# Label sizes are not written down here. They are derived per diagram from the width it
# ends up at, by `required_font` in scripts/check_diagram_fonts.py -- the same function
# the gate judges the result with, imported rather than restated so the generator and the
# gate cannot come to different numbers.
#
# The old values were 11 to 14, chosen in the editor where the whole canvas is visible at
# full size, which is the one place the reader never sees it. A label arrives at
# `fontSize x min(1, 880 / width)`, so what a canvas needs depends on how wide it is:
# 880 px needs 16, 1200 px needs 20, 1739 px needs 28. Anything fixed is either too small
# on the wide diagrams or larger than the narrow ones need.
MIN_LABEL_PX = MIN_SOURCE_PX  # the floor a narrow canvas still has to clear


def title_style(px: int) -> str:
    return f"text;html=1;align=center;verticalAlign=middle;fontSize={px};fontStyle=1;fontColor={SQUID};"


def note_style(px: int) -> str:
    return (
        "rounded=1;whiteSpace=wrap;html=1;dashed=1;dashPattern=8 4;"
        f"strokeColor={SQUID};fillColor=#FFFFFF;align=left;verticalAlign=top;"
        f"spacingLeft=10;spacingTop=4;fontSize={px};fontColor={SQUID};"
    )


def edge_style(px: int) -> str:
    return (
        "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;"
        f"endArrow=open;endFill=0;strokeColor={SQUID};strokeWidth=1;"
        f"fontSize={px};fontColor={SQUID};labelBackgroundColor=#ffffff;"
    )


def box_style(px: int, *, fill: str, stroke: str) -> str:
    return (
        f"rounded=1;whiteSpace=wrap;html=1;dashed=0;strokeColor={stroke};"
        f"fillColor={fill};align=center;verticalAlign=middle;"
        f"fontSize={px};fontColor={SQUID};"
    )


def group_style(px: int, *, gr: str, stroke: str) -> str:
    return (
        "points=[[0,0],[0.25,0],[0.5,0],[0.75,0],[1,0],[1,0.25],[1,0.5],[1,0.75],[1,1],"
        "[0.75,1],[0.5,1],[0.25,1],[0,1],[0,0.75],[0,0.5],[0,0.25]];outlineConnect=0;"
        "gradientColor=none;html=1;whiteSpace=wrap;"
        f"fontSize={px};fontStyle=1;"
        f"shape=mxgraph.aws4.group;grIcon=mxgraph.aws4.{gr};"
        f"strokeColor={stroke};fillColor=none;verticalAlign=top;align=left;"
        # The title needs a background for the same reason an icon's label does: it sits
        # at the top-left of the frame, and on a narrow diagram the leftmost column's
        # vertical run enters exactly there. `fillColor=none` keeps the frame itself
        # transparent, so this paints behind the text only.
        f"spacingLeft=30;fontColor={stroke};dashed=0;labelBackgroundColor={CANVAS};"
    )


def section_label_style(px: int) -> str:
    return f"text;html=1;align=center;verticalAlign=middle;fontSize={px};fontStyle=1;fontColor=#ED7100;"


SERVICE = "service"
RESOURCE = "resource"
BOX = "box"

# Labels legitimately exempt from the Amazon/AWS prefix rule: generic endpoints,
# people, and third-party products.
PREFIX_EXEMPT = re.compile(
    r"^(Web ブラウザ|Web browser|利用者|Users|NFS |SMB |Nextcloud|オンプレ|On-prem"
    r"|ユーザー|User|管理者|Admin|ブラウザ|Browser"
    # Sources outside AWS. A migration figure has to name what the data is coming
    # from, and "Amazon" in front of another vendor's storage would be wrong.
    r"|オブジェクトストレージ|Object storage|SaaS)"
)
ABBREVIATIONS = {"ALB": "Elastic Load Balancing", "ELB": "Elastic Load Balancing"}

# draw.io runs a math typesetter over label text. Backticks are AsciiMath
# delimiters and `$`/`\(`/`\[` are TeX delimiters, so Markdown-style code spans get
# silently re-rendered: `storage-admin` came out as "s → ra ≥ −ad min".
MATH_TRIGGER = re.compile(r"`|\$|\\\(|\\\[")


def esc(text: str) -> str:
    """Escape for use inside a double-quoted XML attribute (quotes included)."""
    return escape(text, {'"': "&quot;"})


# ------------------------------------------------------------------ model ----
@dataclass
class Grid:
    """Pitch and default box width for one diagram."""

    col_pitch: int = COL_PITCH
    row_pitch: int = ROW_PITCH
    box_w: int = BOX_W


@dataclass
class Node:
    id: str
    label: str
    col: float
    row: float
    kind: str = SERVICE
    icon: str | None = None
    fill: str = "#FFFFFF"
    stroke: str = SQUID
    w: int | None = None
    h: int | None = None

    def size(self, grid: Grid) -> tuple[int, int]:
        if self.kind == SERVICE:
            return SERVICE_SIZE, SERVICE_SIZE
        if self.kind == RESOURCE:
            return RESOURCE_SIZE, RESOURCE_SIZE
        return self.w or grid.box_w, self.h or BOX_H

    def centre(self, grid: Grid) -> tuple[float, float]:
        return (
            MARGIN_X + self.col * grid.col_pitch + grid.col_pitch / 2,
            MARGIN_Y + self.row * grid.row_pitch + grid.row_pitch / 2,
        )

    def rect(self, grid: Grid) -> tuple[float, float, int, int]:
        cx, cy = self.centre(grid)
        w, h = self.size(grid)
        return cx - w / 2, cy - h / 2, w, h

    def label_extent(self, grid: Grid, px: int) -> tuple[float, float]:
        """Horizontal span of the rendered label, which for icons sits below and
        centred and so can be much wider than the icon itself.

        Takes the label size because it is what makes the canvas wider, which in turn
        is what decides the label size: `build` settles the two together.
        """
        cx, _ = self.centre(grid)
        if self.kind == BOX:
            w, _ = self.size(grid)
            return cx - w / 2, cx + w / 2
        half = text_width(self.label, px) / 2
        return cx - half, cx + half


def text_width(label: str, font_size: int) -> float:
    """Rough rendered width of the widest line, for collision-free bounds.

    Full-width (CJK) glyphs advance ~1.0em, ASCII ~0.55em.
    """
    widest = 0.0
    for line in re.split(r"<br\s*/?>|&#xa;", label):
        plain = re.sub(r"<[^>]+>", "", line)
        cjk = sum(1 for ch in plain if ord(ch) > 0x2E7F)
        rest = len(plain) - cjk
        widest = max(widest, cjk * font_size + rest * font_size * 0.55)
    return widest


@dataclass
class Edge:
    source: str
    target: str
    label: str = ""
    # position along path (-1..1) and pixel offset, for pushing a label off an icon
    at: float | None = None
    dx: int = 0
    dy: int = 0
    # Anchor overrides as (x, y) in 0..1 of the node box. An icon's label sits
    # centred below it, so a connector attaching at (0.5, 1) or arriving from below
    # runs through that label — anchor on a side instead.
    exit: tuple[float, float] | None = None
    entry: tuple[float, float] | None = None


@dataclass
class Group:
    id: str
    label: str
    cols: tuple[float, float]
    rows: tuple[float, float]
    gr_icon: str = "group_aws_cloud_alt"
    stroke: str = SQUID
    # Shrink on all sides. A nested group needs this so its border does not land on
    # the enclosing group's border or run through the enclosing group's label.
    inset: int = 0


@dataclass
class SectionLabel:
    id: str
    label: str
    col: float
    row: float
    span: float = 1.0


@dataclass
class Diagram:
    id: str
    name: str
    title: str
    nodes: list[Node]
    edges: list[Edge] = field(default_factory=list)
    groups: list[Group] = field(default_factory=list)
    sections: list[SectionLabel] = field(default_factory=list)
    notes: list[tuple[str, str]] = field(default_factory=list)
    note_lang: str = "ja"
    grid: Grid = field(default_factory=Grid)


# ------------------------------------------------------------ validation ----
def check_labels(diagram: Diagram) -> list[str]:
    """Fail the build on label rules that the official deck makes explicit."""
    problems: list[str] = []
    for n in diagram.nodes:
        lines = re.split(r"<br\s*/?>|&#xa;", n.label)
        first = re.sub(r"<[^>]+>", "", lines[0]).strip()
        if "&#xa;" in n.label:
            problems.append(
                f"{n.id}: '&#xa;' does not break a line in an html=1 label (it collapses to a space) — use '<br>'"
            )
        if n.kind == BOX or PREFIX_EXEMPT.match(first):
            continue
        for abbr, full in ABBREVIATIONS.items():
            if re.fullmatch(rf"{abbr}\b.*", first):
                problems.append(f"{n.id}: abbreviation '{abbr}' — use '{full}'")
        if not first.startswith(("Amazon ", "AWS ", "Elastic Load")):
            problems.append(f"{n.id}: label '{first}' lacks an Amazon/AWS prefix")
        if len(lines) > 2:
            problems.append(f"{n.id}: label exceeds 2 lines")
    return problems


def check_edge_labels(diagram: Diagram, px: int) -> list[str]:
    """A horizontal edge label wider than the gap between its endpoints overlaps
    the icons, so require the pitch to accommodate it."""
    grid = diagram.grid
    by_id = {n.id: n for n in diagram.nodes}
    problems = []
    for e in diagram.edges:
        if not e.label or e.source not in by_id or e.target not in by_id:
            continue
        s, t = by_id[e.source], by_id[e.target]
        if s.row != t.row or s.col == t.col:
            continue  # only horizontal runs are pitch-constrained
        sx, _, sw, _ = s.rect(grid)
        tx, _, tw, _ = t.rect(grid)
        gap = max(tx - (sx + sw), sx - (tx + tw))
        need = text_width(e.label, font_size=px)
        if need > gap - 8:
            problems.append(
                f"edge {e.source}->{e.target}: label '{e.label}' needs ~{need:.0f}px "
                f"but the gap is {gap:.0f}px — widen col_pitch or shorten the label"
            )
    return problems


# Rendered line height of an icon label, from the label font size. Was a bare 18 for a
# 13px label; left behind when the label grew, it under-reserved the band below a node
# and an edge label landed on the label's second line.
def label_line_h(px: int) -> int:
    """Rendered line height of an icon label. Was a bare 18 for a 13px label; left
    behind when the label grew, it under-reserved the band below a node and an edge
    label landed on the label's second line."""
    return round(px * 18 / 13)


def edge_label_half_h(px: int) -> int:
    """Half the rendered height of an edge label. Was a bare 9 for 12px."""
    return round(px * 9 / 12)


LABEL_BAND_GAP = 14  # breathing room between a node label and an edge label
ARROWHEAD_KEEPOUT = 14  # keep a pushed-down label off the arrowhead


def vertical_label_shortfall(diagram: Diagram, e: Edge, px: int) -> float:
    """Pixels an edge label must move down to clear the upper node's label band.

    An icon's own label renders *below* the icon, inside the vertical run that
    leaves it, so a label centred on that run can land in the band and read as a
    third line of the node label ('ONTAP REST API' under 'AWS Lambda / (VPC 内)').
    Returns 0.0 when the edge is not affected or already clears the band.
    """
    by_id = {n.id: n for n in diagram.nodes}
    if not e.label or e.source not in by_id or e.target not in by_id:
        return 0.0
    s, t = by_id[e.source], by_id[e.target]
    if s.col != t.col or s.row == t.row:
        return 0.0  # only straight vertical runs stack under a node label
    if e.exit or e.entry:
        return 0.0  # anchored off the bottom edge, so the band is not in the path
    upper, lower = (s, t) if t.row > s.row else (t, s)
    if upper.kind == BOX:
        return 0.0  # a box label is inside the box, leaving no band below it

    grid = diagram.grid
    _, uy, _, uh = upper.rect(grid)
    _, ly, _, _ = lower.rect(grid)
    run_start, run_end = uy + uh, ly
    # Default label position is the midpoint of the run; `at` runs -1..1 over it.
    pos = 0.5 if e.at is None else (e.at + 1) / 2
    label_y = run_start + (run_end - run_start) * pos + e.dy
    lines = len(re.split(r"<br\s*/?>|&#xa;", upper.label))
    band_end = run_start + lines * label_line_h(px) + LABEL_BAND_GAP
    target_y = band_end + edge_label_half_h(px)
    if target_y > run_end - ARROWHEAD_KEEPOUT:
        # The run is too short to hold both labels; widen row_pitch instead of
        # shoving the edge label onto the arrowhead.
        raise ValueError(
            f"{diagram.id}: edge {e.source}->{e.target} label '{e.label}' cannot "
            f"clear {upper.id}'s label band within a {run_end - run_start:.0f}px run "
            f"— increase row_pitch or shorten the node label"
        )
    return max(0.0, target_y - label_y)


def group_label_clearance(diagram: Diagram, e: Edge, px: int, dy: float) -> float:
    """Pixels a vertical edge label must move up to clear a group's own label.

    A group draws its name inside its top-left corner, and an edge entering the group
    from outside crosses that border. With the entry point near the left -- which is
    where a stacked layout puts it -- the edge label lands on top of the group name:
    'AWS Cloud' and '監査クエリ' printed over each other. Returns dy unchanged when
    nothing is in the way.
    """
    by_id = {n.id: n for n in diagram.nodes}
    if not e.label or e.source not in by_id or e.target not in by_id:
        return dy
    s, t = by_id[e.source], by_id[e.target]
    if s.col != t.col or s.row == t.row:
        return dy  # only a straight vertical run crosses a border head-on

    grid = diagram.grid
    upper, lower = (s, t) if t.row > s.row else (t, s)
    _, uy, _, uh = upper.rect(grid)
    _, ly, _, _ = lower.rect(grid)
    run_start, run_end = uy + uh, ly
    pos = 0.5 if e.at is None else (e.at + 1) / 2
    label_y = run_start + (run_end - run_start) * pos + dy
    half = edge_label_half_h(px)

    for g in diagram.groups:
        gx, gy, gw, _ = _group_rect(g, diagram.nodes, grid, px)
        crosses = run_start < gy < run_end
        # The name sits at the left, so only a run near it is in the way.
        near_name = gx <= upper.centre(grid)[0] <= gx + gw / 2 + text_width(g.label, px)
        if not crosses or not near_name:
            continue
        band_end = gy + label_line_h(px)
        if label_y + half < gy or label_y - half > band_end:
            continue
        midpoint = run_start + (run_end - run_start) * pos
        # Below the name, not above it. Lifting the label over the border works for the
        # border but walks it back into the node's own label band, and the two then read
        # as one stacked block -- which is what the node-label clearance above exists to
        # prevent. Going down clears both.
        below = band_end + 6 + half
        if below + half <= run_end - ARROWHEAD_KEEPOUT:
            return below - midpoint
        above = gy - half - 6
        if above - half >= run_start:
            return above - midpoint
        raise ValueError(
            f"{diagram.id}: edge {e.source}->{e.target} label '{e.label}' has nowhere to "
            f"sit that clears both {g.id}'s name and the node label — lengthen the run "
            "with row_pitch, or move the entry away from the group's left edge"
        )
    return dy


def check_vertical_edge_labels(diagram: Diagram, px: int) -> list[str]:
    """Safety net for explicit `at`/`dy` overrides that leave a vertical edge label
    inside the upper node's label band. Unset offsets are corrected in `build()`."""
    problems = []
    for e in diagram.edges:
        if e.at is None and not e.dx and not e.dy:
            continue  # build() applies the clearance automatically
        short = vertical_label_shortfall(diagram, e, px)
        if short > 0:
            problems.append(
                f"edge {e.source}->{e.target}: label '{e.label}' sits in the upper "
                f"node's label band and reads as an extra label line — increase dy "
                f"to {int(e.dy + short) + 1} (or adjust `at`)"
            )
    return problems


def check_math_triggers(diagram: Diagram) -> list[str]:
    """Reject text that draw.io's math typesetter would rewrite."""
    texts: list[tuple[str, str]] = [("title", diagram.title)]
    texts += [(f"node {n.id}", n.label) for n in diagram.nodes]
    texts += [(f"edge {e.source}->{e.target}", e.label) for e in diagram.edges]
    texts += [(f"group {g.id}", g.label) for g in diagram.groups]
    texts += [(f"section {s.id}", s.label) for s in diagram.sections]
    for i, (headline, detail) in enumerate(diagram.notes, start=1):
        texts.append((f"note {i} headline", headline))
        texts.append((f"note {i} detail", detail))

    problems = []
    for where, text in texts:
        hit = MATH_TRIGGER.search(text or "")
        if hit:
            problems.append(f"{where}: {hit.group(0)!r} triggers draw.io math typesetting — use plain text in {text!r}")
    return problems


# --------------------------------------------------------------- emitting ----
class IconResolver:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._cache: dict[str, str] = {}

    def data_uri(self, filename: str) -> str:
        if filename in self._cache:
            return self._cache[filename]
        hits = list(self.root.rglob(filename))
        if not hits:
            raise FileNotFoundError(f"{filename} not found under {self.root}")
        b64 = base64.b64encode(hits[0].read_bytes()).decode("ascii")
        uri = f"data:image/svg+xml,{b64}"
        self._cache[filename] = uri
        return uri


# The size the note text is wrapped for. It has to be the size it is rendered at: when
# these were separate numbers, the box was measured for 11 px text and drawn at 16, so
# the wrap ran past the right border and the last line was cut off by the bottom one.
NOTE_BOX_W = 640  # fixed width of the notes box, right-aligned to the content
NOTE_PADDING = 20  # spacingLeft plus an equal right margin


def note_line_h(px: int) -> int:
    """Line height of note text, keeping the ratio the 11px:16px pair had."""
    return round(px * 16 / 11)


def _wrap_note(text: str, max_w: float, px: int) -> list[str]:
    """Break a note line to fit the box.

    draw.io's own `whiteSpace=wrap` is not applied when the diagram is exported, so
    an over-long English note ran past the border. Wrap explicitly instead. ASCII
    breaks on spaces; CJK breaks between characters, as it does in Japanese
    typesetting.
    """
    # Each token carries its own trailing spaces, so a break opportunity after a
    # CJK character does not swallow the space that follows it.
    tokens = re.findall(
        r"[\u3000-\u9FFF\uFF00-\uFFEF]\s*"  # one CJK glyph + following spaces
        r"|[^\s\u3000-\u9FFF\uFF00-\uFFEF]+\s*"  # an ASCII run + following spaces
        r"|\s+",
        text,
    )
    lines: list[str] = []
    current = ""
    for token in tokens:
        candidate = current + token
        if current and text_width(candidate.strip(), px) > max_w:
            lines.append(current.rstrip())
            current = token.lstrip() if token.strip() else ""
        else:
            current = candidate
    if current.strip():
        lines.append(current.rstrip())
    return lines or [""]


def _note_lines(notes: list[tuple[str, str]], lang: str, max_w: float, px: int) -> list[str]:
    marker = "※" if lang == "ja" else "*"
    heading = "補足" if lang == "ja" else "Notes"
    lines = [f"<b>{heading}</b>"]
    for i, (headline, detail) in enumerate(notes, start=1):
        num = f"{marker}{i}" if len(notes) > 1 else marker
        head = _wrap_note(f"{num} {headline}", max_w, px)
        lines += [f"<b>{part}</b>" for part in head]
        lines += _wrap_note(detail, max_w, px)
    return lines


# drawio crops the export to its rendered content and adds `--border 12` on each side.
# Measured against the exported SVGs, the width lands 38px above the content span.
EXPORT_SLACK = 38


def _content_width(diagram: Diagram, px: int) -> float:
    """Width of the nodes, labels and groups with labels this size."""
    grid = diagram.grid
    xs: list[float] = []
    for n in diagram.nodes:
        x, _, w, _ = n.rect(grid)
        lx0, lx1 = n.label_extent(grid, px)
        xs += [x, x + w, lx0, lx1]
    for g in diagram.groups:
        gx, _, gw, _ = _group_rect(g, diagram.nodes, grid, px)
        xs += [gx, gx + gw]
    return max(xs) - min(xs)


def export_width(diagram: Diagram, px: int) -> float:
    """What the exported SVG will be, which is what the gate measures.

    The nodes are not the only thing in the frame, and on a narrow diagram they are
    not the widest. The title is centred on the content and overflows it on both
    sides; the notes box is a fixed 640 and hangs off the right edge, reaching left
    past the content when the content is narrower than it is. Predicting from the
    nodes alone put a four-state diagram one notch below the floor: the estimate said
    1120 and drawio wrote 1158, which needs 19px rather than 18.
    """
    content = _content_width(diagram, px)
    # Coordinates relative to the content's left edge, so the union is easy to read.
    spans = [(0.0, content)]
    title_w = text_width(diagram.title, px)
    spans.append(((content - title_w) / 2, (content + title_w) / 2))
    if diagram.notes:
        spans.append((content - NOTE_BOX_W, content))
    return max(hi for _, hi in spans) - min(lo for lo, _ in spans) + EXPORT_SLACK


def label_size(diagram: Diagram) -> int:
    """The label size this diagram needs, settled against its own width.

    Larger labels widen the canvas, because an icon's label is centred below it and
    runs wider than the icon; a wider canvas is scaled down further in a reader's
    column and so needs larger labels. The two are solved together rather than
    assumed apart: measured over the diagrams here it settles in at most three
    rounds, and a diagram that did not settle would be one whose labels grow the
    canvas faster than the canvas raises the requirement, which is worth failing on
    rather than capping silently.
    """
    px = MIN_LABEL_PX
    for _ in range(8):
        want = max(MIN_LABEL_PX, required_font(export_width(diagram, px)))
        if want == px:
            return px
        px = want
    raise ValueError(
        f"{diagram.id}: label size does not settle (reached {px}px). The labels widen "
        "the canvas faster than the width raises the floor — shorten a label, or split "
        "the diagram so it stops growing."
    )


def build(diagram: Diagram, icons: IconResolver) -> str:
    px = label_size(diagram)
    problems = (
        check_labels(diagram)
        + check_math_triggers(diagram)
        + check_edge_labels(diagram, px)
        + check_vertical_edge_labels(diagram, px)
    )
    if problems:
        raise ValueError(f"{diagram.id}: label rule violations:\n  - " + "\n  - ".join(problems))

    grid = diagram.grid
    by_id = {n.id: n for n in diagram.nodes}
    cells: list[str] = []

    # extent, for placing the title and the notes box. Icon labels sit below and
    # centred, so they widen the extent well past the icon box.
    xs, ys = [], []
    for n in diagram.nodes:
        x, y, w, h = n.rect(grid)
        lx0, lx1 = n.label_extent(grid, px)
        xs += [x, x + w, lx0, lx1]
        ys += [y, y + h + 34]
    for g in diagram.groups:
        gx, gy, gw, gh = _group_rect(g, diagram.nodes, grid, px)
        xs += [gx, gx + gw]
        ys += [gy, gy + gh]
    left, right = min(xs), max(xs)
    top, bottom = min(ys), max(ys)

    cells.append(
        f'        <mxCell id="d-title" value="{esc(diagram.title)}" '
        f'style="{title_style(px)}" vertex="1" parent="1">\n'
        f'          <mxGeometry x="{left:.0f}" y="{top - 70:.0f}" '
        f'width="{right - left:.0f}" height="34" as="geometry" />\n'
        f"        </mxCell>"
    )

    group_start = len(cells)
    # groups first so they render behind the nodes
    for g in diagram.groups:
        gx, gy, gw, gh = _group_rect(g, diagram.nodes, grid, px)
        style = group_style(px, gr=g.gr_icon, stroke=g.stroke)
        cells.append(
            f'        <mxCell id="{g.id}" value="{esc(g.label)}" style="{style}" '
            f'vertex="1" parent="1">\n'
            f'          <mxGeometry x="{gx:.0f}" y="{gy:.0f}" '
            f'width="{gw:.0f}" height="{gh:.0f}" as="geometry" />\n'
            f"        </mxCell>"
        )

    for s in diagram.sections:
        cx = MARGIN_X + s.col * grid.col_pitch + grid.col_pitch / 2
        cy = MARGIN_Y + s.row * grid.row_pitch + grid.row_pitch / 2
        w = s.span * grid.col_pitch
        cells.append(
            f'        <mxCell id="{s.id}" value="{esc(s.label)}" '
            f'style="{section_label_style(px)}" vertex="1" parent="1">\n'
            f'          <mxGeometry x="{cx - w / 2:.0f}" y="{cy - 12:.0f}" '
            f'width="{w:.0f}" height="24" as="geometry" />\n'
            f"        </mxCell>"
        )

    node_start = len(cells)
    for n in diagram.nodes:
        x, y, w, h = n.rect(grid)
        if n.kind in (SERVICE, RESOURCE):
            if not n.icon:
                raise ValueError(f"{n.id}: {n.kind} node needs an icon filename")
            uri = icons.data_uri(n.icon)
            # labelBackgroundColor is not decoration. An icon's label renders *below*
            # the icon, which is exactly where a vertical edge leaving that icon runs,
            # so the connector is drawn straight through the text -- measured on
            # saas-migration-group-b-worker, where the line to the access point passed
            # between "Amazon" and "FSx" and again between "NetApp" and "ONTAP".
            # `vertical_label_shortfall` moves the *edge* label out of that band but can
            # do nothing about the line itself, and this builder routes only between
            # adjacent cells, so there is no riser to send it around. Masking the line
            # behind the text is what is left. It grew visible when the label size rose
            # to the readability floor: a bigger glyph puts more ink on the same line.
            style = (
                "sketch=0;html=1;shape=image;verticalLabelPosition=bottom;"
                "verticalAlign=top;labelPosition=center;align=center;"
                f"imageAspect=1;aspect=fixed;fontSize={px};fontColor={SQUID};"
                f"labelBackgroundColor={CANVAS};image={uri};"
            )
        else:
            style = box_style(px, fill=n.fill, stroke=n.stroke)
        cells.append(
            f'        <mxCell id="{n.id}" value="{esc(n.label)}" style="{style}" '
            f'vertex="1" parent="1">\n'
            f'          <mxGeometry x="{x:.0f}" y="{y:.0f}" '
            f'width="{w}" height="{h}" as="geometry" />\n'
            f"        </mxCell>"
        )

    edge_start = len(cells)
    for i, e in enumerate(diagram.edges):
        for end in (e.source, e.target):
            if end not in by_id:
                raise ValueError(f"{diagram.id}: edge references unknown node '{end}'")
        dx, dy = e.dx, e.dy
        if e.label and e.at is None and not dx and not dy:
            # A label centred on a horizontal connector gets struck through by it.
            # Lift it clear.
            s, t = by_id[e.source], by_id[e.target]
            if s.row == t.row and s.col != t.col:
                dy = -13
            else:
                # On a vertical run, drop the label below the upper node's own
                # label so the two do not read as one stacked block.
                dy = round(vertical_label_shortfall(diagram, e, px))
                dy = round(group_label_clearance(diagram, e, px, dy))
        if e.at is None and not dx and not dy:
            geo = '<mxGeometry relative="1" as="geometry" />'
        else:
            at = f' x="{e.at}"' if e.at is not None else ""
            geo = (
                f'<mxGeometry{at} relative="1" as="geometry">\n'
                f'            <mxPoint as="offset" x="{dx}" y="{dy}" />\n'
                f"          </mxGeometry>"
            )
        anchors = ""
        if e.exit:
            anchors += f"exitX={e.exit[0]};exitY={e.exit[1]};exitDx=0;exitDy=0;"
        if e.entry:
            anchors += f"entryX={e.entry[0]};entryY={e.entry[1]};entryDx=0;entryDy=0;"
        cells.append(
            f'        <mxCell id="e{i}" value="{esc(e.label)}" '
            f'style="{edge_style(px)}{anchors}" '
            f'edge="1" source="{e.source}" target="{e.target}" parent="1">\n'
            f"          {geo}\n"
            f"        </mxCell>"
        )

    # Edges before nodes, so a node paints over a line rather than under it. draw.io
    # paints in document order, and with nodes first the connector leaving an icon was
    # drawn on top of that icon's own label -- the label sits directly below the icon,
    # which is where the line runs. `labelBackgroundColor` alone could not fix it: the
    # background is painted with the label, then the line goes over it.
    #
    # Nothing is lost by the swap. Group frames are `fillColor=none`, so they hide
    # nothing; an edge that ran through an icon would now disappear behind it, and this
    # builder forbids that arrangement anyway; and an edge label keeps its own
    # background and is already moved clear of the node's label band by
    # `vertical_label_shortfall`.
    # Group frames go after the edges too, for the same reason one step out: a group's
    # title sits at the top-left of its frame, which on a narrow diagram is exactly where
    # the leftmost column's vertical run enters -- and a line through "AWS Cloud" is the
    # same defect as a line through an icon's label. The frame paints nothing but its own
    # border and title, so an edge crossing the border reads the same either way: two thin
    # lines of one colour meeting, with no fill to hide anything behind.
    cells[:] = (
        cells[:group_start]  # title, section labels
        + cells[edge_start:]  # edges
        + cells[group_start:node_start]  # group frames
        + cells[node_start:edge_start]  # nodes
    )

    if diagram.notes:
        note_w = float(NOTE_BOX_W)
        note_lines = _note_lines(diagram.notes, diagram.note_lang, note_w - NOTE_PADDING, px)
        note_h = 14 + len(note_lines) * note_line_h(px)
        cells.append(
            f'        <mxCell id="d-notes" '
            f'value="{esc("<br>".join(note_lines))}" '
            f'style="{note_style(px)}" vertex="1" parent="1">\n'
            f'          <mxGeometry x="{right - note_w:.0f}" y="{bottom + 40:.0f}" '
            f'width="{note_w:.0f}" height="{note_h:.0f}" as="geometry" />\n'
            f"        </mxCell>"
        )

    body = "\n".join(cells)
    return (
        '<mxfile host="Kiro" agent="Kiro" version="1.0.0">\n'
        f'  <diagram id="{diagram.id}" name="{esc(diagram.name)}">\n'
        '    <mxGraphModel dx="1400" dy="1000" grid="1" gridSize="10" guides="1" '
        'tooltips="1" connect="1" arrows="1" fold="1" page="1" '
        'pageWidth="1600" pageHeight="1200" background="#FFFFFF">\n'
        "      <root>\n"
        '        <mxCell id="0" />\n'
        '        <mxCell id="1" parent="0" />\n'
        f"{body}\n"
        "      </root>\n"
        "    </mxGraphModel>\n"
        "  </diagram>\n"
        "</mxfile>\n"
    )


def _group_rect(g: Group, nodes: list[Node], grid: Grid, px: int) -> tuple[float, float, float, float]:
    i = g.inset
    x0 = MARGIN_X + g.cols[0] * grid.col_pitch + 20 + i
    x1 = MARGIN_X + (g.cols[1] + 1) * grid.col_pitch - 20 - i
    y0 = MARGIN_Y + g.rows[0] * grid.row_pitch - 10 + i
    y1 = MARGIN_Y + (g.rows[1] + 1) * grid.row_pitch + 10 - i

    # Icon labels are centred below the icon and often wider than the grid cell, so
    # a border drawn on the cell boundary cuts through them. Grow to contain them.
    # This runs after the inset so label containment always wins.
    for n in nodes:
        inside = g.cols[0] <= n.col <= g.cols[1] and g.rows[0] <= n.row <= g.rows[1]
        if not inside:
            continue
        lx0, lx1 = n.label_extent(grid, px)
        x0 = min(x0, lx0 - 14)
        x1 = max(x1, lx1 + 14)
        if n.kind != BOX:
            _, ny, _, nh = n.rect(grid)
            lines = len(re.split(r"<br\s*/?>|&#xa;", n.label))
            # Was a bare 19, another line height tied to the old label size.
            y1 = max(y1, ny + nh + 8 + lines * label_line_h(px) + 8)

    return x0, y0, x1 - x0, y1 - y0


def write(diagram: Diagram, icons: IconResolver, out_dir: Path) -> Path:
    xml = build(diagram, icons)
    path = out_dir / f"{diagram.id}.drawio"
    path.write_text(xml, encoding="utf-8")
    # Hard gate: drawio discards everything after a malformed cell and still
    # exports, so a broken write is invisible without re-parsing. This is our
    # own output, not untrusted XML.
    ET.parse(path)  # nosec B314
    return path


# ------------------------------------------------------------- translation ----
# CJK ideographs, kana, and the full-width punctuation these diagrams use.
CJK_RE = re.compile(r"[\u2460-\u24FF\u3000-\u303F\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\uFF00-\uFFEF]")


def translate_diagram(diagram: Diagram, mapping: dict[str, str]) -> Diagram:
    """Return an English variant of a spec.

    Translating the spec rather than the emitted XML means the layout is recomputed
    and every check re-runs against the English strings, which are usually wider
    than their Japanese equivalents — a string substitution on the finished XML
    would silently leave labels overlapping.
    """

    def tr(text: str, where: str) -> str:
        if not text:
            return text
        out = mapping.get(text, text)
        if CJK_RE.search(out):
            raise ValueError(
                f"{diagram.id}: no English text for {where}: {text!r}"
                if out == text
                else f"{diagram.id}: English text for {where} still has CJK: {out!r}"
            )
        return out

    return replace(
        diagram,
        id=f"{diagram.id}-en",
        name=f"{diagram.name} (EN)",
        title=tr(diagram.title, "title"),
        note_lang="en",
        nodes=[replace(n, label=tr(n.label, f"node {n.id}")) for n in diagram.nodes],
        edges=[replace(e, label=tr(e.label, f"edge {e.source}->{e.target}")) for e in diagram.edges],
        groups=[replace(g, label=tr(g.label, f"group {g.id}")) for g in diagram.groups],
        sections=[replace(s, label=tr(s.label, f"section {s.id}")) for s in diagram.sections],
        notes=[
            (tr(head, f"note {i} headline"), tr(detail, f"note {i} detail"))
            for i, (head, detail) in enumerate(diagram.notes, start=1)
        ],
    )
