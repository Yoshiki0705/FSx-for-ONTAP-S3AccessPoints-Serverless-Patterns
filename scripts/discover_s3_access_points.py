#!/usr/bin/env python3
"""Enumerate FSx for ONTAP S3 access points across accounts and regions.

The portal reads one alias from `amplify/portal-config.ts`, which is fine for a
single deployment and does not answer "which access points exist, and are they
usable?" in an estate with many accounts, file systems and access points. A hand
kept list goes stale silently: a deleted or `MISCONFIGURED` access point still
looks correct in a config file.

`fsx describe-s3-access-point-attachments` is the primitive that does answer it.
One call per (account, region) returns every attachment with its `Lifecycle`, its
alias, its network origin and the volume behind it, so the inventory is derived
rather than maintained.

Usage:
    # Current credentials, one region
    python3 scripts/discover_s3_access_points.py --regions ap-northeast-1

    # Several regions, only usable ones, aliases for scripting
    python3 scripts/discover_s3_access_points.py \\
        --regions ap-northeast-1 us-east-1 --lifecycle AVAILABLE --format alias

    # Across an organization, assuming the same role name in each account
    python3 scripts/discover_s3_access_points.py --regions ap-northeast-1 \\
        --accounts 111111111111 222222222222 --role-name PortalDiscoveryReadOnly

    # Gate: fail if the alias a deployment expects is not AVAILABLE
    python3 scripts/discover_s3_access_points.py --regions ap-northeast-1 \\
        --require-alias my-ap-0123456789abcdef0-ext-s3alias

Read-only: describes attachments, and calls sts:AssumeRole when --role-name is
given. Nothing here creates, changes or deletes anything.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Iterator

import boto3

# `AVAILABLE` is the only state in which data operations work. The others are
# listed so that a caller asking for everything sees why an alias is unusable
# rather than finding it absent.
USABLE = "AVAILABLE"


def _client(service: str, region: str, account: str | None, role_name: str | None) -> Any:
    """A client for `region`, in `account` when a role to assume is given."""
    if not (account and role_name):
        return boto3.client(service, region_name=region)
    sts = boto3.client("sts")
    assumed = sts.assume_role(
        RoleArn=f"arn:aws:iam::{account}:role/{role_name}",
        RoleSessionName="s3ap-discovery",
    )["Credentials"]
    return boto3.client(
        service,
        region_name=region,
        aws_access_key_id=assumed["AccessKeyId"],
        aws_secret_access_key=assumed["SecretAccessKey"],
        aws_session_token=assumed["SessionToken"],
    )


def attachments(fsx: Any) -> Iterator[dict[str, Any]]:
    """Every attachment the client can see, following pagination.

    The paginator is used rather than a single call because an estate with many
    access points returns them in pages, and reading only the first page would
    report a subset as the whole inventory.

    Args:
        fsx: An FSx client, already scoped to one account and region.

    Yields:
        Raw `S3AccessPointAttachments` entries, in API order.
    """
    paginator = fsx.get_paginator("describe_s3_access_point_attachments")
    for page in paginator.paginate():
        yield from page.get("S3AccessPointAttachments", [])


def describe(attachment: dict[str, Any], account: str | None, region: str) -> dict[str, Any]:
    """The fields needed to decide whether an access point is usable, flattened.

    Args:
        attachment: One `S3AccessPointAttachments` entry.
        account: Account the attachment was read from, or None for the caller's own.
        region: Region the attachment was read from.

    Returns:
        A flat record: account, region, name, lifecycle, alias, origin, type,
        volume_id and the lifecycle transition reason when the API supplied one.
    """
    access_point = attachment.get("S3AccessPoint") or {}
    vpc = access_point.get("VpcConfiguration") or {}
    ontap = attachment.get("OpenZFSConfiguration") or {}
    return {
        "account": account or "current",
        "region": region,
        "name": attachment.get("Name"),
        "lifecycle": attachment.get("Lifecycle"),
        "alias": access_point.get("Alias"),
        # Absent means Internet-origin, which is what a browser-facing portal
        # needs; a VPC id means the caller has to be inside that VPC.
        "origin": vpc.get("VpcId") or "internet",
        "type": attachment.get("Type"),
        "volume_id": ontap.get("VolumeId"),
        "reason": (attachment.get("LifecycleTransitionReason") or {}).get("Message"),
    }


def collect(
    regions: list[str],
    accounts: list[str],
    role_name: str | None,
    lifecycle: str | None,
) -> list[dict[str, Any]]:
    """Inventory across the requested regions, and accounts when given.

    Args:
        regions: Regions to query.
        accounts: Account ids to query; empty means the caller's own account.
        role_name: Role assumed in each account. Required when accounts is set.
        lifecycle: Keep only attachments in this state; None keeps all.

    Returns:
        Flat records as produced by `describe`, one per attachment kept.
    """
    found: list[dict[str, Any]] = []
    for account in accounts or [None]:
        for region in regions:
            fsx = _client("fsx", region, account, role_name)
            for attachment in attachments(fsx):
                row = describe(attachment, account, region)
                if lifecycle and row["lifecycle"] != lifecycle:
                    continue
                found.append(row)
    return found


def main(argv: list[str] | None = None) -> int:
    """Print the inventory and, with --require-alias, gate on it.

    Args:
        argv: Command-line arguments, defaulting to `sys.argv[1:]`.

    Returns:
        0 when every required alias was found, 1 otherwise.
    """
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--regions", nargs="+", required=True, help="Regions to query")
    parser.add_argument("--accounts", nargs="*", default=[], help="Account ids; needs --role-name")
    parser.add_argument("--role-name", help="Role assumed in each account")
    parser.add_argument(
        "--lifecycle",
        help=f"Keep only this lifecycle state, e.g. {USABLE}",
    )
    parser.add_argument("--format", choices=["json", "table", "alias"], default="json")
    parser.add_argument(
        "--require-alias",
        action="append",
        default=[],
        help="Exit non-zero unless this alias was found (repeatable). Implies --lifecycle AVAILABLE.",
    )
    args = parser.parse_args(argv)

    if args.accounts and not args.role_name:
        parser.error("--accounts needs --role-name: cross-account describe requires a role to assume")

    lifecycle = USABLE if args.require_alias else args.lifecycle
    rows = collect(args.regions, args.accounts, args.role_name, lifecycle)

    if args.format == "json":
        print(json.dumps(rows, indent=2))
    elif args.format == "alias":
        for row in rows:
            print(row["alias"])
    else:
        width = max((len(str(r["name"])) for r in rows), default=4)
        for row in rows:
            print(
                f"{row['region']}  {str(row['name']):<{width}}  {row['lifecycle']:<12} "
                f"{row['origin']:<24} {row['alias']}"
            )

    missing = [a for a in args.require_alias if a not in {r["alias"] for r in rows}]
    if missing:
        # Printed to stderr so `--format alias` stays pipeable.
        print(f"not found or not {USABLE}: {', '.join(missing)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
