#!/usr/bin/env python3
"""Phase 11 スクリーンショットマスキング.

アカウント ID、ユーザー名等の環境固有情報をマスクする。
"""

from pathlib import Path
from PIL import Image, ImageDraw

SCREENSHOTS_DIR = Path(__file__).parent.parent / "docs" / "screenshots" / "phase11"
MASKED_DIR = SCREENSHOTS_DIR  # Overwrite originals (they're in git)

# Masking regions: (x1, y1, x2, y2) — coordinates for sensitive areas
# These are approximate and cover the navigation bar account name area
# Standard AWS Console layout at ~1440px viewport width

# Common mask: top-right account name area (all screenshots)
NAV_ACCOUNT_MASK = (1250, 0, 1440, 40)  # Account name in nav bar


def mask_image(filepath: Path, extra_masks: list = None):
    """Apply black rectangle masks to an image."""
    img = Image.open(filepath)
    draw = ImageDraw.Draw(img)

    # Always mask the nav bar account name
    draw.rectangle(NAV_ACCOUNT_MASK, fill="black")

    # Apply extra masks
    if extra_masks:
        for mask in extra_masks:
            draw.rectangle(mask, fill="black")

    img.save(filepath)
    print(f"  ✅ Masked: {filepath.name}")


def main():
    print("=" * 60)
    print("Phase 11 Screenshot Masking")
    print("=" * 60)

    # 01 - CloudWatch Dashboard
    mask_image(
        SCREENSHOTS_DIR / "01-cloudwatch-dashboard-cross-account.png",
    )

    # 02 - CloudFormation Stacks (has ARNs with account ID)
    mask_image(
        SCREENSHOTS_DIR / "02-cloudformation-stacks.png",
    )

    # 03 - EventBridge Custom Bus (has ARN with account ID)
    mask_image(
        SCREENSHOTS_DIR / "03-eventbridge-custom-bus.png",
    )

    # 04 - DynamoDB (has ARN with account ID)
    mask_image(
        SCREENSHOTS_DIR / "04-dynamodb-idempotency-store.png",
    )

    # 05 - ECS Cluster (has ARN with account ID)
    mask_image(
        SCREENSHOTS_DIR / "05-ecs-fpolicy-server.png",
    )

    # 06 - CloudWatch OAM
    mask_image(
        SCREENSHOTS_DIR / "06-cloudwatch-oam-settings.png",
    )

    print()
    print("Done. Review masked images before committing.")


if __name__ == "__main__":
    main()
