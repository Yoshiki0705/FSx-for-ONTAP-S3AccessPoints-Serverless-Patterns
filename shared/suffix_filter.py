"""`SUFFIX_FILTER` 環境変数を検出対象の拡張子に変換する

## なぜ共通化するか

複数のパターンが「対象拡張子をモジュール定数で持ち、テンプレートにも
`SUFFIX_FILTER` を宣言しているが、ハンドラは環境変数を読まない」状態になっていた。
テンプレートに見えるノブを編集しても何も起きないため、設定ミスを誘発する。

配線するにあたり、値の正規化はどのパターンでも同じ判断が要る。運用者が手で編集する
値なので、ドットの有無・大文字・空白のいずれかで無言の不一致が起きると、原因の
分かりにくい取りこぼしになる。各パターンで少しずつ違う正規化が生えるのを避けるため、
ここに集約する。

## 使い方

    from shared.suffix_filter import allowed_suffixes

    DOCUMENT_SUFFIXES = (".pdf", ".tiff", ".tif", ".jpeg", ".jpg")
    ...
    suffixes = allowed_suffixes(DOCUMENT_SUFFIXES)
"""

from __future__ import annotations

import os
from collections.abc import Iterable

__all__ = ["allowed_suffixes", "parse_suffix_filter"]


def parse_suffix_filter(raw: str) -> tuple[str, ...]:
    """カンマ区切りの拡張子指定をタプルに正規化する

    次を吸収する。いずれも運用者が実際に書く形で、放置すると無言の不一致になる:

    | 書かれた値 | 解釈 |
    |---|---|
    | `exr` | `.exr` |
    | `.EXR` | `.exr` |
    | ` .exr ` | `.exr` |
    | `.exr,` / `,.exr` | `.exr` |
    | `.exr,.exr` | `.exr`（重複排除） |

    ドットを補うのは表記揃えではない。`endswith("exr")` は `render_latestexr` にも
    一致するため、ドットが無いと拡張子ではない名前まで対象になる。

    Args:
        raw: `SUFFIX_FILTER` の生の値

    Returns:
        tuple[str, ...]: 正規化した拡張子。有効な項目が無ければ空タプル
    """
    suffixes: list[str] = []
    for token in raw.split(","):
        suffix = token.strip().lower()
        if not suffix:
            continue
        if not suffix.startswith("."):
            suffix = f".{suffix}"
        if suffix not in suffixes:
            suffixes.append(suffix)
    return tuple(suffixes)


def allowed_suffixes(
    default: Iterable[str],
    env_var: str = "SUFFIX_FILTER",
    environ: dict[str, str] | None = None,
) -> tuple[str, ...]:
    """検出対象の拡張子を決める

    環境変数が設定されていればそれを使い、未設定または実質空なら `default` を使う。

    フォールバックを残すのは、環境変数の欠落や打ち間違いで空になったときに
    「1 件も検出せず成功を返す」状態にしないため。対象を絞りたい場合は環境変数に
    明示的に列挙する。

    Args:
        default: 環境変数が無いときに使う拡張子
        env_var: 参照する環境変数名
        environ: 環境変数の辞書（省略時は `os.environ`）

    Returns:
        tuple[str, ...]: 検出対象の拡張子
    """
    source = os.environ if environ is None else environ
    configured = parse_suffix_filter(source.get(env_var, ""))
    return configured or tuple(default)
