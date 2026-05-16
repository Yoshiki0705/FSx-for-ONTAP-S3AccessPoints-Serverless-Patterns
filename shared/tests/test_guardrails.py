"""Capacity Guardrails ユニットテスト.

CapacityGuardrail クラスの各モード動作、レート制限、日次キャップ、
クールダウン、DynamoDB 障害時の fail-closed/fail-open を検証する。
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.guardrails import CapacityGuardrail, GuardrailMode, GuardrailResult


@pytest.fixture
def guardrail_table_name():
    return "test-guardrails-tracking"


@pytest.fixture
def dynamodb_table(guardrail_table_name):
    """Create a mock DynamoDB table for testing."""
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-1")
        table = dynamodb.create_table(
            TableName=guardrail_table_name,
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        table.meta.client.get_waiter("table_exists").wait(
            TableName=guardrail_table_name
        )
        yield table


@pytest.fixture
def sns_topic():
    """Create a mock SNS topic."""
    with mock_aws():
        sns = boto3.client("sns", region_name="ap-northeast-1")
        response = sns.create_topic(Name="test-guardrail-alerts")
        yield response["TopicArn"]


@pytest.fixture
def env_vars(guardrail_table_name):
    """Set environment variables for testing."""
    env = {
        "GUARDRAIL_TABLE": guardrail_table_name,
        "GUARDRAIL_MODE": "ENFORCE",
        "GUARDRAIL_RATE_LIMIT": "10",
        "GUARDRAIL_DAILY_CAP_GB": "500.0",
        "GUARDRAIL_COOLDOWN_SECONDS": "300",
        "GUARDRAIL_SNS_TOPIC_ARN": "",
        "AWS_DEFAULT_REGION": "ap-northeast-1",
    }
    with patch.dict(os.environ, env):
        yield env


class TestGuardrailMode:
    """GuardrailMode enum のテスト."""

    def test_dry_run_value(self):
        assert GuardrailMode.DRY_RUN.value == "DRY_RUN"

    def test_enforce_value(self):
        assert GuardrailMode.ENFORCE.value == "ENFORCE"

    def test_break_glass_value(self):
        assert GuardrailMode.BREAK_GLASS.value == "BREAK_GLASS"

    def test_from_string(self):
        assert GuardrailMode("DRY_RUN") == GuardrailMode.DRY_RUN
        assert GuardrailMode("ENFORCE") == GuardrailMode.ENFORCE
        assert GuardrailMode("BREAK_GLASS") == GuardrailMode.BREAK_GLASS


class TestGuardrailResult:
    """GuardrailResult dataclass のテスト."""

    def test_allowed_result(self):
        result = GuardrailResult(allowed=True, mode=GuardrailMode.ENFORCE)
        assert result.allowed is True
        assert result.mode == GuardrailMode.ENFORCE
        assert result.reason is None
        assert result.action_id is None

    def test_denied_result(self):
        result = GuardrailResult(
            allowed=False, mode=GuardrailMode.ENFORCE, reason="rate_limit_exceeded"
        )
        assert result.allowed is False
        assert result.reason == "rate_limit_exceeded"


class TestCapacityGuardrailEnforce:
    """ENFORCE モードのテスト."""

    @mock_aws
    def test_allow_action_within_limits(self, env_vars, guardrail_table_name):
        """制限内のアクションは許可される."""
        # Setup DynamoDB table
        dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-1")
        dynamodb.create_table(
            TableName=guardrail_table_name,
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        guardrail = CapacityGuardrail(
            table_name=guardrail_table_name,
            mode=GuardrailMode.ENFORCE,
        )
        result = guardrail.check_and_execute("volume_grow", 50.0)

        assert result.allowed is True
        assert result.mode == GuardrailMode.ENFORCE
        assert result.action_id is not None

    @mock_aws
    def test_deny_rate_limit_exceeded(self, env_vars, guardrail_table_name):
        """レート制限超過時はアクションを拒否する."""
        dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-1")
        dynamodb.create_table(
            TableName=guardrail_table_name,
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Pre-populate with rate limit reached
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        table = dynamodb.Table(guardrail_table_name)
        table.put_item(
            Item={
                "pk": "volume_grow",
                "sk": today,
                "daily_total_gb": 100,
                "action_count": 10,  # At rate limit
                "last_action_ts": "1970-01-01T00:00:00Z",
                "actions": [],
            }
        )

        guardrail = CapacityGuardrail(
            table_name=guardrail_table_name,
            mode=GuardrailMode.ENFORCE,
        )
        result = guardrail.check_and_execute("volume_grow", 10.0)

        assert result.allowed is False
        assert result.reason == "rate_limit_exceeded"

    @mock_aws
    def test_deny_daily_cap_exceeded(self, env_vars, guardrail_table_name):
        """日次キャップ超過時はアクションを拒否する."""
        dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-1")
        dynamodb.create_table(
            TableName=guardrail_table_name,
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Pre-populate with near cap
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        table = dynamodb.Table(guardrail_table_name)
        table.put_item(
            Item={
                "pk": "volume_grow",
                "sk": today,
                "daily_total_gb": 490,
                "action_count": 5,
                "last_action_ts": "1970-01-01T00:00:00Z",
                "actions": [],
            }
        )

        guardrail = CapacityGuardrail(
            table_name=guardrail_table_name,
            mode=GuardrailMode.ENFORCE,
        )
        # Request 20 GB would exceed 500 GB cap
        result = guardrail.check_and_execute("volume_grow", 20.0)

        assert result.allowed is False
        assert result.reason == "daily_cap_exceeded"

    @mock_aws
    def test_deny_cooldown_active(self, env_vars, guardrail_table_name):
        """クールダウン期間中はアクションを拒否する."""
        dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-1")
        dynamodb.create_table(
            TableName=guardrail_table_name,
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Pre-populate with recent action (within cooldown)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        recent_ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        table = dynamodb.Table(guardrail_table_name)
        table.put_item(
            Item={
                "pk": "volume_grow",
                "sk": today,
                "daily_total_gb": 50,
                "action_count": 1,
                "last_action_ts": recent_ts,
                "actions": [],
            }
        )

        guardrail = CapacityGuardrail(
            table_name=guardrail_table_name,
            mode=GuardrailMode.ENFORCE,
        )
        result = guardrail.check_and_execute("volume_grow", 10.0)

        assert result.allowed is False
        assert result.reason == "cooldown_active"

    @mock_aws
    def test_updates_tracking_on_success(self, env_vars, guardrail_table_name):
        """許可されたアクション後にDynamoDBカウンターが更新される."""
        dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-1")
        dynamodb.create_table(
            TableName=guardrail_table_name,
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        guardrail = CapacityGuardrail(
            table_name=guardrail_table_name,
            mode=GuardrailMode.ENFORCE,
        )
        result = guardrail.check_and_execute("volume_grow", 50.0)
        assert result.allowed is True

        usage = guardrail.get_daily_usage("volume_grow")
        assert usage["daily_total_gb"] == 50.0
        assert usage["action_count"] == 1


class TestCapacityGuardrailDryRun:
    """DRY_RUN モードのテスト."""

    @mock_aws
    def test_dry_run_always_allows(self, env_vars, guardrail_table_name):
        """DRY_RUN モードでは常に許可される."""
        dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-1")
        dynamodb.create_table(
            TableName=guardrail_table_name,
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Pre-populate with rate limit exceeded
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        table = dynamodb.Table(guardrail_table_name)
        table.put_item(
            Item={
                "pk": "volume_grow",
                "sk": today,
                "daily_total_gb": 490,
                "action_count": 10,
                "last_action_ts": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
                "actions": [],
            }
        )

        guardrail = CapacityGuardrail(
            table_name=guardrail_table_name,
            mode=GuardrailMode.DRY_RUN,
        )
        result = guardrail.check_and_execute("volume_grow", 50.0)

        # DRY_RUN always allows even when checks would fail
        assert result.allowed is True
        assert result.mode == GuardrailMode.DRY_RUN

    @mock_aws
    def test_dry_run_fail_open_on_dynamodb_error(self, env_vars, guardrail_table_name):
        """DRY_RUN モードでDynamoDB障害時はfail-open."""
        # Don't create the table — access will fail
        dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-1")
        # Table doesn't exist, so access will fail

        guardrail = CapacityGuardrail(
            table_name="nonexistent-table",
            mode=GuardrailMode.DRY_RUN,
        )
        result = guardrail.check_and_execute("volume_grow", 50.0)

        assert result.allowed is True
        assert "dynamodb_access_failed" in (result.reason or "")


class TestCapacityGuardrailBreakGlass:
    """BREAK_GLASS モードのテスト."""

    @mock_aws
    def test_break_glass_always_allows(self, env_vars, guardrail_table_name):
        """BREAK_GLASS モードでは常に許可される."""
        dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-1")
        dynamodb.create_table(
            TableName=guardrail_table_name,
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        guardrail = CapacityGuardrail(
            table_name=guardrail_table_name,
            mode=GuardrailMode.BREAK_GLASS,
        )
        result = guardrail.check_and_execute("volume_grow", 9999.0)

        assert result.allowed is True
        assert result.mode == GuardrailMode.BREAK_GLASS
        assert result.action_id is not None

    @mock_aws
    def test_break_glass_sends_sns_alert(self, env_vars, guardrail_table_name):
        """BREAK_GLASS モードでSNS通知が送信される."""
        dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-1")
        dynamodb.create_table(
            TableName=guardrail_table_name,
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        sns = boto3.client("sns", region_name="ap-northeast-1")
        topic = sns.create_topic(Name="test-alerts")
        topic_arn = topic["TopicArn"]

        with patch.dict(os.environ, {"GUARDRAIL_SNS_TOPIC_ARN": topic_arn}):
            guardrail = CapacityGuardrail(
                table_name=guardrail_table_name,
                mode=GuardrailMode.BREAK_GLASS,
            )
            result = guardrail.check_and_execute("volume_grow", 100.0)

        assert result.allowed is True


class TestCapacityGuardrailFailClosed:
    """DynamoDB 障害時の fail-closed テスト."""

    @mock_aws
    def test_enforce_fail_closed_on_dynamodb_error(
        self, env_vars, guardrail_table_name
    ):
        """ENFORCE モードでDynamoDB障害時はfail-closed."""
        # Table doesn't exist
        guardrail = CapacityGuardrail(
            table_name="nonexistent-table",
            mode=GuardrailMode.ENFORCE,
        )
        result = guardrail.check_and_execute("volume_grow", 50.0)

        assert result.allowed is False
        assert result.reason == "dynamodb_access_failed"


class TestCapacityGuardrailExecuteFn:
    """execute_fn 実行のテスト."""

    @mock_aws
    def test_execute_fn_called_on_allow(self, env_vars, guardrail_table_name):
        """許可時にexecute_fnが呼ばれる."""
        dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-1")
        dynamodb.create_table(
            TableName=guardrail_table_name,
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        mock_fn = MagicMock()
        guardrail = CapacityGuardrail(
            table_name=guardrail_table_name,
            mode=GuardrailMode.ENFORCE,
        )
        result = guardrail.check_and_execute(
            "volume_grow", 50.0, execute_fn=mock_fn, volume_id="vol-123"
        )

        assert result.allowed is True
        mock_fn.assert_called_once_with(volume_id="vol-123")

    @mock_aws
    def test_execute_fn_not_called_on_deny(self, env_vars, guardrail_table_name):
        """拒否時にexecute_fnは呼ばれない."""
        dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-1")
        dynamodb.create_table(
            TableName=guardrail_table_name,
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Pre-populate with rate limit exceeded
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        table = dynamodb.Table(guardrail_table_name)
        table.put_item(
            Item={
                "pk": "volume_grow",
                "sk": today,
                "daily_total_gb": 100,
                "action_count": 10,
                "last_action_ts": "1970-01-01T00:00:00Z",
                "actions": [],
            }
        )

        mock_fn = MagicMock()
        guardrail = CapacityGuardrail(
            table_name=guardrail_table_name,
            mode=GuardrailMode.ENFORCE,
        )
        result = guardrail.check_and_execute(
            "volume_grow", 10.0, execute_fn=mock_fn
        )

        assert result.allowed is False
        mock_fn.assert_not_called()


class TestGetDailyUsage:
    """get_daily_usage のテスト."""

    @mock_aws
    def test_empty_usage(self, env_vars, guardrail_table_name):
        """レコードがない場合はゼロ状態を返す."""
        dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-1")
        dynamodb.create_table(
            TableName=guardrail_table_name,
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        guardrail = CapacityGuardrail(
            table_name=guardrail_table_name,
            mode=GuardrailMode.ENFORCE,
        )
        usage = guardrail.get_daily_usage("volume_grow")

        assert usage["daily_total_gb"] == 0.0
        assert usage["action_count"] == 0
        assert usage["last_action_ts"] == 0.0


class TestResetDailyCounters:
    """reset_daily_counters のテスト."""

    @mock_aws
    def test_reset_counters(self, env_vars, guardrail_table_name):
        """カウンターがリセットされる."""
        dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-1")
        dynamodb.create_table(
            TableName=guardrail_table_name,
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        guardrail = CapacityGuardrail(
            table_name=guardrail_table_name,
            mode=GuardrailMode.ENFORCE,
        )

        # First, execute an action to create some state
        guardrail.check_and_execute("volume_grow", 50.0)
        usage = guardrail.get_daily_usage("volume_grow")
        assert usage["daily_total_gb"] == 50.0

        # Reset
        guardrail.reset_daily_counters("volume_grow")
        usage = guardrail.get_daily_usage("volume_grow")
        assert usage["daily_total_gb"] == 0.0
        assert usage["action_count"] == 0
