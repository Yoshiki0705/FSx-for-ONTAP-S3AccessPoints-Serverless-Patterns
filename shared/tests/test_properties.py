"""Property-Based Tests for shared modules

Hypothesis を使用したプロパティベーステスト。
共通モジュールの不変条件（invariants）を任意入力で検証する。

Testing Strategy:
- 最小 100 イテレーション/プロパティ
- 各テストにプロパティ番号タグを付与
- タグ形式: Feature: fsxn-s3ap-serverless-patterns, Property {number}: {property_text}
"""

from __future__ import annotations

from hypothesis import given, settings, strategies as st

from shared.ontap_client import OntapClientConfig


@settings(max_examples=100)
@given(
    management_ip=st.from_regex(
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", fullmatch=True
    ),
    secret_name=st.text(
        min_size=1,
        max_size=100,
        alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    ),
    verify_ssl=st.booleans(),
    ca_cert_path=st.one_of(
        st.none(),
        st.text(
            min_size=1,
            max_size=200,
            alphabet=st.characters(whitelist_categories=("L", "N", "P")),
        ),
    ),
    connect_timeout=st.floats(
        min_value=1.0, max_value=60.0, allow_nan=False, allow_infinity=False
    ),
    read_timeout=st.floats(
        min_value=1.0, max_value=120.0, allow_nan=False, allow_infinity=False
    ),
    retry_total=st.integers(min_value=0, max_value=10),
    backoff_factor=st.floats(
        min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False
    ),
)
def test_config_round_trip(
    management_ip,
    secret_name,
    verify_ssl,
    ca_cert_path,
    connect_timeout,
    read_timeout,
    retry_total,
    backoff_factor,
):
    """Feature: fsxn-s3ap-serverless-patterns, Property 1: OntapClient configuration round-trip

    For any valid OntapClientConfig object with arbitrary management_ip,
    secret_name, verify_ssl, ca_cert_path, connect_timeout, read_timeout,
    retry_total, and backoff_factor values, serializing via to_dict() then
    deserializing via from_dict() SHALL produce an equivalent configuration
    object.

    **Validates: Requirements 2.11**
    """
    config = OntapClientConfig(
        management_ip=management_ip,
        secret_name=secret_name,
        verify_ssl=verify_ssl,
        ca_cert_path=ca_cert_path,
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        retry_total=retry_total,
        backoff_factor=backoff_factor,
    )
    restored = OntapClientConfig.from_dict(config.to_dict())
    assert restored.to_dict() == config.to_dict()


# ---------------------------------------------------------------------------
# Property 3: FsxHelper exception wrapping preserves original error
# ---------------------------------------------------------------------------

from unittest.mock import MagicMock

from botocore.exceptions import ClientError

from shared.fsx_helper import FsxHelper, FsxHelperError


@settings(max_examples=100)
@given(
    error_code=st.sampled_from(
        [
            "FileSystemNotFound",
            "VolumeNotFound",
            "InternalServerError",
            "ServiceLimitExceeded",
        ]
    ),
    error_message=st.text(
        min_size=1,
        max_size=200,
        alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    ),
)
def test_fsx_helper_exception_wrapping_preserves_original(error_code, error_message):
    """Feature: fsxn-s3ap-serverless-patterns, Property 3: FsxHelper exception wrapping preserves original error

    For any boto3 ClientError raised during an FSx API call, the resulting
    FsxHelperError SHALL have an original_error attribute that is the same
    exception instance as the original boto3 error.

    **Validates: Requirements 3.4**
    """
    original = ClientError(
        {"Error": {"Code": error_code, "Message": error_message}},
        "DescribeFileSystems",
    )

    # Mock the FSx client to raise this error
    mock_session = MagicMock()
    mock_fsx_client = MagicMock()
    mock_cw_client = MagicMock()

    def client_factory(service_name, **kwargs):
        if service_name == "fsx":
            return mock_fsx_client
        elif service_name == "cloudwatch":
            return mock_cw_client
        return MagicMock()

    mock_session.client.side_effect = client_factory

    paginator = MagicMock()
    paginator.paginate.side_effect = original
    mock_fsx_client.get_paginator.return_value = paginator

    helper = FsxHelper(session=mock_session)

    try:
        helper.describe_file_systems()
        # Should not reach here
        assert False, "Expected FsxHelperError to be raised"
    except FsxHelperError as e:
        # Verify the original_error is the exact same instance
        assert e.original_error is original
        # Verify the error message contains useful context
        assert "Failed to describe file systems" in str(e)


# ---------------------------------------------------------------------------
# Property 4: S3ApHelper accepts valid Alias and ARN formats
# ---------------------------------------------------------------------------

from shared.s3ap_helper import S3ApHelper


@settings(max_examples=100)
@given(
    alias=st.from_regex(r"[a-z0-9-]+-ext-s3alias", fullmatch=True),
)
def test_s3ap_helper_alias_acceptance(alias):
    """Feature: fsxn-s3ap-serverless-patterns, Property 4: S3ApHelper accepts valid Alias and ARN formats (Alias)

    For any valid S3 Access Point Alias (matching pattern ^[a-z0-9-]+-ext-s3alias$),
    the S3ApHelper SHALL initialize successfully and use the value as the Bucket
    parameter in S3 API calls.

    **Validates: Requirements 4.1**
    """
    mock_session = MagicMock()
    mock_session.client.return_value = MagicMock()

    helper = S3ApHelper(alias, session=mock_session)

    assert helper.bucket_param == alias


@settings(max_examples=100)
@given(
    region=st.from_regex(r"[a-z]{2}-[a-z]+-\d", fullmatch=True),
    account_id=st.from_regex(r"\d{12}", fullmatch=True),
    ap_name=st.text(
        min_size=1,
        max_size=50,
        alphabet=st.characters(
            whitelist_categories=("Ll", "Nd"),
            whitelist_characters="-",
        ),
    ),
)
def test_s3ap_helper_arn_acceptance(region, account_id, ap_name):
    """Feature: fsxn-s3ap-serverless-patterns, Property 4: S3ApHelper accepts valid Alias and ARN formats (ARN)

    For any valid S3 Access Point ARN (matching pattern
    ^arn:aws:s3:[a-z0-9-]+:\\d{12}:accesspoint/.+$), the S3ApHelper SHALL
    initialize successfully and use the value as the Bucket parameter in S3 API calls.

    **Validates: Requirements 4.1**
    """
    arn = f"arn:aws:s3:{region}:{account_id}:accesspoint/{ap_name}"

    mock_session = MagicMock()
    mock_session.client.return_value = MagicMock()

    helper = S3ApHelper(arn, session=mock_session)

    assert helper.bucket_param == arn


# ---------------------------------------------------------------------------
# Property 5: S3ApHelper pagination collects all objects
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    n_objects=st.integers(min_value=0, max_value=100),
)
def test_s3ap_helper_pagination_completeness(n_objects):
    """Feature: fsxn-s3ap-serverless-patterns, Property 5: S3ApHelper pagination collects all objects

    For any set of N objects (0 to 100), list_objects SHALL return exactly N objects
    regardless of the page size or number of pagination rounds required.

    **Validates: Requirements 4.2**
    """
    from datetime import datetime

    # Build object list
    all_objects = [
        {
            "Key": f"obj-{i:04d}.dat",
            "Size": i * 10,
            "LastModified": datetime(2026, 1, 15),
            "ETag": f'"etag-{i}"',
        }
        for i in range(n_objects)
    ]

    # Simulate pagination with page_size=10
    page_size = 10
    pages: list[dict] = []
    for start in range(0, max(n_objects, 1), page_size):
        chunk = all_objects[start : start + page_size]
        is_truncated = (start + page_size) < n_objects
        page: dict = {
            "Contents": chunk,
            "IsTruncated": is_truncated,
        }
        if is_truncated:
            page["NextContinuationToken"] = f"token-{start + page_size}"
        pages.append(page)

    # Handle n_objects == 0: single empty page
    if n_objects == 0:
        pages = [{"Contents": [], "IsTruncated": False}]

    mock_session = MagicMock()
    mock_s3_client = MagicMock()
    mock_session.client.return_value = mock_s3_client
    mock_s3_client.list_objects_v2.side_effect = pages

    helper = S3ApHelper("test-ext-s3alias", session=mock_session)
    result = helper.list_objects()

    assert len(result) == n_objects


# ---------------------------------------------------------------------------
# Property 6: S3ApHelper prefix and suffix filtering
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    prefix=st.text(
        min_size=0,
        max_size=10,
        alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="/"),
    ),
    suffix=st.sampled_from(["", ".csv", ".json", ".txt", ".parquet"]),
    n_matching=st.integers(min_value=0, max_value=20),
    n_non_matching=st.integers(min_value=0, max_value=20),
)
def test_s3ap_helper_prefix_suffix_filtering(prefix, suffix, n_matching, n_non_matching):
    """Feature: fsxn-s3ap-serverless-patterns, Property 6: S3ApHelper prefix and suffix filtering

    For any prefix P and suffix S, list_objects(prefix=P, suffix=S) returns only
    objects matching both the prefix and suffix criteria, and returns ALL such
    matching objects.

    **Validates: Requirements 4.3, 4.7**
    """
    from datetime import datetime

    # Build matching objects (prefix is handled server-side, suffix client-side)
    matching = [
        {
            "Key": f"{prefix}match-{i}{suffix}",
            "Size": 100,
            "LastModified": datetime(2026, 1, 15),
            "ETag": f'"m-{i}"',
        }
        for i in range(n_matching)
    ]

    # Build non-matching objects (have the prefix but wrong suffix)
    non_suffix = ".NOMATCH" if suffix else ""
    non_matching = [
        {
            "Key": f"{prefix}nomatch-{i}{non_suffix}",
            "Size": 100,
            "LastModified": datetime(2026, 1, 15),
            "ETag": f'"n-{i}"',
        }
        for i in range(n_non_matching)
    ]

    # S3 API returns all objects with the prefix (server-side prefix filter)
    all_contents = matching + non_matching

    mock_session = MagicMock()
    mock_s3_client = MagicMock()
    mock_session.client.return_value = mock_s3_client
    mock_s3_client.list_objects_v2.return_value = {
        "Contents": all_contents,
        "IsTruncated": False,
    }

    helper = S3ApHelper("test-ext-s3alias", session=mock_session)
    result = helper.list_objects(prefix=prefix, suffix=suffix)

    # All returned objects must match both prefix and suffix
    for obj in result:
        assert obj["Key"].startswith(prefix)
        if suffix:
            assert obj["Key"].endswith(suffix)

    # All matching objects must be returned
    if suffix:
        assert len(result) == n_matching
    else:
        # When suffix is empty, all objects match
        assert len(result) == n_matching + n_non_matching


# ---------------------------------------------------------------------------
# Property 7: S3ApHelper list-then-get consistency
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    n_objects=st.integers(min_value=1, max_value=20),
)
def test_s3ap_helper_list_then_get_consistency(n_objects):
    """Feature: fsxn-s3ap-serverless-patterns, Property 7: S3ApHelper list-then-get consistency

    For any object in list_objects result, get_object(key) returns valid content
    with a non-empty Body.

    **Validates: Requirements 4.8**
    """
    from datetime import datetime
    from io import BytesIO

    # Build object list
    objects = [
        {
            "Key": f"data/file-{i}.dat",
            "Size": (i + 1) * 100,
            "LastModified": datetime(2026, 1, 15),
            "ETag": f'"etag-{i}"',
        }
        for i in range(n_objects)
    ]

    mock_session = MagicMock()
    mock_s3_client = MagicMock()
    mock_session.client.return_value = mock_s3_client

    # Mock list_objects_v2
    mock_s3_client.list_objects_v2.return_value = {
        "Contents": objects,
        "IsTruncated": False,
    }

    # Mock get_object to return valid content for any key
    def mock_get_object(Bucket, Key):
        body = BytesIO(f"content-of-{Key}".encode())
        return {
            "Body": body,
            "ContentLength": len(f"content-of-{Key}"),
            "ContentType": "application/octet-stream",
        }

    mock_s3_client.get_object.side_effect = mock_get_object

    helper = S3ApHelper("test-ext-s3alias", session=mock_session)

    # List objects
    listed = helper.list_objects()
    assert len(listed) == n_objects

    # For each listed object, get_object should return valid content
    for obj in listed:
        response = helper.get_object(obj["Key"])
        assert response["Body"] is not None
        assert response["ContentLength"] > 0


# ---------------------------------------------------------------------------
# Property 2: OntapClient error propagation for non-2xx responses
# ---------------------------------------------------------------------------

import pytest

from shared.ontap_client import OntapClient, OntapClientConfig, OntapClientError


@settings(max_examples=100)
@given(
    status_code=st.sampled_from([400, 401, 403, 404, 409, 500, 502, 503]),
    response_body=st.text(
        min_size=0,
        max_size=500,
        alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    ),
)
def test_ontap_client_non_2xx_error_propagation(status_code, response_body):
    """Feature: fsxn-s3ap-serverless-patterns, Property 2: OntapClient error propagation for non-2xx responses

    For any HTTP response with a non-2xx status code (4xx or 5xx) and any
    response body, the OntapClient SHALL raise an OntapClientError whose
    status_code attribute equals the HTTP status code and whose response_body
    attribute equals the response body content.

    **Validates: Requirements 2.7, 2.10**
    """
    # Build a mock urllib3 response
    mock_response = MagicMock()
    mock_response.status = status_code
    mock_response.data = response_body.encode("utf-8")

    # Build a mock pool that returns the mock response
    mock_pool = MagicMock()
    mock_pool.request.return_value = mock_response

    # Build a mock Secrets Manager that returns valid credentials
    mock_session = MagicMock()
    mock_sm_client = MagicMock()
    mock_sm_client.get_secret_value.return_value = {
        "SecretString": '{"username": "admin", "password": "secret"}'
    }
    mock_session.client.return_value = mock_sm_client

    config = OntapClientConfig(
        management_ip="10.0.0.1",
        secret_name="test-secret",
    )
    client = OntapClient(config, session=mock_session)

    # Inject the mocked pool directly
    client._pool = mock_pool

    with pytest.raises(OntapClientError) as exc_info:
        client.get("/test")

    assert exc_info.value.status_code == status_code
    assert exc_info.value.response_body == response_body


# ---------------------------------------------------------------------------
# Property 15: Lambda error handler produces structured response
# ---------------------------------------------------------------------------

import json as _json

from shared.exceptions import lambda_error_handler


@settings(max_examples=100)
@given(
    error_message=st.text(
        min_size=1,
        max_size=200,
        alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    ),
    error_type=st.sampled_from([ValueError, TypeError, RuntimeError, KeyError, IOError]),
    request_id=st.uuids().map(str),
)
def test_lambda_error_handler_structured_response(error_message, error_type, request_id):
    """Feature: fsxn-s3ap-serverless-patterns, Property 15: Lambda error handler produces structured response

    For any unhandled exception raised within a Lambda function handler, the
    error handling wrapper SHALL log the full stack trace and return a response
    with statusCode >= 500 and a JSON body containing error and request_id fields.

    **Validates: Requirements 13.5**
    """

    @lambda_error_handler
    def failing_handler(event, context):
        raise error_type(error_message)

    # Create a mock Lambda context with aws_request_id
    mock_context = MagicMock()
    mock_context.aws_request_id = request_id

    response = failing_handler({}, mock_context)

    # Assert statusCode >= 500
    assert response["statusCode"] >= 500

    # Assert body is valid JSON containing required fields
    body = _json.loads(response["body"])
    assert "error" in body
    assert "request_id" in body
    assert body["request_id"] == request_id
    # KeyError wraps its argument in quotes via __str__ and may repr() non-ASCII chars.
    # We verify the error field is non-empty rather than exact containment.
    assert len(body["error"]) > 0


# ---------------------------------------------------------------------------
# Property 8: Discovery Lambda generates valid Manifest
# ---------------------------------------------------------------------------

from shared.discovery_handler import generate_manifest


@settings(max_examples=100)
@given(
    n_objects=st.integers(min_value=0, max_value=100),
    execution_id=st.uuids().map(str),
)
def test_discovery_manifest_validity(n_objects, execution_id):
    """Feature: fsxn-s3ap-serverless-patterns, Property 8: Discovery Lambda generates valid Manifest

    For any list of discovered S3 objects (0 to 100), the Discovery Lambda
    SHALL produce a Manifest JSON containing all required fields
    (execution_id, timestamp, total_objects, objects) where total_objects
    equals the length of the objects array.

    **Validates: Requirements 7.3**
    """
    from datetime import datetime

    # Generate a list of mock S3 objects
    objects = [
        {
            "Key": f"data/file-{i:04d}.dat",
            "Size": i * 100,
            "LastModified": datetime(2026, 1, 15).isoformat(),
            "ETag": f'"etag-{i}"',
        }
        for i in range(n_objects)
    ]

    manifest = generate_manifest(objects, execution_id)

    # Required fields must be present
    assert "execution_id" in manifest
    assert "timestamp" in manifest
    assert "total_objects" in manifest
    assert "objects" in manifest

    # execution_id must match the input
    assert manifest["execution_id"] == execution_id

    # timestamp must be a valid ISO 8601 string
    datetime.fromisoformat(manifest["timestamp"])

    # total_objects must equal the length of the objects array
    assert manifest["total_objects"] == len(manifest["objects"])
    assert manifest["total_objects"] == n_objects

    # All input objects must be present in the manifest
    for i, obj in enumerate(manifest["objects"]):
        assert obj["Key"] == objects[i]["Key"]
        assert obj["Size"] == objects[i]["Size"]


# ---------------------------------------------------------------------------
# Property 9: ACL Collection writes valid JSON Lines with date partitioning
# ---------------------------------------------------------------------------

import importlib.util as _importlib_util
import re as _re
from datetime import datetime as _datetime

# legal-compliance ディレクトリはハイフンを含むため importlib で読み込む
_acl_spec = _importlib_util.spec_from_file_location(
    "acl_collection_handler",
    str(
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "legal-compliance"
        / "functions"
        / "acl_collection"
        / "handler.py"
    ),
)
_acl_module = _importlib_util.module_from_spec(_acl_spec)
_acl_spec.loader.exec_module(_acl_module)
format_acl_record = _acl_module.format_acl_record
build_s3_key = _acl_module.build_s3_key


@settings(max_examples=100)
@given(
    object_key=st.text(
        min_size=1,
        max_size=200,
        alphabet=st.characters(whitelist_categories=("L", "N", "P"), whitelist_characters="/"),
    ),
    volume_uuid=st.uuids().map(str),
    security_style=st.sampled_from(["ntfs", "unix", "mixed"]),
    n_acls=st.integers(min_value=0, max_value=10),
)
def test_acl_collection_json_lines_and_date_partition(
    object_key, volume_uuid, security_style, n_acls
):
    """Feature: fsxn-s3ap-serverless-patterns, Property 9: ACL Collection writes valid JSON Lines with date partitioning

    For any ACL data collected for an object, the output SHALL be a valid
    JSON Lines record (one JSON object per line) and the S3 key path SHALL
    contain a date partition in the format YYYY/MM/DD.

    **Validates: Requirements 7.5**
    """
    # Generate ACL entries
    acls = [
        {
            "sid": f"S-1-5-21-{i}",
            "type": "ALLOWED" if i % 2 == 0 else "DENIED",
            "permissions": "FULL" if i % 3 == 0 else "READ",
        }
        for i in range(n_acls)
    ]

    # Test format_acl_record produces valid JSON
    record_line = format_acl_record(
        object_key=object_key,
        volume_uuid=volume_uuid,
        security_style=security_style,
        acls=acls,
    )

    # Must be valid JSON (single line)
    parsed = _json.loads(record_line)
    assert "\n" not in record_line, "JSON Lines record must be a single line"

    # Must contain required fields
    assert parsed["object_key"] == object_key
    assert parsed["volume_uuid"] == volume_uuid
    assert parsed["security_style"] == security_style
    assert isinstance(parsed["acls"], list)
    assert len(parsed["acls"]) == n_acls
    assert "collected_at" in parsed

    # collected_at must be a valid ISO 8601 timestamp
    _datetime.fromisoformat(parsed["collected_at"])

    # Test build_s3_key produces a path with YYYY/MM/DD date partition
    execution_id = str(volume_uuid)  # reuse as a unique ID
    s3_key = build_s3_key(execution_id)

    # S3 key must contain a date partition in YYYY/MM/DD format
    date_pattern = _re.compile(r"\d{4}/\d{2}/\d{2}")
    assert date_pattern.search(s3_key), (
        f"S3 key must contain date partition YYYY/MM/DD, got: {s3_key}"
    )

    # S3 key must end with .jsonl extension
    assert s3_key.endswith(".jsonl"), (
        f"S3 key must end with .jsonl extension, got: {s3_key}"
    )


# ---------------------------------------------------------------------------
# Property 10: OCR Lambda selects correct Textract API based on page count
# ---------------------------------------------------------------------------

import importlib.util as _ocr_importlib_util

# financial-idp ディレクトリはハイフンを含むため importlib で読み込む
_ocr_spec = _ocr_importlib_util.spec_from_file_location(
    "ocr_handler",
    str(
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "financial-idp"
        / "functions"
        / "ocr"
        / "handler.py"
    ),
)
_ocr_module = _ocr_importlib_util.module_from_spec(_ocr_spec)
_ocr_spec.loader.exec_module(_ocr_module)
select_textract_api = _ocr_module.select_textract_api


@settings(max_examples=100)
@given(
    page_count=st.integers(min_value=1, max_value=1000),
    threshold=st.integers(min_value=1, max_value=100),
)
def test_ocr_textract_api_selection(page_count, threshold):
    """Feature: fsxn-s3ap-serverless-patterns, Property 10: OCR Lambda selects correct Textract API based on page count

    For any page count and threshold, if page_count <= threshold the OCR Lambda
    SHALL use AnalyzeDocument (sync). If page_count exceeds the threshold, it
    SHALL use StartDocumentAnalysis (async).

    **Validates: Requirements 8.3**
    """
    result = select_textract_api(page_count, threshold)

    if page_count <= threshold:
        assert result == "sync", (
            f"Expected 'sync' for page_count={page_count} <= threshold={threshold}, "
            f"got '{result}'"
        )
    else:
        assert result == "async", (
            f"Expected 'async' for page_count={page_count} > threshold={threshold}, "
            f"got '{result}'"
        )


# ---------------------------------------------------------------------------
# Property 11: Summary Lambda structured output completeness
# ---------------------------------------------------------------------------

_summary_spec = _ocr_importlib_util.spec_from_file_location(
    "summary_handler",
    str(
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "financial-idp"
        / "functions"
        / "summary"
        / "handler.py"
    ),
)
_summary_module = _ocr_importlib_util.module_from_spec(_summary_spec)
_summary_spec.loader.exec_module(_summary_module)
build_summary_output = _summary_module.build_summary_output


@settings(max_examples=100)
@given(
    extracted_text=st.text(
        min_size=0,
        max_size=500,
        alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    ),
    entities=st.fixed_dictionaries({
        "dates": st.lists(st.text(min_size=1, max_size=20), max_size=5),
        "amounts": st.lists(st.text(min_size=1, max_size=20), max_size=5),
        "organizations": st.lists(st.text(min_size=1, max_size=20), max_size=5),
        "persons": st.lists(st.text(min_size=1, max_size=20), max_size=5),
    }),
    summary_text=st.text(
        min_size=0,
        max_size=500,
        alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    ),
    document_key=st.text(
        min_size=1,
        max_size=200,
        alphabet=st.characters(whitelist_categories=("L", "N", "P"), whitelist_characters="/"),
    ),
)
def test_summary_structured_output_completeness(
    extracted_text, entities, summary_text, document_key
):
    """Feature: fsxn-s3ap-serverless-patterns, Property 11: Summary Lambda structured output completeness

    For any extracted_text, entities, summary_text, and document_key, the output
    JSON SHALL contain all required fields: extracted_text, entities, summary,
    document_key, and processed_at.

    **Validates: Requirements 8.6**
    """
    output = build_summary_output(
        extracted_text=extracted_text,
        entities=entities,
        summary_text=summary_text,
        document_key=document_key,
    )

    # All required fields must be present
    required_fields = {"extracted_text", "entities", "summary", "document_key", "processed_at"}
    assert required_fields.issubset(output.keys()), (
        f"Missing fields: {required_fields - output.keys()}"
    )

    # Field values must match inputs
    assert output["extracted_text"] == extracted_text
    assert output["entities"] == entities
    assert output["summary"] == summary_text
    assert output["document_key"] == document_key

    # processed_at must be a valid ISO 8601 timestamp
    _datetime.fromisoformat(output["processed_at"])


# ---------------------------------------------------------------------------
# Property 12: CSV to Parquet transformation preserves data
# ---------------------------------------------------------------------------

import importlib.util as _transform_importlib_util
import io as _io

# manufacturing-analytics ディレクトリはハイフンを含むため importlib で読み込む
_transform_spec = _transform_importlib_util.spec_from_file_location(
    "transform_handler",
    str(
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "manufacturing-analytics"
        / "functions"
        / "transform"
        / "handler.py"
    ),
)
_transform_module = _transform_importlib_util.module_from_spec(_transform_spec)
_transform_spec.loader.exec_module(_transform_module)
csv_to_jsonlines = _transform_module.csv_to_jsonlines


@settings(max_examples=100, deadline=None)
@given(
    n_rows=st.integers(min_value=1, max_value=50),
    n_cols=st.integers(min_value=1, max_value=10),
    data=st.data(),
)
def test_csv_to_parquet_preserves_data(n_rows, n_cols, data):
    """Feature: fsxn-s3ap-serverless-patterns, Property 12: CSV to JSON Lines transformation preserves data

    For any valid CSV with arbitrary rows and columns, converting to JSON Lines
    and reading back SHALL produce a dataset with the same number of rows,
    same column names, and equivalent cell values.

    **Validates: Requirements 9.2**
    """
    import json as _json

    col_names = [f"col_{i}" for i in range(n_cols)]
    header = ",".join(col_names)

    rows = []
    for _ in range(n_rows):
        row_values = []
        for _ in range(n_cols):
            val = data.draw(st.integers(min_value=-999999, max_value=999999))
            row_values.append(str(val))
        rows.append(",".join(row_values))

    csv_text = header + "\n" + "\n".join(rows) + "\n"
    csv_bytes = csv_text.encode("utf-8")

    jsonlines_str, record_count = csv_to_jsonlines(csv_bytes)

    assert record_count == n_rows, (
        f"Expected {n_rows} records, got {record_count}"
    )

    parsed_lines = [_json.loads(line) for line in jsonlines_str.strip().split("\n")]
    assert len(parsed_lines) == n_rows

    for col_name in col_names:
        assert col_name in parsed_lines[0], (
            f"Column {col_name} not found in JSON output"
        )

    for row_idx in range(n_rows):
        for col_idx, col_name in enumerate(col_names):
            original_val = float(rows[row_idx].split(",")[col_idx])
            assert parsed_lines[row_idx][col_name] == original_val, (
                f"Mismatch at row={row_idx}, col={col_name}: "
                f"expected {original_val}, got {parsed_lines[row_idx][col_name]}"
            )


# ---------------------------------------------------------------------------
# Property 13: Image analysis threshold flagging
# ---------------------------------------------------------------------------

_image_analysis_spec = _transform_importlib_util.spec_from_file_location(
    "image_analysis_handler",
    str(
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "manufacturing-analytics"
        / "functions"
        / "image_analysis"
        / "handler.py"
    ),
)
_image_analysis_module = _transform_importlib_util.module_from_spec(_image_analysis_spec)
_image_analysis_spec.loader.exec_module(_image_analysis_module)
should_flag_for_review = _image_analysis_module.should_flag_for_review


@settings(max_examples=100)
@given(
    confidence=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    threshold=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
)
def test_image_threshold_flagging(confidence, threshold):
    """Feature: fsxn-s3ap-serverless-patterns, Property 13: Image analysis threshold flagging

    For any confidence score and threshold, if confidence < threshold the image
    SHALL be flagged for manual review (True). If confidence >= threshold the
    image SHALL NOT be flagged (False).

    **Validates: Requirements 9.6**
    """
    result = should_flag_for_review(confidence, threshold)

    if confidence < threshold:
        assert result is True, (
            f"Expected flagged=True for confidence={confidence} < threshold={threshold}, "
            f"got {result}"
        )
    else:
        assert result is False, (
            f"Expected flagged=False for confidence={confidence} >= threshold={threshold}, "
            f"got {result}"
        )


# ---------------------------------------------------------------------------
# Property 14: DICOM anonymization removes PII
# ---------------------------------------------------------------------------

import importlib.util as _anon_importlib_util

# healthcare-dicom ディレクトリはハイフンを含むため importlib で読み込む
_anon_spec = _anon_importlib_util.spec_from_file_location(
    "anonymization_handler",
    str(
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "healthcare-dicom"
        / "functions"
        / "anonymization"
        / "handler.py"
    ),
)
_anon_module = _anon_importlib_util.module_from_spec(_anon_spec)
_anon_spec.loader.exec_module(_anon_module)
redact_phi_fields = _anon_module.redact_phi_fields


@settings(max_examples=100)
@given(
    patient_name=st.text(
        min_size=1,
        max_size=50,
        alphabet=st.characters(whitelist_categories=("L", "Z")),
    ),
    patient_id=st.text(
        min_size=1,
        max_size=20,
        alphabet=st.characters(whitelist_categories=("L", "N")),
    ),
    patient_birth_date=st.text(
        min_size=1,
        max_size=10,
        alphabet=st.characters(whitelist_categories=("N",), whitelist_characters="-"),
    ),
    modality=st.sampled_from(["CT", "MR", "US", "XR", "CR", "MG", "NM", "PT", "DX", "OT"]),
    body_part=st.sampled_from([
        "CHEST", "HEAD", "ABDOMEN", "SPINE", "PELVIS",
        "EXTREMITY", "KNEE", "SHOULDER", "UNKNOWN",
    ]),
    n_phi_entities=st.integers(min_value=0, max_value=5),
)
def test_dicom_anonymization_removes_pii(
    patient_name, patient_id, patient_birth_date,
    modality, body_part, n_phi_entities,
):
    """Feature: fsxn-s3ap-serverless-patterns, Property 14: DICOM anonymization removes PII

    For any DICOM metadata containing patient_name, patient_id, or other
    PHI fields, after anonymization the output metadata SHALL NOT contain
    the original PHI values, and SHALL contain classification metadata
    (modality, body_part).

    **Validates: Requirements 11.6**
    """
    # 入力メタデータを構築（PHI フィールドを含む）
    metadata = {
        "patient_name": patient_name,
        "patient_id": patient_id,
        "patient_birth_date": patient_birth_date,
        "modality": modality,
        "body_part": body_part,
        "study_date": "2026-01-15",
    }

    # Comprehend Medical が検出する PHI エンティティを模擬
    phi_entities = [
        {
            "Text": patient_name,
            "Type": "NAME",
            "Score": 0.99,
        }
    ]
    # 追加の PHI エンティティを生成
    for i in range(n_phi_entities):
        phi_entities.append({
            "Text": f"phi-entity-{i}",
            "Type": "ID",
            "Score": 0.95,
        })

    # 匿名化を実行
    result = redact_phi_fields(metadata, phi_entities)

    # PHI フィールドの元の値が結果に含まれないこと
    for key, value in result.items():
        if key in ("modality", "body_part", "study_date", "classification"):
            continue
        # 元の PHI 値がそのまま残っていないことを検証
        assert value != patient_name, (
            f"Original patient_name '{patient_name}' found in field '{key}'"
        )
        assert value != patient_id, (
            f"Original patient_id '{patient_id}' found in field '{key}'"
        )
        assert value != patient_birth_date, (
            f"Original patient_birth_date '{patient_birth_date}' found in field '{key}'"
        )

    # modality と body_part は保持されること
    assert result.get("modality") == modality, (
        f"Expected modality '{modality}', got '{result.get('modality')}'"
    )
    assert result.get("body_part") == body_part, (
        f"Expected body_part '{body_part}', got '{result.get('body_part')}'"
    )
