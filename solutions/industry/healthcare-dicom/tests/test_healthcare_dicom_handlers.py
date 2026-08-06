"""UC5 医療 DICOM Lambda ハンドラー ユニットテスト

## このファイルの方針

以前は 18 件すべてが「ハンドラのソースに特定の文字列が現れるか」の検査だった。
`assert "PHI_FIELDS" in content`、`assert 'b"DICM"' in content`、
`assert "patient_name" in content` といった形である。この形は両方向に弱い。

PHI の扱いでは特に危険だった。`assert "patient_name" in content` は、
`patient_name` が PHI_FIELDS に列挙されていることも、実際に除去されることも
確認していない。ハンドラのどこかにその語が現れれば通る。つまり
「PHI を除去する」という、このパターンの存在理由そのものが検査されていなかった。
除去処理を削っても、変数名が残っていれば 18 件すべて通り続ける。

そこでハンドラを実行し、匿名化の結果と S3 AP への書き込み内容を見る形にした。
テンプレートは YAML を解析して `Parameters` と `Environment.Variables` を見る。

## 書くときの注意: SUFFIX_FILTER を明示する

Discovery は `allowed_suffixes((DICOM_SUFFIX,))` を既定の環境変数名 `SUFFIX_FILTER`
で読む。ハーネスの既定値は `.txt` なので、明示しないと `.dcm` ではなく `.txt` を
走査してしまい、意図と違う経路を検証することになる。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "shared"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.testing import load_pattern_handler, load_sam_template  # noqa: E402

PATTERN_DIR = Path(__file__).resolve().parents[1]
DISCOVERY_HANDLER = "solutions/industry/healthcare-dicom/functions/discovery/handler.py"
DICOM_PARSE_HANDLER = "solutions/industry/healthcare-dicom/functions/dicom_parse/handler.py"
TEMPLATE = PATTERN_DIR / "template.yaml"
TEMPLATE_DEPLOY = PATTERN_DIR / "template-deploy.yaml"


def _objects(*keys: str) -> list[dict]:
    return [{"Key": k, "Size": 100} for k in keys]


def _dicom_bytes(magic: bytes = b"DICM", preamble: int = 128, tail: int = 0) -> bytes:
    return b"\x00" * preamble + magic + b"\x00" * tail


# =========================================================================
# Discovery
# =========================================================================


class TestDiscoveryHandler:
    def test_scans_the_configured_suffix_and_returns_the_objects(self, monkeypatch):
        harness = load_pattern_handler(
            DISCOVERY_HANDLER,
            monkeypatch,
            env={"SUFFIX_FILTER": ".dcm"},
            objects=_objects("study1/img1.dcm", "study1/img2.dcm"),
        )
        result = harness.handler({}, harness.context)

        assert harness.calls.count("list_objects") == 1
        assert result["total_objects"] == 2
        assert [o["Key"] for o in result["objects"]] == ["study1/img1.dcm", "study1/img2.dcm"]

    def test_blank_suffix_filter_falls_back_to_dcm(self, monkeypatch):
        """未設定なら .dcm を使う（0 件検出して成功、を避ける）"""
        harness = load_pattern_handler(
            DISCOVERY_HANDLER,
            monkeypatch,
            env={"SUFFIX_FILTER": ""},
            objects=_objects("study1/img1.dcm"),
        )
        result = harness.handler({}, harness.context)

        assert harness.calls.count("list_objects") == 1
        assert result["total_objects"] == 1

    def test_deduplicates_across_suffixes(self, monkeypatch):
        """複数サフィックス指定時、同じキーは 1 度だけ数える

        ハーネスの list_objects はサフィックスに関わらず同じ一覧を返すので、
        3 サフィックスなら重複排除が無ければ 3 倍に膨れる。
        """
        harness = load_pattern_handler(
            DISCOVERY_HANDLER,
            monkeypatch,
            env={"SUFFIX_FILTER": ".dcm,.dicom,.dc3"},
            objects=_objects("study1/img1.dcm", "study1/img2.dcm"),
        )
        result = harness.handler({}, harness.context)

        assert harness.calls.count("list_objects") == 3
        assert result["total_objects"] == 2

    def test_reports_the_deduplicated_count(self, monkeypatch):
        """返り値の件数は重複排除後の一覧と一致する"""
        harness = load_pattern_handler(
            DISCOVERY_HANDLER,
            monkeypatch,
            env={"SUFFIX_FILTER": ".dcm,.dicom"},
            objects=_objects("a.dcm", "b.dcm", "c.dcm"),
        )
        result = harness.handler({}, harness.context)

        assert result["total_objects"] == len(result["objects"]) == 3

    def test_writes_manifest_after_listing(self, monkeypatch):
        harness = load_pattern_handler(
            DISCOVERY_HANDLER,
            monkeypatch,
            env={"SUFFIX_FILTER": ".dcm"},
            objects=_objects("a.dcm"),
        )
        harness.handler({}, harness.context)

        harness.assert_called_before("list_objects", "put_object")

    def test_manifest_key_is_date_partitioned_json(self, monkeypatch):
        harness = load_pattern_handler(
            DISCOVERY_HANDLER,
            monkeypatch,
            env={"SUFFIX_FILTER": ".dcm"},
            objects=_objects("a.dcm"),
        )
        result = harness.handler({}, harness.context)

        key = result["manifest_key"]
        assert key.startswith("manifests/")
        assert key.endswith(f"{harness.context.aws_request_id}.json")

        middle = key[len("manifests/") : -len(f"/{harness.context.aws_request_id}.json")]
        parts = middle.split("/")
        assert [len(p) for p in parts] == [4, 2, 2], key
        assert all(p.isdigit() for p in parts), key

    def test_manifest_body_lists_the_objects(self, monkeypatch):
        captured: dict = {}
        harness = load_pattern_handler(
            DISCOVERY_HANDLER,
            monkeypatch,
            env={"SUFFIX_FILTER": ".dcm"},
            objects=_objects("a.dcm", "b.dcm"),
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
        assert [o["Key"] for o in manifest["objects"]] == ["a.dcm", "b.dcm"]
        assert manifest["execution_id"] == harness.context.aws_request_id

    def test_writes_through_the_output_access_point(self, monkeypatch):
        """書き込みを受けるのが出力 AP であることを見る（生成の有無ではない）"""
        wrote_to: list[str] = []
        harness = load_pattern_handler(
            DISCOVERY_HANDLER,
            monkeypatch,
            env={
                "SUFFIX_FILTER": ".dcm",
                "S3_ACCESS_POINT": "in-ap-ext-s3alias",
                "S3_ACCESS_POINT_OUTPUT": "out-ap-ext-s3alias",
            },
            objects=_objects("a.dcm"),
        )
        monkeypatch.setattr(
            harness.module.S3ApHelper,
            "put_object",
            lambda self, **kw: wrote_to.append(self.access_point) or {},
        )
        harness.handler({}, harness.context)

        assert wrote_to == ["out-ap-ext-s3alias"]

    def test_list_failure_propagates(self, monkeypatch):
        harness = load_pattern_handler(
            DISCOVERY_HANDLER,
            monkeypatch,
            env={"SUFFIX_FILTER": ".dcm"},
            objects=_objects("a.dcm"),
            fail_on="list_objects",
        )
        with pytest.raises(Exception):
            harness.handler({}, harness.context)

        assert "put_object" not in harness.calls


# =========================================================================
# anonymize_metadata — このパターンの中核
# =========================================================================


# 除去されなければならない PHI フィールド。実装の PHI_FIELDS から読まず、ここに
# 独立して書く。
#
# 実装から読むと検査が同語反復になる。PHI_FIELDS から 1 項目を削ると、期待値も
# 同じだけ縮むので、その項目が漏れるようになっても全件通ってしまう。変異で確認した
# （patient_id を PHI_FIELDS から外しても 35 件すべて通った）。
#
# 除去すべき項目の集合は実装の詳細ではなく要件なので、テスト側に置く。実装が項目を
# 増やすのは構わないが、この一覧より減らすことはできない。
REQUIRED_PHI_FIELDS = (
    "patient_name",
    "patient_id",
    "patient_birth_date",
    "patient_address",
    "patient_phone",
    "referring_physician",
    "institution_name",
    "institution_address",
)


class TestAnonymizeMetadata:
    """PHI 除去と分類付与"""

    def test_implementation_covers_every_required_phi_field(self, monkeypatch):
        """PHI_FIELDS が要件の一覧を満たしている

        この 1 件が、下の「宣言された項目を全部消す」検査の同語反復を防いでいる。
        """
        harness = load_pattern_handler(DICOM_PARSE_HANDLER, monkeypatch)
        declared = set(harness.module.PHI_FIELDS)

        missing = [f for f in REQUIRED_PHI_FIELDS if f not in declared]
        assert not missing, f"PHI_FIELDS に不足: {missing}"

    @pytest.mark.parametrize("field", REQUIRED_PHI_FIELDS)
    def test_each_required_phi_field_is_removed(self, monkeypatch, field):
        """要件の各項目が、単独で渡されても除去される"""
        harness = load_pattern_handler(DICOM_PARSE_HANDLER, monkeypatch)
        result = harness.module.anonymize_metadata({field: "SENTINEL", "modality": "CT"})

        assert field not in result, f"{field} が除去されていない"
        assert "SENTINEL" not in json.dumps(result), f"{field} の値が残っている"

    def test_removes_every_declared_phi_field(self, monkeypatch):
        """PHI_FIELDS に挙がっている項目がすべて消える

        個別のフィールド名を文字列で探すのではなく、実装が宣言している一覧を
        使って全件を確認する。PHI_FIELDS に項目を足したとき、除去漏れがあれば
        ここで落ちる。
        """
        harness = load_pattern_handler(DICOM_PARSE_HANDLER, monkeypatch)
        phi_fields = harness.module.PHI_FIELDS
        assert phi_fields, "PHI_FIELDS が空"

        metadata = {field: f"secret-{field}" for field in phi_fields}
        metadata.update({"modality": "CT", "body_part": "CHEST"})

        result = harness.module.anonymize_metadata(metadata)

        for field in phi_fields:
            assert field not in result, f"{field} が除去されていない"

    def test_no_phi_value_survives_anywhere_in_the_result(self, monkeypatch):
        """PHI の値が結果のどこにも残らない

        キーを消しても値が分類情報などに混ざれば漏洩する。直列化した全体を見る。
        """
        harness = load_pattern_handler(DICOM_PARSE_HANDLER, monkeypatch)
        phi_fields = harness.module.PHI_FIELDS

        metadata = {field: f"SENTINEL_{field.upper()}" for field in phi_fields}
        metadata.update({"modality": "MR", "body_part": "HEAD"})

        serialized = json.dumps(harness.module.anonymize_metadata(metadata))

        for field in phi_fields:
            assert f"SENTINEL_{field.upper()}" not in serialized, f"{field} の値が残っている"

    def test_keeps_the_clinical_fields(self, monkeypatch):
        """診療上必要な非 PHI 項目は保持する（全消しでは用途を満たさない）"""
        harness = load_pattern_handler(DICOM_PARSE_HANDLER, monkeypatch)
        result = harness.module.anonymize_metadata(
            {"patient_name": "secret", "modality": "CT", "body_part": "CHEST", "study_date": "20260101"}
        )

        assert result["modality"] == "CT"
        assert result["body_part"] == "CHEST"
        assert result["study_date"] == "20260101"

    def test_does_not_mutate_the_input(self, monkeypatch):
        """呼び出し元の辞書を書き換えない"""
        harness = load_pattern_handler(DICOM_PARSE_HANDLER, monkeypatch)
        metadata = {"patient_name": "secret", "modality": "CT"}

        harness.module.anonymize_metadata(metadata)

        assert metadata["patient_name"] == "secret"

    def test_maps_every_declared_modality_to_its_category(self, monkeypatch):
        """MODALITY_CATEGORIES の全エントリが分類に反映される"""
        harness = load_pattern_handler(DICOM_PARSE_HANDLER, monkeypatch)
        categories = harness.module.MODALITY_CATEGORIES
        assert categories, "MODALITY_CATEGORIES が空"

        for code, expected in categories.items():
            result = harness.module.anonymize_metadata({"modality": code})
            assert result["classification"]["modality_category"] == expected, code
            assert result["classification"]["modality_code"] == code

    def test_unknown_modality_falls_back_to_other(self, monkeypatch):
        harness = load_pattern_handler(DICOM_PARSE_HANDLER, monkeypatch)
        result = harness.module.anonymize_metadata({"modality": "ZZ"})

        assert result["classification"]["modality_category"] == "other"
        assert result["classification"]["modality_code"] == "ZZ"

    def test_missing_modality_and_body_part_get_defaults(self, monkeypatch):
        harness = load_pattern_handler(DICOM_PARSE_HANDLER, monkeypatch)
        result = harness.module.anonymize_metadata({})

        assert result["classification"]["modality_code"] == "OT"
        assert result["classification"]["modality_category"] == "other"
        assert result["classification"]["body_part"] == "UNKNOWN"


# =========================================================================
# _parse_dicom_header
# =========================================================================


class TestParseDicomHeader:
    """DICM マジックナンバー検証"""

    def test_accepts_a_valid_preamble_and_magic(self, monkeypatch):
        harness = load_pattern_handler(DICOM_PARSE_HANDLER, monkeypatch)
        data = _dicom_bytes(tail=20)

        info = harness.module._parse_dicom_header(data)

        assert info is not None
        assert info["valid_dicom"] is True
        assert info["file_size"] == len(data)

    def test_rejects_a_wrong_magic_number(self, monkeypatch):
        harness = load_pattern_handler(DICOM_PARSE_HANDLER, monkeypatch)
        assert harness.module._parse_dicom_header(_dicom_bytes(magic=b"NOPE")) is None

    def test_rejects_input_shorter_than_the_header(self, monkeypatch):
        """132 バイト未満は無効

        補足: 実装の `len(data) < 132` を緩めても振る舞いは変わらない。短い入力では
        `data[128:132]` が空バイト列になり、続く `!= b"DICM"` で弾かれるため、
        同じく None を返す。長さガードは意図を明示する防御であり、判定はマジック
        ナンバーの比較が担っている。テストで区別できる差は無いので、そこは追わない。
        """
        harness = load_pattern_handler(DICOM_PARSE_HANDLER, monkeypatch)
        assert harness.module._parse_dicom_header(b"\x00" * 131) is None
        assert harness.module._parse_dicom_header(b"") is None
        assert harness.module._parse_dicom_header(b"DICM") is None

    def test_accepts_exactly_132_bytes(self, monkeypatch):
        """境界: プリアンブル 128 + マジック 4 = 132 は有効"""
        harness = load_pattern_handler(DICOM_PARSE_HANDLER, monkeypatch)
        info = harness.module._parse_dicom_header(_dicom_bytes())

        assert info is not None
        assert info["file_size"] == 132

    def test_rejects_magic_at_the_wrong_offset(self, monkeypatch):
        """先頭に DICM があってもプリアンブル後になければ無効"""
        harness = load_pattern_handler(DICOM_PARSE_HANDLER, monkeypatch)
        data = b"DICM" + b"\x00" * 128

        assert harness.module._parse_dicom_header(data) is None


# =========================================================================
# dicom_parse handler
# =========================================================================


class TestDicomParseHandler:
    def test_uses_supplied_metadata_without_fetching(self, monkeypatch):
        """イベントにメタデータがあれば S3 から取得しない"""
        harness = load_pattern_handler(DICOM_PARSE_HANDLER, monkeypatch)
        result = harness.handler(
            {"Key": "study1/img.dcm", "metadata": {"patient_name": "secret", "modality": "CT"}},
            harness.context,
        )

        assert "get_object" not in harness.calls
        assert result["status"] == "SUCCESS"
        assert "patient_name" not in result["metadata"]

    def test_fetches_when_metadata_is_absent(self, monkeypatch):
        harness = load_pattern_handler(DICOM_PARSE_HANDLER, monkeypatch)
        monkeypatch.setattr(
            harness.module.S3ApHelper,
            "get_object",
            lambda self, key: {"Body": type("B", (), {"read": staticmethod(lambda: _dicom_bytes(tail=8))})()},
        )
        result = harness.handler({"Key": "study1/img.dcm"}, harness.context)

        assert result["status"] == "SUCCESS"

    def test_invalid_dicom_returns_invalid_without_writing(self, monkeypatch):
        """DICM で始まらないデータは INVALID を返し、結果を書き出さない"""
        harness = load_pattern_handler(DICOM_PARSE_HANDLER, monkeypatch)
        monkeypatch.setattr(
            harness.module.S3ApHelper,
            "get_object",
            lambda self, key: {"Body": type("B", (), {"read": staticmethod(lambda: b"\x00" * 200)})()},
        )
        result = harness.handler({"Key": "study1/broken.dcm"}, harness.context)

        assert result["status"] == "INVALID"
        assert "put_object" not in harness.calls

    def test_fetch_failure_returns_invalid_rather_than_raising(self, monkeypatch):
        """取得失敗は例外を投げず INVALID として返す（Map ステートを止めない）"""
        harness = load_pattern_handler(DICOM_PARSE_HANDLER, monkeypatch)
        monkeypatch.setattr(
            harness.module.S3ApHelper,
            "get_object",
            lambda self, key: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        result = harness.handler({"Key": "study1/img.dcm"}, harness.context)

        assert result["status"] == "INVALID"
        assert "boom" in result["error"]
        assert "put_object" not in harness.calls

    def test_output_key_is_date_partitioned_under_dicom_metadata(self, monkeypatch):
        harness = load_pattern_handler(DICOM_PARSE_HANDLER, monkeypatch)
        result = harness.handler(
            {"Key": "study1/deep/img.dcm", "metadata": {"modality": "CT"}},
            harness.context,
        )

        key = result["output_key"]
        assert key.startswith("dicom-metadata/")
        assert key.endswith("img.dcm.json")
        assert "study1/deep" not in key

        middle = key[len("dicom-metadata/") : -len("/img.dcm.json")]
        assert [len(p) for p in middle.split("/")] == [4, 2, 2], key

    def test_written_body_contains_no_phi(self, monkeypatch):
        """S3 に書き出す本文に PHI が含まれない

        このパターンで最も重要な検査。返り値だけを見ると、書き出す本文に元の
        メタデータが混ざる実装でも通ってしまう。
        """
        captured: dict = {}
        harness = load_pattern_handler(DICOM_PARSE_HANDLER, monkeypatch)
        phi_fields = harness.module.PHI_FIELDS

        monkeypatch.setattr(
            harness.module.S3ApHelper,
            "put_object",
            lambda self, **kw: captured.update(kw) or {},
        )

        metadata = {field: f"SENTINEL_{field.upper()}" for field in phi_fields}
        metadata.update({"modality": "CT", "body_part": "CHEST"})
        harness.handler({"Key": "study1/img.dcm", "metadata": metadata}, harness.context)

        body = captured["body"]
        for field in phi_fields:
            assert field not in body, f"{field} が書き出し本文に残っている"
            assert f"SENTINEL_{field.upper()}" not in body, f"{field} の値が本文に残っている"

        parsed = json.loads(body)
        assert parsed["status"] == "SUCCESS"
        assert parsed["classification"]["modality_category"] == "computed_tomography"

    def test_classification_is_exposed_on_the_return_value(self, monkeypatch):
        harness = load_pattern_handler(DICOM_PARSE_HANDLER, monkeypatch)
        result = harness.handler(
            {"Key": "study1/img.dcm", "metadata": {"modality": "US", "body_part": "ABDOMEN"}},
            harness.context,
        )

        assert result["classification"]["modality_category"] == "ultrasound"
        assert result["classification"]["body_part"] == "ABDOMEN"


# =========================================================================
# CloudFormation テンプレート
# =========================================================================


class TestTemplateConsistency:
    def test_both_templates_parse(self):
        assert load_sam_template(TEMPLATE).resources
        assert load_sam_template(TEMPLATE_DEPLOY).resources

    def test_suffix_filter_is_passed_to_a_function(self):
        """SUFFIX_FILTER が実際に関数の環境変数として渡されている

        以前は本文に部分文字列があるかだけを見ていたので、コメント内の記述でも
        通ってしまった。
        """
        assert "SUFFIX_FILTER" in load_sam_template(TEMPLATE).all_function_env_names()

    def test_discovery_env_matches_what_the_handler_reads(self):
        template = load_sam_template(TEMPLATE)
        discovery = [lid for lid in template.functions() if "Discovery" in lid]
        assert discovery, f"Discovery 関数が見つからない: {list(template.functions())}"

        env = template.function_env(discovery[0])
        for name in ("S3_ACCESS_POINT", "SUFFIX_FILTER"):
            assert name in env, f"{name} が {discovery[0]} に無い: {sorted(env)}"

    @pytest.mark.parametrize(
        "name",
        ["EnableVpcEndpoints", "EnableS3GatewayEndpoint", "PrivateRouteTableIds"],
    )
    def test_vpc_endpoint_parameters_declared(self, name):
        assert name in load_sam_template(TEMPLATE).parameters

    def test_conditions_only_reference_declared_parameters(self):
        assert load_sam_template(TEMPLATE).undefined_condition_refs() == set()
