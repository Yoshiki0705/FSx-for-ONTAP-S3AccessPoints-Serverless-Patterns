#!/usr/bin/env python3
"""Pin an exported draw.io SVG to the theme its source actually authored.

Why
---
draw.io exports SVG with `color-scheme: light dark` and wraps every colour in
`light-dark(<authored>, <auto-inverted>)`, so a viewer's OS theme silently
restyles the canvas and the label text. The embedded AWS Architecture Icons are
raster-embedded artwork and carry no such adaptation — measured: 24 of 24 icon
elements have no `light-dark()`. Auto-inverting everything *except* the icons
leaves navy line art on a near-black canvas, so the adaptive export is broken by
construction.

Resolving every `light-dark()` to its first (authored) value yields one fixed
rendering that matches the icon artwork in the source. Applied to a light source
that is a white diagram with navy icons; applied to a dark source (see
`scripts/make-dark-diagrams.py`, which swaps in the `Res_*_48_Dark` artwork) it
is a dark diagram with white icons. Both themes are therefore stable regardless
of the reader's OS setting, and the choice of theme stays an explicit editorial
one rather than an accident of the viewer.

Usage:
    python3 scripts/pin-svg-theme.py docs/images/*.svg
    python3 scripts/pin-svg-theme.py --check docs/images/foo.svg
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

FUNC = "light-dark("


def _split_top_level(text: str) -> tuple[str, str]:
    """Split `a, b` on the comma that is not inside nested parentheses.

    Needed because the light value can itself be a function call, as in
    `light-dark(rgb(245, 245, 245), rgb(18, 18, 18))`.
    """
    depth = 0
    for i, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            return text[:i], text[i + 1 :]
    raise ValueError(f"no top-level comma in {text!r}")


def resolve_light_dark(svg: str) -> tuple[str, int]:
    """Replace every `light-dark(authored, auto)` with its authored value."""
    out: list[str] = []
    i = 0
    count = 0
    while True:
        start = svg.find(FUNC, i)
        if start == -1:
            out.append(svg[i:])
            break
        out.append(svg[i:start])
        # scan to the matching close paren
        depth = 0
        j = start + len(FUNC) - 1
        for j in range(start + len(FUNC) - 1, len(svg)):
            if svg[j] == "(":
                depth += 1
            elif svg[j] == ")":
                depth -= 1
                if depth == 0:
                    break
        else:
            raise ValueError("unbalanced light-dark() call")
        authored, _auto = _split_top_level(svg[start + len(FUNC) : j])
        out.append(authored.strip())
        count += 1
        i = j + 1
    return "".join(out), count


def pin(path: Path, check_only: bool = False) -> tuple[int, bool]:
    original = path.read_text(encoding="utf-8")
    pinned, count = resolve_light_dark(original)
    # `color-scheme` alone would still let a viewer restyle the canvas.
    pinned = pinned.replace("color-scheme: light dark;", "color-scheme: light;")
    changed = pinned != original
    if changed and not check_only:
        ET.fromstring(pinned)  # hard gate: never write a malformed SVG
        path.write_text(pinned, encoding="utf-8")
    return count, changed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument(
        "--check",
        action="store_true",
        help="report without writing; exit 1 if any file still adapts",
    )
    args = ap.parse_args()

    pending = 0
    for path in args.paths:
        if not path.is_file():
            print(f"SKIP (missing): {path}", file=sys.stderr)
            continue
        count, changed = pin(path, check_only=args.check)
        state = "would pin" if args.check and changed else "pinned" if changed else "already pinned"
        print(f"  {path.name}: {state} ({count} light-dark() calls)")
        if args.check and changed:
            pending += 1
    return 1 if pending else 0


if __name__ == "__main__":
    raise SystemExit(main())
