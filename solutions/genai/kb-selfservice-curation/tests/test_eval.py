"""UC29 RAG 評価ハーネスのスコアリング単体テスト（AWS 不要、CI 実行可）"""

from __future__ import annotations

import importlib.util
import os


def _load_eval():
    path = os.path.join(os.path.dirname(__file__), "..", "evaluation", "run_eval.py")
    spec = importlib.util.spec_from_file_location("uc29_run_eval", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestNoAnswer:
    def test_no_answer_detected(self):
        m = _load_eval()
        assert m.is_no_answer("検索結果には情報が含まれていません") is True
        assert m.is_no_answer("") is True
        assert m.is_no_answer("製品Xの計量範囲は0.1g〜30kgです") is False


class TestScoreCase:
    def test_citation_match_pass(self):
        m = _load_eval()
        case = {"id": "sales-1", "expected_source": "ai-knowledge/sales/product-catalog/product-x-spec.md"}
        result = {
            "answer": "...",
            "citations": [{"source": "s3://b/ai-knowledge/sales/product-catalog/product-x-spec.md"}],
        }
        s = m.score_case(case, result)
        assert s["passed"] is True
        assert s["citation_match"] is True

    def test_citation_match_fail(self):
        m = _load_eval()
        case = {"id": "x", "expected_source": "ai-knowledge/sales/product-catalog/product-x-spec.md"}
        result = {"answer": "...", "citations": [{"source": "s3://b/ai-knowledge/legal/contracts/nda-template.md"}]}
        s = m.score_case(case, result)
        assert s["passed"] is False

    def test_no_answer_case_pass(self):
        m = _load_eval()
        case = {"id": "na-1", "expected_behavior": "no_answer", "expected_source": None}
        result = {"answer": "申し訳ありませんが、情報が含まれていません", "citations": []}
        s = m.score_case(case, result)
        assert s["passed"] is True
        assert s["type"] == "no_answer"


class TestSummarize:
    def test_summary_rates(self):
        m = _load_eval()
        scored = [
            {"type": "citation", "passed": True},
            {"type": "citation", "passed": False},
            {"type": "no_answer", "passed": True},
        ]
        s = m.summarize(scored)
        assert s["total"] == 3
        assert s["passed"] == 2
        assert s["citation_pass_rate"] == 0.5
        assert s["no_answer_pass_rate"] == 1.0
