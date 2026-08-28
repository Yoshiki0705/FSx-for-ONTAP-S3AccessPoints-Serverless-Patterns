#!/usr/bin/env python3
"""Every portal endpoint that takes an object key from the client must be scoped.

Why this exists as a check rather than a note
---------------------------------------------
Eight handlers took a client-supplied object key while consulting neither the caller's
access point nor the caller's prefixes. None of them failed: they returned the right
answer about the wrong file. The listing endpoint had the boundary all along, so the
gap was invisible from the UI -- a caller could not see another team's file in a
listing, and could still name its key to the endpoints that read content.

Two of them had already been handed the mapping in `backend.ts` and ignored it, which
is the reason a review of the CDK configuration would not have found this. Wiring the
environment variable is not the same as reading it.

What is checked, for each Lambda under `functions/` that a resolver can reach:

1. If the handler reads an object key or prefix from the event, it must consult the
   shared boundary (`shared.portal_path_scope`).
2. If it consults the boundary, `backend.ts` must pass the matching environment
   variables to that function, or the boundary resolves to "unrestricted" at runtime
   and the check above passes while nothing is enforced.
3. The resolver that invokes it must forward the caller's Cognito groups, or the
   handler receives an empty list and the boundary again resolves to unrestricted.

The third is the one worth having most. A boundary that silently means "no restriction"
when its input is missing is the failure mode this repository has already shipped once.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PORTAL = REPO / "solutions" / "amplify-portal"
FUNCTIONS = PORTAL / "functions"
RESOLVERS = PORTAL / "amplify" / "data" / "resolvers"
BACKEND = PORTAL / "amplify" / "backend.ts"
SCHEMA = PORTAL / "amplify" / "data" / "resource.ts"

# Fields through which a client names an object. `fileKeys` is the batch form.
KEY_FIELDS = ("key", "prefix", "sourceKey", "destinationKey", "fileKeys", "trashKey")

# The field name alone is not enough to conclude anything. `event.get("key")` in the
# resource-management handler is the name of a portal setting being written to
# DynamoDB, and reporting it would be a false positive that trains the reader to
# ignore this check. A handler is in scope only when it also uses the value against
# object storage, so both conditions have to hold.
OBJECT_ACCESS_SYMBOLS = (
    "S3ApHelper",
    "list_objects_v2",
    "get_object",
    "put_object",
    "copy_object",
    "delete_object",
    "generate_presigned",
)

# Reading any of these means the handler consulted the boundary.
BOUNDARY_SYMBOLS = ("scope_for_caller", "reject_key", "allowed_prefixes", "key_is_visible")

# Handlers reached only by events or by another function, never by a signed-in caller
# naming a key. They have no groups to scope against, so requiring the boundary would
# be requiring something meaningless.
NOT_CLIENT_FACING = {
    "notification-bridge",  # EventBridge: FPolicy and Transfer Family events
    "job-status-updater",  # Step Functions callback
    "pii-auto-tagger",  # invoked by the processing workflow, not by a user
    "office-convert",  # invoked by the preview path with a key already checked
    "secure-viewer",  # serves a pre-authorised viewer session
}

# Kept separate from the set above, because the reason is different and conflating the
# two would hide it. These handlers do read a field named like an object key and do
# reach object storage, but not in the same action: `resource-management` is a dispatch
# of over a hundred admin actions, and its `event.get("key")` is the *name of a portal
# setting* being written to DynamoDB, while its object calls belong to the S3 Object
# Lock actions and take no caller-supplied key.
#
# The limitation is this check's, not the handler's: co-occurrence within a file cannot
# tell one action from another. A per-action reading would be the fix if a second entry
# ever appears here -- one entry is a quirk, two would be a pattern the check should
# understand rather than list.
KEY_FIELD_IS_NOT_AN_OBJECT_KEY = {
    "resource-management",
}


def handler_path(directory: Path) -> Path | None:
    """The handler source in a function directory.

    Args:
        directory: A directory under `functions/`.

    Returns:
        The path to `index.py` or `handler.py`, or None when neither is present.
    """
    for name in ("index.py", "handler.py"):
        candidate = directory / name
        if candidate.exists():
            return candidate
    return None


def declaration_for(backend: str, directory: str) -> str:
    """The `new lambda.Function(...)` call that packages this directory.

    Read as a span rather than by searching the whole file: `backend.ts` mentions the
    environment variables many times, so a file-wide search would report every
    function as wired the moment one of them was.

    Args:
        backend: The full text of `backend.ts`.
        directory: The function directory name, as it appears in `functionCode(...)`.

    Returns:
        The text of the enclosing declaration, or an empty string when the directory
        is not packaged by any function.
    """
    marker = re.search(r'code: functionCode\("functions/' + re.escape(directory) + r'"\)', backend)
    if not marker:
        return ""
    start = backend.rfind("new lambda.Function(", 0, marker.start())
    end = backend.find("  }\n);", marker.end())
    if end == -1:
        end = backend.find("});", marker.end())
    return backend[start:end]


def resolvers_invoking(directory: str, backend: str, schema: str) -> list[str]:
    """Resolver entry files whose data source is the Lambda packaging `directory`.

    Walks the same three hops the deployment does: directory to function variable in
    `backend.ts`, variable to data source name, data source to resolver entry in the
    schema. Following the chain rather than matching names by convention is what lets
    the check notice a resolver that was renamed but still wired.

    Args:
        directory: The function directory name.
        backend: The full text of `backend.ts`.
        schema: The full text of `data/resource.ts`.

    Returns:
        Resolver file names, sorted and de-duplicated. Empty when nothing invokes it.
    """
    variable = None
    for match in re.finditer(
        r"const (\w+) = new lambda\.Function\((?:.|\n)*?functionCode\(\"functions/([^\"]+)\"\)",
        backend,
    ):
        if match.group(2) == directory:
            variable = match.group(1)
    if not variable:
        return []
    sources = [
        name for name, fn in re.findall(r'addLambdaDataSource\(\s*"([^"]+)",\s*(\w+)', backend) if fn == variable
    ]
    entries = []
    for source in sources:
        entries += re.findall(
            r'dataSource:\s*"' + re.escape(source) + r'"\s*,\s*entry:\s*"\./resolvers/([^"]+)"',
            schema.replace("\n", " "),
        )
    return sorted(set(entries))


def main() -> int:
    """Check every client-reachable endpoint that names an object.

    Returns:
        0 when every such endpoint consults the boundary and is wired to receive the
        inputs the boundary needs, 1 otherwise.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit findings as JSON")
    args = parser.parse_args()

    backend = BACKEND.read_text(encoding="utf-8")
    schema = SCHEMA.read_text(encoding="utf-8")

    findings: list[dict[str, str]] = []
    checked = 0

    for directory in sorted(p for p in FUNCTIONS.iterdir() if p.is_dir()):
        name = directory.name
        if name in NOT_CLIENT_FACING or name in KEY_FIELD_IS_NOT_AN_OBJECT_KEY:
            continue
        source_file = handler_path(directory)
        if source_file is None:
            continue
        source = source_file.read_text(encoding="utf-8")

        takes_key = any(f'event.get("{field}"' in source for field in KEY_FIELDS)
        touches_objects = any(symbol in source for symbol in OBJECT_ACCESS_SYMBOLS)
        if not (takes_key and touches_objects):
            continue
        checked += 1

        has_boundary = any(symbol in source for symbol in BOUNDARY_SYMBOLS)
        if not has_boundary:
            findings.append(
                {
                    "function": name,
                    "problem": "takes an object key from the caller but never consults the boundary",
                    "fix": "call shared.portal_path_scope.scope_for_caller before reading the key",
                }
            )
            continue

        declaration = declaration_for(backend, name)
        if not declaration:
            findings.append(
                {
                    "function": name,
                    "problem": "no lambda.Function declaration found in backend.ts",
                    "fix": 'package it with functionCode("functions/<dir>") so this check can read its environment',
                }
            )
            continue
        if "GROUP_PATH_PREFIXES" not in declaration:
            findings.append(
                {
                    "function": name,
                    "problem": "consults the boundary but backend.ts does not pass GROUP_PATH_PREFIXES",
                    "fix": "add GROUP_PATH_PREFIXES to its environment; without it the boundary is empty, which means unrestricted",
                }
            )

        for entry in resolvers_invoking(name, backend, schema):
            resolver = RESOLVERS / entry
            if not resolver.exists():
                continue
            if "cognito:groups" not in resolver.read_text(encoding="utf-8"):
                findings.append(
                    {
                        "function": name,
                        "problem": f"resolver {entry} does not forward the caller's groups",
                        "fix": 'add groups: ctx.identity.claims["cognito:groups"] to the payload; an empty list means unrestricted',
                    }
                )

    if args.json:
        print(json.dumps({"checked": checked, "findings": findings}, indent=2))
    elif findings:
        print("PORTAL KEY BOUNDARY: FAIL")
        for finding in findings:
            print(f"  {finding['function']}: {finding['problem']}")
            print(f"    fix: {finding['fix']}")
    else:
        print(f"PORTAL KEY BOUNDARY: PASS ({checked} endpoint(s) taking a caller-supplied key)")

    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
