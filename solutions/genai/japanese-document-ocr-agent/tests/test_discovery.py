"""Unit tests for the discovery handler (input validation, allow-list, routing)."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from unittest.mock import patch

import boto3
import pytest
from helpers import load_handler
from hypothesis import given, settings
from hypothesis import strategies as st
from moto import mock_aws

from shared.exceptions import InvalidConfiguration, InvalidInput

BUCKET = "demo-bucket"
COLLECTIONS = {
    "invoices": {
        "prefix": "scans/invoices/",
        "profile": "structure",
        "classification": "RESTRICTED",
        "fields": ["請求書番号", "合計金額"],
    },
    "memos": {"prefix": "scans/memos/", "suffixes": [".PNG", "jpg"]},
}
ENV = {
    "S3_ACCESS_POINT_ALIAS": BUCKET,
    "COLLECTIONS_JSON": json.dumps(COLLECTIONS, ensure_ascii=False),
    "DEFAULT_PROFILE": "text",
    "MAX_FILES": "50",
    "MAX_DOCUMENT_BYTES": str(50 * 1024 * 1024),
    "MAP_CONCURRENCY": "2",
    "DATA_CLASSIFICATION": "INTERNAL",
    "ENABLE_FIELD_EXTRACTION": "false",
    "AWS_DEFAULT_REGION": "ap-northeast-1",
}
mod = load_handler("discovery")


def _event(request: object, execution: str = "exec-1") -> dict:
    return {"request": request, "execution_name": execution}


@pytest.fixture
def bucket():
    with mock_aws():
        s3 = boto3.client("s3", region_name="ap-northeast-1")
        s3.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"})
        yield s3


def _put(s3, key: str, size: int = 10) -> None:
    s3.put_object(Bucket=BUCKET, Key=key, Body=b"x" * size)


# ---------------------------------------------------------------------------
# validate_request
# ---------------------------------------------------------------------------


class TestValidateRequest:
    def test_minimal(self):
        assert mod.validate_request({"collection": "invoices"}, 50) == {
            "collection": "invoices",
            "profile": None,
            "max_files": None,
            "modified_after": None,
        }

    def test_all_fields(self):
        request = {"collection": "a-1_b", "profile": "text", "max_files": 5, "modified_after": "2026-10-01"}
        assert mod.validate_request(request, 50) == request

    @pytest.mark.parametrize("request_value", [None, [], "invoices", 1, True])
    def test_must_be_an_object(self, request_value):
        with pytest.raises(InvalidInput, match="JSON object"):
            mod.validate_request(request_value, 50)

    def test_unknown_keys_are_rejected_and_named(self):
        with pytest.raises(InvalidInput, match="unknown field.*prefix.*allowed"):
            mod.validate_request({"collection": "invoices", "prefix": "../secret/"}, 50)

    @pytest.mark.parametrize(
        "collection",
        [None, "", 1, "請求書", "../etc", "a/b", " invoices", "-bad", "x" * 33, "inv oices"],
    )
    def test_collection_must_be_an_ascii_id(self, collection):
        with pytest.raises(InvalidInput, match="collection"):
            mod.validate_request({"collection": collection}, 50)

    def test_collection_is_required(self):
        with pytest.raises(InvalidInput, match="collection"):
            mod.validate_request({}, 50)

    @pytest.mark.parametrize("profile", ["forms", "queries", "TEXT", "", 1])
    def test_profile_is_limited_to_the_supported_ones(self, profile):
        with pytest.raises(InvalidInput, match="profile"):
            mod.validate_request({"collection": "a", "profile": profile}, 50)

    @pytest.mark.parametrize("max_files", [0, -1, 51, "5", 1.5, True, False])
    def test_max_files_bounds_and_type(self, max_files):
        with pytest.raises(InvalidInput, match="max_files"):
            mod.validate_request({"collection": "a", "max_files": max_files}, 50)

    @pytest.mark.parametrize("value", ["2026-13-01", "2026-02-30", "2026/10/01", "20261001", 20261001, "2026-10-1"])
    def test_modified_after_must_be_a_real_date(self, value):
        with pytest.raises(InvalidInput, match="modified_after"):
            mod.validate_request({"collection": "a", "modified_after": value}, 50)

    @given(
        request=st.dictionaries(
            st.sampled_from(["collection", "profile", "max_files", "modified_after", "x", "prefix", "key"]),
            st.one_of(st.none(), st.booleans(), st.integers(-5, 99), st.text(max_size=12), st.lists(st.integers())),
            max_size=5,
        )
    )
    @settings(deadline=None, max_examples=300)
    def test_property_only_valid_inputs_pass_and_nothing_else_is_raised(self, request):
        try:
            result = mod.validate_request(request, 50)
        except InvalidInput:
            return
        assert set(request) <= mod.ALLOWED_INPUT_KEYS
        assert mod.COLLECTION_ID.match(result["collection"])
        assert result["profile"] in (None, "text", "structure")
        assert result["max_files"] is None or 1 <= result["max_files"] <= 50


# ---------------------------------------------------------------------------
# parse_collections
# ---------------------------------------------------------------------------


class TestParseCollections:
    def test_suffixes_are_normalized(self):
        parsed = mod.parse_collections(json.dumps(COLLECTIONS, ensure_ascii=False))
        assert parsed["memos"]["suffixes"] == [".png", ".jpg"]
        assert ".pdf" in parsed["invoices"]["suffixes"]
        assert parsed["invoices"]["fields"] == ["請求書番号", "合計金額"]

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "not json",
            "[]",
            "{}",
            '{"a": 1}',
            '{"請求書": {"prefix": "x/"}}',
            '{"a": {"prefix": ""}}',
            '{"a": {"prefix": "/abs/"}}',
            '{"a": {}}',
            '{"a": {"prefix": "x/", "suffixes": []}}',
            '{"a": {"prefix": "x/", "profile": "forms"}}',
            '{"a": {"prefix": "x/", "classification": "SECRET"}}',
            '{"a": {"prefix": "x/", "fields": "total"}}',
            '{"a": {"prefix": "x/", "unknown": 1}}',
        ],
    )
    def test_invalid_configuration_is_rejected(self, raw):
        with pytest.raises(InvalidConfiguration):
            mod.parse_collections(raw)

    def test_ascii_escaped_json_restores_the_japanese_field_names(self):
        """CloudFormation replaces every non-ASCII character in a parameter value with '?' (checked on a
        live account), so the deploy script sends the allow-list as \\uXXXX escapes. The handler must turn
        them back into the original names, byte for byte."""
        escaped = json.dumps(COLLECTIONS, ensure_ascii=True, separators=(",", ":"))
        assert escaped.isascii()
        assert "請求書番号" not in escaped
        parsed = mod.parse_collections(escaped)
        assert parsed["invoices"]["fields"] == ["請求書番号", "合計金額"]

    def test_a_question_mark_field_name_is_not_silently_accepted_as_a_real_name(self):
        """What the allow-list looks like if the characters were already replaced before the handler saw
        them. It parses (a name is a name), which is why the deploy script verifies the stored value."""
        raw = json.dumps({"a": {"prefix": "x/", "fields": ["?????"]}})
        assert mod.parse_collections(raw)["a"]["fields"] == ["?????"]

    def test_too_many_fields(self):
        raw = json.dumps({"a": {"prefix": "x/", "fields": [f"f{i}" for i in range(21)]}})
        with pytest.raises(InvalidConfiguration, match="fields"):
            mod.parse_collections(raw)

    def test_field_name_length_limit(self):
        raw = json.dumps({"a": {"prefix": "x/", "fields": ["あ" * 41]}}, ensure_ascii=False)
        with pytest.raises(InvalidConfiguration, match="fields"):
            mod.parse_collections(raw)


# ---------------------------------------------------------------------------
# route_object
# ---------------------------------------------------------------------------

ALL = list(mod.DEFAULT_SUFFIXES)
LIMIT = 50 * 1024 * 1024


class TestRouteObject:
    @pytest.mark.parametrize("key", ["a.png", "a.JPG", "dir/日本語.jpeg"])
    def test_small_images_use_the_sync_api(self, key):
        assert mod.route_object(key, 1000, ALL, LIMIT) == ("sync", None)

    @pytest.mark.parametrize("key", ["a.pdf", "a.PDF", "scan.tif", "scan.tiff", "請求書.pdf"])
    def test_pdf_and_tiff_always_use_the_async_api(self, key):
        assert mod.route_object(key, 1000, ALL, LIMIT) == ("async", None)

    def test_image_over_the_inline_limit_goes_async(self):
        assert mod.route_object("a.png", mod.SYNC_INLINE_LIMIT, ALL, LIMIT)[0] == "sync"
        assert mod.route_object("a.png", mod.SYNC_INLINE_LIMIT + 1, ALL, LIMIT)[0] == "async"
        assert mod.route_object("a.png", mod.ASYNC_IMAGE_LIMIT, ALL, LIMIT)[0] == "async"

    def test_image_over_the_async_image_limit_is_skipped(self):
        assert mod.route_object("a.png", mod.ASYNC_IMAGE_LIMIT + 1, ALL, LIMIT) == ("skip", "image_too_large")

    @pytest.mark.parametrize("key", ["a.txt", "a.docx", "a.gif", "a.heic", "noext", "a.pdf.bak"])
    def test_other_extensions_are_skipped(self, key):
        assert mod.route_object(key, 1000, ALL, LIMIT) == ("skip", "unsupported_extension")

    def test_extension_must_be_allowed_by_the_collection(self):
        assert mod.route_object("a.pdf", 1000, [".png"], LIMIT) == ("skip", "unsupported_extension")

    def test_empty_and_oversized_documents_are_skipped_with_a_reason(self):
        assert mod.route_object("a.pdf", 0, ALL, LIMIT) == ("skip", "empty")
        assert mod.route_object("a.pdf", LIMIT + 1, ALL, LIMIT) == ("skip", "too_large")
        assert mod.route_object("a.pdf", LIMIT, ALL, LIMIT)[0] == "async"

    @given(key=st.text(max_size=40), size=st.integers(-5, 2**31))
    @settings(deadline=None, max_examples=300)
    def test_property_route_is_always_one_of_three_and_skip_has_a_reason(self, key, size):
        route, reason = mod.route_object(key, size, ALL, LIMIT)
        assert route in {"sync", "async", "skip"}
        assert (reason is not None) == (route == "skip")


def test_doc_id_is_stable_short_and_ascii():
    first = mod.doc_id_for("請求書/2026-10/株式会社サンプル.pdf")
    assert first == mod.doc_id_for("請求書/2026-10/株式会社サンプル.pdf")
    assert first != mod.doc_id_for("請求書/2026-10/株式会社サンプル2.pdf")
    assert len(first) == 16 and first.isascii()


# ---------------------------------------------------------------------------
# handler
# ---------------------------------------------------------------------------


class TestHandler:
    @patch.dict(os.environ, ENV)
    def test_resolves_the_collection_and_routes_documents(self, bucket):
        _put(bucket, "scans/invoices/b.pdf")
        _put(bucket, "scans/invoices/a.png")
        _put(bucket, "scans/invoices/notes.txt")
        _put(bucket, "scans/invoices/日本語の請求書.jpg")
        _put(bucket, "scans/memos/other.png")
        result = mod.handler(_event({"collection": "invoices"}), None)

        assert result["collection"] == "invoices"
        assert result["profile"] == "structure"  # the collection's setting
        assert result["classification"] == "RESTRICTED"
        assert result["output_prefix"] == "invoices/exec-1"
        assert result["object_count"] == 3
        assert [o["key"] for o in result["objects"]] == sorted(o["key"] for o in result["objects"])
        assert {o["route"] for o in result["objects"]} == {"sync", "async"}
        assert all(o["doc_id"].isascii() for o in result["objects"])
        assert result["skipped"] == [{"key": "scans/invoices/notes.txt", "reason": "unsupported_extension"}]
        assert result["skipped_count"] == 1
        assert result["map_concurrency"] == 2
        assert not any("memos" in o["key"] for o in result["objects"])  # the prefix is the boundary

    @patch.dict(os.environ, ENV)
    def test_request_profile_overrides_the_collection(self, bucket):
        _put(bucket, "scans/invoices/a.png")
        result = mod.handler(_event({"collection": "invoices", "profile": "text"}), None)
        assert result["profile"] == "text"

    @patch.dict(os.environ, ENV)
    def test_falls_back_to_the_default_profile_and_classification(self, bucket):
        _put(bucket, "scans/memos/a.png")
        result = mod.handler(_event({"collection": "memos"}), None)
        assert result["profile"] == "text"
        assert result["classification"] == "INTERNAL"

    @patch.dict(os.environ, ENV)
    def test_max_files_truncates_deterministically(self, bucket):
        for name in "dcba":
            _put(bucket, f"scans/memos/{name}.png")
        result = mod.handler(_event({"collection": "memos", "max_files": 2}), None)
        assert [o["key"] for o in result["objects"]] == ["scans/memos/a.png", "scans/memos/b.png"]
        assert result["truncated"] is True

    @patch.dict(os.environ, ENV)
    def test_modified_after_filters_by_last_modified(self, bucket):
        _put(bucket, "scans/memos/a.png")  # moto stamps it with the current time
        future = datetime(2999, 1, 1, tzinfo=UTC).strftime("%Y-%m-%d")
        assert mod.handler(_event({"collection": "memos", "modified_after": future}), None)["object_count"] == 0
        assert mod.handler(_event({"collection": "memos", "modified_after": "2000-01-01"}), None)["object_count"] == 1

    @patch.dict(os.environ, ENV)
    def test_skipped_list_is_bounded_but_counted(self, bucket):
        for i in range(mod.MAX_SKIPPED_LISTED + 7):
            _put(bucket, f"scans/memos/f{i:03d}.txt")
        result = mod.handler(_event({"collection": "memos"}), None)
        assert result["skipped_count"] == mod.MAX_SKIPPED_LISTED + 7
        assert len(result["skipped"]) == mod.MAX_SKIPPED_LISTED

    @patch.dict(os.environ, ENV)
    def test_folder_placeholders_are_ignored(self, bucket):
        bucket.put_object(Bucket=BUCKET, Key="scans/memos/sub/", Body=b"")
        assert mod.handler(_event({"collection": "memos"}), None)["skipped_count"] == 0

    @patch.dict(os.environ, ENV)
    def test_no_documents_returns_an_empty_manifest(self, bucket):
        result = mod.handler(_event({"collection": "memos"}), None)
        assert result["object_count"] == 0
        assert result["objects"] == []

    @patch.dict(os.environ, ENV)
    def test_unknown_collection_names_the_available_ones(self, bucket):
        with pytest.raises(InvalidInput, match="available: invoices, memos"):
            mod.handler(_event({"collection": "contracts"}), None)

    @patch.dict(os.environ, ENV)
    def test_a_path_is_not_a_collection(self, bucket):
        with pytest.raises(InvalidInput):
            mod.handler(_event({"collection": "scans/invoices/"}), None)

    @patch.dict(os.environ, {**ENV, "COLLECTIONS_JSON": "oops"})
    def test_broken_configuration_is_reported_as_configuration(self, bucket):
        with pytest.raises(InvalidConfiguration):
            mod.handler(_event({"collection": "invoices"}), None)

    @patch.dict(os.environ, {**ENV, "ENABLE_FIELD_EXTRACTION": "true"})
    def test_field_extraction_needs_both_the_switch_and_fields(self, bucket):
        assert mod.handler(_event({"collection": "invoices"}), None)["extract_fields"] is True
        assert mod.handler(_event({"collection": "memos"}), None)["extract_fields"] is False

    @patch.dict(os.environ, ENV)
    def test_field_extraction_is_off_by_default(self, bucket):
        assert mod.handler(_event({"collection": "invoices"}), None)["extract_fields"] is False

    @patch.dict(os.environ, {**ENV, "MAX_FILES": "3"})
    def test_stack_cap_bounds_the_request(self, bucket):
        with pytest.raises(InvalidInput, match="max_files"):
            mod.handler(_event({"collection": "memos", "max_files": 4}), None)
        for i in range(5):
            _put(bucket, f"scans/memos/{i}.png")
        assert mod.handler(_event({"collection": "memos"}), None)["object_count"] == 3

    @patch.dict(os.environ, {**ENV, "MAX_DOCUMENT_BYTES": "100"})
    def test_oversized_documents_are_skipped(self, bucket):
        _put(bucket, "scans/memos/big.pdf", size=101)
        _put(bucket, "scans/memos/ok.pdf", size=100)
        result = mod.handler(_event({"collection": "memos"}), None)
        assert [o["key"] for o in result["objects"]] == []  # memos allows only png/jpg
        _put(bucket, "scans/memos/big.png", size=101)
        result = mod.handler(_event({"collection": "memos"}), None)
        assert {"key": "scans/memos/big.png", "reason": "too_large"} in result["skipped"]
