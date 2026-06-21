#!/usr/bin/env python3
"""Mask AWS account IDs and sensitive ARNs in screenshots.

This script applies rectangular masks over regions containing
AWS account IDs (178625946981) in console screenshots.

All screenshots are 1680x906 (Phase 16 set).
"""

from PIL import Image, ImageDraw
import os

# Uniform black mask for all regions — clearly communicates redaction
MASK_COLOR = (0, 0, 0)


def mask_regions(input_path, regions, output_path=None):
    """Apply colored rectangles over specified regions.
    
    Args:
        input_path: Path to source image
        regions: List of (x1, y1, x2, y2, color) tuples
        output_path: Where to save (defaults to overwrite input)
    """
    if output_path is None:
        output_path = input_path
    
    img = Image.open(input_path)
    draw = ImageDraw.Draw(img)
    
    for x1, y1, x2, y2, color in regions:
        draw.rectangle([x1, y1, x2, y2], fill=color)
    
    img.save(output_path, 'PNG')
    print(f"  Masked {len(regions)} regions: {os.path.basename(output_path)}")


def main():
    base_uc29 = 'solutions/genai/kb-selfservice-curation/docs/screenshots/masked'
    base_uc30 = 'solutions/genai/quick-agentic-workspace/docs/screenshots/masked'
    
    print("Phase 16 (UC29) screenshots:")
    
    # 1. step-functions-execution-succeeded.png (1680x906)
    # Coordinates derived from attached 1024x558 images, scaled by ~1.64x/1.62y
    # Exposed: Execution ARN, IAM role ARN, top-right badge
    mask_regions(f'{base_uc29}/step-functions-execution-succeeded.png', [
        # Top-right account badge "yoshiki" (attached: x≈940~1024, y≈0~17)
        (1542, 0, 1680, 28, MASK_COLOR),
        # Execution ARN line (attached: x≈200~535, y≈210~240)
        (328, 341, 877, 390, MASK_COLOR),
        # IAM role ARN line (attached: x≈200~530, y≈260~275)
        (328, 422, 870, 447, MASK_COLOR),
    ])
    
    # 2. bedrock-kb-datasource-sync.png (1680x906)
    # Exposed: Collection ARN with account ID, top-right badge
    mask_regions(f'{base_uc29}/bedrock-kb-datasource-sync.png', [
        # Top-right account badge (same position as step-functions)
        (1542, 0, 1680, 28, MASK_COLOR),
        # Collection ARN (attached: x≈595~935, y≈370~385)
        (976, 601, 1533, 626, MASK_COLOR),
    ])
    
    # 3. bedrock-kb-detail.png - likely has account ARNs too
    if os.path.exists(f'{base_uc29}/bedrock-kb-detail.png'):
        mask_regions(f'{base_uc29}/bedrock-kb-detail.png', [
            (1542, 0, 1680, 28, MASK_COLOR),
        ])
    
    # 4. bedrock-kb-list.png - may show KB ARN
    if os.path.exists(f'{base_uc29}/bedrock-kb-list.png'):
        mask_regions(f'{base_uc29}/bedrock-kb-list.png', [
            (1542, 0, 1680, 28, MASK_COLOR),
        ])
    
    # 5. scenario-c-eventbridge-rule.png - EventBridge rule
    if os.path.exists(f'{base_uc29}/scenario-c-eventbridge-rule.png'):
        mask_regions(f'{base_uc29}/scenario-c-eventbridge-rule.png', [
            (1542, 0, 1680, 28, MASK_COLOR),
        ])
    
    # 6. windows-explorer-quickaccess.png - Windows, likely no AWS account
    # But check top-right area just in case
    
    # 7. windows-smb-product-catalog.png - Windows Explorer, no AWS console
    
    # 8. windows-smb-share-roles.png - Windows Explorer, no AWS console
    
    print("\nPhase 17 (UC30) screenshots:")
    
    # UC30 screenshots (1680x906 for AWS console ones)
    for fname in ['athena-recent-queries.png', 'cloudformation-stacks.png']:
        fpath = f'{base_uc30}/{fname}'
        if os.path.exists(fpath):
            mask_regions(fpath, [
                # Top-right account badge
                (1542, 0, 1680, 28, MASK_COLOR),
            ])
    
    # Quick screenshots are different size (1512x805) - likely no AWS account ID
    # but verify Quick-specific ones don't show ARNs
    
    print("\nDone. Verify visually before re-uploading to dev.to.")
    print("\nREMINDER: Re-upload masked images to dev.to to replace the old ones.")


if __name__ == '__main__':
    main()
