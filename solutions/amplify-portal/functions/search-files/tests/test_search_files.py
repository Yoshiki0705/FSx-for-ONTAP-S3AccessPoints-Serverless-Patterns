"""Tests for the boundary on search results.

Search results are object keys, so an unfiltered search is a directory listing by
another route -- and this endpoint returns a 500-character snippet of file content
beside each key, so it is also a partial read.

`shared/tests/test_portal_path_scope.py` covers `key_is_visible` itself. What is
asserted here is that this handler calls it, on every path that can return a key. That
is a different question, and the answer was no: `_search_semantic` accepted `allowed`
as a parameter and never referenced it, while the handler's own docstring said "every
result from either mode is dropped unless the caller may see the key". A knowledge base
indexes whatever it was pointed at and has no notion of the portal's groups, so nothing
upstream of that function was going to apply the boundary for it.

Three paths return keys and each is tested separately, because they filter in three
different places: the keyword search filters inside its pagination loop, the semantic
search inside its result loop, and the DemoMode mock inside its comprehension.

Both AWS clients are stubbed. What matters is which keys the handler passes on, not
whether boto3 can reach a knowledge base.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

MODULE_PATH = Path(__file__).resolve().parent.parent / "index.py"

DEFAULT_ALIAS = "default-ap-s3alias"
TEAM_A_ALIAS = "team-a-ap-s3alias"
GROUP_AP_MAPPING = {"team-a": TEAM_A_ALIAS}
GROUP_PATH_PREFIXES = {"team-a": ["team-a/"], "team-b": ["team-b/"]}

# One key inside team-a's boundary and one outside it, which is the whole test matrix.
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
        "S3_AP_ALIAS": DEFAULT_ALIAS,
        "GROUP_AP_MAPPING": json.dumps(GROUP_AP_MAPPING),
        "GROUP_PATH_PREFIXES": json.dumps(GROUP_PATH_PREFIXES),
        "BEDROCK_KB_ID": "kb-0123456789",
        "EXTERNAL_AI_ENABLED": "true",
        "AWS_REGION": "ap-northeast-1",
    }
    base.update(env or {})
    with patch.dict(os.environ, base, clear=False):
        spec = importlib.util.spec_from_file_location("search_files_under_test", MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules["search_files_under_test"] = module
        spec.loader.exec_module(module)
    return module


def stub_keyword(module: Any, keys: list[str]) -> None:
    """Make the S3 listing return `keys`, through the paginator the handler uses.

    Args:
        module: The freshly imported handler module.
        keys: Object keys the listing should report.
    """
    paginator = MagicMock()
    paginator.paginate.return_value = [{"Contents": [{"Key": k} for k in keys]}]
    module.s3 = MagicMock()
    module.s3.get_paginator.return_value = paginator


def retrieval_results(keys: list[str], snippet: str) -> dict:
    """A knowledge base response carrying one result per key.

    Args:
        keys: Object keys to report, each as an `s3://` location.
        snippet: The content text attached to every result.

    Returns:
        The shape `bedrock-agent-runtime.retrieve` returns.
    """
    return {
        "retrievalResults": [
            {
                "content": {"text": snippet},
                "location": {"s3Location": {"uri": f"s3://{DEFAULT_ALIAS}/{key}"}},
                "score": 0.5,
            }
            for key in keys
        ]
    }


@contextmanager
def stub_semantic(module: Any, response: dict) -> Iterator[MagicMock]:
    """Answer the knowledge base call with `response` for the duration of the block.

    A context manager rather than a bare `patcher.start()`, because `module.boto3` is
    the process-wide boto3 and a patch left running would follow the next test out of
    this file.

    Args:
        module: The freshly imported handler module.
        response: What `retrieve` should return.

    Yields:
        The stub client, for asserting on how it was called.
    """
    client = MagicMock()
    client.retrieve.return_value = response
    with patch.object(module.boto3, "client", return_value=client):
        yield client


def call(module: Any, query: str, groups: list[str] | None = None) -> dict:
    """Invoke the handler as the resolver would, with an attributed caller.

    Args:
        module: The freshly imported handler module.
        query: The search query, optionally prefixed with a mode.
        groups: The caller's Cognito groups.

    Returns:
        The handler's response.
    """
    return module.handler({"query": query, "groups": groups or []}, None)


def keys_of(result: dict) -> list[str]:
    """The keys the handler was willing to return.

    Args:
        result: A handler response.

    Returns:
        The `fileKey` of each result, in order.
    """
    return [item["fileKey"] for item in result["results"]]


KEYLESS_RESULT = {"retrievalResults": [{"content": {"text": "x"}, "location": {}, "score": 0.5}]}


class TestSemanticSearch:
    def test_a_result_outside_the_boundary_is_dropped(self) -> None:
        # The regression. Without the filter this returned both keys and a snippet of
        # each file, for a caller who cannot list either.
        module = load_module()
        with stub_semantic(module, retrieval_results([INSIDE, OUTSIDE], "contents")):
            result = call(module, "semantic:thermal", groups=["team-a"])
        assert keys_of(result) == [INSIDE]

    def test_the_snippet_of_a_dropped_result_does_not_come_back(self) -> None:
        # Dropping the key while keeping its text would leak the contents and lose only
        # the name, which is the worse half to keep.
        module = load_module()
        secret = "the confidential contents of another team's file"
        with stub_semantic(module, retrieval_results([OUTSIDE], secret)):
            result = call(module, "semantic:thermal", groups=["team-a"])
        assert result["results"] == []
        assert secret not in json.dumps(result)

    def test_an_unconfined_caller_still_sees_everything(self) -> None:
        # No prefixes configured means no restriction, not "nothing allowed".
        module = load_module(env={"GROUP_PATH_PREFIXES": "{}"})
        with stub_semantic(module, retrieval_results([INSIDE, OUTSIDE], "contents")):
            result = call(module, "semantic:thermal", groups=["team-a"])
        assert keys_of(result) == [INSIDE, OUTSIDE]

    def test_a_result_with_no_resolvable_key_is_dropped_for_a_confined_caller(self) -> None:
        # Nothing about a result without a key proves it is inside the boundary.
        module = load_module()
        with stub_semantic(module, KEYLESS_RESULT):
            result = call(module, "semantic:thermal", groups=["team-a"])
        assert result["results"] == []

    def test_the_same_keyless_result_is_kept_when_nothing_is_configured(self) -> None:
        module = load_module(env={"GROUP_PATH_PREFIXES": "{}"})
        with stub_semantic(module, KEYLESS_RESULT):
            result = call(module, "semantic:thermal", groups=["team-a"])
        assert len(result["results"]) == 1


class TestKeywordSearch:
    def test_a_listed_key_outside_the_boundary_is_dropped(self) -> None:
        module = load_module()
        stub_keyword(module, [INSIDE, OUTSIDE])
        result = call(module, "keyword:thermal", groups=["team-a"])
        assert keys_of(result) == [INSIDE]

    def test_it_lists_through_the_caller_s_own_access_point(self) -> None:
        # The prefixes decide which keys may be named; the access point decides which
        # ONTAP identity does the listing. Filtering the results of the wrong volume
        # would still be the wrong volume.
        module = load_module()
        stub_keyword(module, [INSIDE])
        call(module, "keyword:thermal", groups=["team-a"])
        assert module.s3.get_paginator.return_value.paginate.call_args.kwargs["Bucket"] == TEAM_A_ALIAS

    def test_an_unmapped_caller_lists_through_the_default(self) -> None:
        module = load_module()
        stub_keyword(module, [INSIDE])
        call(module, "keyword:thermal", groups=["team-c"])
        assert module.s3.get_paginator.return_value.paginate.call_args.kwargs["Bucket"] == DEFAULT_ALIAS


class TestDemoMode:
    # `2026` deliberately, because it matches the invented list across two folders --
    # `contracts/nda-2026.pdf` as well as the two under `reports/`. A query matching only
    # inside the boundary would pass whether or not the filter is there, which is how the
    # first version of this test failed to notice the filter being removed.
    def test_the_mock_results_are_confined_too(self) -> None:
        # No access point configured, so the handler answers from its invented list.
        # Nothing leaks either way, but a demo where the boundary does not apply
        # demonstrates the wrong behaviour.
        module = load_module(
            env={
                "S3_AP_ALIAS": "",
                "GROUP_AP_MAPPING": "{}",
                "GROUP_PATH_PREFIXES": json.dumps({"team-a": ["reports/"]}),
            }
        )
        keys = keys_of(call(module, "keyword:2026", groups=["team-a"]))
        assert keys, "the mock returned nothing to check"
        assert all(k.startswith("reports/") for k in keys)
        assert "contracts/nda-2026.pdf" not in keys

    def test_the_mock_is_unfiltered_without_prefixes(self) -> None:
        module = load_module(env={"S3_AP_ALIAS": "", "GROUP_AP_MAPPING": "{}", "GROUP_PATH_PREFIXES": "{}"})
        keys = keys_of(call(module, "keyword:2026", groups=["team-a"]))
        assert "contracts/nda-2026.pdf" in keys


class TestModeRouting:
    def test_an_empty_query_is_refused_before_either_search(self) -> None:
        module = load_module()
        stub_keyword(module, [INSIDE])
        result = call(module, "keyword:   ", groups=["team-a"])
        assert result["error"] == "Empty query"
        assert not module.s3.get_paginator.called

    def test_an_unknown_prefix_is_part_of_the_query_rather_than_a_mode(self) -> None:
        # "file:name.txt" is a search for that text, not a mode called `file`.
        module = load_module()
        stub_keyword(module, ["team-a/file:name.txt"])
        result = call(module, "file:name.txt", groups=["team-a"])
        assert result["query"] == "file:name.txt"
        assert keys_of(result) == ["team-a/file:name.txt"]

    def test_semantic_is_refused_for_an_external_caller_when_ai_is_off(self) -> None:
        module = load_module(env={"EXTERNAL_AI_ENABLED": ""})
        result = call(module, "semantic:thermal", groups=["team-a", "external"])
        assert result["results"] == []
        assert result["error"]

    def test_keyword_stays_available_to_that_caller(self) -> None:
        # It reaches no model and lists through the caller's own access point, so
        # refusing it would remove a search they can already do in the file browser.
        module = load_module(env={"EXTERNAL_AI_ENABLED": ""})
        stub_keyword(module, [INSIDE])
        result = call(module, "keyword:thermal", groups=["team-a", "external"])
        assert result["error"] is None
        assert keys_of(result) == [INSIDE]
