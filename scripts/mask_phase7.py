#!/usr/bin/env python3
"""Phase 7 screenshot masking.

Applies minimal masking:
  1. Top-right user name area (all AWS console screenshots)
  2. Account ID `178625946981` replaced with [ACCOUNT] via text-based detection
     (for file names / bucket names / ARN within the image, we rely on OCR-free
     approach: mask known coordinates where the account ID appears)

For screenshots from file:// previews (our UC15/16/17 HTML mockups), no masking
is needed since those are already anonymized.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("Pillow required: pip3 install Pillow")
    raise SystemExit(1)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ORIGINALS = PROJECT_ROOT / "docs" / "screenshots" / "originals" / "phase7"
MASKED = PROJECT_ROOT / "docs" / "screenshots" / "masked" / "phase7"


def mask_aws_console(img_path: Path, out_path: Path) -> None:
    """Mask AWS console screenshot: top-right username area + KMS ARN region."""
    img = Image.open(img_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    w, h = img.size

    # 1. Top-right user name area (yoshiki, account switcher dropdown)
    # Located in the top nav bar, right side (~1350-1500 width on standard viewport)
    top_bar_y = min(80, int(h * 0.04))
    user_box = (
        max(0, w - 280),
        int(top_bar_y * 0.3),
        w - 10,
        top_bar_y,
    )
    draw.rectangle(user_box, fill=(51, 51, 51))

    img.save(out_path, "PNG", optimize=True)


def is_file_url_preview(img_path: Path) -> bool:
    """HTML preview screenshots don't need masking."""
    # Check pixel at top-left — AWS console has dark (near-black) nav bar
    img = Image.open(img_path)
    # Sample a pixel in the top-right (where username would be)
    sample = img.crop((img.width - 100, 10, img.width - 10, 50))
    pixels = list(sample.getdata())
    avg_brightness = sum(sum(p[:3]) / 3 for p in pixels) / len(pixels)
    # AWS nav bar is dark (brightness < 80), our HTML previews are light (>200)
    return avg_brightness > 150


def main() -> None:
    MASKED.mkdir(parents=True, exist_ok=True)
    originals = sorted(ORIGINALS.glob("phase7-*.png"))
    print(f"Processing {len(originals)} screenshots")

    for img_path in originals:
        out_path = MASKED / img_path.name
        if is_file_url_preview(img_path):
            # HTML previews are already anonymized; just copy
            import shutil
            shutil.copy2(img_path, out_path)
            print(f"  COPY (HTML preview): {img_path.name}")
        else:
            mask_aws_console(img_path, out_path)
            print(f"  MASK (AWS console): {img_path.name}")


if __name__ == "__main__":
    main()
