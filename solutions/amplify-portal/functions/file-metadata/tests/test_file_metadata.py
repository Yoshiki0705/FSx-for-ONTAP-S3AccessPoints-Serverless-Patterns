"""Tests for the boundary on AI-derived metadata.

The records here are summaries of file contents -- a classification, a Bedrock summary,
entity and label counts -- so answering for a key is close to answering about the file.
The keys arrive from the client in a batch.

`shared/tests/test_portal_path_scope.py` covers `key_is_visible` itself. What is
asserted here is that this handler applies it to every key it was handed, and that it
does so by dropping rather than refusing. That choice is the handler's, not the shared
module's: the explorer asks for a whole page at once, so refusing the batch because one
key does not belong would turn a boundary into a broken folder view.

DynamoDB is stubbed. What matters is which keys reach the request and which records come
back, not whether boto3 can reach a table.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

MODULE_PATH = Path(__file__).resolve().parent.parent / "index.py"

TABLE = "ai-metadata"
GROUP_PATH_PREFIXES = {"team-a": ["team-a/"], "team-b": ["team-b/"]}

INSIDE = "team-a/thermal-spec.pdf"
OUTSIDE = "team-b/thermal-spec.pdf"


def load_module(env: dict[str, str] | None = None) -> Any:
    """Import index.py fresh, since its configuration is read at import time.

    Args:
        env: Environment overrides applied on top of the defaults below.

    Returns:
        The freshly imported handler module.
    """
    base = {
        "AI_METADATA_TABLE_NAME": TABLE,
        "GROUP_PATH_PREFIXES": json.dumps(GROUP_PATH_PREFIXES),
        "AWS_REGION": "ap-northeast-1",
    }
    base.update(env or {})
    with patch.dict(os.environ, base, clear=False):
        spec = importlib.util.spec_from_file_location("file_metadata_under_test", MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules["file_metadata_under_test"] = module
        spec.loader.exec_module(module)
    return module


def record(key: str) -> dict:
    """A stored metadata row for `key`.

    Args:
        key: The object key the row describes.

    Returns:
        The item shape the handler reads.
    """
    return {
        "file_key": key,
        "classification": "INTERNAL",
        "bedrock_summary": f"a summary of {key}",
        "processed_at": "2026-08-01T00:00:00Z",
    }


def stub_dynamo(module: Any, rows: list[dict]) -> MagicMock:
    """Answer `batch_get_item` with `rows`, once.

    Args:
        module: The freshly imported handler module.
        rows: Items the table should return.

    Returns:
        The stub `dynamodb` resource, for asserting on the request.
    """
    resource = MagicMock()
    resource.batch_get_item.return_value = {"Responses": {TABLE: rows}, "UnprocessedKeys": {}}
    module.boto3 = MagicMock()
    module.boto3.resource.return_value = resource
    return resource


def call(module: Any, keys: list[str], groups: list[str] | None = None) -> dict:
    """Invoke the handler as the resolver would, with an attributed caller.

    Args:
        module: The freshly imported handler module.
        keys: The object keys being asked about.
        groups: The caller's Cognito groups.

    Returns:
        The handler's response.
    """
    return module.handler({"fileKeys": keys, "groups": groups or []}, None)


def requested_keys(resource: MagicMock) -> list[str]:
    """The keys the handler actually asked the table for.

    Args:
        resource: The stub returned by `stub_dynamo`.

    Returns:
        Each `file_key` in the request, in order.
    """
    request = resource.batch_get_item.call_args.kwargs["RequestItems"]
    return [entry["file_key"] for entry in request[TABLE]["Keys"]]


class TestTheKeyBoundary:
    def test_a_key_outside_the_boundary_is_never_asked_for(self) -> None:
        # Filtering the response would be too late in one respect: the key itself is in
        # the request, and a table with a resource policy or an audit trail sees it.
        module = load_module()
        resource = stub_dynamo(module, [record(INSIDE)])
        call(module, [INSIDE, OUTSIDE], groups=["team-a"])
        assert requested_keys(resource) == [INSIDE]

    def test_the_rest_of_the_batch_is_still_answered(self) -> None:
        # Dropping rather than refusing. The explorer asks for a page at once, and one
        # foreign key must not blank the folder.
        module = load_module()
        stub_dynamo(module, [record(INSIDE)])
        result = call(module, [OUTSIDE, INSIDE], groups=["team-a"])
        assert result["error"] is None
        assert [item["fileKey"] for item in result["metadata"]] == [INSIDE]

    def test_a_batch_entirely_outside_the_boundary_asks_for_nothing(self) -> None:
        module = load_module()
        resource = stub_dynamo(module, [])
        result = call(module, [OUTSIDE], groups=["team-a"])
        assert result == {"metadata": [], "error": None}
        assert not resource.batch_get_item.called

    def test_an_unconfined_caller_may_ask_for_anything(self) -> None:
        module = load_module(env={"GROUP_PATH_PREFIXES": "{}"})
        resource = stub_dynamo(module, [record(INSIDE), record(OUTSIDE)])
        call(module, [INSIDE, OUTSIDE], groups=["team-a"])
        assert requested_keys(resource) == [INSIDE, OUTSIDE]

    def test_a_caller_with_no_groups_is_unconfined(self) -> None:
        # An empty prefix list means "not using per-team prefixes for this caller",
        # not "nothing allowed" -- stated in `allowed_prefixes` and load bearing here.
        module = load_module()
        resource = stub_dynamo(module, [record(OUTSIDE)])
        call(module, [OUTSIDE], groups=[])
        assert requested_keys(resource) == [OUTSIDE]


class TestBatching:
    def test_duplicate_keys_are_asked_for_once(self) -> None:
        # BatchGetItem rejects a request containing the same key twice.
        module = load_module()
        resource = stub_dynamo(module, [record(INSIDE)])
        call(module, [INSIDE, INSIDE, INSIDE], groups=["team-a"])
        assert requested_keys(resource) == [INSIDE]

    def test_the_batch_is_capped_at_a_hundred_keys(self) -> None:
        module = load_module()
        resource = stub_dynamo(module, [])
        call(module, [f"team-a/f{n}.txt" for n in range(150)], groups=["team-a"])
        assert len(requested_keys(resource)) == 100

    def test_unprocessed_keys_are_retried_rather_than_lost(self) -> None:
        # BatchGetItem returns some keys unread when it hits its response size limit,
        # as UnprocessedKeys rather than as an error. Stopping after one call would drop
        # them silently and the folder would show badges on some files and not others.
        module = load_module()
        second = "team-a/other.pdf"
        resource = MagicMock()
        resource.batch_get_item.side_effect = [
            {
                "Responses": {TABLE: [record(INSIDE)]},
                "UnprocessedKeys": {TABLE: {"Keys": [{"file_key": second}]}},
            },
            {"Responses": {TABLE: [record(second)]}, "UnprocessedKeys": {}},
        ]
        module.boto3 = MagicMock()
        module.boto3.resource.return_value = resource

        result = call(module, [INSIDE, second], groups=["team-a"])
        assert resource.batch_get_item.call_count == 2
        assert [item["fileKey"] for item in result["metadata"]] == [INSIDE, second]


class TestConfiguration:
    def test_an_unconfigured_table_is_reported(self) -> None:
        module = load_module(env={"AI_METADATA_TABLE_NAME": ""})
        result = call(module, [INSIDE], groups=["team-a"])
        assert result["metadata"] == []
        assert "not configured" in result["error"]

    def test_an_empty_request_asks_for_nothing(self) -> None:
        module = load_module()
        resource = stub_dynamo(module, [])
        result = call(module, [], groups=["team-a"])
        assert result == {"metadata": [], "error": None}
        assert not resource.batch_get_item.called

    def test_a_table_failure_is_reported_rather_than_raised(self) -> None:
        # The badges are decoration on a folder view; the listing itself must not fail
        # because the metadata table did.
        module = load_module()
        resource = MagicMock()
        resource.batch_get_item.side_effect = RuntimeError("table is on fire")
        module.boto3 = MagicMock()
        module.boto3.resource.return_value = resource

        result = call(module, [INSIDE], groups=["team-a"])
        assert result["metadata"] == []
        assert "table is on fire" in result["error"]
