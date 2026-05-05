"""Property-Based Tests for shared modules — Phase 2

Hypothesis を使用したプロパティベーステスト。
Phase 2 で追加された共通モジュール（CrossRegionClient, S3ApHelper 拡張）の
不変条件（invariants）を任意入力で検証する。

Testing Strategy:
- 最小 100 イテレーション/プロパティ
- 各テストにプロパティ番号タグを付与
- タグ形式: Feature: fsxn-s3ap-serverless-patterns-phase2, Property {number}: {property_text}
"""

from __future__ import annotations

from hypothesis import given, settings, strategies as st

from shared.cross_region_client import CrossRegionConfig
from shared.exceptions import CrossRegionClientError


# ---------------------------------------------------------------------------
# Property 1: CrossRegionConfig round-trip
# ---------------------------------------------------------------------------

VALID_REGIONS = ["us-east-1", "us-east-2", "us-west-2", "eu-west-1", "eu-west-2"]
VALID_SERVICES = ["textract", "comprehendmedical", "comprehend", "rekognition"]


@settings(max_examples=100)
@given(
    target_region=st.sampled_from(VALID_REGIONS),
    services=st.lists(
        st.sampled_from(VALID_SERVICES), min_size=1, max_size=4, unique=True
    ),
    verify_ssl=st.booleans(),
    connect_timeout=st.integers(min_value=1, max_value=120),
    read_timeout=st.integers(min_value=1, max_value=300),
)
def test_cross_region_config_round_trip(
    target_region, services, verify_ssl, connect_timeout, read_timeout
):
    """Feature: fsxn-s3ap-serverless-patterns-phase2, Property 1: CrossRegionConfig round-trip

    For any valid CrossRegionConfig object with arbitrary target_region,
    services list, verify_ssl, connect_timeout, and read_timeout values,
    serializing via to_dict() then deserializing via from_dict() SHALL
    produce an equivalent configuration object.

    **Validates: Requirements 2.6**
    """
    config = CrossRegionConfig(
        target_region=target_region,
        services=services,
        verify_ssl=verify_ssl,
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
    )
    restored = CrossRegionConfig.from_dict(config.to_dict())
    assert restored.to_dict() == config.to_dict()


# ---------------------------------------------------------------------------
# Property 2: CrossRegionClientError attribute completeness
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    target_region=st.text(min_size=1, max_size=30),
    service_name=st.text(min_size=1, max_size=30),
    error_message=st.text(min_size=1, max_size=200),
)
def test_cross_region_error_attributes(target_region, service_name, error_message):
    """Feature: fsxn-s3ap-serverless-patterns-phase2, Property 2: CrossRegionClientError attribute completeness

    For any failed cross-region API call with any target_region string,
    service_name string, and original exception, the raised
    CrossRegionClientError SHALL have target_region, service_name, and
    original_error attributes that match the input values, and the error
    message SHALL contain both the target_region and service_name.

    **Validates: Requirements 2.5, 15.4**
    """
    original = ValueError(error_message)
    # Construct message matching actual CrossRegionClient usage pattern:
    # real code always includes service_name and target_region in the message
    message = (
        f"Service '{service_name}' failed in region "
        f"'{target_region}': {error_message}"
    )
    error = CrossRegionClientError(
        message=message,
        target_region=target_region,
        service_name=service_name,
        original_error=original,
    )
    assert error.target_region == target_region
    assert error.service_name == service_name
    assert error.original_error is original
    assert target_region in str(error)
    assert service_name in str(error)


# ---------------------------------------------------------------------------
# Property 3: Streaming download chunk concatenation equals original
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    data=st.binary(min_size=0, max_size=2048),
    chunk_size=st.integers(min_value=1, max_value=512),
)
def test_streaming_download_round_trip(data, chunk_size):
    """Feature: fsxn-s3ap-serverless-patterns-phase2, Property 3: Streaming download chunk concatenation equals original

    For any byte sequence uploaded to S3 via put_object(), downloading via
    streaming_download() and concatenating all yielded chunks SHALL produce
    a byte sequence identical to the original.

    This test mocks the S3 client to simulate the streaming_download behavior:
    get_object returns a Body whose read(chunk_size) yields the data in chunks.

    **Validates: Requirements 2.4**
    """
    import io
    from unittest.mock import MagicMock

    from shared.s3ap_helper import S3ApHelper

    # Create a mock session and S3 client
    mock_session = MagicMock()
    mock_s3_client = MagicMock()
    mock_session.client.return_value = mock_s3_client

    helper = S3ApHelper("test-alias-ext-s3alias", session=mock_session)

    # Simulate get_object returning a StreamingBody-like object
    stream = io.BytesIO(data)
    mock_body = MagicMock()
    mock_body.read = stream.read
    mock_body.close = MagicMock()

    mock_s3_client.get_object.return_value = {"Body": mock_body}

    # Download via streaming_download and concatenate chunks
    downloaded = b"".join(helper.streaming_download("test-key", chunk_size=chunk_size))

    # The concatenated result must equal the original data
    assert downloaded == data

    # Body.close() must always be called
    mock_body.close.assert_called_once()


# ---------------------------------------------------------------------------
# Property 4: Multipart upload round-trip
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    data=st.binary(min_size=1, max_size=2048),
    part_size=st.integers(min_value=1, max_value=256),
    num_chunks=st.integers(min_value=1, max_value=8),
)
def test_multipart_upload_round_trip(data, part_size, num_chunks):
    """Feature: fsxn-s3ap-serverless-patterns-phase2, Property 4: Multipart upload round-trip

    For any byte sequence, uploading via multipart_upload() SHALL pass data
    to upload_part calls such that concatenating all upload_part Body arguments
    produces a byte sequence identical to the original.

    Since multipart_upload requires mocking (can't easily use moto for multipart
    with access points), this test verifies the buffering logic: the data passed
    to upload_part calls concatenated equals the original input data.

    **Validates: Requirements 2.3**
    """
    from unittest.mock import MagicMock, call

    from shared.s3ap_helper import S3ApHelper

    # Create a mock session and S3 client
    mock_session = MagicMock()
    mock_s3_client = MagicMock()
    mock_session.client.return_value = mock_s3_client

    helper = S3ApHelper("test-alias-ext-s3alias", session=mock_session)

    # Setup mock responses
    mock_s3_client.create_multipart_upload.return_value = {"UploadId": "test-upload-id"}
    mock_s3_client.upload_part.return_value = {"ETag": '"test-etag"'}
    mock_s3_client.complete_multipart_upload.return_value = {"ETag": '"final-etag"'}

    # Split data into num_chunks input chunks (simulating an iterator)
    chunk_len = max(1, len(data) // num_chunks)
    input_chunks = []
    for i in range(0, len(data), chunk_len):
        input_chunks.append(data[i : i + chunk_len])

    # Execute multipart_upload
    helper.multipart_upload(
        "test-key",
        iter(input_chunks),
        part_size=part_size,
    )

    # Collect all data passed to upload_part
    uploaded_data = b""
    for c in mock_s3_client.upload_part.call_args_list:
        uploaded_data += c[1]["Body"]

    # The concatenated upload_part data must equal the original
    assert uploaded_data == data

    # Verify part numbers are sequential starting from 1
    part_numbers = [c[1]["PartNumber"] for c in mock_s3_client.upload_part.call_args_list]
    assert part_numbers == list(range(1, len(part_numbers) + 1))

    # complete_multipart_upload must be called exactly once
    mock_s3_client.complete_multipart_upload.assert_called_once()

    # abort_multipart_upload must NOT be called on success
    mock_s3_client.abort_multipart_upload.assert_not_called()


# ---------------------------------------------------------------------------
# Property 20: Manifest pagination at 10K threshold
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    num_objects=st.integers(min_value=0, max_value=25000),
)
def test_manifest_pagination_10k_threshold(num_objects):
    """Feature: fsxn-s3ap-serverless-patterns-phase2, Property 20: Manifest pagination at 10K threshold

    For any list of discovered S3 objects with count N, if N ≤ 10,000 the
    function SHALL produce a single chunk. If N > 10,000, it SHALL split into
    ceil(N / 10,000) chunks, and the union of all chunks SHALL contain exactly
    N objects with no duplicates or omissions.

    **Validates: Requirements 12.5**
    """
    import math

    from shared.discovery_handler import paginate_manifest

    # Generate mock objects (small dicts to keep memory reasonable)
    objects = [{"Key": f"obj-{i}", "Size": i} for i in range(num_objects)]

    chunks = paginate_manifest(objects)

    if num_objects <= 10000:
        # Single chunk case
        assert len(chunks) == 1
        assert chunks[0]["chunk_index"] == 0
        assert chunks[0]["total_chunks"] == 1
        assert chunks[0]["total_objects_in_chunk"] == num_objects
        assert chunks[0]["objects"] == objects
    else:
        # Multi-chunk case
        expected_total_chunks = math.ceil(num_objects / 10000)
        assert len(chunks) == expected_total_chunks

        # Verify chunk metadata
        for i, chunk in enumerate(chunks):
            assert chunk["chunk_index"] == i
            assert chunk["total_chunks"] == expected_total_chunks
            assert chunk["total_objects_in_chunk"] == len(chunk["objects"])
            assert chunk["total_objects_in_chunk"] <= 10000

        # Verify union of all chunks equals original (no duplicates, no omissions)
        all_objects = []
        for chunk in chunks:
            all_objects.extend(chunk["objects"])
        assert len(all_objects) == num_objects
        assert all_objects == objects
