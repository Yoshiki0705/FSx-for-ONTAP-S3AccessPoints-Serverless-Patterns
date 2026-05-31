#!/usr/bin/env python3
"""Check for sensitive string leaks in both masked screenshots (OCR) and
git-tracked text files.

This is the ground-truth leak check (complement to _verify_masks.py which
counts generic dark-on-light pixels).

Usage:
    python3 scripts/_check_sensitive_leaks.py          # scan images + text
    python3 scripts/_check_sensitive_leaks.py --images  # images only
    python3 scripts/_check_sensitive_leaks.py --text    # text files only

GITIGNORED.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from _sensitive_strings import SENSITIVE_STRINGS  # type: ignore

# File extensions to scan for text leaks
TEXT_EXTENSIONS = {".md", ".yaml", ".yml", ".json", ".sh", ".py", ".ts", ".js", ".txt"}

# Paths to exclude from text scanning (relative to PROJECT_ROOT)
EXCLUDE_PATHS = {
    "scripts/_sensitive_strings.py",  # The definition file itself
    "scripts/_check_sensitive_leaks.py",  # This file
    "scripts/mask_screenshots.py",  # Mask targets list
    ".hypothesis/",
    "node_modules/",
    "__pycache__/",
    ".git/",
    "build/",
}


def scan_image(path: Path) -> list[tuple[str, str]]:
    """Return (sensitive_token, matching_word) list for any leak found."""
    try:
        from PIL import Image
        import pytesseract  # type: ignore
    except ImportError:
        return [("IMPORT_ERROR", "PIL/pytesseract not installed — skipping image scan")]

    img = Image.open(path).convert("RGB")
    try:
        text = pytesseract.image_to_data(
            img, lang="eng+jpn", output_type=pytesseract.Output.DICT
        )
    except Exception as e:
        return [("OCR_ERROR", str(e))]
    hits: list[tuple[str, str]] = []
    for word in text["text"]:
        if not word:
            continue
        for s in SENSITIVE_STRINGS:
            if s in word:
                hits.append((s, word))
    return hits


def get_tracked_files() -> list[Path]:
    """Get list of git-tracked files."""
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            capture_output=True, text=True, cwd=PROJECT_ROOT
        )
        if result.returncode != 0:
            return []
        return [PROJECT_ROOT / f for f in result.stdout.strip().split("\n") if f]
    except FileNotFoundError:
        return []


def is_excluded(path: Path) -> bool:
    """Check if path should be excluded from scanning."""
    rel = str(path.relative_to(PROJECT_ROOT))
    for excl in EXCLUDE_PATHS:
        if rel == excl or rel.startswith(excl):
            return True
    return False


def scan_text_file(path: Path) -> list[tuple[str, int, str]]:
    """Return (sensitive_token, line_number, line_content) for any leak found."""
    hits: list[tuple[str, int, str]] = []
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except (OSError, UnicodeDecodeError):
        return hits

    for line_num, line in enumerate(content.splitlines(), 1):
        for s in SENSITIVE_STRINGS:
            if s in line:
                hits.append((s, line_num, line.strip()[:120]))
    return hits


def scan_images() -> dict[str, list[tuple[str, str]]]:
    """Scan masked screenshots for sensitive string leaks via OCR."""
    root = PROJECT_ROOT / "docs" / "screenshots" / "masked"
    leaks: dict[str, list[tuple[str, str]]] = {}
    total = 0
    for p in sorted(root.rglob("*.png")):
        total += 1
        hits = scan_image(p)
        if hits:
            leaks[str(p.relative_to(PROJECT_ROOT))] = hits
    print(f"Scanned: {total} masked images")
    print(f"Images with detectable sensitive substrings: {len(leaks)}")
    return leaks


def scan_text_files() -> dict[str, list[tuple[str, int, str]]]:
    """Scan git-tracked text files for sensitive string leaks."""
    tracked = get_tracked_files()
    leaks: dict[str, list[tuple[str, int, str]]] = {}
    total = 0
    for path in tracked:
        if path.suffix not in TEXT_EXTENSIONS:
            continue
        if is_excluded(path):
            continue
        if not path.exists():
            continue
        total += 1
        hits = scan_text_file(path)
        if hits:
            leaks[str(path.relative_to(PROJECT_ROOT))] = hits
    print(f"Scanned: {total} tracked text files")
    print(f"Files with sensitive strings: {len(leaks)}")
    return leaks


def main() -> None:
    args = sys.argv[1:]
    scan_img = "--images" in args or not args
    scan_txt = "--text" in args or not args

    total_leaks = 0

    if scan_img:
        print("=== Image Scan (OCR) ===")
        img_leaks = scan_images()
        for path, hits in img_leaks.items():
            print(f"\n  {path}")
            for s, w in hits:
                print(f"    leaked='{s}' in OCR word='{w}'")
        total_leaks += len(img_leaks)
        print()

    if scan_txt:
        print("=== Text File Scan (git-tracked) ===")
        txt_leaks = scan_text_files()
        for path, hits in txt_leaks.items():
            print(f"\n  {path}")
            for s, line_num, line in hits:
                print(f"    L{line_num}: leaked='{s}' in: {line}")
        total_leaks += len(txt_leaks)
        print()

    print(f"{'='*50}")
    print(f"Total files with leaks: {total_leaks}")
    if total_leaks > 0:
        print("❌ LEAKS DETECTED — fix before committing")
        sys.exit(1)
    else:
        print("✅ No leaks detected")
        sys.exit(0)


if __name__ == "__main__":
    main()
