"""Capacity Guardrails プロパティベーステスト.

Property 1: Guardrail Mode Consistency
  - BREAK_GLASS → 常に allowed=True
  - DRY_RUN → 常に allowed=True
Property 2: ENFORCE Daily Cap Invariant
  - 任意のアクションシーケンスで daily_total_gb が daily_cap_gb を超過しない

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.7**
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from decimal import Decimal

import boto3
import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st
from moto import mock_aws

from shared.guardrails import CapacityGuardrail, GuardrailMode, GuardrailResult


# --- Hypothesis Strategies ---

action_type_strategy = st.sampled_from([
    "volume_grow",
    "volume_shrink",
    "tier_change",
    "snapshot_create",
    "flexclone_create",
])

requested_gb_strategy = st.floats(min_value=0.1, max_value=200.0, allow_nan=False, allow_infinity=False)

daily_cap_strategy = st.floats(min_value=50.0, max_value=2000.0, allow_nan=False, allow_infinity=False)

rate_limit_strategy = st.integers(min_value=1, max_value=50)

# Strategy for a sequence of action requests (list of GB amounts)
action_sequence_strategy = st.lists(
    st.floats(min_value=0.1, max_value=100.0, allow_nan=False, allow_infinity=False),
    min_size=1,
    max_size=20,
)


# --- Helpers ---

TABLE_NAME = "test-guardrails-pbt"


def _ensure_table_exists(region: str = "ap-northeast-1") -> None:
    """Create the DynamoDB guardrails tracking table if it doesn't exist."""
    dynamodb = boto3.resource("dynamodb", region_name=region)
    existing_tables = boto3.client("dynamodb", region_name=region).list_tables()["TableNames"]
    if TABLE_NAME not in existing_tables:
        dynamodb.create_table(
            TableName=TABLE_NAME,
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


# --- Property 1: Guardrail Mode Consistency ---


class TestGuardrailModeConsistency:
    """Property 1: Guardrail Mode Consistency.

    **Validates: Requirements 1.1, 1.2, 1.3**

    BREAK_GLASS モードでは常に allowed=True を返す。
    DRY_RUN モードでは常に allowed=True を返す（チェック失敗時もブロックしない）。
    """

    @pytest.mark.property
    @given(
        action_type=action_type_strategy,
        requested_gb=requested_gb_strategy,
    )
    @settings(max_examples=50, deadline=None, suppress_health_check=[
        HealthCheck.function_scoped_fixture,
    ])
    def test_break_glass_always_allows(self, action_type: str, requested_gb: float):
        """BREAK_GLASS モードでは任意のアクション・GB量で常に allowed=True."""
        os.environ["AWS_DEFAULT_REGION"] = "ap-northeast-1"
        with mock_aws():
            _ensure_table_exists()

            guardrail = CapacityGuardrail(
                table_name=TABLE_NAME,
                mode=GuardrailMode.BREAK_GLASS,
            )
            result = guardrail.check_and_execute(action_type, requested_gb)

            assert result.allowed is True
            assert result.mode == GuardrailMode.BREAK_GLASS

    @pytest.mark.property
    @given(
        action_type=action_type_strategy,
        requested_gb=requested_gb_strategy,
        pre_daily_total=st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        pre_action_count=st.integers(min_value=0, max_value=100),
    )
    @settings(max_examples=50, deadline=None, suppress_health_check=[
        HealthCheck.function_scoped_fixture,
    ])
    def test_dry_run_always_allows(
        self,
        action_type: str,
        requested_gb: float,
        pre_daily_total: float,
        pre_action_count: int,
    ):
        """DRY_RUN モードでは任意の事前状態でも常に allowed=True.

        レート制限超過、日次キャップ超過、クールダウン中でもブロックしない。
        """
        os.environ["AWS_DEFAULT_REGION"] = "ap-northeast-1"
        with mock_aws():
            _ensure_table_exists()

            # Pre-populate DynamoDB with arbitrary state (may exceed limits)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-1")
            table = dynamodb.Table(TABLE_NAME)
            # Use a recent timestamp to trigger cooldown
            recent_ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            table.put_item(
                Item={
                    "pk": action_type,
                    "sk": today,
                    "daily_total_gb": Decimal(str(round(pre_daily_total, 4))),
                    "action_count": pre_action_count,
                    "last_action_ts": recent_ts,
                    "actions": [],
                }
            )

            guardrail = CapacityGuardrail(
                table_name=TABLE_NAME,
                mode=GuardrailMode.DRY_RUN,
            )
            result = guardrail.check_and_execute(action_type, requested_gb)

            assert result.allowed is True
            assert result.mode == GuardrailMode.DRY_RUN

    @pytest.mark.property
    @given(
        action_type=action_type_strategy,
        requested_gb=requested_gb_strategy,
    )
    @settings(max_examples=30, deadline=None, suppress_health_check=[
        HealthCheck.function_scoped_fixture,
    ])
    def test_dry_run_fail_open_on_dynamodb_error(
        self, action_type: str, requested_gb: float
    ):
        """DRY_RUN モードで DynamoDB アクセス失敗時も allowed=True (fail-open)."""
        os.environ["AWS_DEFAULT_REGION"] = "ap-northeast-1"
        with mock_aws():
            # Don't create the table — access will fail
            guardrail = CapacityGuardrail(
                table_name="nonexistent-table-pbt",
                mode=GuardrailMode.DRY_RUN,
            )
            result = guardrail.check_and_execute(action_type, requested_gb)

            assert result.allowed is True


# --- Property 2: ENFORCE Daily Cap Invariant ---


class TestEnforceDailyCapInvariant:
    """Property 2: ENFORCE Daily Cap Invariant.

    **Validates: Requirements 1.4, 1.5, 1.7**

    ENFORCE モードで任意のアクションシーケンスを実行した後、
    daily_total_gb が daily_cap_gb を超過しないことを検証する。
    """

    @pytest.mark.property
    @given(
        action_type=action_type_strategy,
        action_sequence=action_sequence_strategy,
        daily_cap_gb=daily_cap_strategy,
    )
    @settings(max_examples=30, deadline=None, suppress_health_check=[
        HealthCheck.function_scoped_fixture,
    ])
    def test_daily_total_never_exceeds_cap(
        self,
        action_type: str,
        action_sequence: list[float],
        daily_cap_gb: float,
    ):
        """任意のアクションシーケンスで daily_total_gb <= daily_cap_gb が不変条件."""
        os.environ["AWS_DEFAULT_REGION"] = "ap-northeast-1"
        os.environ["GUARDRAIL_DAILY_CAP_GB"] = str(daily_cap_gb)
        os.environ["GUARDRAIL_RATE_LIMIT"] = "1000"  # High limit to focus on cap
        os.environ["GUARDRAIL_COOLDOWN_SECONDS"] = "0"  # Disable cooldown

        with mock_aws():
            _ensure_table_exists()

            guardrail = CapacityGuardrail(
                table_name=TABLE_NAME,
                mode=GuardrailMode.ENFORCE,
            )

            for requested_gb in action_sequence:
                guardrail.check_and_execute(action_type, requested_gb)

            # After all actions, daily_total_gb must not exceed daily_cap_gb.
            # Note: The guardrail check uses strict > comparison, so daily_total_gb
            # can equal daily_cap_gb (when a single request exactly fills the cap).
            # We allow a small tolerance for Decimal/float conversion rounding.
            usage = guardrail.get_daily_usage(action_type)
            assert usage["daily_total_gb"] <= daily_cap_gb + 0.001, (
                f"Daily total {usage['daily_total_gb']:.4f} GB exceeded cap "
                f"{daily_cap_gb:.4f} GB after {len(action_sequence)} actions"
            )

    @pytest.mark.property
    @given(
        action_type=action_type_strategy,
        action_sequence=action_sequence_strategy,
        daily_cap_gb=daily_cap_strategy,
        rate_limit=rate_limit_strategy,
    )
    @settings(max_examples=30, deadline=None, suppress_health_check=[
        HealthCheck.function_scoped_fixture,
    ])
    def test_action_count_never_exceeds_rate_limit(
        self,
        action_type: str,
        action_sequence: list[float],
        daily_cap_gb: float,
        rate_limit: int,
    ):
        """任意のアクションシーケンスで action_count <= rate_limit が不変条件."""
        os.environ["AWS_DEFAULT_REGION"] = "ap-northeast-1"
        os.environ["GUARDRAIL_DAILY_CAP_GB"] = str(daily_cap_gb)
        os.environ["GUARDRAIL_RATE_LIMIT"] = str(rate_limit)
        os.environ["GUARDRAIL_COOLDOWN_SECONDS"] = "0"  # Disable cooldown

        with mock_aws():
            _ensure_table_exists()

            guardrail = CapacityGuardrail(
                table_name=TABLE_NAME,
                mode=GuardrailMode.ENFORCE,
            )

            for requested_gb in action_sequence:
                guardrail.check_and_execute(action_type, requested_gb)

            usage = guardrail.get_daily_usage(action_type)
            assert usage["action_count"] <= rate_limit, (
                f"Action count {usage['action_count']} exceeded rate limit "
                f"{rate_limit} after {len(action_sequence)} actions"
            )
