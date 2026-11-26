"""Ledger transitions, approval manifest, summary."""

from __future__ import annotations

import json

import boto3
import pytest
from avd_support import ARCHIVE, load_handler

from shared.archive_verify import ledger as L
from shared.archive_verify.checksums import CRC64NVME, SHA256
from shared.archive_verify.runtime import RuntimeConfig
from shared.exceptions import InvalidInput

ledger_fn = load_handler("ledger")
approval = load_handler("approval")
summarize = load_handler("summarize")


def _seed(ledger, key="a", large=False, **extra):
    fields = {
        "size": 5,
        "etag": '"e"',
        "isLarge": large,
        "sha256B64": "SHA=",
        "crc64nvme": "CRC=",
        "archiveKey": f"data/{key}",
        "secondCopyRequired": False,
        **extra,
    }
    ledger.put("r1", key, L.RECORDED, **fields)


def _compare(ledger, head, target="archive", key="a", ctx=None):
    return ledger_fn.handler({"action": "compare", "runId": "r1", "key": key, "head": head, "target": target}, ctx)


GOOD_SHA = {"ContentLength": 5, "ChecksumSHA256": "SHA=", "ChecksumType": "FULL_OBJECT"}
GOOD_CRC = {"ContentLength": 5, "ChecksumCRC64NVME": "CRC=", "ChecksumType": "FULL_OBJECT"}


def test_compare_marks_verified_with_sha256_for_small_files(ledger, lambda_context):
    _seed(ledger)
    out = _compare(ledger, GOOD_SHA, ctx=lambda_context)
    assert out["verified"] and out["algorithm"] == SHA256
    assert ledger.get("r1", "a")["status"] == L.VERIFIED


def test_compare_uses_crc64nvme_for_large_files(ledger, lambda_context):
    _seed(ledger, large=True)
    out = _compare(ledger, GOOD_CRC, ctx=lambda_context)
    assert out["verified"] and out["algorithm"] == CRC64NVME


def test_compare_marks_mismatch_and_keeps_the_reason(ledger, lambda_context):
    _seed(ledger)
    out = _compare(ledger, {**GOOD_SHA, "ChecksumSHA256": "OTHER="}, ctx=lambda_context)
    assert not out["verified"]
    item = ledger.get("r1", "a")
    assert item["status"] == L.MISMATCH and "differs" in item["verifyReason"]


def test_compare_without_a_checksum_is_a_mismatch(ledger, lambda_context):
    _seed(ledger)
    assert not _compare(ledger, {"ContentLength": 5}, ctx=lambda_context)["verified"]
    assert ledger.get("r1", "a")["status"] == L.MISMATCH


def test_compare_does_not_resurrect_a_changed_item(ledger, lambda_context):
    _seed(ledger)
    ledger.update("r1", "a", L.CHANGED)
    _compare(ledger, GOOD_SHA, ctx=lambda_context)
    assert ledger.get("r1", "a")["status"] == L.CHANGED


def test_second_copy_mismatch_withdraws_the_file_from_deletion(ledger, lambda_context):
    _seed(ledger, secondCopy=None)
    _compare(ledger, GOOD_SHA, ctx=lambda_context)
    _compare(ledger, {**GOOD_SHA, "ChecksumSHA256": "BAD="}, target="second", ctx=lambda_context)
    item = ledger.get("r1", "a")
    assert item["status"] == L.MISMATCH and item["secondCopy"] == L.MISMATCH


def test_second_copy_match_records_it(ledger, lambda_context):
    _seed(ledger)
    _compare(ledger, GOOD_SHA, ctx=lambda_context)
    _compare(ledger, GOOD_SHA, target="second", ctx=lambda_context)
    item = ledger.get("r1", "a")
    assert item["status"] == L.VERIFIED and item["secondCopy"] == L.VERIFIED


def test_compare_unknown_item_is_an_error(ledger, lambda_context):
    with pytest.raises(InvalidInput):
        _compare(ledger, GOOD_SHA, key="nope", ctx=lambda_context)


@pytest.mark.parametrize(
    "error,expected",
    [
        ("S3.S3Exception: At least one of the pre-conditions you specified did not hold (Status Code: 412)", L.CHANGED),
        ("PreconditionFailed", L.CHANGED),
        ("States.Timeout", L.FAILED),
    ],
)
def test_mark_classifies_precondition_failures_as_changed(ledger, lambda_context, error, expected):
    _seed(ledger)
    ledger_fn.handler({"action": "mark", "runId": "r1", "key": "a", "error": error}, lambda_context)
    assert ledger.get("r1", "a")["status"] == expected


def test_mark_creates_an_item_that_never_reached_the_ledger(ledger, lambda_context):
    ledger_fn.handler({"action": "mark", "runId": "r1", "key": "new", "error": "boom"}, lambda_context)
    assert ledger.get("r1", "new")["status"] == L.FAILED


def test_mark_does_not_touch_a_deleted_item(ledger, lambda_context):
    _seed(ledger)
    ledger.update("r1", "a", L.DELETED)
    ledger_fn.handler({"action": "mark", "runId": "r1", "key": "a", "error": "late"}, lambda_context)
    assert ledger.get("r1", "a")["status"] == L.DELETED


# ---------------------------------------------------------------- approval


def test_prepare_lists_only_deletable_files(aws, ledger):
    _seed(ledger, "ok")
    ledger.update("r1", "ok", L.VERIFIED)
    _seed(ledger, "needs-second", secondCopyRequired=True)
    ledger.update("r1", "needs-second", L.VERIFIED)
    _seed(ledger, "bad")
    ledger.update("r1", "bad", L.MISMATCH)
    out = approval.prepare(RuntimeConfig.from_env(), {"runId": "r1", "dryRun": True, "storageClass": "GLACIER"}, ledger)
    assert (out["count"], out["excluded"]) == (1, 2)
    manifest = json.loads(aws.get_object(Bucket=ARCHIVE, Key=out["manifestKey"])["Body"].read())
    assert [f["key"] for f in manifest["files"]] == ["ok"]
    assert {n["key"] for n in manifest["notDeletable"]} == {"needs-second", "bad"}
    assert manifest["totalBytes"] == 5 and manifest["runId"] == "r1"
    items = json.loads(aws.get_object(Bucket=ARCHIVE, Key=out["itemsKey"])["Body"].read())
    assert items == [{"key": "ok"}]


def test_request_stores_the_token_in_ssm_and_keeps_it_out_of_the_message(aws, monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")
    sns = boto3.client("sns")
    topic = sns.create_topic(Name="t")["TopicArn"]
    sqs = boto3.client("sqs")
    q = sqs.create_queue(QueueName="q")["QueueUrl"]
    sns.subscribe(
        TopicArn=topic,
        Protocol="sqs",
        Endpoint=sqs.get_queue_attributes(QueueUrl=q, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"],
    )
    monkeypatch.setenv("SNS_TOPIC_ARN", topic)
    cfg = RuntimeConfig.from_env()
    token = "SECRET-TASK-TOKEN-123"
    approval.request(
        cfg,
        {
            "runId": "r1",
            "taskToken": token,
            "prepared": {"count": 3, "totalBytes": 15, "manifestKey": "manifests/r1.json"},
            "dryRun": False,
            "executionArn": "arn:aws:states:ap-northeast-1:123456789012:execution:m:e",
        },
    )
    param = boto3.client("ssm").get_parameter(Name="/avd-test/approvals/r1", WithDecryption=True)["Parameter"]
    assert param["Value"] == token and param["Type"] == "SecureString"
    body = sqs.receive_message(QueueUrl=q, MaxNumberOfMessages=1)["Messages"][0]["Body"]
    assert token not in body
    assert "send-task-success" in body and "/avd-test/approvals/r1" in body and "manifests/r1.json" in body


def test_request_requires_a_token(aws):
    with pytest.raises(InvalidInput):
        approval.request(RuntimeConfig.from_env(), {"runId": "r1", "prepared": {}})


# ---------------------------------------------------------------- summary


def test_summary_counts_by_status_and_lists_exceptions():
    items = [
        {"key": "a", "size": 10, "status": L.DELETED},
        {"key": "b", "size": 20, "status": L.VERIFIED},
        {"key": "c", "size": 5, "status": L.MISMATCH},
        {"key": "d", "size": 5, "status": L.CHANGED},
        {"key": "e", "size": 5, "status": L.FAILED},
    ]
    s = summarize.build_summary("r1", "COMPLETED", items, {"dryRun": False})
    assert s["filesByStatus"] == {L.DELETED: 1, L.VERIFIED: 1, L.MISMATCH: 1, L.CHANGED: 1, L.FAILED: 1}
    assert (s["bytesVerified"], s["bytesDeleted"]) == (30, 10)
    assert (s["mismatches"], s["changed"], s["failed"]) == (["c"], ["d"], ["e"])
    assert s["dataClassification"] == "operational-metadata"


def test_summarize_handler_writes_result_and_removes_the_token(aws, ledger, lambda_context, monkeypatch):
    _seed(ledger)
    ledger.update("r1", "a", L.VERIFIED)
    ssm = boto3.client("ssm")
    ssm.put_parameter(Name="/avd-test/approvals/r1", Value="t", Type="SecureString")
    out = summarize.handler({"runId": "r1", "outcome": "DRY_RUN_COMPLETED", "dryRun": True}, lambda_context)
    result = json.loads(aws.get_object(Bucket=ARCHIVE, Key=out["resultKey"])["Body"].read())
    assert result["outcome"] == "DRY_RUN_COMPLETED" and result["filesByStatus"] == {L.VERIFIED: 1}
    with pytest.raises(ssm.exceptions.ParameterNotFound):
        ssm.get_parameter(Name="/avd-test/approvals/r1")
