"""Media VFX パターンのハンドラを実際に実行して検証する

## このファイルの変更について

以前はハンドラのソースを文字列として読み、`assert ".exr" in content` のように
部分文字列の有無だけを見ていた。それは「そのファイルにその文字列がある」ことしか
示さない。`.exr` が docstring やコメントに出てくるだけでも通るし、
`_filter_render_assets` が `.exr` を落とすように壊れても通る。

いまは実際に呼ぶ。拡張子の判定はフィルタ関数に渡して結果を見る。Deadline Cloud
への送信は `create_job` の引数を見る。テンプレートは YAML として解析して
`Parameters` や関数の `Environment.Variables` に在るかを問う。

`handler` 関数の存在と `@lambda_error_handler` による例外伝播は、全パターン共通の
契約として `shared/tests/test_discovery_handlers_behaviour.py` が検証している。
ここでは重複させず、このパターン固有の振る舞いだけを見る。
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from shared.suffix_filter import parse_suffix_filter
from shared.testing import load_pattern_handler, load_sam_template

PATTERN = "solutions/industry/media-vfx"
DISCOVERY = f"{PATTERN}/functions/discovery/handler.py"
JOB_SUBMIT = f"{PATTERN}/functions/job_submit/handler.py"
TEMPLATE = f"{PATTERN}/template.yaml"


# =========================================================================
# Discovery Handler
# =========================================================================


class TestDiscoveryHandler:
    """Discovery ハンドラの振る舞い"""

    def test_returns_render_assets_and_a_manifest_key(self, monkeypatch):
        """レンダリング対象を返し、Manifest キーを返すことを検証する

        SUFFIX_FILTER を空にして既定の 15 種を使う。ハーネスの共通既定は `.txt`
        なので、明示しないとこのテストは `.txt` を対象に検証してしまう。
        """
        harness = load_pattern_handler(
            DISCOVERY,
            monkeypatch,
            env={"SUFFIX_FILTER": ""},
            objects=[
                {"Key": "shots/a.exr", "Size": 10},
                {"Key": "notes/readme.txt", "Size": 1},
            ],
        )

        result = harness.handler({}, harness.context)

        assert [o["Key"] for o in result["objects"]] == ["shots/a.exr"]
        assert result["total_objects"] == 1
        assert result["manifest_key"].startswith("manifests/")

    def test_manifest_key_is_date_partitioned(self, monkeypatch):
        """Manifest キーが `manifests/YYYY/MM/DD/<id>.json` 形式であることを検証する

        Athena / Glue のパーティション射影が日付階層を前提にしているため、
        階層が崩れるとクエリ側が読めなくなる。
        """
        harness = load_pattern_handler(DISCOVERY, monkeypatch, objects=[{"Key": "s/a.exr", "Size": 1}])

        key = harness.handler({}, harness.context)["manifest_key"]

        prefix, year, month, day, name = key.split("/")
        assert prefix == "manifests"
        assert (len(year), len(month), len(day)) == (4, 2, 2)
        assert year.isdigit() and month.isdigit() and day.isdigit()
        assert name.endswith(".json")

    def test_manifest_is_written_through_the_output_access_point(self, monkeypatch):
        """Manifest が出力用 S3 AP に書かれることを検証する

        入力 AP に書き戻すと、読み取り専用の入力ボリュームに書こうとして失敗する。

        「出力 AP のインスタンスが生成されたか」では不十分で、入力用と出力用は
        どちらも必ず生成される。書き込みを受けたのがどちらかを見る必要がある
        （この区別を入れる前は、出力先を入力 AP に差し替える変異が検出されなかった）。
        """
        harness = load_pattern_handler(DISCOVERY, monkeypatch)
        writes: list[tuple[str, str]] = []

        class RecordingS3Ap:
            def __init__(self, access_point, *a, **kw):
                self.access_point = access_point

            def list_objects(self, prefix="", suffix="", max_keys=1000):
                return [{"Key": "s/a.exr", "Size": 1}]

            def put_object(self, **kw):
                writes.append((self.access_point, kw["key"]))
                return {}

        monkeypatch.setenv("S3_ACCESS_POINT", "in-sentinel-ext-s3alias")
        monkeypatch.setenv("S3_ACCESS_POINT_OUTPUT", "out-sentinel-ext-s3alias")
        monkeypatch.setattr(harness.module, "S3ApHelper", RecordingS3Ap)

        harness.handler({}, harness.context)

        assert writes, "the manifest was never written"
        written_to = {access_point for access_point, _ in writes}
        assert written_to == {"out-sentinel-ext-s3alias"}, f"manifest written to {written_to}"

    def test_output_access_point_falls_back_to_the_input(self, monkeypatch):
        """S3_ACCESS_POINT_OUTPUT 未設定時は入力 AP を使うことを検証する"""
        harness = load_pattern_handler(
            DISCOVERY,
            monkeypatch,
            env={"S3_ACCESS_POINT": "only-one-ext-s3alias", "S3_ACCESS_POINT_OUTPUT": ""},
            objects=[{"Key": "s/a.exr", "Size": 1}],
        )
        monkeypatch.delenv("S3_ACCESS_POINT_OUTPUT", raising=False)

        harness.handler({}, harness.context)

        assert {i.access_point for i in harness.s3ap_instances} == {"only-one-ext-s3alias"}

    def test_prefix_filter_is_passed_to_the_access_point(self, monkeypatch):
        """PREFIX_FILTER の値が list_objects の prefix に渡ることを検証する

        渡されないと、対象プレフィックス外まで走査して課金と実行時間が増える。
        """
        harness = load_pattern_handler(DISCOVERY, monkeypatch, env={"PREFIX_FILTER": "project-x/"})
        recorded: list[dict] = []

        class RecordingS3Ap:
            def __init__(self, access_point, *a, **kw):
                self.access_point = access_point

            def list_objects(self, prefix="", suffix="", max_keys=1000):
                recorded.append({"prefix": prefix, "suffix": suffix})
                return [{"Key": "project-x/a.exr", "Size": 1}]

            def put_object(self, **kw):
                return {}

        monkeypatch.setattr(harness.module, "S3ApHelper", RecordingS3Ap)

        harness.handler({}, harness.context)

        assert recorded, "list_objects was never called"
        assert recorded[0]["prefix"] == "project-x/"


class TestRenderAssetFiltering:
    """`_filter_render_assets` の判定"""

    @pytest.fixture
    def filter_assets(self, monkeypatch):
        harness = load_pattern_handler(DISCOVERY, monkeypatch)
        return harness.module._filter_render_assets

    @pytest.mark.parametrize(
        "extension",
        [".exr", ".dpx", ".tga", ".obj", ".fbx", ".blend", ".abc", ".ma", ".mb", ".hip", ".hda"],
    )
    def test_keeps_render_formats(self, filter_assets, extension):
        """レンダリング対象の拡張子が残ることを検証する"""
        kept = filter_assets([{"Key": f"shots/asset{extension}", "Size": 1}])

        assert [o["Key"] for o in kept] == [f"shots/asset{extension}"]

    @pytest.mark.parametrize("extension", [".usd", ".usda", ".usdc", ".usdz"])
    def test_keeps_usd_formats(self, filter_assets, extension):
        """USD 系フォーマットが残ることを検証する"""
        kept = filter_assets([{"Key": f"scene{extension}", "Size": 1}])

        assert len(kept) == 1

    @pytest.mark.parametrize("key", ["notes.txt", "thumb.jpg", "report.pdf", "archive.zip", "noextension"])
    def test_drops_non_render_files(self, filter_assets, key):
        """レンダリング対象外のファイルが落ちることを検証する"""
        assert filter_assets([{"Key": key, "Size": 1}]) == []

    def test_matches_extensions_case_insensitively(self, filter_assets):
        """大文字の拡張子も対象になることを検証する

        DCC ツールや Windows 由来のファイルは `.EXR` を出すことがある。
        """
        kept = filter_assets([{"Key": "shots/frame.EXR", "Size": 1}])

        assert len(kept) == 1

    def test_does_not_match_extension_in_the_middle_of_a_name(self, filter_assets):
        """拡張子が名前の途中にあるだけのファイルは対象外であることを検証する"""
        assert filter_assets([{"Key": "shots/asset.exr.bak", "Size": 1}]) == []


# =========================================================================
# Job Submit Handler
# =========================================================================


def _load_job_submit(monkeypatch, deadline=None, **env):
    """job_submit を読み込み、Deadline Cloud クライアントを差し替える"""
    harness = load_pattern_handler(
        JOB_SUBMIT,
        monkeypatch,
        env={"DEADLINE_FARM_ID": "farm-abc", "DEADLINE_QUEUE_ID": "queue-def", **env},
    )
    client = deadline or MagicMock()
    if deadline is None:
        client.create_job.return_value = {"jobId": "job-123"}
    monkeypatch.setattr(harness.module.boto3, "client", lambda name, **kw: client)
    return harness, client


class TestJobSubmitHandler:
    """Job Submit ハンドラの振る舞い"""

    def test_returns_submitted_status_and_job_id(self, monkeypatch):
        """送信後に SUBMITTED と jobId を返すことを検証する"""
        harness, _ = _load_job_submit(monkeypatch)

        result = harness.handler({"Key": "shots/a.exr", "Size": 10}, harness.context)

        assert result["status"] == "SUBMITTED"
        assert result["job_id"] == "job-123"
        assert result["asset_key"] == "shots/a.exr"

    def test_submits_with_the_farm_and_queue_from_the_environment(self, monkeypatch):
        """環境変数の Farm / Queue ID で create_job を呼ぶことを検証する

        ハードコードされた ID への退行を検出する。
        """
        harness, client = _load_job_submit(
            monkeypatch,
            DEADLINE_FARM_ID="farm-sentinel",
            DEADLINE_QUEUE_ID="queue-sentinel",
        )

        result = harness.handler({"Key": "shots/a.exr"}, harness.context)

        kwargs = client.create_job.call_args.kwargs
        assert kwargs["farmId"] == "farm-sentinel"
        assert kwargs["queueId"] == "queue-sentinel"
        assert result["farm_id"] == "farm-sentinel"
        assert result["queue_id"] == "queue-sentinel"

    def test_confirms_asset_metadata_before_submitting(self, monkeypatch):
        """ジョブ送信前に head_object でアセットを確認することを検証する

        存在しないアセットに対してジョブを投げると、Deadline 側のキューで失敗し、
        原因が Lambda のログに残らない。
        """
        harness, client = _load_job_submit(monkeypatch)

        harness.handler({"Key": "shots/a.exr"}, harness.context)

        assert "head_object" in harness.calls
        assert client.create_job.called

    def test_template_is_sent_as_json(self, monkeypatch):
        """テンプレートが JSON 文字列として送られることを検証する"""
        harness, client = _load_job_submit(monkeypatch)

        harness.handler({"Key": "shots/a.exr"}, harness.context)

        kwargs = client.create_job.call_args.kwargs
        assert kwargs["templateType"] == "JSON"
        template = json.loads(kwargs["template"])
        assert template["parameters"]["asset_key"]["string"] == "shots/a.exr"

    def test_failure_from_deadline_propagates(self, monkeypatch):
        """Deadline 呼び出しの失敗が伝播することを検証する

        飲み込むと Step Functions はジョブ未送信を成功と見なして次へ進む。
        """
        client = MagicMock()
        client.create_job.side_effect = RuntimeError("deadline unavailable")
        harness, _ = _load_job_submit(monkeypatch, deadline=client)

        with pytest.raises(RuntimeError, match="deadline unavailable"):
            harness.handler({"Key": "shots/a.exr"}, harness.context)


class TestJobTemplate:
    """`_build_job_template` の構築結果"""

    @pytest.fixture
    def build(self, monkeypatch):
        harness = load_pattern_handler(JOB_SUBMIT, monkeypatch)
        return harness.module._build_job_template

    def test_job_name_contains_the_asset_file_name(self, build):
        """ジョブ名にアセットのファイル名が入ることを検証する

        Deadline のコンソールでどのアセットのジョブか分かるようにするため。
        """
        template = build("shots/seq010/frame.exr", "out-ap")

        assert template["name"].startswith("render-frame.exr-")

    def test_parameters_carry_the_key_and_output_target(self, build):
        """パラメータにアセットキーと出力先が入ることを検証する"""
        template = build("shots/a.exr", "out-ap-ext-s3alias")

        assert template["parameters"]["asset_key"]["string"] == "shots/a.exr"
        assert template["parameters"]["output_bucket"]["string"] == "out-ap-ext-s3alias"
        assert template["parameters"]["asset_name"]["string"] == "a.exr"


# =========================================================================
# CloudFormation テンプレート
# =========================================================================


class TestTemplateConsistency:
    """テンプレートの構造

    以前は文字列として読んで名前の有無を見ていた。それでは `Description` や
    コメントに名前があるだけで通るため、YAML として解析して在るべき場所を問う。
    """

    @pytest.fixture
    def tpl(self):
        return load_sam_template(TEMPLATE)

    @pytest.mark.parametrize(
        "name",
        [
            "EnableVpcEndpoints",
            "EnableS3GatewayEndpoint",
            "PrivateRouteTableIds",
            "DeadlineFarmId",
            "DeadlineQueueId",
        ],
    )
    def test_parameter_is_declared(self, tpl, name):
        """パラメータが Parameters に宣言されていることを検証する"""
        assert name in tpl.parameters, f"declared parameters: {sorted(tpl.parameters)}"

    def test_suffix_filter_is_passed_to_a_function(self, tpl):
        """SUFFIX_FILTER が実際に環境変数として渡されることを検証する"""
        assert "SUFFIX_FILTER" in tpl.all_function_env_names()

    def test_deadline_ids_reach_the_job_submit_function(self, tpl):
        """Deadline の Farm / Queue ID が job_submit に渡ることを検証する"""
        env = tpl.function_env("JobSubmitFunction")

        assert "DEADLINE_FARM_ID" in env
        assert "DEADLINE_QUEUE_ID" in env

    def test_conditions_only_reference_declared_names(self, tpl):
        """Conditions が未宣言の名前を参照していないことを検証する"""
        assert tpl.undefined_condition_refs() == set()


class TestSuffixFilterDrivesDiscovery:
    """`SUFFIX_FILTER` が実際に検出対象を決めることを検証する

    以前はテンプレートが `SUFFIX_FILTER` を渡していてもハンドラが読まず、
    判定はモジュール定数だけで行われていた。編集しても何も起きないノブが
    テンプレートに見えている状態で、設定ミスを誘発していた。

    いまはハンドラが読む。テンプレートは定数と同じ 15 種を列挙しており、
    ここを編集すれば検出対象が変わる。
    """

    def test_narrowing_the_filter_narrows_the_result(self, monkeypatch):
        """SUFFIX_FILTER を狭めると検出対象が狭まることを検証する"""
        harness = load_pattern_handler(
            DISCOVERY,
            monkeypatch,
            env={"SUFFIX_FILTER": ".exr"},
            objects=[{"Key": "a.exr", "Size": 1}, {"Key": "b.blend", "Size": 1}],
        )

        result = harness.handler({}, harness.context)

        assert {o["Key"] for o in result["objects"]} == {"a.exr"}

    def test_an_empty_filter_falls_back_to_the_full_set(self, monkeypatch):
        """SUFFIX_FILTER が空なら既定の 15 種にフォールバックすることを検証する

        環境変数の欠落で空になったときに「1 件も検出せず成功」にしないため。
        """
        harness = load_pattern_handler(
            DISCOVERY,
            monkeypatch,
            env={"SUFFIX_FILTER": ""},
            objects=[{"Key": "a.exr", "Size": 1}, {"Key": "b.blend", "Size": 1}],
        )

        result = harness.handler({}, harness.context)

        assert {o["Key"] for o in result["objects"]} == {"a.exr", "b.blend"}

    def test_an_unset_filter_falls_back_to_the_full_set(self, monkeypatch):
        """SUFFIX_FILTER 未設定なら既定の 15 種を使うことを検証する"""
        harness = load_pattern_handler(DISCOVERY, monkeypatch, objects=[{"Key": "b.blend", "Size": 1}])
        monkeypatch.delenv("SUFFIX_FILTER", raising=False)

        result = harness.handler({}, harness.context)

        assert [o["Key"] for o in result["objects"]] == ["b.blend"]

    @pytest.mark.parametrize("raw", ["exr", ".EXR", " .exr ", ".exr,", ",.exr"])
    def test_filter_values_are_normalised(self, monkeypatch, raw):
        """ドットの有無・大文字・空白・余分なカンマを吸収することを検証する

        運用者が編集する値なので、書き方の揺れで無言の取りこぼしが起きないこと。
        """
        harness = load_pattern_handler(
            DISCOVERY,
            monkeypatch,
            env={"SUFFIX_FILTER": raw},
            objects=[{"Key": "a.exr", "Size": 1}, {"Key": "b.blend", "Size": 1}],
        )

        result = harness.handler({}, harness.context)

        assert {o["Key"] for o in result["objects"]} == {"a.exr"}, f"SUFFIX_FILTER={raw!r}"

    def test_a_dotless_filter_value_still_requires_a_dot_in_the_key(self, monkeypatch):
        """ドット無しで書いても、拡張子の区切りとして解釈されることを検証する

        `SUFFIX_FILTER="exr"` をそのまま `endswith("exr")` に使うと、
        `render_latestexr` のように拡張子ではない名前まで一致してしまう。
        ドットを補う正規化は、この取り違えを防ぐためにある
        （この検証を入れる前は、ドット補完を外す変異が検出されなかった）。
        """
        harness = load_pattern_handler(
            DISCOVERY,
            monkeypatch,
            env={"SUFFIX_FILTER": "exr"},
            objects=[{"Key": "shots/a.exr", "Size": 1}, {"Key": "shots/render_latestexr", "Size": 1}],
        )

        result = harness.handler({}, harness.context)

        assert [o["Key"] for o in result["objects"]] == ["shots/a.exr"]

    def test_template_lists_exactly_what_the_handler_defaults_to(self, monkeypatch):
        """テンプレートの列挙とハンドラの既定が一致することを検証する

        片方だけ増えると、テンプレート経由の検出対象と既定が食い違い、
        フォールバックしたときだけ挙動が変わる。
        """
        harness = load_pattern_handler(DISCOVERY, monkeypatch)
        tpl = load_sam_template(TEMPLATE)

        listed = parse_suffix_filter(str(tpl.function_env("DiscoveryFunction")["SUFFIX_FILTER"]))

        assert set(listed) == set(harness.module.RENDER_ASSET_EXTENSIONS)
