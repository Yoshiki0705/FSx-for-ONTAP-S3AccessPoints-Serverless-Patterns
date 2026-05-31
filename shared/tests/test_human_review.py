"""Tests for shared.human_review module."""

import os
from unittest.mock import patch


from shared.human_review import (
    HumanReviewDecision,
    evaluate_confidence,
    format_sns_subject,
)


class TestEvaluateConfidence:
    """evaluate_confidence() tests."""

    def test_high_confidence_auto_approves(self):
        decision = evaluate_confidence(0.95, threshold_auto_approve=0.85)
        assert decision.action == "AUTO_APPROVE"
        assert decision.requires_review is False
        assert decision.confidence == 0.95

    def test_medium_confidence_requires_review(self):
        decision = evaluate_confidence(0.70, threshold_auto_approve=0.85, threshold_reject=0.30)
        assert decision.action == "HUMAN_REVIEW"
        assert decision.requires_review is True

    def test_low_confidence_rejects(self):
        decision = evaluate_confidence(0.20, threshold_auto_approve=0.85, threshold_reject=0.30)
        assert decision.action == "REJECT"
        assert decision.requires_review is True

    def test_boundary_auto_approve(self):
        decision = evaluate_confidence(0.85, threshold_auto_approve=0.85)
        assert decision.action == "AUTO_APPROVE"

    def test_boundary_reject(self):
        decision = evaluate_confidence(0.30, threshold_auto_approve=0.85, threshold_reject=0.30)
        assert decision.action == "HUMAN_REVIEW"

    def test_env_variable_thresholds(self):
        with patch.dict(
            os.environ,
            {
                "HUMAN_REVIEW_AUTO_APPROVE_THRESHOLD": "0.90",
                "HUMAN_REVIEW_REJECT_THRESHOLD": "0.50",
            },
        ):
            decision = evaluate_confidence(0.88)
            assert decision.action == "HUMAN_REVIEW"

    def test_to_dict(self):
        decision = evaluate_confidence(0.75, threshold_auto_approve=0.85)
        d = decision.to_dict()
        assert "confidence_score" in d
        assert "requires_review" in d
        assert "action" in d
        assert "reason" in d


class TestFormatSnsSubject:
    """format_sns_subject() tests."""

    def test_auto_approve_no_prefix(self):
        decision = HumanReviewDecision(
            confidence=0.95, requires_review=False, action="AUTO_APPROVE", reason="High confidence"
        )
        subject = format_sns_subject("UC1 Legal", decision, file_count=10)
        assert "[REVIEW REQUIRED]" not in subject
        assert "UC1 Legal" in subject
        assert "10 files" in subject

    def test_human_review_has_prefix(self):
        decision = HumanReviewDecision(
            confidence=0.70, requires_review=True, action="HUMAN_REVIEW", reason="Low confidence"
        )
        subject = format_sns_subject("UC1 Legal", decision, file_count=5)
        assert "[REVIEW REQUIRED]" in subject

    def test_reject_has_escalation_prefix(self):
        decision = HumanReviewDecision(
            confidence=0.20, requires_review=True, action="REJECT", reason="Very low confidence"
        )
        subject = format_sns_subject("UC15 Defense", decision, file_count=2)
        assert "[ESCALATION]" in subject
