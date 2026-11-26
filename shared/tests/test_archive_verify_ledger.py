"""Ledger behaviour: conditional transitions are what stop a second delete."""

from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from shared.archive_verify import ledger as L


@pytest.fixture
def ledger(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    with mock_aws():
        boto3.client("dynamodb").create_table(
            TableName="t",
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": "runId", "AttributeType": "S"},
                {"AttributeName": "key", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "runId", "KeyType": "HASH"},
                {"AttributeName": "key", "KeyType": "RANGE"},
            ],
        )
        yield L.Ledger("t")


def test_put_get_roundtrip_returns_plain_ints(ledger):
    ledger.put("r", "k", L.RECORDED, size=5, isLarge=False, sha256="ab")
    item = ledger.get("r", "k")
    assert item["size"] == 5 and isinstance(item["size"], int)
    assert item["status"] == L.RECORDED


def test_none_attributes_are_not_written(ledger):
    ledger.put("r", "k", L.RECORDED, attrs=None)
    assert "attrs" not in ledger.get("r", "k")


def test_update_requires_existing_item(ledger):
    assert ledger.update("r", "missing", L.FAILED) is False
    assert ledger.get("r", "missing") is None


def test_update_only_if_status(ledger):
    ledger.put("r", "k", L.VERIFIED)
    assert ledger.update("r", "k", L.DELETED, only_if_status=L.RECORDED) is False
    assert ledger.get("r", "k")["status"] == L.VERIFIED
    assert ledger.update("r", "k", L.DELETED, only_if_status=(L.RECORDED, L.VERIFIED), deletedBy="a") is True
    assert ledger.get("r", "k")["deletedBy"] == "a"


def test_only_one_of_two_claims_wins(ledger):
    ledger.put("r", "k", L.VERIFIED)
    first = ledger.update("r", "k", "DELETING", only_if_status=L.VERIFIED)
    second = ledger.update("r", "k", "DELETING", only_if_status=L.VERIFIED)
    assert (first, second) == (True, False)


def test_query_run_filters_and_paginates(ledger):
    for i in range(30):
        ledger.put("r", f"dir/{i:03}", L.VERIFIED if i % 2 else L.MISMATCH, size=i)
    ledger.put("other", "x", L.VERIFIED)
    assert len(ledger.query_run("r")) == 30
    assert len(ledger.query_run("r", status=L.VERIFIED)) == 15
    assert len(ledger.query_run("r", key_prefix="dir/00")) == 10


def test_also_if_requires_the_attribute_to_match(ledger):
    ledger.put("r", "k", L.DELETING, claimedBy="exec-1")
    assert ledger.update("r", "k", L.DELETED, only_if_status=L.DELETING, also_if={"claimedBy": "exec-2"}) is False
    assert ledger.get("r", "k")["status"] == L.DELETING
    assert ledger.update("r", "k", L.DELETED, only_if_status=L.DELETING, also_if={"claimedBy": "exec-1"}) is True


def test_has_items(ledger):
    assert ledger.has_items("r") is False
    ledger.put("r", "k", L.VERIFIED)
    assert ledger.has_items("r") is True and ledger.has_items("other") is False


def test_status_values_for_the_new_states_are_distinct():
    names = [L.APPROVED, L.DELETING, L.SKIPPED_TOO_LARGE, L.RESTORE_VERIFIED, L.RESTORE_MISMATCH]
    assert len(set(names)) == 5
