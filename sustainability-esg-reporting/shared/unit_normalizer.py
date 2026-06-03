"""ESG メトリクス単位正規化モジュール (UC23)

各 ESG メトリクスカテゴリに対して、ソース単位からターゲット単位への
正規化変換を行う。

正規化対象:
    - CO2 排出量: → tCO2e (トン CO2 換算)
    - エネルギー使用量: → MWh (メガワット時)
    - 廃棄物量: → t (メートルトン)
    - 水使用量: → m3 (立方メートル)

バリデーション:
    - 単位なし: "requires-validation" (reason: "missing_unit")
    - 単位矛盾: "requires-validation" (reason: "conflicting_units")
    - 範囲外値: "requires-validation" (reason: "out_of_range")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Unit Normalization Tables
# ─────────────────────────────────────────────────────────────────────────────

UNIT_NORMALIZATION: dict[str, dict[str, Any]] = {
    "co2_emissions": {
        "target": "tCO2e",
        "conversions": {"kg": 0.001, "t": 1.0, "Mt": 1_000_000},
    },
    "energy_usage": {
        "target": "MWh",
        "conversions": {"kWh": 0.001, "GWh": 1000, "GJ": 0.2778},
    },
    "waste_volume": {
        "target": "t",
        "conversions": {"kg": 0.001, "t": 1.0},
    },
    "water_usage": {
        "target": "m3",
        "conversions": {"L": 0.001, "kL": 1.0, "ML": 1000},
    },
}

# プラウシブルレンジ (1施設あたりの年間値の妥当範囲)
PLAUSIBLE_RANGES: dict[str, dict[str, float]] = {
    "co2_emissions": {"min": 0.0, "max": 100_000_000.0},  # 0 〜 100M tCO2e
    "energy_usage": {"min": 0.0, "max": 1_000_000.0},     # 0 〜 1M MWh
    "waste_volume": {"min": 0.0, "max": 10_000_000.0},    # 0 〜 10M t
    "water_usage": {"min": 0.0, "max": 100_000_000.0},    # 0 〜 100M m3
}

# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class NormalizationResult:
    """正規化結果

    Attributes:
        value: 正規化された値 (None if requires-validation)
        unit: ターゲット単位
        status: "success" | "requires-validation"
        reason: バリデーション失敗理由 (成功時は None)
        original_value: 元の値
        original_unit: 元の単位
    """

    value: float | None
    unit: str
    status: str
    reason: str | None
    original_value: float
    original_unit: str | None


# ─────────────────────────────────────────────────────────────────────────────
# Core Functions
# ─────────────────────────────────────────────────────────────────────────────


def get_supported_categories() -> list[str]:
    """サポートされているメトリクスカテゴリ一覧を返す。

    Returns:
        list[str]: カテゴリ名リスト
    """
    return list(UNIT_NORMALIZATION.keys())


def get_target_unit(category: str) -> str | None:
    """カテゴリのターゲット単位を返す。

    Args:
        category: メトリクスカテゴリ名

    Returns:
        str | None: ターゲット単位、カテゴリが存在しない場合は None
    """
    config = UNIT_NORMALIZATION.get(category)
    if config is None:
        return None
    return config["target"]


def get_supported_units(category: str) -> list[str]:
    """カテゴリでサポートされている入力単位一覧を返す。

    Args:
        category: メトリクスカテゴリ名

    Returns:
        list[str]: サポートされている単位リスト (空リストならカテゴリなし)
    """
    config = UNIT_NORMALIZATION.get(category)
    if config is None:
        return []
    return list(config["conversions"].keys())


def normalize_value(
    value: float,
    unit: str | None,
    category: str,
) -> NormalizationResult:
    """メトリクス値を正規化する。

    Args:
        value: 元の数値
        unit: 元の単位 (None の場合は missing_unit)
        category: メトリクスカテゴリ

    Returns:
        NormalizationResult: 正規化結果
    """
    config = UNIT_NORMALIZATION.get(category)
    if config is None:
        logger.warning("Unknown category: %s", category)
        return NormalizationResult(
            value=None,
            unit="unknown",
            status="requires-validation",
            reason="unknown_category",
            original_value=value,
            original_unit=unit,
        )

    target_unit = config["target"]
    conversions = config["conversions"]

    # 単位なしチェック
    if unit is None or unit.strip() == "":
        return NormalizationResult(
            value=None,
            unit=target_unit,
            status="requires-validation",
            reason="missing_unit",
            original_value=value,
            original_unit=unit,
        )

    # 既にターゲット単位の場合
    if unit == target_unit:
        normalized = value
    elif unit in conversions:
        conversion_factor = conversions[unit]
        normalized = value * conversion_factor
    else:
        # 不明な単位
        return NormalizationResult(
            value=None,
            unit=target_unit,
            status="requires-validation",
            reason="conflicting_units",
            original_value=value,
            original_unit=unit,
        )

    # 範囲チェック
    plausible = PLAUSIBLE_RANGES.get(category)
    if plausible:
        if normalized < plausible["min"] or normalized > plausible["max"]:
            return NormalizationResult(
                value=normalized,
                unit=target_unit,
                status="requires-validation",
                reason="out_of_range",
                original_value=value,
                original_unit=unit,
            )

    return NormalizationResult(
        value=normalized,
        unit=target_unit,
        status="success",
        reason=None,
        original_value=value,
        original_unit=unit,
    )


def normalize_metric_record(record: dict) -> dict:
    """メトリクスレコード辞書を正規化する。

    Args:
        record: メトリクスレコード (value, unit, category を含む)

    Returns:
        dict: 正規化結果を含むレコード
    """
    value = record.get("value")
    unit = record.get("unit")
    category = record.get("category")

    if value is None or category is None:
        return {
            **record,
            "normalized_value": None,
            "normalized_unit": None,
            "normalization_status": "requires-validation",
            "normalization_reason": "missing_value_or_category",
        }

    try:
        numeric_value = float(value)
    except (ValueError, TypeError):
        return {
            **record,
            "normalized_value": None,
            "normalized_unit": None,
            "normalization_status": "requires-validation",
            "normalization_reason": "non_numeric_value",
        }

    result = normalize_value(numeric_value, unit, category)

    return {
        **record,
        "normalized_value": result.value,
        "normalized_unit": result.unit,
        "normalization_status": result.status,
        "normalization_reason": result.reason,
    }
