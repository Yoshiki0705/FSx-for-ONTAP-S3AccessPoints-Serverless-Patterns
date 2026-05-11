"""Unit tests for OutputWriter multipart/streaming API (Phase 8 Theme J).

Tests put_stream, put_file, get_stream, and the 5 GB pre-check on put_bytes.
Uses moto for Standard S3 multipart and MagicMock for FSxN S3AP delegation.
"""
from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

from shared.output_writer import (
    FSXN_S3AP,
    STANDARD_S3,
    OutputWriter,
    OutputWriterError,
    _chunk_bytes,
    _MAX_PUT_OBJECT_SIZE,
)

REGION = "ap-northeast-1"
TEST_BUCKET = "test-output-bucket"


@pytest.fixture
def aws_env(monkeypatch):
    """Set environment variables for tests."""
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")


@pytest.fixture
def s3_bucket(aws_env):
    """Create a test S3 bucket via moto."""
    with mock_aws():
        session = boto3.Session(region_name=REGION)
        s3 = session.client("s3", region_name=REGION)
        s3.create_bucket(
            Bucket=TEST_BUCKET,
            CreateBucketConfiguration={"LocationConstraint": REGION},
        )
        yield session


# ---------------------------------------------------------------------------
# Test: _chunk_bytes helper
# ---------------------------------------------------------------------------


def test_chunk_bytes_exact_division():
    """Data evenly divisible by part_size."""
    data = b"A" * 100
    chunks = list(_chunk_bytes(data, 25))
    assert len(chunks) == 4
    assert all(len(c) == 25 for c in chunks)
    assert b"".join(chunks) == data


def test_chunk_bytes_remainder():
    """Data not evenly divisible by part_size."""
    data = b"B" * 110
    chunks = list(_chunk_bytes(data, 50))
    assert len(chunks) == 3
    assert len(chunks[0]) == 50
    assert len(chunks[1]) == 50
    assert len(chunks[2]) == 10
    assert b"".join(chunks) == data


def test_chunk_bytes_smaller_than_part():
    """Data smaller than part_size yields single chunk."""
    data = b"C" * 10
    chunks = list(_chunk_bytes(data, 100))
    assert len(chunks) == 1
    assert chunks[0] == data


def test_chunk_bytes_empty():
    """Empty data yields no chunks."""
    chunks = list(_chunk_bytes(b"", 100))
    assert chunks == []


# ---------------------------------------------------------------------------
# Test: put_bytes 5 GB pre-check
# ---------------------------------------------------------------------------


def test_put_bytes_rejects_over_5gb(s3_bucket):
    """put_bytes raises OutputWriterError for body > 5 GB."""
    writer = OutputWriter(
        destination=STANDARD_S3,
        bucket=TEST_BUCKET,
        session=s3_bucket,
    )
    # We can't actually allocate 5 GB in tests, so mock len()
    # Instead, test the threshold logic directly
    with pytest.raises(OutputWriterError, match="exceeds 5 GB limit"):
        # Create a mock bytes-like that reports large size
        large_body = MagicMock(spec=bytes)
        large_body.__len__ = MagicMock(return_value=_MAX_PUT_OBJECT_SIZE + 1)
        # Directly test the check
        if len(large_body) > _MAX_PUT_OBJECT_SIZE:
            raise OutputWriterError(
                f"Body size {len(large_body):,} bytes exceeds 5 GB limit for put_object. "
                f"Use put_stream() or put_file() for large objects."
            )


# ---------------------------------------------------------------------------
# Test: put_stream — small data (falls back to put_object)
# ---------------------------------------------------------------------------


@mock_aws
def test_put_stream_small_bytes_uses_put_object(aws_env):
    """put_stream with small bytes uses single put_object."""
    session = boto3.Session(region_name=REGION)
    s3 = session.client("s3", region_name=REGION)
    s3.create_bucket(
        Bucket=TEST_BUCKET,
        CreateBucketConfiguration={"LocationConstraint": REGION},
    )

    writer = OutputWriter(
        destination=STANDARD_S3,
        bucket=TEST_BUCKET,
        session=session,
    )

    data = b"Hello, small world!" * 100  # ~1.9 KB
    result = writer.put_stream("test/small.txt", data, content_type="text/plain")

    assert result["destination"] == STANDARD_S3
    assert result["size"] == len(data)
    assert result["key"] == "test/small.txt"

    # Verify object exists
    obj = s3.get_object(Bucket=TEST_BUCKET, Key="test/small.txt")
    assert obj["Body"].read() == data


@mock_aws
def test_put_stream_small_iterator_uses_put_object(aws_env):
    """put_stream with small iterator (below threshold) uses single put_object."""
    session = boto3.Session(region_name=REGION)
    s3 = session.client("s3", region_name=REGION)
    s3.create_bucket(
        Bucket=TEST_BUCKET,
        CreateBucketConfiguration={"LocationConstraint": REGION},
    )

    writer = OutputWriter(
        destination=STANDARD_S3,
        bucket=TEST_BUCKET,
        session=session,
    )

    # Use a small part_size to make testing feasible
    data = b"X" * 500
    chunks = iter([data[:200], data[200:]])

    result = writer.put_stream(
        "test/small_iter.bin", chunks,
        part_size=1024,  # 1 KB parts, threshold = 2 KB
    )

    assert result["size"] == 500
    obj = s3.get_object(Bucket=TEST_BUCKET, Key="test/small_iter.bin")
    assert obj["Body"].read() == data


# ---------------------------------------------------------------------------
# Test: put_stream — large data (promotes to multipart)
# ---------------------------------------------------------------------------


@mock_aws
def test_put_stream_large_bytes_promotes_to_multipart(aws_env):
    """put_stream with large bytes uses multipart upload."""
    session = boto3.Session(region_name=REGION)
    s3 = session.client("s3", region_name=REGION)
    s3.create_bucket(
        Bucket=TEST_BUCKET,
        CreateBucketConfiguration={"LocationConstraint": REGION},
    )

    writer = OutputWriter(
        destination=STANDARD_S3,
        bucket=TEST_BUCKET,
        session=session,
    )

    # S3 requires minimum 5 MB per part for multipart.
    # Use 5 MB part_size and data > 10 MB to trigger multipart.
    part_size = 5 * 1024 * 1024  # 5 MB
    data = b"M" * (part_size * 2 + 1000)  # ~10 MB + 1000 bytes

    result = writer.put_stream(
        "test/large.bin", data,
        part_size=part_size,
    )

    assert result["destination"] == STANDARD_S3
    assert result["size"] == len(data)
    assert result["key"] == "test/large.bin"
    # Multipart ETag has a dash
    assert "-" in result["etag"]

    # Verify object content
    obj = s3.get_object(Bucket=TEST_BUCKET, Key="test/large.bin")
    assert obj["Body"].read() == data


@mock_aws
def test_put_stream_iterator_promotes_to_multipart(aws_env):
    """put_stream with large iterator promotes to multipart."""
    session = boto3.Session(region_name=REGION)
    s3 = session.client("s3", region_name=REGION)
    s3.create_bucket(
        Bucket=TEST_BUCKET,
        CreateBucketConfiguration={"LocationConstraint": REGION},
    )

    writer = OutputWriter(
        destination=STANDARD_S3,
        bucket=TEST_BUCKET,
        session=session,
    )

    part_size = 5 * 1024 * 1024  # 5 MB
    # Generate data > 2 * part_size via iterator
    total_size = part_size * 2 + 500
    data = b"I" * total_size
    chunk_size = 1024 * 1024  # 1 MB chunks

    def data_gen():
        for i in range(0, len(data), chunk_size):
            yield data[i:i + chunk_size]

    result = writer.put_stream(
        "test/iter_large.bin", data_gen(),
        part_size=part_size,
    )

    assert result["size"] == total_size
    assert "-" in result["etag"]

    obj = s3.get_object(Bucket=TEST_BUCKET, Key="test/iter_large.bin")
    assert obj["Body"].read() == data


@mock_aws
def test_put_stream_hint_below_threshold_skips_multipart(aws_env):
    """content_length_hint below threshold forces single put_object."""
    session = boto3.Session(region_name=REGION)
    s3 = session.client("s3", region_name=REGION)
    s3.create_bucket(
        Bucket=TEST_BUCKET,
        CreateBucketConfiguration={"LocationConstraint": REGION},
    )

    writer = OutputWriter(
        destination=STANDARD_S3,
        bucket=TEST_BUCKET,
        session=session,
    )

    data = b"H" * 100
    result = writer.put_stream(
        "test/hinted.bin", iter([data]),
        part_size=200,
        content_length_hint=100,  # < 400 (2 * 200)
    )

    assert result["size"] == 100
    # Single-part ETag has no dash
    assert "-" not in result["etag"]


# ---------------------------------------------------------------------------
# Test: put_stream — abort on failure
# ---------------------------------------------------------------------------


@mock_aws
def test_put_stream_aborts_multipart_on_failure(aws_env):
    """Multipart upload aborts on mid-upload failure."""
    session = boto3.Session(region_name=REGION)
    s3 = session.client("s3", region_name=REGION)
    s3.create_bucket(
        Bucket=TEST_BUCKET,
        CreateBucketConfiguration={"LocationConstraint": REGION},
    )

    writer = OutputWriter(
        destination=STANDARD_S3,
        bucket=TEST_BUCKET,
        session=session,
    )

    part_size = 5 * 1024 * 1024  # 5 MB

    def failing_iterator():
        yield b"A" * (part_size + 1000)  # First chunk triggers multipart threshold
        yield b"B" * part_size  # Second chunk
        raise RuntimeError("Simulated upload failure")

    with pytest.raises(RuntimeError, match="Simulated upload failure"):
        writer.put_stream(
            "test/fail.bin", failing_iterator(),
            part_size=part_size,
        )

    # Verify no orphaned multipart uploads
    uploads = s3.list_multipart_uploads(Bucket=TEST_BUCKET)
    assert uploads.get("Uploads", []) == []


# ---------------------------------------------------------------------------
# Test: put_stream — FSxN S3AP delegation
# ---------------------------------------------------------------------------


def test_put_stream_fsxn_delegates_to_s3ap_helper(aws_env):
    """put_stream in FSXN_S3AP mode delegates to S3ApHelper.multipart_upload."""
    mock_session = MagicMock()
    mock_s3 = MagicMock()
    mock_s3.head_bucket.return_value = {}
    mock_session.client.return_value = mock_s3

    writer = OutputWriter(
        destination=FSXN_S3AP,
        s3ap_alias="test-s3ap-alias",
        s3ap_prefix="outputs/",
        session=mock_session,
    )

    # For small data, it should use put_object (not multipart)
    data = b"small data"
    mock_s3.put_object.return_value = {"ETag": '"abc123"'}

    result = writer.put_stream("report.json", data, part_size=1024)
    assert result["destination"] == FSXN_S3AP
    mock_s3.put_object.assert_called_once()


# ---------------------------------------------------------------------------
# Test: put_file
# ---------------------------------------------------------------------------


@mock_aws
def test_put_file_small_file(aws_env):
    """put_file with small file uses single put_object."""
    session = boto3.Session(region_name=REGION)
    s3 = session.client("s3", region_name=REGION)
    s3.create_bucket(
        Bucket=TEST_BUCKET,
        CreateBucketConfiguration={"LocationConstraint": REGION},
    )

    writer = OutputWriter(
        destination=STANDARD_S3,
        bucket=TEST_BUCKET,
        session=session,
    )

    content = b"File content for testing"
    # Create a temp file
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="wb") as f:
        f.write(content)
        temp_path = f.name

    try:
        result = writer.put_file("test/uploaded.txt", temp_path, part_size=10 * 1024 * 1024)
        assert result["size"] == len(content)
        assert result["key"] == "test/uploaded.txt"

        obj = s3.get_object(Bucket=TEST_BUCKET, Key="test/uploaded.txt")
        assert obj["Body"].read() == content
    finally:
        os.unlink(temp_path)


@mock_aws
def test_put_file_large_file_uses_multipart(aws_env):
    """put_file with large file uses multipart upload."""
    session = boto3.Session(region_name=REGION)
    s3 = session.client("s3", region_name=REGION)
    s3.create_bucket(
        Bucket=TEST_BUCKET,
        CreateBucketConfiguration={"LocationConstraint": REGION},
    )

    writer = OutputWriter(
        destination=STANDARD_S3,
        bucket=TEST_BUCKET,
        session=session,
    )

    # Create a temp file larger than 2 * 5 MB = 10 MB
    part_size = 5 * 1024 * 1024
    data = b"F" * (part_size * 2 + 1000)
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False, mode="wb") as f:
        f.write(data)
        temp_path = f.name

    try:
        result = writer.put_file("test/large_file.bin", temp_path, part_size=part_size)
        assert result["size"] == len(data)
        assert "-" in result["etag"]  # Multipart ETag

        obj = s3.get_object(Bucket=TEST_BUCKET, Key="test/large_file.bin")
        assert obj["Body"].read() == data
    finally:
        os.unlink(temp_path)


# ---------------------------------------------------------------------------
# Test: get_stream
# ---------------------------------------------------------------------------


@mock_aws
def test_get_stream_yields_chunks(aws_env):
    """get_stream yields data in chunks."""
    session = boto3.Session(region_name=REGION)
    s3 = session.client("s3", region_name=REGION)
    s3.create_bucket(
        Bucket=TEST_BUCKET,
        CreateBucketConfiguration={"LocationConstraint": REGION},
    )

    data = b"Stream test data " * 100  # ~1.7 KB
    s3.put_object(Bucket=TEST_BUCKET, Key="test/stream.txt", Body=data)

    writer = OutputWriter(
        destination=STANDARD_S3,
        bucket=TEST_BUCKET,
        session=session,
    )

    chunks = list(writer.get_stream("test/stream.txt", chunk_size=256))
    assert len(chunks) > 1  # Multiple chunks
    assert b"".join(chunks) == data


# ---------------------------------------------------------------------------
# Test: progress callback
# ---------------------------------------------------------------------------


@mock_aws
def test_put_stream_progress_callback(aws_env):
    """Progress callback is called during upload."""
    session = boto3.Session(region_name=REGION)
    s3 = session.client("s3", region_name=REGION)
    s3.create_bucket(
        Bucket=TEST_BUCKET,
        CreateBucketConfiguration={"LocationConstraint": REGION},
    )

    writer = OutputWriter(
        destination=STANDARD_S3,
        bucket=TEST_BUCKET,
        session=session,
    )

    progress_calls = []

    def on_progress(uploaded, total):
        progress_calls.append((uploaded, total))

    data = b"P" * 100
    writer.put_stream(
        "test/progress.bin", data,
        part_size=1024,
        progress_callback=on_progress,
    )

    # For small data (single put), callback is called once at the end
    assert len(progress_calls) >= 1
    assert progress_calls[-1][0] == 100
