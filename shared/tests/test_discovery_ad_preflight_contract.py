"""すべての discovery ハンドラが AD DC pre-flight を正しい位置で呼ぶことの検証

ROADMAP の「AD DC Health Check Integration（全 WINDOWS パターン）」に対応する。
`shared/ad_health_check.py` と `shared/tests/test_ad_health_check.py` はチェック
自体を検証しており、していなかったのは「各パターンがそれを呼んでいるか」の検証。
両者は別の問いで、実装では 10 パターンのうち 1 つだけが呼んでいた。

パターンごとにテストファイルを複製していない。1 本のパラメトライズドテストで
ツリーを走査するのは、新しいパターンが追加されたときに自動で対象に入るためで、
複製した 9 ファイルは追加分を守らない。`portal_path_scope` の docstring が
「境界のコピーが 2 つあると食い違う」と書いているのと同じ理由。

対象の選び方が固定値でないのも同じ理由。identity type は S3 AP 側の設定で
テンプレートには現れないので、「WINDOWS を使うパターン」を列挙して書き留めることは
できない。代わりに構造で選ぶ: ONTAP クライアントと S3 AP の両方を持つ discovery
ハンドラは、AD 参加 SVM に向けられうる。

pre-flight を「最初の S3 AP データ操作より前」に置くことが要点。後ろに置くと
list_objects が先に AccessDenied になり、原因が AD DC だと特定する機会が失われる。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from shared.testing import load_pattern_handler

REPO_ROOT = Path(__file__).resolve().parents[2]


def _discovery_handlers_touching_both() -> list[Path]:
    """ONTAP クライアントと S3 AP の両方を使う discovery ハンドラ

    Returns:
        リポジトリルートからの相対パスのリスト（パターン名でソート）
    """
    found = []
    for handler in sorted((REPO_ROOT / "solutions" / "industry").glob("*/functions/discovery/handler.py")):
        source = handler.read_text(encoding="utf-8")
        if "OntapClient" in source and "S3ApHelper" in source:
            found.append(handler.relative_to(REPO_ROOT))
    return found


HANDLERS = _discovery_handlers_touching_both()
IDS = [str(p).split("/")[2] for p in HANDLERS]


def test_the_scan_found_the_patterns() -> None:
    """走査そのものが空振りしていないことを確認する

    glob が何も返さなくても、パラメトライズドテストは 0 件成功として緑になる。
    それは検証ではないので、ここで下限を置く。
    """
    assert len(HANDLERS) >= 10, f"expected at least 10 discovery handlers, found {len(HANDLERS)}: {IDS}"


@pytest.mark.parametrize("handler_path", HANDLERS, ids=IDS)
def test_preflight_runs_before_the_first_s3ap_data_operation(
    handler_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """pre-flight が最初の S3 AP データ操作より前に走ることを検証する"""
    harness = load_pattern_handler(handler_path, monkeypatch, objects=[{"Key": "a.txt", "Size": 1}])

    harness.handler({}, harness.context)

    harness.assert_called_before("preflight", "list_objects")


@pytest.mark.parametrize("handler_path", HANDLERS, ids=IDS)
def test_preflight_is_given_the_svm_uuid_rather_than_a_name(
    handler_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """環境変数の SVM_UUID で呼ばれることを検証する

    パターンの Lambda は SVM 名を持たない。UUID で呼べることがテンプレート変更
    なしで統合できる理由なので、名前指定に変わっていないことを固定する。
    """
    harness = load_pattern_handler(handler_path, monkeypatch, objects=[{"Key": "a.txt", "Size": 1}])

    seen: dict[str, object] = {}

    def capture(ontap_client: object, svm_name: str | None = None, *, svm_uuid: str | None = None) -> object:
        seen["svm_name"] = svm_name
        seen["svm_uuid"] = svm_uuid

        class _Status:
            message = "captured"

        return _Status()

    monkeypatch.setattr(harness.module, "preflight_ad_dc_reachability", capture)

    harness.handler({}, harness.context)

    assert seen["svm_uuid"] == "svm-uuid-0000"
    assert seen["svm_name"] is None


@pytest.mark.parametrize("handler_path", HANDLERS, ids=IDS)
def test_an_unreachable_dc_stops_before_touching_the_access_point(
    handler_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DC 到達不能なら S3 AP に触らずに失敗することを検証する

    固定したい点は 2 つ。S3 AP を叩かずに止まること、そして例外型が保たれること
    （Step Functions の Catch が ErrorEquals で判別する）。
    """
    from shared.ad_health_check import AdDcUnreachableError, AdHealthStatus

    harness = load_pattern_handler(handler_path, monkeypatch, objects=[{"Key": "a.txt", "Size": 1}])

    def raiser(ontap_client: object, svm_name: str | None = None, *, svm_uuid: str | None = None) -> None:
        harness.calls.append("preflight")
        raise AdDcUnreachableError(
            message="AD CONNECTIVITY FAILURE: cannot reach any AD Domain Controllers",
            status=AdHealthStatus(is_ad_joined=True, dc_reachable=False),
            svm_name=f"uuid={svm_uuid}",
        )

    monkeypatch.setattr(harness.module, "preflight_ad_dc_reachability", raiser)

    with pytest.raises(AdDcUnreachableError, match="AD CONNECTIVITY FAILURE"):
        harness.handler({}, harness.context)

    assert "preflight" in harness.calls
    assert "list_objects" not in harness.calls, "S3 AP was touched despite an unreachable AD DC"
    assert "put_object" not in harness.calls
