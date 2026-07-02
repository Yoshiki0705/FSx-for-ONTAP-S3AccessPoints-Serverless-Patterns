#!/usr/bin/env python3
"""One-off doc sync for semiconductor-eda READMEs (all 8 languages).

Aligns the deployment docs to the post-#54 SAM-first standard:
  T1. Remove the outdated manual "Lambda deploy package" step (zip + S3 upload)
      that `sam build` now handles automatically, then renumber later steps.
  T2. Replace the "template usage" table (which framed template-deploy.yaml as
      the production path) with the canonical SAM/raw-CFn clarifying note.
  T3. Remove the stale `DeployBucket` parameter table row (no longer in
      the self-contained template.yaml).

Structural anchors (code blocks, table keys) are language-agnostic; only the
replacement note text is per-language.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERN_DIR = ROOT / "solutions" / "industry" / "semiconductor-eda"

# Canonical clarifying note (2 blockquote lines) per language.
NOTES: dict[str, str] = {
    "README.md": (
        "> **注意**: `template.yaml` は SAM CLI（`sam build` + `sam deploy`）で使用します。\n"
        "> `aws cloudformation deploy` コマンドで直接デプロイする場合は `template-deploy.yaml` を使用してください（Lambda zip ファイルの事前パッケージングと S3 アップロードが必要です）。"
    ),
    "README.en.md": (
        "> **Note**: `template.yaml` is designed for use with SAM CLI (`sam build` + `sam deploy`).\n"
        "> To deploy with raw `aws cloudformation deploy`, use `template-deploy.yaml` instead (requires pre-packaging Lambda zip files and uploading them to an S3 bucket)."
    ),
    "README.ko.md": (
        "> **참고**: `template.yaml`은 SAM CLI (`sam build` + `sam deploy`) 를 통해 배포합니다.\n"
        "> `aws cloudformation deploy` 명령으로 직접 배포하려면 `template-deploy.yaml`을 사용하세요 (Lambda zip 파일의 사전 패키징 및 S3 업로드가 필요합니다)."
    ),
    "README.zh-CN.md": (
        "> **注意**: `template.yaml` 用于 SAM CLI（`sam build` + `sam deploy`）。\n"
        "> 如需使用原生 `aws cloudformation deploy` 部署，请改用 `template-deploy.yaml`（需要预先打包 Lambda zip 文件并上传到 S3 存储桶）。"
    ),
    "README.zh-TW.md": (
        "> **注意**: `template.yaml` 用於 SAM CLI（`sam build` + `sam deploy`）。\n"
        "> 如需使用原生 `aws cloudformation deploy` 部署，請改用 `template-deploy.yaml`（需要預先封裝 Lambda zip 檔案並上傳至 S3 儲存貯體）。"
    ),
    "README.fr.md": (
        "> **Remarque** : `template.yaml` est conçu pour être utilisé avec AWS SAM CLI (`sam build` + `sam deploy`).\n"
        "> Pour un déploiement direct avec `aws cloudformation deploy`, utilisez plutôt `template-deploy.yaml` (nécessite de packager au préalable les fichiers zip Lambda et de les téléverser dans un bucket S3)."
    ),
    "README.de.md": (
        "> **Hinweis**: `template.yaml` ist für die Verwendung mit der AWS SAM CLI (`sam build` + `sam deploy`) vorgesehen.\n"
        "> Für eine direkte Bereitstellung mit `aws cloudformation deploy` verwenden Sie stattdessen `template-deploy.yaml` (erfordert das vorherige Packen der Lambda-Zip-Dateien und das Hochladen in einen S3-Bucket)."
    ),
    "README.es.md": (
        "> **Nota**: `template.yaml` está diseñado para usarse con AWS SAM CLI (`sam build` + `sam deploy`).\n"
        "> Para desplegar directamente con `aws cloudformation deploy`, use `template-deploy.yaml` en su lugar (requiere empaquetar previamente los archivos zip de Lambda y subirlos a un bucket de S3)."
    ),
}

MANUAL_ZIP_ANCHOR = 'DEPLOY_BUCKET="<your-deploy-bucket-name>"'


def remove_manual_zip_step(text: str) -> str:
    lines = text.split("\n")
    try:
        idx_bucket = next(i for i, ln in enumerate(lines) if MANUAL_ZIP_ANCHOR in ln)
    except StopIteration:
        return text
    # nearest ### heading before the anchor
    idx_head = next(i for i in range(idx_bucket, -1, -1) if lines[i].startswith("### "))
    m = re.match(r"^### (\d+)\.", lines[idx_head])
    removed_no = int(m.group(1)) if m else None
    # next ### heading after the anchor (start of the following step)
    idx_next = next(i for i in range(idx_bucket + 1, len(lines)) if lines[i].startswith("### "))
    del lines[idx_head:idx_next]
    # renumber later numbered steps (> removed_no) until the next H2 boundary
    if removed_no is not None:
        for i in range(idx_head, len(lines)):
            if lines[i].startswith("## ") and not lines[i].startswith("### "):
                break
            hm = re.match(r"^### (\d+)\.(.*)$", lines[i])
            if hm and int(hm.group(1)) > removed_no:
                lines[i] = f"### {int(hm.group(1)) - 1}.{hm.group(2)}"
    return "\n".join(lines)


def replace_usage_table(text: str, note: str) -> str:
    lines = text.split("\n")
    try:
        idx_row = next(i for i, ln in enumerate(lines) if ln.startswith("| `template.yaml` |"))
    except StopIteration:
        return text
    idx_head = next(i for i in range(idx_row, -1, -1) if lines[i].startswith("### "))
    idx_note = next(i for i in range(idx_row + 1, len(lines)) if "cloudformation deploy" in lines[i])
    new_lines = lines[:idx_head] + [note] + lines[idx_note + 1:]
    return "\n".join(new_lines)


def remove_deploybucket_row(text: str) -> str:
    lines = text.split("\n")
    return "\n".join(ln for ln in lines if not re.match(r"^\|\s*`DeployBucket`\s*\|", ln))


def main() -> int:
    for fname, note in NOTES.items():
        path = PATTERN_DIR / fname
        original = path.read_text()
        text = remove_manual_zip_step(original)
        text = replace_usage_table(text, note)
        text = remove_deploybucket_row(text)
        if text != original:
            path.write_text(text)
            print(f"updated {path.relative_to(ROOT)}")
        else:
            print(f"no change {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
