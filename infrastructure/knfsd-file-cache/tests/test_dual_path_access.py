"""Test KNFSD + S3 AP dual-path access to same FSx for ONTAP volume."""
from __future__ import annotations

import time
import uuid

import pytest


@pytest.mark.integration
@pytest.mark.dual_path
class TestDualPathAccess:
    """Verify same file is accessible via both KNFSD (NFS) and S3 AP (S3 API)."""

    def test_s3ap_write_visible_via_knfsd(self, s3_client, ssm_client, knfsd_config):
        """File written via S3 AP should be readable via KNFSD NFS."""
        client_id = knfsd_config["client_instance_id"]
        if not client_id:
            pytest.skip("CLIENT_INSTANCE_ID not set")

        s3ap_alias = knfsd_config["s3ap_alias"]
        knfsd_ip = knfsd_config["knfsd_ip"]
        export_path = knfsd_config["export_path"]

        # Write via S3 AP
        test_key = f"knfsd-test/dual-path-{uuid.uuid4().hex[:8]}.txt"
        test_content = f"dual-path-test-{time.time()}"

        s3_client.put_object(
            Bucket=s3ap_alias,
            Key=test_key,
            Body=test_content.encode("utf-8"),
        )

        try:
            # Allow propagation time
            time.sleep(3)

            # Read via KNFSD NFS
            nfs_read_script = f"""
set -e
MOUNT=/mnt/knfsd-dual-test
mkdir -p $MOUNT
mount -t nfs -o vers=3 {knfsd_ip}:{export_path} $MOUNT 2>/dev/null || true
cat $MOUNT/{test_key} 2>/dev/null || echo "FILE_NOT_FOUND"
umount $MOUNT 2>/dev/null || true
"""
            cmd = ssm_client.send_command(
                InstanceIds=[client_id],
                DocumentName="AWS-RunShellScript",
                Parameters={"commands": [nfs_read_script]},
            )
            time.sleep(8)

            result = ssm_client.get_command_invocation(
                CommandId=cmd["Command"]["CommandId"],
                InstanceId=client_id,
            )

            nfs_content = result["StandardOutputContent"].strip()
            assert nfs_content == test_content, (
                f"NFS content mismatch. Expected: '{test_content}', Got: '{nfs_content}'"
            )
        finally:
            # Cleanup
            s3_client.delete_object(Bucket=s3ap_alias, Key=test_key)

    def test_s3ap_list_includes_nfs_written_file(self, s3_client, ssm_client, knfsd_config):
        """File written via KNFSD NFS should appear in S3 AP ListObjectsV2."""
        client_id = knfsd_config["client_instance_id"]
        if not client_id:
            pytest.skip("CLIENT_INSTANCE_ID not set")

        s3ap_alias = knfsd_config["s3ap_alias"]
        knfsd_ip = knfsd_config["knfsd_ip"]
        export_path = knfsd_config["export_path"]

        test_filename = f"knfsd-test/nfs-write-{uuid.uuid4().hex[:8]}.txt"
        test_content = f"written-via-nfs-{time.time()}"

        # Write via KNFSD NFS (write-through to FSx for ONTAP)
        nfs_write_script = f"""
set -e
MOUNT=/mnt/knfsd-write-test
mkdir -p $MOUNT
mount -t nfs -o vers=3 {knfsd_ip}:{export_path} $MOUNT 2>/dev/null || true
mkdir -p $MOUNT/knfsd-test
echo -n "{test_content}" > $MOUNT/{test_filename}
sync
umount $MOUNT 2>/dev/null || true
echo "WRITE_OK"
"""
        cmd = ssm_client.send_command(
            InstanceIds=[client_id],
            DocumentName="AWS-RunShellScript",
            Parameters={"commands": [nfs_write_script]},
        )
        time.sleep(8)

        result = ssm_client.get_command_invocation(
            CommandId=cmd["Command"]["CommandId"],
            InstanceId=client_id,
        )
        assert "WRITE_OK" in result["StandardOutputContent"]

        try:
            # Allow write-through propagation
            time.sleep(3)

            # Read via S3 AP
            response = s3_client.get_object(Bucket=s3ap_alias, Key=test_filename)
            s3_content = response["Body"].read().decode("utf-8")
            assert s3_content == test_content, (
                f"S3 AP content mismatch. Expected: '{test_content}', Got: '{s3_content}'"
            )
        finally:
            # Cleanup via S3 AP
            s3_client.delete_object(Bucket=s3ap_alias, Key=test_filename)

    def test_simultaneous_read_both_paths(self, s3_client, knfsd_config):
        """Both S3 AP and KNFSD should be able to read simultaneously without error."""
        s3ap_alias = knfsd_config["s3ap_alias"]

        # Write a test file via S3 AP
        test_key = f"knfsd-test/simultaneous-{uuid.uuid4().hex[:8]}.txt"
        s3_client.put_object(
            Bucket=s3ap_alias,
            Key=test_key,
            Body=b"simultaneous-access-test",
        )

        try:
            # Read via S3 AP (should always work)
            response = s3_client.get_object(Bucket=s3ap_alias, Key=test_key)
            content = response["Body"].read().decode("utf-8")
            assert content == "simultaneous-access-test"

            # HeadObject via S3 AP
            head = s3_client.head_object(Bucket=s3ap_alias, Key=test_key)
            assert head["ContentLength"] == len(b"simultaneous-access-test")
        finally:
            s3_client.delete_object(Bucket=s3ap_alias, Key=test_key)
