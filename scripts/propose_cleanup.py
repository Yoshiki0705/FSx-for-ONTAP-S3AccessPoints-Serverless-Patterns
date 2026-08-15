#!/usr/bin/env python3
"""Propose — never perform — cleanup of the deployed demo environment.

Two jobs, in order.

1. Decide whether it is time to propose anything at all. `docs/ROADMAP.md` holds
   the open work by design ("完了した作業の履歴は git とマージ済み PR にあります.
   このファイルは未完了のものだけを持ちます"), so the open markers in it are the
   tracked backlog. While any remain, this script reports them and withholds the
   proposal: tearing down the environment that the remaining verification work
   needs is the expensive mistake here, and an FSx for ONTAP file system takes
   real time to rebuild.

2. Once the backlog is clear, inventory what is standing, price it from the AWS
   Price List API, and suggest an order — pointing at the teardown tooling that
   already exists rather than reimplementing it.

**This script never deletes anything.** It calls describe/list/get only. Deletion
belongs to the existing tools, run deliberately by a person:

  scripts/cleanup_generic_ucs.py     UC1–UC28 / SAP / FC1–FC6 stacks
  scripts/teardown-uc29-uc30.sh      UC29 / UC30 (Bedrock KB, AOSS, Athena WG)
  docs/uc29-uc30-cleanup-runbook.md  the order and the reasoning behind it

Prices come from the Price List API at run time and are printed with the
usagetype they were read from, so a wrong lookup is visible rather than silent.
Nothing here hardcodes a rate.

Usage:
    python3 scripts/propose_cleanup.py
    python3 scripts/propose_cleanup.py --anyway        # inventory despite open items
    python3 scripts/propose_cleanup.py --no-pricing    # skip the Price List API
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

# ROADMAP.md marks state with these. ✅ means done and is deliberately absent.
OPEN_MARKERS = ("📋", "⚠️")

# The Price List API only answers in us-east-1 and eu-central-1.
PRICING_REGION = "us-east-1"

# FSx DeploymentType -> the deploymentOption the Price List API uses. "2N" is the
# two-node HA pair; the "-2" suffix is the second generation. Verified against
# https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/high-availability-AZ.html,
# which pairs SINGLE_AZ_1/MULTI_AZ_1 as first-generation and SINGLE_AZ_2/
# MULTI_AZ_2 as second. A DeploymentType missing from here is reported as
# unpriced rather than guessed.
FSX_DEPLOYMENT_OPTION = {
    "SINGLE_AZ_1": "Single-AZ_2N",
    "SINGLE_AZ_2": "Single-AZ_2N-2",
    "MULTI_AZ_1": "Multi-AZ",
    "MULTI_AZ_2": "Multi-AZ-2",
}

HOURS_PER_MONTH = 730

# Ownership buckets. The account is shared, so "standing cost" and "ours to delete"
# are different questions and the report must not answer the second with the first.
OWNER_OURS = "this project"
OWNER_OTHER = "another owner — do not touch"
OWNER_SHARED = "shared — ask before touching"
OWNER_UNKNOWN = "unattributed — identify before acting"

# A resource is treated as ours when its name or tags carry one of these. They come
# from the repository's own naming: stacks are `fsxn-*`, the portal sandbox is
# `amplify-fsxns3apamplifyportal-*`, and templates tag `UseCase` and `Phase`.
OURS_NAME_MARKERS = ("fsxn-", "amplify-fsxns3apamplifyportal", "s3ap", "verify", "verification")
OURS_TAG_KEYS = ("UseCase", "Phase")


# ---------------------------------------------------------------------------
# 1. Is the backlog clear?
# ---------------------------------------------------------------------------


@dataclass
class OpenItem:
    """One unfinished entry in the roadmap."""

    section: str
    line_no: int
    text: str


def read_open_items(roadmap: Path) -> list[OpenItem]:
    """Collect the unfinished entries from the roadmap.

    Args:
        roadmap: Path to `docs/ROADMAP.md`.

    Returns:
        One entry per line carrying an open marker, tagged with the heading it
        appeared under. Empty means the tracked backlog is clear.
    """
    items: list[OpenItem] = []
    section = "(before the first heading)"
    for line_no, raw in enumerate(roadmap.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if line.startswith("#"):
            section = line.lstrip("# ").strip()
            continue
        # Only table rows and list items are entries. Prose that mentions the
        # markers — including the paragraph in ROADMAP.md explaining this very
        # rule — is documentation, and counting it inflated the backlog by one
        # the moment that paragraph was written.
        if not (line.startswith("|") or line.startswith(("- ", "* "))):
            continue
        if any(marker in line for marker in OPEN_MARKERS):
            items.append(OpenItem(section=section, line_no=line_no, text=line))
    return items


# ---------------------------------------------------------------------------
# 2. What is standing, and what does it cost?
# ---------------------------------------------------------------------------


@dataclass
class Standing:
    """A resource that costs money while it exists, whether or not it is used."""

    kind: str
    identifier: str
    detail: str
    monthly_usd: float | None = None
    # How the number was arrived at, so a reader can check it.
    price_basis: list[str] = field(default_factory=list)
    # Anything that makes deletion impossible or delayed.
    irreversible: str | None = None
    # Who the resource appears to belong to. This report used to omit it and
    # present one total, which in a shared account meant proposing the deletion of
    # a colleague's NAT gateway and VPC endpoints alongside our own resources. An
    # unattributed total is not a cleanup proposal, it is a hazard.
    owner: str = OWNER_UNKNOWN


def _unit_prices(pricing: Any, service_code: str, filters: list[dict[str, str]]) -> dict[str, tuple[float, str]]:
    """Map usagetype to (price per unit, unit) for one Price List query.

    Args:
        pricing: A boto3 `pricing` client.
        service_code: For example `AmazonFSx`.
        filters: `get_products` filters, already in TERM_MATCH form.

    Returns:
        usagetype -> (USD per unit, unit name). Empty when the query returns
        nothing, which the caller must treat as "price unknown", not as zero.
    """
    out: dict[str, tuple[float, str]] = {}
    paginator = pricing.get_paginator("get_products")
    for page in paginator.paginate(ServiceCode=service_code, Filters=filters):
        for blob in page["PriceList"]:
            product = json.loads(blob)
            usagetype = product["product"]["attributes"].get("usagetype", "")
            for term in product.get("terms", {}).get("OnDemand", {}).values():
                for dim in term["priceDimensions"].values():
                    price = float(dim["pricePerUnit"].get("USD", "0"))
                    if price:
                        out[usagetype] = (price, dim.get("unit", ""))
    return out


def price_fsx(pricing: Any, region: str) -> dict[str, tuple[float, str]]:
    """Read FSx for ONTAP unit prices for one region.

    Args:
        pricing: A boto3 `pricing` client.
        region: Region code, for example `ap-northeast-1`.

    Returns:
        usagetype -> (USD per unit, unit name).
    """
    return _unit_prices(
        pricing,
        "AmazonFSx",
        [
            {"Type": "TERM_MATCH", "Field": "regionCode", "Value": region},
            {"Type": "TERM_MATCH", "Field": "fileSystemType", "Value": "ONTAP"},
        ],
    )


def price_vpc(pricing: Any, region: str) -> dict[str, tuple[float, str]]:
    """Read NAT gateway and VPC endpoint hourly prices for one region.

    The two live under different service codes: Interface endpoints are billed
    under `AmazonVPC`, while the NAT gateway is under `AmazonEC2` in the
    `NGW:NatGateway` group. Querying only AmazonVPC returns endpoint prices and
    silently no NAT price, which reads as "NAT is free" unless the caller treats a
    missing key as unknown.

    Args:
        pricing: A boto3 `pricing` client.
        region: Region code, for example `ap-northeast-1`.

    Returns:
        usagetype -> (USD per unit, unit name), merged across both service codes.
    """
    prices = _unit_prices(
        pricing,
        "AmazonVPC",
        [{"Type": "TERM_MATCH", "Field": "regionCode", "Value": region}],
    )
    prices.update(
        _unit_prices(
            pricing,
            "AmazonEC2",
            [
                {"Type": "TERM_MATCH", "Field": "regionCode", "Value": region},
                {"Type": "TERM_MATCH", "Field": "group", "Value": "NGW:NatGateway"},
            ],
        )
    )
    return prices


def collect_fsx(session: Any, region: str, fsx_prices: dict[str, tuple[float, str]]) -> list[Standing]:
    """Inventory file systems, noting any volume that blocks deleting one.

    Args:
        session: A boto3 Session.
        region: Region to inventory.
        fsx_prices: Output of `price_fsx`. Empty means amounts are omitted.

    Returns:
        One entry per file system, with `irreversible` set when a SnapLock volume
        would block its deletion.
    """
    fsx = session.client("fsx", region_name=region)
    out: list[Standing] = []

    filesystems = []
    for page in fsx.get_paginator("describe_file_systems").paginate():
        filesystems.extend(page["FileSystems"])

    # SnapLock is the reason a "cleanup" can turn into a six-month bill: an
    # unexpired audit log volume blocks volume -> SVM -> file system deletion, and
    # the AWS API has no field for the audit log's retention, so the default
    # applies. Collected per file system so the warning names the blocker.
    blockers: dict[str, list[str]] = {}
    for page in fsx.get_paginator("describe_volumes").paginate():
        for volume in page["Volumes"]:
            snaplock = (volume.get("OntapConfiguration") or {}).get("SnaplockConfiguration") or {}
            if not snaplock:
                continue
            parts = [f"SnapLock={snaplock.get('SnaplockType', '?')}"]
            # DescribeVolumes reporting AuditLogVolume: false does not mean the
            # volume is deletable. The flag is the current designation, and AWS
            # support confirmed it is the right field for that; what blocks the
            # delete is the retention already applied to the log files, which
            # outlives the designation. Reported as-is, never as a verdict.
            parts.append(f"AuditLogVolume(FSx API)={snaplock.get('AuditLogVolume')}")
            if snaplock.get("PrivilegedDelete") == "PERMANENTLY_DISABLED":
                # Terminal: this makes an ENTERPRISE volume behave as COMPLIANCE,
                # so even a privileged delete is no longer available.
                parts.append("PrivilegedDelete=PERMANENTLY_DISABLED (terminal)")
            retention = snaplock.get("RetentionPeriod") or {}
            default = retention.get("DefaultRetention") or {}
            if default:
                parts.append(f"DefaultRetention={default.get('Value')} {default.get('Type')}")
            note = f"{volume.get('Name')} ({volume.get('VolumeId')}) " + ", ".join(parts)
            blockers.setdefault(volume["FileSystemId"], []).append(note)

    # Volumes are attributed separately from their file system. A file system can
    # belong to someone else while carrying volumes this project created — which is
    # how a SnapLock volume from our verification work ended up on a colleague's
    # file system, where it may block their deletion.
    ours_volumes: dict[str, list[str]] = {}
    for page in fsx.get_paginator("describe_volumes").paginate():
        for volume in page["Volumes"]:
            if attribute(volume.get("Name"), volume.get("Tags")) == OWNER_OURS:
                ours_volumes.setdefault(volume["FileSystemId"], []).append(str(volume.get("Name")))

    for filesystem in filesystems:
        ontap = filesystem.get("OntapConfiguration") or {}
        deployment = ontap.get("DeploymentType", "?")
        throughput = ontap.get("ThroughputCapacity") or 0
        storage_gb = filesystem.get("StorageCapacity") or 0

        monthly: float | None = None
        basis: list[str] = []
        option = FSX_DEPLOYMENT_OPTION.get(deployment)
        if option and fsx_prices:
            # Match on the deploymentOption encoded in the usagetype suffix rather
            # than reconstructing the usagetype string, which differs per region.
            storage_key = next(
                (k for k, _ in fsx_prices.items() if k.endswith(f"Storage.{_suffix(option)}:SSD")),
                None,
            )
            throughput_key = next(
                (k for k, _ in fsx_prices.items() if k.endswith(f"ThroughputCapacity.{_suffix(option)}")),
                None,
            )
            if storage_key and throughput_key:
                storage_rate, storage_unit = fsx_prices[storage_key]
                throughput_rate, throughput_unit = fsx_prices[throughput_key]
                monthly = storage_gb * storage_rate + throughput * throughput_rate
                basis = [
                    f"{storage_key} {storage_rate} / {storage_unit} x {storage_gb}",
                    f"{throughput_key} {throughput_rate} / {throughput_unit} x {throughput}",
                ]

        fs_id = filesystem["FileSystemId"]
        fs_name = next((t["Value"] for t in filesystem.get("Tags", []) if t.get("Key") == "Name"), None)
        owner = attribute(fs_name, filesystem.get("Tags"))
        ours_here = ours_volumes.get(fs_id, [])
        if owner != OWNER_OURS and ours_here:
            # Our volumes on someone else's file system: neither purely theirs nor
            # ours to delete.
            owner = OWNER_SHARED
        detail = f"{deployment}, {storage_gb} GB SSD, {throughput} MBps"
        if fs_name:
            detail = f"name={fs_name}, {detail}"
        if ours_here:
            detail += f"; {len(ours_here)} volume(s) look like ours: " + ", ".join(sorted(ours_here)[:6])

        out.append(
            Standing(
                kind="FSx for ONTAP file system",
                identifier=fs_id,
                detail=detail,
                owner=owner,
                monthly_usd=monthly,
                price_basis=basis,
                irreversible=(
                    "SnapLock volume(s) present — deletion may be blocked. Confirm "
                    "with LifecycleTransitionReason and ONTAP's snaplock.expiry_time, "
                    "not with the AuditLogVolume flag: " + "; ".join(blockers[filesystem["FileSystemId"]])
                    if filesystem["FileSystemId"] in blockers
                    else None
                ),
            )
        )
    return out


def attribute(name: str | None, tags: list[dict[str, str]] | None = None) -> str:
    """Guess who a resource belongs to, from its name and tags.

    A guess, deliberately labelled as one. In a shared account the safe default is
    "identify before acting" rather than "ours", so an unrecognised name is never
    reported as this project's.

    Args:
        name: The resource's Name tag or identifier, if any.
        tags: Its tags, as returned by the EC2/FSx APIs.

    Returns:
        One of the `OWNER_*` constants.
    """
    keys = {t.get("Key", "") for t in (tags or [])}
    if keys & set(OURS_TAG_KEYS):
        return OWNER_OURS
    lowered = (name or "").lower()
    if not lowered:
        return OWNER_UNKNOWN
    if any(marker in lowered for marker in OURS_NAME_MARKERS):
        return OWNER_OURS
    return OWNER_UNKNOWN


def _suffix(deployment_option: str) -> str:
    """The usagetype fragment for a Price List deploymentOption.

    Args:
        deployment_option: For example `Single-AZ_2N` or `Multi-AZ-2`.

    Returns:
        The abbreviation the usagetype uses (`SAZ_2N`, `MAZ2`).
    """
    mapping = {
        "Single-AZ_2N": "SAZ_2N",
        "Single-AZ_2N-2": "SAZ_2N2",
        "Multi-AZ": "MAZ",
        "Multi-AZ-2": "MAZ2",
    }
    return mapping[deployment_option]


def collect_vpc(session: Any, region: str, vpc_prices: dict[str, tuple[float, str]]) -> list[Standing]:
    """Inventory NAT gateways and Interface VPC endpoints.

    Both bill per hour whether or not anything uses them.

    Args:
        session: A boto3 Session.
        region: Region to inventory.
        vpc_prices: Output of `price_vpc`. Empty means amounts are omitted.

    Returns:
        One entry per NAT gateway, plus one aggregate entry for the Interface
        endpoints because they are priced per ENI rather than per endpoint.
    """
    ec2 = session.client("ec2", region_name=region)
    out: list[Standing] = []

    # A VPC's Name tag is often the only clue to who made it.
    vpc_names: dict[str, str] = {}
    for page in ec2.get_paginator("describe_vpcs").paginate():
        for vpc in page["Vpcs"]:
            name = next((t["Value"] for t in vpc.get("Tags", []) if t.get("Key") == "Name"), None)
            if name:
                vpc_names[vpc["VpcId"]] = name

    # Endswith, not `in`: "RegionalNatGateway-Hours" also contains
    # "NatGateway-Hours" and is a different product.
    nat_key = next((k for k in vpc_prices if k.endswith("-NatGateway-Hours")), None)
    endpoint_key = next((k for k in vpc_prices if "VpcEndpoint-Hours" in k), None)

    for page in ec2.get_paginator("describe_nat_gateways").paginate(
        Filters=[{"Name": "state", "Values": ["available"]}]
    ):
        for nat in page["NatGateways"]:
            rate = vpc_prices.get(nat_key) if nat_key else None
            nat_name = next((t["Value"] for t in nat.get("Tags", []) if t.get("Key") == "Name"), None)
            out.append(
                Standing(
                    kind="NAT gateway",
                    identifier=nat["NatGatewayId"],
                    detail=f"vpc={nat.get('VpcId')}" + (f", name={nat_name}" if nat_name else ""),
                    owner=attribute(nat_name, nat.get("Tags")),
                    monthly_usd=rate[0] * HOURS_PER_MONTH if rate else None,
                    price_basis=([f"{nat_key} {rate[0]} / {rate[1]} x {HOURS_PER_MONTH} h"] if rate else []),
                )
            )

    interface_endpoints = []
    for page in ec2.get_paginator("describe_vpc_endpoints").paginate():
        interface_endpoints += [e for e in page["VpcEndpoints"] if e.get("VpcEndpointType") == "Interface"]
    # Grouped per VPC, not per account. One combined total hid that every endpoint
    # here lives in a VPC this project did not create, which is the difference
    # between a saving and someone else's outage.
    rate = vpc_prices.get(endpoint_key) if endpoint_key else None
    by_vpc: dict[str, list[dict[str, Any]]] = {}
    for endpoint in interface_endpoints:
        by_vpc.setdefault(endpoint.get("VpcId", "?"), []).append(endpoint)

    for vpc_id, endpoints in sorted(by_vpc.items()):
        # Priced per ENI, so a multi-subnet endpoint costs more than one endpoint.
        enis = sum(max(1, len(e.get("SubnetIds") or [])) for e in endpoints)
        names = ", ".join(sorted(e.get("ServiceName", "?").split(".")[-1] for e in endpoints))
        tags = [t for e in endpoints for t in (e.get("Tags") or [])]
        tag_name = next((t["Value"] for t in tags if t.get("Key") == "Name"), None)
        vpc_name = vpc_names.get(vpc_id)
        out.append(
            Standing(
                kind="Interface VPC endpoints",
                identifier=f"{vpc_id}: {len(endpoints)} endpoint(s), {enis} ENI(s)",
                detail=names
                + (f" | vpc name={vpc_name}" if vpc_name else "")
                + (f" | a tag reads {tag_name}" if tag_name else ""),
                owner=attribute(tag_name or vpc_name, tags),
                monthly_usd=rate[0] * HOURS_PER_MONTH * enis if rate else None,
                price_basis=(
                    [f"{endpoint_key} {rate[0]} / {rate[1]} x {HOURS_PER_MONTH} h x {enis} ENI"] if rate else []
                ),
            )
        )
    return out


def collect_always_on(session: Any, region: str) -> list[Standing]:
    """Inventory resources that are cheap to switch off and easy to forget.

    Left unpriced on purpose: cost depends on task size and running hours, and a
    made-up number would be worse than none.

    Args:
        session: A boto3 Session.
        region: Region to inventory.

    Returns:
        ECS services with a non-zero desired count, and online Transfer Family
        servers.
    """
    out: list[Standing] = []

    ecs = session.client("ecs", region_name=region)
    for page in ecs.get_paginator("list_clusters").paginate():
        for cluster in page["clusterArns"]:
            arns: list[str] = []
            for svc_page in ecs.get_paginator("list_services").paginate(cluster=cluster):
                arns += svc_page["serviceArns"]
            if not arns:
                continue
            described = ecs.describe_services(cluster=cluster, services=arns[:10])["services"]
            for service in described:
                if service.get("desiredCount", 0) > 0:
                    out.append(
                        Standing(
                            kind="ECS service (desiredCount > 0)",
                            identifier=service["serviceName"],
                            owner=attribute(service["serviceName"]),
                            detail=f"cluster={cluster.split('/')[-1]}, desired={service['desiredCount']}",
                        )
                    )

    transfer = session.client("transfer", region_name=region)
    for page in transfer.get_paginator("list_servers").paginate():
        for server in page["Servers"]:
            if server.get("State") == "ONLINE":
                out.append(
                    Standing(
                        kind="Transfer Family server",
                        identifier=server["ServerId"],
                        owner=attribute(server.get("Tags", [{}])[0].get("Value")),
                        detail=f"protocols={','.join(server.get('IdentityProviderType', '') or '') or '?'}",
                    )
                )

    return out


def credit_runway(session: Any) -> str:
    """Describe how long the remaining promotional credit lasts at the current burn.

    This is the number that decides whether cleanup is urgent, and it is invisible
    in Cost Explorer's default view: net cost here reads as a couple of dollars a
    month because credits absorb the usage. Gross usage was ~64x the net figure at
    the time of writing, so "the bill is tiny" and "nothing is being consumed" are
    different statements.

    Args:
        session: A boto3 Session.

    Returns:
        A human-readable line, or an explanation of why it could not be computed.
        Never raises: a billing permission gap must not hide the inventory.
    """
    try:
        explorer = session.client("ce", region_name="us-east-1")
        account = session.client("sts").get_caller_identity()["Account"]

        today = date.today()
        start = today.replace(day=1)
        # Usage and credit are separate RECORD_TYPEs on the same query, so one call
        # gives both the burn and the offset actually applied.
        response = explorer.get_cost_and_usage(
            TimePeriod={"Start": start.isoformat(), "End": today.isoformat()},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "RECORD_TYPE"}],
            Filter={"Dimensions": {"Key": "LINKED_ACCOUNT", "Values": [account]}},
        )
        usage = 0.0
        applied_credit = 0.0
        for period in response["ResultsByTime"]:
            for group in period["Groups"]:
                amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                if group["Keys"][0] == "Usage":
                    usage += amount
                elif group["Keys"][0] == "Credit":
                    applied_credit += amount

        days = max((today - start).days, 1)
        per_day = usage / days
        if per_day <= 0:
            return "Credit runway: no usage recorded this month yet."
        return (
            f"Gross usage this month: ${usage:,.2f} over {days} day(s) "
            f"= ${per_day:,.2f}/day (~${per_day * 30:,.0f}/month).\n"
            f"  Credit applied this month: ${-applied_credit:,.2f}. Net cost is the "
            "difference, so a small net figure does not mean small consumption.\n"
            "  For the remaining balance and its expiry, read the Credits page or\n"
            "  `get_credits`; divide it by the per-day figure above for the runway."
        )
    except Exception as exc:  # noqa: BLE001 — billing access is optional here
        return f"Credit runway: not available ({type(exc).__name__}). Needs ce:GetCostAndUsage."


def collect_stacks(session: Any, region: str) -> list[str]:
    """List top-level CloudFormation stacks in a settled, deployed state.

    Args:
        session: A boto3 Session.
        region: Region to inventory.

    Returns:
        Sorted stack names, excluding nested stacks.
    """
    cfn = session.client("cloudformation", region_name=region)
    wanted = {
        "CREATE_COMPLETE",
        "UPDATE_COMPLETE",
        "UPDATE_ROLLBACK_COMPLETE",
        "ROLLBACK_COMPLETE",
        "IMPORT_COMPLETE",
    }
    names: list[str] = []
    for page in cfn.get_paginator("list_stacks").paginate():
        for stack in page["StackSummaries"]:
            if stack["StackStatus"] in wanted and not stack.get("ParentId"):
                names.append(stack["StackName"])
    return sorted(names)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

IRREVERSIBLE_WARNING = """
Before deleting anything, note what cannot be undone. Verifying afterwards is
not a recovery path for any of these:

  * A SnapLock volume cannot be un-SnapLocked. `snaplock.type` is creation-time
    only, and unexpired WORM files block volume -> SVM -> file system deletion.
  * A SnapLock audit log volume blocks its parent for a minimum of six months.
    The AWS API has no field for the audit log's retention, so the default
    applies. There is no route to early deletion short of closing the account.
  * A locked snapshot's expiry can be extended, never shortened or released.
  * `snapshot_locking_enabled` cannot be turned off once on.
  * S3 Object Lock in COMPLIANCE mode cannot be shortened or removed.

DeleteVolume can also return success and quietly do nothing: with unexpired WORM
content the volume moves to DELETING and returns to CREATED a minute later.
Judge by Lifecycle after the fact, not by the response, and do not retry with
more flags.
"""

SUGGESTED_ORDER = """
Suggested order — run these yourself, deliberately. This script does not.

  1. Disable the EventBridge schedules first, so nothing recreates work while
     the rest is coming down.
  2. Set any ECS service desiredCount to 0 (FPolicy server) — reversible, and
     it stops the largest per-hour item that is not the file system.
  3. UC29 / UC30 first, because their Bedrock KB, OpenSearch Serverless
     collection and Athena WorkGroup have an order that the generic tool does
     not know:  bash scripts/teardown-uc29-uc30.sh
  4. The remaining UC stacks:  python3 scripts/cleanup_generic_ucs.py --all
     (add --dry-run first; it handles Athena WorkGroups, versioned buckets, VPC
     endpoint SG rules and DELETE_FAILED repair)
  5. Interface VPC endpoints and the NAT gateway, once nothing needs egress.
  6. The FSx for ONTAP file system last, and only if no verification work still
     needs it. Rebuilding takes far longer than deleting.

The reasoning behind steps 3 and 4 is in docs/uc29-uc30-cleanup-runbook.md.
"""


def report(standing: list[Standing], stacks: list[str], runway: str = "") -> None:
    """Print the inventory, the estimate and the warnings.

    Args:
        standing: Resources found, priced or not.
        stacks: Stack names from `collect_stacks`.
        runway: Output of `credit_runway`, or empty to omit the section.
    """
    print("\n=== Standing resources, grouped by who appears to own them ===\n")
    print("  Attribution is a guess from names and tags. It exists because this is a")
    print("  shared account: an unattributed total invites deleting someone else's")
    print("  resources. Confirm before acting on anything not marked as ours.\n")

    ours_total = 0.0
    for bucket in (OWNER_OURS, OWNER_SHARED, OWNER_UNKNOWN, OWNER_OTHER):
        items = [i for i in standing if i.owner == bucket]
        if not items:
            continue
        subtotal = sum(i.monthly_usd for i in items if i.monthly_usd is not None)
        unpriced = sum(1 for i in items if i.monthly_usd is None)
        if bucket == OWNER_OURS:
            ours_total = subtotal
        print(f"--- {bucket}: ${subtotal:,.2f}/month" + (f" + {unpriced} unpriced" if unpriced else ""))
        for item in items:
            amount = f"${item.monthly_usd:>10,.2f}/mo" if item.monthly_usd is not None else "     (not priced)"
            print(f"{amount}  {item.kind}: {item.identifier}")
            print(f"{'':17}  {item.detail}")
            for line in item.price_basis:
                print(f"{'':17}    from {line}")
            if item.irreversible:
                print(f"{'':17}  !! {item.irreversible}")
        print()

    print(f"  Attributable to this project: ${ours_total:,.2f}/month")
    print("  Excludes request, data transfer and per-invocation charges, which stop")
    print("  on their own when the workload stops. Standing egress does not: measure")
    print("  it per resource (CloudWatch NAT BytesOutToDestination, VPN TunnelDataOut)")
    print("  before blaming an endpoint for a data transfer line on the bill.")

    print(f"\n=== Credit and burn ===\n\n  {runway}\n")
    print(f"=== CloudFormation stacks in a deployed state: {len(stacks)} ===\n")
    for name in stacks:
        print(f"  {name}")

    blocked = [i for i in standing if i.irreversible]
    if blocked:
        print("\n=== Deletion is currently blocked ===\n")
        for item in blocked:
            print(f"  {item.kind} {item.identifier}: {item.irreversible}")

    print(IRREVERSIBLE_WARNING)
    print(SUGGESTED_ORDER)


def main(argv: list[str] | None = None) -> int:
    """Report the backlog and, when it is clear, propose cleanup.

    Args:
        argv: Command-line arguments. `None` reads `sys.argv`.

    Returns:
        Always 0. This is a report; there is no failure condition to signal, and
        an open backlog is the normal state.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roadmap", type=Path, default=REPO_ROOT / "docs" / "ROADMAP.md")
    parser.add_argument("--region", default="ap-northeast-1")
    parser.add_argument(
        "--anyway",
        action="store_true",
        help="Inventory even while roadmap items are open",
    )
    parser.add_argument(
        "--no-pricing",
        action="store_true",
        help="Skip the Price List API; report resources without amounts",
    )
    args = parser.parse_args(argv)

    if not args.roadmap.exists():
        print(f"Roadmap not found: {args.roadmap}")
        return 0

    open_items = read_open_items(args.roadmap)
    # A roadmap passed with --roadmap need not live under the repository, so
    # relative_to would raise rather than shorten.
    try:
        shown = args.roadmap.relative_to(REPO_ROOT)
    except ValueError:
        shown = args.roadmap
    print(f"=== Tracked backlog in {shown} ===\n")
    if not open_items:
        print("  No open items.\n")
    else:
        current = None
        for item in open_items:
            if item.section != current:
                current = item.section
                print(f"  {current}")
            print(f"    L{item.line_no}: {item.text[:110]}")
        print(f"\n  {len(open_items)} open item(s).")

    if open_items and not args.anyway:
        print(
            "\nWithholding the cleanup proposal. The remaining work needs this\n"
            "environment, and an FSx for ONTAP file system is slow to rebuild.\n"
            "Re-run with --anyway to see the inventory regardless."
        )
        return 0

    try:
        import boto3
    except ImportError:
        print("\nboto3 is not available, so nothing can be inventoried.")
        return 0

    session = boto3.Session()
    fsx_prices: dict[str, tuple[float, str]] = {}
    vpc_prices: dict[str, tuple[float, str]] = {}
    if not args.no_pricing:
        pricing = session.client("pricing", region_name=PRICING_REGION)
        try:
            fsx_prices = price_fsx(pricing, args.region)
            vpc_prices = price_vpc(pricing, args.region)
        except Exception as exc:  # noqa: BLE001 — a pricing failure must not hide the inventory
            print(f"\nPrice List lookup failed ({type(exc).__name__}: {exc}).")
            print("Reporting resources without amounts rather than guessing rates.")

    standing = (
        collect_fsx(session, args.region, fsx_prices)
        + collect_vpc(session, args.region, vpc_prices)
        + collect_always_on(session, args.region)
    )
    report(standing, collect_stacks(session, args.region), credit_runway(session))
    return 0


if __name__ == "__main__":
    sys.exit(main())
