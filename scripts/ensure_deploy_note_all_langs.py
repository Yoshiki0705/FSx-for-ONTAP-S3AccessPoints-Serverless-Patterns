#!/usr/bin/env python3
"""Ensure the canonical template.yaml/template-deploy.yaml note follows the
`sam deploy` block in every language README that has a deploy block.

Some READMEs (often the canonical ja README, sometimes en) carried a
`sam deploy` block from before the note was standardized. This inserts the
localized note right after the deploy fenced block.

Idempotent: skips READMEs that already mention `template-deploy.yaml`.
Only touches READMEs that actually contain a `sam deploy` block.
"""
from __future__ import annotations

import glob
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

NOTE = {
    "md": (
        "> **注意**: `template.yaml` は SAM CLI（`sam build` + `sam deploy`）で使用します。\n"
        "> `aws cloudformation deploy` コマンドで直接デプロイする場合は `template-deploy.yaml` を使用してください（Lambda zip ファイルの事前パッケージングと S3 アップロードが必要です）。"
    ),
    "en.md": (
        "> **Note**: `template.yaml` is designed for use with SAM CLI (`sam build` + `sam deploy`).\n"
        "> To deploy with raw `aws cloudformation deploy`, use `template-deploy.yaml` instead (requires pre-packaging Lambda zip files and uploading them to an S3 bucket)."
    ),
    "ko.md": (
        "> **참고**: `template.yaml`은 SAM CLI (`sam build` + `sam deploy`) 를 통해 배포합니다.\n"
        "> `aws cloudformation deploy` 명령으로 직접 배포하려면 `template-deploy.yaml`을 사용하세요 (Lambda zip 파일의 사전 패키징 및 S3 업로드가 필요합니다)."
    ),
    "zh-CN.md": (
        "> **注意**: `template.yaml` 用于 SAM CLI（`sam build` + `sam deploy`）。\n"
        "> 如需使用原生 `aws cloudformation deploy` 部署，请改用 `template-deploy.yaml`（需要预先打包 Lambda zip 文件并上传到 S3 存储桶）。"
    ),
    "zh-TW.md": (
        "> **注意**: `template.yaml` 用於 SAM CLI（`sam build` + `sam deploy`）。\n"
        "> 如需使用原生 `aws cloudformation deploy` 部署，請改用 `template-deploy.yaml`（需要預先封裝 Lambda zip 檔案並上傳至 S3 儲存貯體）。"
    ),
    "fr.md": (
        "> **Remarque** : `template.yaml` est conçu pour être utilisé avec AWS SAM CLI (`sam build` + `sam deploy`).\n"
        "> Pour un déploiement direct avec `aws cloudformation deploy`, utilisez plutôt `template-deploy.yaml` (nécessite de packager au préalable les fichiers zip Lambda et de les téléverser dans un bucket S3)."
    ),
    "de.md": (
        "> **Hinweis**: `template.yaml` ist für die Verwendung mit der AWS SAM CLI (`sam build` + `sam deploy`) vorgesehen.\n"
        "> Für eine direkte Bereitstellung mit `aws cloudformation deploy` verwenden Sie stattdessen `template-deploy.yaml` (erfordert das vorherige Packen der Lambda-Zip-Dateien und das Hochladen in einen S3-Bucket)."
    ),
    "es.md": (
        "> **Nota**: `template.yaml` está diseñado para usarse con AWS SAM CLI (`sam build` + `sam deploy`).\n"
        "> Para desplegar directamente con `aws cloudformation deploy`, use `template-deploy.yaml` en su lugar (requiere empaquetar previamente los archivos zip de Lambda y subirlos a un bucket de S3)."
    ),
}


def suffix_of(path: Path) -> str:
    return "md" if path.name == "README.md" else path.name[len("README."):]


def insert_note_after_deploy_block(text: str, note: str) -> str | None:
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith("```"):
            start = i
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("```"):
                j += 1
            block = lines[start:j + 1]
            if any("sam deploy" in ln for ln in block):
                close_idx = j  # index of closing ```
                new_lines = lines[:close_idx + 1] + ["", note] + lines[close_idx + 1:]
                out = "\n".join(new_lines)
                out = re.sub(r"\n{3,}", "\n\n", out)
                return out
            i = j + 1
        else:
            i += 1
    return None


def main() -> int:
    changed = 0
    for md in sorted(glob.glob(str(ROOT / "solutions" / "**" / "README*.md"), recursive=True)):
        p = Path(md)
        suf = suffix_of(p)
        if suf not in NOTE:
            continue
        text = p.read_text()
        if "template-deploy.yaml" in text:
            continue
        if "sam deploy" not in text:
            continue
        updated = insert_note_after_deploy_block(text, NOTE[suf])
        if updated and updated != text:
            p.write_text(updated)
            changed += 1
            print(f"note added -> {p.relative_to(ROOT)}")
    print(f"\n{changed} file(s) updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
