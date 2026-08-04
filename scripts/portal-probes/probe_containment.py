#!/usr/bin/env python3
"""Exercise the ARP containment actions against a deployed portal.

Unit tests cannot tell you whether a Lambda can reach ONTAP, whether the shared
modules are actually packaged, or whether the confirmation gate survived a
deployment. Every defect in the containment path found so far was found here and
not by the test suite:

- the shared modules were never packaged, so every containment call failed at
  import; the error text was the string "4", which reads like an HTTP status
- the name-mapping index was hardcoded to 1, so a second SMB block was
  impossible and ONTAP answered with a bare 409
- the ledger write hung until the function was killed, which made a block ONTAP
  had already accepted look like a failure to the caller

Subcommands
    gates     read-only. Confirms every containment action refuses without
              confirm=true, and that the protected-account guard holds.
    blocks    read-only. Lists active blocks and their expiry.
    svms      read-only. Lists the SVMs available as containment targets.
    ttl       writes. Blocks a principal, forces its expiry, runs the sweep and
              checks ONTAP stopped reporting it.
    fanout    writes. Blocks across every running SVM and checks the per-SVM
              result, then lifts what it created.
    lift      writes. Removes a named block. For clearing one left behind.

The writing subcommands use a principal that does not exist in the directory, so
no real access is affected, and they clean up after themselves. They still ask
before touching anything unless --yes is passed.

Examples
    python3 scripts/portal-probes/probe_containment.py gates
    python3 scripts/portal-probes/probe_containment.py blocks
    python3 scripts/portal-probes/probe_containment.py ttl --yes
    python3 scripts/portal-probes/probe_containment.py lift --domain CORP --username someone
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).parent))
from _common import (  # noqa: E402
    confirm_write,
    emit,
    find_function,
    find_table,
    invoke,
    summarise,
)

FUNCTION_FRAGMENT = "ArpResponseFun"
TABLE_FRAGMENT = "ContainmentBlocks"

INTERESTING = (
    "success",
    "error",
    "status",
    "expiresAt",
    "expiryTracked",
    "swept",
    "failed",
    "examined",
    "total",
    "fannedOut",
    "targets",
    "succeededOn",
    "failedOn",
    "entries_removed",
)

# A domain and user that should not exist in any directory, so a block on it
# denies nothing that matters.
PROBE_DOMAIN = "PROBEONLY"
PROBE_USER = "portalprobe01"

GATED_ACTIONS = {
    "blockSmbUser": {"domain": PROBE_DOMAIN, "username": PROBE_USER},
    "blockNfsIp": {"clientIp": "203.0.113.99"},  # RFC 5737 documentation range
    "containThreat": {"domain": PROBE_DOMAIN, "username": PROBE_USER},
    "disconnectSessions": {"user": f"{PROBE_DOMAIN}\\{PROBE_USER}"},
}


def cmd_gates(args, fn: str) -> int:
    failures = 0

    emit("checking that each containment action refuses without confirm=true")
    for action, params in sorted(GATED_ACTIONS.items()):
        result = invoke(fn, {"action": action, **params}, args.region)
        refused = result.get("success") is False and "confirm" in str(result.get("error", ""))
        emit(f"{'ok  ' if refused else 'FAIL'} {action}:", summarise(result, INTERESTING))
        failures += 0 if refused else 1

    emit("\nchecking that a protected account cannot be blocked")
    result = invoke(
        fn,
        {"action": "blockSmbUser", "domain": PROBE_DOMAIN, "username": "fsxadmin", "confirm": True},
        args.region,
    )
    protected = result.get("success") is False and "protected" in str(result.get("error", "")).lower()
    emit(f"{'ok  ' if protected else 'FAIL'} fsxadmin:", summarise(result, INTERESTING))
    failures += 0 if protected else 1

    print(f"\n{'GATES: PASS' if failures == 0 else f'GATES: {failures} FAILED'}")
    return 1 if failures else 0


def cmd_blocks(args, fn: str) -> int:
    payload: dict = {"action": "listActiveBlocks"}
    if args.all_svms:
        payload["allSvms"] = True
    result = invoke(fn, payload, args.region)
    emit("listing:", summarise(result, INTERESTING))
    for kind in ("smbBlocks", "nfsBlocks"):
        for block in result.get(kind, []):
            emit(
                f"{kind[:3]}",
                {
                    "svm": block.get("svm"),
                    "target": block.get("pattern") or block.get("client_match"),
                    "expiresAt": block.get("expiresAt"),
                    "managedByPortal": block.get("managedByPortal"),
                },
            )
    return 0 if result.get("success") else 1


def cmd_svms(args, fn: str) -> int:
    result = invoke(fn, {"action": "listSvms"}, args.region)
    emit("listSvms:", summarise(result, INTERESTING))
    for svm in result.get("svms", []):
        emit("", {"name": svm.get("name"), "state": svm.get("state")})
    return 0 if result.get("success") else 1


def cmd_ttl(args, fn: str) -> int:
    """Block, force the expiry into the past, sweep, and confirm it is gone.

    Backdating rather than waiting is deliberate: a probe that sleeps for the
    real interval is a probe nobody runs.
    """
    confirm_write("create and then lift one containment block", args.yes)

    table = find_table(TABLE_FRAGMENT, args.region)
    if not table:
        print("No containment ledger table found; expiry cannot be exercised.")
        return 1
    ddb = boto3.client("dynamodb", region_name=args.region)

    emit("\n1. block with a 1h expiry")
    first = invoke(
        fn,
        {
            "action": "blockSmbUser",
            "domain": PROBE_DOMAIN,
            "username": PROBE_USER,
            "confirm": True,
            "ttlHours": 1,
        },
        args.region,
    )
    emit("", summarise(first, INTERESTING))
    if not first.get("success"):
        print("\nblock failed, so the rest would prove nothing")
        return 1
    if not first.get("expiryTracked"):
        print("\nblock succeeded but no expiry was recorded: the ledger is unreachable.")
        print("Set vpcRouteTableIds so a DynamoDB gateway endpoint exists for the VPC functions.")
        return 1

    emit("\n2. sweep before it is due (expect swept=0)")
    emit("", summarise(invoke(fn, {"action": "sweepExpiredBlocks"}, args.region), INTERESTING))

    emit("\n3. backdate the expiry so it is due")
    svm = first.get("svm") or args.svm
    ddb.update_item(
        TableName=table,
        Key={"blockId": {"S": f"smb#{svm}#{PROBE_DOMAIN}#{PROBE_USER}"}},
        UpdateExpression="SET expiresAt = :e",
        ExpressionAttributeValues={":e": {"S": "2020-01-01T00:00:00Z"}},
    )
    emit("", "done")

    emit("\n4. sweep again (expect swept=1)")
    swept = invoke(fn, {"action": "sweepExpiredBlocks"}, args.region)
    emit("", summarise(swept, INTERESTING))

    emit("\n5. has ONTAP stopped reporting it?")
    listing = invoke(fn, {"action": "listActiveBlocks"}, args.region)
    remaining = [b for b in listing.get("smbBlocks", []) if PROBE_USER in str(b.get("pattern", ""))]
    emit("", f"probe blocks remaining: {len(remaining)}")

    ok = swept.get("swept") == 1 and not remaining
    print(f"\n{'TTL: PASS' if ok else 'TTL: FAILED'}")
    return 0 if ok else 1


def cmd_fanout(args, fn: str) -> int:
    confirm_write("create and then lift one containment block on every running SVM", args.yes)

    listing = invoke(fn, {"action": "listSvms"}, args.region)
    running = [s["name"] for s in listing.get("svms", []) if s.get("state") == "running"]
    emit(f"running SVMs: {len(running)}", running)
    if len(running) < 2:
        print("Fewer than two running SVMs; multi-target fan-out cannot be exercised here.")
        return 1

    emit("\n1. block across every running SVM")
    result = invoke(
        fn,
        {
            "action": "blockSmbUser",
            "domain": PROBE_DOMAIN,
            "username": PROBE_USER,
            "confirm": True,
            "ttlHours": 1,
            "svms": running,
        },
        args.region,
    )
    emit("", summarise(result, INTERESTING))
    for svm, detail in sorted((result.get("perSvm") or {}).items()):
        if not detail.get("success"):
            emit("  failed on", {svm: detail.get("error")})

    emit("\n2. listing across the same SVMs")
    blocks = invoke(fn, {"action": "listActiveBlocks", "svms": running}, args.region)
    for block in blocks.get("smbBlocks", []):
        emit("", {"svm": block.get("svm"), "expiresAt": block.get("expiresAt")})

    emit("\n3. cleanup")
    for svm in running:
        out = invoke(
            fn,
            {
                "action": "unblockSmbUser",
                "domain": PROBE_DOMAIN,
                "username": PROBE_USER,
                "svm": svm,
                "reason": "probe cleanup",
            },
            args.region,
        )
        emit("", {svm: out.get("status")})

    after = invoke(fn, {"action": "listActiveBlocks", "svms": running}, args.region)
    left = [b for b in after.get("smbBlocks", []) if PROBE_USER in str(b.get("pattern", ""))]
    emit("", f"probe blocks remaining: {len(left)}")

    # A partial failure is a legitimate outcome, not a probe failure: what
    # matters is that the result says which SVMs worked and cleanup left nothing.
    ok = bool(result.get("fannedOut")) and not left
    print(f"\n{'FANOUT: PASS' if ok else 'FANOUT: FAILED'}")
    if result.get("failedOn"):
        print(f"  note: {len(result['failedOn'])} SVM(s) refused the block, reported per SVM above")
    return 0 if ok else 1


def cmd_lift(args, fn: str) -> int:
    if not args.domain or not args.username:
        print("lift needs --domain and --username")
        return 1
    confirm_write(f"lift the SMB block on {args.domain}\\{args.username}", args.yes)

    emit("before:", summarise(invoke(fn, {"action": "listActiveBlocks"}, args.region), INTERESTING))
    payload = {
        "action": "unblockSmbUser",
        "domain": args.domain,
        "username": args.username,
        "reason": args.reason,
    }
    if args.svm:
        payload["svm"] = args.svm
    result = invoke(fn, payload, args.region)
    emit("lift:", summarise(result, INTERESTING))
    emit("after:", summarise(invoke(fn, {"action": "listActiveBlocks"}, args.region), INTERESTING))
    return 0 if result.get("success") else 1


COMMANDS = {
    "gates": cmd_gates,
    "blocks": cmd_blocks,
    "svms": cmd_svms,
    "ttl": cmd_ttl,
    "fanout": cmd_fanout,
    "lift": cmd_lift,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=sorted(COMMANDS))
    parser.add_argument("--region", default="ap-northeast-1")
    parser.add_argument("--svm", help="SVM name, for the subcommands that need one")
    parser.add_argument("--domain", help="Windows domain, for lift")
    parser.add_argument("--username", help="username, for lift")
    parser.add_argument("--reason", default="operator-requested", help="audit reason, for lift")
    parser.add_argument("--all-svms", action="store_true", help="widen a read-only listing to every SVM")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation for writing probes")
    args = parser.parse_args()

    fn = find_function(FUNCTION_FRAGMENT, args.region)
    print(f"function: {fn.split('-')[-1]} (in {args.region})")
    # Timestamps make a transcript comparable across runs.
    print(f"at:       {datetime.now(timezone.utc).replace(microsecond=0).isoformat()}\n")
    return COMMANDS[args.command](args, fn)


if __name__ == "__main__":
    sys.exit(main())
