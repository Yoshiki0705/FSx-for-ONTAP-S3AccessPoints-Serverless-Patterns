#!/usr/bin/env python3
"""Generate the language switcher, so it stops being hand-maintained.

## Why

The switcher is the row of links at the top of a translated document that lets a
reader reach their own language. It was written by hand in every file, and hand
maintenance produced exactly what hand maintenance produces at this scale.
Measured 2026-08-15 across 1,361 tracked Markdown files:

* **12 distinct label formats.** `🌐 **Language / 言語**` in 830 files,
  `🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**` in 168,
  `🌐 Language` in 47, `🌐 言語` in 18, six single-language variants, and the root
  README with no label at all.
* **The current language marked three different ways** — `**English**`, bare
  `English`, and in the root README a link pointing at the file you are already
  reading.
* **`check_doc_pairs.py` can only see 902 of the 1,115 switchers that exist.** Its
  regex is `Language / 言語|🌐 *(言語|Language)`, and `🌐 **Language` fails it
  because of the `**`. The 168 files using the fully-localized label and the root
  and portal READMEs are invisible to the check that is supposed to guarantee a
  switcher is present. Those files happen to sit outside its `PAIR_DIRS`, so today
  it produces no false failure — only silent non-coverage, which is worse, because
  the check reports a clean tree.

A generated switcher has one format by construction, and `--check` makes a
hand-edited one a build failure rather than a thing someone notices in review.

## What it generates

    🌐 **Language / 言語**: [日本語](README.md) | English | [한국어](README.ko.md) | ...

The current language is plain text, never a link to the file being read. Order is
the manifest's `locales_all` order, so it is stable across files.

Group membership comes from `docs/i18n-manifest.toml` through
`check_i18n_parity.py`, so the switcher and the parity check cannot disagree about
what a group is — two answers to that question is how 27 of 83 pairs came to have
no switcher at all.

## Usage

    python3 scripts/sync_lang_switcher.py --check     # CI: fail on any difference
    python3 scripts/sync_lang_switcher.py --diff      # show what would change
    python3 scripts/sync_lang_switcher.py --write     # rewrite in place
    python3 scripts/sync_lang_switcher.py --write --group solutions/industry/legal-compliance/README.md
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parent.parent

LABELS: dict[str, str] = {
    "ja": "日本語",
    "en": "English",
    "ko": "한국어",
    "zh-CN": "简体中文",
    "zh-TW": "繁體中文",
    "fr": "Français",
    "de": "Deutsch",
    "es": "Español",
}

PREFIX = "🌐 **Language / 言語**: "

# How far past the H1 counts as "the header". A switcher inside this window is the
# navigation element; one beyond it is a deliberate footer. Measured: the header
# switchers all sit 2-4 lines after the H1, while the footer ones in the root README
# and the portal READMEs are 216-698 lines down. 8 separates the two cleanly without
# reaching anything.
HEADER_WINDOW = 8
# Any existing switcher line, in any of the 12 formats found, INCLUDING the 66 that
# sit inside a blockquote as `> 🌐 ...`. The first version of this pattern was
# `^\s*🌐`, which does not match a `>` prefix — so instead of replacing those
# switchers it inserted a second one above them, and the file ended up with two.
# Caught on the first `--write` of a single file, which is the argument for trying
# one file before 502.
#
# `| 🌐` (a table cell, 5 occurrences) and `## 🌐` (a heading, 2) must NOT match, and
# do not: neither `|` nor `#` is a blockquote marker or whitespace. Prose that
# mentions the emoji mid-sentence is excluded by the `^` anchor.
#
# Note the whitespace placement: `^\s*(>\s*)?` and not `^(\s*>\s*)?`. The latter
# makes the WHOLE prefix optional, so a line indented without a blockquote marker
# ("  🌐 ...") failed to match and would have been duplicated rather than replaced.
EXISTING = re.compile(r"^\s*(>\s*)?🌐")


def _parity() -> ModuleType:
    """Import the parity checker, which owns group resolution.

    Returns:
        The imported ``check_i18n_parity`` module.
    """
    spec = importlib.util.spec_from_file_location("check_i18n_parity", ROOT / "scripts" / "check_i18n_parity.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_i18n_parity"] = module
    spec.loader.exec_module(module)
    return module


def switcher_for(locale: str, group: dict[str, str], from_path: str, order: list[str]) -> str:
    """The switcher line as it should appear in one file.

    Args:
        locale: Locale of the file the line is going into.
        group: Mapping of locale to repository-relative path.
        from_path: Path of the file the line is going into, for relative links.
        order: Locale order from the manifest.

    Returns:
        The complete switcher line, without a trailing newline.
    """
    here = Path(from_path).parent
    parts: list[str] = []
    for candidate in order:
        target = group.get(candidate)
        if target is None:
            continue
        label = LABELS[candidate]
        if candidate == locale:
            parts.append(label)  # never link the file being read
            continue
        relative = Path(target).relative_to(here) if Path(target).parent == here else _relative(here, Path(target))
        parts.append(f"[{label}]({relative.as_posix()})")
    return PREFIX + " | ".join(parts)


def _relative(from_dir: Path, target: Path) -> Path:
    """A relative path from one directory to a file, across directories.

    `docs/ja/x.md` links `docs/en/x.md` as `../en/x.md`, so a plain
    `relative_to` is not enough.

    Args:
        from_dir: Directory the link lives in.
        target: File being linked.

    Returns:
        The relative path.
    """
    from_parts = from_dir.parts
    to_parts = target.parts
    common = 0
    while common < min(len(from_parts), len(to_parts) - 1) and from_parts[common] == to_parts[common]:
        common += 1
    ups = [".."] * (len(from_parts) - common)
    return Path(*ups, *to_parts[common:]) if ups else Path(*to_parts[common:])


def _apply(text: str, line: str) -> str:
    """Insert or replace the switcher, keeping it directly under the H1.

    Args:
        text: Current file contents.
        line: Switcher line to place.

    Returns:
        The updated contents.
    """
    lines = text.split("\n")
    h1 = next((i for i, value in enumerate(lines) if value.startswith("# ")), None)
    window = (h1 + HEADER_WINDOW) if h1 is not None else HEADER_WINDOW

    placed: int | None = None
    duplicates: list[int] = []
    for index, value in enumerate(lines[:window]):
        found = EXISTING.match(value)
        if not found:
            continue
        if placed is None:
            # Keep the blockquote marker when there was one. Dropping it would take
            # the line out of the quote block it belongs to, and in a multi-line
            # quote that splits the block in two — a formatting change nobody asked
            # for, made by a script whose job is the label and the links.
            lines[index] = (found.group(1) or "") + line
            placed = index
        else:
            # A SECOND switcher in the header. Four files shipped one: two in
            # docs/architecture-diagrams (the canonical line followed by an older
            # `🌐 **言語**:` form) and two in docs/partner-si-one-pager, where the
            # stale copy linked the reader's own language back to the page they were
            # already on. Only the header is de-duplicated — the root README and the
            # portal READMEs carry a deliberate footer switcher 200-700 lines down,
            # and removing that would be deleting content rather than a duplicate.
            duplicates.append(index)

    if placed is not None:
        for index in reversed(duplicates):
            end = index + 1
            # Take one trailing blank line with it, so removing the duplicate does
            # not leave a double blank behind.
            if end < len(lines) and not lines[end].strip():
                end += 1
            del lines[index:end]
        return "\n".join(lines)

    if h1 is None:
        return line + "\n\n" + text
    return "\n".join([*lines[: h1 + 1], "", line, *lines[h1 + 1 :]])


def plan(only: str | None = None) -> list[tuple[str, str, str]]:
    """Files whose switcher differs from the generated one.

    Args:
        only: Restrict to one source document's group.

    Returns:
        Tuples of (path, current contents, desired contents).
    """
    parity = _parity()
    locales_all, source_locale, rules = parity.load_manifest()
    published = parity.tracked()
    others = [loc for loc in locales_all if loc != source_locale]
    suffix = re.compile(r"[.\-](" + "|".join(others) + r")\.md$")
    locale_dir = re.compile(r"^docs/(" + "|".join(others) + r")/")

    changes: list[tuple[str, str, str]] = []
    for path in sorted(p for p in published if p.endswith(".md")):
        if suffix.search(path) or locale_dir.match(path):
            continue
        if only and path != only:
            continue
        required = parity.required_for(path, rules)
        if required is None:
            continue
        lookup = locales_all if required == "keep" else required
        group = parity._resolve_group(path, lookup, source_locale, published)
        if len(group) < 2:
            continue  # nothing to switch between

        for locale, target in group.items():
            current = (ROOT / target).read_text(encoding="utf-8")
            desired = _apply(current, switcher_for(locale, group, target, locales_all))
            if desired != current:
                changes.append((target, current, desired))
    return changes


def main(argv: list[str]) -> int:
    """Check, show or write the generated switchers.

    Args:
        argv: Command-line arguments.

    Returns:
        1 when `--check` finds a difference, otherwise 0.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="fail if any switcher differs")
    mode.add_argument("--diff", action="store_true", help="print the differing lines")
    mode.add_argument("--write", action="store_true", help="rewrite in place")
    parser.add_argument("--group", default=None)
    parser.add_argument("--max-differing", type=int, default=0, help="ratchet for --check")
    args = parser.parse_args(argv)

    changes = plan(args.group)

    if args.write:
        for path, _, desired in changes:
            (ROOT / path).write_text(desired, encoding="utf-8")
        print(f"LANG SWITCHER: rewrote {len(changes)} file(s)")
        return 0

    if args.diff:
        for path, current, desired in changes:
            before = next((line for line in current.split("\n")[:12] if EXISTING.match(line)), "(none)")
            after = next(line for line in desired.split("\n")[:14] if EXISTING.match(line))
            print(f"\n{path}\n  -{before}\n  +{after}")

    if not changes:
        print("LANG SWITCHER: PASS (every switcher matches the generated form)")
        return 0

    print(f"\nLANG SWITCHER: {len(changes)} file(s) differ from the generated form")
    if args.check and len(changes) > args.max_differing:
        print(
            "The switcher is generated. Run `python3 scripts/sync_lang_switcher.py --write` "
            "rather than editing it by hand — hand maintenance produced 12 different label "
            "formats across 1,361 files, and left 246 group members with no switcher at all."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
