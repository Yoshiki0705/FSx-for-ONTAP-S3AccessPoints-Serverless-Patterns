"""Unified Portal Verification Script — P0 + P3 tests with consolidated report.

Runs all environment-dependent verification tests in one pass and generates
a consolidated JSON report at .private/p0-results/consolidated_report.json.

Includes:
  P0 (pre-production): B-1, B-2, D-1, D-2, D-4, G-3, G-4
  P3 (future):         B-3 (Nextcloud vs NFS), G-1 (cross-region latency)

Environment variables (required):
    S3AP_ALIAS          - S3 Access Point alias
    AWS_REGION          - AWS region (default: ap-northeast-1)

Environment variables (optional, enables more tests):
    NFS_MOUNT_PATH      - NFS mount point (enables D-1, D-2, G-3, B-3)
    SMB_MOUNT_PATH      - SMB mount point (enables D-4)
    NEXTCLOUD_URL       - Nextcloud base URL (enables B-3, e.g., http://localhost:8080)
    NEXTCLOUD_USER      - Nextcloud admin user (default: admin)
    NEXTCLOUD_PASS      - Nextcloud admin password
    CROSS_REGION_AP     - S3 AP alias in different region (enables G-1)
    CROSS_REGION        - Region of CROSS_REGION_AP (e.g., us-east-1)

Usage:
    # Run all available tests
    python3 scripts/verify_portal_all.py

    # Run specific category
    python3 scripts/verify_portal_all.py --category p0
    python3 scripts/verify_portal_all.py --category p3

    # Generate report only (uses cached results)
    python3 scripts/verify_portal_all.py --report

    # List all tests with requirements
    python3 scripts/verify_portal_all.py --list

CAVEAT: Results are from a specific test environment and represent a sizing
reference, not a service limit.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.config import Config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

REGION = os.environ.get("AWS_REGION", "ap-northeast-1")
S3AP_ALIAS = os.environ.get("S3AP_ALIAS", "")
NFS_MOUNT = os.environ.get("NFS_MOUNT_PATH", "")
SMB_MOUNT = os.environ.get("SMB_MOUNT_PATH", "")
NEXTCLOUD_URL = os.environ.get("NEXTCLOUD_URL", "")
NEXTCLOUD_USER = os.environ.get("NEXTCLOUD_USER", "admin")
NEXTCLOUD_PASS = os.environ.get("NEXTCLOUD_PASS", "")
CROSS_REGION_AP = os.environ.get("CROSS_REGION_AP", "")
CROSS_REGION = os.environ.get("CROSS_REGION", "us-east-1")
RESULTS_DIR = Path(__file__).parent.parent / ".private" / "p0-results"


def _s3_client(region: str = REGION):
    return boto3.client(
        "s3",
        region_name=region,
        endpoint_url=f"https://s3.{region}.amazonaws.com",
        config=Config(signature_version="s3v4"),
    )


def _write_result(test_id: str, result: dict) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = RESULTS_DIR / f"{test_id}_{ts}.json"
    result["test_id"] = test_id
    result["timestamp"] = ts
    result["environment"] = {
        "region": REGION,
        "s3ap_alias": S3AP_ALIAS,
        "nfs_mount": NFS_MOUNT,
        "smb_mount": SMB_MOUNT,
    }
    with open(path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    return path


# ─── P3: B-3 Nextcloud S3 AP vs NFSv3 Performance ───────────────────────────


def test_b3_nextcloud_vs_nfs():
    """B-3: Compare read latency — Nextcloud (S3 AP) vs NFSv3 direct mount."""
    if not NFS_MOUNT:
        logger.warning("B-3 skipped: NFS_MOUNT_PATH not set")
        return None
    if not NEXTCLOUD_URL or not NEXTCLOUD_PASS:
        logger.warning("B-3 skipped: NEXTCLOUD_URL or NEXTCLOUD_PASS not set")
        return None

    import urllib3

    http = urllib3.PoolManager()

    # Find a test file accessible from both NFS and Nextcloud
    test_files = list(Path(NFS_MOUNT).glob("*"))[:5]
    if not test_files:
        return {"error": "No files found on NFS mount for comparison"}

    results = []
    for fpath in test_files:
        if fpath.is_dir() or fpath.stat().st_size == 0:
            continue

        filename = fpath.name
        file_size = fpath.stat().st_size

        # NFS direct read
        nfs_start = time.perf_counter()
        _ = fpath.read_bytes()
        nfs_ms = (time.perf_counter() - nfs_start) * 1000

        # Nextcloud WebDAV read
        webdav_url = f"{NEXTCLOUD_URL}/remote.php/dav/files/{NEXTCLOUD_USER}/{filename}"
        headers = urllib3.make_headers(basic_auth=f"{NEXTCLOUD_USER}:{NEXTCLOUD_PASS}")
        nc_start = time.perf_counter()
        try:
            resp = http.request("GET", webdav_url, headers=headers)
            if resp.status == 200:
                nc_ms = (time.perf_counter() - nc_start) * 1000
                nc_success = True
            else:
                nc_ms = None
                nc_success = False
        except Exception:
            nc_ms = None
            nc_success = False

        results.append(
            {
                "file": filename,
                "size_bytes": file_size,
                "nfs_read_ms": round(nfs_ms, 2),
                "nextcloud_read_ms": round(nc_ms, 2) if nc_ms else None,
                "nextcloud_success": nc_success,
                "ratio": round(nc_ms / nfs_ms, 2) if nc_ms and nfs_ms > 0 else None,
            }
        )

    nfs_latencies = [r["nfs_read_ms"] for r in results if r["nfs_read_ms"]]
    nc_latencies = [r["nextcloud_read_ms"] for r in results if r["nextcloud_read_ms"]]

    result = {
        "files_tested": len(results),
        "nfs_mean_ms": round(statistics.mean(nfs_latencies), 2) if nfs_latencies else None,
        "nextcloud_mean_ms": round(statistics.mean(nc_latencies), 2) if nc_latencies else None,
        "avg_ratio": round(statistics.mean(nc_latencies) / statistics.mean(nfs_latencies), 2)
        if nc_latencies and nfs_latencies
        else None,
        "details": results,
        "interpretation": (
            "Ratio > 1 means Nextcloud (S3 AP via WebDAV) is slower than NFS direct. "
            "Expected: Nextcloud adds HTTP + External Storage overhead (typically 3-10x for small files). "
            "For large files, the difference narrows as transfer time dominates."
        ),
    }
    _write_result("b3", result)
    logger.info(f"B-3: NFS mean={result['nfs_mean_ms']}ms, Nextcloud mean={result['nextcloud_mean_ms']}ms")
    return result


# ─── P3: G-1 Cross-Region Latency ───────────────────────────────────────────


def test_g1_cross_region_latency():
    """G-1: Measure S3 AP access latency from a different region."""
    if not S3AP_ALIAS:
        logger.warning("G-1 skipped: S3AP_ALIAS not set")
        return None

    # Test same-region as baseline
    s3_local = _s3_client(REGION)
    s3_remote = _s3_client(CROSS_REGION) if CROSS_REGION != REGION else None

    # Find a test file
    resp = s3_local.list_objects_v2(Bucket=S3AP_ALIAS, MaxKeys=3)
    if not resp.get("Contents"):
        return {"error": "No files on S3 AP for latency test"}

    test_key = resp["Contents"][0]["Key"]
    logger.info(f"G-1: Testing latency for {test_key}")

    # Same-region latency (baseline)
    local_latencies = []
    for _ in range(10):
        start = time.perf_counter()
        obj = s3_local.get_object(Bucket=S3AP_ALIAS, Key=test_key)
        obj["Body"].read()
        local_latencies.append((time.perf_counter() - start) * 1000)

    # Cross-region latency (if configured)
    remote_latencies = []
    remote_error = None
    if s3_remote:
        for _ in range(10):
            try:
                start = time.perf_counter()
                obj = s3_remote.get_object(Bucket=S3AP_ALIAS, Key=test_key)
                obj["Body"].read()
                remote_latencies.append((time.perf_counter() - start) * 1000)
            except Exception as e:
                remote_error = str(e)
                break
    else:
        remote_error = "CROSS_REGION same as AWS_REGION — set a different region to test"

    result = {
        "test_file": test_key,
        "local_region": REGION,
        "remote_region": CROSS_REGION,
        "local_latency_ms": {
            "mean": round(statistics.mean(local_latencies), 2),
            "p50": round(statistics.median(local_latencies), 2),
            "p95": round(sorted(local_latencies)[int(len(local_latencies) * 0.95)], 2),
        },
        "remote_latency_ms": {
            "mean": round(statistics.mean(remote_latencies), 2),
            "p50": round(statistics.median(remote_latencies), 2),
            "p95": round(sorted(remote_latencies)[int(len(remote_latencies) * 0.95)], 2),
        }
        if remote_latencies
        else None,
        "remote_error": remote_error,
        "cross_region_overhead_ms": round(statistics.mean(remote_latencies) - statistics.mean(local_latencies), 2)
        if remote_latencies
        else None,
        "interpretation": (
            "Cross-region access adds network latency (typically 50-200ms depending on regions). "
            "For interactive portal use, keep users and S3 AP in the same region. "
            "Cross-region is acceptable for batch/async operations."
        ),
    }
    _write_result("g1", result)
    logger.info(
        f"G-1: local={result['local_latency_ms']['mean']}ms, remote={result.get('remote_latency_ms', {}).get('mean', 'N/A')}ms"
    )
    return result


# ─── Consolidated Report ─────────────────────────────────────────────────────


def generate_report():
    """Generate consolidated report from all result files."""
    if not RESULTS_DIR.exists():
        logger.warning("No results directory found")
        return

    results = {}
    for f in sorted(RESULTS_DIR.glob("*.json")):
        if f.name == "consolidated_report.json":
            continue
        try:
            with open(f) as fh:
                data = json.load(fh)
                test_id = data.get("test_id", f.stem)
                # Keep latest result per test_id
                results[test_id] = data
        except json.JSONDecodeError:
            continue

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_tests": len(results),
        "tests": results,
        "summary": {
            "passed": sum(1 for r in results.values() if not r.get("error")),
            "failed": sum(1 for r in results.values() if r.get("error")),
            "test_ids": sorted(results.keys()),
        },
    }

    report_path = RESULTS_DIR / "consolidated_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    logger.info(f"Report: {report_path}")
    logger.info(
        f"  Total: {report['total_tests']} | Passed: {report['summary']['passed']} | Failed: {report['summary']['failed']}"
    )
    return report


# ─── Main ────────────────────────────────────────────────────────────────────

ALL_TESTS = {
    # P0 tests (imported from verify_portal_p0.py)
    "b1": ("P0", "B-1: Throughput baseline"),
    "b2": ("P0", "B-2: Tiering latency"),
    "d1": ("P0", "D-1: Write-in-progress read"),
    "d2": ("P0", "D-2: PutObject visibility"),
    "d4": ("P0", "D-4: SMB oplock interaction"),
    "g3": ("P0", "G-3: Unicode filenames"),
    "g4": ("P0", "G-4: Quota error"),
    # P3 tests (native to this file)
    "b3": ("P3", "B-3: Nextcloud vs NFS performance"),
    "g1": ("P3", "G-1: Cross-region latency"),
}

P3_FUNCS = {
    "b3": test_b3_nextcloud_vs_nfs,
    "g1": test_g1_cross_region_latency,
}


def main():
    parser = argparse.ArgumentParser(description="Unified Portal Verification (P0 + P3)")
    parser.add_argument("--category", choices=["p0", "p3", "all"], default="all")
    parser.add_argument("--test", help="Run specific test by ID")
    parser.add_argument("--report", action="store_true", help="Generate report from cached results")
    parser.add_argument("--list", action="store_true", help="List all tests")
    args = parser.parse_args()

    if args.list:
        print("\nAll verification tests:")
        print("-" * 70)
        for tid, (cat, desc) in ALL_TESTS.items():
            reqs = []
            if tid in ("d1", "d2", "g3", "b3"):
                reqs.append("NFS_MOUNT_PATH")
            if tid == "d4":
                reqs.append("SMB_MOUNT_PATH")
            if tid == "b3":
                reqs.append("NEXTCLOUD_URL")
            if tid == "g1":
                reqs.append("CROSS_REGION_AP (optional)")
            req_str = f" [{', '.join(reqs)}]" if reqs else ""
            print(f"  [{cat}] {tid:4s} — {desc}{req_str}")
        print("\nEnvironment:")
        print(f"  S3AP_ALIAS={S3AP_ALIAS or '(not set)'}")
        print(f"  NFS_MOUNT_PATH={NFS_MOUNT or '(not set)'}")
        print(f"  NEXTCLOUD_URL={NEXTCLOUD_URL or '(not set)'}")
        print(f"  CROSS_REGION={CROSS_REGION}")
        return

    if args.report:
        generate_report()
        return

    if args.test:
        if args.test in P3_FUNCS:
            logger.info(f"Running P3 test: {args.test}")
            P3_FUNCS[args.test]()
        else:
            # Delegate to P0 script
            import subprocess

            subprocess.run(
                ["python3", "scripts/verify_portal_p0.py", "--test", args.test],
                cwd=Path(__file__).parent.parent,
            )
        return

    # Run all applicable tests
    logger.info("=" * 70)
    logger.info("Unified Portal Verification — P0 + P3")
    logger.info("=" * 70)

    if args.category in ("p0", "all"):
        logger.info("\n--- P0 Tests (pre-production) ---")
        import subprocess

        subprocess.run(
            ["python3", "scripts/verify_portal_p0.py"],
            cwd=Path(__file__).parent.parent,
        )

    if args.category in ("p3", "all"):
        logger.info("\n--- P3 Tests (future/environment-dependent) ---")
        for tid, func in P3_FUNCS.items():
            logger.info(f"\nRunning {tid}: {ALL_TESTS[tid][1]}")
            try:
                func()
            except Exception as e:
                logger.error(f"Test {tid} failed: {e}")

    # Generate consolidated report
    logger.info("\n--- Generating consolidated report ---")
    generate_report()


if __name__ == "__main__":
    main()
