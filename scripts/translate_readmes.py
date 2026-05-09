#!/usr/bin/env python3
"""UC フォルダ多言語 README 翻訳システム.

全14ユースケースフォルダの README.md を8言語に展開し、
統一された Language Switcher を注入するプロセスを管理する。

対象言語: ja (source), en, ko, zh-CN, zh-TW, fr, de, es
翻訳エンジン: Amazon Bedrock (Claude Haiku)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import boto3
from botocore.config import Config as BotoConfig

logger = logging.getLogger(__name__)


class BlockType(Enum):
    """Markdown コンテンツブロックの種別."""

    PROSE = "prose"  # 翻訳対象
    CODE = "code"  # 保持（コードブロック）
    MERMAID = "mermaid"  # 保持（Mermaid ダイアグラム）
    TABLE = "table"  # テキストセルのみ翻訳
    HEADING = "heading"  # テキスト部分を翻訳
    SWITCHER = "switcher"  # 置換対象


@dataclass
class ContentBlock:
    """翻訳パイプライン内部のコンテンツブロック."""

    block_type: BlockType
    content: str
    translated: str | None = None


@dataclass
class TranslationResult:
    """UC フォルダ単位の翻訳生成結果."""

    uc_folder: str
    lang: str
    output_path: str
    source_hash: str  # ソース README の SHA256（変更検知用）
    success: bool
    error: str | None = None


@dataclass
class LanguageSwitcherConfig:
    """Language Switcher の設定."""

    languages: dict[str, str]  # lang_code -> display_label
    file_map: dict[str, str]  # lang_code -> filename
    current_lang: str  # 現在のファイルの言語


@dataclass
class TranslationConfig:
    """翻訳システム全体の設定."""

    source_lang: str = "ja"
    target_languages: list[str] = field(
        default_factory=lambda: ["en", "ko", "zh-CN", "zh-TW", "fr", "de", "es"]
    )
    uc_folders: list[str] = field(
        default_factory=lambda: [
            "semiconductor-eda",
            "legal-compliance",
            "financial-idp",
            "manufacturing-analytics",
            "media-vfx",
            "healthcare-dicom",
            "autonomous-driving",
            "construction-bim",
            "education-research",
            "energy-seismic",
            "genomics-pipeline",
            "insurance-claims",
            "logistics-ocr",
            "retail-catalog",
        ]
    )
    bedrock_model_id: str = "anthropic.claude-3-haiku-20240307-v1:0"


class LanguageSwitcherInjector:
    """Language Switcher の生成と注入を担当するコンポーネント.

    H1 直後に統一フォーマットの Language Switcher 行を挿入し、
    現在言語はプレーンテキスト、他言語はリンクとして表示する。
    """

    SWITCHER_TEMPLATE = "🌐 **Language / 言語**: {links}"

    LANG_LABELS: dict[str, str] = {
        "ja": "日本語",
        "en": "English",
        "ko": "한국어",
        "zh-CN": "简体中文",
        "zh-TW": "繁體中文",
        "fr": "Français",
        "de": "Deutsch",
        "es": "Español",
    }

    LANG_FILES: dict[str, str] = {
        "ja": "README.md",
        "en": "README.en.md",
        "ko": "README.ko.md",
        "zh-CN": "README.zh-CN.md",
        "zh-TW": "README.zh-TW.md",
        "fr": "README.fr.md",
        "de": "README.de.md",
        "es": "README.es.md",
    }

    def generate_switcher(self, current_lang: str) -> str:
        """現在言語をプレーンテキスト、他言語をリンクとして Switcher 行を生成.

        Args:
            current_lang: 現在のファイルの言語コード (e.g., "ja", "en")

        Returns:
            フォーマット済みの Language Switcher 行文字列
        """
        parts: list[str] = []
        for lang, label in self.LANG_LABELS.items():
            if lang == current_lang:
                parts.append(label)
            else:
                filename = self.LANG_FILES[lang]
                parts.append(f"[{label}]({filename})")
        links = " | ".join(parts)
        return self.SWITCHER_TEMPLATE.format(links=links)

    def inject_into_markdown(self, content: str, current_lang: str) -> str:
        """H1 直後に Language Switcher を挿入（既存 Switcher があれば置換）.

        Args:
            content: 元の Markdown 文字列
            current_lang: 現在のファイルの言語コード

        Returns:
            Switcher が注入された Markdown 文字列
        """
        switcher_line = self.generate_switcher(current_lang)
        lines = content.split("\n")

        # H1 行を検索
        h1_index: int | None = None
        for i, line in enumerate(lines):
            if line.startswith("# "):
                h1_index = i
                break

        if h1_index is None:
            # H1 が見つからない場合は先頭に挿入
            return switcher_line + "\n\n" + content

        # H1 の次の行以降で既存 Switcher 行を検索
        existing_switcher_index: int | None = None
        search_start = h1_index + 1
        for i in range(search_start, len(lines)):
            stripped = lines[i].strip()
            if stripped.startswith("🌐"):
                existing_switcher_index = i
                break
            # 空行はスキップして探索を続ける
            if stripped != "":
                break

        if existing_switcher_index is not None:
            # 既存 Switcher を置換
            lines[existing_switcher_index] = switcher_line
            return "\n".join(lines)
        else:
            # H1 直後に挿入（空行 + switcher + 空行）
            new_lines = lines[: h1_index + 1]
            new_lines.append("")
            new_lines.append(switcher_line)
            # H1 の次に既に空行がある場合は重複を避ける
            remaining = lines[h1_index + 1 :]
            if remaining and remaining[0].strip() == "":
                # 既存の空行を活用
                new_lines.extend(remaining)
            else:
                new_lines.append("")
                new_lines.extend(remaining)
            return "\n".join(new_lines)


class MarkdownTranslator:
    """Markdown コンテンツの翻訳.

    Markdown の構造を保持しながら翻訳を行うコンポーネント。
    コードブロック・Mermaid ダイアグラム・テーブル構造を分離し、
    prose セクションのみを翻訳対象とする。
    """

    LANG_NAMES: dict[str, str] = {
        "en": "English",
        "ko": "Korean",
        "zh-CN": "Simplified Chinese",
        "zh-TW": "Traditional Chinese",
        "fr": "French",
        "de": "German",
        "es": "Spanish",
    }

    def __init__(
        self,
        bedrock_model_id: str = "anthropic.claude-3-haiku-20240307-v1:0",
    ) -> None:
        """MarkdownTranslator を初期化.

        Args:
            bedrock_model_id: 翻訳に使用する Bedrock モデル ID
        """
        self.bedrock_model_id = bedrock_model_id
        self.bedrock_client = boto3.client(
            "bedrock-runtime",
            config=BotoConfig(read_timeout=60, connect_timeout=60),
        )

    def split_translatable(self, content: str) -> list[ContentBlock]:
        """コードブロック・Mermaid・テーブル構造を分離.

        Markdown コンテンツを行単位で解析し、ブロック種別ごとに分割する。

        Args:
            content: Markdown 文字列

        Returns:
            ContentBlock のリスト（元の順序を保持）
        """
        lines = content.split("\n")
        blocks: list[ContentBlock] = []
        i = 0

        while i < len(lines):
            line = lines[i]

            # CODE / MERMAID blocks: lines between ``` fences
            if line.strip().startswith("```"):
                fence_line = line.strip()
                # Determine if mermaid
                is_mermaid = fence_line.lower().startswith("```mermaid")
                block_type = BlockType.MERMAID if is_mermaid else BlockType.CODE
                block_lines = [line]
                i += 1
                # Collect until closing fence
                while i < len(lines):
                    block_lines.append(lines[i])
                    if lines[i].strip().startswith("```") and len(block_lines) > 1:
                        i += 1
                        break
                    i += 1
                blocks.append(ContentBlock(
                    block_type=block_type,
                    content="\n".join(block_lines),
                ))
                continue

            # HEADING blocks: lines starting with #
            if re.match(r"^#{1,6}\s", line):
                blocks.append(ContentBlock(
                    block_type=BlockType.HEADING,
                    content=line,
                ))
                i += 1
                continue

            # SWITCHER blocks: lines starting with 🌐
            if line.startswith("🌐"):
                blocks.append(ContentBlock(
                    block_type=BlockType.SWITCHER,
                    content=line,
                ))
                i += 1
                continue

            # TABLE blocks: consecutive lines starting with |
            if line.startswith("|"):
                table_lines = []
                while i < len(lines) and lines[i].startswith("|"):
                    table_lines.append(lines[i])
                    i += 1
                blocks.append(ContentBlock(
                    block_type=BlockType.TABLE,
                    content="\n".join(table_lines),
                ))
                continue

            # PROSE blocks: everything else (paragraphs, list items, blockquotes, empty lines)
            prose_lines = []
            while i < len(lines):
                current = lines[i]
                # Stop if we hit a different block type
                if current.strip().startswith("```"):
                    break
                if re.match(r"^#{1,6}\s", current):
                    break
                if current.startswith("🌐"):
                    break
                if current.startswith("|"):
                    break
                prose_lines.append(current)
                i += 1
            if prose_lines:
                blocks.append(ContentBlock(
                    block_type=BlockType.PROSE,
                    content="\n".join(prose_lines),
                ))
            continue

        return blocks

    def reassemble(self, blocks: list[ContentBlock]) -> str:
        """翻訳済みブロックを再結合.

        各ブロックの translated フィールドがあればそれを使用し、
        なければ元の content を使用する。

        Args:
            blocks: ContentBlock のリスト

        Returns:
            再結合された Markdown 文字列
        """
        parts: list[str] = []
        for block in blocks:
            if block.translated is not None:
                parts.append(block.translated)
            else:
                parts.append(block.content)
        return "\n".join(parts)

    def _is_nova_model(self) -> bool:
        """Check if the configured model is an Amazon Nova model."""
        return "nova" in self.bedrock_model_id.lower()

    def _build_request_body(self, prompt: str) -> str:
        """Build the request body based on model type.

        Args:
            prompt: The prompt text to send

        Returns:
            JSON string for the request body
        """
        if self._is_nova_model():
            # Amazon Nova models use Converse-style format via InvokeModel
            return json.dumps({
                "messages": [
                    {"role": "user", "content": [{"text": prompt}]},
                ],
                "inferenceConfig": {
                    "max_new_tokens": 4096,
                },
            })
        else:
            # Anthropic Claude models
            return json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4096,
                "messages": [
                    {"role": "user", "content": prompt},
                ],
            })

    def _parse_response(self, response_body: dict) -> str:
        """Parse the response body based on model type.

        Args:
            response_body: Parsed JSON response

        Returns:
            Extracted translated text
        """
        if self._is_nova_model():
            return response_body["output"]["message"]["content"][0]["text"]
        else:
            return response_body["content"][0]["text"]

    def translate_prose(self, text: str, target_lang: str) -> str:
        """Bedrock で prose を翻訳.

        Args:
            text: 翻訳対象テキスト
            target_lang: 翻訳先言語コード

        Returns:
            翻訳済みテキスト
        """
        if not text.strip():
            return text

        lang_name = self.LANG_NAMES.get(target_lang, target_lang)

        prompt = (
            f"Translate the following text to {lang_name}.\n\n"
            "Rules:\n"
            "- Keep AWS service names in English (Amazon Bedrock, AWS Step Functions, Amazon Athena, Amazon S3, AWS Lambda, Amazon FSx for NetApp ONTAP, Amazon CloudWatch, AWS CloudFormation, etc.)\n"
            "- Keep technical terms untranslated (GDSII, DRC, OASIS, GDS, Lambda, tapeout, etc.)\n"
            "- Keep inline code (`...`) untranslated\n"
            "- Keep file paths and URLs untranslated\n"
            "- Translate naturally, not word-for-word\n"
            "- Return ONLY the translated text, no explanations\n\n"
            f"Text to translate:\n{text}"
        )

        body = self._build_request_body(prompt)

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.bedrock_client.invoke_model(
                    modelId=self.bedrock_model_id,
                    contentType="application/json",
                    accept="application/json",
                    body=body,
                )
                response_body = json.loads(response["body"].read())
                translated = self._parse_response(response_body)
                return translated.strip()
            except self.bedrock_client.exceptions.ThrottlingException:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    time.sleep(wait_time)
                else:
                    raise

        # Should not reach here, but return original text as fallback
        return text


class ReadmeGenerator:
    """UC フォルダ単位の README 生成オーケストレーター."""

    def __init__(self, config: TranslationConfig, project_root: str) -> None:
        self.config = config
        self.project_root = project_root
        self.injector = LanguageSwitcherInjector()
        self.translator = MarkdownTranslator(bedrock_model_id=config.bedrock_model_id)
        self.results: list[TranslationResult] = []

    def generate_for_folder(self, folder_name: str) -> list[TranslationResult]:
        """1 UC フォルダの全言語版を生成."""
        folder_path = os.path.join(self.project_root, folder_name)
        source_path = os.path.join(folder_path, "README.md")

        if not os.path.exists(source_path):
            logger.warning(f"Source README not found: {source_path}")
            return []

        with open(source_path, "r", encoding="utf-8") as f:
            source_content = f.read()

        source_hash = hashlib.sha256(source_content.encode()).hexdigest()[:16]

        # Add language switcher to source (ja) README
        updated_source = self.injector.inject_into_markdown(source_content, "ja")
        with open(source_path, "w", encoding="utf-8") as f:
            f.write(updated_source)

        folder_results = []

        for target_lang in self.config.target_languages:
            output_filename = LanguageSwitcherInjector.LANG_FILES[target_lang]
            output_path = os.path.join(folder_path, output_filename)

            try:
                # Check if file already exists
                if os.path.exists(output_path):
                    # Only update language switcher for existing files
                    with open(output_path, "r", encoding="utf-8") as f:
                        existing_content = f.read()
                    updated = self.injector.inject_into_markdown(
                        existing_content, target_lang
                    )
                    with open(output_path, "w", encoding="utf-8") as f:
                        f.write(updated)
                    logger.info(f"Updated switcher: {output_path}")
                else:
                    # Translate and generate new file
                    blocks = self.translator.split_translatable(source_content)
                    for block in blocks:
                        if block.block_type in (BlockType.PROSE, BlockType.HEADING):
                            block.translated = self.translator.translate_prose(
                                block.content, target_lang
                            )
                        elif block.block_type == BlockType.SWITCHER:
                            block.translated = self.injector.generate_switcher(
                                target_lang
                            )

                    translated_content = self.translator.reassemble(blocks)
                    # Inject language switcher
                    final_content = self.injector.inject_into_markdown(
                        translated_content, target_lang
                    )

                    with open(output_path, "w", encoding="utf-8") as f:
                        f.write(final_content)
                    logger.info(f"Generated: {output_path}")

                result = TranslationResult(
                    uc_folder=folder_name,
                    lang=target_lang,
                    output_path=output_path,
                    source_hash=source_hash,
                    success=True,
                )
            except Exception as e:
                logger.error(f"Failed to generate {output_path}: {e}")
                result = TranslationResult(
                    uc_folder=folder_name,
                    lang=target_lang,
                    output_path=output_path,
                    source_hash=source_hash,
                    success=False,
                    error=str(e),
                )

            folder_results.append(result)
            self.results.append(result)

        return folder_results

    def generate_all(self) -> None:
        """全14フォルダを処理."""
        total = len(self.config.uc_folders)
        for idx, folder in enumerate(self.config.uc_folders, 1):
            logger.info(f"[{idx}/{total}] Processing: {folder}")
            self.generate_for_folder(folder)

        # Summary report
        success_count = sum(1 for r in self.results if r.success)
        fail_count = sum(1 for r in self.results if not r.success)
        logger.info(f"Complete: {success_count} succeeded, {fail_count} failed")

        if fail_count > 0:
            with open("translation_errors.log", "w") as f:
                for r in self.results:
                    if not r.success:
                        f.write(f"{r.uc_folder}/{r.lang}: {r.error}\n")


def main():
    """CLI エントリーポイント."""
    parser = argparse.ArgumentParser(
        description="UC フォルダ多言語 README 翻訳システム"
    )
    parser.add_argument(
        "--folders", nargs="+", help="対象フォルダ名（スペース区切り）"
    )
    parser.add_argument("--all", action="store_true", help="全14フォルダを処理")
    parser.add_argument(
        "--dry-run", action="store_true", help="ファイル書き出しをスキップ"
    )
    parser.add_argument(
        "--project-root", default=".", help="プロジェクトルートパス"
    )
    parser.add_argument(
        "--model-id",
        default="anthropic.claude-3-haiku-20240307-v1:0",
        help="Bedrock モデル ID",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    config = TranslationConfig(bedrock_model_id=args.model_id)

    if args.folders:
        config.uc_folders = args.folders
    elif not args.all:
        parser.error("--folders or --all is required")

    generator = ReadmeGenerator(config=config, project_root=args.project_root)

    if args.dry_run:
        logger.info(f"Dry run: would process {len(config.uc_folders)} folders")
        for folder in config.uc_folders:
            logger.info(f"  - {folder}")
        return

    generator.generate_all()


if __name__ == "__main__":
    main()
