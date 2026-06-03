"""UC27 HR Document Screening — Processing Lambda unit tests."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

# Dynamic import — resume_extractor
_re_path = Path(__file__).parent.parent / "functions" / "resume_extractor" / "handler.py"
_re_spec = importlib.util.spec_from_file_location("hr_resume_extractor", _re_path)
_re_module = importlib.util.module_from_spec(_re_spec)
sys.modules["hr_resume_extractor"] = _re_module
_re_spec.loader.exec_module(_re_module)

extract_candidate_data = _re_module.extract_candidate_data

# Dynamic import — candidate_scorer
_cs_path = Path(__file__).parent.parent / "functions" / "candidate_scorer" / "handler.py"
_cs_spec = importlib.util.spec_from_file_location("hr_candidate_scorer", _cs_path)
_cs_module = importlib.util.module_from_spec(_cs_spec)
sys.modules["hr_candidate_scorer"] = _cs_module
_cs_spec.loader.exec_module(_cs_module)

_parse_scoring_response = _cs_module._parse_scoring_response

# Import PiiFilter
from shared.pii_filter import PiiFilter, mask_pii_in_text, is_strict_mode


class TestExtractCandidateData:
    def test_skills_extraction(self):
        text = "スキル: Python, AWS, Docker, Kubernetes"
        result = extract_candidate_data(text, [])
        assert "Python" in result["skills"]
        assert "AWS" in result["skills"]

    def test_experience_years_ja(self):
        text = "経験: 5年"
        result = extract_candidate_data(text, [])
        assert result["experience_years"] == 5

    def test_experience_years_en(self):
        text = "Experience: 10 years"
        result = extract_candidate_data(text, [])
        assert result["experience_years"] == 10

    def test_certifications(self):
        text = "資格: AWS Solutions Architect, PMP"
        result = extract_candidate_data(text, [])
        assert "aws" in result["certifications"]
        assert "pmp" in result["certifications"]

    def test_education_from_entities(self):
        text = "学歴あり"
        entities = [
            {"text": "東京大学", "type": "ORGANIZATION", "score": 0.95},
            {"text": "株式会社ABC", "type": "ORGANIZATION", "score": 0.90},
        ]
        result = extract_candidate_data(text, entities)
        assert "東京大学" in result["education"]
        assert "株式会社ABC" not in result["education"]

    def test_empty_text(self):
        result = extract_candidate_data("", [])
        assert result["skills"] == []
        assert result["experience_years"] is None
        assert result["certifications"] == []


class TestParseScoringResponse:
    def test_valid_json(self):
        text = '{"score": 85, "matched_skills": ["Python"], "skill_gaps": ["Go"], "recommendation": "Good"}'
        result = _parse_scoring_response(text)
        assert result["score"] == 85
        assert "Python" in result["matched_skills"]

    def test_json_in_text(self):
        text = 'Here is the result: {"score": 70, "matched_skills": [], "skill_gaps": [], "recommendation": "OK"}'
        result = _parse_scoring_response(text)
        assert result["score"] == 70

    def test_score_clamped_to_100(self):
        text = '{"score": 150, "matched_skills": [], "skill_gaps": [], "recommendation": ""}'
        result = _parse_scoring_response(text)
        assert result["score"] == 100

    def test_score_clamped_to_0(self):
        text = '{"score": -10, "matched_skills": [], "skill_gaps": [], "recommendation": ""}'
        result = _parse_scoring_response(text)
        assert result["score"] == 0

    def test_invalid_json(self):
        text = "No valid JSON here"
        result = _parse_scoring_response(text)
        assert result["score"] == 0


class TestPiiFilter:
    def test_mask_email(self):
        result = mask_pii_in_text("Contact: test@example.com")
        assert "[MASKED:email]" in result
        assert "test@example.com" not in result

    def test_mask_phone_jp(self):
        result = mask_pii_in_text("電話: 03-1234-5678")
        assert "[MASKED:phone_jp]" in result

    def test_remove_protected_characteristics(self):
        pii_filter = PiiFilter(mode="strict")
        data = {
            "skills": ["Python", "AWS"],
            "age": 35,
            "gender": "male",
            "nationality": "Japanese",
            "experience_years": 5,
        }
        result = pii_filter.remove_protected_characteristics(data)
        assert "skills" in result
        assert "experience_years" in result
        assert "age" not in result
        assert "gender" not in result
        assert "nationality" not in result

    def test_contains_protected_characteristics(self):
        pii_filter = PiiFilter()
        text = "田中太郎 35歳 男性 日本国籍"
        found = pii_filter.contains_protected_characteristics(text)
        assert "歳" in found or "男性" in found

    def test_scoring_exclusion_prompt(self):
        pii_filter = PiiFilter()
        prompt = pii_filter.create_scoring_exclusion_prompt()
        assert "年齢" in prompt
        assert "性別" in prompt
        assert "国籍" in prompt

    def test_strict_mode_detection(self):
        os.environ["PII_MODE"] = "strict"
        assert is_strict_mode() is True
        os.environ["PII_MODE"] = "standard"
        assert is_strict_mode() is False
        # Reset
        os.environ["PII_MODE"] = "strict"
