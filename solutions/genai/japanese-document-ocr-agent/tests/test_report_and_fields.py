"""Unit tests for the report and extract_fields handlers."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import boto3
import pytest
from botocore.exceptions import ClientError
from helpers import load_handler
from hypothesis import given, settings
from hypothesis import strategies as st
from moto import mock_aws

from shared.exceptions import BedrockThrottled, InvalidConfiguration

RESULTS = "results-bucket"
ENV = {
    "OUTPUT_BUCKET": RESULTS,
    "OUTPUT_DESTINATION": "STANDARD_S3",
    "AWS_DEFAULT_REGION": "ap-northeast-1",
    "AWS_REGION": "ap-northeast-1",
}
report = load_handler("report")
extract = load_handler("extract_fields")
STATE_LIMIT_BYTES = 256 * 1024


@pytest.fixture
def s3():
    with mock_aws():
        client = boto3.client("s3", region_name="ap-northeast-1")
        client.create_bucket(Bucket=RESULTS, CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"})
        yield client


def done(
    key: str, action: str = "AUTO_APPROVE", pages: int = 1, conf: float = 0.99, fields: dict | None = None
) -> dict:
    """A record as the state machine's Summarize state produces it for a finished document."""
    return {
        "doc_id": key[-8:].replace("/", "_"),
        "key": key,
        "route": "sync",
        "ocr": {
            "status": "completed",
            "pages": pages,
            "api": "AnalyzeDocument",
            "mean_confidence": conf,
            "human_review": {"action": action, "requires_review": action != "AUTO_APPROVE", "reason": "r"},
            "result": f"s3://{RESULTS}/x/result.json",
            "text": f"s3://{RESULTS}/x/text.txt",
        },
        "fields": fields or {"status": "not_requested"},
    }


def completed_fields(requested: int, ungrounded_count: int) -> dict:
    """The compact record extract_fields puts in the state (values and evidence live in fields.json)."""
    return {
        "status": "completed",
        "requested": requested,
        "ungrounded_count": ungrounded_count,
        "result": f"s3://{RESULTS}/x/fields.json",
    }


def store_fields(s3, record: dict, entries: dict[str, tuple[str | None, bool]]) -> None:
    """Store the fields.json that extract_fields writes for this record: name -> (value, grounded)."""
    body = {
        "model_id": "m",
        "fields": {
            name: {"value": value, "evidence": f"EVIDENCE-{value}" if value else None, "grounded": grounded}
            for name, (value, grounded) in entries.items()
        },
        "ungrounded": [name for name, (_, grounded) in entries.items() if not grounded],
    }
    s3.put_object(
        Bucket=RESULTS,
        Key=f"invoices/exec-1/{record['doc_id']}/fields.json",
        Body=json.dumps(body, ensure_ascii=False).encode("utf-8"),
    )


def failed_lambda(key: str, kind: str = "UnsupportedDocumentException") -> dict:
    """A failure the Lambda itself returned: error is an object."""
    return {
        "doc_id": "f",
        "key": key,
        "route": "sync",
        "ocr": {"status": "failed", "error": {"type": kind, "message": "m"}},
    }


def failed_catch(key: str, kind: str = "TextractThrottled") -> dict:
    """A failure the state machine's RecordFailure produced from a Catch: error is a plain string."""
    return {"doc_id": "g", "key": key, "route": "async", "ocr": {"status": "failed", "error": kind}}


def event(processed: list[dict], **discovery: object) -> dict:
    base = {
        "collection": "invoices",
        "profile": "structure",
        "classification": "RESTRICTED",
        "output_prefix": "invoices/exec-1",
        "skipped_count": 0,
        "skipped": [],
        "truncated": False,
    }
    return {"discovery": {**base, **discovery}, "processed": processed, "execution_name": "exec-1"}


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


class TestReport:
    @patch.dict(os.environ, ENV)
    def test_completed(self, s3):
        with patch.object(report, "_sns", MagicMock()):
            result = report.handler(event([done("a.png"), done("b.pdf", pages=3)], skipped_count=2), None)
        assert result["status"] == "completed"
        assert result["summary"]["total"] == 2
        assert result["summary"]["pages"] == 4
        assert result["summary"]["skipped"] == 2
        assert result["summary"]["review_required"] == 0
        assert result["data_classification"] == "RESTRICTED"
        assert result["output"]["manifest"] == f"s3://{RESULTS}/invoices/exec-1/manifest.json"
        assert result["region"] == "ap-northeast-1"
        assert "error_type" not in result

    @patch.dict(os.environ, ENV)
    def test_manifest_is_written_with_every_document(self, s3):
        with patch.object(report, "_sns", MagicMock()):
            report.handler(event([done("a.png"), failed_lambda("b.png")]), None)
        manifest = json.loads(s3.get_object(Bucket=RESULTS, Key="invoices/exec-1/manifest.json")["Body"].read())
        assert [d["key"] for d in manifest["documents"]] == ["a.png", "b.png"]
        assert manifest["status"] == "completed_with_errors"
        assert manifest["data_classification"] == "RESTRICTED"

    @patch.dict(os.environ, ENV)
    def test_some_failures_still_succeed_but_say_so(self, s3):
        with patch.object(report, "_sns", MagicMock()):
            result = report.handler(event([done("a.png"), failed_lambda("b.png")]), None)
        assert result["status"] == "completed_with_errors"
        assert result["summary"]["failed"] == 1
        assert result["summary"]["errors"] == {"UnsupportedDocumentException": 1}

    @patch.dict(os.environ, ENV)
    def test_all_failed_is_reported_as_failed_with_a_cause(self, s3):
        processed = [failed_lambda("a.png"), failed_lambda("b.png"), failed_catch("c.pdf")]
        with patch.object(report, "_sns", MagicMock()):
            result = report.handler(event(processed), None)
        assert result["status"] == "failed"
        assert result["error_type"] == "AllDocumentsFailed"
        assert "All 3 documents failed" in result["cause"]
        assert "UnsupportedDocumentException x2" in result["cause"]
        assert "manifest.json" in result["cause"]

    @patch.dict(os.environ, ENV)
    def test_a_failure_from_a_catch_does_not_break_the_aggregation(self, s3):
        """RecordFailure writes error as a string; the Lambda writes an object. Both must be readable."""
        with patch.object(report, "_sns", MagicMock()):
            result = report.handler(event([done("a.png"), failed_catch("b.pdf", "TextractTransient")]), None)
        assert result["summary"]["errors"] == {"TextractTransient": 1}
        assert result["documents"][0]["error"] == {"type": "TextractTransient", "message": ""}

    @patch.dict(os.environ, ENV)
    def test_review_queue_lists_what_needs_a_person_first(self, s3):
        processed = [
            done("ok.png"),
            done("review.png", "HUMAN_REVIEW"),
            failed_lambda("bad.png"),
            done("rej.png", "REJECT"),
        ]
        with patch.object(report, "_sns", MagicMock()):
            result = report.handler(event(processed), None)
        assert result["review_queue"] == ["review.png", "rej.png"]
        assert result["summary"]["review_required"] == 2
        # failed first, then documents that need review, then the approved ones
        assert [d["key"] for d in result["documents"]] == ["bad.png", "review.png", "rej.png", "ok.png"]

    @patch.dict(os.environ, ENV)
    def test_no_documents(self, s3):
        with patch.object(report, "_sns", MagicMock()):
            result = report.handler(event([], skipped_count=4), None)
        assert result["status"] == "completed"
        assert result["summary"]["total"] == 0
        assert result["summary"]["mean_confidence"] is None
        assert result["summary"]["skipped"] == 4

    @patch.dict(os.environ, {**ENV, "SNS_TOPIC_ARN": "arn:aws:sns:ap-northeast-1:123456789012:t"})
    def test_notifies_and_flags_review(self, s3):
        sns = MagicMock()
        with patch.object(report, "_sns", sns):
            report.handler(event([done("a.png", "HUMAN_REVIEW")]), None)
        subject = sns.publish.call_args.kwargs["Subject"]
        assert subject.startswith("[REVIEW 1]")

    @patch.dict(os.environ, {**ENV, "SNS_TOPIC_ARN": "arn:aws:sns:ap-northeast-1:123456789012:t"})
    def test_a_notification_failure_does_not_fail_the_report(self, s3):
        sns = MagicMock()
        sns.publish.side_effect = RuntimeError("boom")
        with patch.object(report, "_sns", sns):
            assert report.handler(event([done("a.png")]), None)["status"] == "completed"

    @patch.dict(os.environ, ENV)
    def test_no_topic_skips_the_notification(self, s3):
        sns = MagicMock()
        with patch.object(report, "_sns", sns):
            report.handler(event([done("a.png")]), None)
        sns.publish.assert_not_called()

    @patch.dict(os.environ, ENV)
    def test_the_result_carries_no_ocr_text(self, s3):
        with patch.object(report, "_sns", MagicMock()):
            result = report.handler(event([done("a.png")]), None)
        assert "text" not in result["documents"][0]


class TestReportError:
    @patch.dict(os.environ, ENV)
    def test_invalid_input_is_reported_without_the_stack_trace(self, s3):
        cause = json.dumps(
            {
                "errorMessage": "unknown field(s): prefix; allowed: collection, max_files",
                "errorType": "InvalidInput",
                "stackTrace": ['  File "/var/task/handler.py", line 1\n'] * 40,
            }
        )
        sns = MagicMock()
        with (
            patch.object(report, "_sns", sns),
            patch.dict(os.environ, {"SNS_TOPIC_ARN": "arn:aws:sns:ap-northeast-1:1:t"}),
        ):
            result = report.handler({"status": "ERROR", "error": {"Error": "InvalidInput", "Cause": cause}}, None)
        assert result == {
            "status": "error",
            "error_type": "InvalidInput",
            "cause": "unknown field(s): prefix; allowed: collection, max_files",
        }
        sns.publish.assert_not_called()  # an agent's typo is not worth an email

    @patch.dict(os.environ, ENV)
    def test_other_errors_notify(self, s3):
        cause = json.dumps({"errorMessage": "Access Denied", "errorType": "S3ApHelperError"})
        sns = MagicMock()
        with (
            patch.object(report, "_sns", sns),
            patch.dict(os.environ, {"SNS_TOPIC_ARN": "arn:aws:sns:ap-northeast-1:1:t"}),
        ):
            result = report.handler({"status": "ERROR", "error": {"Error": "S3ApHelperError", "Cause": cause}}, None)
        assert result["error_type"] == "S3ApHelperError"
        assert sns.publish.call_args.kwargs["Subject"].startswith("[FAILED]")

    @patch.dict(os.environ, ENV)
    @pytest.mark.parametrize(
        "error", [{}, {"Error": "States.Runtime"}, {"Error": "X", "Cause": "not json"}, {"Cause": 5}]
    )
    def test_odd_errors_never_break_the_error_path(self, s3, error):
        with patch.object(report, "_sns", MagicMock()):
            result = report.handler({"status": "ERROR", "error": error}, None)
        assert result["status"] == "error"
        assert result["error_type"]
        assert isinstance(result["cause"], str) and len(result["cause"]) <= report.MAX_CAUSE_CHARS

    def test_a_long_cause_is_cut(self):
        error_type, message = report.clean_error_message({"Error": "X", "Cause": "y" * 5000})
        assert error_type == "X"
        assert len(message) == report.MAX_CAUSE_CHARS


class TestSizeLimit:
    @patch.dict(os.environ, ENV)
    def test_many_documents_are_truncated_and_stay_under_the_state_limit(self, s3):
        processed = [done(f"scans/請求書/{'あ' * 60}-{i:04d}.pdf", "HUMAN_REVIEW") for i in range(400)]
        with patch.object(report, "_sns", MagicMock()):
            result = report.handler(event(processed), None)
        assert result["documents_truncated"] is True
        assert len(result["documents"]) < 400
        assert len(json.dumps(result, ensure_ascii=False).encode("utf-8")) < STATE_LIMIT_BYTES
        # nothing is lost: the manifest has all of them
        manifest = json.loads(s3.get_object(Bucket=RESULTS, Key="invoices/exec-1/manifest.json")["Body"].read())
        assert len(manifest["documents"]) == 400

    def test_fit_documents_keeps_failures_when_it_has_to_cut(self):
        views = [{"key": f"k{i}", "status": "completed", "action": "AUTO_APPROVE"} for i in range(50)]
        views.append({"key": "bad", "status": "failed"})
        kept, truncated = report.fit_documents(views, budget_bytes=200)
        assert truncated is True
        assert kept[0]["key"] == "bad"

    @given(
        count=st.integers(0, 120),
        failures=st.integers(0, 20),
        name_len=st.integers(1, 150),
    )
    @settings(deadline=None, max_examples=60)
    def test_property_result_never_exceeds_the_state_limit(self, count, failures, name_len):
        processed = [done(f"{'日' * name_len}-{i}.pdf", "HUMAN_REVIEW") for i in range(count)]
        processed += [failed_lambda(f"{'本' * name_len}-f{i}.png") for i in range(failures)]
        with mock_aws(), patch.dict(os.environ, ENV):
            boto3.client("s3", region_name="ap-northeast-1").create_bucket(
                Bucket=RESULTS, CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"}
            )
            with patch.object(report, "_sns", MagicMock()):
                result = report.handler(event(processed, skipped=[{"key": "s" * 100, "reason": "x"}] * 60), None)
        assert len(json.dumps(result, ensure_ascii=False).encode("utf-8")) < STATE_LIMIT_BYTES
        assert len(result["skipped"]) <= 20
        assert len(result["review_queue"]) <= 50


# ---------------------------------------------------------------------------
# extract_fields
# ---------------------------------------------------------------------------

TEXT = "請求書\n請求書番号: INV-2026-0001\n発行日: 2026年10月15日\n合計金額 (税込) ¥485,100\n"
FIELDS = ["請求書番号", "発行日", "合計金額", "支払期限"]
COLLECTIONS = json.dumps({"invoices": {"prefix": "x/", "fields": FIELDS}}, ensure_ascii=False)
#: The most fields discovery accepts (20), each at the longest name it accepts (40 characters).
BIG_FIELDS = [f"項目{i:02d}" + "あ" * 36 for i in range(20)]


def model_answer(**entries: object) -> dict:
    return {"output": {"message": {"content": [{"text": json.dumps(entries, ensure_ascii=False)}]}}}


def put_text(s3, text: str = TEXT) -> None:
    s3.put_object(Bucket=RESULTS, Key="invoices/exec-1/abc/text.txt", Body=text.encode("utf-8"))


def fields_event() -> dict:
    return {"doc": {"doc_id": "abc", "key": "k"}, "collection": "invoices", "output_prefix": "invoices/exec-1"}


class TestExtractHelpers:
    def test_parse_json_with_fences_and_prose(self):
        assert extract.parse_model_json('はい。\n```json\n{"a": {"value": "1"}}\n```\n以上です。') == {
            "a": {"value": "1"}
        }

    @pytest.mark.parametrize("raw", ["", "no json here", "[1, 2]", "{broken", "{"])
    def test_unreadable_output_raises(self, raw):
        with pytest.raises(ValueError):
            extract.parse_model_json(raw)

    def test_grounded_when_the_evidence_is_in_the_text(self):
        result = extract.ground_fields(
            ["合計金額"], {"合計金額": {"value": "¥485,100", "evidence": "合計金額 (税込) ¥485,100"}}, TEXT
        )
        assert result["合計金額"]["grounded"] is True

    def test_width_and_spacing_differences_do_not_break_grounding(self):
        result = extract.ground_fields(
            ["合計金額"], {"合計金額": {"value": "¥485,100", "evidence": "合計金額（税込）¥４８５，１００"}}, TEXT
        )
        assert result["合計金額"]["grounded"] is True

    def test_an_invented_or_reworded_quote_is_not_grounded(self):
        result = extract.ground_fields(
            ["合計金額"], {"合計金額": {"value": "¥999,999", "evidence": "合計金額は¥999,999です"}}, TEXT
        )
        assert result["合計金額"]["grounded"] is False

    def test_a_value_without_evidence_is_not_grounded(self):
        result = extract.ground_fields(["発行日"], {"発行日": {"value": "2026年10月15日", "evidence": None}}, TEXT)
        assert result["発行日"]["grounded"] is False

    def test_a_null_value_is_not_grounded_and_a_missing_field_is_reported(self):
        result = extract.ground_fields(["支払期限", "請求先"], {"支払期限": {"value": None, "evidence": None}}, TEXT)
        assert result["支払期限"] == {"value": None, "evidence": None, "grounded": False}
        assert result["請求先"]["grounded"] is False  # the model did not mention it at all

    def test_every_requested_field_is_returned_and_extras_are_ignored(self):
        result = extract.ground_fields(["a"], {"a": {"value": "x", "evidence": "x"}, "z": {"value": "y"}}, "x")
        assert list(result) == ["a"]

    def test_values_are_truncated(self):
        long = "あ" * 1000
        result = extract.ground_fields(["a"], {"a": {"value": long, "evidence": long}}, long)
        assert len(result["a"]["value"]) == extract.MAX_VALUE_CHARS
        assert result["a"]["grounded"] is True

    @given(
        entry=st.one_of(
            st.none(),
            st.text(max_size=20),
            st.integers(),
            st.dictionaries(
                st.sampled_from(["value", "evidence", "x"]), st.one_of(st.none(), st.text(max_size=30), st.integers())
            ),
        ),
        text=st.text(max_size=60),
    )
    @settings(deadline=None, max_examples=200)
    def test_property_grounding_never_raises_and_is_boolean(self, entry, text):
        result = extract.ground_fields(["f"], {"f": entry}, text)
        assert isinstance(result["f"]["grounded"], bool)
        if result["f"]["grounded"]:
            assert result["f"]["value"] and result["f"]["evidence"]

    def test_the_prompt_names_every_field_and_the_text(self):
        prompt = extract.build_prompt(FIELDS, TEXT)
        for name in FIELDS:
            assert name in prompt
        assert "INV-2026-0001" in prompt
        assert "そのまま引用" in prompt

    def test_the_text_is_cut_to_the_limit(self):
        prompt = extract.build_prompt(["a"], "あ" * (extract.MAX_TEXT_CHARS + 5000))
        assert prompt.count("あ") == extract.MAX_TEXT_CHARS


class TestExtractHandler:
    @patch.dict(os.environ, {**ENV, "COLLECTIONS_JSON": COLLECTIONS})
    def test_extracts_grounds_and_writes_fields_json(self, s3):
        put_text(s3)
        bedrock = MagicMock()
        bedrock.converse.return_value = model_answer(
            請求書番号={"value": "INV-2026-0001", "evidence": "請求書番号: INV-2026-0001"},
            発行日={"value": "2026年10月15日", "evidence": "発行日: 2026年10月15日"},
            合計金額={"value": "¥485,100", "evidence": "合計金額 (税込) ¥485,100"},
            支払期限={"value": None, "evidence": None},
        )
        with patch.object(extract, "_bedrock", bedrock):
            result = extract.handler(fields_event(), None)

        # The state carries counts and a pointer only. Values and evidence stay in fields.json.
        assert result == {
            "status": "completed",
            "requested": 4,
            "ungrounded_count": 1,
            "result": f"s3://{RESULTS}/invoices/exec-1/abc/fields.json",
        }
        stored = json.loads(s3.get_object(Bucket=RESULTS, Key="invoices/exec-1/abc/fields.json")["Body"].read())
        assert stored["ungrounded"] == ["支払期限"]
        assert stored["fields"]["合計金額"]["grounded"] is True
        assert stored["fields"]["合計金額"]["evidence"] == "合計金額 (税込) ¥485,100"

    @patch.dict(
        os.environ, {**ENV, "COLLECTIONS_JSON": json.dumps({"invoices": {"prefix": "x/", "fields": BIG_FIELDS}})}
    )
    def test_the_state_record_stays_small_for_the_largest_request(self, s3):
        """20 fields of 40 characters, each with a 200-character value and quote: the record is still tiny."""
        put_text(s3, "う" * 200)
        bedrock = MagicMock()
        bedrock.converse.return_value = model_answer(
            **{name: {"value": "い" * 200, "evidence": "う" * 200} for name in BIG_FIELDS}
        )
        with patch.object(extract, "_bedrock", bedrock):
            result = extract.handler(fields_event(), None)
        assert result["requested"] == 20
        assert len(json.dumps(result, ensure_ascii=False).encode("utf-8")) < 300
        stored = json.loads(s3.get_object(Bucket=RESULTS, Key="invoices/exec-1/abc/fields.json")["Body"].read())
        assert len(stored["fields"]) == 20  # nothing was dropped, it just does not travel in the state

    @patch.dict(os.environ, {**ENV, "COLLECTIONS_JSON": COLLECTIONS})
    def test_temperature_is_not_sent_by_default(self, s3):
        put_text(s3)
        bedrock = MagicMock()
        bedrock.converse.return_value = model_answer()
        with patch.object(extract, "_bedrock", bedrock):
            extract.handler(fields_event(), None)
        assert "temperature" not in bedrock.converse.call_args.kwargs["inferenceConfig"]
        assert bedrock.converse.call_args.kwargs["modelId"] == "apac.amazon.nova-pro-v1:0"

    @patch.dict(os.environ, {**ENV, "COLLECTIONS_JSON": COLLECTIONS, "BEDROCK_TEMPERATURE": "0"})
    def test_temperature_is_sent_when_configured(self, s3):
        put_text(s3)
        bedrock = MagicMock()
        bedrock.converse.return_value = model_answer()
        with patch.object(extract, "_bedrock", bedrock):
            extract.handler(fields_event(), None)
        assert bedrock.converse.call_args.kwargs["inferenceConfig"]["temperature"] == 0.0

    @patch.dict(os.environ, {**ENV, "COLLECTIONS_JSON": COLLECTIONS})
    def test_unreadable_model_output_is_a_failed_result_not_an_exception(self, s3):
        put_text(s3)
        bedrock = MagicMock()
        bedrock.converse.return_value = {"output": {"message": {"content": [{"text": "申し訳ありません"}]}}}
        with patch.object(extract, "_bedrock", bedrock):
            result = extract.handler(fields_event(), None)
        assert result == {"status": "failed", "error": "UnreadableModelOutput"}

    @patch.dict(os.environ, {**ENV, "COLLECTIONS_JSON": COLLECTIONS})
    def test_throttling_is_raised_so_step_functions_retries(self, s3):
        put_text(s3)
        bedrock = MagicMock()
        bedrock.converse.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "m"}}, "Converse"
        )
        with patch.object(extract, "_bedrock", bedrock), pytest.raises(BedrockThrottled):
            extract.handler(fields_event(), None)

    @patch.dict(os.environ, {**ENV, "COLLECTIONS_JSON": COLLECTIONS})
    def test_a_rejected_request_is_a_failed_result(self, s3):
        put_text(s3)
        bedrock = MagicMock()
        bedrock.converse.side_effect = ClientError(
            {"Error": {"Code": "ValidationException", "Message": "m"}}, "Converse"
        )
        with patch.object(extract, "_bedrock", bedrock):
            result = extract.handler(fields_event(), None)
        assert result == {"status": "failed", "error": "ValidationException"}

    @patch.dict(os.environ, {**ENV, "COLLECTIONS_JSON": json.dumps({"invoices": {"prefix": "x/"}})})
    def test_a_collection_without_fields_is_a_configuration_error(self, s3):
        put_text(s3)
        with patch.object(extract, "_bedrock", MagicMock()), pytest.raises(InvalidConfiguration):
            extract.handler(fields_event(), None)


# ---------------------------------------------------------------------------
# field extraction x report (Requirement 6.4 and 6.5)
# ---------------------------------------------------------------------------


def run_report(records: list[dict]) -> dict:
    with patch.object(report, "_sns", MagicMock()):
        return report.handler(event(records), None)


class TestFieldsEscalation:
    @patch.dict(os.environ, ENV)
    def test_an_ungrounded_field_sends_an_auto_approved_document_to_review(self, s3):
        record = done("a.png", fields=completed_fields(4, 1))
        store_fields(s3, record, {"請求書番号": ("INV-1", True), "支払期限": (None, False)})
        result = run_report([record])

        view = result["documents"][0]
        assert view["action"] == "HUMAN_REVIEW"  # the OCR alone said AUTO_APPROVE
        assert "1 of 4 requested fields have no matching evidence" in view["review_reason"]
        assert result["review_queue"] == ["a.png"]
        assert result["summary"]["review_required"] == 1
        manifest = json.loads(s3.get_object(Bucket=RESULTS, Key="invoices/exec-1/manifest.json")["Body"].read())
        assert manifest["documents"][0]["action"] == "HUMAN_REVIEW"

    @patch.dict(os.environ, ENV)
    def test_fully_grounded_fields_leave_the_decision_alone(self, s3):
        record = done("a.png", fields=completed_fields(2, 0))
        store_fields(s3, record, {"請求書番号": ("INV-1", True), "合計金額": ("¥1", True)})
        result = run_report([record])
        view = result["documents"][0]
        assert view["action"] == "AUTO_APPROVE"
        assert "review_reason" not in view
        assert result["review_queue"] == []
        assert result["summary"]["review_required"] == 0

    @patch.dict(os.environ, ENV)
    def test_a_rejected_document_stays_rejected_and_both_reasons_are_kept(self, s3):
        record = done("a.png", "REJECT", fields=completed_fields(2, 2))
        store_fields(s3, record, {"請求書番号": (None, False), "合計金額": (None, False)})
        view = run_report([record])["documents"][0]
        assert view["action"] == "REJECT"
        assert view["review_reason"].startswith("r; 2 of 2 requested fields")  # OCR reason first

    @patch.dict(os.environ, ENV)
    def test_a_document_already_in_review_keeps_its_reason(self, s3):
        view = run_report([done("a.png", "HUMAN_REVIEW")])["documents"][0]
        assert view["action"] == "HUMAN_REVIEW"
        assert view["review_reason"] == "r"

    @patch.dict(os.environ, ENV)
    def test_a_failed_extraction_also_goes_to_review_and_says_why(self, s3):
        """Fields were wanted but could not be produced; a person must not be skipped silently."""
        failed = {"status": "failed", "error": "UnreadableModelOutput"}
        view = run_report([done("a.png", fields=failed)])["documents"][0]
        assert view["action"] == "HUMAN_REVIEW"
        assert view["review_reason"] == "field extraction failed (UnreadableModelOutput)"
        assert view["fields"] == failed

    @patch.dict(os.environ, ENV)
    def test_extraction_not_requested_changes_nothing(self, s3):
        view = run_report([done("a.png")])["documents"][0]
        assert view["action"] == "AUTO_APPROVE"
        assert "fields" not in view

    @patch.dict(os.environ, ENV)
    def test_a_document_that_failed_ocr_has_no_fields_and_no_action(self, s3):
        view = run_report([failed_lambda("b.png")])["documents"][0]
        assert view["status"] == "failed"
        assert "action" not in view and "fields" not in view

    @patch.dict(os.environ, ENV)
    def test_the_decision_does_not_depend_on_reading_fields_json(self, s3):
        """The state's counts decide. fields.json only adds the values for the agent."""
        record = done("a.png", fields=completed_fields(4, 1))  # nothing stored
        view = run_report([record])["documents"][0]
        assert view["action"] == "HUMAN_REVIEW"
        assert view["fields"] == {"status": "completed", "ungrounded_count": 1, "values_unavailable": True}

    @patch.dict(os.environ, ENV)
    def test_a_corrupt_fields_json_is_tolerated(self, s3):
        record = done("a.png", fields=completed_fields(1, 0))
        s3.put_object(Bucket=RESULTS, Key=f"invoices/exec-1/{record['doc_id']}/fields.json", Body=b"{not json")
        view = run_report([record])["documents"][0]
        assert view["action"] == "AUTO_APPROVE"
        assert view["fields"]["values_unavailable"] is True

    @patch.dict(os.environ, ENV)
    def test_the_agent_gets_short_values_and_the_ungrounded_names_but_no_evidence(self, s3):
        record = done("a.png", fields=completed_fields(3, 1))
        store_fields(s3, record, {"請求書番号": ("INV-1", True), "備考": ("あ" * 100, True), "支払期限": (None, False)})
        result = run_report([record])
        fields = result["documents"][0]["fields"]
        assert fields["values"]["請求書番号"] == "INV-1"
        assert fields["values"]["備考"] == "あ" * 60 + "…"  # cut, and visibly so
        assert fields["values"]["支払期限"] is None
        assert fields["ungrounded"] == ["支払期限"]
        assert "EVIDENCE" not in json.dumps(result, ensure_ascii=False)

    @patch.dict(os.environ, {**ENV, "SNS_TOPIC_ARN": "arn:aws:sns:ap-northeast-1:123456789012:t"})
    def test_the_notification_counts_a_document_escalated_by_its_fields(self, s3):
        sns = MagicMock()
        with patch.object(report, "_sns", sns):
            report.handler(event([done("a.png", fields=completed_fields(4, 1))]), None)
        assert sns.publish.call_args.kwargs["Subject"].startswith("[REVIEW 1]")

    @patch.dict(os.environ, ENV)
    def test_escalated_documents_are_listed_before_approved_ones_when_the_list_is_cut(self, s3):
        records = [done("ok.png"), done("esc.png", fields=completed_fields(4, 1))]
        assert [d["key"] for d in run_report(records)["documents"]] == ["esc.png", "ok.png"]

    @patch.dict(os.environ, {**ENV, "COLLECTIONS_JSON": COLLECTIONS})
    def test_what_extract_fields_writes_is_what_report_reads(self, s3):
        """Chain the two real handlers so a change to one side's shape cannot pass unnoticed."""
        put_text(s3)
        bedrock = MagicMock()
        bedrock.converse.return_value = model_answer(
            請求書番号={"value": "INV-2026-0001", "evidence": "請求書番号: INV-2026-0001"},
            発行日={"value": "2026年10月15日", "evidence": "発行日: 2026年10月15日"},
            合計金額={"value": "¥485,100", "evidence": "合計金額 (税込) ¥485,100"},
            支払期限={"value": None, "evidence": None},
        )
        with patch.object(extract, "_bedrock", bedrock):
            state_record = extract.handler(fields_event(), None)
        record = done("a.png", fields=state_record)
        record["doc_id"] = "abc"

        view = run_report([record])["documents"][0]
        assert view["action"] == "HUMAN_REVIEW"
        assert view["fields"]["values"]["合計金額"] == "¥485,100"
        assert view["fields"]["ungrounded"] == ["支払期限"]
