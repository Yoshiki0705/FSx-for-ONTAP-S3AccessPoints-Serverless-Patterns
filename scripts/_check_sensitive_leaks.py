#!/usr/bin/env python3
"""Check for sensitive string leaks in both masked screenshots (OCR) and
git-tracked text files.

This is the ground-truth leak check (complement to _verify_masks.py which
counts generic dark-on-light pixels).

Usage:
    python3 scripts/_check_sensitive_leaks.py          # scan images + text
    python3 scripts/_check_sensitive_leaks.py --images  # images only
    python3 scripts/_check_sensitive_leaks.py --text    # text files only
    python3 scripts/_check_sensitive_leaks.py a.png b.md   # only these paths

The string list lives in scripts/_sensitive_strings.py, which IS gitignored and
must never be committed: it is the inventory of the real identifiers being kept out
of the repository. This file is tracked, so a fresh checkout has the checker but not
the list, and supplying your own is the intended setup step. It used to import the
list at module scope, which meant a clean checkout could not even reach --help.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# The options this script knows. Declared here, and checked before the sensitive-string
# inventory is imported, because rejecting a typo needs no inventory: on a machine
# without `_sensitive_strings.py` -- which includes CI, where it arrives from a secret
# -- the import guard below would otherwise answer a misspelled flag with "the
# inventory is missing", sending the caller to fix the wrong thing.
KNOWN_OPTIONS = {"--images", "--text"}


def reject_unknown_options(args: list[str]) -> None:
    """Exit 2 when an argument looks like an option this script does not know.

    Rejected rather than ignored. `--text-only` selected neither half, so the run
    printed "No leaks detected" and exited 0 having scanned nothing -- and it was used
    to check a real leak, which it duly failed to see.

    Args:
        args: The command-line arguments, without the program name.
    """
    unknown = [a for a in args if a.startswith("-") and a not in KNOWN_OPTIONS]
    if unknown:
        print(
            f"unknown option(s): {' '.join(unknown)}. "
            f"Known: {' '.join(sorted(KNOWN_OPTIONS))}, or no option to scan both.",
            file=sys.stderr,
        )
        sys.exit(2)


reject_unknown_options(sys.argv[1:])

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
try:
    from _sensitive_strings import SENSITIVE_STRINGS  # type: ignore
except ImportError:
    # Exit 2, distinct from the exit 1 that means "leaks found", so a caller can tell
    # "this machine cannot check" apart from "this content is clean". Conflating those
    # is how a checker starts reporting success without having looked at anything.
    print(
        "scripts/_sensitive_strings.py が見つかりません（gitignore 対象なので clone には含まれません）。\n"
        "検査したい実際の識別子を SENSITIVE_STRINGS: list[str] として定義してください。\n"
        "例: SENSITIVE_STRINGS = ['123456789012', 'fs-0123456789abcdef0', '10.1.2.3']",
        file=sys.stderr,
    )
    sys.exit(2)

if not SENSITIVE_STRINGS:
    # An empty inventory means "cannot check", not "nothing to find", and the difference
    # is not cosmetic. The CI job substituted scripts/_sensitive_strings.py.example --
    # which defines SENSITIVE_STRINGS as an empty tuple -- whenever the secret holding
    # the real list was absent. The secret was never configured, so from 2026-05-13 the
    # check "Screenshot OCR sensitive-leak scan" compared 460 images against zero
    # strings and reported a green "No leaks detected" every time. It was green on
    # 2026-06-06 while three screenshots carrying a real AWS account id were committed,
    # and stayed green for the ten weeks they sat in a public repository.
    print(
        "SENSITIVE_STRINGS が空です。検査対象が無いので「リーク無し」とは報告できません。\n"
        "CI では SENSITIVE_STRINGS_PY secret を設定してください。ローカルでは実際の識別子を\n"
        "scripts/_sensitive_strings.py に定義してください。",
        file=sys.stderr,
    )
    sys.exit(2)

# File extensions to scan for text leaks
TEXT_EXTENSIONS = {".md", ".yaml", ".yml", ".json", ".sh", ".py", ".ts", ".js", ".txt"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

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
        import pytesseract  # type: ignore
        from PIL import Image
    except ImportError:
        return [("IMPORT_ERROR", "PIL/pytesseract not installed — skipping image scan")]

    img = Image.open(path).convert("RGB")
    try:
        text = pytesseract.image_to_data(img, lang="eng+jpn", output_type=pytesseract.Output.DICT)
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
        result = subprocess.run(["git", "ls-files"], capture_output=True, text=True, cwd=PROJECT_ROOT)
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
    """Scan every git-tracked image for sensitive string leaks via OCR.

    Scope note: this used to glob docs/screenshots/masked/**.png only. 87 of the 279
    tracked images sit outside that directory -- docs/screenshots/ itself, portal-demo,
    phase11 -- so a clean run described one subtree while being reported as describing
    the repository. What a checker looked at is part of its result, and the text half
    of this file had always enumerated tracked files rather than one directory.

    Two things this still cannot tell you: OCR only reads text it can resolve, so a
    leak rendered small enough may not be read (verified: a 12-digit id at the default
    PIL bitmap size was missed, the same id at 44px was read verbatim), and it only
    matches the strings listed in _sensitive_strings.py.
    """
    leaks: dict[str, list[tuple[str, str]]] = {}
    total = 0
    for p in sorted(get_tracked_files()):
        if p.suffix.lower() not in IMAGE_SUFFIXES or is_excluded(p) or not p.exists():
            continue
        total += 1
        hits = scan_image(p)
        if hits:
            leaks[str(p.relative_to(PROJECT_ROOT))] = hits
    print(f"Scanned: {total} tracked images")
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


UNAVAILABLE = -1


def scan_explicit(paths: list[Path]) -> int:
    """Scan exactly the paths given. Returns the count of files with leaks.

    Returns UNAVAILABLE if OCR could not run at all, which the caller must not read
    as "clean". The commit gate uses this mode: it knows which files are staged, and
    re-scanning the whole screenshot tree does not fit a PreToolUse timeout.
    """
    files_with_leaks = 0
    for path in paths:
        if not path.exists():
            print(f"  skipped (missing): {path}")
            continue
        if path.suffix.lower() in IMAGE_SUFFIXES:
            hits = scan_image(path)
            if any(token in ("IMPORT_ERROR", "OCR_ERROR") for token, _ in hits):
                print(f"  cannot scan {path}: {hits[0][1]}", file=sys.stderr)
                return UNAVAILABLE
            for token, word in hits:
                print(f"  {path}: leaked='{token}' in OCR word='{word}'")
        else:
            text_hits = scan_text_file(path)
            hits = [(token, line) for token, _, line in text_hits]
            for token, line_num, line in text_hits:
                print(f"  {path}: L{line_num} leaked='{token}' in: {line}")
        if hits:
            files_with_leaks += 1
    return files_with_leaks


def main() -> None:
    args = sys.argv[1:]
    explicit = [Path(a) for a in args if not a.startswith("-")]
    if explicit:
        found = scan_explicit(explicit)
        if found == UNAVAILABLE:
            sys.exit(2)
        print(f"Scanned {len(explicit)} path(s); files with leaks: {found}")
        sys.exit(1 if found else 0)

    # Already rejected at import time, before the inventory is loaded. Repeated here so
    # main() is correct when called directly rather than through __main__.
    reject_unknown_options(args)

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

    print(f"{'=' * 50}")
    print(f"Total files with leaks: {total_leaks}")
    if total_leaks > 0:
        print("❌ LEAKS DETECTED — fix before committing")
        sys.exit(1)
    else:
        print("✅ No leaks detected")
        sys.exit(0)


if __name__ == "__main__":
    main()
