"""
S3 AP Concurrent GetObject Benchmark Lambda
Measures latency for concurrent GetObject operations against FSx for ONTAP S3 Access Point.
"""

import time
import statistics
import concurrent.futures
import boto3

s3 = boto3.client("s3")


def get_object_latency(bucket_alias, key):
    """Measure single GetObject latency in ms."""
    start = time.perf_counter()
    response = s3.get_object(Bucket=bucket_alias, Key=key)
    # Read the body to ensure full transfer
    data = response["Body"].read()
    response["Body"].close()
    elapsed_ms = (time.perf_counter() - start) * 1000
    return elapsed_ms, len(data)


def run_benchmark(bucket_alias, key, concurrency, iterations):
    """Run concurrent GetObject benchmark."""
    all_latencies = []

    for i in range(iterations):
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(get_object_latency, bucket_alias, key) for _ in range(concurrency)]
            for f in concurrent.futures.as_completed(futures):
                latency, size = f.result()
                all_latencies.append(latency)

    all_latencies.sort()
    n = len(all_latencies)

    return {
        "concurrency": concurrency,
        "total_requests": n,
        "avg_ms": round(statistics.mean(all_latencies), 1),
        "p50_ms": round(all_latencies[int(n * 0.5)], 1),
        "p90_ms": round(all_latencies[int(n * 0.9)], 1),
        "p95_ms": round(all_latencies[int(n * 0.95)], 1),
        "p99_ms": round(all_latencies[int(n * 0.99)], 1),
        "min_ms": round(all_latencies[0], 1),
        "max_ms": round(all_latencies[-1], 1),
        "object_size_bytes": size if all_latencies else 0,
    }


def lambda_handler(event, context):
    bucket_alias = event.get("bucket_alias", "fsxn-eda-s3ap-fhyst3uaibf46uywh5xka84pnz8jaapn1a-ext-s3alias")
    key = event.get("key", "_health/marker.txt")
    concurrencies = event.get("concurrencies", [1, 5, 10, 25, 50])
    iterations_per_concurrency = event.get("iterations", 10)

    # First, verify access
    try:
        response = s3.list_objects_v2(Bucket=bucket_alias, MaxKeys=5)
        objects = response.get("Contents", [])
        if not objects:
            return {"error": "No objects found in S3 AP"}

        # Use the first ~1MB object if no key specified
        if key == "_health/marker.txt":
            # Find a suitable test object
            for obj in objects:
                if 500000 < obj["Size"] < 2000000:  # ~1MB
                    key = obj["Key"]
                    break
            else:
                key = objects[0]["Key"]
    except Exception as e:
        return {"error": f"Cannot access S3 AP: {str(e)}"}

    results = []
    for c in concurrencies:
        try:
            result = run_benchmark(bucket_alias, key, c, iterations_per_concurrency)
            results.append(result)
        except Exception as e:
            results.append({"concurrency": c, "error": str(e)})

    return {
        "benchmark_run_id": f"s3ap-bench-{time.strftime('%Y-%m-%d')}-002",
        "fsx_throughput_mbps": event.get("fsx_throughput_mbps", "unknown"),
        "test_key": key,
        "lambda_memory_mb": context.memory_limit_in_mb if context else "local",
        "results": results,
    }
