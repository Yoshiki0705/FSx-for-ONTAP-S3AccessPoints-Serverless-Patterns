"""discovery ハンドラが発行する FilesProcessed が実際の件数と一致することを検証する

## なぜ必要か

多くの discovery ハンドラは対象サフィックスごとに `list_objects` を呼ぶ:

    for suffix in DOCUMENT_SUFFIXES:
        objects = s3ap.list_objects(prefix=prefix, suffix=suffix)
        all_objects.extend(objects)

ループを抜けた時点で `objects` は**最後のサフィックスの結果だけ**を保持している。
にもかかわらずメトリクスがそれを使っていた:

    metrics.put_metric("FilesProcessed", float(len(objects)), "Count")   # 最後の 1 種のみ

戻り値と Manifest は重複排除後の `unique_objects` を使うので、返す件数と
ダッシュボードに出る件数が食い違う。PDF が 100 件・JPEG が 0 件の実行では
`FilesProcessed` が 0 になり、処理は 100 件走っている。

この不一致は次のいずれでも検出できなかった:

- 型チェックや lint — `objects` は定義済みの正当な変数
- ソース文字列検査 — `put_metric` の行は存在する
- 各パターンのテスト — メトリクスの値を誰も見ていなかった

書き込み先やレポートの件数と違い、メトリクスは「間違っていても動く」ため、
気付く契機が監視側の違和感しかない。

## 検証方法

サフィックスごとに別のオブジェクトを返すフェイクでハンドラを実行し、stdout に
出た EMF ログの `FilesProcessed` が戻り値の `total_objects` と一致することを見る。

サフィックスごとに違う結果を返すのが要点。ハーネス共通のフェイクは全呼び出しで
同じリストを返すため、ループする実装でも「重複排除後 1 件・メトリクス 1 件」で
一致してしまい、この不一致が隠れる。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shared.testing import load_pattern_handler

REPO_ROOT = Path(__file__).resolve().parents[2]

DISCOVERY_HANDLERS = sorted(
    p.relative_to(REPO_ROOT).as_posix()
    for p in REPO_ROOT.glob("solutions/industry/*/functions/discovery/handler.py")
    if ".aws-sam" not in p.as_posix()
)

# ハンドラが走査する可能性のあるサフィックスを広めに渡す。ここが 1 種だけだと
# 「最後のサフィックスの件数」と「全体の件数」が一致してしまい、検証にならない。
SUFFIX_FILTER = ".pdf,.tiff,.jpg,.txt,.csv"


def _pattern_name(rel_path: str) -> str:
    return rel_path.split("/")[2]


class _SuffixAwareS3Ap:
    """サフィックスごとに異なる 1 件を返す S3ApHelper 代替

    同じリストを返すと、ループ実装でも重複排除後の件数と最後の 1 回の件数が
    一致してしまう。サフィックスごとに別キーを返すことで差を作る。
    """

    def __init__(self, access_point, *args, **kwargs):
        self.access_point = access_point

    def list_objects(self, prefix="", suffix="", max_keys=1000):
        tag = (suffix or "all").replace(".", "")
        return [{"Key": f"{prefix}doc-{tag}{suffix or '.bin'}", "Size": 1, "ETag": f"etag-{tag}"}]

    def get_object(self, key):
        return {"Body": _Body(), "ContentLength": 0}

    def head_object(self, key):
        return {"ContentLength": 0}

    def put_object(self, **kwargs):
        return {}

    def delete_object(self, key):
        return {}


class _Body:
    def read(self):
        return b""


def _emitted_files_processed(captured: str) -> float | None:
    """stdout の EMF ログから FilesProcessed の値を取り出す"""
    for line in captured.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "_aws" not in payload or "FilesProcessed" not in payload:
            continue
        return float(payload["FilesProcessed"])
    return None


def test_discovery_handlers_are_discovered():
    """対象ハンドラが実際に集まっていることを検証する"""
    assert len(DISCOVERY_HANDLERS) >= 25, f"expected the industry discovery handlers, found {len(DISCOVERY_HANDLERS)}"


@pytest.mark.parametrize("rel_path", DISCOVERY_HANDLERS, ids=_pattern_name)
def test_files_processed_matches_the_reported_total(rel_path, monkeypatch, capsys):
    """FilesProcessed が戻り値の total_objects と一致することを検証する

    一致しない場合、ダッシュボードとワークフローが別の件数を報告している。
    """
    harness = load_pattern_handler(rel_path, monkeypatch, env={"SUFFIX_FILTER": SUFFIX_FILTER})
    monkeypatch.setattr(harness.module, "S3ApHelper", _SuffixAwareS3Ap)

    result = harness.handler({}, harness.context)

    if not isinstance(result, dict) or "total_objects" not in result:
        pytest.skip("handler does not report total_objects")

    emitted = _emitted_files_processed(capsys.readouterr().out)
    if emitted is None:
        pytest.skip("handler does not emit a FilesProcessed metric")

    assert emitted == float(result["total_objects"]), (
        f"FilesProcessed={emitted} but the handler reported total_objects={result['total_objects']}; "
        "the metric is most likely reading a loop variable instead of the accumulated list"
    )
