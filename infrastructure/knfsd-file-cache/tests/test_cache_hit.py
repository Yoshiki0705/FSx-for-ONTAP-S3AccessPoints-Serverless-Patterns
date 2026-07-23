"""Test KNFSD File Cache hit/miss behavior."""
from __future__ import annotations

import time

import pytest


@pytest.mark.integration
class TestCacheBehavior:
    """Verify KNFSD L1/L2 cache provides speedup on repeated reads."""

    def _run_on_client(self, ssm_client, instance_id, command, timeout=30):
        """Execute command on client instance via SSM and return output."""
        cmd = ssm_client.send_command(
            InstanceIds=[instance_id],
            DocumentName="AWS-RunShellScript",
            Parameters={"commands": [command]},
            TimeoutSeconds=timeout,
        )
        time.sleep(min(timeout, 15))

        result = ssm_client.get_command_invocation(
            CommandId=cmd["Command"]["CommandId"],
            InstanceId=instance_id,
        )
        if result["Status"] != "Success":
            pytest.fail(
                f"SSM command failed: {result.get('StandardErrorContent', 'unknown')}"
            )
        return result["StandardOutputContent"].strip()

    def test_cache_miss_then_hit(self, ssm_client, knfsd_config):
        """Second read of same file should be faster (cache hit)."""
        client_id = knfsd_config["client_instance_id"]
        if not client_id:
            pytest.skip("CLIENT_INSTANCE_ID not set")

        knfsd_ip = knfsd_config["knfsd_ip"]
        export_path = knfsd_config["export_path"]

        # Generate test file and measure read times
        test_script = f"""
set -e
MOUNT=/mnt/knfsd-cache-test
mkdir -p $MOUNT
mount -t nfs -o vers=3 {knfsd_ip}:{export_path} $MOUNT 2>/dev/null || true

# Create 10MB test file
TEST_FILE=$MOUNT/.cache-test-$$.dat
dd if=/dev/urandom of=$TEST_FILE bs=1M count=10 2>/dev/null
sync

# Drop client page cache
echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true
sleep 1

# First read (cache miss on KNFSD)
START1=$(date +%s%N)
cat $TEST_FILE > /dev/null
END1=$(date +%s%N)
MISS_NS=$((END1 - START1))

# Second read (cache hit on KNFSD)
START2=$(date +%s%N)
cat $TEST_FILE > /dev/null
END2=$(date +%s%N)
HIT_NS=$((END2 - START2))

# Output results
echo "MISS_MS=$((MISS_NS / 1000000))"
echo "HIT_MS=$((HIT_NS / 1000000))"

# Cleanup
rm -f $TEST_FILE
umount $MOUNT 2>/dev/null || true
"""
        output = self._run_on_client(ssm_client, client_id, test_script, timeout=60)

        # Parse results
        results = {}
        for line in output.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                results[key.strip()] = int(value.strip())

        miss_ms = results.get("MISS_MS", 0)
        hit_ms = results.get("HIT_MS", 0)

        assert miss_ms > 0, "Cache miss time should be > 0"
        assert hit_ms > 0, "Cache hit time should be > 0"
        # Cache hit should be at least 2x faster (conservative threshold)
        assert hit_ms < miss_ms, (
            f"Cache hit ({hit_ms}ms) should be faster than miss ({miss_ms}ms)"
        )

    def test_multiple_reads_stay_cached(self, ssm_client, knfsd_config):
        """Multiple reads of same file should all be cache hits after first."""
        client_id = knfsd_config["client_instance_id"]
        if not client_id:
            pytest.skip("CLIENT_INSTANCE_ID not set")

        knfsd_ip = knfsd_config["knfsd_ip"]
        export_path = knfsd_config["export_path"]

        test_script = f"""
set -e
MOUNT=/mnt/knfsd-multi-test
mkdir -p $MOUNT
mount -t nfs -o vers=3 {knfsd_ip}:{export_path} $MOUNT 2>/dev/null || true

TEST_FILE=$MOUNT/.multi-read-test-$$.dat
dd if=/dev/urandom of=$TEST_FILE bs=1M count=5 2>/dev/null
sync
echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true
sleep 1

# Read 5 times, report each time
for i in 1 2 3 4 5; do
  START=$(date +%s%N)
  cat $TEST_FILE > /dev/null
  END=$(date +%s%N)
  echo "READ_${{i}}_MS=$(( (END - START) / 1000000 ))"
done

rm -f $TEST_FILE
umount $MOUNT 2>/dev/null || true
"""
        output = self._run_on_client(ssm_client, client_id, test_script, timeout=60)

        # Parse results
        times = []
        for line in output.splitlines():
            if line.startswith("READ_") and "_MS=" in line:
                ms = int(line.split("=")[1])
                times.append(ms)

        assert len(times) == 5, f"Expected 5 read times, got {len(times)}"
        # Reads 2-5 should all be faster than read 1 (cache hit)
        first_read = times[0]
        cached_avg = sum(times[1:]) / len(times[1:])
        assert cached_avg < first_read, (
            f"Cached reads avg ({cached_avg:.0f}ms) should be faster than "
            f"first read ({first_read}ms)"
        )
