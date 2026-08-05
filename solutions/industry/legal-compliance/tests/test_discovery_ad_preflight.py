"""Discovery ハンドラの AD DC pre-flight の振る舞いテスト

同ディレクトリの test_legal_compliance_handlers.py はハンドラのソース文字列を
検査するテストで、ハンドラを実行しない。そのため呼び出し順序のような設計上の
取り決めは何も守られていなかった。ここでは実際に handler() を動かして固定する。

pre-flight で重要なのは「最初の S3 AP データ操作より前に走る」こと。後ろに置くと
list_objects が先に AccessDenied になり、チェックが存在する意味が無くなる。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

HANDLER_PATH = Path(__file__).parent.parent / "functions" / "discovery" / "handler.py"

ENV = {
    "S3_ACCESS_POINT": "ap-in-ext-s3alias",
    "S3_ACCESS_POINT_OUTPUT": "ap-out-ext-s3alias",
    "ONTAP_MANAGEMENT_IP": "198.51.100.10",
    "ONTAP_SECRET_NAME": "example-secret",
    "SVM_UUID": "svm-uuid-1",
    "PREFIX_FILTER": "",
    "SUFFIX_FILTER": "",
}


@pytest.fixture
def discovery(monkeypatch):
    """handler モジュールを、共有依存をモックした状態で読み込む"""
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)

    calls: list[str] = []

    s3ap_instances = []

    class FakeS3Ap:
        def __init__(self, access_point, *a, **kw):
            self.access_point = access_point
            s3ap_instances.append(self)

        def list_objects(self, prefix="", suffix=""):
            calls.append("list_objects")
            return [{"Key": "a.txt", "Size": 1}]

        def put_object(self, **kw):
            calls.append("put_object")
            return {}

    def fake_preflight(ontap_client, svm_name=None, *, svm_uuid=None):
        calls.append("preflight")
        status = MagicMock()
        status.message = "preflight ran"
        return status

    import shared.ad_health_check as ad_mod
    import shared.ontap_client as ontap_mod
    import shared.s3ap_helper as s3ap_mod

    monkeypatch.setattr(s3ap_mod, "S3ApHelper", FakeS3Ap)
    monkeypatch.setattr(ad_mod, "preflight_ad_dc_reachability", fake_preflight)

    fake_client = MagicMock()
    fake_client.list_volumes.return_value = []
    fake_client.list_nfs_exports.return_value = []
    fake_client.list_cifs_shares.return_value = []
    monkeypatch.setattr(ontap_mod, "OntapClient", lambda cfg: fake_client)

    spec = importlib.util.spec_from_file_location("lc_discovery_under_test", HANDLER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["lc_discovery_under_test"] = module
    spec.loader.exec_module(module)

    yield module, calls

    sys.modules.pop("lc_discovery_under_test", None)


def _context():
    ctx = MagicMock()
    ctx.aws_request_id = "req-1"
    return ctx


def test_preflight_runs_before_first_s3ap_data_operation(discovery):
    """pre-flight が list_objects より前に走ることを検証する

    これが逆になると list_objects が先に AccessDenied になり、AD DC が原因だと
    特定する機会が失われる。
    """
    module, calls = discovery

    module.handler({}, _context())

    assert "preflight" in calls, "pre-flight was not invoked at all"
    assert "list_objects" in calls
    assert calls.index("preflight") < calls.index("list_objects")


def test_preflight_receives_the_svm_uuid_from_env(discovery, monkeypatch):
    """pre-flight に環境変数の SVM_UUID が渡されることを検証する

    ハンドラは SVM 名を持たない。UUID で呼べることがテンプレート変更なしで
    統合できる理由なので、ここが名前指定に変わっていないことを固定する。
    """
    module, _ = discovery
    seen = {}

    def capture(ontap_client, svm_name=None, *, svm_uuid=None):
        seen["svm_name"] = svm_name
        seen["svm_uuid"] = svm_uuid
        return MagicMock(message="ok")

    monkeypatch.setattr(module, "preflight_ad_dc_reachability", capture)

    module.handler({}, _context())

    assert seen["svm_uuid"] == ENV["SVM_UUID"]
    assert seen["svm_name"] is None


def test_unreachable_dc_fails_the_invocation_before_listing(discovery, monkeypatch):
    """DC 到達不能なら S3 AP に触らず、呼び出しそのものを失敗させることを検証する

    `lambda_error_handler` は診断ログを残して例外を再送出する。Lambda の呼び出しが
    失敗するので、Step Functions は Discovery タスクを失敗として扱い、ステート
    マシンに定義済みの `States.TaskFailed` の Retry / Catch が働く。

    固定したい点:
    - list_objects に到達しない（S3 AP を叩かずに止まる）
    - 例外型が保たれる（Catch の ErrorEquals で判別できる）
    """
    module, calls = discovery

    from shared.ad_health_check import AdDcUnreachableError, AdHealthStatus

    def raiser(ontap_client, svm_name=None, *, svm_uuid=None):
        calls.append("preflight")
        raise AdDcUnreachableError(
            message="AD CONNECTIVITY FAILURE: cannot reach any AD Domain Controllers",
            status=AdHealthStatus(is_ad_joined=True, dc_reachable=False),
            svm_name="uuid=svm-uuid-1",
        )

    monkeypatch.setattr(module, "preflight_ad_dc_reachability", raiser)

    with pytest.raises(AdDcUnreachableError, match="AD CONNECTIVITY FAILURE"):
        module.handler({}, _context())

    assert "preflight" in calls
    assert "list_objects" not in calls, "S3 AP was touched despite an unreachable AD DC"
    assert "put_object" not in calls
