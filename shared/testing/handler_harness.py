"""パターンの Lambda ハンドラを実際に実行するためのテストハーネス

## なぜこれが必要か

パターン側のテストの多くは、ハンドラを実行せずソース文字列を検査している:

    handler_path = os.path.join(..., "functions", "discovery", "handler.py")
    content = open(handler_path).read()
    assert "def handler(event, context):" in content

これは「その文字列がファイルに存在する」ことしか示さない。実行しないので、
呼び出し順序・環境変数の扱い・例外の伝播といった実際の振る舞いは何も守られない。
リポジトリ全体で 286 箇所がこの形になっている。

ハンドラを実行しようとすると毎回同じ準備が必要になる:

- ハンドラは `functions/<name>/handler.py` にあり、パッケージではないので
  通常の import ができない
- モジュールレベルで `shared.*` を import しているため、差し替えは import 前に
  済ませる必要がある
- `os.environ[...]` を直接読むため、環境変数が無いと import/実行で落ちる

その準備をここに集約する。これがないと、各パターンで少しずつ違う 28 通りの
ローダーが生えることになる。

## 使い方

    from shared.testing import load_pattern_handler

    harness = load_pattern_handler(
        "solutions/industry/legal-compliance/functions/discovery/handler.py",
        env={"S3_ACCESS_POINT": "ap-ext-s3alias", ...},
    )
    harness.handler({}, harness.context)
    assert harness.calls.index("preflight") < harness.calls.index("list_objects")
"""

from __future__ import annotations

import importlib.util
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from unittest.mock import MagicMock

# ハンドラが共通して必要とする環境変数。実際の値は使わないので、形だけ満たす。
DEFAULT_ENV: dict[str, str] = {
    "S3_ACCESS_POINT": "in-ap-ext-s3alias",
    "S3_ACCESS_POINT_OUTPUT": "out-ap-ext-s3alias",
    "ONTAP_MANAGEMENT_IP": "198.51.100.10",
    "ONTAP_SECRET_NAME": "example-secret",
    "SVM_UUID": "svm-uuid-0000",
    "VOLUME_UUID": "vol-uuid-0000",
    "PREFIX_FILTER": "",
    # 空文字にしてはいけない。suffix をカンマ区切りで回して 1 件ずつ list_objects を
    # 呼ぶハンドラがあり、空だとループ本体が一度も実行されず「S3 AP を呼ばずに成功」
    # という現実には起こらない経路をテストしてしまう。
    "SUFFIX_FILTER": ".txt",
    "OUTPUT_BUCKET": "example-output-bucket",
    "DEMO_MODE": "true",
}


@dataclass
class HandlerHarness:
    """読み込んだハンドラモジュールと、記録された呼び出し列

    Attributes:
        module: 読み込んだハンドラモジュール
        calls: S3 AP / ONTAP に対する呼び出しの発生順（順序の検証に使う）
        s3ap_instances: 生成された S3ApHelper 代替のリスト
        ontap_client: ONTAP クライアント代替（MagicMock）
        context: Lambda コンテキスト代替
    """

    module: Any
    calls: list[str] = field(default_factory=list)
    s3ap_instances: list[Any] = field(default_factory=list)
    ontap_client: Any = None
    context: Any = None

    @property
    def handler(self) -> Callable[[dict, Any], Any]:
        return self.module.handler

    def index_of(self, name: str) -> int:
        """呼び出し列の中での位置を返す（未発生なら AssertionError）"""
        assert name in self.calls, f"{name!r} was never called; calls={self.calls}"
        return self.calls.index(name)

    def assert_called_before(self, first: str, second: str) -> None:
        """first が second より前に呼ばれたことを検証する"""
        assert self.index_of(first) < self.index_of(second), f"expected {first!r} before {second!r}, got {self.calls}"


class InjectedHandlerFailure(RuntimeError):
    """ハーネスが意図的に発生させる失敗

    ハンドラの失敗経路を検証するために使う。実際の例外型と区別できるよう専用の型に
    している。
    """


def _make_fake_s3ap(
    calls: list[str],
    instances: list[Any],
    objects: list[dict],
    fail_on: str | None,
):
    def _maybe_fail(op: str) -> None:
        if fail_on == op:
            raise InjectedHandlerFailure(f"injected failure on {op}")

    class FakeS3Ap:
        def __init__(self, access_point, *a, **kw):
            self.access_point = access_point
            instances.append(self)

        @property
        def bucket_param(self) -> str:
            # 実クラスと同じく、エイリアス/ARN をそのまま Bucket パラメータに使う。
            # エラーメッセージの組み立てで参照するハンドラがある。
            return self.access_point

        # 実シグネチャに合わせる。max_keys を落とすと、接続確認で
        # `list_objects(prefix="", suffix="", max_keys=1)` を呼ぶハンドラが
        # TypeError になり、本来のテスト対象とは別の理由で落ちる。
        def list_objects(self, prefix="", suffix="", max_keys=1000):
            calls.append("list_objects")
            _maybe_fail("list_objects")
            return list(objects)[:max_keys]

        def get_object(self, key):
            calls.append("get_object")
            _maybe_fail("get_object")
            return {"Body": MagicMock(read=lambda: b""), "ContentLength": 0}

        def put_object(self, **kw):
            calls.append("put_object")
            _maybe_fail("put_object")
            return {}

        def head_object(self, key):
            calls.append("head_object")
            _maybe_fail("head_object")
            return {"ContentLength": 0}

        def delete_object(self, key):
            calls.append("delete_object")
            _maybe_fail("delete_object")
            return {}

    return FakeS3Ap


def load_pattern_handler(
    handler_path: str | Path,
    monkeypatch,
    env: dict[str, str] | None = None,
    objects: list[dict] | None = None,
    fail_on: str | None = None,
) -> HandlerHarness:
    """パターンのハンドラを、共有依存を差し替えた状態で読み込む

    Args:
        handler_path: リポジトリルートからの `handler.py` へのパス
        monkeypatch: pytest の monkeypatch フィクスチャ
        env: 追加/上書きする環境変数（DEFAULT_ENV にマージされる）
        objects: list_objects が返すオブジェクト一覧
        fail_on: 指定した S3 AP 操作で `InjectedHandlerFailure` を発生させる
                 （例: "list_objects"）。失敗経路の検証に使う。
                 読み込み後にクラスを差し替えると、ハンドラが import 時に束縛した
                 参照には効かないため、生成時に組み込む必要がある。

    Returns:
        HandlerHarness: 読み込んだモジュールと呼び出し記録
    """
    path = Path(handler_path)
    if not path.is_absolute():
        # このファイルは shared/testing/ にあるので、2 つ上がリポジトリルート
        path = Path(__file__).resolve().parents[2] / path
    if not path.exists():
        raise FileNotFoundError(f"handler not found: {path}")

    merged = {**DEFAULT_ENV, **(env or {})}
    for k, v in merged.items():
        monkeypatch.setenv(k, v)

    calls: list[str] = []
    instances: list[Any] = []

    import shared.ontap_client as ontap_mod
    import shared.s3ap_helper as s3ap_mod

    monkeypatch.setattr(
        s3ap_mod,
        "S3ApHelper",
        _make_fake_s3ap(
            calls,
            instances,
            objects if objects is not None else [],
            fail_on,
        ),
    )

    fake_client = MagicMock()
    # ONTAP のリスト系は空を返す。件数ではなく呼び出しの有無と順序を見る。
    for name in (
        "list_volumes",
        "list_nfs_exports",
        "list_cifs_shares",
        "list_snapshots",
        "list_snapmirror_relationships",
    ):
        getattr(fake_client, name).return_value = []
    fake_client.get.return_value = {"records": []}
    monkeypatch.setattr(ontap_mod, "OntapClient", lambda cfg: fake_client)

    # AD DC pre-flight を入れているハンドラでは、実際の ONTAP 問い合わせを避ける。
    try:
        import shared.ad_health_check as ad_mod
    except ImportError:  # pragma: no cover - モジュールが無い構成
        ad_mod = None
    if ad_mod is not None:

        def fake_preflight(ontap_client, svm_name=None, *, svm_uuid=None):
            calls.append("preflight")
            status = MagicMock()
            status.message = "preflight (harness)"
            return status

        monkeypatch.setattr(ad_mod, "preflight_ad_dc_reachability", fake_preflight)

    # モジュール名を毎回変えて、同名衝突とキャッシュの持ち越しを避ける。
    mod_name = f"harness_{path.parent.parent.name}_{path.parent.name}_{uuid.uuid4().hex[:8]}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(mod_name, None)
        raise
    monkeypatch.setitem(sys.modules, mod_name, module)

    ctx = MagicMock()
    ctx.aws_request_id = "req-harness"
    ctx.function_name = "harness-fn"

    return HandlerHarness(
        module=module,
        calls=calls,
        s3ap_instances=instances,
        ontap_client=fake_client,
        context=ctx,
    )
