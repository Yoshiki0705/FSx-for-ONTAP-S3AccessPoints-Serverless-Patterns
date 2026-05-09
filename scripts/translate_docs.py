#!/usr/bin/env python3
"""docs/ フォルダ内ドキュメントの多言語翻訳スクリプト.

指定されたソースファイル（日本語）を8言語に展開し、
統一された Language Switcher を注入する。

対象言語: ja (source), en, ko, zh-CN, zh-TW, fr, de, es
翻訳エンジン: Amazon Bedrock (Amazon Nova Lite)

Usage:
    python scripts/translate_docs.py \
        --source semiconductor-eda/docs/demo-guide.md \
        --project-root /path/to/project

    python scripts/translate_docs.py \
        --source semiconductor-eda/docs/uc6-architecture.md \
        --project-root /path/to/project
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

# Add scripts directory to path for importing translate_readmes
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from translate_readmes import (
    BlockType,
    ContentBlock,
    LanguageSwitcherInjector,
    MarkdownTranslator,
)

logger = logging.getLogger(__name__)


# Patterns that indicate instruction leakage from the translation prompt
INSTRUCTION_LEAKAGE_PATTERNS = [
    r"^(?:Rules?|규칙|Regeln|Règles|Reglas|规则|規則)\s*[:：]?\s*$",
    r"^-\s*(?:Keep|Maintain|Preserve|Conserver|Behalten|Mantener|保持|유지)",
    r"^-\s*(?:Translate naturally|Return ONLY|翻訳|번역|自然翻译|只返回|自然に翻訳)",
    r"^-\s*(?:Keep inline code|Keep file paths|Keep technical terms|Keep AWS service names)",
    r"^-\s*(?:AWS 서비스|기술 용어|인라인 코드|파일 경로|자연스럽게|설명 없이)",
    r"^-\s*(?:保持AWS|保持技术|保持内联|保持文件|自然翻译|只返回翻译)",
    r"^-\s*(?:AWS-Dienstnamen|Technische Begriffe|Inline-Code|Dateipfade)",
    r"^-\s*(?:Conserver les noms|Garder les termes|Conserver le code|Conserver les chemins)",
    r"^-\s*(?:Mantener los nombres|Mantener los términos|Mantener el código|Mantener las rutas)",
    r"^(?:Text to translate|翻訳するテキスト|번역할 텍스트|翻译文本|要翻譯的文本|Texte à traduire|Zu übersetzender Text|Texto a traducir)\s*[:：]?\s*$",
]

# Target languages (source is ja)
TARGET_LANGUAGES = ["en", "ko", "zh-CN", "zh-TW", "fr", "de", "es"]


def strip_instruction_leakage(text: str) -> str:
    """Remove instruction leakage from translated text.

    Nova models sometimes echo back the translation prompt rules
    in the output. This function detects and removes those lines.

    Args:
        text: Translated text that may contain instruction leakage

    Returns:
        Cleaned text with instruction lines removed
    """
    import re as _re

    lines = text.split("\n")
    cleaned_lines: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Check if this line is an instruction leakage line
        is_instruction = False
        for pattern in INSTRUCTION_LEAKAGE_PATTERNS:
            if _re.match(pattern, stripped):
                is_instruction = True
                break

        # Also check for "AWS service names" instruction pattern in any language
        if not is_instruction and _re.search(
            r"(?:Keep|Maintain|Garder|Behalten|Mantener|Mantén|보持|유지|保持).*(?:AWS|service|서비스|服务|服務|Dienst).*(?:English|anglais|Englisch|inglés|영어|英文|英語)",
            stripped,
        ):
            is_instruction = True

        # Check for "technical terms untranslated" pattern
        if not is_instruction and _re.search(
            r"(?:Keep|Maintain|Garder|Behalten|Mantener|Mantén|유지|保持).*(?:technical|technique|technisch|técnic|기술|技术|技術).*(?:untranslated|inchangé|unverändert|sin traducir|번역하지|不翻译|不翻譯)",
            stripped,
        ):
            is_instruction = True

        # Check for "inline code" instruction pattern
        if not is_instruction and _re.search(
            r"(?:Keep|Maintain|Garder|Behalten|Mantener|Mantén|유지|保持).*(?:inline code|code en ligne|Inline-Code|código en línea|인라인 코드|内联代码|內聯代碼)",
            stripped,
        ):
            is_instruction = True

        # Check for "file paths" instruction pattern
        if not is_instruction and _re.search(
            r"(?:Keep|Maintain|Garder|Behalten|Mantener|Mantén|유지|保持).*(?:file paths|chemins|Dateipfade|rutas|파일 경로|文件路径|文件路徑)",
            stripped,
        ):
            is_instruction = True

        # Check for "translate naturally" instruction pattern
        if not is_instruction and _re.search(
            r"(?:Translate naturally|Traduire naturellement|Natürlich übersetzen|Traducir de forma natural|자연스럽게 번역|自然翻译|自然地翻譯)",
            stripped,
        ):
            is_instruction = True

        # Check for "return ONLY" instruction pattern
        if not is_instruction and _re.search(
            r"(?:Return ONLY|Retourner UNIQUEMENT|Nur.*zurückgeben|Devolver SOLO|번역문만 반환|只返回翻译|只返回翻譯)",
            stripped,
        ):
            is_instruction = True

        # Korean-specific patterns
        if not is_instruction and _re.search(
            r"(?:영어로 유지|번역하지 않습니다|단어 그대로 번역하지)",
            stripped,
        ):
            is_instruction = True

        # Chinese-specific patterns
        if not is_instruction and _re.search(
            r"(?:保持.*英文|不翻译|不翻譯|只返回翻译文本|只返回翻譯文本)",
            stripped,
        ):
            is_instruction = True

        if is_instruction:
            # Skip this line and any following instruction lines
            i += 1
            continue
        else:
            cleaned_lines.append(line)
            i += 1

    # Remove excessive blank lines (more than 2 consecutive)
    result_lines: list[str] = []
    blank_count = 0
    for line in cleaned_lines:
        if line.strip() == "":
            blank_count += 1
            if blank_count <= 2:
                result_lines.append(line)
        else:
            blank_count = 0
            result_lines.append(line)

    return "\n".join(result_lines)


class CleanMarkdownTranslator(MarkdownTranslator):
    """Extended MarkdownTranslator that strips instruction leakage."""

    def translate_prose(self, text: str, target_lang: str) -> str:
        """Translate prose and clean instruction leakage from output."""
        result = super().translate_prose(text, target_lang)
        return strip_instruction_leakage(result)


class DocLanguageSwitcherInjector(LanguageSwitcherInjector):
    """docs/ ファイル用の Language Switcher.

    README.md ではなく、任意のファイル名ベースで
    Language Switcher のリンクを生成する。
    """

    def __init__(self, basename: str) -> None:
        """Initialize with the base filename (without extension).

        Args:
            basename: e.g., "demo-guide" or "uc6-architecture"
        """
        super().__init__()
        self.basename = basename
        # Override LANG_FILES with doc-specific filenames
        self.LANG_FILES = {
            "ja": f"{basename}.md",
            "en": f"{basename}.en.md",
            "ko": f"{basename}.ko.md",
            "zh-CN": f"{basename}.zh-CN.md",
            "zh-TW": f"{basename}.zh-TW.md",
            "fr": f"{basename}.fr.md",
            "de": f"{basename}.de.md",
            "es": f"{basename}.es.md",
        }


def translate_doc(
    source_path: str,
    project_root: str,
    model_id: str = "amazon.nova-lite-v1:0",
    force: bool = False,
) -> None:
    """Translate a single documentation file into 7 target languages.

    Args:
        source_path: Relative path from project root (e.g., "semiconductor-eda/docs/demo-guide.md")
        project_root: Absolute path to project root
        model_id: Bedrock model ID for translation
        force: If True, overwrite existing translations
    """
    full_source_path = os.path.join(project_root, source_path)

    if not os.path.exists(full_source_path):
        logger.error(f"Source file not found: {full_source_path}")
        return

    # Derive basename and output directory
    source_dir = os.path.dirname(full_source_path)
    source_filename = os.path.basename(full_source_path)
    basename = source_filename.rsplit(".", 1)[0]  # e.g., "demo-guide"

    logger.info(f"=== Translating: {source_path} ===")
    logger.info(f"  Basename: {basename}")
    logger.info(f"  Output dir: {source_dir}")

    # Read source content
    with open(full_source_path, "r", encoding="utf-8") as f:
        source_content = f.read()

    # Initialize components
    injector = DocLanguageSwitcherInjector(basename)
    translator = CleanMarkdownTranslator(bedrock_model_id=model_id)

    # Step 1: Update source file with Language Switcher
    logger.info("  Injecting Language Switcher into source (ja)...")
    updated_source = injector.inject_into_markdown(source_content, "ja")
    with open(full_source_path, "w", encoding="utf-8") as f:
        f.write(updated_source)
    logger.info(f"  ✅ Updated: {source_filename}")

    # Step 2: Generate translations for each target language
    for target_lang in TARGET_LANGUAGES:
        output_filename = injector.LANG_FILES[target_lang]
        output_path = os.path.join(source_dir, output_filename)

        if os.path.exists(output_path) and not force:
            logger.info(f"  ⏭️  Skipping (exists): {output_filename}")
            continue

        logger.info(f"  🔄 Translating to {target_lang}: {output_filename}...")

        try:
            # Split source into translatable blocks
            blocks = translator.split_translatable(source_content)

            # Translate prose and heading blocks
            for block in blocks:
                if block.block_type in (BlockType.PROSE, BlockType.HEADING):
                    block.translated = translator.translate_prose(
                        block.content, target_lang
                    )
                elif block.block_type == BlockType.SWITCHER:
                    block.translated = injector.generate_switcher(target_lang)

            # Reassemble translated content
            translated_content = translator.reassemble(blocks)

            # Inject language switcher for this language
            final_content = injector.inject_into_markdown(
                translated_content, target_lang
            )

            # Write output file
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(final_content)

            logger.info(f"  ✅ Generated: {output_filename}")

        except Exception as e:
            logger.error(f"  ❌ Failed {output_filename}: {e}")
            import traceback
            traceback.print_exc()


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="docs/ フォルダ内ドキュメントの多言語翻訳"
    )
    parser.add_argument(
        "--source",
        required=True,
        nargs="+",
        help="翻訳対象ファイルの相対パス（プロジェクトルートから）",
    )
    parser.add_argument(
        "--project-root",
        default=".",
        help="プロジェクトルートパス",
    )
    parser.add_argument(
        "--model-id",
        default="amazon.nova-lite-v1:0",
        help="Bedrock モデル ID (default: amazon.nova-lite-v1:0)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="既存の翻訳ファイルを上書き",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    for source in args.source:
        translate_doc(
            source_path=source,
            project_root=args.project_root,
            model_id=args.model_id,
            force=args.force,
        )

    logger.info("=== All translations complete ===")


if __name__ == "__main__":
    main()
