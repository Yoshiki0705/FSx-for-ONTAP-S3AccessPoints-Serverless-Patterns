#!/usr/bin/env python3
"""Check that a deployed portal sandbox matches the config and outputs on disk.

Three failures cost a demo session on 2026-08-28, and none of them showed up as
an error at deploy time:

1. ``amplify_outputs.json`` named a Cognito user pool belonging to a *different*
   sandbox. The portal loaded, the sign-in form rendered, and the account handed
   to the reviewer did not exist in the pool the browser was talking to.

2. The deployed ONTAP-facing Lambda functions had no ``VpcConfig`` while
   ``portal-config.ts`` declared a ``vpcId``. Every ONTAP call ran to the 60 s
   timeout, which the UI shows as "読み込み中..." forever rather than as an error.

3. A second sandbox in the same VPC failed to create its DynamoDB gateway
   endpoint, because a route table holds one route per prefix list and an earlier
   stack already owned that route.

Each check reads deployed state and compares it against the files, rather than
asserting that a command exited zero. Run before handing a URL to anyone:

    make portal-preflight

Exit codes: 0 all checks pass, 1 at least one check failed, 2 could not run.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PORTAL_DIR = Path(__file__).resolve().parent.parent / "solutions" / "amplify-portal"
OUTPUTS_PATH = PORTAL_DIR / "amplify_outputs.json"
CONFIG_PATH = PORTAL_DIR / "amplify" / "portal-config.ts"

# Function names in the portal that reach ONTAP over the management LIF. A
# private address is only reachable from inside the VPC, so these are the ones
# whose missing VpcConfig turns into a silent timeout.
ONTAP_FUNCTION_HINTS = ("ResourceMgmt", "Protection", "ArpResponse", "AuditQuery")

OK = "ok"
FAIL = "fail"
SKIP = "skip"


@dataclass
class Result:
    """One check, its verdict, and what to do about it."""

    name: str
    status: str
    detail: str
    remedy: str = ""


def aws(*args: str) -> str:
    """Run an AWS CLI command and return stdout, or raise RuntimeError."""
    proc = subprocess.run(["aws", *args], capture_output=True, text=True, check=False, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"aws {' '.join(args)} failed")
    return proc.stdout.strip()


def read_config_text() -> str:
    """Return portal-config.ts source, or an empty string when absent."""
    return CONFIG_PATH.read_text(encoding="utf-8") if CONFIG_PATH.exists() else ""


def config_default(source: str, key: str) -> str | None:
    """Extract the literal default of a scalar config key.

    The config reads environment variables with a literal fallback, e.g.
    ``vpcId: (process.env.X || "vpc-abc").trim()``. Only the literal is read
    here; an override in the environment is reported separately by the caller.
    """
    match = re.search(rf'^\s*{re.escape(key)}:.*?"([^"]*)"', source, re.MULTILINE)
    return match.group(1) if match else None


def config_bool(source: str, key: str) -> bool | None:
    """Extract a boolean config default, whether literal or env-derived.

    ``!== "0"`` defaults to true, ``=== "1"`` defaults to false, and a bare
    ``true``/``false`` is itself.
    """
    match = re.search(rf"^\s*{re.escape(key)}:\s*(.+?),\s*$", source, re.MULTILINE)
    if not match:
        return None
    expr = match.group(1)
    if '!== "0"' in expr or expr.strip() == "true":
        return True
    if '=== "1"' in expr or expr.strip() == "false":
        return False
    return None


def load_outputs() -> dict:
    """Return parsed amplify_outputs.json, or raise RuntimeError."""
    if not OUTPUTS_PATH.exists():
        raise RuntimeError(f"{OUTPUTS_PATH} not found. Run `npx ampx sandbox` to generate it.")
    return json.loads(OUTPUTS_PATH.read_text(encoding="utf-8"))


def owning_stack(pool_id: str, region: str) -> str:
    """Return the CloudFormation stack name that owns a user pool.

    Asking CloudFormation which stack holds the physical resource is what makes
    this check trustworthy: it names the sandbox the browser will actually talk
    to, rather than the one whose deploy log is on screen.
    """
    raw = aws(
        "cloudformation",
        "describe-stack-resources",
        "--region",
        region,
        "--physical-resource-id",
        pool_id,
        "--query",
        "StackResources[0].StackName",
        "--output",
        "text",
    )
    return raw


def sandbox_identifier(stack_name: str) -> str:
    """Pull the sandbox identifier out of an Amplify stack name."""
    match = re.search(r"-([^-]+)-sandbox-", stack_name)
    return match.group(1) if match else "(not a sandbox stack)"


def check_outputs_pool(region_hint: str) -> tuple[Result, str | None]:
    """Confirm the outputs file names a pool that exists, and say whose it is."""
    try:
        outputs = load_outputs()
    except (RuntimeError, json.JSONDecodeError) as exc:
        return Result("outputs file", FAIL, str(exc)), None

    auth = outputs.get("auth") or {}
    pool_id = auth.get("user_pool_id")
    region = auth.get("aws_region") or region_hint
    if not pool_id:
        return Result("outputs file", FAIL, "auth.user_pool_id missing"), None

    try:
        pool_name = aws(
            "cognito-idp",
            "describe-user-pool",
            "--region",
            region,
            "--user-pool-id",
            pool_id,
            "--query",
            "UserPool.Name",
            "--output",
            "text",
        )
    except RuntimeError as exc:
        return (
            Result(
                "outputs file",
                FAIL,
                f"{pool_id} does not resolve: {exc}",
                "The outputs file is stale. Redeploy the sandbox it belongs to.",
            ),
            None,
        )

    try:
        stack = owning_stack(pool_id, region)
    except RuntimeError as exc:
        return (
            Result("outputs file", FAIL, f"cannot resolve owner of {pool_id}: {exc}"),
            None,
        )

    return (
        Result(
            "outputs file",
            OK,
            f"pool {pool_id} ({pool_name}) belongs to sandbox '{sandbox_identifier(stack)}'",
            "Accounts must be created in this pool. A user in any other pool "
            "cannot sign in, and the form reports only 'incorrect username or "
            "password'.",
        ),
        stack,
    )


def stack_family(stack: str, region: str) -> list[str]:
    """Return the root stack and every nested stack under it.

    A Lambda's generated name cannot say which sandbox it belongs to:
    CloudFormation truncates the stack prefix, so three sandboxes produce three
    functions all called ``amplify-fsxns3apamplifypo-ResourceMgmtFunction962E-*``
    and the identifier is gone. Walking the stack tree is what attributes a
    function to a sandbox.
    """
    root = aws(
        "cloudformation",
        "describe-stacks",
        "--region",
        region,
        "--stack-name",
        stack,
        "--query",
        "Stacks[0].RootId",
        "--output",
        "text",
    )
    if root in ("", "None"):
        root_name = stack
    else:
        root_name = root.split("/")[1] if "/" in root else root

    raw = aws(
        "cloudformation",
        "list-stacks",
        "--region",
        region,
        "--stack-status-filter",
        "CREATE_COMPLETE",
        "UPDATE_COMPLETE",
        "UPDATE_ROLLBACK_COMPLETE",
        "UPDATE_FAILED",
        "--query",
        "StackSummaries[].[StackName,RootId]",
        "--output",
        "json",
    )
    family = [root_name]
    for name, root_id in json.loads(raw):
        if root_id and root_name in root_id and name != root_name:
            family.append(name)
    return family


def ontap_functions(stack: str, region: str) -> list[str]:
    """Return names of ONTAP-facing Lambda functions in a stack family."""
    names: list[str] = []
    for member in stack_family(stack, region):
        raw = aws(
            "cloudformation",
            "list-stack-resources",
            "--region",
            region,
            "--stack-name",
            member,
            "--query",
            "StackResourceSummaries[?ResourceType=='AWS::Lambda::Function'].[LogicalResourceId,PhysicalResourceId]",
            "--output",
            "json",
        )
        for logical, physical in json.loads(raw):
            if any(hint.lower() in logical.lower() for hint in ONTAP_FUNCTION_HINTS):
                names.append(physical)
    return names


def check_lambda_vpc(stack: str | None, region: str, config_src: str) -> list[Result]:
    """Confirm ONTAP-facing functions in the deployed stack are in the VPC."""
    declared_vpc = config_default(config_src, "vpcId")
    if not declared_vpc:
        return [Result("VPC wiring", SKIP, "portal-config.ts declares no vpcId")]
    if not stack:
        return [Result("VPC wiring", SKIP, "owning stack unknown")]

    try:
        functions = ontap_functions(stack, region)
    except RuntimeError as exc:
        return [Result("VPC wiring", FAIL, f"cannot resolve functions: {exc}")]

    if not functions:
        return [
            Result(
                "VPC wiring",
                FAIL,
                "no ONTAP-facing function found in this stack family",
                "The deployed stack does not match this checkout, or the "
                "logical IDs changed and ONTAP_FUNCTION_HINTS needs updating.",
            )
        ]

    results: list[Result] = []
    for name in functions:
        try:
            raw = aws(
                "lambda",
                "get-function-configuration",
                "--region",
                region,
                "--function-name",
                name,
                "--query",
                "VpcConfig.SubnetIds",
                "--output",
                "json",
            )
        except RuntimeError as exc:
            results.append(Result("VPC wiring", FAIL, f"{name}: {exc}"))
            continue
        subnets = json.loads(raw or "null") or []
        short = name.split("-")[-2] if name.count("-") >= 2 else name
        if subnets:
            results.append(Result("VPC wiring", OK, f"{short}: {len(subnets)} subnet(s)"))
        else:
            results.append(
                Result(
                    "VPC wiring",
                    FAIL,
                    f"{short}: no VpcConfig, so the ONTAP management LIF is unreachable",
                    "Every ONTAP call runs to the function timeout, which the "
                    "UI shows as a panel stuck on loading rather than as an "
                    "error. Redeploy the sandbox so the VPC config applies.",
                )
            )
    return results


def check_gateway_endpoint(region: str, config_src: str) -> Result:
    """Compare the gateway-endpoint claim in config against the route tables."""
    claims_exists = config_bool(config_src, "dynamoDbGatewayEndpointExists")
    if claims_exists is None:
        return Result(
            "DynamoDB route",
            SKIP,
            "dynamoDbGatewayEndpointExists not readable from portal-config.ts",
        )

    # Line-scoped on purpose. A dot-matching-newline search here reached into the
    # comment above the assignment, which quotes the very error this check
    # reports, and used that prose as a route table ID.
    rtb = config_default(config_src, "vpcRouteTableIds")
    if not rtb or not rtb.startswith("rtb-"):
        return Result("DynamoDB route", SKIP, "no route table configured")

    try:
        raw = aws(
            "ec2",
            "describe-route-tables",
            "--region",
            region,
            "--route-table-ids",
            rtb,
            "--query",
            "RouteTables[0].Routes[?DestinationPrefixListId!=null].DestinationPrefixListId",
            "--output",
            "json",
        )
    except RuntimeError as exc:
        return Result("DynamoDB route", FAIL, f"cannot read {rtb}: {exc}")

    present = bool(json.loads(raw or "[]"))
    if present == claims_exists:
        state = "already routed" if present else "not routed yet"
        return Result(
            "DynamoDB route",
            OK,
            f"{rtb} {state}, matching dynamoDbGatewayEndpointExists={str(claims_exists).lower()}",
        )
    if present:
        return Result(
            "DynamoDB route",
            FAIL,
            f"{rtb} already carries a prefix-list route, but dynamoDbGatewayEndpointExists is false",
            "The data stack will fail to create its gateway endpoint and roll "
            "back after the rest of it succeeds. Set "
            "AMPLIFY_PORTAL_DDB_GW_ENDPOINT_EXISTS=1 or the config default.",
        )
    return Result(
        "DynamoDB route",
        FAIL,
        f"{rtb} has no prefix-list route, but dynamoDbGatewayEndpointExists is true",
        "Nothing will create the route, so the VPC functions have no path to "
        "the block ledger and expiry silently does not run. Set "
        "AMPLIFY_PORTAL_DDB_GW_ENDPOINT_EXISTS=0.",
    )


def main() -> int:
    """Run every check and report. Returns the process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", default="ap-northeast-1")
    args = parser.parse_args()

    config_src = read_config_text()
    if not config_src:
        print(f"cannot read {CONFIG_PATH}", file=sys.stderr)
        return 2

    outputs_result, stack = check_outputs_pool(args.region)
    results = [outputs_result]
    results.extend(check_lambda_vpc(stack, args.region, config_src))
    results.append(check_gateway_endpoint(args.region, config_src))

    marks = {OK: "ok  ", FAIL: "FAIL", SKIP: "skip"}
    for result in results:
        print(f"[{marks[result.status]}] {result.name}: {result.detail}")
        if result.remedy and result.status != OK:
            for line in result.remedy.split(". "):
                if line.strip():
                    print(f"         {line.strip().rstrip('.')}.")

    failed = [r for r in results if r.status == FAIL]
    print()
    if failed:
        print(f"{len(failed)} check(s) failed. Do not hand out the URL yet.")
        return 1
    print(
        "All checks passed. Note that reaching the page over HTTP is not "
        "evidence that anyone can sign in -- that is what the pool identity "
        "above establishes."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
