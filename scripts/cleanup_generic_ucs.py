#!/usr/bin/env python3
"""
Cleanup generic UC demo stacks.

Handles:
  - Athena WorkGroup recursive deletion
  - Versioned S3 bucket two-phase emptying + removal
  - VPC Endpoint Security Group inbound rule revocation
  - CloudFormation stack deletion + polling

Usage:
    python3 scripts/cleanup_generic_ucs.py UC1 UC2 UC3 ...
    python3 scripts/cleanup_generic_ucs.py --all
    python3 scripts/cleanup_generic_ucs.py --dry-run UC1 UC5

Environment variables:
    ACCOUNT_ID  - AWS account ID (auto-resolved via STS if not set)
    REGION      - AWS region (default: ap-northeast-1)
    VPC_ENDPOINT_SG - VPC Endpoint Security Group ID (optional, for auto-revoke)
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

import boto3
from botocore.exceptions import ClientError

# ---------------------------------------------------------------------------
# UC directory mapping
# ---------------------------------------------------------------------------
UC_DIR_MAP: dict[str, str] = {
    "UC1": "legal-compliance",
    "UC2": "financial-idp",
    "UC3": "manufacturing-analytics",
    "UC4": "media-vfx",
    "UC5": "healthcare-dicom",
    "UC6": "semiconductor-eda",
    "UC7": "genomics-pipeline",
    "UC8": "energy-seismic",
    "UC9": "autonomous-driving",
    "UC10": "construction-bim",
    "UC11": "retail-catalog",
    "UC12": "logistics-ocr",
    "UC13": "education-research",
    "UC14": "insurance-claims",
    "UC15": "defense-satellite",
    "UC16": "government-archives",
    "UC17": "smart-city-geospatial",
}

ALL_UCS = list(UC_DIR_MAP.keys())

# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------


@dataclass
class CleanupResult:
    """Track cleanup results for a single stack."""

    stack_name: str
    uc_label: str
    success: bool = True
    steps_completed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core cleanup functions
# ---------------------------------------------------------------------------


def resolve_account_id(sts_client) -> str:
    """Resolve AWS account ID from STS."""
    resp = sts_client.get_caller_identity()
    return resp["Account"]


def delete_athena_workgroup(
    athena_client, workgroup: str, region: str, *, dry_run: bool = False
) -> Optional[str]:
    """Delete Athena WorkGroup with --recursive-delete-option.

    Returns error message on failure, None on success.
    """
    try:
        athena_client.get_work_group(WorkGroup=workgroup)
    except ClientError as e:
        if e.response["Error"]["Code"] == "InvalidRequestException":
            return None  # WorkGroup doesn't exist
        return f"Athena WorkGroup check failed: {e}"

    if dry_run:
        print(f"  [DRY-RUN] Would delete Athena WorkGroup: {workgroup}")
        return None

    print(f"  Deleting Athena WorkGroup: {workgroup} (recursive)")
    try:
        athena_client.delete_work_group(
            WorkGroup=workgroup, RecursiveDeleteOption=True
        )
    except ClientError as e:
        return f"Athena WorkGroup delete failed: {e}"
    return None


def empty_versioned_bucket(
    s3_client, bucket: str, region: str, *, dry_run: bool = False
) -> Optional[str]:
    """Empty a versioned S3 bucket (objects + versions + delete markers) then remove it.

    Returns error message on failure, None on success.
    """
    # Check if bucket exists
    try:
        s3_client.head_bucket(Bucket=bucket)
    except ClientError:
        return None  # Bucket doesn't exist

    if dry_run:
        # Count objects for dry-run report
        try:
            paginator = s3_client.get_paginator("list_object_versions")
            total_versions = 0
            total_markers = 0
            for page in paginator.paginate(Bucket=bucket):
                total_versions += len(page.get("Versions", []))
                total_markers += len(page.get("DeleteMarkers", []))
            print(
                f"  [DRY-RUN] Would empty bucket: {bucket} "
                f"({total_versions} versions, {total_markers} delete markers)"
            )
        except ClientError as e:
            print(f"  [DRY-RUN] Would empty bucket: {bucket} (count failed: {e})")
        return None

    print(f"  Emptying bucket: {bucket}")
    try:
        # Delete all object versions
        paginator = s3_client.get_paginator("list_object_versions")
        for page in paginator.paginate(Bucket=bucket):
            # Delete versions
            versions = page.get("Versions", [])
            if versions:
                delete_objects = [
                    {"Key": v["Key"], "VersionId": v["VersionId"]} for v in versions
                ]
                s3_client.delete_objects(
                    Bucket=bucket, Delete={"Objects": delete_objects, "Quiet": True}
                )

            # Delete markers
            markers = page.get("DeleteMarkers", [])
            if markers:
                delete_objects = [
                    {"Key": m["Key"], "VersionId": m["VersionId"]} for m in markers
                ]
                s3_client.delete_objects(
                    Bucket=bucket, Delete={"Objects": delete_objects, "Quiet": True}
                )

        # Remove the bucket itself
        s3_client.delete_bucket(Bucket=bucket)
        print(f"  Bucket deleted: {bucket}")
    except ClientError as e:
        return f"Bucket cleanup failed ({bucket}): {e}"
    return None


def revoke_vpc_endpoint_sg_rule(
    ec2_client,
    vpc_endpoint_sg: str,
    lambda_sg: str,
    region: str,
    *,
    dry_run: bool = False,
) -> Optional[str]:
    """Revoke inbound rule from VPC Endpoint SG that allows Lambda SG.

    Returns error message on failure, None on success.
    """
    if dry_run:
        print(
            f"  [DRY-RUN] Would revoke VPC Endpoint SG rule: "
            f"{vpc_endpoint_sg} ← {lambda_sg}"
        )
        return None

    print(f"  Revoking VPC Endpoint SG rule for Lambda SG: {lambda_sg}")
    try:
        ec2_client.revoke_security_group_ingress(
            GroupId=vpc_endpoint_sg,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 443,
                    "ToPort": 443,
                    "UserIdGroupPairs": [{"GroupId": lambda_sg}],
                }
            ],
        )
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "InvalidPermission.NotFound":
            # Rule already removed — not an error
            print(f"  Rule already removed (not found).")
            return None
        return f"VPC Endpoint SG revoke failed: {e}"
    return None


def get_lambda_sg_from_stack(
    cfn_client, stack_name: str
) -> Optional[str]:
    """Get Lambda Security Group physical ID from a CloudFormation stack."""
    try:
        resp = cfn_client.describe_stack_resource(
            StackName=stack_name, LogicalResourceId="LambdaSecurityGroup"
        )
        physical_id = resp["StackResourceDetail"]["PhysicalResourceId"]
        return physical_id if physical_id and physical_id != "None" else None
    except ClientError:
        return None


def delete_cfn_stack(
    cfn_client, stack_name: str, *, dry_run: bool = False
) -> Optional[str]:
    """Initiate CloudFormation stack deletion.

    Returns error message on failure, None on success.
    """
    if dry_run:
        print(f"  [DRY-RUN] Would delete stack: {stack_name}")
        return None

    print(f"  Deleting stack: {stack_name}")
    try:
        cfn_client.delete_stack(StackName=stack_name)
    except ClientError as e:
        return f"delete-stack failed: {e}"
    return None


def poll_stack_deletion(
    cfn_client,
    stack_name: str,
    *,
    timeout: int = 1800,
    interval: int = 15,
) -> Optional[str]:
    """Poll until stack reaches DELETE_COMPLETE or fails.

    Returns error message on failure/timeout, None on success.
    """
    elapsed = 0
    while elapsed < timeout:
        try:
            resp = cfn_client.describe_stacks(StackName=stack_name)
            stacks = resp.get("Stacks", [])
            if not stacks:
                return None  # Stack gone
            status = stacks[0]["StackStatus"]
            if status == "DELETE_COMPLETE":
                return None
            if status == "DELETE_FAILED":
                reason = stacks[0].get("StackStatusReason", "unknown")
                return f"Stack {stack_name} DELETE_FAILED: {reason}"
            # Still in progress
            time.sleep(interval)
            elapsed += interval
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if "does not exist" in str(e) or error_code == "ValidationError":
                return None  # Stack deleted
            return f"Poll error: {e}"
    return f"Timeout ({timeout}s) waiting for {stack_name} deletion"


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------


def cleanup_stack(
    stack_name: str,
    uc_label: str,
    account_id: str,
    region: str,
    vpc_endpoint_sg: Optional[str],
    *,
    dry_run: bool = False,
    wait: bool = False,
    session: Optional[boto3.Session] = None,
) -> CleanupResult:
    """Run full cleanup sequence for a single stack."""
    result = CleanupResult(stack_name=stack_name, uc_label=uc_label)

    sess = session or boto3.Session(region_name=region)
    cfn_client = sess.client("cloudformation", region_name=region)
    s3_client = sess.client("s3", region_name=region)
    athena_client = sess.client("athena", region_name=region)
    ec2_client = sess.client("ec2", region_name=region)

    # Check if stack exists
    try:
        resp = cfn_client.describe_stacks(StackName=stack_name)
        stacks = resp.get("Stacks", [])
        if not stacks:
            print(f"  Stack not found (already deleted). Skipping.")
            result.steps_completed.append("skip:not_found")
            return result
        stack_status = stacks[0]["StackStatus"]
    except ClientError as e:
        if "does not exist" in str(e):
            print(f"  Stack not found (already deleted). Skipping.")
            result.steps_completed.append("skip:not_found")
            return result
        result.success = False
        result.errors.append(f"describe-stacks failed: {e}")
        return result

    print(f"  Current status: {stack_status}")

    # Step 1: Delete Athena WorkGroup
    workgroup = f"{stack_name}-workgroup"
    err = delete_athena_workgroup(athena_client, workgroup, region, dry_run=dry_run)
    if err:
        result.errors.append(err)
    else:
        result.steps_completed.append("athena_workgroup")

    # Step 2: Empty output bucket (versioned)
    out_bucket = f"{stack_name}-output-{account_id}"
    err = empty_versioned_bucket(s3_client, out_bucket, region, dry_run=dry_run)
    if err:
        result.errors.append(err)
    else:
        result.steps_completed.append("output_bucket")

    # Step 3: Empty Athena results bucket (versioned)
    athena_bucket = f"{stack_name}-athena-results-{account_id}"
    err = empty_versioned_bucket(s3_client, athena_bucket, region, dry_run=dry_run)
    if err:
        result.errors.append(err)
    else:
        result.steps_completed.append("athena_bucket")

    # Step 4: Revoke VPC Endpoint SG inbound rule
    if vpc_endpoint_sg:
        lambda_sg = get_lambda_sg_from_stack(cfn_client, stack_name)
        if lambda_sg:
            err = revoke_vpc_endpoint_sg_rule(
                ec2_client, vpc_endpoint_sg, lambda_sg, region, dry_run=dry_run
            )
            if err:
                result.errors.append(err)
            else:
                result.steps_completed.append("vpc_endpoint_sg_revoke")
        else:
            result.steps_completed.append("vpc_endpoint_sg_revoke:no_lambda_sg")

    # Step 5: Delete CloudFormation stack
    err = delete_cfn_stack(cfn_client, stack_name, dry_run=dry_run)
    if err:
        result.errors.append(err)
        result.success = False
    else:
        result.steps_completed.append("cfn_delete_initiated")

    # Step 6 (optional): Poll for completion
    if wait and not dry_run and not err:
        print(f"  Waiting for DELETE_COMPLETE...")
        err = poll_stack_deletion(cfn_client, stack_name)
        if err:
            result.errors.append(err)
            result.success = False
        else:
            result.steps_completed.append("cfn_delete_complete")
            print(f"  ✅ Stack deleted: {stack_name}")

    if result.errors:
        result.success = False

    return result


def main(argv: Optional[list[str]] = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Cleanup FSxN S3AP serverless pattern demo stacks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "ucs",
        nargs="*",
        help="UC identifiers (UC1, UC2, ..., UC17) or directory names",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Clean up all 17 UCs",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be deleted without making changes",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Wait for stack deletion to complete (poll)",
    )
    parser.add_argument(
        "--region",
        default=None,
        help="AWS region (default: REGION env var or ap-northeast-1)",
    )
    parser.add_argument(
        "--account-id",
        default=None,
        help="AWS account ID (default: ACCOUNT_ID env var or auto-resolve via STS)",
    )
    parser.add_argument(
        "--vpc-endpoint-sg",
        default=None,
        help="VPC Endpoint Security Group ID for auto-revoke (default: VPC_ENDPOINT_SG env var)",
    )

    args = parser.parse_args(argv)

    # Resolve UC list
    if args.all:
        uc_list = ALL_UCS
    elif args.ucs:
        uc_list = args.ucs
    else:
        parser.error("Specify UC identifiers (UC1, UC2, ...) or --all")
        return 1

    # Resolve configuration from args > env > auto
    import os

    region = args.region or os.environ.get("REGION", "ap-northeast-1")
    vpc_endpoint_sg = args.vpc_endpoint_sg or os.environ.get("VPC_ENDPOINT_SG") or None

    session = boto3.Session(region_name=region)

    # Resolve account ID
    account_id = args.account_id or os.environ.get("ACCOUNT_ID")
    if not account_id or account_id == "<ACCOUNT_ID>":
        try:
            sts_client = session.client("sts")
            account_id = resolve_account_id(sts_client)
        except (ClientError, Exception) as e:
            print(
                f"ERROR: Could not resolve AWS account ID. "
                f"Set ACCOUNT_ID env var or configure AWS credentials.\n{e}",
                file=sys.stderr,
            )
            return 1

    print(f"Cleanup target account: {account_id}, region: {region}")
    if args.dry_run:
        print("🔍 DRY-RUN MODE — no resources will be modified\n")
    print()

    # Process each UC
    results: list[CleanupResult] = []
    for uc_input in uc_list:
        uc_upper = uc_input.upper()
        if uc_upper in UC_DIR_MAP:
            uc_dir = UC_DIR_MAP[uc_upper]
            uc_label = uc_upper
        else:
            # Assume it's a directory name directly
            uc_dir = uc_input
            uc_label = uc_input

        stack_name = f"fsxn-{uc_dir}-demo"

        print("=" * 50)
        print(f"  Cleaning up: {stack_name} ({uc_label})")
        print("=" * 50)

        result = cleanup_stack(
            stack_name=stack_name,
            uc_label=uc_label,
            account_id=account_id,
            region=region,
            vpc_endpoint_sg=vpc_endpoint_sg,
            dry_run=args.dry_run,
            wait=args.wait,
            session=session,
        )
        results.append(result)
        print()

    # Summary
    print("=" * 50)
    print("  Cleanup Summary")
    print("=" * 50)

    failed = [r for r in results if not r.success]
    if not failed:
        print("  ✅ All stacks: delete initiated successfully.")
        if not args.dry_run and not args.wait:
            print("  Note: VPC Lambda ENI release may take 15-30 minutes.")
            print("  Monitor with: python3 scripts/cleanup_generic_ucs.py --status")
    else:
        print("  FAILED RESOURCES:")
        for r in failed:
            for err in r.errors:
                print(f"    ❌ {r.stack_name}: {err}")

    print()
    if not args.dry_run:
        print("  Post-cleanup checklist:")
        print("    □ Wait for DELETE_COMPLETE (15-30 min for VPC Lambda ENIs)")
        print(f"    □ Check retained DynamoDB tables:")
        print(
            f"      aws dynamodb list-tables --region {region} "
            f"--query 'TableNames[?contains(@, `fsxn-`)]'"
        )
        print(
            "    □ If DELETE_FAILED, see: docs/operational-runbooks/cleanup-troubleshooting.md"
        )

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
