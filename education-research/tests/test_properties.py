"""UC13 教育 / 研究 プロパティテスト

Property 19: Citation network construction consistency
引用ネットワーク構築の一貫性を検証する。

任意の論文セットに対して:
- total_papers == len(nodes)
- total_citations == len(edges)
- 全エッジの source/target が有効なノード ID を参照する
- 重複エッジが存在しない

**Validates: Requirements 10.5, 10.6**
"""

from __future__ import annotations

import os
import sys

from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from functions.citation_analysis.handler import build_citation_network


# =========================================================================
# Strategies
# =========================================================================

# 参考文献のストラテジー
reference_strategy = st.fixed_dictionaries({
    "ref_id": st.text(
        alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_"),
        min_size=3,
        max_size=20,
    ),
    "title": st.text(min_size=1, max_size=100),
})

# 論文のストラテジー
paper_strategy = st.fixed_dictionaries({
    "paper_id": st.text(
        alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_"),
        min_size=3,
        max_size=20,
    ),
    "title": st.text(min_size=1, max_size=100),
    "references": st.lists(reference_strategy, min_size=0, max_size=10),
})

# 論文リストのストラテジー（ユニークな paper_id を保証）
papers_strategy = st.lists(paper_strategy, min_size=0, max_size=20).map(
    lambda papers: _deduplicate_paper_ids(papers)
)


def _deduplicate_paper_ids(papers: list[dict]) -> list[dict]:
    """論文リストから重複 paper_id を除去する"""
    seen = set()
    unique = []
    for paper in papers:
        pid = paper["paper_id"]
        if pid and pid not in seen:
            seen.add(pid)
            unique.append(paper)
    return unique


# =========================================================================
# Property 19: Citation network construction consistency
# =========================================================================


class TestCitationNetworkConsistency:
    """Property 19: 引用ネットワーク構築一貫性

    **Validates: Requirements 10.5, 10.6**
    """

    @settings(max_examples=100)
    @given(papers=papers_strategy)
    def test_total_papers_equals_node_count(self, papers):
        """total_papers == len(nodes) であること"""
        result = build_citation_network(papers)
        assert result["total_papers"] == len(result["nodes"])

    @settings(max_examples=100)
    @given(papers=papers_strategy)
    def test_total_citations_equals_edge_count(self, papers):
        """total_citations == len(edges) であること"""
        result = build_citation_network(papers)
        assert result["total_citations"] == len(result["edges"])

    @settings(max_examples=100)
    @given(papers=papers_strategy)
    def test_all_edge_sources_reference_valid_nodes(self, papers):
        """全エッジの source が有効なノード ID を参照すること"""
        result = build_citation_network(papers)
        node_ids = {node["id"] for node in result["nodes"]}
        for edge in result["edges"]:
            assert edge["source"] in node_ids, (
                f"Edge source '{edge['source']}' not in nodes: {node_ids}"
            )

    @settings(max_examples=100)
    @given(papers=papers_strategy)
    def test_all_edge_targets_reference_valid_nodes(self, papers):
        """全エッジの target が有効なノード ID を参照すること"""
        result = build_citation_network(papers)
        node_ids = {node["id"] for node in result["nodes"]}
        for edge in result["edges"]:
            assert edge["target"] in node_ids, (
                f"Edge target '{edge['target']}' not in nodes: {node_ids}"
            )

    @settings(max_examples=100)
    @given(papers=papers_strategy)
    def test_no_duplicate_edges(self, papers):
        """重複エッジが存在しないこと"""
        result = build_citation_network(papers)
        edge_keys = [
            (edge["source"], edge["target"]) for edge in result["edges"]
        ]
        assert len(edge_keys) == len(set(edge_keys)), (
            f"Duplicate edges found: {edge_keys}"
        )
