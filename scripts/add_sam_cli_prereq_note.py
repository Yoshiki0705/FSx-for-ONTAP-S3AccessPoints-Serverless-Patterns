#!/usr/bin/env python3
"""Insert a localized 'AWS SAM CLI required' comment before each `sam build` line
in README files (inside the existing bash code fence). Idempotent.

Language is inferred from the filename suffix (README.md = Japanese primary).

Usage: python3 scripts/add_sam_cli_prereq_note.py <README.md> [--write]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

NOTES = {
    "ja": "# 前提: AWS SAM CLI が必要です。sam build がコードと共有レイヤーを自動でパッケージングします。",
    "en": "# Prerequisite: AWS SAM CLI required. 'sam build' packages the code and shared layer automatically.",
    "ko": "# 사전 요구사항: AWS SAM CLI가 필요합니다. 'sam build'가 코드와 공유 레이어를 자동으로 패키징합니다.",
    "zh-CN": "# 前提条件：需要 AWS SAM CLI。'sam build' 会自动打包代码和共享层。",
    "zh-TW": "# 前提條件：需要 AWS SAM CLI。'sam build' 會自動打包程式碼與共用層。",
    "fr": "# Prérequis : AWS SAM CLI requis. « sam build » empaquette automatiquement le code et la couche partagée.",
    "de": "# Voraussetzung: AWS SAM CLI erforderlich. „sam build“ verpackt Code und Shared Layer automatisch.",
    "es": "# Requisito: se necesita AWS SAM CLI. «sam build» empaqueta automáticamente el código y la capa compartida.",
}


def lang_of(name: str) -> str:
    m = re.match(r"README(?:\.([a-zA-Z-]+))?\.md$", name)
    if not m or not m.group(1):
        return "ja"
    return m.group(1)


def transform(content: str, note: str) -> tuple[str, int]:
    lines = content.split("\n")
    out: list[str] = []
    count = 0
    for idx, line in enumerate(lines):
        if line.strip() == "sam build":
            prev = out[-1].strip() if out else ""
            if prev != note:
                indent = line[: len(line) - len(line.lstrip())]
                out.append(f"{indent}{note}")
                count += 1
        out.append(line)
    return "\n".join(out), count


def main() -> int:
    path = Path(sys.argv[1])
    write = "--write" in sys.argv
    note = NOTES.get(lang_of(path.name), NOTES["en"])
    new, count = transform(path.read_text(), note)
    if write and count:
        path.write_text(new)
    print(f"{'WROTE' if (write and count) else 'dry'} {path} ({count})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
