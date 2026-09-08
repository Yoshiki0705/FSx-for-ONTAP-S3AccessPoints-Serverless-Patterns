#!/usr/bin/env python3
"""Verify the claim-bearing strings a sibling repository has registered against this one.

## What this closes

`FSx-for-ONTAP-Adoption-Playbook` publishes `docs/agent/cross-repo-probe-contract.txt`:
one line per string it depends on inside another repository, generated from its own
citation index. **Nine of those lines name this repository.** They were all present
when this was written, and nothing here looked at them, so the first reword of one
would have surfaced as a failure in the Playbook's CI — after the commit, in someone
else's repository, with its guidance already published against a sentence that had
moved.

This moves the discovery to the commit that causes it. That is the whole point: the
owner of a string is the only party who can decide whether a reword is a reword or a
retraction, and the owner is here.

## What a probe is, and what it is not

**Each probe is an opaque byte substring, tested with `in`. Nothing is normalised.**
The Playbook's index escapes markdown, so its rendered form and its source form differ
by backslashes; normalising either side would turn a real break into a pass or the
reverse. The contract carries the literal bytes to search for.

Two roles, and they ask different questions:

- `retraction` — the string must be present. Its absence means the claim was withdrawn
  or reworded and the citation over there has lost its evidence. **Fails.**
- `reread` — the string pins a minimum or maximum over a measured set, so adding a
  measurement rewrites it while the finding still stands. A gate cannot tell an addition
  from a withdrawal. **Warns.**

**A probe cannot tell you the finding is still true.** It tells you the sentence is
still there. A claim that has been superseded but kept as history — "as of ONTAP
9.18.1P3D1 the accepted protocols were …" — keeps every probe green. That case is only
reachable by telling the citing side, which is why the registration is a floor and not
a substitute for saying so.

## Modes

Default reads a sibling checkout beside this repository and **skips** when there is
none, which is every pull-request runner. `--fetch` reads the published contract over
the network, for the scheduled job. A skip is not a pass and says so.
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

# Both names: the sibling was renamed from `fsxn-adoption-playbook`, so a clone made
# before the rename carries the old directory name. Holding only the new one meant a
# checkout went unfound and the skip stood in for a pass.
CHECKOUT_NAMES = ("FSx-for-ONTAP-Adoption-Playbook", "fsxn-adoption-playbook")
CONTRACT = Path("docs/agent/cross-repo-probe-contract.txt")
RAW_CONTRACT = (
    "https://raw.githubusercontent.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/main/" + CONTRACT.as_posix()
)

# The names the sibling's first field may use for this repository. This repository was
# also renamed, from `fsxn-s3ap-serverless-patterns`, and the contract is generated
# from the sibling's index rather than from anything here — so which spelling appears
# is their state, not ours. Accepting one would make a stale spelling read as "no rows
# registered".
THIS_REPO_NAMES = (
    "FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns",
    "fsxn-s3ap-serverless-patterns",
)

FAIL_ROLE = "retraction"
WARN_ROLE = "reread"

# The sibling documents its vocabulary as those two and states its own gate rejects a
# third. A value this does not recognise is therefore a format change nobody announced
# or a typo, and both are reasons to stop rather than to skip the row. Guessing which
# is how a probe stops being checked while the output still says everything passed.
#
# The contract IS published today — read from the sibling's `main` on 2026-09-08, 71
# rows, 9 of them naming this repository. So a 404 from `--fetch` means the
# registration this depends on was removed or renamed, not that it has yet to appear,
# and it fails. There is no way to tell those apart from the response, which is why
# this is stated here rather than inferred.
CONTRACT_IS_PUBLISHED = True

# Zero rows for this repository, out of a contract that parsed, is not "nothing to
# check" — it means the repository name or the field order moved. Nine were registered
# when this was written. A scan that finds none has to say so.
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


def read_contract(fetch: bool) -> tuple[str | None, str]:
    """Locate the contract.

    Args:
        fetch: Read over the network instead of from a sibling checkout.

    Returns:
        `(body, source)`. `body` is None when the contract could not be read, and
        `source` says why or from where.
    """
    if fetch:
        # The URL is a constant in this file with no interpolation, so nothing external can
        # steer it. Asserted anyway, for the reason check_repo_name_redirects.py gives:
        # `urlopen` also honours `file:`, and a later edit that made the host a parameter
        # would turn this into a local-file read while still looking like an HTTP request.
        if not RAW_CONTRACT.startswith("https://"):
            raise ValueError(f"the contract URL must be https: {RAW_CONTRACT!r}")
        try:
            with urllib.request.urlopen(  # nosec B310 - scheme asserted above  # noqa: S310
                RAW_CONTRACT, timeout=20
            ) as response:
                return response.read().decode("utf-8"), RAW_CONTRACT
        except urllib.error.HTTPError as error:
            return None, f"HTTP {error.code} from {RAW_CONTRACT}"
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            return None, f"could not reach {RAW_CONTRACT}: {error}"
    explicit = os.environ.get("SIBLING_PLAYBOOK")
    candidates = [Path(explicit).expanduser()] if explicit else [ROOT.parent / name for name in CHECKOUT_NAMES]
    for candidate in candidates:
        if (candidate / CONTRACT).is_file():
            return (candidate / CONTRACT).read_text(encoding="utf-8"), str(candidate / CONTRACT)
    return None, "no sibling checkout found beside this repository (set SIBLING_PLAYBOOK to override)"


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    Args:
        argv: Command-line arguments, defaulting to `sys.argv[1:]`.

    Returns:
        0 clean, 1 findings, 2 undetermined.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", help="read the published contract over the network")
    args = parser.parse_args(argv)

    body, source = read_contract(args.fetch)
    if body is None:
        if args.fetch:
            verdict = (
                "the contract was published and is now unreachable, so the registration this depends on may be gone"
                if CONTRACT_IS_PUBLISHED
                else "the contract is not published yet"
            )
            print(f"incoming-probes: UNDETERMINED — {source}\n  {verdict}", file=sys.stderr)
            return EXIT_UNDETERMINED if CONTRACT_IS_PUBLISHED else EXIT_CLEAN
        print(f"incoming-probes: SKIPPED — {source}")
        print("  A skip is not a pass. The scheduled job runs this with --fetch.")
        return EXIT_CLEAN

    probes, malformed = parse_contract(body)
    if malformed:
        print(f"incoming-probes: the contract at {source} could not be read:", file=sys.stderr)
        for line in malformed:
            print(f"  {line}", file=sys.stderr)
        return EXIT_FINDINGS
    if not probes and EXPECT_AT_LEAST_ONE_ROW:
        print(
            f"incoming-probes: the contract at {source} parsed but registers nothing against "
            f"this repository.\n  Nine rows were registered when this check was written, so either "
            f"the repository name or the field order moved.\n  Names accepted in the first field: "
            f"{', '.join(THIS_REPO_NAMES)}",
            file=sys.stderr,
        )
        return EXIT_FINDINGS

    failures, warnings = audit(probes)
    for line in warnings:
        print(f"incoming-probes: WARN {line}")
    if failures:
        print(f"incoming-probes: {len(failures)} finding(s) against {source}", file=sys.stderr)
        for line in failures:
            print(f"  {line}", file=sys.stderr)
        print(
            "\n  A registered string is one another repository publishes guidance against. If the "
            "change was a reword, restore the string or tell the sibling to regenerate its index. "
            "If the claim was withdrawn or superseded, tell them — their gate cannot tell those "
            "apart, and a superseded claim kept as history keeps every probe green.",
            file=sys.stderr,
        )
        return EXIT_FINDINGS
    print(f"incoming-probes: {len(probes)} registered string(s) still present ({source})")
    return EXIT_CLEAN


if __name__ == "__main__":
    sys.exit(main())
