"""operations/ の analyze ハンドラの property-based テスト

AGENTS.md の Definition of Done は「unit tests + property-based tests pass」を
求めているが、operations/ の 6 パターンには hypothesis を使ったテストが 1 件も
無かった。既存の unit テストは代表値を数点ずつ確認するもので、境界や組み合わせは
覆われていない。

ここで固定するのは、入力によらず成立すべき不変条件:

- total_recommendations は各解析結果の推奨件数の合計と一致する
- summary の件数は入力の件数と一致する
- 推奨は入力に根拠があるときだけ出る（無条件に出さない）
- 空入力でも例外にならず、空の結果を返す

パターン固有の閾値の妥当性は各パターンの unit テストの仕事。
"""

from __future__ import annotations

import importlib.util
import os
import sys
import uuid
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_analyze(pattern: str):
    path = REPO_ROOT / "operations" / pattern / "functions" / "analyze" / "handler.py"
    mod_name = f"ops_analyze_{pattern.replace('-', '_')}_{uuid.uuid4().hex[:8]}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


# Bedrock 呼び出しは property テストの対象外。無効化して解析ロジックだけを見る。
os.environ["ENABLE_BEDROCK_SUMMARY"] = "false"

QOS = _load_analyze("qos-monitoring")
EFFICIENCY = _load_analyze("storage-efficiency")
COST = _load_analyze("cost-optimization")


# --- 入力ストラテジ ----------------------------------------------------------

volume_names = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), max_codepoint=127),
    min_size=1,
    max_size=12,
)

qos_policy = st.fixed_dictionaries(
    {
        "name": volume_names,
        "max_throughput_iops": st.one_of(st.none(), st.integers(min_value=1, max_value=100000)),
        "max_throughput_mbps": st.one_of(st.none(), st.integers(min_value=1, max_value=10000)),
        "assigned_volume_count": st.integers(min_value=0, max_value=40),
    }
)

qos_fs = st.fixed_dictionaries(
    {
        "fs_id": volume_names,
        "qos_policies": st.lists(qos_policy, max_size=6),
        "volumes_without_qos": st.lists(volume_names, max_size=8),
    }
)


class TestQosAnalyzeProperties:
    """qos-monitoring の analyze の不変条件"""

    @settings(max_examples=150, deadline=None)
    @given(file_systems=st.lists(qos_fs, max_size=4))
    def test_total_matches_sum_of_recommendations(self, file_systems):
        """total_recommendations が各結果の推奨件数の合計と一致することを検証する

        ここがずれると、レポートの見出し件数と明細が食い違う。
        """
        result = QOS.handler({"file_systems": file_systems}, None)

        expected = sum(len(a["recommendations"]) for a in result["analyses"])
        assert result["total_recommendations"] == expected

    @settings(max_examples=150, deadline=None)
    @given(file_systems=st.lists(qos_fs, max_size=4))
    def test_one_analysis_per_input_file_system(self, file_systems):
        """入力のファイルシステム数と解析結果数が一致することを検証する"""
        result = QOS.handler({"file_systems": file_systems}, None)

        assert len(result["analyses"]) == len(file_systems)

    @settings(max_examples=150, deadline=None)
    @given(file_systems=st.lists(qos_fs, max_size=4))
    def test_summary_counts_match_the_input(self, file_systems):
        """summary の件数が入力そのものと一致することを検証する"""
        result = QOS.handler({"file_systems": file_systems}, None)

        for fs_in, analysis in zip(file_systems, result["analyses"], strict=True):
            summary = analysis["summary"]
            assert summary["total_policies"] == len(fs_in["qos_policies"])
            assert summary["volumes_without_qos"] == len(fs_in["volumes_without_qos"])
            assert summary["recommendation_count"] == len(analysis["recommendations"])
            # limits あり + unlimited は総数を超えない
            assert summary["policies_with_limits"] + summary["policies_unlimited"] <= summary["total_policies"]

    @settings(max_examples=150, deadline=None)
    @given(file_systems=st.lists(qos_fs, max_size=4))
    def test_assign_policy_recommendation_requires_unassigned_volumes(self, file_systems):
        """QoS 未割り当ての推奨は、実際に未割り当てがあるときだけ出ることを検証する

        根拠なく推奨を出すと、運用側の信頼を落とす。
        """
        result = QOS.handler({"file_systems": file_systems}, None)

        for fs_in, analysis in zip(file_systems, result["analyses"], strict=True):
            kinds = {r["type"] for r in analysis["recommendations"]}
            if "assign_qos_policy" in kinds:
                assert fs_in["volumes_without_qos"], "recommended assigning a QoS policy with no unassigned volumes"

    @settings(max_examples=100, deadline=None)
    @given(file_systems=st.lists(qos_fs, max_size=4))
    def test_every_recommendation_has_type_and_severity(self, file_systems):
        """推奨に type と severity が必ず付くことを検証する

        レポート側がこの 2 つで並べ替えるため、欠けると出力が壊れる。
        """
        result = QOS.handler({"file_systems": file_systems}, None)

        for analysis in result["analyses"]:
            for rec in analysis["recommendations"]:
                assert rec.get("type"), f"recommendation without type: {rec}"
                assert rec.get("severity") in {"low", "medium", "high"}, f"unexpected severity: {rec.get('severity')}"

    def test_empty_input_is_not_an_error(self):
        """入力が空でも例外にならず、空の結果を返すことを検証する

        収集側が 0 件を返すのは正常な状態（対象のファイルシステムが無い）。
        """
        result = QOS.handler({"file_systems": []}, None)

        assert result["analyses"] == []
        assert result["total_recommendations"] == 0

    def test_missing_key_is_treated_as_empty(self):
        """file_systems キー自体が無くても落ちないことを検証する"""
        result = QOS.handler({}, None)

        assert result["analyses"] == []
        assert result["total_recommendations"] == 0


# --- storage-efficiency / cost-optimization -----------------------------------


class TestAnalyzeHandlersShareTheOutputShape:
    """3 パターンの analyze が同じ出力形を保つことを検証する

    レポート側は analyses / total_recommendations を前提にしている。片方だけ形が
    変わると、そのパターンのレポートが静かに空になる。
    """

    def test_empty_input_shape_is_consistent(self):
        for module in (QOS, EFFICIENCY, COST):
            result = module.handler({"file_systems": []}, None)

            assert "analyses" in result
            assert result["analyses"] == []
            assert "analyzed_at" in result

    def test_total_recommendations_present_where_recommendations_are_produced(self):
        # cost-optimization は推奨ではなくコスト内訳が主だが、キー自体は揃えている
        for module in (QOS, EFFICIENCY):
            result = module.handler({"file_systems": []}, None)
            assert result["total_recommendations"] == 0
