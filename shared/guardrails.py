"""shared.guardrails — Capacity Guardrails モジュール

FSx ONTAP の自動拡張操作に対するレート制限・日次上限・クールダウン制御を提供する。
GuardrailMode（DRY_RUN / ENFORCE / BREAK_GLASS）に応じた安全制御を実装し、
CloudWatch EMF メトリクスと DynamoDB による追跡を行う。

設計方針:
- 環境変数 GUARDRAIL_MODE からモードを読み込み
- ENFORCE: fail-closed（DynamoDB アクセス失敗時はアクションを拒否）
- DRY_RUN: fail-open（DynamoDB アクセス失敗時はアクションを許可）
- BREAK_GLASS: 全チェックをバイパスし、SNS 通知 + 監査ログ発行
- CloudWatch EMF メトリクスに Mode + ActionType ディメンション追加

Usage:
    from shared.guardrails import CapacityGuardrail, GuardrailMode, GuardrailResult

    guardrail = CapacityGuardrail()
    result = guardrail.check_and_execute(
        action_type="volume_grow",
        requested_gb=50.0,
        execute_fn=my_grow_function,
        volume_id="vol-abc123",
    )
    if result.allowed:
        print(f"Action executed: {result.action_id}")
    else:
        print(f"Action denied: {result.reason}")
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

import boto3
from botocore.exceptions import ClientError

from shared.observability import EmfMetrics

logger = logging.getLogger(__name__)


class GuardrailMode(Enum):
    """ガードレールの動作モード。"""

    DRY_RUN = "DRY_RUN"
    ENFORCE = "ENFORCE"
    BREAK_GLASS = "BREAK_GLASS"


@dataclass
class GuardrailResult:
    """ガードレールチェック結果。"""

    allowed: bool
    mode: GuardrailMode
    reason: str | None = None
    action_id: str | None = None


class CapacityGuardrail:
    """FSx ONTAP 自動拡張操作に対する安全制御クラス。

    DynamoDB テーブルで日次拡張量・アクション回数・最終実行時刻を追跡し、
    ENFORCE モードではレート制限・日次キャップ・クールダウン期間を検証する。

    Args:
        table_name: DynamoDB テーブル名。None の場合は環境変数から取得。
        mode: ガードレールモード。None の場合は環境変数から取得。
    """

    # デフォルト設定値
    DEFAULT_RATE_LIMIT: int = 10
    DEFAULT_DAILY_CAP_GB: float = 500.0
    DEFAULT_COOLDOWN_SECONDS: int = 300

    def __init__(
        self,
        table_name: str | None = None,
        mode: GuardrailMode | None = None,
    ) -> None:
        self._table_name = table_name or os.environ.get(
            "GUARDRAIL_TABLE", "fsxn-s3ap-guardrails-tracking"
        )
        self._mode = mode or GuardrailMode(
            os.environ.get("GUARDRAIL_MODE", "DRY_RUN")
        )
        self._rate_limit = int(
            os.environ.get("GUARDRAIL_RATE_LIMIT", str(self.DEFAULT_RATE_LIMIT))
        )
        self._daily_cap_gb = float(
            os.environ.get("GUARDRAIL_DAILY_CAP_GB", str(self.DEFAULT_DAILY_CAP_GB))
        )
        self._cooldown_seconds = int(
            os.environ.get(
                "GUARDRAIL_COOLDOWN_SECONDS", str(self.DEFAULT_COOLDOWN_SECONDS)
            )
        )
        self._sns_topic_arn = os.environ.get("GUARDRAIL_SNS_TOPIC_ARN", "")
        self._dynamodb = boto3.resource("dynamodb")
        self._sns_client = boto3.client("sns")

    @property
    def mode(self) -> GuardrailMode:
        """現在のガードレールモードを返す。"""
        return self._mode

    def check_and_execute(
        self,
        action_type: str,
        requested_gb: float,
        execute_fn: callable | None = None,
        **kwargs: Any,
    ) -> GuardrailResult:
        """ガードレールチェックを実行し、許可された場合にアクションを実行する。

        Args:
            action_type: アクション種別（例: "volume_grow"）
            requested_gb: リクエストされた拡張量（GB）
            execute_fn: 実行する関数。None の場合はチェックのみ。
            **kwargs: execute_fn に渡す追加引数

        Returns:
            GuardrailResult: チェック結果
        """
        metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns")
        metrics.set_dimension("Mode", self._mode.value)
        metrics.set_dimension("ActionType", action_type)

        # BREAK_GLASS: bypass all checks
        if self._mode == GuardrailMode.BREAK_GLASS:
            self._send_break_glass_alert(action_type, requested_gb, **kwargs)
            action_id = self._execute_action(execute_fn, **kwargs)
            self._safe_update_tracking(action_type, requested_gb)
            metrics.put_metric("GuardrailBypass", 1.0, "Count")
            metrics.flush()
            logger.info(
                "[Guardrail] BREAK_GLASS: action=%s gb=%.1f action_id=%s",
                action_type,
                requested_gb,
                action_id,
            )
            return GuardrailResult(
                allowed=True, mode=self._mode, action_id=action_id
            )

        # Load current daily state (with fail-closed/fail-open handling)
        try:
            daily_state = self._get_daily_state(action_type)
        except Exception as e:
            logger.error(
                "[Guardrail] DynamoDB access failed: %s", str(e)
            )
            return self._handle_dynamodb_failure(metrics, action_type, e)

        # Check 1: Per-action rate limit
        if daily_state["action_count"] >= self._rate_limit:
            return self._deny(metrics, "rate_limit_exceeded", action_type)

        # Check 2: Daily cumulative cap
        if daily_state["daily_total_gb"] + requested_gb > self._daily_cap_gb:
            return self._deny(metrics, "daily_cap_exceeded", action_type)

        # Check 3: Cooldown period
        elapsed = time.time() - daily_state["last_action_ts"]
        if elapsed < self._cooldown_seconds:
            return self._deny(metrics, "cooldown_active", action_type)

        # All checks passed
        if self._mode == GuardrailMode.DRY_RUN:
            metrics.put_metric("GuardrailDryRunAllowed", 1.0, "Count")

        # Execute action (both DRY_RUN and ENFORCE)
        action_id = self._execute_action(execute_fn, **kwargs)

        # Update tracking
        try:
            self._update_tracking(action_type, requested_gb)
        except Exception as e:
            logger.error(
                "[Guardrail] Failed to update tracking after execution: %s",
                str(e),
            )
            # Action already executed, log the failure but don't deny

        metrics.put_metric("GuardrailAllowed", 1.0, "Count")
        metrics.flush()
        logger.info(
            "[Guardrail] %s: action=%s gb=%.1f action_id=%s",
            self._mode.value,
            action_type,
            requested_gb,
            action_id,
        )
        return GuardrailResult(
            allowed=True, mode=self._mode, action_id=action_id
        )

    def get_daily_usage(self, action_type: str) -> dict[str, Any]:
        """指定アクション種別の日次使用状況を取得する。

        Args:
            action_type: アクション種別

        Returns:
            日次使用状況の辞書（daily_total_gb, action_count, last_action_ts）
        """
        state = self._get_daily_state(action_type)
        return {
            "daily_total_gb": state["daily_total_gb"],
            "action_count": state["action_count"],
            "last_action_ts": state["last_action_ts"],
        }

    def reset_daily_counters(self, action_type: str) -> None:
        """指定アクション種別の日次カウンターをリセットする。

        Args:
            action_type: アクション種別
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        table = self._dynamodb.Table(self._table_name)
        table.put_item(
            Item={
                "pk": action_type,
                "sk": today,
                "daily_total_gb": Decimal("0"),
                "action_count": 0,
                "last_action_ts": "1970-01-01T00:00:00Z",
                "actions": [],
                "ttl": int(time.time()) + (30 * 86400),
            }
        )
        logger.info(
            "[Guardrail] Reset daily counters: action_type=%s date=%s",
            action_type,
            today,
        )

    # ─── Private Methods ───────────────────────────────────────────────

    def _get_daily_state(self, action_type: str) -> dict[str, Any]:
        """DynamoDB から当日の状態を取得する。

        Args:
            action_type: アクション種別

        Returns:
            日次状態の辞書

        Raises:
            ClientError: DynamoDB アクセスに失敗した場合
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        table = self._dynamodb.Table(self._table_name)

        response = table.get_item(
            Key={"pk": action_type, "sk": today},
            ConsistentRead=True,
        )

        item = response.get("Item")
        if item is None:
            # No record for today — return zero state
            return {
                "daily_total_gb": 0.0,
                "action_count": 0,
                "last_action_ts": 0.0,
            }

        # Parse last_action_ts to epoch
        last_action_ts_str = item.get("last_action_ts", "1970-01-01T00:00:00Z")
        try:
            last_action_ts = datetime.fromisoformat(
                last_action_ts_str.replace("Z", "+00:00")
            ).timestamp()
        except (ValueError, AttributeError):
            last_action_ts = 0.0

        return {
            "daily_total_gb": float(item.get("daily_total_gb", 0)),
            "action_count": int(item.get("action_count", 0)),
            "last_action_ts": last_action_ts,
        }

    def _update_tracking(self, action_type: str, requested_gb: float) -> None:
        """DynamoDB の日次カウンターを更新する。

        Args:
            action_type: アクション種別
            requested_gb: 拡張量（GB）
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        table = self._dynamodb.Table(self._table_name)
        ttl_value = int(time.time()) + (30 * 86400)

        action_record = {
            "timestamp": now_iso,
            "requested_gb": str(requested_gb),
            "mode": self._mode.value,
        }

        try:
            table.update_item(
                Key={"pk": action_type, "sk": today},
                UpdateExpression=(
                    "SET daily_total_gb = if_not_exists(daily_total_gb, :zero) + :gb, "
                    "action_count = if_not_exists(action_count, :zero_int) + :one, "
                    "last_action_ts = :now, "
                    "#ttl_attr = :ttl, "
                    "actions = list_append(if_not_exists(actions, :empty_list), :action)"
                ),
                ExpressionAttributeNames={
                    "#ttl_attr": "ttl",
                },
                ExpressionAttributeValues={
                    ":gb": Decimal(str(round(requested_gb, 4))),
                    ":zero": Decimal("0"),
                    ":zero_int": 0,
                    ":one": 1,
                    ":now": now_iso,
                    ":ttl": ttl_value,
                    ":empty_list": [],
                    ":action": [action_record],
                },
            )
        except ClientError as e:
            logger.error(
                "[Guardrail] Failed to update DynamoDB tracking: %s", str(e)
            )
            raise

    def _safe_update_tracking(self, action_type: str, requested_gb: float) -> None:
        """DynamoDB の日次カウンターを更新する（エラーを握りつぶす）。

        BREAK_GLASS モードで使用。追跡更新の失敗はアクション実行を妨げない。
        """
        try:
            self._update_tracking(action_type, requested_gb)
        except Exception as e:
            logger.warning(
                "[Guardrail] BREAK_GLASS tracking update failed (non-blocking): %s",
                str(e),
            )

    def _execute_action(
        self, execute_fn: callable | None, **kwargs: Any
    ) -> str | None:
        """アクション関数を実行し、action_id を返す。

        Args:
            execute_fn: 実行する関数。None の場合はチェックのみ。
            **kwargs: execute_fn に渡す追加引数

        Returns:
            action_id（UUID 文字列）。execute_fn が None の場合も生成される。
        """
        action_id = str(uuid.uuid4())
        if execute_fn is not None:
            try:
                execute_fn(**kwargs)
            except Exception as e:
                logger.error(
                    "[Guardrail] Action execution failed: %s", str(e)
                )
                raise
        return action_id

    def _deny(
        self,
        metrics: EmfMetrics,
        reason: str,
        action_type: str,
    ) -> GuardrailResult:
        """チェック失敗時の処理。

        DRY_RUN モードでは allowed=True を返し（ブロックしない）、
        ENFORCE モードでは allowed=False を返す。

        Args:
            metrics: EmfMetrics インスタンス
            reason: 拒否理由
            action_type: アクション種別

        Returns:
            GuardrailResult
        """
        metrics.put_metric("GuardrailBlocked", 1.0, "Count")
        metrics.set_property("Reason", reason)
        metrics.flush()

        if self._mode == GuardrailMode.DRY_RUN:
            logger.info(
                "[Guardrail] DRY_RUN: would deny action=%s reason=%s (allowing)",
                action_type,
                reason,
            )
            return GuardrailResult(
                allowed=True, mode=self._mode, reason=reason
            )

        # ENFORCE mode: deny the action
        logger.warning(
            "[Guardrail] ENFORCE: denied action=%s reason=%s",
            action_type,
            reason,
        )
        return GuardrailResult(
            allowed=False, mode=self._mode, reason=reason
        )

    def _handle_dynamodb_failure(
        self,
        metrics: EmfMetrics,
        action_type: str,
        error: Exception,
    ) -> GuardrailResult:
        """DynamoDB アクセス失敗時の処理。

        ENFORCE モード: fail-closed（アクションを拒否）
        DRY_RUN モード: fail-open（アクションを許可）

        Args:
            metrics: EmfMetrics インスタンス
            action_type: アクション種別
            error: 発生した例外

        Returns:
            GuardrailResult
        """
        metrics.put_metric("GuardrailDynamoDBError", 1.0, "Count")
        metrics.set_property("Error", str(error))
        metrics.flush()

        if self._mode == GuardrailMode.ENFORCE:
            logger.error(
                "[Guardrail] ENFORCE fail-closed: DynamoDB error for action=%s",
                action_type,
            )
            return GuardrailResult(
                allowed=False,
                mode=self._mode,
                reason="dynamodb_access_failed",
            )

        # DRY_RUN: fail-open
        logger.warning(
            "[Guardrail] DRY_RUN fail-open: DynamoDB error for action=%s (allowing)",
            action_type,
        )
        return GuardrailResult(
            allowed=True,
            mode=self._mode,
            reason="dynamodb_access_failed_failopen",
        )

    def _send_break_glass_alert(
        self,
        action_type: str,
        requested_gb: float,
        **kwargs: Any,
    ) -> None:
        """BREAK_GLASS モード時の SNS 通知を送信する。

        Args:
            action_type: アクション種別
            requested_gb: リクエストされた拡張量（GB）
            **kwargs: 追加コンテキスト情報
        """
        if not self._sns_topic_arn:
            logger.warning(
                "[Guardrail] BREAK_GLASS alert skipped: no SNS topic ARN configured"
            )
            return

        message = {
            "alert_type": "BREAK_GLASS_ACTIVATED",
            "action_type": action_type,
            "requested_gb": requested_gb,
            "timestamp": datetime.now(timezone.utc).isoformat().replace(
                "+00:00", "Z"
            ),
            "context": {
                k: str(v) for k, v in kwargs.items()
            },
        }

        try:
            self._sns_client.publish(
                TopicArn=self._sns_topic_arn,
                Subject=f"[BREAK_GLASS] Guardrail bypassed: {action_type}",
                Message=json.dumps(message, indent=2),
            )
            logger.info(
                "[Guardrail] BREAK_GLASS SNS alert sent: action=%s",
                action_type,
            )
        except ClientError as e:
            logger.error(
                "[Guardrail] Failed to send BREAK_GLASS SNS alert: %s",
                str(e),
            )
            # Do not block the action even if SNS fails in BREAK_GLASS mode
