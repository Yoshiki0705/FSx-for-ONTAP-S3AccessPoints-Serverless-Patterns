"""The state the Map leaves behind must fit in 256 KiB.

After the Map, Step Functions holds the agent's request, discovery's whole output (`objects` and
`skipped`, which carry every key) and one result per document (`processed`, which carries every key
again). Truncating the final report does not help if this intermediate state is already over the
limit, so discovery chooses how many documents to take from an estimate of that state
(`STATE_BUDGET_BYTES`, `document_state_cost`).

These tests build the state from the real handlers' return values, padded to their worst case, and
compare it with the estimate. If a handler starts returning more, the estimate test fails and the
constant in discovery has to grow (or the record has to shrink).
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import boto3
import pytest
from helpers import FIXTURES_DIR, load_handler
from hypothesis import given, settings
from hypothesis import strategies as st
from moto import mock_aws

STATE_LIMIT_BYTES = 256 * 1024
SOURCE = "source-bucket"
RESULTS = "r" * 63  # the longest bucket name: it appears in three S3 URIs per document
EXECUTION = "e" * 80  # the longest execution name Step Functions accepts
DOC_ID = "0123456789abcdef"
#: The largest document discovery accepts (MAX_DOCUMENT_BYTES): the widest `size` it can list.
LARGEST_DOCUMENT_BYTES = 50 * 1024 * 1024
#: The most fields discovery accepts (20), each at the longest name it accepts (40 characters).
BIG_FIELDS = [f"項目{i:02d}" + "あ" * 36 for i in range(20)]
REQUEST = {"collection": "invoices", "max_files": 100, "profile": "structure", "modified_after": "2026-01-01"}
ENV = {
    "S3_ACCESS_POINT_ALIAS": SOURCE,
    "OUTPUT_BUCKET": RESULTS,
    "OUTPUT_DESTINATION": "STANDARD_S3",
    "COLLECTIONS_JSON": json.dumps(
        {"invoices": {"prefix": "scans/", "profile": "structure", "fields": BIG_FIELDS}}, ensure_ascii=False
    ),
    "ENABLE_FIELD_EXTRACTION": "true",
    "MAX_FILES": "100",
    "AWS_DEFAULT_REGION": "ap-northeast-1",
}

discovery = load_handler("discovery")
sync_mod = load_handler("ocr_sync")
extract = load_handler("extract_fields")


def size(value: object) -> int:
    """Return the size of a value as Step Functions counts it: its JSON in UTF-8 bytes.

    Args:
        value: Any JSON-serializable value.

    Returns:
        Number of bytes.
    """
    return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))


@pytest.fixture(scope="module")
def real_records() -> tuple[dict, dict]:
    """Return the `ocr` and `fields` records the handlers produce, padded to the longest values allowed.

    Returns:
        (ocr record from ocr_sync, fields record from extract_fields).
    """
    with mock_aws(), patch.dict(os.environ, ENV):
        s3 = boto3.client("s3", region_name="ap-northeast-1")
        for bucket in (SOURCE, RESULTS):
            s3.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"})
        s3.put_object(Bucket=SOURCE, Key="scans/a.png", Body=b"png")
        textract = MagicMock()
        textract.analyze_document.return_value = json.loads(
            (FIXTURES_DIR / "invoice-ja-001-analyze.json").read_text(encoding="utf-8")
        )
        textract.meta.region_name = "ap-northeast-1"
        base = {
            "doc": {"key": "scans/a.png", "size": 3, "doc_id": DOC_ID, "last_modified": "", "etag": '"e"'},
            "profile": "structure",
            "output_prefix": f"invoices/{EXECUTION}",
            "classification": "RESTRICTED",
            "collection": "invoices",
        }
        with patch.object(sync_mod, "_textract", textract):
            ocr = sync_mod.handler(base, None)

        bedrock = MagicMock()
        answer = {name: {"value": "い" * 200, "evidence": "う" * 200} for name in BIG_FIELDS}
        bedrock.converse.return_value = {"output": {"message": {"content": [{"text": json.dumps(answer)}]}}}
        with patch.object(extract, "_bedrock", bedrock):
            fields = extract.handler(
                {"doc": base["doc"], "collection": "invoices", "output_prefix": base["output_prefix"]}, None
            )
    assert ocr["status"] == "completed" and fields["status"] == "completed"
    # Worst case for the values that vary: a reason cut at its limit, even in 3-byte characters,
    # and a page count with many digits.
    ocr["human_review"]["reason"] = "あ" * 160
    ocr["pages"] = 99999
    ocr["mean_confidence"] = 0.123456789
    return ocr, fields


def run_discovery(keys: list[str], skipped_keys: list[str] | None = None) -> dict:
    """Run discovery over a synthetic listing (no S3 needed: only the sizes matter here).

    Args:
        keys: Keys of documents discovery should accept (`.pdf`).
        skipped_keys: Keys discovery should skip (`.zip`), listed after the others.

    Returns:
        Discovery's output.
    """
    when = datetime(2026, 11, 1, tzinfo=UTC)
    etag = '"0123456789abcdef0123456789abcdef"'
    listing = [
        {"Key": k, "Size": LARGEST_DOCUMENT_BYTES, "LastModified": when, "ETag": etag}
        for k in [*keys, *(skipped_keys or [])]
    ]
    helper = MagicMock()
    helper.list_objects.return_value = listing
    with patch.dict(os.environ, ENV), patch.object(discovery, "S3ApHelper", return_value=helper):
        return discovery.handler({"request": REQUEST, "execution_name": EXECUTION}, None)


def state_after_map(output: dict, ocr: dict, fields: dict) -> dict:
    """Build what Step Functions holds when the Map finishes.

    That is the agent's request, discovery's output, and one result per document, in the shape the
    workflow's Summarize state gives it.

    Args:
        output: Discovery's output.
        ocr: A (worst-case) `ocr` record.
        fields: A (worst-case) `fields` record.

    Returns:
        The state as a dictionary.
    """
    processed = []
    for obj in output["objects"]:
        base = f"s3://{RESULTS}/{output['output_prefix']}/{obj['doc_id']}"
        processed.append(
            {
                "doc_id": obj["doc_id"],
                "key": obj["key"],
                "route": obj["route"],
                "ocr": {**ocr, "result": f"{base}/result.json", "text": f"{base}/text.txt"},
                "fields": {**fields, "result": f"{base}/fields.json"},
            }
        )
    return {**REQUEST, "discovery": output, "processed": processed}


def key_of(index: int, chars: int, suffix: str = ".pdf") -> str:
    """Return a key made of `chars` three-byte characters, unique per index.

    Args:
        index: Distinguishes keys of the same length.
        chars: Number of 'あ' characters in the name.
        suffix: File extension.

    Returns:
        The object key.
    """
    return f"scans/{'あ' * chars}-{index:04d}{suffix}"


class TestEstimate:
    @pytest.mark.parametrize("chars", [1, 50, 300, 330])
    def test_the_per_document_cost_is_not_underestimated(self, real_records: tuple[dict, dict], chars: int) -> None:
        key = key_of(0, chars)
        output = run_discovery([key])
        state = state_after_map(output, *real_records)
        actual = size(output["objects"][0]) + size(state["processed"][0]) + 2  # list separators
        assert actual <= discovery.document_state_cost(key)

    def test_the_fixed_part_of_the_state_is_not_underestimated(self) -> None:
        output = run_discovery([key_of(0, 1)])
        empty = {**output, "objects": [], "skipped": []}
        assert size({**REQUEST, "discovery": empty, "processed": []}) <= discovery.BASE_STATE_BYTES

    def test_the_key_counts_twice(self) -> None:
        short, long = "scans/a.pdf", "scans/" + "a" * 100 + ".pdf"
        extra = discovery.document_state_cost(long) - discovery.document_state_cost(short)
        assert extra == 2 * (len(long) - len(short))

    def test_the_cost_is_in_bytes_not_characters(self) -> None:
        # 'あ' is 3 bytes in UTF-8 and 'a' is 1; the key appears twice.
        assert discovery.document_state_cost("あ") - discovery.document_state_cost("a") == 2 * (3 - 1)


class TestSelection:
    def test_ordinary_keys_fit_the_largest_batch_with_room_to_spare(self, real_records: tuple[dict, dict]) -> None:
        output = run_discovery([key_of(i, 30) for i in range(100)])
        assert output["object_count"] == 100
        assert output["truncated"] is False
        assert size(state_after_map(output, *real_records)) < STATE_LIMIT_BYTES * 0.8

    def test_very_long_keys_are_cut_to_fit_and_the_cut_is_reported(self, real_records: tuple[dict, dict]) -> None:
        keys = [key_of(i, 295) for i in range(100)]  # about 900 bytes each
        output = run_discovery(keys)
        assert 0 < output["object_count"] < 100
        assert output["truncated"] is True
        assert size(state_after_map(output, *real_records)) < STATE_LIMIT_BYTES
        # The prefix of the sorted keys, so the same call picks the same documents.
        assert [o["key"] for o in output["objects"]] == sorted(keys)[: output["object_count"]]

    def test_without_the_budget_the_same_batch_would_not_fit(self, real_records: tuple[dict, dict]) -> None:
        """The reason the budget exists: taking all 100 of these documents overflows the state."""
        keys = [key_of(i, 295) for i in range(100)]
        with patch.object(discovery, "STATE_BUDGET_BYTES", 10**9):
            output = run_discovery(keys)
        assert output["object_count"] == 100
        assert size(state_after_map(output, *real_records)) > STATE_LIMIT_BYTES

    def test_skipped_entries_count_against_the_budget(self, real_records: tuple[dict, dict]) -> None:
        keys = [key_of(i, 150) for i in range(100)]
        skipped = [key_of(i, 330, ".zip") for i in range(60)]  # only 50 are listed, each about 1 KB
        output = run_discovery(keys, skipped)
        assert len(output["skipped"]) == discovery.MAX_SKIPPED_LISTED
        assert output["skipped_count"] == 60
        assert size(state_after_map(output, *real_records)) < STATE_LIMIT_BYTES

    def test_max_files_still_wins_when_it_is_the_tighter_limit(self) -> None:
        helper = MagicMock()
        helper.list_objects.return_value = [
            {"Key": key_of(i, 10), "Size": 10, "LastModified": datetime(2026, 11, 1, tzinfo=UTC), "ETag": '"e"'}
            for i in range(20)
        ]
        request = {**REQUEST, "max_files": 5}
        with patch.dict(os.environ, ENV), patch.object(discovery, "S3ApHelper", return_value=helper):
            output = discovery.handler({"request": request, "execution_name": "x"}, None)
        assert output["object_count"] == 5
        assert output["truncated"] is True

    @given(
        count=st.integers(1, 100),
        chars=st.integers(1, 330),
        skipped=st.integers(0, 80),
        skipped_chars=st.integers(1, 330),
    )
    @settings(deadline=None, max_examples=60)
    def test_property_the_state_after_the_map_never_exceeds_the_limit(
        self, real_records: tuple[dict, dict], count: int, chars: int, skipped: int, skipped_chars: int
    ) -> None:
        output = run_discovery(
            [key_of(i, chars) for i in range(count)],
            [key_of(i, skipped_chars, ".zip") for i in range(skipped)],
        )
        assert output["object_count"] >= 1  # a single document always fits
        assert size(state_after_map(output, *real_records)) < STATE_LIMIT_BYTES
