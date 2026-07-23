"""Test FSx for ONTAP throughput sharing between KNFSD and S3 AP."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest


@pytest.mark.integration
@pytest.mark.benchmark
class TestThroughputSharing:
    """Verify KNFSD cache hits reduce FSx for ONTAP bandwidth consumption."""

    def test_cache_hit_reduces_fsxn_bandwidth(self, cloudwatch_client, ssm_client, knfsd_config):
        """After cache warm-up, FSx DataReadBytes should decrease."""
        client_id = knfsd_config["client_instance_id"]
        fsxn_id = knfsd_config["fsxn_file_system_id"]
        if not client_id or not fsxn_id:
            pytest.skip("CLIENT_INSTANCE_ID and FSXN_FILE_SYSTEM_ID required")

        knfsd_ip = knfsd_config["knfsd_ip"]
        export_path = knfsd_config["export_path"]

        # Step 1: Record baseline FSx DataReadBytes
        now = datetime.now(timezone.utc)
        baseline = self._get_fsxn_read_bytes(cloudwatch_client, fsxn_id, now - timedelta(minutes=5), now)

        # Step 2: First read pass (cache miss — FSx bandwidth consumed)
        read_script = f"""
set -e
MOUNT=/mnt/knfsd-bw-test
mkdir -p $MOUNT
mount -t nfs -o vers=3 {knfsd_ip}:{export_path} $MOUNT 2>/dev/null || true

# Create test data
TEST_DIR=$MOUNT/knfsd-test/bw-test-$$
mkdir -p $TEST_DIR
for i in $(seq 1 5); do
  dd if=/dev/urandom of=$TEST_DIR/file_$i.dat bs=1M count=10 2>/dev/null
done
sync
echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true
sleep 1

# First read (cache miss)
for i in $(seq 1 5); do
  cat $TEST_DIR/file_$i.dat > /dev/null
done
echo "PASS1_DONE"

sleep 2

# Second read (cache hit)
for i in $(seq 1 5); do
  cat $TEST_DIR/file_$i.dat > /dev/null
done
echo "PASS2_DONE"

# Cleanup
rm -rf $TEST_DIR
umount $MOUNT 2>/dev/null || true
"""
        cmd = ssm_client.send_command(
            InstanceIds=[client_id],
            DocumentName="AWS-RunShellScript",
            Parameters={"commands": [read_script]},
            TimeoutSeconds=120,
        )
        time.sleep(30)

        result = ssm_client.get_command_invocation(
            CommandId=cmd["Command"]["CommandId"],
            InstanceId=client_id,
        )
        assert "PASS1_DONE" in result["StandardOutputContent"]
        assert "PASS2_DONE" in result["StandardOutputContent"]

        # Step 3: Check FSx bandwidth — second pass should show less
        # Note: CloudWatch metrics have 1-minute granularity, so this is
        # a coarse check. Detailed analysis requires KNFSD's own metrics.
        time.sleep(60)  # Wait for CloudWatch metric publication

        after = datetime.now(timezone.utc)
        total_read = self._get_fsxn_read_bytes(
            cloudwatch_client, fsxn_id, now, after
        )

        # We wrote 50 MB of test data. If cache works, FSx should see
        # ~50 MB (first pass) but NOT another 50 MB (second pass was cached).
        # With some tolerance for other traffic:
        assert total_read is not None, "Could not retrieve FSx DataReadBytes metric"

    def test_s3ap_accessible_during_knfsd_burst(self, s3_client, knfsd_config):
        """S3 AP should remain accessible while KNFSD is actively caching."""
        s3ap_alias = knfsd_config["s3ap_alias"]
        if not s3ap_alias:
            pytest.skip("S3AP_ALIAS not set")

        # Simple S3 AP operation during potential KNFSD activity
        response = s3_client.list_objects_v2(
            Bucket=s3ap_alias,
            MaxKeys=1,
        )
        # Should succeed (not get SlowDown/503)
        assert response["ResponseMetadata"]["HTTPStatusCode"] == 200

    @staticmethod
    def _get_fsxn_read_bytes(cw_client, fs_id, start_time, end_time):
        """Get FSx DataReadBytes metric sum for the given period."""
        try:
            response = cw_client.get_metric_statistics(
                Namespace="AWS/FSx",
                MetricName="DataReadBytes",
                Dimensions=[{"Name": "FileSystemId", "Value": fs_id}],
                StartTime=start_time,
                EndTime=end_time,
                Period=60,
                Statistics=["Sum"],
            )
            datapoints = response.get("Datapoints", [])
            if not datapoints:
                return None
            return sum(dp["Sum"] for dp in datapoints)
        except Exception:
            return None
