"""データ分類ラベル定義

全 UC の出力 JSON に統一的な data_classification フィールドを付与するための定数。
Public Sector (UC15/16/17) では CUI/UNCLASSIFIED 等を使用し、
その他の UC ではデフォルト INTERNAL を使用する。

Usage:
    from shared.data_classification import DataClassification, get_classification

    # 環境変数から取得（デフォルト: INTERNAL）
    classification = get_classification()

    # 出力 JSON に付与
    result["data_classification"] = classification.value
    result["data_classification_label"] = classification.label
"""

from __future__ import annotations

import os
from enum import Enum


class DataClassification(Enum):
    """データ分類レベル

    NIST SP 800-171 / NARA GRS / 一般企業向けの分類体系を統合。
    """

    # Public Sector 向け
    UNCLASSIFIED = "UNCLASSIFIED"
    CUI = "CUI"
    CONFIDENTIAL = "CONFIDENTIAL"

    # 一般企業向け
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    RESTRICTED = "RESTRICTED"
    HIGHLY_RESTRICTED = "HIGHLY_RESTRICTED"

    @property
    def label(self) -> str:
        labels = {
            "UNCLASSIFIED": "Unclassified — No restrictions",
            "CUI": "Controlled Unclassified Information",
            "CONFIDENTIAL": "Confidential — Government classified",
            "PUBLIC": "Public — No restrictions",
            "INTERNAL": "Internal — Company internal use only",
            "RESTRICTED": "Restricted — Limited access",
            "HIGHLY_RESTRICTED": "Highly Restricted — Need-to-know basis",
        }
        return labels.get(self.value, self.value)


def get_classification() -> DataClassification:
    """環境変数 DATA_CLASSIFICATION からデータ分類を取得する。

    Returns:
        DataClassification: データ分類レベル（デフォルト: INTERNAL）
    """
    env_value = os.environ.get("DATA_CLASSIFICATION", "INTERNAL").upper()
    try:
        return DataClassification(env_value)
    except ValueError:
        return DataClassification.INTERNAL
