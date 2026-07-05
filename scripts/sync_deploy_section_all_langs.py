#!/usr/bin/env python3
"""Bring the SAM deploy instructions to parity across all language READMEs.

Many patterns have a canonical full Japanese README (README.md) with a
`sam build && sam deploy` section, while the other-language READMEs are
summary-level and lack any deploy section. This script reuses each pattern's
own Japanese deploy code block (parameters are accurate and language-agnostic —
they are placeholders) and inserts a localized "Deployment" section into every
language README that is missing one.

Localized: section heading, one intro line, the in-block SAM prerequisite
comment, and the canonical template.yaml/template-deploy.yaml note.
Language-agnostic and reused verbatim: the `sam build` / `sam deploy` commands.

Idempotent: skips any README that already contains `sam deploy`.
Self-limiting: patterns whose Japanese README has no `sam deploy` block
(pure design-guide patterns) are skipped automatically.
"""

from __future__ import annotations

import glob
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# suffix -> localized strings
HEADING = {
    "md": "## デプロイ",
    "en.md": "## Deployment",
    "ko.md": "## 배포",
    "zh-CN.md": "## 部署",
    "zh-TW.md": "## 部署",
    "fr.md": "## Déploiement",
    "de.md": "## Bereitstellung",
    "es.md": "## Despliegue",
}
INTRO = {
    "md": "AWS SAM CLI でデプロイします（パラメータは環境に合わせて置き換えてください）:",
    "en.md": "Deploy with the AWS SAM CLI (replace the placeholder parameters for your environment):",
    "ko.md": "AWS SAM CLI로 배포합니다 (파라미터는 환경에 맞게 교체하세요):",
    "zh-CN.md": "使用 AWS SAM CLI 部署（请将占位参数替换为您的环境值）：",
    "zh-TW.md": "使用 AWS SAM CLI 部署（請將佔位參數替換為您的環境值）：",
    "fr.md": "Déployez avec AWS SAM CLI (remplacez les paramètres d'exemple selon votre environnement) :",
    "de.md": "Stellen Sie mit der AWS SAM CLI bereit (ersetzen Sie die Platzhalter-Parameter für Ihre Umgebung):",
    "es.md": "Despliegue con AWS SAM CLI (reemplace los parámetros de ejemplo por los de su entorno):",
}
PREREQ_COMMENT = {
    "md": "# 前提: AWS SAM CLI が必要です。sam build がコードと共有レイヤーを自動でパッケージングします。",
    "en.md": "# Prerequisite: AWS SAM CLI required. 'sam build' packages the code and shared layer automatically.",
    "ko.md": "# 전제 조건: AWS SAM CLI 필요. 'sam build'가 코드와 공유 레이어를 자동으로 패키징합니다.",
    "zh-CN.md": "# 前提条件：需要 AWS SAM CLI。'sam build' 会自动打包代码和共享层。",
    "zh-TW.md": "# 前提條件：需要 AWS SAM CLI。'sam build' 會自動封裝程式碼與共用層。",
    "fr.md": "# Prérequis : AWS SAM CLI requis. « sam build » empaquette automatiquement le code et la couche partagée.",
    "de.md": "# Voraussetzung: AWS SAM CLI erforderlich. „sam build“ verpackt Code und Shared Layer automatisch.",
    "es.md": "# Requisito: se necesita AWS SAM CLI. «sam build» empaqueta automáticamente el código y la capa compartida.",
}
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
    name = path.name
    if name == "README.md":
        return "md"
    return name[len("README.") :]


def extract_ja_deploy_block(ja_text: str) -> list[str] | None:
    """Return the lines of the first ```bash fenced block that contains
    `sam deploy` (i.e. the main deploy command, not `sam local invoke`)."""
    lines = ja_text.split("\n")
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith("```"):
            start = i
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("```"):
                j += 1
            block = lines[start : j + 1]
            if any("sam deploy" in ln for ln in block):
                return block
            i = j + 1
        else:
            i += 1
    return None


def localize_block(block: list[str], suf: str) -> list[str]:
    out = []
    for ln in block:
        if re.match(r"^#\s*前提", ln):
            out.append(PREREQ_COMMENT[suf])
        else:
            out.append(ln)
    return out


def build_section(suf: str, block: list[str]) -> list[str]:
    return [HEADING[suf], "", INTRO[suf], "", *localize_block(block, suf), "", NOTE[suf], ""]


def insert_section(text: str, section: list[str]) -> str:
    lines = text.split("\n")
    h2_idx = [i for i, ln in enumerate(lines) if ln.startswith("## ")]
    if not h2_idx:
        # no H2 at all: append
        return text.rstrip("\n") + "\n\n" + "\n".join(section).rstrip("\n") + "\n"
    insert_at = h2_idx[-1]  # before the last top-level section
    new_lines = lines[:insert_at] + section + lines[insert_at:]
    return "\n".join(new_lines)


def main() -> int:
    changed = 0
    for tpl in sorted(glob.glob(str(ROOT / "solutions" / "**" / "template.yaml"), recursive=True)):
        if ".aws-sam" in tpl:
            continue
        d = Path(tpl).parent
        ja = d / "README.md"
        if not ja.exists():
            continue
        block = extract_ja_deploy_block(ja.read_text())
        if block is None:
            continue  # design-guide pattern with no deploy command; skip
        for md in sorted(d.glob("README.*.md")):
            suf = suffix_of(md)
            if suf not in HEADING:
                continue
            text = md.read_text()
            if "sam deploy" in text:
                continue  # already has deploy instructions
            section = build_section(suf, block)
            md.write_text(insert_section(text, section))
            changed += 1
            print(f"added deploy section -> {md.relative_to(ROOT)}")
    print(f"\n{changed} file(s) updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
