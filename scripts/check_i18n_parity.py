#!/usr/bin/env python3
"""Check translations exist where declared, and match the source's structure.

## What this adds over the checks already here

`check_doc_pairs.py` verifies that translations which exist are reachable and their
links resolve. `check_doc_structural_parity.py` compares structure — but only for
`docs/ja` against `docs/en`, which is 28 of 209 translation groups, and nothing in
CI looked at any locale other than English.

Both are existence-driven: a group is whatever files happen to be on disk, so a
missing translation is not a finding, it is simply a smaller group. That is the
defect a translation actually produces. A section added to the Japanese source and
never carried across leaves no trace — the other file renders, its links resolve,
and the only reader affected is the one who cannot read Japanese.

This reads `docs/i18n-manifest.toml`, which declares which documents must exist in
which languages, and reports two things:

1. **Missing** — a locale the manifest requires and no file provides.
2. **Structure** — a locale whose heading structure differs from the source's.

## Headings are counted outside fenced code blocks

`check_doc_structural_parity.py` does not skip fences, so `# Wait for AVAILABLE
status` inside a shell block counts as a heading. On
`docs/ja/portal-deployment-runbook.md` that turns 22 real headings into 37 and makes
the positional section walk misalign, which is why its reported mismatch count is
larger than the work it represents. Counting outside fences here gives a number that
means what it says.

## Why the totals are ratcheted rather than strict

Measured 2026-08-15: 51 of 209 groups differ in at least one locale, 277
locale-level differences in total. The six non-English locales drift together —
they were produced in one batch and never re-run as the Japanese sources grew. A
strict gate would fail every pull request on untouched debt, and a gate that does
that is switched off within a week. The baseline can only go down.

Use `--strict` when working through a specific group.

## Usage

    python3 scripts/check_i18n_parity.py                      # report
    python3 scripts/check_i18n_parity.py --max-missing 6 --max-structure 277
    python3 scripts/check_i18n_parity.py --strict
    python3 scripts/check_i18n_parity.py --group solutions/industry/legal-compliance/README.md
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "docs" / "i18n-manifest.toml"

HEADING = re.compile(r"^#{1,6} ")
FENCE = re.compile(r"^\s*```")

# Baselines measured on 2026-08-15 against docs/i18n-manifest.toml. Ratchets, not
# targets: they may only go down. Raising one is the change a reviewer should stop.
#
# missing = 0. It was 1 —
#   docs/aws-feature-requests/fsxn-s3ap-improvements.md, reported as having no
#   English twin. It turned out to BE the English one: 15,725 characters of body with
#   zero CJK, Japanese only in "Appendix B: Japanese Summary". A single bilingual
#   document with no twin, which the twin-based inference could not see. The manifest
#   now declares its locale and the finding is gone, correctly.
#
# structure = 269: dominated by the six non-English locales, which were produced in
#   one batch and never re-run as the Japanese sources grew. The largest are the root
#   README (delta -7 in six locales) and the industry demo guides, where Japanese
#   gained a whole FlexClone scenario the translations never received.
#
#   Ratcheted down twice while the portal authorization work was under way: 271 -> 270
#   when the Japanese authorization model gained the "Related Documents" section its
#   English twin already had, and 270 -> 269 when GETTING-STARTED.md's duplicated and
#   truncated "next steps" sections were merged into the one the English has. The number
#   only ratchets down: raising it admits a new mismatch, which is what this stops.
DEFAULT_MAX_MISSING = 0
DEFAULT_MAX_STRUCTURE = 264


def tracked() -> set[str]:
    """Files a reader of the repository can open.

    Returns:
        Repository-relative paths that git knows about and does not ignore.
    """
    proc = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return {line for line in proc.stdout.splitlines() if line}


def load_manifest() -> tuple[list[str], str, list[dict[str, object]]]:
    """Read the locale set and rules.

    Returns:
        Tuple of (all locales, source locale, rules in declaration order).

    Raises:
        SystemExit: When a rule is missing a field, which would otherwise apply a
            requirement nobody stated a reason for.
    """
    data = tomllib.loads(MANIFEST.read_text(encoding="utf-8"))
    locales_all = list(data["locales_all"])
    source = str(data["source_locale"])
    rules: list[dict[str, object]] = []
    for rule in data.get("rule", []):
        for field in ("glob", "locales", "why"):
            if field not in rule:
                sys.exit(f"i18n-manifest.toml: a rule is missing '{field}': {rule}")
        declared = rule["locales"]
        if declared == "all":
            locales: list[str] | str = locales_all
        elif declared == "keep":
            locales = "keep"
        else:
            locales = list(declared)
        rules.append({"glob": rule["glob"], "locales": locales, "why": rule["why"]})
    return locales_all, source, rules


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Compile a path-aware glob where `*` does not cross a directory separator.

    `fnmatch` translates `*` to `.*`, which spans `/`. That made
    `solutions/*/*/README.md` match
    `solutions/genai/kb-selfservice-curation/sample-data/README.md` and demand seven
    translations of a sample-data README — a rule appearing to say one thing and
    matching another, which is the failure mode a manifest is supposed to remove.

    Args:
        pattern: Glob with `*` (within one path segment) and `**` (any depth).

    Returns:
        An anchored compiled pattern.
    """
    out: list[str] = []
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if pattern.startswith("**/", index):
            out.append(r"(?:[^/]+/)*")
            index += 3
        elif char == "*":
            out.append(r"[^/]*")
            index += 1
        elif char == "?":
            out.append(r"[^/]")
            index += 1
        else:
            out.append(re.escape(char))
            index += 1
    return re.compile("^" + "".join(out) + "$")


_REGEX_CACHE: dict[str, re.Pattern[str]] = {}


def matches(path: str, pattern: str) -> bool:
    """Whether a repository-relative path matches a manifest glob.

    Args:
        path: Repository-relative path.
        pattern: Glob from the manifest.

    Returns:
        True when the path matches with segment-aware semantics.
    """
    compiled = _REGEX_CACHE.get(pattern)
    if compiled is None:
        compiled = _glob_to_regex(pattern)
        _REGEX_CACHE[pattern] = compiled
    return bool(compiled.match(path))


def required_for(path: str, rules: list[dict[str, object]]) -> list[str] | str | None:
    """Locales required for a source document.

    Args:
        path: Repository-relative path of the source document.
        rules: Rules from the manifest, in declaration order.

    Returns:
        The required locale list, the string ``"keep"`` when whatever exists must
        be held without adding an obligation, or None when no rule matches.
    """
    found: list[str] | str | None = None
    for rule in rules:  # later rules win
        if matches(path, str(rule["glob"])):
            declared = rule["locales"]
            found = declared if declared == "keep" else list(declared)  # type: ignore[arg-type]
    return found


def base_locale_of(
    source: str,
    published: set[str],
    source_locale: str,
    declared: list[str] | None = None,
) -> str:
    """Which language the unsuffixed file is actually written in.

    Three cases, in order of confidence:

    1. **The manifest says so.** A rule naming exactly one locale is a statement
       that the unsuffixed file *is* that locale. `docs/aws-feature-requests/
       fsxn-s3ap-improvements.md` is English with no twin at all — a single
       bilingual document whose Japanese is one appendix — so inference has nothing
       to work from and the declaration is the only source of truth.
    2. **A `X.ja.md` twin exists**, so `X.md` is not the Japanese one.
       `solutions/amplify-portal/README.md` is the case: English, with
       `README.ja.md` beside it.
    3. **Otherwise the nominal source locale**, which is right for the other ~200
       groups.

    Deciding by position alone made case 2 read as Japanese, so the checker asked
    for a `README.en.md` that should not exist while the English text sat in front
    of it. Deciding by inference alone made case 1 report the English document as
    missing its English translation.

    Args:
        source: Unsuffixed document path.
        published: Paths git knows about.
        source_locale: The manifest's nominal source locale.
        declared: Locales the manifest requires for this document, when known.

    Returns:
        The locale the unsuffixed file provides.
    """
    if declared is not None and len(declared) == 1:
        return declared[0]
    stem = source[: -len(".md")]
    if f"{stem}.{source_locale}.md" in published:
        return "en"
    return source_locale


def sibling(source: str, locale: str, source_locale: str) -> list[str]:
    """Candidate paths for a locale, under either convention in this repository.

    Args:
        source: Repository-relative path of the source document.
        locale: Target locale code.
        source_locale: The manifest's source locale.

    Returns:
        Candidate paths, most likely first. Both the `X.<loc>.md` and `X-<loc>.md`
        suffix forms are produced because both are in use, and the
        `docs/<loc>/` directory form is produced for paths under `docs/ja/`.
    """
    if locale == source_locale:
        return [source]
    candidates: list[str] = []
    if source.startswith(f"docs/{source_locale}/"):
        candidates.append(source.replace(f"docs/{source_locale}/", f"docs/{locale}/", 1))
    stem = source[: -len(".md")]
    candidates.append(f"{stem}.{locale}.md")
    candidates.append(f"{stem}-{locale}.md")
    return candidates


def headings(path: Path) -> list[str]:
    """Headings outside fenced code blocks.

    Args:
        path: File to read.

    Returns:
        Stripped heading lines, in order. A `# comment` inside a shell fence is
        not a heading, which is the distinction the older parity check misses.
    """
    out: list[str] = []
    in_fence = False
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence and HEADING.match(line):
            out.append(line.strip())
    return out


def _resolve_group(source: str, locales: list[str], source_locale: str, published: set[str]) -> dict[str, str]:
    """Map each present locale to its path.

    Args:
        source: Source document path.
        locales: Locales to look for.
        source_locale: The manifest's source locale.
        published: Paths git knows about.

    Returns:
        Mapping of locale to the path that provides it. Absent locales are omitted.
    """
    base = base_locale_of(source, published, source_locale, locales)
    group: dict[str, str] = {base: source}
    for locale in locales:
        if locale == base:
            continue
        # Candidates are derived relative to the locale the unsuffixed file
        # actually provides. Deriving them from the manifest's nominal source
        # locale made the inverted group ask for its own base file when looking up
        # Japanese, so `README.ja.md` — sitting right there — was reported missing.
        for candidate in sibling(source, locale, base):
            if candidate == source:
                continue
            if candidate in published:
                group[locale] = candidate
                break
    return group


def analyse(only: str | None = None) -> tuple[list[str], list[str], int]:
    """Compare every governed document against its declared locales.

    Args:
        only: When given, restrict the analysis to this source path.

    Returns:
        Tuple of (missing findings, structure findings, number of groups examined).
    """
    locales_all, source_locale, rules = load_manifest()
    published = tracked()

    missing: list[str] = []
    structure: list[str] = []
    examined = 0

    # Source documents are the tracked .md files that are not themselves a
    # localized sibling. The inverted case — solutions/amplify-portal/README.md is
    # English with README.ja.md beside it — is handled by treating the unsuffixed
    # file as the source whichever language it happens to be in: parity is about
    # structure matching across the group, and that does not depend on which member
    # is the original.
    others = [loc for loc in locales_all if loc != source_locale]
    suffix = re.compile(r"[.\-](" + "|".join(others) + r")\.md$")
    # A file under `docs/en/` is the English SIDE of a `docs/ja/` pair, not a source
    # in its own right. Without this it was read as one, and the checker asked for
    # `docs/en/foo.en.md` — 34 of the first run's "missing" findings were that,
    # which is a checker reporting its own bug as a repository defect.
    locale_dir = re.compile(r"^docs/(" + "|".join(others) + r")/")

    for path in sorted(p for p in published if p.endswith(".md")):
        if suffix.search(path) or locale_dir.match(path):
            continue
        if only and path != only:
            continue
        required = required_for(path, rules)
        if required is None:
            continue

        if required == "keep":
            # No obligation is added; the locales present today become the
            # requirement, so losing one is a finding and gaining one is free.
            present = _resolve_group(path, locales_all, source_locale, published)
            if len(present) <= 1:
                continue
            required = sorted(present)

        group = _resolve_group(path, required, source_locale, published)
        if len(group) <= 1 and set(group) <= {source_locale}:
            # Only the source exists. Report the absences, but do not then compare
            # structure against nothing.
            for locale in required:
                if locale not in group and locale != source_locale:
                    missing.append(f"{path}: no {locale} translation")
            if len(required) > 1:
                examined += 1
            continue

        examined += 1
        for locale in required:
            if locale not in group:
                missing.append(f"{path}: no {locale} translation")

        base_headings = headings(ROOT / group.get(source_locale, path))
        for locale, target in sorted(group.items()):
            if locale == source_locale or target == path:
                continue
            other = headings(ROOT / target)
            if len(other) != len(base_headings):
                structure.append(
                    f"{target}: {len(other)} headings, source {path} has {len(base_headings)} "
                    f"(delta {len(other) - len(base_headings):+d})"
                )

    return missing, structure, examined


def _report_by_source(structure: list[str], examined: int) -> int:
    """Print the structural backlog as a work queue rather than a count.

    271 findings is not 271 problems. Measured 2026-08-15: they come from 51 source
    documents, and most contribute exactly 7 — one per locale, because the six
    non-English translations were produced in one batch and none of them received
    the sections the Japanese source gained afterwards. `en` has 41 findings and each
    of the other six has exactly 36, which is that symmetry showing through.

    So the unit of work is the source document: bringing one back into line closes
    about seven findings at once. Sorting by (locales affected, largest gap) puts the
    documents where a reader loses the most at the top — `docs/guides/
    fpolicy-setup-guide.md` is 45 headings in Japanese against 10-11 in every
    translation, which means those files are summaries rather than translations.

    Args:
        structure: Structural findings from :func:`analyse`.
        examined: Number of governed groups, for the header line.

    Returns:
        0 — this is a reporting mode, not a gate.
    """
    per_source: dict[str, list[int]] = {}
    for finding in structure:
        _, _, rest = finding.partition(":")
        source = re.search(r"source (\S+\.md)", rest)
        delta = re.search(r"delta ([-+]\d+)", rest)
        if not source or not delta:
            continue
        per_source.setdefault(source.group(1), []).append(int(delta.group(1)))

    print(
        f"I18N PARITY backlog: {len(structure)} finding(s) from {len(per_source)} source document(s), {examined} governed\n"
    )
    print(f"{'locales':>7} {'max gap':>8}  source document")
    ordered = sorted(per_source.items(), key=lambda kv: (-len(kv[1]), -max(abs(d) for d in kv[1])))
    for source, deltas in ordered:
        print(f"{len(deltas):>7} {max(abs(d) for d in deltas):>8}  {source}")
    print(
        "\nOne source document is one unit of work: its translations are re-run together, "
        "so closing the top entry removes about seven findings. `scripts/translate_readmes.py` "
        "is the existing Bedrock pipeline, but its output needs reading before it is committed — "
        "a machine translation that drops a section leaves exactly the gap this check exists to find."
    )
    return 0


def main(argv: list[str]) -> int:
    """Report missing translations and structural drift.

    Args:
        argv: Command-line arguments.

    Returns:
        1 when a threshold is exceeded or `--strict` finds anything, else 0.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="fail on any finding")
    parser.add_argument("--max-missing", type=int, default=DEFAULT_MAX_MISSING)
    parser.add_argument("--max-structure", type=int, default=DEFAULT_MAX_STRUCTURE)
    parser.add_argument("--group", default=None, help="restrict to one source document")
    parser.add_argument("--quiet", action="store_true", help="totals only")
    parser.add_argument(
        "--by-source",
        action="store_true",
        help="group the structural backlog by source document, worst first",
    )
    args = parser.parse_args(argv)

    missing, structure, examined = analyse(args.group)

    if args.by_source:
        return _report_by_source(structure, examined)

    if not examined:
        print("I18N PARITY: FAIL — no governed documents found, so this check proves nothing")
        return 1

    if not args.quiet:
        if missing:
            print(f"\nmissing translations ({len(missing)}):")
            for finding in missing:
                print(f"  {finding}")
        if structure:
            print(f"\nstructural drift ({len(structure)}):")
            for finding in structure[:40]:
                print(f"  {finding}")
            if len(structure) > 40:
                print(f"  ... and {len(structure) - 40} more")

    print(
        f"\nI18N PARITY: {examined} group(s) governed by docs/i18n-manifest.toml, "
        f"{len(missing)} missing, {len(structure)} structural"
    )

    guidance = (
        "\nA structural difference means one language has a section the other does not. "
        "Port the missing section rather than deleting the other side — the gap almost "
        "always means a reader is short of something, not that one side has something spare."
    )

    if args.strict and (missing or structure):
        print(guidance)
        return 1

    failed = False
    if len(missing) > args.max_missing:
        print(f"\n{len(missing)} missing exceeds the baseline of {args.max_missing}.")
        failed = True
    if len(structure) > args.max_structure:
        print(f"\n{len(structure)} structural exceeds the baseline of {args.max_structure}.")
        failed = True
    if failed:
        print(guidance)
        return 1

    for label, count, ceiling in (
        ("missing", len(missing), args.max_missing),
        ("structural", len(structure), args.max_structure),
    ):
        if count < ceiling:
            print(f"{label} is below its baseline of {ceiling}; lower it to {count} to lock the progress in.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
