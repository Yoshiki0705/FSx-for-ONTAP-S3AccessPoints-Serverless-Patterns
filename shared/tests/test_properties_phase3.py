"""Property-Based Tests for shared modules — Phase 3

Hypothesis を使用したプロパティベーステスト。
Phase 3 で追加された共通モジュール（StreamingHelper, StreamingConfig）の
不変条件（invariants）を任意入力で検証する。

Testing Strategy:
- 最小 100 イテレーション/プロパティ
- 各テストにプロパティ番号タグを付与
- タグ形式: Feature: fsxn-s3ap-serverless-patterns-phase3, Property {number}: {property_text}
"""

from __future__ import annotations

from hypothesis import given, settings, strategies as st

from shared.streaming import StreamingConfig, StreamingHelper


# ---------------------------------------------------------------------------
# Property 1: StreamingConfig round-trip serialization
# ---------------------------------------------------------------------------

VALID_REGIONS = [
    "ap-northeast-1",
    "us-east-1",
    "us-west-2",
    "eu-west-1",
    "eu-central-1",
]


@settings(max_examples=100)
@given(
    stream_name=st.text(
        min_size=1,
        max_size=128,
        alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
    ),
    region=st.sampled_from(VALID_REGIONS),
    batch_size=st.integers(min_value=1, max_value=500),
    max_retries=st.integers(min_value=1, max_value=10),
)
def test_streaming_config_round_trip(stream_name, region, batch_size, max_retries):
    """Feature: fsxn-s3ap-serverless-patterns-phase3, Property 1: StreamingConfig round-trip serialization

    For any valid StreamingConfig object with arbitrary stream_name, region,
    batch_size (1-500), and max_retries (1-10) values, serializing via
    to_dict() then deserializing via from_dict() SHALL produce an equivalent
    configuration object.

    **Validates: Requirements 1.7**
    """
    config = StreamingConfig(
        stream_name=stream_name,
        region=region,
        batch_size=batch_size,
        max_retries=max_retries,
    )
    restored = StreamingConfig.from_dict(config.to_dict())
    assert restored.to_dict() == config.to_dict()


# ---------------------------------------------------------------------------
# Property 2: Record batching preserves total count and content
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    n_records=st.integers(min_value=0, max_value=1500),
    data=st.data(),
)
def test_record_batching_preserves_count_and_content(n_records, data):
    """Feature: fsxn-s3ap-serverless-patterns-phase3, Property 2: Record batching preserves total count and content

    For any list of records (varying sizes), batching SHALL preserve:
    1. The total number of records (sum of batch sizes == original list length)
    2. The content and order of records (flattened batches == original records)

    **Validates: Requirements 1.8**
    """
    # Generate records with varying data sizes
    records = []
    for i in range(n_records):
        # Use small data to keep test fast, but vary size
        data_size = data.draw(st.integers(min_value=1, max_value=200))
        record = {
            "Data": b"x" * data_size,
            "PartitionKey": f"pk-{i}",
        }
        records.append(record)

    batches = StreamingHelper._batch_records(records)

    # Property 1: sum of batch sizes == original list length
    total_in_batches = sum(len(batch) for batch in batches)
    assert total_in_batches == n_records, (
        f"Expected {n_records} records in batches, got {total_in_batches}"
    )

    # Property 2: flattened batches == original records (order preserved)
    flattened = [record for batch in batches for record in batch]
    assert flattened == records, "Flattened batches must equal original records"

    # Additional invariant: each batch respects the 500 record limit
    for batch in batches:
        assert len(batch) <= 500, (
            f"Batch exceeds 500 record limit: {len(batch)}"
        )


# ---------------------------------------------------------------------------
# Property 3: EMF JSON round-trip validity
# ---------------------------------------------------------------------------

import json
import os
from io import StringIO
from unittest.mock import patch

from shared.observability import EmfMetrics


# Strategy for valid metric names: ASCII alphanumeric + underscore, 1-256 chars
_METRIC_NAME_ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
valid_metric_names = st.text(
    min_size=1,
    max_size=256,
    alphabet=_METRIC_NAME_ALPHABET,
)

valid_metric_values = st.floats(
    min_value=-1e15,
    max_value=1e15,
    allow_nan=False,
    allow_infinity=False,
)

valid_units = st.sampled_from(["Count", "Milliseconds", "Bytes", "None"])


@settings(max_examples=100)
@given(
    metric_name=valid_metric_names,
    metric_value=valid_metric_values,
    unit=valid_units,
    namespace=st.text(min_size=1, max_size=64, alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_")),
)
def test_emf_json_round_trip_validity(metric_name, metric_value, unit, namespace):
    """Feature: fsxn-s3ap-serverless-patterns-phase3, Property 3: EMF JSON round-trip validity

    For all valid metric names and values, creating EmfMetrics, adding metrics,
    and flushing produces valid JSON that can be parsed back and contains the
    _aws block with correct structure (Timestamp, CloudWatchMetrics array).

    **Validates: Requirements 7.6, 10.7**
    """
    metrics = EmfMetrics(namespace=namespace, service="test-service")
    metrics.set_dimension("UseCase", "test-uc")
    metrics.put_metric(metric_name, metric_value, unit)

    # Capture stdout output from flush
    with patch("builtins.print") as mock_print:
        metrics.flush()

    # Verify print was called with valid JSON
    assert mock_print.called, "flush() must call print"
    output = mock_print.call_args[0][0]

    # Round-trip: parse JSON back
    parsed = json.loads(output)

    # Verify _aws block exists and has correct structure
    assert "_aws" in parsed, "EMF output must contain _aws block"
    aws_block = parsed["_aws"]
    assert "Timestamp" in aws_block, "_aws must contain Timestamp"
    assert isinstance(aws_block["Timestamp"], int), "Timestamp must be integer (epoch ms)"
    assert aws_block["Timestamp"] > 0, "Timestamp must be positive"

    assert "CloudWatchMetrics" in aws_block, "_aws must contain CloudWatchMetrics"
    cw_metrics = aws_block["CloudWatchMetrics"]
    assert isinstance(cw_metrics, list), "CloudWatchMetrics must be a list"
    assert len(cw_metrics) == 1, "CloudWatchMetrics must have exactly one entry"

    metric_def = cw_metrics[0]
    assert metric_def["Namespace"] == namespace
    assert "Dimensions" in metric_def
    assert "Metrics" in metric_def
    assert isinstance(metric_def["Dimensions"], list)
    assert isinstance(metric_def["Metrics"], list)

    # Verify metric value is present as top-level key
    assert metric_name in parsed, f"Metric '{metric_name}' must be a top-level key"
    assert parsed[metric_name] == metric_value


# ---------------------------------------------------------------------------
# Property 4: xray_subsegment no-op when disabled
# ---------------------------------------------------------------------------

from shared.observability import xray_subsegment


@settings(max_examples=100)
@given(
    name=st.text(min_size=1, max_size=128),
    annotations=st.dictionaries(
        keys=st.text(min_size=1, max_size=32, alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_")),
        values=st.text(min_size=0, max_size=64),
        max_size=5,
    ),
    metadata=st.dictionaries(
        keys=st.text(min_size=1, max_size=32, alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_")),
        values=st.text(min_size=0, max_size=64),
        max_size=5,
    ),
    return_value=st.integers(min_value=-1000, max_value=1000),
)
def test_xray_subsegment_noop_when_disabled(name, annotations, metadata, return_value):
    """Feature: fsxn-s3ap-serverless-patterns-phase3, Property 4: xray_subsegment no-op when disabled

    For all inputs (name, annotations, metadata), when ENABLE_XRAY=false,
    xray_subsegment operates as no-op without raising errors and the wrapped
    code executes normally, returning the expected value.

    **Validates: Requirements 6.6 (graceful degradation), 10.4**
    """
    with patch.dict(os.environ, {"ENABLE_XRAY": "false"}):
        result = None
        with xray_subsegment(name=name, annotations=annotations, metadata=metadata):
            result = return_value

        assert result == return_value, (
            f"Wrapped code must execute normally. Expected {return_value}, got {result}"
        )
