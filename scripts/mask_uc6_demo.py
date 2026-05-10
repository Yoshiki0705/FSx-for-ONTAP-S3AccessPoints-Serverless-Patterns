#!/usr/bin/env python3
"""Mask UC6 demo screenshots (from 2026-05-10 AWS re-verification).

Same approach as mask_phase7.py: detect AWS console vs HTML preview and
apply minimal masking only to AWS console images.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ORIGINALS = PROJECT_ROOT / "docs" / "screenshots" / "originals" / "uc6-demo"
MASKED = PROJECT_ROOT / "docs" / "screenshots" / "masked" / "uc6-demo"


def mask_aws_console(img_path: Path, out_path: Path) -> None:
    img = Image.open(img_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    w, _ = img.size
    # Top-right username area
    draw.rectangle((max(0, w - 280), 24, w - 10, 80), fill=(51, 51, 51))
    img.save(out_path, "PNG", optimize=True)


def is_html_preview(img_path: Path) -> bool:
    img = Image.open(img_path)
    sample = img.crop((img.width - 100, 10, img.width - 10, 50))
    pixels = list(sample.getdata())
    avg = sum(sum(p[:3]) / 3 for p in pixels) / len(pixels)
    return avg > 150


def main() -> None:
    MASKED.mkdir(parents=True, exist_ok=True)
    for img_path in sorted(ORIGINALS.glob("*.png")):
        out_path = MASKED / img_path.name
        if is_html_preview(img_path):
            shutil.copy2(img_path, out_path)
            print(f"  COPY (preview): {img_path.name}")
        else:
            mask_aws_console(img_path, out_path)
            print(f"  MASK (AWS console): {img_path.name}")


if __name__ == "__main__":
    main()
