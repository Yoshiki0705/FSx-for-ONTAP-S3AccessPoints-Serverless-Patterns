#!/usr/bin/env python3
"""Compare `groupApMapping` in portal-config.ts with the access point tags.

The mapping decides which Cognito group browses which access point, and it is a
hand-written object. Nothing has been telling anyone when it stops matching the
resources: an access point that was replaced keeps its old alias in the file, and
the group silently points at something that no longer exists.

Deriving the mapping from tags instead would move the source of truth onto
whoever creates the access point. That is a larger change to how visibility is
decided, so this does the smaller thing: the file stays authoritative, and this
reports where the two disagree. A missing tag is a finding, not a failure of the
portal -- nothing here changes what anyone can browse.

The tag key defaults to `PortalGroup`. An access point tagged
`PortalGroup=engineering` is expected to appear in the mapping under
`engineering`, and vice versa.

Usage:
    python3 scripts/check_group_ap_tags.py --regions ap-northeast-1
    python3 scripts/check_group_ap_tags.py --regions ap-northeast-1 --tag-key Team
    python3 scripts/check_group_ap_tags.py --regions ap-northeast-1 --config path/to/portal-config.ts

Exit codes: 0 when they agree (or the mapping is empty), 1 on any disagreement,
2 when the configuration could not be read. Read-only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import boto3

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO_ROOT / "solutions" / "amplify-portal" / "amplify" / "portal-config.ts"
DEFAULT_TAG_KEY = "PortalGroup"

# `groupApMapping: { engineering: "alias", ... }`, allowing quoted keys and
# trailing commas. Parsed with a regex because portal-config.ts is TypeScript:
# running it would need a toolchain, and this check has to work from any
# language's CI.
_MAPPING_BLOCK = re.compile(r"groupApMapping\s*:\s*\{(?P<body>[^}]*)\}", re.DOTALL)
_ENTRY = re.compile(r"""['"]?(?P<group>[A-Za-z0-9_.\-]+)['"]?\s*:\s*['"](?P<alias>[^'"]*)['"]""")


def parse_mapping(source: str) -> dict[str, str]:
    """Group to alias pairs declared in portal-config.ts.

    Args:
        source: Contents of portal-config.ts.

    Returns:
        The mapping, empty when the object is absent or has no entries. An empty
        mapping is the documented default (all users share one access point), so
        it is not an error.
    """
    block = _MAPPING_BLOCK.search(source)
    if not block:
        return {}
    return {m.group("group"): m.group("alias") for m in _ENTRY.finditer(block.group("body"))}


def tagged_access_points(regions: list[str], tag_key: str) -> dict[str, list[str]]:
    """Group to aliases as the access point tags declare it.

    A list per group because more than one access point can carry the same tag
    value; that is itself worth reporting rather than silently picking one.

    Args:
        regions: Regions to query.
        tag_key: Tag whose value names the Cognito group.

    Returns:
        Mapping of tag value to the aliases carrying it.
    """
    found: dict[str, list[str]] = {}
    for region in regions:
        fsx = boto3.client("fsx", region_name=region)
        for page in fsx.get_paginator("describe_s3_access_point_attachments").paginate():
            for attachment in page.get("S3AccessPointAttachments", []):
                alias = (attachment.get("S3AccessPoint") or {}).get("Alias")
                if not alias:
                    continue
                for tag in attachment.get("Tags") or []:
                    if tag.get("Key") == tag_key and tag.get("Value"):
                        found.setdefault(tag["Value"], []).append(alias)
    return found


def compare(mapping: dict[str, str], tagged: dict[str, list[str]], tag_key: str) -> list[str]:
    """Disagreements between the configured mapping and the tags.

    Args:
        mapping: Group to alias from portal-config.ts.
        tagged: Tag value to aliases from the FSx API.
        tag_key: Tag key, named in the messages so a finding is actionable.

    Returns:
        One message per disagreement, empty when they agree.
    """
    findings: list[str] = []
    for group, alias in sorted(mapping.items()):
        aliases = tagged.get(group)
        if aliases is None:
            findings.append(f"{group} -> {alias}: no access point tagged {tag_key}={group}")
        elif alias not in aliases:
            findings.append(f"{group} -> {alias}: tagged {tag_key}={group} is {', '.join(sorted(aliases))}")
        elif len(aliases) > 1:
            findings.append(
                f"{group} -> {alias}: {len(aliases)} access points are tagged {tag_key}={group} "
                f"({', '.join(sorted(aliases))}); the mapping can name only one"
            )
    for group, aliases in sorted(tagged.items()):
        if group not in mapping:
            findings.append(
                f"{', '.join(sorted(aliases))}: tagged {tag_key}={group}, which the mapping does not mention"
            )
    return findings


def main(argv: list[str] | None = None) -> int:
    """Report disagreements and return a shell exit code.

    Args:
        argv: Command-line arguments, defaulting to `sys.argv[1:]`.

    Returns:
        0 when the mapping and the tags agree, 1 on a disagreement, 2 when
        portal-config.ts is missing.
    """
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--regions", nargs="+", required=True)
    parser.add_argument("--tag-key", default=DEFAULT_TAG_KEY)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    if not args.config.exists():
        # gitignored, so CI without a real environment has nothing to compare.
        # Reported rather than passed silently, because "no config" and "config
        # agrees with the tags" are different answers.
        print(f"{args.config} not found: nothing to compare", file=sys.stderr)
        return 2

    mapping = parse_mapping(args.config.read_text())
    if not mapping:
        print("groupApMapping is empty: all users share one access point, nothing to compare")
        return 0

    findings = compare(mapping, tagged_access_points(args.regions, args.tag_key), args.tag_key)

    if args.format == "json":
        print(json.dumps({"mapping": mapping, "findings": findings}, indent=2))
    else:
        for finding in findings:
            print(f"MISMATCH {finding}")
        if not findings:
            print(f"GROUP AP TAGS: PASS ({len(mapping)} group(s) agree with {args.tag_key})")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
