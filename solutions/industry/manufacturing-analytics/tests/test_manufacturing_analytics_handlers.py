"""UC3 製造業 Analytics Lambda ハンドラー ユニットテスト

## このファイルの方針

以前は 20 件すべてが「ハンドラのソースに特定の文字列が現れるか」の検査だった。
`assert "seen_keys" in content`、`assert "rekognition" in content`、
`assert "manifests/" in content` といった形である。この形は両方向に弱い。

- 通るのに壊れている: `seen_keys` という名前の変数があっても、重複排除に使われて
  いなければ通る。処理全体がコメントアウトされていても文字列は残るので通る。
- 壊れていないのに落ちる: 変数名を変えたり共通ヘルパーへ移すと、振る舞いが同じでも
  落ちる。実際 `SUFFIX_FILTER` の読み取りを `shared/suffix_filter.py` へ移したときに
  これが起きた。

さらにこのパターン固有の問題があった。`test_template_has_suffix_filter` は
テンプレート本文に `SUFFIX_FILTER` という部分文字列があるかを見ていたので、
環境変数が `SENSOR_LOG_SUFFIX_FILTER` と `INSPECTION_IMAGE_SUFFIX_FILTER` の 2 つに
分割されたあとも通り続けた。分割の意図（走査対象と分類対象を構造的に一致させる）を
何も守っていない。

そこでハンドラを実行し、S3 AP / Rekognition への呼び出しと返り値を見る形にした。
テンプレートは YAML を解析して `Parameters` と `Environment.Variables` を見る。

## 書くときの注意: サフィックスは 2 カテゴリ別の環境変数

このパターンは `SUFFIX_FILTER` を読まない。`SENSOR_LOG_SUFFIX_FILTER` と
`INSPECTION_IMAGE_SUFFIX_FILTER` を別々に読み、その合併を走査する。ハーネスの既定
`SUFFIX_FILTER=".txt"` はここでは効かないので、既定の 4 サフィックス
(.csv, .jpeg, .jpg, .png) で走査される。

ハーネスの `list_objects` はサフィックスに関係なく同じ一覧を返すため、既定でも
4 回分の重複が発生する。つまり重複排除は既定の設定でも実際に効いている。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "shared"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.testing import load_pattern_handler, load_sam_template  # noqa: E402

PATTERN_DIR = Path(__file__).resolve().parents[1]
DISCOVERY_HANDLER = "solutions/industry/manufacturing-analytics/functions/discovery/handler.py"
IMAGE_ANALYSIS_HANDLER = "solutions/industry/manufacturing-analytics/functions/image_analysis/handler.py"
TEMPLATE = PATTERN_DIR / "template.yaml"
TEMPLATE_DEPLOY = PATTERN_DIR / "template-deploy.yaml"


def _objects(*keys: str) -> list[dict]:
    return [{"Key": k, "Size": 100} for k in keys]


# =========================================================================
# Discovery Handler
# =========================================================================


class TestDiscoveryHandler:
    """Discovery ハンドラを実行して検証する"""

    def test_lists_once_per_suffix_and_deduplicates(self, monkeypatch):
        """合併したサフィックスごとに 1 回ずつ走査し、重複キーを 1 件に畳む

        ハーネスの list_objects はサフィックスに関わらず同じ一覧を返すので、
        4 サフィックス × 2 件 = 8 件が集まり、重複排除で 2 件に戻るはずである。
        重複排除を外すと total_objects が 8 になって落ちる。
        """
        harness = load_pattern_handler(
            DISCOVERY_HANDLER,
            monkeypatch,
            objects=_objects("line1/sensor.csv", "line1/panel.jpg"),
        )
        result = harness.handler({}, harness.context)

        # .csv, .jpeg, .jpg, .png の 4 カテゴリぶん
        assert harness.calls.count("list_objects") == 4
        assert result["total_objects"] == 2

    def test_classifies_sensor_logs_and_inspection_images(self, monkeypatch):
        """拡張子でセンサーログと検査画像に振り分ける"""
        harness = load_pattern_handler(
            DISCOVERY_HANDLER,
            monkeypatch,
            objects=_objects(
                "line1/a.csv",
                "line1/b.jpg",
                "line1/c.jpeg",
                "line1/d.png",
            ),
        )
        result = harness.handler({}, harness.context)

        assert [o["Key"] for o in result["csv_files"]] == ["line1/a.csv"]
        assert sorted(o["Key"] for o in result["image_files"]) == [
            "line1/b.jpg",
            "line1/c.jpeg",
            "line1/d.png",
        ]

    def test_ignores_keys_outside_both_categories(self, monkeypatch):
        """どちらのカテゴリにも属さない拡張子は分類されない

        走査は合併サフィックスで行うので実運用では現れないが、S3 AP が余分な
        キーを返した場合に片方へ紛れ込まないことを確認する。
        """
        harness = load_pattern_handler(
            DISCOVERY_HANDLER,
            monkeypatch,
            objects=_objects("line1/readme.txt", "line1/a.csv"),
        )
        result = harness.handler({}, harness.context)

        assert [o["Key"] for o in result["csv_files"]] == ["line1/a.csv"]
        assert result["image_files"] == []
        # 走査結果には残る（分類されないだけ）
        assert result["total_objects"] == 2

    def test_case_insensitive_classification(self, monkeypatch):
        """大文字の拡張子も分類される"""
        harness = load_pattern_handler(
            DISCOVERY_HANDLER,
            monkeypatch,
            objects=_objects("line1/A.CSV", "line1/B.PNG"),
        )
        result = harness.handler({}, harness.context)

        assert [o["Key"] for o in result["csv_files"]] == ["line1/A.CSV"]
        assert [o["Key"] for o in result["image_files"]] == ["line1/B.PNG"]

    def test_sensor_suffix_override_widens_scan_and_classification_together(self, monkeypatch):
        """センサーログの拡張子を足すと、走査と分類の両方に反映される

        これが環境変数を 2 つに分けた理由そのものである。単一の SUFFIX_FILTER だと
        走査対象は広がるが分類の if/elif に該当せず、無言で落ちる件が出る。
        """
        harness = load_pattern_handler(
            DISCOVERY_HANDLER,
            monkeypatch,
            env={"SENSOR_LOG_SUFFIX_FILTER": ".csv,.tsv"},
            objects=_objects("line1/a.csv", "line1/b.tsv"),
        )
        result = harness.handler({}, harness.context)

        # .csv,.tsv + 既定の画像 3 種 = 5 回
        assert harness.calls.count("list_objects") == 5
        assert sorted(o["Key"] for o in result["csv_files"]) == ["line1/a.csv", "line1/b.tsv"]
        assert result["image_files"] == []

    def test_image_suffix_override_replaces_defaults(self, monkeypatch):
        """検査画像の拡張子を指定すると既定を置き換える（追加ではない）"""
        harness = load_pattern_handler(
            DISCOVERY_HANDLER,
            monkeypatch,
            env={"INSPECTION_IMAGE_SUFFIX_FILTER": ".bmp"},
            objects=_objects("line1/a.csv", "line1/b.bmp", "line1/c.png"),
        )
        result = harness.handler({}, harness.context)

        # .csv + .bmp = 2 回。既定の .jpeg/.jpg/.png はもう走査しない
        assert harness.calls.count("list_objects") == 2
        assert [o["Key"] for o in result["image_files"]] == ["line1/b.bmp"]
        # .png は分類対象から外れている
        assert "line1/c.png" not in [o["Key"] for o in result["image_files"]]

    def test_blank_suffix_override_falls_back_to_defaults(self, monkeypatch):
        """空の指定は既定へ倒す（0 件検出して成功、を避ける）"""
        harness = load_pattern_handler(
            DISCOVERY_HANDLER,
            monkeypatch,
            env={"SENSOR_LOG_SUFFIX_FILTER": "  ,  "},
            objects=_objects("line1/a.csv"),
        )
        result = harness.handler({}, harness.context)

        assert harness.calls.count("list_objects") == 4
        assert [o["Key"] for o in result["csv_files"]] == ["line1/a.csv"]

    def test_writes_manifest_after_listing(self, monkeypatch):
        """走査がすべて終わったあとに manifest を書く"""
        harness = load_pattern_handler(
            DISCOVERY_HANDLER,
            monkeypatch,
            objects=_objects("line1/a.csv"),
        )
        harness.handler({}, harness.context)

        harness.assert_called_before("list_objects", "put_object")
        assert harness.calls.count("put_object") == 1

    def test_manifest_key_is_date_partitioned_json(self, monkeypatch):
        """manifest キーは manifests/YYYY/MM/DD/<request_id>.json"""
        harness = load_pattern_handler(
            DISCOVERY_HANDLER,
            monkeypatch,
            objects=_objects("line1/a.csv"),
        )
        result = harness.handler({}, harness.context)

        key = result["manifest_key"]
        assert key.startswith("manifests/")
        assert key.endswith(f"{harness.context.aws_request_id}.json")

        # manifests/ と ファイル名 の間が YYYY/MM/DD の 3 階層
        middle = key[len("manifests/") : -len(f"/{harness.context.aws_request_id}.json")]
        parts = middle.split("/")
        assert len(parts) == 3, key
        assert [len(p) for p in parts] == [4, 2, 2], key
        assert all(p.isdigit() for p in parts), key

    def test_manifest_body_is_valid_json_carrying_the_classification(self, monkeypatch):
        """書き出す本文は JSON で、分類結果と件数を含む"""
        captured: dict = {}

        harness = load_pattern_handler(
            DISCOVERY_HANDLER,
            monkeypatch,
            objects=_objects("line1/a.csv", "line1/b.png"),
        )
        monkeypatch.setattr(
            harness.module.S3ApHelper,
            "put_object",
            lambda self, **kw: captured.update(kw) or {},
        )
        harness.handler({}, harness.context)

        assert captured["content_type"] == "application/json"
        manifest = json.loads(captured["body"])
        assert manifest["total_objects"] == 2
        assert [o["Key"] for o in manifest["csv_files"]] == ["line1/a.csv"]
        assert [o["Key"] for o in manifest["image_files"]] == ["line1/b.png"]
        assert manifest["execution_id"] == harness.context.aws_request_id

    def test_writes_manifest_through_the_output_access_point(self, monkeypatch):
        """入力と出力の AP が別なら、書き込みは出力 AP を使う

        両方の AP が生成されたことを見るだけでは不十分だった。ハンドラは入力用と
        出力用の両方を必ず生成するので、put_object を入力側に向けても生成の検査は
        通ってしまう（変異で確認した）。どちらの AP が書き込みを受けたかを見る。
        """
        wrote_to: list[str] = []

        harness = load_pattern_handler(
            DISCOVERY_HANDLER,
            monkeypatch,
            env={
                "S3_ACCESS_POINT": "in-ap-ext-s3alias",
                "S3_ACCESS_POINT_OUTPUT": "out-ap-ext-s3alias",
            },
            objects=_objects("line1/a.csv"),
        )
        monkeypatch.setattr(
            harness.module.S3ApHelper,
            "put_object",
            lambda self, **kw: wrote_to.append(self.access_point) or {},
        )
        harness.handler({}, harness.context)

        assert wrote_to == ["out-ap-ext-s3alias"]

    def test_list_failure_propagates(self, monkeypatch):
        """走査が失敗したら成功を返さない"""
        harness = load_pattern_handler(
            DISCOVERY_HANDLER,
            monkeypatch,
            objects=_objects("line1/a.csv"),
            fail_on="list_objects",
        )
        with pytest.raises(Exception):
            harness.handler({}, harness.context)

        assert "put_object" not in harness.calls


# =========================================================================
# Image Analysis Handler
# =========================================================================


class TestShouldFlagForReview:
    """信頼度スコアの閾値判定"""

    @pytest.mark.parametrize(
        ("confidence", "threshold", "expected"),
        [
            (79.9, 80.0, True),  # 閾値未満 -> レビュー
            (80.0, 80.0, False),  # 閾値と同じ -> レビュー不要（境界）
            (80.1, 80.0, False),
            (0.0, 80.0, True),  # ラベルなし相当
            (100.0, 100.0, False),
        ],
    )
    def test_boundary(self, monkeypatch, confidence, threshold, expected):
        harness = load_pattern_handler(IMAGE_ANALYSIS_HANDLER, monkeypatch)
        assert harness.module.should_flag_for_review(confidence, threshold) is expected


def _load_image_analysis(monkeypatch, labels, env=None):
    """Rekognition を差し替えた image_analysis ハーネスを返す"""
    harness = load_pattern_handler(IMAGE_ANALYSIS_HANDLER, monkeypatch, env=env)

    fake_rekognition = MagicMock()
    fake_rekognition.detect_labels.return_value = {"Labels": labels}
    fake_boto3 = MagicMock()
    fake_boto3.client.return_value = fake_rekognition
    monkeypatch.setattr(harness.module, "boto3", fake_boto3)

    return harness, fake_rekognition


class TestImageAnalysisHandler:
    """Image Analysis ハンドラを実行して検証する"""

    def test_reads_image_then_writes_result(self, monkeypatch):
        """画像を取得してから結果を書き出す"""
        harness, _ = _load_image_analysis(
            monkeypatch,
            labels=[{"Name": "Scratch", "Confidence": 95.0}],
        )
        harness.handler({"Key": "line1/panel.jpg", "Size": 100}, harness.context)

        harness.assert_called_before("get_object", "put_object")

    def test_sends_the_retrieved_bytes_to_rekognition(self, monkeypatch):
        """取得したバイト列をそのまま Rekognition に渡す"""
        harness, rek = _load_image_analysis(
            monkeypatch,
            labels=[{"Name": "Scratch", "Confidence": 95.0}],
        )
        harness.handler({"Key": "line1/panel.jpg", "Size": 100}, harness.context)

        rek.detect_labels.assert_called_once()
        kwargs = rek.detect_labels.call_args.kwargs
        assert "Bytes" in kwargs["Image"]

    def test_flags_when_the_lowest_label_confidence_is_below_threshold(self, monkeypatch):
        """レビュー判定は最小の信頼度で行う（最大や平均ではない）"""
        harness, _ = _load_image_analysis(
            monkeypatch,
            labels=[
                {"Name": "Panel", "Confidence": 99.0},
                {"Name": "Scratch", "Confidence": 42.0},
            ],
            env={"CONFIDENCE_THRESHOLD": "80.0"},
        )
        result = harness.handler({"Key": "line1/panel.jpg", "Size": 100}, harness.context)

        assert result["flagged_for_review"] is True
        assert result["labels"] == 2

    def test_does_not_flag_when_every_label_clears_the_threshold(self, monkeypatch):
        harness, _ = _load_image_analysis(
            monkeypatch,
            labels=[
                {"Name": "Panel", "Confidence": 99.0},
                {"Name": "Scratch", "Confidence": 88.0},
            ],
            env={"CONFIDENCE_THRESHOLD": "80.0"},
        )
        result = harness.handler({"Key": "line1/panel.jpg", "Size": 100}, harness.context)

        assert result["flagged_for_review"] is False

    def test_no_labels_is_flagged(self, monkeypatch):
        """ラベルが無い場合は 0.0 扱いでレビューに回す"""
        harness, _ = _load_image_analysis(monkeypatch, labels=[])
        result = harness.handler({"Key": "line1/panel.jpg", "Size": 100}, harness.context)

        assert result["labels"] == 0
        assert result["flagged_for_review"] is True

    def test_threshold_comes_from_the_environment(self, monkeypatch):
        """同じ信頼度でも閾値の設定で判定が変わる"""
        labels = [{"Name": "Scratch", "Confidence": 85.0}]

        harness_low, _ = _load_image_analysis(monkeypatch, labels=labels, env={"CONFIDENCE_THRESHOLD": "80.0"})
        assert harness_low.handler({"Key": "a.jpg"}, harness_low.context)["flagged_for_review"] is False

        harness_high, _ = _load_image_analysis(monkeypatch, labels=labels, env={"CONFIDENCE_THRESHOLD": "90.0"})
        assert harness_high.handler({"Key": "a.jpg"}, harness_high.context)["flagged_for_review"] is True

    def test_output_key_is_date_partitioned_under_image_analysis(self, monkeypatch):
        """出力キーは image-analysis/YYYY/MM/DD/<filename>.json"""
        harness, _ = _load_image_analysis(
            monkeypatch,
            labels=[{"Name": "Scratch", "Confidence": 95.0}],
        )
        result = harness.handler({"Key": "line1/deep/panel.jpg", "Size": 100}, harness.context)

        key = result["output_key"]
        assert key.startswith("image-analysis/")
        # ディレクトリ部は落として basename だけを使う
        assert key.endswith("panel.jpg.json")
        assert "line1/deep" not in key

        middle = key[len("image-analysis/") : -len("/panel.jpg.json")]
        parts = middle.split("/")
        assert [len(p) for p in parts] == [4, 2, 2], key

    def test_result_body_records_confidence_and_threshold(self, monkeypatch):
        """書き出す JSON に min_confidence / threshold / flagged を残す"""
        captured: dict = {}
        harness, _ = _load_image_analysis(
            monkeypatch,
            labels=[
                {"Name": "Panel", "Confidence": 99.0},
                {"Name": "Scratch", "Confidence": 42.0},
            ],
            env={"CONFIDENCE_THRESHOLD": "80.0"},
        )
        monkeypatch.setattr(
            harness.module.S3ApHelper,
            "put_object",
            lambda self, **kw: captured.update(kw) or {},
        )
        harness.handler({"Key": "line1/panel.jpg", "Size": 100}, harness.context)

        body = json.loads(captured["body"])
        assert body["min_confidence"] == 42.0
        assert body["threshold"] == 80.0
        assert body["flagged_for_review"] is True
        assert body["image_key"] == "line1/panel.jpg"
        assert [lbl["name"] for lbl in body["labels"]] == ["Panel", "Scratch"]

    def test_get_failure_propagates(self, monkeypatch):
        """画像取得が失敗したら結果を書かない"""
        harness, _ = _load_image_analysis(
            monkeypatch,
            labels=[{"Name": "Scratch", "Confidence": 95.0}],
        )
        monkeypatch.setattr(
            harness.module.S3ApHelper,
            "get_object",
            lambda self, key: (_ for _ in ()).throw(RuntimeError("injected")),
        )
        with pytest.raises(Exception):
            harness.handler({"Key": "line1/panel.jpg"}, harness.context)


# =========================================================================
# CloudFormation テンプレート
# =========================================================================


class TestTemplateConsistency:
    """テンプレートを YAML として解析して検証する"""

    def test_both_templates_parse(self):
        """壊れた YAML なら解析時に落ちる（部分文字列検査では気付けない）"""
        assert load_sam_template(TEMPLATE).resources
        assert load_sam_template(TEMPLATE_DEPLOY).resources

    def test_declares_the_two_category_suffix_filters(self):
        """カテゴリ別のサフィックス環境変数が実際に関数へ渡されている

        以前は本文に `SUFFIX_FILTER` という部分文字列があるかだけを見ていたため、
        2 つに分割したあとも通り続け、分割の意図を何も守っていなかった。
        """
        env_names = load_sam_template(TEMPLATE).all_function_env_names()
        assert "SENSOR_LOG_SUFFIX_FILTER" in env_names
        assert "INSPECTION_IMAGE_SUFFIX_FILTER" in env_names

    def test_discovery_env_matches_what_the_handler_reads(self):
        """Discovery が読む環境変数がテンプレートに揃っている"""
        template = load_sam_template(TEMPLATE)
        discovery = [lid for lid in template.functions() if "Discovery" in lid]
        assert discovery, f"Discovery 関数が見つからない: {list(template.functions())}"

        env = template.function_env(discovery[0])
        for name in ("S3_ACCESS_POINT", "SENSOR_LOG_SUFFIX_FILTER", "INSPECTION_IMAGE_SUFFIX_FILTER"):
            assert name in env, f"{name} が {discovery[0]} に無い: {sorted(env)}"

    def test_image_analysis_receives_its_threshold(self):
        """Image Analysis の閾値がテンプレートから渡されている"""
        env_names = load_sam_template(TEMPLATE).all_function_env_names()
        assert "CONFIDENCE_THRESHOLD" in env_names

    @pytest.mark.parametrize(
        "name",
        ["EnableVpcEndpoints", "EnableS3GatewayEndpoint", "PrivateRouteTableIds"],
    )
    def test_vpc_endpoint_parameters_declared(self, name):
        assert name in load_sam_template(TEMPLATE).parameters

    def test_conditions_only_reference_declared_parameters(self):
        """Conditions が消えたパラメータを参照していない

        パラメータを削除して Conditions の !Ref が残る壊れ方は、部分文字列検査では
        通ってしまう。
        """
        assert load_sam_template(TEMPLATE).undefined_condition_refs() == set()
