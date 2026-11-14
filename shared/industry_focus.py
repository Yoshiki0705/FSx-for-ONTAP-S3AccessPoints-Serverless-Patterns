"""Industry focus hints for the AI summarization step.

An industry id (for example ``legal``) selects a short list of things the
summary should pay attention to. The id is looked up in a fixed table: a value
that is not in the table is ignored, and the caller's text is never placed in
the prompt. The ids match the industries of the RAG app's industry cards.

The hints steer the summary only. They do not turn the summary into a
professional judgement; the Human Review thresholds in ``shared.human_review``
still decide what is passed to a person.
"""

from __future__ import annotations

from typing import Any

# id -> what the summary should pay attention to (Japanese, because the summary is Japanese).
INDUSTRY_FOCUS: dict[str, str] = {
    "government": "条例・規則・通達の名称と条番号、公開前に確認が要る個人情報や非開示情報の可能性",
    "healthcare": "手順書やガイドラインの名称、数値と単位（原文のまま）、患者を特定できる記述の有無。診断や治療方針は述べない",
    "legal": "契約当事者、期間、解除・損害賠償・秘密保持などの条項と条番号。法的助言は述べない",
    "insurance": "事案の種類、必要書類と不足、適用される約款や査定基準。支払可否は述べない",
    "manufacturing": "品質基準、仕様の値と許容差（原文のまま）、不具合の原因と是正処置",
    "construction": "安全基準、工程、設計変更の内容と影響を受ける図面や協力会社",
    "education": "科目や制度の名称、成績や評価の方針、研究計画や助成の要件。個人の成績は述べない",
    "financial": "金額、通貨、期日、当事者。予算・実績・見込みの区別。数値は丸めない",
    "media": "素材やプロジェクトの名称、利用許諾の範囲・期間・地域、審査の指摘",
    "semiconductor": "設計仕様と設計ルールの該当箇所、検証結果の重大度、リビジョン間の変更点",
    "lifesciences": "実験や手順の名称、取扱い・保管・緊急時対応の要点、数値（原文のまま）、手順の逸脱",
    "energy": "設備名、点検日と指摘事項、調査の目的・方法・結果、保安規程の該当箇所",
    "automotive": "試験や走行の条件と日付、不具合と対策、仕様変更の影響を受ける仕様書や試験",
    "retail": "商品名と仕様、取引条件、返品規程。資料にない効能や性能は述べない",
    "logistics": "伝票番号、日付、車両や設備の点検・整備記録、運送契約の条項",
    "telecom": "障害の症状と発生日時、対応手順、変更の影響を受けるサービスと手順書",
    "agrifood": "ロット番号、原料から出荷までの記録、衛生・品質検査で基準を外れた点",
    "realestate": "物件名、賃貸借の期間・賃料・更新・解約の条件、修繕と点検の履歴",
    "hr": "制度や手続の名称、対象者、期限。個人の人事記録は述べない",
    "esg": "指標名、実績値、年度と単位、開示基準との対応と不足している情報",
    "travel": "予約や手配の番号、日付、取消規定と料金",
}


def normalize_industry(value: Any) -> str | None:
    """Return the industry id when it is in the table, otherwise None."""
    if isinstance(value, str) and value in INDUSTRY_FOCUS:
        return value
    return None


def focus_hint(industry: str | None) -> str:
    """Prompt text for the industry, or an empty string when there is none."""
    if industry is None or industry not in INDUSTRY_FOCUS:
        return ""
    return f"業種: {industry}。要約では次の点に注目してください: {INDUSTRY_FOCUS[industry]}。\n"
