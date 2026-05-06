#!/usr/bin/env python3
"""Polling vs Event-Driven レイテンシ比較スクリプト

テストファイルをアップロードし、Polling パス（UC11 既存）と
Event-Driven パス（プロトタイプ）の処理レイテンシを比較する。

使用方法:
    python scripts/compare_polling_vs_event.py \
        --polling-bucket <UC11-source-bucket> \
        --event-bucket <event-driven-source-bucket> \
        --output-bucket <output-bucket> \
        --test-files 10 \
        --prefix products/

前提条件:
    - UC11 (Retail Catalog) スタックがデプロイ済み
    - Event-Driven Prototype スタックがデプロイ済み
    - AWS 認証情報が設定済み
    - テスト用画像ファイルが test-data/ に存在

出力:
    - コンソールにレイテンシ比較結果を表示
    - CloudWatch EMF メトリクスを出力
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.observability import EmfMetrics

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def generate_test_image(size_bytes: int = 5000) -> bytes:
    """テスト用の擬似画像データを生成する。

    Args:
        size_bytes: 生成するデータサイズ（バイト）

    Returns:
        bytes: JPEG ヘッダー付きのテストデータ
    """
    # Minimal JPEG header + random-ish data
    jpeg_header = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    padding = b"\x00" * (size_bytes - len(jpeg_header) - 2)
    jpeg_footer = b"\xff\xd9"
    return jpeg_header + padding + jpeg_footer


def upload_test_files(
    s3_client,
    bucket: str,
    prefix: str,
    num_files: int,
    file_size: int = 5000,
) -> list[dict]:
    """テストファイルをアップロードし、タイムスタンプを記録する。

    Args:
        s3_client: boto3 S3 クライアント
        bucket: アップロード先バケット名
        prefix: ファイルプレフィックス
        num_files: アップロードするファイル数
        file_size: 各ファイルのサイズ（バイト）

    Returns:
        list[dict]: アップロード情報のリスト
    """
    uploads = []
    for i in range(num_files):
        key = f"{prefix}test_image_{i:04d}.jpg"
        image_data = generate_test_image(file_size)

        upload_start = time.time()
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=image_data,
            ContentType="image/jpeg",
        )
        upload_end = time.time()

        uploads.append({
            "key": key,
            "size": file_size,
            "upload_time": datetime.now(timezone.utc).isoformat(),
            "upload_timestamp": upload_start,
            "upload_duration_ms": (upload_end - upload_start) * 1000,
        })

        logger.info("Uploaded: %s (%.1f ms)", key, (upload_end - upload_start) * 1000)

    return uploads


def wait_for_processing(
    s3_client,
    output_bucket: str,
    expected_keys: list[str],
    timeout_seconds: int = 300,
    poll_interval: int = 5,
) -> dict[str, float]:
    """処理完了を待機し、検出時刻を記録する。

    Args:
        s3_client: boto3 S3 クライアント
        output_bucket: 出力バケット名
        expected_keys: 期待する出力キーのリスト
        timeout_seconds: タイムアウト（秒）
        poll_interval: ポーリング間隔（秒）

    Returns:
        dict: キー → 検出タイムスタンプのマッピング
    """
    start_time = time.time()
    detected = {}

    while time.time() - start_time < timeout_seconds:
        for key in expected_keys:
            if key in detected:
                continue
            try:
                s3_client.head_object(Bucket=output_bucket, Key=key)
                detected[key] = time.time()
                logger.info("Detected output: %s", key)
            except s3_client.exceptions.ClientError:
                pass

        if len(detected) == len(expected_keys):
            break

        time.sleep(poll_interval)

    return detected


def calculate_latency_stats(latencies: list[float]) -> dict:
    """レイテンシ統計を計算する。

    Args:
        latencies: レイテンシ値のリスト（ミリ秒）

    Returns:
        dict: 統計情報
    """
    if not latencies:
        return {"count": 0, "avg": 0, "min": 0, "max": 0, "p50": 0, "p95": 0, "p99": 0}

    sorted_latencies = sorted(latencies)
    n = len(sorted_latencies)

    return {
        "count": n,
        "avg": sum(sorted_latencies) / n,
        "min": sorted_latencies[0],
        "max": sorted_latencies[-1],
        "p50": sorted_latencies[n // 2],
        "p95": sorted_latencies[int(n * 0.95)],
        "p99": sorted_latencies[int(n * 0.99)],
    }


def run_comparison(
    polling_bucket: str,
    event_bucket: str,
    output_bucket: str,
    prefix: str,
    num_files: int,
    file_size: int,
    timeout: int,
) -> dict:
    """Polling vs Event-Driven のレイテンシ比較を実行する。

    Args:
        polling_bucket: Polling パスのソースバケット
        event_bucket: Event-Driven パスのソースバケット
        output_bucket: 出力バケット
        prefix: ファイルプレフィックス
        num_files: テストファイル数
        file_size: ファイルサイズ（バイト）
        timeout: タイムアウト（秒）

    Returns:
        dict: 比較結果
    """
    s3_client = boto3.client("s3")
    now = datetime.now(timezone.utc)
    date_prefix = now.strftime("%Y/%m/%d")

    logger.info("=" * 60)
    logger.info("Polling vs Event-Driven Latency Comparison")
    logger.info("=" * 60)
    logger.info("Polling bucket: %s", polling_bucket)
    logger.info("Event-Driven bucket: %s", event_bucket)
    logger.info("Output bucket: %s", output_bucket)
    logger.info("Test files: %d x %d bytes", num_files, file_size)
    logger.info("=" * 60)

    # --- Phase 1: Event-Driven パス ---
    logger.info("\n--- Event-Driven Path ---")
    event_uploads = upload_test_files(
        s3_client, event_bucket, prefix, num_files, file_size
    )

    # 期待する出力キー
    event_expected_keys = [
        f"tags/{date_prefix}/test_image_{i:04d}.json"
        for i in range(num_files)
    ]

    event_detected = wait_for_processing(
        s3_client, output_bucket, event_expected_keys, timeout
    )

    # Event-Driven レイテンシ計算
    event_latencies = []
    for i, upload in enumerate(event_uploads):
        key = event_expected_keys[i]
        if key in event_detected:
            latency_ms = (event_detected[key] - upload["upload_timestamp"]) * 1000
            event_latencies.append(latency_ms)

    # --- Phase 2: Polling パス ---
    logger.info("\n--- Polling Path ---")
    logger.info("Note: Polling latency depends on schedule interval.")
    logger.info("Uploading files and waiting for next scheduled execution...")

    polling_uploads = upload_test_files(
        s3_client, polling_bucket, prefix, num_files, file_size
    )

    polling_expected_keys = [
        f"tags/{date_prefix}/test_image_{i:04d}.json"
        for i in range(num_files)
    ]

    polling_detected = wait_for_processing(
        s3_client, output_bucket, polling_expected_keys, timeout
    )

    # Polling レイテンシ計算
    polling_latencies = []
    for i, upload in enumerate(polling_uploads):
        key = polling_expected_keys[i]
        if key in polling_detected:
            latency_ms = (polling_detected[key] - upload["upload_timestamp"]) * 1000
            polling_latencies.append(latency_ms)

    # --- 結果集計 ---
    event_stats = calculate_latency_stats(event_latencies)
    polling_stats = calculate_latency_stats(polling_latencies)

    results = {
        "timestamp": now.isoformat(),
        "config": {
            "num_files": num_files,
            "file_size": file_size,
            "prefix": prefix,
            "timeout": timeout,
        },
        "event_driven": {
            "stats": event_stats,
            "files_processed": len(event_latencies),
            "files_missed": num_files - len(event_latencies),
        },
        "polling": {
            "stats": polling_stats,
            "files_processed": len(polling_latencies),
            "files_missed": num_files - len(polling_latencies),
        },
        "improvement": {
            "avg_reduction_ms": polling_stats["avg"] - event_stats["avg"],
            "avg_reduction_pct": (
                ((polling_stats["avg"] - event_stats["avg"]) / polling_stats["avg"] * 100)
                if polling_stats["avg"] > 0
                else 0
            ),
        },
    }

    # --- 結果表示 ---
    logger.info("\n" + "=" * 60)
    logger.info("RESULTS")
    logger.info("=" * 60)
    logger.info("\nEvent-Driven Path:")
    logger.info("  Files processed: %d/%d", event_stats["count"], num_files)
    logger.info("  Avg latency: %.1f ms", event_stats["avg"])
    logger.info("  P50 latency: %.1f ms", event_stats["p50"])
    logger.info("  P95 latency: %.1f ms", event_stats["p95"])
    logger.info("  P99 latency: %.1f ms", event_stats["p99"])

    logger.info("\nPolling Path:")
    logger.info("  Files processed: %d/%d", polling_stats["count"], num_files)
    logger.info("  Avg latency: %.1f ms", polling_stats["avg"])
    logger.info("  P50 latency: %.1f ms", polling_stats["p50"])
    logger.info("  P95 latency: %.1f ms", polling_stats["p95"])
    logger.info("  P99 latency: %.1f ms", polling_stats["p99"])

    logger.info("\nImprovement:")
    logger.info(
        "  Avg reduction: %.1f ms (%.1f%%)",
        results["improvement"]["avg_reduction_ms"],
        results["improvement"]["avg_reduction_pct"],
    )
    logger.info("=" * 60)

    # EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="latency_comparison")
    metrics.set_dimension("UseCase", "event-driven-prototype")
    metrics.put_metric("EventDrivenAvgLatency", event_stats["avg"], "Milliseconds")
    metrics.put_metric("PollingAvgLatency", polling_stats["avg"], "Milliseconds")
    metrics.put_metric("LatencyImprovement", results["improvement"]["avg_reduction_pct"], "None")
    metrics.flush()

    return results


def main():
    """メインエントリポイント。"""
    parser = argparse.ArgumentParser(
        description="Polling vs Event-Driven レイテンシ比較スクリプト"
    )
    parser.add_argument(
        "--polling-bucket",
        required=True,
        help="Polling パスのソースバケット名（UC11 S3 AP エイリアス）",
    )
    parser.add_argument(
        "--event-bucket",
        required=True,
        help="Event-Driven パスのソースバケット名",
    )
    parser.add_argument(
        "--output-bucket",
        required=True,
        help="出力バケット名",
    )
    parser.add_argument(
        "--prefix",
        default="products/",
        help="ファイルプレフィックス (default: products/)",
    )
    parser.add_argument(
        "--test-files",
        type=int,
        default=10,
        help="テストファイル数 (default: 10)",
    )
    parser.add_argument(
        "--file-size",
        type=int,
        default=5000,
        help="ファイルサイズ（バイト） (default: 5000)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="処理完了待機タイムアウト（秒） (default: 300)",
    )
    parser.add_argument(
        "--output-json",
        help="結果を JSON ファイルに出力",
    )

    args = parser.parse_args()

    results = run_comparison(
        polling_bucket=args.polling_bucket,
        event_bucket=args.event_bucket,
        output_bucket=args.output_bucket,
        prefix=args.prefix,
        num_files=args.test_files,
        file_size=args.file_size,
        timeout=args.timeout,
    )

    if args.output_json:
        with open(args.output_json, "w") as f:
            json.dump(results, f, indent=2, default=str)
        logger.info("Results saved to: %s", args.output_json)


if __name__ == "__main__":
    main()
