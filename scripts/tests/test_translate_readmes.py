"""Comprehensive tests for translate_readmes.py.

Includes property-based tests (Hypothesis) and unit tests (pytest + mock)
for the Translation System components.

Test coverage:
- Property 1: Language Switcher placement after H1
- Property 2: Current language is plain text in switcher
- Property 3: Document structure invariant across translation
- Property 4: Untranslatable content preservation
- Property 5: Hyperlink target preservation
- Property 6: Content preservation on switcher injection
- Unit tests: ReadmeGenerator orchestrator
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from translate_readmes import (
    BlockType,
    ContentBlock,
    LanguageSwitcherInjector,
    MarkdownTranslator,
    ReadmeGenerator,
    TranslationConfig,
    TranslationResult,
)


# =============================================================================
# Hypothesis Strategies
# =============================================================================

def markdown_word():
    """Generate a single markdown-safe word."""
    return st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N"),
            whitelist_characters="_-",
        ),
        min_size=1,
        max_size=20,
    )


def markdown_line():
    """Generate a single line of markdown text (no newlines)."""
    return st.text(
        alphabet=st.characters(
            blacklist_characters="\n\r\x00",
            blacklist_categories=("Cs",),
        ),
        min_size=0,
        max_size=100,
    )


def h1_heading():
    """Generate a valid H1 heading line."""
    return st.builds(
        lambda title: f"# {title}",
        st.text(
            alphabet=st.characters(
                blacklist_characters="\n\r\x00",
                blacklist_categories=("Cs",),
            ),
            min_size=1,
            max_size=50,
        ),
    )


def markdown_with_h1():
    """Generate markdown content that contains at least one H1 heading."""
    return st.builds(
        lambda before, h1, after: "\n".join(
            [line for line in before if line.strip() != ""]
            + [h1]
            + list(after)
        ),
        st.lists(markdown_line(), min_size=0, max_size=3),
        h1_heading(),
        st.lists(markdown_line(), min_size=0, max_size=5),
    )


def code_block():
    """Generate a fenced code block."""
    return st.builds(
        lambda lang, body: f"```{lang}\n{body}\n```",
        st.sampled_from(["python", "bash", "typescript", "json", ""]),
        st.text(
            alphabet=st.characters(
                blacklist_characters="\x00",
                blacklist_categories=("Cs",),
            ),
            min_size=1,
            max_size=80,
        ).filter(lambda s: "```" not in s),
    )


def mermaid_block():
    """Generate a mermaid diagram block."""
    return st.builds(
        lambda body: f"```mermaid\n{body}\n```",
        st.text(
            alphabet=st.characters(
                blacklist_characters="\x00`",
                blacklist_categories=("Cs",),
            ),
            min_size=5,
            max_size=80,
        ),
    )


def table_block():
    """Generate a markdown table."""
    return st.builds(
        lambda cols, rows: "\n".join(
            [
                "| " + " | ".join(f"Col{i}" for i in range(cols)) + " |",
                "| " + " | ".join("---" for _ in range(cols)) + " |",
            ]
            + [
                "| " + " | ".join(f"r{r}c{c}" for c in range(cols)) + " |"
                for r in range(rows)
            ]
        ),
        st.integers(min_value=2, max_value=4),
        st.integers(min_value=1, max_value=3),
    )


def markdown_with_structure():
    """Generate markdown with mixed structural elements."""
    elements = st.one_of(
        st.builds(lambda t: f"# {t}", markdown_word()),
        st.builds(lambda t: f"## {t}", markdown_word()),
        st.builds(lambda t: f"### {t}", markdown_word()),
        code_block(),
        mermaid_block(),
        table_block(),
        st.builds(
            lambda words: " ".join(words),
            st.lists(markdown_word(), min_size=1, max_size=10),
        ),
        st.just(""),
    )
    return st.builds(
        lambda parts: "\n".join(parts),
        st.lists(elements, min_size=2, max_size=8),
    )


def markdown_with_links():
    """Generate markdown containing hyperlinks."""
    link = st.builds(
        lambda text, target: f"[{text}]({target})",
        markdown_word(),
        st.one_of(
            st.builds(lambda p: f"https://example.com/{p}", markdown_word()),
            st.builds(lambda p: f"./{p}.md", markdown_word()),
            st.builds(lambda p: f"../docs/{p}", markdown_word()),
        ),
    )
    prose_with_links = st.builds(
        lambda before, lnk, after: f"{before} {lnk} {after}",
        st.text(
            alphabet=st.characters(
                blacklist_characters="\n\r\x00[]()`,",
                blacklist_categories=("Cs",),
            ),
            min_size=1,
            max_size=30,
        ),
        link,
        st.text(
            alphabet=st.characters(
                blacklist_characters="\n\r\x00[]()`,",
                blacklist_categories=("Cs",),
            ),
            min_size=0,
            max_size=30,
        ),
    )
    return st.builds(
        lambda lines: "\n".join(lines),
        st.lists(prose_with_links, min_size=1, max_size=5),
    )


ALL_LANG_CODES = ["ja", "en", "ko", "zh-CN", "zh-TW", "fr", "de", "es"]


# =============================================================================
# Property 1: Language Switcher placement after H1
# Feature: uc-multilingual-readme-and-eda-demo, Property 1: Language Switcher placement after H1
# Validates: Requirements 1.2, 2.2
# =============================================================================


class TestProperty1SwitcherPlacementAfterH1:
    """Property 1: Language Switcher placement after H1.

    For any valid Markdown string containing an H1 heading, after Language
    Switcher injection, the switcher line (starting with 🌐) SHALL appear on
    the first non-empty line immediately following the H1 heading line.

    **Validates: Requirements 1.2, 2.2**
    """

    @given(content=markdown_with_h1(), lang=st.sampled_from(ALL_LANG_CODES))
    @settings(max_examples=100)
    def test_switcher_appears_after_h1(self, content: str, lang: str):
        """After injection, switcher is on the first non-empty line after H1."""
        injector = LanguageSwitcherInjector()
        result = injector.inject_into_markdown(content, lang)
        lines = result.split("\n")

        # Find H1 line
        h1_index = None
        for i, line in enumerate(lines):
            if line.startswith("# "):
                h1_index = i
                break

        assert h1_index is not None, "H1 heading must exist in output"

        # Find first non-empty line after H1
        switcher_found = False
        for i in range(h1_index + 1, len(lines)):
            if lines[i].strip() != "":
                assert lines[i].strip().startswith("🌐"), (
                    f"First non-empty line after H1 should be switcher, "
                    f"got: {lines[i]!r}"
                )
                switcher_found = True
                break

        assert switcher_found, "Switcher line must exist after H1"


# =============================================================================
# Property 2: Current language is plain text in switcher
# Feature: uc-multilingual-readme-and-eda-demo, Property 2: Current language is plain text in switcher
# Validates: Requirements 2.3
# =============================================================================


class TestProperty2CurrentLanguagePlainText:
    """Property 2: Current language is plain text in switcher.

    For any valid language code from the set {ja, en, ko, zh-CN, zh-TW, fr,
    de, es}, the generated Language Switcher SHALL contain exactly 7 markdown
    links and exactly 1 plain-text label corresponding to the current language.

    **Validates: Requirements 2.3**
    """

    @given(lang=st.sampled_from(ALL_LANG_CODES))
    @settings(max_examples=100)
    def test_switcher_has_7_links_and_1_plain_text(self, lang: str):
        """Generated switcher has exactly 7 links and 1 plain text label."""
        injector = LanguageSwitcherInjector()
        switcher = injector.generate_switcher(lang)

        # Count markdown links [text](url)
        links = re.findall(r"\[([^\]]+)\]\([^)]+\)", switcher)
        assert len(links) == 7, (
            f"Expected 7 links for lang={lang}, got {len(links)}: {links}"
        )

        # Verify current language label is NOT a link
        current_label = injector.LANG_LABELS[lang]
        # The current label should appear as plain text (not inside [...](...)
        # Check it appears in the switcher but not as a link
        assert current_label in switcher, (
            f"Current language label '{current_label}' not found in switcher"
        )

        # Verify it's not wrapped in a link
        link_pattern = re.compile(
            r"\[" + re.escape(current_label) + r"\]\([^)]+\)"
        )
        assert not link_pattern.search(switcher), (
            f"Current language '{current_label}' should be plain text, "
            f"not a link"
        )


# =============================================================================
# Property 6: Content preservation on switcher injection
# Feature: uc-multilingual-readme-and-eda-demo, Property 6: Content preservation on switcher injection
# Validates: Requirements 3.2
# =============================================================================


class TestProperty6ContentPreservation:
    """Property 6: Content preservation on switcher injection.

    For any existing README content (with or without a pre-existing Language
    Switcher), after switcher injection, all original content lines excluding
    the old switcher line SHALL be preserved in the output in their original
    order.

    **Validates: Requirements 3.2**
    """

    @given(content=markdown_with_h1(), lang=st.sampled_from(ALL_LANG_CODES))
    @settings(max_examples=100)
    def test_original_content_preserved_after_injection(
        self, content: str, lang: str
    ):
        """All original non-switcher lines are preserved after injection."""
        injector = LanguageSwitcherInjector()
        result = injector.inject_into_markdown(content, lang)

        # Get original lines excluding any existing switcher
        original_lines = [
            line
            for line in content.split("\n")
            if not line.strip().startswith("🌐")
        ]

        # Get result lines excluding the new switcher
        result_lines = [
            line
            for line in result.split("\n")
            if not line.strip().startswith("🌐")
        ]

        # All original non-empty lines should appear in result (order preserved)
        original_non_empty = [l for l in original_lines if l.strip()]
        result_non_empty = [l for l in result_lines if l.strip()]

        # Check that all original non-empty lines are present in result
        orig_idx = 0
        for res_line in result_non_empty:
            if orig_idx < len(original_non_empty):
                if res_line == original_non_empty[orig_idx]:
                    orig_idx += 1

        assert orig_idx == len(original_non_empty), (
            f"Not all original lines preserved. "
            f"Found {orig_idx}/{len(original_non_empty)} lines."
        )

    @given(
        content=markdown_with_h1(),
        lang1=st.sampled_from(ALL_LANG_CODES),
        lang2=st.sampled_from(ALL_LANG_CODES),
    )
    @settings(max_examples=100)
    def test_double_injection_preserves_content(
        self, content: str, lang1: str, lang2: str
    ):
        """Injecting twice (simulating existing switcher) preserves content."""
        injector = LanguageSwitcherInjector()

        # First injection
        result1 = injector.inject_into_markdown(content, lang1)
        # Second injection (replaces existing switcher)
        result2 = injector.inject_into_markdown(result1, lang2)

        # Original non-switcher content should still be present
        original_lines = [
            line
            for line in content.split("\n")
            if not line.strip().startswith("🌐")
        ]
        result_lines = [
            line
            for line in result2.split("\n")
            if not line.strip().startswith("🌐")
        ]

        original_non_empty = [l for l in original_lines if l.strip()]
        result_non_empty = [l for l in result_lines if l.strip()]

        orig_idx = 0
        for res_line in result_non_empty:
            if orig_idx < len(original_non_empty):
                if res_line == original_non_empty[orig_idx]:
                    orig_idx += 1

        assert orig_idx == len(original_non_empty), (
            f"Double injection lost content. "
            f"Found {orig_idx}/{len(original_non_empty)} lines."
        )


# =============================================================================
# Property 3: Document structure invariant across translation
# Feature: uc-multilingual-readme-and-eda-demo, Property 3: Document structure invariant across translation
# Validates: Requirements 1.3, 7.3
# =============================================================================


class TestProperty3DocumentStructureInvariant:
    """Property 3: Document structure invariant across translation.

    For any Markdown document, after split → reassemble round-trip, the output
    SHALL preserve: (a) the same number of headings, (b) the same number of
    fenced code blocks, (c) the same number of Mermaid diagram blocks, and
    (d) the same number of table rows.

    **Validates: Requirements 1.3, 7.3**
    """

    @given(content=markdown_with_structure())
    @settings(max_examples=100)
    def test_split_reassemble_preserves_structure(self, content: str):
        """Split → reassemble round-trip preserves structural counts."""
        translator = MarkdownTranslator.__new__(MarkdownTranslator)
        # Don't call __init__ to avoid boto3 client creation
        translator.bedrock_model_id = "test"

        blocks = translator.split_translatable(content)
        reassembled = translator.reassemble(blocks)

        # Count headings
        original_headings = len(
            re.findall(r"^#{1,6}\s", content, re.MULTILINE)
        )
        result_headings = len(
            re.findall(r"^#{1,6}\s", reassembled, re.MULTILINE)
        )
        assert original_headings == result_headings, (
            f"Heading count mismatch: {original_headings} vs {result_headings}"
        )

        # Count code blocks (``` fences)
        original_code = content.count("```")
        result_code = reassembled.count("```")
        assert original_code == result_code, (
            f"Code fence count mismatch: {original_code} vs {result_code}"
        )

        # Count mermaid blocks
        original_mermaid = len(
            re.findall(r"^```mermaid", content, re.MULTILINE | re.IGNORECASE)
        )
        result_mermaid = len(
            re.findall(r"^```mermaid", reassembled, re.MULTILINE | re.IGNORECASE)
        )
        assert original_mermaid == result_mermaid, (
            f"Mermaid count mismatch: {original_mermaid} vs {result_mermaid}"
        )

        # Count table rows (lines starting with |)
        original_table_rows = len(
            re.findall(r"^\|", content, re.MULTILINE)
        )
        result_table_rows = len(
            re.findall(r"^\|", reassembled, re.MULTILINE)
        )
        assert original_table_rows == result_table_rows, (
            f"Table row count mismatch: "
            f"{original_table_rows} vs {result_table_rows}"
        )


# =============================================================================
# Property 4: Untranslatable content preservation
# Feature: uc-multilingual-readme-and-eda-demo, Property 4: Untranslatable content preservation
# Validates: Requirements 1.4, 3.3, 7.2
# =============================================================================


class TestProperty4UntranslatableContentPreservation:
    """Property 4: Untranslatable content preservation.

    For any Markdown document containing fenced code blocks, inline code,
    AWS service names, after split → reassemble those elements SHALL appear
    byte-for-byte identical in the output.

    **Validates: Requirements 1.4, 3.3, 7.2**
    """

    @given(
        code_content=st.text(
            alphabet=st.characters(
                blacklist_characters="\x00`",
                blacklist_categories=("Cs",),
            ),
            min_size=1,
            max_size=50,
        ).filter(lambda s: "\n" not in s),
        lang_tag=st.sampled_from(["python", "bash", "json", ""]),
    )
    @settings(max_examples=100)
    def test_code_blocks_preserved(self, code_content: str, lang_tag: str):
        """Code blocks are preserved byte-for-byte after split → reassemble."""
        code_block_str = f"```{lang_tag}\n{code_content}\n```"
        markdown = f"# Title\n\nSome text before.\n\n{code_block_str}\n\nSome text after."

        translator = MarkdownTranslator.__new__(MarkdownTranslator)
        translator.bedrock_model_id = "test"

        blocks = translator.split_translatable(markdown)
        reassembled = translator.reassemble(blocks)

        assert code_block_str in reassembled, (
            f"Code block not preserved.\n"
            f"Expected: {code_block_str!r}\n"
            f"In result: {reassembled!r}"
        )

    @given(
        aws_service=st.sampled_from([
            "Amazon Bedrock",
            "AWS Step Functions",
            "Amazon Athena",
            "Amazon S3",
            "AWS Lambda",
            "Amazon FSx for NetApp ONTAP",
            "Amazon CloudWatch",
            "AWS CloudFormation",
        ]),
    )
    @settings(max_examples=100)
    def test_aws_service_names_in_code_preserved(self, aws_service: str):
        """AWS service names inside code blocks are preserved."""
        code_block_str = f"```bash\naws {aws_service.lower()} describe\n```"
        markdown = f"# Title\n\n{code_block_str}\n\nEnd."

        translator = MarkdownTranslator.__new__(MarkdownTranslator)
        translator.bedrock_model_id = "test"

        blocks = translator.split_translatable(markdown)
        reassembled = translator.reassemble(blocks)

        assert code_block_str in reassembled, (
            f"Code block with AWS service name not preserved"
        )

    @given(content=mermaid_block())
    @settings(max_examples=100)
    def test_mermaid_blocks_preserved(self, content: str):
        """Mermaid diagram blocks are preserved byte-for-byte."""
        markdown = f"# Architecture\n\n{content}\n\nEnd."

        translator = MarkdownTranslator.__new__(MarkdownTranslator)
        translator.bedrock_model_id = "test"

        blocks = translator.split_translatable(markdown)
        reassembled = translator.reassemble(blocks)

        assert content in reassembled, "Mermaid block not preserved"


# =============================================================================
# Property 5: Hyperlink target preservation
# Feature: uc-multilingual-readme-and-eda-demo, Property 5: Hyperlink target preservation
# Validates: Requirements 7.4
# =============================================================================


class TestProperty5HyperlinkTargetPreservation:
    """Property 5: Hyperlink target preservation.

    For any Markdown document containing hyperlinks, after split → reassemble
    all link targets (URLs and relative paths) SHALL remain unchanged.

    **Validates: Requirements 7.4**
    """

    @given(content=markdown_with_links())
    @settings(max_examples=100)
    def test_link_targets_preserved(self, content: str):
        """Markdown link targets are unchanged after split → reassemble."""
        translator = MarkdownTranslator.__new__(MarkdownTranslator)
        translator.bedrock_model_id = "test"

        # Extract original link targets
        original_targets = re.findall(r"\[([^\]]*)\]\(([^)]+)\)", content)

        blocks = translator.split_translatable(content)
        reassembled = translator.reassemble(blocks)

        # Extract result link targets
        result_targets = re.findall(r"\[([^\]]*)\]\(([^)]+)\)", reassembled)

        # All original link targets should be present
        original_urls = sorted([t[1] for t in original_targets])
        result_urls = sorted([t[1] for t in result_targets])

        assert original_urls == result_urls, (
            f"Link targets changed.\n"
            f"Original: {original_urls}\n"
            f"Result: {result_urls}"
        )


# =============================================================================
# Unit Tests: ReadmeGenerator
# Task 6.3: Unit tests for ReadmeGenerator
# Validates: Requirements 1.1, 1.5, 3.2
# =============================================================================


class TestReadmeGeneratorUnit:
    """Unit tests for ReadmeGenerator orchestrator.

    Tests generate_for_folder with mock Bedrock, existing file switcher
    update, and error handling/skip behavior.
    """

    def _create_generator(self, tmp_path: Path) -> ReadmeGenerator:
        """Create a ReadmeGenerator with mocked Bedrock client."""
        config = TranslationConfig()
        config.uc_folders = ["test-uc"]

        with patch("translate_readmes.boto3.client") as mock_boto:
            generator = ReadmeGenerator(
                config=config, project_root=str(tmp_path)
            )

        # Mock the translator's bedrock_client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"content": [{"text": "Translated text"}]}'
        mock_response.__getitem__ = lambda self, key: mock_response
        mock_client.invoke_model.return_value = {"body": mock_response}
        mock_client.exceptions = MagicMock()
        mock_client.exceptions.ThrottlingException = Exception
        generator.translator.bedrock_client = mock_client

        return generator

    def test_generate_for_folder_creates_files(self, tmp_path: Path):
        """generate_for_folder creates translated README files."""
        # Setup: create UC folder with source README
        uc_folder = tmp_path / "test-uc"
        uc_folder.mkdir()
        source_readme = uc_folder / "README.md"
        source_readme.write_text(
            "# テストプロジェクト\n\nこれはテストです。\n",
            encoding="utf-8",
        )

        generator = self._create_generator(tmp_path)
        results = generator.generate_for_folder("test-uc")

        # Should generate 7 language files
        assert len(results) == 7
        assert all(r.success for r in results)

        # Check files were created
        for lang in ["en", "ko", "zh-CN", "zh-TW", "fr", "de", "es"]:
            filename = LanguageSwitcherInjector.LANG_FILES[lang]
            filepath = uc_folder / filename
            assert filepath.exists(), f"File not created: {filepath}"

    def test_generate_for_folder_updates_existing_switcher(
        self, tmp_path: Path
    ):
        """Existing files get their Language Switcher updated, not overwritten."""
        uc_folder = tmp_path / "test-uc"
        uc_folder.mkdir()

        # Source README
        source_readme = uc_folder / "README.md"
        source_readme.write_text(
            "# テストプロジェクト\n\nこれはテストです。\n",
            encoding="utf-8",
        )

        # Pre-existing English README (should only get switcher updated)
        existing_en = uc_folder / "README.en.md"
        existing_content = "# Test Project\n\nThis is existing content.\n"
        existing_en.write_text(existing_content, encoding="utf-8")

        generator = self._create_generator(tmp_path)
        results = generator.generate_for_folder("test-uc")

        # English file should have switcher added but content preserved
        updated_en = existing_en.read_text(encoding="utf-8")
        assert "🌐" in updated_en, "Switcher should be injected"
        assert "This is existing content." in updated_en, (
            "Original content should be preserved"
        )

    def test_generate_for_folder_missing_source(self, tmp_path: Path):
        """Missing source README returns empty results."""
        uc_folder = tmp_path / "test-uc"
        uc_folder.mkdir()
        # No README.md created

        generator = self._create_generator(tmp_path)
        results = generator.generate_for_folder("test-uc")

        assert results == []

    def test_generate_for_folder_error_handling(self, tmp_path: Path):
        """Errors during translation are captured in TranslationResult."""
        uc_folder = tmp_path / "test-uc"
        uc_folder.mkdir()
        source_readme = uc_folder / "README.md"
        source_readme.write_text(
            "# テスト\n\nコンテンツ\n", encoding="utf-8"
        )

        generator = self._create_generator(tmp_path)

        # Make bedrock client raise an error
        generator.translator.bedrock_client.invoke_model.side_effect = (
            RuntimeError("API Error")
        )

        results = generator.generate_for_folder("test-uc")

        # All results should be failures
        assert len(results) == 7
        assert all(not r.success for r in results)
        assert all(r.error is not None for r in results)

    def test_source_readme_gets_switcher(self, tmp_path: Path):
        """Source README.md gets Language Switcher injected."""
        uc_folder = tmp_path / "test-uc"
        uc_folder.mkdir()
        source_readme = uc_folder / "README.md"
        source_readme.write_text(
            "# テストプロジェクト\n\nこれはテストです。\n",
            encoding="utf-8",
        )

        generator = self._create_generator(tmp_path)
        generator.generate_for_folder("test-uc")

        # Source README should now have switcher
        updated_source = source_readme.read_text(encoding="utf-8")
        assert "🌐" in updated_source, (
            "Source README should have switcher injected"
        )
        # Current lang for source should be "ja" (plain text)
        assert "日本語" in updated_source
        # "日本語" should NOT be a link in the source
        assert "[日本語](" not in updated_source

    def test_translation_result_contains_source_hash(self, tmp_path: Path):
        """TranslationResult includes source hash for change detection."""
        uc_folder = tmp_path / "test-uc"
        uc_folder.mkdir()
        source_readme = uc_folder / "README.md"
        source_readme.write_text(
            "# テスト\n\nコンテンツ\n", encoding="utf-8"
        )

        generator = self._create_generator(tmp_path)
        results = generator.generate_for_folder("test-uc")

        assert all(r.source_hash for r in results)
        # All results for same source should have same hash
        hashes = set(r.source_hash for r in results)
        assert len(hashes) == 1, "All results should share same source hash"
