#!/usr/bin/env python3
"""Publish the portal to Amplify Hosting so another machine can reach it.

Why this exists rather than the tunnel: `npm run phone` produces a URL that changes
on every run and only lives while a laptop stays awake, which `docs/portal-handover-guide.md`
records as "do not hand out". Amplify Hosting gives an https origin that survives
both. https matters and is not cosmetic -- sign-in uses SRP, which calls
`crypto.subtle`, and browsers restrict that to secure contexts, so a LAN address
cannot be substituted.

Deployment is the zip-upload kind, not a git connection. That keeps the published
artifact exactly the one built here, needs no repository access, and consumes no
build minutes.

**What the published bundle is bound to.** `main.tsx` imports `amplify_outputs.json`
statically, so the user pool and the GraphQL endpoint are compiled into the bundle.
The hosted URL is therefore only as permanent as the backend behind it: delete or
recreate that sandbox and the page still loads, still renders the sign-in form, and
rejects every credential. So the sandbox this bundle was built against is recorded as
a tag on the app, where it can be read later, rather than left implicit.

Usage:
    python3 scripts/portal_deploy_hosting.py                 # build, publish, report
    python3 scripts/portal_deploy_hosting.py --skip-build    # publish the existing dist/
    python3 scripts/portal_deploy_hosting.py --show          # report the current URL only

Exit codes: 0 published, 1 refused or failed, 2 could not run.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PORTAL_DIR = REPO_ROOT / "solutions" / "amplify-portal"
OUTPUTS_PATH = PORTAL_DIR / "amplify_outputs.json"
DIST_DIR = PORTAL_DIR / "dist"

BRANCH_NAME = "demo"

# The username half of the basic-auth credential. Fixed so that only the password has
# to be communicated, and it is not a secret in any case.
BASIC_AUTH_USER = "demo"

# A single-page app serves every route from index.html. Without this an Amplify
# branch answers 403/404 for anything but "/", which shows up only after a reload on
# a sub-route -- the first visit works, so it reads as intermittent.
SPA_REWRITE = [{"source": "/<*>", "target": "/index.html", "status": "404-200"}]

# Records which backend the bundle was compiled against. Read it back with
# `aws amplify get-app`; a hosted app whose tag names a sandbox that no longer exists
# is the explanation for "the page loads but nobody can sign in".
SANDBOX_TAG = "portal:sandbox"
BOUND_POOL_TAG = "portal:user-pool-id"


def aws(*args: str, timeout: int = 300) -> str:
    """Run an AWS CLI command and return stdout, or raise RuntimeError."""
    proc = subprocess.run(["aws", *args], capture_output=True, text=True, check=False, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"aws {' '.join(args)} failed")
    return proc.stdout.strip()


def load_outputs() -> dict:
    """Return parsed amplify_outputs.json, or raise RuntimeError."""
    if not OUTPUTS_PATH.exists():
        raise RuntimeError(
            f"{OUTPUTS_PATH} not found. Deploy the backend first (`make sandbox` in solutions/amplify-portal)."
        )
    return json.loads(OUTPUTS_PATH.read_text(encoding="utf-8"))


def sandbox_identifier(stack_name: str) -> str:
    """Pull the sandbox identifier out of an Amplify stack name."""
    match = re.search(r"-([^-]+)-sandbox-", stack_name or "")
    return match.group(1) if match else "(not a sandbox stack)"


def owning_sandbox(pool_id: str, region: str) -> str:
    """Return the sandbox identifier that owns a user pool."""
    stack = aws(
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
    return sandbox_identifier(stack)


def app_name(sandbox: str) -> str:
    """The hosting app name for a sandbox.

    Derived from the sandbox rather than fixed, so publishing from a second sandbox
    creates a second app instead of overwriting the first one's bundle with a build
    pointing at a different user pool.
    """
    return f"fsxn-portal-{sandbox}"


def find_app(name: str, region: str) -> dict | None:
    """Return the hosting app with this name, or None."""
    raw = aws(
        "amplify",
        "list-apps",
        "--region",
        region,
        "--query",
        "apps[].{appId:appId,name:name,defaultDomain:defaultDomain,tags:tags}",
        "--output",
        "json",
    )
    for app in json.loads(raw or "[]"):
        if app.get("name") == name:
            return app
    return None


def create_app(name: str, region: str, sandbox: str, pool_id: str) -> dict:
    """Create the hosting app with SPA rewrites and the binding tags."""
    raw = aws(
        "amplify",
        "create-app",
        "--region",
        region,
        "--name",
        name,
        "--custom-rules",
        json.dumps(SPA_REWRITE),
        "--tags",
        f"{SANDBOX_TAG}={sandbox},{BOUND_POOL_TAG}={pool_id}",
        "--query",
        "app.{appId:appId,name:name,defaultDomain:defaultDomain,tags:tags}",
        "--output",
        "json",
    )
    return json.loads(raw)


def ensure_branch(app_id: str, region: str) -> None:
    """Create the branch if it is absent."""
    raw = aws(
        "amplify",
        "list-branches",
        "--region",
        region,
        "--app-id",
        app_id,
        "--query",
        "branches[].branchName",
        "--output",
        "json",
    )
    if BRANCH_NAME in json.loads(raw or "[]"):
        return
    aws(
        "amplify",
        "create-branch",
        "--region",
        region,
        "--app-id",
        app_id,
        "--branch-name",
        BRANCH_NAME,
    )


def build_frontend() -> None:
    """Build the production bundle, raising RuntimeError on failure."""
    proc = subprocess.run(
        ["npm", "run", "build"],
        cwd=PORTAL_DIR,
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )
    if proc.returncode != 0:
        tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-25:])
        raise RuntimeError(f"npm run build failed:\n{tail}")


def zip_dist() -> bytes:
    """Return dist/ as a zip archive with its contents at the archive root.

    Amplify serves the archive's root as the site root, so the paths are stored
    relative to dist/. Nesting them under "dist/" produces a deployment that
    succeeds and serves 404 for everything.
    """
    if not DIST_DIR.is_dir():
        raise RuntimeError(f"{DIST_DIR} not found. Build first, or drop --skip-build.")
    index = DIST_DIR / "index.html"
    if not index.is_file():
        raise RuntimeError(f"{index} not found, so this dist/ would serve nothing.")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(DIST_DIR.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(DIST_DIR).as_posix())
    return buffer.getvalue()


def upload_and_start(app_id: str, region: str, payload: bytes) -> str:
    """Upload the bundle and start the deployment. Returns the job id."""
    raw = aws(
        "amplify",
        "create-deployment",
        "--region",
        region,
        "--app-id",
        app_id,
        "--branch-name",
        BRANCH_NAME,
        "--query",
        "{jobId:jobId,zipUploadUrl:zipUploadUrl}",
        "--output",
        "json",
    )
    created = json.loads(raw)

    upload_url = created["zipUploadUrl"]
    # Checked rather than assumed. The URL arrives from the Amplify API and is
    # presigned, so it should always be https, but `urlopen` also honours `file:` and
    # would read a local path as if it were the upload target. Asserting the scheme
    # keeps that from being reachable at all if the response is ever wrong.
    if not upload_url.startswith("https://"):
        raise RuntimeError(f"refusing to upload to a non-https target: {upload_url[:40]}")

    request = urllib.request.Request(
        upload_url,
        data=payload,
        method="PUT",
        headers={"Content-Type": "application/zip"},
    )
    # The URL is presigned and points at Amplify's own bucket; it carries the
    # credentials, so no signing happens here. The scheme is checked above, which is
    # what B310 asks for.
    with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310  # nosec B310
        if response.status not in (200, 204):
            raise RuntimeError(f"uploading the bundle returned HTTP {response.status}")

    raw = aws(
        "amplify",
        "start-deployment",
        "--region",
        region,
        "--app-id",
        app_id,
        "--branch-name",
        BRANCH_NAME,
        "--job-id",
        created["jobId"],
        "--query",
        "jobSummary.jobId",
        "--output",
        "text",
    )
    return raw


def wait_for_job(app_id: str, region: str, job_id: str, timeout_s: int = 600) -> str:
    """Poll until the deployment settles. Returns the terminal status."""
    deadline = time.time() + timeout_s
    last = "PENDING"
    while time.time() < deadline:
        status = aws(
            "amplify",
            "get-job",
            "--region",
            region,
            "--app-id",
            app_id,
            "--branch-name",
            BRANCH_NAME,
            "--job-id",
            job_id,
            "--query",
            "job.summary.status",
            "--output",
            "text",
        )
        if status != last:
            print(f"  deployment {status.lower()}")
            last = status
        if status in ("SUCCEED", "FAILED", "CANCELLED"):
            return status
        time.sleep(5)
    return f"TIMEOUT after {timeout_s}s (last: {last})"


def branch_url(app: dict) -> str:
    """The https URL a person opens."""
    return f"https://{BRANCH_NAME}.{app['defaultDomain']}"


def basic_auth_state(app_id: str, region: str) -> bool | None:
    """Whether the branch is behind basic auth, or None when it cannot be read.

    Reported alongside the URL because "who can reach this page" is part of handing
    it over, and the answer is not visible from the URL itself.
    """
    try:
        raw = aws(
            "amplify",
            "get-branch",
            "--region",
            region,
            "--app-id",
            app_id,
            "--branch-name",
            BRANCH_NAME,
            "--query",
            "branch.enableBasicAuth",
            "--output",
            "text",
        )
    except RuntimeError:
        return None
    return raw.strip().lower() == "true"


def set_basic_auth(app_id: str, region: str, enable: bool) -> str | None:
    """Turn basic auth on or off. Returns the generated password when enabling.

    Opt-in rather than the default. Cognito sign-in is already a real gate, so
    requiring a second credential for every demo adds a secret to hand over without
    changing who can sign in. What it does add is keeping a published URL out of
    casual reach, which matters when the URL has been shared more widely than the
    accounts have.
    """
    if not enable:
        aws(
            "amplify",
            "update-branch",
            "--region",
            region,
            "--app-id",
            app_id,
            "--branch-name",
            BRANCH_NAME,
            "--no-enable-basic-auth",
        )
        return None

    # Generated here rather than taken as an argument, so the credential never sits in
    # a shell history or a Makefile invocation.
    import portal_provision_demo_user as provision

    # A colon is legal in the password half -- RFC 7617 splits on the first one -- but
    # the credential is decoded by Amplify, by CloudFront and by whatever client the
    # reviewer uses, and there is no reason to depend on all three splitting the same
    # way. Regenerating is cheaper than reasoning about it.
    password = provision.generate_password({})
    while ":" in password:
        password = provision.generate_password({})

    credentials = base64.b64encode(f"{BASIC_AUTH_USER}:{password}".encode()).decode()
    aws(
        "amplify",
        "update-branch",
        "--region",
        region,
        "--app-id",
        app_id,
        "--branch-name",
        BRANCH_NAME,
        "--enable-basic-auth",
        "--basic-auth-credentials",
        credentials,
    )
    return password


def report_binding(app: dict, sandbox: str, pool_id: str) -> None:
    """Print the app's recorded backend binding, and whether it still matches."""
    tags = app.get("tags") or {}
    bound_sandbox = tags.get(SANDBOX_TAG)
    bound_pool = tags.get(BOUND_POOL_TAG)
    print(f"  built against sandbox '{sandbox}', pool {pool_id}")
    if bound_pool and bound_pool != pool_id:
        print(
            f"  ⚠ this app was previously published against pool {bound_pool} "
            f"(sandbox '{bound_sandbox}'). Republish, or the bundle and the pool "
            "disagree and nobody can sign in."
        )


def report_gate(app_id: str, region: str) -> None:
    """Print what stands between the URL and the data."""
    gated = basic_auth_state(app_id, region)
    if gated is None:
        print("  gate     could not read the branch; basic-auth state unknown")
    elif gated:
        print("  gate     basic auth, then Cognito sign-in")
    else:
        print("  gate     Cognito sign-in only -- anyone with the URL reaches the form")
        print("           add a second one with --basic-auth")


def main() -> int:
    """Publish and report. Returns the process exit code."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--region", default="ap-northeast-1")
    parser.add_argument("--skip-build", action="store_true", help="publish the existing dist/ unchanged")
    parser.add_argument("--show", action="store_true", help="report the current URL and binding, change nothing")
    gate = parser.add_mutually_exclusive_group()
    gate.add_argument(
        "--basic-auth",
        action="store_true",
        help="put the branch behind basic auth, generating and printing the password once",
    )
    gate.add_argument("--no-basic-auth", action="store_true", help="remove basic auth from the branch")
    args = parser.parse_args()

    try:
        outputs = load_outputs()
    except (RuntimeError, json.JSONDecodeError) as exc:
        print(f"cannot read the outputs file: {exc}", file=sys.stderr)
        return 2

    auth = outputs.get("auth") or {}
    pool_id = auth.get("user_pool_id")
    region = auth.get("aws_region") or args.region
    if not pool_id:
        print("amplify_outputs.json has no auth.user_pool_id", file=sys.stderr)
        return 2

    try:
        sandbox = owning_sandbox(pool_id, region)
    except RuntimeError as exc:
        print(f"cannot resolve which sandbox owns {pool_id}: {exc}", file=sys.stderr)
        return 1

    name = app_name(sandbox)

    try:
        app = find_app(name, region)

        if args.show:
            if not app:
                print(f"no hosting app named {name} in {region}")
                return 1
            print(f"app  {app['appId']} ({name})")
            print(f"url  {branch_url(app)}")
            report_binding(app, sandbox, pool_id)
            report_gate(app["appId"], region)
            return 0

        # Before publishing, so `--basic-auth` on its own is a way to gate an app that
        # is already live without rebuilding it.
        if args.basic_auth or args.no_basic_auth:
            if not app:
                print(f"no hosting app named {name}; publish first", file=sys.stderr)
                return 1
            password = set_basic_auth(app["appId"], region, enable=args.basic_auth)
            if password:
                print("basic auth enabled")
                print(f"  username  {BASIC_AUTH_USER}")
                print(f"  password  {password}")
                print("Shown once and not written to disk.")
            else:
                print("basic auth removed; Cognito sign-in is again the only gate")
            return 0

        if app:
            print(f"app  {app['appId']} ({name}) exists")
        else:
            app = create_app(name, region, sandbox, pool_id)
            print(f"app  {app['appId']} ({name}) created")

        ensure_branch(app["appId"], region)
        print(f"branch {BRANCH_NAME}")

        if not args.skip_build:
            print("building...")
            build_frontend()
        payload = zip_dist()
        print(f"bundle {len(payload) / 1024:.0f} KiB")

        job_id = upload_and_start(app["appId"], region, payload)
        status = wait_for_job(app["appId"], region, job_id)
        if status != "SUCCEED":
            print(f"✖ deployment did not succeed: {status}", file=sys.stderr)
            return 1
    except RuntimeError as exc:
        print(f"✖ {exc}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"✖ uploading the bundle failed: {exc}", file=sys.stderr)
        return 1

    # Re-read so the tags reported are the stored ones rather than what was sent.
    published = find_app(name, region) or app
    url = branch_url(published)
    print()
    print("─" * 68)
    print(f"  {url}")
    print("─" * 68)
    report_binding(published, sandbox, pool_id)
    print()
    report_gate(published["appId"], region)
    return 0


if __name__ == "__main__":
    sys.exit(main())
