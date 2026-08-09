#!/usr/bin/env python3
"""Check that translated documentation pairs are navigable and their links resolve.

Three failures this catches, all of which had shipped:

**A pair with no language switcher.** 27 of 83 pairs had none, so a reader who
landed on one language had no way to reach the other. The translation existed;
nothing pointed at it.

**A relative link that resolves to nothing.** 18 links were dead in the portal
docs alone, because `../../docs/` from `solutions/amplify-portal/docs/` is
`solutions/docs/`, which does not exist. Nobody noticed because nothing looked
at them: a dead relative link renders as ordinary text on GitHub until clicked.

**A link to a file that is not in the repository.** `.gitignore` excludes
`**/docs/verification-results.md` while its `.en.md` twin is committed, so a link
to the Japanese one resolves for whoever wrote it and 404s for every reader. Only
git decides what exists here, for that reason — and the first version of this
check, which trusted the filesystem, added a switcher pointing at that very file.

Six pairing conventions are in use across the repository, which is why this reads
the layout rather than assuming one:

    docs/ja/X.md      + docs/en/X.md
    docs/X.md         + docs/en/X.md
    X.md              + X.en.md         (same directory)
    X.md              + X-en.md         (same directory)
    …either suffix form extended to eight locales
    solutions/amplify-portal/README.md is English with README.ja.md alongside —
    the inverted case, which is why language is never inferred from position.

Run with no arguments. Exits non-zero on any finding.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _in_repository() -> set[pathlib.Path]:
    """Files a reader of the repository can actually open.

    `solutions/amplify-portal/docs/verification-results.md` exists on a
    contributor's machine and is excluded by `.gitignore`, while its `.en.md`
    twin is committed. Pairing the two produced a switcher on the published file
    pointing at one that is not published — a dead link created by the very pass
    meant to remove dead links, and invisible locally because the file was right
    there.
    """
    result = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return set()
    return {ROOT / line for line in result.stdout.split("\n") if line}


LOCALES = ("en", "ko", "zh-CN", "zh-TW", "fr", "de", "es")
SWITCHER = re.compile(r"Language / 言語|🌐 *(言語|Language)")
LOCALE_SUFFIX = re.compile(r"[.\-](" + "|".join(LOCALES) + r")\.md$")
# Any markdown link to a `.md` file that is not an absolute URL. Restricting this
# to `./` and `../` prefixes missed same-directory links, and a dead
# `[日本語](verification-results.md)` in the same directory is just as dead. The
# `](` prefix keeps it unambiguous: an inline code span containing a filename has
# no such prefix.
RELATIVE_LINK = re.compile(r"\]\((?!https?://|/)([^)#\s]+\.md)")

# Directories whose pairs are checked. The pattern library under `solutions/`
# carries 108 eight-locale README sets that are generated, and including them
# would make a single missing switcher in a generated file fail this check
# without telling anyone which generator to fix.
PAIR_DIRS = ("docs", "docs/ja", "docs/guides", "solutions/amplify-portal/docs")
# `docs/agent/` is link-checked but not pair-checked. It holds the agent-facing notes
# that used to live in AGENTS.md, a single mixed-language file with no translation to
# pair with. Its links do need checking: they arrived as root-relative paths and 54 of
# them resolved to `docs/docs/...` the moment the content moved one directory down.
LINK_DIRS = ("docs", "docs/ja", "docs/en", "docs/guides", "docs/agent", "solutions/amplify-portal/docs")


def _switcher(path: pathlib.Path) -> bool:
    return bool(SWITCHER.search(path.read_text(encoding="utf-8")))


def find_pairs() -> list[list[pathlib.Path]]:
    """Every group of files that are translations of one another."""
    published = _in_repository()
    groups: list[list[pathlib.Path]] = []
    claimed: set[pathlib.Path] = set()

    def exists(path: pathlib.Path) -> bool:
        return path.exists() and path in published

    # A Japanese file in docs/ja/ or docs/ paired with the same name in docs/en/.
    for parent in (ROOT / "docs" / "ja", ROOT / "docs"):
        if not parent.is_dir():
            continue
        for base in sorted(parent.glob("*.md")):
            twin = ROOT / "docs" / "en" / base.name
            if exists(base) and exists(twin) and base not in claimed:
                groups.append([base, twin])
                claimed.update({base, twin})

    # Suffix conventions inside one directory, two locales or eight.
    for name in PAIR_DIRS:
        parent = ROOT / name
        if not parent.is_dir():
            continue
        for base in sorted(parent.glob("*.md")):
            if base in claimed or LOCALE_SUFFIX.search(base.name) or not exists(base):
                continue
            group = [base]
            for locale in LOCALES:
                for candidate in (
                    parent / f"{base.stem}.{locale}.md",
                    parent / f"{base.stem}-{locale}.md",
                ):
                    if exists(candidate):
                        group.append(candidate)
            if len(group) > 1:
                groups.append(group)
                claimed.update(group)
    return groups


def check_switchers() -> list[str]:
    findings = []
    for group in find_pairs():
        without = [p for p in group if not _switcher(p)]
        if without:
            names = ", ".join(str(p.relative_to(ROOT)) for p in without)
            findings.append(f"no language switcher, so the translation is unreachable from it: {names}")
    return findings


def check_links() -> list[str]:
    published = _in_repository()
    findings = []
    for name in LINK_DIRS:
        parent = ROOT / name
        if not parent.is_dir():
            continue
        for md in sorted(parent.glob("*.md")):
            if published and md not in published:
                continue
            lines = md.read_text(encoding="utf-8").split("\n")
            for number, line in enumerate(lines, start=1):
                for match in RELATIVE_LINK.finditer(line):
                    target = (md.parent / match.group(1)).resolve()
                    if not target.exists():
                        reason = "resolves to nothing"
                    elif published and target not in published:
                        reason = "resolves to a file that is not in the repository"
                    else:
                        continue
                    findings.append(f"{md.relative_to(ROOT)}:{number}: link {reason}: {match.group(1)}")
    return findings


def main() -> int:
    pairs = find_pairs()
    if not pairs:
        print("DOC PAIRS: FAIL — found no pairs at all, so this check proves nothing")
        return 1

    findings = check_switchers() + check_links()
    if findings:
        print(f"\ndoc-pairs ({len(findings)}):")
        for finding in findings:
            print(f"  {finding}")
        print(f"\nDOC PAIRS: {len(findings)} finding(s)")
        return 1

    files = sum(len(group) for group in pairs)
    print(f"DOC PAIRS: PASS ({len(pairs)} pairs, {files} files, all switchers and relative links resolve)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
