"""Unit tests for the OCR handlers: ocr_sync, async_start, async_check, async_collect.

Textract is replaced by a stub that returns the real responses stored under fixtures/ (captured
from ap-northeast-1 on 2026-11-03), so the handlers see the shapes the service produces. S3 is moto.
"""

from __future__ import annotations

import json
import os
import time
from unittest.mock import MagicMock, patch

import boto3
import pytest
from botocore.exceptions import ClientError
from helpers import FIXTURES_DIR, load_handler
from moto import mock_aws

from shared.exceptions import TextractRejected, TextractThrottled, TextractTransient
from shared.textract_helper import client_request_token

SOURCE = "source-bucket"
STAGING = "staging-bucket"
RESULTS = "results-bucket"
ENV = {
    "S3_ACCESS_POINT_ALIAS": SOURCE,
    "STAGING_BUCKET": STAGING,
    "OUTPUT_BUCKET": RESULTS,
    "OUTPUT_DESTINATION": "STANDARD_S3",
    "ASYNC_JOB_MAX_SECONDS": "600",
    "AWS_DEFAULT_REGION": "ap-northeast-1",
}
sync_mod = load_handler("ocr_sync")
start_mod = load_handler("async_start")
check_mod = load_handler("async_check")
collect_mod = load_handler("async_collect")


def fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / f"{name}.json").read_text(encoding="utf-8"))


def client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "m"}}, "Op")


def doc(key: str = "scans/invoices/請求書.png", size: int = 1000) -> dict:
    return {
        "key": key,
        "size": size,
        "doc_id": "0123456789abcdef",
        "last_modified": "2026-11-01T00:00:00+00:00",
        "etag": '"e"',
    }


def sync_event(profile: str = "structure", **extra: object) -> dict:
    return {
        "doc": doc(),
        "profile": profile,
        "output_prefix": "invoices/exec-1",
        "classification": "RESTRICTED",
        "collection": "invoices",
        **extra,
    }


@pytest.fixture
def s3():
    with mock_aws():
        client = boto3.client("s3", region_name="ap-northeast-1")
        for bucket in (SOURCE, STAGING, RESULTS):
            client.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"})
        client.put_object(Bucket=SOURCE, Key="scans/invoices/請求書.png", Body=b"png-bytes")
        client.put_object(Bucket=SOURCE, Key="scans/invoices/契約書.pdf", Body=b"%PDF-" + b"x" * 100)
        yield client


def stored_json(s3, key: str) -> dict:
    return json.loads(s3.get_object(Bucket=RESULTS, Key=key)["Body"].read())


# ---------------------------------------------------------------------------
# ocr_sync
# ---------------------------------------------------------------------------


class TestOcrSync:
    @patch.dict(os.environ, ENV)
    def test_structure_profile_calls_analyze_document_with_tables_and_layout(self, s3):
        stub = MagicMock()
        stub.analyze_document.return_value = fixture("invoice-ja-001-analyze")
        stub.meta.region_name = "ap-northeast-1"
        with patch.object(sync_mod, "_textract", stub):
            record = sync_mod.handler(sync_event("structure"), None)

        _, kwargs = stub.analyze_document.call_args
        assert kwargs["Document"] == {"Bytes": b"png-bytes"}  # inline bytes, never an S3Object reference
        assert kwargs["FeatureTypes"] == ["TABLES", "LAYOUT"]
        stub.detect_document_text.assert_not_called()
        assert record["status"] == "completed"
        assert record["api"] == "AnalyzeDocument"
        assert record["pages"] == 1
        assert record["human_review"]["requires_review"] is True  # the wrongly merged totals cell
        assert record["result"] == f"s3://{RESULTS}/invoices/exec-1/0123456789abcdef/result.json"

    @patch.dict(os.environ, ENV)
    def test_text_profile_calls_detect_document_text_and_never_forms(self, s3):
        stub = MagicMock()
        stub.detect_document_text.return_value = fixture("memo-ja-001-detect")
        stub.meta.region_name = "ap-northeast-1"
        with patch.object(sync_mod, "_textract", stub):
            record = sync_mod.handler(sync_event("text"), None)
        stub.analyze_document.assert_not_called()
        assert stub.detect_document_text.call_args.kwargs == {"Document": {"Bytes": b"png-bytes"}}
        assert record["api"] == "DetectDocumentText"

    @patch.dict(os.environ, ENV)
    def test_outputs_carry_the_source_the_model_version_and_the_classification(self, s3):
        stub = MagicMock()
        stub.analyze_document.return_value = fixture("invoice-ja-001-analyze")
        stub.meta.region_name = "ap-northeast-1"
        with patch.object(sync_mod, "_textract", stub):
            sync_mod.handler(sync_event("structure"), None)
        result = stored_json(s3, "invoices/exec-1/0123456789abcdef/result.json")
        assert result["source"]["key"] == "scans/invoices/請求書.png"  # the original key stays in the JSON
        assert result["textract"]["region"] == "ap-northeast-1"
        assert result["textract"]["model_version"] == "1.0"
        assert result["textract"]["features"] == ["TABLES", "LAYOUT"]
        assert result["data_classification"] == "RESTRICTED"
        text = s3.get_object(Bucket=RESULTS, Key="invoices/exec-1/0123456789abcdef/text.txt")["Body"].read()
        assert "請求書番号" in text.decode("utf-8")

    @patch.dict(os.environ, ENV)
    def test_the_state_record_carries_no_ocr_text(self, s3):
        stub = MagicMock()
        stub.analyze_document.return_value = fixture("invoice-ja-001-analyze")
        stub.meta.region_name = "ap-northeast-1"
        with patch.object(sync_mod, "_textract", stub):
            record = sync_mod.handler(sync_event("structure"), None)
        dumped = json.dumps(record, ensure_ascii=False)
        assert "INV-2026-0001" not in dumped
        assert len(dumped.encode("utf-8")) < 1024

    @patch.dict(os.environ, ENV)
    @pytest.mark.parametrize("code", ["ThrottlingException", "ProvisionedThroughputExceededException"])
    def test_throttling_is_raised_for_step_functions_to_retry(self, s3, code):
        stub = MagicMock()
        stub.analyze_document.side_effect = client_error(code)
        with patch.object(sync_mod, "_textract", stub), pytest.raises(TextractThrottled):
            sync_mod.handler(sync_event(), None)

    @patch.dict(os.environ, ENV)
    def test_transient_failure_is_raised_for_step_functions_to_retry(self, s3):
        stub = MagicMock()
        stub.analyze_document.side_effect = client_error("InternalServerError")
        with patch.object(sync_mod, "_textract", stub), pytest.raises(TextractTransient):
            sync_mod.handler(sync_event(), None)

    @patch.dict(os.environ, ENV)
    @pytest.mark.parametrize("code", ["UnsupportedDocumentException", "BadDocumentException", "AccessDeniedException"])
    def test_a_rejected_document_is_a_failed_record_not_an_exception(self, s3, code):
        stub = MagicMock()
        stub.analyze_document.side_effect = client_error(code)
        with patch.object(sync_mod, "_textract", stub):
            record = sync_mod.handler(sync_event(), None)
        assert record["status"] == "failed"
        assert record["error"]["type"] == code
        assert s3.list_objects_v2(Bucket=RESULTS).get("KeyCount", 0) == 0

    @patch.dict(os.environ, ENV)
    def test_a_missing_source_is_a_failed_record(self, s3):
        event = sync_event()
        event["doc"]["key"] = "scans/invoices/消えた.png"
        with patch.object(sync_mod, "_textract", MagicMock()):
            record = sync_mod.handler(event, None)
        assert record["status"] == "failed"
        assert record["error"]["type"] == "404"

    @patch.dict(os.environ, ENV)
    def test_an_object_over_the_inline_limit_is_a_failed_record(self, s3):
        s3.put_object(Bucket=SOURCE, Key="scans/invoices/big.png", Body=b"x" * (5 * 1024 * 1024 + 1))
        event = sync_event()
        event["doc"]["key"] = "scans/invoices/big.png"
        with patch.object(sync_mod, "_textract", MagicMock()):
            record = sync_mod.handler(event, None)
        assert record["error"]["type"] == "ObjectTooLargeForInlineAnalysis"

    @patch.dict(os.environ, ENV)
    def test_a_transient_s3_error_is_raised_not_recorded(self, s3):
        from shared.exceptions import S3ApHelperError

        with (
            patch.object(sync_mod, "S3ApHelper") as helper,
            patch.object(sync_mod, "_textract", MagicMock()),
            pytest.raises(S3ApHelperError),
        ):
            helper.return_value.get_object_bytes.side_effect = S3ApHelperError("slow", error_code="SlowDown")
            sync_mod.handler(sync_event(), None)

    @patch.dict(os.environ, {**ENV, "REVIEW_AUTO_APPROVE": "0.5", "LOW_CONFIDENCE_CHAR_RATIO": "1"})
    def test_review_thresholds_come_from_the_environment(self, s3):
        stub = MagicMock()
        stub.detect_document_text.return_value = fixture("memo-ja-001-detect")
        stub.meta.region_name = "ap-northeast-1"
        with patch.object(sync_mod, "_textract", stub):
            record = sync_mod.handler(sync_event("text"), None)
        assert record["human_review"]["action"] == "AUTO_APPROVE"


# ---------------------------------------------------------------------------
# async_start
# ---------------------------------------------------------------------------


def start_event(profile: str = "structure") -> dict:
    return {
        "doc": doc("scans/invoices/契約書.pdf", 105),
        "profile": profile,
        "execution_name": "exec-1",
        "poll_seconds": 5,
        "collection": "invoices",
    }


class TestAsyncStart:
    @patch.dict(os.environ, ENV)
    def test_copies_to_staging_then_starts_the_job_on_the_staged_object(self, s3):
        stub = MagicMock()
        stub.start_document_analysis.return_value = {"JobId": "job-1"}
        with patch.object(start_mod, "_textract", stub):
            job = start_mod.handler(start_event("structure"), None)

        staged = s3.get_object(Bucket=STAGING, Key="staging/exec-1/0123456789abcdef.pdf")["Body"].read()
        assert staged == b"%PDF-" + b"x" * 100
        kwargs = stub.start_document_analysis.call_args.kwargs
        # The source is an S3 Access Point; Textract is given the staging bucket instead.
        assert kwargs["DocumentLocation"] == {
            "S3Object": {"Bucket": STAGING, "Name": "staging/exec-1/0123456789abcdef.pdf"}
        }
        assert kwargs["FeatureTypes"] == ["TABLES", "LAYOUT"]
        assert kwargs["JobTag"] == "0123456789abcdef"
        assert job["status"] == "started"
        assert job["job_id"] == "job-1"
        assert job["api"] == "StartDocumentAnalysis"
        assert job["poll_index"] == 0
        assert job["wait_seconds"] == 5

    @patch.dict(os.environ, ENV)
    def test_text_profile_uses_start_document_text_detection(self, s3):
        stub = MagicMock()
        stub.start_document_text_detection.return_value = {"JobId": "job-2"}
        with patch.object(start_mod, "_textract", stub):
            job = start_mod.handler(start_event("text"), None)
        stub.start_document_analysis.assert_not_called()
        assert "FeatureTypes" not in stub.start_document_text_detection.call_args.kwargs
        assert job["api"] == "StartDocumentTextDetection"

    @patch.dict(os.environ, ENV)
    def test_request_token_is_deterministic_so_a_retry_does_not_start_a_second_job(self, s3):
        stub = MagicMock()
        stub.start_document_analysis.return_value = {"JobId": "job-1"}
        with patch.object(start_mod, "_textract", stub):
            start_mod.handler(start_event(), None)
            start_mod.handler(start_event(), None)
        tokens = {c.kwargs["ClientRequestToken"] for c in stub.start_document_analysis.call_args_list}
        assert tokens == {client_request_token("exec-1", "0123456789abcdef", "structure")}

    @patch.dict(os.environ, ENV)
    def test_the_profile_is_part_of_the_token(self, s3):
        stub = MagicMock()
        stub.start_document_analysis.return_value = {"JobId": "a"}
        stub.start_document_text_detection.return_value = {"JobId": "b"}
        with patch.object(start_mod, "_textract", stub):
            start_mod.handler(start_event("structure"), None)
            start_mod.handler(start_event("text"), None)
        a = stub.start_document_analysis.call_args.kwargs["ClientRequestToken"]
        b = stub.start_document_text_detection.call_args.kwargs["ClientRequestToken"]
        assert a != b

    @patch.dict(os.environ, ENV)
    def test_rejected_start_removes_the_staged_copy_and_returns_a_failed_record(self, s3):
        stub = MagicMock()
        stub.start_document_analysis.side_effect = client_error("UnsupportedDocumentException")
        with patch.object(start_mod, "_textract", stub):
            record = start_mod.handler(start_event(), None)
        assert record["status"] == "failed"
        assert s3.list_objects_v2(Bucket=STAGING).get("KeyCount", 0) == 0

    @patch.dict(os.environ, ENV)
    @pytest.mark.parametrize(
        "code,exc", [("ThrottlingException", TextractThrottled), ("InternalServerError", TextractTransient)]
    )
    def test_retryable_start_failures_are_raised_and_keep_the_copy_for_the_retry(self, s3, code, exc):
        stub = MagicMock()
        stub.start_document_analysis.side_effect = client_error(code)
        with patch.object(start_mod, "_textract", stub), pytest.raises(exc):
            start_mod.handler(start_event(), None)
        assert s3.list_objects_v2(Bucket=STAGING)["KeyCount"] == 1

    @patch.dict(os.environ, ENV)
    def test_missing_source_is_a_failed_record_and_nothing_is_staged(self, s3):
        event = start_event()
        event["doc"]["key"] = "scans/invoices/消えた.pdf"
        with patch.object(start_mod, "_textract", MagicMock()):
            record = start_mod.handler(event, None)
        assert record["status"] == "failed"
        assert record["error"]["type"] == "NoSuchKey"
        assert s3.list_objects_v2(Bucket=STAGING).get("KeyCount", 0) == 0

    def test_staged_key_has_no_original_path(self):
        key = start_mod.staged_key_for("exec-1", "abc", "請求書/2026年/契約書.PDF")
        assert key == "staging/exec-1/abc.pdf"
        assert key.isascii()


# ---------------------------------------------------------------------------
# async_check
# ---------------------------------------------------------------------------


def job(**overrides: object) -> dict:
    base = {
        "status": "started",
        "job_id": "job-1",
        "api": "StartDocumentAnalysis",
        "staged_key": "staging/exec-1/x.pdf",
        "started_at": int(time.time()),
        "wait_seconds": 5,
        "poll_index": 0,
    }
    return {**base, **overrides}


class TestAsyncCheck:
    def test_wait_schedule_grows_then_holds(self):
        assert [check_mod.next_wait_seconds(i) for i in range(8)] == [5, 10, 15, 20, 30, 30, 30, 30]
        assert check_mod.next_wait_seconds(-3) == 5

    @patch.dict(os.environ, ENV)
    def test_in_progress_returns_the_next_wait(self):
        stub = MagicMock()
        stub.get_document_analysis.return_value = {"JobStatus": "IN_PROGRESS"}
        with patch.object(check_mod, "_textract", stub):
            result = check_mod.handler({"job": job(), "profile": "structure"}, None)
        assert stub.get_document_analysis.call_args.kwargs == {"JobId": "job-1", "MaxResults": 1}
        assert result["status"] == "IN_PROGRESS"
        assert result["poll_index"] == 1
        assert result["wait_seconds"] == 10
        assert result["job_id"] == "job-1"  # the rest of the job survives

    @patch.dict(os.environ, ENV)
    def test_text_profile_polls_the_text_detection_api(self):
        stub = MagicMock()
        stub.get_document_text_detection.return_value = {"JobStatus": "SUCCEEDED"}
        with patch.object(check_mod, "_textract", stub):
            result = check_mod.handler({"job": job(), "profile": "text"}, None)
        stub.get_document_analysis.assert_not_called()
        assert result["status"] == "SUCCEEDED"

    @patch.dict(os.environ, ENV)
    @pytest.mark.parametrize("status", ["SUCCEEDED", "PARTIAL_SUCCESS", "FAILED"])
    def test_terminal_statuses_pass_through(self, status):
        stub = MagicMock()
        stub.get_document_analysis.return_value = {"JobStatus": status, "StatusMessage": "x" * 500}
        with patch.object(check_mod, "_textract", stub):
            result = check_mod.handler({"job": job(), "profile": "structure"}, None)
        assert result["status"] == status
        assert len(result["status_message"]) == 200

    @patch.dict(os.environ, {**ENV, "ASYNC_JOB_MAX_SECONDS": "60"})
    def test_a_job_that_runs_past_the_limit_times_out(self):
        stub = MagicMock()
        stub.get_document_analysis.return_value = {"JobStatus": "IN_PROGRESS"}
        with patch.object(check_mod, "_textract", stub):
            result = check_mod.handler({"job": job(started_at=int(time.time()) - 61), "profile": "structure"}, None)
        assert result["status"] == "TIMED_OUT"

    @patch.dict(os.environ, {**ENV, "ASYNC_JOB_MAX_SECONDS": "60"})
    def test_a_finished_job_is_not_called_a_timeout(self):
        stub = MagicMock()
        stub.get_document_analysis.return_value = {"JobStatus": "SUCCEEDED"}
        with patch.object(check_mod, "_textract", stub):
            result = check_mod.handler({"job": job(started_at=int(time.time()) - 600), "profile": "structure"}, None)
        assert result["status"] == "SUCCEEDED"

    @patch.dict(os.environ, ENV)
    def test_throttling_is_raised(self):
        stub = MagicMock()
        stub.get_document_analysis.side_effect = client_error("ThrottlingException")
        with patch.object(check_mod, "_textract", stub), pytest.raises(TextractThrottled):
            check_mod.handler({"job": job(), "profile": "structure"}, None)

    @patch.dict(os.environ, ENV)
    def test_an_unknown_job_is_rejected(self):
        stub = MagicMock()
        stub.get_document_analysis.side_effect = client_error("InvalidJobIdException")
        with patch.object(check_mod, "_textract", stub), pytest.raises(TextractRejected):
            check_mod.handler({"job": job(), "profile": "structure"}, None)


# ---------------------------------------------------------------------------
# async_collect
# ---------------------------------------------------------------------------


def paged(name: str, parts: int = 2) -> list[dict]:
    """Split one real response into `parts` pages, chained with NextToken, like Get* returns."""
    data = fixture(name)
    blocks = data["Blocks"]
    size = -(-len(blocks) // parts)
    pages = []
    for i in range(parts):
        page = {
            "JobStatus": "SUCCEEDED",
            "DocumentMetadata": data["DocumentMetadata"],
            "Blocks": blocks[i * size : (i + 1) * size],
        }
        for version_key in ("AnalyzeDocumentModelVersion", "DetectDocumentTextModelVersion"):
            if version_key in data:
                page[version_key] = data[version_key]
        if i < parts - 1:
            page["NextToken"] = f"t{i + 1}"
        pages.append(page)
    return pages


def collect_event(status: str = "SUCCEEDED", profile: str = "structure", **extra: object) -> dict:
    return {
        "doc": doc("scans/invoices/契約書.pdf", 105),
        "profile": profile,
        "job": job(status=status, poll_index=3, elapsed_seconds=22),
        "output_prefix": "invoices/exec-1",
        "classification": "RESTRICTED",
        "collection": "invoices",
        **extra,
    }


@pytest.fixture
def staged(s3):
    s3.put_object(Bucket=STAGING, Key="staging/exec-1/x.pdf", Body=b"%PDF-")


class TestAsyncCollect:
    @patch.dict(os.environ, ENV)
    def test_follows_next_token_and_matches_a_single_response(self, s3, staged):
        pages = paged("invoice-ja-001-analyze", parts=3)
        stub = MagicMock()
        stub.get_document_analysis.side_effect = pages
        stub.meta.region_name = "ap-northeast-1"
        with patch.object(collect_mod, "_textract", stub):
            record = collect_mod.handler(collect_event(), None)

        calls = stub.get_document_analysis.call_args_list
        assert [c.kwargs.get("NextToken") for c in calls] == [None, "t1", "t2"]
        assert record["status"] == "completed"
        result = stored_json(s3, "invoices/exec-1/0123456789abcdef/result.json")
        assert result["quality"]["line_count"] == 39  # nothing lost across the page boundaries
        assert result["pages"][0]["tables"][0]["rows"][1][0] == "部品A (精密加工)"
        assert result["textract"]["mode"] == "async"
        assert result["textract"]["job_id"] == "job-1"
        assert result["textract"]["polls"] == 3

    @patch.dict(os.environ, ENV)
    def test_the_staged_copy_is_deleted_on_success(self, s3, staged):
        stub = MagicMock()
        stub.get_document_analysis.side_effect = paged("invoice-ja-001-analyze", parts=1)
        stub.meta.region_name = "ap-northeast-1"
        with patch.object(collect_mod, "_textract", stub):
            collect_mod.handler(collect_event(), None)
        assert s3.list_objects_v2(Bucket=STAGING).get("KeyCount", 0) == 0

    @patch.dict(os.environ, ENV)
    @pytest.mark.parametrize("status,kind", [("FAILED", "JobFailed"), ("TIMED_OUT", "JobTimeout")])
    def test_failed_and_timed_out_jobs_are_failed_records_and_the_copy_is_deleted(self, s3, staged, status, kind):
        stub = MagicMock()
        with patch.object(collect_mod, "_textract", stub):
            record = collect_mod.handler(collect_event(status), None)
        assert record == {"status": "failed", "error": {"type": kind, "message": f"Textract job ended with {status}"}}
        stub.get_document_analysis.assert_not_called()
        assert s3.list_objects_v2(Bucket=STAGING).get("KeyCount", 0) == 0

    @patch.dict(os.environ, ENV)
    def test_a_failed_status_check_cleans_up_and_reports_the_error_type(self, s3, staged):
        event = collect_event("started", check_error={"Error": "TextractThrottled", "Cause": "x" * 5000})
        with patch.object(collect_mod, "_textract", MagicMock()):
            record = collect_mod.handler(event, None)
        assert record["status"] == "failed"
        assert record["error"]["type"] == "TextractThrottled"
        assert "x" * 100 not in json.dumps(record)  # the long Cause is not copied into the state
        assert s3.list_objects_v2(Bucket=STAGING).get("KeyCount", 0) == 0

    @patch.dict(os.environ, ENV)
    def test_partial_success_requires_review(self, s3, staged):
        stub = MagicMock()
        stub.get_document_analysis.side_effect = paged("invoice-ja-002-analyze", parts=1)
        stub.meta.region_name = "ap-northeast-1"
        with patch.object(collect_mod, "_textract", stub):
            record = collect_mod.handler(collect_event("PARTIAL_SUCCESS"), None)
        assert record["status"] == "completed"
        assert "PARTIAL_SUCCESS" in record["human_review"]["reason"]
        assert record["human_review"]["requires_review"] is True

    @patch.dict(os.environ, ENV)
    def test_warnings_are_kept_but_bounded(self, s3, staged):
        page = paged("memo-ja-001-detect", parts=1)[0]
        page["Warnings"] = [{"ErrorCode": "LIMIT_EXCEEDED", "Pages": list(range(1, 200))}] * 9
        stub = MagicMock()
        stub.get_document_text_detection.side_effect = [page]
        stub.meta.region_name = "ap-northeast-1"
        with patch.object(collect_mod, "_textract", stub):
            collect_mod.handler(collect_event(profile="text"), None)
        warnings = stored_json(s3, "invoices/exec-1/0123456789abcdef/result.json")["textract"]["warnings"]
        assert len(warnings) == collect_mod.MAX_WARNINGS
        assert len(warnings[0]["pages"]) == 20

    @patch.dict(os.environ, ENV)
    def test_text_profile_reads_with_get_document_text_detection(self, s3, staged):
        page = paged("memo-ja-001-detect", parts=1)[0]
        stub = MagicMock()
        stub.get_document_text_detection.side_effect = [page]
        stub.meta.region_name = "ap-northeast-1"
        with patch.object(collect_mod, "_textract", stub):
            record = collect_mod.handler(collect_event(profile="text"), None)
        stub.get_document_analysis.assert_not_called()
        assert record["status"] == "completed"

    @patch.dict(os.environ, ENV)
    def test_throttled_reads_are_raised_and_the_copy_is_still_removed(self, s3, staged):
        stub = MagicMock()
        stub.get_document_analysis.side_effect = client_error("ThrottlingException")
        with patch.object(collect_mod, "_textract", stub), pytest.raises(TextractThrottled):
            collect_mod.handler(collect_event(), None)
        # The job already read the document; a retry of this step needs only the results.
        assert s3.list_objects_v2(Bucket=STAGING).get("KeyCount", 0) == 0

    @patch.dict(os.environ, ENV)
    def test_a_job_that_turns_out_failed_while_reading_is_a_failed_record(self, s3, staged):
        stub = MagicMock()
        stub.get_document_analysis.return_value = {"JobStatus": "FAILED", "StatusMessage": "boom"}
        with patch.object(collect_mod, "_textract", stub):
            record = collect_mod.handler(collect_event(), None)
        assert record["status"] == "failed"

    @patch.dict(os.environ, ENV)
    def test_page_chaining_has_a_ceiling(self, s3, staged):
        stub = MagicMock()
        stub.get_document_analysis.return_value = {"JobStatus": "SUCCEEDED", "Blocks": [], "NextToken": "again"}
        with patch.object(collect_mod, "_textract", stub), patch.object(collect_mod, "MAX_RESULT_PAGES", 5):
            record = collect_mod.handler(collect_event(), None)
        assert record["status"] == "failed"
        assert stub.get_document_analysis.call_count == 5
