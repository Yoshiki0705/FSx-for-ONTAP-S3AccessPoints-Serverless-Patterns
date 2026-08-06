"""テンプレートが SUFFIX_FILTER を渡すパターンで、それが実際に効くことを検証する

## なぜ必要か

いくつかのパターンはテンプレートで `SUFFIX_FILTER` を渡しているのに、ハンドラが
それを読まず、モジュール定数だけで検出対象を決めていた。編集しても何も起きない
ノブがテンプレートに見えている状態で、設定ミスを誘発する。

この乖離は静的解析では確実に判定できない。ハンドラのソースに文字列
`SUFFIX_FILTER` が現れるかを見る方法だと、共通ヘルパー
（`shared/suffix_filter.py`）経由で読むようにした時点で偽陽性になる。実際に
そうなった。だから実行して結果を見る。

## 検証方法

`SUFFIX_FILTER` にこのパターンの既定には無いサフィックスを 1 つだけ渡し、
ハンドラを実行する。返ってきたオブジェクトがすべてそのサフィックスなら、
環境変数が効いている。既定の定数で走っていれば別のサフィックスが混ざる。

## 対象外

`manufacturing-analytics` は意図的に除外している。このパターンは検出対象を
センサーログ（`.csv`）と検査画像（`.jpeg` `.jpg` `.png`）の 2 カテゴリに分け、
オブジェクトごとにどちらかへ分類する。平坦な `SUFFIX_FILTER` を配線すると、
追加された拡張子がどちらのカテゴリにも入らず分類を素通りする。1 つのノブでは
設計に載らないため、`SENSOR_LOG_SUFFIXES` / `INSPECTION_IMAGE_SUFFIXES` の
2 つに分けるかどうかは設計判断として保留している。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from shared.testing import load_pattern_handler, load_sam_template

REPO_ROOT = Path(__file__).resolve().parents[2]

# 既定の拡張子と衝突しない検証用サフィックス
SENTINEL = ".zzsentinel"

# 平坦な SUFFIX_FILTER が設計に載らないパターン（理由はモジュール docstring）
NOT_WIRED_BY_DESIGN = {"manufacturing-analytics"}


def _patterns_declaring_suffix_filter() -> list[str]:
    """テンプレートが DiscoveryFunction に SUFFIX_FILTER を渡すパターン"""
    found = []
    for template_path in sorted(REPO_ROOT.glob("solutions/industry/*/template.yaml")):
        if ".aws-sam" in template_path.as_posix():
            continue
        pattern = template_path.parent.name
        if pattern in NOT_WIRED_BY_DESIGN:
            continue
        handler = template_path.parent / "functions" / "discovery" / "handler.py"
        if not handler.exists():
            continue
        try:
            tpl = load_sam_template(template_path)
        except Exception:  # noqa: BLE001 - テンプレート解析は別のテストが見る
            continue
        for logical_id in tpl.functions():
            if logical_id != "DiscoveryFunction":
                continue
            if "SUFFIX_FILTER" in tpl.function_env(logical_id):
                found.append(pattern)
    return found


PATTERNS = _patterns_declaring_suffix_filter()


class _SentinelS3Ap:
    """照会されたサフィックスを記録し、判定材料を返す S3ApHelper 代替

    サフィックス未指定で一覧を取るハンドラ（クライアント側で拡張子を判定する型）
    には、sentinel のキーと無関係なキーの両方を返す。片方だけだと、
    `SUFFIX_FILTER` を無視しているハンドラでも結果が空になり区別できない。
    """

    queried_suffixes: list[str] = []

    def __init__(self, access_point, *args, **kwargs):
        self.access_point = access_point

    def list_objects(self, prefix="", suffix="", max_keys=1000):
        type(self).queried_suffixes.append(suffix)
        if suffix:
            return [{"Key": f"{prefix}sample{suffix}", "Size": 1, "ETag": "e"}]
        return [
            {"Key": f"{prefix}sample{SENTINEL}", "Size": 1, "ETag": "e"},
            {"Key": f"{prefix}sample.unrelated", "Size": 1, "ETag": "e"},
        ]

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


def test_patterns_are_discovered():
    """対象パターンが実際に集まっていることを検証する"""
    assert PATTERNS, "no pattern declares SUFFIX_FILTER on DiscoveryFunction"


@pytest.mark.parametrize("pattern", PATTERNS)
def test_suffix_filter_is_honoured(pattern, monkeypatch):
    """SUFFIX_FILTER に指定したサフィックスだけが検出されることを検証する

    テンプレートがこのノブを渡しているなら、編集した結果が検出対象に出なければ
    運用者を誤解させる。

    ハンドラには 2 つの型がある。`list_objects(suffix=...)` を対象ごとに呼ぶ型と、
    一覧を取ってからクライアント側で拡張子を判定する型。前者は「何を照会したか」、
    後者は「何を残したか」に環境変数の効果が出るので、両方を見る。

    「結果が空でないこと」は要求しない。sentinel をカテゴリ分類できないパターン
    （`autonomous-driving` の VIDEO/LIDAR/ANNOTATION 等）では、フィルタが効いた
    結果として正しく 0 件になる。空を失敗にすると、正しい実装が落ちる。
    """
    rel = f"solutions/industry/{pattern}/functions/discovery/handler.py"
    harness = load_pattern_handler(rel, monkeypatch, env={"SUFFIX_FILTER": SENTINEL})
    _SentinelS3Ap.queried_suffixes = []
    monkeypatch.setattr(harness.module, "S3ApHelper", _SentinelS3Ap)

    result = harness.handler({}, harness.context)

    # 照会側: サフィックスを指定して呼ぶなら、sentinel だけを照会しているはず
    explicit = [s for s in _SentinelS3Ap.queried_suffixes if s]
    if explicit:
        assert set(explicit) == {SENTINEL}, (
            f"{pattern}: SUFFIX_FILTER={SENTINEL} but the handler queried {sorted(set(explicit))}. "
            "It is most likely using its module constant instead of the environment variable."
        )

    # 結果側: 残ったキーに sentinel 以外が混ざっていないこと
    keys = [o["Key"] for o in result.get("objects", [])]
    unexpected = [k for k in keys if not k.endswith(SENTINEL)]
    assert not unexpected, (
        f"{pattern}: SUFFIX_FILTER={SENTINEL} but these keys came back: {unexpected}. "
        "The handler is most likely using its module constant instead of the environment variable."
    )

    # 少なくとも一方の経路で効果が観測できていること（両方空なら検証になっていない）
    assert explicit or keys, f"{pattern}: neither the queried suffixes nor the returned keys were observable"
