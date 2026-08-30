#!/usr/bin/env python3
"""Turn a calendar obligation into a gate that fails when it comes due.

## The failure being closed

Some obligations in this repository are not triggered by a code change. They are
triggered by a date, and the only thing carrying them is a paragraph in a document.

The one that prompted this: a SnapLock audit log volume was created with a 6-month
minimum retention. Unexpired WORM files block deletion of the volume, its SVM and
the **file system** it lives on, and AWS confirmed there is no route to early
deletion. AWS also confirmed a support case cannot be held open for half a year,
so the billing follow-up has to be opened again at expiry, attaching the earlier
case ID. All of that was written down in
`docs/ja/snaplock-audit-log-console-guardrails.md` -- and a paragraph does not
fire on 2027-02-06. Nothing in the repository would have said anything on that
date, while the resource kept billing and kept the file system undeletable.

This is the same shape as the context-budget check: prose asking a future reader
to remember does not survive contact with a deadline. A failing check does.

## Why it fails rather than warns

A warning about an approaching deadline is the same kind of object as the
paragraph it replaces -- something that scrolls past. `lead_days` exists so the
failure lands with enough time to act, not so it can be acknowledged and ignored.
Clearing it means doing the thing and removing the entry, which is also what
records that it was done.

## Why the case ID is not in the ledger

This repository is public and its git history is permanent. The ledger carries
what the action is and when it is due; the case number, account ID and file system
ID live in the file named by `private_ref`, which has to be gitignored. That is
checked here, because a `private_ref` pointing at a tracked path would invite the
leak it exists to prevent.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "docs/agent/dated-obligations.json"
REQUIRED_FIELDS = ("id", "due", "lead_days", "what", "why", "where", "private_ref")


def _rel(path: Path) -> str:
    """Repository-relative form of a path, or the path itself if it lies outside.

    The fallback is what keeps a failure message from raising instead of printing:
    `relative_to` throws for any path outside the repository, and the tests point
    `LEDGER` at a temporary directory precisely to exercise the failure paths.

    Args:
        path: Path to render.

    Returns:
        A string suitable for a message.
    """
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _load() -> list[dict]:
    """Read the ledger, failing loudly rather than reporting a clean tree.

    Returns:
        The list of obligation entries.

    Raises:
        SystemExit: if the ledger is missing, unparseable or empty.
    """
    if not LEDGER.is_file():
        raise SystemExit(
            f"FAIL: {_rel(LEDGER)} is missing. A ledger that cannot be read "
            "reports no obligations, which is indistinguishable from having none."
        )
    try:
        data = json.loads(LEDGER.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"FAIL: {_rel(LEDGER)} is not valid JSON: {exc}") from exc
    obligations = data.get("obligations")
    if not isinstance(obligations, list) or not obligations:
        raise SystemExit(
            f"FAIL: {_rel(LEDGER)} declares no obligations. If the last one was "
            "discharged, delete this check and its wiring rather than leaving an empty ledger "
            "that passes forever."
        )
    return obligations


def _gitignored(rel_path: str) -> bool:
    """Whether git would ignore the given repository-relative path.

    Args:
        rel_path: Path relative to the repository root.

    Returns:
        True when the path is ignored, False when it is tracked or untracked-but-visible.
    """
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "check-ignore", "-q", rel_path],  # noqa: S607 - git resolved from PATH by design
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def check(today: date | None = None) -> list[str]:
    """Validate the ledger and report obligations that have come due.

    Args:
        today: Date to evaluate against. Defaults to the current date.

    Returns:
        Human-readable problems. Empty means nothing is due and the ledger is sound.
    """
    today = today or date.today()
    problems: list[str] = []
    seen: set[str] = set()

    for index, entry in enumerate(_load()):
        label = entry.get("id") or f"entry #{index}"

        missing = [field for field in REQUIRED_FIELDS if not entry.get(field) and entry.get(field) != 0]
        if missing:
            problems.append(f"{label}: missing required field(s): {', '.join(missing)}")
            continue

        if entry["id"] in seen:
            problems.append(f"{label}: duplicate id; two entries would clear each other's failure")
        seen.add(entry["id"])

        try:
            due = datetime.strptime(entry["due"], "%Y-%m-%d").date()
        except ValueError:
            problems.append(f"{label}: `due` is {entry['due']!r}, which is not YYYY-MM-DD")
            continue

        if not isinstance(entry["lead_days"], int) or entry["lead_days"] < 0:
            problems.append(f"{label}: `lead_days` must be a non-negative integer")
            continue

        target = ROOT / entry["where"]
        if not target.is_file():
            problems.append(
                f"{label}: `where` points at {entry['where']}, which does not exist. "
                "A pointer that resolves to nothing leaves the reason for the deadline unreadable."
            )

        if not _gitignored(entry["private_ref"]):
            problems.append(
                f"{label}: `private_ref` is {entry['private_ref']}, which git does not ignore. "
                "It has to be gitignored: it is where the case number and resource IDs go, and "
                "this repository is public."
            )

        fires_on = due - timedelta(days=entry["lead_days"])
        if today >= fires_on:
            overdue = "OVERDUE" if today >= due else f"due in {(due - today).days} day(s)"
            problems.append(
                f"{label}: {overdue} (due {entry['due']}, lead {entry['lead_days']}d).\n"
                f"    Action: {entry['what']}\n"
                f"    Why:    {entry['why']}\n"
                f"    Context: {entry['where']}  |  private note: {entry['private_ref']}\n"
                f"    Clear this by doing it and removing the entry from "
                f"{_rel(LEDGER)}."
            )

    return problems


def main() -> int:
    """Entry point.

    Returns:
        0 when nothing is due and the ledger is sound, 1 otherwise.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", metavar="YYYY-MM-DD", help="evaluate against this date instead of today")
    parser.add_argument("--list", action="store_true", help="print every obligation and exit 0")
    args = parser.parse_args()

    if args.list:
        for entry in _load():
            print(f"{entry.get('due', '????-??-??')}  {entry.get('id', '(no id)')}  {entry.get('what', '')}")
        return 0

    as_of = datetime.strptime(args.as_of, "%Y-%m-%d").date() if args.as_of else None
    problems = check(as_of)
    if problems:
        print("FAIL: dated obligations need attention\n")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    entries = _load()
    nearest = min(entries, key=lambda entry: entry["due"])
    print(f"dated obligations OK: {len(entries)} tracked, nearest {nearest['due']} ({nearest['id']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
