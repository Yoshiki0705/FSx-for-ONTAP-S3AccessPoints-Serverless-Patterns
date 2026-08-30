"""Tests for the check that external-scope restrictions are actually reachable.

A check that has only ever passed is not yet a check. Each case here builds a handler
tree with one defect and asserts the check names it: the decision missing from the
handler, the setting missing from `backend.ts`, the groups missing from the resolver.

The third is the one that matters most and the one that shipped elsewhere in this
portal. The handler consults the decision, the decision reads its setting, and no groups
arrive -- so every caller looks internal, every restriction evaluates to "allowed", and
nothing anywhere fails.

Two cases assert the check does *not* fire, which is the other half of being a check:
presigning with a fixed lifetime is rendering, not sharing, and treating it as sharing
would have forced a meaningless decision into four handlers.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
CHECK = REPO / "scripts" / "check_portal_external_policy.py"
# The check walks the same directory-to-resolver chain as the key-boundary check and
# imports it rather than repeating it, so the tree needs both files.
DEPENDENCY = REPO / "scripts" / "check_portal_key_boundary.py"

GUARDED_AI_HANDLER = """
import boto3
from shared.portal_external_policy import ai_denial_reason
comprehend = boto3.client("comprehend")
EXTERNAL_AI_ENABLED = False
def handler(event, context):
    groups = event.get("groups", [])
    denied = ai_denial_reason(groups, ai_enabled=EXTERNAL_AI_ENABLED)
    if denied:
        return {"error": denied}
    return {"results": []}
"""

UNGUARDED_AI_HANDLER = """
import boto3
comprehend = boto3.client("comprehend")
def handler(event, context):
    return {"results": comprehend.detect_entities(Text=event.get("text", ""))}
"""

GUARDED_SHARE_HANDLER = """
from shared.portal_external_policy import share_link_expiry_ceiling
from shared.s3ap_helper import S3ApHelper
EXTERNAL_SHARE_LINKS_BY_ROLE = {}
def handler(event, context):
    groups = event.get("groups", [])
    expires_in = event.get("expiresIn", 300)
    ceiling = share_link_expiry_ceiling(groups, share_links_by_role=EXTERNAL_SHARE_LINKS_BY_ROLE)
    if ceiling is not None and expires_in > ceiling:
        expires_in = ceiling
    return {"url": S3ApHelper("a").generate_presigned_get_url(event["key"], expires_in)}
"""

UNGUARDED_SHARE_HANDLER = """
from shared.s3ap_helper import S3ApHelper
def handler(event, context):
    expires_in = event.get("expiresIn", 300)
    return {"url": S3ApHelper("a").generate_presigned_get_url(event["key"], expires_in)}
"""

# Presigns, but with a lifetime the caller never chooses. This is a thumbnail or a
# converted page being rendered in the current session, not a link being handed out.
FIXED_EXPIRY_HANDLER = """
from shared.s3ap_helper import S3ApHelper
URL_TTL_SECONDS = 60
def handler(event, context):
    return {"url": S3ApHelper("a").generate_presigned_get_url(event["key"], URL_TTL_SECONDS)}
"""

RESOLVER_WITH_GROUPS = """
export function request(ctx) {
  return { operation: "Invoke", payload: {
    key: ctx.arguments.key,
    groups: ctx.identity.claims ? ctx.identity.claims["cognito:groups"] || [] : [],
  } };
}
"""

# The other spelling in use. Accepted, because refusing it would report a wired
# endpoint as unwired.
RESOLVER_WITH_IDENTITY_GROUPS = """
export function request(ctx) {
  const groups = (ctx.identity.groups || []);
  return { operation: "Invoke", payload: { userGroups: groups } };
}
"""

RESOLVER_WITHOUT_GROUPS = """
export function request(ctx) {
  return { operation: "Invoke", payload: { key: ctx.arguments.key } };
}
"""

SCHEMA_TS = """
  widgetQuery: a.query().handler(a.handler.custom({
    dataSource: "WidgetLambdaDataSource", entry: "./resolvers/widget.js" })),
"""


def backend_ts(*, settings: tuple[str, ...]) -> str:
    """A minimal `backend.ts` declaring one function and its data source.

    Args:
        settings: Environment variable names to include. Omitting the one the handler
            reads is the defect where the restriction is inert at runtime.

    Returns:
        The file contents.
    """
    env = "      S3_AP_ALIAS: config.s3ApAlias,\n"
    env += "      GROUP_PATH_PREFIXES: JSON.stringify(groupPathPrefixes),\n"
    for name in settings:
        env += f"      {name}: JSON.stringify(x),\n"
    return (
        'const widgetFunction = new lambda.Function(dataStack, "WidgetFunction", {\n'
        '    code: functionCode("functions/widget"),\n'
        "    environment: {\n" + env + "    },\n"
        "  }\n);\n\n"
        'api.addLambdaDataSource("WidgetLambdaDataSource", widgetFunction);\n'
    )


def build_tree(
    root: Path,
    *,
    handler: str,
    settings: tuple[str, ...],
    resolver: str | None = RESOLVER_WITH_GROUPS,
) -> None:
    """Lay out the portal paths the check reads, and nothing else.

    Args:
        root: Temporary directory standing in for the repository root.
        handler: Contents of the function's `index.py`.
        settings: Passed through to `backend_ts`.
        resolver: Contents of the resolver, or None to wire no resolver at all.
    """
    portal = root / "solutions" / "amplify-portal"
    (portal / "functions" / "widget").mkdir(parents=True)
    (portal / "functions" / "widget" / "index.py").write_text(handler)
    resolvers = portal / "amplify" / "data" / "resolvers"
    resolvers.mkdir(parents=True)
    if resolver is not None:
        (resolvers / "widget.js").write_text(resolver)
    (portal / "amplify" / "backend.ts").write_text(backend_ts(settings=settings))
    (portal / "amplify" / "data" / "resource.ts").write_text(SCHEMA_TS if resolver is not None else "\n")
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    for script in (CHECK, DEPENDENCY):
        (scripts / script.name).write_text(script.read_text(encoding="utf-8"), encoding="utf-8")


def run(root: Path) -> subprocess.CompletedProcess[str]:
    """Run the copied check against a built tree.

    Args:
        root: The temporary repository root created by `build_tree`.

    Returns:
        The completed process, with stdout captured.
    """
    return subprocess.run(
        [sys.executable, str(root / "scripts" / CHECK.name)],
        capture_output=True,
        text=True,
    )


def test_a_guarded_ai_endpoint_passes(tmp_path: Path) -> None:
    build_tree(tmp_path, handler=GUARDED_AI_HANDLER, settings=("EXTERNAL_AI_ENABLED",))
    result = run(tmp_path)
    assert result.returncode == 0, result.stdout
    assert "PASS" in result.stdout


def test_an_ai_endpoint_without_the_decision_fails(tmp_path: Path) -> None:
    build_tree(tmp_path, handler=UNGUARDED_AI_HANDLER, settings=("EXTERNAL_AI_ENABLED",))
    result = run(tmp_path)
    assert result.returncode == 1
    assert "ai_denial_reason" in result.stdout


def test_an_ai_endpoint_without_the_setting_fails(tmp_path: Path) -> None:
    """The decision is present and reads a variable nothing sets."""
    build_tree(tmp_path, handler=GUARDED_AI_HANDLER, settings=())
    result = run(tmp_path)
    assert result.returncode == 1
    assert "EXTERNAL_AI_ENABLED" in result.stdout


def test_an_endpoint_whose_resolver_drops_the_groups_fails(tmp_path: Path) -> None:
    """The defect that ships looking finished.

    Everything is in place except the input, and with no groups every caller resolves to
    internal, so the restriction is absent without any error to notice it by.
    """
    build_tree(
        tmp_path,
        handler=GUARDED_AI_HANDLER,
        settings=("EXTERNAL_AI_ENABLED",),
        resolver=RESOLVER_WITHOUT_GROUPS,
    )
    result = run(tmp_path)
    assert result.returncode == 1
    assert "forwards the caller's groups" in result.stdout


def test_the_identity_groups_spelling_is_accepted(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        handler=GUARDED_AI_HANDLER,
        settings=("EXTERNAL_AI_ENABLED",),
        resolver=RESOLVER_WITH_IDENTITY_GROUPS,
    )
    result = run(tmp_path)
    assert result.returncode == 0, result.stdout


def test_a_guarded_share_link_endpoint_passes(tmp_path: Path) -> None:
    build_tree(tmp_path, handler=GUARDED_SHARE_HANDLER, settings=("EXTERNAL_SHARE_LINKS_BY_ROLE",))
    result = run(tmp_path)
    assert result.returncode == 0, result.stdout


def test_a_share_link_endpoint_without_the_decision_fails(tmp_path: Path) -> None:
    build_tree(tmp_path, handler=UNGUARDED_SHARE_HANDLER, settings=("EXTERNAL_SHARE_LINKS_BY_ROLE",))
    result = run(tmp_path)
    assert result.returncode == 1
    assert "share link" in result.stdout


def test_a_fixed_expiry_presign_is_not_treated_as_sharing(tmp_path: Path) -> None:
    """Rendering a thumbnail is not offering a link.

    Without this distinction the check would demand a decision in four handlers where
    the caller has no choice to govern, and the decision would be noise -- which is how
    a check stops being read.
    """
    build_tree(tmp_path, handler=FIXED_EXPIRY_HANDLER, settings=())
    result = run(tmp_path)
    assert result.returncode == 0, result.stdout


def test_a_restricted_capability_with_no_resolver_fails(tmp_path: Path) -> None:
    """Unreachable is not the same as safe, and the check cannot tell them apart.

    An AI handler nothing invokes is either wiring that was forgotten or a function
    driven by an event, and only a person knows which. Failing asks.
    """
    build_tree(
        tmp_path,
        handler=GUARDED_AI_HANDLER,
        settings=("EXTERNAL_AI_ENABLED",),
        resolver=None,
    )
    result = run(tmp_path)
    assert result.returncode == 1
    assert "NOT_CLIENT_FACING" in result.stdout


def test_the_real_repository_passes() -> None:
    """Keeps the check honest about the tree it is actually run against."""
    result = subprocess.run([sys.executable, str(CHECK)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout
