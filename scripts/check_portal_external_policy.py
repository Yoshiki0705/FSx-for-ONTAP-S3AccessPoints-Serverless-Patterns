#!/usr/bin/env python3
"""Every capability restricted for external portal callers actually asks.

Two capabilities are withheld from callers outside the organisation by default, and
both are withheld in the handler rather than in AppSync authorization -- they are
decisions about where data goes, not about who may call what:

  AI endpoints, because the call sends file content to a model and is billed per token.
  Share links, because a presigned URL is a bearer credential that outlives the request
  and is redeemable without AWS credentials.

The failure this guards against is an endpoint added later. Somebody adding a seventh
AI endpoint writes it by copying a neighbour, and a neighbour that predates the policy
has no check in it. The result reads as finished, returns correct answers, and hands an
outside member a model. Nothing fails.

So the check does not hold a list of endpoints. It finds them by what they do -- which
AWS client they construct, or whether they mint a presigned URL -- and then requires
that each one asks. A new endpoint is therefore in scope from the moment it is written,
which is the only arrangement that survives somebody who has not read this file.

Three hops per endpoint, because two of them can be satisfied while the policy is still
inert:

1. The handler must consult the shared decision.
2. `backend.ts` must pass the setting the decision reads.
3. A resolver must forward the caller's Cognito groups.

Hop 3 is the one that has actually shipped broken elsewhere in this portal: the check in
the handler is present and correct, no groups arrive, and `is_external([])` is False, so
every caller resolves to internal and the restriction silently does not exist.

Usage:
    python3 scripts/check_portal_external_policy.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_portal_key_boundary import (  # noqa: E402
    BACKEND,
    FUNCTIONS,
    RESOLVERS,
    SCHEMA,
    declaration_for,
    handler_path,
    resolvers_invoking,
)

# Constructing one of these clients is what makes an endpoint an AI endpoint. Matched on
# the boto3 client name rather than on the handler's own naming, so a function called
# something else is still in scope.
AI_CLIENTS = (
    "bedrock-runtime",
    "bedrock-agent-runtime",
    "textract",
    "comprehend",
    "rekognition",
)

# Minting one of these is how a handler produces a presigned URL.
SHARE_LINK_SYMBOLS = (
    "generate_presigned_get_url",
    "generate_presigned_url",
)

# What makes a presigned URL a share link rather than plumbing: the caller chooses how
# long it lives.
#
# The distinction is not "is it forwardable" -- every presigned URL is, since it needs no
# AWS credentials to redeem. It is whether the caller can ask for a lifetime long enough
# to be worth forwarding. Handlers that presign with a fixed server-side expiry are
# rendering something in the current session: a thumbnail, a converted page, a ZIP. A
# handler that takes the lifetime from the request is offering the caller a choice about
# exposure, and that choice is what the role setting governs.
#
# Measured against the request field rather than a list of endpoint names, so an endpoint
# added later is in scope by virtue of what it accepts.
CALLER_CONTROLLED_EXPIRY = (
    'event.get("expiresIn"',
    'params.get("expiresIn"',
)

# A resolver forwards the caller's identity in one of two spellings.
GROUP_FORWARDING_SYMBOLS = ("cognito:groups", "identity.groups")

AI_DECISION = ("ai_denial_reason",)
AI_SETTING = "EXTERNAL_AI_ENABLED"

# Either is acceptable, and which one is right depends on the endpoint. Refusing suits an
# endpoint that exists only to hand a link to somebody else -- a QR code, an upload link
# for an unauthenticated party. Shortening suits an endpoint that also serves the
# caller's own preview and download, where refusing would take away retrieving the file.
SHARE_DECISION = ("share_link_denial_reason", "share_link_expiry_ceiling")
SHARE_SETTING = "EXTERNAL_SHARE_LINKS_BY_ROLE"

# Handlers that use an AI client but are not reachable by a signed-in caller, so there
# is no caller whose scope could be consulted. Each entry needs a reason, because an
# entry added to silence the check is indistinguishable from one added because the
# reason holds.
NOT_CLIENT_FACING = {
    # Runs from an S3 event to tag newly written objects. No caller and no request.
    "pii-auto-tagger": "event-driven tagger, invoked by S3 notifications rather than a resolver",
}


def ai_clients_used(source: str) -> list[str]:
    """AI service clients this handler constructs.

    Args:
        source: The handler source.

    Returns:
        The client names found, sorted. Empty when the handler reaches no AI service.
    """
    found = set()
    for client in AI_CLIENTS:
        # Matches boto3.client("comprehend") and the resource/config variants, while
        # not matching the word appearing in a comment or a dictionary key.
        if re.search(r'boto3\.(?:client|resource)\(\s*"' + re.escape(client) + r'"', source):
            found.add(client)
    return sorted(found)


def mints_share_links(source: str) -> bool:
    """Whether this handler lets the caller mint a link worth passing on.

    Both halves are required. Presigning alone is not the capability -- the portal
    presigns to render thumbnails and to serve a converted page, with a fixed lifetime
    the caller never sees. The capability appears when the caller also chooses how long
    the URL lives.

    Args:
        source: The handler source.

    Returns:
        True when the handler presigns with a caller-supplied lifetime.
    """
    return any(symbol in source for symbol in SHARE_LINK_SYMBOLS) and any(
        symbol in source for symbol in CALLER_CONTROLLED_EXPIRY
    )


def check_capability(
    *,
    name: str,
    source: str,
    declaration: str,
    resolvers: list[str],
    decision: tuple[str, ...],
    setting: str,
    capability: str,
) -> list[dict[str, str]]:
    """The three hops for one capability on one endpoint.

    Args:
        name: The function directory name.
        source: The handler source.
        declaration: The `new lambda.Function(...)` text packaging this directory.
        resolvers: Resolver entry files invoking it.
        decision: The shared functions, any one of which satisfies the check.
        setting: The environment variable the decision reads.
        capability: Human-readable capability name, for the message.

    Returns:
        One finding per broken hop. Empty when the endpoint is guarded end to end.
    """
    findings: list[dict[str, str]] = []
    if not any(symbol in source for symbol in decision):
        findings.append(
            {
                "function": name,
                "problem": (
                    f"{capability} endpoint consults none of "
                    f"{', '.join(f'{s}()' for s in decision)}, so a caller holding the "
                    "external scope is served"
                ),
            }
        )
    if f"{setting}:" not in declaration:
        findings.append(
            {
                "function": name,
                "problem": (
                    f"backend.ts does not pass {setting} to this function, so the handler reads the unset default"
                ),
            }
        )
    forwards = any(
        (RESOLVERS / entry).exists()
        and any(symbol in (RESOLVERS / entry).read_text(encoding="utf-8") for symbol in GROUP_FORWARDING_SYMBOLS)
        for entry in resolvers
    )
    if resolvers and not forwards:
        findings.append(
            {
                "function": name,
                "problem": (
                    "no resolver forwards the caller's groups, so every caller looks "
                    "internal and the restriction never applies"
                ),
            }
        )
    return findings


def main() -> int:
    """Check every AI and share-link endpoint against the external-scope policy.

    Returns:
        0 when every endpoint asks, 1 otherwise.
    """
    backend = BACKEND.read_text(encoding="utf-8")
    schema = SCHEMA.read_text(encoding="utf-8")

    findings: list[dict[str, str]] = []
    guarded: list[str] = []
    skipped: list[str] = []

    for directory in sorted(p for p in FUNCTIONS.iterdir() if p.is_dir()):
        handler = handler_path(directory)
        if handler is None:
            continue
        name = directory.name
        source = handler.read_text(encoding="utf-8")

        capabilities: list[tuple[str, tuple[str, ...], str]] = []
        if ai_clients_used(source):
            capabilities.append(("AI", AI_DECISION, AI_SETTING))
        if mints_share_links(source):
            capabilities.append(("share link", SHARE_DECISION, SHARE_SETTING))
        if not capabilities:
            continue

        if name in NOT_CLIENT_FACING:
            skipped.append(f"{name} ({NOT_CLIENT_FACING[name]})")
            continue

        resolvers = resolvers_invoking(name, backend, schema)
        if not resolvers:
            findings.append(
                {
                    "function": name,
                    "problem": (
                        "uses a restricted capability but no resolver invokes it. Either "
                        "wire it, or add it to NOT_CLIENT_FACING with the reason"
                    ),
                }
            )
            continue

        declaration = declaration_for(backend, name)
        for capability, decision, setting in capabilities:
            findings += check_capability(
                name=name,
                source=source,
                declaration=declaration,
                resolvers=resolvers,
                decision=decision,
                setting=setting,
                capability=capability,
            )
            guarded.append(f"{name} ({capability})")

    if findings:
        print("PORTAL EXTERNAL POLICY: FAIL")
        for finding in findings:
            print(f"  {finding['function']}: {finding['problem']}")
        print(
            "\nExternal callers hold no Windows or UNIX account on the file system. "
            "A capability that does not consult the shared decision is granted to them."
        )
        return 1

    print(f"PORTAL EXTERNAL POLICY: PASS ({len(set(guarded))} capabilities)")
    for entry in skipped:
        print(f"  skipped: {entry}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
