"""S3 AP Benchmark Script for throughput capacity comparison testing.

Tests GetObject latency at various concurrency levels against FSx for ONTAP S3 Access Point.
Records: mean, p50, p90, p95, p99, max, std_dev, error_rate per concurrency level.

CAVEAT: Results are from a specific test environment and represent a sizing reference,
not a service limit. Actual performance depends on workload characteristics, network
conditions, and FSx for ONTAP configuration.

Usage:
    python3 scripts/benchmark_throughput.py --throughput 256 --concurrency 1,5,10,20,25,50
    python3 scripts/benchmark_throughput.py --throughput 512 --concurrency 1,5,10,20,25,50
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import boto3

S3_AP_ALIAS = "fsxn-eda-s3ap-fhyst3uaibf46uywh5xka84pnz8jaapn1a-ext-s3alias"
REGION = "ap-northeast-1"
ITERATIONS = 50
WARM_UP = 3

# Test file (pre-existing health marker on the volume)
TEST_KEY = "_health/marker.txt"
TEST_LABEL = "tiny (<1KB)"


def get_object_latency(s3_client, bucket: str, key: str) -> tuple[float, bool]:
    """Measure single GetObject latency in ms. Returns (latency_ms, success)."""
    start = time.perf_counter()
    try:
        resp = s3_client.get_object(Bucket=bucket, Key=key)
        resp["Body"].read()
        resp["Body"].close()
        elapsed = (time.perf_counter() - start) * 1000
        return elapsed, True
    except Exception as e:
        elapsed = (time.perf_counter() - start) * 1000
        print(f"  ERROR: {e}")
        return elapsed, False


def run_concurrent_benchmark(s3_client, bucket: str, key: str, concurrency: int, iterations: int) -> dict:
    """Run benchmark at specified concurrency level."""
    latencies: list[float] = []
    errors = 0

    # Warm-up
    for _ in range(WARM_UP):
        get_object_latency(s3_client, bucket, key)

    # Actual benchmark
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = []
        for _ in range(iterations):
            futures.append(executor.submit(get_object_latency, s3_client, bucket, key))
        for future in as_completed(futures):
            latency_ms, success = future.result()
            latencies.append(latency_ms)
            if not success:
                errors += 1

    latencies.sort()
    n = len(latencies)

    return {
        "concurrency": concurrency,
        "iterations": iterations,
        "mean_ms": round(statistics.mean(latencies), 2),
        "p50_ms": round(latencies[n // 2], 2),
        "p90_ms": round(latencies[int(n * 0.90)], 2),
        "p95_ms": round(latencies[int(n * 0.95)], 2),
        "p99_ms": round(latencies[int(n * 0.99)], 2),
        "max_ms": round(max(latencies), 2),
        "min_ms": round(min(latencies), 2),
        "std_dev_ms": round(statistics.stdev(latencies) if n > 1 else 0, 2),
        "error_count": errors,
        "error_rate_pct": round(errors / n * 100, 2),
    }


def main():
    parser = argparse.ArgumentParser(description="S3 AP Throughput Benchmark")
    parser.add_argument("--throughput", type=int, required=True, help="FSx throughput MBps")
    parser.add_argument(
        "--concurrency",
        type=str,
        default="1,5,10,20,25,50",
        help="Comma-separated concurrency levels",
    )
    parser.add_argument("--iterations", type=int, default=ITERATIONS)
    args = parser.parse_args()

    concurrency_levels = [int(x) for x in args.concurrency.split(",")]

    s3 = boto3.client("s3", region_name=REGION)

    run_id = f"s3ap-bench-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}-{args.throughput}mbps"

    print("=== S3 AP Throughput Benchmark ===")
    print(f"Run ID: {run_id}")
    print(f"Throughput Capacity: {args.throughput} MBps")
    print(f"Concurrency levels: {concurrency_levels}")
    print(f"Iterations per level: {args.iterations}")
    print(f"S3 AP: {S3_AP_ALIAS}")
    print(f"Region: {REGION}")
    print("Caller: local machine (Internet Origin)")
    print()

    # Connectivity check
    print("Connectivity check...")
    try:
        resp = s3.list_objects_v2(Bucket=S3_AP_ALIAS, Prefix="_health/", MaxKeys=1)
        if resp.get("KeyCount", 0) > 0:
            print(f"  OK - found {resp['KeyCount']} objects")
        else:
            print("  WARNING: No objects found at _health/ prefix")
            return
    except Exception as e:
        print(f"  FAILED: {e}")
        print("  S3 AP may be unavailable during throughput capacity change.")
        return

    results = {
        "benchmark_run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "test_environment": {
            "region": REGION,
            "s3ap_alias": S3_AP_ALIAS,
            "s3ap_name": "fsxn-eda-s3ap",
            "fsxn_throughput_capacity_mbps": args.throughput,
            "fsxn_storage_capacity_gb": 1024,
            "network_origin": "Internet",
            "caller": "local_machine_macos",
            "note": "Sizing reference, not service limit",
        },
        "test_parameters": {
            "object_key": TEST_KEY,
            "object_label": TEST_LABEL,
            "iterations_per_config": args.iterations,
            "warm_up_runs": WARM_UP,
            "concurrency_levels": concurrency_levels,
        },
        "results": [],
    }

    print(f"\n--- Testing: {TEST_LABEL} ({TEST_KEY}) ---")

    for conc in concurrency_levels:
        print(f"  Concurrency={conc}...", end=" ", flush=True)
        result = run_concurrent_benchmark(s3, S3_AP_ALIAS, TEST_KEY, conc, args.iterations)
        result["file_key"] = TEST_KEY
        result["file_label"] = TEST_LABEL
        results["results"].append(result)
        print(
            f"mean={result['mean_ms']:.1f}ms p50={result['p50_ms']:.1f}ms "
            f"p95={result['p95_ms']:.1f}ms p99={result['p99_ms']:.1f}ms "
            f"errors={result['error_count']}"
        )

    # Save results
    output_file = (
        f"benchmarks/data/throughput-{args.throughput}mbps-{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"
    )
    import os

    os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else ".", exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to: {output_file}")

    # Print summary table
    print(f"\n{'=' * 80}")
    print(f"SUMMARY: {args.throughput} MBps - GetObject Latency (ms)")
    print("Sizing reference, not service limit.")
    print(f"{'=' * 80}")
    print(f"{'Conc':>5} {'Mean':>8} {'P50':>8} {'P90':>8} {'P95':>8} {'P99':>8} {'Max':>8} {'Err%':>6}")
    print(f"{'-' * 5} {'-' * 8} {'-' * 8} {'-' * 8} {'-' * 8} {'-' * 8} {'-' * 8} {'-' * 6}")
    for r in results["results"]:
        print(
            f"{r['concurrency']:>5} {r['mean_ms']:>8.1f} {r['p50_ms']:>8.1f} "
            f"{r['p90_ms']:>8.1f} {r['p95_ms']:>8.1f} {r['p99_ms']:>8.1f} "
            f"{r['max_ms']:>8.1f} {r['error_rate_pct']:>5.1f}%"
        )


if __name__ == "__main__":
    main()
