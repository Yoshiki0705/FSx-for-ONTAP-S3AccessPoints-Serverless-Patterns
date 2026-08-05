"""OPS3 / OPS4 の collect の本番経路テスト

両パターンのテストは DemoMode のみを対象にしていた。live 経路は ONTAP へ接続する
ため書きにくいが、そこに保持コンプライアンスの判定を左右するロジックが入っている。

とくに OPS4 の経過日数計算は、失敗しても例外にならず「新しいスナップショット」に
見える形で落ちていた。保持期限を超えたスナップショットが期限切れ判定から外れ、
RetentionCompliancePercent が 100% に見える。保持を監査するパターンで最も避けたい
種類の誤りなので、ここで固定する。
"""

from __future__ import annotations

import importlib.util
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(pattern: str, func: str):
    path = REPO_ROOT / "operations" / pattern / "functions" / func / "handler.py"
    mod_name = f"ops34_{pattern.replace('-', '_')}_{func}_{uuid.uuid4().hex[:8]}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def live_env(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("FILE_SYSTEM_IDS", "fs-example")
    monkeypatch.setenv("ONTAP_SECRET_ARN", "example-secret")


def _fsx_response(ips=("198.51.100.10",)):
    return {
        "FileSystems": [
            {
                "StorageCapacity": 1024,
                "OntapConfiguration": {
                    "ThroughputCapacity": 128,
                    "Endpoints": {"Management": {"IpAddresses": list(ips)}},
                },
            }
        ]
    }


def _patched_collector(fake):
    """collect が遅延 import する shared モジュールを差し替える."""
    return (
        patch("shared.ontap_metrics.OntapMetricsCollector", return_value=fake),
        patch("shared.ontap_client.OntapClient"),
    )


# --------------------------------------------------------------------------- #
# OPS3 tiering-optimizer
# --------------------------------------------------------------------------- #


class TestTieringCollectLive:
    """OPS3: live 経路"""

    def test_management_ip_lookup_failure_when_no_file_system(self, live_env):
        """FSx がファイルシステムを返さない場合に失敗することを検証する"""
        collect = _load("tiering-optimizer", "collect")

        with patch("boto3.client") as c:
            c.return_value.describe_file_systems.return_value = {"FileSystems": []}
            with pytest.raises(RuntimeError, match="File system not found"):
                collect.handler({}, MagicMock())

    def test_management_ip_lookup_failure_when_no_ip(self, live_env):
        """管理エンドポイントに IP が無い場合に失敗することを検証する"""
        collect = _load("tiering-optimizer", "collect")

        with patch("boto3.client") as c:
            c.return_value.describe_file_systems.return_value = _fsx_response(ips=())
            with pytest.raises(RuntimeError, match="Management IP not found"):
                collect.handler({}, MagicMock())

    def test_uses_the_first_management_ip(self, live_env):
        """複数 IP が返る場合は先頭を使うことを検証する"""
        collect = _load("tiering-optimizer", "collect")
        fake = MagicMock()
        fake.collect_tiering.return_value = []
        p1, p2 = _patched_collector(fake)

        with patch("boto3.client") as c:
            c.return_value.describe_file_systems.return_value = _fsx_response(ips=("198.51.100.10", "198.51.100.11"))
            with p1, p2, patch("shared.ontap_client.OntapClientConfig") as cfg:
                collect.handler({}, MagicMock())

        assert cfg.call_args.kwargs["management_ip"] == "198.51.100.10"

    def test_tags_each_volume_with_the_file_system_id(self, live_env):
        """収集したボリュームに fs_id を付与することを検証する

        複数ファイルシステムを 1 レポートに集約するため、由来が分からないと
        推奨の適用先を特定できない。
        """
        collect = _load("tiering-optimizer", "collect")
        fake = MagicMock()
        fake.collect_tiering.return_value = [{"name": "vol1"}, {"name": "vol2"}]
        p1, p2 = _patched_collector(fake)

        with patch("boto3.client") as c:
            c.return_value.describe_file_systems.return_value = _fsx_response()
            with p1, p2:
                result = collect.handler({}, MagicMock())

        assert all(v["fs_id"] == "fs-example" for v in result["file_systems"][0]["volumes"])

    def test_event_fs_id_overrides_the_environment(self, live_env, monkeypatch):
        """イベントの fs_id が環境変数の一覧を上書きすることを検証する

        単一ファイルシステムの再実行に使う経路。
        """
        monkeypatch.setenv("FILE_SYSTEM_IDS", "fs-a,fs-b,fs-c")
        collect = _load("tiering-optimizer", "collect")
        fake = MagicMock()
        fake.collect_tiering.return_value = []
        p1, p2 = _patched_collector(fake)

        with patch("boto3.client") as c:
            c.return_value.describe_file_systems.return_value = _fsx_response()
            with p1, p2:
                result = collect.handler({"fs_id": "fs-only-this"}, MagicMock())

        assert [f["fs_id"] for f in result["file_systems"]] == ["fs-only-this"]

    def test_demo_mode_flag_is_false_in_live_mode(self, live_env):
        """live 実行では demo_mode=False を報告することを検証する

        レポートを見た人が実データか擬似データかを判別できる必要がある。
        """
        collect = _load("tiering-optimizer", "collect")
        fake = MagicMock()
        fake.collect_tiering.return_value = []
        p1, p2 = _patched_collector(fake)

        with patch("boto3.client") as c:
            c.return_value.describe_file_systems.return_value = _fsx_response()
            with p1, p2:
                result = collect.handler({}, MagicMock())

        assert result["demo_mode"] is False


# --------------------------------------------------------------------------- #
# OPS4 snapshot-lifecycle
# --------------------------------------------------------------------------- #


def _snap(name="snap1", create_time=None, size=1024):
    s = {"name": name, "size_bytes": size}
    if create_time is not None:
        s["create_time"] = create_time
    return s


class TestSnapshotCollectLive:
    """OPS4: live 経路と経過日数の算出"""

    def _run(self, collect, snapshots, volumes=None):
        fake = MagicMock()
        fake.collect_snapshot_policies.return_value = []
        fake.collect_volume_space.return_value = volumes or [{"name": "vol1", "uuid": "u1"}]
        fake.collect_snapshots.return_value = snapshots
        p1, p2 = _patched_collector(fake)

        with patch("boto3.client") as c:
            c.return_value.describe_file_systems.return_value = _fsx_response()
            with p1, p2:
                return collect.handler({}, MagicMock())

    def test_age_is_calculated_from_an_offset_timestamp(self, live_env):
        """タイムゾーン付きタイムスタンプから経過日数を算出することを検証する"""
        collect = _load("snapshot-lifecycle", "collect")
        created = (datetime.now(UTC) - timedelta(days=100)).isoformat()

        result = self._run(collect, [_snap(create_time=created)])

        snap = result["file_systems"][0]["volume_snapshots"][0]["snapshots"][0]
        assert snap["age_days"] == 100
        assert snap["age_unknown"] is False

    def test_naive_timestamp_is_treated_as_utc(self, live_env):
        """タイムゾーンなしのタイムスタンプでも算出できることを検証する

        aware な now との減算は TypeError になる。以前はそれが age_days = 0 に
        落ちて「新しいスナップショット」に化けていた。
        """
        collect = _load("snapshot-lifecycle", "collect")
        naive = (datetime.now(UTC) - timedelta(days=200)).replace(tzinfo=None).isoformat()

        result = self._run(collect, [_snap(create_time=naive)])

        snap = result["file_systems"][0]["volume_snapshots"][0]["snapshots"][0]
        assert snap["age_days"] == 200
        assert snap["age_unknown"] is False

    def test_unparseable_timestamp_is_marked_unknown_not_zero(self, live_env):
        """解析できないタイムスタンプを 0 日ではなく判定不能として扱うことを検証する

        これが 0 に戻ると、analyze 側で「若すぎて削除不可」に分類され、期限切れの
        検出から外れる。保持期限を超えていてもコンプライアンス 100% に見える。
        """
        collect = _load("snapshot-lifecycle", "collect")

        result = self._run(collect, [_snap(create_time="not-a-timestamp")])

        snap = result["file_systems"][0]["volume_snapshots"][0]["snapshots"][0]
        assert snap["age_days"] is None
        assert snap["age_unknown"] is True

    def test_missing_timestamp_is_marked_unknown(self, live_env):
        """create_time が無い場合も判定不能として扱うことを検証する"""
        collect = _load("snapshot-lifecycle", "collect")

        result = self._run(collect, [_snap(create_time=None)])

        snap = result["file_systems"][0]["volume_snapshots"][0]["snapshots"][0]
        assert snap["age_days"] is None
        assert snap["age_unknown"] is True

    def test_unknown_age_count_is_aggregated(self, live_env):
        """判定不能の件数がボリューム単位とファイルシステム単位で集計されることを検証する

        件数が見えないと、コンプライアンス率が何割の対象を判定できていないのか
        分からない。
        """
        collect = _load("snapshot-lifecycle", "collect")
        good = (datetime.now(UTC) - timedelta(days=10)).isoformat()

        result = self._run(
            collect,
            [
                _snap("ok", create_time=good),
                _snap("bad1", create_time="???"),
                _snap("bad2", create_time=None),
            ],
        )

        fs = result["file_systems"][0]
        assert fs["volume_snapshots"][0]["unknown_age_count"] == 2
        assert fs["unknown_age_count"] == 2

    def test_volumes_without_uuid_are_skipped(self, live_env):
        """UUID を持たないボリュームはスキップすることを検証する

        UUID が無いとスナップショットを問い合わせられない。
        """
        collect = _load("snapshot-lifecycle", "collect")

        result = self._run(
            collect,
            [_snap()],
            volumes=[{"name": "no-uuid", "uuid": ""}, {"name": "ok", "uuid": "u1"}],
        )

        names = [v["volume_name"] for v in result["file_systems"][0]["volume_snapshots"]]
        assert names == ["ok"]

    def test_snapshots_are_tagged_with_their_volume_and_file_system(self, live_env):
        """スナップショットに由来のボリュームとファイルシステムを付与することを検証する"""
        collect = _load("snapshot-lifecycle", "collect")
        created = (datetime.now(UTC) - timedelta(days=5)).isoformat()

        result = self._run(collect, [_snap(create_time=created)])

        snap = result["file_systems"][0]["volume_snapshots"][0]["snapshots"][0]
        assert snap["volume_name"] == "vol1"
        assert snap["volume_uuid"] == "u1"
        assert snap["fs_id"] == "fs-example"

    def test_no_file_system_raises(self, live_env):
        """FSx がファイルシステムを返さない場合に失敗することを検証する"""
        collect = _load("snapshot-lifecycle", "collect")

        with patch("boto3.client") as c:
            c.return_value.describe_file_systems.return_value = {"FileSystems": []}
            with pytest.raises(RuntimeError, match="File system not found"):
                collect.handler({}, MagicMock())

    def test_no_management_ip_raises(self, live_env):
        """管理 IP が無い場合に失敗することを検証する"""
        collect = _load("snapshot-lifecycle", "collect")

        with patch("boto3.client") as c:
            c.return_value.describe_file_systems.return_value = _fsx_response(ips=())
            with pytest.raises(RuntimeError, match="Management IP not found"):
                collect.handler({}, MagicMock())


# --------------------------------------------------------------------------- #
# OPS4 analyze: 判定不能の扱い
# --------------------------------------------------------------------------- #


class TestSnapshotAnalyzeUnknownAge:
    """判定不能なスナップショットを準拠として数えないこと"""

    @pytest.fixture
    def analyze(self):
        return _load("snapshot-lifecycle", "analyze")

    def _event(self, snapshots):
        return {
            "file_systems": [
                {
                    "fs_id": "fs-example",
                    "volume_snapshots": [{"volume_name": "vol1", "volume_uuid": "u1", "snapshots": snapshots}],
                    "snapshot_policies": [],
                }
            ]
        }

    def test_unknown_age_is_counted_separately(self, analyze):
        """判定不能を protected でも expired でもない枠に数えることを検証する"""
        result = analyze.handler(self._event([{"name": "s", "age_days": None, "size_bytes": 1}]), None)

        audit = result["analyses"][0]["volume_audits"][0]
        assert audit["unknown_age_count"] == 1
        assert audit["protected_count"] == 0
        assert audit["expired_count"] == 0

    def test_unknown_age_prevents_claiming_compliance(self, analyze):
        """判定不能が残っている間は準拠と言い切らないことを検証する

        「期限切れ 0 件」だけを見て準拠とすると、判定できなかった対象を
        暗黙に準拠に数えることになる。
        """
        result = analyze.handler(self._event([{"name": "s", "age_days": None, "size_bytes": 1}]), None)

        assert result["analyses"][0]["volume_audits"][0]["retention_compliant"] is False

    def test_all_known_and_within_window_is_compliant(self, analyze):
        """すべて判定できて期限内なら準拠と報告することを検証する"""
        result = analyze.handler(self._event([{"name": "s", "age_days": 30, "size_bytes": 1}]), None)

        assert result["analyses"][0]["volume_audits"][0]["retention_compliant"] is True

    def test_oldest_age_ignores_unknown_entries(self, analyze):
        """最古の経過日数の算出で判定不能を 0 日として混ぜないことを検証する

        判定不能が混ざっていても、判定できた最大値がそのまま最古として出ること。

        補足: 実装は判定不能を除外してから max() を取るが、`None` を 0 に潰す実装でも
        max() の結果は変わらない（0 は他の値を上回らない）。つまりこの箇所は挙動が
        等価で、除外は意図を明示するための書き方に過ぎない。テストで守れるのは
        「判定できた値が正しく最古として出る」ことまで。
        """
        result = analyze.handler(
            self._event(
                [
                    {"name": "old", "age_days": 400, "size_bytes": 1},
                    {"name": "unknown", "age_days": None, "size_bytes": 1},
                ]
            ),
            None,
        )

        assert result["analyses"][0]["volume_audits"][0]["oldest_snapshot_age_days"] == 400

    def test_oldest_age_does_not_crash_on_unknown_only(self, analyze):
        """判定不能だけの場合も最古の算出が落ちないことを検証する

        `s.get("age_days") or 0` のように None を 0 に潰す実装だと、経過日数の
        リストに 0 が混ざる。ここでは「判定できた値が 1 つも無い」ことを
        既定値 0 と区別できる形で扱えているかを見る: 判定不能が 1 件でも
        あれば retention_compliant は False になるはずで、oldest だけを見て
        「新しくて健全」と読める状態にはならない。
        """
        result = analyze.handler(
            self._event([{"name": "unknown", "age_days": None, "size_bytes": 1}]),
            None,
        )

        audit = result["analyses"][0]["volume_audits"][0]
        assert audit["oldest_snapshot_age_days"] == 0
        assert audit["unknown_age_count"] == 1
        assert audit["retention_compliant"] is False

    def test_unknown_entries_are_not_classified(self, analyze):
        """判定不能を protected / expired / compliant のいずれにも数えないことを検証する

        3 つの分類の合計が、判定できた件数と一致する必要がある。判定不能を既定値 0 で
        分類に流すと protected が増え、「削除禁止の新しいスナップショット」として
        コンプライアンス集計に紛れ込む。
        """
        result = analyze.handler(
            self._event(
                [
                    {"name": "a", "age_days": 10, "size_bytes": 1},
                    {"name": "b", "age_days": None, "size_bytes": 1},
                    {"name": "c", "age_days": None, "size_bytes": 1},
                ]
            ),
            None,
        )

        audit = result["analyses"][0]["volume_audits"][0]
        classified = audit["protected_count"] + audit["expired_count"] + audit["compliant_count"]
        assert audit["total_snapshots"] == 3
        assert audit["unknown_age_count"] == 2
        assert classified == 1, "判定できたのは 1 件だけ。0 日として混ぜてはいけない"

    def test_expired_still_detected_alongside_unknown(self, analyze):
        """判定不能が混ざっていても期限切れは検出することを検証する"""
        result = analyze.handler(
            self._event(
                [
                    {"name": "expired", "age_days": 999, "size_bytes": 1},
                    {"name": "unknown", "age_days": None, "size_bytes": 1},
                ]
            ),
            None,
        )

        audit = result["analyses"][0]["volume_audits"][0]
        assert audit["expired_count"] == 1
        assert audit["unknown_age_count"] == 1
