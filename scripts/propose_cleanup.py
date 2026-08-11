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
            # volume is deletable. ONTAP's read-only `snaplock.is_audit_log` is
            # the authority, and clearing the SVM-level designation does not
            # change it, so this flag is reported as-is and never as a verdict.
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

        out.append(
            Standing(
                kind="FSx for ONTAP file system",
                identifier=filesystem["FileSystemId"],
                detail=f"{deployment}, {storage_gb} GB SSD, {throughput} MBps",
                monthly_usd=monthly,
                price_basis=basis,
                irreversible=(
                    "SnapLock volume(s) present — deletion may be blocked. Confirm "
                    "with ONTAP's snaplock.is_audit_log and snaplock.expiry_time, "
                    "not with the FSx flag: " + "; ".join(blockers[filesystem["FileSystemId"]])
                    if filesystem["FileSystemId"] in blockers
                    else None
                ),
            )
        )
    return out


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

    # Endswith, not `in`: "RegionalNatGateway-Hours" also contains
    # "NatGateway-Hours" and is a different product.
    nat_key = next((k for k in vpc_prices if k.endswith("-NatGateway-Hours")), None)
    endpoint_key = next((k for k in vpc_prices if "VpcEndpoint-Hours" in k), None)

    for page in ec2.get_paginator("describe_nat_gateways").paginate(
        Filters=[{"Name": "state", "Values": ["available"]}]
    ):
        for nat in page["NatGateways"]:
            rate = vpc_prices.get(nat_key) if nat_key else None
            out.append(
                Standing(
                    kind="NAT gateway",
                    identifier=nat["NatGatewayId"],
                    detail=f"vpc={nat.get('VpcId')}",
                    monthly_usd=rate[0] * HOURS_PER_MONTH if rate else None,
                    price_basis=([f"{nat_key} {rate[0]} / {rate[1]} x {HOURS_PER_MONTH} h"] if rate else []),
                )
            )

    interface_endpoints = []
    for page in ec2.get_paginator("describe_vpc_endpoints").paginate():
        interface_endpoints += [e for e in page["VpcEndpoints"] if e.get("VpcEndpointType") == "Interface"]
    if interface_endpoints:
        rate = vpc_prices.get(endpoint_key) if endpoint_key else None
        # Priced per ENI, so a multi-subnet endpoint costs more than one endpoint.
        enis = sum(max(1, len(e.get("SubnetIds") or [])) for e in interface_endpoints)
        names = ", ".join(sorted(e.get("ServiceName", "?").split(".")[-1] for e in interface_endpoints))
        out.append(
            Standing(
                kind="Interface VPC endpoints",
                identifier=f"{len(interface_endpoints)} endpoint(s), {enis} ENI(s)",
                detail=names,
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
                        detail=f"protocols={','.join(server.get('IdentityProviderType', '') or '') or '?'}",
                    )
                )

    return out


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


def report(standing: list[Standing], stacks: list[str]) -> None:
    """Print the inventory, the estimate and the warnings.

    Args:
        standing: Resources found, priced or not.
        stacks: Stack names from `collect_stacks`.
    """
    print("\n=== Standing resources ===\n")
    total = 0.0
    unpriced: list[Standing] = []
    for item in standing:
        if item.monthly_usd is None:
            unpriced.append(item)
            amount = "     (not priced)"
        else:
            total += item.monthly_usd
            amount = f"${item.monthly_usd:>10,.2f}/mo"
        print(f"{amount}  {item.kind}: {item.identifier}")
        print(f"{'':17}  {item.detail}")
        for line in item.price_basis:
            print(f"{'':17}    from {line}")
        if item.irreversible:
            print(f"{'':17}  !! {item.irreversible}")

    print(f"\n  Priced subtotal: ${total:,.2f}/month")
    if unpriced:
        print(f"  {len(unpriced)} item(s) not priced — usage-dependent, so no number is given:")
        for item in unpriced:
            print(f"    - {item.kind}: {item.identifier}")
    print("\n  Excludes request, data transfer and per-invocation charges, which")
    print("  stop on their own when the workload stops.")

    print(f"\n=== CloudFormation stacks in a deployed state: {len(stacks)} ===\n")
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
    report(standing, collect_stacks(session, args.region))
    return 0


if __name__ == "__main__":
    sys.exit(main())
