"""Tests for the check that every key-taking portal endpoint is scoped.

A check that has only ever passed is not yet a check. These build handler trees on
disk with each defect in turn -- boundary absent, environment variable absent, groups
not forwarded -- and assert the check reports it. The last of those is the one the real
codebase shipped: the boundary was present in code and resolved to "unrestricted" at
runtime because the resolver never sent the groups.

The real repository is asserted to pass at the end, so the check stays honest about the
tree it is actually run against.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
CHECK = REPO / "scripts" / "check_portal_key_boundary.py"

BOUNDED_HANDLER = """
from shared.portal_path_scope import scope_for_caller
from shared.s3ap_helper import S3ApHelper

def handler(event, context):
    key = event.get("key", "")
    alias, refused = scope_for_caller([], group_ap_mapping={}, group_path_prefixes={},
                                      default_alias="a", key=key)
    if refused:
        return refused
    return {"bytes": S3ApHelper(alias).get_object_bytes(key)}
"""

UNBOUNDED_HANDLER = """
import boto3
s3 = boto3.client("s3")

def handler(event, context):
    key = event.get("key", "")
    return {"body": s3.get_object(Bucket="fixed-alias", Key=key)}
"""

RESOLVER_WITH_GROUPS = """
export function request(ctx) {
  return { operation: "Invoke", payload: {
    key: ctx.arguments.key,
    groups: ctx.identity.claims ? ctx.identity.claims["cognito:groups"] || [] : [],
  } };
}
"""

RESOLVER_WITHOUT_GROUPS = """
export function request(ctx) {
  return { operation: "Invoke", payload: { key: ctx.arguments.key } };
}
"""


def backend_ts(*, with_prefixes: bool) -> str:
    """A minimal `backend.ts` declaring one function and its data source.

    Args:
        with_prefixes: Whether the function's environment carries
            `GROUP_PATH_PREFIXES`. Omitting it is the defect where the boundary is
            present in code and empty at runtime.

    Returns:
        The file contents.
    """
    env = "      S3_AP_ALIAS: config.s3ApAlias,\n"
    if with_prefixes:
        env += "      GROUP_PATH_PREFIXES: JSON.stringify(groupPathPrefixes),\n"
    return (
        'const widgetFunction = new lambda.Function(dataStack, "WidgetFunction", {\n'
        '    code: functionCode("functions/widget"),\n'
        "    environment: {\n" + env + "    },\n"
        "  }\n);\n\n"
        'api.addLambdaDataSource("WidgetLambdaDataSource", widgetFunction);\n'
    )


SCHEMA_TS = """
  widgetQuery: a.query().handler(a.handler.custom({
    dataSource: "WidgetLambdaDataSource", entry: "./resolvers/widget.js" })),
"""


def build_tree(root: Path, *, handler: str, with_prefixes: bool, resolver: str) -> None:
    """Lay out the portal paths the check reads, and nothing else.

    The check resolves its own location to find the repository root, so a copy of it
    is placed inside the tree rather than run from the real `scripts/` directory.

    Args:
        root: Temporary directory standing in for the repository root.
        handler: Contents of the function's `index.py`.
        with_prefixes: Passed through to `backend_ts`.
        resolver: Contents of the resolver that invokes the function.
    """
    portal = root / "solutions" / "amplify-portal"
    (portal / "functions" / "widget").mkdir(parents=True)
    (portal / "functions" / "widget" / "index.py").write_text(handler)
    resolvers = portal / "amplify" / "data" / "resolvers"
    resolvers.mkdir(parents=True)
    (resolvers / "widget.js").write_text(resolver)
    (portal / "amplify" / "backend.ts").write_text(backend_ts(with_prefixes=with_prefixes))
    (portal / "amplify" / "data" / "resource.ts").write_text(SCHEMA_TS)
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    (scripts / CHECK.name).write_text(CHECK.read_text(encoding="utf-8"), encoding="utf-8")


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


def test_a_scoped_endpoint_passes(tmp_path: Path) -> None:
    build_tree(tmp_path, handler=BOUNDED_HANDLER, with_prefixes=True, resolver=RESOLVER_WITH_GROUPS)
    result = run(tmp_path)
    assert result.returncode == 0, result.stdout
    assert "PASS" in result.stdout


def test_a_handler_that_never_consults_the_boundary_fails(tmp_path: Path) -> None:
    build_tree(tmp_path, handler=UNBOUNDED_HANDLER, with_prefixes=True, resolver=RESOLVER_WITH_GROUPS)
    result = run(tmp_path)
    assert result.returncode == 1
    assert "never consults the boundary" in result.stdout


def test_a_missing_environment_variable_fails(tmp_path: Path) -> None:
    """The boundary is in the code and empty at runtime, which means unrestricted."""
    build_tree(tmp_path, handler=BOUNDED_HANDLER, with_prefixes=False, resolver=RESOLVER_WITH_GROUPS)
    result = run(tmp_path)
    assert result.returncode == 1
    assert "GROUP_PATH_PREFIXES" in result.stdout


def test_a_resolver_that_withholds_the_groups_fails(tmp_path: Path) -> None:
    """The defect the repository actually shipped: scoped code, no scope input."""
    build_tree(tmp_path, handler=BOUNDED_HANDLER, with_prefixes=True, resolver=RESOLVER_WITHOUT_GROUPS)
    result = run(tmp_path)
    assert result.returncode == 1
    assert "does not forward the caller's groups" in result.stdout


def test_a_key_field_that_is_not_an_object_key_is_not_reported(tmp_path: Path) -> None:
    """`event.get("key")` naming a settings row must not be mistaken for an object."""
    settings_handler = (
        'import boto3\ndef handler(event, context):\n    key = event.get("key", "")\n    return {"wrote": key}\n'
    )
    build_tree(tmp_path, handler=settings_handler, with_prefixes=False, resolver=RESOLVER_WITHOUT_GROUPS)
    result = run(tmp_path)
    assert result.returncode == 0, result.stdout
    assert "0 endpoint" in result.stdout


def test_the_real_repository_passes() -> None:
    """Keeps the check honest about the tree it is actually run against."""
    result = subprocess.run([sys.executable, str(CHECK), "--json"], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout
    assert '"findings": []' in result.stdout
