"""P0 Portal Verification Script — Pre-production checks for File Portal UI.

Validates 7 critical behaviors before production deployment of the
FSx for ONTAP S3 AP file portal. Each test is independently runnable.

Environment variables (required):
    S3AP_ALIAS      - S3 Access Point alias (e.g., 'my-ap-xxx-ext-s3alias')
    AWS_REGION      - AWS region (default: ap-northeast-1)

Environment variables (optional, for specific tests):
    NFS_MOUNT_PATH  - NFS mount point for cross-protocol tests (e.g., /mnt/fsxn)
    SMB_MOUNT_PATH  - SMB mount point (e.g., /mnt/smb or Z: on Windows)
    VOLUME_NAME     - ONTAP volume name for quota tests
    SVM_MGMT_IP     - SVM management IP for ONTAP REST API calls

Usage:
    # Run all tests that can be executed with current env
    python3 scripts/verify_portal_p0.py

    # Run a specific test
    python3 scripts/verify_portal_p0.py --test b1
    python3 scripts/verify_portal_p0.py --test d1
    python3 scripts/verify_portal_p0.py --test g3

    # List available tests
    python3 scripts/verify_portal_p0.py --list

CAVEAT: Results are from a specific test environment. Actual behavior depends on
workload characteristics, ONTAP version, and FSx for ONTAP configuration.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import statistics
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

REGION = os.environ.get("AWS_REGION", "ap-northeast-1")
S3AP_ALIAS = os.environ.get("S3AP_ALIAS", "")
NFS_MOUNT = os.environ.get("NFS_MOUNT_PATH", "")
SMB_MOUNT = os.environ.get("SMB_MOUNT_PATH", "")
RESULTS_DIR = Path(__file__).parent.parent / ".private" / "p0-results"


def _s3_client():
    """Create S3 client with regional endpoint."""
    return boto3.client(
        "s3",
        region_name=REGION,
        endpoint_url=f"https://s3.{REGION}.amazonaws.com",
    )


def _write_result(test_id: str, result: dict) -> None:
    """Write test result to JSON file."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = RESULTS_DIR / f"{test_id}_{ts}.json"
    result["test_id"] = test_id
    result["timestamp"] = ts
    result["environment"] = {
        "region": REGION,
        "s3ap_alias": S3AP_ALIAS,
        "nfs_mount": NFS_MOUNT,
    }
    with open(path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    logger.info(f"Result written to {path}")


# ---------------------------------------------------------------------------
# B-1: Throughput sharing baseline benchmark
# ---------------------------------------------------------------------------
def test_b1_throughput_baseline():
    """B-1: Measure S3 AP GetObject latency with and without NFS background load.

    Requires: S3AP_ALIAS, NFS_MOUNT_PATH (optional for full test)
    """
    if not S3AP_ALIAS:
        logger.error("S3AP_ALIAS not set")
        return

    s3 = _s3_client()

    # Find a test file on the volume
    resp = s3.list_objects_v2(Bucket=S3AP_ALIAS, MaxKeys=5)
    if not resp.get("Contents"):
        logger.error("No files found on S3 AP — upload test data first")
        return

    test_key = resp["Contents"][0]["Key"]
    logger.info(f"Using test file: {test_key}")

    # Phase 1: S3 AP only (no NFS load)
    latencies_idle = []
    for i in range(20):
        start = time.perf_counter()
        obj = s3.get_object(Bucket=S3AP_ALIAS, Key=test_key)
        obj["Body"].read()
        latencies_idle.append((time.perf_counter() - start) * 1000)

    result = {
        "phase": "idle_baseline",
        "file": test_key,
        "iterations": 20,
        "latency_ms": {
            "mean": statistics.mean(latencies_idle),
            "p50": statistics.median(latencies_idle),
            "p95": sorted(latencies_idle)[int(len(latencies_idle) * 0.95)],
            "max": max(latencies_idle),
        },
        "nfs_background_load": False,
        "note": "Run with NFS_MOUNT_PATH set and dd running for full comparison",
    }

    if NFS_MOUNT:
        logger.info("NFS mount detected — starting background load for comparison...")
        logger.info(
            "To complete this test: run 'dd if=/dev/zero of=$NFS_MOUNT_PATH/bench_load bs=1M count=1024' "
            "in a separate terminal, then re-run this test."
        )
        result["instruction"] = (
            "Re-run with concurrent NFS write load to measure impact. "
            "Compare latency_ms values between idle and loaded runs."
        )

    _write_result("b1", result)
    logger.info(
        f"B-1 idle baseline: mean={result['latency_ms']['mean']:.1f}ms, "
        f"p95={result['latency_ms']['p95']:.1f}ms"
    )


# ---------------------------------------------------------------------------
# B-2: Capacity Pool tiering read latency
# ---------------------------------------------------------------------------
def test_b2_tiering_latency():
    """B-2: Compare read latency for SSD vs Capacity Pool tiered files.

    Requires: S3AP_ALIAS
    Assumes: Volume has tiering-policy=auto and some files are tiered.
    """
    if not S3AP_ALIAS:
        logger.error("S3AP_ALIAS not set")
        return

    s3 = _s3_client()

    logger.info(
        "B-2: Reading multiple files and recording latencies.\n"
        "Files tiered to Capacity Pool will show higher first-read latency.\n"
        "Compare with CloudWatch ReadLatency metric for confirmation."
    )

    resp = s3.list_objects_v2(Bucket=S3AP_ALIAS, MaxKeys=50)
    if not resp.get("Contents"):
        logger.error("No files found")
        return

    results = []
    for obj in resp["Contents"][:20]:
        key = obj["Key"]
        size = obj["Size"]
        # First read (cold — may need to recall from Capacity Pool)
        start = time.perf_counter()
        r = s3.get_object(Bucket=S3AP_ALIAS, Key=key)
        r["Body"].read()
        first_read_ms = (time.perf_counter() - start) * 1000

        # Second read (warm — should be from SSD cache)
        start = time.perf_counter()
        r = s3.get_object(Bucket=S3AP_ALIAS, Key=key)
        r["Body"].read()
        second_read_ms = (time.perf_counter() - start) * 1000

        results.append({
            "key": key,
            "size_bytes": size,
            "first_read_ms": round(first_read_ms, 2),
            "second_read_ms": round(second_read_ms, 2),
            "delta_ms": round(first_read_ms - second_read_ms, 2),
            "likely_tiered": first_read_ms > second_read_ms * 3,
        })

    tiered_count = sum(1 for r in results if r["likely_tiered"])
    result = {
        "files_tested": len(results),
        "likely_tiered_files": tiered_count,
        "details": results,
        "interpretation": (
            "Files with first_read_ms >> second_read_ms are likely tiered to Capacity Pool. "
            "Verify with CloudWatch DataReadOperations and ReadLatency metrics."
        ),
    }
    _write_result("b2", result)
    logger.info(f"B-2: {len(results)} files tested, {tiered_count} likely tiered")


# ---------------------------------------------------------------------------
# D-1: Write-in-progress S3 AP read behavior
# ---------------------------------------------------------------------------
def test_d1_write_in_progress():
    """D-1: Read a file via S3 AP while it's being written via NFS.

    Requires: S3AP_ALIAS, NFS_MOUNT_PATH
    """
    if not S3AP_ALIAS:
        logger.error("S3AP_ALIAS not set")
        return
    if not NFS_MOUNT:
        logger.error("NFS_MOUNT_PATH not set — required for D-1")
        return

    s3 = _s3_client()
    test_file = "p0_test_write_in_progress.dat"
    nfs_path = Path(NFS_MOUNT) / test_file

    logger.info(f"D-1: Writing 100MB file via NFS at {nfs_path}")
    logger.info("Simultaneously reading via S3 AP during write...")

    # Start NFS write in background (100MB, slow write to give time to read)
    proc = subprocess.Popen(
        ["dd", "if=/dev/zero", f"of={nfs_path}", "bs=1M", "count=100"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    time.sleep(0.5)  # Let write start

    # Attempt S3 AP read while write is in progress
    read_results = []
    for i in range(5):
        try:
            start = time.perf_counter()
            resp = s3.get_object(Bucket=S3AP_ALIAS, Key=test_file)
            body = resp["Body"].read()
            latency = (time.perf_counter() - start) * 1000
            read_results.append({
                "attempt": i + 1,
                "success": True,
                "bytes_read": len(body),
                "latency_ms": round(latency, 2),
                "content_length_header": resp.get("ContentLength"),
            })
        except Exception as e:
            read_results.append({
                "attempt": i + 1,
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
            })
        time.sleep(1)

    proc.wait()

    # Final read after write completes
    time.sleep(1)
    try:
        resp = s3.get_object(Bucket=S3AP_ALIAS, Key=test_file)
        body = resp["Body"].read()
        final_size = len(body)
    except Exception as e:
        final_size = f"ERROR: {e}"

    result = {
        "test_file": test_file,
        "write_size_mb": 100,
        "reads_during_write": read_results,
        "final_file_size_bytes": final_size,
        "expected_final_size": 100 * 1024 * 1024,
        "interpretation": (
            "If reads succeed during write, the file is readable in an intermediate state. "
            "If ContentLength changes between reads, ONTAP exposes the growing file. "
            "If reads fail, ONTAP may block reads until write completes."
        ),
    }

    # Cleanup
    try:
        nfs_path.unlink()
    except OSError:
        pass

    _write_result("d1", result)
    logger.info(f"D-1 complete: {sum(1 for r in read_results if r.get('success'))}/5 reads succeeded during write")


# ---------------------------------------------------------------------------
# D-2: S3 AP PutObject → NFS/SMB immediate visibility
# ---------------------------------------------------------------------------
def test_d2_put_visibility():
    """D-2: Verify S3 AP PutObject is immediately visible via NFS.

    Requires: S3AP_ALIAS, NFS_MOUNT_PATH
    """
    if not S3AP_ALIAS:
        logger.error("S3AP_ALIAS not set")
        return
    if not NFS_MOUNT:
        logger.error("NFS_MOUNT_PATH not set — required for D-2")
        return

    s3 = _s3_client()
    results = []

    for i in range(10):
        filename = f"p0_visibility_test_{i:04d}.txt"
        content = f"visibility test {i} at {time.time()}"

        # Write via S3 AP
        put_start = time.perf_counter()
        s3.put_object(Bucket=S3AP_ALIAS, Key=filename, Body=content.encode())
        put_ms = (time.perf_counter() - put_start) * 1000

        # Check NFS visibility immediately
        nfs_path = Path(NFS_MOUNT) / filename
        check_start = time.perf_counter()
        visible = nfs_path.exists()
        check_ms = (time.perf_counter() - check_start) * 1000

        nfs_content = ""
        if visible:
            nfs_content = nfs_path.read_text()

        results.append({
            "file": filename,
            "put_latency_ms": round(put_ms, 2),
            "nfs_visible_immediately": visible,
            "nfs_check_latency_ms": round(check_ms, 2),
            "content_matches": nfs_content == content,
        })

        # Cleanup
        try:
            s3.delete_object(Bucket=S3AP_ALIAS, Key=filename)
            if nfs_path.exists():
                nfs_path.unlink()
        except Exception:
            pass

    all_visible = all(r["nfs_visible_immediately"] for r in results)
    all_match = all(r["content_matches"] for r in results)

    result = {
        "files_tested": len(results),
        "all_immediately_visible": all_visible,
        "all_content_matches": all_match,
        "details": results,
        "conclusion": (
            "PASS: Strong consistency confirmed" if (all_visible and all_match)
            else "INVESTIGATE: Some files not immediately visible or content mismatch"
        ),
    }
    _write_result("d2", result)
    logger.info(f"D-2: {sum(1 for r in results if r['nfs_visible_immediately'])}/10 immediately visible via NFS")


# ---------------------------------------------------------------------------
# D-4: SMB oplock + S3 AP interaction
# ---------------------------------------------------------------------------
def test_d4_oplock():
    """D-4: Test if S3 AP GetObject breaks SMB oplocks.

    Requires: S3AP_ALIAS, SMB_MOUNT_PATH
    Note: This test provides guidance — full oplock verification requires
    Windows client with oplock monitoring (e.g., handle.exe or procmon).
    """
    if not S3AP_ALIAS:
        logger.error("S3AP_ALIAS not set")
        return

    logger.info(
        "D-4: SMB oplock interaction test.\n"
        "Manual verification steps:\n"
        "1. Open a file via SMB on a Windows client (e.g., open in Notepad)\n"
        "2. Run: python3 scripts/verify_portal_p0.py --test d4-read\n"
        "3. On Windows, check if the file shows 'another user has modified' prompt\n"
        "4. If prompt appears → oplock was broken by S3 AP read\n"
        "5. If no prompt → S3 AP read does NOT break oplock (expected for read-only)\n"
    )

    result = {
        "test_type": "manual_guidance",
        "steps": [
            "1. Open a file via SMB on Windows (e.g., open .txt in Notepad)",
            "2. Note the file key/path",
            "3. Execute S3 AP GetObject on the same file",
            "4. Observe Windows client for oplock break notification",
            "5. Record observation in this result file",
        ],
        "expected_behavior": (
            "S3 AP GetObject (read-only) should NOT break SMB read oplocks. "
            "It may break exclusive/batch oplocks if ONTAP treats S3 AP as a second reader. "
            "This is ONTAP version dependent (9.17.1+)."
        ),
        "status": "awaiting_manual_verification",
    }

    # If we can at least do the S3 AP read part
    s3 = _s3_client()
    resp = s3.list_objects_v2(Bucket=S3AP_ALIAS, MaxKeys=1)
    if resp.get("Contents"):
        key = resp["Contents"][0]["Key"]
        start = time.perf_counter()
        r = s3.get_object(Bucket=S3AP_ALIAS, Key=key)
        r["Body"].read()
        ms = (time.perf_counter() - start) * 1000
        result["s3ap_read_latency_ms"] = round(ms, 2)
        result["s3ap_read_key"] = key
        logger.info(f"S3 AP read completed: {key} in {ms:.1f}ms — check Windows client for oplock break")

    _write_result("d4", result)


# ---------------------------------------------------------------------------
# G-3: Unicode / long filename compatibility
# ---------------------------------------------------------------------------
def test_g3_unicode_filenames():
    """G-3: Test S3 AP handling of Unicode and long filenames.

    Requires: S3AP_ALIAS, NFS_MOUNT_PATH (for file creation)
    """
    if not S3AP_ALIAS:
        logger.error("S3AP_ALIAS not set")
        return
    if not NFS_MOUNT:
        logger.error("NFS_MOUNT_PATH not set — required for G-3")
        return

    s3 = _s3_client()
    test_names = [
        ("japanese_basic", "設計図面_v2.3_最終版.pdf"),
        ("japanese_long", "プロジェクト管理_2026年度_第3四半期_進捗報告書_改訂版_承認済み.xlsx"),
        ("mixed_script", "CAD_図面_Assembly-Part01_修正3.step"),
        ("emoji", "📊_quarterly_report_Q3.pptx"),
        ("max_ascii_255", "a" * 251 + ".txt"),  # 255 bytes total
        ("deep_path", "level1/level2/level3/level4/level5/level6/level7/deep_file.txt"),
        ("spaces_special", "my file (copy 2) [final].docx"),
    ]

    results = []
    for label, name in test_names:
        # Create file via NFS
        if "/" in name:
            nfs_path = Path(NFS_MOUNT) / name
            nfs_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            nfs_path = Path(NFS_MOUNT) / name

        try:
            nfs_path.write_text(f"test content for {label}")
            nfs_created = True
        except OSError as e:
            nfs_created = False
            results.append({"label": label, "name": name, "nfs_create": False, "error": str(e)})
            continue

        # Try to list/read via S3 AP
        time.sleep(0.5)  # Brief wait for visibility
        try:
            key = name
            resp = s3.get_object(Bucket=S3AP_ALIAS, Key=key)
            body = resp["Body"].read().decode("utf-8")
            s3ap_readable = True
            content_match = body == f"test content for {label}"
        except Exception as e:
            s3ap_readable = False
            content_match = False

        results.append({
            "label": label,
            "name": name,
            "name_bytes": len(name.encode("utf-8")),
            "nfs_create": nfs_created,
            "s3ap_readable": s3ap_readable,
            "content_matches": content_match,
        })

        # Cleanup
        try:
            nfs_path.unlink()
        except OSError:
            pass

    # Cleanup deep dirs
    try:
        import shutil
        shutil.rmtree(Path(NFS_MOUNT) / "level1", ignore_errors=True)
    except Exception:
        pass

    result = {
        "files_tested": len(results),
        "all_s3ap_readable": all(r.get("s3ap_readable", False) for r in results),
        "details": results,
        "s3_key_byte_limit": 1024,
        "nfs_filename_byte_limit": 255,
        "note": "S3 keys support 1024 bytes UTF-8. NFS filenames support 255 bytes.",
    }
    _write_result("g3", result)
    logger.info(f"G-3: {sum(1 for r in results if r.get('s3ap_readable'))}/{len(results)} files readable via S3 AP")


# ---------------------------------------------------------------------------
# G-4: Quota exceeded error response
# ---------------------------------------------------------------------------
def test_g4_quota_error():
    """G-4: Test S3 AP PutObject behavior when volume/qtree quota is exceeded.

    Requires: S3AP_ALIAS
    Note: Requires a volume with quota configured and nearly full.
    If quota is not configured, this test documents the expected approach.
    """
    if not S3AP_ALIAS:
        logger.error("S3AP_ALIAS not set")
        return

    s3 = _s3_client()

    logger.info(
        "G-4: Quota exceeded test.\n"
        "Pre-requisite: Configure a tight qtree/volume quota (e.g., 10MB)\n"
        "then run this test to observe the S3 AP error response.\n"
    )

    # Try a small write first to confirm basic PutObject works
    test_key = "p0_quota_test_small.txt"
    try:
        s3.put_object(Bucket=S3AP_ALIAS, Key=test_key, Body=b"small test")
        small_write_ok = True
        s3.delete_object(Bucket=S3AP_ALIAS, Key=test_key)
    except Exception as e:
        small_write_ok = False
        logger.warning(f"Basic PutObject failed: {e}")

    # Attempt large write that might exceed quota
    large_key = "p0_quota_test_large.dat"
    large_body = b"x" * (50 * 1024 * 1024)  # 50MB
    try:
        s3.put_object(Bucket=S3AP_ALIAS, Key=large_key, Body=large_body)
        large_write_result = "SUCCESS (quota not hit or not configured)"
        error_code = None
        # Cleanup
        try:
            s3.delete_object(Bucket=S3AP_ALIAS, Key=large_key)
        except Exception:
            pass
    except s3.exceptions.ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_msg = e.response["Error"]["Message"]
        large_write_result = f"REJECTED: {error_code} — {error_msg}"
    except Exception as e:
        error_code = type(e).__name__
        large_write_result = f"ERROR: {e}"

    result = {
        "small_write_ok": small_write_ok,
        "large_write_50mb_result": large_write_result,
        "error_code": error_code,
        "recommendation": (
            "If quota is not configured, set up a qtree quota (e.g., 10MB) and re-run. "
            "Expected error codes: 'AccessDenied' or 'InternalError' when ONTAP rejects the write."
        ),
        "portal_ui_guidance": (
            "Map error_code to user-friendly message: "
            "'AccessDenied' on write → 'Storage quota exceeded. Contact your administrator.' "
            "'InternalError' → 'Write failed. The volume may be full.'"
        ),
    }
    _write_result("g4", result)
    logger.info(f"G-4: small_write={small_write_ok}, large_write={large_write_result}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
TESTS = {
    "b1": ("B-1: Throughput baseline", test_b1_throughput_baseline),
    "b2": ("B-2: Tiering latency", test_b2_tiering_latency),
    "d1": ("D-1: Write-in-progress read", test_d1_write_in_progress),
    "d2": ("D-2: PutObject visibility", test_d2_put_visibility),
    "d4": ("D-4: SMB oplock interaction", test_d4_oplock),
    "g3": ("G-3: Unicode filenames", test_g3_unicode_filenames),
    "g4": ("G-4: Quota error", test_g4_quota_error),
}


def main():
    parser = argparse.ArgumentParser(description="P0 Portal Verification")
    parser.add_argument("--test", help="Run specific test (b1, b2, d1, d2, d4, g3, g4)")
    parser.add_argument("--list", action="store_true", help="List available tests")
    args = parser.parse_args()

    if args.list:
        print("\nAvailable P0 tests:")
        print("-" * 60)
        for key, (desc, _) in TESTS.items():
            reqs = []
            if key in ("d1", "d2", "g3"):
                reqs.append("NFS_MOUNT_PATH")
            if key in ("d4",):
                reqs.append("SMB_MOUNT_PATH (manual)")
            req_str = f" [requires: {', '.join(reqs)}]" if reqs else ""
            print(f"  {key:4s} — {desc}{req_str}")
        print(f"\nEnvironment: S3AP_ALIAS={S3AP_ALIAS or '(not set)'}")
        print(f"             NFS_MOUNT_PATH={NFS_MOUNT or '(not set)'}")
        print(f"             SMB_MOUNT_PATH={SMB_MOUNT or '(not set)'}")
        return

    if args.test:
        if args.test not in TESTS:
            print(f"Unknown test: {args.test}. Use --list to see available tests.")
            return
        desc, func = TESTS[args.test]
        logger.info(f"Running: {desc}")
        func()
    else:
        # Run all tests that can be executed
        logger.info("Running all P0 tests with available environment...")
        logger.info(f"S3AP_ALIAS: {S3AP_ALIAS or '(NOT SET — most tests will skip)'}")
        logger.info(f"NFS_MOUNT_PATH: {NFS_MOUNT or '(not set — cross-protocol tests will skip)'}")
        print()
        for key, (desc, func) in TESTS.items():
            logger.info(f"{'='*60}")
            logger.info(f"Running {key}: {desc}")
            logger.info(f"{'='*60}")
            try:
                func()
            except Exception as e:
                logger.error(f"Test {key} failed with exception: {e}")
            print()


if __name__ == "__main__":
    main()
