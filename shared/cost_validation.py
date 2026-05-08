"""shared.cost_validation - コスト最適化バリデーション共通モジュール

Scheduled Scaling と Billing Alarm のパラメータバリデーションを提供する。

設計方針:
- Scheduled Scaling: ビジネスアワーの時間順序とキャパシティ制約を検証
- Billing Alarm: 閾値の厳密順序（warning < critical < emergency）を検証
- 全バリデーション関数は (is_valid, error_message) タプルを返す

Usage:
    from shared.cost_validation import validate_scaling_schedule, validate_billing_thresholds

    is_valid, error = validate_scaling_schedule(
        business_hours_start=9, business_hours_end=18,
        business_min_capacity=1, business_max_capacity=4,
        off_hours_min_capacity=0, off_hours_max_capacity=1,
    )
    assert is_valid is True

    is_valid, error = validate_billing_thresholds(warning=50.0, critical=100.0, emergency=500.0)
    assert is_valid is True
"""

from __future__ import annotations

from typing import Optional

# ビジネスアワーの有効範囲（0–23 時）
HOURS_MIN: int = 0
HOURS_MAX: int = 23

# キャパシティの最小値
CAPACITY_MIN: int = 0


def validate_scaling_schedule(
    business_hours_start: int,
    business_hours_end: int,
    business_min_capacity: int,
    business_max_capacity: int,
    off_hours_min_capacity: int,
    off_hours_max_capacity: int,
) -> tuple[bool, Optional[str]]:
    """Scheduled Scaling パラメータをバリデーションする。

    Application Auto Scaling の Scheduled Actions に設定する
    ビジネスアワーとキャパシティ値の整合性を検証する。

    バリデーションルール:
        - business_hours_start, business_hours_end: [0, 23] の範囲内
        - business_hours_start < business_hours_end（同一日内の時間順序）
        - 全キャパシティ値 >= 0
        - business_min_capacity <= business_max_capacity
        - off_hours_min_capacity <= off_hours_max_capacity
        - off_hours_max_capacity <= business_min_capacity（コスト削減保証）

    Args:
        business_hours_start: ビジネスアワー開始時刻（0–23）
        business_hours_end: ビジネスアワー終了時刻（0–23）
        business_min_capacity: ビジネスアワー最小キャパシティ
        business_max_capacity: ビジネスアワー最大キャパシティ
        off_hours_min_capacity: オフアワー最小キャパシティ
        off_hours_max_capacity: オフアワー最大キャパシティ

    Returns:
        tuple[bool, Optional[str]]: (is_valid, error_message)
            - is_valid が True の場合、error_message は None
            - is_valid が False の場合、error_message にエラー詳細を含む
    """
    # Validate hours range
    if business_hours_start < HOURS_MIN or business_hours_start > HOURS_MAX:
        return (
            False,
            f"Invalid business_hours_start: {business_hours_start}. "
            f"Must be in range [{HOURS_MIN}, {HOURS_MAX}]",
        )

    if business_hours_end < HOURS_MIN or business_hours_end > HOURS_MAX:
        return (
            False,
            f"Invalid business_hours_end: {business_hours_end}. "
            f"Must be in range [{HOURS_MIN}, {HOURS_MAX}]",
        )

    # Validate time ordering (same day)
    if business_hours_start >= business_hours_end:
        return (
            False,
            f"business_hours_start ({business_hours_start}) must be less than "
            f"business_hours_end ({business_hours_end})",
        )

    # Validate all capacity values >= 0
    if business_min_capacity < CAPACITY_MIN:
        return (
            False,
            f"Invalid business_min_capacity: {business_min_capacity}. "
            f"Must be >= {CAPACITY_MIN}",
        )

    if business_max_capacity < CAPACITY_MIN:
        return (
            False,
            f"Invalid business_max_capacity: {business_max_capacity}. "
            f"Must be >= {CAPACITY_MIN}",
        )

    if off_hours_min_capacity < CAPACITY_MIN:
        return (
            False,
            f"Invalid off_hours_min_capacity: {off_hours_min_capacity}. "
            f"Must be >= {CAPACITY_MIN}",
        )

    if off_hours_max_capacity < CAPACITY_MIN:
        return (
            False,
            f"Invalid off_hours_max_capacity: {off_hours_max_capacity}. "
            f"Must be >= {CAPACITY_MIN}",
        )

    # Validate business capacity ordering
    if business_min_capacity > business_max_capacity:
        return (
            False,
            f"business_min_capacity ({business_min_capacity}) must be less than or equal to "
            f"business_max_capacity ({business_max_capacity})",
        )

    # Validate off-hours capacity ordering
    if off_hours_min_capacity > off_hours_max_capacity:
        return (
            False,
            f"off_hours_min_capacity ({off_hours_min_capacity}) must be less than or equal to "
            f"off_hours_max_capacity ({off_hours_max_capacity})",
        )

    # Validate cost reduction guarantee
    if off_hours_max_capacity > business_min_capacity:
        return (
            False,
            f"off_hours_max_capacity ({off_hours_max_capacity}) must be less than or equal to "
            f"business_min_capacity ({business_min_capacity}) for cost reduction guarantee",
        )

    return (True, None)


def validate_billing_thresholds(
    warning: float,
    critical: float,
    emergency: float,
) -> tuple[bool, Optional[str]]:
    """Billing Alarm 閾値をバリデーションする。

    CloudWatch Billing Alarm の 3 段階閾値が厳密な昇順であることを検証する。

    バリデーションルール:
        - 全閾値 > 0
        - warning < critical < emergency（厳密順序）

    Args:
        warning: 警告閾値（USD）
        critical: 重大閾値（USD）
        emergency: 緊急閾値（USD）

    Returns:
        tuple[bool, Optional[str]]: (is_valid, error_message)
            - is_valid が True の場合、error_message は None
            - is_valid が False の場合、error_message にエラー詳細を含む
    """
    # Validate all values > 0
    if warning <= 0:
        return (
            False,
            f"Invalid warning threshold: {warning}. Must be > 0",
        )

    if critical <= 0:
        return (
            False,
            f"Invalid critical threshold: {critical}. Must be > 0",
        )

    if emergency <= 0:
        return (
            False,
            f"Invalid emergency threshold: {emergency}. Must be > 0",
        )

    # Validate strict ordering
    if warning >= critical:
        return (
            False,
            f"warning ({warning}) must be strictly less than critical ({critical})",
        )

    if critical >= emergency:
        return (
            False,
            f"critical ({critical}) must be strictly less than emergency ({emergency})",
        )

    return (True, None)
