"""AgentCore Web Search Client

Amazon Bedrock AgentCore Gateway の Web Search Tool を呼び出す共通ユーティリティ。
FSx for ONTAP S3 AP パターンのハイブリッド RAG（内部文書 + 外部 Web 情報）を実現する。

Key Design:
- Graceful degradation: Web Search が失敗しても例外を投げず空リストを返す
- クエリ安全性: 200文字上限、内部文書コンテンツは Web クエリに含めない
- クロスリージョン対応: Gateway は us-east-1、呼び出し元は ap-northeast-1
- 引用義務: 結果にはソース URL・タイトルが含まれ、回答時に表示必須

Usage:
    from shared.web_search_client import WebSearchClient

    client = WebSearchClient(
        gateway_id="your-gateway-id",
        region="us-east-1",
    )
    results = client.search("latest data protection regulations 2026")
    # [{"text": "...", "url": "...", "title": "...", "publishedDate": "..."}]

Environment Variables:
    AGENTCORE_GATEWAY_ID: AgentCore Gateway ID (us-east-1)
    AGENTCORE_GATEWAY_REGION: Gateway リージョン (デフォルト: us-east-1)
    WEB_SEARCH_MAX_RESULTS: デフォルト最大結果数 (デフォルト: 5)
    WEB_SEARCH_ENABLED: "true" / "false" (デフォルト: "false")

References:
    - docs/investigations/agentcore-web-search-fsxn-integration.md
    - https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-connector-web-search-tool.html
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class WebSearchError(Exception):
    """Web Search 呼び出しエラー（ログ用。Graceful degradation のため通常は raise しない）。"""

    def __init__(self, message: str, error_code: str | None = None):
        super().__init__(message)
        self.error_code = error_code


class WebSearchResult:
    """Web 検索結果の1件を表す構造体。"""

    __slots__ = ("text", "url", "title", "published_date")

    def __init__(self, text: str, url: str, title: str, published_date: str):
        self.text = text
        self.url = url
        self.title = title
        self.published_date = published_date

    def to_dict(self) -> dict[str, str]:
        return {
            "text": self.text,
            "url": self.url,
            "title": self.title,
            "publishedDate": self.published_date,
        }

    def to_citation(self) -> str:
        """引用表示用フォーマット（Acceptable Use Policy 準拠）。"""
        date_part = f" ({self.published_date})" if self.published_date else ""
        return f"[Web: {self.title}]({self.url}){date_part}"

    def __repr__(self) -> str:
        return f"WebSearchResult(title={self.title!r}, url={self.url!r})"


class WebSearchClient:
    """AgentCore Gateway Web Search Tool クライアント。

    Graceful degradation を基本方針とする:
    - Web Search が無効 (WEB_SEARCH_ENABLED=false) → 空リスト
    - Gateway 未設定 (gateway_id 空) → 空リスト
    - API 呼び出し失敗 → ログ出力 + 空リスト
    - タイムアウト → ログ出力 + 空リスト

    内部文書 RAG (Bedrock KB + S3 Vectors) が必須パス、Web Search は補完パスという設計。
    """

    # Web Search Tool のターゲット名 + ツール名のフォーマット
    # NOTE: GA 後にターゲット名が変わる場合はここを修正
    DEFAULT_TOOL_NAME = "WebSearchTool___WebSearch"

    def __init__(
        self,
        gateway_id: str | None = None,
        region: str | None = None,
        max_results: int | None = None,
        enabled: bool | None = None,
        tool_name: str | None = None,
    ):
        """初期化。

        引数を省略した場合は環境変数から読み込む。

        Args:
            gateway_id: AgentCore Gateway ID
            region: Gateway のリージョン
            max_results: デフォルト最大結果数
            enabled: Web Search を有効にするか
            tool_name: Gateway 上のツール名（ターゲット名___ツール名）
        """
        self._gateway_id = gateway_id or os.environ.get("AGENTCORE_GATEWAY_ID", "")
        self._region = region or os.environ.get("AGENTCORE_GATEWAY_REGION", "us-east-1")
        self._max_results = max_results or int(os.environ.get("WEB_SEARCH_MAX_RESULTS", "5"))
        self._tool_name = tool_name or self.DEFAULT_TOOL_NAME

        # 明示的に有効/無効が渡されなければ環境変数で判定
        if enabled is not None:
            self._enabled = enabled
        else:
            self._enabled = os.environ.get("WEB_SEARCH_ENABLED", "false").lower() == "true"

        self._client: Any = None

    @property
    def is_enabled(self) -> bool:
        """Web Search が有効かつ gateway_id が設定されているか。"""
        return self._enabled and bool(self._gateway_id)

    def _get_client(self):
        """boto3 クライアントを遅延初期化（Lambda コールドスタート最適化）。"""
        if self._client is None:
            self._client = boto3.client("bedrock-agentcore", region_name=self._region)
        return self._client

    def search(
        self,
        query: str,
        max_results: int | None = None,
    ) -> list[WebSearchResult]:
        """Web 検索を実行する。

        Graceful degradation: 失敗時は例外を投げず空リストを返す。

        Args:
            query: 検索クエリ（200文字以内に自動切り詰め）
            max_results: 最大結果数 (1-25、省略時はインスタンスのデフォルト)

        Returns:
            WebSearchResult のリスト。失敗時は空リスト。
        """
        if not self.is_enabled:
            logger.debug("Web Search disabled or gateway_id not set — returning empty")
            return []

        # クエリ安全性: 200文字上限
        truncated_query = query.strip()[:200]
        if not truncated_query:
            return []

        effective_max = min(max_results or self._max_results, 25)

        start_time = time.time()
        try:
            results = self._invoke(truncated_query, effective_max)
            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(
                "Web Search completed: %d results, %.0f ms, query='%s'",
                len(results),
                elapsed_ms,
                truncated_query[:50],
            )
            return results

        except ClientError as e:
            elapsed_ms = (time.time() - start_time) * 1000
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            logger.warning(
                "Web Search failed (ClientError): code=%s, %.0f ms, query='%s' — %s",
                error_code,
                elapsed_ms,
                truncated_query[:50],
                str(e),
            )
            return []

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.warning(
                "Web Search failed (unexpected): %.0f ms, query='%s' — %s",
                elapsed_ms,
                truncated_query[:50],
                str(e),
            )
            return []

    def _invoke(self, query: str, max_results: int) -> list[WebSearchResult]:
        """Gateway API 呼び出し（内部メソッド）。

        NOTE: AgentCore Data Plane API の正確な形式は GA 後に確定する。
        boto3 で 'invoke_tool' や 'invoke_gateway' が見つからない場合は、
        MCP over HTTPS (StreamableHTTP) で直接呼び出すフォールバックを検討すること。
        """
        client = self._get_client()

        # --- Primary: boto3 invoke_tool API ---
        try:
            response = client.invoke_tool(
                gatewayIdentifier=self._gateway_id,
                toolName=self._tool_name,
                content=json.dumps(
                    {
                        "query": query,
                        "maxResults": max_results,
                    }
                ),
            )
            return self._parse_response(response)
        except AttributeError:
            # boto3 バージョンが invoke_tool 未対応の場合
            logger.warning(
                "boto3 client does not have 'invoke_tool' method. "
                "Ensure boto3 >= 1.36.x (AgentCore data plane support). "
                "Falling back to empty results."
            )
            return []
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "UnknownOperationException":
                logger.warning(
                    "invoke_tool API not recognized. The AgentCore data plane API "
                    "may have a different method name in the current SDK version. "
                    "Check: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/"
                )
                return []
            raise  # 他の ClientError は上位で処理

    def _parse_response(self, response: dict[str, Any]) -> list[WebSearchResult]:
        """MCP レスポンスをパースして WebSearchResult リストを返す。"""
        raw_content = response.get("content", [])
        if not raw_content or not isinstance(raw_content, list):
            return []

        text_block = raw_content[0].get("text", "{}")
        try:
            parsed = json.loads(text_block)
        except json.JSONDecodeError:
            logger.warning("Failed to parse Web Search response JSON")
            return []

        results = parsed.get("results", [])
        return [
            WebSearchResult(
                text=r.get("text", ""),
                url=r.get("url", ""),
                title=r.get("title", ""),
                published_date=r.get("publishedDate", ""),
            )
            for r in results
            if r.get("text")  # テキストが空の結果はスキップ
        ]

    def format_context_block(
        self,
        results: list[WebSearchResult],
        max_chars: int = 3000,
    ) -> str:
        """Web 検索結果を LLM コンテキストに埋め込む XML ブロックとして整形する。

        Args:
            results: WebSearchResult リスト
            max_chars: コンテキストブロックの最大文字数

        Returns:
            "<web_search_results>...</web_search_results>" 形式のテキスト。
            結果が空の場合は空文字列。
        """
        if not results:
            return ""

        lines: list[str] = []
        current_chars = 0
        for r in results:
            line = f"- [{r.title}]({r.url}) ({r.published_date}): {r.text[:300]}"
            if current_chars + len(line) > max_chars:
                break
            lines.append(line)
            current_chars += len(line)

        if not lines:
            return ""

        return "<web_search_results>\n" + "\n".join(lines) + "\n</web_search_results>"

    def format_citations(self, results: list[WebSearchResult]) -> list[str]:
        """引用リスト（Acceptable Use Policy 準拠: ソース URL + タイトル表示義務）。"""
        return [r.to_citation() for r in results]
