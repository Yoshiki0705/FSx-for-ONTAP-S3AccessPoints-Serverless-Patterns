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
here would have skipped 91 files carrying a clone URL that 404s — the single most
user-facing instance of exactly what this check is for.

## The two questions, and why casing needs the second one

**Redirects do not reveal casing.** Measured 2026-09-07: GitHub serves
`Yoshiki0705/vmware-migration-ec2-ontap` at the URL requested and reports that URL back,
while `Yoshiki0705/fsxn-cyber-resilience-patterns` redirects to
`FSx-for-ONTAP-Cyber-Resilience-Patterns`. A rename is visible in the landing URL; a
casing difference is not.

That gap is not academic here. Of the five stale names this check was written to find, one
-- `vmware-migration-ec2-ontap`, whose real name is `VMware-Migration-EC2-ONTAP` -- sits
inside it, and the default mode reports that name as canonical.

So there are two modes:

- **default** -- resolve the HTML URL. No token, no rate limit, catches renames.
- **`--strict-casing`** -- additionally read `full_name` from the REST API, which is
  authoritative for capitalisation. Costs one API call per name against a 60/hour
  unauthenticated limit, so it is opt-in and runs weekly rather than on every invocation.
  Reads `GITHUB_TOKEN` when present to lift that limit.

`FSx-for-ONTAP-Observability-integrations` is the shape that makes this worth having: a
lowercase `i` where its siblings use `-Integrations`, correct as written, and impossible to
confirm without asking.

## What this still cannot see

A URL wrapped across two source lines. The first half yields no match at all, so the
reference is skipped silently rather than reported. `WRAPPED` handles the narrower case of a
name left with a trailing hyphen.

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
import json
import os
import re
import subprocess
import sys
import time
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
    "trending",
    "gist",
    "sponsors",
    "codespaces",
    "explore",
}

# Trailing punctuation that belongs to the prose rather than the URL. `)` and `>` come
# from Markdown link syntax; `.` and `,` from the end of a sentence.
TRAILING = ".,;:!?)>\"'"

# A repository name cannot end in a hyphen, so one here came from a line-wrapped URL in the
# source rather than from the name. Stripping it turned a false `missing` into a correct
# lookup; a name that is genuinely truncated mid-word is still wrong, but it is wrong in a
# way that resolves rather than one that accuses an existing repository of being gone.
WRAPPED = "-"

# Coverage floor. See the check in `main()`.
MINIMUM_REFERENCES = 10

# GitHub answers a burst of serial requests with 504 rather than a rate-limit header. Running
# the two checks back to back -- 29 names plus 24 hub paths -- produced 2-6 of them per run,
# on different URLs each time. Left unhandled the weekly job fails intermittently, and since
# exit 2 is treated as a failure there, the result is a gate that cries wolf. The same comment
# in published-articles-check.yml explains why that matters: a noisy required check is one
# people learn to force through.
RETRY_ON = (500, 502, 503, 504)
ATTEMPTS = 3
BACKOFF_SECONDS = 2.0


def fetch(request: urllib.request.Request) -> tuple[str | None, int | None, str | None]:
    """Open a request, retrying only the statuses that mean "ask again".

    Args:
        request: A prepared request whose scheme the caller has already asserted.

    Returns:
        `(landing_url, status, error)`. On success `error` is None. On a 404 the status is
        404 and `error` is None, because that is an answer rather than a failure. Otherwise
        `error` carries the reason and the caller reports it as unreachable.
    """
    last = "no attempt made"
    for attempt in range(1, ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(  # nosec B310 - scheme asserted by the caller  # noqa: S310
                request, timeout=30
            ) as response:
                return response.url, response.status, None
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None, 404, None
            last = f"HTTP {exc.code}"
            if exc.code not in RETRY_ON:
                return None, exc.code, last
        except (urllib.error.URLError, TimeoutError) as exc:
            last = str(exc)
        if attempt < ATTEMPTS:
            time.sleep(BACKOFF_SECONDS * attempt)
    return None, None, f"{last} after {ATTEMPTS} attempts"


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
            # Matched case-sensitively. These segments are always lowercase in a real
            # github.com product URL, while `Security`, `About` and `Enterprise` are all
            # plausible organisation names -- folding case would skip a real owner and
            # produce no diagnostic saying so.
            if owner in NOT_OWNERS:
                continue
            repo = match.group("repo").rstrip(TRAILING).rstrip(WRAPPED)
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
    url = f"https://github.com/{slug}"
    # `slug` comes out of a regex anchored on `https://github.com/`, so the scheme cannot
    # be steered from prose. Asserted anyway, because `urlopen` also honours `file:` and
    # the guarantee is one refactor away from being someone else's assumption.
    if not url.startswith("https://github.com/"):
        raise ValueError(f"refusing a non-GitHub https URL: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "repo-name-redirect-check"})
    final, status, error = fetch(request)
    # 404 is a finding about the name. Every other failure is about GitHub or the runner, and
    # saying "renamed" on a 503 would be a false accusation.
    if status == 404:
        return "missing", "404 (deleted, redirect expired, or now private)"
    if error is not None or final is None:
        return "unreachable", error or "no response"

    canonical = "/".join(final.rstrip("/").split("/")[-2:])
    # Compared case-sensitively. Folding case would suppress a rename whose only
    # change was capitalisation, and it cannot buy anything back: GitHub echoes the
    # casing that was requested, so a casing difference never reaches this line.
    if canonical != slug:
        return "renamed", canonical
    return "ok", None


def canonical_casing(slug: str) -> tuple[str, str | None]:
    """Ask the REST API for the repository's `full_name`.

    The HTML endpoint echoes back whatever casing was requested, so it cannot answer this.
    `full_name` can.

    Args:
        slug: An `owner/repo` reference as written in the prose.

    Returns:
        `("miscased", canonical)` when the capitalisation differs, `("ok", None)` when it
        matches, `("unreachable", reason)` when no verdict was reached. A 404 is left to the
        default mode, which already reports it.
    """
    url = f"https://api.github.com/repos/{slug}"
    if not url.startswith("https://api.github.com/repos/"):
        raise ValueError(f"refusing a non-GitHub https URL: {url}")
    headers = {"User-Agent": "repo-name-redirect-check", "Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    for attempt in range(1, ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(  # nosec B310 - scheme asserted above  # noqa: S310
                request, timeout=30
            ) as response:
                full_name = json.load(response).get("full_name")
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                # The default mode already reports a missing name; not this one's job.
                return "ok", None
            if exc.code not in RETRY_ON or attempt == ATTEMPTS:
                return "unreachable", f"HTTP {exc.code}"
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            if attempt == ATTEMPTS:
                return "unreachable", str(exc)
        time.sleep(BACKOFF_SECONDS * attempt)

    if not full_name:
        return "unreachable", "the API response carried no full_name"
    if full_name != slug:
        return "miscased", full_name
    return "ok", None


def audit(
    references: dict[str, list[str]],
    resolver: Callable[[str], tuple[str, str | None]] = resolve,
    casing_resolver: Callable[[str], tuple[str, str | None]] | None = None,
) -> tuple[list[str], list[str]]:
    """Turn resolved names into findings.

    Args:
        references: Output of `collect()`.
        resolver: Injected so the verdict can be tested without the network.
        casing_resolver: When given, each name that resolves cleanly is also checked for
            capitalisation. `None` skips that pass entirely.

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
        elif casing_resolver is not None:
            # Only for names that already resolve. Asking about capitalisation of a name that
            # was renamed or is gone would report the same problem twice under two labels.
            cased, canonical = casing_resolver(slug)
            if cased == "miscased":
                stale.append(
                    f"{slug} is capitalised {canonical} upstream. GitHub serves the casing "
                    f"requested and reports it back, so no redirect makes this visible. "
                    f"Referenced by: {listed}"
                )
            elif cased == "unreachable":
                unreachable.append(f"{slug} (casing): {canonical}")

    return stale, unreachable


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true", help="one summary line")
    parser.add_argument("--list", action="store_true", help="list referenced names and exit, no network")
    parser.add_argument(
        "--strict-casing",
        action="store_true",
        help="also read full_name from the REST API, the only way to see a casing-only rename",
    )
    args = parser.parse_args()

    references = collect()

    # A gate that certifies an empty corpus is a gate that a change to PROSE_SUFFIXES or to
    # what `git ls-files` returns can switch off in silence. The floor is deliberately far
    # below the current 29: it is asserting that scanning happened, not how much.
    if len(references) < MINIMUM_REFERENCES:
        print(
            f"REPO NAMES: only {len(references)} repository reference(s) found, expected at "
            f"least {MINIMUM_REFERENCES}. The scan found almost nothing, which is more likely "
            "to be a broken file filter than a repository that stopped linking anywhere.",
            file=sys.stderr,
        )
        return 1

    if args.list:
        for slug, files in sorted(references.items()):
            print(f"{slug}  ({len(files)} file(s))")
        return 0

    stale, unreachable = audit(references, casing_resolver=canonical_casing if args.strict_casing else None)

    if unreachable and not stale:
        # Nothing was concluded, so do not report a clean run. Exit 2 keeps a flaky
        # runner distinguishable from a repository that really moved.
        print(f"REPO NAMES: {len(unreachable)} name(s) could not be checked", file=sys.stderr)
        for line in unreachable:
            print(f"  {line}", file=sys.stderr)
        return 2

    if stale:
        print(
            # Counts what was concluded, not what was looked at. `len(references)` as the
            # denominator read as "28 verified clean" in the shape that matters: GitHub
            # degrading mid-run, one stale name and the rest never checked.
            f"REPO NAMES: {len(stale)} stale of {len(references) - len(unreachable)} "
            f"name(s) checked" + (f", {len(unreachable)} not checked" if unreachable else ""),
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
