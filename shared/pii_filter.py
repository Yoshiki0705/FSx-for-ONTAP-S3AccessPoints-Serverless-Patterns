"""PII フィルタリング + ログマスキングモジュール

UC27 (HR) および UC20 (旅行) で使用する PII 保護機能を提供する。

機能:
    - PII_MODE=strict: ログへの PII 出力禁止
    - 保護特性（年齢、性別、国籍）のフィルタリング
    - 暗号化出力の強制
    - 監査証跡の記録

Environment Variables:
    PII_MODE: PII 保護モード (strict/standard, default: strict)
    KMS_KEY_ARN: 出力暗号化用 KMS キー ARN

Usage:
    from shared.pii_filter import PiiFilter, mask_pii_in_text, is_strict_mode

    # テキストから PII をマスク
    masked = mask_pii_in_text("田中太郎 35歳 男性")

    # 保護特性を除外
    pii_filter = PiiFilter()
    cleaned = pii_filter.remove_protected_characteristics(data)
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# 保護特性カテゴリ
PROTECTED_CHARACTERISTICS: frozenset[str] = frozenset({
    "age",
    "gender",
    "sex",
    "nationality",
    "race",
    "ethnicity",
    "religion",
    "disability",
    "marital_status",
    "sexual_orientation",
})

# 保護特性キーワード（日本語 + 英語）
PROTECTED_KEYWORDS_JA: frozenset[str] = frozenset({
    "年齢", "性別", "国籍", "人種", "民族", "宗教",
    "障害", "配偶者", "婚姻", "歳", "男性", "女性",
})

PROTECTED_KEYWORDS_EN: frozenset[str] = frozenset({
    "age", "gender", "sex", "nationality", "race", "ethnicity",
    "religion", "disability", "marital", "married", "single",
})

# PII パターン（マスク対象）
PII_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("email", re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")),
    ("phone_jp", re.compile(r"0\d{1,4}-?\d{1,4}-?\d{3,4}")),
    ("phone_intl", re.compile(r"\+\d{1,3}[-\s]?\d{1,14}")),
    ("address_jp", re.compile(r"〒?\d{3}-?\d{4}")),
    ("mynumber", re.compile(r"\d{4}\s?\d{4}\s?\d{4}")),
]


def is_strict_mode() -> bool:
    """PII_MODE が strict かどうかを返す。

    Returns:
        bool: strict モードの場合 True
    """
    return os.environ.get("PII_MODE", "strict").lower() == "strict"


def mask_pii_in_text(text: str) -> str:
    """テキスト中の PII パターンをマスクする。

    Args:
        text: 入力テキスト

    Returns:
        str: PII がマスクされたテキスト
    """
    if not text:
        return text

    masked = text
    for pattern_name, pattern in PII_PATTERNS:
        masked = pattern.sub(f"[MASKED:{pattern_name}]", masked)

    return masked


class PiiFilter:
    """PII フィルタリングクラス。

    ログ出力のマスキングと保護特性の除外を行う。
    """

    def __init__(self, mode: str | None = None):
        """初期化。

        Args:
            mode: PII モード (strict/standard)。None の場合は環境変数から取得。
        """
        self.mode = mode or os.environ.get("PII_MODE", "strict")
        self.strict = self.mode.lower() == "strict"
        self.audit_log: list[dict] = []

    def filter_log_message(self, message: str) -> str:
        """ログメッセージから PII を除去する。

        strict モードではすべての PII パターンをマスクする。

        Args:
            message: ログメッセージ

        Returns:
            str: フィルタリングされたメッセージ
        """
        if not self.strict:
            return message
        return mask_pii_in_text(message)

    def remove_protected_characteristics(self, data: dict) -> dict:
        """辞書データから保護特性フィールドを除去する。

        Args:
            data: 入力データ辞書

        Returns:
            dict: 保護特性が除去されたデータ
        """
        if not data:
            return data

        cleaned: dict = {}
        removed_keys: list[str] = []

        for key, value in data.items():
            key_lower = key.lower().replace("-", "_").replace(" ", "_")
            if key_lower in PROTECTED_CHARACTERISTICS:
                removed_keys.append(key)
                continue
            cleaned[key] = value

        if removed_keys:
            self._record_audit(
                action="protected_characteristic_removed",
                details={"removed_keys": removed_keys},
            )

        return cleaned

    def contains_protected_characteristics(self, text: str) -> list[str]:
        """テキスト内の保護特性キーワードを検出する。

        Args:
            text: 入力テキスト

        Returns:
            list[str]: 検出されたキーワードのリスト
        """
        if not text:
            return []

        found: list[str] = []
        text_lower = text.lower()

        for keyword in PROTECTED_KEYWORDS_JA:
            if keyword in text:
                found.append(keyword)

        for keyword in PROTECTED_KEYWORDS_EN:
            if keyword in text_lower:
                found.append(keyword)

        return found

    def create_scoring_exclusion_prompt(self) -> str:
        """Bedrock スコアリング時の保護特性除外プロンプトを生成する。

        Returns:
            str: 除外指示プロンプト
        """
        return (
            "重要: 以下の保護特性は評価から完全に除外してください。"
            "これらの情報に基づくスコアリングは禁止されています:\n"
            "- 年齢 (age)\n"
            "- 性別 (gender/sex)\n"
            "- 国籍 (nationality)\n"
            "- 人種・民族 (race/ethnicity)\n"
            "- 宗教 (religion)\n"
            "- 障害の有無 (disability)\n"
            "- 婚姻状況 (marital status)\n\n"
            "評価はスキル、経験、資格、実績のみに基づいてください。"
        )

    def validate_output_encryption(self, output_config: dict) -> bool:
        """出力設定が暗号化要件を満たしているか検証する。

        Args:
            output_config: 出力設定

        Returns:
            bool: 暗号化要件を満たしている場合 True
        """
        if not self.strict:
            return True

        kms_key = output_config.get("kms_key_arn") or os.environ.get("KMS_KEY_ARN")
        if not kms_key:
            self._record_audit(
                action="encryption_validation_failed",
                details={"reason": "KMS key not configured"},
            )
            return False
        return True

    def _record_audit(self, action: str, details: dict) -> None:
        """監査ログを記録する。

        Args:
            action: アクション名
            details: 詳細情報
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "mode": self.mode,
            "details": details,
        }
        self.audit_log.append(entry)
        logger.info("PII audit: action=%s, details=%s", action, details)

    def get_audit_trail(self) -> list[dict]:
        """監査証跡を取得する。

        Returns:
            list[dict]: 監査ログエントリのリスト
        """
        return list(self.audit_log)
