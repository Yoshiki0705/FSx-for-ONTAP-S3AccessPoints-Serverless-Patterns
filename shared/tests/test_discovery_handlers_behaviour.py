"""全パターンの discovery ハンドラを実際に実行する横断テスト

## なぜ必要か

各パターンのテストの多くはハンドラのソース文字列を検査するだけで、実行しない
（リポジトリ全体で 286 箇所）。そのため次のような退行を誰も検出できなかった:

- モジュールレベルの import が壊れている
- `os.environ[...]` の必須キーが増えたのにテンプレート側が未対応
- `lambda_error_handler` の契約変更で例外が伝播しなくなる/しすぎる
- 例外型が包み直されて Catch の ErrorEquals が一致しなくなる

28 個の discovery ハンドラは同じ形をしている（`lambda_error_handler` +
`S3ApHelper`）。ここでは 1 ファイルで全部を実行し、パターンごとに個別テストを
28 個書かずに振る舞いを固定する。

ドメインロジックの検証は各パターンのテストの仕事。ここで見るのは全パターンに
共通する契約だけ。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from shared.testing import InjectedHandlerFailure, load_pattern_handler

REPO_ROOT = Path(__file__).resolve().parents[2]

DISCOVERY_HANDLERS = sorted(
    p.relative_to(REPO_ROOT).as_posix()
    for p in REPO_ROOT.glob("solutions/industry/*/functions/discovery/handler.py")
    if ".aws-sam" not in p.as_posix()
)


def _pattern_name(rel_path: str) -> str:
    return rel_path.split("/")[2]


# 収集漏れ（glob の誤りやディレクトリ移動）そのものを検出する
def test_discovery_handlers_are_discovered():
    """対象ハンドラが実際に集まっていることを検証する

    glob が空になるとこのファイルの全テストが「0 件成功」で通ってしまう。
    """
    assert len(DISCOVERY_HANDLERS) >= 25, f"expected the industry discovery handlers, found {len(DISCOVERY_HANDLERS)}"


@pytest.mark.parametrize("rel_path", DISCOVERY_HANDLERS, ids=_pattern_name)
class TestDiscoveryHandlerContract:
    """全 discovery ハンドラに共通する契約"""

    def test_module_imports_and_exposes_handler(self, rel_path, monkeypatch):
        """モジュールが import でき、handler が呼び出せることを検証する

        ソース文字列検査では import エラーを検出できない。
        """
        harness = load_pattern_handler(rel_path, monkeypatch)

        assert callable(harness.handler)
        assert harness.handler.__name__ in ("handler", "wrapper")

    def test_reads_the_access_point_from_the_environment(self, rel_path, monkeypatch):
        """環境変数の S3 AP を使って S3ApHelper を組み立てることを検証する

        ハードコードされた値や、別の環境変数名への置き換えを検出する。
        """
        harness = load_pattern_handler(
            rel_path,
            monkeypatch,
            env={"S3_ACCESS_POINT": "sentinel-ap-ext-s3alias"},
        )

        harness.handler({}, harness.context)

        used = {i.access_point for i in harness.s3ap_instances}
        assert "sentinel-ap-ext-s3alias" in used, f"the handler did not use S3_ACCESS_POINT; used={used}"

    def test_lists_objects_through_the_access_point(self, rel_path, monkeypatch):
        """S3 AP 経由でオブジェクト一覧を取得することを検証する

        boto3 の s3 クライアントを直接使う実装への退行を検出する
        （AGENTS.md: ハンドラで boto3.client('s3') を直接使わない）。
        """
        harness = load_pattern_handler(
            rel_path,
            monkeypatch,
            objects=[{"Key": "a.txt", "Size": 1, "ETag": "e"}],
        )

        harness.handler({}, harness.context)

        assert "list_objects" in harness.calls, f"calls={harness.calls}"

    def test_failure_propagates_instead_of_returning_a_status_code(self, rel_path, monkeypatch):
        """失敗時に例外が伝播することを検証する

        `lambda_error_handler` が例外を飲み込んで 500 を返すと Lambda は正常終了し、
        Step Functions は失敗を成功と判定して次のステートへ進む。各ステートマシンの
        States.TaskFailed の Retry / Catch も発火しない。

        ここでは S3 AP の一覧取得を失敗させ、その例外が呼び出し側まで届くこと、
        そして型が包み直されないことを固定する（Catch の ErrorEquals が型名を見る）。
        """
        harness = load_pattern_handler(rel_path, monkeypatch, fail_on="list_objects")

        with pytest.raises(InjectedHandlerFailure):
            harness.handler({}, harness.context)
