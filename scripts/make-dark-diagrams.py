#!/usr/bin/env python3
"""Derive dark-theme diagram sources from the light-theme originals.

Why a separate source instead of a CSS/SVG trick
------------------------------------------------
The published SVGs are pinned to one fixed rendering (see
`scripts/pin-svg-theme.py`), because draw.io's dark-mode-adaptive export
flips the canvas and label colours but leaves the embedded AWS Architecture
Icons untouched — measured: 0 of 24 icon elements carry `light-dark()`. A theme
that only recolours the canvas therefore produces navy line art on a near-black
background, which is unreadable.

A genuine dark variant has to swap the icon artwork too. The official asset
package ships `Res_*_48_Dark.svg` (white artwork) alongside `Res_*_48_Light.svg`
(navy artwork), so this script rebuilds the diagram source with the Dark icon
payloads and a dark palette, and the normal export path then produces a second
set of assets. Light stays the primary published theme; dark is the opt-in one.

Scope of the transform
----------------------
1. Icon payloads: `Res_*_48_Light.svg` base64 -> `Res_*_48_Dark.svg` base64.
   `Arch_*_64.svg` service icons and the S3 Access Point resource icon ship in a
   single coloured-tile form and are legible on both themes, so they are left
   alone — matching the official guidance not to recolour service icons.
2. Canvas, surfaces and ink: white/near-white -> dark greys, squid ink -> off-white.
3. Accent strokes: AWS brand hues are kept, but the darker ones are lightened to
   hold contrast against a dark surface. Hue is preserved so the two themes stay
   recognisably the same diagram.

Generated output is written to `docs/diagrams/dark/` and must not be hand-edited;
edit the light source (or its builder spec) and re-run.

Usage:
    python3 scripts/make-dark-diagrams.py --icon-root /tmp/awsicons
    python3 scripts/make-dark-diagrams.py --icon-root /tmp/awsicons --check
"""

from __future__ import annotations

import argparse
import base64
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "docs" / "diagrams"
OUT_DIR = SRC_DIR / "dark"

AWS_ICON_PACKAGE_URL = "https://aws.amazon.com/architecture/icons/  (Asset Package, e.g. Icon-package_04302026)"

# Resource icons that ship a matched Light/Dark pair. Service icons (Arch_*) and
# the S3 Access Point resource icon have no variant and stay as-is.
ICON_VARIANT_PAIRS = [
    ("Res_Users_48_Light.svg", "Res_Users_48_Dark.svg"),
    ("Res_Client_48_Light.svg", "Res_Client_48_Dark.svg"),
    ("Res_Server_48_Light.svg", "Res_Server_48_Dark.svg"),
]

CANVAS = "#161B22"  # page background
SURFACE = "#21262D"  # default box fill (was #FFFFFF)
SURFACE_ALT = "#2D333B"  # secondary/grey box fill (was #F5F5F5)
INK = "#E6EDF3"  # label text, borders, arrows (was #232F3E squid ink)

# Light fill -> dark tint of the same hue. Kept dark enough that INK text on top
# clears WCAG AA, while the hue still signals the same grouping as the light theme.
PALETTE: dict[str, str] = {
    "#FFFFFF": SURFACE,
    "#F5F5F5": SURFACE_ALT,
    "#232F3E": INK,
    # pastel category fills
    "#EDF3FB": "#152A3E",  # blue
    "#EDF6EC": "#16301C",  # green
    "#FEF3E6": "#3A2412",  # orange
    "#FFFBE6": "#332B0D",  # yellow
    "#FDEDEE": "#3A1A1D",  # red
    "#E6F6F4": "#10302C",  # teal
    # accent strokes: hue preserved, luminance raised where needed for dark bg
    "#2E73B8": "#589BE5",  # blue
    "#3F8624": "#57A83A",  # green
    "#B7950B": "#D9B310",  # yellow
    "#DD344C": "#F26D7D",  # red
    "#8C4FFF": "#A97BFF",  # purple
    "#01A88D": "#2BC4A9",  # teal
    "#ED7100": "#ED7100",  # AWS orange already clears contrast on dark
}

HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}")
BACKGROUND_RE = re.compile(r'(<mxGraphModel\b[^>]*?\bbackground=")([^"]*)(")')


def find_icon(icon_root: Path, filename: str) -> Path:
    hits = list(icon_root.rglob(filename))
    if not hits:
        raise FileNotFoundError(f"{filename} not found under {icon_root}")
    return hits[0]


def data_uri_payload(path: Path) -> str:
    """Base64 payload exactly as the diagram builders embed it."""
    return base64.b64encode(path.read_bytes()).decode("ascii")


def build_icon_map(icon_root: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for light_name, dark_name in ICON_VARIANT_PAIRS:
        light = data_uri_payload(find_icon(icon_root, light_name))
        dark = data_uri_payload(find_icon(icon_root, dark_name))
        mapping[light] = dark
    return mapping


def recolour(xml: str) -> tuple[str, int]:
    """Map every light palette colour to its dark counterpart.

    Runs on hex tokens rather than whole attributes so that both style strings
    (`fillColor=#FFFFFF`) and the lowercase `labelBackgroundColor=#ffffff` are
    covered. Base64 icon payloads cannot contain `#`, so they are unaffected.
    """
    count = 0

    def sub(m: re.Match[str]) -> str:
        nonlocal count
        token = m.group(0).upper()
        replacement = PALETTE.get(token)
        if replacement is None or replacement == token:
            return m.group(0)
        count += 1
        return replacement

    return HEX_RE.sub(sub, xml), count


def convert(src: Path, icon_map: dict[str, str]) -> tuple[str, dict[str, int]]:
    xml = src.read_text(encoding="utf-8")

    icons = 0
    for light_payload, dark_payload in icon_map.items():
        hits = xml.count(light_payload)
        if hits:
            xml = xml.replace(light_payload, dark_payload)
            icons += hits

    # The canvas attribute is set before the generic pass so an explicit
    # `background="#FFFFFF"` becomes the page colour, not a box surface colour.
    xml, canvas_hits = BACKGROUND_RE.subn(rf"\g<1>{CANVAS}\g<3>", xml)
    xml, colours = recolour(xml)

    stats = {"icons": icons, "canvas": canvas_hits, "colours": colours}
    return xml, stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--icon-root",
        required=True,
        help="Local extraction of the official AWS Architecture Icons asset package",
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="report without writing; exit 1 if any output would change",
    )
    args = ap.parse_args()

    icon_root = Path(args.icon_root)
    if not icon_root.is_dir():
        print(f"ERROR: --icon-root not a directory: {icon_root}", file=sys.stderr)
        print(f"Download the asset package from {AWS_ICON_PACKAGE_URL}", file=sys.stderr)
        return 1

    icon_map = build_icon_map(icon_root)
    sources = sorted(SRC_DIR.glob("*.drawio"))
    if not sources:
        print(f"ERROR: no .drawio sources in {SRC_DIR}", file=sys.stderr)
        return 1

    if not args.check:
        OUT_DIR.mkdir(parents=True, exist_ok=True)

    stale = 0
    failed = False
    for src in sources:
        dest = OUT_DIR / src.name
        xml, stats = convert(src, icon_map)

        try:
            ET.fromstring(xml)
            status = "XML OK"
        except ET.ParseError as exc:
            status = f"XML BROKEN -> {exc}"
            failed = True

        existing = dest.read_text(encoding="utf-8") if dest.is_file() else None
        changed = existing != xml
        if changed and not args.check and not failed:
            dest.write_text(xml, encoding="utf-8")
        if changed and args.check:
            stale += 1

        state = "stale" if args.check and changed else "written" if changed else "up to date"
        print(
            f"  {src.name}: {state} "
            f"(icons={stats['icons']} canvas={stats['canvas']} colours={stats['colours']})"
            f"  {status}"
        )

    if failed:
        return 1
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
