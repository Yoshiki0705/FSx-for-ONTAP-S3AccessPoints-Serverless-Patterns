#!/usr/bin/env python3
"""Add author-verified standard Deployment sections to the 6 patterns that had
none, in every language they ship. Each pattern's parameters were verified
against its template.yaml, and `sam build` was confirmed to succeed.

Pattern-specific facts baked in:
  - flexcache/{automotive-cae,gaming-build-pipeline,life-sciences-research}:
    Internet-origin S3AP readers; only S3AccessPointAlias/Name are required.
  - flexcache/rag-enterprise-files: adds a note that ACL extraction needs the
    ONTAP management IP + secret (SharedLayer now packages shared.ontap_client).
  - genai/kb-selfservice-curation: requires a pre-created Bedrock Knowledge Base
    + data source (KnowledgeBaseId/DataSourceId); documents the prerequisite.
  - genai/quick-agentic-workspace: notes the Amazon Quick console post-setup.

Idempotent: skips any README already containing `sam deploy`.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

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
    "md": "AWS SAM CLI でデプロイします（プレースホルダは環境に合わせて置き換えてください）:",
    "en.md": "Deploy with the AWS SAM CLI (replace the placeholders for your environment):",
    "ko.md": "AWS SAM CLI로 배포합니다 (플레이스홀더는 환경에 맞게 교체하세요):",
    "zh-CN.md": "使用 AWS SAM CLI 部署（请将占位符替换为您的环境值）：",
    "zh-TW.md": "使用 AWS SAM CLI 部署（請將佔位符替換為您的環境值）：",
    "fr.md": "Déployez avec AWS SAM CLI (remplacez les valeurs d'exemple selon votre environnement) :",
    "de.md": "Stellen Sie mit der AWS SAM CLI bereit (ersetzen Sie die Platzhalter für Ihre Umgebung):",
    "es.md": "Despliegue con AWS SAM CLI (reemplace los marcadores por los de su entorno):",
}
PREREQ = {
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

# --- pattern-specific extra notes ---
RAG_ACL_NOTE = {
    "md": "> **ファイルレベル ACL 抽出を使う場合**: 実際の ONTAP 連携で ACL を抽出するには、`OntapManagementIp` と `OntapSecretName` も指定してください（VPC 内から ONTAP REST API へ到達できる必要があります）。",
    "en.md": "> **For file-level ACL extraction**: to extract ACLs against a real ONTAP system, also pass `OntapManagementIp` and `OntapSecretName` (the function must reach the ONTAP REST API from within the VPC).",
    "ko.md": "> **파일 수준 ACL 추출 시**: 실제 ONTAP 연동으로 ACL을 추출하려면 `OntapManagementIp`와 `OntapSecretName`도 지정하세요 (VPC 내부에서 ONTAP REST API에 도달할 수 있어야 합니다).",
    "zh-CN.md": "> **使用文件级 ACL 提取时**: 若要针对真实 ONTAP 提取 ACL，请同时传入 `OntapManagementIp` 与 `OntapSecretName`（函数需能从 VPC 内访问 ONTAP REST API）。",
    "zh-TW.md": "> **使用檔案級 ACL 擷取時**: 若要針對真實 ONTAP 擷取 ACL，請同時傳入 `OntapManagementIp` 與 `OntapSecretName`（函式需能從 VPC 內存取 ONTAP REST API）。",
    "fr.md": "> **Pour l'extraction d'ACL au niveau fichier** : pour extraire les ACL depuis un système ONTAP réel, passez également `OntapManagementIp` et `OntapSecretName` (la fonction doit joindre l'API REST ONTAP depuis le VPC).",
    "de.md": "> **Für die ACL-Extraktion auf Dateiebene**: Um ACLs von einem echten ONTAP-System zu extrahieren, übergeben Sie zusätzlich `OntapManagementIp` und `OntapSecretName` (die Funktion muss die ONTAP-REST-API aus dem VPC erreichen).",
    "es.md": "> **Para la extracción de ACL a nivel de archivo**: para extraer ACL de un sistema ONTAP real, pase también `OntapManagementIp` y `OntapSecretName` (la función debe poder alcanzar la API REST de ONTAP desde la VPC).",
}
QUICK_CONSOLE_NOTE = {
    "md": "> **Amazon Quick の設定**: Index 接続・データセット作成・Flows 実行は本テンプレートの範囲外です。デプロイ後に Amazon Quick コンソールで設定してください（[quick-console-setup](docs/quick-console-setup.md) 参照）。",
    "en.md": "> **Amazon Quick setup**: connecting an Index, creating datasets, and running Flows are out of scope for this template. Configure them in the Amazon Quick console after deploy (see [quick-console-setup](docs/quick-console-setup.md)).",
    "ko.md": "> **Amazon Quick 설정**: Index 연결·데이터셋 생성·Flows 실행은 본 템플릿 범위 밖입니다. 배포 후 Amazon Quick 콘솔에서 설정하세요 ([quick-console-setup](docs/quick-console-setup.md) 참조).",
    "zh-CN.md": "> **Amazon Quick 设置**: 连接 Index、创建数据集、运行 Flows 不在本模板范围内。部署后请在 Amazon Quick 控制台中配置（参见 [quick-console-setup](docs/quick-console-setup.md)）。",
    "zh-TW.md": "> **Amazon Quick 設定**: 連接 Index、建立資料集、執行 Flows 不在本範本範圍內。部署後請在 Amazon Quick 主控台中設定（參見 [quick-console-setup](docs/quick-console-setup.md)）。",
    "fr.md": "> **Configuration Amazon Quick** : la connexion d'un Index, la création de jeux de données et l'exécution de Flows sont hors du périmètre de ce modèle. Configurez-les dans la console Amazon Quick après le déploiement (voir [quick-console-setup](docs/quick-console-setup.md)).",
    "de.md": "> **Amazon-Quick-Konfiguration**: Das Verbinden eines Index, das Erstellen von Datasets und das Ausführen von Flows liegen außerhalb des Umfangs dieser Vorlage. Konfigurieren Sie sie nach der Bereitstellung in der Amazon-Quick-Konsole (siehe [quick-console-setup](docs/quick-console-setup.md)).",
    "es.md": "> **Configuración de Amazon Quick**: conectar un Index, crear conjuntos de datos y ejecutar Flows quedan fuera del alcance de esta plantilla. Configúrelos en la consola de Amazon Quick tras el despliegue (consulte [quick-console-setup](docs/quick-console-setup.md)).",
}
# KB prerequisite preamble (paragraph shown BEFORE the deploy block)
KB_PREREQ = {
    "md": "> **デプロイ前提**: 本テンプレートは既存の Amazon Bedrock Knowledge Base とデータソース（S3 AP 接続）を前提とします。OpenSearch Serverless のベクトルインデックス作成が CloudFormation ネイティブではないため、Knowledge Base 本体はデプロイ前に作成し、その `KnowledgeBaseId` / `DataSourceId` をパラメータに渡します（リポジトリルートの `scripts/create_bedrock_kb.py` または Bedrock コンソールで作成）。",
    "en.md": "> **Deployment prerequisite**: this template assumes an existing Amazon Bedrock Knowledge Base and data source (connected to the S3 AP). Because OpenSearch Serverless vector index creation is not CloudFormation-native, create the Knowledge Base first and pass its `KnowledgeBaseId` / `DataSourceId` as parameters (use `scripts/create_bedrock_kb.py` from the repo root, or the Bedrock console).",
    "ko.md": "> **배포 전제**: 본 템플릿은 기존 Amazon Bedrock Knowledge Base와 데이터 소스(S3 AP 연결)를 전제로 합니다. OpenSearch Serverless 벡터 인덱스 생성이 CloudFormation 네이티브가 아니므로, Knowledge Base를 먼저 생성하고 그 `KnowledgeBaseId` / `DataSourceId`를 파라미터로 전달하세요 (리포지토리 루트의 `scripts/create_bedrock_kb.py` 또는 Bedrock 콘솔 사용).",
    "zh-CN.md": "> **部署前提**: 本模板假设已存在 Amazon Bedrock Knowledge Base 及数据源（连接到 S3 AP）。由于 OpenSearch Serverless 向量索引创建并非 CloudFormation 原生支持，请先创建 Knowledge Base，并将其 `KnowledgeBaseId` / `DataSourceId` 作为参数传入（使用仓库根目录的 `scripts/create_bedrock_kb.py` 或 Bedrock 控制台）。",
    "zh-TW.md": "> **部署前提**: 本範本假設已存在 Amazon Bedrock Knowledge Base 及資料來源（連接到 S3 AP）。由於 OpenSearch Serverless 向量索引建立並非 CloudFormation 原生支援，請先建立 Knowledge Base，並將其 `KnowledgeBaseId` / `DataSourceId` 作為參數傳入（使用儲存庫根目錄的 `scripts/create_bedrock_kb.py` 或 Bedrock 主控台）。",
    "fr.md": "> **Prérequis de déploiement** : ce modèle suppose une Amazon Bedrock Knowledge Base et une source de données existantes (connectées au S3 AP). La création d'index vectoriel OpenSearch Serverless n'étant pas native à CloudFormation, créez d'abord la Knowledge Base et passez ses `KnowledgeBaseId` / `DataSourceId` en paramètres (via `scripts/create_bedrock_kb.py` à la racine du dépôt, ou la console Bedrock).",
    "de.md": "> **Bereitstellungsvoraussetzung**: Diese Vorlage setzt eine vorhandene Amazon Bedrock Knowledge Base und Datenquelle (mit dem S3 AP verbunden) voraus. Da die Erstellung des OpenSearch-Serverless-Vektorindex nicht CloudFormation-nativ ist, erstellen Sie die Knowledge Base zuerst und übergeben deren `KnowledgeBaseId` / `DataSourceId` als Parameter (mit `scripts/create_bedrock_kb.py` im Repo-Stammverzeichnis oder der Bedrock-Konsole).",
    "es.md": "> **Requisito de despliegue**: esta plantilla asume una Amazon Bedrock Knowledge Base y una fuente de datos existentes (conectadas al S3 AP). Como la creación del índice vectorial de OpenSearch Serverless no es nativa de CloudFormation, cree primero la Knowledge Base y pase sus `KnowledgeBaseId` / `DataSourceId` como parámetros (use `scripts/create_bedrock_kb.py` desde la raíz del repositorio, o la consola de Bedrock).",
}

# Per-pattern deploy configuration: stack name + the --parameter-overrides lines.
PATTERNS: dict[str, dict] = {
    "flexcache/automotive-cae": {
        "stack": "fsxn-automotive-cae",
        "params": [
            "S3AccessPointAlias=<your-s3ap-alias>",
            "S3AccessPointName=<your-s3ap-name>",
            "NotificationEmail=<your-email@example.com>",
        ],
    },
    "flexcache/gaming-build-pipeline": {
        "stack": "fsxn-gaming-build-pipeline",
        "params": [
            "S3AccessPointAlias=<your-s3ap-alias>",
            "S3AccessPointName=<your-s3ap-name>",
            "NotificationEmail=<your-email@example.com>",
        ],
    },
    "flexcache/life-sciences-research": {
        "stack": "fsxn-life-sciences-research",
        "params": [
            "S3AccessPointAlias=<your-s3ap-alias>",
            "S3AccessPointName=<your-s3ap-name>",
            "NotificationEmail=<your-email@example.com>",
        ],
    },
    "flexcache/rag-enterprise-files": {
        "stack": "fsxn-rag-enterprise-files",
        "params": [
            "S3AccessPointAlias=<your-s3ap-alias>",
            "S3AccessPointName=<your-s3ap-name>",
            "NotificationEmail=<your-email@example.com>",
        ],
        "extra_note": RAG_ACL_NOTE,
    },
    "genai/kb-selfservice-curation": {
        "stack": "fsxn-kb-selfservice-curation",
        "params": [
            "S3AccessPointAlias=<your-s3ap-alias>",
            "S3AccessPointName=<your-s3ap-name>",
            "KnowledgeBaseId=<your-kb-id>",
            "DataSourceId=<your-datasource-id>",
            "NotificationEmail=<your-email@example.com>",
        ],
        "preamble": KB_PREREQ,
    },
    "genai/quick-agentic-workspace": {
        "stack": "fsxn-quick-agentic-workspace",
        "params": [
            "S3AccessPointAlias=<your-s3ap-alias>",
            "S3AccessPointName=<your-s3ap-name>",
            "NotificationEmail=<your-email@example.com>",
        ],
        "extra_note": QUICK_CONSOLE_NOTE,
    },
}


def suffix_of(path: Path) -> str:
    return "md" if path.name == "README.md" else path.name[len("README.") :]


def code_block(suf: str, stack: str, params: list[str]) -> list[str]:
    lines = [
        "```bash",
        PREREQ[suf],
        "sam build",
        "",
        "sam deploy \\",
        f"  --stack-name {stack} \\",
        "  --parameter-overrides \\",
    ]
    for p in params:
        lines.append(f"    {p} \\")
    lines += ["  --capabilities CAPABILITY_NAMED_IAM \\", "  --resolve-s3 \\", "  --region <your-region>", "```"]
    return lines


def build_section(suf: str, cfg: dict) -> list[str]:
    out = [HEADING[suf], "", INTRO[suf], ""]
    if "preamble" in cfg:
        out += [cfg["preamble"][suf], ""]
    out += code_block(suf, cfg["stack"], cfg["params"])
    out += ["", NOTE[suf]]
    if "extra_note" in cfg:
        out += ["", cfg["extra_note"][suf]]
    out += [""]
    return out


def insert_section(text: str, section: list[str]) -> str:
    lines = text.split("\n")
    h2 = [i for i, ln in enumerate(lines) if ln.startswith("## ")]
    if not h2:
        return text.rstrip("\n") + "\n\n" + "\n".join(section).rstrip("\n") + "\n"
    at = h2[-1]
    return "\n".join(lines[:at] + section + lines[at:])


def main() -> int:
    changed = 0
    for pat, cfg in PATTERNS.items():
        d = ROOT / "solutions" / pat
        for md in sorted(list(d.glob("README.md")) + list(d.glob("README.*.md"))):
            suf = suffix_of(md)
            if suf not in HEADING:
                continue
            text = md.read_text()
            if "sam deploy" in text:
                continue
            md.write_text(insert_section(text, build_section(suf, cfg)))
            changed += 1
            print(f"deploy section added -> {md.relative_to(ROOT)}")
    print(f"\n{changed} file(s) updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
