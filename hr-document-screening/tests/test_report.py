"""UC27 HR Document Screening — Report Lambda unit tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_handler_path = Path(__file__).parent.parent / "functions" / "report" / "handler.py"
_spec = importlib.util.spec_from_file_location("hr_report_handler", _handler_path)
_module = importlib.util.module_from_spec(_spec)
sys.modules["hr_report_handler"] = _module
_spec.loader.exec_module(_module)

compute_pipeline_summary = _module.compute_pipeline_summary


class TestComputePipelineSummary:
    def test_basic_summary(self):
        scored_results = [
            {
                "status": "success",
                "position_type": "engineering",
                "candidate_data": {"skills": ["Python", "AWS"]},
                "scoring": {"score": 85},
            },
            {
                "status": "success",
                "position_type": "engineering",
                "candidate_data": {"skills": ["Java", "AWS"]},
                "scoring": {"score": 60},
            },
            {
                "status": "success",
                "position_type": "sales",
                "candidate_data": {"skills": ["Communication"]},
                "scoring": {"score": 45},
            },
        ]

        result = compute_pipeline_summary(scored_results)
        assert result["total_candidates"] == 3
        assert result["processed"] == 3
        assert result["errors"] == 0
        assert result["score_distribution"]["high_match_80_plus"] == 1
        assert result["score_distribution"]["medium_match_50_79"] == 1
        assert result["score_distribution"]["low_match_below_50"] == 1
        assert "AWS" in result["skill_distribution"]

    def test_empty_results(self):
        result = compute_pipeline_summary([])
        assert result["total_candidates"] == 0
        assert result["score_distribution"]["average_score"] == 0.0

    def test_all_errors(self):
        scored_results = [
            {"status": "error", "error_type": "TRANSIENT"},
            {"status": "error", "error_type": "PARSE_ERROR"},
        ]
        result = compute_pipeline_summary(scored_results)
        assert result["total_candidates"] == 2
        assert result["processed"] == 0
        assert result["errors"] == 2

    def test_position_breakdown(self):
        scored_results = [
            {
                "status": "success",
                "position_type": "engineering",
                "candidate_data": {"skills": []},
                "scoring": {"score": 80},
            },
            {
                "status": "success",
                "position_type": "engineering",
                "candidate_data": {"skills": []},
                "scoring": {"score": 60},
            },
        ]
        result = compute_pipeline_summary(scored_results)
        assert result["position_breakdown"]["engineering"]["count"] == 2
        assert result["position_breakdown"]["engineering"]["avg_score"] == 70.0
