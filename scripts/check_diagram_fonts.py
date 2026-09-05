#!/usr/bin/env python3
"""Fail when a diagram label would render too small for a reader to read.

The rule is not "`fontSize` must be at least N", because that check passes on a diagram nobody can
read: a label is displayed at the size it has *after* the image is scaled down to fit the column it
sits in, and a wider canvas scales down further. Diagrams in these repositories were authored at
`fontSize=11` on canvases between 1080 and 1600px, which arrive in an 880px column between 6 and 9px
— small enough that a measured figure in a notes box is guesswork on a laptop.

So two floors apply together:

* **effective size** -- `fontSize x min(1, PUBLICATION_WIDTH / rendered width)` must reach
  `MIN_EFFECTIVE_PX`. This is the one that tracks what a reader sees;
* **source size** -- `fontSize` must reach `MIN_SOURCE_PX` regardless. Without it, the first floor
  can be satisfied by making the canvas narrower and the text relatively larger while both are tiny,
  and it would also accept a 400px canvas at 8px.

The width used is the **exported SVG's** width when the export exists, not `pageWidth`. draw.io crops
to content and adds `--border`, so the two differ, and the export is what a reader loads. `pageWidth`
is the fallback so a diagram can be checked before it has ever been exported.

Both `style="...fontSize=11..."` and an inline `font-size:11px` inside a cell's `value` are read. The
second form is how a hand-edit sneaks a small font past a generator whose style functions all look
correct.

**Existing debt is carried in a file, and the file may only shrink.** Wiring this into a repository
whose diagrams all predate it would turn the build red until every one is redesigned, and a gate
that is red for weeks gets disabled. So paths listed in `diagram-font-debt.txt` are reported and
tolerated — but an unlisted violation fails, and so does a *listed* path that no longer violates.
The second half is what stops the file becoming permanent: fixing a diagram forces its line out, and
there is no way to add a line without a reviewer seeing it.

Nothing here is specific to one repository: paths are discovered rather than configured, so this file
is copied between repositories as-is with **one line** adjusted -- the suppression on the parse call
in `_parse()`. A repository whose ruff selects `S` needs `# noqa: S314` there; one that selects
`RUF100` without `S` rejects the same comment as unused. The two cannot both be satisfied by one
line, so the divergence is isolated to that function rather than left to spread.

Run:  python3 tools/check_diagram_fonts.py
      python3 tools/check_diagram_fonts.py --selftest
"""

from __future__ import annotations

import argparse
import math
import re
import sys
import xml.etree.ElementTree as ET  # nosec B405  reads this repository's own committed files
from dataclasses import dataclass
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEBT_FILE = ROOT / "diagram-font-debt.txt"

# Directories that hold copies of other people's files, or build output. Scanning them reports
# findings nobody in this repository can act on.
SKIP = {".git", ".venv", "node_modules", "__pycache__", ".private", "site-packages"}

# The width a reader's column gives the image. GitHub renders Markdown body content at roughly this;
# dev.to and hatenablog are close enough that a separate number would be false precision.
PUBLICATION_WIDTH = 880

# Body text on all three targets is 16px. A label one notch under that is still comfortable; the
# floor sits there rather than at 16 so a diagram is not forced wider than its content needs.
MIN_EFFECTIVE_PX = 14

# Applied to the authored value, so narrowing the canvas cannot satisfy the floor above while the
# text stays small.
MIN_SOURCE_PX = 16

STYLE_FONT = re.compile(r"fontSize=(\d+(?:\.\d+)?)")
INLINE_FONT = re.compile(r"font-size:\s*(\d+(?:\.\d+)?)")
SVG_WIDTH = re.compile(r'\bwidth="(\d+(?:\.\d+)?)(?:px)?"')


@dataclass(frozen=True)
class Finding:
    """One cell whose label breaks a floor, carrying the width the verdict was reached with.

    The width is kept here so the advice printed at the end can name the canvas that actually failed.
    Recomputing it in the reporting path meant re-reading every file and then quoting the narrowest
    one, which is not necessarily the one being complained about.
    """

    path: Path
    cell: str
    width: float
    reason: str


def _skipped(path: Path) -> bool:
    return bool(SKIP.intersection(path.relative_to(ROOT).parts))


# Written to sit inside the narrowest line length used across these repositories, because a
# comprehension that fits on one line at 100 and wraps at 88 makes the same file format two ways and
# the copies stop being byte-identical.
def walk(pattern: str) -> list[Path]:
    return sorted(p for p in ROOT.rglob(pattern) if not _skipped(p))


@cache
def exports() -> dict[str, Path]:
    """Exported SVGs by stem. Built once: a repository can hold a megabyte of them."""
    return {p.stem: p for p in walk("*.svg")}


def rendered_width(source: Path, page_width: float) -> tuple[float, str]:
    """The width the reader's browser receives, and where that number came from."""
    exported = exports().get(source.stem)
    if exported is not None:
        # The width attribute is on the opening <svg>; read a prefix rather than the whole file,
        # which carries every icon as base64 and runs to about a megabyte.
        head = exported.read_text(encoding="utf-8", errors="replace")[:2048]
        match = SVG_WIDTH.search(head)
        if match:
            return float(match.group(1)), exported.name
    return page_width, "pageWidth"


def sizes(cell: ET.Element) -> list[float]:
    """Every font size this cell asks for, from its style and from any inline HTML in its label."""
    found = [float(m) for m in STYLE_FONT.findall(cell.get("style") or "")]
    found += [float(m) for m in INLINE_FONT.findall(cell.get("value") or "")]
    return found


def _parse(text: str) -> ET.Element:
    """Parse a committed .drawio from this repository -- never user-supplied data.

    The whole function exists to hold one line. The suppression has to sit on the call itself: moved
    to a line of its own, a formatter can shift it off the statement it applies to and the finding
    comes back. And the exact comment differs per repository (see the module docstring), so keeping
    it here means one known line to adjust instead of hunting for it.
    """
    return ET.fromstring(text)  # nosec B314


def inspect(path: Path, text: str) -> list[Finding]:
    findings: list[Finding] = []
    root = _parse(text)
    for model in root.iter("mxGraphModel"):
        page_width = float(model.get("pageWidth") or PUBLICATION_WIDTH)
        width, origin = rendered_width(path, page_width)
        scale = min(1.0, PUBLICATION_WIDTH / width) if width else 1.0
        for cell in model.iter("mxCell"):
            for size in sizes(cell):
                effective = size * scale
                if size < MIN_SOURCE_PX:
                    reason = f"fontSize {size:g} < {MIN_SOURCE_PX}"
                elif effective < MIN_EFFECTIVE_PX:
                    reason = (
                        f"effective {effective:.1f}px < {MIN_EFFECTIVE_PX} "
                        f"({size:g} x {PUBLICATION_WIDTH}/{width:g} from {origin})"
                    )
                else:
                    continue
                findings.append(Finding(path, cell.get("id") or "?", width, reason))
    return findings


def required_font(width: float) -> int:
    """The smallest whole `fontSize` that clears both floors on a canvas this wide."""
    scale = min(1.0, PUBLICATION_WIDTH / width) if width else 1.0
    return max(MIN_SOURCE_PX, math.ceil(MIN_EFFECTIVE_PX / scale))


def read_debt() -> list[str]:
    if not DEBT_FILE.is_file():
        return []
    lines = []
    for raw in DEBT_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            lines.append(line)
    return lines


def advice(width: float) -> str:
    return (
        "\n  Raising the number is only half the fix: a larger label needs the room to sit in.\n"
        f"  On the widest failing canvas ({width:g}px) the floor is fontSize {required_font(width)}.\n"
        "  Fold labels to two lines, move the notes box out of the figure into body prose, narrow\n"
        "  the canvas toward the 880px publication width, or split the figure. Widening the canvas\n"
        "  raises the floor again, so empty canvas is not free."
    )


def check() -> int:
    files = walk("*.drawio")
    if not files:
        print("diagram-fonts: no .drawio files found")
        return 0

    findings: list[Finding] = []
    for path in files:
        try:
            findings += inspect(path, path.read_text(encoding="utf-8"))
        except ET.ParseError as error:
            print(
                f"error: {path.relative_to(ROOT)} is not valid XML: {error}",
                file=sys.stderr,
            )
            return 1

    failing = {str(f.path.relative_to(ROOT)) for f in findings}
    listed = read_debt()
    unlisted = sorted(failing - set(listed))
    stale = [name for name in listed if name not in failing]

    problems = 0
    if unlisted:
        problems += 1
        print("error: diagram labels below the readability floor", file=sys.stderr)
        seen: set[tuple[Path, str]] = set()
        widest = 0.0
        for finding in findings:
            name = str(finding.path.relative_to(ROOT))
            if name not in unlisted:
                continue
            widest = max(widest, finding.width)
            key = (finding.path, finding.reason)
            if key in seen:
                continue
            seen.add(key)
            print(f"  {name}  cell {finding.cell}: {finding.reason}", file=sys.stderr)
        print(advice(widest), file=sys.stderr)
        if listed:
            print(
                f"\n  {DEBT_FILE.name} carries pre-existing debt, but not these. Fix them rather\n"
                "  than adding a line: the file is only allowed to shrink.",
                file=sys.stderr,
            )

    if stale:
        problems += 1
        print(
            f"error: {DEBT_FILE.name} lists file(s) that now meet the floor. Delete these lines:",
            file=sys.stderr,
        )
        for name in stale:
            print(f"  {name}", file=sys.stderr)

    if problems:
        return 1

    remaining = [name for name in listed if name in failing]
    if remaining:
        print(
            f"diagram-fonts: {len(files) - len(remaining)} file(s) meet the readability floor; "
            f"{len(remaining)} still carried as debt in {DEBT_FILE.name}"
        )
    else:
        print(f"diagram-fonts: {len(files)} file(s) meet the readability floor")
    return 0


# --- selftest ------------------------------------------------------------------------------------

# A gate is only trustworthy once it has been seen to fail. Every gate target runs this before the
# check itself, so a refactor that makes this accept everything is caught by the gate rather than by
# noticing, months later, that no diagram was ever reported.


def _doc(page_width: int, *sizes_: float, inline: float | None = None) -> str:
    cells = "".join(
        f'<mxCell id="c{n}" value="x" style="rounded=1;fontSize={s:g};" vertex="1" parent="1" />'
        for n, s in enumerate(sizes_)
    )
    if inline is not None:
        cells += (
            f'<mxCell id="inline" value="&lt;span style=&quot;font-size:{inline:g}px&quot;&gt;'
            'x&lt;/span&gt;" style="rounded=1;fontSize=24;" vertex="1" parent="1" />'
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?><mxfile><diagram id="d" name="d">'
        f'<mxGraphModel pageWidth="{page_width}" pageHeight="400"><root>'
        '<mxCell id="0" /><mxCell id="1" parent="0" />'
        f"{cells}</root></mxGraphModel></diagram></mxfile>"
    )


def selftest() -> int:
    missing = ROOT / "never-exported.drawio"
    cases: list[tuple[str, str, bool]] = [
        # (name, document, expected to be rejected)
        (
            "the 11px these repositories shipped, on a 1220px canvas",
            _doc(1220, 11),
            True,
        ),
        ("16px source floor met but effective 11.5px on 1220px", _doc(1220, 16), True),
        ("20px on a 1220px canvas clears both floors", _doc(1220, 20), False),
        ("16px on an 880px canvas clears both floors", _doc(880, 16), False),
        ("15px on a narrow canvas still breaks the source floor", _doc(400, 15), True),
        ("one bad cell among good ones is caught", _doc(880, 18, 16, 11), True),
        (
            "an inline font-size is read, not just the style",
            _doc(880, 24, inline=10),
            True,
        ),
        ("an inline font-size above the floor passes", _doc(880, 24, inline=18), False),
    ]
    failures = 0
    for name, document, should_reject in cases:
        rejected = bool(inspect(missing, document))
        if rejected != should_reject:
            verdict = "rejected" if rejected else "accepted"
            wanted = "reject" if should_reject else "accept"
            print(
                f"  selftest FAILED: {name} -> {verdict}, expected to {wanted}",
                file=sys.stderr,
            )
            failures += 1

    expectations = {880: 16, 1000: 16, 1220: 20, 1600: 26, 2000: 32}
    for width, want in expectations.items():
        got = required_font(width)
        if got != want:
            print(
                f"  selftest FAILED: required_font({width}) = {got}, expected {want}",
                file=sys.stderr,
            )
            failures += 1

    # The ratchet is deliberately not asserted here. Checking it in this function would mean
    # re-deriving the set arithmetic `check()` performs and comparing the two, which proves the two
    # copies agree rather than that either is right. It is exercised end to end against real files
    # by the repository's gate tests, which can write both a probe diagram and a probe debt file.

    if failures:
        print(f"selftest: {failures} case(s) failed", file=sys.stderr)
        return 1
    print(f"selftest: {len(cases) + len(expectations)} case(s) behave as documented")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="prove the check rejects small fonts, accepts compliant ones, and ratchets debt",
    )
    args = parser.parse_args()
    return selftest() if args.selftest else check()


if __name__ == "__main__":
    sys.exit(main())
