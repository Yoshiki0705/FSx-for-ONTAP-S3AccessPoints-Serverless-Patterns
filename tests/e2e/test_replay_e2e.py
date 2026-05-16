"""Persistent Store Replay E2E Validation.

Fargate タスク再起動中に発生した FPolicy イベントが Persistent Store に保存され、
再起動後に SQS へ正しくリプレイされることを検証する。

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import boto3
import pytest

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass
class DeliveryResult:
    """SQS 配信検証の結果."""

    expected_files: list[str]
    delivered_files: list[str]
    missing_files: list[str]
    extra_files: list[str]
    all_delivered: bool
    poll_duration_sec: float


@dataclass
class ReplayValidationResult:
    """Replay E2E 検証の全体結果."""

    total_files_created: int
    files_delivered_to_sqs: int
    files_lost: list[str]
    replay_duration_sec: float
    all_delivered: bool
    delivery_result: DeliveryResult | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# ReplayE2EValidator
# ---------------------------------------------------------------------------


class ReplayE2EValidator:
    """Fargate 再起動時の FPolicy イベントリプレイを検証する.

    テストフロー:
    1. ECS Fargate タスクを強制停止
    2. 停止中に NFS 経由でテストファイルを作成（FPolicy イベント発生）
    3. Fargate タスク再起動を待機
    4. SQS キューから全テストファイルのイベント配信を検証
    5. テストアーティファクトをクリーンアップ
    """

    def __init__(
        self,
        fsx_management_ip: str,
        sqs_queue_url: str,
        ecs_cluster: str,
        ecs_service: str,
        nfs_mount_path: str | None = None,
        region: str | None = None,
    ) -> None:
        """ReplayE2EValidator を初期化する.

        Args:
            fsx_management_ip: FSx ONTAP 管理 IP アドレス
            sqs_queue_url: SQS キュー URL
            ecs_cluster: ECS クラスター名または ARN
            ecs_service: ECS サービス名
            nfs_mount_path: NFS マウントパス（デフォルト: 環境変数 NFS_MOUNT_PATH）
            region: AWS リージョン（デフォルト: 環境変数 AWS_DEFAULT_REGION）
        """
        self.fsx_management_ip = fsx_management_ip
        self.sqs_queue_url = sqs_queue_url
        self.ecs_cluster = ecs_cluster
        self.ecs_service = ecs_service
        self.nfs_mount_path = nfs_mount_path or os.environ.get(
            "NFS_MOUNT_PATH", "/mnt/fsxn"
        )
        self._region = region or os.environ.get("AWS_DEFAULT_REGION", "ap-northeast-1")

        self._ecs_client = boto3.client("ecs", region_name=self._region)
        self._sqs_client = boto3.client("sqs", region_name=self._region)

        self._created_files: list[str] = []
        self._test_prefix = f"replay-e2e-{uuid.uuid4().hex[:8]}"

    async def run_validation(
        self,
        num_test_files: int = 10,
        restart_delay_sec: int = 30,
        sqs_timeout_sec: int = 120,
    ) -> ReplayValidationResult:
        """Replay E2E 検証を実行する.

        Args:
            num_test_files: 作成するテストファイル数
            restart_delay_sec: Fargate 再起動待機時間（秒）
            sqs_timeout_sec: SQS ポーリングタイムアウト（秒）

        Returns:
            ReplayValidationResult: 検証結果
        """
        start_time = time.time()

        try:
            # Step 1: Fargate タスクを強制停止 (Requirement 7.1)
            logger.info("Step 1: Stopping Fargate task...")
            await self._stop_fargate_task()

            # Step 2: 停止中にテストファイルを作成 (Requirement 7.2)
            logger.info(
                "Step 2: Creating %d test files during restart...", num_test_files
            )
            volume_path = os.path.join(self.nfs_mount_path, self._test_prefix)
            created_files = await self.create_test_files_during_restart(
                volume_path=volume_path,
                num_files=num_test_files,
            )

            # Step 3: Fargate 再起動を待機
            logger.info(
                "Step 3: Waiting %d seconds for Fargate restart...", restart_delay_sec
            )
            await asyncio.sleep(restart_delay_sec)
            await self._wait_for_task_running(timeout_sec=120)

            # Step 4: SQS 配信を検証 (Requirement 7.3)
            logger.info("Step 4: Verifying SQS delivery...")
            delivery_result = await self.verify_sqs_delivery(
                expected_file_keys=created_files,
                timeout_sec=sqs_timeout_sec,
            )

            # Requirement 7.4: リプレイ所要時間を計測
            replay_duration = time.time() - start_time

            # Requirement 7.5: 欠損イベントの特定
            result = ReplayValidationResult(
                total_files_created=len(created_files),
                files_delivered_to_sqs=len(delivery_result.delivered_files),
                files_lost=delivery_result.missing_files,
                replay_duration_sec=replay_duration,
                all_delivered=delivery_result.all_delivered,
                delivery_result=delivery_result,
            )

            if delivery_result.missing_files:
                logger.warning(
                    "Missing events detected: %s", delivery_result.missing_files
                )

            return result

        except Exception as e:
            logger.error("Replay E2E validation failed: %s", e)
            elapsed = time.time() - start_time
            return ReplayValidationResult(
                total_files_created=len(self._created_files),
                files_delivered_to_sqs=0,
                files_lost=self._created_files.copy(),
                replay_duration_sec=elapsed,
                all_delivered=False,
                error=str(e),
            )
        finally:
            # Requirement 7.6: テストアーティファクトのクリーンアップ
            await self._cleanup()

    async def create_test_files_during_restart(
        self,
        volume_path: str,
        num_files: int,
    ) -> list[str]:
        """NFS 経由でテストファイルを作成する.

        Fargate タスク停止中に呼び出され、FPolicy イベントを発生させる。
        これらのイベントは Persistent Store に蓄積される。

        Args:
            volume_path: テストファイル作成先のパス
            num_files: 作成するファイル数

        Returns:
            作成されたファイルパスのリスト
        """
        created_files: list[str] = []

        # ディレクトリ作成
        os.makedirs(volume_path, exist_ok=True)

        for i in range(num_files):
            filename = f"test-replay-{self._test_prefix}-{i:04d}.txt"
            filepath = os.path.join(volume_path, filename)

            content = json.dumps(
                {
                    "test_id": self._test_prefix,
                    "file_index": i,
                    "timestamp": time.time(),
                    "purpose": "replay_e2e_validation",
                }
            )

            # NFS 経由でファイル作成（FPolicy イベントをトリガー）
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)

            created_files.append(filepath)
            self._created_files.append(filepath)

            # ファイル作成間に小さな遅延を入れてイベント順序を保証
            await asyncio.sleep(0.1)

        logger.info("Created %d test files in %s", len(created_files), volume_path)
        return created_files

    async def verify_sqs_delivery(
        self,
        expected_file_keys: list[str],
        timeout_sec: int = 120,
    ) -> DeliveryResult:
        """SQS ポーリングで全イベント配信を確認する.

        Args:
            expected_file_keys: 期待されるファイルパスのリスト
            timeout_sec: ポーリングタイムアウト（秒）

        Returns:
            DeliveryResult: 配信検証結果
        """
        start_time = time.time()
        delivered_files: set[str] = set()
        expected_set = set(expected_file_keys)

        while time.time() - start_time < timeout_sec:
            # SQS からメッセージを受信
            response = self._sqs_client.receive_message(
                QueueUrl=self.sqs_queue_url,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=5,
                MessageAttributeNames=["All"],
            )

            messages = response.get("Messages", [])

            for message in messages:
                file_key = self._extract_file_key_from_message(message)
                if file_key and file_key in expected_set:
                    delivered_files.add(file_key)

                # メッセージを削除
                self._sqs_client.delete_message(
                    QueueUrl=self.sqs_queue_url,
                    ReceiptHandle=message["ReceiptHandle"],
                )

            # 全イベントが配信されたら早期終了
            if delivered_files >= expected_set:
                break

            await asyncio.sleep(1)

        poll_duration = time.time() - start_time
        missing_files = list(expected_set - delivered_files)
        extra_files = list(delivered_files - expected_set)

        return DeliveryResult(
            expected_files=expected_file_keys,
            delivered_files=list(delivered_files),
            missing_files=missing_files,
            extra_files=extra_files,
            all_delivered=len(missing_files) == 0,
            poll_duration_sec=poll_duration,
        )

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    async def _stop_fargate_task(self) -> None:
        """ECS Fargate タスクを強制停止する."""
        # 現在実行中のタスクを取得
        list_response = self._ecs_client.list_tasks(
            cluster=self.ecs_cluster,
            serviceName=self.ecs_service,
            desiredStatus="RUNNING",
        )

        task_arns = list_response.get("taskArns", [])
        if not task_arns:
            raise RuntimeError(
                f"No running tasks found for service {self.ecs_service} "
                f"in cluster {self.ecs_cluster}"
            )

        # 最初のタスクを停止
        task_arn = task_arns[0]
        logger.info("Stopping task: %s", task_arn)

        self._ecs_client.stop_task(
            cluster=self.ecs_cluster,
            task=task_arn,
            reason="Replay E2E validation - forced stop for testing",
        )

        # タスクが停止するまで待機
        await self._wait_for_task_stopped(task_arn, timeout_sec=60)

    async def _wait_for_task_stopped(
        self, task_arn: str, timeout_sec: int = 60
    ) -> None:
        """タスクが停止するまで待機する."""
        start_time = time.time()

        while time.time() - start_time < timeout_sec:
            response = self._ecs_client.describe_tasks(
                cluster=self.ecs_cluster,
                tasks=[task_arn],
            )

            tasks = response.get("tasks", [])
            if tasks and tasks[0].get("lastStatus") == "STOPPED":
                logger.info("Task %s stopped successfully", task_arn)
                return

            await asyncio.sleep(2)

        raise TimeoutError(
            f"Task {task_arn} did not stop within {timeout_sec} seconds"
        )

    async def _wait_for_task_running(self, timeout_sec: int = 120) -> None:
        """新しいタスクが RUNNING 状態になるまで待機する."""
        start_time = time.time()

        while time.time() - start_time < timeout_sec:
            list_response = self._ecs_client.list_tasks(
                cluster=self.ecs_cluster,
                serviceName=self.ecs_service,
                desiredStatus="RUNNING",
            )

            task_arns = list_response.get("taskArns", [])
            if task_arns:
                response = self._ecs_client.describe_tasks(
                    cluster=self.ecs_cluster,
                    tasks=task_arns,
                )
                tasks = response.get("tasks", [])
                running_tasks = [
                    t for t in tasks if t.get("lastStatus") == "RUNNING"
                ]
                if running_tasks:
                    logger.info(
                        "New task running: %s", running_tasks[0].get("taskArn")
                    )
                    return

            await asyncio.sleep(5)

        raise TimeoutError(
            f"No running task found within {timeout_sec} seconds "
            f"for service {self.ecs_service}"
        )

    def _extract_file_key_from_message(self, message: dict[str, Any]) -> str | None:
        """SQS メッセージからファイルキーを抽出する.

        FPolicy イベントメッセージのボディからファイルパスを取得する。
        メッセージフォーマットに応じてパース方法を調整する。
        """
        try:
            body = json.loads(message.get("Body", "{}"))

            # FPolicy イベントメッセージのフォーマットに対応
            # パターン 1: {"file_path": "..."} 直接フォーマット
            if "file_path" in body:
                return body["file_path"]

            # パターン 2: {"detail": {"file_path": "..."}} EventBridge 経由
            if "detail" in body and "file_path" in body["detail"]:
                return body["detail"]["file_path"]

            # パターン 3: {"Records": [{"s3": {"object": {"key": "..."}}}]} S3 イベント形式
            records = body.get("Records", [])
            if records:
                s3_info = records[0].get("s3", {})
                obj_key = s3_info.get("object", {}).get("key")
                if obj_key:
                    return obj_key

            # パターン 4: メッセージ属性にファイルパスが含まれる場合
            attrs = message.get("MessageAttributes", {})
            file_path_attr = attrs.get("FilePath", {})
            if file_path_attr:
                return file_path_attr.get("StringValue")

            logger.debug("Could not extract file key from message: %s", message)
            return None

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.debug("Error parsing SQS message: %s", e)
            return None

    async def _cleanup(self) -> None:
        """テストアーティファクトをクリーンアップする.

        Requirement 7.6: 検証完了後のクリーンアップ
        """
        logger.info("Cleaning up %d test files...", len(self._created_files))

        for filepath in self._created_files:
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except OSError as e:
                logger.warning("Failed to remove test file %s: %s", filepath, e)

        # テストディレクトリの削除
        test_dir = os.path.join(self.nfs_mount_path, self._test_prefix)
        try:
            if os.path.isdir(test_dir):
                os.rmdir(test_dir)
        except OSError as e:
            logger.warning("Failed to remove test directory %s: %s", test_dir, e)

        self._created_files.clear()
        logger.info("Cleanup completed")


# ---------------------------------------------------------------------------
# Pytest E2E Tests
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestReplayE2EValidation:
    """Persistent Store Replay E2E 検証テスト.

    実環境（ECS Fargate + FSx ONTAP + SQS）が必要なため、
    CI では @pytest.mark.e2e マーカーでスキップ可能。
    """

    @pytest.fixture
    def validator(self) -> ReplayE2EValidator:
        """テスト用の ReplayE2EValidator インスタンスを作成する."""
        return ReplayE2EValidator(
            fsx_management_ip=os.environ.get("FSX_MANAGEMENT_IP", "10.0.0.1"),
            sqs_queue_url=os.environ.get(
                "SQS_QUEUE_URL",
                "https://sqs.ap-northeast-1.amazonaws.com/123456789012/fpolicy-events",
            ),
            ecs_cluster=os.environ.get("ECS_CLUSTER", "fpolicy-cluster"),
            ecs_service=os.environ.get("ECS_SERVICE", "fpolicy-server"),
        )

    @pytest.mark.asyncio
    async def test_replay_validation_full(self, validator: ReplayE2EValidator):
        """フル Replay E2E 検証を実行する.

        Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6
        """
        result = await validator.run_validation(
            num_test_files=10,
            restart_delay_sec=30,
            sqs_timeout_sec=120,
        )

        # 全ファイルが作成されたことを確認
        assert result.total_files_created == 10

        # 全イベントが配信されたことを確認 (Requirement 7.3)
        assert result.all_delivered, (
            f"Event loss detected. "
            f"Created: {result.total_files_created}, "
            f"Delivered: {result.files_delivered_to_sqs}, "
            f"Lost: {result.files_lost}"
        )

        # リプレイ所要時間が記録されていることを確認 (Requirement 7.4)
        assert result.replay_duration_sec > 0

        # エラーがないことを確認
        assert result.error is None

    @pytest.mark.asyncio
    async def test_replay_no_event_loss(self, validator: ReplayE2EValidator):
        """イベント欠損がないことを検証する.

        Validates: Requirements 7.3, 7.5
        """
        result = await validator.run_validation(
            num_test_files=5,
            restart_delay_sec=30,
            sqs_timeout_sec=90,
        )

        # 欠損イベントのレポート (Requirement 7.5)
        assert len(result.files_lost) == 0, (
            f"Lost {len(result.files_lost)} events: {result.files_lost}"
        )

    @pytest.mark.asyncio
    async def test_replay_with_larger_batch(self, validator: ReplayE2EValidator):
        """より大きなバッチでのリプレイ検証.

        Validates: Requirements 7.1, 7.2, 7.3
        """
        result = await validator.run_validation(
            num_test_files=50,
            restart_delay_sec=45,
            sqs_timeout_sec=180,
        )

        assert result.total_files_created == 50
        assert result.all_delivered, (
            f"Lost {len(result.files_lost)} of 50 events"
        )


@pytest.mark.e2e
class TestReplayE2EValidatorUnit:
    """ReplayE2EValidator のユニットテスト（モック不要な部分）."""

    def test_dataclass_replay_validation_result(self):
        """ReplayValidationResult dataclass が正しく初期化される."""
        result = ReplayValidationResult(
            total_files_created=10,
            files_delivered_to_sqs=8,
            files_lost=["/mnt/fsxn/test/file1.txt", "/mnt/fsxn/test/file2.txt"],
            replay_duration_sec=45.5,
            all_delivered=False,
        )

        assert result.total_files_created == 10
        assert result.files_delivered_to_sqs == 8
        assert len(result.files_lost) == 2
        assert result.replay_duration_sec == 45.5
        assert result.all_delivered is False
        assert result.delivery_result is None
        assert result.error is None

    def test_dataclass_delivery_result(self):
        """DeliveryResult dataclass が正しく初期化される."""
        result = DeliveryResult(
            expected_files=["/mnt/fsxn/a.txt", "/mnt/fsxn/b.txt"],
            delivered_files=["/mnt/fsxn/a.txt"],
            missing_files=["/mnt/fsxn/b.txt"],
            extra_files=[],
            all_delivered=False,
            poll_duration_sec=30.0,
        )

        assert len(result.expected_files) == 2
        assert len(result.delivered_files) == 1
        assert result.missing_files == ["/mnt/fsxn/b.txt"]
        assert result.extra_files == []
        assert result.all_delivered is False
        assert result.poll_duration_sec == 30.0

    def test_extract_file_key_direct_format(self):
        """file_path 直接フォーマットからファイルキーを抽出できる."""
        validator = ReplayE2EValidator(
            fsx_management_ip="10.0.0.1",
            sqs_queue_url="https://sqs.example.com/queue",
            ecs_cluster="test-cluster",
            ecs_service="test-service",
        )

        message = {
            "Body": json.dumps({"file_path": "/mnt/fsxn/test/file.txt"}),
            "ReceiptHandle": "test-handle",
        }

        result = validator._extract_file_key_from_message(message)
        assert result == "/mnt/fsxn/test/file.txt"

    def test_extract_file_key_eventbridge_format(self):
        """EventBridge 経由フォーマットからファイルキーを抽出できる."""
        validator = ReplayE2EValidator(
            fsx_management_ip="10.0.0.1",
            sqs_queue_url="https://sqs.example.com/queue",
            ecs_cluster="test-cluster",
            ecs_service="test-service",
        )

        message = {
            "Body": json.dumps(
                {"detail": {"file_path": "/mnt/fsxn/test/file.txt"}}
            ),
            "ReceiptHandle": "test-handle",
        }

        result = validator._extract_file_key_from_message(message)
        assert result == "/mnt/fsxn/test/file.txt"

    def test_extract_file_key_s3_event_format(self):
        """S3 イベント形式からファイルキーを抽出できる."""
        validator = ReplayE2EValidator(
            fsx_management_ip="10.0.0.1",
            sqs_queue_url="https://sqs.example.com/queue",
            ecs_cluster="test-cluster",
            ecs_service="test-service",
        )

        message = {
            "Body": json.dumps(
                {
                    "Records": [
                        {"s3": {"object": {"key": "test-prefix/file.txt"}}}
                    ]
                }
            ),
            "ReceiptHandle": "test-handle",
        }

        result = validator._extract_file_key_from_message(message)
        assert result == "test-prefix/file.txt"

    def test_extract_file_key_message_attributes(self):
        """メッセージ属性からファイルキーを抽出できる."""
        validator = ReplayE2EValidator(
            fsx_management_ip="10.0.0.1",
            sqs_queue_url="https://sqs.example.com/queue",
            ecs_cluster="test-cluster",
            ecs_service="test-service",
        )

        message = {
            "Body": "{}",
            "ReceiptHandle": "test-handle",
            "MessageAttributes": {
                "FilePath": {
                    "StringValue": "/mnt/fsxn/test/file.txt",
                    "DataType": "String",
                }
            },
        }

        result = validator._extract_file_key_from_message(message)
        assert result == "/mnt/fsxn/test/file.txt"

    def test_extract_file_key_invalid_message(self):
        """不正なメッセージで None が返る."""
        validator = ReplayE2EValidator(
            fsx_management_ip="10.0.0.1",
            sqs_queue_url="https://sqs.example.com/queue",
            ecs_cluster="test-cluster",
            ecs_service="test-service",
        )

        message = {
            "Body": "not-json",
            "ReceiptHandle": "test-handle",
        }

        result = validator._extract_file_key_from_message(message)
        assert result is None

    def test_extract_file_key_empty_body(self):
        """空のボディで None が返る."""
        validator = ReplayE2EValidator(
            fsx_management_ip="10.0.0.1",
            sqs_queue_url="https://sqs.example.com/queue",
            ecs_cluster="test-cluster",
            ecs_service="test-service",
        )

        message = {
            "Body": json.dumps({"unrelated": "data"}),
            "ReceiptHandle": "test-handle",
        }

        result = validator._extract_file_key_from_message(message)
        assert result is None

    def test_replay_validation_result_with_error(self):
        """エラー付き ReplayValidationResult が正しく初期化される."""
        result = ReplayValidationResult(
            total_files_created=5,
            files_delivered_to_sqs=0,
            files_lost=["/mnt/fsxn/test/f1.txt"],
            replay_duration_sec=10.0,
            all_delivered=False,
            error="Connection timeout",
        )

        assert result.error == "Connection timeout"
        assert result.all_delivered is False

    def test_validator_initialization(self):
        """ReplayE2EValidator が正しく初期化される."""
        validator = ReplayE2EValidator(
            fsx_management_ip="192.168.1.100",
            sqs_queue_url="https://sqs.ap-northeast-1.amazonaws.com/123/queue",
            ecs_cluster="my-cluster",
            ecs_service="fpolicy-svc",
            nfs_mount_path="/custom/mount",
            region="us-east-1",
        )

        assert validator.fsx_management_ip == "192.168.1.100"
        assert validator.sqs_queue_url == "https://sqs.ap-northeast-1.amazonaws.com/123/queue"
        assert validator.ecs_cluster == "my-cluster"
        assert validator.ecs_service == "fpolicy-svc"
        assert validator.nfs_mount_path == "/custom/mount"
        assert validator._region == "us-east-1"
