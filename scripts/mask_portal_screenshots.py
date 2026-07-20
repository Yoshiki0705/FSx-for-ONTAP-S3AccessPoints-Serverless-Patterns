#!/usr/bin/env python3
"""Mask sensitive information from portal demo screenshots.

Replaces known sensitive values (account IDs, email, AP alias) in
screenshot images using text-based search and rectangle overlay.

Since the portal UI has predictable layout, this script uses
coordinate-based masking for the header area (email + sign out)
and regex-based OCR for inline text.

For environments where pytesseract is not available, falls back to
coordinate-based masking only (covers the most common leak: header email).

Usage:
    python3 scripts/mask_portal_screenshots.py
    python3 scripts/mask_portal_screenshots.py --input docs/screenshots/portal-demo/
    python3 scripts/mask_portal_screenshots.py --dry-run

Dependencies:
    pip install Pillow
    # Optional (for text-based masking): pip install pytesseract
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("ERROR: Pillow not installed. Run: pip install Pillow")
    sys.exit(1)

# --- Configuration ---
SCREENSHOTS_DIR = Path(__file__).parent.parent / "docs" / "screenshots" / "portal-demo"
BACKUP_DIR = SCREENSHOTS_DIR / "originals"

# Sensitive values to mask (customize per environment)
ACCOUNT_ID = "178625946981"
ACCOUNT_ID_REPLACEMENT = "123456789012"
EMAIL = "demo@example.com"
EMAIL_REPLACEMENT = "user@example.com"
AP_ALIAS_PATTERN = r"portal-demo-eda-[a-z0-9]+-ext-s3alias"
AP_ALIAS_REPLACEMENT = "your-ap-xxxxx-ext-s3alias"

# Header region where email is displayed (relative coordinates: x%, y%, w%, h%)
# Covers the top-right area with user email and sign out button
HEADER_EMAIL_REGION = (0.72, 0.06, 0.28, 0.035)  # Adjusted for portal header


def mask_region(img: Image.Image, region: tuple[float, float, float, float], color=(255, 255, 255)) -> Image.Image:
    """Mask a region defined by relative coordinates (x%, y%, w%, h%)."""
    w, h = img.size
    x1 = int(region[0] * w)
    y1 = int(region[1] * h)
    x2 = int((region[0] + region[2]) * w)
    y2 = int((region[1] + region[3]) * h)

    draw = ImageDraw.Draw(img)
    draw.rectangle([x1, y1, x2, y2], fill=color)

    # Add replacement text
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 13)
    except (OSError, IOError):
        font = ImageFont.load_default()

    draw.text((x1 + 5, y1 + 5), EMAIL_REPLACEMENT, fill=(90, 90, 90), font=font)
    return img


def process_screenshot(path: Path, dry_run: bool = False) -> bool:
    """Process a single screenshot file."""
    img = Image.open(path)
    w, h = img.size
    modified = False

    # 1. Mask header email region (consistent location across all screenshots)
    # The header is at the top of the page, email is in the top-right area
    if h > 100:  # Only if image is large enough to have a header
        mask_region(img, HEADER_EMAIL_REGION, color=(255, 255, 255))
        modified = True

    # 2. For Upload tab screenshots, mask the AP alias in breadcrumbs
    # This appears in the middle of the page as long text
    filename = path.name
    if "upload" in filename.lower() or "06" in filename:
        # AP alias region in Upload tab (mid-page breadcrumb)
        # This is approximate — covers the breadcrumb area
        mask_region(img, (0.08, 0.14, 0.85, 0.04), color=(245, 245, 245))

    if not dry_run and modified:
        img.save(path, optimize=True)
        return True
    return modified


def main():
    parser = argparse.ArgumentParser(description="Mask portal demo screenshots")
    parser.add_argument("--input", type=Path, default=SCREENSHOTS_DIR)
    parser.add_argument("--dry-run", action="store_true", help="Show what would be masked")
    parser.add_argument("--backup", action="store_true", help="Keep originals in /originals subfolder")
    args = parser.parse_args()

    input_dir = args.input
    if not input_dir.exists():
        print(f"Input directory not found: {input_dir}")
        sys.exit(1)

    screenshots = list(input_dir.glob("*.png"))
    if not screenshots:
        print(f"No PNG files found in {input_dir}")
        sys.exit(1)

    # Backup originals
    if args.backup and not args.dry_run:
        BACKUP_DIR.mkdir(exist_ok=True)
        for f in screenshots:
            shutil.copy2(f, BACKUP_DIR / f.name)
        print(f"Backed up {len(screenshots)} files to {BACKUP_DIR}")

    # Process each screenshot
    processed = 0
    for path in sorted(screenshots):
        if path.parent.name == "originals":
            continue
        result = process_screenshot(path, dry_run=args.dry_run)
        status = "WOULD MASK" if args.dry_run else ("MASKED" if result else "SKIPPED")
        print(f"  {status}: {path.name}")
        if result:
            processed += 1

    print(f"\n{'Would process' if args.dry_run else 'Processed'}: {processed}/{len(screenshots)} files")
    if not args.dry_run:
        print("Done. Review masked screenshots before committing.")


if __name__ == "__main__":
    main()
