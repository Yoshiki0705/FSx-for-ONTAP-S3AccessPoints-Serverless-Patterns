#!/usr/bin/env python3
"""Find what a stack deletion left behind, and remove it only when told to.

The gap this fills
------------------
Deleting a stack is not the end of the teardown. Measured on this repository's own
verification stacks (2026-09-14), after two stacks reported DELETE_COMPLETE:

* **15 CloudWatch log groups** survived, every one on never-expire retention. They
  are created by Lambda on first invocation, so they are not in the template and the
  stack deletion never had a claim on them.
* **2 DynamoDB tables** survived, carrying deletion protection and
  ``DeletionPolicy: Retain``. One still held three items.
* **1 Cognito user pool** survived on ``Retain`` -- deactivating its deletion
  protection was necessary but not sufficient, because a retained resource is
  removed from the stack's management rather than deleted.

None of that is a failure. It is what ``Retain`` and deletion protection are for. But
it means a teardown that stops at ``delete-stack`` leaves a standing charge and, in
the log groups' case, data with no expiry. The existing tooling reaches up to the
stack boundary and no further: ``cleanup_generic_ucs.py`` handles Athena workgroups,
versioned buckets and endpoint security groups; ``cleanup_stacks.sh`` unblocks
DELETE_FAILED. Neither looks at what outlived a successful delete.

Report first, delete on request
------------------------------
The default run changes nothing. It lists what it found, why the resource survived,
and -- for tables -- how many items are in it, because "empty" and "holds three rows"
are different decisions. ``--apply`` performs the removals.

This follows ``propose_cleanup.py``, which never deletes at all. The difference is
scope: that script decides whether teardown should begin, this one finishes one.

What is deliberately out of scope
---------------------------------
**Anything holding data under a retention lock, and anything belonging to the file
system.** SnapLock and WORM volumes, snapshot locks, S3 Object Lock, FSx for ONTAP
volumes, SVMs and file systems are never touched, and ``--apply`` will not reach
them. A retention lock is not a leftover: it is doing what it was configured to do,
and its retention period cannot be shortened afterwards. Removing a volume is data
loss, which no cleanup script should decide on anyone's behalf.

The resources here were all created by a CloudFormation stack that has since been
deleted. That is the boundary: this removes what a stack left, not what a person put
somewhere.

Usage
-----
::

    python3 scripts/cleanup_retained_resources.py --stack-prefix fsxn-portal
    python3 scripts/cleanup_retained_resources.py --stack-prefix fsxn- --apply
    python3 scripts/cleanup_retained_resources.py --stack-prefix x --only log-groups

    make cleanup-retained ARGS='--stack-prefix fsxn-portal'

Exit codes
----------
``0`` nothing found, or ``--apply`` removed everything it found. ``1`` leftovers
found while reporting (so it can gate a teardown check), or a removal failed. ``2``
usage.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

EXIT_OK = 0
EXIT_FOUND_OR_FAILED = 1
EXIT_USAGE = 2

#: Resource kinds this script knows how to find and remove.
KINDS = ("log-groups", "dynamodb", "user-pools")

#: Never touched, whatever the prefix matches. Listed so the exclusion is a value in
#: the program rather than an intention in a comment: a retention lock cannot be
#: shortened once set, and a volume is data.
NEVER_TOUCHED = (
    "FSx for ONTAP volumes, SVMs and file systems",
    "SnapLock and WORM volumes, and any snapshot under a lock",
    "S3 buckets and Object Lock configurations",
    "Secrets Manager secrets",
)


@dataclass
class Leftover:
    """One surviving resource, with why it survived and what removing it costs."""

    kind: str
    name: str
    reason: str
    detail: str = ""
    removal_note: str = ""


@dataclass
class Report:
    """What was found, and what happened if --apply was given."""

    leftovers: list[Leftover] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)


def _client(service: str, region: str | None):
    import boto3

    return boto3.client(service, region_name=region)


def find_log_groups(stack_prefix: str, region: str | None) -> list[Leftover]:
    """Find log groups whose name carries the stack prefix.

    Lambda creates these on first invocation, so they are absent from the template
    and a stack deletion has no claim on them. Retention is reported because the
    default is never-expire: the cost is small per group and unbounded in time.
    """
    logs = _client("logs", region)
    found: list[Leftover] = []
    paginator = logs.get_paginator("describe_log_groups")
    # Lambda's own prefix, plus the bare name, so API Gateway and custom-resource
    # groups are covered too.
    for prefix in (f"/aws/lambda/{stack_prefix}", f"/aws/{stack_prefix}", stack_prefix):
        for page in paginator.paginate(logGroupNamePrefix=prefix):
            for group in page.get("logGroups", []):
                name = group["logGroupName"]
                if any(f.name == name for f in found):
                    continue
                retention = group.get("retentionInDays")
                found.append(
                    Leftover(
                        kind="log-groups",
                        name=name,
                        reason="created by the function on first invocation, not by the template",
                        detail=("retention: never expires" if retention is None else f"retention: {retention} day(s)"),
                        removal_note="deletes the stored log events",
                    )
                )
    return found


def find_dynamodb_tables(stack_prefix: str, region: str | None) -> list[Leftover]:
    """Find tables whose name carries the stack prefix.

    Item count is reported because it decides the answer. `ItemCount` is updated
    about every six hours, so it is described as approximate rather than presented as
    a fact about this moment.
    """
    ddb = _client("dynamodb", region)
    found: list[Leftover] = []
    paginator = ddb.get_paginator("list_tables")
    for page in paginator.paginate():
        for table_name in page.get("TableNames", []):
            if not table_name.startswith(stack_prefix):
                continue
            described = ddb.describe_table(TableName=table_name)["Table"]
            protected = bool(described.get("DeletionProtectionEnabled"))
            items = described.get("ItemCount", 0)
            found.append(
                Leftover(
                    kind="dynamodb",
                    name=table_name,
                    reason=(
                        "deletion protection is on"
                        if protected
                        else "survived the stack deletion (DeletionPolicy: Retain)"
                    ),
                    detail=f"~{items} item(s) (DynamoDB updates this roughly every 6 hours)",
                    removal_note="deletes the table and its items" if items else "table is empty",
                )
            )
    return found


def find_user_pools(stack_prefix: str, region: str | None) -> list[Leftover]:
    """Find Cognito user pools whose name carries the stack prefix.

    A pool on ``Retain`` outlives its stack even with deletion protection cleared:
    clearing protection permits the delete, and ``Retain`` means the stack does not
    attempt one. Both have to be dealt with, in that order.
    """
    idp = _client("cognito-idp", region)
    found: list[Leftover] = []
    paginator = idp.get_paginator("list_user_pools")
    for page in paginator.paginate(MaxResults=60):
        for pool in page.get("UserPools", []):
            if stack_prefix not in pool["Name"]:
                continue
            described = idp.describe_user_pool(UserPoolId=pool["Id"])["UserPool"]
            protection = described.get("DeletionProtection", "INACTIVE")
            users = idp.describe_user_pool(UserPoolId=pool["Id"])["UserPool"].get("EstimatedNumberOfUsers", 0)
            found.append(
                Leftover(
                    kind="user-pools",
                    name=f"{pool['Id']} ({pool['Name']})",
                    reason=(
                        f"deletion protection is {protection}"
                        if protection == "ACTIVE"
                        else "survived the stack deletion (DeletionPolicy: Retain)"
                    ),
                    detail=f"~{users} user(s)",
                    removal_note="deletes the accounts in it, and the hosted UI domain with it",
                )
            )
    return found


def remove_log_group(name: str, region: str | None) -> None:
    _client("logs", region).delete_log_group(logGroupName=name)


def remove_dynamodb_table(name: str, region: str | None) -> None:
    """Clear deletion protection, then delete.

    Two calls because they answer different refusals: with protection on, the delete
    is refused outright.
    """
    ddb = _client("dynamodb", region)
    described = ddb.describe_table(TableName=name)["Table"]
    if described.get("DeletionProtectionEnabled"):
        ddb.update_table(TableName=name, DeletionProtectionEnabled=False)
    ddb.delete_table(TableName=name)


def remove_user_pool(name: str, region: str | None) -> None:
    """Clear deletion protection, then delete.

    ``UpdateUserPool`` replaces the whole configuration, so the settings that would
    otherwise reset are read back and sent with the change. Omitting them is refused
    a second time, for a different reason than the first -- which reads as the same
    failure repeating.
    """
    idp = _client("cognito-idp", region)
    pool_id = name.split(" ")[0]
    described = idp.describe_user_pool(UserPoolId=pool_id)["UserPool"]
    if described.get("DeletionProtection") == "ACTIVE":
        kwargs: dict = {"UserPoolId": pool_id, "DeletionProtection": "INACTIVE"}
        if described.get("AutoVerifiedAttributes"):
            kwargs["AutoVerifiedAttributes"] = described["AutoVerifiedAttributes"]
        if described.get("UserAttributeUpdateSettings"):
            kwargs["UserAttributeUpdateSettings"] = described["UserAttributeUpdateSettings"]
        if described.get("MfaConfiguration"):
            kwargs["MfaConfiguration"] = described["MfaConfiguration"]
        sms = described.get("SmsConfiguration")
        if sms:
            kwargs["SmsConfiguration"] = sms
        idp.update_user_pool(**kwargs)
    idp.delete_user_pool(UserPoolId=pool_id)


REMOVERS = {
    "log-groups": remove_log_group,
    "dynamodb": remove_dynamodb_table,
    "user-pools": remove_user_pool,
}

FINDERS = {
    "log-groups": find_log_groups,
    "dynamodb": find_dynamodb_tables,
    "user-pools": find_user_pools,
}


def live_stacks(stack_prefix: str, region: str | None) -> list[str]:
    """Names of stacks matching the prefix that have not been deleted.

    A non-empty result means the prefix still identifies something in use, so its
    resources are not leftovers. Deleted stacks are excluded by status rather than by
    absence: CloudFormation keeps them listable for 90 days, and treating a
    DELETE_COMPLETE entry as "standing" would block every legitimate run.

    DELETE_IN_PROGRESS counts as standing. This script's premise is that the stack
    deletion already finished, and a stack still deleting owns its resources:
    removing them underneath it can leave the stack in DELETE_FAILED, and a table
    CloudFormation was about to retain would be gone before anyone decided that.
    Only DELETE_COMPLETE means there is nothing left to own them.
    """
    cfn = _client("cloudformation", region)
    live: list[str] = []
    paginator = cfn.get_paginator("list_stacks")
    for page in paginator.paginate():
        for summary in page.get("StackSummaries", []):
            if summary.get("StackStatus") == "DELETE_COMPLETE":
                continue
            if summary["StackName"].startswith(stack_prefix):
                live.append(summary["StackName"])
    return live


def collect(stack_prefix: str, region: str | None, kinds: tuple[str, ...]) -> Report:
    report = Report()
    for kind in kinds:
        try:
            report.leftovers.extend(FINDERS[kind](stack_prefix, region))
        except Exception as error:  # noqa: BLE001 - one unreadable service must not hide the rest
            report.failed.append((f"{kind} (listing)", str(error)))
    return report


def print_report(report: Report, stack_prefix: str, apply: bool) -> None:
    print(f"=== leftovers matching {stack_prefix!r} ===")
    if not report.leftovers:
        print("  none found")
    for kind in KINDS:
        items = [item for item in report.leftovers if item.kind == kind]
        if not items:
            continue
        print(f"\n  {kind} ({len(items)}):")
        for item in items:
            print(f"    {item.name}")
            print(f"        why it survived: {item.reason}")
            if item.detail:
                print(f"        {item.detail}")
            if not apply and item.removal_note:
                print(f"        removing it: {item.removal_note}")
    print("\n  never touched by this script, whatever the prefix matches:")
    for entry in NEVER_TOUCHED:
        print(f"    - {entry}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report -- and on request remove -- what a stack deletion left behind.",
        epilog=(
            "Default is a report and changes nothing. Exit 1 while reporting means "
            "leftovers were found, so this can gate a teardown check."
        ),
    )
    parser.add_argument(
        "--stack-prefix",
        required=True,
        help="Name prefix of the deleted stack, e.g. fsxn-portal-nx. Required: this script will not sweep an account.",
    )
    parser.add_argument("--region", default=None, help="AWS region (default: the session's)")
    parser.add_argument(
        "--only",
        choices=KINDS,
        action="append",
        help="Limit to one kind; repeatable. Default: all of them.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform the removals. Without this nothing is changed.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    # A bare or very short prefix would match resources belonging to stacks that are
    # still standing. Refused rather than confirmed, because the confirmation would
    # be answered by whoever typed it.
    if len(args.stack_prefix.strip("-_ ")) < 4:
        print(
            f"❌ --stack-prefix {args.stack_prefix!r} is too short to identify one stack's "
            "leftovers. Use at least four characters of the stack name."
        )
        return EXIT_USAGE

    kinds = tuple(args.only) if args.only else KINDS

    # `--apply` is refused while a stack with this prefix is still standing. The
    # prefix is a name fragment, so it matches live resources as readily as
    # leftovers: this repository's own portal prefix matches six DynamoDB tables that
    # are in use. Reporting on those is harmless; deleting them is not something a
    # person should be able to do by getting a prefix slightly wrong. Checked against
    # CloudFormation rather than asked as a confirmation, because the confirmation
    # would be answered by whoever typed the prefix.
    if args.apply:
        try:
            standing = live_stacks(args.stack_prefix, args.region)
        except ImportError as error:
            print(f"❌ {error}")
            print("   Install the dependencies first: make install")
            return EXIT_FOUND_OR_FAILED
        if standing:
            print(f"❌ --apply refused: {len(standing)} stack(s) matching {args.stack_prefix!r} still exist.")
            for name in standing[:5]:
                print(f"     {name}")
            print(
                "   Those resources may belong to a stack in use. Delete the stack first, "
                "then run this to collect what it left behind."
            )
            return EXIT_USAGE

    try:
        report = collect(args.stack_prefix, args.region, kinds)
    except ImportError as error:
        print(f"❌ {error}")
        print("   Install the dependencies first: make install")
        return EXIT_FOUND_OR_FAILED

    print_report(report, args.stack_prefix, args.apply)

    if not args.apply:
        for kind, error in report.failed:
            print(f"\n  could not list {kind}: {error}")
        if report.leftovers:
            print(
                f"\n{len(report.leftovers)} leftover(s). Re-run with --apply to remove them. "
                "Read the list first: a table with items in it and an empty one look the same "
                "in a count."
            )
            return EXIT_FOUND_OR_FAILED
        return EXIT_OK if not report.failed else EXIT_FOUND_OR_FAILED

    print("\n=== removing ===")
    for item in report.leftovers:
        try:
            REMOVERS[item.kind](item.name, args.region)
            report.removed.append(item.name)
            print(f"  removed {item.name}")
        except Exception as error:  # noqa: BLE001 - one failure must not stop the rest
            report.failed.append((item.name, str(error)))
            print(f"  FAILED  {item.name}: {error}")

    print(f"\nremoved {len(report.removed)}, failed {len(report.failed)}")
    if report.failed:
        print(
            "  A failure here is usually a dependency that has to go first. "
            "docs/ja/scaffolding-deploy-verification.md#撤収手順 has the order."
        )
        return EXIT_FOUND_OR_FAILED
    print("  Confirm by state rather than by this output: re-run without --apply.")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
