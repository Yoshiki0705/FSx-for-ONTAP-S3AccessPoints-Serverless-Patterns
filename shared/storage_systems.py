"""The storage systems the portal can see, above the SVM layer.

Why this layer exists
---------------------
The portal narrowed resources by SVM and then by volume. In an estate with many
file systems that is the wrong entry point twice over: the names carry no
indication of which system they belong to, so the list is noise, and every
listing is an ONTAP call that requires the management LIF to be reachable and a
credential to be accepted before anything can be shown at all.

One layer up, the grouping is a storage system -- a file system for
FSx for ONTAP, a cluster for ONTAP running elsewhere, and the equivalent
container on platforms that are not ONTAP. Choosing one first turns the SVM list
from "every SVM anyone can reach" into "the SVMs of the system being worked on".

Discovery is separate from management
-------------------------------------
For FSx for ONTAP both layers come from the AWS control plane. Measured
2026-08-28 in ap-northeast-1: ``describe_file_systems`` answered in 0.75 s and
``describe_storage_virtual_machines`` in 0.47 s, neither requiring ONTAP
credentials nor a route to the management LIF. That is what makes this layer
usable as the entry point -- it cannot be blocked by the credential mismatch it
exists to help diagnose.

Anything that is not FSx for ONTAP has to be declared, because no AWS API lists
it. A declaration on its own is not an entry: it becomes one only when a probe
answers. That rule is the whole design. Listing a declared system that cannot be
reached would put an option in front of an operator that no action can act on,
which is the noise this layer is meant to remove rather than a different kind of
completeness.

A system that fails its probe is reported to the log with the reason and left out
of the inventory. `hidden` on the result carries those reasons so an operator can
ask why something they declared is not there, without the inventory itself
implying it is available.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Platform identifiers. These name the management interface, not the vendor: what
# a caller needs to know is which API answers for this system and therefore which
# operations exist for it.
PLATFORM_FSX_ONTAP = "FSX_ONTAP"
PLATFORM_ONTAP_CLUSTER = "ONTAP_CLUSTER"

#: Platforms whose management interface is the ONTAP REST API, and which the
#: portal's ONTAP actions can therefore address once reachable. Cloud Volumes
#: ONTAP and an on-premises cluster are both ``ONTAP_CLUSTER``: they differ in
#: where they run, which is not a difference this portal acts on.
ONTAP_REST_PLATFORMS = frozenset({PLATFORM_FSX_ONTAP, PLATFORM_ONTAP_CLUSTER})


@dataclass(frozen=True)
class StorageSystem:
    """One system an operator can scope the portal to.

    Attributes:
        platform: One of the ``PLATFORM_*`` values.
        system_id: Stable identifier. The file system ID for FSx for ONTAP, and
            the declared identifier otherwise.
        name: What an operator calls it. For FSx for ONTAP this is the ``Name``
            tag when set, because the file system ID is not what anyone uses to
            refer to it in conversation.
        management_address: Where the management interface answers, or "" when the
            platform has no address the portal connects to.
        svms: The SVMs on this system. Empty for platforms without SVMs, which is
            not the same as an ONTAP system whose SVMs could not be read.
        manageable: Whether the portal's actions can act on it, rather than only
            list it. False for a system that answered a probe but whose
            management interface the portal does not speak.
        discovered_by: How this entry was established, for a reader asking why it
            is in the list.
        resource_type: The platform's own name for what this container is, when it
            is not a file system or a cluster. Carried through so the UI can label
            an entry in the platform's vocabulary instead of in ONTAP's.
        account: The AWS account the platform was found in, or "" when it was not
            found through AWS. Carried because a name is only unique within an
            account: two teams each name a file system after their project, and an
            inventory that shows both as one entry is worse than no inventory.
        region: Likewise for the region.
        connected: Whether this is the platform the deployment's ONTAP actions
            address. Exactly one entry can be, because the handlers read one
            management address from their environment. The inventory lists the
            others so an operator can see what exists without having to reach it,
            and this flag is what stops the UI offering them as a working scope.
    """

    platform: str
    system_id: str
    name: str
    management_address: str = ""
    svms: tuple[str, ...] = ()
    manageable: bool = False
    discovered_by: str = ""
    resource_type: str = ""
    connected: bool = False
    account: str = ""
    region: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Return every field, for callers that route requests."""
        return {
            "platform": self.platform,
            "systemId": self.system_id,
            "name": self.name,
            "managementAddress": self.management_address,
            "svms": list(self.svms),
            "manageable": self.manageable,
            "discoveredBy": self.discovered_by,
            "resourceType": self.resource_type,
            "connected": self.connected,
            "account": self.account,
            "region": self.region,
        }

    def as_public_dict(self) -> dict[str, Any]:
        """Return the fields a browser needs, without the management address.

        The selector needs a name, the SVMs under it, and whether it can be acted
        on. It has no use for the address: routing happens in the handler, which
        reads it from configuration rather than from anything the browser sends.

        Leaving it out is what keeps this response answerable to every signed-in
        user. The alternative is deciding per group whether an inventory may
        include management endpoints, which is a question the panels that need the
        selector should not have to carry -- one of them is not admin-only.
        """
        public = self.as_dict()
        del public["managementAddress"]
        return public


@dataclass(frozen=True)
class Declaration:
    """A system the operator says exists, to be shown only once it answers.

    Attributes:
        platform: One of the ``PLATFORM_*`` values, or a platform this build does
            not know. An unknown platform is not an error: it is a system that
            cannot be probed yet, so it stays hidden with that as its reason.
        system_id: Stable identifier chosen by whoever declared it.
        name: Display name.
        resource_type: The platform's own term for the container, when it has one.
        management_address: Where to probe.
        secret_name: Secrets Manager secret holding the credential, when the probe
            needs one.
    """

    platform: str
    system_id: str
    name: str = ""
    resource_type: str = ""
    management_address: str = ""
    secret_name: str = ""

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Declaration | None:
        """Build a declaration from configuration, or None when unusable.

        A declaration without a platform or an identifier cannot be probed and
        cannot be told apart from another entry, so it is dropped rather than
        carried as a half-entry that fails later for a reason unrelated to the
        system itself.
        """
        platform = str(raw.get("platform") or "").strip()
        system_id = str(raw.get("systemId") or raw.get("system_id") or "").strip()
        if not platform or not system_id:
            logger.warning(
                "Ignoring a declared storage system without both platform and systemId: %r",
                raw,
            )
            return None
        return cls(
            platform=platform,
            system_id=system_id,
            name=str(raw.get("name") or system_id).strip(),
            resource_type=str(raw.get("resourceType") or raw.get("resource_type") or "").strip(),
            management_address=str(raw.get("managementAddress") or raw.get("management_address") or "").strip(),
            secret_name=str(raw.get("secretName") or raw.get("secret_name") or "").strip(),
        )


@dataclass
class Inventory:
    """What was found, and what was declared but not found.

    ``hidden`` exists so "I declared it and it is not there" has an answer. It is
    deliberately not merged into ``systems``: an entry an operator can select has
    to be one the actions can use.
    """

    systems: list[StorageSystem] = field(default_factory=list)
    hidden: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Return the inventory as the portal's dispatch response.

        ``platforms`` rather than ``systems``: the portal calls this unit a data
        platform, because it is the same choice whether the thing underneath is a
        file system, a cluster, or a container on a platform that has neither. The
        Python type stays ``StorageSystem`` since that is what it models.
        """
        return {
            "platforms": [s.as_public_dict() for s in self.systems],
            "hidden": list(self.hidden),
            "count": len(self.systems),
        }


def _name_from_tags(tags: Iterable[dict[str, Any]], fallback: str) -> str:
    """Return the ``Name`` tag, or the fallback when it is absent."""
    for tag in tags or ():
        if tag.get("Key") == "Name" and str(tag.get("Value") or "").strip():
            return str(tag["Value"]).strip()
    return fallback


def group_svms_by_file_system(records: Sequence[dict[str, Any]]) -> dict[str, tuple[str, ...]]:
    """Group SVM records from the FSx API by the file system they belong to.

    Only SVMs in a lifecycle that can serve are included. A ``CREATING`` or
    ``DELETING`` SVM offered as a scope answers with an empty list, which reads as
    an empty system rather than as a transition.
    """
    grouped: dict[str, list[str]] = {}
    for record in records:
        file_system_id = str(record.get("FileSystemId") or "")
        name = str(record.get("Name") or "")
        if not file_system_id or not name:
            continue
        if str(record.get("Lifecycle") or "") != "CREATED":
            continue
        grouped.setdefault(file_system_id, []).append(name)
    return {fs: tuple(sorted(names)) for fs, names in grouped.items()}


def discover_fsx_ontap(fsx_client: Any, account: str = "", region: str = "") -> list[StorageSystem]:
    """Enumerate FSx for ONTAP file systems and their SVMs from the control plane.

    Two calls for the whole estate, rather than one per system: the SVM listing
    already carries ``FileSystemId``, so grouping is done here instead of by
    asking per file system.

    Args:
        fsx_client: A boto3 FSx client.
        account: The account this client reads, recorded on each result.
        region: The region this client reads, recorded on each result.

    Returns:
        The available file systems. A file system that is not ``AVAILABLE`` is
        left out: its management interface is not answering, so offering it as a
        scope produces a failure that looks like a credential problem.
    """
    file_systems: list[dict[str, Any]] = []
    for page in fsx_client.get_paginator("describe_file_systems").paginate():
        file_systems.extend(page.get("FileSystems") or [])

    svm_records: list[dict[str, Any]] = []
    for page in fsx_client.get_paginator("describe_storage_virtual_machines").paginate():
        svm_records.extend(page.get("StorageVirtualMachines") or [])
    svms_by_fs = group_svms_by_file_system(svm_records)

    systems: list[StorageSystem] = []
    for fs in file_systems:
        if fs.get("FileSystemType") != "ONTAP":
            continue
        if fs.get("Lifecycle") != "AVAILABLE":
            continue
        file_system_id = str(fs.get("FileSystemId") or "")
        if not file_system_id:
            continue
        ontap = fs.get("OntapConfiguration") or {}
        addresses = ((ontap.get("Endpoints") or {}).get("Management") or {}).get("IpAddresses") or []
        systems.append(
            StorageSystem(
                platform=PLATFORM_FSX_ONTAP,
                system_id=file_system_id,
                name=_name_from_tags(fs.get("Tags") or (), file_system_id),
                management_address=str(addresses[0]) if addresses else "",
                svms=svms_by_fs.get(file_system_id, ()),
                # The management interface is reachable from inside the VPC and the
                # actions speak its API. Whether this deployment holds a credential
                # that it accepts is a separate question, answered by the action
                # rather than by the inventory -- claiming it here would mean
                # authenticating against every file system just to draw a list.
                manageable=True,
                discovered_by="fsx-control-plane",
                resource_type="file system",
                account=account,
                region=region,
            )
        )
    return sorted(systems, key=lambda s: (s.name.lower(), s.system_id))


@dataclass(frozen=True)
class DiscoveryScope:
    """One account and region to enumerate.

    An account with no role to assume is read with the caller's own credentials,
    which is how the deployment's own account is scanned without special-casing it.
    """

    region: str
    account: str = ""
    role_name: str = ""

    def label(self) -> str:
        """A short description, for reporting a scope that could not be read."""
        return f"{self.account or 'this account'}/{self.region}"


def discover_fsx_ontap_across(
    scopes: Sequence[DiscoveryScope],
    client_factory: Callable[[DiscoveryScope], Any],
    max_workers: int = 32,
) -> Inventory:
    """Enumerate every scope, keeping the scopes that failed out of the way.

    One unreachable account must not empty the inventory. A role that has not been
    created yet, a region not enabled for the account, a policy missing the FSx
    read: each of these fails one scope, and reporting the whole inventory as
    failed would hide every platform in the scopes that answered -- including the
    one the operator is connected to.

    A failed scope is recorded in ``hidden`` with the reason, in the same shape a
    declared platform that did not answer uses, so a reader asking "why is our
    other account not listed" has an answer in the response rather than in a log
    they cannot reach.

    Scopes are read concurrently, and that is not an optimisation. Measured
    2026-08-29 against the 25 regions this account has enabled: read one after
    another, a single region that did not answer -- me-central-1, a connect timeout
    under botocore's default retries -- held the walk past fifteen minutes. The
    caller is a Lambda with a thirty second timeout and a browser waiting on it, so
    one unreachable region has to cost one scope rather than the inventory. The
    per-scope bound belongs in the client the factory builds; this only stops the
    scopes from queueing behind each other.

    Args:
        scopes: The accounts and regions to read. Duplicates are collapsed.
        client_factory: Builds an FSx client for a scope. Raising is expected and
            is reported as that scope failing. It should carry short connect and
            read timeouts: a scope that hangs still occupies a worker.
        max_workers: How many scopes to read at once. High enough that an estate's
            worth of regions is one wave: with two waves, a scope that times out in
            each of them adds its bound twice, which is how a 25-region walk still
            took 29 s against a caller with a 30 s budget.

    Returns:
        Everything found, and the scopes that could not be read. Ordering does not
        depend on which scope answered first.
    """
    unique: list[DiscoveryScope] = []
    seen_scopes: set[tuple[str, str]] = set()
    for scope in scopes:
        key = (scope.account, scope.region)
        if key in seen_scopes:
            continue
        seen_scopes.add(key)
        unique.append(scope)

    def read(scope: DiscoveryScope) -> tuple[DiscoveryScope, list[StorageSystem] | Exception]:
        try:
            client = client_factory(scope)
            return scope, discover_fsx_ontap(client, account=scope.account, region=scope.region)
        except Exception as exc:  # noqa: BLE001 - one scope, not the inventory
            return scope, exc

    if not unique:
        return Inventory()

    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(unique)))) as pool:
        outcomes = list(pool.map(read, unique))

    # Merged in the order the scopes were given, not the order they answered, so two
    # runs over the same estate produce the same inventory.
    inventory = Inventory()
    seen_systems: set[str] = set()
    for scope, outcome in outcomes:
        if isinstance(outcome, Exception):
            logger.warning(
                "Discovery failed for %s: %s: %s",
                scope.label(),
                type(outcome).__name__,
                outcome,
            )
            inventory.hidden.append(
                {
                    "systemId": scope.label(),
                    "platform": PLATFORM_FSX_ONTAP,
                    "reason": f"Could not read this account and region: {type(outcome).__name__}",
                }
            )
            continue
        for system in outcome:
            # A file system ID is globally unique, so a repeat means two scopes
            # overlapped rather than two systems colliding.
            if system.system_id in seen_systems:
                continue
            seen_systems.add(system.system_id)
            inventory.systems.append(system)
    inventory.systems.sort(key=lambda s: (s.name.lower(), s.system_id))
    return inventory


def probe_declared(
    declarations: Sequence[Declaration],
    probes: dict[str, Callable[[Declaration], StorageSystem | None]],
) -> Inventory:
    """Turn declarations into entries, keeping only the ones that answered.

    Args:
        declarations: What the operator declared.
        probes: One probe per platform. A platform with no probe cannot be
            confirmed, so its declarations stay hidden with that as the reason --
            which is the honest report for a build that does not speak that
            platform's API yet.

    Returns:
        The systems that answered, and the reasons the others are absent.
    """
    inventory = Inventory()
    for declaration in declarations:
        probe = probes.get(declaration.platform)
        if probe is None:
            inventory.hidden.append(
                {
                    "systemId": declaration.system_id,
                    "platform": declaration.platform,
                    "reason": (
                        "No discovery method for this platform in this build, so it "
                        "cannot be confirmed to exist. Declared systems appear only "
                        "once something answers for them."
                    ),
                }
            )
            continue
        try:
            found = probe(declaration)
        except Exception as exc:  # noqa: BLE001 - a probe failure is a hidden entry
            logger.warning(
                "Probe for %s (%s) raised %s: %s",
                declaration.system_id,
                declaration.platform,
                type(exc).__name__,
                exc,
            )
            inventory.hidden.append(
                {
                    "systemId": declaration.system_id,
                    "platform": declaration.platform,
                    "reason": f"Discovery failed: {type(exc).__name__}",
                }
            )
            continue
        if found is None:
            inventory.hidden.append(
                {
                    "systemId": declaration.system_id,
                    "platform": declaration.platform,
                    "reason": "Did not answer discovery.",
                }
            )
            continue
        inventory.systems.append(found)
    return inventory


def build_inventory(
    discovered: Sequence[StorageSystem],
    declared: Inventory | None = None,
) -> Inventory:
    """Merge auto-discovered and confirmed declared systems into one list.

    A declared entry never replaces a discovered one. If an operator declares a
    file system the control plane already reported, the control plane's answer is
    the one kept: it was read from the resource rather than typed.
    """
    merged = Inventory(systems=list(discovered))
    if declared is None:
        return merged
    known = {s.system_id for s in merged.systems}
    for system in declared.systems:
        if system.system_id in known:
            logger.info(
                "Declared system %s is already reported by discovery; keeping the discovered entry.",
                system.system_id,
            )
            continue
        merged.systems.append(system)
        known.add(system.system_id)
    merged.hidden = list(declared.hidden)
    return merged
