"""Fail on a GitHub repository name that is not the name the repository has.

## Why a link checker cannot find this

A rename is normal. What has no symptom is that GitHub keeps serving the old name through a
redirect: the link returns 200, a link checker reports it reachable, and two documents can
spell the same repository differently while both look fine. The Adoption Playbook hit this
with seven renamed repositories whose links all reported reachable, and its
`tools/check_cross_repo.py` grew `check_repo_names()` for it.

Reachability is the wrong question. This asks a different one: **is the name we wrote the
name the repository has?**

## Why this asks the API rather than following the redirect

The Playbook's implementation, and the first version of this one, compared the landing URL of
a request to `github.com/<owner>/<repo>`. Two things made that the wrong mechanism here, both
found by running it rather than by reading it.

**It cannot see capitalisation.** Measured 2026-09-07: GitHub serves
`Yoshiki0705/vmware-migration-ec2-ontap` at the URL requested and reports that URL back,
while `Yoshiki0705/fsxn-cyber-resilience-patterns` redirects to
`FSx-for-ONTAP-Cyber-Resilience-Patterns`. A rename is visible in the landing URL; a rename
that only changed case is not. That gap was not academic: of the five stale names this check
was written to find, `vmware-migration-ec2-ontap` sits inside it, and the redirect method
certified it as canonical.

**And the HTML endpoint 504s.** On a GitHub-hosted runner, `NetApp/FSx-ONTAP-samples-scripts`
and `NetApp/fsxn-monitoring-auto-resizing` returned 504 on all three attempts, so the weekly
job failed with "could not be checked" while nothing was wrong with either name. Both answer
the API immediately.

`GET /repos/{owner}/{repo}` returns `full_name`, which is the canonical `owner/repo` including
its capitalisation, and it follows renames. One request per name settles rename, casing and
existence together:

| written | `full_name` | verdict |
|---|---|---|
| `Yoshiki0705/fsxn-cyber-resilience-patterns` | `Yoshiki0705/FSx-for-ONTAP-Cyber-Resilience-Patterns` | renamed |
| `Yoshiki0705/vmware-migration-ec2-ontap` | `Yoshiki0705/VMware-Migration-EC2-ONTAP` | miscapitalised |
| `Yoshiki0705/Permission-aware-RAG-FSxN-CDK-github` | 404 | does not resolve |  # allow:naming - the retired repository name, quoted

`FSx-for-ONTAP-Observability-integrations` is the shape that makes casing worth checking: a
lowercase `i` where its siblings use `-Integrations`, correct as written, and impossible to
confirm without asking.

The cost is a rate limit. Unauthenticated is 60/hour, which covers the 29 names here but not
much more; `GITHUB_TOKEN` lifts it to 5,000 and the weekly workflow passes one. When the limit
is the reason a name could not be checked, the message says so rather than leaving someone to
infer it from a 403.

## One deliberate difference from the Playbook's version

**Fenced code blocks are scanned here, not skipped.** The Playbook blanks them out, because
there a citation inside a fence is an example rather than a claim. In this repository the
opposite is true: the majority of repository references sit inside

    ```bash
    git clone https://github.com/<owner>/<repo>.git
    ```

in a demo guide, and that is a URL a reader pastes into a terminal. Skipping fences here would
have skipped 91 files carrying a clone URL that 404s -- the single most user-facing instance of
exactly what this check is for.

## What this still cannot see

A URL wrapped across two source lines. The first half yields no match at all, so the reference
is skipped silently rather than reported. `WRAPPED` handles the narrower case of a name left
with a trailing hyphen.

## What a 404 means, and what it does not

A 404 has more than one cause: the repository was deleted, or renamed with the redirect
expired, **or it is private and this request lacks access to it.** The check cannot tell those
apart and does not guess. It reports that the name does not resolve, which is what a reader of
a public repository would experience, and leaves the interpretation to a human. It is kept
separate from "could not be checked" for that reason -- one is an answer, the other is not.

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

Set GITHUB_TOKEN to lift the 60/hour unauthenticated rate limit.

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
            if exc.code in (403, 429):
                # The one unreachable reason a human can act on. Left unnamed it reads as an
                # outage, and the fix -- set GITHUB_TOKEN -- is not guessable from "HTTP 403".
                remaining = exc.headers.get("x-ratelimit-remaining") if exc.headers else None
                if remaining == "0":
                    last = f"HTTP {exc.code}: API rate limit exhausted" + (
                        "" if os.environ.get("GITHUB_TOKEN") else ". Set GITHUB_TOKEN"
                    )
                return None, exc.code, last
            if exc.code not in RETRY_ON:
                return None, exc.code, last
        except (urllib.error.URLError, TimeoutError) as exc:
            last = str(exc)
        if attempt < ATTEMPTS:
            time.sleep(BACKOFF_SECONDS * attempt)
    return None, None, f"{last} after {ATTEMPTS} attempts"


REPO_REF = re.compile(r"https://github\.com/(?P<owner>[A-Za-z0-9][A-Za-z0-9._-]*)/(?P<repo>[A-Za-z0-9][A-Za-z0-9._-]*)")


def fetch_json(
    request: urllib.request.Request,
) -> tuple[object | None, int | None, str | None]:
    """`fetch()` for an endpoint whose answer is in the body rather than the landing URL.

    Args:
        request: A prepared request whose scheme the caller has already asserted.

    Returns:
        `(body, status, error)`. A 404 returns `(None, 404, None)`, because it is an answer.
    """
    last = "no attempt made"
    for attempt in range(1, ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(  # nosec B310 - scheme asserted by the caller  # noqa: S310
                request, timeout=30
            ) as response:
                return json.load(response), response.status, None
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None, 404, None
            _body, _status, error = None, exc.code, f"HTTP {exc.code}"
            if exc.code in (403, 429):
                remaining = exc.headers.get("x-ratelimit-remaining") if exc.headers else None
                if remaining == "0":
                    error += ": API rate limit exhausted" + (
                        "" if os.environ.get("GITHUB_TOKEN") else ". Set GITHUB_TOKEN"
                    )
                return None, exc.code, error
            if exc.code not in RETRY_ON:
                return None, exc.code, error
            last = error
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            last = str(exc)
        if attempt < ATTEMPTS:
            time.sleep(BACKOFF_SECONDS * attempt)
    return None, None, f"{last} after {ATTEMPTS} attempts"


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
    """Ask the API what the canonical name of `slug` is.

    Args:
        slug: An `owner/repo` reference as written in the prose.

    Returns:
        A pair of `(outcome, detail)`. Outcome is `ok`, `renamed`, `missing` or
        `unreachable`. `renamed` carries the canonical `owner/repo` -- which covers a change
        of capitalisation, since `full_name` is authoritative for that too. `missing` and
        `unreachable` carry the reason. `ok` carries `None`.
    """
    url = f"https://api.github.com/repos/{slug}"
    # `slug` comes out of a regex anchored on `https://github.com/`, so neither the scheme nor
    # the host can be steered from prose. Asserted anyway, because `urlopen` also honours
    # `file:` and the guarantee is one refactor away from being someone else's assumption.
    if not url.startswith("https://api.github.com/repos/"):
        raise ValueError(f"refusing a non-GitHub https URL: {url}")

    headers = {"User-Agent": "repo-name-check", "Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body, status, error = fetch_json(urllib.request.Request(url, headers=headers))
    if status == 404:
        return "missing", "404 (deleted, redirect expired, or not accessible)"
    if error is not None:
        return "unreachable", error
    if not isinstance(body, dict) or not body.get("full_name"):
        return "unreachable", "the API response carried no full_name"

    canonical = body["full_name"]
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
        A pair of `(stale, unreachable)` message lists. `stale` holds findings about names;
        `unreachable` holds names about which nothing was concluded.
    """
    stale: list[str] = []
    unreachable: list[str] = []

    for slug, files in sorted(references.items()):
        outcome, detail = resolver(slug)
        listed = ", ".join(files[:4]) + (f" and {len(files) - 4} more" if len(files) > 4 else "")
        if outcome == "renamed":
            # Split the message, because the two shapes need different reactions: a rename
            # still resolves for a reader, a change of case is invisible to every other check.
            miscased = (detail or "").lower() == slug.lower()
            what = (
                "is capitalised {0} upstream. GitHub serves the casing requested, so no "
                "redirect and no link checker makes this visible."
                if miscased
                else "is now {0}. The old name still resolves through a redirect, so nothing else reports it."
            ).format(detail)
            stale.append(f"{slug} {what} Referenced by: {listed}")
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
