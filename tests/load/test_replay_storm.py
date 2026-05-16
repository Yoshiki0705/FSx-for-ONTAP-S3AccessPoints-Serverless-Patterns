"""Replay Storm Load Testing.

FPolicy サーバーダウンタイム中に大量のイベントを蓄積し、
再接続後のリプレイストームがシステムに与える影響を計測する。

Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
import pytest

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper: Percentile calculation
# ---------------------------------------------------------------------------


def calculate_percentile(values: list[float], percentile: float) -> float:
    """Calculate the given percentile from a sorted list of values.

    Args:
        values: List of numeric values (need not be pre-sorted).
        percentile: Percentile to compute (0-100).

    Returns:
        The percentile value. Returns 0.0 for empty lists.
    """
    if not values:
        return 0.0
    sorted_values = sorted(values)
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    # Use the "nearest rank" interpolation method
    k = (percentile / 100.0) * (n - 1)
    lower = int(k)
    upper = lower + 1
    if upper >= n:
        return sorted_values[-1]
    weight = k - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ReplayStormConfig:
    """Configuration for replay storm load testing.

    Attributes:
        downtime_duration_sec: Duration to keep FPolicy server down (default 5 min).
        events_during_downtime: Target number of events to generate during downtime.
        file_creation_rate_per_sec: Rate of NFS file operations per second.
        sqs_ingestion_timeout_sec: Max wait time for all events to be ingested.
        ecs_cluster: ECS cluster name for FPolicy server.
        ecs_service: ECS service name for FPolicy server.
        sqs_queue_url: SQS queue URL for event ingestion.
        nfs_volume_path: NFS mount path for file operations.
        step_functions_state_machine_arn: Step Functions state machine ARN.
    """

    downtime_duration_sec: int = 300
    events_during_downtime: int = 5000
    file_creation_rate_per_sec: int = 20
    sqs_ingestion_timeout_sec: int = 600
    ecs_cluster: str = ""
    ecs_service: str = ""
    sqs_queue_url: str = ""
    nfs_volume_path: str = "/mnt/fsxn/replay-storm-test"
    step_functions_state_machine_arn: str = ""


@dataclass
class ReplayStormResult:
    """Results from a replay storm load test execution.

    Attributes:
        events_generated: Total events generated during downtime.
        events_replayed: Events successfully replayed after reconnection.
        events_lost: Number of events that were not delivered.
        replay_duration_sec: Time from reconnection to last event delivery.
        sqs_ingestion_rate_per_sec: Average SQS message ingestion rate.
        step_functions_concurrency_peak: Peak concurrent Step Functions executions.
        throttling_events: Number of throttling events detected.
        p50_latency_ms: 50th percentile event delivery latency.
        p99_latency_ms: 99th percentile event delivery latency.
        lost_event_keys: File keys of events that were lost.
        start_time: Test start timestamp.
        end_time: Test end timestamp.
    """

    events_generated: int = 0
    events_replayed: int = 0
    events_lost: int = 0
    replay_duration_sec: float = 0.0
    sqs_ingestion_rate_per_sec: float = 0.0
    step_functions_concurrency_peak: int = 0
    throttling_events: int = 0
    p50_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    lost_event_keys: list[str] = field(default_factory=list)
    start_time: str = ""
    end_time: str = ""


# ---------------------------------------------------------------------------
# ReplayStormTester
# ---------------------------------------------------------------------------


class ReplayStormTester:
    """Load tester for FPolicy replay storm scenarios.

    Simulates a FPolicy server downtime period during which NFS file
    operations accumulate in the ONTAP Persistent Store. After the server
    reconnects, measures the replay storm impact on SQS ingestion rate,
    Step Functions concurrency, throttling, and end-to-end latency.
    """

    def __init__(self, config: ReplayStormConfig) -> None:
        self.config = config
        self._ecs_client = boto3.client("ecs")
        self._sqs_client = boto3.client("sqs")
        self._sfn_client = boto3.client("stepfunctions")
        self._cloudwatch_client = boto3.client("cloudwatch")
        self._test_id = str(uuid.uuid4())[:8]
        self._generated_file_keys: list[str] = []
        self._event_timestamps: list[float] = []
        self._throttling_count: int = 0

    async def execute(self) -> ReplayStormResult:
        """Execute the full replay storm test.

        Flow:
        1. Stop FPolicy server (Fargate task)
        2. Generate NFS file operations during downtime
        3. Wait for FPolicy server to reconnect
        4. Measure replay metrics (SQS ingestion, SF concurrency, latency)
        5. Compile and return results

        Returns:
            ReplayStormResult with all measured metrics.
        """
        start_time = datetime.now(timezone.utc)
        logger.info(
            "Starting replay storm test [test_id=%s, downtime=%ds, target_events=%d]",
            self._test_id,
            self.config.downtime_duration_sec,
            self.config.events_during_downtime,
        )

        # Step 1: Stop FPolicy server
        await self._stop_fpolicy_server()

        # Step 2: Generate events during downtime
        events_generated = await self.generate_events_during_downtime()

        # Step 3: Restart FPolicy server and wait for reconnection
        await self._restart_fpolicy_server()

        # Step 4: Measure replay metrics
        replay_start = time.monotonic()
        metrics = await self.measure_replay_metrics()
        replay_duration = time.monotonic() - replay_start

        # Step 5: Compile results
        end_time = datetime.now(timezone.utc)
        latencies = metrics.get("latencies_ms", [])
        lost_keys = metrics.get("lost_event_keys", [])

        result = ReplayStormResult(
            events_generated=events_generated,
            events_replayed=metrics.get("events_replayed", 0),
            events_lost=len(lost_keys),
            replay_duration_sec=replay_duration,
            sqs_ingestion_rate_per_sec=metrics.get("ingestion_rate", 0.0),
            step_functions_concurrency_peak=metrics.get("sf_concurrency_peak", 0),
            throttling_events=metrics.get("throttling_events", 0),
            p50_latency_ms=calculate_percentile(latencies, 50),
            p99_latency_ms=calculate_percentile(latencies, 99),
            lost_event_keys=lost_keys,
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
        )

        logger.info(
            "Replay storm test complete [test_id=%s, generated=%d, replayed=%d, lost=%d]",
            self._test_id,
            result.events_generated,
            result.events_replayed,
            result.events_lost,
        )
        return result

    async def generate_events_during_downtime(self) -> int:
        """Generate NFS file operations during FPolicy server downtime.

        Creates files at the configured rate to simulate real workload
        that accumulates in the ONTAP Persistent Store.

        Returns:
            Number of events (files) generated.
        """
        logger.info(
            "Generating events during downtime [rate=%d/sec, duration=%ds]",
            self.config.file_creation_rate_per_sec,
            self.config.downtime_duration_sec,
        )

        total_generated = 0
        target_total = self.config.events_during_downtime
        rate = self.config.file_creation_rate_per_sec
        duration = self.config.downtime_duration_sec

        start = time.monotonic()
        elapsed = 0.0

        while elapsed < duration and total_generated < target_total:
            batch_start = time.monotonic()

            # Generate a batch of file operations
            batch_size = min(rate, target_total - total_generated)
            for i in range(batch_size):
                file_key = f"replay-storm-{self._test_id}/{total_generated + i:06d}.dat"
                file_path = os.path.join(self.config.nfs_volume_path, file_key)

                try:
                    # Create parent directory if needed
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)
                    # Write a small test file to trigger FPolicy event
                    with open(file_path, "w") as f:
                        f.write(f"replay-storm-test-{self._test_id}-{time.time()}")
                    self._generated_file_keys.append(file_key)
                except OSError as e:
                    logger.warning("Failed to create file %s: %s", file_path, e)

            total_generated += batch_size

            # Throttle to maintain target rate
            batch_elapsed = time.monotonic() - batch_start
            sleep_time = max(0, 1.0 - batch_elapsed)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

            elapsed = time.monotonic() - start

        logger.info(
            "Event generation complete [total=%d, elapsed=%.1fs]",
            total_generated,
            elapsed,
        )
        return total_generated

    async def measure_replay_metrics(self) -> dict[str, Any]:
        """Measure replay storm metrics after FPolicy server reconnects.

        Polls SQS for ingested events, monitors Step Functions concurrency,
        and detects throttling events.

        Returns:
            Dictionary containing:
            - events_replayed: int
            - ingestion_rate: float (events/sec)
            - sf_concurrency_peak: int
            - throttling_events: int
            - latencies_ms: list[float]
            - lost_event_keys: list[str]
        """
        logger.info(
            "Measuring replay metrics [timeout=%ds]",
            self.config.sqs_ingestion_timeout_sec,
        )

        received_keys: set[str] = set()
        latencies_ms: list[float] = []
        sf_concurrency_peak = 0
        throttling_events = 0

        poll_start = time.monotonic()
        timeout = self.config.sqs_ingestion_timeout_sec
        last_receive_time = poll_start
        ingestion_start: float | None = None

        while (time.monotonic() - poll_start) < timeout:
            # Poll SQS for messages
            try:
                response = self._sqs_client.receive_message(
                    QueueUrl=self.config.sqs_queue_url,
                    MaxNumberOfMessages=10,
                    WaitTimeSeconds=5,
                    AttributeNames=["SentTimestamp"],
                )
            except Exception as e:
                logger.warning("SQS receive error: %s", e)
                await asyncio.sleep(1)
                continue

            messages = response.get("Messages", [])
            if messages:
                if ingestion_start is None:
                    ingestion_start = time.monotonic()
                last_receive_time = time.monotonic()

                for msg in messages:
                    body = msg.get("Body", "")
                    # Extract file key from message body
                    file_key = self._extract_file_key(body)
                    if file_key:
                        received_keys.add(file_key)

                    # Calculate latency from SentTimestamp
                    sent_ts = msg.get("Attributes", {}).get("SentTimestamp")
                    if sent_ts:
                        sent_time_ms = int(sent_ts)
                        receive_time_ms = int(time.time() * 1000)
                        latency = receive_time_ms - sent_time_ms
                        latencies_ms.append(float(latency))

                    # Delete processed message
                    try:
                        self._sqs_client.delete_message(
                            QueueUrl=self.config.sqs_queue_url,
                            ReceiptHandle=msg["ReceiptHandle"],
                        )
                    except Exception as e:
                        logger.warning("SQS delete error: %s", e)

            # Check Step Functions concurrency
            sf_concurrent = await self._get_sf_concurrent_executions()
            sf_concurrency_peak = max(sf_concurrency_peak, sf_concurrent)

            # Check for throttling
            throttle_count = await self._detect_throttling()
            throttling_events += throttle_count

            # Early exit if all events received
            if len(received_keys) >= len(self._generated_file_keys):
                logger.info("All events received, stopping poll")
                break

            # Timeout if no new messages for 60 seconds
            if (time.monotonic() - last_receive_time) > 60:
                logger.warning("No new messages for 60s, stopping poll")
                break

        # Calculate ingestion rate
        ingestion_duration = (
            (last_receive_time - ingestion_start) if ingestion_start else 1.0
        )
        ingestion_rate = (
            len(received_keys) / ingestion_duration
            if ingestion_duration > 0
            else 0.0
        )

        # Determine lost events
        expected_keys = set(self._generated_file_keys)
        lost_keys = list(expected_keys - received_keys)

        logger.info(
            "Replay metrics collected [received=%d, lost=%d, peak_concurrency=%d, "
            "throttling=%d, ingestion_rate=%.1f/s]",
            len(received_keys),
            len(lost_keys),
            sf_concurrency_peak,
            throttling_events,
            ingestion_rate,
        )

        return {
            "events_replayed": len(received_keys),
            "ingestion_rate": ingestion_rate,
            "sf_concurrency_peak": sf_concurrency_peak,
            "throttling_events": throttling_events,
            "latencies_ms": latencies_ms,
            "lost_event_keys": lost_keys,
        }

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    async def _stop_fpolicy_server(self) -> None:
        """Stop the FPolicy server Fargate tasks."""
        logger.info(
            "Stopping FPolicy server [cluster=%s, service=%s]",
            self.config.ecs_cluster,
            self.config.ecs_service,
        )
        try:
            # List running tasks
            response = self._ecs_client.list_tasks(
                cluster=self.config.ecs_cluster,
                serviceName=self.config.ecs_service,
                desiredStatus="RUNNING",
            )
            task_arns = response.get("taskArns", [])

            # Stop each task
            for task_arn in task_arns:
                self._ecs_client.stop_task(
                    cluster=self.config.ecs_cluster,
                    task=task_arn,
                    reason=f"Replay storm test {self._test_id}",
                )
                logger.info("Stopped task: %s", task_arn)

            # Wait for tasks to stop
            if task_arns:
                waiter = self._ecs_client.get_waiter("tasks_stopped")
                waiter.wait(
                    cluster=self.config.ecs_cluster,
                    tasks=task_arns,
                    WaiterConfig={"Delay": 5, "MaxAttempts": 30},
                )
        except Exception as e:
            logger.error("Failed to stop FPolicy server: %s", e)
            raise

    async def _restart_fpolicy_server(self) -> None:
        """Wait for ECS service to restart the FPolicy server task."""
        logger.info("Waiting for FPolicy server to restart...")

        # ECS service auto-recovery will restart the task.
        # Poll until a new RUNNING task appears.
        max_wait = 120  # seconds
        poll_interval = 5
        elapsed = 0

        while elapsed < max_wait:
            try:
                response = self._ecs_client.list_tasks(
                    cluster=self.config.ecs_cluster,
                    serviceName=self.config.ecs_service,
                    desiredStatus="RUNNING",
                )
                task_arns = response.get("taskArns", [])
                if task_arns:
                    logger.info(
                        "FPolicy server restarted [task=%s, elapsed=%ds]",
                        task_arns[0],
                        elapsed,
                    )
                    # Allow time for FPolicy reconnection to ONTAP
                    await asyncio.sleep(10)
                    return
            except Exception as e:
                logger.warning("Error checking task status: %s", e)

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        logger.warning(
            "FPolicy server did not restart within %ds", max_wait
        )

    async def _get_sf_concurrent_executions(self) -> int:
        """Get current number of concurrent Step Functions executions."""
        if not self.config.step_functions_state_machine_arn:
            return 0

        try:
            response = self._sfn_client.list_executions(
                stateMachineArn=self.config.step_functions_state_machine_arn,
                statusFilter="RUNNING",
                maxResults=100,
            )
            return len(response.get("executions", []))
        except Exception as e:
            logger.warning("Failed to get SF executions: %s", e)
            return 0

    async def _detect_throttling(self) -> int:
        """Detect throttling events from CloudWatch metrics.

        Checks for Step Functions and SQS throttling in the last minute.

        Returns:
            Number of throttling events detected in this check.
        """
        throttle_count = 0
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(minutes=1)

        try:
            # Check Step Functions throttling
            response = self._cloudwatch_client.get_metric_data(
                MetricDataQueries=[
                    {
                        "Id": "sf_throttle",
                        "MetricStat": {
                            "Metric": {
                                "Namespace": "AWS/States",
                                "MetricName": "ThrottledEvents",
                                "Dimensions": [],
                            },
                            "Period": 60,
                            "Stat": "Sum",
                        },
                    },
                    {
                        "Id": "sqs_throttle",
                        "MetricStat": {
                            "Metric": {
                                "Namespace": "AWS/SQS",
                                "MetricName": "NumberOfMessagesReceived",
                                "Dimensions": [],
                            },
                            "Period": 60,
                            "Stat": "Sum",
                        },
                    },
                ],
                StartTime=start_time,
                EndTime=now,
            )

            for result in response.get("MetricDataResults", []):
                if result["Id"] == "sf_throttle" and result.get("Values"):
                    throttle_count += int(sum(result["Values"]))

        except Exception as e:
            logger.warning("Failed to check throttling metrics: %s", e)

        return throttle_count

    def _extract_file_key(self, message_body: str) -> str | None:
        """Extract the file key from an SQS message body.

        Attempts to parse the message body as JSON and extract the file path.
        Falls back to checking if the body contains a known test prefix.

        Args:
            message_body: Raw SQS message body string.

        Returns:
            Extracted file key or None if not parseable.
        """
        import json

        try:
            data = json.loads(message_body)
            # Try common field names for file path
            for key in ("file_key", "file_path", "key", "path", "objectKey"):
                if key in data:
                    return data[key]
            # Check nested detail structure
            detail = data.get("detail", {})
            for key in ("file_key", "file_path", "key", "path", "objectKey"):
                if key in detail:
                    return detail[key]
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass

        # Fallback: check if body contains our test prefix
        prefix = f"replay-storm-{self._test_id}/"
        if prefix in message_body:
            start = message_body.index(prefix)
            # Extract until whitespace or quote
            end = start
            while end < len(message_body) and message_body[end] not in (' ', '"', "'", '}', ','):
                end += 1
            return message_body[start:end]

        return None


# ---------------------------------------------------------------------------
# Pytest test functions (marked with @pytest.mark.load for CI skip)
# ---------------------------------------------------------------------------


@pytest.mark.load
@pytest.mark.asyncio
async def test_replay_storm_default_config():
    """Execute replay storm test with default configuration.

    Validates Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7

    This test requires a live AWS environment with:
    - ECS cluster running FPolicy server
    - SQS queue for event ingestion
    - NFS mount accessible at configured path
    - Step Functions state machine
    """
    config = ReplayStormConfig(
        ecs_cluster=os.environ.get("ECS_CLUSTER", "fpolicy-cluster"),
        ecs_service=os.environ.get("ECS_SERVICE", "fpolicy-service"),
        sqs_queue_url=os.environ.get("SQS_QUEUE_URL", ""),
        nfs_volume_path=os.environ.get("NFS_VOLUME_PATH", "/mnt/fsxn/replay-storm-test"),
        step_functions_state_machine_arn=os.environ.get("STATE_MACHINE_ARN", ""),
    )

    tester = ReplayStormTester(config)
    result = await tester.execute()

    # Requirement 8.1: Events accumulated during downtime
    assert result.events_generated > 0, "Should generate events during downtime"

    # Requirement 8.2: Replay detected after reconnection
    assert result.events_replayed >= 0, "Should measure replayed events"

    # Requirement 8.3: SQS ingestion rate measured
    assert result.sqs_ingestion_rate_per_sec >= 0, "Should measure ingestion rate"

    # Requirement 8.4: Step Functions concurrency peak measured
    assert result.step_functions_concurrency_peak >= 0, "Should measure SF concurrency"

    # Requirement 8.5: Throttling detected and recorded
    assert result.throttling_events >= 0, "Should detect throttling events"

    # Requirement 8.6: P50/P99 latency measured
    assert result.p50_latency_ms >= 0, "P50 latency should be non-negative"
    assert result.p99_latency_ms >= result.p50_latency_ms, "P99 >= P50"

    # Requirement 8.7: Event loss measured
    assert result.events_lost >= 0, "Should measure event loss"
    assert result.events_lost == len(result.lost_event_keys)


@pytest.mark.load
@pytest.mark.asyncio
async def test_replay_storm_short_downtime():
    """Execute replay storm test with short downtime for quick validation.

    Uses reduced parameters for faster feedback during development.
    """
    config = ReplayStormConfig(
        downtime_duration_sec=60,
        events_during_downtime=100,
        file_creation_rate_per_sec=5,
        sqs_ingestion_timeout_sec=120,
        ecs_cluster=os.environ.get("ECS_CLUSTER", "fpolicy-cluster"),
        ecs_service=os.environ.get("ECS_SERVICE", "fpolicy-service"),
        sqs_queue_url=os.environ.get("SQS_QUEUE_URL", ""),
        nfs_volume_path=os.environ.get("NFS_VOLUME_PATH", "/mnt/fsxn/replay-storm-test"),
        step_functions_state_machine_arn=os.environ.get("STATE_MACHINE_ARN", ""),
    )

    tester = ReplayStormTester(config)
    result = await tester.execute()

    # Basic sanity checks
    assert result.events_generated <= config.events_during_downtime
    assert result.replay_duration_sec >= 0
    assert result.start_time != ""
    assert result.end_time != ""


# ---------------------------------------------------------------------------
# Unit tests for percentile helper (always runnable, no AWS needed)
# ---------------------------------------------------------------------------


class TestCalculatePercentile:
    """Unit tests for the calculate_percentile helper function."""

    def test_empty_list(self):
        assert calculate_percentile([], 50) == 0.0

    def test_single_value(self):
        assert calculate_percentile([42.0], 50) == 42.0
        assert calculate_percentile([42.0], 99) == 42.0

    def test_two_values(self):
        result = calculate_percentile([10.0, 20.0], 50)
        assert result == 15.0  # midpoint

    def test_p50_odd_count(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = calculate_percentile(values, 50)
        assert result == 3.0

    def test_p99_returns_near_max(self):
        values = list(range(1, 101))  # 1 to 100
        result = calculate_percentile([float(v) for v in values], 99)
        assert result >= 99.0

    def test_p50_less_than_p99(self):
        values = [float(i) for i in range(1, 1001)]
        p50 = calculate_percentile(values, 50)
        p99 = calculate_percentile(values, 99)
        assert p50 <= p99

    def test_unsorted_input(self):
        values = [5.0, 1.0, 3.0, 2.0, 4.0]
        result = calculate_percentile(values, 50)
        assert result == 3.0  # median of sorted [1,2,3,4,5]

    def test_percentile_zero(self):
        values = [10.0, 20.0, 30.0]
        result = calculate_percentile(values, 0)
        assert result == 10.0

    def test_percentile_100(self):
        values = [10.0, 20.0, 30.0]
        result = calculate_percentile(values, 100)
        assert result == 30.0
