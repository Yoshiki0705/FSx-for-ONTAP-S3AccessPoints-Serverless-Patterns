"""UC13 教育 / 研究 引用ネットワーク分析ユニットテスト

引用解析、ネットワーク構築をテストする。

Requirements: 13.1, 13.2
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from functions.citation_analysis.handler import (
    extract_references_section,
    parse_references,
    build_citation_network,
)


class TestExtractReferencesSection:
    """参考文献セクション抽出のテスト"""

    def test_extract_english_references(self):
        """英語の References セクションが抽出されること"""
        text = "Some content here.\n\nReferences\n\n[1] Smith et al. (2020). Title.\n[2] Jones (2021). Another."
        result = extract_references_section(text)
        assert "[1] Smith" in result
        assert "[2] Jones" in result

    def test_extract_japanese_references(self):
        """日本語の参考文献セクションが抽出されること"""
        text = "本文内容。\n\n参考文献\n\n[1] 田中 (2020). タイトル。"
        result = extract_references_section(text)
        assert "[1] 田中" in result

    def test_no_references_section(self):
        """参考文献セクションがない場合に空文字列が返ること"""
        text = "This is just regular text without any references section."
        result = extract_references_section(text)
        assert result == ""


class TestParseReferences:
    """参考文献解析のテスト"""

    def test_parse_numbered_references(self):
        """番号付き参考文献が正しく解析されること"""
        text = "[1] Smith, J. (2020). Machine Learning Basics. Journal of AI.\n[2] Jones, A. (2021). Deep Learning. Nature."
        result = parse_references(text)
        assert len(result) == 2
        assert result[0]["ref_id"] == "ref_1"
        assert "2020" in result[0]["year"]
        assert result[1]["ref_id"] == "ref_2"

    def test_parse_empty_text(self):
        """空テキストで空リストが返ること"""
        result = parse_references("")
        assert result == []

    def test_parse_short_entries_skipped(self):
        """短すぎるエントリがスキップされること"""
        text = "[1] Short\n[2] Also very short text entry that is long enough to be parsed."
        result = parse_references(text)
        # 10文字未満はスキップ
        assert all(len(r["raw_text"]) >= 10 for r in result)


class TestBuildCitationNetwork:
    """引用ネットワーク構築のテスト"""

    def test_build_simple_network(self):
        """シンプルなネットワークが正しく構築されること"""
        papers = [
            {
                "paper_id": "paper_1",
                "title": "Paper One",
                "references": [
                    {"ref_id": "ref_a", "title": "Reference A"},
                    {"ref_id": "ref_b", "title": "Reference B"},
                ],
            },
            {
                "paper_id": "paper_2",
                "title": "Paper Two",
                "references": [
                    {"ref_id": "ref_a", "title": "Reference A"},
                ],
            },
        ]
        result = build_citation_network(papers)

        assert result["total_papers"] == 4  # 2 papers + 2 unique refs
        assert result["total_citations"] == 3  # 3 edges
        assert len(result["nodes"]) == 4
        assert len(result["edges"]) == 3

    def test_no_duplicate_edges(self):
        """重複エッジが生成されないこと"""
        papers = [
            {
                "paper_id": "paper_1",
                "title": "Paper One",
                "references": [
                    {"ref_id": "ref_a", "title": "Ref A"},
                    {"ref_id": "ref_a", "title": "Ref A"},  # 重複
                ],
            },
        ]
        result = build_citation_network(papers)
        assert result["total_citations"] == 1

    def test_empty_papers(self):
        """空の論文リストで空ネットワークが返ること"""
        result = build_citation_network([])
        assert result["total_papers"] == 0
        assert result["total_citations"] == 0
        assert result["nodes"] == []
        assert result["edges"] == []

    def test_all_edge_references_valid_nodes(self):
        """全エッジの source/target が有効なノード ID を参照すること"""
        papers = [
            {
                "paper_id": "p1",
                "title": "P1",
                "references": [
                    {"ref_id": "r1", "title": "R1"},
                    {"ref_id": "r2", "title": "R2"},
                ],
            },
        ]
        result = build_citation_network(papers)
        node_ids = {n["id"] for n in result["nodes"]}
        for edge in result["edges"]:
            assert edge["source"] in node_ids
            assert edge["target"] in node_ids
