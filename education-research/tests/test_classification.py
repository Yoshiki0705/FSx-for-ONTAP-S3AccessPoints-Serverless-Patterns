"""UC13 教育 / 研究 分類ユニットテスト

論文分類、Comprehend エンティティ抽出をテストする。

Requirements: 13.1, 13.2
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from functions.classification.handler import (
    extract_entities_with_comprehend,
    detect_key_phrases,
)


class TestExtractEntities:
    """Comprehend エンティティ抽出のテスト"""

    def test_extract_entities_success(self):
        """正常系: エンティティが正しく抽出されること"""
        mock_client = MagicMock()
        mock_client.detect_entities.return_value = {
            "Entities": [
                {"Text": "John Smith", "Type": "PERSON", "Score": 0.95},
                {"Text": "MIT", "Type": "ORGANIZATION", "Score": 0.88},
                {"Text": "2026", "Type": "DATE", "Score": 0.92},
            ]
        }
        result = extract_entities_with_comprehend(mock_client, "Sample text")
        assert len(result) == 3
        assert result[0]["text"] == "John Smith"
        assert result[0]["type"] == "PERSON"
        assert result[0]["score"] == 0.95

    def test_extract_entities_empty(self):
        """空レスポンスで空リストが返ること"""
        mock_client = MagicMock()
        mock_client.detect_entities.return_value = {"Entities": []}
        result = extract_entities_with_comprehend(mock_client, "text")
        assert result == []

    def test_text_truncation(self):
        """長いテキストが切り詰められること"""
        mock_client = MagicMock()
        mock_client.detect_entities.return_value = {"Entities": []}
        long_text = "x" * 200000
        extract_entities_with_comprehend(mock_client, long_text)
        call_args = mock_client.detect_entities.call_args
        assert len(call_args[1]["Text"]) <= 99000


class TestDetectKeyPhrases:
    """キーフレーズ検出のテスト"""

    def test_detect_key_phrases_success(self):
        """正常系: キーフレーズが検出されること"""
        mock_client = MagicMock()
        mock_client.detect_key_phrases.return_value = {
            "KeyPhrases": [
                {"Text": "machine learning", "Score": 0.95},
                {"Text": "neural networks", "Score": 0.88},
                {"Text": "low relevance", "Score": 0.3},
            ]
        }
        result = detect_key_phrases(mock_client, "Sample text")
        assert "machine learning" in result
        assert "neural networks" in result
        assert "low relevance" not in result

    def test_max_20_phrases(self):
        """最大20件に制限されること"""
        mock_client = MagicMock()
        mock_client.detect_key_phrases.return_value = {
            "KeyPhrases": [
                {"Text": f"phrase_{i}", "Score": 0.9}
                for i in range(30)
            ]
        }
        result = detect_key_phrases(mock_client, "text")
        assert len(result) <= 20
