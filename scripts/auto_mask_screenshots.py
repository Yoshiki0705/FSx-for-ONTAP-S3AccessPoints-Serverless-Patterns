#!/usr/bin/env python3
"""スクリーンショットの環境固有情報を自動マスクするスクリプト

AWS コンソールのスクリーンショットから以下の領域をマスク:
1. 上部ナビゲーションバーの右側（アカウント名・リージョン表示領域）
2. URL バー（ブラウザのアドレスバー）

Usage:
    python3 scripts/auto_mask_screenshots.py [--dry-run]
"""
import os
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("Pillow is required: pip3 install Pillow")
    sys.exit(1)

SCREENSHOTS_DIR = Path(__file__).resolve().parent.parent / "docs" / "screenshots"
MASKED_DIR = SCREENSHOTS_DIR  # 上書き保存


def mask_screenshot(filepath: Path, dry_run: bool = False) -> bool:
    """スクリーンショットの環境固有情報をマスクする

    AWS コンソールのスクリーンショットでは:
    - 上部 ~56px がナビゲーションバー（右端にアカウント名）
    - ブラウザの URL バーは通常含まれない（ページスクリーンショットの場合）

    マスク戦略:
    - 画像上部の右 1/3 を黒塗り（アカウント名・リージョン表示）
    """
    img = Image.open(filepath)
    width, height = img.size

    if dry_run:
        print(f"  [DRY-RUN] Would mask {filepath.name} ({width}x{height})")
        return False

    draw = ImageDraw.Draw(img)

    # AWS コンソールのナビバー右側をマスク（アカウント名・リージョン）
    # 上部 56px、右 40% の領域
    nav_bar_height = 56
    mask_start_x = int(width * 0.6)
    draw.rectangle(
        [mask_start_x, 0, width, nav_bar_height],
        fill="black",
    )

    img.save(filepath)
    print(f"  ✅ Masked {filepath.name}")
    return True


def main():
    dry_run = "--dry-run" in sys.argv

    png_files = sorted(SCREENSHOTS_DIR.glob("*.png"))
    if not png_files:
        print("No PNG files found in", SCREENSHOTS_DIR)
        return

    print(f"Processing {len(png_files)} screenshots...")
    if dry_run:
        print("(DRY-RUN mode — no files will be modified)")
    print()

    masked = 0
    for f in png_files:
        if mask_screenshot(f, dry_run):
            masked += 1

    print(f"\nDone: {masked}/{len(png_files)} files masked")


if __name__ == "__main__":
    main()
