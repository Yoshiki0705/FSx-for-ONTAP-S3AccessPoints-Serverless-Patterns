"""shared.web_search_client のユニットテスト

WebSearchClient の graceful degradation、パース、引用フォーマットをテストする。
実際の AgentCore Gateway は呼ばず、モックで動作を検証。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# shared モジュールの解決
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.web_search_client import WebSearchClient, WebSearchResult


# --- WebSearchResult テスト ---


class TestWebSearchResult:
    """WebSearchResult 構造体のテスト。"""

    def test_to_dict(self):
        r = WebSearchResult(
            text="snippet text",
            url="https://example.com/article",
            title="Example Article",
            published_date="2026-06-17",
        )
        d = r.to_dict()
        assert d == {
            "text": "snippet text",
            "url": "https://example.com/article",
            "title": "Example Article",
            "publishedDate": "2026-06-17",
        }

    def test_to_citation(self):
        r = WebSearchResult(
            text="snippet",
            url="https://example.com",
            title="My Article",
            published_date="2026-06-17",
        )
        assert r.to_citation() == "[Web: My Article](https://example.com) (2026-06-17)"

    def test_to_citation_no_date(self):
        r = WebSearchResult(text="x", url="https://x.com", title="X", published_date="")
        assert r.to_citation() == "[Web: X](https://x.com)"

    def test_repr(self):
        r = WebSearchResult(text="t", url="u", title="T", published_date="d")
        assert "WebSearchResult" in repr(r)
        assert "T" in repr(r)


# --- WebSearchClient テスト ---


class TestWebSearchClientDisabled:
    """Web Search が無効の場合のテスト（graceful degradation）。"""

    def test_disabled_returns_empty(self):
        client = WebSearchClient(gateway_id="gw-123", enabled=False)
        assert client.search("test query") == []

    def test_no_gateway_id_returns_empty(self):
        client = WebSearchClient(gateway_id="", enabled=True)
        assert client.search("test query") == []

    def test_empty_query_returns_empty(self):
        client = WebSearchClient(gateway_id="gw-123", enabled=True)
        assert client.search("") == []
        assert client.search("   ") == []

    def test_is_enabled_false_when_disabled(self):
        client = WebSearchClient(gateway_id="gw-123", enabled=False)
        assert client.is_enabled is False

    def test_is_enabled_false_when_no_gateway(self):
        client = WebSearchClient(gateway_id="", enabled=True)
        assert client.is_enabled is False

    def test_is_enabled_true(self):
        client = WebSearchClient(gateway_id="gw-123", enabled=True)
        assert client.is_enabled is True


class TestWebSearchClientEnvVars:
    """環境変数からの設定読み込みテスト。"""

    @patch.dict(
        "os.environ",
        {
            "AGENTCORE_GATEWAY_ID": "gw-env-test",
            "AGENTCORE_GATEWAY_REGION": "us-west-2",
            "WEB_SEARCH_MAX_RESULTS": "10",
            "WEB_SEARCH_ENABLED": "true",
        },
    )
    def test_from_env_vars(self):
        client = WebSearchClient()
        assert client._gateway_id == "gw-env-test"
        assert client._region == "us-west-2"
        assert client._max_results == 10
        assert client._enabled is True
        assert client.is_enabled is True

    @patch.dict(
        "os.environ",
        {
            "AGENTCORE_GATEWAY_ID": "",
            "WEB_SEARCH_ENABLED": "false",
        },
    )
    def test_defaults_disabled(self):
        client = WebSearchClient()
        assert client.is_enabled is False


class TestWebSearchClientInvoke:
    """API 呼び出しのモックテスト。"""

    def _mock_response(self, results: list[dict]) -> dict:
        """MCP 形式のモックレスポンスを生成。"""
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps({"id": "test-id", "results": results}),
                }
            ]
        }

    def test_successful_search(self):
        client = WebSearchClient(gateway_id="gw-123", region="us-east-1", enabled=True)
        mock_boto3_client = MagicMock()
        mock_boto3_client.invoke_tool.return_value = self._mock_response(
            [
                {
                    "text": "FSx for ONTAP now supports S3 Access Points",
                    "url": "https://aws.amazon.com/fsx",
                    "title": "FSx Update",
                    "publishedDate": "2026-06-17",
                },
                {
                    "text": "Enterprise storage meets AI workloads",
                    "url": "https://example.com/storage",
                    "title": "Storage AI",
                    "publishedDate": "2026-06-16",
                },
            ]
        )
        client._client = mock_boto3_client

        results = client.search("FSx for ONTAP")
        assert len(results) == 2
        assert results[0].title == "FSx Update"
        assert results[0].url == "https://aws.amazon.com/fsx"
        assert results[1].published_date == "2026-06-16"

        # invoke_tool が正しい引数で呼ばれたか
        mock_boto3_client.invoke_tool.assert_called_once()
        call_kwargs = mock_boto3_client.invoke_tool.call_args[1]
        assert call_kwargs["gatewayIdentifier"] == "gw-123"
        assert call_kwargs["toolName"] == "WebSearchTool___WebSearch"
        payload = json.loads(call_kwargs["content"])
        assert payload["query"] == "FSx for ONTAP"
        assert payload["maxResults"] == 5

    def test_query_truncation(self):
        """200文字超のクエリが切り詰められることを確認。"""
        client = WebSearchClient(gateway_id="gw-123", enabled=True)
        mock_client = MagicMock()
        mock_client.invoke_tool.return_value = self._mock_response([])
        client._client = mock_client

        long_query = "x" * 300
        client.search(long_query)

        call_kwargs = mock_client.invoke_tool.call_args[1]
        payload = json.loads(call_kwargs["content"])
        assert len(payload["query"]) == 200

    def test_max_results_capped_at_25(self):
        """max_results が 25 を超えないことを確認。"""
        client = WebSearchClient(gateway_id="gw-123", enabled=True, max_results=50)
        mock_client = MagicMock()
        mock_client.invoke_tool.return_value = self._mock_response([])
        client._client = mock_client

        client.search("test")
        call_kwargs = mock_client.invoke_tool.call_args[1]
        payload = json.loads(call_kwargs["content"])
        assert payload["maxResults"] == 25

    def test_client_error_returns_empty(self):
        """ClientError 時に空リストを返す（graceful degradation）。"""
        from botocore.exceptions import ClientError

        client = WebSearchClient(gateway_id="gw-123", enabled=True)
        mock_client = MagicMock()
        mock_client.invoke_tool.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "InvokeTool",
        )
        client._client = mock_client

        results = client.search("test query")
        assert results == []

    def test_unexpected_error_returns_empty(self):
        """予期しないエラー時に空リストを返す。"""
        client = WebSearchClient(gateway_id="gw-123", enabled=True)
        mock_client = MagicMock()
        mock_client.invoke_tool.side_effect = RuntimeError("network timeout")
        client._client = mock_client

        results = client.search("test query")
        assert results == []

    def test_empty_results_in_response(self):
        """API が空結果を返した場合。"""
        client = WebSearchClient(gateway_id="gw-123", enabled=True)
        mock_client = MagicMock()
        mock_client.invoke_tool.return_value = self._mock_response([])
        client._client = mock_client

        results = client.search("obscure query with no results")
        assert results == []

    def test_malformed_json_returns_empty(self):
        """JSON パース失敗時に空リストを返す。"""
        client = WebSearchClient(gateway_id="gw-123", enabled=True)
        mock_client = MagicMock()
        mock_client.invoke_tool.return_value = {"content": [{"type": "text", "text": "not valid json {{{"}]}
        client._client = mock_client

        results = client.search("test")
        assert results == []

    def test_results_without_text_are_skipped(self):
        """text が空の結果はスキップされる。"""
        client = WebSearchClient(gateway_id="gw-123", enabled=True)
        mock_client = MagicMock()
        mock_client.invoke_tool.return_value = self._mock_response(
            [
                {"text": "valid", "url": "https://a.com", "title": "A", "publishedDate": "2026-01-01"},
                {"text": "", "url": "https://b.com", "title": "B", "publishedDate": "2026-01-01"},
                {"text": "also valid", "url": "https://c.com", "title": "C", "publishedDate": "2026-01-02"},
            ]
        )
        client._client = mock_client

        results = client.search("test")
        assert len(results) == 2
        assert results[0].title == "A"
        assert results[1].title == "C"


class TestWebSearchClientFormatting:
    """コンテキストブロックと引用フォーマットのテスト。"""

    def _sample_results(self) -> list[WebSearchResult]:
        return [
            WebSearchResult(
                text="Latest update on data protection",
                url="https://example.com/dp",
                title="Data Protection 2026",
                published_date="2026-06-17",
            ),
            WebSearchResult(
                text="New compliance framework released",
                url="https://example.com/compliance",
                title="Compliance Framework",
                published_date="2026-06-16",
            ),
        ]

    def test_format_context_block(self):
        client = WebSearchClient(gateway_id="gw-123", enabled=True)
        results = self._sample_results()
        block = client.format_context_block(results)

        assert block.startswith("<web_search_results>")
        assert block.endswith("</web_search_results>")
        assert "Data Protection 2026" in block
        assert "Compliance Framework" in block
        assert "https://example.com/dp" in block

    def test_format_context_block_empty(self):
        client = WebSearchClient(gateway_id="gw-123", enabled=True)
        assert client.format_context_block([]) == ""

    def test_format_context_block_max_chars(self):
        client = WebSearchClient(gateway_id="gw-123", enabled=True)
        results = self._sample_results()
        # 非常に小さい max_chars → 1件も入らない場合
        block = client.format_context_block(results, max_chars=10)
        assert block == ""

    def test_format_citations(self):
        client = WebSearchClient(gateway_id="gw-123", enabled=True)
        results = self._sample_results()
        citations = client.format_citations(results)

        assert len(citations) == 2
        assert "[Web: Data Protection 2026](https://example.com/dp) (2026-06-17)" in citations[0]
        assert "[Web: Compliance Framework](https://example.com/compliance) (2026-06-16)" in citations[1]
