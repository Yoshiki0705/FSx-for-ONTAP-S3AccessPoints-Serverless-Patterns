"""Property-Based Tests for LineageRecord v2 — Hypothesis

Properties 6, 7, 8: Round-trip, backward compatibility, SHA-256 validation.
"""

from __future__ import annotations

import re
import string

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from moto import mock_aws

from shared.lineage import (
    LineageRecord,
    LineageTracker,
    validate_checksum,
    validate_guardrail_mode,
    validate_retention_profile,
)

# --- Strategies ---

sha256_hex = st.text(
    alphabet=string.hexdigits[:16],  # 0-9a-f only
    min_size=64,
    max_size=64,
)

valid_checksum = st.one_of(st.just(""), sha256_hex)

valid_guardrail_mode = st.sampled_from(["", "DRY_RUN", "ENFORCE", "BREAK_GLASS"])

valid_retention_profile = st.sampled_from(
    ["", "standard-365d", "compliance-7y", "custom"]
)

valid_lineage_record_v2 = st.builds(
    LineageRecord,
    source_file_key=st.text(min_size=1, max_size=100).map(lambda s: f"/vol1/{s}"),
    processing_timestamp=st.text(min_size=20, max_size=30).map(
        lambda _: "2026-05-19T10:00:00.000Z"
    ),
    step_functions_execution_arn=st.just("arn:aws:states:ap-northeast-1:123:execution:test:run1"),
    uc_id=st.sampled_from(["legal-compliance", "financial-idp", "media-vfx"]),
    output_keys=st.lists(st.text(min_size=5, max_size=50), min_size=0, max_size=3),
    status=st.sampled_from(["success", "failed", "partial"]),
    duration_ms=st.integers(min_value=0, max_value=300000),
    metadata=st.none(),
    input_checksum=valid_checksum,
    output_checksum=valid_checksum,
    fpolicy_sequence_number=st.integers(min_value=0, max_value=999999),
    policy_version=st.text(min_size=0, max_size=20),
    uc_template_version=st.text(min_size=0, max_size=40),
    guardrail_mode=valid_guardrail_mode,
    retention_profile=valid_retention_profile,
)


# --- Property 6: LineageRecord v2 Round-Trip ---


class TestLineageV2RoundTrip:
    """Property 6: Writing and reading a v2 record preserves all fields."""

    @given(record=valid_lineage_record_v2)
    @settings(max_examples=50, deadline=None)
    def test_round_trip_preserves_v2_fields(self, record: LineageRecord):
        """Any valid v2 record written and read back preserves all fields."""
        import boto3

        with mock_aws():
            # Create DynamoDB table
            dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-1")
            table = dynamodb.create_table(
                TableName="test-lineage-rt",
                KeySchema=[
                    {"AttributeName": "source_file_key", "KeyType": "HASH"},
                    {"AttributeName": "processing_timestamp", "KeyType": "RANGE"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "source_file_key", "AttributeType": "S"},
                    {"AttributeName": "processing_timestamp", "AttributeType": "S"},
                ],
                BillingMode="PAY_PER_REQUEST",
            )

            tracker = LineageTracker(table_name="test-lineage-rt", dynamodb_resource=dynamodb)
            tracker.record(record)

            # Read back
            history = tracker.get_history(record.source_file_key)
            assert len(history) == 1

            result = history[0]
            assert result.input_checksum == record.input_checksum
            assert result.output_checksum == record.output_checksum
            assert result.fpolicy_sequence_number == record.fpolicy_sequence_number
            assert result.policy_version == record.policy_version
            assert result.uc_template_version == record.uc_template_version
            assert result.guardrail_mode == record.guardrail_mode
            assert result.retention_profile == record.retention_profile


# --- Property 7: Backward Compatibility ---


class TestLineageV2BackwardCompatibility:
    """Property 7: v1 records read with v2-aware code return defaults."""

    @given(
        source_key=st.text(min_size=1, max_size=50).map(lambda s: f"/vol1/{s}"),
        uc_id=st.sampled_from(["legal-compliance", "financial-idp"]),
    )
    @settings(max_examples=20, deadline=None)
    def test_v1_record_returns_v2_defaults(self, source_key: str, uc_id: str):
        """v1 records without v2 fields return default values."""
        import boto3

        with mock_aws():
            dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-1")
            dynamodb.create_table(
                TableName="test-lineage-compat",
                KeySchema=[
                    {"AttributeName": "source_file_key", "KeyType": "HASH"},
                    {"AttributeName": "processing_timestamp", "KeyType": "RANGE"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "source_file_key", "AttributeType": "S"},
                    {"AttributeName": "processing_timestamp", "AttributeType": "S"},
                ],
                BillingMode="PAY_PER_REQUEST",
            )

            # Write a v1 record directly (no v2 fields)
            table = dynamodb.Table("test-lineage-compat")
            table.put_item(
                Item={
                    "source_file_key": source_key,
                    "processing_timestamp": "2026-05-19T10:00:00.000Z",
                    "step_functions_execution_arn": "arn:aws:states:test",
                    "uc_id": uc_id,
                    "output_keys": ["s3://out/file.json"],
                    "status": "success",
                    "duration_ms": 1000,
                }
            )

            tracker = LineageTracker(
                table_name="test-lineage-compat", dynamodb_resource=dynamodb
            )
            history = tracker.get_history(source_key)
            assert len(history) == 1

            result = history[0]
            # v2 fields should have defaults
            assert result.input_checksum == ""
            assert result.output_checksum == ""
            assert result.fpolicy_sequence_number == 0
            assert result.policy_version == ""
            assert result.uc_template_version == ""
            assert result.guardrail_mode == ""
            assert result.retention_profile == ""
            # v1 fields preserved
            assert result.source_file_key == source_key
            assert result.uc_id == uc_id
            assert result.status == "success"


# --- Property 8: SHA-256 Checksum Validation ---


class TestSHA256Validation:
    """Property 8: Validator accepts empty or 64-char lowercase hex only."""

    @given(value=sha256_hex)
    @settings(max_examples=100)
    def test_valid_sha256_accepted(self, value: str):
        """64-char lowercase hex strings are accepted."""
        assert validate_checksum(value) is True

    def test_empty_string_accepted(self):
        """Empty string is accepted."""
        assert validate_checksum("") is True

    @given(
        value=st.text(min_size=1, max_size=100).filter(
            lambda s: s != "" and not re.match(r"^[0-9a-f]{64}$", s)
        )
    )
    @settings(max_examples=100)
    def test_invalid_strings_rejected(self, value: str):
        """Non-empty strings that aren't 64-char lowercase hex are rejected."""
        assert validate_checksum(value) is False

    @given(value=st.text(alphabet="ABCDEF0123456789", min_size=64, max_size=64))
    @settings(max_examples=50)
    def test_uppercase_hex_rejected(self, value: str):
        """Uppercase hex strings are rejected (must be lowercase)."""
        if any(c in value for c in "ABCDEF"):
            assert validate_checksum(value) is False

    @given(length=st.integers(min_value=1, max_value=100).filter(lambda n: n != 64))
    @settings(max_examples=50)
    def test_wrong_length_rejected(self, length: int):
        """Hex strings of wrong length are rejected."""
        value = "a" * length
        assert validate_checksum(value) is False
