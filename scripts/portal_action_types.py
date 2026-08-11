#!/usr/bin/env python3
"""Generate and verify the TypeScript parameter map for the portal's dispatch actions.

The parameter check that lives next door compares what a call site sends against
what a handler reads, and it catches a key that is missing or misspelled. It cannot
catch a key whose *name* is right and whose *value* is wrong — a volume name passed
where a UUID is expected satisfies every check it makes, and the request fails in
ONTAP instead of in review.

Closing that needs the compiler, which needs types. This module derives those types
from the handlers themselves, so the declared shape of an action is not a second
description of the backend that can quietly disagree with it.

Two modes:

    --emit      print the TypeScript module
    --check     compare the committed module against the handlers and fail on drift

`--check` is the part that keeps working after today: it fails when a handler starts
requiring a parameter the map does not declare, or when the map declares one no
handler reads.

Branded types are applied from BRANDS, keyed by parameter name. That mapping is
hand-maintained on purpose — which values must not be interchangeable is a judgement
about the domain, not something a parser can infer.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_portal_action_params import (  # noqa: E402
    PORTAL,
    ActionContract,
    contracts_for,
    discover_endpoints,
)

TARGET = PORTAL / "src" / "lib" / "dispatchActions.ts"

# One interface per handler directory, not per endpoint. A query endpoint and a
# mutation endpoint reach the same Lambda — `adminQuery` and `adminMutation` both
# land in functions/resource-management — so generating per endpoint listed every
# action twice and implied a read/write split the backend does not make.
HANDLER_MAPS = {
    "resource-management": "ResourceMgmtActionParams",
    "data-protection": "DataProtectionActionParams",
    "snapshots": "SnapshotsActionParams",
    "list-files": "ListFilesActionParams",
    "agent-chat": "AgentChatActionParams",
}

# Parameter name -> branded type. A branded type is a string or number that plain
# strings and numbers are not assignable to, so the value has to be produced
# deliberately. This is the whole point of the exercise: `resizeVolume` taking a
# `VolumeUuid` cannot be handed a volume name, even though both are strings.
#
# Only values that are genuinely confusable are branded. Branding everything would
# force a cast at every call site, and a cast is how a type system is told to stop
# helping.
BRANDS: dict[str, str] = {
    # Identifiers, each of which has a human-readable sibling that is not it.
    "volumeUuid": "VolumeUuid",
    "snapshotId": "SnapshotId",
    # The resource-management handler spells the same thing differently.
    "snapshotUuid": "SnapshotId",
    "relationshipUuid": "SnapmirrorUuid",
    "svmUuid": "SvmUuid",
    "policyUuid": "PolicyUuid",
    "qtreeId": "QtreeId",
    # Absolute instants, whose sibling is a number of days. The lock button sent
    # a day count where an instant was expected and failed on every click.
    "expiryTime": "IsoTimestamp",
    # ISO 8601 durations, whose sibling is also a number of days.
    "retentionPeriod": "IsoDuration",
    "retentionDefault": "IsoDuration",
    "retentionMin": "IsoDuration",
    "retentionMax": "IsoDuration",
    "autocommitPeriod": "IsoDuration",
}

# Parameter name -> TypeScript type, for values that are not strings. Wrong here is
# visible immediately: a boolean flag typed as a string would reject `true`.
SCALARS: dict[str, str] = {
    "days": "number",
    "years": "number",
    "sizeGiB": "number",
    "newSizeGiB": "number",
    "maxFileSize": "number",
    "maxKeys": "number",
    "maxResults": "number",
    "maxRecords": "number",
    "limit": "number",
    "count": "number",
    "retentionDays": "number",
    "ttlHours": "number",
    # Seconds until a presigned URL expires. The handlers clamp it with `min(...)`,
    # which raises a TypeError on a string, so declaring it as one would have made
    # every well-typed caller fail at runtime.
    "expiresIn": "number",
    "thresholdPercent": "number",
    "lookbackMinutes": "number",
    "priority": "number",
    "spaceHardLimitGiB": "number",
    "spaceSoftLimitGiB": "number",
    "filesHardLimit": "number",
    "maxIops": "number",
    "maxMbps": "number",
    "expectedIops": "number",
    "peakIops": "number",
    "index": "number",
    "ruleIndex": "number",
    "encryption": "boolean",
    "continuouslyAvailable": "boolean",
    "surgeAsNormal": "boolean",
    # Epoch seconds, taken from the first message's timestamp.
    "createdAt": "number",
    "confirm": "boolean",
    "enabled": "boolean",
    "mandatory": "boolean",
    "generatePassphrase": "boolean",
    "acknowledgeIrreversible": "true",
    # Declared `true` rather than `boolean` for the same reason as the
    # acknowledgement above: these are flags a caller opts into. `overwrite: false`
    # reads as "do not overwrite", which is already the default, so allowing it
    # invites a call site to pass the value of a checkbox and believe it means
    # something. Omitting the property is the only way to say no.
    "overwrite": "true",
    "allSvms": "boolean",
    "isShared": "boolean",
    "force": "boolean",
}

# (action, parameter) -> the values ONTAP accepts, for parameters the handler passes
# straight through without checking.
#
# Keyed on the pair, not the name. A table keyed on the name alone asserted that
# `protocol` is nfs/cifs/s3 — true where the handler validates it, wrong for FPolicy
# events, which take ONTAP's cifs/nfsv3/nfsv4. That entry rejected a working screen.
#
# Everything else is derived from the handler's own `if x not in (...)` guard, which
# cannot disagree with the handler. Only add an entry here when the handler does not
# check and the set is documented by the API being called; cite it.
UNCHECKED_ENUMS: dict[tuple[str, str], str] = {
    # ONTAP REST POST /storage/volumes: snaplock.type, nas.security_style.
    ("createVolume", "snaplockType"): '"compliance" | "enterprise" | "non_snaplock"',
    ("createVolume", "securityStyle"): '"unix" | "ntfs" | "mixed"',
    # agent-chat: SYSTEM_PROMPTS / TOOLS_BY_MODE are keyed by exactly these three,
    # and an unknown mode falls back to "multi" silently rather than being refused.
    ("chat", "mode"): '"multi" | "kb" | "agent"',
}

# Parameters that carry a list rather than one value.
LISTS: dict[str, str] = {
    # The plural of a branded identifier keeps the brand: a list of volume names is
    # not a list of volume UUIDs any more than one name is one UUID.
    "volumeUuids": "VolumeUuid[]",
    "remoteAddresses": "string[]",
    "excludedPaths": "string[]",
    "excludedExtensions": "string[]",
    "includedExtensions": "string[]",
    "svms": "string[]",
    "events": "string[]",
    "fileOperations": "string[]",
    "accountIds": "string[]",
    "remoteVserverNames": "string[]",
    "applications": "string[]",
    "domains": "string[]",
    "servers": "string[]",
    "prepopulatePaths": "string[]",
    "roRule": "string[]",
    "rwRule": "string[]",
    "superuser": "string[]",
    "protocols": "string[]",
    "schedules": "string",  # JSON-encoded by the caller, so a string on the wire.
    # Structured payloads, spelled out because the element shape is what the caller
    # can get wrong. These four were previously declared `string` on the assumption
    # that the caller encoded them; it does not — `dispatch` serialises the whole
    # params object once, so a list arrives as a list and the handler reads it as
    # one (`json.dumps(messages)` on the way into DynamoDB, `for h in history` on
    # the way into Bedrock).
    "tools": "string[]",
    "history": "Array<{ role: string; content: string }>",
    "messages": "Array<{ role: string; content: string; timestamp: number }>",
    "agents": "Array<{ agentId: string; name: string; icon: string; role: string }>",
    "image": "{ data: string; mediaType: string }",
}

BRAND_DEFINITIONS = """\
/**
 * A string that a plain string is not assignable to.
 *
 * The parameter check next to this file compares the *names* a call site sends
 * against the names a handler reads. It cannot see that a name was passed where an
 * identifier was expected, because both are strings and both spell the key
 * correctly. Branding makes those two different types, so the compiler can.
 *
 * Produce one with the matching helper below. The helper is a deliberate act,
 * which is the point: somewhere a value crosses from "some string" to "the UUID of
 * a volume", and that crossing should be visible in the diff.
 */
type Brand<K, T extends string> = K & { readonly __brand: T };

/** The UUID of an FSx for ONTAP volume, as ONTAP reports it. Not a volume name. */
export type VolumeUuid = Brand<string, "VolumeUuid">;
/** The UUID of a snapshot. Not a snapshot name. */
export type SnapshotId = Brand<string, "SnapshotId">;
/** The UUID of a SnapMirror relationship. */
export type SnapmirrorUuid = Brand<string, "SnapmirrorUuid">;
/** The UUID of an SVM. Not an SVM name. */
export type SvmUuid = Brand<string, "SvmUuid">;
/** The UUID of a policy. Not a policy name. */
export type PolicyUuid = Brand<string, "PolicyUuid">;
/** The identifier of a qtree. */
export type QtreeId = Brand<string, "QtreeId">;
/** An absolute instant, ISO 8601. Not a number of days. */
export type IsoTimestamp = Brand<string, "IsoTimestamp">;
/** An ISO 8601 duration such as P30D. Not a number of days. */
export type IsoDuration = Brand<string, "IsoDuration">;

/**
 * Brand an identifier that came from ONTAP.
 *
 * Call this where a listing response is read, not at the call site that consumes
 * the value: branding at the point of use would let a name be branded as a UUID,
 * which is the mistake this is meant to prevent.
 */
export const asVolumeUuid = (uuid: string): VolumeUuid => uuid as VolumeUuid;
export const asSnapshotId = (id: string): SnapshotId => id as SnapshotId;
export const asSnapmirrorUuid = (uuid: string): SnapmirrorUuid => uuid as SnapmirrorUuid;
export const asSvmUuid = (uuid: string): SvmUuid => uuid as SvmUuid;
export const asPolicyUuid = (uuid: string): PolicyUuid => uuid as PolicyUuid;
export const asQtreeId = (id: string): QtreeId => id as QtreeId;

/** An instant, from a Date rather than from arithmetic on a string. */
export const asIsoTimestamp = (when: Date): IsoTimestamp => when.toISOString() as IsoTimestamp;

/** Days from now, as an instant. The conversion a lock has to make. */
export const daysFromNow = (days: number): IsoTimestamp => {
  const when = new Date();
  when.setDate(when.getDate() + days);
  return asIsoTimestamp(when);
};

/**
 * An ISO 8601 duration.
 *
 * Validated rather than asserted, because these arrive from free-text fields. A
 * malformed period was accepted silently before there was anywhere to check it.
 */
export const asIsoDuration = (period: string): IsoDuration | null =>
  /^P(?!$)(\\d+Y)?(\\d+M)?(\\d+W)?(\\d+D)?$/.test(period.trim())
    ? (period.trim() as IsoDuration)
    : null;

/** Days as an ISO duration, for a field that takes a period. */
export const daysAsIsoDuration = (days: number): IsoDuration => `P${days}D` as IsoDuration;
"""

HEADER = """\
/**
 * Parameter types for the portal's generic dispatch actions.
 *
 * GENERATED, then curated. The action names and parameter names come from the
 * Lambda handlers, via `scripts/portal_action_types.py`; the types applied to them
 * come from that script's BRANDS and SCALARS tables. Regenerate with:
 *
 *     python3 scripts/portal_action_types.py --emit > \\
 *       solutions/amplify-portal/src/lib/dispatchActions.ts
 *
 * `python3 scripts/portal_action_types.py --check` fails when a handler starts
 * requiring a parameter this file does not declare, or declares one no handler
 * reads. That check is what stops this file becoming a second, disagreeing
 * description of the backend.
 *
 * Why it exists: the dispatch endpoints take an untyped `params` blob, so a
 * component could send anything and the compiler had nothing to check it against.
 * A lock button shipped that had never worked, sending a snapshot name and a day
 * count where the action reads a UUID and an absolute instant. The name mismatch is
 * now caught by a script; the value mismatch needed types.
 */

"""


def _type_for(action: str, name: str, contract: ActionContract) -> str:
    """The TypeScript type for a parameter, most specific rule first.

    The handler's own accepted set wins over every table here: it is the thing being
    called, and it cannot be out of date with itself.
    """
    if name in BRANDS:
        return BRANDS[name]
    derived = contract.enums.get(name)
    if derived:
        return " | ".join(f'"{value}"' for value in derived)
    if (action, name) in UNCHECKED_ENUMS:
        return UNCHECKED_ENUMS[(action, name)]
    if name in SCALARS:
        return SCALARS[name]
    if name in LISTS:
        return LISTS[name]
    return "string"


def _required_keys(contract: ActionContract) -> set[str]:
    """Keys the handler refuses the request without, one alternative each."""
    return {next(iter(group)) for group in contract.groups if len(group) == 1}


def _optional_keys(contract: ActionContract) -> set[str]:
    """Keys the action's own branch reads that it does not insist on.

    `branch_read` rather than `read`: the wider set includes everything the Lambda
    reads anywhere, which would let every action accept every parameter and defeat
    the purpose.
    """
    alternatives: set[str] = set()
    for group in contract.groups:
        if len(group) > 1:
            alternatives |= group
    return (contract.branch_read | alternatives) - _required_keys(contract)


def _entry(action: str, contract: ActionContract) -> str:
    """One `action: { ... }` member."""
    required = sorted(_required_keys(contract))
    optional = sorted(_optional_keys(contract))
    if not required and not optional:
        return f"  /** No parameters. */\n  {action}: Record<string, never>;"

    fields = [f"    {name}: {_type_for(action, name, contract)};" for name in required]
    fields += [f"    {name}?: {_type_for(action, name, contract)};" for name in optional]
    body = "\n".join(fields)
    return f"  {action}: {{\n{body}\n  }};"


def handler_contract_sets() -> dict[str, dict[str, ActionContract]]:
    """Action contracts per handler directory, for the handlers with a map."""
    endpoints, problems = discover_endpoints()
    if problems:
        raise SystemExit("cannot read the endpoint wiring: " + "; ".join(problems))

    found: dict[str, dict[str, ActionContract]] = {}
    for endpoint in endpoints:
        if endpoint.handler_dir not in HANDLER_MAPS or endpoint.handler_dir in found:
            continue
        contracts = contracts_for(endpoint)
        if contracts is not None:
            found[endpoint.handler_dir] = contracts
    return found


def endpoint_to_handler() -> dict[str, str]:
    """Which handler directory each generic-dispatch endpoint reaches."""
    endpoints, problems = discover_endpoints()
    if problems:
        raise SystemExit("cannot read the endpoint wiring: " + "; ".join(problems))
    return {endpoint.name: endpoint.handler_dir for endpoint in endpoints}


def emit() -> str:
    """The whole TypeScript module."""
    by_handler = handler_contract_sets()
    routes = endpoint_to_handler()

    out = [HEADER, BRAND_DEFINITIONS, ""]

    for handler_dir, interface in HANDLER_MAPS.items():
        contracts = by_handler.get(handler_dir)
        if contracts is None:
            continue
        endpoints = sorted(name for name, directory in routes.items() if directory == handler_dir)
        out.append(f"/** Actions of functions/{handler_dir}, reached by {', '.join(f'`{e}`' for e in endpoints)}. */")
        out.append(f"export interface {interface} {{")
        for action in sorted(contracts):
            out.append(_entry(action, contracts[action]))
        out.append("}")
        out.append("")

    out.append("/**")
    out.append(" * Which action map each endpoint uses.")
    out.append(" *")
    out.append(" * A query endpoint and a mutation endpoint that share a Lambda share its")
    out.append(" * actions: the handler does not distinguish them, and pretending otherwise")
    out.append(" * would be a constraint this file invented rather than one it read.")
    out.append(" */")
    out.append("export type DispatchParams = {")
    for name, handler_dir in sorted(routes.items()):
        if handler_dir in by_handler:
            out.append(f"  {name}: {HANDLER_MAPS[handler_dir]};")
    out.append("};")
    out.append("")
    out.append("/** Every endpoint whose actions are constrained. */")
    out.append("export type DispatchEndpoint = keyof DispatchParams;")
    out.append("")
    out.append("/** The actions one endpoint accepts. */")
    out.append("export type ActionOf<E extends DispatchEndpoint> = keyof DispatchParams[E] & string;")
    out.append("")
    out.append("/** The parameters one action takes. */")
    out.append("export type ParamsOf<E extends DispatchEndpoint, A extends ActionOf<E>> = DispatchParams[E][A];")
    out.append("")
    return "\n".join(out)


def _declared(source: str) -> dict[str, dict[str, tuple[set[str], set[str]]]]:
    """Parse the committed module back into handler -> action -> (required, optional).

    Reading the file rather than trusting it is the only way `--check` can mean
    anything: a generated file that is never compared with its source is just a file.
    """
    interfaces = {value: key for key, value in HANDLER_MAPS.items()}
    found: dict[str, dict[str, tuple[set[str], set[str]]]] = {}

    for match in re.finditer(r"export interface (?P<name>[A-Za-z]+) \{(?P<body>.*?)\n\}", source, re.DOTALL):
        handler_dir = interfaces.get(match.group("name"))
        if handler_dir is None:
            continue
        actions: dict[str, tuple[set[str], set[str]]] = {}
        body = match.group("body")

        for entry in re.finditer(
            r"^  (?P<action>[A-Za-z][A-Za-z0-9_]*): (?:\{(?P<fields>.*?)^  \}|Record<string, never>);",
            body,
            re.DOTALL | re.MULTILINE,
        ):
            required: set[str] = set()
            optional: set[str] = set()
            for field_line in (entry.group("fields") or "").splitlines():
                field_match = re.match(r"\s*(?P<name>[A-Za-z][A-Za-z0-9_]*)(?P<opt>\??): ", field_line)
                if field_match:
                    (optional if field_match.group("opt") else required).add(field_match.group("name"))
            actions[entry.group("action")] = (required, optional)
        found[handler_dir] = actions
    return found


def check() -> int:
    """Compare the committed module against the handlers."""
    if not TARGET.exists():
        print(f"{TARGET.relative_to(PORTAL.parent.parent)} does not exist; run with --emit")
        return 1

    by_handler = handler_contract_sets()
    declared = _declared(TARGET.read_text())
    failures: list[str] = []

    for handler_dir, contracts in sorted(by_handler.items()):
        actions = declared.get(handler_dir)
        if actions is None:
            failures.append(f"{HANDLER_MAPS[handler_dir]} is missing from the module")
            continue

        for action, contract in sorted(contracts.items()):
            if action not in actions:
                failures.append(f"functions/{handler_dir} dispatches '{action}', which is not declared")
                continue
            required, optional = actions[action]
            handler_required = _required_keys(contract)
            handler_known = handler_required | _optional_keys(contract)

            missing = handler_required - required
            if missing:
                failures.append(
                    f"{handler_dir}.{action} refuses the request without {sorted(missing)}, "
                    "which the module does not declare as required"
                )
            unknown = (required | optional) - handler_known
            if unknown:
                failures.append(
                    f"{handler_dir}.{action} declares {sorted(unknown)}, which the handler does not read on that action"
                )

        for action in sorted(set(actions) - set(contracts)):
            failures.append(f"{handler_dir}.{action} is declared but the handler does not dispatch it")

    if failures:
        print(f"dispatch action types ({len(failures)}):")
        for failure in failures:
            print(f"  {failure}")
        print(f"\nRegenerate with: python3 scripts/portal_action_types.py --emit > {TARGET.relative_to(PORTAL)}")
        return 1

    total = sum(len(actions) for actions in declared.values())
    print(f"DISPATCH ACTION TYPES: PASS ({total} actions declared, matching the handlers)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--emit", action="store_true", help="print the TypeScript module")
    group.add_argument("--check", action="store_true", help="verify the committed module")
    args = parser.parse_args()

    if args.emit:
        print(emit(), end="")
        return 0
    return check()


if __name__ == "__main__":
    sys.exit(main())
