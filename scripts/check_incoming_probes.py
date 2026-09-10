#!/usr/bin/env python3
"""Verify the claim-bearing strings sibling repositories have registered against this one.

## What this closes

Two repositories cite this one and each publishes `docs/agent/cross-repo-probe-contract.txt`:
one line per string it depends on inside another repository.
`FSx-for-ONTAP-Adoption-Playbook` generates its file from its own citation index;
`S3-Burst-on-ONTAP-Files` maintains its by hand, because a probe is a *chosen*
claim-bearing substring rather than every link. Both use the same format, which is why one
reader serves both.

Nothing here read either of them. The first reword of a registered string would have
surfaced as a failure in someone else's CI — after the commit, in another repository, with
its guidance already published against a sentence that had moved.

This moves the discovery to the commit that causes it. The owner of a string is the only
party who can decide whether a reword is a reword or a retraction, and the owner is here.

**Every source is read on every run.** Handling one and stopping was the shape of the gap
this reopened once already: the reader was written for a single URL, then a second
repository published a contract registering eight rows and nothing looked at them.

## What a probe is, and what it is not

**Each probe is an opaque byte substring, tested with `in`. Nothing is normalised.** The
Playbook's index escapes markdown, so its rendered form and its source form differ by
backslashes; normalising either side would turn a real break into a pass or the reverse.
The contract carries the literal bytes to search for.

Two roles, and they ask different questions:

- `retraction` — the string must be present. Its absence means the claim was withdrawn or
  reworded and the citation over there has lost its evidence. **Fails.**
- `reread` — the string pins a minimum or maximum over a measured set, so adding a
  measurement rewrites it while the finding still stands. A gate cannot tell an addition
  from a withdrawal. **Warns.**

**A probe cannot tell you the finding is still true.** It tells you the sentence is still
there. A claim that has been superseded but kept as history — "as of ONTAP 9.18.1P3D1 the
accepted protocols were …" — keeps every probe green. It also passes while **any single
occurrence** survives, so a string that also appears in a summary table says nothing about
the sentence that carries the claim. Both are reasons the registration is a floor and not a
substitute for telling the citing side.

One consequence worth expecting rather than debugging: the mechanism probes on the FPolicy
errata fire when a later ONTAP release accepts `s3` as an event protocol. That is good news
arriving as a red gate on both sides, and a defect in neither.

## Modes

Default reads whichever sibling checkouts sit beside this repository and **skips** the ones
that do not, which on a pull-request runner is all of them. `--fetch` reads every published
contract over the network, for the scheduled job. A skip is not a pass and says so.

"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent

CONTRACT = Path("docs/agent/cross-repo-probe-contract.txt")


class Source(NamedTuple):
    """A repository that publishes a contract naming this one."""

    repo: str
    checkout_names: tuple[str, ...]
    raw_url: str


def _raw(repo: str) -> str:
    """Build the raw URL for a repository's contract.

    Args:
        repo: Repository name under the same owner.

    Returns:
        The `raw.githubusercontent.com` URL on `main`.
    """
    return f"https://raw.githubusercontent.com/Yoshiki0705/{repo}/main/{CONTRACT.as_posix()}"


# Two repositories cite this one and publish what they depend on. Both were added after
# being read, not on being announced: the Playbook's on 2026-09-08 and
# S3-Burst-on-ONTAP-Files' on 2026-09-09, the latter after it was pointed at #401 and
# published one in the format the Playbook uses -- which is what makes a single reader
# serve both.
#
# Reading only the first was the same gap #401 closed, reopened by a second citer: eight
# rows were registered against this repository and nothing here looked at them.
#
# Each repository carries both directory names it has had. The Playbook was renamed from
# `fsxn-adoption-playbook`, so a clone made before that carries the old name, and holding
# only the new one meant a checkout went unfound while the skip stood in for a pass.
SOURCES = (
    Source(
        "FSx-for-ONTAP-Adoption-Playbook",
        ("FSx-for-ONTAP-Adoption-Playbook", "fsxn-adoption-playbook"),
        _raw("FSx-for-ONTAP-Adoption-Playbook"),
    ),
    Source(
        "S3-Burst-on-ONTAP-Files",
        ("S3-Burst-on-ONTAP-Files",),
        _raw("S3-Burst-on-ONTAP-Files"),
    ),
)

# The names a contract's first field may use for this repository. This repository was
# renamed from `fsxn-s3ap-serverless-patterns`, and each contract is maintained on the
# citing side rather than from anything here -- so which spelling appears is their state,
# not ours. Accepting one would make a stale spelling read as "no rows registered".
THIS_REPO_NAMES = (
    "FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns",
    "fsxn-s3ap-serverless-patterns",
)

FAIL_ROLE = "retraction"
WARN_ROLE = "reread"

# Both contracts document their vocabulary as those two words and state their own gates
# reject a third. A value this does not recognise is therefore a format change nobody
# announced or a typo, and both are reasons to stop rather than to skip the row. Guessing
# which is how a probe stops being checked while the output still says everything passed.
#
# Both contracts ARE published -- each read over the network before being added here. So a
# 404 from `--fetch` means the registration this depends on was removed or renamed, not
# that it has yet to appear, and it fails. There is no way to tell those apart from the
# response, which is why this is stated rather than inferred.
CONTRACT_IS_PUBLISHED = True

# Zero rows for this repository, out of a contract that parsed, is not "nothing to check"
# -- it means the repository name or the field order moved. Deliberately not a count: the
# Playbook's rows went from 9 to 11 within a day, so a number here would be wrong by the
# next read and would be corrected by lowering it rather than by looking.
EXPECT_AT_LEAST_ONE_ROW = True

EXIT_CLEAN = 0
EXIT_FINDINGS = 1
EXIT_UNDETERMINED = 2


class Probe(NamedTuple):
    """One registered string."""

    repo: str
    path: str
    role: str
    text: str


def parse_contract(body: str) -> tuple[list[Probe], list[str]]:
    """Read the contract into probes for this repository.

    Four TAB-separated fields: repo, path, role, string. The string is taken whole and
    last, so a probe may contain any character except a tab. `#` starts a comment only
    at the start of a line — a probe string can contain one, and testing for it anywhere
    in the line would silently drop those rows.

    Args:
        body: Contents of the contract file.

    Returns:
        `(probes, malformed)` where `probes` are the rows naming this repository and
        `malformed` describes rows that could not be read at all.
    """
    probes: list[Probe] = []
    malformed: list[str] = []
    for number, line in enumerate(body.splitlines(), start=1):
        if not line.strip() or line.startswith("#"):
            continue
        fields = line.split("\t", 3)
        if len(fields) != 4:
            malformed.append(f"line {number}: expected 4 tab-separated fields, found {len(fields)}")
            continue
        repo, path, role, text = fields
        if repo not in THIS_REPO_NAMES:
            continue
        probes.append(Probe(repo, path, role, text))
    return probes, malformed


def audit(probes: list[Probe], root: Path = ROOT) -> tuple[list[str], list[str]]:
    """Test each probe against the file it names.

    Args:
        probes: Rows naming this repository.
        root: Repository root, overridable for tests.

    Returns:
        `(failures, warnings)` as human-readable lines.
    """
    failures: list[str] = []
    warnings: list[str] = []
    for probe in probes:
        target = root / probe.path
        if probe.role not in (FAIL_ROLE, WARN_ROLE):
            failures.append(
                f"{probe.path}: role {probe.role!r} is not one the contract defines "
                f"({FAIL_ROLE} / {WARN_ROLE}) — the format changed or the row is a typo"
            )
            continue
        if not target.is_file():
            failures.append(
                f"{probe.path}: cited file is absent. The sibling registered a probe against it, "
                f"so its citation is already broken"
            )
            continue
        if probe.text in target.read_text(encoding="utf-8"):
            continue
        where = failures if probe.role == FAIL_ROLE else warnings
        where.append(f"{probe.path}: [{probe.role}] string not found — {probe.text!r}")
    return failures, warnings


def read_contract(fetch: bool, source: Source) -> tuple[str | None, str]:
    """Locate one repository's contract.

    Args:
        fetch: Read over the network instead of from a sibling checkout.
        source: The repository to read from.

    Returns:
        `(body, where)`. `body` is None when the contract could not be read, and `where`
        says why or from where.
    """
    if fetch:
        # The URL is built from a constant in this file with no external input, so nothing
        # outside can steer it. Asserted anyway, for the reason check_repo_name_redirects.py
        # gives: `urlopen` also honours `file:`, and a later edit that made the host a
        # parameter would turn this into a local-file read while still looking like HTTP.
        if not source.raw_url.startswith("https://"):
            raise ValueError(f"the contract URL must be https: {source.raw_url!r}")
        try:
            with urllib.request.urlopen(  # nosec B310 - scheme asserted above  # noqa: S310
                source.raw_url, timeout=20
            ) as response:
                return response.read().decode("utf-8"), source.raw_url
        except urllib.error.HTTPError as error:
            return None, f"HTTP {error.code} from {source.raw_url}"
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            return None, f"could not reach {source.raw_url}: {error}"
    # One variable per source, so a machine that keeps one sibling elsewhere can point at
    # it without also having to relocate the other.
    explicit = os.environ.get("SIBLING_" + source.repo.replace("-", "_").upper())
    if not explicit and source.repo.startswith("FSx-for-ONTAP-Adoption"):
        explicit = os.environ.get("SIBLING_PLAYBOOK")  # the name this had before there were two
    candidates = [Path(explicit).expanduser()] if explicit else [ROOT.parent / name for name in source.checkout_names]
    for candidate in candidates:
        if (candidate / CONTRACT).is_file():
            return (candidate / CONTRACT).read_text(encoding="utf-8"), str(candidate / CONTRACT)
    return None, f"no {source.repo} checkout beside this repository"


def check_source(source: Source, fetch: bool) -> tuple[int, list[str]]:
    """Read and audit one repository's contract.

    Args:
        source: The repository to read from.
        fetch: Read over the network instead of from a sibling checkout.

    Returns:
        `(exit_code, lines)` where the lines are already prefixed for printing.
    """
    body, where = read_contract(fetch, source)
    label = source.repo
    if body is None:
        if fetch:
            verdict = (
                "published once and now unreachable, so the registration this depends on may be gone"
                if CONTRACT_IS_PUBLISHED
                else "not published yet"
            )
            return EXIT_UNDETERMINED if CONTRACT_IS_PUBLISHED else EXIT_CLEAN, [
                f"  {label}: UNDETERMINED — {where}",
                f"    {verdict}",
            ]
        return EXIT_CLEAN, [
            f"  {label}: SKIPPED — {where}",
            "    A skip is not a pass. The scheduled job reads every contract with --fetch.",
        ]

    probes, malformed = parse_contract(body)
    if malformed:
        return EXIT_FINDINGS, [f"  {label}: the contract at {where} could not be read:"] + [
            f"    {line}" for line in malformed
        ]
    if not probes and EXPECT_AT_LEAST_ONE_ROW:
        return EXIT_FINDINGS, [
            f"  {label}: the contract at {where} parsed but registers nothing against this repository.",
            "    That is the repository name or the field order having moved, not an empty registration.",
            f"    Names accepted in the first field: {', '.join(THIS_REPO_NAMES)}",
        ]

    failures, warnings = audit(probes)
    lines = [f"    WARN {line}" for line in warnings]
    if failures:
        return EXIT_FINDINGS, [f"  {label}: {len(failures)} finding(s) against {where}"] + [
            f"    {line}" for line in failures
        ] + lines
    return EXIT_CLEAN, [f"  {label}: {len(probes)} registered string(s) still present ({where})"] + lines


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    Args:
        argv: Command-line arguments, defaulting to `sys.argv[1:]`.

    Returns:
        0 clean, 1 findings, 2 undetermined.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", help="read every published contract over the network")
    args = parser.parse_args(argv)

    # Every source is read before anything is returned. Stopping at the first failure would
    # report one citing repository's break and leave the other unexamined, which reads as
    # "one problem" when there may be two.
    codes: list[int] = []
    output: list[str] = []
    for source in SOURCES:
        code, lines = check_source(source, args.fetch)
        codes.append(code)
        output.extend(lines)

    # Findings beat undetermined rather than the numerically larger code winning. A string
    # that is gone is actionable now; a contract that could not be read is a question about
    # the check itself, and reporting the question in place of the answer buries the answer.
    if EXIT_FINDINGS in codes:
        worst = EXIT_FINDINGS
    elif EXIT_UNDETERMINED in codes:
        worst = EXIT_UNDETERMINED
    else:
        worst = EXIT_CLEAN

    stream = sys.stderr if worst != EXIT_CLEAN else sys.stdout
    print(f"incoming-probes: {len(SOURCES)} contract(s)", file=stream)
    for line in output:
        print(line, file=stream)
    if worst == EXIT_FINDINGS:
        print(
            "\n  A registered string is one another repository publishes guidance against. If the "
            "change was a reword, restore the string or tell the citing side to update its contract. "
            "If the claim was withdrawn or superseded, tell them — their gate cannot tell those "
            "apart, and a superseded claim kept as history keeps every probe green.",
            file=sys.stderr,
        )
    return worst


if __name__ == "__main__":
    sys.exit(main())
