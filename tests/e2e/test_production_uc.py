"""Production UC Deployment E2E Validation.

TriggerMode=EVENT_DRIVEN で UC テンプレートをデプロイし、
ファイル操作から Step Functions 実行までのエンドツーエンドフローを検証する。

Feature 1 (Guardrails) と Feature 5 (Data Lineage) の統合確認を含む。

Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import boto3
from boto3.dynamodb.conditions import Attr
import pytest

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass
class ProductionUCConfig:
    """Production UC 検証の設定."""

    uc_id: str  # e.g., "legal-compliance"
    trigger_mode: str = "EVENT_DRIVEN"
    test_file_path: str = ""  # NFS path for test file
    expected_outputs: list[str] = field(default_factory=list)
    timeout_sec: int = 300
    stack_name: str = ""  # CloudFormation stack name
    sqs_queue_url: str = ""
    state_machine_arn: str = ""
    nfs_mount_path: str = ""
    lineage_table_name: str = ""
    guardrails_table_name: str = ""
    has_auto_expand: bool = False  # UC が自動拡張を含むか


@dataclass
class ProductionUCResult:
    """Production UC 検証の結果."""

    uc_id: str
    file_created: bool
    fpolicy_event_received: bool
    sqs_message_delivered: bool
    step_functions_started: bool
    step_functions_succeeded: bool
    execution_arn: str | None = None
    e2e_latency_sec: float = 0.0
    lineage_recorded: bool = False  # Feature 5 integration check
    guardrail_checked: bool = False  # Feature 1 integration check (if applicable)
    outputs_verified: bool = False
    error: str | None = None


# ---------------------------------------------------------------------------
# ProductionUCValidator
# ---------------------------------------------------------------------------


class ProductionUCValidator:
    """TriggerMode=EVENT_DRIVEN での本番 UC エンドツーエンド検証.

    テストフロー:
    1. UC テンプレートが EVENT_DRIVEN でデプロイされていることを確認
    2. NFS 経由でテストファイルを作成（FPolicy イベントをトリガー）
    3. FPolicy イベント → SQS → Step Functions の全パスを検証
    4. Step Functions 実行の成功を確認
    5. Feature 5 (Data Lineage) のレコード書き込みを確認
    6. Feature 1 (Guardrails) の統合確認（自動拡張 UC の場合）
    7. エンドツーエンドレイテンシを計測
    """

    def __init__(self, config: ProductionUCConfig) -> None:
        """ProductionUCValidator を初期化する.

        Args:
            config: 検証設定
        """
        self.config = config
        self._region = os.environ.get("AWS_DEFAULT_REGION", "ap-northeast-1")

        # AWS クライアント初期化
        self._cfn_client = boto3.client("cloudformation", region_name=self._region)
        self._sfn_client = boto3.client("stepfunctions", region_name=self._region)
        self._sqs_client = boto3.client("sqs", region_name=self._region)
        self._s3_client = boto3.client("s3", region_name=self._region)
        self._dynamodb = boto3.resource("dynamodb", region_name=self._region)
        self._cw_client = boto3.client("cloudwatch", region_name=self._region)

        # NFS マウントパス
        self._nfs_mount_path = config.nfs_mount_path or os.environ.get(
            "NFS_MOUNT_PATH", "/mnt/fsxn"
        )

        # テスト識別子
        self._test_id = f"prod-uc-{uuid.uuid4().hex[:8]}"
        self._test_file_created: str | None = None

    async def deploy_and_validate(self) -> ProductionUCResult:
        """UC テンプレート確認 → テストファイル作成 → 全パス検証.

        Requirement 12.1: TriggerMode=EVENT_DRIVEN でのデプロイ確認
        Requirement 12.2: FPolicy → SQS → Step Functions の全パス検証
        Requirement 12.3: Step Functions 実行の成功確認
        Requirement 12.4: Data Lineage レコード確認
        Requirement 12.5: Guardrails 統合確認
        Requirement 12.6: E2E レイテンシ計測

        Returns:
            ProductionUCResult: 検証結果
        """
        result = ProductionUCResult(
            uc_id=self.config.uc_id,
            file_created=False,
            fpolicy_event_received=False,
            sqs_message_delivered=False,
            step_functions_started=False,
            step_functions_succeeded=False,
        )
        start_time = time.time()

        try:
            # Step 1: UC テンプレートの TriggerMode 確認 (Requirement 12.1)
            logger.info(
                "Step 1: Verifying UC stack '%s' with TriggerMode=%s...",
                self.config.uc_id,
                self.config.trigger_mode,
            )
            if not await self._verify_stack_trigger_mode():
                result.error = (
                    f"UC stack '{self.config.stack_name}' is not deployed "
                    f"with TriggerMode={self.config.trigger_mode}"
                )
                return result

            # Step 2: テストファイル作成 (Requirement 12.2)
            logger.info("Step 2: Creating test file via NFS...")
            test_file_path = await self.create_test_file()
            result.file_created = True
            logger.info("Test file created: %s", test_file_path)

            # Step 3: SQS メッセージ配信を待機 (Requirement 12.2)
            logger.info("Step 3: Waiting for SQS message delivery...")
            sqs_received = await self._wait_for_sqs_message(
                test_file_path, timeout_sec=60
            )
            result.sqs_message_delivered = sqs_received
            if sqs_received:
                result.fpolicy_event_received = True

            # Step 4: Step Functions 実行を待機 (Requirement 12.3)
            logger.info("Step 4: Waiting for Step Functions execution...")
            execution_result = await self.wait_for_execution()
            if execution_result:
                result.step_functions_started = True
                result.execution_arn = execution_result.get("executionArn")
                status = execution_result.get("status", "")
                result.step_functions_succeeded = status == "SUCCEEDED"
            else:
                result.step_functions_started = False

            # Step 5: Data Lineage レコード確認 (Requirement 12.4)
            if result.execution_arn:
                logger.info("Step 5: Verifying Data Lineage record...")
                result.lineage_recorded = await self.verify_lineage(
                    result.execution_arn
                )

            # Step 6: 出力ファイル確認
            if result.step_functions_succeeded:
                logger.info("Step 6: Verifying output files...")
                result.outputs_verified = await self.verify_outputs()

            # Step 7: Guardrails 統合確認 (Requirement 12.5)
            if self.config.has_auto_expand:
                logger.info("Step 7: Verifying Guardrails integration...")
                result.guardrail_checked = await self._verify_guardrail_integration()

            # Requirement 12.6: E2E レイテンシ計測
            result.e2e_latency_sec = time.time() - start_time
            logger.info(
                "E2E validation completed in %.2f seconds", result.e2e_latency_sec
            )

        except Exception as e:
            logger.error("Production UC validation failed: %s", e)
            result.error = str(e)
            result.e2e_latency_sec = time.time() - start_time

        finally:
            # テストアーティファクトのクリーンアップ
            await self._cleanup()

        return result

    async def create_test_file(self) -> str:
        """NFS 経由でテストファイルを作成する.

        FPolicy イベントをトリガーするためのテストファイルを作成する。

        Returns:
            作成されたファイルのパス
        """
        # テストファイルパスの決定
        if self.config.test_file_path:
            file_path = self.config.test_file_path
        else:
            uc_dir = os.path.join(
                self._nfs_mount_path, self.config.uc_id, self._test_id
            )
            os.makedirs(uc_dir, exist_ok=True)
            file_path = os.path.join(uc_dir, f"test-{self._test_id}.txt")

        # テストファイルの内容
        content = json.dumps(
            {
                "test_id": self._test_id,
                "uc_id": self.config.uc_id,
                "trigger_mode": self.config.trigger_mode,
                "timestamp": time.time(),
                "purpose": "production_uc_e2e_validation",
            },
            indent=2,
        )

        # NFS 経由でファイル作成
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        self._test_file_created = file_path
        return file_path

    async def wait_for_execution(self) -> dict[str, Any] | None:
        """Step Functions 実行完了を待機する.

        Requirement 12.3: Step Functions 実行の成功確認

        Returns:
            実行結果の辞書。タイムアウト時は None。
        """
        timeout_sec = self.config.timeout_sec
        start_time = time.time()
        poll_interval = 5  # 秒

        while time.time() - start_time < timeout_sec:
            try:
                # RUNNING 状態の実行を検索
                response = self._sfn_client.list_executions(
                    stateMachineArn=self.config.state_machine_arn,
                    statusFilter="RUNNING",
                    maxResults=10,
                )

                executions = response.get("executions", [])

                # テスト ID に関連する実行を検索
                for execution in executions:
                    exec_arn = execution["executionArn"]
                    exec_detail = self._sfn_client.describe_execution(
                        executionArn=exec_arn
                    )
                    input_data = exec_detail.get("input", "{}")
                    if self._test_id in input_data:
                        status = exec_detail.get("status")
                        if status in (
                            "SUCCEEDED",
                            "FAILED",
                            "TIMED_OUT",
                            "ABORTED",
                        ):
                            return {
                                "executionArn": exec_arn,
                                "status": status,
                                "output": exec_detail.get("output"),
                                "startDate": str(
                                    exec_detail.get("startDate", "")
                                ),
                                "stopDate": str(
                                    exec_detail.get("stopDate", "")
                                ),
                            }
                        # まだ実行中 — 待機を続ける
                        break

                # SUCCEEDED の実行も確認
                succeeded_response = self._sfn_client.list_executions(
                    stateMachineArn=self.config.state_machine_arn,
                    statusFilter="SUCCEEDED",
                    maxResults=5,
                )
                for execution in succeeded_response.get("executions", []):
                    exec_arn = execution["executionArn"]
                    exec_detail = self._sfn_client.describe_execution(
                        executionArn=exec_arn
                    )
                    input_data = exec_detail.get("input", "{}")
                    if self._test_id in input_data:
                        return {
                            "executionArn": exec_arn,
                            "status": "SUCCEEDED",
                            "output": exec_detail.get("output"),
                            "startDate": str(
                                exec_detail.get("startDate", "")
                            ),
                            "stopDate": str(
                                exec_detail.get("stopDate", "")
                            ),
                        }

            except Exception as e:
                logger.warning("Error polling Step Functions: %s", e)

            await asyncio.sleep(poll_interval)

        logger.warning(
            "Step Functions execution not found within %d seconds", timeout_sec
        )
        return None

    async def verify_lineage(self, execution_arn: str) -> bool:
        """Feature 5 (Data Lineage) レコード確認.

        Requirement 12.4: Data Lineage のレコード書き込みを確認する。

        Args:
            execution_arn: Step Functions 実行 ARN

        Returns:
            Lineage レコードが存在する場合 True
        """
        lineage_table = self.config.lineage_table_name or os.environ.get(
            "LINEAGE_TABLE", "fsxn-s3ap-data-lineage"
        )

        try:
            table = self._dynamodb.Table(lineage_table)

            # execution_arn で検索（スキャン + フィルタ）
            response = table.scan(
                FilterExpression=Attr("step_functions_execution_arn").eq(
                    execution_arn
                ),
                Limit=10,
            )

            items = response.get("Items", [])
            if items:
                logger.info(
                    "Lineage record found for execution %s: %d records",
                    execution_arn,
                    len(items),
                )
                return True

            # リトライ — レコード書き込みに遅延がある場合
            await asyncio.sleep(5)
            response = table.scan(
                FilterExpression=Attr("step_functions_execution_arn").eq(
                    execution_arn
                ),
                Limit=10,
            )
            items = response.get("Items", [])
            if items:
                logger.info(
                    "Lineage record found (retry) for execution %s",
                    execution_arn,
                )
                return True

            logger.warning(
                "No lineage record found for execution %s", execution_arn
            )
            return False

        except Exception as e:
            logger.error("Error verifying lineage: %s", e)
            return False

    async def verify_outputs(self) -> bool:
        """出力ファイルの存在を確認する.

        config.expected_outputs に指定された S3 キーが存在するかを検証する。

        Returns:
            全出力ファイルが存在する場合 True
        """
        if not self.config.expected_outputs:
            logger.info("No expected outputs configured, skipping verification")
            return True

        missing_outputs: list[str] = []

        for output_key in self.config.expected_outputs:
            try:
                # S3 キーのパース（bucket/key 形式を想定）
                parts = output_key.split("/", 1)
                if len(parts) == 2:
                    bucket, key = parts[0], parts[1]
                else:
                    # バケット名が環境変数で指定されている場合
                    bucket = os.environ.get("OUTPUT_BUCKET", "")
                    key = output_key

                if not bucket:
                    logger.warning(
                        "Cannot verify output '%s': no bucket specified",
                        output_key,
                    )
                    missing_outputs.append(output_key)
                    continue

                self._s3_client.head_object(Bucket=bucket, Key=key)
                logger.info("Output verified: s3://%s/%s", bucket, key)

            except self._s3_client.exceptions.ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "")
                if error_code in ("404", "NoSuchKey"):
                    logger.warning("Output not found: %s", output_key)
                    missing_outputs.append(output_key)
                else:
                    logger.error(
                        "Error checking output '%s': %s", output_key, e
                    )
                    missing_outputs.append(output_key)
            except Exception as e:
                logger.error("Error verifying output '%s': %s", output_key, e)
                missing_outputs.append(output_key)

        if missing_outputs:
            logger.warning("Missing outputs: %s", missing_outputs)
            return False

        logger.info(
            "All %d expected outputs verified", len(self.config.expected_outputs)
        )
        return True

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    async def _verify_stack_trigger_mode(self) -> bool:
        """CloudFormation スタックの TriggerMode パラメータを確認する.

        Requirement 12.1: UC テンプレートが EVENT_DRIVEN でデプロイされていることを確認

        Returns:
            TriggerMode が期待値と一致する場合 True
        """
        stack_name = self.config.stack_name
        if not stack_name:
            # スタック名が未指定の場合、UC ID から推測
            stack_name = f"fsxn-s3ap-{self.config.uc_id}"

        try:
            response = self._cfn_client.describe_stacks(StackName=stack_name)
            stacks = response.get("Stacks", [])

            if not stacks:
                logger.error("Stack '%s' not found", stack_name)
                return False

            stack = stacks[0]
            stack_status = stack.get("StackStatus", "")

            # スタックが正常にデプロイされていることを確認
            if stack_status not in (
                "CREATE_COMPLETE",
                "UPDATE_COMPLETE",
                "UPDATE_ROLLBACK_COMPLETE",
            ):
                logger.error(
                    "Stack '%s' is in unexpected status: %s",
                    stack_name,
                    stack_status,
                )
                return False

            # TriggerMode パラメータを確認
            parameters = stack.get("Parameters", [])
            for param in parameters:
                if param.get("ParameterKey") == "TriggerMode":
                    actual_mode = param.get("ParameterValue", "")
                    if actual_mode == self.config.trigger_mode:
                        logger.info(
                            "Stack '%s' TriggerMode=%s confirmed",
                            stack_name,
                            actual_mode,
                        )
                        return True
                    else:
                        logger.error(
                            "Stack '%s' TriggerMode mismatch: "
                            "expected=%s, actual=%s",
                            stack_name,
                            self.config.trigger_mode,
                            actual_mode,
                        )
                        return False

            # TriggerMode パラメータが見つからない場合
            logger.warning(
                "TriggerMode parameter not found in stack '%s'", stack_name
            )
            return False

        except Exception as e:
            logger.error("Error verifying stack '%s': %s", stack_name, e)
            return False

    async def _wait_for_sqs_message(
        self, test_file_path: str, timeout_sec: int = 60
    ) -> bool:
        """SQS メッセージの配信を待機する.

        Requirement 12.2: FPolicy イベント → SQS の配信確認

        Args:
            test_file_path: テストファイルのパス
            timeout_sec: タイムアウト（秒）

        Returns:
            メッセージが配信された場合 True
        """
        if not self.config.sqs_queue_url:
            logger.warning("SQS queue URL not configured, skipping SQS check")
            return True

        start_time = time.time()

        while time.time() - start_time < timeout_sec:
            try:
                response = self._sqs_client.receive_message(
                    QueueUrl=self.config.sqs_queue_url,
                    MaxNumberOfMessages=10,
                    WaitTimeSeconds=5,
                    MessageAttributeNames=["All"],
                )

                messages = response.get("Messages", [])
                for message in messages:
                    body = message.get("Body", "{}")
                    # テスト ID またはファイルパスがメッセージに含まれるか確認
                    if self._test_id in body or test_file_path in body:
                        logger.info(
                            "SQS message received for test file: %s",
                            test_file_path,
                        )
                        # メッセージを削除
                        self._sqs_client.delete_message(
                            QueueUrl=self.config.sqs_queue_url,
                            ReceiptHandle=message["ReceiptHandle"],
                        )
                        return True

            except Exception as e:
                logger.warning("Error polling SQS: %s", e)

            await asyncio.sleep(2)

        logger.warning(
            "SQS message not received within %d seconds for %s",
            timeout_sec,
            test_file_path,
        )
        return False

    async def _verify_guardrail_integration(self) -> bool:
        """Feature 1 (Guardrails) の統合を確認する.

        Requirement 12.5: 自動拡張 UC の場合、Guardrails が正しく統合されていることを確認。
        CloudWatch メトリクスで GuardrailAllowed または GuardrailBlocked が発行されたかを確認する。

        Returns:
            Guardrail メトリクスが確認された場合 True
        """
        try:
            # CloudWatch メトリクスで Guardrail 関連メトリクスを確認
            end_time = time.time()
            start_time_cw = end_time - 600  # 過去 10 分間

            response = self._cw_client.get_metric_data(
                MetricDataQueries=[
                    {
                        "Id": "guardrail_allowed",
                        "MetricStat": {
                            "Metric": {
                                "Namespace": "FSxN-S3AP-Patterns",
                                "MetricName": "GuardrailAllowed",
                                "Dimensions": [
                                    {
                                        "Name": "UCId",
                                        "Value": self.config.uc_id,
                                    }
                                ],
                            },
                            "Period": 60,
                            "Stat": "Sum",
                        },
                    },
                    {
                        "Id": "guardrail_checked",
                        "MetricStat": {
                            "Metric": {
                                "Namespace": "FSxN-S3AP-Patterns",
                                "MetricName": "GuardrailChecked",
                                "Dimensions": [
                                    {
                                        "Name": "UCId",
                                        "Value": self.config.uc_id,
                                    }
                                ],
                            },
                            "Period": 60,
                            "Stat": "Sum",
                        },
                    },
                ],
                StartTime=time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime(start_time_cw)
                ),
                EndTime=time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime(end_time)
                ),
            )

            # いずれかのメトリクスにデータポイントがあれば統合確認 OK
            for metric_result in response.get("MetricDataResults", []):
                values = metric_result.get("Values", [])
                if values and any(v > 0 for v in values):
                    logger.info(
                        "Guardrail integration confirmed via metric: %s",
                        metric_result.get("Id"),
                    )
                    return True

            # DynamoDB テーブルでも確認
            if self.config.guardrails_table_name:
                table = self._dynamodb.Table(self.config.guardrails_table_name)
                today = time.strftime("%Y-%m-%d")
                response = table.get_item(
                    Key={"pk": "volume_grow", "sk": today}
                )
                if "Item" in response:
                    logger.info("Guardrail tracking record found in DynamoDB")
                    return True

            logger.warning(
                "No guardrail integration evidence found for UC '%s'",
                self.config.uc_id,
            )
            return False

        except Exception as e:
            logger.error("Error verifying guardrail integration: %s", e)
            return False

    async def _cleanup(self) -> None:
        """テストアーティファクトをクリーンアップする."""
        if self._test_file_created and os.path.exists(self._test_file_created):
            try:
                os.remove(self._test_file_created)
                logger.info("Cleaned up test file: %s", self._test_file_created)
            except OSError as e:
                logger.warning(
                    "Failed to remove test file %s: %s",
                    self._test_file_created,
                    e,
                )

        # テストディレクトリの削除
        if not self.config.test_file_path:
            test_dir = os.path.join(
                self._nfs_mount_path, self.config.uc_id, self._test_id
            )
            try:
                if os.path.isdir(test_dir):
                    os.rmdir(test_dir)
            except OSError as e:
                logger.warning(
                    "Failed to remove test directory %s: %s", test_dir, e
                )


# ---------------------------------------------------------------------------
# Pytest E2E Tests
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestProductionUCDeployment:
    """Production UC Deployment E2E 検証テスト.

    実環境（CloudFormation + FSx ONTAP + SQS + Step Functions）が必要なため、
    CI では @pytest.mark.e2e マーカーでスキップ可能。

    Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.5, 12.6
    """

    @pytest.fixture
    def config(self) -> ProductionUCConfig:
        """テスト用の ProductionUCConfig を作成する."""
        return ProductionUCConfig(
            uc_id=os.environ.get("TEST_UC_ID", "legal-compliance"),
            trigger_mode="EVENT_DRIVEN",
            stack_name=os.environ.get("TEST_STACK_NAME", ""),
            sqs_queue_url=os.environ.get("SQS_QUEUE_URL", ""),
            state_machine_arn=os.environ.get("STATE_MACHINE_ARN", ""),
            nfs_mount_path=os.environ.get("NFS_MOUNT_PATH", "/mnt/fsxn"),
            lineage_table_name=os.environ.get(
                "LINEAGE_TABLE", "fsxn-s3ap-data-lineage"
            ),
            guardrails_table_name=os.environ.get(
                "GUARDRAILS_TABLE", "fsxn-s3ap-guardrails-tracking"
            ),
            has_auto_expand=os.environ.get("HAS_AUTO_EXPAND", "false").lower()
            == "true",
            timeout_sec=int(os.environ.get("E2E_TIMEOUT_SEC", "300")),
        )

    @pytest.fixture
    def validator(self, config: ProductionUCConfig) -> ProductionUCValidator:
        """テスト用の ProductionUCValidator インスタンスを作成する."""
        return ProductionUCValidator(config=config)

    @pytest.mark.asyncio
    async def test_full_e2e_validation(
        self, validator: ProductionUCValidator
    ):
        """フル E2E 検証を実行する.

        Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.6
        """
        result = await validator.deploy_and_validate()

        # エラーがないことを確認
        assert result.error is None, f"E2E validation failed: {result.error}"

        # ファイル作成の確認 (Requirement 12.2)
        assert result.file_created, "Test file was not created"

        # SQS 配信の確認 (Requirement 12.2)
        assert result.sqs_message_delivered, "SQS message was not delivered"

        # Step Functions 実行の確認 (Requirement 12.3)
        assert result.step_functions_started, (
            "Step Functions execution was not started"
        )
        assert result.step_functions_succeeded, (
            f"Step Functions execution did not succeed. "
            f"ARN: {result.execution_arn}"
        )

        # Data Lineage の確認 (Requirement 12.4)
        assert result.lineage_recorded, (
            "Data Lineage record was not written"
        )

        # E2E レイテンシの確認 (Requirement 12.6)
        assert result.e2e_latency_sec > 0, "E2E latency was not measured"

    @pytest.mark.asyncio
    async def test_trigger_mode_verification(
        self, validator: ProductionUCValidator
    ):
        """TriggerMode=EVENT_DRIVEN の確認のみ実行する.

        Validates: Requirement 12.1
        """
        is_valid = await validator._verify_stack_trigger_mode()
        assert is_valid, (
            f"Stack is not deployed with TriggerMode="
            f"{validator.config.trigger_mode}"
        )

    @pytest.mark.asyncio
    async def test_guardrails_integration(
        self, validator: ProductionUCValidator, config: ProductionUCConfig
    ):
        """Guardrails 統合の確認.

        Validates: Requirement 12.5
        """
        if not config.has_auto_expand:
            pytest.skip("UC does not include auto-expand, skipping guardrails check")

        result = await validator._verify_guardrail_integration()
        assert result, "Guardrails integration not confirmed"


@pytest.mark.e2e
class TestProductionUCValidatorUnit:
    """ProductionUCValidator のユニットテスト（AWS 接続不要な部分）."""

    def test_dataclass_production_uc_config_defaults(self):
        """ProductionUCConfig dataclass のデフォルト値が正しい."""
        config = ProductionUCConfig(uc_id="test-uc")

        assert config.uc_id == "test-uc"
        assert config.trigger_mode == "EVENT_DRIVEN"
        assert config.test_file_path == ""
        assert config.expected_outputs == []
        assert config.timeout_sec == 300
        assert config.stack_name == ""
        assert config.sqs_queue_url == ""
        assert config.state_machine_arn == ""
        assert config.nfs_mount_path == ""
        assert config.lineage_table_name == ""
        assert config.guardrails_table_name == ""
        assert config.has_auto_expand is False

    def test_dataclass_production_uc_config_custom(self):
        """ProductionUCConfig dataclass のカスタム値が正しく設定される."""
        config = ProductionUCConfig(
            uc_id="legal-compliance",
            trigger_mode="EVENT_DRIVEN",
            test_file_path="/mnt/fsxn/test.txt",
            expected_outputs=["bucket/output1.json", "bucket/output2.json"],
            timeout_sec=600,
            stack_name="fsxn-s3ap-legal-compliance",
            sqs_queue_url="https://sqs.ap-northeast-1.amazonaws.com/123/queue",
            state_machine_arn="arn:aws:states:ap-northeast-1:123:stateMachine:sm",
            nfs_mount_path="/mnt/custom",
            lineage_table_name="my-lineage-table",
            guardrails_table_name="my-guardrails-table",
            has_auto_expand=True,
        )

        assert config.uc_id == "legal-compliance"
        assert config.trigger_mode == "EVENT_DRIVEN"
        assert config.test_file_path == "/mnt/fsxn/test.txt"
        assert len(config.expected_outputs) == 2
        assert config.timeout_sec == 600
        assert config.has_auto_expand is True

    def test_dataclass_production_uc_result_defaults(self):
        """ProductionUCResult dataclass のデフォルト値が正しい."""
        result = ProductionUCResult(
            uc_id="test-uc",
            file_created=True,
            fpolicy_event_received=True,
            sqs_message_delivered=True,
            step_functions_started=True,
            step_functions_succeeded=True,
        )

        assert result.uc_id == "test-uc"
        assert result.file_created is True
        assert result.fpolicy_event_received is True
        assert result.sqs_message_delivered is True
        assert result.step_functions_started is True
        assert result.step_functions_succeeded is True
        assert result.execution_arn is None
        assert result.e2e_latency_sec == 0.0
        assert result.lineage_recorded is False
        assert result.guardrail_checked is False
        assert result.outputs_verified is False
        assert result.error is None

    def test_dataclass_production_uc_result_with_error(self):
        """エラー付き ProductionUCResult が正しく初期化される."""
        result = ProductionUCResult(
            uc_id="test-uc",
            file_created=True,
            fpolicy_event_received=False,
            sqs_message_delivered=False,
            step_functions_started=False,
            step_functions_succeeded=False,
            error="FPolicy event not received",
            e2e_latency_sec=15.5,
        )

        assert result.error == "FPolicy event not received"
        assert result.e2e_latency_sec == 15.5
        assert result.fpolicy_event_received is False

    def test_dataclass_production_uc_result_full(self):
        """全フィールドが設定された ProductionUCResult."""
        result = ProductionUCResult(
            uc_id="legal-compliance",
            file_created=True,
            fpolicy_event_received=True,
            sqs_message_delivered=True,
            step_functions_started=True,
            step_functions_succeeded=True,
            execution_arn="arn:aws:states:ap-northeast-1:123:execution:sm:exec-1",
            e2e_latency_sec=45.2,
            lineage_recorded=True,
            guardrail_checked=True,
            outputs_verified=True,
        )

        assert result.execution_arn is not None
        assert result.lineage_recorded is True
        assert result.guardrail_checked is True
        assert result.outputs_verified is True
        assert result.e2e_latency_sec == 45.2

    def test_validator_initialization(self):
        """ProductionUCValidator が正しく初期化される."""
        config = ProductionUCConfig(
            uc_id="test-uc",
            nfs_mount_path="/mnt/test",
        )
        validator = ProductionUCValidator(config=config)

        assert validator.config.uc_id == "test-uc"
        assert validator._nfs_mount_path == "/mnt/test"
        assert validator._test_id.startswith("prod-uc-")
        assert validator._test_file_created is None

    def test_validator_test_id_uniqueness(self):
        """各 Validator インスタンスが一意のテスト ID を持つ."""
        config = ProductionUCConfig(uc_id="test-uc")
        v1 = ProductionUCValidator(config=config)
        v2 = ProductionUCValidator(config=config)

        assert v1._test_id != v2._test_id
        assert v1._test_id.startswith("prod-uc-")
        assert v2._test_id.startswith("prod-uc-")
