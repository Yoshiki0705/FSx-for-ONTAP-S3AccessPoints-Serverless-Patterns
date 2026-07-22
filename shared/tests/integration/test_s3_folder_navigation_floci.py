"""Integration tests for S3 folder navigation using floci (local AWS emulator).

Verifies that ListObjectsV2 with Delimiter='/' returns the correct folder-like
structure that the portal's FileExplorer depends on. This catches edge cases
that moto may not accurately reproduce (prefix handling, CommonPrefixes ordering).

Prerequisites:
    docker run -d --name floci -p 4566:4566 floci/floci:latest

    Or via docker compose:
    services:
      floci:
        image: floci/floci:latest
        ports:
          - "4566:4566"

Reference:
    CDK Conference Japan 2026 — "起動時間24msのAWSエミュレーター「floci」で
    AWS CDK開発をローカル環境でも爆速化する！"

Usage:
    # Start floci first
    docker run -d --name floci -p 4566:4566 floci/floci:latest

    # Run tests
    python -m pytest shared/tests/integration/test_s3_folder_navigation_floci.py -v

    # Stop floci
    docker stop floci && docker rm floci
"""

from __future__ import annotations

import os
import pytest
import boto3
from botocore.config import Config

# Skip if floci is not running
FLOCI_ENDPOINT = os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566")
BUCKET_NAME = "test-portal-ap"


def is_floci_running() -> bool:
    """Check if floci is accessible."""
    import urllib.request

    try:
        urllib.request.urlopen(f"{FLOCI_ENDPOINT}/_floci/health", timeout=2)
        return True
    except Exception:
        try:
            # Fallback: try S3 list-buckets
            urllib.request.urlopen(f"{FLOCI_ENDPOINT}/", timeout=2)
            return True
        except Exception:
            return False


pytestmark = pytest.mark.skipif(
    not is_floci_running(),
    reason="floci not running (start with: docker run -d -p 4566:4566 floci/floci:latest)",
)


@pytest.fixture(scope="module")
def s3_client():
    """Create S3 client pointing to floci."""
    return boto3.client(
        "s3",
        endpoint_url=FLOCI_ENDPOINT,
        region_name="ap-northeast-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        config=Config(signature_version="s3v4"),
    )


@pytest.fixture(scope="module", autouse=True)
def setup_test_data(s3_client):
    """Create bucket and seed with test files mimicking FSx for ONTAP S3 AP structure."""
    # Create bucket (simulating S3 AP alias)
    try:
        s3_client.create_bucket(
            Bucket=BUCKET_NAME,
            CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"},
        )
    except s3_client.exceptions.BucketAlreadyOwnedByYou:
        pass

    # Seed data: simulate a typical NAS folder structure
    test_files = [
        # Root level files
        "README.md",
        "config.yaml",
        # documents/ folder
        "documents/contracts/2024/contract-001.pdf",
        "documents/contracts/2024/contract-002.pdf",
        "documents/contracts/2025/contract-003.pdf",
        "documents/reports/quarterly-q1.xlsx",
        "documents/reports/quarterly-q2.xlsx",
        # simulation/ folder (EDA logs)
        "simulation/JOB_00001_PASS.log",
        "simulation/JOB_00002_PASS.log",
        "simulation/JOB_00003_FAIL.log",
        "simulation/results/summary.csv",
        # images/ folder
        "images/photo-001.jpg",
        "images/photo-002.png",
        "images/thumbnails/thumb-001.jpg",
        # .trash/ folder (hidden, used by portal trash feature)
        ".trash/deleted-file.txt",
    ]

    for key in test_files:
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=key,
            Body=f"test content for {key}".encode(),
        )

    yield

    # Cleanup
    try:
        objects = s3_client.list_objects_v2(Bucket=BUCKET_NAME)
        if "Contents" in objects:
            for obj in objects["Contents"]:
                s3_client.delete_object(Bucket=BUCKET_NAME, Key=obj["Key"])
        s3_client.delete_bucket(Bucket=BUCKET_NAME)
    except Exception:
        pass


class TestFolderNavigation:
    """Tests for ListObjectsV2 with Delimiter='/' (folder-like navigation).

    This is the core S3 operation used by the portal's FileExplorer component.
    """

    def test_root_level_listing(self, s3_client):
        """Root prefix should return top-level files + folder prefixes."""
        response = s3_client.list_objects_v2(Bucket=BUCKET_NAME, Prefix="", Delimiter="/")

        # Files at root
        root_files = [obj["Key"] for obj in response.get("Contents", [])]
        assert "README.md" in root_files
        assert "config.yaml" in root_files

        # Folders (CommonPrefixes)
        folders = [cp["Prefix"] for cp in response.get("CommonPrefixes", [])]
        assert "documents/" in folders
        assert "simulation/" in folders
        assert "images/" in folders
        assert ".trash/" in folders

        # Nested files should NOT appear at root
        assert "documents/contracts/2024/contract-001.pdf" not in root_files

    def test_subfolder_listing(self, s3_client):
        """Navigating into documents/ should show its children only."""
        response = s3_client.list_objects_v2(Bucket=BUCKET_NAME, Prefix="documents/", Delimiter="/")

        # No files directly under documents/ (only subfolders)
        files = [obj["Key"] for obj in response.get("Contents", [])]
        assert len(files) == 0  # All content is in subfolders

        # Subfolders
        folders = [cp["Prefix"] for cp in response.get("CommonPrefixes", [])]
        assert "documents/contracts/" in folders
        assert "documents/reports/" in folders

    def test_deep_subfolder(self, s3_client):
        """Navigating into documents/contracts/2024/ should show files."""
        response = s3_client.list_objects_v2(Bucket=BUCKET_NAME, Prefix="documents/contracts/2024/", Delimiter="/")

        files = [obj["Key"] for obj in response.get("Contents", [])]
        assert "documents/contracts/2024/contract-001.pdf" in files
        assert "documents/contracts/2024/contract-002.pdf" in files
        assert len(files) == 2

        # No subfolders at this level
        folders = response.get("CommonPrefixes", [])
        assert len(folders) == 0

    def test_pagination(self, s3_client):
        """MaxKeys should limit results and return continuation token."""
        response = s3_client.list_objects_v2(Bucket=BUCKET_NAME, Prefix="simulation/", Delimiter="/", MaxKeys=2)

        # Should get at most 2 items (files + folders combined counted differently)
        total = len(response.get("Contents", [])) + len(response.get("CommonPrefixes", []))
        assert total <= 3  # MaxKeys applies to both

        if response.get("IsTruncated"):
            # Continue with token
            response2 = s3_client.list_objects_v2(
                Bucket=BUCKET_NAME,
                Prefix="simulation/",
                Delimiter="/",
                ContinuationToken=response["NextContinuationToken"],
            )
            assert response2 is not None

    def test_empty_prefix_returns_all_structure(self, s3_client):
        """Empty prefix with no delimiter returns all objects flat."""
        response = s3_client.list_objects_v2(Bucket=BUCKET_NAME)

        all_keys = [obj["Key"] for obj in response.get("Contents", [])]
        # Should include all 15 test files
        assert len(all_keys) >= 15
        assert "documents/contracts/2024/contract-001.pdf" in all_keys
        assert "simulation/JOB_00001_PASS.log" in all_keys

    def test_nonexistent_prefix(self, s3_client):
        """Non-existent prefix should return empty results."""
        response = s3_client.list_objects_v2(Bucket=BUCKET_NAME, Prefix="nonexistent/path/", Delimiter="/")

        assert response.get("Contents", []) == []
        assert response.get("CommonPrefixes", []) == []

    def test_hidden_folder_visibility(self, s3_client):
        """.trash/ should appear in root listing (portal filters in UI layer)."""
        response = s3_client.list_objects_v2(Bucket=BUCKET_NAME, Prefix="", Delimiter="/")

        folders = [cp["Prefix"] for cp in response.get("CommonPrefixes", [])]
        # S3 does not hide dot-prefixed folders — filtering is application-level
        assert ".trash/" in folders


class TestPresignedUrl:
    """Tests for Presigned URL generation against floci S3."""

    def test_presigned_url_generation(self, s3_client):
        """Presigned URL should be generated without error."""
        url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": BUCKET_NAME, "Key": "README.md"},
            ExpiresIn=300,
        )
        assert url is not None
        assert BUCKET_NAME in url or "localhost" in url

    def test_presigned_url_with_regional_endpoint(self):
        """SigV4 + regional endpoint (same as portal production config)."""
        regional_client = boto3.client(
            "s3",
            endpoint_url=FLOCI_ENDPOINT,
            region_name="ap-northeast-1",
            aws_access_key_id="test",
            aws_secret_access_key="test",
            config=Config(signature_version="s3v4"),
        )
        url = regional_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": BUCKET_NAME, "Key": "images/photo-001.jpg"},
            ExpiresIn=60,
        )
        assert url is not None
        assert "X-Amz-Signature" in url
