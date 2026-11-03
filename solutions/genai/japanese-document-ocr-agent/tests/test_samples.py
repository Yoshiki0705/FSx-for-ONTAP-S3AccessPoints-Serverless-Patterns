"""Tests for the synthetic sample documents and the OCR scorer.

The ground truth is derived from the document content alone, so these tests run
without fonts. Only the layout check needs a Japanese font and skips without one.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest
from helpers import SAMPLES_DIR, load_sample_module

gen = load_sample_module("generate_samples")
scorer = load_sample_module("score_ocr")

DOCUMENTS = gen.build_documents()
BY_NAME = {d.name: d for d in DOCUMENTS}
FONT_DIR = Path(os.environ.get("JA_FONT_DIR", "/tmp/ja-fonts"))
ROW = re.compile(r"^(?P<name>.+) (?P<qty>[\d,]+) ¥(?P<price>[\d,]+) ¥(?P<amount>[\d,]+)$")


def _yen(line: str) -> int:
    return int(line.rsplit("¥", 1)[1].replace(",", ""))


def test_document_names_are_unique():
    names = [d.name for d in DOCUMENTS]
    assert len(names) == len(set(names))


def test_contract_is_a_three_page_pdf():
    contract = BY_NAME["contract-ja-001"]
    assert contract.suffix == ".pdf"
    assert len(contract.pages) == 3


@pytest.mark.parametrize("name", [n for n in BY_NAME if n.startswith("invoice")])
def test_invoice_arithmetic_is_consistent(name):
    document = BY_NAME[name]
    lines = gen.document_truth(document)
    start = lines.index("品名 数量 単価 金額") + 1
    end = next(i for i, ln in enumerate(lines) if ln.startswith("小計"))
    amounts = []
    for line in lines[start:end]:
        match = ROW.match(line)
        assert match, line
        qty, price, amount = (int(match[k].replace(",", "")) for k in ("qty", "price", "amount"))
        assert qty * price == amount
        amounts.append(amount)
    subtotal = _yen(lines[end])
    tax = _yen(lines[end + 1])
    total = _yen(lines[end + 2])
    assert sum(amounts) == subtotal
    assert tax == subtotal // 10
    assert total == subtotal + tax
    assert document.fields["合計金額"] == f"¥{total:,}"


@pytest.mark.parametrize("name", list(BY_NAME))
def test_committed_ground_truth_matches_the_content(name):
    """Regenerating the samples must not silently change what the scorer compares against."""
    document = BY_NAME[name]
    expected = "\n".join(gen.document_truth(document)) + "\n"
    assert (SAMPLES_DIR / "ground-truth" / f"{name}.txt").read_text(encoding="utf-8") == expected
    fields_path = SAMPLES_DIR / "ground-truth" / f"{name}.json"
    if document.fields:
        assert json.loads(fields_path.read_text(encoding="utf-8")) == document.fields
    else:
        assert not fields_path.exists()


@pytest.mark.parametrize("name", list(BY_NAME))
def test_committed_sample_file_exists(name):
    assert (SAMPLES_DIR / f"{name}{BY_NAME[name].suffix}").stat().st_size > 0


def test_memo_keeps_the_characters_ocr_confuses():
    """These characters are in the samples on purpose; losing them weakens the measurement."""
    text = "".join(gen.document_truth(BY_NAME["memo-ja-001"]))
    for char in ("〜", "→", "へ", "ヘ", "弧", "AI", "１２３，４５６", "①"):
        assert char in text


@pytest.mark.parametrize("name", list(BY_NAME))
def test_ground_truth_has_no_real_looking_identifiers(name):
    text = "\n".join(gen.document_truth(BY_NAME[name]))
    assert not re.search(r"(?<!\d)\d{12}(?!\d)", text), "12-digit run looks like an account ID"
    assert not re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", text), "dotted quad looks like an IP address"
    assert not re.search(r"[\w.+-]+@(?!example\.com\b)[\w.-]+", text), "email outside example.com"


@pytest.mark.skipif(
    not (FONT_DIR / "BIZUDGothic-Regular.ttf").exists(),
    reason=f"Japanese font not found in {FONT_DIR} (see generate_samples.py for a download example)",
)
@pytest.mark.parametrize("name", list(BY_NAME))
def test_every_page_fits_inside_the_margins(name):
    fonts = gen.Fonts(FONT_DIR / "BIZUDGothic-Regular.ttf", FONT_DIR / "BIZUDGothic-Bold.ttf")
    for page in BY_NAME[name].pages:
        image = gen.render_page(page, fonts)  # raises ValueError on overflow
        left, top, right, bottom = image.point(lambda v: 255 if v < 200 else 0).getbbox()
        assert left >= gen.MARGIN - 4
        assert right <= gen.PAGE_W - gen.MARGIN + 4
        assert top >= gen.MARGIN - 4
        assert bottom <= gen.PAGE_H - gen.MARGIN


class TestScorer:
    def test_identical_text_scores_perfectly(self):
        result = scorer.score("請求書\n合計 ¥100", "請求書合計¥100")
        assert result["cer"] == 0.0
        assert result["char_recall"] == 1.0

    def test_one_substitution_is_reported_in_both_lists(self):
        result = scorer.score("担当者へ連絡", "担当者ヘ連絡")
        assert result["edit_distance"] == 1
        assert result["missing_top"] == [["へ", 1]] or result["missing_top"] == [("へ", 1)]
        assert result["extra_top"] == [["ヘ", 1]] or result["extra_top"] == [("ヘ", 1)]

    def test_width_and_whitespace_differences_are_ignored(self):
        assert scorer.score("金額 １２３，４５６円", "金額123,456円")["cer"] == 0.0

    def test_empty_truth_does_not_divide_by_zero(self):
        assert scorer.score("", "abc")["cer"] == 3.0

    def test_edit_distance_known_values_and_symmetry(self):
        assert scorer.edit_distance("kitten", "sitting") == 3
        assert scorer.edit_distance("sitting", "kitten") == 3
        assert scorer.edit_distance("", "abc") == 3
        assert scorer.edit_distance("abc", "abc") == 0

    def test_reads_result_json_pages_in_order(self):
        document = {"pages": [{"lines": [{"text": "a"}, {"text": "b"}]}, {"lines": [{"text": "c"}]}]}
        assert scorer.lines_from_result(document) == ["a", "b", "c"]

    def test_reads_only_line_blocks_from_a_textract_response(self):
        response = {
            "Blocks": [
                {"BlockType": "PAGE"},
                {"BlockType": "LINE", "Text": "請求書"},
                {"BlockType": "WORD", "Text": "請求書"},
            ]
        }
        assert scorer.lines_from_textract(response) == ["請求書"]
