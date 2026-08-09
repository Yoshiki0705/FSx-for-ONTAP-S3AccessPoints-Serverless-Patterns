#!/usr/bin/env python3
"""Generate agent-readable preview PNGs from exported diagram PNGs.

Why this exists
---------------
Exported diagrams are PNG@2x for blog use, so most of them are wider or taller
than 2000 px. Agent image inputs are rejected when either dimension exceeds
2000 px ("At least one of the image dimensions exceed max allowed size for
many-image requests: 2000 pixels"), which makes visual verification impossible
against the published asset directly.

This script writes downscaled copies (long edge <= --max-dim, default 1800 px)
into a scratch directory. Read those for visual checks; never commit them.

Usage
-----
    python3 scripts/preview-diagram.py                       # all part2/part3
    python3 scripts/preview-diagram.py part3-agentchat-modes # single diagram
    python3 scripts/preview-diagram.py --glob 'docs/images/png/*.png'

Output defaults to /tmp/diagram-previews/<name>.png and the resolved paths are
printed one per line.
"""

from __future__ import annotations

import argparse
import glob as globlib
import sys
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GLOB = "docs/images/png/part[23]-*.png"
# Previews are deliberately written outside the repository so they cannot be
# committed; AGENTS.md documents them as /tmp output.
DEFAULT_OUT = Path("/tmp/diagram-previews")  # nosec B108
DEFAULT_MAX_DIM = 1800


def preview(src: Path, out_dir: Path, max_dim: int) -> tuple[Path, str]:
    """Write a downscaled copy of ``src`` and return (path, description)."""
    with Image.open(src) as img:
        width, height = img.size
        longest = max(width, height)
        if longest <= max_dim:
            scale = 1.0
            resized = img.copy()
        else:
            scale = max_dim / longest
            resized = img.resize(
                (max(1, round(width * scale)), max(1, round(height * scale))),
                Image.LANCZOS,
            )
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / f"{src.stem}.png"
        resized.save(dest, optimize=True)
        note = f"{src.name}: {width}x{height} -> {resized.width}x{resized.height} (scale {scale:.3f})"
    return dest, note


def resolve_sources(names: list[str], pattern: str) -> list[Path]:
    if names:
        found: list[Path] = []
        for name in names:
            candidate = Path(name)
            if candidate.is_file():
                found.append(candidate)
                continue
            stem = candidate.stem.removesuffix("@2x")
            matches = sorted(Path(p) for p in globlib.glob(str(REPO_ROOT / f"docs/images/png/{stem}*.png")))
            if not matches:
                print(f"NOT FOUND: {name}", file=sys.stderr)
            found.extend(matches)
        return found
    return sorted(Path(p) for p in globlib.glob(str(REPO_ROOT / pattern)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "names",
        nargs="*",
        help="Diagram names or PNG paths. Default: all part2/part3 exports.",
    )
    parser.add_argument("--glob", default=DEFAULT_GLOB, help="Glob relative to repo root.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--max-dim", type=int, default=DEFAULT_MAX_DIM)
    args = parser.parse_args()

    sources = resolve_sources(args.names, args.glob)
    if not sources:
        print("No source PNGs matched.", file=sys.stderr)
        return 1

    for src in sources:
        dest, note = preview(src, args.out_dir, args.max_dim)
        print(f"{dest}  # {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
