"""Guardrails Integration ヘルパーのユニットテスト.

shared/integrations/guardrails_integration.py のオプトイン統合ロジックを検証する。
- GUARDRAIL_MODE 未設定時はガードレールをスキップ
- GUARDRAIL_MODE 設定時は CapacityGuardrail 経由で実行
- デコレータとラッパー関数の両方をテスト
- 既存テストに影響を与えないことを確認

Requirements:
- 1.10: オプトイン制御で既存 UC テンプレートに影響を与えない
- 13.2: 既存テンプレートに変更を加えない
- 13.3: 既存テストスイートを破壊しない
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.integrations.guardrails_integration import (
    _is_guardrail_enabled,
    guardrail_check,
    with_guardrail_check,
)


class TestIsGuardrailEnabled:
    """_is_guardrail_enabled() のテスト."""

    def test_not_set(self):
        """GUARDRAIL_MODE が未設定の場合は False."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove GUARDRAIL_MODE if it exists
            os.environ.pop("GUARDRAIL_MODE", None)
            assert _is_guardrail_enabled() is False

    def test_empty_string(self):
        """GUARDRAIL_MODE が空文字列の場合は False."""
        with patch.dict(os.environ, {"GUARDRAIL_MODE": ""}):
            assert _is_guardrail_enabled() is False

    def test_whitespace_only(self):
        """GUARDRAIL_MODE がスペースのみの場合は False."""
        with patch.dict(os.environ, {"GUARDRAIL_MODE": "   "}):
            assert _is_guardrail_enabled() is False

    def test_dry_run_set(self):
        """GUARDRAIL_MODE が DRY_RUN の場合は True."""
        with patch.dict(os.environ, {"GUARDRAIL_MODE": "DRY_RUN"}):
            assert _is_guardrail_enabled() is True

    def test_enforce_set(self):
        """GUARDRAIL_MODE が ENFORCE の場合は True."""
        with patch.dict(os.environ, {"GUARDRAIL_MODE": "ENFORCE"}):
            assert _is_guardrail_enabled() is True

    def test_break_glass_set(self):
        """GUARDRAIL_MODE が BREAK_GLASS の場合は True."""
        with patch.dict(os.environ, {"GUARDRAIL_MODE": "BREAK_GLASS"}):
            assert _is_guardrail_enabled() is True


class TestGuardrailCheck:
    """guardrail_check() 関数のテスト."""

    def test_skip_when_not_enabled(self):
        """GUARDRAIL_MODE 未設定時は execute_fn を直接実行する."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GUARDRAIL_MODE", None)
            mock_fn = MagicMock(return_value="executed")
            result = guardrail_check(
                action_type="volume_grow",
                requested_gb=50.0,
                execute_fn=mock_fn,
                volume_id="vol-123",
            )
            assert result == "executed"
            mock_fn.assert_called_once_with(volume_id="vol-123")

    def test_skip_returns_none_when_no_fn(self):
        """GUARDRAIL_MODE 未設定で execute_fn=None の場合は None を返す."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GUARDRAIL_MODE", None)
            result = guardrail_check(
                action_type="volume_grow",
                requested_gb=50.0,
            )
            assert result is None

    @mock_aws
    def test_enabled_calls_guardrail(self):
        """GUARDRAIL_MODE 設定時は CapacityGuardrail 経由で実行する."""
        # Setup DynamoDB table
        dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-1")
        dynamodb.create_table(
            TableName="fsxn-s3ap-guardrails-tracking",
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

        env = {
            "GUARDRAIL_MODE": "DRY_RUN",
            "GUARDRAIL_TABLE": "fsxn-s3ap-guardrails-tracking",
            "AWS_DEFAULT_REGION": "ap-northeast-1",
        }
        with patch.dict(os.environ, env):
            mock_fn = MagicMock(return_value="expanded")
            result = guardrail_check(
                action_type="volume_grow",
                requested_gb=50.0,
                execute_fn=mock_fn,
                volume_id="vol-123",
            )

            # In DRY_RUN mode, action is always allowed
            from shared.guardrails import GuardrailResult

            assert isinstance(result, GuardrailResult)
            assert result.allowed is True
            mock_fn.assert_called_once_with(volume_id="vol-123")


class TestWithGuardrailCheckDecorator:
    """with_guardrail_check() デコレータのテスト."""

    def test_skip_when_not_enabled(self):
        """GUARDRAIL_MODE 未設定時はデコレートされた関数をそのまま実行する."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GUARDRAIL_MODE", None)

            @with_guardrail_check(action_type="volume_grow")
            def expand_volume(volume_id: str, requested_gb: float = 50.0):
                return f"expanded {volume_id} by {requested_gb}GB"

            result = expand_volume(volume_id="vol-123", requested_gb=100.0)
            assert result == "expanded vol-123 by 100.0GB"

    def test_preserves_function_name(self):
        """デコレータが元の関数名を保持する."""

        @with_guardrail_check(action_type="volume_grow")
        def my_expand_function(volume_id: str, requested_gb: float = 50.0):
            """My docstring."""
            pass

        assert my_expand_function.__name__ == "my_expand_function"
        assert my_expand_function.__doc__ == "My docstring."

    @mock_aws
    def test_enabled_with_decorator(self):
        """GUARDRAIL_MODE 設定時はデコレータがガードレールチェックを実行する."""
        dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-1")
        dynamodb.create_table(
            TableName="fsxn-s3ap-guardrails-tracking",
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

        env = {
            "GUARDRAIL_MODE": "DRY_RUN",
            "GUARDRAIL_TABLE": "fsxn-s3ap-guardrails-tracking",
            "AWS_DEFAULT_REGION": "ap-northeast-1",
        }
        with patch.dict(os.environ, env):

            @with_guardrail_check(action_type="volume_grow")
            def expand_volume(volume_id: str, requested_gb: float = 50.0):
                return f"expanded {volume_id}"

            result = expand_volume(volume_id="vol-123", requested_gb=100.0)

            from shared.guardrails import GuardrailResult

            assert isinstance(result, GuardrailResult)
            assert result.allowed is True

    @mock_aws
    def test_enforce_mode_denies_over_cap(self):
        """ENFORCE モードで日次キャップ超過時はデコレータが拒否する."""
        from datetime import datetime, timezone

        dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-1")
        dynamodb.create_table(
            TableName="fsxn-s3ap-guardrails-tracking",
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

        # Pre-populate near cap
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        table = dynamodb.Table("fsxn-s3ap-guardrails-tracking")
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

        env = {
            "GUARDRAIL_MODE": "ENFORCE",
            "GUARDRAIL_TABLE": "fsxn-s3ap-guardrails-tracking",
            "GUARDRAIL_DAILY_CAP_GB": "500.0",
            "AWS_DEFAULT_REGION": "ap-northeast-1",
        }
        with patch.dict(os.environ, env):
            call_count = 0

            @with_guardrail_check(action_type="volume_grow")
            def expand_volume(volume_id: str, requested_gb: float = 50.0):
                nonlocal call_count
                call_count += 1
                return f"expanded {volume_id}"

            result = expand_volume(volume_id="vol-123", requested_gb=20.0)

            from shared.guardrails import GuardrailResult

            assert isinstance(result, GuardrailResult)
            assert result.allowed is False
            assert result.reason == "daily_cap_exceeded"
            # Function should NOT have been called
            assert call_count == 0


class TestOptInBehavior:
    """オプトイン動作の統合テスト.

    既存 UC Lambda が GUARDRAIL_MODE を設定しない限り、
    ガードレールが一切介入しないことを確認する。
    """

    def test_no_import_side_effects(self):
        """インポートだけでは副作用が発生しない."""
        # This test verifies that importing the module doesn't
        # create any AWS clients or make any API calls
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GUARDRAIL_MODE", None)
            os.environ.pop("AWS_DEFAULT_REGION", None)

            # Re-import should not fail even without AWS credentials
            import importlib

            import shared.integrations.guardrails_integration as mod

            importlib.reload(mod)
            # No exception means no AWS client was created at import time

    def test_decorator_transparent_when_disabled(self):
        """ガードレール無効時はデコレータが完全に透過的."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GUARDRAIL_MODE", None)

            @with_guardrail_check(action_type="volume_grow")
            def compute_something(x: int, y: int) -> int:
                return x + y

            # Should work exactly like the undecorated function
            assert compute_something(3, 4) == 7
            assert compute_something(x=10, y=20) == 30

    def test_guardrail_check_transparent_when_disabled(self):
        """ガードレール無効時は guardrail_check が execute_fn の結果を返す."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GUARDRAIL_MODE", None)

            def my_action(volume_id: str) -> dict:
                return {"status": "success", "volume_id": volume_id}

            result = guardrail_check(
                action_type="volume_grow",
                requested_gb=100.0,
                execute_fn=my_action,
                volume_id="vol-abc",
            )
            assert result == {"status": "success", "volume_id": "vol-abc"}
