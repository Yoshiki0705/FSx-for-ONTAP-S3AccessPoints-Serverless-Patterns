#!/usr/bin/env python3
"""Mask screenshots for all UC demo directories (UC6, UC11, UC14, etc).

Auto-detects AWS console vs HTML preview and applies appropriate masking.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def mask_aws_console(img_path: Path, out_path: Path) -> None:
    img = Image.open(img_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    w, _ = img.size
    draw.rectangle((max(0, w - 280), 24, w - 10, 80), fill=(51, 51, 51))
    img.save(out_path, "PNG", optimize=True)


def is_html_preview(img_path: Path) -> bool:
    img = Image.open(img_path)
    sample = img.crop((img.width - 100, 10, img.width - 10, 50))
    pixels = list(sample.getdata())
    avg = sum(sum(p[:3]) / 3 for p in pixels) / len(pixels)
    return avg > 150


def mask_dir(demo_name: str) -> None:
    originals = PROJECT_ROOT / "docs" / "screenshots" / "originals" / demo_name
    masked = PROJECT_ROOT / "docs" / "screenshots" / "masked" / demo_name
    if not originals.exists():
        print(f"MISSING: {originals}")
        return
    masked.mkdir(parents=True, exist_ok=True)

    for img_path in sorted(originals.glob("*.png")):
        out_path = masked / img_path.name
        if is_html_preview(img_path):
            shutil.copy2(img_path, out_path)
            print(f"  COPY: {demo_name}/{img_path.name}")
        else:
            mask_aws_console(img_path, out_path)
            print(f"  MASK: {demo_name}/{img_path.name}")


def main() -> None:
    if len(sys.argv) > 1:
        demos = sys.argv[1:]
    else:
        # auto-detect demo dirs
        originals_root = PROJECT_ROOT / "docs" / "screenshots" / "originals"
        demos = [d.name for d in originals_root.iterdir() if d.is_dir() and d.name.endswith("-demo")]

    for demo in demos:
        print(f"=== {demo} ===")
        mask_dir(demo)


if __name__ == "__main__":
    main()
