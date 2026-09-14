#!/usr/bin/env python3
"""Prove a deployed stack reaches its access point: list, read, write, read back.

Why this exists, rather than the test suites that already pass
--------------------------------------------------------------
A green local suite is not evidence that the deployed stack can reach the FSx for
ONTAP S3 Access Point. Measured while comparing three scaffolding options
(2026-09-14): a local end-to-end run passed 7 of 9 checks, and **the upload
round-trip was among the ones that passed**, because the mocked bucket starts empty
and a write-then-read-back completes entirely inside the mock. Only the two checks
that depended on pre-existing real data failed. So the suite was green on a build
whose IAM policy could not have reached the access point at all.

The failure that shape hides is specific and quiet. A policy naming the access point
in the bucket form (``arn:aws:s3:::<alias>/*``) deploys without complaint, reports
CREATE_COMPLETE, and answers AccessDenied for list, get and put alike --
`check_s3ap_iam_patterns.py` catches that in the template, and this catches it in the
deployment, which is where a parameter typo or a hand-edited policy lands.

What it does
------------
Resolves the access point from the stack itself -- its Parameters and Outputs -- so
the caller supplies a stack name and nothing else. Then:

1. **list** a prefix and report the count
2. **read** the first object found and report its size and content type
3. **write** one small object into a prefix reserved for this check
4. **read back** and compare bytes, then confirm the write appears in a listing
5. **delete** what it wrote

Step 4 is the one worth having. A write that returns 200 and a write that is visible
to the next reader are different claims, and only the second is what a portal user
experiences.

Writes are confined to ``smoke-checks/`` by default. This tooling points at live NAS
volumes that NFS and SMB clients are also using, so an arbitrary key is not
acceptable and the prefix is a parameter rather than a constant.

Usage
-----
::

    python3 scripts/smoke_deployed_pattern.py --stack <stack-name>
    python3 scripts/smoke_deployed_pattern.py --stack <name> --list-prefix reports/
    python3 scripts/smoke_deployed_pattern.py --access-point <alias>   # skip the stack
    python3 scripts/smoke_deployed_pattern.py --stack <name> --read-only

    make smoke STACK=<stack-name>

Exit codes
----------
``0`` every step passed. ``1`` a step failed -- the output names which. ``2`` usage,
or the access point could not be resolved from the stack.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

#: Stack parameter and output keys that carry an access point, most specific first.
#: Both are searched because a pattern may take the alias as a parameter, publish it
#: as an output, or do both -- and the alias is what the S3 client wants either way.
ACCESS_POINT_KEYS = (
    "S3AccessPointAlias",
    "S3AccessPointArn",
    "S3AccessPoint",
    "AccessPointAlias",
)

#: Where the write goes unless told otherwise. Trailing slash is significant.
DEFAULT_WRITE_PREFIX = "smoke-checks/"


class SmokeError(Exception):
    """A step failed. The message says which step and what the service answered."""


def _say(status: str, message: str) -> None:
    print(f"  {status:<7} {message}")


def resolve_access_point(stack_name: str, region: str | None) -> tuple[str, str]:
    """Find the access point a stack was deployed against.

    Returns the value and where it came from, so the report says which key was read
    rather than leaving the caller to guess why a stack resolved the way it did.

    Parameters are searched before outputs. A pattern that takes the alias as a
    parameter is being told which access point to use; an output may be a derived or
    reformatted copy.
    """
    import boto3

    cfn = boto3.client("cloudformation", region_name=region)
    try:
        stacks = cfn.describe_stacks(StackName=stack_name)["Stacks"]
    except Exception as error:  # noqa: BLE001 - surfaced with the stack name attached
        raise SmokeError(f"cannot describe stack {stack_name!r}: {error}") from error
    if not stacks:
        raise SmokeError(f"stack {stack_name!r} returned no description")
    stack = stacks[0]

    params = {p["ParameterKey"]: p.get("ParameterValue", "") for p in stack.get("Parameters", [])}
    outputs = {o["OutputKey"]: o.get("OutputValue", "") for o in stack.get("Outputs", [])}

    for source_name, mapping in (("parameter", params), ("output", outputs)):
        for key in ACCESS_POINT_KEYS:
            value = (mapping.get(key) or "").strip()
            if value:
                return value, f"{source_name} {key}"

    # Fall back to any key that looks like one, so a pattern using its own naming is
    # not a dead end -- reported with the key so the caller can see what was matched.
    for source_name, mapping in (("parameter", params), ("output", outputs)):
        for key, value in sorted(mapping.items()):
            if "s3accesspoint" in key.lower().replace("_", "") and (value or "").strip():
                return value.strip(), f"{source_name} {key} (matched by name)"

    raise SmokeError(
        f"stack {stack_name!r} has no access point in its parameters or outputs. "
        f"Looked for {', '.join(ACCESS_POINT_KEYS)}. "
        "Pass --access-point to supply it directly."
    )


def build_helper(access_point: str, region: str | None) -> Any:
    """Construct the repository's own S3 AP helper.

    Imported here rather than at module scope so `--help` works without boto3 and so
    the import error, when it happens, arrives with this file's context.
    """
    import boto3

    from shared.s3ap_helper import S3ApHelper

    session = boto3.Session(region_name=region) if region else boto3.Session()
    return S3ApHelper(access_point, session=session)


def step_list(helper: Any, prefix: str, max_keys: int) -> list[dict]:
    """List a prefix. Returns the objects found, which the read step consumes."""
    objects = helper.list_objects(prefix=prefix, max_keys=max_keys)
    files = [o for o in objects if not str(o.get("Key", "")).endswith("/")]
    _say("[list]", f"prefix={prefix or '(root)'} -> {len(files)} object(s)")
    for obj in files[:3]:
        _say("", f"    {obj.get('Size', 0):>9} B  {str(obj.get('Key', '')).split('/')[-1]}")
    return files


def step_read(helper: Any, files: list[dict]) -> None:
    """Read the first listed object and check the size against the listing.

    The comparison matters: a listing is served from metadata and a read from the
    object, so agreeing on the size is a weak but real check that the two views are
    of the same thing.
    """
    if not files:
        _say("[read]", "skipped -- the listing was empty, so there is nothing to read")
        return
    target = files[0]
    key = str(target["Key"])
    head = helper.head_object(key)
    body = helper.get_object_bytes(key)
    listed = int(target.get("Size", 0))
    content_type = head.get("ContentType", "(none)")
    _say("[read]", f"{len(body)} bytes, {content_type}")
    if listed and listed != len(body):
        raise SmokeError(
            f"read {len(body)} bytes for {key} but the listing said {listed}. The listing and the object disagree."
        )
    _say("", f"    size agrees with the listing: {bool(listed)}")


def step_write_and_read_back(helper: Any, write_prefix: str) -> str:
    """Write one object, read it back, and confirm a listing shows it.

    Returns the key written, so the caller can remove it even when a later step
    raises.
    """
    if not write_prefix.endswith("/"):
        raise SmokeError(f"--write-prefix must end with '/'; got {write_prefix!r}")
    key = f"{write_prefix}smoke-{int(time.time())}.txt"
    payload = b"written by scripts/smoke_deployed_pattern.py\n"

    helper.put_object(key, payload, content_type="text/plain; charset=utf-8")
    _say("[write]", f"{key} ({len(payload)} B)")

    back = helper.get_object_bytes(key)
    if back != payload:
        raise SmokeError(f"read back {len(back)} bytes for {key}, which differ from what was written")
    _say("", "    round-trip content identical: True")

    listed = helper.list_objects(prefix=write_prefix, max_keys=100)
    visible = any(str(o.get("Key")) == key for o in listed)
    _say("", f"    visible in a listing: {visible}")
    if not visible:
        raise SmokeError(
            f"{key} was written and read back but does not appear under {write_prefix}. "
            "A write the next reader cannot see is not a usable write."
        )
    return key


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="List, read and write against a deployed stack's S3 Access Point.",
        epilog="Exit 0 all steps passed, 1 a step failed, 2 usage or unresolved access point.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--stack", help="CloudFormation stack to read the access point from")
    source.add_argument("--access-point", help="Access point alias or ARN, supplied directly")
    parser.add_argument("--region", default=None, help="AWS region (default: the session's)")
    parser.add_argument(
        "--list-prefix",
        default="",
        help="Prefix to list and read from (default: the access point root)",
    )
    parser.add_argument(
        "--write-prefix",
        default=DEFAULT_WRITE_PREFIX,
        help=f"Prefix the write goes into, ending in '/' (default: {DEFAULT_WRITE_PREFIX})",
    )
    parser.add_argument("--max-keys", type=int, default=50, help="Objects to list (default: 50)")
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="List and read only. Use where the caller has no write permission.",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Leave the written object in place instead of deleting it.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    try:
        if args.stack:
            access_point, source = resolve_access_point(args.stack, args.region)
        else:
            access_point, source = args.access_point, "--access-point"
    except SmokeError as error:
        print(f"❌ {error}")
        return EXIT_USAGE

    # An alias carries a random token, so only its leading label is printed. This is
    # the caller's own terminal, but the output gets pasted into issues and pull
    # requests, and eliding it here is cheaper than remembering to redact it there.
    label = access_point.split("-")[0] if "-" in access_point else access_point
    print(f"=== smoke check: {args.stack or f'{label}…'} ===")
    _say("[target]", f"access point from {source} (leading label: {label}…)")

    written: str | None = None
    helper = None
    try:
        helper = build_helper(access_point, args.region)
        files = step_list(helper, args.list_prefix, args.max_keys)
        step_read(helper, files)
        if args.read_only:
            _say("[write]", "skipped -- --read-only")
        else:
            written = step_write_and_read_back(helper, args.write_prefix)
    except SmokeError as error:
        print(f"\n❌ {error}")
        return EXIT_FAILED
    except ImportError as error:
        # Ahead of the catch-all so a missing dependency is not diagnosed as a
        # permission problem. The first run of this script answered
        # "ModuleNotFoundError: No module named 'boto3'" with the IAM hint attached,
        # which sends the reader to rewrite a policy that was never consulted.
        print(f"\n❌ {error}")
        print("   Install the dependencies first: make install")
        return EXIT_FAILED
    except Exception as error:  # noqa: BLE001 - any service error is a failed check
        print(f"\n❌ {type(error).__name__}: {error}")
        if "AccessDenied" in f"{type(error).__name__}{error}":
            print(
                "   AccessDenied on list, get and put alike is the signature of a policy that "
                "names the access point in the bucket form. The access-point form is required: "
                "arn:aws:s3:<region>:<account-id>:accesspoint/<name> for ListBucket and "
                "…/object/* for GetObject and PutObject."
            )
        return EXIT_FAILED
    finally:
        if written and not args.keep and helper is not None:
            try:
                helper.delete_object(written)
                _say("[clean]", f"removed {written}")
            except Exception as error:  # noqa: BLE001 - reported, does not mask a result
                _say("[clean]", f"could not remove {written}: {error}")

    print("\n✅ list, read and write all reached the access point.")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
