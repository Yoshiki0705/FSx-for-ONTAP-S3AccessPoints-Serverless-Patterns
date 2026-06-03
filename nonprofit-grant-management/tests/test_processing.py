"""UC24 Nonprofit Grant Management — Processing Lambda unit tests."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Dynamic import for namespace isolation — Grant Extractor
_grant_handler_path = (
    Path(__file__).parent.parent / "functions" / "grant_extractor" / "handler.py"
)
_grant_spec = importlib.util.spec_from_file_location(
    "npo_grant_extractor_handler", _grant_handler_path
)
_grant_module = importlib.util.module_from_spec(_grant_spec)
sys.modules["npo_grant_extractor_handler"] = _grant_module
_grant_spec.loader.exec_module(_grant_module)

grant_is_supported_format = _grant_module.is_supported_format
grant_extract_text_with_textract = _grant_module.extract_text_with_textract
grant_extract_grant_info_with_bedrock = _grant_module.extract_grant_info_with_bedrock
grant_parse_grant_json = _grant_module._parse_grant_json

# Dynamic import for namespace isolation — Outcome Matcher
_outcome_handler_path = (
    Path(__file__).parent.parent / "functions" / "outcome_matcher" / "handler.py"
)
_outcome_spec = importlib.util.spec_from_file_location(
    "npo_outcome_matcher_handler", _outcome_handler_path
)
_outcome_module = importlib.util.module_from_spec(_outcome_spec)
sys.modules["npo_outcome_matcher_handler"] = _outcome_module
_outcome_spec.loader.exec_module(_outcome_module)

outcome_is_supported_format = _outcome_module.is_supported_format
outcome_extract_key_phrases_with_comprehend = (
    _outcome_module.extract_key_phrases_with_comprehend
)
outcome_match_outcomes_with_bedrock = _outcome_module.match_outcomes_with_bedrock
outcome_parse_outcome_json = _outcome_module._parse_outcome_json


class TestGrantExtractorSupportedFormat:
    """Grant Extractor — フォーマット判定テスト"""

    def test_pdf_supported(self):
        assert grant_is_supported_format("applications/proposal.pdf") is True

    def test_docx_supported(self):
        assert grant_is_supported_format("applications/proposal.docx") is True

    def test_doc_supported(self):
        assert grant_is_supported_format("applications/proposal.doc") is True

    def test_xlsx_not_supported(self):
        assert grant_is_supported_format("applications/budget.xlsx") is False

    def test_zip_not_supported(self):
        assert grant_is_supported_format("applications/archive.zip") is False

    def test_empty_key(self):
        assert grant_is_supported_format("") is False

    def test_no_extension(self):
        assert grant_is_supported_format("applications/noext") is False

    def test_case_insensitive(self):
        assert grant_is_supported_format("applications/proposal.PDF") is True


class TestGrantExtractorTextract:
    """Grant Extractor — Textract テキスト抽出テスト"""

    def test_extract_text_success(self):
        mock_client = MagicMock()
        mock_client.analyze_document.return_value = {
            "Blocks": [
                {"BlockType": "LINE", "Text": "NPO法人 テスト団体"},
                {"BlockType": "LINE", "Text": "助成金申請書"},
                {"BlockType": "LINE", "Text": "予算総額: 500,000円"},
                {"BlockType": "WORD", "Text": "ignored"},
            ]
        }

        result = grant_extract_text_with_textract(b"fake_bytes", mock_client)
        assert "NPO法人 テスト団体" in result
        assert "助成金申請書" in result
        assert "予算総額: 500,000円" in result
        assert "ignored" not in result

    def test_extract_text_empty_blocks(self):
        mock_client = MagicMock()
        mock_client.analyze_document.return_value = {"Blocks": []}

        result = grant_extract_text_with_textract(b"fake_bytes", mock_client)
        assert result == ""


class TestGrantExtractorBedrock:
    """Grant Extractor — Bedrock 情報抽出テスト"""

    def test_extract_grant_info_success(self):
        expected_response = {
            "applicant_info": {
                "applicant_name": "田中太郎",
                "organization_name": "NPO法人 テスト団体",
                "contact_email": "test@example.org",
                "contact_phone": None,
                "representative": "田中太郎",
            },
            "budget": {
                "total_amount": 500000,
                "currency": "JPY",
                "breakdown": [
                    {"item": "人件費", "amount": 300000},
                    {"item": "備品費", "amount": 200000},
                ],
            },
            "project_description": {
                "title": "地域教育支援プロジェクト",
                "summary": "地域の子どもたちに教育支援を行う",
                "objectives": ["学習支援の実施", "居場所づくり"],
                "duration": "2025年4月〜2026年3月",
                "target_beneficiaries": "小学生〜中学生",
            },
        }

        import io

        mock_client = MagicMock()
        response_bytes = json.dumps({
            "content": [{"type": "text", "text": json.dumps(expected_response)}]
        }).encode("utf-8")
        mock_client.invoke_model.return_value = {
            "body": io.BytesIO(response_bytes)
        }

        result = grant_extract_grant_info_with_bedrock(
            "テスト テキスト 十分な長さのテキストです。これは助成金申請書の内容です。", mock_client, "test-model"
        )

        assert result["applicant_info"]["organization_name"] == "NPO法人 テスト団体"
        assert result["budget"]["total_amount"] == 500000
        assert result["project_description"]["title"] == "地域教育支援プロジェクト"

    def test_extract_grant_info_short_text(self):
        mock_client = MagicMock()
        result = grant_extract_grant_info_with_bedrock("短い", mock_client, "test-model")
        assert result == {}

    def test_extract_grant_info_empty_text(self):
        mock_client = MagicMock()
        result = grant_extract_grant_info_with_bedrock("", mock_client, "test-model")
        assert result == {}


class TestGrantExtractorParseJson:
    """Grant Extractor — JSON パーステスト"""

    def test_parse_valid_json(self):
        text = '{"applicant_info": {"applicant_name": "Test"}}'
        result = grant_parse_grant_json(text)
        assert result["applicant_info"]["applicant_name"] == "Test"

    def test_parse_json_with_surrounding_text(self):
        text = 'Here is the result: {"budget": {"total_amount": 100000}} End.'
        result = grant_parse_grant_json(text)
        assert result["budget"]["total_amount"] == 100000

    def test_parse_invalid_json(self):
        text = "This is not JSON"
        result = grant_parse_grant_json(text)
        assert result == {}

    def test_parse_empty_text(self):
        result = grant_parse_grant_json("")
        assert result == {}


class TestOutcomeMatcherSupportedFormat:
    """Outcome Matcher — フォーマット判定テスト"""

    def test_pdf_supported(self):
        assert outcome_is_supported_format("reports/annual.pdf") is True

    def test_docx_supported(self):
        assert outcome_is_supported_format("reports/annual.docx") is True

    def test_xlsx_not_supported(self):
        assert outcome_is_supported_format("reports/data.xlsx") is False

    def test_empty_key(self):
        assert outcome_is_supported_format("") is False


class TestOutcomeMatcherComprehend:
    """Outcome Matcher — Comprehend キーフレーズ抽出テスト"""

    def test_extract_key_phrases_success(self):
        mock_client = MagicMock()
        mock_client.detect_key_phrases.return_value = {
            "KeyPhrases": [
                {"Text": "教育支援", "Score": 0.95},
                {"Text": "参加者100名", "Score": 0.88},
                {"Text": "地域", "Score": 0.60},  # below threshold
            ]
        }

        result = outcome_extract_key_phrases_with_comprehend(
            "テスト テキスト 十分な長さ", mock_client, "ja"
        )
        assert "教育支援" in result
        assert "参加者100名" in result
        assert "地域" not in result  # below 0.7 threshold

    def test_extract_key_phrases_empty_text(self):
        mock_client = MagicMock()
        result = outcome_extract_key_phrases_with_comprehend("", mock_client, "ja")
        assert result == []

    def test_extract_key_phrases_short_text(self):
        mock_client = MagicMock()
        result = outcome_extract_key_phrases_with_comprehend("短い", mock_client, "ja")
        assert result == []


class TestOutcomeMatcherBedrock:
    """Outcome Matcher — Bedrock 成果マッチングテスト"""

    def test_match_outcomes_success(self):
        expected_response = {
            "outcome_metrics": [
                {
                    "metric_name": "参加者数",
                    "achieved_value": "150",
                    "target_value": "100",
                    "unit": "人",
                    "category": "参加者数",
                }
            ],
            "objective_matching": [
                {
                    "original_objective": "学習支援100名実施",
                    "achieved_outcome": "学習支援150名実施",
                    "match_confidence": 0.92,
                    "achievement_status": "achieved",
                }
            ],
            "overall_achievement_rate": 95,
            "summary": "目標を上回る成果を達成",
        }

        import io

        mock_client = MagicMock()
        response_bytes = json.dumps({
            "content": [{"type": "text", "text": json.dumps(expected_response)}]
        }).encode("utf-8")
        mock_client.invoke_model.return_value = {
            "body": io.BytesIO(response_bytes)
        }

        result = outcome_match_outcomes_with_bedrock(
            "テスト テキスト 十分な長さのテキストです。これは活動報告書の内容です。",
            ["教育支援", "参加者"],
            mock_client,
            "test-model",
        )

        assert result["overall_achievement_rate"] == 95
        assert len(result["outcome_metrics"]) == 1
        assert result["outcome_metrics"][0]["metric_name"] == "参加者数"

    def test_match_outcomes_empty_text(self):
        mock_client = MagicMock()
        result = outcome_match_outcomes_with_bedrock("", [], mock_client, "test-model")
        assert result == {}


class TestOutcomeMatcherParseJson:
    """Outcome Matcher — JSON パーステスト"""

    def test_parse_valid_json(self):
        text = '{"overall_achievement_rate": 80, "outcome_metrics": []}'
        result = outcome_parse_outcome_json(text)
        assert result["overall_achievement_rate"] == 80

    def test_parse_invalid_json(self):
        result = outcome_parse_outcome_json("not json")
        assert result == {}

    def test_parse_empty(self):
        result = outcome_parse_outcome_json("")
        assert result == {}
