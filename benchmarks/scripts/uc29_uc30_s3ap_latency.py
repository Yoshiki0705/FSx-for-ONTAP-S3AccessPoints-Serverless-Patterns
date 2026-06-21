#!/usr/bin/env python3
"""UC29/UC30 S3 Access Point レイテンシ ベンチマーク（P50/P90/P95/P99）

FSx for ONTAP S3 Access Point 経由の ListObjectsV2 / GetObject のレイテンシを測定する。
benchmark-rules steering に従い、環境メタデータと分位点・エラー率を記録し、キャビアットを付す。

使い方:
  python3 uc29_uc30_s3ap_latency.py --alias <S3AP_ALIAS> --prefix ai-knowledge/ \
    --iterations 100 --warmup 5 --region ap-northeast-1 --out ../data/uc29_uc30_latency.json

注意:
  - 特定の検証環境での結果であり、本番保証値ではありません（sizing reference であり service limit ではない）。
  - FSx for ONTAP スループットは NFS/SMB/S3AP 共有。実行時の同時ワークロード有無を併記すること。
  - 平均だけでなく P99/tail を sizing シグナルとして解釈すること。
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime, timezone

import boto3


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((pct / 100.0) * (len(s) - 1)))))
    return s[k]


def _summarize(latencies_ms: list[float], errors: int) -> dict:
    total = len(latencies_ms) + errors
    return {
        "samples": len(latencies_ms),
        "mean_ms": round(statistics.fmean(latencies_ms), 2) if latencies_ms else 0.0,
        "p50_ms": round(_percentile(latencies_ms, 50), 2),
        "p90_ms": round(_percentile(latencies_ms, 90), 2),
        "p95_ms": round(_percentile(latencies_ms, 95), 2),
        "p99_ms": round(_percentile(latencies_ms, 99), 2),
        "max_ms": round(max(latencies_ms), 2) if latencies_ms else 0.0,
        "std_dev_ms": round(statistics.pstdev(latencies_ms), 2) if len(latencies_ms) > 1 else 0.0,
        "error_count": errors,
        "error_rate_pct": round(100.0 * errors / total, 2) if total else 0.0,
    }


def run(args: argparse.Namespace) -> dict:
    s3 = boto3.client("s3", region_name=args.region)

    # 対象キーを 1 件取得（GetObject 用）
    sample_key = None
    listing = s3.list_objects_v2(Bucket=args.alias, Prefix=args.prefix, MaxKeys=1)
    contents = listing.get("Contents", [])
    if contents:
        sample_key = contents[0]["Key"]

    # ウォームアップ
    for _ in range(args.warmup):
        try:
            s3.list_objects_v2(Bucket=args.alias, Prefix=args.prefix, MaxKeys=10)
        except Exception:  # noqa: BLE001
            pass

    list_lat, list_err = [], 0
    get_lat, get_err = [], 0

    for _ in range(args.iterations):
        t0 = time.perf_counter()
        try:
            s3.list_objects_v2(Bucket=args.alias, Prefix=args.prefix, MaxKeys=100)
            list_lat.append((time.perf_counter() - t0) * 1000.0)
        except Exception:  # noqa: BLE001
            list_err += 1

        if sample_key:
            t0 = time.perf_counter()
            try:
                resp = s3.get_object(Bucket=args.alias, Key=sample_key)
                resp["Body"].read()
                resp["Body"].close()
                get_lat.append((time.perf_counter() - t0) * 1000.0)
            except Exception:  # noqa: BLE001
                get_err += 1

    return {
        "benchmark_run_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "test_environment": {
            "region": args.region,
            "s3ap_alias": args.alias,
            "prefix": args.prefix,
            "network_origin": args.network_origin,
            "concurrent_workload": args.concurrent_workload,
            "client_location": args.client_location,
        },
        "test_parameters": {
            "iterations": args.iterations,
            "warmup": args.warmup,
            "sample_key_present": bool(sample_key),
        },
        "results": {
            "list_objects_v2": _summarize(list_lat, list_err),
            "get_object": _summarize(get_lat, get_err),
        },
        "caveats": [
            "特定の検証環境での結果であり、本番保証値ではない（sizing reference / not a service limit）。",
            "FSx for ONTAP スループットは NFS/SMB/S3AP 共有。同時ワークロードの有無を併記。",
            "平均ではなく P99/tail を sizing シグナルとして解釈すること。",
            "料金・サービス仕様は time-sensitive。",
        ],
    }


def main() -> None:
    p = argparse.ArgumentParser(description="UC29/UC30 S3 AP latency benchmark")
    p.add_argument("--alias", required=True, help="S3 Access Point alias (xxx-ext-s3alias)")
    p.add_argument("--prefix", default="ai-knowledge/")
    p.add_argument("--iterations", type=int, default=100)
    p.add_argument("--warmup", type=int, default=5)
    p.add_argument("--region", default="ap-northeast-1")
    p.add_argument("--network-origin", default="Internet", help="Internet or VPC")
    p.add_argument("--concurrent-workload", default="unknown", help="同時に動く NFS/SMB 等の有無")
    p.add_argument("--client-location", default="outside-vpc", help="outside-vpc / in-vpc / lambda 等")
    p.add_argument("--out", default="")
    args = p.parse_args()

    report = run(args)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {args.out}")
    print(text)


if __name__ == "__main__":
    main()
