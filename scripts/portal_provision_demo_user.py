#!/usr/bin/env python3
"""Create a portal demo account, then hand the group grant to grant_portal_roles.py.

This script owns only what creating an account adds over granting groups to one that
already exists:

* **The pool has to be the right one.** ``amplify_outputs.json`` is overwritten by
  whichever sandbox ran last, and an account created in any other pool produces a
  portal that loads, renders the sign-in form, and rejects the credentials with
  "incorrect username or password" and nothing else. So the sandbox owning the pool is
  resolved and reported, and ``--expected-sandbox`` can make a mismatch fatal.
* **A password the pool will accept, generated rather than chosen.** The policy is
  read from the pool; ``RequireSymbols`` is the one people forget, and the failure
  arrives as ``InvalidPasswordException`` after the user already exists.
* **A statement of what the role unlocks**, before it is granted, because
  ``storage-admin`` reaches operations that cannot be undone.

Everything about *which groups mean what* stays in ``grant_portal_roles.py``: it reads
the names from ``amplify/portal-groups.ts`` so it cannot offer a group the deployment
does not create, it refuses two roles or both scopes, and it is idempotent. Restating
any of that here would mean two places to keep in step, and the copy would be the one
that goes stale.

Usage:
    python3 scripts/portal_provision_demo_user.py --username demo@example.com \\
        --groups storage-admin,internal --expected-sandbox demo

Exit codes: 0 provisioned, 1 refused or failed, 2 could not run.
"""

from __future__ import annotations

import argparse
import json
import re
import secrets
import string
import sys
from pathlib import Path

import grant_portal_roles

REPO = Path(__file__).resolve().parent.parent
PORTAL = REPO / "solutions" / "amplify-portal"
OUTPUTS = PORTAL / "amplify_outputs.json"

# What each role unlocks, read off the deployed schema's auth directives on 2026-09-03
# rather than from the source, so this describes what AppSync enforces. Keyed by the
# names grant_portal_roles reads from portal-groups.ts; a role gaining a name without
# gaining an entry here is caught by the tests rather than granted silently.
ROLE_EFFECT = {
    "viewer": "read, preview, download and search; no writes",
    "contributor": "adds file and folder writes (upload, rename, move, trash)",
    "storage-admin": (
        "everything group-gated: file and folder writes, the audit trail, and the "
        "adminQuery/adminMutation/arpMutation/protectionMutation/runAthenaQuery endpoints"
    ),
    "auditor": "the audit trail, without write access",
}

# Reachable from the browser once a caller holds storage-admin. Each is on the
# repository's irreversible-operations list. The handler-side `acknowledgeIrreversible`
# flag does not gate a person clicking: the frontend sends it as a literal
# (SnaplockManager.tsx, VolumeManager.tsx, SnapshotAdminManager.tsx).
STORAGE_ADMIN_IRREVERSIBLE = (
    "create a SnapLock volume (compliance/enterprise) -- while it holds an unexpired "
    "WORM file the volume, its SVM and the file system cannot be deleted",
    "enable snapshot locking -- cannot be disabled on a compliance volume",
    "lock a snapshot or extend its retention -- extend only, never shorten or release",
)

# Excludes quotes, backslash, backtick, dollar and space. The password is copied
# through a terminal and pasted into a browser, and a shell-hostile character turns a
# working credential into a support question.
SYMBOL_ALPHABET = "!@#%*-_=+:?"


def load_outputs() -> dict:
    """Return parsed amplify_outputs.json.

    Returns:
        The parsed outputs.

    Raises:
        RuntimeError: When the file is absent, since every later step needs the pool it
            names and guessing one would provision into the wrong account.
    """
    if not OUTPUTS.exists():
        raise RuntimeError(
            f"{OUTPUTS} not found. Deploy the backend first (`make sandbox` in solutions/amplify-portal)."
        )
    return json.loads(OUTPUTS.read_text(encoding="utf-8"))


def sandbox_identifier(stack_name: str) -> str:
    """Pull the sandbox identifier out of an Amplify stack name.

    Args:
        stack_name: A CloudFormation stack name.

    Returns:
        The identifier, or a statement that the name is not a sandbox stack. Reported
        rather than guessed, so a non-sandbox deployment does not silently pass an
        `--expected-sandbox` comparison.
    """
    match = re.search(r"-([^-]+)-sandbox-", stack_name or "")
    return match.group(1) if match else "(not a sandbox stack)"


def generate_password(policy: dict) -> str:
    """Return a password satisfying the pool's policy.

    Builds one character per required class and fills the rest from their union, then
    shuffles. Generating at random and re-testing would usually work and would
    occasionally loop; this cannot fail to satisfy the policy.

    Args:
        policy: The pool's `PasswordPolicy`, which may be empty.

    Returns:
        A password of at least 16 characters, longer if the policy demands it.
    """
    length = max(int(policy.get("MinimumLength", 8)), 16)
    classes: list[str] = []
    if policy.get("RequireUppercase", True):
        classes.append(string.ascii_uppercase)
    if policy.get("RequireLowercase", True):
        classes.append(string.ascii_lowercase)
    if policy.get("RequireNumbers", True):
        classes.append(string.digits)
    if policy.get("RequireSymbols", True):
        classes.append(SYMBOL_ALPHABET)
    if not classes:
        classes.append(string.ascii_letters + string.digits)

    union = "".join(classes)
    chars = [secrets.choice(group) for group in classes]
    chars += [secrets.choice(union) for _ in range(length - len(chars))]
    # SystemRandom, not random.shuffle: the ordering is part of the secret.
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def describe_role(group: str) -> str | None:
    """The stated effect of a role, or None when the group is not a role."""
    return ROLE_EFFECT.get(group)


def main(argv: list[str] | None = None) -> int:
    """Create the account, then delegate the grant. Returns the process exit code."""
    roles, scopes = grant_portal_roles.declared_groups()

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--username", required=True, help="email address used to sign in")
    parser.add_argument(
        "--groups",
        required=True,
        help=(f"comma separated, one role and one scope. roles: {', '.join(roles)}; scopes: {', '.join(scopes)}"),
    )
    parser.add_argument(
        "--expected-sandbox",
        help=(
            "refuse unless the pool belongs to this sandbox. Worth passing whenever a "
            "second sandbox exists, because provisioning into the wrong pool shows up "
            "only as a failed sign-in"
        ),
    )
    args = parser.parse_args(argv)

    wanted = [g.strip() for g in args.groups.split(",") if g.strip()]
    if not wanted:
        parser.error("--groups named nothing")

    try:
        outputs = load_outputs()
    except (RuntimeError, json.JSONDecodeError) as exc:
        print(f"cannot read the outputs file: {exc}", file=sys.stderr)
        return 2

    auth = outputs.get("auth") or {}
    pool = auth.get("user_pool_id")
    region = auth.get("aws_region")
    if not pool:
        print("amplify_outputs.json has no auth.user_pool_id", file=sys.stderr)
        return 2

    import boto3  # Imported late so --help works without credentials or the SDK.

    cognito = boto3.client("cognito-idp", region_name=region)
    cfn = boto3.client("cloudformation", region_name=region)

    try:
        described = cfn.describe_stack_resources(PhysicalResourceId=pool)
        sandbox = sandbox_identifier(described["StackResources"][0]["StackName"])
    except Exception as exc:  # noqa: BLE001 - any failure here means we cannot verify
        print(f"cannot resolve which sandbox owns {pool}: {exc}", file=sys.stderr)
        return 1

    print(f"pool     {pool} (sandbox '{sandbox}', {region})")

    if args.expected_sandbox and sandbox != args.expected_sandbox:
        print(
            f"✖ refusing: the outputs file points at sandbox '{sandbox}', not "
            f"'{args.expected_sandbox}'. An account created here cannot sign in to the "
            "portal you meant.",
            file=sys.stderr,
        )
        return 1

    for group in wanted:
        effect = describe_role(group)
        if effect:
            print(f"role     {group} -- {effect}")
        elif group in scopes:
            print(f"scope    {group}")

    if "storage-admin" in wanted:
        print()
        print("This role reaches irreversible operations from the browser:")
        for effect in STORAGE_ADMIN_IRREVERSIBLE:
            print(f"  - {effect}")
        print("  Group membership is reversible (admin-remove-user-from-group); what it unlocks is not.")
    print()

    created = False
    try:
        cognito.admin_get_user(UserPoolId=pool, Username=args.username)
        print(f"user     {args.username} already exists; password unchanged")
    except cognito.exceptions.UserNotFoundException:
        policy = cognito.describe_user_pool(UserPoolId=pool)["UserPool"].get("Policies", {}).get("PasswordPolicy", {})
        password = generate_password(policy)
        # SUPPRESS because a demo address cannot receive mail and the credential is
        # handed over directly. email_verified so the account is usable at once rather
        # than parked in a verification step.
        cognito.admin_create_user(
            UserPoolId=pool,
            Username=args.username,
            MessageAction="SUPPRESS",
            UserAttributes=[
                {"Name": "email", "Value": args.username},
                {"Name": "email_verified", "Value": "true"},
            ],
        )
        # Permanent, otherwise the first sign-in stops at a forced password change that
        # the portal's sign-in form is not wired to complete.
        cognito.admin_set_user_password(UserPoolId=pool, Username=args.username, Password=password, Permanent=True)
        created = True
        print(f"user     {args.username} created, password set (permanent)")

    print()
    print("groups (delegated to grant_portal_roles.py):")
    grant_status = grant_portal_roles.main(
        ["--apply", "--user-pool-id", pool, "--assign", f"{args.username}={','.join(wanted)}"]
    )
    if grant_status != 0:
        print(
            "✖ the account exists but the groups were refused. Fix the group names and "
            "re-run; this script is idempotent.",
            file=sys.stderr,
        )
        return 1

    if created:
        print()
        print("─" * 68)
        print(f"  username  {args.username}")
        print(f"  password  {password}")
        print("─" * 68)
        print("Shown once and not written to disk. Hand it over out of band.")

    print()
    print("Sign-in needs an https origin: it uses crypto.subtle, which browsers")
    print("restrict to secure contexts, so a LAN address does not work.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
