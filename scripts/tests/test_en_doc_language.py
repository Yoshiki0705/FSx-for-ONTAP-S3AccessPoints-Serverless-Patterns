"""Tests for the English-documentation language check.

96 lines of Japanese were sitting in 37 `.en.md` files, 24 of them the identical
`# 前提: AWS SAM CLI ...` comment copied into every pattern's demo guide. A missed
translation leaves no trace: the file renders, the links resolve, and only a reader
who does not read Japanese notices.

The risk in a check like this is the other direction. Some Japanese in an English
document is correct — a statute is a proper noun, the language switcher is bilingual
by design — and a check that flags those gets an allowlist widened until it flags
nothing. So the cases below pin both directions: what must be caught, and what must
not be, with each exemption tied to the reason it exists.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import check_en_doc_language as checker  # noqa: E402

ANY_FILE = "docs/some-doc.en.md"


class TestMustBeCaught:
    @pytest.mark.parametrize(
        "line",
        [
            "# 前提: AWS SAM CLI が必要です。",
            "# 1. リポジトリをクローン",
            "→ cfn-lint (テンプレート構文)",
            "この多層防御で破壊的変更の大半を検知できる。",
            "// ❌ 動作しない（authMode 未指定）",
            "S3 AP GetObject (Office ファイル取得)",
            "- ONTAP REST API レスポンス (該当する場合)",
        ],
    )
    def test_untranslated_prose_and_comments(self, line: str) -> None:
        assert not checker.is_allowed(ANY_FILE, line)

    def test_a_japanese_anchor_in_an_unlisted_file(self) -> None:
        """The anchor exemption is per file, so a new file with one still fails."""
        line = "See the [Troubleshooting Guide](../docs/guides/troubleshooting-guide.md#1-accessdenied-エラー)."
        assert not checker.is_allowed("solutions/industry/brand-new/README.en.md", line)

    def test_a_new_anchor_in_a_listed_file(self) -> None:
        """Listing a file exempts the enumerated link, not every Japanese anchor in it."""
        line = "See [another guide](../docs/guides/some-other-guide.md#日本語の見出し)."
        assert not checker.is_allowed("solutions/industry/media-vfx/README.en.md", line)


class TestMustNotBeCaught:
    def test_the_language_switcher(self) -> None:
        line = "🌐 **Language / 言語**: [日本語](guide.md) | [English](guide.en.md)"
        assert checker.is_allowed(ANY_FILE, line)

    def test_an_eight_locale_switcher(self) -> None:
        line = (
            "🌐 **Language**: [日本語](d.md) | English | [한국어](d.ko.md) | "
            "[简体中文](d.zh-CN.md) | [繁體中文](d.zh-TW.md)"
        )
        assert checker.is_allowed(ANY_FILE, line)

    def test_a_link_that_says_it_goes_to_japanese(self) -> None:
        line = "See the [Japanese version](./gaps.md#aws-support-提出用テキスト) for the full text."
        assert checker.is_allowed(ANY_FILE, line)

    @pytest.mark.parametrize(
        "line",
        [
            "> **Related Regulations**: 景品表示法 (Act against Unjustifiable Premiums)",
            "> **Related Regulations**: 化学物質管理促進法 (PRTR Act), 労働安全衛生法 (Industrial Safety Act)",
            "> **Related Regulations**: Electricity Business Act (電気事業法)",
            "> **Related Regulations**: 宅地建物取引業法 (Real Estate Brokerage Act)",
        ],
    )
    def test_a_statute_paired_with_its_english_gloss(self, line: str) -> None:
        """A statute is a proper noun. Either order reads correctly; both are allowed."""
        assert checker.is_allowed(ANY_FILE, line)

    def test_the_bilingual_industry_table(self) -> None:
        line = "| 1 | Advertising & Marketing | 広告・マーケティング | UC19 | Covered | 2026-06-02 |"
        assert checker.is_allowed("docs/industry-coverage-map.en.md", line)

    def test_the_same_table_row_elsewhere_is_still_caught(self) -> None:
        """The exemption is scoped to the file whose column is deliberately bilingual."""
        line = "| 1 | Advertising & Marketing | 広告・マーケティング | UC19 | Covered | 2026-06-02 |"
        assert not checker.is_allowed("docs/pattern-selection-guide.en.md", line)

    def test_a_japanese_filename_in_a_utf8_example(self) -> None:
        assert checker.is_allowed("docs/design-considerations-en.md", '"レポート_2026年07月.pdf"')

    def test_a_changelog_quoting_a_japanese_ui_string(self) -> None:
        line = '| 2026-07-26 | UX fix | Replace "本当に削除しますか: X?" with a natural phrasing | ja.ts |'
        assert checker.is_allowed("solutions/amplify-portal/docs/IMPLEMENTATION.en.md", line)

    def test_prose_in_that_changelog_file_is_still_caught(self) -> None:
        """Only the table rows are exempt, not the whole file."""
        assert not checker.is_allowed("solutions/amplify-portal/docs/IMPLEMENTATION.en.md", "この節は未翻訳です。")

    @pytest.mark.parametrize(
        ("path", "needle"),
        [
            ("solutions/industry/media-vfx/README.en.md", "troubleshooting-guide.md#1-accessdenied-エラー"),
            ("docs/pattern-selection-guide.en.md", "dais2026-agent-bricks-industry-cases.md#2-astrazeneca-マルチ"),
        ],
    )
    def test_enumerated_anchor_debt(self, path: str, needle: str) -> None:
        assert checker.is_allowed(path, f"See [the guide]({needle}).")


class TestRealRepository:
    def test_no_english_document_carries_untranslated_japanese(self) -> None:
        """Runs the check as `make drift` does, against the repository as it stands."""
        assert checker.main() == 0

    def test_the_allowlist_does_not_name_files_that_no_longer_exist(self) -> None:
        """A stale entry silently exempts nothing and hides that the debt was paid."""
        for group in (checker.ALLOWED_ANCHORS, checker.BY_DESIGN_FILES):
            for relative in group:
                assert (checker.ROOT / relative).is_file(), f"{relative} は存在しない"

    def test_every_enumerated_anchor_is_still_present(self) -> None:
        """When a link is fixed, its entry must go — otherwise the list only grows."""
        for relative, needles in checker.ALLOWED_ANCHORS.items():
            text = (checker.ROOT / relative).read_text(encoding="utf-8")
            for needle in needles:
                assert needle in text, f"{relative}: {needle} は既に無い。許可リストから削除できる"

    def test_the_check_finds_documents_to_check(self) -> None:
        """A glob that matches nothing would make every assertion above vacuous."""
        assert len(checker.english_docs()) > 100
