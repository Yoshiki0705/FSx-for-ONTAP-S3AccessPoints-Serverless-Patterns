#!/usr/bin/env python3
"""架空の日本語文書（請求書・契約書・メモ）と正解データを生成する。

OCR の検証用に、内容を自分で決めた文書を作る。正解が既知なので、Textract の出力と
文字単位で比べられる（`score_ocr.py`）。

設計:
    文書の内容（ブロックのリスト）と描画（Pillow）を分けてある。正解テキストは内容
    だけから決まり、フォントや折り返し位置に依存しない。そのため、正解の整合は
    フォントが無い環境でもテストできる（`build_documents()` は Pillow を使わない）。

出力:
    PNG / JPEG / 画像のみの PDF（スキャン PDF と同じ形でテキスト層なし）と、
    `ground-truth/` 配下の正解テキスト・項目値。

内容:
    組織名・人名・番号はすべて架空（「甲野 一郎」「乙野 二郎」は契約書の例で使われる仮名）。
    個人情報と実在の識別子は含めない。日本語特有の誤読が出やすい文字を意図して入れる:
    「〜」「→」「へ」と「ヘ」、「弧」、「AI」、全角数字、丸数字、和暦、長音。

フォント:
    日本語フォントのファイルが要る。リポジトリには含めない。
    BIZ UD ゴシック（SIL Open Font License 1.1）の取得例:

        mkdir -p /tmp/ja-fonts && cd /tmp/ja-fonts
        curl -sSfLO https://raw.githubusercontent.com/google/fonts/main/ofl/bizudgothic/BIZUDGothic-Regular.ttf
        curl -sSfLO https://raw.githubusercontent.com/google/fonts/main/ofl/bizudgothic/BIZUDGothic-Bold.ttf

Usage:
    python3 generate_samples.py --font-dir /tmp/ja-fonts
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

DPI = 200
PAGE_W, PAGE_H = 1654, 2339  # A4 を 200 dpi で
MARGIN = 150
CONTENT_W = PAGE_W - 2 * MARGIN
# 本文は 200 dpi で約 11 pt（Textract が文字を検出できる高さの下限は 15 px）
BODY, SMALL, HEAD, TITLE = 30, 26, 40, 64


# ---------------------------------------------------------------------------
# 内容（Pillow に依存しない）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Line:
    """1 行。"""

    text: str
    size: int = BODY
    bold: bool = False
    align: str = "left"  # left / right / center
    gap: int = 20


@dataclass(frozen=True)
class Para:
    """幅に収まるよう折り返す段落。正解には折り返す前の 1 つの文字列として入る。"""

    text: str
    size: int = BODY
    gap: int = 16


@dataclass(frozen=True)
class Table:
    """罫線つきの表。2 列目以降の本文は右寄せ。"""

    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    widths: tuple[int, ...]
    size: int = BODY


@dataclass(frozen=True)
class Space:
    """縦方向の余白（px）。"""

    px: int


Block = Line | Para | Table | Space


@dataclass(frozen=True)
class Document:
    """1 つの文書。ページごとのブロックと、正解の項目値、スキャン風の劣化の設定を持つ。"""

    name: str
    suffix: str  # .png / .jpg / .pdf
    pages: tuple[tuple[Block, ...], ...]
    fields: dict[str, str] = field(default_factory=dict)
    scan: tuple[float, float, int] | None = None  # (傾き度, ぼかし半径, 粒状ノイズの深さ)。None はきれいな画像


def truth_lines(blocks: tuple[Block, ...] | list[Block]) -> list[str]:
    """ブロックから正解の行を作る。

    Args:
        blocks: 1 ページ分のブロック。

    Returns:
        描画順の正解テキスト。表は 1 行を空白で連結した 1 行にする。
    """
    lines: list[str] = []
    for block in blocks:
        if isinstance(block, (Line, Para)):
            lines.append(block.text)
        elif isinstance(block, Table):
            lines.append(" ".join(block.header))
            lines.extend(" ".join(row) for row in block.rows)
    return lines


def document_truth(document: Document) -> list[str]:
    """文書全体（全ページ）の正解の行を返す。

    Args:
        document: 対象の文書。

    Returns:
        ページ順に連結した正解テキストの行。
    """
    return [line for page in document.pages for line in truth_lines(page)]


def invoice_blocks(
    number: str,
    issued: str,
    client: str,
    items: list[tuple[str, int, int]],
    due: str,
    delivery: str,
    note: str,
) -> tuple[tuple[Block, ...], dict[str, str]]:
    """請求書 1 ページ分のブロックと項目値を作る。金額は品目から計算する。

    Args:
        number: 請求書番号。
        issued: 発行日（「2026年10月15日」の形）。
        client: 請求先の名称。
        items: (品名, 数量, 単価) のリスト。
        due: 支払期限。
        delivery: 納期。
        note: 備考の 1 行。

    Returns:
        (ブロック, 正解の項目値) のタプル。
    """
    subtotal = sum(quantity * price for _, quantity, price in items)
    tax = subtotal // 10
    total = subtotal + tax
    rows = tuple((name, f"{q:,}", f"¥{p:,}", f"¥{q * p:,}") for name, q, p in items)
    blocks: tuple[Block, ...] = (
        Line("請求書", TITLE, bold=True, align="center", gap=40),
        Line(f"請求書番号：{number}", align="right"),
        Line(f"発行日：{issued}", align="right", gap=30),
        Line(f"{client} 御中", HEAD, bold=True),
        Line("下記のとおりご請求申し上げます。", gap=30),
        Line("テスト工業株式会社", align="right", gap=8),
        Line("登録番号：T1234567890123", SMALL, align="right", gap=8),
        Line("東京都サンプル区サンプル町1-2-3", SMALL, align="right", gap=30),
        Line("件名：10月分 製造委託費"),
        Line(f"支払期限：{due}"),
        Line(f"納期：{delivery}", gap=30),
        Table(("品名", "数量", "単価", "金額"), rows, (600, 160, 280, 314)),
        Line(f"小計 ¥{subtotal:,}", align="right", gap=8),
        Line(f"消費税（10%） ¥{tax:,}", align="right", gap=8),
        Line(f"合計金額（税込） ¥{total:,}", HEAD, bold=True, align="right", gap=36),
        Line("振込先：サンプル銀行 本店 普通 1234567"),
        Line("検査：AI 外観検査装置による全数検査済み"),
        Line(note),
        Line("ご不明な点は担当者へご連絡ください。"),
    )
    fields = {
        "請求書番号": number,
        "発行日": issued,
        "請求先": client,
        "合計金額": f"¥{total:,}",
        "支払期限": due,
    }
    return blocks, fields


_ARTICLES = (
    ("第1条（目的）", "甲は乙に対し、別紙記載の業務（以下「本業務」という。）を委託し、乙はこれを受託する。"),
    ("第2条（委託料）", "甲は乙に対し、本業務の対価として月額金500,000円（消費税別）を支払う。"),
    (
        "第3条（支払条件）",
        "甲は、毎月末日までに当月分の委託料を、乙の指定する口座へ振り込む方法により支払う。振込手数料は甲の負担とする。",
    ),
    (
        "第4条（秘密保持）",
        "甲および乙は、本契約に関連して知り得た相手方の秘密情報を、相手方の事前の書面による承諾なく、"
        "第三者に開示または漏洩してはならない。",
    ),
    ("第5条（契約期間）", "本契約の有効期間は、令和8年11月1日から令和9年10月31日までとする。"),
    (
        "第6条（再委託）",
        "乙は、甲の事前の書面による承諾を得た場合に限り、本業務の一部を第三者に再委託することができる。",
    ),
    (
        "第7条（解除）",
        "甲または乙は、相手方が本契約に違反し、相当の期間を定めて催告したにもかかわらず是正されないときは、"
        "本契約を解除することができる。",
    ),
    (
        "第8条（反社会的勢力の排除）",
        "甲および乙は、自己が反社会的勢力に該当しないこと、および将来にわたって該当しないことを相互に確約する。",
    ),
    ("第9条（協議事項）", "本契約に定めのない事項または疑義が生じた事項は、甲乙誠意をもって協議のうえ解決する。"),
    ("第10条（管轄）", "本契約に関する紛争は、東京地方裁判所を第一審の専属的合意管轄裁判所とする。"),
)


def _article_blocks(articles: tuple[tuple[str, str], ...]) -> list[Block]:
    blocks: list[Block] = []
    for head, body in articles:
        blocks += [Line(head, HEAD, bold=True, gap=10), Para(body), Space(14)]
    return blocks


def contract_pages() -> tuple[tuple[Block, ...], ...]:
    """業務委託契約書の 3 ページ分のブロックを作る。

    Returns:
        ページごとのブロック。1 ページ目に第 1〜4 条、2 ページ目に第 5〜10 条、
        3 ページ目に結び・署名欄・別紙。
    """
    page1: list[Block] = [
        Line("業務委託契約書", TITLE, bold=True, align="center", gap=40),
        Para(
            "サンプル商事株式会社（以下「甲」という。）とテスト工業株式会社（以下「乙」という。）は、"
            "次のとおり業務委託契約を締結する。",
            gap=22,
        ),
        Space(20),
        *_article_blocks(_ARTICLES[:4]),
    ]
    page2: list[Block] = _article_blocks(_ARTICLES[4:])
    page3: list[Block] = [
        Para("本契約の成立を証するため、本書2通を作成し、甲乙記名押印のうえ各1通を保有する。"),
        Space(30),
        Line("令和8年11月1日", align="right", gap=40),
        Line("甲：サンプル商事株式会社", gap=8),
        Line("代表取締役 甲野 一郎", gap=36),
        Line("乙：テスト工業株式会社", gap=8),
        Line("代表取締役 乙野 二郎", gap=60),
        Line("別紙（業務内容）", HEAD, bold=True, gap=14),
        Line("(1) 製造工程の管理支援"),
        Line("(2) 品質データの集計および報告"),
        Line("(3) 前各号に付随する業務"),
    ]
    return (tuple(page1), tuple(page2), tuple(page3))


def memo_blocks() -> tuple[Block, ...]:
    """誤読が出やすい文字を集めたメモのブロックを作る。

    Returns:
        1 ページ分のブロック。
    """
    return (
        Line("業務メモ", TITLE, bold=True, align="center", gap=40),
        Line("温度範囲は 20〜30℃ とする。"),
        Line("手順：受付 → 検査 → 出荷"),
        Line("担当者へ連絡する。ヘッダーを確認する。"),
        Line("括弧（かっこ）内の数値を確認する。"),
        Line("AI による検査と OCR の結果を比較する。"),
        Line("金額：１２３，４５６円（全角数字）"),
        Line("手順番号：①②③"),
        Line("型番：Model-X200 / ABC-123-XYZ / 2026-11-03"),
        Line("区間：東京－大阪（全角ハイフン）、サーバー（長音）"),
        Line("連絡先：info@example.com"),
        Line("URL：https://example.com/docs"),
    )


def build_documents() -> list[Document]:
    """生成する文書の一覧を作る（Pillow もフォントも使わない）。

    Returns:
        請求書 2 枚（きれいな PNG とスキャン風の JPEG）、3 ページ PDF の契約書、メモ。
    """
    clean_blocks, clean_fields = invoice_blocks(
        "INV-2026-0001",
        "2026年10月15日",
        "サンプル商事株式会社",
        [
            ("部品A（精密加工）", 120, 1500),
            ("部品B（表面処理）", 80, 2250),
            ("検査費用", 1, 45000),
            ("運送費", 3, 12000),
        ],
        "2026年11月30日",
        "2026年10月1日〜10月10日",
        "備考：部品A → 組立ラインへ直送します。",
    )
    scan_blocks, scan_fields = invoice_blocks(
        "INV-2026-0002",
        "2026年10月20日",
        "架空物産株式会社",
        [("樹脂成形品C", 300, 480), ("金型保守", 2, 98000), ("梱包資材", 10, 3500)],
        "2026年12月15日",
        "2026年10月5日〜10月18日",
        "備考：梱包資材は別便にてお届けします。",
    )
    return [
        Document("invoice-ja-001", ".png", (clean_blocks,), clean_fields),
        Document("invoice-ja-002", ".jpg", (scan_blocks,), scan_fields, scan=(1.2, 0.8, 12)),
        Document("contract-ja-001", ".pdf", contract_pages(), scan=(0.4, 0.6, 8)),
        Document("memo-ja-001", ".png", (memo_blocks(),)),
    ]


# ---------------------------------------------------------------------------
# 描画（Pillow）
# ---------------------------------------------------------------------------


@dataclass
class Fonts:
    """サイズと太さごとにフォントを返す。"""

    regular: Path
    bold: Path
    _cache: dict = field(default_factory=dict, repr=False)

    def get(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        """指定したサイズのフォントを返す。

        Args:
            size: ピクセル単位のサイズ。
            bold: True なら太字。

        Returns:
            読み込み済みのフォント（同じ指定ならキャッシュを返す）。
        """
        key = (size, bold)
        if key not in self._cache:
            self._cache[key] = ImageFont.truetype(str(self.bold if bold else self.regular), size)
        return self._cache[key]


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """文字単位で折り返す（禁則処理はしない）。"""
    lines: list[str] = []
    current = ""
    for ch in text:
        if current and font.getlength(current + ch) > max_width:
            lines.append(current)
            current = ch
        else:
            current += ch
    if current:
        lines.append(current)
    return lines


def _line_height(size: int) -> int:
    return int(size * 1.25)


def _draw_line(draw: ImageDraw.ImageDraw, fonts: Fonts, line: Line, y: int) -> int:
    font = fonts.get(line.size, line.bold)
    width = font.getlength(line.text)
    if line.align == "right":
        x = PAGE_W - MARGIN - width
    elif line.align == "center":
        x = (PAGE_W - width) / 2
    else:
        x = MARGIN
    draw.text((x, y), line.text, font=font, fill=0)
    return y + _line_height(line.size) + line.gap


def _draw_table(draw: ImageDraw.ImageDraw, fonts: Fonts, table: Table, y: int) -> int:
    regular = fonts.get(table.size)
    bold = fonts.get(table.size, True)
    row_h = _line_height(table.size) + 26
    all_rows = [table.header, *table.rows]
    for r, cells in enumerate(all_rows):
        x = MARGIN
        for c, cell in enumerate(cells):
            font = bold if r == 0 else regular
            if c > 0 and r > 0:
                tx = x + table.widths[c] - 16 - font.getlength(cell)
            else:
                tx = x + 16
            draw.text((tx, y + r * row_h + 13), cell, font=font, fill=0)
            x += table.widths[c]
    total_w = sum(table.widths)
    bottom = y + len(all_rows) * row_h
    for r in range(len(all_rows) + 1):
        draw.line([(MARGIN, y + r * row_h), (MARGIN + total_w, y + r * row_h)], fill=0, width=2)
    x = MARGIN
    for w in (*table.widths, 0):
        draw.line([(x, y), (x, bottom)], fill=0, width=2)
        x += w
    return bottom + 24


def render_page(blocks: tuple[Block, ...], fonts: Fonts) -> Image.Image:
    """1 ページ分のブロックを白地のグレースケール画像に描く。

    Args:
        blocks: 描くブロック。
        fonts: フォント。

    Returns:
        A4・200 dpi のグレースケール画像。

    Raises:
        ValueError: 内容がページの下端を超える場合。
    """
    image = Image.new("L", (PAGE_W, PAGE_H), 255)
    draw = ImageDraw.Draw(image)
    y = MARGIN
    for block in blocks:
        if isinstance(block, Space):
            y += block.px
        elif isinstance(block, Line):
            y = _draw_line(draw, fonts, block, y)
        elif isinstance(block, Para):
            font = fonts.get(block.size)
            for text in _wrap(block.text, font, CONTENT_W):
                y = _draw_line(draw, fonts, Line(text, block.size, gap=block.gap), y)
        elif isinstance(block, Table):
            y = _draw_table(draw, fonts, block, y)
    if y > PAGE_H - MARGIN:
        raise ValueError(f"content overflows the page: y={y} > {PAGE_H - MARGIN}")
    return image


def degrade(page: Image.Image, angle: float, blur: float, grain_depth: int) -> Image.Image:
    """スキャン風の劣化（わずかな傾き・ぼかし・背景の粒状ノイズ）を加える。

    文字（黒）は変えず、背景の白だけをわずかに暗くする。

    Args:
        page: 元の画像（グレースケール）。
        angle: 傾き（度）。
        blur: ガウスぼかしの半径。
        grain_depth: 背景を暗くする最大の段階数（0〜255）。

    Returns:
        劣化後の画像。
    """
    rotated = page.rotate(angle, resample=Image.Resampling.BICUBIC, fillcolor=255)
    blurred = rotated.filter(ImageFilter.GaussianBlur(blur))
    noise = Image.effect_noise(blurred.size, 14)
    table = [255 - min(grain_depth, abs(v - 128) // 2) for v in range(256)]
    return ImageChops.multiply(blurred, noise.point(table))


def write_document(document: Document, fonts: Fonts, out: Path) -> Path:
    """文書を描いて保存し、正解テキストと項目値を `ground-truth/` に書く。

    Args:
        document: 対象の文書。
        fonts: フォント。
        out: 出力ディレクトリ。

    Returns:
        保存した画像（または PDF）のパス。
    """
    pages = [render_page(page, fonts) for page in document.pages]
    if document.scan is not None:
        pages = [degrade(p, *document.scan) for p in pages]
    path = out / f"{document.name}{document.suffix}"
    if document.suffix == ".pdf":
        pages[0].save(path, "PDF", resolution=float(DPI), save_all=True, append_images=pages[1:])
    elif document.suffix == ".jpg":
        pages[0].save(path, dpi=(DPI, DPI), quality=70)
    else:
        pages[0].save(path, dpi=(DPI, DPI), optimize=True)
    truth_dir = out / "ground-truth"
    truth_dir.mkdir(parents=True, exist_ok=True)
    (truth_dir / f"{document.name}.txt").write_text("\n".join(document_truth(document)) + "\n", encoding="utf-8")
    if document.fields:
        (truth_dir / f"{document.name}.json").write_text(
            json.dumps(document.fields, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return path


def main() -> None:
    """コマンドライン引数を読み、すべての文書を生成する。"""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--font-dir",
        type=Path,
        required=True,
        help="folder holding BIZUDGothic-Regular.ttf and BIZUDGothic-Bold.ttf (not in the repository; see the docstring)",
    )
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()

    regular = args.font_dir / "BIZUDGothic-Regular.ttf"
    bold = args.font_dir / "BIZUDGothic-Bold.ttf"
    for font_path in (regular, bold):
        if not font_path.exists():
            parser.error(f"font not found: {font_path} (see the module docstring for a download example)")
    args.out.mkdir(parents=True, exist_ok=True)
    fonts = Fonts(regular, bold)
    for document in build_documents():
        path = write_document(document, fonts, args.out)
        print(f"{path.name}: {path.stat().st_size:,} bytes, {len(document.pages)} page(s)")


if __name__ == "__main__":
    main()
