#!/usr/bin/env python3
"""Explain what a VPC-attached portal Lambda can and cannot reach.

Written after a failure that cost a long time to understand. The containment
ledger write hung until the function was killed, sixty seconds after ONTAP had
already accepted the block, so a successful containment was reported to the
caller as a timeout.

The cause is a combination that looks fine in the console: the subnet's default
route is an internet gateway, and there is even a NAT gateway in the VPC. But a
Lambda ENI has no public IP, so an internet gateway route gives it no egress at
all — and the NAT is only reachable from a subnet whose route table points at it.
The function could reach Secrets Manager purely because that service has an
interface endpoint. DynamoDB had no path.

This script reads the actual route tables and endpoints and says which AWS
services the function can reach, rather than leaving it to be inferred.

Usage
    python3 scripts/portal-probes/diagnose_vpc_egress.py --function ArpResponseFun
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).parent))
from _common import find_function, redact  # noqa: E402

# Services the portal's VPC functions call from inside the function, so they need
# a path out of the subnet.
#
# CloudWatch Logs is deliberately absent. Lambda delivers a function's logs
# through the service itself rather than from the function's ENI, so a VPC
# endpoint for Logs is not required and listing it here produced a confident
# recommendation to add an endpoint that would change nothing. Containers in a
# private subnet — the FPolicy server on Fargate, for instance — do need one,
# which is where the confusion comes from.
NEEDED = {
    "dynamodb": "containment block ledger — without it nothing expires",
    "secretsmanager": "ONTAP credentials — without it no action runs at all",
    "s3": "audit log and S3 Access Point reads",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--function", default="ArpResponseFun", help="name fragment of the VPC Lambda")
    parser.add_argument("--region", default="ap-northeast-1")
    args = parser.parse_args()

    lam = boto3.client("lambda", region_name=args.region)
    ec2 = boto3.client("ec2", region_name=args.region)

    name = find_function(args.function, args.region)
    config = lam.get_function_configuration(FunctionName=name)
    vpc = config.get("VpcConfig") or {}
    subnet_ids = vpc.get("SubnetIds") or []

    print(f"function: {name.split('-')[-1]}")
    if not subnet_ids:
        print("  not attached to a VPC, so it reaches AWS services over the public internet")
        return 0
    print(f"  subnets: {len(subnet_ids)}   security groups: {len(vpc.get('SecurityGroupIds') or [])}")

    vpc_id = vpc.get("VpcId") or ec2.describe_subnets(SubnetIds=subnet_ids)["Subnets"][0]["VpcId"]

    endpoints = ec2.describe_vpc_endpoints(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])["VpcEndpoints"]
    interface_services = {
        e["ServiceName"].rsplit(".", 1)[-1]
        for e in endpoints
        if e["VpcEndpointType"] == "Interface" and e["State"] == "available"
    }
    gateway_by_service = {
        e["ServiceName"].rsplit(".", 1)[-1]: set(e.get("RouteTableIds") or [])
        for e in endpoints
        if e["VpcEndpointType"] == "Gateway" and e["State"] == "available"
    }

    print("\nroutes per subnet:")
    reachable_via_nat = True
    subnet_route_tables: set[str] = set()
    for subnet_id in subnet_ids:
        tables = ec2.describe_route_tables(Filters=[{"Name": "association.subnet-id", "Values": [subnet_id]}])[
            "RouteTables"
        ]
        note = ""
        if not tables:
            tables = ec2.describe_route_tables(
                Filters=[
                    {"Name": "vpc-id", "Values": [vpc_id]},
                    {"Name": "association.main", "Values": ["true"]},
                ]
            )["RouteTables"]
            note = " (main route table, no explicit association)"

        for table in tables:
            subnet_route_tables.add(table["RouteTableId"])
            default = next((r for r in table["Routes"] if r.get("DestinationCidrBlock") == "0.0.0.0/0"), None)
            target = "none"
            if default:
                target = default.get("NatGatewayId") or default.get("GatewayId") or "?"
            print(f"  {subnet_id}{note}\n     route table   {table['RouteTableId']}\n     default route -> {target}")
            if target.startswith("igw-"):
                reachable_via_nat = False
                print(
                    "     a Lambda ENI has no public IP, so this route provides no egress;\n"
                    "     only VPC endpoints are reachable from here"
                )
            elif target.startswith("nat-"):
                print("     egress via NAT, so any AWS service is reachable")
            else:
                print("     no default route, so only VPC endpoints are reachable")
                reachable_via_nat = False

    print("\nservice reachability:")
    problems = 0
    for service, why in sorted(NEEDED.items()):
        if reachable_via_nat:
            verdict, detail = "ok", "via NAT"
        elif service in interface_services:
            verdict, detail = "ok", "interface endpoint"
        elif service in gateway_by_service:
            covered = subnet_route_tables & gateway_by_service[service]
            if covered:
                verdict, detail = "ok", "gateway endpoint on this subnet's route table"
            else:
                verdict, detail = "FAIL", ("gateway endpoint exists but is not attached to this subnet's route table")
        else:
            verdict, detail = "FAIL", "no endpoint and no NAT route"

        if verdict != "ok":
            problems += 1
        print(f"  {verdict:4}  {service:16} {detail}")
        if verdict != "ok":
            print(f"        needed for: {why}")

    if problems:
        print(
            f"\n{problems} service(s) unreachable. A call to one of these will hang until the\n"
            "function times out, which surfaces as the whole action failing even when the\n"
            "part that mattered already succeeded.\n\n"
            "For DynamoDB, add a gateway endpoint by setting vpcRouteTableIds in\n"
            "portal-config.ts to the route table IDs printed above. Gateway endpoints\n"
            "carry no hourly or data processing charge."
        )
        return 1

    print("\nVPC EGRESS: PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001
        # Report the exception type rather than guessing at a cause: an earlier
        # version of this workflow misread an IndexError as an HTTP 404.
        sys.exit(redact(f"{type(e).__name__}: {e}"))
