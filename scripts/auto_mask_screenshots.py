#!/usr/bin/env python3
"""スクリーンショットの環境固有情報を自動マスクするスクリプト

AWS コンソールのスクリーンショットから環境固有情報をマスク:
1. 上部ナビゲーションバー全体（アカウント名・リージョン）
2. ページ上部のパンくずリスト/ARN 表示領域
3. 画面ごとの固有領域

Usage:
    python3 scripts/auto_mask_screenshots.py
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

# 3024x1618 Retina 解像度での座標
# AWS コンソールの共通レイアウト:
#   - 0-112px: ナビゲーションバー（黒背景、アカウント名・リージョン）
#   - 112-200px: サービス名・パンくずリスト（ARN が表示されることがある）

# 画面ごとのマスク領域定義
# (x1, y1, x2, y2) のリスト
MASK_REGIONS = {
    # Step Functions: ステートマシン一覧 — ARN 列をマスク
    "step-functions-all-succeeded.png": [
        (0, 0, 3024, 112),       # ナビバー全体
        (0, 112, 3024, 260),     # パンくずリスト + タイトル
        (1500, 260, 3024, 1618), # ARN 列（右半分）
    ],
    # Step Functions: UC1 実行詳細 — 実行 ARN をマスク
    "step-functions-uc1-succeeded.png": [
        (0, 0, 3024, 112),       # ナビバー全体
        (0, 112, 3024, 320),     # パンくずリスト + 実行 ARN
    ],
    # CloudFormation: スタック一覧 — スタック ID 列をマスク
    "cloudformation-all-stacks.png": [
        (0, 0, 3024, 112),       # ナビバー全体
        (0, 112, 3024, 240),     # パンくずリスト
    ],
    # FSx: S3 Access Point — ボリューム ID、ARN をマスク
    "fsx-s3-access-point.png": [
        (0, 0, 3024, 112),       # ナビバー全体
        (0, 112, 3024, 350),     # パンくずリスト + ボリューム ID
        (0, 350, 800, 900),      # 左サイドバーのリソース ID
    ],
    # Athena: クエリ履歴 — クエリ ID をマスク
    "athena-query-history.png": [
        (0, 0, 3024, 112),       # ナビバー全体
        (0, 112, 3024, 240),     # パンくずリスト
    ],
    # Bedrock: モデルカタログ — 環境固有情報なし
    "bedrock-model-catalog.png": [
        (0, 0, 3024, 112),       # ナビバー全体
    ],
    # Rekognition: ラベル検出 — 環境固有情報なし
    "rekognition-label-detection.png": [
        (0, 0, 3024, 112),       # ナビバー全体
    ],
    # Comprehend: コンソール — 環境固有情報なし
    "comprehend-console.png": [
        (0, 0, 3024, 112),       # ナビバー全体
    ],
    # Glue: Data Catalog テーブル — データベース名にスタック名が含まれる
    "glue-data-catalog-tables.png": [
        (0, 0, 3024, 112),       # ナビバー全体
        (0, 112, 3024, 240),     # パンくずリスト
    ],
    # CloudWatch: ロググループ — ロググループ名にスタック名が含まれる
    "cloudwatch-log-groups.png": [
        (0, 0, 3024, 112),       # ナビバー全体
        (0, 112, 3024, 240),     # パンくずリスト
    ],
    # SNS: トピック — トピック ARN をマスク
    "sns-topics.png": [
        (0, 0, 3024, 112),       # ナビバー全体
        (0, 112, 3024, 240),     # パンくずリスト
        (1200, 240, 3024, 1618), # ARN 列（右側）
    ],
    # Secrets Manager — シークレット ARN をマスク
    "secrets-manager.png": [
        (0, 0, 3024, 112),       # ナビバー全体
        (0, 112, 3024, 240),     # パンくずリスト
    ],
}


def mask_screenshot(filepath: Path) -> bool:
    """スクリーンショットの環境固有情報をマスクする"""
    filename = filepath.name
    regions = MASK_REGIONS.get(filename)

    if not regions:
        # デフォルト: ナビバーのみ
        regions = [(0, 0, 3024, 112)]

    img = Image.open(filepath)
    # 元画像を再読み込み（前回のマスクを上書きしないよう）
    draw = ImageDraw.Draw(img)

    for x1, y1, x2, y2 in regions:
        # 画像サイズに合わせてクリップ
        x2 = min(x2, img.size[0])
        y2 = min(y2, img.size[1])
        draw.rectangle([x1, y1, x2, y2], fill="black")

    img.save(filepath, optimize=True)
    print(f"  ✅ {filename} ({len(regions)} regions masked)")
    return True


def main():
    png_files = sorted(SCREENSHOTS_DIR.glob("*.png"))
    if not png_files:
        print("No PNG files found")
        return

    print(f"Masking {len(png_files)} screenshots...\n")

    for f in png_files:
        mask_screenshot(f)

    print(f"\nDone: {len(png_files)} files processed")


if __name__ == "__main__":
    main()
