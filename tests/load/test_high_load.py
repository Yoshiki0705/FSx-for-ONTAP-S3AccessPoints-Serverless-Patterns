"""High-Load Testing — 1000+ events/sec 負荷テスト.

FPolicy イベントパイプラインに高負荷を投入し、
Fargate オートスケーリングとシステムスループットを検証する。

実環境（FSx ONTAP、ECS Fargate、SQS、CloudWatch）を使用する。
CI 環境では pytest.mark.load で skip 可能。

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import boto3
import pytest

logger = logging.getLogger(__name__)


@dataclass
class HighLoadConfig:
    """高負荷テストの設定."""

    target_events_per_sec: int = 1000
    duration_sec: int = 300  # 5 minutes sustained load
    ramp_up_sec: int = 60  # Linear ramp from 0 to target
    fargate_min_tasks: int = 1
    fargate_max_tasks: int = 10
    ecs_cluster: str = ""
    ecs_service: str = ""
    sqs_queue_url: str = ""
    nfs_mount_path: str = ""
    cloudwatch_namespace: str = "FSxN-S3AP-Patterns"
    region: str = "ap-northeast-1"


@dataclass
class HighLoadResult:
    """高負荷テストの結果."""

    achieved_events_per_sec: float = 0.0
    total_events_sent: int = 0
    total_events_processed: int = 0
    events_dropped: int = 0
    fargate_tasks_scaled_to: int = 0
    scale_out_latency_sec: float = 0.0
    p50_e2e_latency_ms: float = 0.0
    p95_e2e_latency_ms: float = 0.0
    p99_e2e_latency_ms: float = 0.0
    error_rate_pct: float = 0.0
    sqs_approximate_age_max_sec: float = 0.0
    warnings: list[str] = field(default_factory=list)


def calculate_ramp_rate(elapsed_sec: float, ramp_up_sec: int, target_rate: int) -> int:
    """線形 ramp-up における現在秒の目標レートを計算する.

    Args:
        elapsed_sec: ramp-up 開始からの経過秒数
        ramp_up_sec: ramp-up 期間（秒）
        target_rate: 最終目標レート（events/sec）

    Returns:
        現在秒の目標レート（events/sec）
    """
    if ramp_up_sec <= 0:
        return target_rate
    if elapsed_sec <= 0:
        return 0
    if elapsed_sec >= ramp_up_sec:
        return target_rate
    return int((elapsed_sec / ramp_up_sec) * target_rate)


def calculate_percentile(values: list[float], percentile: float) -> float:
    """ソート済みリストからパーセンタイル値を計算する.

    Args:
        values: 計測値のリスト
        percentile: パーセンタイル（0-100）

    Returns:
        指定パーセンタイルの値。空リストの場合は 0.0。
    """
    if not values:
        return 0.0
    sorted_values = sorted(values)
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    # nearest-rank method
    rank = (percentile / 100.0) * (n - 1)
    lower = int(rank)
    upper = lower + 1
    if upper >= n:
        return sorted_values[-1]
    fraction = rank - lower
    return sorted_values[lower] + fraction * (sorted_values[upper] - sorted_values[lower])


class HighLoadTester:
    """1000+ events/sec の高負荷テスター.

    段階的な負荷増加（ramp-up）で FPolicy イベントパイプラインに負荷を投入し、
    Fargate オートスケーリングとシステムスループットを検証する。
    """

    def __init__(self, config: HighLoadConfig) -> None:
        self.config = config
        self._ecs_client = boto3.client("ecs", region_name=config.region)
        self._sqs_client = boto3.client("sqs", region_name=config.region)
        self._cw_client = boto3.client("cloudwatch", region_name=config.region)
        self._latencies: list[float] = []
        self._errors: list[str] = []
        self._events_sent: int = 0
        self._scale_observations: list[dict[str, Any]] = []
        self._sqs_age_observations: list[float] = []
        self._start_time: float = 0.0
        self._initial_task_count: int = 0

    async def execute(self) -> HighLoadResult:
        """高負荷テストを実行する.

        ramp-up → sustained load → メトリクス収集の順で実行。

        Returns:
            HighLoadResult: テスト結果
        """
        logger.info(
            "Starting high-load test: target=%d events/sec, "
            "duration=%ds, ramp_up=%ds",
            self.config.target_events_per_sec,
            self.config.duration_sec,
            self.config.ramp_up_sec,
        )

        self._start_time = time.time()
        self._initial_task_count = await self._get_current_task_count()

        # Run load generation and monitoring concurrently
        await asyncio.gather(
            self.generate_load(),
            self.monitor_scaling(),
        )

        # Collect final metrics
        metrics = await self.collect_metrics()

        # Build result
        result = self._build_result(metrics)

        logger.info(
            "High-load test complete: sent=%d, processed=%d, "
            "dropped=%d, scaled_to=%d tasks",
            result.total_events_sent,
            result.total_events_processed,
            result.events_dropped,
            result.fargate_tasks_scaled_to,
        )

        return result

    async def generate_load(self) -> None:
        """線形 ramp-up + sustained load でファイル操作を並列生成する.

        ramp-up フェーズ: 0 → target_events_per_sec へ線形に増加
        sustained フェーズ: target_events_per_sec を duration_sec 間維持
        """
        total_duration = self.config.ramp_up_sec + self.config.duration_sec
        start = time.time()

        for second in range(total_duration):
            elapsed = time.time() - start

            # Calculate target rate for this second
            if second < self.config.ramp_up_sec:
                current_rate = calculate_ramp_rate(
                    elapsed_sec=second + 1,
                    ramp_up_sec=self.config.ramp_up_sec,
                    target_rate=self.config.target_events_per_sec,
                )
            else:
                current_rate = self.config.target_events_per_sec

            # Generate file operations in parallel for this second
            tasks = []
            for _ in range(current_rate):
                tasks.append(self._create_file_operation())

            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for r in results:
                    if isinstance(r, Exception):
                        self._errors.append(str(r))
                    else:
                        self._events_sent += 1
                        if r is not None:
                            self._latencies.append(r)

            # Pace to 1-second intervals
            target_time = start + second + 1
            sleep_time = target_time - time.time()
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

        logger.info("Load generation complete: %d events sent", self._events_sent)

    async def monitor_scaling(self) -> dict[str, Any]:
        """Fargate タスク数のスケーリングを監視する.

        テスト実行中に定期的に ECS サービスのタスク数を取得し、
        スケールアウトレイテンシを計測する。

        Returns:
            スケーリング監視結果の辞書
        """
        total_duration = self.config.ramp_up_sec + self.config.duration_sec
        poll_interval_sec = 10
        start = time.time()
        scale_out_detected_at: float | None = None

        while (time.time() - start) < total_duration:
            try:
                task_count = await self._get_current_task_count()
                observation = {
                    "timestamp": time.time(),
                    "task_count": task_count,
                    "elapsed_sec": time.time() - start,
                }
                self._scale_observations.append(observation)

                # Detect first scale-out event
                if (
                    task_count > self._initial_task_count
                    and scale_out_detected_at is None
                ):
                    scale_out_detected_at = time.time() - start
                    logger.info(
                        "Scale-out detected at %.1fs: %d → %d tasks",
                        scale_out_detected_at,
                        self._initial_task_count,
                        task_count,
                    )

                # Monitor SQS queue age
                sqs_age = await self._get_sqs_age()
                self._sqs_age_observations.append(sqs_age)

            except Exception as e:
                logger.warning("Monitoring error: %s", e)

            await asyncio.sleep(poll_interval_sec)

        return {
            "scale_out_latency_sec": scale_out_detected_at or 0.0,
            "observations": self._scale_observations,
        }

    async def collect_metrics(self) -> dict[str, Any]:
        """E2E レイテンシ、SQS age、エラーレートを収集する.

        Returns:
            メトリクス辞書:
            - p50_latency_ms, p95_latency_ms, p99_latency_ms
            - sqs_age_max_sec
            - error_rate_pct
            - total_processed
        """
        # Calculate percentile latencies
        p50 = calculate_percentile(self._latencies, 50)
        p95 = calculate_percentile(self._latencies, 95)
        p99 = calculate_percentile(self._latencies, 99)

        # SQS max age
        sqs_age_max = max(self._sqs_age_observations) if self._sqs_age_observations else 0.0

        # Error rate
        total_attempts = self._events_sent + len(self._errors)
        error_rate = (
            (len(self._errors) / total_attempts * 100.0) if total_attempts > 0 else 0.0
        )

        # Get processed count from SQS (approximate)
        total_processed = await self._get_processed_count()

        return {
            "p50_latency_ms": p50,
            "p95_latency_ms": p95,
            "p99_latency_ms": p99,
            "sqs_age_max_sec": sqs_age_max,
            "error_rate_pct": error_rate,
            "total_processed": total_processed,
        }

    def _build_result(self, metrics: dict[str, Any]) -> HighLoadResult:
        """テスト結果を構築する."""
        # Determine max task count observed
        max_tasks = max(
            (obs["task_count"] for obs in self._scale_observations),
            default=self._initial_task_count,
        )

        # Scale-out latency
        scale_out_latency = 0.0
        for obs in self._scale_observations:
            if obs["task_count"] > self._initial_task_count:
                scale_out_latency = obs["elapsed_sec"]
                break

        total_processed = metrics.get("total_processed", 0)
        events_dropped = max(0, self._events_sent - total_processed)

        # Calculate achieved rate
        total_duration = self.config.ramp_up_sec + self.config.duration_sec
        achieved_rate = self._events_sent / total_duration if total_duration > 0 else 0.0

        result = HighLoadResult(
            achieved_events_per_sec=achieved_rate,
            total_events_sent=self._events_sent,
            total_events_processed=total_processed,
            events_dropped=events_dropped,
            fargate_tasks_scaled_to=max_tasks,
            scale_out_latency_sec=scale_out_latency,
            p50_e2e_latency_ms=metrics["p50_latency_ms"],
            p95_e2e_latency_ms=metrics["p95_latency_ms"],
            p99_e2e_latency_ms=metrics["p99_latency_ms"],
            error_rate_pct=metrics["error_rate_pct"],
            sqs_approximate_age_max_sec=metrics["sqs_age_max_sec"],
        )

        # Requirement 9.7: スケールアウト未発生時の警告
        if max_tasks <= self._initial_task_count:
            warning = (
                f"WARNING: No scale-out observed. "
                f"Fargate tasks remained at {self._initial_task_count}. "
                f"Check auto-scaling configuration."
            )
            result.warnings.append(warning)
            logger.warning(warning)

        return result

    async def _create_file_operation(self) -> float | None:
        """NFS マウント上にテストファイルを作成する.

        Returns:
            操作のレイテンシ（ms）。失敗時は None。
        """
        file_name = f"load_test_{uuid.uuid4().hex[:12]}.dat"
        file_path = Path(self.config.nfs_mount_path) / file_name

        start = time.time()
        try:
            # Create a small test file to trigger FPolicy event
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, self._write_test_file, str(file_path)
            )
            latency_ms = (time.time() - start) * 1000.0
            return latency_ms
        except Exception as e:
            logger.debug("File operation failed: %s", e)
            raise

    @staticmethod
    def _write_test_file(path: str) -> None:
        """テストファイルを書き込む（同期）."""
        with open(path, "w") as f:
            f.write(f"load-test-payload-{uuid.uuid4().hex}\n")

    async def _get_current_task_count(self) -> int:
        """ECS サービスの現在のタスク数を取得する."""
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._ecs_client.describe_services(
                    cluster=self.config.ecs_cluster,
                    services=[self.config.ecs_service],
                ),
            )
            services = response.get("services", [])
            if services:
                return services[0].get("runningCount", 0)
            return 0
        except Exception as e:
            logger.warning("Failed to get task count: %s", e)
            return 0

    async def _get_sqs_age(self) -> float:
        """SQS キューの ApproximateAgeOfOldestMessage を取得する."""
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._sqs_client.get_queue_attributes(
                    QueueUrl=self.config.sqs_queue_url,
                    AttributeNames=["ApproximateAgeOfOldestMessage"],
                ),
            )
            attrs = response.get("Attributes", {})
            return float(attrs.get("ApproximateAgeOfOldestMessage", "0"))
        except Exception as e:
            logger.warning("Failed to get SQS age: %s", e)
            return 0.0

    async def _get_processed_count(self) -> int:
        """処理済みイベント数を SQS メトリクスから推定する."""
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._sqs_client.get_queue_attributes(
                    QueueUrl=self.config.sqs_queue_url,
                    AttributeNames=[
                        "ApproximateNumberOfMessages",
                        "ApproximateNumberOfMessagesNotVisible",
                    ],
                ),
            )
            attrs = response.get("Attributes", {})
            in_queue = int(attrs.get("ApproximateNumberOfMessages", "0"))
            in_flight = int(attrs.get("ApproximateNumberOfMessagesNotVisible", "0"))
            # Processed = sent - (still in queue + in flight)
            processed = max(0, self._events_sent - in_queue - in_flight)
            return processed
        except Exception as e:
            logger.warning("Failed to get processed count: %s", e)
            return 0


# ---------------------------------------------------------------------------
# Pytest テスト関数
# ---------------------------------------------------------------------------

load = pytest.mark.load


@pytest.mark.load
class TestHighLoadTester:
    """HighLoadTester の統合テスト.

    実環境が必要なため @pytest.mark.load でマーク。
    CI では -m 'not load' で skip 可能。
    """

    @pytest.fixture
    def config(self) -> HighLoadConfig:
        """テスト用設定を環境変数から構築する."""
        return HighLoadConfig(
            target_events_per_sec=int(
                os.environ.get("LOAD_TEST_TARGET_RATE", "1000")
            ),
            duration_sec=int(os.environ.get("LOAD_TEST_DURATION_SEC", "300")),
            ramp_up_sec=int(os.environ.get("LOAD_TEST_RAMP_UP_SEC", "60")),
            ecs_cluster=os.environ.get("ECS_CLUSTER", "fpolicy-cluster"),
            ecs_service=os.environ.get("ECS_SERVICE", "fpolicy-service"),
            sqs_queue_url=os.environ.get("SQS_QUEUE_URL", ""),
            nfs_mount_path=os.environ.get("NFS_MOUNT_PATH", "/mnt/fsxn"),
            region=os.environ.get("AWS_DEFAULT_REGION", "ap-northeast-1"),
        )

    @pytest.mark.asyncio
    async def test_execute_high_load(self, config: HighLoadConfig):
        """高負荷テストを実行し結果を検証する."""
        tester = HighLoadTester(config)
        result = await tester.execute()

        # Basic assertions
        assert result.total_events_sent > 0
        assert result.achieved_events_per_sec > 0
        assert result.p50_e2e_latency_ms <= result.p95_e2e_latency_ms
        assert result.p95_e2e_latency_ms <= result.p99_e2e_latency_ms
        assert result.error_rate_pct < 10.0  # Less than 10% errors

        # Log results for analysis
        logger.info("=== High-Load Test Results ===")
        logger.info("Achieved rate: %.1f events/sec", result.achieved_events_per_sec)
        logger.info("Total sent: %d", result.total_events_sent)
        logger.info("Total processed: %d", result.total_events_processed)
        logger.info("Events dropped: %d", result.events_dropped)
        logger.info("Fargate scaled to: %d tasks", result.fargate_tasks_scaled_to)
        logger.info("Scale-out latency: %.1fs", result.scale_out_latency_sec)
        logger.info("P50 latency: %.1fms", result.p50_e2e_latency_ms)
        logger.info("P95 latency: %.1fms", result.p95_e2e_latency_ms)
        logger.info("P99 latency: %.1fms", result.p99_e2e_latency_ms)
        logger.info("Error rate: %.2f%%", result.error_rate_pct)
        logger.info("SQS max age: %.1fs", result.sqs_approximate_age_max_sec)
        if result.warnings:
            for w in result.warnings:
                logger.warning(w)


class TestRampRateCalculation:
    """calculate_ramp_rate のユニットテスト."""

    def test_zero_elapsed(self):
        """経過 0 秒ではレート 0."""
        assert calculate_ramp_rate(0, 60, 1000) == 0

    def test_midpoint(self):
        """ramp-up 中間点では目標の半分."""
        rate = calculate_ramp_rate(30, 60, 1000)
        assert rate == 500

    def test_full_ramp(self):
        """ramp-up 完了時は目標レート."""
        rate = calculate_ramp_rate(60, 60, 1000)
        assert rate == 1000

    def test_beyond_ramp(self):
        """ramp-up 超過時も目標レート."""
        rate = calculate_ramp_rate(120, 60, 1000)
        assert rate == 1000

    def test_zero_ramp_up_sec(self):
        """ramp-up 0 秒では即座に目標レート."""
        rate = calculate_ramp_rate(0, 0, 1000)
        assert rate == 1000

    def test_linear_progression(self):
        """ramp-up が線形に増加する."""
        rates = [calculate_ramp_rate(t, 100, 1000) for t in range(1, 101)]
        # Each rate should be >= previous (monotonically non-decreasing)
        for i in range(1, len(rates)):
            assert rates[i] >= rates[i - 1]
        # Final rate should be target
        assert rates[-1] == 1000


class TestPercentileCalculation:
    """calculate_percentile のユニットテスト."""

    def test_empty_list(self):
        """空リストでは 0.0."""
        assert calculate_percentile([], 50) == 0.0

    def test_single_value(self):
        """単一値ではその値を返す."""
        assert calculate_percentile([42.0], 50) == 42.0
        assert calculate_percentile([42.0], 99) == 42.0

    def test_p50_even_list(self):
        """偶数個リストの P50."""
        values = [10.0, 20.0, 30.0, 40.0]
        p50 = calculate_percentile(values, 50)
        assert 20.0 <= p50 <= 30.0

    def test_p99_large_list(self):
        """大きなリストの P99."""
        values = list(range(1, 101))  # 1 to 100
        p99 = calculate_percentile([float(v) for v in values], 99)
        assert p99 >= 99.0

    def test_monotonicity(self):
        """P50 <= P95 <= P99 の単調性."""
        values = [float(i) for i in range(1, 1001)]
        p50 = calculate_percentile(values, 50)
        p95 = calculate_percentile(values, 95)
        p99 = calculate_percentile(values, 99)
        assert p50 <= p95 <= p99

    def test_unsorted_input(self):
        """ソートされていない入力でも正しく計算する."""
        values = [100.0, 1.0, 50.0, 25.0, 75.0]
        p50 = calculate_percentile(values, 50)
        assert p50 == 50.0


class TestHighLoadConfig:
    """HighLoadConfig dataclass のテスト."""

    def test_default_values(self):
        """デフォルト値が正しく設定される."""
        config = HighLoadConfig()
        assert config.target_events_per_sec == 1000
        assert config.duration_sec == 300
        assert config.ramp_up_sec == 60
        assert config.fargate_min_tasks == 1
        assert config.fargate_max_tasks == 10

    def test_custom_values(self):
        """カスタム値が正しく設定される."""
        config = HighLoadConfig(
            target_events_per_sec=500,
            duration_sec=120,
            ramp_up_sec=30,
            ecs_cluster="my-cluster",
            ecs_service="my-service",
        )
        assert config.target_events_per_sec == 500
        assert config.duration_sec == 120
        assert config.ramp_up_sec == 30
        assert config.ecs_cluster == "my-cluster"
        assert config.ecs_service == "my-service"


class TestHighLoadResult:
    """HighLoadResult dataclass のテスト."""

    def test_default_values(self):
        """デフォルト値が正しく設定される."""
        result = HighLoadResult()
        assert result.achieved_events_per_sec == 0.0
        assert result.total_events_sent == 0
        assert result.events_dropped == 0
        assert result.warnings == []

    def test_warnings_list(self):
        """警告リストが正しく動作する."""
        result = HighLoadResult()
        result.warnings.append("No scale-out observed")
        assert len(result.warnings) == 1
        assert "scale-out" in result.warnings[0]
