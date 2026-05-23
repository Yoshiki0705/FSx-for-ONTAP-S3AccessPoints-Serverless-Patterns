"""Human Review 判定モジュール

AI/ML 処理結果の confidence_score に基づき、Human Review の要否を判定する。
閾値以下の場合は SNS 通知に「要 Human Review」フラグを付与する。

Usage:
    from shared.human_review import HumanReviewDecision, evaluate_confidence

    decision = evaluate_confidence(
        confidence=0.72,
        threshold_auto_approve=0.85,
        threshold_reject=0.50,
    )

    result["human_review"] = {
        "required": decision.requires_review,
        "reason": decision.reason,
        "confidence_score": decision.confidence,
        "action": decision.action,
    }
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal


@dataclass
class HumanReviewDecision:
    """Human Review 判定結果"""

    confidence: float
    requires_review: bool
    action: Literal["AUTO_APPROVE", "HUMAN_REVIEW", "REJECT"]
    reason: str

    def to_dict(self) -> dict:
        return {
            "confidence_score": self.confidence,
            "requires_review": self.requires_review,
            "action": self.action,
            "reason": self.reason,
        }


def evaluate_confidence(
    confidence: float,
    threshold_auto_approve: float | None = None,
    threshold_reject: float | None = None,
) -> HumanReviewDecision:
    """Confidence score に基づき Human Review の要否を判定する。

    Args:
        confidence: AI/ML モデルの confidence score (0.0 - 1.0)
        threshold_auto_approve: 自動承認閾値（デフォルト: 環境変数 or 0.85）
        threshold_reject: 自動拒否閾値（デフォルト: 環境変数 or 0.30）

    Returns:
        HumanReviewDecision: 判定結果

    判定ロジック:
        confidence >= auto_approve → AUTO_APPROVE（Human Review 不要）
        confidence >= reject       → HUMAN_REVIEW（要レビュー）
        confidence < reject        → REJECT（自動拒否、要エスカレーション）
    """
    if threshold_auto_approve is None:
        threshold_auto_approve = float(
            os.environ.get("HUMAN_REVIEW_AUTO_APPROVE_THRESHOLD", "0.85")
        )
    if threshold_reject is None:
        threshold_reject = float(
            os.environ.get("HUMAN_REVIEW_REJECT_THRESHOLD", "0.30")
        )

    if confidence >= threshold_auto_approve:
        return HumanReviewDecision(
            confidence=confidence,
            requires_review=False,
            action="AUTO_APPROVE",
            reason=f"Confidence {confidence:.2f} >= auto-approve threshold {threshold_auto_approve:.2f}",
        )
    elif confidence >= threshold_reject:
        return HumanReviewDecision(
            confidence=confidence,
            requires_review=True,
            action="HUMAN_REVIEW",
            reason=f"Confidence {confidence:.2f} below auto-approve threshold {threshold_auto_approve:.2f}",
        )
    else:
        return HumanReviewDecision(
            confidence=confidence,
            requires_review=True,
            action="REJECT",
            reason=f"Confidence {confidence:.2f} below reject threshold {threshold_reject:.2f} — escalation required",
        )


def format_sns_subject(
    uc_name: str,
    decision: HumanReviewDecision,
    file_count: int = 0,
) -> str:
    """SNS 通知の Subject を生成する。

    Human Review 必要な場合は [REVIEW REQUIRED] プレフィックスを付与。
    """
    if decision.requires_review:
        prefix = "[REVIEW REQUIRED] " if decision.action == "HUMAN_REVIEW" else "[ESCALATION] "
    else:
        prefix = ""

    return f"{prefix}{uc_name}: {file_count} files processed (confidence: {decision.confidence:.0%})"
