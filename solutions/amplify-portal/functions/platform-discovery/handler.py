"""Inventory of the data platforms the portal can scope to.

Deliberately outside the VPC
----------------------------
Every other ONTAP-related function here runs inside the VPC, because the
management LIF is a private address. This one must not: it answers the AWS
control plane, and its whole value is that it can still answer when the ONTAP
path cannot. A function in the VPC reaching ``fsx:DescribeFileSystems`` would
need an interface endpoint or a NAT gateway, and would fail for network reasons
while reporting an inventory problem -- which is the shape of failure this layer
was added to remove.

It also holds no ONTAP credential. Listing what exists is separate from being
able to act on it, and asking every file system to authenticate just to draw a
list is what produced a portal whose panels sat on "loading".

Actions:
    listDataPlatforms - the platforms an operator may select, and the reasons any
        declared platform is absent.

Environment:
    DECLARED_PLATFORMS: JSON array of platforms that are not FSx for ONTAP. Each
        is shown only once a probe answers for it, so an entry here is a claim
        that something exists, not an entry in the inventory.
    ONTAP_MGMT_IP: The management address this deployment's ONTAP actions use, so
        the inventory can say which platform is the working one. Read here only to
        compare; it is never returned.
    DISCOVERY_REGIONS: Comma-separated regions to enumerate. Defaults to the
        function's own region, which is the single-region case.
    DISCOVERY_ACCOUNTS: Comma-separated account IDs to enumerate in addition to
        this one. Requires DISCOVERY_ROLE_NAME.
    DISCOVERY_ROLE_NAME: Read-only role to assume in those accounts. Without it,
        accounts are ignored rather than attempted, because an attempt with no role
        fails as an authorization error and reads as a permissions problem in this
        account.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import replace

import boto3

from shared.storage_systems import (
    Declaration,
    DiscoveryScope,
    StorageSystem,
    build_inventory,
    discover_fsx_ontap_across,
    probe_declared,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DECLARED_PLATFORMS = os.environ.get("DECLARED_PLATFORMS", "")

# The management address the deployment's ONTAP actions use. Compared here rather
# than published: the browser is told which platform is connected as a boolean and
# never receives the address, so the inventory answers "what exists" and "which one
# am I working on" without disclosing endpoints to every signed-in user.
#
# Exactly one entry can match, because the other handlers read a single address
# from their own environment. The rest are listed so an estate is visible from one
# portal rather than hidden behind whichever cluster this deployment happens to
# point at -- and marked, so the UI does not offer them as a working scope.
CONNECTED_MANAGEMENT_ADDRESS = os.environ.get("ONTAP_MGMT_IP", "").strip()

DISCOVERY_ROLE_NAME = os.environ.get("DISCOVERY_ROLE_NAME", "").strip()


def _id_list(raw: str) -> list[str]:
    """Split a comma-separated setting, dropping blanks."""
    return [part.strip() for part in raw.split(",") if part.strip()]


def _scopes() -> list[DiscoveryScope]:
    """The accounts and regions to enumerate.

    The deployment's own account is always included, in every configured region.
    Other accounts are added only when a role to assume is configured: attempting
    one without a role fails as an authorization error against this account, which
    reads as a permissions problem here rather than as missing configuration.
    """
    regions = _id_list(os.environ.get("DISCOVERY_REGIONS", "")) or [os.environ.get("AWS_REGION", "")]
    regions = [region for region in regions if region]
    accounts = _id_list(os.environ.get("DISCOVERY_ACCOUNTS", ""))
    if accounts and not DISCOVERY_ROLE_NAME:
        logger.warning(
            "DISCOVERY_ACCOUNTS is set without DISCOVERY_ROLE_NAME; those accounts cannot be read and are being skipped"
        )
        accounts = []

    scopes = [DiscoveryScope(region=region) for region in regions]
    for account in accounts:
        for region in regions:
            scopes.append(DiscoveryScope(region=region, account=account, role_name=DISCOVERY_ROLE_NAME))
    return scopes


def _fsx_client(scope: DiscoveryScope):
    """An FSx client for a scope, assuming into the account when one is named.

    Credentials are fetched per scope rather than cached. A discovery call happens
    once per five minutes of browser use, so the saving would be small, and a
    cached credential that expires between two calls fails in a way that looks like
    the account became unreachable.
    """
    if not (scope.account and scope.role_name):
        return boto3.client("fsx", region_name=scope.region)
    assumed = boto3.client("sts").assume_role(
        RoleArn=f"arn:aws:iam::{scope.account}:role/{scope.role_name}",
        RoleSessionName="portal-platform-discovery",
    )["Credentials"]
    return boto3.client(
        "fsx",
        region_name=scope.region,
        aws_access_key_id=assumed["AccessKeyId"],
        aws_secret_access_key=assumed["SecretAccessKey"],
        aws_session_token=assumed["SessionToken"],
    )


# No probe is registered yet, so every declared platform is reported as
# unconfirmed rather than offered. That is the intended behaviour of an empty
# registry, not a gap standing in for one: reaching an ONTAP cluster that is not
# an FSx file system needs a route from this account to it, and a platform whose
# management interface is not the ONTAP REST API needs its own client and
# credential. Registering a probe here is what makes such a platform appear.
_PROBES: dict = {}


def _declarations() -> list[Declaration]:
    """Parse the declared platforms, dropping entries that cannot be identified.

    A malformed value is logged and treated as no declarations. The alternative is
    raising at import time, which takes the whole inventory down -- including the
    FSx for ONTAP platforms, which are discovered and do not depend on this.
    """
    if not DECLARED_PLATFORMS.strip():
        return []
    try:
        raw = json.loads(DECLARED_PLATFORMS)
    except json.JSONDecodeError as exc:
        logger.error("DECLARED_PLATFORMS is not valid JSON (%s); ignoring it", exc)
        return []
    if not isinstance(raw, list):
        logger.error("DECLARED_PLATFORMS must be a JSON array; ignoring it")
        return []
    declarations = []
    for entry in raw:
        if not isinstance(entry, dict):
            logger.warning("Ignoring a declared platform that is not an object: %r", entry)
            continue
        declaration = Declaration.from_dict(entry)
        if declaration is not None:
            declarations.append(declaration)
    return declarations


def _mark_connected(system: StorageSystem) -> StorageSystem:
    """Flag the platform this deployment's ONTAP actions address.

    With no address configured nothing is marked, rather than the first entry being
    assumed. A wrong mark is worse than no mark: it would tell an operator that
    actions apply to a platform they do not.
    """
    if not CONNECTED_MANAGEMENT_ADDRESS:
        return system
    if system.management_address != CONNECTED_MANAGEMENT_ADDRESS:
        return system
    return replace(system, connected=True)


def _list_data_platforms() -> dict:
    """Return the inventory, or the reason it could not be read."""
    # Per-scope failures are reported inside the inventory rather than raised, so a
    # second account that cannot be read does not hide the one the operator is
    # connected to. Only a failure outside any scope reaches the except below.
    try:
        discovered = discover_fsx_ontap_across(_scopes(), _fsx_client)
    except Exception as exc:  # noqa: BLE001 - the response says what failed
        logger.error("FSx discovery failed: %s: %s", type(exc).__name__, exc)
        return {
            "platforms": [],
            "hidden": [],
            "count": 0,
            "error": f"Could not read the FSx inventory: {type(exc).__name__}",
        }

    declared = probe_declared(_declarations(), _PROBES)
    declared.hidden = discovered.hidden + declared.hidden
    inventory = build_inventory(discovered.systems, declared)
    inventory.systems = [_mark_connected(system) for system in inventory.systems]
    payload = inventory.as_dict()
    payload["error"] = None
    return payload


def handler(event: dict, context: object) -> dict:
    """Route a dispatch call.

    Args:
        event: The dispatch payload. ``action`` selects the operation.
        context: The Lambda context, unused.

    Returns:
        The response payload for the resolver.
    """
    action = event.get("action", "")
    if action == "listDataPlatforms":
        return _list_data_platforms()
    return {"error": f"Unknown action: {action}"}
