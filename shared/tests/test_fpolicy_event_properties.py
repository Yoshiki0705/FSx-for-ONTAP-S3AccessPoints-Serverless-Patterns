"""FPolicy Event プロパティベーステスト.

Property 1: FPolicy Event ラウンドトリップ
Property 3: FPolicy Event スキーマバリデーション正確性
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# Add shared to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.lambdas.fpolicy_engine.handler import (
    SchemaValidationError,
    validate_fpolicy_event,
)

# Load schema for tests
SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "fpolicy-event-schema.json"
with open(SCHEMA_PATH) as f:
    FPOLICY_SCHEMA = json.load(f)


# --- Hypothesis Strategies ---

uuid_strategy = st.from_regex(
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
    fullmatch=True,
)

operation_type_strategy = st.sampled_from(["create", "write", "delete", "rename"])

file_path_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S"),
        blacklist_characters="\x00",
    ),
    min_size=1,
    max_size=200,
).map(lambda s: f"/vol1/{s}")

volume_name_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=50,
)

svm_name_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=50,
)

timestamp_strategy = st.from_regex(
    r"2026-0[1-9]-[0-2][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]\+09:00",
    fullmatch=True,
)

file_size_strategy = st.integers(min_value=0, max_value=5 * 1024 * 1024 * 1024)

ipv4_strategy = st.from_regex(
    r"(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)",
    fullmatch=True,
)


@st.composite
def valid_fpolicy_event(draw: st.DrawFn) -> dict:
    """有効な FPolicy Event を生成する Hypothesis strategy."""
    op_type = draw(operation_type_strategy)

    event = {
        "event_id": draw(uuid_strategy),
        "operation_type": op_type,
        "file_path": draw(file_path_strategy),
        "volume_name": draw(volume_name_strategy),
        "svm_name": draw(svm_name_strategy),
        "timestamp": draw(timestamp_strategy),
        "file_size": draw(file_size_strategy),
    }

    # Optional fields
    if draw(st.booleans()):
        event["client_ip"] = draw(ipv4_strategy)

    if draw(st.booleans()):
        event["metadata"] = draw(
            st.dictionaries(
                keys=st.text(min_size=1, max_size=20),
                values=st.text(max_size=100),
                max_size=5,
            )
        )

    # rename requires previous_path
    if op_type == "rename":
        event["previous_path"] = draw(file_path_strategy)
    elif draw(st.booleans()):
        # Optionally add previous_path for non-rename ops
        event["previous_path"] = draw(file_path_strategy)

    return event


class TestFPolicyEventRoundTrip:
    """Property 1: FPolicy Event ラウンドトリップ."""

    @settings(max_examples=100)
    @given(event=valid_fpolicy_event())
    def test_roundtrip_serialization(self, event: dict) -> None:
        """Feature: fsxn-s3ap-serverless-patterns-phase10, Property 1: FPolicy Event ラウンドトリップ.

        有効な FPolicy Event の JSON シリアライズ→デシリアライズが等価であることを検証。
        """
        serialized = json.dumps(event, ensure_ascii=False)
        deserialized = json.loads(serialized)
        assert deserialized == event

    @settings(max_examples=100)
    @given(event=valid_fpolicy_event())
    def test_roundtrip_preserves_all_fields(self, event: dict) -> None:
        """ラウンドトリップ後に全フィールドが保持されることを検証."""
        serialized = json.dumps(event, ensure_ascii=False)
        deserialized = json.loads(serialized)

        for key in event:
            assert key in deserialized
            assert deserialized[key] == event[key]


class TestFPolicyEventSchemaValidation:
    """Property 3: FPolicy Event スキーマバリデーション正確性."""

    @settings(max_examples=100)
    @given(event=valid_fpolicy_event())
    def test_valid_events_pass_validation(self, event: dict) -> None:
        """Feature: fsxn-s3ap-serverless-patterns-phase10, Property 3: スキーマバリデーション正確性.

        有効な FPolicy Event はバリデーションを通過する。
        """
        result = validate_fpolicy_event(event, schema=FPOLICY_SCHEMA)
        assert result is True

    @settings(max_examples=100)
    @given(event=valid_fpolicy_event())
    def test_missing_required_field_fails(self, event: dict) -> None:
        """必須フィールド欠落時に SchemaValidationError が発生する."""
        required_fields = [
            "event_id",
            "operation_type",
            "file_path",
            "volume_name",
            "svm_name",
            "timestamp",
            "file_size",
        ]

        for field in required_fields:
            if field in event:
                invalid_event = {k: v for k, v in event.items() if k != field}
                with pytest.raises(SchemaValidationError):
                    validate_fpolicy_event(invalid_event, schema=FPOLICY_SCHEMA)

    def test_invalid_operation_type_fails(self) -> None:
        """無効な operation_type でバリデーション失敗."""
        event = {
            "event_id": "12345678-1234-4123-8123-123456789abc",
            "operation_type": "invalid_op",
            "file_path": "/vol1/test.txt",
            "volume_name": "vol1",
            "svm_name": "svm1",
            "timestamp": "2026-01-15T10:30:00+09:00",
            "file_size": 1024,
        }
        with pytest.raises(SchemaValidationError):
            validate_fpolicy_event(event, schema=FPOLICY_SCHEMA)

    def test_rename_without_previous_path_fails(self) -> None:
        """rename 操作で previous_path がない場合にバリデーション失敗."""
        event = {
            "event_id": "12345678-1234-4123-8123-123456789abc",
            "operation_type": "rename",
            "file_path": "/vol1/new_name.txt",
            "volume_name": "vol1",
            "svm_name": "svm1",
            "timestamp": "2026-01-15T10:30:00+09:00",
            "file_size": 1024,
        }
        with pytest.raises(SchemaValidationError):
            validate_fpolicy_event(event, schema=FPOLICY_SCHEMA)

    def test_negative_file_size_fails(self) -> None:
        """負のファイルサイズでバリデーション失敗."""
        event = {
            "event_id": "12345678-1234-4123-8123-123456789abc",
            "operation_type": "create",
            "file_path": "/vol1/test.txt",
            "volume_name": "vol1",
            "svm_name": "svm1",
            "timestamp": "2026-01-15T10:30:00+09:00",
            "file_size": -1,
        }
        with pytest.raises(SchemaValidationError):
            validate_fpolicy_event(event, schema=FPOLICY_SCHEMA)

    def test_additional_properties_rejected(self) -> None:
        """未定義フィールドが拒否される."""
        event = {
            "event_id": "12345678-1234-4123-8123-123456789abc",
            "operation_type": "create",
            "file_path": "/vol1/test.txt",
            "volume_name": "vol1",
            "svm_name": "svm1",
            "timestamp": "2026-01-15T10:30:00+09:00",
            "file_size": 1024,
            "unknown_field": "should_fail",
        }
        with pytest.raises(SchemaValidationError):
            validate_fpolicy_event(event, schema=FPOLICY_SCHEMA)
