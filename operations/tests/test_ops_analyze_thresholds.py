"""OPS2 / OPS5 / OPS6 の analyze の閾値・境界・障害耐性のテスト

これら 3 パターンは 5〜6 件のテストしか持たず、代表値を 1 点ずつ確認する構成だった。
推奨を出すか出さないかを決めているのは閾値なので、そこを外すと「推奨が出ない」
「根拠なく出る」のどちらかが静かに起きる。unit テストが最も効くのはここ。

各テストは実装から読み取った具体的な閾値を対象にする。閾値を変えたら落ちるように
書いてあるので、値を動かすときはここも一緒に見直すことになる。
"""

from __future__ import annotations

import importlib.util
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(pattern: str, func: str):
    path = REPO_ROOT / "operations" / pattern / "functions" / func / "handler.py"
    mod_name = f"ops_{pattern.replace('-', '_')}_{func}_{uuid.uuid4().hex[:8]}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def no_bedrock(monkeypatch):
    """Bedrock 呼び出しを止める。ここで見たいのは解析ロジックのみ。"""
    monkeypatch.setenv("ENABLE_BEDROCK_SUMMARY", "false")


def _fs(**kw):
    base = {"fs_id": "fs-example"}
    base.update(kw)
    return {"file_systems": [base]}


# --------------------------------------------------------------------------- #
# OPS2 storage-efficiency
# --------------------------------------------------------------------------- #

GIB = 1024**3


def _vol(name="v1", ratio=1.0, dedupe=False, compression=False, physical_gb=100.0, **kw):
    v = {
        "name": name,
        "overall_ratio": ratio,
        "dedupe_enabled": dedupe,
        "compression_enabled": compression,
        "physical_used_bytes": int(physical_gb * GIB),
    }
    v.update(kw)
    return v


class TestStorageEfficiencyThresholds:
    """OPS2: 推奨を出す/出さない境界"""

    @pytest.fixture
    def analyze(self):
        return _load("storage-efficiency", "analyze")

    def test_tiny_volume_produces_no_recommendation(self, analyze):
        """節約見込みが $1/月 以下なら推奨しないことを検証する

        小容量ボリュームまで推奨すると、対応する価値のない項目でレポートが埋まる。
        実装は savings_usd > 1.0 でふるい落としている。
        """
        # 0.1 GB * (1 - 1/2) * $0.125 = $0.006 -> 閾値以下
        result = analyze.handler(_fs(volumes=[_vol(physical_gb=0.1)]), None)

        assert result["total_recommendations"] == 0

    def test_volume_just_above_the_savings_floor_is_recommended(self, analyze):
        """節約見込みが $1/月 を超えれば推奨することを検証する"""
        # 20 GB * 0.5 * $0.125 = $1.25 -> 閾値超え
        result = analyze.handler(_fs(volumes=[_vol(physical_gb=20)]), None)

        assert result["total_recommendations"] == 1
        rec = result["analyses"][0]["recommendations"][0]
        assert rec["estimated_monthly_savings_usd"] > 1.0

    def test_low_ratio_needs_more_than_10gb(self, analyze):
        """既に有効なボリュームは 10 GB 超のときだけ低効率で推奨することを検証する

        小さいボリュームの効率比は誤差が大きく、チューニングの費用対効果が薄い。
        """
        small = analyze.handler(_fs(volumes=[_vol(ratio=1.1, dedupe=True, compression=True, physical_gb=5)]), None)
        large = analyze.handler(_fs(volumes=[_vol(ratio=1.1, dedupe=True, compression=True, physical_gb=50)]), None)

        assert small["total_recommendations"] == 0
        assert large["total_recommendations"] == 1

    def test_min_ratio_is_configurable(self, analyze, monkeypatch):
        """MIN_EFFICIENCY_RATIO で判定基準を変えられることを検証する"""
        vol = _vol(ratio=1.8, dedupe=True, compression=True, physical_gb=50)

        monkeypatch.setenv("MIN_EFFICIENCY_RATIO", "1.5")
        lenient = analyze.handler(_fs(volumes=[vol]), None)
        monkeypatch.setenv("MIN_EFFICIENCY_RATIO", "2.5")
        strict = analyze.handler(_fs(volumes=[vol]), None)

        assert lenient["total_recommendations"] == 0, "1.8 >= 1.5 なので推奨しない"
        assert strict["total_recommendations"] == 1, "1.8 < 2.5 なので推奨する"

    def test_high_ratio_volume_is_left_alone(self, analyze):
        """十分に効率が出ているボリュームには推奨しないことを検証する"""
        result = analyze.handler(_fs(volumes=[_vol(ratio=3.0, dedupe=True, compression=True, physical_gb=500)]), None)

        assert result["total_recommendations"] == 0

    def test_partially_enabled_volume_is_not_treated_as_disabled(self, analyze):
        """片方だけ有効なボリュームを「両方無効」と混同しないことを検証する

        実装は `not dedupe and not compression` を最初に見る。片方有効なら低効率判定
        の側に回る必要がある。
        """
        result = analyze.handler(_fs(volumes=[_vol(ratio=3.0, dedupe=True, compression=False, physical_gb=500)]), None)

        # 効率比が高いので推奨は出ない。ここで「両方有効化」が出たら分岐が壊れている。
        recs = result["analyses"][0]["recommendations"]
        assert all("Enable deduplication" not in r["recommendation"] for r in recs)

    def test_summary_counts_are_consistent(self, analyze):
        """summary の各カウントが入力と一致することを検証する"""
        volumes = [
            _vol("a", dedupe=True, compression=True, ratio=2.0),
            _vol("b", dedupe=False, compression=False, ratio=1.0),
            _vol("c", dedupe=True, compression=False, ratio=1.5),
        ]

        summary = analyze.handler(_fs(volumes=volumes), None)["analyses"][0]["summary"]

        assert summary["total_volumes"] == 3
        assert summary["volumes_with_both_enabled"] == 1
        assert summary["volumes_with_none"] == 1
        assert summary["avg_efficiency_ratio"] == pytest.approx(1.5, abs=0.01)

    def test_no_volumes_does_not_divide_by_zero(self, analyze):
        """ボリューム 0 件で平均を計算しても落ちないことを検証する

        実装は max(len(volumes), 1) で割っている。ここが素の len に戻ると
        ZeroDivisionError でワークフローが止まる。
        """
        summary = analyze.handler(_fs(volumes=[]), None)["analyses"][0]["summary"]

        assert summary["total_volumes"] == 0
        assert summary["avg_efficiency_ratio"] == 0.0

    def test_bedrock_failure_does_not_fail_the_analysis(self, analyze, monkeypatch):
        """Bedrock が失敗しても解析結果を返すことを検証する

        AI 要約は付加価値なので、失敗はワークフローを止める理由にならない。
        """
        monkeypatch.setenv("ENABLE_BEDROCK_SUMMARY", "true")

        with patch.object(analyze, "_generate_ai_summary", side_effect=RuntimeError("bedrock down")):
            with pytest.raises(RuntimeError):
                analyze.handler(_fs(volumes=[_vol(physical_gb=100)]), None)

        # 実装側の except は _generate_ai_summary の内部にあるので、
        # boto3 レベルの失敗を注入した場合は None が返り解析は継続する。
        with patch("boto3.client", side_effect=RuntimeError("bedrock down")):
            result = analyze.handler(_fs(volumes=[_vol(physical_gb=100)]), None)

        assert result["analyses"][0]["ai_summary"] is None
        assert result["total_recommendations"] == 1


# --------------------------------------------------------------------------- #
# OPS5 cost-optimization
# --------------------------------------------------------------------------- #


class TestCostOptimizationThresholds:
    """OPS5: コスト構成に基づく推奨の境界"""

    @pytest.fixture
    def analyze(self):
        return _load("cost-optimization", "analyze")

    def test_throughput_review_needs_more_than_half_the_cost(self, analyze):
        """スループットが総額の 50% を超えたときだけ推奨することを検証する"""
        under = analyze.handler(
            _fs(
                monthly_cost_breakdown={"throughput": 50, "ssd": 50},
                total_monthly_cost_usd=100,
            ),
            None,
        )
        over = analyze.handler(
            _fs(
                monthly_cost_breakdown={"throughput": 51, "ssd": 49},
                total_monthly_cost_usd=100,
            ),
            None,
        )

        assert "throughput_review" not in {r["type"] for r in under["analyses"][0]["recommendations"]}, (
            "ちょうど 50% では推奨しない"
        )
        assert "throughput_review" in {r["type"] for r in over["analyses"][0]["recommendations"]}

    def test_tiering_requires_ssd_dominance_and_little_pool_usage(self, analyze):
        """SSD が 60% 超 かつ Capacity Pool がほぼ未使用のときだけ推奨することを検証する

        既に階層化しているファイルシステムに「階層化しろ」と出すと信頼を落とす。
        """
        both = analyze.handler(
            _fs(
                monthly_cost_breakdown={"ssd": 70, "throughput": 30},
                total_monthly_cost_usd=100,
                capacity_pool_gb=0,
            ),
            None,
        )
        already_tiering = analyze.handler(
            _fs(
                monthly_cost_breakdown={"ssd": 70, "throughput": 30},
                total_monthly_cost_usd=100,
                capacity_pool_gb=500,
            ),
            None,
        )

        assert "enable_tiering" in {r["type"] for r in both["analyses"][0]["recommendations"]}
        assert "enable_tiering" not in {r["type"] for r in already_tiering["analyses"][0]["recommendations"]}

    def test_top_cost_driver_is_the_largest_component(self, analyze):
        """最大のコスト構成要素を top_cost_driver として選ぶことを検証する"""
        result = analyze.handler(
            _fs(
                monthly_cost_breakdown={"ssd": 10, "throughput": 90, "backup": 5},
                total_monthly_cost_usd=105,
            ),
            None,
        )

        assert result["analyses"][0]["summary"]["top_cost_driver"] == "throughput"

    def test_empty_breakdown_reports_unknown_driver(self, analyze):
        """内訳が空でも例外にならず unknown を返すことを検証する

        max() を空の辞書に対して呼ぶと ValueError になる。実装はガードしている。
        """
        result = analyze.handler(_fs(monthly_cost_breakdown={}, total_monthly_cost_usd=0), None)

        assert result["analyses"][0]["summary"]["top_cost_driver"] == "unknown"

    def test_projection_compounds_the_fixed_growth_rate(self, analyze):
        """3 か月予測が固定 5% の複利であることを検証する

        README にも「実測に基づかない固定値」と明記している。ここが変わるなら
        ドキュメントも一緒に直す必要がある。
        """
        result = analyze.handler(_fs(monthly_cost_breakdown={"ssd": 100}, total_monthly_cost_usd=100), None)

        summary = result["analyses"][0]["summary"]
        assert summary["growth_rate_percent"] == 5.0
        assert summary["projected_3month_cost_usd"] == pytest.approx(115.76, abs=0.01)

    def test_zero_cost_skips_the_ai_summary(self, analyze, monkeypatch):
        """総額 0 では AI 要約を呼ばないことを検証する

        コストが 0 のファイルシステムに要約は不要で、Bedrock の課金だけが発生する。
        """
        monkeypatch.setenv("ENABLE_BEDROCK_SUMMARY", "true")

        with patch("boto3.client") as mock_client:
            result = analyze.handler(_fs(monthly_cost_breakdown={}, total_monthly_cost_usd=0), None)

        assert result["analyses"][0]["ai_summary"] is None
        mock_client.assert_not_called()


# --------------------------------------------------------------------------- #
# OPS6 qos-monitoring
# --------------------------------------------------------------------------- #


def _policy(name="p", iops=None, mbps=None, count=0):
    return {
        "name": name,
        "max_throughput_iops": iops,
        "max_throughput_mbps": mbps,
        "assigned_volume_count": count,
    }


class TestQosMonitoringThresholds:
    """OPS6: 検出の境界"""

    @pytest.fixture
    def analyze(self):
        return _load("qos-monitoring", "analyze")

    def test_split_policy_needs_more_than_ten_volumes(self, analyze):
        """ポリシー分割の推奨は 10 本超のときだけ出ることを検証する

        README に「10+ ボリューム」と書いた閾値。ちょうど 10 では出ない。
        """
        ten = analyze.handler(_fs(qos_policies=[_policy(iops=1000, count=10)], volumes_without_qos=[]), None)
        eleven = analyze.handler(_fs(qos_policies=[_policy(iops=1000, count=11)], volumes_without_qos=[]), None)

        assert "split_policy" not in {r["type"] for r in ten["analyses"][0]["recommendations"]}
        assert "split_policy" in {r["type"] for r in eleven["analyses"][0]["recommendations"]}

    def test_unlimited_policy_with_no_volumes_is_not_flagged(self, analyze):
        """ボリュームが乗っていない無制限ポリシーは推奨対象外であることを検証する

        使われていないポリシーに上限を設定しても効果がない。
        """
        result = analyze.handler(_fs(qos_policies=[_policy(count=0)], volumes_without_qos=[]), None)

        assert "set_limits" not in {r["type"] for r in result["analyses"][0]["recommendations"]}

    def test_unlimited_policy_with_volumes_is_flagged(self, analyze):
        """ボリュームが乗っている無制限ポリシーは推奨対象になることを検証する"""
        result = analyze.handler(_fs(qos_policies=[_policy(count=3)], volumes_without_qos=[]), None)

        assert "set_limits" in {r["type"] for r in result["analyses"][0]["recommendations"]}

    def test_policy_with_only_mbps_limit_counts_as_limited(self, analyze):
        """IOPS 上限が無くても MBps 上限があれば無制限扱いしないことを検証する

        どちらか一方でも設定されていれば帯域は制限されている。
        """
        result = analyze.handler(_fs(qos_policies=[_policy(mbps=100, count=5)], volumes_without_qos=[]), None)

        types = {r["type"] for r in result["analyses"][0]["recommendations"]}
        assert "set_limits" not in types
        assert result["analyses"][0]["summary"]["policies_unlimited"] == 0

    def test_unassigned_volumes_are_reported_with_their_names(self, analyze):
        """未割り当てボリューム名が推奨に含まれることを検証する

        件数だけでは運用側が対象を特定できない。
        """
        result = analyze.handler(_fs(qos_policies=[], volumes_without_qos=["vol_a", "vol_b"]), None)

        rec = next(r for r in result["analyses"][0]["recommendations"] if r["type"] == "assign_qos_policy")
        assert rec["target_volumes"] == ["vol_a", "vol_b"]
        assert rec["severity"] == "medium"

    def test_summary_separates_limited_and_unlimited(self, analyze):
        """summary が上限あり/なしを正しく分けることを検証する"""
        result = analyze.handler(
            _fs(
                qos_policies=[
                    _policy("with-iops", iops=1000, count=1),
                    _policy("with-mbps", mbps=100, count=1),
                    _policy("unlimited", count=1),
                ],
                volumes_without_qos=[],
            ),
            None,
        )

        summary = result["analyses"][0]["summary"]
        assert summary["total_policies"] == 3
        assert summary["policies_with_limits"] == 2
        assert summary["policies_unlimited"] == 1

    def test_healthy_configuration_produces_no_recommendations(self, analyze):
        """すべて適切な構成では推奨を出さないことを検証する

        常に何か出す実装だと、推奨の有無が情報にならない。
        """
        result = analyze.handler(
            _fs(
                qos_policies=[_policy("prod", iops=10000, mbps=500, count=4)],
                volumes_without_qos=[],
            ),
            None,
        )

        assert result["total_recommendations"] == 0


# --------------------------------------------------------------------------- #
# collect: live path error handling
# --------------------------------------------------------------------------- #


class TestCollectLivePathErrors:
    """live モードのエラー処理

    DemoMode しかテストされていなかったため、本番経路のエラー処理は未検証だった。
    """

    @pytest.mark.parametrize("pattern", ["storage-efficiency", "cost-optimization", "qos-monitoring"])
    def test_missing_file_system_raises(self, pattern, monkeypatch):
        """FSx API がファイルシステムを返さない場合に失敗することを検証する

        黙って空を返すと「対象なし」と区別できず、収集漏れに気付けない。
        """
        monkeypatch.setenv("DEMO_MODE", "false")
        monkeypatch.setenv("FILE_SYSTEM_IDS", "fs-missing")
        collect = _load(pattern, "collect")

        with patch("boto3.client") as mock_client:
            mock_client.return_value.describe_file_systems.return_value = {"FileSystems": []}
            with pytest.raises(RuntimeError, match="not found|FS not found"):
                collect.handler({}, MagicMock())

    # cost-optimization は ONTAP に接続せず FSx API の構成値だけを使うため、
    # 管理 IP を必要としない。ONTAP へ問い合わせる 2 パターンのみを対象にする。
    @pytest.mark.parametrize("pattern", ["storage-efficiency", "qos-monitoring"])
    def test_missing_management_ip_raises(self, pattern, monkeypatch):
        """管理 IP が取得できない場合に失敗することを検証する"""
        monkeypatch.setenv("DEMO_MODE", "false")
        monkeypatch.setenv("FILE_SYSTEM_IDS", "fs-example")
        collect = _load(pattern, "collect")

        with patch("boto3.client") as mock_client:
            mock_client.return_value.describe_file_systems.return_value = {
                "FileSystems": [{"OntapConfiguration": {"Endpoints": {}}}]
            }
            with pytest.raises(RuntimeError):
                collect.handler({}, MagicMock())

    def test_cost_collect_derives_pool_and_backup_from_ssd_capacity(self, monkeypatch):
        """capacity_pool と backup が SSD 容量からの推測値であることを固定する

        `_live_cost` は Capacity Pool と Backup の実使用量を取得していない。SSD 容量に
        係数を掛けた推測値（pool = 0.5x, backup = 0.2x）を使っている。実測値に見える
        数字が出るため、この性質はテストとドキュメントの両方で明示しておく。

        実測値を取る実装に変えるなら、このテストと README を一緒に直すことになる。
        """
        monkeypatch.setenv("DEMO_MODE", "false")
        monkeypatch.setenv("FILE_SYSTEM_IDS", "fs-example")
        collect = _load("cost-optimization", "collect")

        with patch("boto3.client") as mock_client:
            mock_client.return_value.describe_file_systems.return_value = {
                "FileSystems": [
                    {
                        "StorageCapacity": 1000,
                        "OntapConfiguration": {"ThroughputCapacity": 128},
                    }
                ]
            }
            result = collect.handler({}, MagicMock())

        fs = result["file_systems"][0]
        assert fs["ssd_capacity_gb"] == 1000
        assert fs["capacity_pool_gb"] == 500, "SSD 容量の 0.5 倍という推測値"
        assert fs["throughput_mbps"] == 128

    @pytest.mark.parametrize("pattern", ["storage-efficiency", "cost-optimization", "qos-monitoring"])
    def test_no_file_system_ids_returns_empty(self, pattern, monkeypatch):
        """FILE_SYSTEM_IDS が空なら何も収集せずに返すことを検証する"""
        monkeypatch.setenv("DEMO_MODE", "true")
        monkeypatch.setenv("FILE_SYSTEM_IDS", "")
        collect = _load(pattern, "collect")

        result = collect.handler({}, MagicMock())

        assert result["file_systems"] == []

    @pytest.mark.parametrize("pattern", ["storage-efficiency", "cost-optimization", "qos-monitoring"])
    def test_demo_mode_flag_is_reported(self, pattern, monkeypatch):
        """demo_mode の値が出力に含まれることを検証する

        レポートを見た人が「実データか擬似データか」を判別できる必要がある。
        """
        monkeypatch.setenv("DEMO_MODE", "true")
        monkeypatch.setenv("FILE_SYSTEM_IDS", "fs-example")
        collect = _load(pattern, "collect")

        result = collect.handler({}, MagicMock())

        assert result["demo_mode"] is True
        assert len(result["file_systems"]) == 1

    def test_qos_collect_reports_volumes_without_qos_in_live_mode(self, monkeypatch):
        """live モードで未割り当てボリュームを収集することを検証する

        以前ここは空リスト固定で、README に記載した「QoS 未割り当て」検出が本番で
        一度も発火しなかった。
        """
        monkeypatch.setenv("DEMO_MODE", "false")
        monkeypatch.setenv("FILE_SYSTEM_IDS", "fs-example")
        collect = _load("qos-monitoring", "collect")

        fake_collector = MagicMock()
        fake_collector.collect_qos_policies.return_value = [_policy("p", iops=1000, count=2)]
        fake_collector.collect_volumes_without_qos.return_value = ["vol_x", "vol_y"]

        with patch("boto3.client") as mock_client:
            mock_client.return_value.describe_file_systems.return_value = {
                "FileSystems": [
                    {"OntapConfiguration": {"Endpoints": {"Management": {"IpAddresses": ["198.51.100.10"]}}}}
                ]
            }
            with patch("shared.ontap_metrics.OntapMetricsCollector", return_value=fake_collector):
                with patch("shared.ontap_client.OntapClient"):
                    result = collect.handler({}, MagicMock())

        fs = result["file_systems"][0]
        assert fs["volumes_without_qos"] == ["vol_x", "vol_y"]
        fake_collector.collect_volumes_without_qos.assert_called_once()
