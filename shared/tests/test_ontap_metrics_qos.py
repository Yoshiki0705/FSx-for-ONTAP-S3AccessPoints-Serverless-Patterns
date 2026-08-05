"""shared/ontap_metrics.py の QoS 収集のテスト

これらのメソッドには shared 側のテストが存在しなかった。OPS6 は本番モードで
`assigned_volume_count` と `volumes_without_qos` を得られず、README に記載した
3 つの検出がすべて発火しない状態だった。ここではその両方を固定する。

実機（ONTAP 9.x / FSx for ONTAP, ap-northeast-1）で確認した挙動:

- `/storage/qos/policies` は `object_count` をフィールドとして受け付ける
  （200 + レコードに object_count が入る）
- `/storage/volumes` は `qos.policy.name` をフィールドとして受け付ける
- ポリシー未割り当てのボリュームでは **レコードに qos キーが現れない**
  （空文字や null ではなく、キーの省略）
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from shared.ontap_metrics import OntapMetricsCollector
from shared.ontap_client import OntapClientError


@pytest.fixture
def client():
    return MagicMock()


@pytest.fixture
def collector(client):
    return OntapMetricsCollector(client)


class TestCollectQosPolicies:
    """QoS ポリシー収集"""

    def test_requests_object_count_field(self, collector, client):
        """object_count をフィールドに含めて問い合わせることを検証する

        これを落とすと assigned_volume_count が常に 0 になり、集約度に基づく推奨が
        本番モードで一度も出なくなる。
        """
        client.get.return_value = {"records": []}

        collector.collect_qos_policies()

        params = client.get.call_args.kwargs["params"]
        assert "object_count" in params["fields"]

    def test_maps_object_count_to_assigned_volume_count(self, collector, client):
        """object_count を呼び出し側が使うキー名に変換することを検証する"""
        client.get.return_value = {
            "records": [
                {
                    "name": "production-high",
                    "uuid": "qp1",
                    "fixed": {"max_throughput_iops": 10000, "max_throughput_mbps": 500},
                    "adaptive": {},
                    "object_count": 7,
                }
            ]
        }

        result = collector.collect_qos_policies()

        assert result[0]["assigned_volume_count"] == 7

    def test_missing_object_count_defaults_to_zero(self, collector, client):
        """object_count が返らない構成でも例外にならないことを検証する

        ONTAP のバージョンや構成でフィールドが返らない可能性を考慮する。0 として
        扱えば推奨が出ないだけで、収集そのものは成功する。
        """
        client.get.return_value = {"records": [{"name": "p", "uuid": "u", "fixed": {}, "adaptive": {}}]}

        result = collector.collect_qos_policies()

        assert result[0]["assigned_volume_count"] == 0

    def test_404_returns_empty_rather_than_failing(self, collector, client):
        """QoS エンドポイントが無い構成では空リストを返すことを検証する"""
        client.get.side_effect = OntapClientError("not found", status_code=404)

        assert collector.collect_qos_policies() == []

    def test_non_404_error_propagates(self, collector, client):
        """404 以外のエラーは伝播することを検証する

        認証エラーやタイムアウトを空リストに変えてしまうと、「ポリシーが 0 件」と
        区別できなくなる。
        """
        client.get.side_effect = OntapClientError("boom", status_code=500)

        with pytest.raises(OntapClientError):
            collector.collect_qos_policies()

    def test_adaptive_policy_min_throughput(self, collector, client):
        """adaptive ポリシーの expected_iops を min_throughput_iops に写すことを検証する"""
        client.get.return_value = {
            "records": [
                {
                    "name": "adaptive-1",
                    "uuid": "qp9",
                    "fixed": {},
                    "adaptive": {"expected_iops": 128},
                    "object_count": 2,
                }
            ]
        }

        result = collector.collect_qos_policies()

        assert result[0]["min_throughput_iops"] == 128
        assert result[0]["max_throughput_iops"] is None


class TestCollectVolumesWithoutQos:
    """QoS 未割り当てボリュームの収集"""

    def test_requests_the_qos_policy_field(self, collector, client):
        """qos.policy.name をフィールドに含めて問い合わせることを検証する"""
        client.get.return_value = {"records": []}

        collector.collect_volumes_without_qos()

        params = client.get.call_args.kwargs["params"]
        assert "qos.policy.name" in params["fields"]

    def test_absent_qos_key_means_unassigned(self, collector, client):
        """qos キーが無いボリュームを未割り当てと判定することを検証する

        実機ではポリシー未割り当ての場合、空文字や null ではなく **キー自体が
        省略される**。空文字だけを見る実装にすると、未割り当てを 1 件も検出できない。
        """
        client.get.return_value = {
            "records": [
                {"name": "vol_no_policy", "uuid": "v1"},
                {"name": "vol_with_policy", "uuid": "v2", "qos": {"policy": {"name": "prod"}}},
            ]
        }

        assert collector.collect_volumes_without_qos() == ["vol_no_policy"]

    @pytest.mark.parametrize(
        "qos_value",
        [None, {}, {"policy": {}}, {"policy": {"name": ""}}, {"policy": None}],
        ids=["qos-none", "qos-empty", "policy-empty", "name-empty", "policy-none"],
    )
    def test_empty_shapes_are_treated_as_unassigned(self, collector, client, qos_value):
        """qos の様々な空表現を未割り当てとして扱うことを検証する

        ONTAP のバージョン差でどの形が返るか断定できないため、いずれも未割り当てと
        みなす。ここで例外を出すと収集全体が止まる。
        """
        client.get.return_value = {"records": [{"name": "v", "uuid": "u", "qos": qos_value}]}

        assert collector.collect_volumes_without_qos() == ["v"]

    def test_all_assigned_returns_empty(self, collector, client):
        """全ボリュームに割り当てがあれば空リストを返すことを検証する"""
        client.get.return_value = {
            "records": [
                {"name": "a", "qos": {"policy": {"name": "p1"}}},
                {"name": "b", "qos": {"policy": {"name": "p2"}}},
            ]
        }

        assert collector.collect_volumes_without_qos() == []

    def test_excludes_non_data_volumes(self, collector, client):
        """データボリュームのみを対象にすることを検証する

        dp (SnapMirror 先) や ls (load-sharing) は QoS 割り当ての対象として扱わない。
        """
        client.get.return_value = {"records": []}

        collector.collect_volumes_without_qos()

        assert client.get.call_args.kwargs["params"]["type"] == "rw"

    def test_empty_cluster_returns_empty(self, collector, client):
        """ボリュームが無い場合も例外にならないことを検証する"""
        client.get.return_value = {"records": []}

        assert collector.collect_volumes_without_qos() == []
