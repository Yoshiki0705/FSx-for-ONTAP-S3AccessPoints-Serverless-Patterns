#!/usr/bin/env python3
"""Add the canonical SAM/raw-CFn clarifying note to logistics-ocr READMEs that
lack it (zh-CN, zh-TW, fr, de, es), matching the ja/en/ko placement: right
after the `sam deploy` fenced block, before the next `## ` section heading.

Idempotent: skips files that already contain the note.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERN_DIR = ROOT / "solutions" / "industry" / "logistics-ocr"

NOTES: dict[str, str] = {
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


def insert_note(text: str, note: str) -> str:
    if "template-deploy.yaml" in text:
        return text  # already has a note
    lines = text.split("\n")
    try:
        idx_deploy = next(i for i, ln in enumerate(lines) if ln.strip().startswith("sam deploy"))
    except StopIteration:
        return text
    # first H2 heading after the deploy command marks the config-params section
    idx_heading = next((i for i in range(idx_deploy, len(lines)) if lines[i].startswith("## ")), None)
    if idx_heading is None:
        return text
    # ensure a blank line separates the note block from the heading
    new_lines = lines[:idx_heading] + [note, ""] + lines[idx_heading:]
    return "\n".join(new_lines)


def main() -> int:
    for fname, note in NOTES.items():
        path = PATTERN_DIR / fname
        original = path.read_text()
        updated = insert_note(original, note)
        if updated != original:
            path.write_text(updated)
            print(f"updated {path.relative_to(ROOT)}")
        else:
            print(f"no change {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
