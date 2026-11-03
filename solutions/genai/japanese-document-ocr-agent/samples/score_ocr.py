#!/usr/bin/env python3
"""OCR の出力を正解テキストと文字単位で比べる。

比べ方:
    両方を NFKC で正規化し、空白を除いた文字列にする。そのうえで次の 2 つを出す。

    - `cer`: 編集距離 / 正解の文字数（文字誤り率。小さいほど良い。順序を見る）
    - `char_recall`: 正解の各文字が出力にも現れる割合（出現数ベース。順序は見ない）

    出現数ベースの値は、順序が入れ替わっても、他の文字が混ざっても下がらない。
    `cer` と合わせて読む。

    NFKC のため、全角と半角の違い（`１２３` と `123`）、丸数字（`①` と `1`）、
    `℃` と `°C` は同じ文字として扱われる。この違いは検出できない。

入力（どれか 1 つ）:
    --result   このパターンの `result.json`（`pages[].lines[].text`）
    --text     プレーンテキスト（`text.txt` など）
    --textract Textract の応答 JSON（`Blocks` の LINE を連結する）

Usage:
    python3 score_ocr.py ground-truth/invoice-ja-001.txt --result result.json
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any


def normalize(text: str) -> str:
    """NFKC で正規化し、空白をすべて除く。

    Args:
        text: 元の文字列。

    Returns:
        比較用の文字列。
    """
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))


def edit_distance(a: str, b: str) -> int:
    """2 つの文字列のレーベンシュタイン距離を返す。

    Args:
        a: 文字列。
        b: 文字列。

    Returns:
        挿入・削除・置換をそれぞれ 1 と数えた最小の操作回数。
    """
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def lines_from_result(document: dict[str, Any]) -> list[str]:
    """`result.json` の行テキストをページ順に返す。

    Args:
        document: `result.json` を読み込んだ辞書。

    Returns:
        ページ順・行順のテキスト。
    """
    return [line["text"] for page in document.get("pages", []) for line in page.get("lines", [])]


def lines_from_textract(response: dict[str, Any]) -> list[str]:
    """Textract の応答から LINE ブロックのテキストを返す。

    Args:
        response: `Blocks` を持つ応答（複数ページ分を連結した辞書でもよい）。

    Returns:
        応答内の順序のままの LINE テキスト。
    """
    return [b.get("Text", "") for b in response.get("Blocks", []) if b.get("BlockType") == "LINE"]


def score(truth_text: str, ocr_text: str) -> dict[str, Any]:
    """正解と OCR 出力を比べる。

    Args:
        truth_text: 正解テキスト。
        ocr_text: OCR の出力テキスト。

    Returns:
        `cer`、`char_recall`、文字数、編集距離、足りなかった文字・余分な文字の上位。
    """
    truth = normalize(truth_text)
    ocr = normalize(ocr_text)
    distance = edit_distance(truth, ocr)
    missing = Counter(truth) - Counter(ocr)
    extra = Counter(ocr) - Counter(truth)
    total = max(1, len(truth))
    return {
        "truth_chars": len(truth),
        "ocr_chars": len(ocr),
        "edit_distance": distance,
        "cer": round(distance / total, 4),
        "char_recall": round((len(truth) - sum(missing.values())) / total, 4),
        "missing_top": missing.most_common(8),
        "extra_top": extra.most_common(8),
    }


def main() -> None:
    """コマンドライン引数を読み、採点結果を JSON で標準出力に出す。"""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("truth", type=Path, help="正解テキスト（ground-truth/*.txt）")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--result", type=Path, help="このパターンの result.json")
    source.add_argument("--text", type=Path, help="プレーンテキスト")
    source.add_argument("--textract", type=Path, help="Textract の応答 JSON")
    args = parser.parse_args()

    truth_text = args.truth.read_text(encoding="utf-8")
    if args.result:
        ocr_text = "".join(lines_from_result(json.loads(args.result.read_text(encoding="utf-8"))))
    elif args.textract:
        ocr_text = "".join(lines_from_textract(json.loads(args.textract.read_text(encoding="utf-8"))))
    else:
        ocr_text = args.text.read_text(encoding="utf-8")
    print(json.dumps(score(truth_text, ocr_text), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
