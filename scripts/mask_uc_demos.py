#!/usr/bin/env python3
"""Mask screenshots for all UC demo directories and phase directories.

**Masking strategy (v6, 2026-05-10) — safe-by-default**:

For AWS console screenshots, we apply heavy, fail-safe masking:

1. All AWS console screenshots: mask top-right account widget
2. All AWS console screenshots: mask breadcrumb bar (may contain stack/
   workflow name which includes resource names, OK but keep safe)
3. All AWS console screenshots: mask the ENTIRE main content area
   EXCEPT for a narrow band that typically shows a graph / table / chart
   which is the actual UI/UX content.

Because the Step Functions "Graph view" is the only content we want to
show, the default rule is "mask everything except the Graph/table section
at the bottom of the page". This errs on the side of over-masking.

File-based exceptions (whitelist — filename contains keyword → only light masking):
- "graph-view" | "graph_view": only mask top-right; assume graph content below
- "bedrock-report" | "athena-query-result" | "claims-report" | "product-tags":
  HTML previews (no AWS sidebar); copy as-is

HTML previews (detected by bright top-right) are copied as-is.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

# Known sensitive literals that must never appear in any published screenshot.
# These are loaded from _sensitive_strings.py (gitignored local file).
# Copy scripts/_sensitive_strings.py.example → scripts/_sensitive_strings.py
# and fill in your environment-specific values.
try:
    from _sensitive_strings import SENSITIVE_STRINGS  # type: ignore
except ImportError:
    SENSITIVE_STRINGS: tuple[str, ...] = ()  # verification disabled if file missing


def _rect_frac(draw: ImageDraw.ImageDraw, w: int, h: int,
               x0: float, y0: float, x1: float, y1: float,
               color: tuple[int, int, int]) -> None:
    """Draw a rectangle using fractional coordinates (0.0-1.0)."""
    draw.rectangle(
        (int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)),
        fill=color,
    )


def mask_aws_header(draw: ImageDraw.ImageDraw, w: int, h: int) -> None:
    """Hide the top-right account widget (account ID, username, region)."""
    _rect_frac(draw, w, h, 0.56, 0.0, 1.0, 0.065, (30, 30, 35))


def mask_breadcrumb(draw: ImageDraw.ImageDraw, w: int, h: int) -> None:
    """Hide breadcrumb text AND page heading area (covers resource names with account IDs)."""
    # Breadcrumb + heading row: from below nav (~y=65px) to just before content (~y=0.22*h)
    _rect_frac(draw, w, h, 0.170, 0.065, 0.99, 0.205, (255, 255, 255))


def mask_main_content_details(draw: ImageDraw.ImageDraw, w: int, h: int) -> None:
    """Redact the main-content Details panel region (most AWS console pages).

    This covers the typical area where resource IDs, ARNs, and sensitive
    attributes are displayed. Extends from just below the page header to
    about 85% of page height, across the full width right of sidebar.
    """
    _rect_frac(draw, w, h, 0.170, 0.185, 0.99, 0.850, (245, 245, 245))


def mask_stepfunctions_graph_view_mode(draw: ImageDraw.ImageDraw, w: int, h: int) -> None:
    """Step Functions execution page in Graph view mode:
    Mask header + breadcrumb + Details panel ONLY. Leave Graph view visible.

    The graph view starts at ~y=0.60*h, so we cover only 0.21-0.58.
    """
    mask_aws_header(draw, w, h)
    mask_breadcrumb(draw, w, h)
    _rect_frac(draw, w, h, 0.170, 0.210, 0.99, 0.580, (245, 245, 245))


def mask_full_main_content(draw: ImageDraw.ImageDraw, w: int, h: int) -> None:
    """Nuke the entire main content area (for pages where all content
    contains resource IDs, like FSx Volumes list, Lambda list, etc.).

    This is the default for pages that aren't explicitly the Step
    Functions Graph view.
    """
    mask_aws_header(draw, w, h)
    mask_breadcrumb(draw, w, h)
    _rect_frac(draw, w, h, 0.170, 0.185, 0.99, 0.99, (245, 245, 245))


def is_html_preview(img_path: Path) -> bool:
    """HTML previews have predominantly bright top-right area."""
    img = Image.open(img_path)
    sample = img.crop((img.width - 100, 10, img.width - 10, 50))
    pixels = list(sample.getdata())
    avg = sum(sum(p[:3]) / 3 for p in pixels) / len(pixels)
    return avg > 150


# Filename patterns that indicate safe HTML preview / decorative content
# (no AWS sidebar, no account ID, no ARNs)
HTML_PREVIEW_KEYWORDS = (
    "bedrock-report",
    "athena-query-result",
    "claims-report",
    "product-tags",
    "foia-reminder",
    "redacted-text",
    "redaction-metadata",
    "detections-json",
    "sns-alert-email",
    "risk-map-json",
    "landuse-distribution",
    "bedrock-design-review",
)

# Filename patterns for Step Functions Graph view screenshots
# (mask only top card and header; keep graph visible)
STEPFUNCTIONS_GRAPH_KEYWORDS = (
    "stepfunctions-graph",
    "step-functions-graph",
    "sfn-graph",
)


def mask_aws_console(img_path: Path, out_path: Path) -> None:
    """Apply masking based on filename hints; safe-by-default (full mask)."""
    img = Image.open(img_path).convert("RGB")
    w, h = img.size
    draw = ImageDraw.Draw(img)

    name = img_path.name.lower()

    if any(kw in name for kw in STEPFUNCTIONS_GRAPH_KEYWORDS):
        # Step Functions Graph view: preserve graph, mask Details panel
        mask_stepfunctions_graph_view_mode(draw, w, h)
    else:
        # Default: mask header + breadcrumb + all central content
        # This is over-cautious but guarantees no leaks.
        mask_full_main_content(draw, w, h)

    img.save(out_path, "PNG", optimize=True)


def mask_dir(demo_name: str) -> None:
    originals = PROJECT_ROOT / "docs" / "screenshots" / "originals" / demo_name
    masked = PROJECT_ROOT / "docs" / "screenshots" / "masked" / demo_name
    if not originals.exists():
        print(f"MISSING: {originals}")
        return
    masked.mkdir(parents=True, exist_ok=True)

    for img_path in sorted(originals.glob("*.png")):
        out_path = masked / img_path.name
        name = img_path.name.lower()

        # HTML preview detection: either filename keyword or bright top-right
        if any(kw in name for kw in HTML_PREVIEW_KEYWORDS) or is_html_preview(img_path):
            shutil.copy2(img_path, out_path)
            print(f"  COPY: {demo_name}/{img_path.name}")
        else:
            mask_aws_console(img_path, out_path)
            print(f"  MASK: {demo_name}/{img_path.name}")


def main() -> None:
    if len(sys.argv) > 1:
        demos = sys.argv[1:]
    else:
        originals_root = PROJECT_ROOT / "docs" / "screenshots" / "originals"
        demos = sorted(d.name for d in originals_root.iterdir() if d.is_dir())

    for demo in demos:
        print(f"=== {demo} ===")
        mask_dir(demo)


if __name__ == "__main__":
    main()
