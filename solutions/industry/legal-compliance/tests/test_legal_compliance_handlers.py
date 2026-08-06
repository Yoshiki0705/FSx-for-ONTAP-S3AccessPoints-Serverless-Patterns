"""Legal Compliance パターンのハンドラを実際に実行して検証する

## このファイルの変更について

以前はハンドラのソースを文字列として読み、部分文字列の有無を見ていた:

    with open(handler_path) as f:
        content = f.read()
    assert "def format_acl_record(" in content

これは「その名前で def が書かれている」ことしか示さない。ACL レコードの中身が
壊れても、`build_s3_key` が日付パーティションを落としても、
`OntapClientError` を捕まえずに投げるようになっても、すべて通る。

いまは実際に呼ぶ。

`handler` の存在と `@lambda_error_handler` による例外伝播は全パターン共通の契約で
`shared/tests/test_discovery_handlers_behaviour.py` が、AD DC pre-flight の実行
順序は同ディレクトリの `test_discovery_ad_preflight.py` が既に検証している。
ここでは重複させず、このパターン固有の振る舞いだけを見る。
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from shared.ontap_client import OntapClientError
from shared.testing import load_pattern_handler, load_sam_template

PATTERN = "solutions/industry/legal-compliance"
DISCOVERY = f"{PATTERN}/functions/discovery/handler.py"
ACL_COLLECTION = f"{PATTERN}/functions/acl_collection/handler.py"
TEMPLATE = f"{PATTERN}/template.yaml"


# =========================================================================
# Discovery Handler
# =========================================================================


class TestDiscoveryHandler:
    """Discovery ハンドラの振る舞い"""

    def test_returns_objects_and_ontap_metadata(self, monkeypatch):
        """オブジェクト一覧と ONTAP メタデータの両方を返すことを検証する

        後続の Map ステートは objects を、監査レポートは metadata を読む。
        どちらが欠けても後続が壊れる。
        """
        harness = load_pattern_handler(DISCOVERY, monkeypatch, objects=[{"Key": "case/a.pdf", "Size": 1}])

        result = harness.handler({}, harness.context)

        assert [o["Key"] for o in result["objects"]] == ["case/a.pdf"]
        assert result["total_objects"] == 1
        assert "metadata" in result
        assert result["manifest_key"].startswith("manifests/")

    def test_manifest_key_is_date_partitioned(self, monkeypatch):
        """Manifest キーが日付階層を持つことを検証する"""
        harness = load_pattern_handler(DISCOVERY, monkeypatch, objects=[{"Key": "a.pdf", "Size": 1}])

        prefix, year, month, day, name = harness.handler({}, harness.context)["manifest_key"].split("/")

        assert prefix == "manifests"
        assert (len(year), len(month), len(day)) == (4, 2, 2)
        assert name.endswith(".json")

    def test_written_manifest_carries_the_objects_and_metadata(self, monkeypatch):
        """S3 に書かれた Manifest 本体にオブジェクトとメタデータが入ることを検証する

        戻り値だけを見ても足りない。後続の監査レポートは Step Functions の
        ペイロードではなく S3 上の Manifest を読むため、戻り値には入っていて
        Manifest 側から落ちる、という壊れ方があり得る（実際にこの検証を入れる前は
        Manifest から metadata を落とす変異が検出されなかった）。
        """
        harness = load_pattern_handler(DISCOVERY, monkeypatch)
        writes: list[dict] = []

        class RecordingS3Ap:
            def __init__(self, access_point, *a, **kw):
                self.access_point = access_point

            def list_objects(self, prefix="", suffix="", max_keys=1000):
                return [{"Key": "case/a.pdf", "Size": 1}]

            def put_object(self, **kw):
                writes.append(kw)
                return {}

        monkeypatch.setattr(harness.module, "S3ApHelper", RecordingS3Ap)

        harness.handler({}, harness.context)

        assert len(writes) == 1, "the manifest was not written exactly once"
        manifest = json.loads(writes[0]["body"])
        assert [o["Key"] for o in manifest["objects"]] == ["case/a.pdf"]
        assert "metadata" in manifest, "the audit report reads metadata from the manifest"
        assert manifest["total_objects"] == 1
        assert "execution_id" in manifest and "timestamp" in manifest

    def test_verify_ssl_false_disables_certificate_validation(self, monkeypatch):
        """VERIFY_SSL=false が ONTAP クライアント設定に伝わることを検証する

        検証を切る設定が無視されると、自己署名証明書の検証環境で接続できない。
        逆に既定で切れていると本番で黙って検証なしになる。
        """
        harness = load_pattern_handler(DISCOVERY, monkeypatch, env={"VERIFY_SSL": "false"})
        captured: list[object] = []
        monkeypatch.setattr(harness.module, "OntapClient", lambda cfg: captured.append(cfg) or MagicMock())

        harness.handler({}, harness.context)

        assert captured, "OntapClient was never constructed"
        assert captured[0].verify_ssl is False

    def test_verify_ssl_defaults_to_enabled(self, monkeypatch):
        """VERIFY_SSL 未設定時は証明書検証が有効であることを検証する"""
        harness = load_pattern_handler(DISCOVERY, monkeypatch)
        monkeypatch.delenv("VERIFY_SSL", raising=False)
        captured: list[object] = []
        monkeypatch.setattr(harness.module, "OntapClient", lambda cfg: captured.append(cfg) or MagicMock())

        harness.handler({}, harness.context)

        assert captured[0].verify_ssl is True


class TestOntapMetadataCollection:
    """`_collect_ontap_metadata` の収集結果"""

    @pytest.fixture
    def collect(self, monkeypatch):
        harness = load_pattern_handler(DISCOVERY, monkeypatch)
        return harness.module._collect_ontap_metadata

    def test_collects_exports_and_shares(self, collect):
        """エクスポートポリシーと CIFS 共有を収集することを検証する"""
        client = MagicMock()
        client.list_nfs_exports.return_value = [{"policy": "default"}]
        client.list_cifs_shares.return_value = [{"name": "share1"}]

        metadata = collect(client, "svm-1")

        assert metadata["export_policies"] == [{"policy": "default"}]
        assert metadata["cifs_shares"] == [{"name": "share1"}]

    def test_a_failing_call_does_not_lose_the_other_sections(self, collect):
        """1 つの収集が失敗しても他のセクションが残ることを検証する

        監査用のメタデータなので、一部が取れないことは起こる。そこで全体を
        落とすと、取れたはずの情報まで失われる。
        """
        client = MagicMock()
        client.list_nfs_exports.side_effect = OntapClientError("export policy read failed")
        client.list_cifs_shares.return_value = [{"name": "share1"}]

        metadata = collect(client, "svm-1")

        assert metadata["export_policies"] == []
        assert metadata["cifs_shares"] == [{"name": "share1"}]

    def test_security_style_is_unknown_when_volume_info_is_unavailable(self, collect):
        """ボリューム情報が取れないとき security_style が unknown になることを検証する

        既定値を "ntfs" などにすると、確認できていない前提で ACL 収集へ進む。
        """
        client = MagicMock()
        client.list_volumes.side_effect = OntapClientError("volume read failed")

        metadata = collect(client, "svm-1")

        assert metadata["security_style"] == "unknown"


# =========================================================================
# ACL Collection Handler
# =========================================================================


def _load_acl(monkeypatch, security_info=None, error=None, **env):
    """acl_collection を読み込み、ONTAP の応答を設定する"""
    harness = load_pattern_handler(ACL_COLLECTION, monkeypatch, env=env)
    if error is not None:
        harness.ontap_client.get_file_security.side_effect = error
    else:
        harness.ontap_client.get_file_security.return_value = security_info or {
            "security_style": "ntfs",
            "acls": [{"user": "DOMAIN\\user", "access": "full_control"}],
        }
    return harness


class TestAclCollectionHandler:
    """ACL Collection ハンドラの振る舞い"""

    def test_returns_success_with_the_output_key(self, monkeypatch):
        """成功時に SUCCESS と出力キーを返すことを検証する"""
        harness = _load_acl(monkeypatch)

        result = harness.handler({"Key": "case/a.pdf", "Size": 1}, harness.context)

        assert result["status"] == "SUCCESS"
        assert result["object_key"] == "case/a.pdf"
        assert result["s3_output_key"].startswith("acl-data/")

    def test_writes_ndjson_to_the_output_access_point(self, monkeypatch):
        """出力が NDJSON の Content-Type で書かれることを検証する

        Athena の JSON SerDe が 1 行 1 レコードを前提にしているため、
        通常の application/json にすると取り込み側が読めない。
        """
        harness = _load_acl(monkeypatch)
        writes: list[dict] = []

        class RecordingS3Ap:
            def __init__(self, access_point, *a, **kw):
                self.access_point = access_point

            def put_object(self, **kw):
                writes.append(kw)
                return {}

        monkeypatch.setattr(harness.module, "S3ApHelper", RecordingS3Ap)

        harness.handler({"Key": "case/a.pdf"}, harness.context)

        assert len(writes) == 1
        assert writes[0]["content_type"] == "application/x-ndjson"
        assert writes[0]["body"].endswith("\n"), "NDJSON records must be newline-terminated"
        record = json.loads(writes[0]["body"])
        assert record["object_key"] == "case/a.pdf"
        assert record["security_style"] == "ntfs"

    def test_ontap_failure_marks_the_object_without_stopping_the_workflow(self, monkeypatch):
        """ONTAP 失敗時に例外を投げず FAILED を返すことを検証する

        Map ステートの 1 件が例外で落ちると Map 全体が失敗する。ACL が読めない
        オブジェクトは記録して先へ進むのがこのパターンの設計。
        """
        harness = _load_acl(monkeypatch, error=OntapClientError("acl read denied"))

        result = harness.handler({"Key": "case/locked.pdf"}, harness.context)

        assert result["status"] == "FAILED"
        assert result["object_key"] == "case/locked.pdf"
        assert "acl read denied" in result["error"]

    def test_unexpected_errors_still_propagate(self, monkeypatch):
        """想定外の例外は伝播することを検証する

        すべてを飲み込むと、設定ミスや権限不足も「FAILED を返して完走」になり、
        ワークフローが成功扱いで終わる。
        """
        harness = _load_acl(monkeypatch, error=RuntimeError("credentials missing"))

        with pytest.raises(RuntimeError, match="credentials missing"):
            harness.handler({"Key": "case/a.pdf"}, harness.context)

    def test_missing_security_style_falls_back_to_unknown(self, monkeypatch):
        """security_style が応答に無いとき unknown になることを検証する"""
        harness = _load_acl(monkeypatch, security_info={"acls": []})
        writes: list[dict] = []

        class RecordingS3Ap:
            def __init__(self, access_point, *a, **kw):
                pass

            def put_object(self, **kw):
                writes.append(kw)
                return {}

        monkeypatch.setattr(harness.module, "S3ApHelper", RecordingS3Ap)

        harness.handler({"Key": "case/a.pdf"}, harness.context)

        assert json.loads(writes[0]["body"])["security_style"] == "unknown"


class TestAclRecordFormatting:
    """`format_acl_record` と `build_s3_key`"""

    @pytest.fixture
    def module(self, monkeypatch):
        return load_pattern_handler(ACL_COLLECTION, monkeypatch).module

    def test_record_is_a_single_json_line(self, module):
        """レコードが改行を含まない 1 行の JSON であることを検証する

        改行が入ると NDJSON の 1 行 1 レコードが崩れ、Athena が壊れた行を読む。
        """
        line = module.format_acl_record(
            object_key="case/a.pdf",
            volume_uuid="vol-1",
            security_style="ntfs",
            acls=[{"user": "DOMAIN\\user"}],
        )

        assert "\n" not in line
        record = json.loads(line)
        assert record["object_key"] == "case/a.pdf"
        assert record["volume_uuid"] == "vol-1"
        assert record["security_style"] == "ntfs"
        assert record["acls"] == [{"user": "DOMAIN\\user"}]
        assert "collected_at" in record

    def test_s3_key_is_date_partitioned_ndjson(self, module):
        """S3 キーが `acl-data/YYYY/MM/DD/<id>.jsonl` であることを検証する

        Glue のパーティション射影がこの階層を前提にしている。
        """
        key = module.build_s3_key("exec-123")

        prefix, year, month, day, name = key.split("/")
        assert prefix == "acl-data"
        assert (len(year), len(month), len(day)) == (4, 2, 2)
        assert year.isdigit() and month.isdigit() and day.isdigit()
        assert name == "exec-123.jsonl"


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
            "OntapSecretName",
            "OntapManagementIp",
        ],
    )
    def test_parameter_is_declared(self, tpl, name):
        """パラメータが Parameters に宣言されていることを検証する"""
        assert name in tpl.parameters, f"declared parameters: {sorted(tpl.parameters)}"

    def test_suffix_filter_is_passed_to_a_function(self, tpl):
        """SUFFIX_FILTER が実際に環境変数として渡されることを検証する"""
        assert "SUFFIX_FILTER" in tpl.all_function_env_names()

    def test_acl_collection_receives_the_ontap_connection_settings(self, tpl):
        """ACL 収集関数に ONTAP 接続情報が渡ることを検証する

        この関数は ONTAP REST API を直接呼ぶので、接続情報が無いと起動しない。
        """
        env = tpl.function_env("AclCollectionFunction")

        assert "ONTAP_MANAGEMENT_IP" in env
        assert "ONTAP_SECRET_NAME" in env
        assert "SVM_UUID" in env
        assert "VOLUME_UUID" in env

    def test_conditions_only_reference_declared_names(self, tpl):
        """Conditions が未宣言の名前を参照していないことを検証する"""
        assert tpl.undefined_condition_refs() == set()
