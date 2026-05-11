"""Unit tests for scripts/cleanup_generic_ucs.py.

Uses moto to mock AWS services (S3, Athena, EC2, STS).
Uses unittest.mock for CloudFormation (moto CFn requires openapi_spec_validator).
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

# Ensure scripts directory is importable
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
import cleanup_generic_ucs as cleanup  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

REGION = "ap-northeast-1"
ACCOUNT_ID = "123456789012"


@pytest.fixture
def aws_env(monkeypatch):
    """Set environment variables for tests."""
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("ACCOUNT_ID", ACCOUNT_ID)
    monkeypatch.setenv("REGION", REGION)


@pytest.fixture
def session(aws_env):
    """Create a boto3 session for tests."""
    return boto3.Session(region_name=REGION)


# ---------------------------------------------------------------------------
# Test: resolve_account_id
# ---------------------------------------------------------------------------


@mock_aws
def test_resolve_account_id(aws_env):
    """STS get-caller-identity returns account ID."""
    session = boto3.Session(region_name=REGION)
    sts = session.client("sts", region_name=REGION)
    account_id = cleanup.resolve_account_id(sts)
    assert account_id == "123456789012"


# ---------------------------------------------------------------------------
# Test: delete_athena_workgroup
# ---------------------------------------------------------------------------


@mock_aws
def test_delete_athena_workgroup_not_exists(aws_env):
    """Non-existent workgroup returns None (no error)."""
    session = boto3.Session(region_name=REGION)
    athena = session.client("athena", region_name=REGION)
    result = cleanup.delete_athena_workgroup(
        athena, "nonexistent-workgroup", REGION, dry_run=False
    )
    assert result is None


@mock_aws
def test_delete_athena_workgroup_exists(aws_env):
    """Existing workgroup is deleted successfully."""
    session = boto3.Session(region_name=REGION)
    athena = session.client("athena", region_name=REGION)

    # Create a workgroup
    athena.create_work_group(
        Name="test-workgroup",
        Configuration={"ResultConfiguration": {"OutputLocation": "s3://test-bucket/"}},
    )

    result = cleanup.delete_athena_workgroup(
        athena, "test-workgroup", REGION, dry_run=False
    )
    assert result is None

    # Verify it's gone
    wgs = athena.list_work_groups()["WorkGroups"]
    names = [wg["Name"] for wg in wgs]
    assert "test-workgroup" not in names


@mock_aws
def test_delete_athena_workgroup_dry_run(aws_env, capsys):
    """Dry-run does not delete the workgroup."""
    session = boto3.Session(region_name=REGION)
    athena = session.client("athena", region_name=REGION)

    athena.create_work_group(
        Name="test-workgroup",
        Configuration={"ResultConfiguration": {"OutputLocation": "s3://test-bucket/"}},
    )

    result = cleanup.delete_athena_workgroup(
        athena, "test-workgroup", REGION, dry_run=True
    )
    assert result is None

    captured = capsys.readouterr()
    assert "[DRY-RUN]" in captured.out

    # Verify it still exists
    wgs = athena.list_work_groups()["WorkGroups"]
    names = [wg["Name"] for wg in wgs]
    assert "test-workgroup" in names


# ---------------------------------------------------------------------------
# Test: empty_versioned_bucket
# ---------------------------------------------------------------------------


@mock_aws
def test_empty_versioned_bucket_not_exists(aws_env):
    """Non-existent bucket returns None (no error)."""
    session = boto3.Session(region_name=REGION)
    s3 = session.client("s3", region_name=REGION)
    result = cleanup.empty_versioned_bucket(
        s3, "nonexistent-bucket-xyz", REGION, dry_run=False
    )
    assert result is None


@mock_aws
def test_empty_versioned_bucket_with_objects(aws_env):
    """Bucket with versioned objects is emptied and deleted."""
    session = boto3.Session(region_name=REGION)
    s3 = session.client("s3", region_name=REGION)

    bucket = "test-versioned-bucket"
    s3.create_bucket(
        Bucket=bucket,
        CreateBucketConfiguration={"LocationConstraint": REGION},
    )
    # Enable versioning
    s3.put_bucket_versioning(
        Bucket=bucket, VersioningConfiguration={"Status": "Enabled"}
    )
    # Put some objects (creates versions)
    s3.put_object(Bucket=bucket, Key="file1.txt", Body=b"v1")
    s3.put_object(Bucket=bucket, Key="file1.txt", Body=b"v2")
    s3.put_object(Bucket=bucket, Key="file2.txt", Body=b"data")
    # Delete one to create a delete marker
    s3.delete_object(Bucket=bucket, Key="file2.txt")

    result = cleanup.empty_versioned_bucket(s3, bucket, REGION, dry_run=False)
    assert result is None

    # Verify bucket is gone
    buckets = [b["Name"] for b in s3.list_buckets()["Buckets"]]
    assert bucket not in buckets


@mock_aws
def test_empty_versioned_bucket_dry_run(aws_env, capsys):
    """Dry-run reports counts but does not delete."""
    session = boto3.Session(region_name=REGION)
    s3 = session.client("s3", region_name=REGION)

    bucket = "test-dry-run-bucket"
    s3.create_bucket(
        Bucket=bucket,
        CreateBucketConfiguration={"LocationConstraint": REGION},
    )
    s3.put_bucket_versioning(
        Bucket=bucket, VersioningConfiguration={"Status": "Enabled"}
    )
    s3.put_object(Bucket=bucket, Key="file1.txt", Body=b"data")

    result = cleanup.empty_versioned_bucket(s3, bucket, REGION, dry_run=True)
    assert result is None

    captured = capsys.readouterr()
    assert "[DRY-RUN]" in captured.out
    assert "Would empty bucket" in captured.out

    # Bucket still exists
    buckets = [b["Name"] for b in s3.list_buckets()["Buckets"]]
    assert bucket in buckets


# ---------------------------------------------------------------------------
# Test: revoke_vpc_endpoint_sg_rule
# ---------------------------------------------------------------------------


@mock_aws
def test_revoke_vpc_endpoint_sg_rule_success(aws_env):
    """Successfully revoke an existing SG rule."""
    session = boto3.Session(region_name=REGION)
    ec2 = session.client("ec2", region_name=REGION)

    # Create VPC
    vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")
    vpc_id = vpc["Vpc"]["VpcId"]

    # Create security groups
    vpce_sg = ec2.create_security_group(
        GroupName="vpce-sg", Description="VPC Endpoint SG", VpcId=vpc_id
    )
    vpce_sg_id = vpce_sg["GroupId"]

    lambda_sg = ec2.create_security_group(
        GroupName="lambda-sg", Description="Lambda SG", VpcId=vpc_id
    )
    lambda_sg_id = lambda_sg["GroupId"]

    # Add the rule we want to revoke
    ec2.authorize_security_group_ingress(
        GroupId=vpce_sg_id,
        IpPermissions=[
            {
                "IpProtocol": "tcp",
                "FromPort": 443,
                "ToPort": 443,
                "UserIdGroupPairs": [{"GroupId": lambda_sg_id}],
            }
        ],
    )

    result = cleanup.revoke_vpc_endpoint_sg_rule(
        ec2, vpce_sg_id, lambda_sg_id, REGION, dry_run=False
    )
    assert result is None


@mock_aws
def test_revoke_vpc_endpoint_sg_rule_dry_run(aws_env, capsys):
    """Dry-run does not revoke."""
    session = boto3.Session(region_name=REGION)
    ec2 = session.client("ec2", region_name=REGION)

    result = cleanup.revoke_vpc_endpoint_sg_rule(
        ec2, "sg-12345", "sg-67890", REGION, dry_run=True
    )
    assert result is None

    captured = capsys.readouterr()
    assert "[DRY-RUN]" in captured.out


# ---------------------------------------------------------------------------
# Test: delete_cfn_stack
# ---------------------------------------------------------------------------


def test_delete_cfn_stack_success(aws_env):
    """Stack deletion is initiated successfully."""
    cfn = MagicMock()
    cfn.delete_stack.return_value = {}

    result = cleanup.delete_cfn_stack(cfn, "test-stack", dry_run=False)
    assert result is None
    cfn.delete_stack.assert_called_once_with(StackName="test-stack")


def test_delete_cfn_stack_dry_run(aws_env, capsys):
    """Dry-run does not delete the stack."""
    cfn = MagicMock()

    result = cleanup.delete_cfn_stack(cfn, "test-stack", dry_run=True)
    assert result is None

    captured = capsys.readouterr()
    assert "[DRY-RUN]" in captured.out
    cfn.delete_stack.assert_not_called()


def test_delete_cfn_stack_client_error(aws_env):
    """ClientError is captured and returned as error string."""
    cfn = MagicMock()
    cfn.delete_stack.side_effect = ClientError(
        {"Error": {"Code": "ValidationError", "Message": "Stack does not exist"}},
        "DeleteStack",
    )

    result = cleanup.delete_cfn_stack(cfn, "nonexistent-stack", dry_run=False)
    assert result is not None
    assert "delete-stack failed" in result


# ---------------------------------------------------------------------------
# Test: cleanup_stack (integration)
# ---------------------------------------------------------------------------


def test_cleanup_stack_not_found(aws_env, capsys):
    """Stack that doesn't exist is skipped gracefully."""
    # Mock session that returns a CFn client raising "does not exist"
    mock_session = MagicMock()
    mock_cfn = MagicMock()
    mock_cfn.describe_stacks.side_effect = ClientError(
        {"Error": {"Code": "ValidationError", "Message": "Stack does not exist"}},
        "DescribeStacks",
    )
    mock_session.client.return_value = mock_cfn

    result = cleanup.cleanup_stack(
        stack_name="fsxn-nonexistent-demo",
        uc_label="UC99",
        account_id=ACCOUNT_ID,
        region=REGION,
        vpc_endpoint_sg=None,
        dry_run=False,
        wait=False,
        session=mock_session,
    )
    assert result.success is True
    assert "skip:not_found" in result.steps_completed


@mock_aws
def test_cleanup_stack_full_flow(aws_env, capsys):
    """Full cleanup flow with stack + bucket (CFn mocked, S3 via moto)."""
    session = boto3.Session(region_name=REGION)
    s3 = session.client("s3", region_name=REGION)

    stack_name = "fsxn-legal-compliance-demo"

    # Create output bucket via moto
    out_bucket = f"{stack_name}-output-{ACCOUNT_ID}"
    s3.create_bucket(
        Bucket=out_bucket,
        CreateBucketConfiguration={"LocationConstraint": REGION},
    )
    s3.put_object(Bucket=out_bucket, Key="test.txt", Body=b"data")

    # Patch boto3.Session to return real S3/Athena but mock CFn
    mock_cfn = MagicMock()
    mock_cfn.describe_stacks.return_value = {
        "Stacks": [{"StackStatus": "CREATE_COMPLETE"}]
    }
    mock_cfn.delete_stack.return_value = {}
    mock_cfn.describe_stack_resource.side_effect = ClientError(
        {"Error": {"Code": "ValidationError", "Message": "Resource not found"}},
        "DescribeStackResource",
    )

    def mock_client(service, **kwargs):
        if service == "cloudformation":
            return mock_cfn
        return session.client(service, region_name=REGION)

    mock_session = MagicMock()
    mock_session.client.side_effect = mock_client

    result = cleanup.cleanup_stack(
        stack_name=stack_name,
        uc_label="UC1",
        account_id=ACCOUNT_ID,
        region=REGION,
        vpc_endpoint_sg=None,
        dry_run=False,
        wait=False,
        session=mock_session,
    )

    assert result.success is True
    assert "athena_workgroup" in result.steps_completed
    assert "output_bucket" in result.steps_completed
    assert "cfn_delete_initiated" in result.steps_completed


# ---------------------------------------------------------------------------
# Test: main() CLI
# ---------------------------------------------------------------------------


def test_main_dry_run(aws_env, capsys):
    """Main with --dry-run outputs preview without errors."""
    # Mock boto3.Session to return mock clients
    mock_cfn = MagicMock()
    mock_cfn.describe_stacks.return_value = {
        "Stacks": [{"StackStatus": "CREATE_COMPLETE"}]
    }
    mock_cfn.describe_stack_resource.side_effect = ClientError(
        {"Error": {"Code": "ValidationError", "Message": "not found"}},
        "DescribeStackResource",
    )

    mock_athena = MagicMock()
    mock_athena.get_work_group.side_effect = ClientError(
        {"Error": {"Code": "InvalidRequestException", "Message": "not found"}},
        "GetWorkGroup",
    )

    mock_s3 = MagicMock()
    mock_s3.head_bucket.side_effect = ClientError(
        {"Error": {"Code": "404", "Message": "Not Found"}}, "HeadBucket"
    )

    mock_ec2 = MagicMock()
    mock_sts = MagicMock()
    mock_sts.get_caller_identity.return_value = {"Account": ACCOUNT_ID}

    def mock_client(service, **kwargs):
        clients = {
            "cloudformation": mock_cfn,
            "athena": mock_athena,
            "s3": mock_s3,
            "ec2": mock_ec2,
            "sts": mock_sts,
        }
        return clients.get(service, MagicMock())

    with patch("cleanup_generic_ucs.boto3.Session") as mock_session_cls:
        mock_session = MagicMock()
        mock_session.client.side_effect = mock_client
        mock_session_cls.return_value = mock_session

        exit_code = cleanup.main(["--dry-run", "UC1"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "DRY-RUN MODE" in captured.out
    assert "fsxn-legal-compliance-demo" in captured.out


def test_main_no_args(aws_env, capsys):
    """Main with no args prints error."""
    with pytest.raises(SystemExit) as exc_info:
        cleanup.main([])
    assert exc_info.value.code == 2  # argparse error


def test_main_all_flag(aws_env, capsys):
    """Main with --all processes all 17 UCs."""
    # Mock all clients to return "not found" for stacks
    mock_cfn = MagicMock()
    mock_cfn.describe_stacks.side_effect = ClientError(
        {"Error": {"Code": "ValidationError", "Message": "does not exist"}},
        "DescribeStacks",
    )

    mock_athena = MagicMock()
    mock_s3 = MagicMock()
    mock_ec2 = MagicMock()
    mock_sts = MagicMock()
    mock_sts.get_caller_identity.return_value = {"Account": ACCOUNT_ID}

    def mock_client(service, **kwargs):
        clients = {
            "cloudformation": mock_cfn,
            "athena": mock_athena,
            "s3": mock_s3,
            "ec2": mock_ec2,
            "sts": mock_sts,
        }
        return clients.get(service, MagicMock())

    with patch("cleanup_generic_ucs.boto3.Session") as mock_session_cls:
        mock_session = MagicMock()
        mock_session.client.side_effect = mock_client
        mock_session_cls.return_value = mock_session

        exit_code = cleanup.main(["--dry-run", "--all"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "DRY-RUN MODE" in captured.out
    # Should mention all 17 UCs
    for uc_dir in cleanup.UC_DIR_MAP.values():
        assert f"fsxn-{uc_dir}-demo" in captured.out


# ---------------------------------------------------------------------------
# Test: UC_DIR_MAP completeness
# ---------------------------------------------------------------------------


def test_uc_dir_map_has_17_entries():
    """UC_DIR_MAP covers all 17 UCs."""
    assert len(cleanup.UC_DIR_MAP) == 17
    for i in range(1, 18):
        assert f"UC{i}" in cleanup.UC_DIR_MAP


# ---------------------------------------------------------------------------
# Test: dry-run output snapshot
# ---------------------------------------------------------------------------


@mock_aws
def test_dry_run_output_snapshot(aws_env, capsys):
    """Snapshot test: dry-run output contains expected sections."""
    session = boto3.Session(region_name=REGION)
    s3 = session.client("s3", region_name=REGION)

    stack_name = "fsxn-legal-compliance-demo"

    # Create output bucket via moto
    out_bucket = f"{stack_name}-output-{ACCOUNT_ID}"
    s3.create_bucket(
        Bucket=out_bucket,
        CreateBucketConfiguration={"LocationConstraint": REGION},
    )
    s3.put_bucket_versioning(
        Bucket=out_bucket, VersioningConfiguration={"Status": "Enabled"}
    )
    s3.put_object(Bucket=out_bucket, Key="report.pdf", Body=b"pdf-content")

    # Mock CFn to return existing stack
    mock_cfn = MagicMock()
    mock_cfn.describe_stacks.return_value = {
        "Stacks": [{"StackStatus": "CREATE_COMPLETE"}]
    }
    mock_cfn.describe_stack_resource.side_effect = ClientError(
        {"Error": {"Code": "ValidationError", "Message": "not found"}},
        "DescribeStackResource",
    )

    mock_athena = MagicMock()
    mock_athena.get_work_group.return_value = {"WorkGroup": {"Name": f"{stack_name}-workgroup"}}
    mock_athena.delete_work_group.return_value = {}

    def mock_client(service, **kwargs):
        if service == "cloudformation":
            return mock_cfn
        if service == "athena":
            return mock_athena
        return session.client(service, region_name=REGION)

    mock_session = MagicMock()
    mock_session.client.side_effect = mock_client

    with patch("cleanup_generic_ucs.boto3.Session", return_value=mock_session):
        exit_code = cleanup.main(["--dry-run", "UC1"])

    assert exit_code == 0

    captured = capsys.readouterr()
    output = captured.out

    # Verify key sections are present
    assert "DRY-RUN MODE" in output
    assert f"Cleanup target account: {ACCOUNT_ID}" in output
    assert "fsxn-legal-compliance-demo" in output
    assert "[DRY-RUN]" in output
    assert "Cleanup Summary" in output
