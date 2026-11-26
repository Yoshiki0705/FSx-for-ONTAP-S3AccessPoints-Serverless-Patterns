"""Fixtures for archive-verify-delete tests.

moto stands in for AWS. A regular bucket plays the part of the S3 Access Point: the shared
S3ApHelper accepts a bucket name wherever it accepts an alias.
"""

from __future__ import annotations

import sys
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

sys.path.insert(0, str(Path(__file__).resolve().parent))

from avd_support import AP, ARCHIVE, REGION, SECOND, TABLE  # noqa: E402


@pytest.fixture(autouse=True)
def aws_env(monkeypatch):
    for k, v in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_DEFAULT_REGION": REGION,
        "ACCESS_POINT": AP,
        "ARCHIVE_BUCKET": ARCHIVE,
        "ARCHIVE_PREFIX": "data/",
        "SECOND_COPY_BUCKET": "",
        "LEDGER_TABLE": TABLE,
        "LARGE_FILE_THRESHOLD_BYTES": str(5 * 1024**3),
        "FARGATE_ENABLED": "false",
        "ONTAP_ENABLED": "false",
        "APPROVAL_TIMEOUT_HOURS": "72",
        "STACK_NAME": "avd-test",
        "SNS_TOPIC_ARN": "",
    }.items():
        monkeypatch.setenv(k, v)


@pytest.fixture
def aws():
    """Buckets and the ledger table, inside moto."""
    with mock_aws():
        s3 = boto3.client("s3", region_name=REGION)
        for bucket in (AP, ARCHIVE, SECOND):
            s3.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": REGION})
        ddb = boto3.client("dynamodb", region_name=REGION)
        ddb.create_table(
            TableName=TABLE,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": "runId", "AttributeType": "S"},
                {"AttributeName": "key", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "runId", "KeyType": "HASH"},
                {"AttributeName": "key", "KeyType": "RANGE"},
            ],
        )
        yield s3


@pytest.fixture
def ledger(aws):
    from shared.archive_verify.ledger import Ledger

    return Ledger(TABLE)


@pytest.fixture
def lambda_context():
    from unittest.mock import MagicMock

    ctx = MagicMock()
    ctx.aws_request_id = "test-request-id"
    ctx.function_name = "test-function"
    return ctx
