#!/usr/bin/env python3
"""Mask screenshots by OCR-detecting sensitive strings and redacting only those regions.

**Masking strategy (v7, OCR-based precision with iterative passes)**:

1. Run tesseract OCR with word-level bounding boxes (image_to_data).
2. For each word, check if it contains any sensitive substring.
3. Draw a small black rectangle ONLY over those specific words.
4. Re-run OCR on the masked image and repeat (up to MAX_OCR_PASSES) until
   no sensitive words remain. This handles tesseract tokenisation quirks
   where long URIs (e.g. `s3://bucket-<account-id>/obj`) are first parsed
   as a single unmatched word.
5. Also mask the top-right account widget for AWS console screenshots
   (always, since it's a fixed styled element OCR may miss).
6. HTML preview mocks are masked too (they embed S3 URIs with account IDs)
   but the top-right widget mask is skipped (not applicable to HTML).

Preserves ~99% of the screenshot content so reviewers can see what the
UI actually looks like. Only the specific sensitive strings are blocked.

Requires:
    brew install tesseract tesseract-lang
    pip3 install pillow pytesseract
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

try:
    import pytesseract  # type: ignore
except ImportError:
    print("ERROR: pytesseract not installed. Run: pip3 install pytesseract")
    raise SystemExit(1)

# Load sensitive literals from gitignored local file
try:
    from _sensitive_strings import SENSITIVE_STRINGS  # type: ignore
except ImportError:
    print("ERROR: scripts/_sensitive_strings.py not found.")
    print("       cp scripts/_sensitive_strings.py.example scripts/_sensitive_strings.py")
    print("       and fill in your environment-specific values.")
    SENSITIVE_STRINGS: tuple[str, ...] = ()


def _rect_frac(draw, w, h, x0, y0, x1, y1, color):
    draw.rectangle((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)), fill=color)


def mask_aws_header(draw: ImageDraw.ImageDraw, w: int, h: int) -> None:
    """Hide the top-right account widget. Always safe to mask."""
    _rect_frac(draw, w, h, 0.82, 0.0, 1.0, 0.045, (30, 30, 35))


def find_sensitive_words(img: Image.Image) -> list[tuple[int, int, int, int]]:
    """Run OCR and return bounding boxes (x, y, w, h) of words containing
    any sensitive substring.
    """
    # image_to_data returns dict with keys: level, page_num, block_num,
    # par_num, line_num, word_num, left, top, width, height, conf, text
    try:
        data = pytesseract.image_to_data(
            img, lang="eng+jpn", output_type=pytesseract.Output.DICT
        )
    except Exception as e:
        print(f"  OCR failed: {e}")
        return []

    boxes: list[tuple[int, int, int, int]] = []
    words: list[str] = data["text"]
    for i, word in enumerate(words):
        if not word or len(word.strip()) < 4:
            continue
        for sensitive in SENSITIVE_STRINGS:
            if sensitive in word:
                x = data["left"][i]
                y = data["top"][i]
                ww = data["width"][i]
                hh = data["height"][i]
                # Pad the box a bit to fully cover antialiasing
                boxes.append((max(0, x - 2), max(0, y - 2), ww + 4, hh + 4))
                break
    return boxes


MAX_OCR_PASSES = 4


def mask_with_ocr(
    img_path: Path, out_path: Path, mask_header: bool = True
) -> tuple[int, int]:
    """Mask sensitive words detected by OCR.

    Runs multiple OCR passes because tesseract is non-deterministic at word
    boundaries: the first pass may tokenise 's3://bucket-NNNN/obj' as a
    single long word that fails our match; a second pass on the partially
    masked image often succeeds where the first failed.

    Returns (total_words_masked, passes_used).
    """
    img = Image.open(img_path).convert("RGB")
    w, h = img.size
    draw = ImageDraw.Draw(img)

    # 1. Always mask top-right account widget for AWS console screenshots
    #    (may not be OCR-detected due to styling). Skip for HTML previews.
    if mask_header:
        mask_aws_header(draw, w, h)

    # 2. Iterative OCR passes until no more sensitive words are found
    total_boxes = 0
    passes = 0
    for _ in range(MAX_OCR_PASSES):
        passes += 1
        boxes = find_sensitive_words(img)
        if not boxes:
            break
        for x, y, ww, hh in boxes:
            draw.rectangle((x, y, x + ww, y + hh), fill=(30, 30, 35))
        total_boxes += len(boxes)

    img.save(out_path, "PNG", optimize=True)
    return total_boxes, passes


def is_html_preview(img_path: Path) -> bool:
    """HTML preview mocks have bright top-right (no AWS dark nav)."""
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
        html = is_html_preview(img_path)
        # HTML previews still need OCR masking: S3 URIs and resource
        # identifiers embedded in rendered HTML leak the account ID.
        # Skip only the top-right account widget mask (not applicable).
        nboxes, passes = mask_with_ocr(img_path, out_path, mask_header=not html)
        tag = "HTML" if html else "AWS "
        print(f"  {tag} MASK ({nboxes} boxes, {passes} passes): {demo_name}/{img_path.name}")


def main() -> None:
    if not SENSITIVE_STRINGS:
        print("WARNING: SENSITIVE_STRINGS is empty. No content-level masking will be applied.")
        print("         Only the top-right account widget will be masked.")

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
