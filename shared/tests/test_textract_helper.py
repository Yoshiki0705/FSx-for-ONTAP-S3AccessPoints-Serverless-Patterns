"""Tests for shared.textract_helper.

Two kinds of input:
- Real Textract responses (ap-northeast-1, 2026-11-03) for fictional sample documents, stored under
  solutions/genai/japanese-document-ocr-agent/tests/fixtures. They pin the response shapes the
  normalizer depends on, so a mock that drifts from the real service cannot pass quietly.
- Hand-built blocks, for the cases the real responses do not contain.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError, ConnectTimeoutError, ReadTimeoutError
from hypothesis import given, settings
from hypothesis import strategies as st

from shared.exceptions import TextractRejected, TextractThrottled, TextractTransient
from shared.textract_helper import (
    FEATURE_PROFILES,
    BlockAccumulator,
    build_client,
    classify_client_error,
    client_request_token,
    decide_review,
    finalize_document,
    normalize_for_match,
    result_text,
)

FIXTURES = (
    Path(__file__).resolve().parents[2] / "solutions" / "genai" / "japanese-document-ocr-agent" / "tests" / "fixtures"
)


def _load(name: str) -> BlockAccumulator:
    data = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    acc = BlockAccumulator()
    acc.declare_pages(data["DocumentMetadata"]["Pages"])
    acc.add(data["Blocks"])
    return acc


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "m"}}, "Op")


def _line(i: int, text: str, conf: float = 99.0, page: int | None = None) -> dict:
    block = {"BlockType": "LINE", "Id": f"l{i}", "Text": text, "Confidence": conf}
    if page is not None:
        block["Page"] = page
    return block


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------


class TestClassifyClientError:
    @pytest.mark.parametrize(
        "code", ["ThrottlingException", "ProvisionedThroughputExceededException", "LimitExceededException"]
    )
    def test_throttling_codes(self, code):
        error = classify_client_error(_client_error(code))
        assert isinstance(error, TextractThrottled)
        assert error.error_code == code

    @pytest.mark.parametrize("code", ["InternalServerError", "ServiceUnavailable"])
    def test_transient_codes(self, code):
        assert isinstance(classify_client_error(_client_error(code)), TextractTransient)

    @pytest.mark.parametrize(
        "code",
        [
            "UnsupportedDocumentException",
            "BadDocumentException",
            "DocumentTooLargeException",
            "InvalidParameterException",
            "InvalidS3ObjectException",
            "InvalidKMSKeyException",
            "AccessDeniedException",
            "IdempotentParameterMismatchException",
            "InvalidJobIdException",
            "SomethingNew",
        ],
    )
    def test_everything_else_is_rejected_and_not_retried(self, code):
        assert isinstance(classify_client_error(_client_error(code)), TextractRejected)

    def test_timeouts_are_transient(self):
        assert isinstance(classify_client_error(ReadTimeoutError(endpoint_url="https://x")), TextractTransient)
        assert isinstance(classify_client_error(ConnectTimeoutError(endpoint_url="https://x")), TextractTransient)

    def test_non_aws_exception_is_rejected(self):
        assert isinstance(classify_client_error(ValueError("x")), TextractRejected)

    def test_class_names_match_what_step_functions_retries_on(self):
        """The ASL Retry blocks match on these exact names."""
        assert TextractThrottled.__name__ == "TextractThrottled"
        assert TextractTransient.__name__ == "TextractTransient"
        assert TextractRejected.__name__ == "TextractRejected"


def test_build_client_uses_adaptive_retries_and_the_given_region():
    session = MagicMock()
    build_client("ap-northeast-1", session=session)
    _, kwargs = session.client.call_args
    assert session.client.call_args.args == ("textract",)
    assert kwargs["region_name"] == "ap-northeast-1"
    config = kwargs["config"]
    assert config.retries["mode"] == "adaptive"
    assert config.retries["max_attempts"] == 5


# ---------------------------------------------------------------------------
# ClientRequestToken
# ---------------------------------------------------------------------------


class TestClientRequestToken:
    def test_is_deterministic(self):
        assert client_request_token("exec", "doc", "text") == client_request_token("exec", "doc", "text")

    def test_differs_when_any_part_differs(self):
        base = client_request_token("exec", "doc", "text")
        assert client_request_token("exec2", "doc", "text") != base
        assert client_request_token("exec", "doc", "structure") != base

    def test_part_boundaries_matter(self):
        assert client_request_token("ab", "c") != client_request_token("a", "bc")

    def test_matches_the_api_constraint(self):
        token = client_request_token("実行-1", "文書", "text")
        assert 1 <= len(token) <= 64
        assert re.fullmatch(r"[a-zA-Z0-9\-_]+", token)

    @given(parts=st.lists(st.text(max_size=200), min_size=1, max_size=6))
    @settings(deadline=None, max_examples=200)
    def test_property_always_valid(self, parts):
        token = client_request_token(*parts)
        assert 1 <= len(token) <= 64
        assert re.fullmatch(r"[a-zA-Z0-9\-_]+", token)
        assert token == client_request_token(*parts)


# ---------------------------------------------------------------------------
# normalize_for_match
# ---------------------------------------------------------------------------


class TestNormalizeForMatch:
    def test_width_and_whitespace(self):
        assert normalize_for_match("金額： １２３，４５６ 円") == "金額:123,456円"

    def test_fullwidth_parentheses_match_halfwidth(self):
        assert normalize_for_match("消費税（10%）") == normalize_for_match("消費税 (10%)")

    def test_empty(self):
        assert normalize_for_match("") == ""


# ---------------------------------------------------------------------------
# BlockAccumulator: real responses
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def invoice_001():
    return _load("invoice-ja-001-analyze").result()


@pytest.fixture(scope="module")
def invoice_002():
    return _load("invoice-ja-002-analyze").result()


class TestRealInvoice:
    """invoice-ja-001, AnalyzeDocument(TABLES, LAYOUT): the table has a MERGED_CELL Textract got wrong."""

    @pytest.fixture
    def doc(self, invoice_001):
        return invoice_001

    def test_page_and_line_counts(self, doc):
        assert len(doc["pages"]) == 1
        assert doc["quality"]["pages"] == 1
        assert doc["quality"]["line_count"] == 39
        assert doc["pages"][0]["lines"][0] == {"text": "請求書", "confidence": 99.96}

    def test_table_rows_are_rebuilt_from_cells(self, doc):
        rows = doc["pages"][0]["tables"][0]["rows"]
        assert rows[0] == ["品名", "数量", "単価", "金額"]
        assert rows[1] == ["部品A (精密加工)", "120", "¥1,500", "¥180,000"]
        assert rows[4] == ["運送費", "3", "¥12,000", "¥36,000"]

    def test_wrongly_merged_summary_cell_is_flagged(self, doc):
        """The totals below the table were swallowed into one cell (confidence ~45)."""
        table = doc["pages"][0]["tables"][0]
        assert table["merged_cells"] == 1
        assert table["structure_suspect"] is True
        assert doc["quality"]["low_confidence_tables"] == 1
        assert "¥485,100" in table["rows"][-1][-1]

    def test_layout_children_are_in_document_order(self, doc):
        footer = doc["pages"][0]["layout"][-1]["text"]
        # Textract lists this block's child LINEs as "組立ライン..." before "備考: 部品A", which is not the
        # order on the page; the normalizer restores document order.
        assert "備考: 部品A 組立ラインへ直送します。" in footer
        assert footer.index("備考") < footer.index("組立ライン")

    def test_layout_types_are_kept(self, doc):
        types = [item["type"] for item in doc["pages"][0]["layout"]]
        assert types[0] == "LAYOUT_TITLE"
        assert "LAYOUT_TABLE" in types

    def test_review_is_required(self, doc):
        decision = decide_review(doc["quality"])
        assert decision.requires_review is True
        assert "table structure looks unreliable" in decision.reason


class TestRealScannedInvoice:
    """invoice-ja-002 (rotated, noisy JPEG): a misread line is reported with low confidence."""

    @pytest.fixture
    def doc(self, invoice_002):
        return invoice_002

    def test_clean_table_is_not_suspect(self, doc):
        table = doc["pages"][0]["tables"][0]
        assert table["structure_suspect"] is False
        assert table["rows"][1][0] == "樹脂成形品C"

    def test_misread_line_pulls_the_ratio_over_the_limit(self, doc):
        assert doc["quality"]["min_confidence"] < 70
        assert doc["quality"]["low_confidence_char_ratio"] > 0.05
        assert decide_review(doc["quality"]).action == "HUMAN_REVIEW"


class TestRealMemo:
    """memo-ja-001, DetectDocumentText: no tables or layout."""

    def test_text_only_has_no_tables_or_layout(self):
        doc = _load("memo-ja-001-detect").result()
        assert doc["pages"][0]["tables"] == []
        assert doc["pages"][0]["layout"] == []
        assert doc["quality"]["table_count"] == 0

    def test_high_confidence_misread_cannot_be_detected_from_confidence(self):
        """'括弧' came back as '括孤' on a line with confidence 98: the pattern must say so, not hide it."""
        doc = _load("memo-ja-001-detect").result()
        wrong = next(ln for ln in doc["pages"][0]["lines"] if "括孤" in ln["text"])
        assert wrong["confidence"] > 95


# ---------------------------------------------------------------------------
# BlockAccumulator: hand-built blocks
# ---------------------------------------------------------------------------


class TestAccumulator:
    def test_no_blocks(self):
        doc = BlockAccumulator().result()
        assert doc["pages"] == []
        assert doc["quality"]["line_count"] == 0
        assert doc["quality"]["mean_confidence"] == 0.0

    def test_pages_come_from_the_page_field(self):
        acc = BlockAccumulator()
        acc.add([_line(1, "一", page=1), _line(2, "二", page=2), _line(3, "三", page=2)])
        doc = acc.result()
        assert [p["page"] for p in doc["pages"]] == [1, 2]
        assert [len(p["lines"]) for p in doc["pages"]] == [1, 2]

    def test_blocks_can_arrive_in_separate_calls(self):
        """A parent and its children may be in different Get* responses."""
        acc = BlockAccumulator()
        acc.add(
            [
                {
                    "BlockType": "TABLE",
                    "Id": "t1",
                    "Confidence": 90,
                    "Relationships": [{"Type": "CHILD", "Ids": ["c1"]}],
                }
            ]
        )
        acc.add(
            [
                {
                    "BlockType": "CELL",
                    "Id": "c1",
                    "RowIndex": 1,
                    "ColumnIndex": 1,
                    "Confidence": 90,
                    "Relationships": [{"Type": "CHILD", "Ids": ["w1", "w2"]}],
                }
            ]
        )
        acc.add(
            [
                {"BlockType": "WORD", "Id": "w1", "Text": "株式", "Confidence": 99, "TextType": "PRINTED"},
                {"BlockType": "WORD", "Id": "w2", "Text": "会社", "Confidence": 99, "TextType": "PRINTED"},
            ]
        )
        assert acc.result()["pages"][0]["tables"][0]["rows"] == [["株式 会社"]]

    def test_mean_confidence_is_weighted_by_characters(self):
        acc = BlockAccumulator()
        acc.add([_line(1, "あ" * 90, 100.0), _line(2, "い" * 10, 50.0)])
        assert acc.result()["quality"]["mean_confidence"] == pytest.approx(95.0)

    def test_low_confidence_ratio_counts_characters_not_lines(self):
        acc = BlockAccumulator(low_confidence_threshold=90)
        acc.add([_line(1, "あ" * 90, 99.0), _line(2, "い" * 10, 50.0)])
        quality = acc.result()["quality"]
        assert quality["low_confidence_lines"] == 1
        assert quality["low_confidence_char_ratio"] == pytest.approx(0.1)

    def test_handwriting_ratio(self):
        acc = BlockAccumulator()
        acc.add(
            [
                {"BlockType": "WORD", "Id": "a", "Text": "x", "Confidence": 99, "TextType": "HANDWRITING"},
                {"BlockType": "WORD", "Id": "b", "Text": "y", "Confidence": 99, "TextType": "PRINTED"},
            ]
        )
        assert acc.result()["quality"]["handwriting_word_ratio"] == pytest.approx(0.5)

    def test_declared_pages_without_blocks_is_reported(self):
        acc = BlockAccumulator()
        acc.declare_pages(3)
        assert acc.result()["quality"]["pages"] == 3

    def test_table_with_a_missing_cell_leaves_an_empty_string(self):
        acc = BlockAccumulator()
        acc.add(
            [
                {
                    "BlockType": "TABLE",
                    "Id": "t",
                    "Confidence": 99,
                    "Relationships": [{"Type": "CHILD", "Ids": ["c1", "c2"]}],
                },
                {"BlockType": "CELL", "Id": "c1", "RowIndex": 1, "ColumnIndex": 1, "Confidence": 99},
                {"BlockType": "CELL", "Id": "c2", "RowIndex": 2, "ColumnIndex": 2, "Confidence": 99},
            ]
        )
        assert acc.result()["pages"][0]["tables"][0]["rows"] == [["", ""], ["", ""]]


# ---------------------------------------------------------------------------
# decide_review
# ---------------------------------------------------------------------------

GOOD = {"line_count": 10, "mean_confidence": 99.0, "low_confidence_char_ratio": 0.0, "handwriting_word_ratio": 0.0}


class TestDecideReview:
    def test_auto_approve(self):
        decision = decide_review(GOOD)
        assert decision.action == "AUTO_APPROVE"
        assert decision.requires_review is False

    def test_mean_below_threshold_needs_review_and_the_reason_shows_the_difference(self):
        decision = decide_review({**GOOD, "mean_confidence": 94.9})
        assert decision.action == "HUMAN_REVIEW"
        assert "0.949" in decision.reason
        assert "0.950" in decision.reason

    def test_reject_is_kept(self):
        decision = decide_review({**GOOD, "mean_confidence": 20.0})
        assert decision.action == "REJECT"

    def test_low_confidence_characters_escalate_an_otherwise_good_document(self):
        decision = decide_review({**GOOD, "low_confidence_char_ratio": 0.2})
        assert decision.action == "HUMAN_REVIEW"
        assert "20%" in decision.reason

    def test_handwriting_escalates(self):
        decision = decide_review({**GOOD, "handwriting_word_ratio": 0.5})
        assert decision.requires_review
        assert "English only" in decision.reason

    def test_suspect_table_escalates(self):
        assert decide_review({**GOOD, "low_confidence_tables": 1}).requires_review

    def test_no_text_is_not_auto_approved(self):
        decision = decide_review({"line_count": 0})
        assert decision.action == "HUMAN_REVIEW"
        assert decision.reason.startswith("No text detected")

    def test_extra_reasons_escalate(self):
        decision = decide_review(GOOD, extra_reasons=["field 合計金額 is not grounded"])
        assert decision.action == "HUMAN_REVIEW"
        assert "not grounded" in decision.reason

    def test_extra_reasons_do_not_downgrade_a_reject(self):
        decision = decide_review({**GOOD, "mean_confidence": 10.0}, extra_reasons=["x"])
        assert decision.action == "REJECT"
        assert decision.reason.endswith("x")

    def test_thresholds_are_parameters(self):
        assert decide_review({**GOOD, "mean_confidence": 90.0}, auto_approve=0.85).action == "AUTO_APPROVE"

    @given(
        mean=st.floats(0, 100, allow_nan=False),
        ratio=st.floats(0, 1, allow_nan=False),
        hand=st.floats(0, 1, allow_nan=False),
        tables=st.integers(0, 3),
        lines=st.integers(0, 50),
    )
    @settings(deadline=None, max_examples=200)
    def test_property_decision_is_consistent(self, mean, ratio, hand, tables, lines):
        decision = decide_review(
            {
                "line_count": lines,
                "mean_confidence": mean,
                "low_confidence_char_ratio": ratio,
                "handwriting_word_ratio": hand,
                "low_confidence_tables": tables,
            }
        )
        assert decision.action in {"AUTO_APPROVE", "HUMAN_REVIEW", "REJECT"}
        assert decision.requires_review == (decision.action != "AUTO_APPROVE")
        if lines == 0:
            assert decision.requires_review


# ---------------------------------------------------------------------------
# finalize_document
# ---------------------------------------------------------------------------


class FakeWriter:
    """Records what `finalize_document` writes, in place of shared.output_writer.OutputWriter."""

    def __init__(self) -> None:
        self.objects: dict[str, object] = {}

    def put_json(self, key: str, data: object, **_: object) -> None:
        self.objects[key] = data

    def put_text(self, key: str, text: str, **_: object) -> None:
        self.objects[key] = text

    def build_s3_uri(self, key: str) -> str:
        return f"s3://results/{key}"


def test_finalize_writes_outputs_and_returns_a_small_record():
    writer = FakeWriter()
    record = finalize_document(
        accumulator=_load("memo-ja-001-detect"),
        writer=writer,
        key_prefix="memos/exec-1/abc",
        source={"key": "メモ/業務メモ.png", "size": 54699},
        textract_meta={"api": "DetectDocumentText", "mode": "sync", "region": "ap-northeast-1"},
        classification="INTERNAL",
        thresholds={},
    )
    assert set(writer.objects) == {"memos/exec-1/abc/result.json", "memos/exec-1/abc/text.txt"}
    stored = writer.objects["memos/exec-1/abc/result.json"]
    assert stored["source"]["key"] == "メモ/業務メモ.png"
    assert stored["data_classification"] == "INTERNAL"
    assert stored["schema_version"] == "1"
    assert "括孤" in writer.objects["memos/exec-1/abc/text.txt"]
    assert record["status"] == "completed"
    assert record["result"] == "s3://results/memos/exec-1/abc/result.json"
    # The record that goes into the Step Functions state carries no OCR text.
    assert "括孤" not in json.dumps(record, ensure_ascii=False)
    assert len(json.dumps(record, ensure_ascii=False).encode("utf-8")) < 1024


def test_result_text_separates_pages_with_a_blank_line():
    acc = BlockAccumulator()
    acc.add([_line(1, "一枚目", page=1), _line(2, "二枚目", page=2)])
    assert result_text(acc.result()) == "一枚目\n\n二枚目"


def test_feature_profiles_never_include_forms_or_queries():
    """Forms and Queries are not supported for Japanese; the pattern must not offer them."""
    for features in FEATURE_PROFILES.values():
        assert "FORMS" not in features
        assert "QUERIES" not in features


# ---------------------------------------------------------------------------
# Properties over arbitrary blocks
# ---------------------------------------------------------------------------

_block = st.fixed_dictionaries(
    {
        "BlockType": st.sampled_from(
            ["PAGE", "LINE", "WORD", "TABLE", "CELL", "MERGED_CELL", "LAYOUT_TEXT", "SELECTION_ELEMENT", "UNKNOWN"]
        ),
        "Id": st.text(alphabet="abcdef0123456789", min_size=1, max_size=4),
    },
    optional={
        "Text": st.text(max_size=30),
        "Confidence": st.floats(0, 100, allow_nan=False),
        "Page": st.integers(1, 5),
        "RowIndex": st.integers(1, 4),
        "ColumnIndex": st.integers(1, 4),
        "RowSpan": st.integers(1, 2),
        "ColumnSpan": st.integers(1, 2),
        "TextType": st.sampled_from(["PRINTED", "HANDWRITING"]),
        "Relationships": st.lists(
            st.fixed_dictionaries(
                {
                    "Type": st.sampled_from(["CHILD", "MERGED_CELL", "VALUE"]),
                    "Ids": st.lists(st.text(alphabet="abcdef0123456789", min_size=1, max_size=4), max_size=4),
                }
            ),
            max_size=2,
        ),
    },
)


@given(blocks=st.lists(_block, max_size=40))
@settings(deadline=None, max_examples=200)
def test_property_any_blocks_normalize_without_error_and_stay_in_range(blocks):
    acc = BlockAccumulator()
    acc.add(blocks)
    doc = acc.result()
    quality = doc["quality"]
    assert 0.0 <= quality["mean_confidence"] <= 100.0
    assert 0.0 <= quality["low_confidence_char_ratio"] <= 1.0
    assert 0.0 <= quality["handwriting_word_ratio"] <= 1.0
    assert quality["line_count"] == sum(len(p["lines"]) for p in doc["pages"])
    json.dumps(doc, ensure_ascii=False)  # always serializable
    decide_review(quality)  # never raises
