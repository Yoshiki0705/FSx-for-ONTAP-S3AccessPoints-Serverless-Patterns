"""Test KNFSD write-through behavior to FSx for ONTAP."""
from __future__ import annotations

import time
import uuid

import pytest


@pytest.mark.integration
class TestWriteThrough:
    """Verify KNFSD write-through writes reach FSx for ONTAP (visible via S3 AP)."""

    def test_write_through_small_file(self, s3_client, ssm_client, knfsd_config):
        """Small file written via KNFSD NFS should be immediately visible via S3 AP."""
        client_id = knfsd_config["client_instance_id"]
        if not client_id:
            pytest.skip("CLIENT_INSTANCE_ID not set")

        s3ap_alias = knfsd_config["s3ap_alias"]
        knfsd_ip = knfsd_config["knfsd_ip"]
        export_path = knfsd_config["export_path"]

        test_key = f"knfsd-test/wt-small-{uuid.uuid4().hex[:8]}.txt"
        test_content = f"write-through-{time.time()}"

        # Write via KNFSD
        write_script = f"""
set -e
MOUNT=/mnt/knfsd-wt-test
mkdir -p $MOUNT
mount -t nfs -o vers=3 {knfsd_ip}:{export_path} $MOUNT 2>/dev/null || true
mkdir -p $MOUNT/knfsd-test
echo -n "{test_content}" > $MOUNT/{test_key}
sync
echo "WRITE_DONE"
umount $MOUNT 2>/dev/null || true
"""
        cmd = ssm_client.send_command(
            InstanceIds=[client_id],
            DocumentName="AWS-RunShellScript",
            Parameters={"commands": [write_script]},
        )
        time.sleep(8)

        result = ssm_client.get_command_invocation(
            CommandId=cmd["Command"]["CommandId"],
            InstanceId=client_id,
        )
        assert "WRITE_DONE" in result["StandardOutputContent"]

        try:
            # Verify via S3 AP (write-through should make it immediately available)
            time.sleep(2)
            response = s3_client.get_object(Bucket=s3ap_alias, Key=test_key)
            content = response["Body"].read().decode("utf-8")
            assert content == test_content
        finally:
            s3_client.delete_object(Bucket=s3ap_alias, Key=test_key)

    def test_write_through_preserves_metadata(self, s3_client, ssm_client, knfsd_config):
        """File metadata (size) should be consistent across NFS write and S3 AP read."""
        client_id = knfsd_config["client_instance_id"]
        if not client_id:
            pytest.skip("CLIENT_INSTANCE_ID not set")

        s3ap_alias = knfsd_config["s3ap_alias"]
        knfsd_ip = knfsd_config["knfsd_ip"]
        export_path = knfsd_config["export_path"]

        test_key = f"knfsd-test/wt-meta-{uuid.uuid4().hex[:8]}.bin"
        file_size_bytes = 1048576  # 1 MB

        # Write fixed-size file via KNFSD
        write_script = f"""
set -e
MOUNT=/mnt/knfsd-meta-test
mkdir -p $MOUNT
mount -t nfs -o vers=3 {knfsd_ip}:{export_path} $MOUNT 2>/dev/null || true
mkdir -p $MOUNT/knfsd-test
dd if=/dev/zero of=$MOUNT/{test_key} bs=1M count=1 2>/dev/null
sync
stat -c %s $MOUNT/{test_key}
umount $MOUNT 2>/dev/null || true
"""
        cmd = ssm_client.send_command(
            InstanceIds=[client_id],
            DocumentName="AWS-RunShellScript",
            Parameters={"commands": [write_script]},
        )
        time.sleep(8)

        result = ssm_client.get_command_invocation(
            CommandId=cmd["Command"]["CommandId"],
            InstanceId=client_id,
        )
        nfs_size = int(result["StandardOutputContent"].strip())
        assert nfs_size == file_size_bytes

        try:
            time.sleep(2)
            head = s3_client.head_object(Bucket=s3ap_alias, Key=test_key)
            s3_size = head["ContentLength"]
            assert s3_size == file_size_bytes, (
                f"Size mismatch: NFS={nfs_size}, S3 AP={s3_size}"
            )
        finally:
            s3_client.delete_object(Bucket=s3ap_alias, Key=test_key)
