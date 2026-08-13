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
# Image targets, which were not checked at all. A dead one renders as a broken-image
# placeholder rather than as text, so it is more visible than a dead link to a reader
# and less visible to the author: it looks fine in a diff.
# `![Audit Trail](screenshots/portal-audit-trail.png)` sat in both the Japanese and
# the English guide, pointing at a name that has never existed -- the files are
# portal-ja-audit.png and portal-en-audit.png.
RELATIVE_IMAGE = re.compile(r"!\[[^\]]*\]\((?!https?://|/|data:)([^)#\s]+)")
# The HTML form, which markdown allows and which is the only way to set a width. A
# phone screenshot is 390px wide and renders at full size otherwise, so this form gets
# used exactly where it is easiest to forget it is not being checked.
HTML_IMAGE = re.compile(r"<img[^>]*\ssrc=[\"'](?!https?://|/|data:)([^\"'#]+)")
# Removed before either pattern runs. Non-greedy so adjacent spans on one line do not
# merge into a single match that swallows the text between them.
CODE_SPAN = re.compile(r"`[^`]*`")

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


def _pattern_doc_dirs() -> tuple[str, ...]:
    """The per-pattern `docs/` directories, for link resolution only.

    These were outside LINK_DIRS until 2026-08-12, and all 224 demo guides had broken
    references as a result: they were written `../../docs/...`, which from
    `solutions/industry/<pattern>/docs/` resolves to `solutions/industry/docs/` -- one
    level short of the repository root, and a directory that has never existed. Every
    cross-reference and every embedded screenshot in every demo guide pointed at nothing,
    in eight languages, and nothing failed because nothing was looking.

    Deliberately not added to LINK_DIRS itself: that tuple also feeds the link-language
    check, and these guides carry roughly a hundred pre-existing cross-locale references
    (a Korean guide linking the Japanese README when a Korean one exists). Those are real
    but are a separate cleanup, and a gate that fails on untouched debt gets disabled.

    Returns:
        Repository-relative paths, derived from disk so a new pattern is covered as soon
        as it is added rather than when someone remembers to extend a list.
    """
    return tuple(
        str(path.relative_to(ROOT))
        for path in sorted((ROOT / "solutions" / "industry").glob("*/docs"))
        if path.is_dir()
    )


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


# A markdown link, with its text, allowing the text to wrap. DOTALL matters: a link
# whose text runs across a line break is still one link, and a line-based pattern reads
# it as no link at all -- which is how the last of these hid.
LINK_WITH_TEXT = re.compile(r"\[([^\]]*)\]\((?!https?://|/)([^)#\s]+\.md)", re.DOTALL)
# Link text, or the line around it, that names a language. Those are deliberate: a
# "(日本語)" beside an English link is an offer, not a mistake.
NAMES_A_LANGUAGE = re.compile(
    r"\(JA\)|\(EN\)|\(KO\)|日本語|Japanese|English|한국어|简体|繁體|Français|Deutsch|Español",
    re.IGNORECASE,
)


def _locale_of(path: pathlib.Path) -> str | None:
    """The language a document is written in, under either convention in this repo.

    `docs/` uses a directory per locale; `solutions/amplify-portal/docs/` uses the
    Japanese file as the base name with an `.en.md` twin. Both are in use, so both are
    recognised here.

    Takes an absolute path. It was given a repo-relative one at first, and the
    `.exists()` calls below then resolved against the working directory instead of the
    tree being examined -- which is invisible in production, where those happen to be
    the same, and made every fixture in the tests read as "language unknown".
    """
    try:
        parts = path.relative_to(ROOT).parts
    except ValueError:
        parts = path.parts
    for locale in LOCALES + ("ja",):
        if locale in parts:
            return locale
    stem = path.name[: -len(".md")]
    for locale in LOCALES:
        if stem.endswith(f".{locale}"):
            return locale
    # The language of an unsuffixed name is decided by which twin exists beside it, and
    # the two families disagree. `solutions/amplify-portal/docs/foo.md` is Japanese with
    # `foo.en.md` alongside; `solutions/amplify-portal/README.md` is English with
    # `README.ja.md` alongside. Assuming one convention made the English README read as
    # "language unknown", so the check skipped the very file whose wrong link prompted
    # it -- a link to the Japanese tabs guide from the English README.
    if path.with_name(f"{stem}.ja.md").exists():
        return "en"
    if path.with_name(f"{stem}.en.md").exists():
        return "ja"
    return None


def _sibling_in(target: pathlib.Path, locale: str) -> pathlib.Path | None:
    """The same document in `locale`, if the repository has one."""
    stem = target.name[: -len(".md")]
    for known in LOCALES:
        if stem.endswith(f".{known}"):
            stem = stem[: -len(f".{known}")]
            break
    candidates = []
    if locale == "ja":
        candidates.append(target.with_name(f"{stem}.md"))
    candidates.append(target.with_name(f"{stem}.{locale}.md"))
    parts = list(target.parts)
    for index, part in enumerate(parts):
        if part in LOCALES + ("ja",):
            swapped = parts.copy()
            swapped[index] = locale
            candidates.append(pathlib.Path(*swapped))
            break
    return next((candidate for candidate in candidates if candidate.exists()), None)


def check_link_language() -> list[str]:
    """Cross-references that send the reader into a language they were not reading.

    165 of these were live: an English document linking a Japanese file that had an
    English twin next to it, mostly in "Related documents" lists -- which is where a
    reader goes when they want more, and so the worst place to land in a script they
    cannot read. Every one of the eight portal READMEs pointed at the English user
    guide, and every one of them, including the English README, pointed at the Japanese
    tabs guide.

    Nothing caught it because the link resolves: the file is there, the anchor is
    valid, and only its language is wrong. The one reader who would notice is the one
    who cannot read the result.

    Two shapes are deliberate and skipped: the language switcher, and a link whose
    text or line names a language. A target that git ignores is skipped too -- the
    Japanese verification results are local-only, so "the same document in your
    language" does not exist for a reader of the repository.
    """
    published = _in_repository()
    findings = []
    for name in LINK_DIRS + ("solutions/amplify-portal", "docs/aws-feature-requests"):
        parent = ROOT / name
        if not parent.is_dir():
            continue
        for md in sorted(parent.glob("*.md")):
            if published and md not in published:
                continue
            relative = md.relative_to(ROOT)
            source_locale = _locale_of(md)
            if source_locale is None:
                continue
            text = md.read_text(encoding="utf-8")
            lines = text.split("\n")
            for match in LINK_WITH_TEXT.finditer(text):
                number = text.count("\n", 0, match.start()) + 1
                line = lines[number - 1] if number <= len(lines) else ""
                if SWITCHER.search(line) or NAMES_A_LANGUAGE.search(match.group(1)) or NAMES_A_LANGUAGE.search(line):
                    continue
                target = (md.parent / match.group(2)).resolve()
                if not target.exists():
                    continue
                if _locale_of(target) in (None, source_locale):
                    continue
                better = _sibling_in(target, source_locale)
                if not better or better.resolve() == target:
                    continue
                if published and better.resolve() not in published:
                    continue
                findings.append(
                    f"{relative}:{number}: this document is {source_locale} but links "
                    f"{match.group(2)}; {better.relative_to(ROOT)} exists"
                )
    return findings


def check_links() -> list[str]:
    published = _in_repository()
    findings = []
    for name in LINK_DIRS + _pattern_doc_dirs():
        parent = ROOT / name
        if not parent.is_dir():
            continue
        for md in sorted(parent.glob("*.md")):
            if published and md not in published:
                continue
            lines = md.read_text(encoding="utf-8").split("\n")
            for number, raw in enumerate(lines, start=1):
                # An inline code span quotes a name rather than referring to a file, and
                # a doc explaining the syntax writes the whole `![alt](path)` form. The
                # `](` prefix alone does not distinguish that from a real reference.
                line = CODE_SPAN.sub("", raw)
                for kind, pattern in (("link", RELATIVE_LINK), ("image", RELATIVE_IMAGE), ("image", HTML_IMAGE)):
                    for match in pattern.finditer(line):
                        target = (md.parent / match.group(1)).resolve()
                        if not target.exists():
                            reason = "resolves to nothing"
                        elif published and target not in published:
                            reason = "resolves to a file that is not in the repository"
                        else:
                            continue
                        findings.append(f"{md.relative_to(ROOT)}:{number}: {kind} {reason}: {match.group(1)}")
    return findings


def main() -> int:
    pairs = find_pairs()
    if not pairs:
        print("DOC PAIRS: FAIL — found no pairs at all, so this check proves nothing")
        return 1

    findings = check_switchers() + check_links() + check_link_language()
    if findings:
        print(f"\ndoc-pairs ({len(findings)}):")
        for finding in findings:
            print(f"  {finding}")
        print(f"\nDOC PAIRS: {len(findings)} finding(s)")
        return 1

    files = sum(len(group) for group in pairs)
    print(
        f"DOC PAIRS: PASS ({len(pairs)} pairs, {files} files; switchers, links and images "
        f"resolve and cross-references stay in the reader's language)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
