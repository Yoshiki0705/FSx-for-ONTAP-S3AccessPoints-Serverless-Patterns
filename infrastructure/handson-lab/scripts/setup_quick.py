"""Amazon Q Business Setup Script for FSx for ONTAP Hands-on Lab.

Creates an Amazon Q Business application with a Knowledge Base connected
to the FSx for ONTAP S3 Access Point.

Prerequisites:
    - Amazon Q Business enabled in the account
    - IAM Identity Center configured
    - S3 Access Point created (from CloudFormation stack)
    - boto3 >= 1.34.0

Usage:
    python3 scripts/setup_quick.py --stack-name fsx-ontap-handson
    python3 scripts/setup_quick.py --s3-ap-alias <alias> --region ap-northeast-1
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time

import boto3
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def get_stack_outputs(stack_name: str, region: str) -> dict[str, str]:
    """Retrieve CloudFormation stack outputs."""
    cfn = boto3.client("cloudformation", region_name=region)
    response = cfn.describe_stacks(StackName=stack_name)
    outputs = response["Stacks"][0].get("Outputs", [])
    return {o["OutputKey"]: o["OutputValue"] for o in outputs}


def create_q_application(region: str, app_name: str) -> str:
    """Create Amazon Q Business application."""
    q_client = boto3.client("qbusiness", region_name=region)

    logger.info("Creating Amazon Q Business application: %s", app_name)

    try:
        response = q_client.create_application(
            displayName=app_name,
            description="FSx for ONTAP Hands-on Lab - Knowledge Base powered by S3 Access Points",
        )
        app_id = response["applicationId"]
        logger.info("Application created: %s", app_id)
        return app_id
    except ClientError as e:
        if "ConflictException" in str(type(e)):
            logger.info("Application may already exist, listing...")
            apps = q_client.list_applications()
            for app in apps.get("applications", []):
                if app["displayName"] == app_name:
                    logger.info("Found existing application: %s", app["applicationId"])
                    return app["applicationId"]
        raise


def create_index(region: str, app_id: str, index_name: str) -> str:
    """Create an index in the Q Business application."""
    q_client = boto3.client("qbusiness", region_name=region)

    logger.info("Creating index: %s", index_name)

    try:
        response = q_client.create_index(
            applicationId=app_id,
            displayName=index_name,
            description="Index for FSx for ONTAP documents accessed via S3 Access Points",
        )
        index_id = response["indexId"]
        logger.info("Index created: %s", index_id)
        return index_id
    except ClientError as e:
        if "ConflictException" in str(type(e)):
            indices = q_client.list_indices(applicationId=app_id)
            for idx in indices.get("indices", []):
                if idx["displayName"] == index_name:
                    return idx["indexId"]
        raise


def create_s3_data_source(
    region: str,
    app_id: str,
    index_id: str,
    s3_ap_alias: str,
    role_arn: str,
) -> str:
    """Create S3 data source connected to FSx for ONTAP S3 Access Point."""
    q_client = boto3.client("qbusiness", region_name=region)

    ds_name = "FSx-ONTAP-S3AP-DataSource"
    logger.info("Creating data source: %s (S3 AP: %s)", ds_name, s3_ap_alias)

    # S3 data source configuration using S3 AP alias as bucket name
    configuration = {
        "type": "S3",
        "connectionConfiguration": {
            "repositoryEndpointMetadata": {
                "BucketName": s3_ap_alias,
            }
        },
        "repositoryConfigurations": {
            "document": {
                "fieldMappings": []
            }
        },
        "syncMode": "FULL_CRAWL",
    }

    try:
        response = q_client.create_data_source(
            applicationId=app_id,
            indexId=index_id,
            displayName=ds_name,
            description="Documents from FSx for ONTAP via S3 Access Point",
            configuration=configuration,
            roleArn=role_arn,
        )
        ds_id = response["dataSourceId"]
        logger.info("Data source created: %s", ds_id)
        return ds_id
    except ClientError as e:
        logger.error("Failed to create data source: %s", str(e))
        raise


def start_sync(region: str, app_id: str, index_id: str, ds_id: str) -> None:
    """Start data source synchronization."""
    q_client = boto3.client("qbusiness", region_name=region)

    logger.info("Starting data source sync...")
    q_client.start_data_source_sync_job(
        applicationId=app_id,
        indexId=index_id,
        dataSourceId=ds_id,
    )
    logger.info("Sync job started")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Set up Amazon Q Business with FSx for ONTAP S3 Access Point"
    )
    parser.add_argument("--stack-name", help="CloudFormation stack name")
    parser.add_argument("--s3-ap-alias", help="S3 Access Point alias (if not using stack)")
    parser.add_argument("--region", default="ap-northeast-1", help="AWS region")
    parser.add_argument("--app-name", default="FSx-ONTAP-Handson-Lab", help="Q Business app name")
    parser.add_argument("--role-arn", help="IAM role ARN for Q Business data source")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")

    args = parser.parse_args()

    # Resolve S3 AP alias
    s3_ap_alias = args.s3_ap_alias
    if not s3_ap_alias and args.stack_name:
        logger.info("Resolving S3 AP alias from stack: %s", args.stack_name)
        outputs = get_stack_outputs(args.stack_name, args.region)
        s3_ap_alias = outputs.get("S3AccessPointAlias")
        if not s3_ap_alias:
            logger.error("S3AccessPointAlias not found in stack outputs")
            sys.exit(1)
        logger.info("S3 AP Alias: %s", s3_ap_alias)

    if not s3_ap_alias:
        logger.error("--s3-ap-alias or --stack-name is required")
        sys.exit(1)

    if args.dry_run:
        logger.info("DRY RUN - Would create:")
        logger.info("  Application: %s", args.app_name)
        logger.info("  Index: FSx-ONTAP-Documents")
        logger.info("  Data Source: S3 AP = %s", s3_ap_alias)
        return

    # Create Q Business resources
    logger.info("=" * 60)
    logger.info(" Amazon Q Business Setup")
    logger.info("=" * 60)

    app_id = create_q_application(args.region, args.app_name)
    time.sleep(5)  # Wait for application to be ready

    index_id = create_index(args.region, app_id, "FSx-ONTAP-Documents")
    time.sleep(5)

    if not args.role_arn:
        logger.warning(
            "No --role-arn provided. You need to create an IAM role for Q Business "
            "data source with S3 read permissions on the AP ARN."
        )
        logger.info(
            "Create the data source manually in the Q Business console with "
            "S3 AP alias: %s", s3_ap_alias
        )
        return

    ds_id = create_s3_data_source(
        args.region, app_id, index_id, s3_ap_alias, args.role_arn
    )

    # Start initial sync
    start_sync(args.region, app_id, index_id, ds_id)

    logger.info("")
    logger.info("=" * 60)
    logger.info(" Setup Complete")
    logger.info("=" * 60)
    logger.info(" Application ID: %s", app_id)
    logger.info(" Index ID: %s", index_id)
    logger.info(" Data Source ID: %s", ds_id)
    logger.info(" S3 AP Alias: %s", s3_ap_alias)
    logger.info("")
    logger.info(" Access Q Business at:")
    logger.info("   https://%s.console.aws.amazon.com/amazonq/home", args.region)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
