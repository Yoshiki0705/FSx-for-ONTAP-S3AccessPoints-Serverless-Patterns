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

Before the first deployment there is no deployed state to compare against, which is
also when the config is most likely to be wrong. ``--check-config`` -- and the
default when ``amplify_outputs.json`` does not exist yet -- checks the config on its
own instead of reporting that it could not run: the region against the one your AWS
session will deploy into, a state machine ARN that is still a placeholder, a VPC with
no subnets or no route tables, and an ONTAP connection configured halfway. Offline
apart from reading the CLI's configured region.

``--print-sandbox-identifier`` reports which sandbox the outputs file points at,
so the wrappers that run ``ampx sandbox`` can name it explicitly instead of
letting the CLI default to one named after the OS user. Without that, running
``npm start`` in a checkout whose outputs belong to another sandbox deploys a
second one; on 2026-09-03 that reached ~25 Lambdas and a Cognito pool before
failing on the gateway-endpoint route, and Amplify does not roll a sandbox back.
Exit codes for that mode: 0 identifier printed, 3 no outputs file (nothing is
deployed yet, so the caller's default is correct), 1 outputs exist but the
identifier could not be resolved -- which must stop the caller rather than fall
back to the default.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PORTAL_DIR = Path(__file__).resolve().parent.parent / "solutions" / "amplify-portal"
OUTPUTS_PATH = PORTAL_DIR / "amplify_outputs.json"
CONFIG_PATH = PORTAL_DIR / "amplify" / "portal-config.ts"

# What makes a function ONTAP-facing is that it was given a management address,
# so that is what identifies one. Matching names instead missed
# ListSnapshotsFunction, which held a stale address and a credential for another
# cluster while the panel it serves reported "User is not authorized" -- measured
# 2026-08-28, after the same defect had been fixed on the function whose name did
# match. A hint list has to be updated when a function is added; this does not.
ONTAP_ADDRESS_VAR = "ONTAP_MGMT_IP"
ONTAP_CREDENTIAL_VAR = "ONTAP_SECRET_NAME"

# Read together, these say which file system a function addresses. All of them
# have to name the same one, and the same one the access point is attached to.
ONTAP_TARGET_VARS = (ONTAP_ADDRESS_VAR, "SVM_NAME", ONTAP_CREDENTIAL_VAR)

# Connecting to ONTAP takes both an address and a credential, so both are what
# identify a function that connects. The address alone is not enough: the data
# platform inventory reads it to say which platform is the working one, connects to
# nothing, and holds no credential -- and on the address alone this check called it
# an ONTAP function, then reported it as disagreeing with the others about a file
# system it never contacts, and as missing the VPC config it must not have.
ONTAP_CONNECT_VARS = (ONTAP_ADDRESS_VAR, ONTAP_CREDENTIAL_VAR)

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

    Read out of the key's own expression rather than by scanning forward from the
    key, because a long fallback is wrapped onto the next line:

        ontapSecretName:
          process.env.ONTAP_SECRET_NAME || "fsx-ontap-fsxadmin-credentials",

    A single-line pattern reported that as unset. Scanning across lines without a
    bound is worse than reporting nothing: for a key whose value holds no string
    literal at all -- ``vpcSubnetIds: idList(process.env.X),`` -- it runs on into
    the next entries and returns some other key's value as this one's.
    """
    expr = config_expression(source, key)
    if expr is None:
        return None
    match = re.search(r'"([^"]*)"', expr)
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


def config_body(source: str) -> str:
    """Return the source from the config object onwards.

    The same key names appear twice in the file: once in the ``PortalConfig``
    interface as ``region: string;`` and once in the object as an assignment.
    Searching the whole file finds the declaration first, and a pattern that spans
    lines then runs from there to the first line-final comma it meets -- which is
    inside some later entry, whose value it returns as this key's. Measured while
    adding these checks: the region read back as an access point alias.
    """
    marker = source.find("export const config")
    return source[marker:] if marker != -1 else source


def config_expression(source: str, key: str) -> str | None:
    """Return the raw right-hand side of a config assignment, or None.

    Bounded twice: to the config object rather than the whole file, and to text
    without a ``;`` ending at the first line-final comma. So a value wrapped onto
    following lines is read whole, while a value that is only a helper call --
    ``vpcSubnetIds: idList(process.env.X),`` -- cannot reach into the entries after
    it and return one of their literals.
    """
    match = re.search(rf"^\s*{re.escape(key)}:\s*([^;]*?),\s*$", config_body(source), re.MULTILINE | re.DOTALL)
    return match.group(1) if match else None


def config_env_var(source: str, key: str) -> str | None:
    """Return the environment variable a config key reads, if it reads one.

    Taken from the expression rather than a table here, so a key added to the
    config is covered without editing this file -- the table is the thing that
    goes stale, and a key missing from it reads as "no variable" rather than as
    an omission.
    """
    expr = config_expression(source, key)
    if not expr:
        return None
    match = re.search(r"process\.env\.([A-Z0-9_]+)", expr)
    return match.group(1) if match else None


def effective_scalar(source: str, key: str) -> tuple[str | None, str]:
    """Return a scalar config value as it will be at synth, and where it came from.

    The environment wins over the literal, matching the config itself. Reading
    only the literal would report the file's value as the deployment's, which is
    wrong in exactly the case somebody has reached for a variable.
    """
    variable = config_env_var(source, key)
    if variable:
        from_env = os.environ.get(variable)
        if from_env is not None and from_env.strip() != "":
            return from_env.strip(), variable
    return config_default(source, key), "portal-config.ts"


def effective_list(source: str, key: str) -> tuple[list[str] | None, str]:
    """Return a list config value as it will be at synth, and where it came from.

    Covers both shapes the config uses: an array literal, and ``idList`` around
    an environment variable with an optional literal fallback.
    """
    variable = config_env_var(source, key)
    if variable:
        from_env = os.environ.get(variable)
        if from_env is not None and from_env.strip() != "":
            return [entry.strip() for entry in from_env.split(",") if entry.strip()], variable

    expr = config_expression(source, key)
    if expr is None:
        return None, "portal-config.ts"
    return re.findall(r'"([^"]*)"', expr), "portal-config.ts"


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


def stack_functions(stack: str, region: str) -> list[str]:
    """Return every Lambda function in a stack family."""
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
            "StackResourceSummaries[?ResourceType=='AWS::Lambda::Function'].PhysicalResourceId",
            "--output",
            "json",
        )
        names.extend(json.loads(raw))
    return names


def function_config(name: str, region: str) -> dict:
    """Return a function's VPC subnets and the file system it addresses."""
    raw = aws(
        "lambda",
        "get-function-configuration",
        "--region",
        region,
        "--function-name",
        name,
        "--query",
        "{subnets: VpcConfig.SubnetIds, env: Environment.Variables}",
        "--output",
        "json",
    )
    parsed = json.loads(raw)
    env = parsed.get("env") or {}
    return {
        "subnets": parsed.get("subnets") or [],
        "target": tuple(env.get(var) for var in ONTAP_TARGET_VARS),
        "ontap_facing": all(env.get(var) for var in ONTAP_CONNECT_VARS),
    }


def short_name(function_name: str) -> str:
    """Return the readable middle segment of a generated function name."""
    parts = function_name.split("-")
    return parts[-2] if len(parts) >= 2 else function_name


def check_lambda_vpc(stack: str | None, region: str, config_src: str) -> list[Result]:
    """Confirm every ONTAP-facing function is in the VPC and shares one target."""
    declared_vpc = config_default(config_src, "vpcId")
    if not declared_vpc:
        return [Result("VPC wiring", SKIP, "portal-config.ts declares no vpcId")]
    if not stack:
        return [Result("VPC wiring", SKIP, "owning stack unknown")]

    try:
        candidates = stack_functions(stack, region)
        configs = {name: function_config(name, region) for name in candidates}
    except RuntimeError as exc:
        return [Result("VPC wiring", FAIL, f"cannot read functions: {exc}")]

    facing = {n: c for n, c in configs.items() if c["ontap_facing"]}
    if not facing:
        return [
            Result(
                "VPC wiring",
                FAIL,
                f"no function in this stack family sets both {ONTAP_ADDRESS_VAR} and {ONTAP_CREDENTIAL_VAR}",
                "The deployed stack does not match this checkout, or the "
                "variables were renamed and ONTAP_CONNECT_VARS needs updating.",
            )
        ]

    results: list[Result] = []
    for name, conf in sorted(facing.items()):
        if conf["subnets"]:
            results.append(
                Result(
                    "VPC wiring",
                    OK,
                    f"{short_name(name)}: {len(conf['subnets'])} subnet(s)",
                )
            )
        else:
            results.append(
                Result(
                    "VPC wiring",
                    FAIL,
                    f"{short_name(name)}: no VpcConfig, so the ONTAP management LIF is unreachable",
                    "Every ONTAP call runs to the function timeout, which the "
                    "UI shows as a panel stuck on loading rather than as an "
                    "error. Redeploy the sandbox so the VPC config applies.",
                )
            )

    targets: dict[tuple, list[str]] = {}
    for name, conf in sorted(facing.items()):
        targets.setdefault(conf["target"], []).append(short_name(name))
    if len(targets) == 1:
        address, svm, secret = next(iter(targets))
        results.append(
            Result(
                "ONTAP target",
                OK,
                f"all {len(facing)} function(s) address {address} / {svm} with {secret}",
            )
        )
    else:
        lines = [f"{'+'.join(names)} -> {t[0]} / {t[1]} with {t[2]}" for t, names in targets.items()]
        results.append(
            Result(
                "ONTAP target",
                FAIL,
                "functions disagree on which file system to manage: " + "; ".join(lines),
                "Panels served by the odd one out fail with ONTAP's own message "
                "while the rest work, so the portal looks partly broken rather "
                "than misconfigured. Patching one function leaves the others "
                "behind: deploy so they all read the same config.",
            )
        )
    return results


def sandbox_root(stack_name: str) -> str:
    """The root sandbox stack name, given any of its nested stack names.

    Nested stacks carry the root name as a prefix (`...-demo-sandbox-753443151c-auth…`,
    `…-data…`), so two resources can be compared for "same sandbox" without knowing
    which nested stack each of them lives in.
    """
    match = re.match(r"^(.*?-[^-]+-sandbox-[0-9a-z]+)", stack_name or "")
    return match.group(1) if match else (stack_name or "")


def check_gateway_endpoint(region: str, config_src: str, stack: str | None = None) -> Result:
    """Compare the gateway-endpoint claim in config against who owns the route.

    Presence of a route is not the question. This check previously asked whether the
    configured route table carried any prefix-list route, which the S3 gateway
    endpoint satisfies on its own, so the answer was always yes and the verdict was
    always "matching". It passed on 2026-09-02 while the DynamoDB endpoint had in fact
    been deleted with a leftover sandbox and the VPC Lambdas were timing out against
    DynamoDB.

    Presence alone is also not enough once it is fixed: "a DynamoDB route exists"
    means something different when this sandbox owns it than when another stack does.
    Owning it and declaring `dynamoDbGatewayEndpointExists: true` would make the next
    deploy remove the endpoint this stack's own functions depend on.
    """
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

    vpc_id = config_default(config_src, "vpcId")
    if not vpc_id or not vpc_id.startswith("vpc-"):
        return Result("DynamoDB route", SKIP, "no VPC configured")

    # Asked of the DynamoDB service specifically, so an S3 gateway endpoint on the
    # same route table cannot answer for it, and the reply carries the owning stack
    # rather than only "something is routed".
    #
    # `route-table-id` is not a DescribeVpcEndpoints filter -- passing it returns
    # `InvalidFilter` -- so the route tables are matched here instead.
    try:
        raw = aws(
            "ec2",
            "describe-vpc-endpoints",
            "--region",
            region,
            "--filters",
            f"Name=vpc-id,Values={vpc_id}",
            f"Name=service-name,Values=com.amazonaws.{region}.dynamodb",
            "--query",
            "VpcEndpoints[].[VpcEndpointId,RouteTableIds,Tags[?Key=='aws:cloudformation:stack-name']|[0].Value]",
            "--output",
            "json",
        )
    except RuntimeError as exc:
        return Result("DynamoDB route", FAIL, f"cannot read the DynamoDB endpoints in {vpc_id}: {exc}")

    found = next((e for e in json.loads(raw or "[]") if rtb in (e[1] or [])), None)
    endpoint = found[0] if found else None
    owner = (found[2] if found else None) or ""

    if not endpoint:
        if claims_exists:
            return Result(
                "DynamoDB route",
                FAIL,
                f"{rtb} has no DynamoDB gateway endpoint, but dynamoDbGatewayEndpointExists is true",
                "Nothing will create the route, so the VPC functions have no path to "
                "the block ledger and expiry silently does not run. Set "
                "AMPLIFY_PORTAL_DDB_GW_ENDPOINT_EXISTS=0.",
            )
        return Result("DynamoDB route", OK, f"{rtb} not routed yet; this stack will create the endpoint")

    ours = bool(stack) and sandbox_root(owner) == sandbox_root(stack or "")
    where = f"{endpoint} on {rtb}"
    if ours:
        if claims_exists:
            return Result(
                "DynamoDB route",
                FAIL,
                f"{where} belongs to this sandbox, but dynamoDbGatewayEndpointExists is true",
                "The next deploy would drop the endpoint this stack's own functions "
                "route through, and expiry would silently stop. Unset "
                "AMPLIFY_PORTAL_DDB_GW_ENDPOINT_EXISTS.",
            )
        return Result("DynamoDB route", OK, f"{where} owned by this sandbox, matching the config")

    held_by = owner or "no CloudFormation stack (created by hand)"
    if claims_exists:
        return Result("DynamoDB route", OK, f"{where} held by {held_by}; this stack reuses the route")
    return Result(
        "DynamoDB route",
        FAIL,
        f"{where} is held by {held_by}, but dynamoDbGatewayEndpointExists is false",
        "A route table takes one route per prefix list, so the data stack will fail "
        "to create its endpoint and roll back after the rest of it succeeds. Set "
        "AMPLIFY_PORTAL_DDB_GW_ENDPOINT_EXISTS=1, or delete that endpoint first if "
        "this stack should own it.",
    )


def check_hosted_binding(region: str, pool_id: str, stack: str | None) -> Result:
    """Compare what the published bundle was built against with what is deployed now.

    `main.tsx` imports `amplify_outputs.json` statically, so the user pool and the
    GraphQL endpoint are compiled into the hosted bundle. Recreating the sandbox
    therefore leaves a page that loads, renders the sign-in form, and rejects every
    credential -- the same symptom as an account created in the wrong pool, and with
    nothing in the browser to distinguish it.

    `portal_deploy_hosting.py` records the binding as tags at publish time; this reads
    them back. The app name and the tag keys are imported rather than repeated, so a
    change to the naming convention cannot leave this check looking for an app that is
    no longer called that and reporting "nothing published".
    """
    if not stack:
        return Result("hosted bundle", SKIP, "owning sandbox unknown")

    import portal_deploy_hosting as hosting

    sandbox = sandbox_identifier(stack)
    name = hosting.app_name(sandbox)

    try:
        raw = aws(
            "amplify",
            "list-apps",
            "--region",
            region,
            "--query",
            "apps[].{name:name,appId:appId,defaultDomain:defaultDomain,tags:tags}",
            "--output",
            "json",
        )
    except RuntimeError as exc:
        return Result("hosted bundle", SKIP, f"cannot list hosting apps: {exc}")

    app = next((a for a in json.loads(raw or "[]") if a.get("name") == name), None)
    if not app:
        # Not a failure: the tunnel and localhost are legitimate ways to run the
        # portal, and most checkouts never publish one.
        return Result("hosted bundle", SKIP, f"no hosting app named {name}")

    url = f"https://{hosting.BRANCH_NAME}.{app['defaultDomain']}"
    bound_pool = (app.get("tags") or {}).get(hosting.BOUND_POOL_TAG)

    if not bound_pool:
        return Result(
            "hosted bundle",
            FAIL,
            f"{url} carries no {hosting.BOUND_POOL_TAG} tag, so what it was built against is unknown",
            "Republish with `make portal-hosting` so the binding is recorded, or the "
            "next person to hand out this URL cannot tell whether it still works.",
        )

    if bound_pool != pool_id:
        return Result(
            "hosted bundle",
            FAIL,
            f"{url} was built against pool {bound_pool}, but the outputs file now names {pool_id}",
            "The page will load, render the sign-in form and reject every credential. "
            "Rebuild and republish with `make portal-hosting`.",
        )

    return Result("hosted bundle", OK, f"{url} was built against this pool")


# An ARN carrying one of these is a value nobody set. The example config used to
# ship a state machine ARN naming 123456789012, which deploys and grants cleanly
# and fails when somebody presses the button.
PLACEHOLDER_MARKERS = ("123456789012", ":placeholder", "amplify-portal-test-workflow")


def session_region() -> str | None:
    """Return the region the AWS CLI would use, without calling AWS.

    Environment first, then the profile, matching the CLI's own order. Returns
    None when neither says anything, in which case the comparison is skipped --
    no value is not the same thing as a disagreeing value.
    """
    for variable in ("AWS_REGION", "AWS_DEFAULT_REGION"):
        value = os.environ.get(variable, "").strip()
        if value:
            return value
    try:
        return aws("configure", "get", "region").strip() or None
    except RuntimeError:
        return None


def check_config(source: str) -> list[Result]:
    """Check the config alone, before anything is deployed from it.

    Separate from the checks above because those compare deployed state against
    the files, which cannot run before the first deployment -- and the first
    deployment is when the config is most likely to be wrong. Everything here is
    offline apart from reading the CLI's configured region.

    What it looks for is the failure that survives a deploy: a value nobody set
    that is nonetheless well-formed. An unset value mostly turns a feature off and
    says so, and the two synth guards in ``backend.ts`` refuse the combinations
    that would deploy as complete. A placeholder ARN does neither.
    """
    results: list[Result] = []

    region, region_origin = effective_scalar(source, "region")
    session = session_region()
    if not region:
        results.append(Result("region", FAIL, "region is unset", "Set region in portal-config.ts."))
    elif session and session != region:
        results.append(
            Result(
                "region",
                FAIL,
                f"config says {region} ({region_origin}), your AWS session is {session}",
                f"The backend deploys to {session} while the Step Functions endpoint, the "
                f"DynamoDB gateway endpoint and the ONTAP VPC's availability zones would all "
                f"name {region}. Set one of them to match the other; backend.ts refuses this "
                f"combination rather than building it.",
            )
        )
    elif session:
        results.append(Result("region", OK, f"{region}, matching your AWS session"))
    else:
        results.append(Result("region", SKIP, f"{region} ({region_origin}); no region on the AWS session to compare"))

    arn, arn_origin = effective_scalar(source, "stateMachineArn")
    marker = next((m for m in PLACEHOLDER_MARKERS if arn and m in arn), None)
    if marker:
        results.append(
            Result(
                "state machine",
                FAIL,
                f"stateMachineArn contains the placeholder {marker!r} ({arn_origin})",
                "startProcessing would call StartExecution against a state machine in another "
                "account. Set it to a state machine you own, or leave it empty -- empty reports "
                "that processing is not configured, which a placeholder does not.",
            )
        )
    elif not arn:
        results.append(
            Result("state machine", SKIP, "not configured; startProcessing reports that rather than failing")
        )
    else:
        results.append(Result("state machine", OK, f"{arn} ({arn_origin})"))

    alias, alias_origin = effective_scalar(source, "s3ApAlias")
    if not alias:
        results.append(Result("file source", SKIP, "s3ApAlias is empty; the Files tab shows no files"))
    else:
        results.append(Result("file source", OK, f"{alias} ({alias_origin})"))

    ontap = {key: effective_scalar(source, key)[0] or "" for key in ("ontapMgmtIp", "ontapSecretName", "ontapSvmName")}
    if not any(ontap.values()):
        results.append(
            Result("ONTAP connection", SKIP, "not configured; the admin panels report that a connection is required")
        )
    else:
        missing = [key for key, value in ontap.items() if not value]
        if missing:
            results.append(
                Result(
                    "ONTAP connection",
                    FAIL,
                    f"partially configured: {', '.join(missing)} unset",
                    "An address without a credential, or a credential without an SVM, deploys "
                    "and then fails per call. Set all three, and make the secret the one for the "
                    "same file system as the address -- `make ontap-preflight FS_ID=<id>` checks "
                    "that pair without authenticating, because pairing one cluster's address with "
                    "another's credential locks fsxadmin out rather than merely failing.",
                )
            )
        else:
            results.append(Result("ONTAP connection", OK, f"{ontap['ontapMgmtIp']} / {ontap['ontapSvmName']}"))

    vpc_id, vpc_origin = effective_scalar(source, "vpcId")
    if not vpc_id:
        results.append(Result("VPC wiring", SKIP, "vpcId is empty; the ONTAP-facing functions deploy outside a VPC"))
    else:
        subnets, _ = effective_list(source, "vpcSubnetIds")
        route_tables, _ = effective_list(source, "vpcRouteTableIds")
        allow_no_expiry = config_bool(source, "allowNoBlockExpiry")
        if not subnets:
            results.append(
                Result(
                    "VPC wiring",
                    FAIL,
                    f"{vpc_id} ({vpc_origin}) with no subnets",
                    "A function with a VPC and no subnet cannot be placed. Set vpcSubnetIds to "
                    "the subnets carrying the FSx for ONTAP ENIs.",
                )
            )
        elif not route_tables and not allow_no_expiry:
            results.append(
                Result(
                    "VPC wiring",
                    FAIL,
                    f"{vpc_id} ({vpc_origin}) with no route tables",
                    "backend.ts refuses this: without a DynamoDB gateway endpoint the containment "
                    "ledger is unreachable, so blocks are placed on the cluster and never expire. "
                    "Set vpcRouteTableIds, or set allowNoBlockExpiry to accept it deliberately.",
                )
            )
        else:
            detail = f"{vpc_id}, {len(subnets)} subnet(s), {len(route_tables)} route table(s)"
            results.append(Result("VPC wiring", OK, detail))

    return results


def print_sandbox_identifier(region_hint: str) -> int:
    """Print the identifier of the sandbox the outputs file points at.

    Resolution goes through the deployed pool rather than the file name or a
    config literal, because the identifier is not written anywhere on disk --
    the outputs file names a pool, and CloudFormation is what says which stack,
    and therefore which sandbox, owns it.
    """
    if not OUTPUTS_PATH.exists():
        print(
            f"{OUTPUTS_PATH.name} not found: no sandbox is deployed from this checkout.",
            file=sys.stderr,
        )
        return 3

    try:
        outputs = load_outputs()
    except (RuntimeError, json.JSONDecodeError) as exc:
        print(f"cannot read {OUTPUTS_PATH.name}: {exc}", file=sys.stderr)
        return 1

    auth = outputs.get("auth") or {}
    pool_id = auth.get("user_pool_id")
    region = auth.get("aws_region") or region_hint
    if not pool_id:
        print(f"{OUTPUTS_PATH.name} has no auth.user_pool_id", file=sys.stderr)
        return 1

    try:
        stack = owning_stack(pool_id, region)
    except RuntimeError as exc:
        print(f"cannot resolve the stack owning {pool_id}: {exc}", file=sys.stderr)
        return 1

    identifier = sandbox_identifier(stack)
    if identifier.startswith("("):
        print(f"{stack} is not a sandbox stack", file=sys.stderr)
        return 1

    print(identifier)
    return 0


def report(results: list[Result]) -> None:
    """Print one line per check, and the remedy for anything that did not pass."""
    marks = {OK: "ok  ", FAIL: "FAIL", SKIP: "skip"}
    for result in results:
        print(f"[{marks[result.status]}] {result.name}: {result.detail}")
        if result.remedy and result.status != OK:
            for line in result.remedy.split(". "):
                if line.strip():
                    print(f"         {line.strip().rstrip('.')}.")
    print()


def main() -> int:
    """Run every check and report. Returns the process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", default="ap-northeast-1")
    parser.add_argument(
        "--print-sandbox-identifier",
        action="store_true",
        help="print the sandbox identifier the outputs file points at, and exit",
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="check portal-config.ts alone, without comparing it to a deployment",
    )
    args = parser.parse_args()

    if args.print_sandbox_identifier:
        return print_sandbox_identifier(args.region)

    config_src = read_config_text()
    if not config_src:
        print(f"cannot read {CONFIG_PATH}", file=sys.stderr)
        print(
            "  Copy the example and fill it in:\n"
            "    cd solutions/amplify-portal && cp amplify/portal-config.example.ts "
            "amplify/portal-config.ts",
            file=sys.stderr,
        )
        return 2

    # Before the first deployment there is nothing to compare the files against, and
    # that is when the config is most likely to be wrong. Reporting "could not run"
    # there left the checks useful only to whoever already had a working deployment.
    if args.check_config or not OUTPUTS_PATH.exists():
        results = check_config(config_src)
        report(results)
        failed = [r for r in results if r.status == FAIL]
        if failed:
            print(f"{len(failed)} check(s) failed. Fix the config before deploying.")
            return 1
        if args.check_config:
            print(
                "Config checks passed. Deployed state is not covered here; run without --check-config after deploying."
            )
        else:
            print(
                f"Config checks passed. {OUTPUTS_PATH.name} does not exist yet, so nothing was "
                "compared against a deployment -- run this again after `make sandbox`."
            )
        return 0

    outputs_result, stack = check_outputs_pool(args.region)
    results = [outputs_result]
    results.extend(check_lambda_vpc(stack, args.region, config_src))
    results.append(check_gateway_endpoint(args.region, config_src, stack))

    # Last, because it is about the copy a reviewer opens rather than the backend the
    # checks above cover. Reached even when the outputs file could not be read, in
    # which case there is no pool to compare and the check skips.
    try:
        pool_for_binding = (load_outputs().get("auth") or {}).get("user_pool_id") or ""
    except (RuntimeError, json.JSONDecodeError):
        pool_for_binding = ""
    if pool_for_binding:
        results.append(check_hosted_binding(args.region, pool_for_binding, stack))

    report(results)

    failed = [r for r in results if r.status == FAIL]
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
