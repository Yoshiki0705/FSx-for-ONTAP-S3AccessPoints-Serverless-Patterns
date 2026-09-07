#!/usr/bin/env python3
"""Fail on a GitHub repository name that only still resolves because of a redirect.

## Why a link checker cannot find this

A rename is normal. What has no symptom is that GitHub keeps serving the old name
through a redirect: the link returns 200, a link checker reports it reachable, and
two documents can spell the same repository differently while both look fine. The
Adoption Playbook hit this with seven renamed repositories whose links all reported
reachable, and its `tools/check_cross_repo.py` grew `check_repo_names()` for it.

Reachability is the wrong question. This asks a different one: **is the name we wrote
the name the repository has?** The answer comes from the URL the request lands on,
not from its status code.

## One deliberate difference from the Playbook's version

**Fenced code blocks are scanned here, not skipped.** The Playbook blanks them out,
because there a citation inside a fence is an example rather than a claim. In this
repository the opposite is true: the majority of repository references sit inside

    ```bash
    git clone https://github.com/<owner>/<repo>.git
    ```

in a demo guide, and that is a URL a reader pastes into a terminal. Skipping fences
here would have skipped 98 files carrying a clone URL that 404s — the single most
user-facing instance of exactly what this check is for.

## What this cannot see

**A difference of casing alone.** Measured 2026-09-07: GitHub serves
`Yoshiki0705/vmware-migration-ec2-ontap` at the URL requested and reports that URL
back, while `Yoshiki0705/fsxn-cyber-resilience-patterns` redirects to
`FSx-for-ONTAP-Cyber-Resilience-Patterns`. So a rename is visible in the landing URL
and a casing difference is not, and no redirect-based check can close that gap. The
REST API's `full_name` would answer it; that costs a rate limit and a token, and it is
a different question from the one this gate was asked to settle. Recorded rather than
silently left out.

## What a 404 means, and what it does not

A 404 is reported separately from a redirect, because it has more than one cause: the
repository was deleted, or renamed with the redirect expired, **or it is private and
this request is unauthenticated.** The check cannot tell those apart and does not
guess. It says the name does not resolve anonymously, which is what a reader of a
public repository would experience, and leaves the interpretation to a human.

## Shape of the code

`collect()` and `audit()` take their inputs as arguments and touch no network, so the
behaviour that decides whether this gate fires is testable without one. `resolve()` is
the only function that reaches out. A checker whose verdict can only be exercised by
running it against the live internet is a checker whose negative case never gets
tested.

## Usage

    python3 scripts/check_repo_name_redirects.py            # report, exit 1 on findings
    python3 scripts/check_repo_name_redirects.py --quiet     # one summary line
    python3 scripts/check_repo_name_redirects.py --list      # names only, no network

Exit codes: 0 clean, 1 stale or unresolvable names found, 2 the network was
unusable and nothing could be concluded.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from collections.abc import Callable, Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Text a reader follows a link from. Templates and code are excluded: a URL there is
# a value, not a reference someone clicks.
PROSE_SUFFIXES = {".md", ".txt"}

# `github.com` serves more than repositories. These first path segments are product
# surfaces, so `github.com/apps/renovate` is not a repository name that can go stale.
NOT_OWNERS = {
    "apps",
    "orgs",
    "users",
    "settings",
    "marketplace",
    "features",
    "sponsors",
    "topics",
    "collections",
    "readme",
    "about",
    "pricing",
    "security",
    "enterprise",
    "login",
    "signup",
    "notifications",
}

# Trailing punctuation that belongs to the prose rather than the URL. `)` and `>` come
# from Markdown link syntax; `.` and `,` from the end of a sentence.
TRAILING = ".,;:!?)>\"'"

REPO_REF = re.compile(r"https://github\.com/(?P<owner>[A-Za-z0-9][A-Za-z0-9._-]*)/(?P<repo>[A-Za-z0-9][A-Za-z0-9._-]*)")


def tracked_prose() -> list[Path]:
    """Every tracked .md and .txt file.

    Tracked rather than globbed: an untracked scratch file is not something a reader
    can reach, and `.private/` is deliberately outside git for content that must not
    be published.
    """
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [ROOT / name for name in result.stdout.split("\0") if name and Path(name).suffix in PROSE_SUFFIXES]


def collect(paths: Iterable[Path] | None = None, root: Path = ROOT) -> dict[str, list[str]]:
    """Map each referenced `owner/repo` to the files referencing it.

    Args:
        paths: Files to scan. Defaults to every tracked `.md` and `.txt` file.
        root: Directory the reported paths are made relative to.

    Returns:
        A mapping of `owner/repo` to the relative paths mentioning it, in the order
        the files were scanned.
    """
    seen: dict[str, list[str]] = defaultdict(list)
    for path in tracked_prose() if paths is None else paths:
        rel = path.relative_to(root).as_posix()
        try:
            body = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for match in REPO_REF.finditer(body):
            owner = match.group("owner")
            if owner.lower() in NOT_OWNERS:
                continue
            repo = match.group("repo").rstrip(TRAILING)
            # A clone URL ends in `.git`; the repository is the same one without it.
            if repo.endswith(".git"):
                repo = repo[: -len(".git")]
            if not repo:
                continue
            slug = f"{owner}/{repo}"
            if rel not in seen[slug]:
                seen[slug].append(rel)
    return dict(seen)


def resolve(slug: str) -> tuple[str, str | None]:
    """Ask GitHub what the canonical name of `slug` is.

    Args:
        slug: An `owner/repo` reference as written in the prose.

    Returns:
        A pair of `(outcome, detail)`. Outcome is `ok`, `renamed`, `missing` or
        `unreachable`. `renamed` carries the canonical `owner/repo`; `missing` and
        `unreachable` carry the reason. `ok` carries `None`.
    """
    request = urllib.request.Request(
        f"https://github.com/{slug}",
        headers={"User-Agent": "repo-name-redirect-check"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            final = response.url
    except urllib.error.HTTPError as exc:
        # 404 is a finding about the name. Every other status is about GitHub or the
        # runner, and saying "renamed" on a 503 would be a false accusation.
        if exc.code == 404:
            return "missing", "404 (deleted, redirect expired, or now private)"
        return "unreachable", f"HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError) as exc:
        return "unreachable", str(exc)

    canonical = "/".join(final.rstrip("/").split("/")[-2:])
    # Compared case-sensitively. Folding case would suppress a rename whose only
    # change was capitalisation, and it cannot buy anything back: GitHub echoes the
    # casing that was requested, so a casing difference never reaches this line.
    if canonical != slug:
        return "renamed", canonical
    return "ok", None


def audit(
    references: dict[str, list[str]],
    resolver: Callable[[str], tuple[str, str | None]] = resolve,
) -> tuple[list[str], list[str]]:
    """Turn resolved names into findings.

    Args:
        references: Output of `collect()`.
        resolver: Injected so the verdict can be tested without the network.

    Returns:
        A pair of `(stale, unreachable)` message lists. `stale` holds findings about
        names; `unreachable` holds names about which nothing was concluded.
    """
    stale: list[str] = []
    unreachable: list[str] = []

    for slug, files in sorted(references.items()):
        outcome, detail = resolver(slug)
        listed = ", ".join(files[:4]) + (f" and {len(files) - 4} more" if len(files) > 4 else "")
        if outcome == "renamed":
            stale.append(
                f"{slug} is now {detail}. The old name still resolves through a redirect, "
                f"so nothing else reports it. Referenced by: {listed}"
            )
        elif outcome == "missing":
            stale.append(f"{slug} does not resolve: {detail}. Referenced by: {listed}")
        elif outcome == "unreachable":
            unreachable.append(f"{slug}: {detail}")

    return stale, unreachable


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true", help="one summary line")
    parser.add_argument("--list", action="store_true", help="list referenced names and exit, no network")
    args = parser.parse_args()

    references = collect()

    if args.list:
        for slug, files in sorted(references.items()):
            print(f"{slug}  ({len(files)} file(s))")
        return 0

    stale, unreachable = audit(references)

    if unreachable and not stale:
        # Nothing was concluded, so do not report a clean run. Exit 2 keeps a flaky
        # runner distinguishable from a repository that really moved.
        print(f"REPO NAMES: {len(unreachable)} name(s) could not be checked", file=sys.stderr)
        for line in unreachable:
            print(f"  {line}", file=sys.stderr)
        return 2

    if stale:
        print(
            f"REPO NAMES: {len(stale)} stale name(s) across {len(references)} referenced repositories",
            file=sys.stderr,
        )
        for line in stale:
            print(f"  {line}", file=sys.stderr)
        if unreachable:
            print("  --- not checked ---", file=sys.stderr)
            for line in unreachable:
                print(f"  {line}", file=sys.stderr)
        return 1

    if not args.quiet:
        print(f"REPO NAMES: {len(references)} referenced repositories, all canonical")
    else:
        print(f"REPO NAMES: {len(references)} ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
