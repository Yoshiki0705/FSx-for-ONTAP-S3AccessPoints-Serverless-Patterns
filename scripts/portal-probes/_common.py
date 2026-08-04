"""Shared discovery and output helpers for the portal probes.

Everything is discovered at runtime. None of these scripts carry an account ID,
VPC ID, subnet ID, route table ID or SVM name, for two reasons: this repository
is public, and a probe with a baked-in resource ID silently targets the wrong
environment instead of failing.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

import boto3
from botocore.config import Config

# The ARP function's own timeout is 60s. A client read timeout at the same value
# races it and reports a timeout for an invocation that actually completed.
LAMBDA_CONFIG = Config(read_timeout=180, retries={"max_attempts": 0})

ACCOUNT_ID = re.compile(r"\b\d{12}\b")


def redact(text: str) -> str:
    """Mask anything that should not end up in a pasted terminal transcript."""
    return ACCOUNT_ID.sub("<account>", text)


def emit(label: str, payload: Any = None, indent: str = "   ") -> None:
    """Print a line, redacted, with optional JSON payload."""
    if payload is None:
        print(redact(label))
        return
    body = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    print(redact(f"{indent}{label} {body}" if label else f"{indent}{body}"))


def find_function(fragment: str, region: str) -> str:
    """Resolve a deployed Lambda by name fragment.

    Fails loudly on zero or several matches. A probe that silently picks the
    first of two candidates is how you verify the wrong deployment.
    """
    client = boto3.client("lambda", region_name=region)
    matches = [
        f["FunctionName"]
        for page in client.get_paginator("list_functions").paginate()
        for f in page["Functions"]
        if fragment in f["FunctionName"]
    ]
    if not matches:
        raise SystemExit(f"No Lambda function matching {fragment!r} in {region}")
    if len(matches) > 1:
        raise SystemExit(f"{len(matches)} functions match {fragment!r}; refusing to guess:\n  " + "\n  ".join(matches))
    return matches[0]


def find_table(fragment: str, region: str) -> str | None:
    """Resolve a DynamoDB table by name fragment, or None when absent."""
    client = boto3.client("dynamodb", region_name=region)
    matches = [
        name
        for page in client.get_paginator("list_tables").paginate()
        for name in page["TableNames"]
        if fragment in name
    ]
    if len(matches) > 1:
        raise SystemExit(f"{len(matches)} tables match {fragment!r}; refusing to guess:\n  " + "\n  ".join(matches))
    return matches[0] if matches else None


def invoke(function_name: str, payload: dict, region: str) -> dict:
    """Invoke a portal Lambda synchronously and parse its response."""
    client = boto3.client("lambda", region_name=region, config=LAMBDA_CONFIG)
    raw = client.invoke(FunctionName=function_name, Payload=json.dumps(payload).encode())["Payload"].read()
    return json.loads(raw)


def summarise(data: dict, keys: tuple[str, ...]) -> dict:
    """Pick the interesting keys, falling back to everything.

    The fallback matters: an unhandled exception or a timeout has none of the
    expected keys, and filtering them out would print an empty object and look
    like a pass.
    """
    picked = {k: v for k, v in data.items() if k in keys}
    return picked or data


def confirm_write(what: str, assume_yes: bool) -> None:
    """Require an explicit go-ahead before a probe changes live state."""
    if assume_yes:
        return
    print(f"\nThis probe will {what} on live infrastructure.")
    answer = input("Type 'yes' to continue: ").strip().lower()
    if answer != "yes":
        sys.exit("aborted")
