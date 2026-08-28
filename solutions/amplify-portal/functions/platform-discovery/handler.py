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
"""

from __future__ import annotations

import json
import logging
import os

import boto3

from dataclasses import replace

from shared.storage_systems import (
    Declaration,
    StorageSystem,
    build_inventory,
    discover_fsx_ontap,
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
    try:
        discovered = discover_fsx_ontap(boto3.client("fsx"))
    except Exception as exc:  # noqa: BLE001 - the response says which half failed
        logger.error("FSx discovery failed: %s: %s", type(exc).__name__, exc)
        return {
            "platforms": [],
            "hidden": [],
            "count": 0,
            "error": f"Could not read the FSx inventory: {type(exc).__name__}",
        }

    inventory = build_inventory(discovered, probe_declared(_declarations(), _PROBES))
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
