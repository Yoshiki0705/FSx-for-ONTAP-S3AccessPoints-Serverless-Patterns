"""The stored task token: encrypted with the stack's key, deleted when it has been used or cannot be.

A task token is a bearer credential for one approval. It sits in an SSM SecureString while the run
waits. It must not stay readable after the run was approved, rejected, timed out or failed.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import boto3
import pytest
from avd_support import ARCHIVE, load_handler

from shared.archive_verify import ledger as L
from shared.archive_verify.runtime import RuntimeConfig

approval = load_handler("approval")
watchdog = load_handler("watchdog")
summarize = load_handler("summarize")

STARTER = "arn:aws:iam::123456789012:user/starter"
APPROVER = "arn:aws:iam::123456789012:user/approver"
CLAIM = "arn:aws:states:ap-northeast-1:123456789012:execution:avd-archive:exec-1"
PARAM = "/avd-test/approvals/run1"


def _store_token(value="TOKEN"):
    boto3.client("ssm").put_parameter(Name=PARAM, Value=value, Type="SecureString")


def _token_exists() -> bool:
    ssm = boto3.client("ssm")
    try:
        ssm.get_parameter(Name=PARAM)
        return True
    except ssm.exceptions.ParameterNotFound:
        return False


def _event(aws, approver=APPROVER, requested_by=STARTER):
    aws.put_object(Bucket=ARCHIVE, Key="manifests/run1-items.json", Body=json.dumps([{"key": "a"}]).encode())
    return {
        "runId": "run1",
        "approval": {"approved": True, "approver": approver},
        "requestedBy": requested_by,
        "bucket": ARCHIVE,
        "itemsKey": "manifests/run1-items.json",
        "executionArn": CLAIM,
    }


def test_the_token_is_stored_with_the_stack_key_when_one_is_configured(aws, monkeypatch):
    monkeypatch.setenv("APPROVAL_TOKEN_KEY_ID", "alias/aws/ssm")
    topic = boto3.client("sns").create_topic(Name="t")["TopicArn"]
    monkeypatch.setenv("SNS_TOPIC_ARN", topic)
    approval.request(
        RuntimeConfig.from_env(),
        {
            "runId": "run1",
            "taskToken": "T",
            "prepared": {"count": 1, "totalBytes": 1, "manifestKey": "m"},
            "dryRun": True,
        },
    )
    described = boto3.client("ssm").describe_parameters(ParameterFilters=[{"Key": "Name", "Values": [PARAM]}])
    assert described["Parameters"][0]["KeyId"] == "alias/aws/ssm"


def test_the_token_is_deleted_once_the_approval_is_recorded(aws, ledger):
    ledger.put("run1", "a", L.VERIFIED, size=1, etag='"e"')
    _store_token()
    out = approval.approve(RuntimeConfig.from_env(), _event(aws), ledger=ledger)
    assert out["approved"] is True
    assert not _token_exists()


def test_the_token_is_deleted_when_the_approval_is_refused(aws, ledger):
    ledger.put("run1", "a", L.VERIFIED, size=1, etag='"e"')
    _store_token()
    out = approval.approve(RuntimeConfig.from_env(), _event(aws, approver=STARTER), ledger=ledger)
    assert out["reason"] == "SELF_APPROVAL"
    assert not _token_exists()


def test_a_missing_token_does_not_fail_the_approval(aws, ledger):
    ledger.put("run1", "a", L.VERIFIED, size=1, etag='"e"')
    assert approval.approve(RuntimeConfig.from_env(), _event(aws), ledger=ledger)["approved"] is True


def test_summarize_deletes_the_token_after_a_rejection_or_timeout(aws, ledger, lambda_context):
    """Rejection and timeout both end in a summarize state (the state machine tests pin that)."""
    _store_token()
    summarize.handler({"runId": "run1", "outcome": "REJECTED_OR_TIMED_OUT"}, lambda_context)
    assert not _token_exists()


class _Ssm:
    def __init__(self, ages_hours):
        now = datetime.now(timezone.utc)
        self.params = {f"/s/approvals/r{i}": now - timedelta(hours=h) for i, h in enumerate(ages_hours)}
        self.deleted: list[str] = []

    def get_parameters_by_path(self, **kw):
        return {"Parameters": [{"Name": n, "LastModifiedDate": t} for n, t in self.params.items()]}

    def delete_parameter(self, Name):  # noqa: N803 - boto3's argument name
        self.deleted.append(Name)


def test_the_watchdog_deletes_a_token_older_than_the_approval_timeout_plus_a_grace_hour():
    ssm = _Ssm([1, 30, 80])
    hours = watchdog.oldest_pending_hours(ssm, "/s/approvals", expire_after_hours=73)
    assert ssm.deleted == ["/s/approvals/r2"]
    assert hours == pytest.approx(80, abs=0.1)  # the age is reported before the token is removed


def test_the_watchdog_deletes_nothing_without_a_limit():
    ssm = _Ssm([500])
    watchdog.oldest_pending_hours(ssm, "/s/approvals")
    assert ssm.deleted == []
