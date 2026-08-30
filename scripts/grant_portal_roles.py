#!/usr/bin/env python3
"""Grant portal roles and scopes to Cognito users, without guessing.

`enforceRoles` defaults to true, so the role rules are already in force: a user holding
no role can read, preview, download and search, and cannot write. Granting a role is
therefore the first thing to do after deploying, not a migration step before turning
something on.

    1. Run this to grant a role and a scope.
    2. Have those users sign out and sign in again. Groups travel in the ID token, and a
       token issued before the grant does not carry it.

Step 2 is not optional and is the usual reason for "I granted the role and nothing
changed".

Idempotent, so it can be run again after adding people without reasoning about who was
done already. It reports three outcomes per assignment -- granted, already held, refused
-- and refuses rather than creates when a group does not exist in the pool: a group
created here would not be in `defineAuth`, so the next deploy's drift check would find it
and nobody would know why it was there.

Dry run by default. Nothing is written until `--apply`.

Usage:
    # See what would change.
    python3 scripts/grant_portal_roles.py --assign alice@example.com=contributor,internal

    # Do it.
    python3 scripts/grant_portal_roles.py --apply \\
        --assign alice@example.com=contributor,internal \\
        --assign partner@example.net=viewer,external

    # Or from a file, one "user=groups" per line, `#` comments allowed.
    python3 scripts/grant_portal_roles.py --apply --from-file roles.txt

    # What does the pool think today?
    python3 scripts/grant_portal_roles.py --list
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, NamedTuple

REPO = Path(__file__).resolve().parent.parent
PORTAL = REPO / "solutions" / "amplify-portal"
GROUPS_TS = PORTAL / "amplify" / "portal-groups.ts"
OUTPUTS = PORTAL / "amplify_outputs.json"


class Assignment(NamedTuple):
    """One user and the groups they should hold."""

    user: str
    groups: tuple[str, ...]


class Action(NamedTuple):
    """What the run decided about one user and one group."""

    user: str
    group: str
    outcome: str
    reason: str


GRANT = "grant"
ALREADY = "already"
REFUSED = "refused"


def declared_groups() -> tuple[list[str], list[str]]:
    """The roles and scopes the portal declares, read from `portal-groups.ts`.

    Read from source rather than listed here, so this script cannot drift into offering
    a group the deployment does not create.

    Returns:
        Roles and scopes, in declaration order.

    Raises:
        SystemExit: When the declaration cannot be read, since every later check
            depends on it and guessing would produce confident wrong advice.
    """
    if not GROUPS_TS.exists():
        sys.exit(f"cannot read group declarations: {GROUPS_TS} is missing")
    source = GROUPS_TS.read_text(encoding="utf-8")
    values = dict(re.findall(r'export const ([A-Z][A-Z0-9_]*) = "([^"]+)"', source))

    def members(name: str) -> list[str]:
        block = re.search(rf"export const {name} = \[([^\]]*)\]", source)
        if not block:
            return []
        return [values[m] for m in re.findall(r"\b([A-Z][A-Z0-9_]*)\b", block.group(1)) if m in values]

    roles, scopes = members("PORTAL_ROLES"), members("PORTAL_SCOPES")
    if not roles or not scopes:
        sys.exit(f"{GROUPS_TS} declares no roles or no scopes; refusing to guess")
    return roles, scopes


def parse_assignment(text: str) -> Assignment:
    """Parse `user=group[,group...]`.

    Args:
        text: One assignment.

    Returns:
        The parsed assignment.

    Raises:
        argparse.ArgumentTypeError: When the shape is wrong. Raised rather than skipped,
            because a silently dropped line reads as a user who was granted nothing.
    """
    user, separator, group_list = text.partition("=")
    if not separator or not user.strip() or not group_list.strip():
        raise argparse.ArgumentTypeError(f"expected user=group[,group...], got {text!r}")
    groups = tuple(g.strip() for g in group_list.split(",") if g.strip())
    if not groups:
        raise argparse.ArgumentTypeError(f"no groups in {text!r}")
    return Assignment(user.strip(), groups)


def read_assignment_file(path: Path) -> list[Assignment]:
    """Parse a file of `user=groups` lines.

    Args:
        path: The file to read.

    Returns:
        One assignment per non-blank, non-comment line.
    """
    assignments = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        try:
            assignments.append(parse_assignment(line))
        except argparse.ArgumentTypeError as error:
            sys.exit(f"{path}:{number}: {error}")
    return assignments


def plan(
    assignments: list[Assignment],
    *,
    existing_groups: set[str],
    current_membership: dict[str, set[str]],
    roles: list[str],
    scopes: list[str],
) -> list[Action]:
    """Decide what to do, without doing it.

    Separated from the API calls so the decisions can be tested against a pool that does
    not exist. Every branch here is a decision somebody has to be able to audit before it
    is applied to real accounts.

    Args:
        assignments: What was asked for.
        existing_groups: Groups the pool actually has.
        current_membership: User to the groups they already hold.
        roles: Declared role names.
        scopes: Declared scope names.

    Returns:
        One action per user and group, in the order given.
    """
    known = set(roles) | set(scopes)
    actions: list[Action] = []
    for user, groups in assignments:
        held = current_membership.get(user, set())
        named_roles = [g for g in groups if g in roles]
        named_scopes = [g for g in groups if g in scopes]

        for group in groups:
            if group not in known:
                actions.append(
                    Action(
                        user,
                        group,
                        REFUSED,
                        f"not a portal group. Roles: {', '.join(roles)}. Scopes: {', '.join(scopes)}",
                    )
                )
            elif group not in existing_groups:
                actions.append(
                    Action(
                        user,
                        group,
                        REFUSED,
                        "declared in portal-groups.ts but not present in the pool. Deploy "
                        "first; creating it here would leave a group defineAuth does not own",
                    )
                )
            elif group in held:
                actions.append(Action(user, group, ALREADY, "already held"))
            else:
                actions.append(Action(user, group, GRANT, "to grant"))

        # Warned about rather than corrected. Which role somebody should have is not a
        # decision this script can make, and a default would be wrong quietly.
        if len(named_roles) > 1:
            actions.append(
                Action(
                    user,
                    ",".join(named_roles),
                    REFUSED,
                    "more than one role. Capabilities are the union, so this grants the "
                    "most permissive one; name a single role instead",
                )
            )
        if len(named_scopes) > 1:
            actions.append(
                Action(
                    user,
                    ",".join(named_scopes),
                    REFUSED,
                    "both scopes. `internal` does not cancel `external`: holding "
                    "`external` confines the caller regardless",
                )
            )
        if not named_scopes and not held & set(scopes):
            actions.append(
                Action(
                    user,
                    "-",
                    REFUSED,
                    "no scope. Without one the caller is treated as internal, which is "
                    "the compatible default and not what an outside member should get",
                )
            )
    return actions


def user_pool_id(explicit: str | None) -> str:
    """The user pool to act on.

    Args:
        explicit: The value of `--user-pool-id`, if given.

    Returns:
        The pool id.

    Raises:
        SystemExit: When it is neither given nor discoverable. Not defaulted, because
            the wrong pool means granting real permissions in the wrong account.
    """
    if explicit:
        return explicit
    if OUTPUTS.exists():
        outputs = json.loads(OUTPUTS.read_text(encoding="utf-8"))
        found = outputs.get("auth", {}).get("user_pool_id")
        if found:
            return found
    sys.exit(
        "no user pool id. Pass --user-pool-id, or run from a workspace where "
        f"{OUTPUTS.relative_to(REPO)} exists (it is written by `npx ampx sandbox`)."
    )


def fetch_state(client: Any, pool: str, users: list[str]) -> tuple[set[str], dict[str, set[str]]]:
    """What the pool has now.

    Args:
        client: A `cognito-idp` client.
        pool: The user pool id.
        users: Users whose membership to read.

    Returns:
        Existing group names, and each user's current groups. A user the pool does not
        have is absent from the mapping rather than empty, so the caller can tell "no
        groups" from "no such user".
    """
    groups = set()
    paginator = client.get_paginator("list_groups")
    for page in paginator.paginate(UserPoolId=pool):
        groups.update(group["GroupName"] for group in page.get("Groups", []))

    membership: dict[str, set[str]] = {}
    for user in users:
        try:
            response = client.admin_list_groups_for_user(UserPoolId=pool, Username=user)
        except client.exceptions.UserNotFoundException:
            continue
        membership[user] = {group["GroupName"] for group in response.get("Groups", [])}
    return groups, membership


def main(argv: list[str] | None = None) -> int:
    """Plan, print, and optionally apply group grants.

    Args:
        argv: Command line arguments, for tests.

    Returns:
        0 when nothing was refused, 1 otherwise.
    """
    roles, scopes = declared_groups()
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--user-pool-id")
    parser.add_argument(
        "--assign",
        action="append",
        default=[],
        type=parse_assignment,
        metavar="USER=GROUPS",
        help=f"roles: {', '.join(roles)}; scopes: {', '.join(scopes)}",
    )
    parser.add_argument("--from-file", type=Path)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the grants. Without this, nothing is changed.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="print current membership for the named users and exit",
    )
    args = parser.parse_args(argv)

    assignments: list[Assignment] = list(args.assign)
    if args.from_file:
        assignments += read_assignment_file(args.from_file)
    if not assignments:
        parser.error("nothing to do: pass --assign or --from-file")

    import boto3  # Imported late so --help works without credentials or the SDK.

    pool = user_pool_id(args.user_pool_id)
    client = boto3.client("cognito-idp")
    existing, membership = fetch_state(client, pool, [a.user for a in assignments])

    if args.list:
        for assignment in assignments:
            held = membership.get(assignment.user)
            state = "no such user" if held is None else ", ".join(sorted(held)) or "no groups"
            print(f"{assignment.user}: {state}")
        return 0

    actions = plan(
        assignments,
        existing_groups=existing,
        current_membership=membership,
        roles=roles,
        scopes=scopes,
    )

    for action in actions:
        if action.outcome == GRANT:
            print(f"  grant   {action.user} -> {action.group}")
        elif action.outcome == ALREADY:
            print(f"  ok      {action.user} -> {action.group} ({action.reason})")
        else:
            print(f"  REFUSE  {action.user} -> {action.group}: {action.reason}")

    refused = [a for a in actions if a.outcome == REFUSED]
    to_grant = [a for a in actions if a.outcome == GRANT]

    if refused:
        print(f"\n{len(refused)} refused. Nothing was written.")
        return 1

    if not args.apply:
        print(f"\n{len(to_grant)} to grant. Re-run with --apply to write them.")
        return 0

    for action in to_grant:
        client.admin_add_user_to_group(UserPoolId=pool, Username=action.user, GroupName=action.group)
    if not to_grant:
        # Nothing changed, so nobody needs to re-authenticate. Saying otherwise on an
        # idempotent re-run sends people to sign out for no reason, and teaches them to
        # skip the line -- which is the line that matters on the run where something did
        # change.
        print("\nNothing to grant; every assignment was already held.")
        return 0

    print(
        f"\n{len(to_grant)} granted. Those users must sign out and sign in again before "
        "the grant takes effect: groups travel in the ID token, so a session opened "
        "before the grant does not carry it."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
